"""Fetch every product from a Shopify store's public /products.json endpoint."""

import logging
import time

import requests

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; SoeurMarketWatch/1.0; contact hmarques@soeur.fr)"
PAGE_LIMIT = 250
MAX_PAGES = 200
DELAY_SECONDS = 0.5
TIMEOUT_SECONDS = 30


def fetch_all_products(base_url: str) -> list[dict]:
    """Page through {base_url}/products.json until an empty page is returned."""
    products = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    for page in range(1, MAX_PAGES + 1):
        resp = session.get(
            f"{base_url}/products.json",
            params={"page": page, "limit": PAGE_LIMIT},
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break

        products.extend(batch)
        logger.info("%s: page %d -> %d products (total %d)", base_url, page, len(batch), len(products))

        if len(batch) < PAGE_LIMIT:
            break
        time.sleep(DELAY_SECONDS)

    return products
