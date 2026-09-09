# SEC EDGAR Funding Leads & Insider Signals

<p align="center">
  <img src="https://raw.githubusercontent.com/ghy037691-sketch/edgar-signals/main/assets/edgar-signals-logo.svg" width="150" alt="SEC EDGAR Signals logo" />
</p>

**Turn official SEC filings into sales-ready funding leads and auditable investor intelligence.** Find private companies that recently reported raising capital, classify real Form 4 open-market insider buys and sells, pull public-company fundamentals, or search filings by keyword — all with one simple Actor and no external API key.

> **Fast first run:** leave the default `funding_leads` input unchanged and click **Start**. You will receive up to 10 recent operating-company leads in a clean dataset table.

## What can SEC EDGAR Signals do?

| Workflow | What you receive | Useful for |
|---|---|---|
| `funding_leads` | Newly filed Form D issuers with amount sold, offering target, phone, address, industry, executives, security type, exemptions, and source links | B2B sales, recruiting, banking, legal, insurance, deal sourcing |
| `insider_transactions` | Form 4 transactions plus an open-market buy/sell summary; gifts, awards, exercises, and tax withholding remain neutral | Investment research, alerts, fintech workflows, RAG |
| `snapshot` | Company identity, SIC, addresses, latest and annual financial facts, and direct links to recent 10-K/10-Q/8-K filings | Company enrichment, research, due diligence |
| `filing_search` | Full-text SEC search by keyword and form type with clean company, ticker, filing date, accession, and source link | Compliance, risk monitoring, competitive intelligence |

### Why the funding-lead output is actionable

A Form D reports an exempt securities offering. The Actor does more than list filing headers: it opens each filing's official XML, normalizes it, removes duplicate issuers, and can exclude pooled funds and property SPVs. Every qualified row can include:

- legal company name, CIK, filing and first-sale dates;
- **actual amount sold** (`amount_raised_usd`) and target / remaining amount;
- industry, entity type, jurisdiction, incorporation year, security types, and exemptions;
- issuer phone, street address, city, state, ZIP, and a convenient location field;
- **all disclosed related persons**, plus a flattened primary contact and title;
- investor count, minimum investment, filing lag, and direct SEC source links.

Nothing is guessed. If a filer omits a value, the field is `null`. Form D does not normally disclose email addresses or websites, so this Actor does not invent them.

## Quick start

1. Select a workflow under **What do you want to find?**
2. Keep the defaults, or narrow by date, state, industry, amount, and contact availability.
3. Click **Start**.
4. Open **Output** to inspect the curated table, or export JSON, CSV, Excel, XML, or RSS.
5. Optional: save the input as an Apify Task and schedule it daily.

### Example: recently funded technology and health-care companies

```json
{
  "action": "funding_leads",
  "days_back": 14,
  "limit": 50,
  "industries": ["Other Technology", "Health Care"],
  "states": ["CA", "NY", "TX"],
  "min_amount_raised_usd": 1000000,
  "only_with_phone": true,
  "only_with_executives": true,
  "exclude_funds": true,
  "exclude_real_estate": true,
  "include_amendments": false
}
```

### Example funding-lead row

```json
{
  "record_type": "funding_lead",
  "company": "Example Robotics, Inc.",
  "cik": 2100000,
  "form_d_filed": "2026-09-08",
  "date_of_first_sale": "2026-09-02",
  "freshness_days": 1,
  "amount_raised_usd": 5200000,
  "total_offering_usd": 8000000,
  "industry": "Other Technology",
  "primary_contact_name": "Jordan Lee",
  "primary_contact_title": "Chief Executive Officer",
  "phone": "415-555-0137",
  "location": "SAN FRANCISCO, CA",
  "securities_offered": ["Equity"],
  "filing_index": "https://www.sec.gov/Archives/edgar/data/...-index.html",
  "source_url": "https://www.sec.gov/Archives/edgar/data/.../primary_doc.xml"
}
```

The example above illustrates the stable schema. Production rows contain public data from real SEC filings.

## Input reference

| Field | Used by | Default | Description |
|---|---|---:|---|
| `action` | all | `funding_leads` | Select one of the four workflows |
| `days_back` | leads / search | `30` | Calendar-day lookback, 1–3,650 |
| `limit` | all | `50` | Hard maximum; the Actor never emits more than this |
| `industries` | leads | all | SEC industry names or partial matches |
| `states` | leads | all | Two-letter codes or full state names |
| `min_amount_raised_usd` | leads | `0` | Minimum `totalAmountSold`; 0 disables |
| `max_amount_raised_usd` | leads | `0` | Maximum `totalAmountSold`; 0 disables |
| `only_with_phone` | leads | `false` | Require a disclosed issuer phone |
| `only_with_executives` | leads | `false` | Require a related person or signatory |
| `exclude_funds` | leads | `true` | Remove pooled investment funds |
| `exclude_real_estate` | leads | `true` | Remove property holding vehicles / SPVs |
| `include_amendments` | leads | `false` | Also search D/A; off prevents old raises looking new |
| `symbol` | snapshot / insider | — | Ticker such as `NVDA` or a numeric CIK |
| `keyword` | search / optional leads | — | Filing phrase, e.g. `material weakness` |
| `forms` | search | 10-K, 10-Q, 8-K | Any SEC form types, e.g. S-1 or DEF 14A |

## More workflow examples

### Insider activity

```json
{ "action": "insider_transactions", "symbol": "MSFT", "limit": 15 }
```

Only transaction codes `P` (open-market purchase) and `S` (open-market sale) drive the net signal. Awards (`A`), gifts (`G`), option exercises (`M`), and tax-related dispositions (`F`) stay neutral and are still returned for auditability.

### Company snapshot

```json
{ "action": "snapshot", "symbol": "AAPL" }
```

Financial facts explicitly label the latest observation as annual, quarterly, or year-to-date. When available, `annual_value` and `annual_fy_end` prevent a 10-Q value from being mistaken for full-year revenue.

### Filing search

```json
{
  "action": "filing_search",
  "keyword": "cybersecurity incident",
  "forms": ["8-K", "10-K"],
  "days_back": 180,
  "limit": 25
}
```

## Output, integrations, and automation

- **Dataset:** one row per qualified funding lead. Snapshot, insider, and filing-search workflows write one structured intelligence row per run.
- **OUTPUT record:** complete result with filters, match counts, provenance, and nested records.
- **Curated views:** Funding leads, Insider signal, Company snapshot, and Filing search.
- **Exports:** JSON, JSONL, CSV, Excel, XML, and RSS through Apify Dataset.
- **Automation:** Apify Schedules, Tasks, webhooks, Zapier, Make, Google Sheets, and the Apify API.
- **AI agents:** explicit input, output, and dataset schemas make the Actor discoverable and chainable through Apify's MCP tooling.

### Run through the API

```bash
curl -X POST \
  "https://api.apify.com/v2/acts/educable_santoor~edgar-signals/run-sync-get-dataset-items?token=$APIFY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"funding_leads","days_back":7,"limit":10}'
```

A free, unauthenticated demonstration API and interactive documentation are available at:

**https://edgar-signals.onrender.com**

The demo may cold-start because it runs on free hosting. Production automation should use the Apify Actor.

## How much does it cost?

Launch pricing uses **pay per event**:

- `apify-default-dataset-item`: **$0.005 per delivered dataset row**;
- `apify-actor-start`: the standard **$0.00005** start event.

That means 100 qualified funding leads cost about **$0.50**, and 1,000 cost **$5**. Filtering happens before rows are written, so rejected funds, SPVs, duplicates, and missing-contact records are not charged as results. An error or a funding run with zero matches writes **zero dataset items**. Snapshot, insider, and filing-search runs write one item each.

Always use the **maximum cost per run** control in Apify if you need a hard spending ceiling. Current pricing displayed in the Store is authoritative if it differs from this README.

## Data quality and important limitations

- **Source:** official `data.sec.gov`, `efts.sec.gov`, and `www.sec.gov` JSON/XML endpoints.
- The client identifies itself, throttles request starts below the SEC's published fair-access ceiling, retries transient 429/5xx responses, and does not use fragile browser automation.
- Form D is generally due within 15 calendar days after the first sale. A fresh filing is a strong funding event signal, but not necessarily a same-day announcement.
- Values reflect what the filer submitted. The Actor does not independently audit the company or offering.
- `amount_raised_usd` means Form D `totalAmountSold`, not valuation, profit, or cash currently available.
- Filing search returns filing metadata and links; it does not provide legal interpretation.
- Insider summaries are mechanical classifications, not predictions or investment recommendations.

## Legal and responsible use

This independent Actor is **not affiliated with or endorsed by the U.S. Securities and Exchange Commission**. It processes public regulatory filings. Follow applicable privacy, telemarketing, securities, and anti-spam laws when using contact information. Do not treat any output as legal, financial, or investment advice.

## Support

If an SEC schema change or edge case produces an incorrect field, open an issue with a non-sensitive accession number:

**https://github.com/ghy037691-sketch/edgar-signals/issues**

For fastest diagnosis, include the workflow, input (without API tokens), run ID, expected behavior, and actual behavior.
