"""Shopify shops to track.

Each site is confirmed Shopify: /products.json responds with real product
data (verified with curl, not just inferred from the old fashion_crawler
audit — that README turned out to be wrong about Sessun, see below).

`markets` lists every domain (or domain+path prefix) to crawl for that
brand. The first entry is the "home" market (used for the top-level/default
price shown in the dashboard); any extra entries are other Shopify Markets
locales serving prices pre-converted to a local currency. Two different
mechanisms are in use, both verified with curl/python rather than guessed:

- subdomain-based (Soeur: ch.soeur.fr, www.soeur.uk) or separate-domain
  (A.P.C.: apcstore.co.uk) — same product/variant ids as the home domain.
- path-based (Rouje, Roseanna, Dries Van Noten: /en-gb, /en-ch) — same
  domain, same ids, currency switches per path.

Isabel Marant's GB/CH locales (intl.isabelmarant.com) are the one exception:
verified same product *handles* as the home store, but different Shopify
product ids — it's a separate Shopify instance, not a Markets-shared
catalog. crawler/main.py handles this by matching products across markets
by handle (falling back to the market's own id when no home-market handle
matches), so this doesn't need special-casing here.

Currency actually available per brand (checked, not assumed):
- Rouje, Roseanna: GBP and CHF both available.
- Dries Van Noten: GBP available; Switzerland is billed in EUR there (no
  CHF path), so no CH entry.
- A.P.C.: GBP available (apcstore.co.uk); no CHF market found.
- Isabel Marant: GBP and CHF both available (separate intl storefront).

Soeur alone exposes ~40 market domains; we only track the ones actually
asked for (FR/CH/UK) to avoid hammering the site for markets nobody looks
at — add more here if needed, no code change required elsewhere.

Sessun (fr.sessun.com) was in the original candidate list but is NOT
Shopify (404 on /products.json; cookies/headers show a custom CodeIgniter
PHP backend) — excluded.
"""

SHOPS = [
    {
        "brand": "Rouje",
        "markets": [
            "https://www.rouje.com",
            "https://www.rouje.com/en-gb",
            "https://www.rouje.com/en-ch",
        ],
    },
    {
        "brand": "Dries Van Noten",
        "markets": [
            "https://www.driesvannoten.com",
            "https://www.driesvannoten.com/en-gb",
        ],
    },
    {
        "brand": "Soeur",
        "markets": [
            "https://www.soeur.fr",
            "https://ch.soeur.fr",
            "https://www.soeur.uk",
        ],
    },
    {
        "brand": "A.P.C.",
        "markets": [
            "https://www.apc.fr",
            "https://www.apcstore.co.uk",
        ],
    },
    {
        "brand": "Isabel Marant",
        "markets": [
            "https://www.isabelmarant.com",
            "https://intl.isabelmarant.com/en-gb",
            "https://intl.isabelmarant.com/en-ch",
        ],
    },
    {
        "brand": "Roseanna",
        "markets": [
            "https://roseanna.fr",
            "https://roseanna.fr/en-gb",
            "https://roseanna.fr/en-ch",
        ],
    },
]
