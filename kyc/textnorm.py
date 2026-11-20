"""Name normalisation and transliteration helpers."""
import re
import unicodedata

_SPECIAL = {"Ł": "L", "ł": "l", "Ø": "O", "ø": "o", "Đ": "D", "đ": "d", "Ð": "D",
            "ß": "SS", "Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe", "Þ": "TH"}
_DE = {"Ä": "AE", "Ö": "OE", "Ü": "UE", "ä": "ae", "ö": "oe", "ü": "ue"}


def strip_diacritics(s: str) -> str:
    """Plain transliteration: Ł->L, Ó->O, Ä->A ..."""
    s = "".join(_SPECIAL.get(c, c) for c in s)
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def translit_de(s: str) -> str:
    """German-style transliteration: Ä->AE, Ö->OE, Ü->UE (then plain)."""
    return strip_diacritics("".join(_DE.get(c, c) for c in s))


def _clean(s: str) -> str:
    s = s.upper().replace("'", "").replace("’", "")
    s = re.sub(r"[^A-Z]+", " ", s)
    return " ".join(s.split())


def normalize_name(s: str) -> str:
    """Upper case, no diacritics, letters and single spaces only."""
    return _clean(strip_diacritics(s or ""))


def name_variants(s: str) -> set:
    """Normalised forms of a name under PL-style and DE-style transliteration."""
    return {_clean(strip_diacritics(s or "")), _clean(translit_de(s or ""))} - {""}


def mrz_name(s: str) -> str:
    """Name as it appears in an MRZ name field (filler < between tokens)."""
    return normalize_name(s).replace(" ", "<")


def mrz_to_text(s: str) -> str:
    return " ".join((s or "").replace("<", " ").split())
