"""Step d: SQLite persistence incl. the decision audit log."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "runtime" / "kyc.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, full_name TEXT, date_of_birth TEXT,
  nationality TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, customer_id INTEGER, filename TEXT UNIQUE,
  doc_type TEXT, mode TEXT, ocr_text TEXT, extracted_json TEXT, result_json TEXT, status TEXT,
  model_versions TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY, document_id INTEGER, name TEXT, status TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS screening_hits(id INTEGER PRIMARY KEY, document_id INTEGER, watchlist_id TEXT,
  score REAL, breakdown_json TEXT, ai_recommendation TEXT, ai_rationale TEXT, cited_sections TEXT,
  guardrail_notes TEXT);
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, filename TEXT, decided_by TEXT, decided_at TEXT,
  decision TEXT, ai_recommendation TEXT, ai_rationale TEXT, comment TEXT, model_versions TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None):
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def get_doc(con, filename):
    return con.execute("SELECT * FROM documents WHERE filename=?", (filename,)).fetchone()


def save_result(con, r):
    """Store one pipeline result (replaces an earlier run of the same file). Decisions are kept."""
    old = get_doc(con, r["filename"])
    if old:
        for t in ("checks", "screening_hits"):
            con.execute(f"DELETE FROM {t} WHERE document_id=?", (old["id"],))
        con.execute("DELETE FROM documents WHERE id=?", (old["id"],))
        con.execute("DELETE FROM customers WHERE id=?", (old["customer_id"],))
    ex = r["extracted"]
    cur = con.execute("INSERT INTO customers(full_name,date_of_birth,nationality,created_at) VALUES(?,?,?,?)",
                      (f"{ex.get('given_names')} {ex.get('surname')}", ex.get("date_of_birth"),
                       ex.get("nationality"), now()))
    cid = cur.lastrowid
    cur = con.execute(
        "INSERT INTO documents(customer_id,filename,doc_type,mode,ocr_text,extracted_json,result_json,status,"
        "model_versions,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (cid, r["filename"], r.get("doc_type"), r["mode"], r["ocr_text"], json.dumps(ex, ensure_ascii=False),
         json.dumps(r, ensure_ascii=False), r["overall"]["status"], json.dumps(r["models"]), now()))
    did = cur.lastrowid
    for c in r["checks"]:
        con.execute("INSERT INTO checks(document_id,name,status,reason) VALUES(?,?,?,?)",
                    (did, c["name"], c["status"], c["reason"]))
    for h in r["hits"]:
        t = h["triage"]
        con.execute("INSERT INTO screening_hits(document_id,watchlist_id,score,breakdown_json,ai_recommendation,"
                    "ai_rationale,cited_sections,guardrail_notes) VALUES(?,?,?,?,?,?,?,?)",
                    (did, h["watchlist_id"], h["total"], json.dumps(h, ensure_ascii=False), t["recommendation"],
                     t["rationale"], json.dumps(t["cited_sections"]), json.dumps(t["guardrail_notes"])))
    con.commit()


def add_decision(con, filename, decided_by, decision, comment, ai_rec, ai_rationale, models):
    con.execute("INSERT INTO decisions(filename,decided_by,decided_at,decision,ai_recommendation,ai_rationale,"
                "comment,model_versions) VALUES(?,?,?,?,?,?,?,?)",
                (filename, decided_by, now(), decision, ai_rec, ai_rationale, comment, json.dumps(models)))
    con.commit()


def decisions(con, filename=None):
    q, a = "SELECT * FROM decisions", ()
    if filename:
        q, a = q + " WHERE filename=?", (filename,)
    return [dict(r) for r in con.execute(q + " ORDER BY id DESC", a)]
