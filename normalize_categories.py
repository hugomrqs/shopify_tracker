#!/usr/bin/env python3
"""Map tracked products onto Soeur's internal taxonomy (FN4 catégorie /
FN5 sous-catégorie) and publish the result as `products_normalized` — the
collection the dashboard actually reads from. This is the "silver" layer
on top of the raw "bronze" `products` collection written by crawler/main.py:
every raw product stays in `products` untouched; only products that
resolve to a category (see INCLUDED_STATUSES below) get mirrored into
`products_normalized`, so the site never has to filter out unmapped junk
itself.

This is a separate, rerunnable step — not part of the crawl itself —
precisely so the mapping rules can be corrected and re-applied without
re-crawling anything. It's invoked automatically at the end of
crawler/main.py's daily run, and can also be run standalone.

Resolution order, per product (see README/AGENTS notes for the full
rationale):
  1. Direct lookup: `taxonomy/mappings/<brand-slug>.json` maps the
     product's `product_type` (Shopify's own category field — the closest
     thing to a breadcrumb this data source has, see note below) to either
     {"fn4": ..., "fn5": ...} or {"out_of_scope": true}. Authoritative,
     highest-confidence path. Only brands with a mapping file get this
     step; drop a new `<brand-slug>.json` in taxonomy/mappings/ to add
     coverage for another brand, no code change needed.
  2. Fuzzy fallback on the product *title* (see crawler/category_matching.py)
     when product_type has no dictionary entry, is missing, or is too
     generic. Tagged "mapped_from_name" at >=90% confidence,
     "low_confidence" below that (still assigned, but flagged for manual
     review), score kept on the document either way.
  3. Neither resolves -> category: None, status "unmapped". Nothing is
     silently guessed past the confidence floor.

Why `product_type` instead of a real breadcrumb: unlike fashion_crawler
(which scrapes full breadcrumb trails via Scrapy), this project only reads
Shopify's public /products.json, which exposes a single flat
`product_type` string per product and no category tree. It's used here as
a one-level "breadcrumb" for the same dictionary-lookup approach.

Usage:
    python3 normalize_categories.py              # full rescan, apply + report
    python3 normalize_categories.py --dry-run     # report only, no writes
    python3 normalize_categories.py --new-only    # only resolve products not yet
                                                    # in products_normalized (what
                                                    # the automated daily job uses)
"""
import argparse
import json
import logging
import os
import re
from collections import Counter
from pathlib import Path

from crawler import firestore_store
from crawler.category_matching import (
    HIGH_CONFIDENCE_THRESHOLD,
    guess_category_from_name,
    is_known_taxonomy_gap,
    is_out_of_scope_by_name,
)
from crawler.taxonomy import load_fn4, load_fn5

logger = logging.getLogger(__name__)

MAPPINGS_DIR = Path(__file__).resolve().parent / "taxonomy" / "mappings"

# Statuses that qualify a product for products_normalized (and therefore
# for display on the site). out_of_scope and unmapped stay in `products`
# only. Low-confidence guesses are included (flagged) rather than held
# back, so coverage stays high while category_mapping_status still lets
# the site/ops prioritize which ones to review or add a dictionary for.
INCLUDED_STATUSES = {"mapped", "mapped_from_name", "low_confidence"}


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def load_mapping(brand: str) -> dict:
    path = MAPPINGS_DIR / f"{_slugify(brand)}.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve(doc: dict, mapping: dict, fn4: dict, fn5: dict) -> tuple[dict, str]:
    """Return (update_dict, status) for one product document."""
    key = doc.get("product_type") or ""
    rule = mapping.get(key)

    if rule and rule.get("out_of_scope"):
        return {"category": None, "category_mapping_status": "out_of_scope"}, "out_of_scope"

    if rule:
        fn4_code, fn5_code = rule.get("fn4"), rule.get("fn5")
        category = {
            "fn4_code": fn4_code,
            "fn4_label": fn4.get(fn4_code),
            "fn5_code": fn5_code,
            "fn5_label": fn5.get(fn5_code) if fn5_code else None,
        }
        return {"category": category, "category_mapping_status": "mapped"}, "mapped"

    title = doc.get("title")

    if is_out_of_scope_by_name(title):
        return {"category": None, "category_mapping_status": "out_of_scope"}, "out_of_scope"

    if is_known_taxonomy_gap(title):
        return {"category": None, "category_mapping_status": "unmapped"}, "unmapped"

    guessed_fn4, guessed_fn5, score = guess_category_from_name(title)
    if guessed_fn4:
        status = "mapped_from_name" if score >= HIGH_CONFIDENCE_THRESHOLD else "low_confidence"
        category = {
            "fn4_code": guessed_fn4,
            "fn4_label": fn4.get(guessed_fn4),
            "fn5_code": guessed_fn5,
            "fn5_label": fn5.get(guessed_fn5) if guessed_fn5 else None,
            "confidence": round(score, 2),
        }
        return {"category": category, "category_mapping_status": status}, status

    return {"category": None, "category_mapping_status": "unmapped"}, "unmapped"


def run(db, dry_run: bool = False, new_only: bool = False) -> None:
    """Resolve categories for products in the `products` (bronze) collection
    and publish qualifying ones to `products_normalized` (silver).

    `new_only=True` only resolves products that have never been written to
    `products_normalized` before (i.e. new since the last run) — cheap,
    used by the automated daily job in crawler/main.py so an unchanged
    catalog doesn't cost a Firestore write per product every day. Products
    already in `products_normalized`, or already known `unmapped`/
    `out_of_scope` from a prior run, are left untouched either way.

    `new_only=False` (the default for manual CLI runs) re-resolves every
    product from scratch — needed after editing a taxonomy dictionary or
    the FN4/FN5 codebook, so corrections retroactively reclassify products
    that were previously unmapped or mis-mapped.
    """
    fn4, fn5 = load_fn4(), load_fn5()
    mapping_cache: dict[str, dict] = {}

    status_counts: dict[str, Counter] = {}
    unmapped_samples: dict[str, Counter] = {}
    skipped_counts: dict[str, int] = {}

    raw_ref = db.collection("products")
    normalized_ref = db.collection("products_normalized")

    existing_normalized_ids = {doc.id for doc in normalized_ref.stream()}

    for doc_snap in raw_ref.stream():
        doc = doc_snap.to_dict()
        brand = doc.get("brand", "")
        if brand not in mapping_cache:
            mapping_cache[brand] = load_mapping(brand)
            status_counts[brand] = Counter()
            unmapped_samples[brand] = Counter()
            skipped_counts[brand] = 0

        already_normalized = doc_snap.id in existing_normalized_ids
        if new_only and already_normalized:
            skipped_counts[brand] += 1
            continue

        mapping = mapping_cache[brand]
        update, status = resolve(doc, mapping, fn4, fn5)
        status_counts[brand][status] += 1
        if status == "unmapped":
            unmapped_samples[brand][doc.get("product_type") or "(none)"] += 1

        if dry_run:
            continue

        if status in INCLUDED_STATUSES:
            normalized_doc = {**doc, **update}
            normalized_ref.document(doc_snap.id).set(normalized_doc)
        elif already_normalized:
            # Was previously included (e.g. product_type changed since the
            # last full rescan) and no longer qualifies — clean it up. Skip
            # the delete call entirely when it was never there, so a full
            # rescan doesn't cost a wasted delete op per unmapped product.
            normalized_ref.document(doc_snap.id).delete()

    print(f"{'[DRY RUN] ' if dry_run else ''}Category normalization summary{' (new products only)' if new_only else ''}:")
    for brand in sorted(status_counts):
        counts = status_counts[brand]
        total = sum(counts.values())
        breakdown = ", ".join(f"{status}: {n}" for status, n in counts.most_common())
        has_dictionary = "yes" if mapping_cache[brand] else "no"
        skipped = skipped_counts[brand]
        skipped_note = f", {skipped} already normalized (skipped)" if skipped else ""
        print(f"  {brand:<20} {total} products — {breakdown} (dictionary: {has_dictionary}){skipped_note}")
        if counts["unmapped"]:
            print(f"    Unmapped product_types (add to taxonomy/mappings/{_slugify(brand)}.json or extend name matching):")
            for key, count in unmapped_samples[brand].most_common(15):
                print(f"      [{count:>4}] {key!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="report only, don't write to Firestore")
    parser.add_argument(
        "--new-only",
        action="store_true",
        help="only resolve products not yet in products_normalized (skip a full rescan)",
    )
    args = parser.parse_args()

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    db = firestore_store.get_client(project_id)
    run(db, dry_run=args.dry_run, new_only=args.new_only)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
