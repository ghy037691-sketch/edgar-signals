"""
Zero-dependency HTTP wrapper around the EDGAR actor, for hosting the same logic
as a live JSON API (e.g. a free Render web service). Standard library only.

Routes (GET, params via query string):
  /health
  /snapshot?symbol=AAPL
  /funding_leads?days_back=30&limit=50&keyword=
  /insider?symbol=NVDA&limit=15
  /search?keyword=cybersecurity&forms=10-K&days_back=180&limit=25

POST /run with a JSON body uses the same input schema as the Apify actor.
"""
import json, sys, os, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import edgar  # noqa: E402


def _i(d, k, default):
    try:
        return int(d.get(k, default))
    except Exception:
        return default


def dispatch(inp):
    action = (inp.get("action") or "snapshot").lower()
    if action == "snapshot":
        return edgar.company_snapshot(inp.get("symbol") or inp.get("ticker") or inp.get("cik"))
    if action == "funding_leads":
        return edgar.funding_leads(_i(inp, "days_back", 30), _i(inp, "limit", 50), inp.get("keyword"))
    if action in ("insider_transactions", "insider", "form4"):
        return edgar.insider_transactions(inp.get("symbol") or inp.get("ticker") or inp.get("cik"),
                                          limit=_i(inp, "limit", 15))
    if action in ("filing_search", "search"):
        forms = inp.get("forms")
        if isinstance(forms, str):
            forms = [forms] if forms else None
        return edgar.filing_search(inp.get("keyword") or inp.get("query") or "",
                                   forms=forms, days_back=_i(inp, "days_back", 365),
                                   limit=_i(inp, "limit", 25))
    return {"error": f"unknown action '{action}'"}


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/health"):
                return self._send(200, {"ok": True, "service": "edgar-signals",
                                        "routes": ["/snapshot", "/funding_leads", "/insider", "/search"]})
            if u.path == "/snapshot":
                return self._send(200, dispatch({"action": "snapshot", "symbol": q.get("symbol")}))
            if u.path == "/funding_leads":
                return self._send(200, dispatch({"action": "funding_leads", "days_back": q.get("days_back", 30),
                                                 "limit": q.get("limit", 50), "keyword": q.get("keyword") or None}))
            if u.path == "/insider":
                return self._send(200, dispatch({"action": "insider", "symbol": q.get("symbol"),
                                                 "limit": q.get("limit", 15)}))
            if u.path == "/search":
                return self._send(200, dispatch({"action": "search", "keyword": q.get("keyword"),
                                                 "forms": q.get("forms"), "days_back": q.get("days_back", 365),
                                                 "limit": q.get("limit", 25)}))
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(500, {"error": str(e), "trace": traceback.format_exc()[:500]})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            inp = json.loads(self.rfile.read(n) or b"{}")
            return self._send(200, dispatch(inp))
        except Exception as e:
            return self._send(500, {"error": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"edgar-signals HTTP on 0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
