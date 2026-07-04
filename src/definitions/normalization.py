r"""
Shoot the Sheet - Name Normalization Rules

Declarative mappings consumed by ``_normalize_name`` in ``src.lib.transform``.
Add or remove entries here; no code changes needed.

Pipeline order (matches ``project_tracking/matching.md``):
    1. Unicode NFC normalization
    2. Diacritic to ASCII conversion
    3. Unicode quotes to ASCII, Unicode dashes to ASCII hyphen
    4. Standalone word replacements (surrounded by whitespace or string
       boundaries, not word-boundary, to avoid matching inside
       hyphenated compounds like "Saint-Louis")
    5. Strip specified characters entirely
    6. Trim / collapse whitespace
"""

from typing import Dict, List

# ---------------------------------------------------------------------------
# Character-level diacritic → ASCII mappings (applied after NFC).
# Both lowercase AND uppercase variants are included — names from
# non-English sources may arrive in title-case or ALL-CAPS.
# ---------------------------------------------------------------------------
DIACRITICS: Dict[str, str] = {
    # ---- ss / ae / oe ----
    "ß": "ss",
    "ẞ": "SS",
    "æ": "ae",
    "Æ": "AE",
    "œ": "oe",
    "Œ": "OE",
    # ---- a ----
    "á": "a",
    "Á": "A",
    "à": "a",
    "À": "A",
    "â": "a",
    "Â": "A",
    "ä": "a",
    "Ä": "A",
    "ã": "a",
    "Ã": "A",
    "å": "a",
    "Å": "A",
    "ā": "a",
    "Ā": "A",
    "ą": "a",
    "Ą": "A",
    # ---- c ----
    "ç": "c",
    "Ç": "C",
    "ć": "c",
    "Ć": "C",
    "č": "c",
    "Č": "C",
    # ---- d ----
    "đ": "d",
    "Đ": "D",
    "ð": "d",
    "Ð": "D",
    # ---- e ----
    "é": "e",
    "É": "E",
    "è": "e",
    "È": "E",
    "ê": "e",
    "Ê": "E",
    "ë": "e",
    "Ë": "E",
    "ē": "e",
    "Ē": "E",
    "ė": "e",
    "Ė": "E",
    "ę": "e",
    "Ę": "E",
    # ---- g (Turkish / Latvian) ----
    "ğ": "g",
    "Ğ": "G",
    "ģ": "g",
    "Ģ": "G",
    # ---- i ----
    "í": "i",
    "Í": "I",
    "ì": "i",
    "Ì": "I",
    "î": "i",
    "Î": "I",
    "ï": "i",
    "Ï": "I",
    "ī": "i",
    "Ī": "I",
    "ı": "i",
    "İ": "I",
    # ---- k (Latvian) ----
    "ķ": "k",
    "Ķ": "K",
    # ---- l ----
    "ł": "l",
    "Ł": "L",
    "ļ": "l",
    "Ļ": "L",
    # ---- n ----
    "ñ": "n",
    "Ñ": "N",
    "ń": "n",
    "Ń": "N",
    "ň": "n",
    "Ň": "N",
    "ņ": "n",
    "Ņ": "N",
    # ---- o ----
    "ó": "o",
    "Ó": "O",
    "ò": "o",
    "Ò": "O",
    "ô": "o",
    "Ô": "O",
    "ö": "o",
    "Ö": "O",
    "õ": "o",
    "Õ": "O",
    "ø": "o",
    "Ø": "O",
    "ō": "o",
    "Ō": "O",
    # ---- r ----
    "ř": "r",
    "Ř": "R",
    # ---- s ----
    "š": "s",
    "Š": "S",
    "ś": "s",
    "Ś": "S",
    "ş": "s",
    "Ş": "S",
    # ---- t ----
    "ț": "t",
    "Ț": "T",
    "ţ": "t",
    "Ţ": "T",
    # ---- u ----
    "ú": "u",
    "Ú": "U",
    "ù": "u",
    "Ù": "U",
    "û": "u",
    "Û": "U",
    "ü": "u",
    "Ü": "U",
    "ū": "u",
    "Ū": "U",
    "ų": "u",
    "Ų": "U",
    # ---- y ----
    "ý": "y",
    "Ý": "Y",
    "ÿ": "y",
    "Ÿ": "Y",
    # ---- z ----
    "ž": "z",
    "Ž": "Z",
    "ź": "z",
    "Ź": "Z",
    "ż": "z",
    "Ż": "Z",
}

# ---------------------------------------------------------------------------
# Unicode quote-like → ASCII apostrophe
# ---------------------------------------------------------------------------
UNICODE_QUOTES: Dict[str, str] = {
    "\u2018": "'",  # left single quotation mark
    "\u2019": "'",  # right single quotation mark
    "\u201c": '"',  # left double quotation mark
    "\u201d": '"',  # right double quotation mark
    "`": "'",  # backtick / grave accent
    "\u00b4": "'",  # acute accent (´)
    "\u02bb": "'",  # okina (ʻ)
    "\u02bc": "'",  # modifier letter apostrophe (ʼ)
}

# ---------------------------------------------------------------------------
# Unicode dash-like → ASCII hyphen
# ---------------------------------------------------------------------------
UNICODE_DASHES: Dict[str, str] = {
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\u2012": "-",  # figure dash
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2212": "-",  # minus sign — common in stats tables
}

# ---------------------------------------------------------------------------
# Standalone word replacements  (matched on word boundaries)
# ---------------------------------------------------------------------------
WORD_REPLACEMENTS: Dict[str, str] = {
    "Saint": "St",
    "Sainte": "Ste",
    "Mount": "Mt",
    "and": "&",
    "LA": "Los Angeles",
}

# ---------------------------------------------------------------------------
# Characters to strip entirely from the normalized string
# ---------------------------------------------------------------------------
STRIP_CHARACTERS: List[str] = [".", ","]
