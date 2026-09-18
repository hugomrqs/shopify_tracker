# -*- coding: utf-8 -*-
"""Fuzzy fallback: guess a product's FN4 (catégorie) from its *title* when
`product_type` gives no usable category (missing, too generic, or a
combined bucket like "Manteaux & Vestes" that spans two FN4 families).

Deterministic string similarity against the FN4/FN5 label vocabulary
(difflib, no ML/LLM) — not a replacement for the product_type mapping,
only a fallback for it. Every guess carries a confidence score:
  - score >= HIGH_CONFIDENCE_THRESHOLD  -> treated as a normal mapping
  - score >= LOW_CONFIDENCE_FLOOR       -> still assigned, but flagged
    `category_mapping_status: "low_confidence"` for manual review
  - below the floor                     -> no guess at all (stays unmapped)

Ported from fashion_crawler/fashion_crawler/utils/category_matching.py,
adapted from Scrapy's `raw_category` breadcrumb trail to Shopify's flat
`product_type` field (see normalize_categories.py for why).
"""
import unicodedata
from difflib import SequenceMatcher

from crawler.taxonomy import load_fn4, load_fn5

HIGH_CONFIDENCE_THRESHOLD = 0.90
LOW_CONFIDENCE_FLOOR = 0.55

# Name keywords for products that are structurally out of this taxonomy's
# scope (beauty/lingerie/home items with no FN4 equivalent) but whose
# product_type was missing/generic, so the dictionary-based out_of_scope
# entries never saw them — they'd otherwise fall through to name-fuzzy-
# matching and produce noise (e.g. "Bougie Rose Jasmin" -> "CHE" at 0.67,
# coincidental). Checked before fuzzy matching is attempted at all.
_OUT_OF_SCOPE_NAME_KEYWORDS = (
    "BOUGIE", "FARD A JOUES", "ROUGE A LEVRES", "PALETTE", "BAUME",
    "CREME", "POUDRE BONNE MINE", "BRUME", "PINCEAU", "BLUSH", "MASCARA",
    "GLOSS", "EYELINER", "STYLO MARGAUX", "SOUTIEN GORGE", "SOUTIEN-GORGE",
    "TANGA", "CULOTTE", "ETUI A ROUGE A LEVRES", "TIRAGE PHOTO",
)


# Garment/accessory types with NO corresponding FN4 family at all (real
# gaps in this taxonomy, confirmed by manual review — see fashion_crawler's
# project notes, ported verbatim). Guessing at these just produces noise
# (e.g. "Top SOLANGE" -> "TOTE BAG" at 0.57), so they short-circuit
# straight to unmapped instead of being scored — an honest "no answer
# exists here" beats a coin-flip low-confidence guess dressed up with a
# number.
_KNOWN_GAP_KEYWORDS = (
    "TOP", "BODY", "DEBARDEUR", "MAILLOT DE BAIN", "MAILLOT", "BANDEAU",
    "GILET", "BERMUDA", "CHAUSSETTES", "BALLERINES", "MULES", "MARCEL",
    "POLO", "CARACO", "VAREUSE", "CHOUCHOU", "PINCE A CHEVEUX",
)


def is_known_taxonomy_gap(name):
    """True if the name's garment type is a confirmed FN4 gap — see
    _KNOWN_GAP_KEYWORDS. Checked before fuzzy matching to avoid dressing up
    a guaranteed-wrong guess as a "low confidence" score."""
    if not name:
        return False
    normalized = _normalize(name)
    words = set(normalized.split())
    return any(
        (keyword in normalized if " " in keyword else keyword in words)
        for keyword in _KNOWN_GAP_KEYWORDS
    )


def is_out_of_scope_by_name(name):
    """True if the product name itself signals it's outside this taxonomy
    (beauty/lingerie/photo prints etc.) — a cheaper, name-only counterpart
    to the dictionary-based out_of_scope entries, for products whose
    product_type didn't carry that signal."""
    if not name:
        return False
    normalized = _normalize(name)
    return any(keyword in normalized for keyword in _OUT_OF_SCOPE_NAME_KEYWORDS)


# FN5 ("forme") codes that are unambiguous variants of a single FN4 family
# — their own label makes the parent obvious (e.g. "JEAN BOYFRIEND" is
# clearly denim, "BOUCLES D'OREILLES" is clearly bijoux) even though no
# FN4<->FN5 parent table was provided. Used so a specific variant name
# still resolves to the right *catégorie*. Deliberately NOT exhaustive:
# several FN5 garment types have no sensible FN4 parent at all in this
# codebook (socks, gloves, tights, swimwear, hats/bandanas, underwear) —
# left out on purpose rather than force-fit into the wrong family.
_FN5_TO_FN4_PARENT = {
    "JBO": "JEA", "JDR": "JEA", "JPE": "JEA", "JSL": "JEA", "BLJ": "JEA",  # jean cuts / denim blouson
    "RCT": "ROB", "RJE": "ROB", "RTR": "ROB", "RCU": "ROB",               # robe by material
    "VCA": "VES", "VFO": "VES",                                          # veste casual/formal
    "TSC": "TSH", "TSM": "TSH",                                          # tshirt sleeve variants
    "BLO": "CHE",                                                        # blouse -> chemise family
    "PFJ": "PUL",                                                        # pull fine jauge
    "BSK": "CHA", "BTE": "CHA", "BTI": "CHA", "DER": "CHA",
    "ESC": "CHA", "MOC": "CHA", "SAB": "CHA", "SAN": "CHA",               # shoe types -> chaussures
    "BAG": "BIJ", "BOR": "BIJ", "BRA": "BIJ", "COL": "BIJ",
    "PEN": "BIJ", "SAU": "BIJ", "BRC": "BIJ",                             # jewelry types -> bijoux
    "CEC": "CEI", "CET": "CEI",                                          # belt materials -> ceinture
    "PNR": "SEM", "PMA": "SEM",                                          # panier / petite maroquinerie -> sac et maro
    "TRE": "MAN", "PAR": "MAN", "CAB": "MAN", "DOU": "MAN",              # outerwear -> manteau
    "FOU": "ECH", "FIC": "ECH",                                          # foulard/fichu -> écharpe
    "LUN": "AUT",                                                        # lunettes -> autres accessoires
}

# Small French stopwords dropped when splitting a multi-word FN4/FN5 label
# into individual searchable words (e.g. "SAC ET MARO" -> also try "SAC",
# "MARO" alone, not just the full 3-word phrase).
_STOPWORDS = {"ET", "DE", "DU", "DES", "LA", "LE", "LES", "A"}

# FN4 codes excluded from fuzzy matching entirely: generic/catch-all labels
# that aren't a specific garment family and are prone to spurious
# collisions (e.g. "PAP" = "PRET A PORTER" — its split word "PORTER"
# nearly-matched "Porte-clé"/"Porte-carte" at 0.91, which is wrong; being a
# division-level label duplicated at FN4, it was never a useful guess
# target even when "correctly" matched).
_EXCLUDED_FN4 = {"PAP"}


def _normalize(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = "".join(c if c.isalnum() else " " for c in text)
    return " ".join(text.upper().split())


def _label_candidates():
    """Yield (normalized_text, fn4_code, fn5_code, is_full_label) for every
    matchable label, both as a whole phrase (is_full_label=True) and as its
    individual significant words (False) — so a one-word product-name
    prefix like "Sac" can still match a multi-word label like "SAC ET
    MARO". `is_full_label` is used to break ties in favor of the more
    specific whole-phrase match (a single split-off word like "CARTE" can
    coincidentally tie a real product's own full-label match otherwise —
    see the "Carte cadeau" bug this fixed in fashion_crawler)."""
    fn4 = load_fn4()
    fn5 = load_fn5()

    def expand(label, fn4_code, fn5_code):
        normalized = _normalize(label)
        yield normalized, fn4_code, fn5_code, True
        words = normalized.split()
        if len(words) > 1:
            for word in words:
                if word not in _STOPWORDS:
                    yield word, fn4_code, fn5_code, False

    for code, label in fn4.items():
        if code in _EXCLUDED_FN4:
            continue
        yield from expand(label, code, None)
    for code, label in fn5.items():
        parent = _FN5_TO_FN4_PARENT.get(code)
        if parent:
            yield from expand(label, parent, code)


_CANDIDATES = None  # lazily built, module-level cache


def _name_segments(name):
    """Yield candidate word-windows to test against the label vocabulary.

    Garment type placement varies by site: Rouje leads with it
    ("Cardigan ABELINA"), some sites bury it in the middle of an SEO title
    ("SOFTY Indigo Blue | Chaussettes | Site officiel"). So this tries the
    first 1-3 words of the whole name AND, when the name contains "|"
    segments (that SEO-title pattern), the first 1-3 words of each segment
    too — cheap and covers both shapes without guessing which site
    produced the name.
    """
    pieces = [name] + name.split("|") if "|" in name else [name]
    for piece in pieces:
        words = _normalize(piece).split()
        for n in (1, 2, 3):
            candidate = " ".join(words[:n])
            if candidate:
                yield candidate


def guess_category_from_name(name):
    """Best-effort (fn4_code, fn5_code, score) guess from a product name.

    Returns (None, None, 0.0) if nothing scores above LOW_CONFIDENCE_FLOOR.
    """
    global _CANDIDATES
    if _CANDIDATES is None:
        _CANDIDATES = list(_label_candidates())

    if not name:
        return None, None, 0.0

    # (fn4, fn5, score, is_full_label) — is_full_label only used to break
    # ties in the comparison below, never returned.
    best = (None, None, 0.0, False)
    for candidate_text in _name_segments(name):
        for label_text, fn4_code, fn5_code, is_full in _CANDIDATES:
            score = SequenceMatcher(None, candidate_text, label_text).ratio()
            if (score, is_full) > (best[2], best[3]):
                best = (fn4_code, fn5_code, score, is_full)

    if best[2] < LOW_CONFIDENCE_FLOOR:
        return None, None, 0.0
    return best[0], best[1], best[2]
