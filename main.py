"""
SEC EDGAR Signals — Apify actor (zero third-party dependencies; Python stdlib only).

Actions (set via input `action`):
  - snapshot            -> one public company's profile + latest financials + recent filings
  - funding_leads       -> newest Form D filings (freshly funded / raising companies = sales leads)
  - insider_transactions-> Form 4 insider buys/sells for a company (directors/officers/10% owners)
  - filing_search       -> full-text search across filings (e.g. 'cybersecurity' in 10-K)

Input is read from, in order: Apify env (INPUT_JSON/APIFY_INPUT), a local file given as argv[1],
or command-line JSON. Results are pushed to the Apify dataset when APIFY_TOKEN is present, and
always printed to stdout.
"""
import sys, os, json, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import edgar  # noqa: E402


def read_input():
    raw = os.environ.get("APIFY_INPUT_JSON") or os.environ.get("INPUT_JSON")
    if raw:
        return json.loads(raw)
    src = os.environ.get("APIFY_INPUT_SOURCE") or os.environ.get("INPUT_PATH")
    if src and os.path.exists(src):
        return json.load(open(src, encoding="utf-8"))
    if len(sys.argv) > 1:
        p = sys.argv[1]
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
        return json.loads(p)
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def push_to_dataset(items):
    """Push items to the Apify default dataset; no-op locally."""
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        return False
    run_id = os.environ.get("APIFY_ACTOR_RUN_ID") or os.environ.get("ACTOR_RUN_ID")
    if not run_id:
        return False
    if isinstance(items, dict):
        items = [items]
    url = f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items?token={token}"
    data = json.dumps(items).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30)
        return True
    except Exception as e:
        print(f"[warn] dataset push failed: {e}", file=sys.stderr)
        return False


def run(inp):
    action = (inp.get("action") or "snapshot").lower()
    if action == "snapshot":
        out = edgar.company_snapshot(inp.get("symbol") or inp.get("ticker") or inp.get("cik"))
    elif action == "funding_leads":
        out = edgar.funding_leads(
            days_back=int(inp.get("days_back", 30)),
            limit=int(inp.get("limit", 50)),
            keyword=inp.get("keyword"),
        )
    elif action in ("insider_transactions", "insider", "form4"):
        out = edgar.insider_transactions(
            inp.get("symbol") or inp.get("ticker") or inp.get("cik"),
            limit=int(inp.get("limit", 15)),
        )
    elif action in ("filing_search", "search"):
        forms = inp.get("forms")
        if isinstance(forms, str):
            forms = [forms]
        out = edgar.filing_search(
            inp.get("keyword") or inp.get("query") or "",
            forms=forms,
            days_back=int(inp.get("days_back", 365)),
            limit=int(inp.get("limit", 25)),
        )
    else:
        out = {"error": f"unknown action '{action}'",
               "allowed": ["snapshot", "funding_leads", "insider_transactions", "filing_search"]}
    out["_meta"] = {"actor": "edgar-signals", "action": action, "source": "SEC EDGAR (public, free)"}
    return out


def main():
    inp = read_input()
    result = run(inp)
    # funding_leads: one dataset item per lead (works with pay-per-result). Others: one item.
    if inp.get("action") == "funding_leads" and result.get("leads"):
        items = [dict(lead, signal="fresh_form_d_funding") for lead in result["leads"]]
        push_to_dataset(items)
        result["_pushed_items"] = len(items)
    else:
        push_to_dataset(result)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
