"""Step a: the vision LLM reads the document image (fields) and, in a second pass, the MRZ strip alone.

A dedicated OCR model (Surya OCR 2 via Ollama) was tried first; through Ollama's chat API it returned
layout boxes instead of text, while Gemma's vision read the samples directly. See README, "What didn't work".
"""
import re

from . import llm, mock

FIELDS = ["surname", "given_names", "document_number", "nationality", "date_of_birth", "sex",
          "expiry_date", "issuing_country"]

MRZ_PROMPT = ("This image is the machine readable zone (MRZ) of an identity document. Transcribe it exactly, "
              "character by character, one string per line. Keep every '<' and every digit, including check digits. "
              "Do not correct or complete anything. Return ONLY JSON: {\"mrz_lines\": [\"...\", ...]}")

PROMPT = """You read identity documents. Read the attached document image.
Return ONLY one JSON object, no commentary, with exactly these keys:
surname, given_names, document_number, nationality (ISO alpha-3), date_of_birth (YYYY-MM-DD),
sex (M/F/X), expiry_date (YYYY-MM-DD), issuing_country (ISO alpha-3),
mrz_lines (list of the machine readable zone lines, copied character by character, '<' kept).
Take the printed (visual) fields exactly as printed, including diacritics. Do not guess missing values: use null.
"""

MRZ_CROP = 0.70  # the MRZ sits in the bottom 30% of the document image
MRZ_LEN = {3: 30, 2: 44}  # TD1: 3 x 30, TD3: 2 x 44


def normalize_mrz(lines):
    """Remove spaces and fix the number of '<' fillers to the ICAO line length (TD1 3x30, TD3 2x44).

    Models often add or drop one or two '<' when copying a long filler run. The difference is applied to the
    longest '<' run in the line (in line 2 that run sits before the final check digit, so the digit keeps its
    position), and a run is never shortened to nothing. Every data field is still verified by its check digit,
    so a wrong repair shows up as a check-digit failure instead of passing silently."""
    out = []
    n = MRZ_LEN.get(len(lines))
    for raw in lines:
        line = re.sub(r"\s", "", str(raw)).upper()
        runs = list(re.finditer(r"<+", line))
        if n and runs and len(line) != n:
            r = max(runs, key=lambda m: (len(m.group()), m.start()))
            size = max(1, len(r.group()) + n - len(line))
            line = line[:r.start()] + "<" * size + line[r.end():]
        out.append(line)
    return out


def run_ocr(path, mock_mode):
    """Mock mode simulates a separate OCR text step; live mode reads the image directly in run_extraction."""
    return mock.mock_ocr(path) if mock_mode else None


def run_extraction(path, ocr_text, mock_mode):
    if mock_mode:
        return mock.mock_extract(path)
    msgs = [{"role": "user", "content": [{"type": "text", "text": PROMPT}, llm.image_part(path)]}]
    obj = llm.parse_json_block(llm.chat(llm.LLM_MODEL, msgs, max_tokens=1200))
    out = {k: obj.get(k) for k in FIELDS}
    # Second pass on the MRZ strip alone. With the whole card in view the model "corrects" the MRZ from the
    # visual zone (e.g. drops the check digit after the document number); on the crop it just copies.
    msgs = [{"role": "user", "content": [{"type": "text", "text": MRZ_PROMPT}, llm.image_part(path, crop=MRZ_CROP)]}]
    m = llm.parse_json_block(llm.chat(llm.LLM_MODEL, msgs, max_tokens=400)).get("mrz_lines") or []
    out["mrz_lines"] = normalize_mrz(m if isinstance(m, list) else [m])
    return out
