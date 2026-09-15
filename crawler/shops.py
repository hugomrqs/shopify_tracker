"""Shopify shops to track.

Each site is confirmed Shopify: /products.json responds with real product
data (verified with curl, not just inferred from the old fashion_crawler
audit — that README turned out to be wrong about Sessun, see below).
`base_url` must be the domain that actually serves /products.json (no
trailing slash).

Sessun (fr.sessun.com) was in the original candidate list but is NOT
Shopify (404 on /products.json; cookies/headers show a custom CodeIgniter
PHP backend) — excluded.
"""

SHOPS = [
    {"brand": "Rouje", "base_url": "https://www.rouje.com"},
    {"brand": "Dries Van Noten", "base_url": "https://www.driesvannoten.com"},
    {"brand": "Soeur", "base_url": "https://www.soeur.fr"},
    {"brand": "A.P.C.", "base_url": "https://www.apc.fr"},
    {"brand": "Isabel Marant", "base_url": "https://www.isabelmarant.com"},
    {"brand": "Roseanna", "base_url": "https://roseanna.fr"},
]
