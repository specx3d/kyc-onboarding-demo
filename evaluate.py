"""Run all samples through the pipeline and compare with data/ground_truth.json.

python evaluate.py [--mock]
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from kyc import extract, llm, pipeline
from kyc.textnorm import normalize_name

ROOT = Path(__file__).parent
SAMPLES = ROOT / "data" / "samples"
ISSUES = ("expired", "bad_check_digit", "viz_mrz_mismatch")


def same(field, a, b):
    if field in ("surname", "given_names"):
        return normalize_name(str(a or "")) == normalize_name(str(b or "")) and (a or "") == (b or "")
    return str(a or "").strip().upper() == str(b or "").strip().upper()


def table(rows, header):
    w = [max(len(str(x)) for x in col) for col in zip(header, *rows)]
    fmt = "| " + " | ".join(f"{{:<{n}}}" for n in w) + " |"
    sep = "|" + "|".join("-" * (n + 2) for n in w) + "|"
    return "\n".join([fmt.format(*header), sep] + [fmt.format(*map(str, r)) for r in rows])


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    gt = json.loads((ROOT / "data" / "ground_truth.json").read_text(encoding="utf-8"))
    results = {}
    for fn in gt:
        try:
            results[fn] = pipeline.process(SAMPLES / fn, a.mock)
        except llm.LLMError as e:
            print(f"ERROR on {fn}: {e}", file=sys.stderr)
            return 2
    n = len(gt)

    # 1. field accuracy
    field_rows = []
    for f in extract.FIELDS:
        ok = sum(same(f, results[fn]["extracted"].get(f), gt[fn]["fields"][f]) for fn in gt)
        field_rows.append((f, f"{ok}/{n}", f"{100 * ok / n:.0f}%"))
    mrz_ok = sum([l.replace(" ", "") for l in results[fn]["extracted"].get("mrz_lines", [])] == gt[fn]["mrz_lines"]
                 for fn in gt)
    field_rows.append(("mrz_lines (exact)", f"{mrz_ok}/{n}", f"{100 * mrz_ok / n:.0f}%"))

    # 2. issue detection
    issue_rows = []
    for iss in ISSUES:
        tp = sum(iss in gt[fn]["issues"] and iss in results[fn]["issues"] for fn in gt)
        fn_ = sum(iss in gt[fn]["issues"] and iss not in results[fn]["issues"] for fn in gt)
        fp = sum(iss not in gt[fn]["issues"] and iss in results[fn]["issues"] for fn in gt)
        issue_rows.append((iss, tp + fn_, tp, fn_, fp))

    # 3. screening
    true_docs = [fn for fn in gt if gt[fn]["screening"]["expected"] == "true_match"]
    fp_docs = [fn for fn in gt if gt[fn]["screening"]["expected"] == "false_positive"]
    none_docs = [fn for fn in gt if gt[fn]["screening"]["expected"] == "none"]

    def hit_for(fn):
        wl = gt[fn]["screening"]["watchlist_id"]
        return next((h for h in results[fn]["hits"] if h["watchlist_id"] == wl), None)

    tm_detected = sum(hit_for(fn) is not None for fn in true_docs)
    fp_flagged = sum(hit_for(fn) is not None for fn in fp_docs)
    unexpected = sum(len(results[fn]["hits"]) for fn in none_docs)
    raw_fp_on_true = sum(1 for fn in true_docs for h in results[fn]["hits"]
                         if h["triage"]["raw_recommendation"] == "likely_false_positive")
    final_fp_on_true = sum(1 for fn in true_docs for h in results[fn]["hits"]
                           if h["triage"]["recommendation"] == "likely_false_positive")
    overrides = sum(1 for r in results.values() for h in r["hits"]
                    if any("override" in x for x in h["triage"]["guardrail_notes"]))
    fp_closed = sum(1 for fn in fp_docs if (h := hit_for(fn)) and h["triage"]["recommendation"] == "likely_false_positive")
    key_ok = final_fp_on_true == 0 and tm_detected == len(true_docs)
    screen_rows = [
        ("True matches detected", f"{tm_detected}/{len(true_docs)}"),
        ("False-positive hits raised (customers who are not on the list)", f"{fp_flagged}/{len(fp_docs)}"),
        ("False positives correctly recommended as likely_false_positive", f"{fp_closed}/{len(fp_docs)}"),
        ("Hits on clean customers (unexpected)", unexpected),
        ("True match recommended as false positive BY THE AI (raw)", raw_fp_on_true),
        ("Guardrail overrides", overrides),
        ("KEY: true matches never recommended as false positive (after guardrails)",
         f"{'PASS' if key_ok else 'FAIL'} ({final_fp_on_true} violations)"),
    ]

    # 4. per-sample overview
    ov_rows = []
    status_ok = 0
    for fn in gt:
        r = results[fn]
        exp, got = gt[fn]["expected_status"], r["overall"]["status"]
        status_ok += exp == got
        ov_rows.append((fn, ",".join(r["issues"]) or "-", len(r["hits"]), got, "ok" if exp == got else f"MISMATCH (expected {exp})"))

    sections = [
        ("Field extraction accuracy", table(field_rows, ["field", "correct", "accuracy"])),
        ("Document issue detection", table(issue_rows, ["issue", "in ground truth", "detected", "missed", "false alarms"])),
        ("Sanctions screening", table(screen_rows, ["metric", "result"])),
        (f"Overall status per sample ({status_ok}/{n} as expected)",
         table(ov_rows, ["sample", "issues found", "hits", "status", "vs expected"])),
    ]
    mode = "mock" if a.mock else "live"
    out = [f"# KYC evaluation ({mode}, {date.today()})\n", f"Samples: {n}. Models: {next(iter(results.values()))['models']}\n"]
    for title, t in sections:
        out.append(f"## {title}\n\n{t}\n")
    text = "\n".join(out)
    print(text)
    (ROOT / "results").mkdir(exist_ok=True)
    p = ROOT / "results" / f"eval_{date.today()}{'_mock' if a.mock else ''}.md"
    p.write_text(text, encoding="utf-8")
    print(f"Saved: {p}")
    all_issues = all(r[3] == 0 and r[4] == 0 for r in issue_rows)
    return 0 if (key_ok and all_issues) else 1


if __name__ == "__main__":
    sys.exit(main())
