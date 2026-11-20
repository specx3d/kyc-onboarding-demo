"""ICAO 9303 MRZ: check digits, TD1/TD3 build and parse."""
from datetime import date

from .textnorm import mrz_name, mrz_to_text

WEIGHTS = (7, 3, 1)


def char_value(c: str) -> int:
    if c.isdigit():
        return int(c)
    if "A" <= c <= "Z":
        return ord(c) - 55
    if c == "<":
        return 0
    raise ValueError(f"invalid MRZ character {c!r}")


def check_digit(s: str) -> int:
    return sum(char_value(c) * WEIGHTS[i % 3] for i, c in enumerate(s)) % 10


def pad(s: str, n: int) -> str:
    return s[:n].ljust(n, "<")


def yymmdd(d: date) -> str:
    return d.strftime("%y%m%d")


def _name_field(surname: str, given: str, width: int) -> str:
    s = mrz_name(surname)
    g = mrz_name(given)
    return pad(f"{s}<<{g}" if g else s, width)


def _cd(s: str) -> str:
    return str(check_digit(s))


def build_td3(issuing, surname, given, number, nationality, dob, sex, expiry, personal=""):
    l1 = "P<" + issuing + _name_field(surname, given, 39)
    num, pers = pad(number, 9), pad(personal, 14)
    l2 = (num + _cd(num) + nationality + yymmdd(dob) + _cd(yymmdd(dob)) + sex +
          yymmdd(expiry) + _cd(yymmdd(expiry)) + pers + _cd(pers))
    l2 += _cd(l2[0:10] + l2[13:20] + l2[21:43])
    return [l1, l2]


def build_td1(issuing, surname, given, number, nationality, dob, sex, expiry, opt1="", opt2=""):
    num = pad(number, 9)
    l1 = "I<" + issuing + num + _cd(num) + pad(opt1, 15)
    l2 = (yymmdd(dob) + _cd(yymmdd(dob)) + sex + yymmdd(expiry) + _cd(yymmdd(expiry)) +
          nationality + pad(opt2, 11))
    l2 += _cd(l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29])
    return [l1, l2, _name_field(surname, given, 30)]


def _split_name(field: str):
    parts = field.split("<<", 1)
    surname = mrz_to_text(parts[0])
    given = mrz_to_text(parts[1]) if len(parts) > 1 else ""
    return surname, given


def _chk(name, data, actual):
    """One check-digit result. '<' is accepted for an all-filler field."""
    try:
        expected = str(check_digit(data))
    except ValueError as e:
        return {"name": name, "ok": False, "expected": "?", "actual": actual, "detail": str(e)}
    ok = actual == expected or (actual == "<" and set(data) <= {"<"})
    return {"name": name, "ok": ok, "expected": expected, "actual": actual, "detail": ""}


def parse_mrz(lines):
    """Parse TD1 (3x30) or TD3 (2x44). Returns dict with ok, format, fields, checks, error."""
    ls = [("".join((l or "").upper().split())) for l in (lines or []) if (l or "").strip()]
    out = {"ok": False, "format": None, "fields": {}, "checks": [], "error": None, "lines": ls}
    if len(ls) == 3 and all(len(l) == 30 for l in ls):
        l1, l2, l3 = ls
        out["format"] = "TD1"
        sn, gn = _split_name(l3)
        out["fields"] = {"doc_type": l1[0:2], "issuing_country": l1[2:5],
                         "document_number": l1[5:14].rstrip("<"), "date_of_birth": l2[0:6],
                         "sex": l2[7], "expiry_date": l2[8:14], "nationality": l2[15:18],
                         "surname": sn, "given_names": gn}
        out["checks"] = [
            _chk("cd_document_number", l1[5:14], l1[14]),
            _chk("cd_date_of_birth", l2[0:6], l2[6]),
            _chk("cd_expiry_date", l2[8:14], l2[14]),
            _chk("cd_composite", l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29], l2[29]),
        ]
    elif len(ls) == 2 and all(len(l) == 44 for l in ls):
        l1, l2 = ls
        out["format"] = "TD3"
        sn, gn = _split_name(l1[5:44])
        out["fields"] = {"doc_type": l1[0:2], "issuing_country": l1[2:5],
                         "document_number": l2[0:9].rstrip("<"), "nationality": l2[10:13],
                         "date_of_birth": l2[13:19], "sex": l2[20], "expiry_date": l2[21:27],
                         "surname": sn, "given_names": gn}
        out["checks"] = [
            _chk("cd_document_number", l2[0:9], l2[9]),
            _chk("cd_date_of_birth", l2[13:19], l2[19]),
            _chk("cd_expiry_date", l2[21:27], l2[27]),
            _chk("cd_personal_number", l2[28:42], l2[42]),
            _chk("cd_composite", l2[0:10] + l2[13:20] + l2[21:43], l2[43]),
        ]
    else:
        out["error"] = ("MRZ must be 3 lines x 30 chars (TD1) or 2 lines x 44 chars (TD3); got "
                        + " x ".join(str(len(l)) for l in ls))
        return out
    out["ok"] = True
    return out


def mrz_date(yymmdd_s: str, kind: str, today: date):
    """YYMMDD -> date. Birth dates in the future are shifted to the 1900s."""
    try:
        yy, mm, dd = int(yymmdd_s[0:2]), int(yymmdd_s[2:4]), int(yymmdd_s[4:6])
        year = 2000 + yy
        if kind == "dob" and year > today.year:
            year -= 100
        return date(year, mm, dd)
    except (ValueError, IndexError):
        return None
