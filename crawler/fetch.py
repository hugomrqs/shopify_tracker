"""Fetch every product from a Shopify store's public /products.json endpoint."""

import logging
import time
from urllib.parse import urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; SoeurMarketWatch/1.0; contact hmarques@soeur.fr)"
PAGE_LIMIT = 250
MAX_PAGES = 200
DELAY_SECONDS = 0.5
TIMEOUT_SECONDS = 30


def _products_url(base_url: str) -> str:
    # `/products.json` must go on the path, before any `?country=XX` query:
    # appending it to the raw string turned the URL into `/?country=GB/products.json`,
    # which served the homepage HTML instead of JSON.
    parts = urlsplit(base_url)
    path = parts.path.rstrip("/") + "/products.json"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def fetch_all_products(base_url: str) -> tuple[list[dict], str | None]:
    """Page through {base_url}/products.json until an empty page is returned.

    Shopify Markets serves each market domain with prices already converted
    to that market's currency (same product/variant ids as the home store).
    The currency isn't in the JSON payload itself, but the store sets it on
    the `cart_currency` cookie on every response, so we read it from there
    instead of hardcoding a currency per domain.
    """
    products = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    currency = None

    for page in range(1, MAX_PAGES + 1):
        resp = session.get(
            _products_url(base_url),
            params={"page": page, "limit": PAGE_LIMIT},
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        if currency is None:
            currency = session.cookies.get("cart_currency")

        batch = resp.json().get("products", [])
        if not batch:
            break

        products.extend(batch)
        logger.info("%s: page %d -> %d products (total %d)", base_url, page, len(batch), len(products))

        if len(batch) < PAGE_LIMIT:
            break
        time.sleep(DELAY_SECONDS)

    return products, currency
