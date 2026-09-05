# Publish on Apify Store (the monetization/distribution step) — ~10 min, free, no card

The actor is **built, tested, and already running live** as an HTTP API:
- Live demo: https://edgar-signals.onrender.com (cold start ~10s on free tier)
- GitHub: https://github.com/ghy037691-sketch/edgar-signals

The Apify Store is where 90k+ buyers search and where pay-per-result billing + payouts to India (PayPal/bank, min $20) happen. Publishing needs **your own free Apify account** (identity + payout must be yours). Two ways:

## Option A — connect GitHub (easiest, no CLI)
1. Sign up free at https://console.apify.com/sign-up (email; no card).
2. Go to **Actors → Create new → Deploy from Git / connect GitHub**.
3. Connect repo `ghy037691-sketch/edgar-signals`, branch `main`.
   - Build uses the root `Dockerfile` (runs the actor `main.py`); the `.actor/` folder already defines the name, description, and input form.
4. Click **Build → Start**; test with input `{"action":"funding_leads","days_back":30,"limit":10}`.
5. **Publish to Store** (top right) → fill SEO listing:
   - Title: "SEC EDGAR Signals — Funding Leads, Insider Trades, Filing Intel"
   - Pricing: **pay-per-event / pay-per-result** (charge ~$0.005 per funding lead; matches the market: IndiaMART leads are $5/1k). Free tier for discovery.
6. Set **Billing → payout to PayPal** (works for India; minimum $20).

## Option B — Apify CLI
```bash
npx apify-cli login        # paste your free-account API token
npx apify-cli push         # builds + uploads from this folder
# then Publish to Store in the console as in steps 5–6
```

## Notes
- `server.py` / `Dockerfile.web` = the standalone HTTP API (already deployed on Render).
- `main.py` / `Dockerfile` + `.actor/` = the Apify actor entry point (reads Apify input, writes to dataset).
- Same `src/edgar.py` logic powers both. No API keys, no paid services, standard-library only.
- After publish, don't rotate/delete: keep output reliable (EDGAR rarely breaks), respond to reviews, add the 1–2 niche filters buyers ask for. That maintenance + ranking is the real (non-viral) "promotion."
