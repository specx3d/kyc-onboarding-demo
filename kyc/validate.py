"""Step c: deterministic validation (no AI): MRZ check digits, VIZ vs MRZ, expiry."""
import re
from datetime import date

from . import mrz
from .textnorm import name_variants


def parse_date(s):
    """Accept YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY. Returns date or None."""
    s = (s or "").strip() if isinstance(s, str) else ""
    for pat, order in ((r"^(\d{4})-(\d{2})-(\d{2})$", "ymd"), (r"^(\d{2})[./](\d{2})[./](\d{4})$", "dmy")):
        m = re.match(pat, s)
        if m:
            a, b, c = map(int, m.groups())
            try:
                return date(a, b, c) if order == "ymd" else date(c, b, a)
            except ValueError:
                return None
    return None


def _chk(name, label, ok, reason, skipped=False):
    return {"name": name, "label": label, "status": "skip" if skipped else ("pass" if ok else "fail"),
            "reason": reason}


def _norm_num(s):
    return re.sub(r"[\s<]", "", (s or "").upper())


def run_checks(ex, today=None):
    today = today or date.today()
    checks = []
    parsed = mrz.parse_mrz(ex.get("mrz_lines"))
    checks.append(_chk("mrz_format", "MRZ readable (TD1/TD3 layout)", parsed["ok"],
                       f"{parsed['format']} layout recognised" if parsed["ok"] else parsed["error"]))
    labels = {"cd_document_number": "Check digit: document number", "cd_date_of_birth": "Check digit: date of birth",
              "cd_expiry_date": "Check digit: expiry date", "cd_personal_number": "Check digit: personal number",
              "cd_composite": "Check digit: composite"}
    if parsed["ok"]:
        for c in parsed["checks"]:
            why = (f"expected {c['expected']}, MRZ has {c['actual']!r}" if not c["ok"] else
                   f"matches ({c['actual']})")
            checks.append(_chk(c["name"], labels[c["name"]], c["ok"], c["detail"] or why))
    else:
        for n in ("cd_document_number", "cd_date_of_birth", "cd_expiry_date", "cd_composite"):
            checks.append(_chk(n, labels[n], False, "MRZ not parsed", skipped=True))

    # dates
    dob, exp = parse_date(ex.get("date_of_birth")), parse_date(ex.get("expiry_date"))
    bad = [n for n, d in (("date of birth", dob), ("expiry date", exp)) if d is None]
    checks.append(_chk("dates_valid", "Dates are valid", not bad,
                       "both dates parsed" if not bad else "unparseable: " + ", ".join(bad)))

    # VIZ vs MRZ
    f = parsed["fields"]
    skip = not parsed["ok"]
    viz = lambda k: ex.get(k) or ""

    def names(key, label):
        a, b = name_variants(viz(key)), name_variants(f.get(key, ""))
        ok = bool(a & b)
        checks.append(_chk("viz_" + key, label, ok,
                           f"VIZ {viz(key)!r} == MRZ {f.get(key)!r} (after transliteration)" if ok else
                           f"VIZ {viz(key)!r} differs from MRZ {f.get(key)!r}", skip))

    names("surname", "VIZ = MRZ: surname")
    names("given_names", "VIZ = MRZ: given names")
    a, b = _norm_num(viz("document_number")), _norm_num(f.get("document_number"))
    checks.append(_chk("viz_document_number", "VIZ = MRZ: document number", a == b and a != "",
                       f"VIZ {a!r} vs MRZ {b!r}", skip))
    m_dob = mrz.mrz_date(f.get("date_of_birth", ""), "dob", today) if parsed["ok"] else None
    m_exp = mrz.mrz_date(f.get("expiry_date", ""), "exp", today) if parsed["ok"] else None
    checks.append(_chk("viz_date_of_birth", "VIZ = MRZ: date of birth", dob is not None and dob == m_dob,
                       f"VIZ {dob} vs MRZ {m_dob}", skip))
    checks.append(_chk("viz_expiry_date", "VIZ = MRZ: expiry date", exp is not None and exp == m_exp,
                       f"VIZ {exp} vs MRZ {m_exp}", skip))
    for k, lab in (("sex", "sex"), ("nationality", "nationality"), ("issuing_country", "issuing country")):
        a, b = viz(k).upper(), f.get(k, "").upper()
        checks.append(_chk("viz_" + k, f"VIZ = MRZ: {lab}", a == b and a != "", f"VIZ {a!r} vs MRZ {b!r}", skip))

    # expiry
    if exp is None:
        checks.append(_chk("not_expired", "Document not expired", False, "no valid expiry date", True))
    else:
        checks.append(_chk("not_expired", "Document not expired", exp >= today,
                           f"expires {exp}, today {today}" + ("" if exp >= today else " (expired)")))
    return checks


def issues_from(checks):
    """Map failed checks to the issue types used in ground truth."""
    issues = []
    fails = [c["name"] for c in checks if c["status"] == "fail"]
    if "not_expired" in fails:
        issues.append("expired")
    if any(n.startswith("cd_") for n in fails):
        issues.append("bad_check_digit")
    if any(n.startswith("viz_") for n in fails):
        issues.append("viz_mrz_mismatch")
    return issues
