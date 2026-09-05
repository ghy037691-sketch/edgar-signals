# Apify Store — Ready-to-paste listing & monetization (EDGAR Signals)

> Actor: https://console.apify.com/actors/rDPJAe1kVKIOJyt6z  (`educable_santoor/edgar-signals`)

## 0. One-time account steps (identity/payout are yours — can't be done via API)
1. Apify console → **Settings → Profile → make profile Public** (required to publish).
2. Complete **identity verification (KYC)** in Billing/Settings — needed to (a) charge money and (b) be eligible for **agentic payments** (AI agents auto-running and paying you).
3. **Add PayPal** in Billing/Payouts (payouts to India, minimum $20, monthly, you keep ~80%).

## 1. Title (paste)
**SEC EDGAR Signals — New Funding Leads, Insider Trades, Company Intel**

## 2. Short summary (paste in "short description")
Freshly-funded US companies with phone + amount raised + founder/CEO; Form 4 insider buy/sell signals; company financials and filing search — clean JSON from official SEC EDGAR. No API key, always current.

## 3. Long description (paste)
Find companies that **just raised money** — the hottest B2B sales trigger — with the contact data to act on it. This actor turns the messy SEC EDGAR Form D feed into clean, ready-to-use, deduplicated leads and signals.

**Funding leads (B2B sales / agencies / lead-gen):**
- Newest Form D filings: companies that *just raised capital*
- Amount raised, sector (Technology / Health Care / Fintech…), entity type, state/city
- **Direct phone number, full address, and named founders / executives (CEO, CFO…)**
- Investment funds and real-estate SPVs automatically removed — only operating companies
- Optional sector filter (e.g. only Technology) and time window

**Insider trades (investors / fintech apps / RAG):**
- Form 4 open-market purchases and sales by directors & officers
- Only real open-market buys/sells count (gifts, awards, option exercises are marked neutral)
- Per-company net signal (bullish insider buying / bearish insider selling) with USD totals

**Company intel & filing search:**
- Snapshot: latest revenue/net income/assets (clearly labeled annual vs quarterly), recent filings
- Full-text search across 10-K/10-Q/8-K (e.g. "cybersecurity", "bankruptcy") with company + ticker

Official SEC source, no third-party API key, stable JSON/XML (not fragile HTML), free dataset. Output is structured for agents and CRMs. Built for sales teams, investors, and AI agents.

## 4. Categories / tags
Categories: **Lead generation**, **AI**
Tags/SEO: `funding leads`, `Form D`, `SEC EDGAR`, `insider trading`, `B2B leads`, `newly funded startups`, `company data`, `investment signals`, `10-K`, `sales prospecting`

## 5. Pricing (Pay Per Event) — set in Monetization step
The actor already writes **one dataset item per funding lead**, and Apify's synthetic
event `apify-default-dataset-item` charges automatically per item — no extra code.

| Event | Price | Notes |
|---|---|---|
| `apify-default-dataset-item` (per qualified lead) | **$0.01** to start ($10 / 1,000 leads) | Competitive; richly enriched (phone+amount+execs) vs raw scrapers at $1.5/1k |
| `apify-actor-start` | keep default $0.00005 | standard |

- Keep the pricing model **Pay per event** (do NOT enable "+ usage" for now, so you qualify for agentic payments).
- Insider/snapshot/search runs produce 1 dataset item each → effectively free teaser; they drive reviews and usage.
- Raise price later as reviews accumulate; offer a small free-trial/tier so the first run is free.

## 6. Why it will rank (the non-paid "promotion")
- Niche has demand (lead-gen + investing) but no dominant EDGAR actor (largest ~89 users vs 589K for Maps).
- Reliability: official JSON/XML APIs → works consistently → high success-rate metric → Store ranks it.
- Fresh data daily (Form D/Form 4 file every day) → recurring runs → compounding usage.
