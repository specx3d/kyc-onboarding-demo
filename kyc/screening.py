"""Step e: watchlist screening with explainable scoring + deterministic procedure rules."""
import re
from difflib import SequenceMatcher

from .textnorm import name_variants

REPORT_THRESHOLD = 80    # §2: below this no hit
POTENTIAL_THRESHOLD = 85  # §2
W_NAME = 0.7
DOB_POINTS = {"exact": 25, "year_match": 12, "unknown": 0, "mismatch": -20}
NAT_POINTS = {"match": 5, "unknown": 0, "mismatch": -5}


def similarity(a: str, b: str) -> float:
    """0-100. Best of token-order-insensitive and plain ratio on normalised names."""
    if not a or not b:
        return 0.0
    r1 = SequenceMatcher(None, " ".join(sorted(a.split())), " ".join(sorted(b.split()))).ratio()
    r2 = SequenceMatcher(None, a, b).ratio()
    return round(100 * max(r1, r2), 1)


def best_name_score(name_a: str, name_b: str) -> float:
    return max((similarity(x, y) for x in name_variants(name_a) for y in name_variants(name_b)), default=0.0)


def compare_dob(client_dob, watch_dob):
    if not client_dob or not watch_dob:
        return "unknown"
    cd, wd = str(client_dob), str(watch_dob)
    if re.fullmatch(r"\d{4}", wd):
        return "year_match" if cd[:4] == wd else "mismatch"
    return "exact" if cd == wd else "mismatch"


def compare_nationality(client_nat, watch_nat):
    if not client_nat or not watch_nat:
        return "unknown"
    return "match" if client_nat.upper() == watch_nat.upper() else "mismatch"


def screen_one(customer, entry):
    full = f"{customer.get('given_names', '')} {customer.get('surname', '')}".strip()
    best = (0.0, entry["name"], "name")
    for cand, kind in [(entry["name"], "name")] + [(a, "alias") for a in entry.get("aliases", [])]:
        s = best_name_score(full, cand)
        if s > best[0]:
            best = (s, cand, kind)
    name_score, matched, kind = best
    if name_score < REPORT_THRESHOLD:
        return None
    dob_st = compare_dob(customer.get("date_of_birth"), entry.get("dob"))
    nat_st = compare_nationality(customer.get("nationality"), entry.get("nationality"))
    name_pts = round(W_NAME * name_score, 1)
    total = max(0.0, min(100.0, name_pts + DOB_POINTS[dob_st] + NAT_POINTS[nat_st]))
    return {"watchlist_id": entry["id"], "watchlist_name": entry["name"], "matched_name": matched,
            "matched_on": kind, "name_score": name_score, "name_points": name_pts,
            "dob_status": dob_st, "dob_points": DOB_POINTS[dob_st],
            "nationality_status": nat_st, "nationality_points": NAT_POINTS[nat_st],
            "total": round(total, 1), "watch_dob": entry.get("dob"),
            "watch_nationality": entry.get("nationality"), "program": entry.get("program"),
            "listing_date": entry.get("listing_date"), "watch_aliases": entry.get("aliases", [])}


def screen(customer, watchlist):
    hits = [h for h in (screen_one(customer, e) for e in watchlist) if h]
    return sorted(hits, key=lambda h: -h["total"])


def procedure_rules(hit):
    """Deterministic reading of the procedure (§3, §6, §7)."""
    n, d = hit["name_score"], hit["dob_status"]
    if n >= POTENTIAL_THRESHOLD and d in ("exact", "year_match"):
        return {"mandatory_escalation": True, "closeable": False, "sections": ["§7", "§3"],
                "explanation": "Name score >= 85 and date of birth supports the match: mandatory escalation."}
    if n >= 100 and d == "unknown":
        return {"mandatory_escalation": True, "closeable": False, "sections": ["§7"],
                "explanation": "Identical name and date of birth unknown: mandatory escalation."}
    if d == "mismatch":
        return {"mandatory_escalation": False, "closeable": True, "sections": ["§6", "§3"],
                "explanation": "Date of birth known on both sides and different: may be recommended as false positive."}
    return {"mandatory_escalation": False, "closeable": False, "sections": ["§6"],
            "explanation": "Cannot be excluded from the available data: analyst review."}
