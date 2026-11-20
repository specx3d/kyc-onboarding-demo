"""Step a+b: OCR text and LLM structuring of the document fields."""
from . import llm, mock

FIELDS = ["surname", "given_names", "document_number", "nationality", "date_of_birth", "sex",
          "expiry_date", "issuing_country"]

PROMPT = """You read identity documents. Below is the raw OCR text of the attached document image.
Return ONLY one JSON object, no commentary, with exactly these keys:
surname, given_names, document_number, nationality (ISO alpha-3), date_of_birth (YYYY-MM-DD),
sex (M/F/X), expiry_date (YYYY-MM-DD), issuing_country (ISO alpha-3),
mrz_lines (list of the machine readable zone lines, copied character by character, '<' kept).
Take the printed (visual) fields exactly as printed, including diacritics. Do not guess missing values: use null.

OCR TEXT:
{ocr}
"""


def run_ocr(path, mock_mode):
    return mock.mock_ocr(path) if mock_mode else llm.ocr_image(path)


def run_extraction(path, ocr_text, mock_mode):
    if mock_mode:
        return mock.mock_extract(path)
    msgs = [{"role": "user", "content": [{"type": "text", "text": PROMPT.format(ocr=ocr_text)},
                                         llm.image_part(path)]}]
    obj = llm.parse_json_block(llm.chat(llm.LLM_MODEL, msgs, max_tokens=1200))
    out = {k: obj.get(k) for k in FIELDS}
    m = obj.get("mrz_lines") or []
    out["mrz_lines"] = [str(x) for x in m] if isinstance(m, list) else [str(m)]
    return out
