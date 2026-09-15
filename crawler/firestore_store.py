"""Persist Shopify products to Firestore.

Data model:
  products/{brand-slug}_{home_market_shopify_id}
    - brand, shopify_id, handle, vendor, product_type, tags, images, options
      (identity fields — always taken from the *home* market; see
      crawler/main.py's handle_to_home_id for how secondary markets, which
      can be a wholly different Shopify instance with different ids, still
      resolve to this same doc)
    - min_price, max_price, variants, source_url  (mirror of the home
      market — kept at top level for convenience/backward compatibility)
    - markets: { <market-key>: { currency, domain, shopify_id, handle,
      title, min_price, max_price, variants, source_url, available } }
      one entry per crawled market, since Shopify Markets serves each one
      with prices already converted to its local currency.
    - first_seen_at / last_seen_at

    products/{doc}/snapshots/{run_date}
      - markets: { <market-key>: { min_price, max_price, variants } }
      - captured_at
      one doc per run, so price history per market can be reconstructed
      without re-crawling.
"""

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from google.cloud import firestore

logger = logging.getLogger(__name__)


def get_client(project_id: str | None = None) -> firestore.Client:
    return firestore.Client(project=project_id)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _market_key(base_url: str) -> str:
    # Must include the path: some brands use the *same* host for every
    # market (rouje.com, rouje.com/en-gb, rouje.com/en-ch) — keying on
    # netloc alone collapses them all into one entry.
    parsed = urlparse(base_url)
    return _slugify(f"{parsed.netloc}{parsed.path}")


def _variant_summary(variants: list[dict]) -> list[dict]:
    return [
        {
            "id": v.get("id"),
            "title": v.get("title"),
            "sku": v.get("sku"),
            "price": v.get("price"),
            "compare_at_price": v.get("compare_at_price"),
            "available": v.get("available"),
            "option1": v.get("option1"),
            "option2": v.get("option2"),
            "option3": v.get("option3"),
        }
        for v in variants
    ]


def upsert_product(
    db: firestore.Client,
    brand: str,
    base_url: str,
    currency: str | None,
    product: dict,
    run_date: str,
    is_home_market: bool,
    doc_shopify_id: int | str | None = None,
) -> None:
    """Upsert one product's data for one market.

    `doc_shopify_id` lets the caller pin the Firestore doc id to the *home*
    market's product id even when this market's own id differs (Isabel
    Marant's intl storefront is a separate Shopify instance with different
    ids for the same handle — see crawler/shops.py). Defaults to this
    product's own id, which is correct whenever markets share ids.
    """
    doc_id = f"{_slugify(brand)}_{doc_shopify_id if doc_shopify_id is not None else product['id']}"
    ref = db.collection("products").document(doc_id)
    market_key = _market_key(base_url)

    variants = product.get("variants", [])
    prices = [float(v["price"]) for v in variants if v.get("price") not in (None, "")]
    now = datetime.now(timezone.utc)

    market_entry = {
        "currency": currency,
        "domain": base_url,
        "shopify_id": product.get("id"),
        "handle": product.get("handle"),
        "title": product.get("title"),
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
        "available": any(v.get("available") for v in variants),
        "variants": _variant_summary(variants),
        "source_url": f"{base_url}/products/{product.get('handle')}",
    }

    # Only the home market is treated as the source of truth for identity
    # fields — a secondary market (different locale, possibly a different
    # Shopify instance entirely) must never overwrite them.
    doc_data = {
        "brand": brand,
        "markets": {market_key: market_entry},
        "last_seen_at": now,
        "last_crawl_date": run_date,
    }

    if is_home_market:
        doc_data.update(
            {
                "shopify_id": product.get("id"),
                "handle": product.get("handle"),
                "vendor": product.get("vendor"),
                "product_type": product.get("product_type"),
                "tags": product.get("tags", []),
                "published_at": product.get("published_at"),
                "created_at_shopify": product.get("created_at"),
                "updated_at_shopify": product.get("updated_at"),
                "images": [img.get("src") for img in product.get("images", [])],
                "options": product.get("options", []),
                "title": market_entry["title"],
                "min_price": market_entry["min_price"],
                "max_price": market_entry["max_price"],
                "variants": market_entry["variants"],
                "source_url": market_entry["source_url"],
            }
        )

    existing = ref.get()
    if not existing.exists:
        doc_data["first_seen_at"] = now

    ref.set(doc_data, merge=True)
    ref.collection("snapshots").document(run_date).set(
        {
            "markets": {
                market_key: {
                    "min_price": market_entry["min_price"],
                    "max_price": market_entry["max_price"],
                    "variants": market_entry["variants"],
                }
            },
            "captured_at": now,
        },
        merge=True,
    )
