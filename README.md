# SEC EDGAR Signals — Apify Actor

**Structured, agent-ready signals from SEC EDGAR — free, no API key, stable official APIs.**

## Why this actor
SEC EDGAR is the free public record of every US public company and every private company
that raises capital (Form D). The data is high-value but tedious to pull and normalize.
This actor turns it into clean JSON for sales teams, investors, and AI agents:

| Action | What it returns | Who pays for it |
|---|---|---|
| `funding_leads` | Newest **Form D** filings — companies that *just raised* (name, date, CIK, filing link). Thousands file/month. | B2B sales / agencies prospecting freshly-funded startups |
| `insider_transactions` | **Form 4** buys & sells by directors/officers/10% owners (name, role, buy/sell, shares, price, value) | Investors tracking insider sentiment |
| `snapshot` | Company profile + latest revenue/net-income/assets/employees + recent 10-K/10-Q/8-K | Equity research, RAG, enrichment |
| `filing_search` | Full-text search across filings (e.g. "cybersecurity" in 10-K) with company + date | Compliance/competitive intel |

- **Data source:** SEC EDGAR (`data.sec.gov`, `efts.sec.gov`, `www.sec.gov`) — official, free, no key.
- **Zero dependencies** — Python standard library only. Reliable (JSON/XML APIs, not fragile HTML scraping).
- Outputs one dataset row per funding lead (works with **pay-per-result** billing).

## Input
```json
{ "action": "funding_leads", "days_back": 30, "limit": 50 }
{ "action": "insider_transactions", "symbol": "NVDA", "limit": 15 }
{ "action": "snapshot", "symbol": "AAPL" }
{ "action": "filing_search", "keyword": "cybersecurity", "forms": ["10-K"], "days_back": 180, "limit": 25 }
```

## Run locally
```bash
python3 main.py '{"action":"insider_transactions","symbol":"TSLA","limit":3}'
```

## Market note
EDGAR actors on the store exist but none has traction (largest ≈ 89 users vs 589K for the
top scrapers) — the category has demand (Form D funding leads, insider trades) but no
dominant, reliable, well-positioned tool. This actor is built to win on reliability + clean
output + agent-friendly schema.
