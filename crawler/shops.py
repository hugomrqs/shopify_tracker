"""Shopify shops to track.

Each site is confirmed Shopify: /products.json responds with real product
data (verified with curl, not just inferred from the old fashion_crawler
audit — that README turned out to be wrong about Sessun, see below).

`markets` lists every domain to crawl for that brand. The first entry is
the "home" market (used for the top-level/default price shown in the
dashboard); any extra entries are other Shopify Markets domains of the
*same* shop serving prices pre-converted to a local currency (verified: same
product/variant ids as the home domain, currency read from the
`cart_currency` cookie at crawl time — see crawler/fetch.py). Soeur alone
exposes ~40 such market domains; we only track the ones actually asked for
(FR/CH/UK) to avoid hammering the site for markets nobody looks at — add
more here if needed, no code change required.

Sessun (fr.sessun.com) was in the original candidate list but is NOT
Shopify (404 on /products.json; cookies/headers show a custom CodeIgniter
PHP backend) — excluded.
"""

SHOPS = [
    {"brand": "Rouje", "markets": ["https://www.rouje.com"]},
    {"brand": "Dries Van Noten", "markets": ["https://www.driesvannoten.com"]},
    {
        "brand": "Soeur",
        "markets": [
            "https://www.soeur.fr",
            "https://ch.soeur.fr",
            "https://www.soeur.uk",
        ],
    },
    {"brand": "A.P.C.", "markets": ["https://www.apc.fr"]},
    {"brand": "Isabel Marant", "markets": ["https://www.isabelmarant.com"]},
    {"brand": "Roseanna", "markets": ["https://roseanna.fr"]},
]
