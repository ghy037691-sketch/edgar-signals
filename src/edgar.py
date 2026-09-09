"""SEC EDGAR client — free, no API key, stable official JSON/XML APIs.
Respects SEC fair-access: custom User-Agent, throttled.
"""
import json, os, time, urllib.request, urllib.parse, re, threading
from datetime import datetime, timezone, timedelta

# SEC asks automated clients to identify themselves. Operators can override this
# without changing code; the default points to the public support repository.
UA = os.environ.get(
    "SEC_EDGAR_USER_AGENT",
    "edgar-signals-actor/1.0 (contact: contact@edgar-signals.onrender.com)",
)
BASE = "https://data.sec.gov"
_last = [0.0]
_lock = threading.Lock()

def _throttle():
    """Rate-limit request STARTS to ~8/s. Lock held only for the short check/update,
    never across the network call — otherwise worker threads can't fetch concurrently."""
    with _lock:
        gap = time.time() - _last[0]
        if gap < 0.12:
            time.sleep(0.12 - gap)
        _last[0] = time.time()


def _get(url, raw=False):
    import gzip
    # Request gzip only: urllib does not transparently decode content encodings and
    # advertising deflate without decoding it can corrupt otherwise valid JSON.
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Encoding": "gzip",
        "Accept": "application/json, application/xml, text/html;q=0.8, */*;q=0.5",
        "Host": url.split('/')[2],
    })
    last_err = None
    for attempt in range(3):
        _throttle()  # space out request starts; release lock before awaiting the network
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
            return data if raw else json.loads(data)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(0.6 * (attempt + 1)); continue
            raise
    raise last_err

def _cik(c):
    c = str(c).strip()
    if c.isdigit():
        return int(c)
    return None

_TICKERS = None
def load_tickers():
    global _TICKERS
    if _TICKERS is None:
        _TICKERS = _get("https://www.sec.gov/files/company_tickers.json")
    return _TICKERS

def resolve(symbol_or_cik):
    """Return (cik:int, ticker:str, name:str) or None."""
    n = _cik(symbol_or_cik)
    if n:
        try:
            sub = _get(f"{BASE}/submissions/CIK{n:010d}.json")
            return n, (sub.get("tickers") or [""])[0], sub.get("name","")
        except Exception:
            return None
    t = str(symbol_or_cik).upper().strip()
    for v in load_tickers().values():
        if v.get("ticker") == t:
            return v["cik_str"], v["ticker"], v["title"]
    return None

def submissions(cik):
    return _get(f"{BASE}/submissions/CIK{int(cik):010d}.json")

_FIN_TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
        "Revenue", "RevenueFromContractsWithCustomers",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "total_assets": ["Assets"],
    # Most issuers report this in the DEI taxonomy, not us-gaap.
    "employees": ["EntityNumberOfEmployees", "NumberOfEmployees"],
}


def _latest_fact(companyfacts, tag_candidates):
    """Select the latest reported fact and separately expose the latest full year.

    SEC companyfacts can contain the same concept in us-gaap, dei, or ifrs-full and
    can expose more than one unit. Unit/taxonomy metadata is attached to each
    candidate so it always describes the value actually selected.
    """
    cands = []
    for taxonomy, concepts in companyfacts.get("facts", {}).items():
        for tag in tag_candidates:
            fact = concepts.get(tag)
            if not fact:
                continue
            for unit, arr in fact.get("units", {}).items():
                for x in arr:
                    if x.get("form") in ("10-K", "10-Q", "20-F", "40-F") and "val" in x:
                        rec = dict(x)
                        rec["_unit"] = unit
                        rec["_taxonomy"] = taxonomy
                        rec["_concept"] = tag
                        cands.append(rec)
    if not cands:
        return None

    def _days(x):
        s, e = x.get("start"), x.get("end")
        if s and e:
            try:
                return (datetime.fromisoformat(e).date() - datetime.fromisoformat(s).date()).days
            except Exception:
                return None
        return None

    def is_annual(x):
        if x.get("form") in ("10-K", "20-F", "40-F"):
            d = _days(x)
            # Instant facts (assets / headcount) have no start date but a 10-K
            # context is still a fiscal-year-end observation.
            return True if d is None else 300 <= d <= 400
        return False

    annual = [x for x in cands if is_annual(x)]
    cands.sort(key=lambda x: (x.get("end", ""), x.get("filed", ""), x.get("form", "")))
    latest = cands[-1]
    out = {
        "value": latest["val"],
        "as_of": latest.get("end"),
        "filed": latest.get("filed"),
        "form": latest.get("form"),
        "unit": latest.get("_unit"),
        "taxonomy": latest.get("_taxonomy"),
        "concept": latest.get("_concept"),
        "period": (
            "annual (fiscal year)" if is_annual(latest)
            else "quarterly / YTD (10-Q)" if latest.get("form") == "10-Q"
            else latest.get("form")
        ),
    }
    if annual:
        annual.sort(key=lambda x: (x.get("end", ""), x.get("filed", ""), x.get("form", "")))
        a = annual[-1]
        out.update({
            "annual_value": a["val"],
            "annual_fy_end": a.get("end"),
            "annual_filed": a.get("filed"),
            "annual_unit": a.get("_unit"),
        })
    return out

def _clean_address(a):
    """Return a compact, stable address object from submissions/Form D data."""
    if not a:
        return None
    out = {
        "street1": a.get("street1"), "street2": a.get("street2"),
        "city": a.get("city"), "state_code": a.get("stateOrCountry"),
        "state": a.get("stateOrCountryDescription") or a.get("stateOrCountry"),
        "postal_code": a.get("zipCode"), "country": a.get("country"),
        "country_code": a.get("countryCode"),
    }
    return {k: v for k, v in out.items() if v not in (None, "")}


def company_snapshot(symbol_or_cik):
    r = resolve(symbol_or_cik)
    if not r:
        return {"error": f"Could not resolve '{symbol_or_cik}' to a public company"}
    cik, ticker, name = r
    sub = submissions(cik)
    addresses = sub.get("addresses", {})
    snap = {
        "record_type": "company_snapshot",
        "cik": cik,
        "ticker": ticker,
        "name": sub.get("name", name),
        "entity_type": sub.get("entityType"),
        "filer_category": sub.get("category"),
        "sic": sub.get("sic"),
        "sic_description": sub.get("sicDescription"),
        "ein": sub.get("ein") or None,
        "exchanges": sub.get("exchanges") or [],
        "state": addresses.get("business", {}).get("stateOrCountry"),
        "state_of_incorporation": sub.get("stateOfIncorporation") or None,
        "fiscal_year_end": sub.get("fiscalYearEnd"),
        "phone": _fmt_phone(sub.get("phone")),
        "website": sub.get("website") or None,
        "investor_website": sub.get("investorWebsite") or None,
        "business_address": _clean_address(addresses.get("business")),
        "mailing_address": _clean_address(addresses.get("mailing")),
        "former_names": sub.get("formerNames") or [],
        "source_url": f"{BASE}/submissions/CIK{cik:010d}.json",
    }
    try:
        facts = _get(f"{BASE}/api/xbrl/companyfacts/CIK{cik:010d}.json")
        for k, tags in _FIN_TAGS.items():
            v = _latest_fact(facts, tags)
            if v:
                snap[k] = v
    except Exception as e:
        snap["financials_note"] = f"companyfacts unavailable: {e}"

    # Direct links for the newest decision-useful filings.
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    docs = recent.get("primaryDocument", [])
    accessions = recent.get("accessionNumber", [])
    want = ("10-K", "10-Q", "8-K")
    flist = []
    for i, form in enumerate(forms):
        if form not in want or i >= len(accessions):
            continue
        accession = accessions[i]
        acc_nodash = accession.replace("-", "")
        primary = docs[i] if i < len(docs) else ""
        flist.append({
            "form": form,
            "filed": dates[i] if i < len(dates) else None,
            "accession": accession,
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{primary}",
            "filing_index": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{accession}-index.html",
        })
    snap["recent_filings"] = flist[:8]
    return snap

def _ftsearch(q=None, forms=None, start=None, end=None, limit=50):
    """Full-text search. SEC returns max 100 hits/page; paginate using start=."""
    out = []
    total = None
    offset = 0
    page = 100
    while len(out) < limit:
        params = {}
        if q: params["q"] = q
        if forms: params["forms"] = ",".join(forms) if isinstance(forms, (list, tuple)) else forms
        if start or end:
            params["dateRange"] = "custom"
            if start: params["startdt"] = start
            if end: params["enddt"] = end
        params["start"] = offset
        d = _get("https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(params))
        hits = d.get("hits", {}).get("hits", [])
        if total is None:
            total = d.get("hits", {}).get("total", {}).get("value")
        if not hits:
            break
        for h in hits:
            src = h.get("_source", {})
            disp = (src.get("display_names") or [""])[0]
            # display_name like: "Loan Artificial Intelligence Corp.  (LAAI)  (CIK 000...)".
            # SEC pads the company name from ticker/CIK with double spaces; ticker/CIK
            # are also in dedicated fields. Take text before the double-space pad, then
            # strip any residual trailing parenthetical.
            company = re.split(r"\s{2,}", disp)[0]
            company = re.sub(r"\s*\([A-Z0-9.,\- ]{1,16}$", "", company).strip()
            ticker_m = re.search(r"\(([A-Z0-9.\-]{1,10})\)\s*\(CIK", disp)
            cik = None
            cik_list = src.get("ciks") or []
            if cik_list:
                try: cik = int(cik_list[0])
                except: pass
            adsh = src.get("adsh") or ""
            form_val = src.get("form")
            if isinstance(form_val, list):
                form_val = ",".join(form_val)
            out.append({
                "company": company or disp,
                "ticker": ticker_m.group(1) if ticker_m else None,
                "cik": cik,
                "form": form_val or (forms[0] if forms and len(forms) == 1 else ""),
                "filed": src.get("file_date") or src.get("fileDate"),
                "accession": adsh,
                "filing_index": (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{adsh}-index.html"
                    if cik and adsh else ""
                ),
            })
            if len(out) >= limit:
                break
        if len(hits) < page:
            break
        offset += page
    return out, total

def funding_leads(days_back=30, limit=50, keyword=None, exclude_funds=True,
                  exclude_real_estate=True, industries=None, enrich=True,
                  scan_cap=None, states=None, min_amount_raised_usd=0,
                  max_amount_raised_usd=0, only_with_phone=False,
                  only_with_executives=False, include_amendments=False):
    """Return fresh, enriched Form D operating-company leads.

    Filtering happens after each filing is parsed because amount, state, phone, and
    issuer type live in the primary XML document rather than the search index.
    Results remain newest-first and never exceed ``limit``.
    """
    days_back = max(1, min(int(days_back), 3650))
    limit = max(1, min(int(limit), 500))
    # Pull enough candidates for fund/SPV and optional field filters, without doing
    # an unbounded search. Small runs need only one FTS page; larger runs paginate.
    if scan_cap is None:
        scan_cap = min(2000, max(100, limit * 5))
    scan_cap = max(limit, min(int(scan_cap), 2000))

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days_back)
    forms = ["D", "D/A"] if include_amendments else ["D"]
    hits, total = _ftsearch(
        q=keyword, forms=forms, start=start.isoformat(), end=end.isoformat(), limit=scan_cap,
    )

    # Enrich in order-preserving chunks and stop when the requested number of
    # *qualified* rows has been found. Requests run concurrently, but the output
    # follows the newest-first SEC search order.
    from concurrent.futures import ThreadPoolExecutor

    def _enrich(hit):
        cik, accession = hit.get("cik"), hit.get("accession")
        details = None
        if enrich and cik and accession:
            try:
                details = _parse_formd(cik, accession)
            except Exception:
                details = None
        return hit, details

    leads = []
    seen_ciks = set()
    scanned = 0
    wanted_industries = [str(x).strip().lower() for x in (industries or []) if str(x).strip()]
    wanted_states = {str(x).strip().upper() for x in (states or []) if str(x).strip()}
    try:
        min_amount = max(0.0, float(min_amount_raised_usd or 0))
    except (TypeError, ValueError):
        min_amount = 0.0
    try:
        max_amount = max(0.0, float(max_amount_raised_usd or 0))
    except (TypeError, ValueError):
        max_amount = 0.0

    def _accept(hit, details):
        nonlocal scanned
        scanned += 1
        cik = hit.get("cik")
        if cik and cik in seen_ciks:
            return

        base = {
            "record_type": "funding_lead",
            "company": hit.get("company", "").split("(")[0].strip(),
            "cik": cik,
            "form_d_filed": hit.get("filed"),
            "accession": hit.get("accession"),
            "filing_index": hit.get("filing_index"),
        }
        if details:
            base.update(details)

        name = base.get("company") or hit.get("company", "")
        industry = base.get("industry") or ""
        industry_lower = industry.lower()
        is_fund = bool(base.get("is_pooled_fund")) or _looks_like_fund(name)
        real_estate_sectors = (
            "real estate", "residential", "commercial", "lodging", "conventions", "investing",
        )
        is_real_estate = _looks_like_real_estate(name) or any(
            value in industry_lower for value in real_estate_sectors
        )
        if exclude_funds and is_fund:
            return
        if exclude_real_estate and is_real_estate:
            return
        if wanted_industries and not any(value in industry_lower for value in wanted_industries):
            return

        state_values = {
            str(base.get("state_code") or "").upper(),
            str(base.get("state") or "").upper(),
        }
        if wanted_states and not (wanted_states & state_values):
            return

        raised = base.get("total_amount_sold_usd")
        if min_amount and (raised is None or raised < min_amount):
            return
        if max_amount and (raised is None or raised > max_amount):
            return
        if only_with_phone and not base.get("phone"):
            return
        if only_with_executives and not base.get("executives"):
            return

        base["is_pooled_fund"] = bool(is_fund)
        base["amount_raised_usd"] = raised
        city, state = base.get("city"), base.get("state_code") or base.get("state")
        base["location"] = ", ".join(str(x) for x in (city, state) if x) or None
        executives = base.get("executives") or []
        if executives:
            primary = executives[0]
            base["primary_contact_name"] = primary.get("name")
            base["primary_contact_title"] = primary.get("title") or primary.get("relationship")
        else:
            base["primary_contact_name"] = None
            base["primary_contact_title"] = None

        try:
            filed_date = datetime.fromisoformat(base["form_d_filed"]).date()
            base["freshness_days"] = max(0, (end - filed_date).days)
        except Exception:
            base["freshness_days"] = None
        try:
            first_sale = datetime.fromisoformat(base.get("date_of_first_sale") or "").date()
            filed_date = datetime.fromisoformat(base["form_d_filed"]).date()
            base["filing_lag_days"] = (filed_date - first_sale).days
        except Exception:
            base["filing_lag_days"] = None

        if cik:
            seen_ciks.add(cik)
        leads.append(base)

    chunk_size = 12
    with ThreadPoolExecutor(max_workers=8 if enrich else 1) as executor:
        for offset in range(0, len(hits), chunk_size):
            if len(leads) >= limit or scanned >= scan_cap:
                break
            batch = hits[offset:offset + chunk_size]
            for hit, details in executor.map(_enrich, batch):
                if len(leads) >= limit or scanned >= scan_cap:
                    break
                _accept(hit, details)

    return {
        "record_type": "funding_leads_run",
        "days_back": days_back,
        "matched_form_d_total": total,
        "candidate_scan_cap": scan_cap,
        "scanned": scanned,
        "returned": len(leads),
        "exclude_funds": bool(exclude_funds),
        "exclude_real_estate": bool(exclude_real_estate),
        "include_amendments": bool(include_amendments),
        "industries_filter": industries or [],
        "states_filter": states or [],
        "min_amount_raised_usd": min_amount,
        "max_amount_raised_usd": max_amount or None,
        "only_with_phone": bool(only_with_phone),
        "only_with_executives": bool(only_with_executives),
        "enriched": bool(enrich),
        "leads": leads,
    }


_FUND_HINTS = (" FUND", "FUND ", "FUND-", "FUND,", "FUND LLC", "MASTER", "FEEDER",
               " REIT", "SERIES OF", " A SERIES", "PROPERTIES", "REAL ESTATE",
               "CAPITAL FUND", "HOLDINGS FUND")
_RE_HINTS = ("VILLAS", "HIGHLANDS", "PROPERTIES", "REAL ESTATE", "APARTMENTS", "TOWNHOMES",
             "LLC, A SERIES", "AVENUE", "GRATIOT", "MACOMB", "POINTE", "ESTATES",
             "LAND", "DEVELOPMENT", "CONDOMINIUM", "RESIDENTIAL", "COMMUNITIES")


def _looks_like_fund(name):
    n = " " + name.upper() + " "
    return any(h in n for h in _FUND_HINTS)


def _looks_like_real_estate(name):
    n = " " + name.upper() + " "
    # only treat as real estate when there is a property/placename-like cue AND name
    # does NOT clearly read like an operating company
    op_cues = ("INC.", "INC ", "CORP", "CORPORATION", "TECH", "LABS", "CONSULTING",
               "THERAPEUTICS", "BIOTECH", "SOFTWARE", "SYSTEMS", "HEALTH", "AI")
    if any(c in n for c in op_cues):
        return False
    return any(h in n for h in _RE_HINTS)


def _fmt_phone(raw):
    """Normalize US phone numbers to NPA-NXX-XXXX style; leave others as-is."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return raw.strip()


def _parse_formd(cik, accession):
    """Parse a Form D primary XML document into a CRM-friendly lead record.

    Parsing is namespace-agnostic and scoped to the correct XML sections. This is
    important because Form D repeats tags such as ``value``, ``city``, and
    ``dollarAmount`` in issuer, contact, fee, and signature blocks.
    """
    import xml.etree.ElementTree as ET

    nodash = str(accession).replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{nodash}/primary_doc.xml"
    try:
        root = ET.fromstring(_get(url, raw=True))
    except Exception:
        return None

    def local(element):
        return element.tag.split("}")[-1]

    def find(parent, tag):
        if parent is None:
            return None
        for element in parent.iter():
            if local(element) == tag:
                return element
        return None

    def find_all(parent, tag):
        if parent is None:
            return []
        return [element for element in parent.iter() if local(element) == tag]

    def text(parent, tag, default=""):
        element = find(parent, tag)
        value = (element.text or "").strip() if element is not None else ""
        return value or default

    def number(parent, tag):
        value = text(parent, tag)
        if not value or value.lower() == "indefinite":
            return None
        try:
            return float(value.replace(",", ""))
        except (TypeError, ValueError):
            return None

    def boolean(parent, tag):
        return text(parent, tag).lower() in ("true", "1", "yes")

    def clean_name(value):
        value = re.sub(r"^/s/\s*", "", value or "", flags=re.I)
        return " ".join(value.replace("/", " ").split())

    issuer = find(root, "primaryIssuer")
    issuer = issuer if issuer is not None else root
    issuer_address = find(issuer, "issuerAddress")
    offering = find(root, "offeringData")
    offering = offering if offering is not None else root
    industry_node = find(offering, "industryGroup")
    industry_node = industry_node if industry_node is not None else offering
    filing_type = find(offering, "typeOfFiling")
    filing_type = filing_type if filing_type is not None else offering
    amounts = find(offering, "offeringSalesAmounts")
    amounts = amounts if amounts is not None else offering
    investors = find(offering, "investors")
    investors = investors if investors is not None else offering

    industry = text(industry_node, "industryGroupType")
    fund_type = text(industry_node, "investmentFundType")
    is_fund = industry == "Pooled Investment Fund" or bool(fund_type)

    # Capture every disclosed related person, not only the filing signatory.
    executives = []
    seen_people = set()
    for person in root.iter():
        if local(person) not in ("relatedPersonInfo", "relatedPerson"):
            continue
        first = text(person, "firstName")
        middle = text(person, "middleName")
        last = text(person, "lastName")
        full_name = clean_name(" ".join(x for x in (first, middle, last) if x))
        if not full_name:
            continue
        relationships = []
        for rel in find_all(person, "relationship"):
            value = (rel.text or "").strip()
            if value and value not in relationships:
                relationships.append(value)
        # Support older schema variants as well.
        old_relationship = text(person, "relatedPersonRelationship")
        if old_relationship and old_relationship not in relationships:
            relationships.append(old_relationship)
        clarification = text(person, "relationshipClarification")
        relationship = "; ".join(relationships) or clarification or None
        key = full_name.casefold()
        if key not in seen_people:
            executives.append({
                "name": full_name,
                "relationship": relationship,
                "title": clarification or None,
            })
            seen_people.add(key)

    signature_block = find(offering, "signatureBlock")
    signature_name = clean_name(text(signature_block, "signatureName"))
    signer_name = clean_name(text(signature_block, "nameOfSigner"))
    signature_title = text(signature_block, "signatureTitle") or None
    signatory = signature_name or signer_name
    if signatory:
        existing = next((p for p in executives if p["name"].casefold() == signatory.casefold()), None)
        if existing:
            if signature_title:
                existing["title"] = signature_title
                if not existing.get("relationship"):
                    existing["relationship"] = signature_title
        else:
            executives.append({
                "name": signatory,
                "relationship": signature_title,
                "title": signature_title,
            })

    exemption_node = find(offering, "federalExemptionsExclusions")
    exemptions = []
    for item in find_all(exemption_node, "item"):
        value = (item.text or "").strip()
        if value and value not in exemptions:
            exemptions.append(value)

    security_map = {
        "isEquityType": "Equity",
        "isDebtType": "Debt",
        "isOptionToAcquireType": "Option to acquire",
        "isSecurityToBeAcquiredType": "Security to be acquired",
        "isPooledInvestmentFundType": "Pooled investment fund interest",
        "isTenantInCommonType": "Tenant-in-common interest",
        "isMineralPropertyType": "Mineral property",
        "isOtherType": "Other",
    }
    security_node = find(offering, "typesOfSecuritiesOffered")
    securities = [label for tag, label in security_map.items() if boolean(security_node, tag)]
    other_security = text(security_node, "descriptionOfOtherType")
    if other_security:
        securities.append(other_security)

    year_node = find(issuer, "yearOfInc")
    year_value = text(year_node, "value")
    try:
        year_value = int(year_value)
    except (TypeError, ValueError):
        year_value = None

    first_sale_node = find(filing_type, "dateOfFirstSale")
    first_sale = text(first_sale_node, "value") or None
    total_offering_raw = text(amounts, "totalOfferingAmount")

    commissions_node = find(offering, "salesCommissions")
    finders_node = find(offering, "findersFees")
    proceeds_node = find(offering, "grossProceedsUsed")

    broker_names = []
    compensation_list = find(offering, "salesCompensationList")
    for recipient in find_all(compensation_list, "recipientName"):
        value = clean_name(" ".join((recipient.text or "").split()))
        if value and value not in broker_names:
            broker_names.append(value)

    return {
        "company": text(issuer, "entityName") or None,
        "entity_type": text(issuer, "entityType") or None,
        "jurisdiction": text(issuer, "jurisdictionOfInc") or None,
        "year_of_incorporation": year_value,
        "incorporated_within_five_years": boolean(year_node, "withinFiveYears"),
        "industry": industry or None,
        "is_pooled_fund": is_fund,
        "fund_type": fund_type or None,
        "date_of_first_sale": first_sale,
        "is_amendment": boolean(filing_type, "isAmendment"),
        "offering_more_than_one_year": boolean(offering, "moreThanOneYear"),
        "securities_offered": securities,
        "federal_exemptions": exemptions,
        "total_offering_usd": number(amounts, "totalOfferingAmount"),
        "offering_indefinite": total_offering_raw.lower() == "indefinite",
        "total_amount_sold_usd": number(amounts, "totalAmountSold"),
        "total_remaining_usd": number(amounts, "totalRemaining"),
        "minimum_investment_usd": number(offering, "minimumInvestmentAccepted"),
        "revenue_range": text(offering, "revenueRange") or None,
        "investors_count": number(investors, "totalNumberAlreadyInvested"),
        "has_non_accredited_investors": boolean(investors, "hasNonAccreditedInvestors"),
        "non_accredited_investors_count": number(investors, "numberNonAccreditedInvestors"),
        "sales_commissions_usd": number(commissions_node, "dollarAmount"),
        "finders_fees_usd": number(finders_node, "dollarAmount"),
        "gross_proceeds_used_usd": number(proceeds_node, "dollarAmount"),
        "broker_names": broker_names,
        "phone": _fmt_phone(text(issuer, "issuerPhoneNumber")),
        "street": text(issuer_address, "street1") or None,
        "street2": text(issuer_address, "street2") or None,
        "city": text(issuer_address, "city") or None,
        "state_code": text(issuer_address, "stateOrCountry") or None,
        "state": text(issuer_address, "stateOrCountryDescription") or text(issuer_address, "stateOrCountry") or None,
        "zip": text(issuer_address, "zipCode") or None,
        "executives": executives[:20],
        "signatory_name": signatory or None,
        "signatory_title": signature_title,
        "source_url": url,
    }


def _browse_form4(cik, count=20):
    """Use browse-edgar atom feed: returns owner-relationship Form 4s for an issuer CIK."""
    url=(f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}"
         f"&type=4&dateb=&owner=include&count={count}&action=getcompany&output=atom")
    xml=_get(url, raw=True).decode("latin-1","ignore")
    entries=[]
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        title=re.search(r"<title[^>]*>(.*?)</title>", entry, re.S)
        upd=re.search(r"<updated>(.*?)</updated>", entry, re.S)
        href=re.search(r'<link[^>]*href="([^"]+)"', entry)
        entries.append({
            "title": (re.sub(r"<[^>]+>","",title.group(1)).strip() if title else ""),
            "filed": (upd.group(1)[:10] if upd else ""),
            "index_url": (href.group(1) if href else ""),
        })
    return entries

def insider_transactions(symbol_or_cik, limit=15):
    r = resolve(symbol_or_cik)
    if not r:
        return {"error": f"Could not resolve '{symbol_or_cik}'"}
    cik, ticker, name = r
    entries = _browse_form4(cik, count=limit+8)
    txns=[]
    for e in entries:
        if len(txns)>=limit: break
        parsed=_parse_form4_index(e["index_url"])
        if parsed and parsed.get("transactions"):
            parsed["filed"]=e["filed"]
            txns.append(parsed)
    # aggregate only meaningful open-market activity
    buy_sh=sell_sh=0; buy_val=sell_val=0.0; open_buy_filings=open_sell_filings=0
    for t in txns:
        fbuy=fsell=0
        for tr in t.get("transactions",[]):
            if not tr.get("open_market"): continue
            if tr.get("code")=="P":
                fbuy+=tr.get("shares") or 0; buy_val+=tr.get("approx_value_usd") or 0
            elif tr.get("code")=="S":
                fsell+=tr.get("shares") or 0; sell_val+=tr.get("approx_value_usd") or 0
        buy_sh+=fbuy; sell_sh+=fsell
        if fbuy>0: open_buy_filings+=1
        if fsell>0: open_sell_filings+=1
    summary={
        "open_market_purchase_shares":int(buy_sh),"open_market_sale_shares":int(sell_sh),
        "open_market_purchase_usd":round(buy_val),"open_market_sale_usd":round(sell_val),
        "net_open_market_value_usd":round(buy_val - sell_val),
        "purchase_filings":open_buy_filings,"sale_filings":open_sell_filings,
        "net_signal":("net insider BUYING" if buy_val>sell_val and buy_val>0
                      else "net insider SELLING" if sell_val>buy_val and sell_val>0
                      else "no priced open-market buy/sell signal"),
    }
    return {"record_type":"insider_signal","company":name,"ticker":ticker,"cik":cik,
            "filings_returned":len(txns),"summary":summary,
            "insider_transactions":txns}

def _parse_form4_index(index_url):
    """Given a filing index page, find the Form 4 primary instance .xml (wk-form4*) and parse it."""
    try:
        html=_get(index_url, raw=True).decode("latin-1","ignore")
        hrefs=re.findall(r'href="([^"]+\.xml)"', html)
        # prefer the data instance doc: contains /0000XXXXXX/ (accession dir) and 'form4' or 'primary', skip xsl/ viewer
        data=[h for h in hrefs if re.search(r"/\d{10}/(?!xsl)[^/]*form4", h, re.I) or re.search(r"/\d{10}/(?!xsl)[^/]*primary", h, re.I)]
        if not data:
            data=[h for h in hrefs if "/xsl" not in h and not h.lower().endswith(".xsd")]
        if not data: return None
        doc_url=data[0]
        if doc_url.startswith("/"): doc_url="https://www.sec.gov"+doc_url
        elif not doc_url.startswith("http"):
            doc_url=index_url.rsplit("/",1)[0]+"/"+doc_url
        return _parse_form4(doc_url)
    except Exception:
        return None

def _txt(parent, path):
    """Return stripped text of first matching element (namespace-agnostic), else ''."""
    if parent is None: return ""
    tag=path.split("/")[-1]
    el=parent.find(".//"+tag) if False else None
    # namespace-agnostic: iterate
    for el in parent.iter():
        if el.tag.split("}")[-1]==tag:
            return (el.text or "").strip()
    return ""

def _parse_form4(url):
    import xml.etree.ElementTree as ET
    try:
        data=_get(url, raw=True)
        if b"ownershipDocument" not in data:
            return None
        root=ET.fromstring(data)
        def first_text(tag):
            for el in root.iter():
                if el.tag.split("}")[-1]==tag:
                    return (el.text or "").strip()
            return ""
        rpt=first_text("rptOwnerName")
        isdir=first_text("isDirector"); isoff=first_text("isOfficer"); is10=first_text("isTenPercentOwner")
        roles=[]
        if isdir=="1": roles.append("Director")
        if isoff=="1": roles.append("Officer")
        if is10=="1": roles.append("10% owner")
        out=[]
        for txn in root.iter():
            if txn.tag.split("}")[-1]!="nonDerivativeTransaction":
                continue
            def g(t):
                for el in txn.iter():
                    if el.tag.split("}")[-1]==t:
                        txt=(el.text or "").strip()
                        if txt: return txt
                        v=el.find(".//value")
                        if v is not None and (v.text or "").strip(): return v.text.strip()
                return ""
            code=g("transactionCode"); shares=g("transactionShares"); price=g("transactionPricePerShare")
            ad=g("transactionAcquiredDisposedCode"); sec=g("securityTitle"); fdate=g("transactionDate")
            if not shares: continue
            # Only open-market purchases (P) and sales (S) are investable signals.
            # Gifts (G), tax withholding (F), option exercises (M), awards (A) are NOT
            # insider buy/sell signals and must not be labelled as bullish/bearish.
            open_market = code in ("P", "S")
            if open_market:
                signal = "BULLISH (insider buying)" if code == "P" else "BEARISH (insider selling)"
                side = "BUY" if code == "P" else "SELL"
            else:
                signal = "neutral (not open-market)"
                # Acquisition/disposition is not synonymous with a market buy/sell
                # (e.g. an award or gift). Keep the language mechanically accurate.
                side = "ACQUIRED" if ad == "A" else ("DISPOSED" if ad == "D" else ad)
            kind={"A":"award/grant","P":"open-market purchase","S":"open-market sale","D":"disposition to issuer",
                  "G":"gift (bona-fide, $0)","M":"option exercise","F":"tax withholding","J":"other","V":"voluntary",
                  "W":"warrant/right","U":"tender/exchange","X":"option exercise (stock)","C":"conversion"}.get(code, code)
            try: val=float(shares)*(float(price) if price else 0)
            except: val=None
            out.append({"date":fdate,"security":sec,"code":code,"type":kind,"side":side,
                        "open_market":open_market,"signal":signal,
                        "shares":_num(shares),"price_per_share":_num(price),
                        "approx_value_usd":round(val) if val is not None else None})
        return {"insider":rpt,"roles":roles,"transactions":out,"source_url":url}
    except Exception:
        return None

def _num(s):
    try: return float(str(s).replace(",",""))
    except: return None

def filing_search(keyword, forms=None, days_back=365, limit=25):
    days_back = max(1, min(int(days_back), 3650))
    limit = max(1, min(int(limit), 500))
    end=datetime.now(timezone.utc).date(); start=end-timedelta(days=days_back)
    hits,total=_ftsearch(q=keyword, forms=forms, start=start.isoformat(), end=end.isoformat(), limit=limit)
    return {
        "record_type":"filing_search",
        "keyword":keyword,"forms":forms,"days_back":days_back,"matched_total":total,
        "returned":len(hits),
        "results":[{
            "record_type":"filing_match","company":h["company"],"ticker":h.get("ticker"),
            "cik":h["cik"],"form":h["form"],"filed":h["filed"],
            "accession":h.get("accession"),"filing_index":h["filing_index"]
        } for h in hits]
    }
