"""Local web UI (standard library only). python app.py [--mock] [--port 8800]"""
import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from kyc import db, llm, pipeline

ROOT = Path(__file__).parent
SAMPLES = ROOT / "data" / "samples"
INDEX = ROOT / "web" / "index.html"
DECISIONS = ("approve", "reject", "escalate")
STATE = {"mock": False, "con": None, "lock": threading.Lock()}


def load_all(mock):
    """Process every sample not yet stored for this mode."""
    con = STATE["con"]
    for p in sorted(SAMPLES.glob("*.png")):
        row = db.get_doc(con, p.name)
        if row and row["mode"] == ("mock" if mock else "live"):
            continue
        print(f"processing {p.name} ...", flush=True)
        try:
            db.save_result(con, pipeline.process(p, mock))
        except (llm.LLMError, KeyError) as e:
            print(f"  skipped {p.name}: {e}", file=sys.stderr)
            if isinstance(e, llm.LLMError):
                print("  model server unavailable; start it or use --mock", file=sys.stderr)
                return


def doc_result(filename):
    row = db.get_doc(STATE["con"], filename)
    return json.loads(row["result_json"]) if row else None


def summary(row):
    r = json.loads(row["result_json"])
    ex = r["extracted"]
    decs = db.decisions(STATE["con"], row["filename"])
    return {"filename": row["filename"], "name": f"{ex.get('given_names')} {ex.get('surname')}",
            "doc_type": r["doc_type"], "status": r["overall"]["status"], "issues": r["issues"],
            "hits": len(r["hits"]), "decision": decs[0]["decision"] if decs else None}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if "json" in ctype or "html" in ctype else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        con = STATE["con"]
        if path == "/":
            return self.send(200, INDEX.read_bytes(), "text/html")
        if path == "/api/info":
            return self.send(200, {"mode": "mock" if STATE["mock"] else "live"})
        if path == "/api/documents":
            rows = con.execute("SELECT * FROM documents ORDER BY filename").fetchall()
            return self.send(200, [summary(r) for r in rows])
        if path.startswith("/api/document/"):
            fn = Path(path[len("/api/document/"):]).name
            r = doc_result(fn)
            if not r:
                return self.send(404, {"error": "not found"})
            r["decisions"] = db.decisions(con, fn)
            return self.send(200, r)
        if path == "/api/audit":
            return self.send(200, db.decisions(con))
        if path.startswith("/image/"):
            f = SAMPLES / Path(path[len("/image/"):]).name
            if f.is_file():
                return self.send(200, f.read_bytes(), "image/png")
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/decision":
            return self.send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(n))
        except (ValueError, json.JSONDecodeError):
            return self.send(400, {"error": "invalid JSON"})
        fn, decision = Path(str(d.get("filename", ""))).name, d.get("decision")
        comment, who = str(d.get("comment", "")).strip(), str(d.get("decided_by", "")).strip()
        r = doc_result(fn)
        if not r:
            return self.send(404, {"error": "unknown document"})
        if decision not in DECISIONS:
            return self.send(400, {"error": "decision must be approve, reject or escalate"})
        if not comment or not who:
            return self.send(400, {"error": "analyst name and comment are required (§8)"})
        recs = [f"{h['watchlist_id']}:{h['triage']['recommendation']}" for h in r["hits"]]
        ai_rec = "; ".join(recs) or "no hits (overall: " + r["overall"]["status"] + ")"
        ai_why = " | ".join(h["triage"]["rationale"] for h in r["hits"]) or "; ".join(r["overall"]["reasons"])
        with STATE["lock"]:
            db.add_decision(STATE["con"], fn, who[:80], decision, comment[:2000], ai_rec, ai_why, r["models"])
        self.send(200, {"ok": True})


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="offline deterministic mode")
    ap.add_argument("--port", type=int, default=8800)
    a = ap.parse_args()
    STATE["mock"] = a.mock
    STATE["con"] = db.connect()
    load_all(a.mock)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"KYC demo ({'MOCK' if a.mock else 'LIVE'}) on http://127.0.0.1:{a.port}  (Ctrl+C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
