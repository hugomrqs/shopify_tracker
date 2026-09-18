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
- path-based (Rouje, Roseanna, Dries Van Noten, Rains, Ami Paris: /en-gb,
  /en-ch, /de-ch, /fr-ch) — same domain, same ids, currency switches per
  path.
- query-param-based (Staud, Cult Gaia, Khaite, Musier Paris, By Far,
  Officine Générale, Nanushka: ?country=GB / ?country=CH on the home
  domain) — same domain, same ids, currency switches per query string.
  Verified stateless (no cookie needed) and that it changes the price
  returned by /products.json itself, not just the rendered HTML.

Isabel Marant's GB/CH locales (intl.isabelmarant.com) are one example of an
exception: verified same product *handles* as the home store, but different
Shopify product ids — it's a separate Shopify instance, not a
Markets-shared catalog. Polène (uk.polene-paris.com) and The Frankie Shop
(eu.thefrankieshop.com) are the same case. crawler/main.py handles this by
matching products across markets by handle (falling back to the market's
own id when no home-market handle matches), so this doesn't need
special-casing here.

Currency actually available per brand (checked, not assumed):
- Rouje, Roseanna: GBP and CHF both available.
- Dries Van Noten: GBP available; Switzerland is billed in EUR there (no
  CHF path), so no CH entry.
- A.P.C.: GBP available (apcstore.co.uk); no CHF market found.
- Isabel Marant: GBP and CHF both available (separate intl storefront).
- Totême: home domain is actually toteme.com (toteme-studio.com
  301-redirects there), home currency is SEK, not EUR. GBP available
  (/en-gb); no CHF locale exists on the site at all.
- Polène: GBP available (uk.polene-paris.com, separate instance, see
  above). Switzerland routes to euro.polene-paris.com, which is EUR, not
  CHF — so no CH entry.
- The Frankie Shop: GBP and CHF both available (eu.thefrankieshop.com,
  separate instance, see above), home currency is USD.
- Staud, Cult Gaia, Khaite, By Far: GBP and CHF both available via
  ?country= query param.
- Officine Générale: GBP and CHF both available via ?country= query param;
  uk.officinegenerale.com exists in hreflang tags but its homepage just
  redirects back to www — it's not a usable market, so it's not listed.
- Rejina Pyo: home currency is GBP already (verified rate 1.0 vs GB), so
  there's no separate GBP market entry. No CHF available — forcing
  country=CH still serves EUR.
- Nanushka: home currency is GBP already (verified rate 1.0 vs GB, unlike
  FR/DE which serve EUR and HU which serves HUF), so no separate GBP
  entry. CHF available via ?country=CH.
- Rains: GBP available (uk.rains.com, subdomain); CHF available (/de-ch,
  same domain/ids).
- Ami Paris: GBP available (/en-gb); CHF available (/fr-ch).
- Musier Paris: GBP available via ?country=GB; no CHF — forcing
  country=CH still serves EUR.

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
    {
        "brand": "Totême",
        "markets": [
            "https://toteme.com/en-se",
            "https://toteme.com/en-gb",
        ],
    },
    {
        "brand": "Polène",
        "markets": [
            "https://www.polene-paris.com",
            "https://uk.polene-paris.com",
        ],
    },
    {
        "brand": "The Frankie Shop",
        "markets": [
            "https://www.thefrankieshop.com",
            "https://eu.thefrankieshop.com/?country=GB&region=GB",
            "https://eu.thefrankieshop.com/?country=CH&region=CH",
        ],
    },
    {
        "brand": "Staud",
        "markets": [
            "https://staud.clothing",
            "https://staud.clothing/?country=GB",
            "https://staud.clothing/?country=CH",
        ],
    },
    {
        "brand": "Cult Gaia",
        "markets": [
            "https://cultgaia.com",
            "https://cultgaia.com/?country=GB",
            "https://cultgaia.com/?country=CH",
        ],
    },
    {
        "brand": "Rejina Pyo",
        "markets": [
            "https://rejinapyo.com",
        ],
    },
    {
        "brand": "Nanushka",
        "markets": [
            "https://www.nanushka.com",
            "https://www.nanushka.com/?country=CH",
        ],
    },
    {
        "brand": "Rains",
        "markets": [
            "https://rains.com",
            "https://uk.rains.com",
            "https://rains.com/de-ch",
        ],
    },
    {
        "brand": "Officine Générale",
        "markets": [
            "https://www.officinegenerale.com",
            "https://www.officinegenerale.com/?country=GB",
            "https://www.officinegenerale.com/?country=CH",
        ],
    },
    {
        "brand": "Ami Paris",
        "markets": [
            "https://www.amiparis.com",
            "https://www.amiparis.com/en-gb",
            "https://www.amiparis.com/fr-ch",
        ],
    },
    {
        "brand": "Khaite",
        "markets": [
            "https://khaite.com",
            "https://khaite.com/?country=GB",
            "https://khaite.com/?country=CH",
        ],
    },
    {
        "brand": "Musier Paris",
        "markets": [
            "https://musier.com",
            "https://musier.com/?country=GB",
        ],
    },
    {
        "brand": "By Far",
        "markets": [
            "https://byfar.com",
            "https://byfar.com/?country=GB",
            "https://byfar.com/?country=CH",
        ],
    },
]
