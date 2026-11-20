"""Step f: AI triage of screening hits + code guardrails. The AI only recommends."""
import json
import re
from pathlib import Path

from . import llm, mock

ROOT = Path(__file__).resolve().parent.parent
PROCEDURE_PATH = ROOT / "data" / "screening_procedure.md"
RECS = ("likely_false_positive", "needs_review", "likely_true_match")

PROMPT = """You are an AML screening assistant. Apply ONLY the procedure below to the hit.
You recommend, a human decides. Return ONLY a JSON object with keys:
recommendation (one of likely_false_positive | needs_review | likely_true_match),
rationale (2-3 sentences), cited_sections (list like ["§3","§6"], only sections that exist),
fields_used (list of the data fields you relied on).

PROCEDURE:
{procedure}

CUSTOMER:
{customer}

WATCHLIST HIT (with score breakdown):
{hit}
"""


def load_procedure():
    return PROCEDURE_PATH.read_text(encoding="utf-8")


def valid_sections(procedure_text):
    return set(re.findall(r"^#+\s*(§\d+)", procedure_text, flags=re.M))


def apply_guardrails(ai, rules, sections):
    """Return the final advisory result. Never 'closes' anything."""
    notes = []
    final = {"recommendation": "needs_review", "rationale": "", "cited_sections": [], "fields_used": [],
             "raw_recommendation": None, "guardrail_notes": notes, "closed": False}
    if not isinstance(ai, dict) or ai.get("recommendation") not in RECS:
        notes.append("guardrail: AI output missing or invalid -> needs_review")
        final["rationale"] = "No valid AI recommendation; analyst review required."
        return final
    final["raw_recommendation"] = ai["recommendation"]
    cited = ai.get("cited_sections") or []
    cited = [str(c) for c in cited] if isinstance(cited, list) else []
    bad = [c for c in cited if c not in sections]
    if bad or not cited:
        notes.append(f"guardrail: cited sections invalid or missing ({', '.join(bad) or 'none cited'}) "
                     "-> AI output rejected, needs_review")
        final["rationale"] = "AI output rejected by guardrail; analyst review required."
        return final
    final.update(recommendation=ai["recommendation"], rationale=str(ai.get("rationale", "")),
                 cited_sections=cited, fields_used=[str(x) for x in (ai.get("fields_used") or [])])
    if rules["mandatory_escalation"] and final["recommendation"] == "likely_false_positive":
        final["recommendation"] = "needs_review"
        notes.append("guardrail override: likely_false_positive -> needs_review "
                     f"(mandatory escalation, {', '.join(rules['sections'])})")
    return final


def triage_hit(customer, hit, rules, procedure_text, mock_mode):
    sections = valid_sections(procedure_text)
    try:
        if mock_mode:
            ai = mock.mock_triage(customer, hit)
        else:
            cust = {k: customer.get(k) for k in ("surname", "given_names", "date_of_birth", "nationality")}
            msgs = [{"role": "user", "content": PROMPT.format(
                procedure=procedure_text, customer=json.dumps(cust, ensure_ascii=False),
                hit=json.dumps(hit, ensure_ascii=False))}]
            ai = llm.parse_json_block(llm.chat(llm.LLM_MODEL, msgs, max_tokens=800))
    except (ValueError, llm.LLMError) as e:
        if isinstance(e, llm.LLMError):
            raise
        ai = None  # unparsable reply -> guardrail falls back to needs_review
    return apply_guardrails(ai, rules, sections)
