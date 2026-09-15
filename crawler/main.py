"""Entry point: crawl every configured Shopify shop and store results in Firestore.

Run locally:
    GOOGLE_CLOUD_PROJECT=<project-id> python -m crawler.main
(requires `gcloud auth application-default login` for local credentials)
"""

import logging
import os
from datetime import date

from crawler import firestore_store
from crawler.fetch import fetch_all_products
from crawler.shops import SHOPS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    db = firestore_store.get_client(project_id)
    run_date = date.today().isoformat()

    summary = {}
    for shop in SHOPS:
        brand, base_url = shop["brand"], shop["base_url"]
        try:
            products = fetch_all_products(base_url)
            for product in products:
                firestore_store.upsert_product(db, brand, base_url, product, run_date)
            summary[brand] = len(products)
            logger.info("%s: stored %d products", brand, len(products))
        except Exception:
            logger.exception("%s: crawl failed", brand)
            summary[brand] = "FAILED"

    logger.info("Run %s summary: %s", run_date, summary)


if __name__ == "__main__":
    main()
