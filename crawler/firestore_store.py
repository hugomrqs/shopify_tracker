"""Persist Shopify products to Firestore.

Data model:
  products/{brand-slug}_{shopify_product_id}
    - current product state (title, variants, prices, images, ...)
    - first_seen_at / last_seen_at
    products/{doc}/snapshots/{run_date}
      - price + availability snapshot for that crawl run, so price history
        can be reconstructed later without re-crawling.
"""

import logging
import re
from datetime import datetime, timezone

from google.cloud import firestore

logger = logging.getLogger(__name__)


def get_client(project_id: str | None = None) -> firestore.Client:
    return firestore.Client(project=project_id)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


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


def upsert_product(db: firestore.Client, brand: str, base_url: str, product: dict, run_date: str) -> None:
    doc_id = f"{_slugify(brand)}_{product['id']}"
    ref = db.collection("products").document(doc_id)

    variants = product.get("variants", [])
    prices = [float(v["price"]) for v in variants if v.get("price") not in (None, "")]
    now = datetime.now(timezone.utc)

    doc_data = {
        "brand": brand,
        "domain": base_url,
        "shopify_id": product.get("id"),
        "handle": product.get("handle"),
        "title": product.get("title"),
        "vendor": product.get("vendor"),
        "product_type": product.get("product_type"),
        "tags": product.get("tags", []),
        "published_at": product.get("published_at"),
        "created_at_shopify": product.get("created_at"),
        "updated_at_shopify": product.get("updated_at"),
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
        "images": [img.get("src") for img in product.get("images", [])],
        "options": product.get("options", []),
        "variants": _variant_summary(variants),
        "source_url": f"{base_url}/products/{product.get('handle')}",
        "last_seen_at": now,
        "last_crawl_date": run_date,
    }

    existing = ref.get()
    if not existing.exists:
        doc_data["first_seen_at"] = now

    ref.set(doc_data, merge=True)
    ref.collection("snapshots").document(run_date).set(
        {
            "min_price": doc_data["min_price"],
            "max_price": doc_data["max_price"],
            "variants": doc_data["variants"],
            "captured_at": now,
        }
    )
