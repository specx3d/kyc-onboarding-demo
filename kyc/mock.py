"""Deterministic offline stand-ins for the OCR and LLM calls (--mock)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GT_PATH = ROOT / "data" / "ground_truth.json"


def ground_truth(image_path):
    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))
    name = Path(image_path).name
    if name not in gt:
        raise KeyError(f"mock mode only knows generated samples; no ground truth for {name}")
    return gt[name]


def _ocr_noise(line):
    # typical OCR slips: '<<<' read as '<<«', first digit-like 'O' read as '0'
    return line.replace("<<<", "<<«", 1)


def mock_ocr(image_path):
    gt = ground_truth(image_path)
    f = gt["fields"]
    lines = [f"SURNAME {f['surname']}", f"GIVEN NAMES {f['given_names']}",
             f"DOCUMENT NO. {f['document_number'].replace('0', 'O', 1)}",
             f"NATIONALITY {f['nationality']}", f"DATE OF BIRTH {f['date_of_birth']}",
             f"SEX {f['sex']}", f"DATE OF EXPIRY {f['expiry_date']}",
             f"ISSUING COUNTRY {f['issuing_country']}"]
    return "\n".join(lines + [_ocr_noise(l) for l in gt["mrz_lines"]])


def mock_extract(image_path):
    gt = ground_truth(image_path)
    return dict(gt["fields"], mrz_lines=list(gt["mrz_lines"]))


def mock_triage(customer, hit):
    """Simulated LLM triage. It is deliberately over-confident on one pattern
    (identical name AND exact date of birth -> 'false positive') so the code
    guardrail has something to catch."""
    nm, dob = hit["name_score"], hit["dob_status"]
    if dob == "exact" and nm >= 95:
        return {"recommendation": "likely_false_positive",
                "rationale": "Very common name shared by many people; no further indicators considered.",
                "cited_sections": ["§2"], "fields_used": ["name"]}
    if dob == "mismatch":
        nat = " and nationality differs" if hit["nationality_status"] == "mismatch" else ""
        return {"recommendation": "likely_false_positive",
                "rationale": f"Date of birth is known on both sides and differs{nat}; name similarity is "
                             f"only {nm}.",
                "cited_sections": ["§3", "§6"], "fields_used": ["name", "date_of_birth", "nationality"]}
    if dob in ("exact", "year_match"):
        return {"recommendation": "likely_true_match",
                "rationale": "Name and date of birth are consistent with the listed person.",
                "cited_sections": ["§3", "§7"], "fields_used": ["name", "date_of_birth"]}
    return {"recommendation": "needs_review",
            "rationale": "Date of birth cannot confirm or exclude the match.",
            "cited_sections": ["§6"], "fields_used": ["name"]}
