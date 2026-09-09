"""Production-shaped, zero-dependency HTTP wrapper for SEC EDGAR Signals.

The public Render deployment is an evaluation API and interactive documentation.
The Apify Actor remains the production/scheduled product and uses the same core.
"""
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
import urllib.error
from urllib.parse import parse_qs, urlparse
import uuid

from main import run as actor_run

VERSION = "1.0.0"
ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC_LIMIT = 100
MAX_BODY_BYTES = 1_000_000
RATE_WINDOW_SECONDS = 60
RATE_REQUESTS = 30
_rate_lock = threading.Lock()
_rate_windows = defaultdict(deque)


def _client_allowed(client):
    now = time.monotonic()
    with _rate_lock:
        window = _rate_windows[client]
        while window and now - window[0] > RATE_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= RATE_REQUESTS:
            return False, 0
        window.append(now)
        return True, RATE_REQUESTS - len(window)


def _cap_input(inp):
    """Protect the shared public demo while leaving the Apify Actor limit at 500."""
    data = dict(inp or {})
    try:
        data["limit"] = max(1, min(int(data.get("limit", 25)), PUBLIC_LIMIT))
    except (TypeError, ValueError):
        data["limit"] = 25
    return data


def dispatch(inp):
    return actor_run(_cap_input(inp))


class Handler(BaseHTTPRequestHandler):
    server_version = "EDGARSignals/1.0"

    def log_message(self, format_string, *args):
        # Minimal structured access log; never log query strings (which can contain
        # user research terms) or authorization headers.
        print(json.dumps({
            "event": "http_request",
            "method": self.command,
            "path": urlparse(self.path).path,
            "client": self.client_address[0],
            "message": format_string % args,
        }), flush=True)

    def _common_headers(self, content_type, length, cache="no-store", request_id=None):
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if request_id:
            self.send_header("X-Request-ID", request_id)

    def _send_bytes(self, code, body, content_type, cache="no-store", request_id=None, head=False):
        self.send_response(code)
        self._common_headers(content_type, len(body), cache, request_id)
        if content_type.startswith("text/html"):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'self'",
            )
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _send_json(self, code, obj, request_id=None, cache="no-store", head=False):
        if isinstance(obj, dict) and request_id and "request_id" not in obj:
            obj = dict(obj, request_id=request_id)
        body = json.dumps(obj, default=str, separators=(",", ":")).encode("utf-8")
        self._send_bytes(code, body, "application/json; charset=utf-8", cache, request_id, head)

    def _client_key(self):
        forwarded = self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        return forwarded or self.client_address[0]

    def _public_file(self, relative_path):
        with open(os.path.join(ROOT, relative_path), "rb") as file:
            return file.read()

    def _result(self, result, request_id, head=False):
        if result.get("error"):
            status = 404 if "Could not resolve" in result["error"] else 400
            return self._send_json(status, result, request_id, head=head)
        return self._send_json(200, result, request_id, head=head)

    def _handle_get(self, head=False):
        started = time.monotonic()
        request_id = uuid.uuid4().hex[:12]
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        try:
            if path in ("/", "/docs"):
                body = self._public_file("web/index.html")
                return self._send_bytes(200, body, "text/html; charset=utf-8", "public, max-age=300", request_id, head)
            if path == "/openapi.json":
                body = self._public_file("openapi.json")
                return self._send_bytes(200, body, "application/json; charset=utf-8", "public, max-age=300", request_id, head)
            if path in ("/favicon.svg", "/assets/logo.svg"):
                body = self._public_file("assets/edgar-signals-logo.svg")
                return self._send_bytes(200, body, "image/svg+xml", "public, max-age=86400", request_id, head)
            if path == "/assets/logo.png":
                body = self._public_file("assets/edgar-signals-logo.png")
                return self._send_bytes(200, body, "image/png", "public, max-age=86400", request_id, head)
            if path in ("/health", "/status"):
                return self._send_json(200, {
                    "ok": True,
                    "service": "edgar-signals",
                    "version": VERSION,
                    "source": "SEC EDGAR",
                    "actor": "educable_santoor/edgar-signals",
                }, request_id, cache="public, max-age=20", head=head)
            if path == "/api":
                return self._send_json(200, {
                    "service": "SEC EDGAR Signals API",
                    "version": VERSION,
                    "documentation": "/docs",
                    "openapi": "/openapi.json",
                    "routes": ["/funding_leads", "/snapshot", "/insider", "/search", "/run"],
                    "public_demo_limit": PUBLIC_LIMIT,
                }, request_id, cache="public, max-age=60", head=head)

            allowed, remaining = _client_allowed(self._client_key())
            if not allowed:
                self.send_response(429)
                body = json.dumps({
                    "error": "Public demo rate limit reached; retry in one minute or use the Apify Actor.",
                    "request_id": request_id,
                }, separators=(",", ":")).encode("utf-8")
                self._common_headers("application/json; charset=utf-8", len(body), "no-store", request_id)
                self.send_header("Retry-After", str(RATE_WINDOW_SECONDS))
                self.send_header("X-RateLimit-Limit", str(RATE_REQUESTS))
                self.send_header("X-RateLimit-Remaining", "0")
                self.end_headers()
                if not head:
                    self.wfile.write(body)
                return

            query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            if path == "/snapshot":
                result = dispatch({"action": "snapshot", "symbol": query.get("symbol")})
            elif path == "/funding_leads":
                result = dispatch({
                    "action": "funding_leads",
                    "days_back": query.get("days_back", 30),
                    "limit": query.get("limit", 25),
                    "keyword": query.get("keyword") or None,
                    "industries": query.get("industries") or "",
                    "states": query.get("states") or "",
                    "min_amount_raised_usd": query.get("min_amount_raised_usd", 0),
                    "max_amount_raised_usd": query.get("max_amount_raised_usd", 0),
                    "only_with_phone": query.get("only_with_phone", "false"),
                    "only_with_executives": query.get("only_with_executives", "false"),
                    "exclude_funds": query.get("exclude_funds", "true"),
                    "exclude_real_estate": query.get("exclude_real_estate", "true"),
                    "include_amendments": query.get("include_amendments", "false"),
                })
            elif path == "/insider":
                result = dispatch({
                    "action": "insider_transactions",
                    "symbol": query.get("symbol"),
                    "limit": query.get("limit", 15),
                })
            elif path == "/search":
                result = dispatch({
                    "action": "filing_search",
                    "keyword": query.get("keyword"),
                    "forms": query.get("forms"),
                    "days_back": query.get("days_back", 365),
                    "limit": query.get("limit", 25),
                })
            else:
                return self._send_json(404, {
                    "error": "Route not found",
                    "documentation": "/docs",
                    "openapi": "/openapi.json",
                }, request_id, head=head)

            if isinstance(result, dict):
                result.setdefault("_http", {})
                result["_http"].update({
                    "request_id": request_id,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "demo_rate_limit_remaining": remaining,
                })
            return self._result(result, request_id, head)
        except urllib.error.HTTPError as error:
            code = 503 if error.code in (429, 500, 502, 503, 504) else 502
            return self._send_json(code, {
                "error": "The SEC upstream service did not complete this request.",
                "upstream_status": error.code,
                "retryable": error.code in (429, 500, 502, 503, 504),
            }, request_id, head=head)
        except (urllib.error.URLError, TimeoutError) as error:
            return self._send_json(503, {
                "error": "The SEC upstream service is temporarily unreachable.",
                "retryable": True,
            }, request_id, head=head)
        except Exception:
            # Do not leak stack traces or filesystem paths to public clients.
            return self._send_json(500, {
                "error": "Unexpected service error.",
                "retryable": True,
            }, request_id, head=head)

    def do_GET(self):
        self._handle_get(False)

    def do_HEAD(self):
        self._handle_get(True)

    def do_OPTIONS(self):
        self.send_response(204)
        self._common_headers("text/plain; charset=utf-8", 0, "public, max-age=86400")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_POST(self):
        request_id = uuid.uuid4().hex[:12]
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/run":
            return self._send_json(404, {"error": "Route not found", "documentation": "/docs"}, request_id)

        allowed, _ = _client_allowed(self._client_key())
        if not allowed:
            return self._send_json(429, {"error": "Public demo rate limit reached; retry in one minute."}, request_id)
        try:
            size = int(self.headers.get("Content-Length", 0))
            if size <= 0:
                return self._send_json(400, {"error": "A JSON request body is required."}, request_id)
            if size > MAX_BODY_BYTES:
                return self._send_json(413, {"error": "Request body exceeds 1 MB."}, request_id)
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                return self._send_json(400, {"error": "Request body must be a JSON object."}, request_id)
            return self._result(dispatch(payload), request_id)
        except json.JSONDecodeError:
            return self._send_json(400, {"error": "Request body is not valid JSON."}, request_id)
        except urllib.error.HTTPError as error:
            return self._send_json(503, {
                "error": "The SEC upstream service did not complete this request.",
                "upstream_status": error.code,
            }, request_id)
        except Exception:
            return self._send_json(500, {"error": "Unexpected service error."}, request_id)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"SEC EDGAR Signals {VERSION} listening on 0.0.0.0:{port}", flush=True)
    Server(("0.0.0.0", port), Handler).serve_forever()
