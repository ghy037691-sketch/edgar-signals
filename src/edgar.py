"""SEC EDGAR client — free, no API key, stable official JSON/XML APIs.
Respects SEC fair-access: custom User-Agent, throttled.
"""
import json, time, urllib.request, urllib.parse, re, threading
from datetime import datetime, timezone, timedelta

UA = "edgar-signals-actor/1.0 (contact: research+edgar@example.com)"
BASE = "https://data.sec.gov"
_last = [0.0]
_lock = threading.Lock()

def _get(url, raw=False):
    # throttle to ~8 req/s
    gap = time.time() - _last[0]
    if gap < 0.12:
        time.sleep(0.12 - gap)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate", "Host": url.split('/')[2]})
    import gzip
    with _lock:
        gap = time.time() - _last[0]
        if gap < 0.12:
            time.sleep(0.12 - gap)
        last_err = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        data = gzip.decompress(data)
                _last[0] = time.time()
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
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "total_assets": ["Assets"],
    "employees": ["NumberOfEmployees"],
}
def _latest_fact(companyfacts, tag_candidates):
    units = companyfacts.get("facts", {}).get("us-gaap", {})
    for tag in tag_candidates:
        if tag in units:
            for ukey, arr in units[tag].get("units", {}).items():
                fy = [x for x in arr if x.get("form") in ("10-K","10-Q","20-F","40-F") and "val" in x]
                if fy:
                    fy.sort(key=lambda x: (x.get("end",""), x.get("filed","")))
                    x = fy[-1]
                    return {"value": x["val"], "as_of": x.get("end"), "form": x.get("form"), "unit": ukey}
    return None

def company_snapshot(symbol_or_cik):
    r = resolve(symbol_or_cik)
    if not r:
        return {"error": f"Could not resolve '{symbol_or_cik}' to a public company"}
    cik, ticker, name = r
    sub = submissions(cik)
    snap = {
        "cik": cik, "ticker": ticker, "name": sub.get("name", name),
        "sic": sub.get("sicDescription"), "exchanges": sub.get("exchanges"),
        "state": sub.get("addresses",{}).get("business",{}).get("stateOrCountry"),
        "fiscal_year_end": sub.get("fiscalYearEnd"),
    }
    try:
        facts = _get(f"{BASE}/api/xbrl/companyfacts/CIK{cik:010d}.json")
        for k, tags in _FIN_TAGS.items():
            v = _latest_fact(facts, tags)
            if v: snap[k] = v
    except Exception as e:
        snap["financials_note"] = f"companyfacts unavailable: {e}"
    # recent filings
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", []); dates = recent.get("filingDate", []); docs = recent.get("primaryDocument", []); acc = recent.get("accessionNumber", [])
    want = ("10-K","10-Q","8-K")
    flist = []
    for i,f in enumerate(forms):
        if f in want:
            acc_nodash = acc[i].replace("-","")
            flist.append({"form": f, "filed": dates[i],
                          "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{docs[i]}"})
    snap["recent_filings"] = flist[:8]
    return snap

def _ftsearch(q=None, forms=None, start=None, end=None, limit=50):
    params = {}
    if q: params["q"] = q
    if forms: params["forms"] = ",".join(forms) if isinstance(forms,(list,tuple)) else forms
    if start or end:
        params["dateRange"] = "custom"
        if start: params["startdt"] = start
        if end: params["enddt"] = end
    url = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(params)
    d = _get(url)
    out = []
    for h in d.get("hits",{}).get("hits",[])[:limit]:
        src = h.get("_source", {})
        _id = h.get("_id","")  # e.g. 0001234567-24-000001:edgar/data/123/d24.htm
        acc = ""; cik = None; doc = ""
        m = re.match(r"([0-9-]+):", _id)
        if m: acc = m.group(1)
        display = src.get("display_names") or []
        cik_list = src.get("ciks") or []
        if cik_list:
            try: cik = int(cik_list[0])
            except: pass
        adsh = src.get("adsh") or acc
        adsh_nodash = (adsh or "").replace("-","")
        doc_url = ""
        if cik and adsh_nodash:
            doc_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}&type={','.join(forms) if forms else ''}"
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh_nodash}/"
        out.append({
            "company": display[0] if display else src.get("entity",""),
            "cik": cik,
            "form": (src.get("file_date") and ",".join(src.get("form",[])) if isinstance(src.get("form"),list) else src.get("form")) or (forms[0] if forms and len(forms)==1 else ""),
            "filed": src.get("file_date") or src.get("fileDate"),
            "accession": adsh,
            "filing_index": doc_url,
            "root": src.get("rootName"),
        })
    return out, d.get("hits",{}).get("total",{}).get("value")

def funding_leads(days_back=30, limit=50, keyword=None, exclude_funds=True,
                  exclude_real_estate=True, industries=None, enrich=True, scan_cap=400):
    """Fresh Form D filings. enrich=True parses primary_doc.xml for amount, sector,
    phone, address, executives. exclude_funds drops pooled investment funds;
    exclude_real_estate drops property-owning SPVs; industries optionally filters to
    Form D industry group(s) (e.g. ['Other Technology','Health Care'])."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days_back)
    hits, total = _ftsearch(q=keyword, forms=["D"], start=start.isoformat(), end=end.isoformat(), limit=scan_cap)
    leads = []
    seen_ciks = set()
    scanned = 0
    want = [i.lower() for i in (industries or [])]
    for h in hits:
        scanned += 1
        name = h["company"].split("(")[0].strip()
        if h.get("cik") and h["cik"] in seen_ciks:
            continue  # amendments / duplicate Form Ds for the same company
        cik = h["cik"]; acc = h["accession"]
        base = {
            "company": name, "cik": cik, "form_d_filed": h["filed"],
            "accession": acc, "filing_index": h["filing_index"],
        }
        if enrich and cik and acc:
            try:
                e = _parse_formd(cik, acc)
                if e:
                    base.update(e)
            except Exception:
                pass
        is_fund = bool(base.get("is_pooled_fund")) or _looks_like_fund(name)
        ind_low = (base.get("industry") or "").lower()
        # Form D real-estate industry groups: Real Estate, Residential, Commercial, Lodging
        re_sectors = ("real estate", "residential", "commercial", "lodging", "conventions", "investing")
        is_re = _looks_like_real_estate(name) or any(s in ind_low for s in re_sectors)
        ind = (base.get("industry") or "")
        if exclude_funds and is_fund:
            continue
        if exclude_real_estate and is_re:
            continue
        if want and not any(w in ind.lower() for w in want):
            continue
        base["is_pooled_fund"] = bool(is_fund)
        if cik:
            seen_ciks.add(cik)
        leads.append(base)
        if len(leads) >= limit:
            break
        if scanned >= scan_cap:
            break
    return {"days_back": days_back, "matched_form_d_total": total, "scanned": scanned,
            "returned": len(leads), "exclude_funds": exclude_funds,
            "exclude_real_estate": exclude_real_estate, "industries_filter": industries or [],
            "enriched": enrich, "leads": leads}


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


def _parse_formd(cik, accession):
    """Parse Form D primary_doc.xml for operating-company lead details."""
    import xml.etree.ElementTree as ET
    nodash = str(accession).replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{nodash}/primary_doc.xml"
    try:
        root = ET.fromstring(_get(url, raw=True))
    except Exception:
        return None

    def leaf(tag):
        for el in root.iter():
            if el.tag.split("}")[-1] == tag and len(list(el)) == 0 and (el.text or "").strip():
                return el.text.strip()
        return ""

    def num(tag):
        v = leaf(tag)
        if not v:
            return None
        try:
            return float(v.replace(",", ""))
        except Exception:
            return None

    industry = leaf("industryGroupType")
    fund_type = leaf("investmentFundType")
    is_fund = (industry == "Pooled Investment Fund") or bool(fund_type)

    # executives / related persons
    execs = []
    for el in root.iter():
        if el.tag.split("}")[-1] == "relatedPerson":
            fn = mn = ln = rel = ""
            for c in el.iter():
                t = c.tag.split("}")[-1]
                if t == "firstName": fn = (c.text or "").strip()
                elif t == "middleName": mn = (c.text or "").strip()
                elif t == "lastName": ln = (c.text or "").strip()
                elif t == "relatedPersonRelationship": rel = (c.text or "").strip()
            full = " ".join(x for x in (fn, mn, ln) if x)
            if full:
                full = " ".join(full.replace("/", " ").split())
                execs.append({"name": full, "relationship": rel})
    # signature titles often capture officer roles
    sig_name = " ".join((leaf("signatureName") or "").replace("/", " ").split())
    sig_title = leaf("signatureTitle")
    if sig_name and sig_title and not any(e["name"] == sig_name for e in execs):
        execs.append({"name": sig_name, "relationship": sig_title})

    return {
        "entity_type": leaf("entityType"),
        "jurisdiction": leaf("jurisdictionOfInc"),
        "industry": industry,
        "is_pooled_fund": is_fund,
        "fund_type": fund_type or None,
        "total_offering_usd": num("totalOfferingAmount") if leaf("totalOfferingAmount") not in ("Indefinite", "") else None,
        "offering_indefinite": leaf("totalOfferingAmount") == "Indefinite",
        "total_amount_sold_usd": num("totalAmountSold"),
        "total_remaining_usd": num("totalRemaining"),
        "minimum_investment_usd": num("minimumInvestmentAccepted"),
        "revenue_range": leaf("revenueRange") or None,
        "phone": leaf("issuerPhoneNumber"),
        "street": leaf("street1"),
        "city": leaf("city"),
        "state": leaf("stateOrCountryDescription") or leaf("stateOrCountry"),
        "zip": leaf("zipCode"),
        "is_amendment": leaf("isAmendment") == "true",
        "has_non_accredited_investors": leaf("hasNonAccreditedInvestors") == "true",
        "executives": execs[:6],
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
        "purchase_filings":open_buy_filings,"sale_filings":open_sell_filings,
        "net_signal":("net insider BUYING" if buy_val>sell_val and buy_val>0
                      else "net insider SELLING" if sell_val>buy_val and sell_val>0
                      else "no open-market signal / mostly scheduled or non-market trades"),
    }
    return {"company":name,"ticker":ticker,"cik":cik,"summary":summary,
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
                side = "BUY" if ad == "A" else ("SELL" if ad == "D" else ad)
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
    end=datetime.now(timezone.utc).date(); start=end-timedelta(days=days_back)
    hits,total=_ftsearch(q=keyword, forms=forms, start=start.isoformat(), end=end.isoformat(), limit=limit)
    return {"keyword":keyword,"forms":forms,"days_back":days_back,"matched_total":total,
            "results":[{"company":h["company"],"cik":h["cik"],"form":h["form"],"filed":h["filed"],"filing_index":h["filing_index"]} for h in hits]}
