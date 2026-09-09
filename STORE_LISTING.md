# Apify Store publication sheet — SEC EDGAR Signals v1.0

> Actor console: https://console.apify.com/actors/rDPJAe1kVKIOJyt6z
>
> Final technical name: `educable_santoor/edgar-signals`

Everything below is already represented in the repository's Actor definition, README, input schema, output schema, dataset views, sample input, and logo. Use this sheet only for fields Apify keeps in the Publishing UI.

## 1. Display information

### Actor title — 41 characters

**SEC EDGAR Funding Leads & Insider Signals**

### Description — 266 characters

**Turn official SEC filings into sales-ready funding leads and investor intelligence. Get newly funded companies with phone, amount raised, location and executives; accurate Form 4 buy/sell signals; company financials; and full-text filing search. No external API key.**

### Logo

Upload: **`assets/edgar-signals-logo.png`** (1024×1024 PNG)

The logo is original and intentionally does not imitate the SEC seal or claim government affiliation.

### Categories

1. **Lead generation** (`LEAD_GENERATION`)
2. **Business** (`BUSINESS`)
3. **AI** (`AI`) — the explicit schemas make it usable as an AI-agent/MCP tool; the data classification itself is deterministic, not LLM-generated.

### SEO title — 46 characters

**SEC Form D Funding Leads & Insider Signals API**

### SEO description — 149 characters

**Find newly funded US companies with phone, amount raised, and executives, plus Form 4 insider signals and filing search from official SEC EDGAR data.**

### Search terms to cover naturally

`SEC Form D scraper`, `funding leads`, `newly funded companies`, `startup leads`, `SEC EDGAR API`, `Form 4 insider trading`, `insider signals`, `company financials`, `10-K search`, `B2B lead generation`

These already appear naturally in `README.md`; do not keyword-stuff the title.

## 2. Sample run

Use this as the Actor's example/default run input:

```json
{
  "action": "funding_leads",
  "days_back": 7,
  "limit": 10,
  "industries": [],
  "states": [],
  "min_amount_raised_usd": 0,
  "max_amount_raised_usd": 0,
  "only_with_phone": false,
  "only_with_executives": false,
  "exclude_funds": true,
  "exclude_real_estate": true,
  "include_amendments": false
}
```

Why this sample: Apify's daily Store health test requires a successful run with a non-empty dataset in under five minutes. A seven-day window and ten-row limit are fast while still robust to weekends.

## 3. Output configuration

Already shipped in code:

- `.actor/output_schema.json` links the default Dataset and complete `OUTPUT` record.
- `.actor/dataset_schema.json` supplies four curated views:
  1. Funding leads
  2. Insider signal
  3. Company snapshot
  4. Filing search
- Errors are saved to `OUTPUT` and make the run fail **without writing a paid dataset row**.
- A zero-match funding run writes zero dataset rows.
- Funding runs write exactly one row per qualified lead and never exceed `limit`.

## 4. Permission level

Choose **Limited permissions**. The Actor needs only its own run storage and outbound HTTPS to public SEC endpoints. It does not need access to the user's account, proxy credentials, other datasets, or secret stores.

## 5. Monetization

### Recommended launch model

Select **Pay per event** — **do not enable “+ usage.”** This keeps customer costs predictable and maintains agentic-payment eligibility once account verification is complete.

| Event | Launch price | Primary? | Meaning |
|---|---:|---:|---|
| `apify-default-dataset-item` | **$0.005** | Yes | One qualified funding lead, or one structured snapshot/insider/search response |
| `apify-actor-start` | **$0.00005** | No | Standard one-time run-start event |

Customer examples:

- 10 funding leads ≈ **$0.05** plus the tiny start event
- 100 leads ≈ **$0.50**
- 1,000 leads ≈ **$5.00**
- snapshot / insider / filing-search utility run ≈ **$0.005** because it writes one item

### Why $0.005 instead of the earlier $0.01 draft

A live Store audit on 2026-09-09 found direct Form D competitors around **$2.00–$6.59 per 1,000 rows**. This Actor delivers deeper qualification and four workflows, but a $5 launch price removes price friction while still leaving a large margin at the optimized 256 MB default memory. Raise toward $0.0075–$0.01 after reviews and repeat users appear.

### PPE event descriptions

**Primary event title:** `Qualified SEC intelligence record`

**Description:** `Charged only when a qualified lead or usable intelligence result is written to the default dataset. Rejected funds/SPVs, errors, and zero matches do not create this event.`

**Start event title:** `Actor start`

**Description:** `Small one-time charge when a run starts.`

Set a reasonable minimum maximum-charge value only if Apify requires it; do not force customers to authorize a large spend for a ten-row test.

## 6. Identity and payout steps — owner-only

These cannot safely or legally be completed by an automated agent because they require your identity, consent, and payout destination:

1. **Settings → Profile:** make the developer profile public and replace the current display name with the person/business name you want buyers to see.
2. Complete **email/account verification** if Apify prompts for it.
3. Complete **KYC / identity verification** in Billing or Payouts.
4. Add your own supported **PayPal or bank payout method** and tax/payout details.
5. Accept Apify Store developer/monetization terms.
6. Return to the Actor's **Publishing** tab, confirm every section is green, choose the PPE prices above, and click **Publish on Store**.

Do not share identity documents, OTPs, passwords, or PayPal credentials in chat.

## 7. Final Store QA immediately after publishing

- Open `https://apify.com/educable_santoor/edgar-signals` in a signed-out/private window.
- Confirm logo, title, description, README, Input, Output, Pricing, API, and Changelog tabs load.
- Run the default ten-lead input with a maximum-cost ceiling.
- Confirm exactly ten or fewer dataset rows, curated columns, working SEC links, and no unexpected usage add-on.
- Export CSV once and confirm `company`, `amount_raised_usd`, `phone`, `primary_contact_name`, and `filing_index` columns.
- Confirm the run's `OUTPUT` record includes `_meta.status = succeeded` and `_pushed_items`.

## 8. Security after publication

Rotate all credentials that appeared in chat:

- GitHub personal access token
- Render API token
- Apify API token
- any other previously shared service tokens

No credential is committed to this repository. Rotating them after publication will not remove the deployed code or Store listing.
