import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kyc import llm, mrz, screening, triage, validate  # noqa: E402
from kyc.textnorm import name_variants, normalize_name, strip_diacritics  # noqa: E402

PROC = triage.load_procedure()
SECTIONS = triage.valid_sections(PROC)


class TestMrz(unittest.TestCase):
    def test_icao_example_digits(self):
        self.assertEqual(mrz.check_digit("L898902C3"), 6)
        self.assertEqual(mrz.check_digit("740812"), 2)
        self.assertEqual(mrz.check_digit("120415"), 9)
        self.assertEqual(mrz.check_digit("ZE184226B<<<<<"), 1)

    def test_icao_example_parse(self):
        r = mrz.parse_mrz(["P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
                           "L898902C36UTO7408122F1204159ZE184226B<<<<<10"])
        self.assertTrue(r["ok"])
        self.assertTrue(all(c["ok"] for c in r["checks"]), r["checks"])
        self.assertEqual(r["fields"]["surname"], "ERIKSSON")
        self.assertEqual(r["fields"]["given_names"], "ANNA MARIA")

    def test_td1_roundtrip_and_tamper(self):
        lines = mrz.build_td1("POL", "NOWAK", "TOMASZ", "ZK4417203", "POL", date(1979, 9, 3), "M", date(2032, 1, 14))
        self.assertEqual([len(l) for l in lines], [30, 30, 30])
        self.assertTrue(all(c["ok"] for c in mrz.parse_mrz(lines)["checks"]))
        lines[0] = lines[0][:5] + "ZK4417209" + lines[0][14:]
        bad = [c["name"] for c in mrz.parse_mrz(lines)["checks"] if not c["ok"]]
        self.assertIn("cd_document_number", bad)
        self.assertIn("cd_composite", bad)

    def test_wrong_layout(self):
        self.assertFalse(mrz.parse_mrz(["ABC", "DEF"])["ok"])


class TestTranslit(unittest.TestCase):
    def test_polish_and_german(self):
        self.assertEqual(strip_diacritics("ŁUKASZEWICZ"), "LUKASZEWICZ")
        self.assertEqual(normalize_name("Wiśniewski-Żółć"), "WISNIEWSKI ZOLC")
        self.assertEqual(name_variants("Müller"), {"MULLER", "MUELLER"})
        self.assertEqual(normalize_name("O'Brien"), "OBRIEN")

    def test_mrz_form(self):
        lines = mrz.build_td3("POL", "ŁUKASZEWICZ", "AGNIESZKA", "EL7291044", "POL", date(1991, 2, 17), "F",
                              date(2032, 7, 7))
        self.assertTrue(lines[0].startswith("P<POLLUKASZEWICZ<<AGNIESZKA"))


class TestScreening(unittest.TestCase):
    wl = json.loads((Path(__file__).resolve().parent.parent / "data" / "watchlist.json").read_text("utf-8"))

    def cust(self, **k):
        return dict({"surname": "DRAGOMIROVIC", "given_names": "MILOS", "date_of_birth": "1971-05-23",
                     "nationality": "SRB"}, **k)

    def test_true_match_scores_high(self):
        h = screening.screen(self.cust(), self.wl)[0]
        self.assertEqual(h["watchlist_id"], "W-001")
        self.assertEqual(h["name_score"], 100.0)
        self.assertEqual(h["dob_status"], "exact")
        self.assertEqual(h["total"], 100.0)
        self.assertTrue(screening.procedure_rules(h)["mandatory_escalation"])

    def test_false_positive_scores_lower(self):
        h = screening.screen(self.cust(surname="DRAGOMIROWICZ", given_names="MILOSZ",
                                       date_of_birth="1988-11-02", nationality="POL"), self.wl)[0]
        self.assertEqual(h["dob_status"], "mismatch")
        self.assertLess(h["total"], 50)
        r = screening.procedure_rules(h)
        self.assertTrue(r["closeable"] and not r["mandatory_escalation"])

    def test_year_only_and_token_order(self):
        self.assertEqual(screening.compare_dob("1975-03-01", "1975"), "year_match")
        self.assertEqual(screening.compare_dob("1976-03-01", "1975"), "mismatch")
        self.assertEqual(screening.compare_dob(None, "1975"), "unknown")
        self.assertEqual(screening.best_name_score("Hassan Mohammed Ali", "Mohammed Ali Hassan"), 100.0)

    def test_alias_and_umlaut(self):
        hits = screening.screen(self.cust(surname="MÜLLER", given_names="HANS", date_of_birth="1990-01-01",
                                          nationality="DEU"), self.wl)
        self.assertTrue(any(h["watchlist_id"] == "W-009" for h in hits))
        hits = screening.screen(self.cust(surname="DRAGOMIROVICH", given_names="MILOSH"), self.wl)
        self.assertEqual(hits[0]["matched_name"], "Milosh Dragomirovich")


class TestGuardrails(unittest.TestCase):
    esc = {"mandatory_escalation": True, "closeable": False, "sections": ["§7"], "explanation": ""}
    ok = {"mandatory_escalation": False, "closeable": True, "sections": ["§6"], "explanation": ""}

    def ai(self, rec="likely_false_positive", cited=("§6",)):
        return {"recommendation": rec, "rationale": "x", "cited_sections": list(cited), "fields_used": ["name"]}

    def test_sections_found(self):
        self.assertEqual(SECTIONS, {f"§{i}" for i in range(1, 9)})

    def test_override_on_mandatory_escalation(self):
        f = triage.apply_guardrails(self.ai(), self.esc, SECTIONS)
        self.assertEqual(f["recommendation"], "needs_review")
        self.assertEqual(f["raw_recommendation"], "likely_false_positive")
        self.assertTrue(any("guardrail override" in n for n in f["guardrail_notes"]))
        self.assertFalse(f["closed"])

    def test_false_positive_allowed_when_closeable(self):
        f = triage.apply_guardrails(self.ai(), self.ok, SECTIONS)
        self.assertEqual(f["recommendation"], "likely_false_positive")
        self.assertEqual(f["guardrail_notes"], [])
        self.assertFalse(f["closed"])

    def test_invented_section_rejected(self):
        f = triage.apply_guardrails(self.ai(cited=("§6", "§99")), self.ok, SECTIONS)
        self.assertEqual(f["recommendation"], "needs_review")
        self.assertTrue(any("§99" in n for n in f["guardrail_notes"]))

    def test_garbage_output(self):
        for bad in (None, {}, {"recommendation": "close_case", "cited_sections": ["§6"]}):
            self.assertEqual(triage.apply_guardrails(bad, self.ok, SECTIONS)["recommendation"], "needs_review")


class TestHelpers(unittest.TestCase):
    def test_json_parser(self):
        self.assertEqual(llm.parse_json_block('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(llm.parse_json_block('Sure! {"a": {"b": 2}} done'), {"a": {"b": 2}})
        with self.assertRaises(ValueError):
            llm.parse_json_block("no json here")

    def test_expiry_check(self):
        ex = {"mrz_lines": [], "expiry_date": "2020-01-01", "date_of_birth": "1980-01-01"}
        c = {x["name"]: x["status"] for x in validate.run_checks(ex, date(2026, 1, 1))}
        self.assertEqual(c["not_expired"], "fail")
        self.assertEqual(c["mrz_format"], "fail")


class TestMrzNormalization(unittest.TestCase):
    def test_pads_dropped_trailing_fillers(self):
        from kyc.extract import normalize_mrz
        # a real gemma4-12b reply: each TD1 line came back one '<' short
        got = normalize_mrz(["I<SRBRS00482155<<<<<<<<<<<<<<", "7105236M3012017SRB<<<<<<<<<<6",
                             "DRAGOMIROVIC<<MILOS <<<<<<<<<<"])
        self.assertEqual([len(x) for x in got], [30, 30, 30])
        self.assertEqual(got[1], "7105236M3012017SRB<<<<<<<<<<<6")  # check digit stays last
        self.assertTrue(got[2].startswith("DRAGOMIROVIC<<MILOS<<"))

    def test_trims_extra_fillers_keeps_check_digit(self):
        from kyc.extract import normalize_mrz
        # a real gemma4-12b reply with one '<' too many before the composite check digit
        got = normalize_mrz(["I<POLZK44172034<<<<<<<<<<<<<<<", "7909032M3201141POL<<<<<<<<<<<<4",
                             "NOWAK<<TOMASZ<JAN<<<<<<<<<<<<<"])
        self.assertEqual(got[1], "7909032M3201141POL<<<<<<<<<<<4")

    def test_never_cuts_data(self):
        from kyc.extract import normalize_mrz
        self.assertEqual(normalize_mrz(["A" * 46, "B" * 44]), ["A" * 46, "B" * 44])


if __name__ == "__main__":
    unittest.main()
