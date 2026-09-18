# -*- coding: utf-8 -*-
"""Loader for Soeur's internal product taxonomy (FN4 = catégorie, FN5 =
sous-catégorie), used as the mapping target for tracked competitor
products. Source files: `taxonomy/FN4.csv`, `taxonomy/FN5.csv` (drop
updated exports there to refresh the codebook — no code change needed).

FN3 (division) and FN6 (matière/type de fabrication) exist in the same
code-book family but are intentionally NOT used as hierarchy levels here:
FN3 isn't present per-product in the source extract, and FN6 is a
cross-cutting facet (a "ROBE" can be denim or jersey), not a tree level.
Ported from fashion_crawler/fashion_crawler/utils/taxonomy.py.
"""
import csv
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent / "taxonomy"


def _load_codebook(filename):
    """Return {CC_CODE: CC_LIBELLE} for one FN*.csv file."""
    path = TAXONOMY_DIR / filename
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {row["CC_CODE"]: row["CC_LIBELLE"] for row in csv.DictReader(f)}


def load_fn4():
    """Catégorie codebook, e.g. {"ROB": "ROBE", "SWE": "SWEAT", ...}."""
    return _load_codebook("FN4.csv")


def load_fn5():
    """Sous-catégorie codebook, e.g. {"BLO": "BLOUSE", "JUP": "JUPE", ...}."""
    return _load_codebook("FN5.csv")


def load_fn6():
    """Matière / type de fabrication codebook (cross-cutting facet)."""
    return _load_codebook("FN6.csv")
