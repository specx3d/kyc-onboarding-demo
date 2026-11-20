"""KYC pipeline: image reading (vision LLM) -> extraction -> validation -> screening -> triage -> overall status.

CLI: python -m kyc.pipeline <image> [--mock]
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import extract, llm, screening, triage, validate

ROOT = Path(__file__).resolve().parent.parent
WATCHLIST_PATH = ROOT / "data" / "watchlist.json"


def load_watchlist():
    return json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))


def decide_overall(issues, checks, hits):
    """Simple rules. The result is always a proposal: a human decides."""
    reasons, status = [], "pass"
    if "expired" in issues:
        status = "reject"
        reasons.append("Document is expired.")
    if "bad_check_digit" in issues:
        status = "reject"
        reasons.append("MRZ check digit failure (possible alteration or misread).")
    if status != "reject":
        if "viz_mrz_mismatch" in issues:
            status = "refer to analyst"
            reasons.append("Visual zone and MRZ disagree.")
        if any(c["name"] == "mrz_format" and c["status"] == "fail" for c in checks):
            status = "refer to analyst"
            reasons.append("MRZ could not be read.")
        open_hits = [h for h in hits if h["triage"]["recommendation"] != "likely_false_positive"]
        if open_hits:
            status = "refer to analyst"
            reasons.append(f"{len(open_hits)} screening hit(s) need analyst review or escalation.")
        elif hits:
            reasons.append(f"{len(hits)} hit(s) recommended as likely false positive; analyst must confirm (§8).")
    if not reasons:
        reasons.append("All checks passed, no screening hits.")
    return {"status": status, "reasons": reasons, "human_decision_required": True}


def process(path, mock=False, today=None, watchlist=None, procedure=None):
    path = Path(path)
    today = today or date.today()
    watchlist = watchlist if watchlist is not None else load_watchlist()
    procedure = procedure or triage.load_procedure()
    ocr_text = extract.run_ocr(path, mock)
    ex = extract.run_extraction(path, ocr_text, mock)
    checks = validate.run_checks(ex, today)
    issues = validate.issues_from(checks)
    hits = screening.screen(ex, watchlist)
    for h in hits:
        h["rules"] = screening.procedure_rules(h)
        h["triage"] = triage.triage_hit(ex, h, h["rules"], procedure, mock)
    models = ({"ocr": "mock-ocr", "llm": "mock-llm", "mode": "mock"} if mock else
              {"ocr": "none (vision LLM reads the image)", "llm": llm.LLM_MODEL, "mode": "live"})
    return {"filename": path.name, "mode": models["mode"], "models": models,
            "doc_type": "TD3" if len(ex.get("mrz_lines") or []) == 2 else "TD1", "ocr_text": ocr_text,
            "extracted": ex, "checks": checks, "issues": issues, "hits": hits,
            "overall": decide_overall(issues, checks, hits), "processed_for": today.isoformat()}


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Run the KYC pipeline on one document image.")
    ap.add_argument("image")
    ap.add_argument("--mock", action="store_true", help="offline deterministic mode (no model server)")
    a = ap.parse_args(argv)
    try:
        r = process(a.image, a.mock)
    except (llm.LLMError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
