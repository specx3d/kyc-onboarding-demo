# KYC onboarding pipeline (prototype)

A local prototype of an AML/KYC onboarding flow: read an identity document, validate it deterministically,
screen the person against a sanctions list, let an AI model triage the hits, and leave the final decision to a human.

**All data is fictional** (invented people, generated document images, an invented watchlist and procedure).
Real ISO country codes are used. Nothing here is a real document template or a real sanctions list.

## Problem

Onboarding analysts spend most of their time on two things: checking that an ID document is genuine and consistent,
and clearing sanctions-screening hits, most of which are false positives. Both are slow, but a mistake on a true
match is very costly. The goal is to speed up the routine work **without** letting a model make or hide a
compliance decision.

## Architecture

```
 document image (PNG)
        |
   [1] OCR  (surya-ocr)                         AI    raw text
        |
   [2] Extraction (gemma4-12b, image + OCR)     AI    JSON: fields + MRZ lines
        |
   [3] Validation (plain Python)                CODE  MRZ check digits (7-3-1, composite), VIZ vs MRZ,
        |                                              transliteration, date formats, expiry
   [4] Screening (plain Python)                 CODE  normalise names, difflib + token sort, aliases,
        |                                              DOB / nationality, score breakdown, procedure rules
   [5] Triage (gemma4-12b, procedure in prompt) AI    recommendation + rationale + cited sections
        |
   [6] Guardrails (plain Python)                CODE  cited sections must exist; mandatory escalation
        |                                              overrides "false positive"; AI never closes a case
   [7] Overall status: pass / refer / reject    CODE  a proposal only
        |
   [8] Human: Approve / Reject / Escalate       HUMAN comment required -> SQLite audit log
```

## What the AI does, what code does, and why

| Step | Who | Why |
|---|---|---|
| OCR, reading messy images, structuring text to JSON | AI | Layouts and image quality vary; this is what models are good at. |
| MRZ check digits, VIZ-vs-MRZ comparison, expiry | Code | Check digits are arithmetic. They act as a **hallucination check on the OCR/LLM output**: if a model misreads or invents a character, the digits stop adding up and the document is flagged instead of silently accepted. They also catch altered documents. |
| Name similarity and scoring | Code | Explainable: every hit shows its points (name, date of birth, nationality). |
| Reading a hit against the procedure | AI | Natural-language reasoning over a text procedure, with rationale and citations. |
| Guardrails | Code | A model can be confidently wrong. Cited sections are verified against the procedure; if the procedure says mandatory escalation (e.g. matching name and date of birth), the AI cannot downgrade it to "false positive" (override is logged). |
| Final decision | Human | The AI only recommends. Each decision is stored with who, when, AI recommendation and rationale, comment and model versions. |

Data stays on the machine: models run behind a local OpenAI-compatible server (`127.0.0.1:8093`), the UI listens on
`127.0.0.1` only, and the database is a local SQLite file.

## Run it

Windows, Python 3.10+. Only dependency: Pillow.

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

.venv\Scripts\python generate_samples.py          # 14 fictional documents + data\ground_truth.json
.venv\Scripts\python evaluate.py --mock           # evaluation table + results\eval_<date>_mock.md
.venv\Scripts\python app.py --mock                # UI at http://127.0.0.1:8800
.venv\Scripts\python -m kyc.pipeline data\samples\s13_td1_srb.png --mock
.venv\Scripts\python -m unittest discover -s tests -v
```

Without `--mock` the pipeline calls `POST http://127.0.0.1:8093/v1/chat/completions` with models `surya-ocr` (OCR)
and `gemma4-12b` (extraction and triage). The first call can take minutes while a model loads (timeout 900 s,
one retry). Override the URL with the `KYC_LLM_URL` environment variable.

`--mock` is deterministic and needs no network: OCR text and extraction come from the ground truth. The mock triage
model is **deliberately over-confident on one pattern** (identical name and exact date of birth -> "false positive")
so that the guardrail visibly fires in the demo. Mock results therefore test the surrounding logic, not model quality.

## Sample set

14 images (ICAO TD1 ID cards with 3x30 MRZ and TD3 passports with 2x44 MRZ): 9 clean (one rotated/blurred/noisy,
one with a Polish surname `ŁUKASZEWICZ` -> `LUKASZEWICZ`), 1 expired, 1 altered document number (bad check digit),
1 surname mismatch between visual zone and MRZ, 1 true sanctions match, 1 false positive (similar name, different
date of birth and nationality). The watchlist has 25 entries.

## Limitations

- Prototype with fictional data; not production software and not a compliance product.
- Screening is simple fuzzy matching (difflib), not a production-grade engine; thresholds are illustrative.
- No fraud/forgery detection of the image itself (photo, security features), no liveness or face matching.
- Live-model behaviour (accuracy of OCR/extraction/triage) must still be measured with `evaluate.py` without `--mock`.
- No authentication on the local UI; it is meant for a single user on localhost.

## Author

Daniel Szczęśniak. Specified and reviewed by Daniel, implemented with AI coding agents (Claude Code).
