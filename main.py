"""SEC EDGAR Signals — Apify Actor entry point (Python standard library only).

One run performs one of four actions:
  funding_leads, insider_transactions, snapshot, or filing_search.

The Actor writes customer-visible records to the default dataset and writes the
complete run result to the default key-value store under OUTPUT. For fair PPE
billing, errors and zero-result funding runs never create a paid dataset item.
"""
from datetime import datetime, timezone
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import edgar  # noqa: E402

ACTOR_VERSION = "1.0"
CANONICAL_ACTIONS = (
    "funding_leads", "insider_transactions", "snapshot", "filing_search",
)
ACTION_ALIASES = {
    "funding_leads": "funding_leads",
    "insider_transactions": "insider_transactions",
    "insider": "insider_transactions",
    "form4": "insider_transactions",
    "snapshot": "snapshot",
    "filing_search": "filing_search",
    "search": "filing_search",
}


def _api_base():
    return os.environ.get("APIFY_API_BASE_URL", "https://api.apify.com").rstrip("/")


def _apify_request(url, data=None, method=None, content_type="application/json", timeout=45):
    """Authenticated Apify request with bounded retries for transient failures."""
    token = os.environ.get("APIFY_TOKEN")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    last_error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code == 429 or 500 <= error.code < 600:
                time.sleep(0.75 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            time.sleep(0.75 * (attempt + 1))
    raise last_error


def _read_apify_input():
    """Read input across current and legacy Apify container conventions."""
    for env_name in ("APIFY_INPUT_PATH", "ACTOR_INPUT_PATH", "APIFY_ACTOR_INPUT_PATH"):
        path = os.environ.get(env_name)
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as file:
                return json.load(file)

    candidates = []
    candidates += glob.glob("/data/key-value-stores/*/INPUT*.json")
    candidates += glob.glob("/data/key-value-stores/*/INPUT")
    candidates += glob.glob("/data/inputs/**/input.json", recursive=True)
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            continue

    store_id = os.environ.get("APIFY_DEFAULT_KEY_VALUE_STORE_ID")
    if os.environ.get("APIFY_TOKEN") and store_id:
        url = f"{_api_base()}/v2/key-value-stores/{store_id}/records/INPUT"
        try:
            return json.loads(_apify_request(url, timeout=20).decode("utf-8"))
        except Exception:
            return None
    return None


def read_input():
    raw = os.environ.get("APIFY_INPUT_JSON") or os.environ.get("INPUT_JSON")
    if raw:
        return json.loads(raw)
    platform_input = _read_apify_input()
    if platform_input is not None:
        return platform_input
    path = os.environ.get("INPUT_PATH")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    if len(sys.argv) > 1:
        value = sys.argv[1]
        if os.path.exists(value):
            with open(value, encoding="utf-8") as file:
                return json.load(file)
        return json.loads(value)
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def _integer(value, default, minimum, maximum):
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _boolean(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _error(message, action=None):
    return {
        "record_type": "error",
        "error": message,
        "allowed_actions": list(CANONICAL_ACTIONS),
        "_billing": {"billable_items": 0, "reason": "error"},
        "_pushed_items": 0,
        "_meta": {
            "actor": "edgar-signals",
            "version": ACTOR_VERSION,
            "action": action,
            "status": "failed",
            "source": "SEC EDGAR (official public filings)",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def run(inp):
    """Validate input, call the selected action, and attach provenance metadata."""
    if not isinstance(inp, dict):
        return _error("Input must be a JSON object")
    raw_action = str(inp.get("action") or "funding_leads").strip().lower()
    action = ACTION_ALIASES.get(raw_action)
    if not action:
        return _error(f"Unknown action '{raw_action}'", raw_action)

    days_back = _integer(inp.get("days_back"), 30, 1, 3650)
    limit = _integer(inp.get("limit"), 50, 1, 500)

    if action == "funding_leads":
        result = edgar.funding_leads(
            days_back=days_back,
            limit=limit,
            keyword=(str(inp.get("keyword") or "").strip() or None),
            exclude_funds=_boolean(inp.get("exclude_funds"), True),
            exclude_real_estate=_boolean(inp.get("exclude_real_estate"), True),
            industries=_list(inp.get("industries")),
            states=_list(inp.get("states")),
            min_amount_raised_usd=max(0, _number(inp.get("min_amount_raised_usd"))),
            max_amount_raised_usd=max(0, _number(inp.get("max_amount_raised_usd"))),
            only_with_phone=_boolean(inp.get("only_with_phone"), False),
            only_with_executives=_boolean(inp.get("only_with_executives"), False),
            include_amendments=_boolean(inp.get("include_amendments"), False),
        )
    elif action in ("snapshot", "insider_transactions"):
        symbol = inp.get("symbol") or inp.get("ticker") or inp.get("cik")
        if symbol is None or not str(symbol).strip():
            return _error(f"'{action}' requires symbol (ticker or CIK)", action)
        if action == "snapshot":
            result = edgar.company_snapshot(symbol)
        else:
            result = edgar.insider_transactions(symbol, limit=limit)
    else:
        keyword = str(inp.get("keyword") or inp.get("query") or "").strip()
        if not keyword:
            return _error("'filing_search' requires a non-empty keyword", action)
        result = edgar.filing_search(
            keyword,
            forms=_list(inp.get("forms")) or None,
            days_back=days_back,
            limit=limit,
        )

    if result.get("error"):
        result["_meta"] = _error(result["error"], action)["_meta"]
        return result
    result["_meta"] = {
        "actor": "edgar-signals",
        "version": ACTOR_VERSION,
        "action": action,
        "status": "succeeded",
        "source": "SEC EDGAR (official public filings)",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def push_to_dataset(items):
    """Push result rows in bounded chunks; return the number written.

    An empty list deliberately produces zero writes (and therefore zero synthetic
    dataset-item charges under pay-per-event pricing).
    """
    if isinstance(items, dict):
        items = [items]
    items = list(items or [])
    if not items:
        return 0

    token = os.environ.get("APIFY_TOKEN")
    dataset_id = os.environ.get("APIFY_DEFAULT_DATASET_ID")
    run_id = os.environ.get("APIFY_ACTOR_RUN_ID") or os.environ.get("ACTOR_RUN_ID")
    if not token or not (dataset_id or run_id):
        return 0  # local execution

    url = (
        f"{_api_base()}/v2/datasets/{dataset_id}/items"
        if dataset_id else f"{_api_base()}/v2/actor-runs/{run_id}/dataset/items"
    )
    written = 0
    for offset in range(0, len(items), 100):
        chunk = items[offset:offset + 100]
        payload = json.dumps(chunk, separators=(",", ":"), default=str).encode("utf-8")
        _apify_request(url, data=payload, method="POST", timeout=60)
        written += len(chunk)
    return written


def save_output(result):
    """Save the complete result as the conventional OUTPUT KVS record."""
    token = os.environ.get("APIFY_TOKEN")
    store_id = os.environ.get("APIFY_DEFAULT_KEY_VALUE_STORE_ID")
    if not token or not store_id:
        return False
    url = f"{_api_base()}/v2/key-value-stores/{store_id}/records/OUTPUT"
    payload = json.dumps(result, separators=(",", ":"), default=str).encode("utf-8")
    _apify_request(url, data=payload, method="PUT", timeout=45)
    return True


def _dataset_items(result):
    action = result.get("_meta", {}).get("action")
    if action == "funding_leads":
        retrieved_at = result["_meta"]["retrieved_at"]
        return [
            dict(
                lead,
                action="funding_leads",
                signal="fresh_form_d_funding",
                source="SEC EDGAR",
                retrieved_at=retrieved_at,
            )
            for lead in result.get("leads", [])
        ]
    # Snapshot, insider, and filing search are each one structured intelligence
    # result. This also keeps those utility actions inexpensive under PPE.
    return [result]


def main():
    inp = read_input()
    result = run(inp)

    if result.get("error"):
        try:
            save_output(result)
        finally:
            print(json.dumps(result, indent=2, default=str))
        raise SystemExit(2)

    try:
        items = _dataset_items(result)
        result["_pushed_items"] = push_to_dataset(items)
        save_output(result)
    except Exception as error:
        failure = _error(f"Could not persist Actor output: {error}", result.get("_meta", {}).get("action"))
        try:
            save_output(failure)
        finally:
            print(json.dumps(failure, indent=2, default=str))
        raise SystemExit(3)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
