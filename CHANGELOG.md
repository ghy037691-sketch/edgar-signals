# Changelog

## 1.0 — Fully furnished release (2026-09-09)

### Added
- Required Actor output schema and four curated dataset views for Apify Console and AI agents.
- Complete `OUTPUT` key-value-store response alongside dataset records.
- Funding filters for US state, minimum/maximum amount raised, phone availability, executive availability, and optional D/A amendments.
- CRM-friendly fields: `amount_raised_usd`, primary contact name/title, location, freshness, and filing lag.
- Deeper Form D extraction: every related person, security types, federal exemptions, investor count, first-sale date, incorporation year, commissions, and finder fees.
- Richer company snapshots with correct SIC code/description, addresses, filer category, EIN, former names, and precise filing links.
- Interactive web documentation, OpenAPI specification, product logo, tests, and continuous integration.

### Fixed
- Enforce the requested result limit exactly; a limit of 10 can no longer return a full 12-row enrichment chunk.
- Never create a billable dataset row for an error or a zero-match funding run.
- Parse `relatedPersonInfo` correctly instead of returning only the Form D signatory.
- Keep non-market Form 4 acquisitions/dispositions neutral rather than labeling them as buys/sells.
- Preserve the unit and taxonomy belonging to the selected SEC company fact.
- Correct `sic`, which previously contained the SIC description instead of the numeric code.
- Use exact SEC filing index URLs and include accession numbers in filing-search results.

### Performance and cost
- True concurrent enrichment with the network wait outside the throttle lock.
- Order-preserving early stop after enough qualified leads are found.
- Default Actor memory reduced from 4,096 MB to 256 MB to minimize platform cost while remaining I/O-concurrent.

## 0.9 — Performance hardening
- Released network calls from the global rate-limit lock.
- Added order-preserving chunked enrichment and early stopping.

## 0.8 — Concurrent Form D enrichment
- Added an eight-worker enrichment pool and thread-safe SEC request throttling.

## 0.7 — Data correctness
- Added SEC full-text pagination beyond 100 hits.
- Cleaned company/ticker fields, separated annual and quarterly financial facts, and normalized US phone numbers.

## 0.6 — Insider and lead filtering correctness
- Limited bullish/bearish insider signals to open-market P/S transactions.
- Marked gifts, grants, exercises, and withholding transactions neutral.
- Strengthened pooled-fund and real-estate SPV filtering.
