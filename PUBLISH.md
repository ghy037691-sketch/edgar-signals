# Release and publication runbook

This repository powers two deployments:

- **Apify Actor:** `educable_santoor/edgar-signals` (`rDPJAe1kVKIOJyt6z`)
- **Public demo / docs:** https://edgar-signals.onrender.com

## Automated technical release

1. Run the local contract suite:

   ```bash
   python -m compileall -q main.py server.py src tests
   python -m unittest discover -s tests -v
   npx apify-cli validate-schema
   ```

2. Commit and push `main`. Two private deployment hooks now run automatically:
   - Render rebuilds the public site/API;
   - GitHub webhook `676554687` asks Apify to build Actor version `1.0` directly from this repository.
3. Ensure the new Apify build receives the `latest` tag and succeeds. Manual fallback (keep the Actor's source type as `GIT_REPO`):

   ```bash
   curl -X POST \
     -H "Authorization: Bearer $APIFY_TOKEN" \
     "https://api.apify.com/v2/actors/rDPJAe1kVKIOJyt6z/builds?version=1.0&tag=latest&waitForFinish=300"
   ```

4. Run these cloud smoke tests:
   - funding leads: 10 rows, exact limit, phone/executive/amount fields;
   - snapshot: AAPL annual revenue and latest-period labels;
   - insider: neutral handling for non-market transactions;
   - filing search: clean name/ticker/accession and exact `-index.html` link;
   - invalid ticker: failed run, `OUTPUT` error, zero dataset rows.
5. Confirm default memory is 256 MB and permission level is Limited.

## Required publication assets already in this repository

| Asset | Path |
|---|---|
| Store README | `README.md` |
| Input UI and sample values | `.actor/input_schema.json` |
| Output links | `.actor/output_schema.json` |
| Curated dataset tables and field contract | `.actor/dataset_schema.json` |
| Release history | `CHANGELOG.md` |
| 1024×1024 Store logo | `assets/edgar-signals-logo.png` |
| SEO, categories, PPE values, owner checklist | `STORE_LISTING.md` |
| Public OpenAPI contract | `openapi.json` |
| Interactive product page | `web/index.html` |

## Owner-only publication steps

Apify intentionally keeps identity, legal consent, and payout setup outside deployment APIs. The account owner must:

1. publish the developer profile under the desired person/business name;
2. upload `assets/edgar-signals-logo.png` under **Publication → Display information**;
3. complete account/email verification and KYC;
4. add payout and tax details;
5. accept Store terms;
6. configure Pay per event using the values in `STORE_LISTING.md`;
7. run Apify's Store publication test and click **Publish on Store**.

Never send identity documents, one-time passwords, tax IDs, or payout credentials to an agent.

## Post-release monitoring

- `/health` must return HTTP 200 and version `1.0.0`.
- The default Store test must finish with a non-empty dataset in under five minutes.
- Review failed runs weekly. SEC 429/5xx responses should be retried automatically; schema changes should receive a parser fixture and regression test before release.
- Keep the public demo capped and rate-limited; direct larger workloads to Apify.
- Rotate every deployment token exposed during setup. After rotating the Apify token, update the secret target URL of GitHub webhook `676554687`; otherwise automatic Actor builds will stop.
