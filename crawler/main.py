"""Entry point: crawl every configured Shopify shop and store results in Firestore.

Run locally:
    GOOGLE_CLOUD_PROJECT=<project-id> python -m crawler.main
(requires `gcloud auth application-default login` for local credentials)
"""

import logging
import os
import time
from datetime import date

from crawler import firestore_store
from crawler.fetch import fetch_all_products
from crawler.shops import SHOPS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MARKET_DELAY_SECONDS = 2


def main() -> None:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    db = firestore_store.get_client(project_id)
    run_date = date.today().isoformat()

    summary = {}
    for shop in SHOPS:
        brand = shop["brand"]
        market_results = {}
        for i, base_url in enumerate(shop["markets"]):
            try:
                products, currency = fetch_all_products(base_url)
                for product in products:
                    firestore_store.upsert_product(
                        db, brand, base_url, currency, product, run_date, is_home_market=(i == 0)
                    )
                market_results[base_url] = f"{len(products)} products ({currency})"
                logger.info("%s / %s: stored %d products (%s)", brand, base_url, len(products), currency)
            except Exception:
                logger.exception("%s / %s: crawl failed", brand, base_url)
                market_results[base_url] = "FAILED"
            time.sleep(MARKET_DELAY_SECONDS)
        summary[brand] = market_results

    logger.info("Run %s summary: %s", run_date, summary)


if __name__ == "__main__":
    main()
