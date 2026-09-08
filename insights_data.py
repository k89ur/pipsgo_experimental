import re
from io import StringIO
from urllib.parse import quote

import cloudscraper
import pandas as pd
import requests
from bs4 import BeautifulSoup


SCREENER_BASE = "https://www.screener.in"
NSE_BASE = "https://www.nseindia.com"
NSE_ARCHIVES_BASE = "https://nsearchives.nseindia.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

NSE_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{NSE_BASE}/",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def _clean_number(value):
    if value is None:
        return None
    text = str(value).replace(",", "").replace("₹", "").replace("%", "").strip()
    if text in {"", "--", "-", "nan", "None"}:
        return None
    multiplier = 1.0
    if text.endswith("Cr"):
        text = text[:-2].strip()
    try:
        return float(text) * multiplier
    except Exception:
        return None


def _request(url, session=None, params=None, timeout=20):
    client = session or requests.Session()
    client.headers.update(HEADERS)
    response = client.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response


def _screener_company_html(symbol):
    session = requests.Session()
    session.headers.update(HEADERS)
    for path in (f"/company/{quote(symbol)}/consolidated/", f"/company/{quote(symbol)}/"):
        response = session.get(SCREENER_BASE + path, timeout=20)
        if response.ok and "Company not found" not in response.text:
            return response.text, session
    raise ValueError(f"Screener could not find {symbol}.")


def _find_ratio(soup, label):
    for item in soup.select("#top .company-ratios li"):
        name = item.select_one(".name")
        value = item.select_one(".number") or item.select_one(".value")
        if name and value and name.get_text(" ", strip=True).lower() == label.lower():
            return value.get_text(" ", strip=True)
    return None


def _section_table(soup, section_id):
    section = soup.select_one(f"section#{section_id}")
    if section is None:
        return pd.DataFrame()
    try:
        tables = pd.read_html(StringIO(str(section)))
    except ValueError:
        return pd.DataFrame()
    return tables[0] if tables else pd.DataFrame()


def _normalise_table(frame):
    if frame.empty:
        return frame
    table = frame.copy()
    if isinstance(table.columns, pd.MultiIndex):
        table.columns = [str(c[-1]) for c in table.columns]
    table.columns = [str(c).strip() for c in table.columns]
    first = table.columns[0]
    table = table.rename(columns={first: "Metric"})
    table["Metric"] = table["Metric"].astype(str).str.strip()
    return table


def _value_row(table, names):
    if table.empty or "Metric" not in table.columns:
        return None
    wanted = {name.lower() for name in names}
    for _, row in table.iterrows():
        metric = str(row["Metric"]).strip().lower()
        if metric in wanted:
            return row
    return None


def _numeric_series(row, columns):
    values = []
    for column in columns:
        values.append(_clean_number(row.get(column)))
    return values


def _growth_chart(table):
    table = _normalise_table(table)
    if table.empty:
        return pd.DataFrame()
    period_cols = [c for c in table.columns if re.match(r"^(Jun|Sep|Dec|Mar) \d{4}$", str(c))]
    if not period_cols:
        return pd.DataFrame()
    period_cols = sorted(period_cols, key=lambda value: pd.to_datetime(value, format="%b %Y"))

    sales_row = _value_row(table, ["Sales", "Revenue"])
    profit_row = _value_row(table, ["Net Profit", "Profit After Tax"])
    margin_row = _value_row(table, ["OPM %", "Operating Margin %"])

    sales = _numeric_series(sales_row, period_cols) if sales_row is not None else []
    profit = _numeric_series(profit_row, period_cols) if profit_row is not None else []
    margin = _numeric_series(margin_row, period_cols) if margin_row is not None else []

    if not margin and sales and profit:
        margin = [round((p / s) * 100, 2) if p is not None and s not in (None, 0) else None for s, p in zip(sales, profit)]

    rows = []
    for i, period in enumerate(period_cols):
        sales_growth = None
        profit_growth = None
        if i >= 4:
            previous_sales = sales[i - 4] if i - 4 < len(sales) else None
            previous_profit = profit[i - 4] if i - 4 < len(profit) else None
            current_sales = sales[i] if i < len(sales) else None
            current_profit = profit[i] if i < len(profit) else None
            if previous_sales not in (None, 0) and current_sales is not None:
                sales_growth = round((current_sales / previous_sales - 1) * 100, 2)
            if previous_profit not in (None, 0) and current_profit is not None:
                profit_growth = round((current_profit / previous_profit - 1) * 100, 2)
        margin_value = margin[i] if i < len(margin) else None
        rows.append({"Quarter": period, "Sales Growth": sales_growth, "Earning Growth": profit_growth, "Margin": margin_value})
    return pd.DataFrame(rows)


def _website(soup):
    for anchor in soup.select("a"):
        text = anchor.get_text(" ", strip=True).lower()
        href = anchor.get("href") or ""
        if "website" in text and href.startswith("http"):
            return href
    for anchor in soup.select("a"):
        href = anchor.get("href") or ""
        if href.startswith("http") and "screener.in" not in href and "nseindia.com" not in href:
            return href
    return None


def _classification(soup):
    labels = []
    for anchor in soup.select('a[href^="/market/"]'):
        text = anchor.get_text(" ", strip=True)
        if text and text not in labels:
            labels.append(text)
    return (labels[0] if labels else "—", labels[1] if len(labels) > 1 else (labels[0] if labels else "—"))


def _market_share(soup):
    text = soup.get_text(" ", strip=True)
    patterns = [
        r"market share[^\d]{0,80}(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%[^.]{0,80}market share",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return float(match.group(1))
    return None


def _parse_peers(session, warehouse_id):
    if not warehouse_id:
        return pd.DataFrame()
    response = session.get(f"{SCREENER_BASE}/api/company/{warehouse_id}/peers/", timeout=20)
    if not response.ok:
        return pd.DataFrame()
    try:
        tables = pd.read_html(StringIO(response.text))
    except ValueError:
        return pd.DataFrame()
    if not tables:
        return pd.DataFrame()
    table = tables[0].copy()
    if isinstance(table.columns, pd.MultiIndex):
        table.columns = [str(c[-1]) for c in table.columns]
    table.columns = [str(c).strip() for c in table.columns]
    return table


def fetch_screener(symbol):
    html, session = _screener_company_html(symbol)
    soup = BeautifulSoup(html, "html.parser")
    company_info = soup.select_one("#company-info")
    warehouse_id = company_info.get("data-warehouse-id") if company_info else None
    company_id = company_info.get("data-company-id") if company_info else None

    quarterly = _normalise_table(_section_table(soup, "quarters"))
    growth = _growth_chart(quarterly)
    shareholders = _normalise_table(_section_table(soup, "shareholding"))
    peers = _parse_peers(session, warehouse_id)
    sector, industry = _classification(soup)

    title = soup.select_one("#top h1")
    company_name = title.get_text(" ", strip=True) if title else symbol

    return {
        "symbol": symbol,
        "company_name": company_name,
        "pe": _clean_number(_find_ratio(soup, "Stock P/E")),
        "market_cap": _clean_number(_find_ratio(soup, "Market Cap")),
        "website": _website(soup),
        "sector": sector,
        "industry": industry,
        "market_share": _market_share(soup),
        "growth": growth,
        "shareholders": shareholders,
        "peers": peers,
        "source": f"{SCREENER_BASE}/company/{symbol}/consolidated/",
        "company_id": company_id,
        "nse_available": False,
    }


def search_screener(query):
    response = _request(f"{SCREENER_BASE}/api/company/search/", params={"q": query})
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _nse_session(symbol=None):
    session = cloudscraper.create_scraper(browser="chrome")
    session.headers.update(NSE_HEADERS)
    quote_page = f"{NSE_BASE}/get-quotes/equity?symbol={quote(symbol) if symbol else ''}"
    session.get(quote_page, timeout=20)
    return session


def _screener_quote_fallback(symbol):
    html, _ = _screener_company_html(symbol)
    soup = BeautifulSoup(html, "html.parser")
    current = _clean_number(_find_ratio(soup, "Current Price"))
    high_low = _find_ratio(soup, "High / Low") or ""
    match = re.search(r"([\d,.]+)\s*/\s*([\d,.]+)", high_low)
    high = _clean_number(match.group(1)) if match else None
    low = _clean_number(match.group(2)) if match else None
    sector, industry = _classification(soup)
    return {
        "ltp": current,
        "change_pct": None,
        "market_cap": _clean_number(_find_ratio(soup, "Market Cap")),
        "sector": sector,
        "industry": industry,
        "basic_industry": None,
        "indices": [],
        "52w_high": high,
        "52w_low": low,
        "isin": None,
        "nse_available": False,
        "source": "Screener fallback (NSE feed blocked)",
    }


def fetch_nse(symbol):
    try:
        session = _nse_session(symbol)
        quote_response = _request(
            f"{NSE_BASE}/api/quote-equity",
            session=session,
            params={"symbol": symbol},
        )
        quote = quote_response.json()
        trade = _request(
            f"{NSE_BASE}/api/quote-equity",
            session=session,
            params={"symbol": symbol, "section": "trade_info"},
        ).json()
        industry_info = quote.get("industryInfo") or {}
        price_info = quote.get("priceInfo") or {}
        week = price_info.get("weekHighLow") or {}
        trade_info = ((trade.get("marketDeptOrderBook") or {}).get("tradeInfo") or {})
        return {
            "ltp": price_info.get("lastPrice"),
            "change_pct": price_info.get("pChange"),
            "market_cap": trade_info.get("totalMarketCap"),
            "sector": industry_info.get("sector") or industry_info.get("macro"),
            "industry": industry_info.get("industry"),
            "basic_industry": industry_info.get("basicIndustry"),
            "indices": (quote.get("metadata") or {}).get("pdSectorIndAll") or [],
            "52w_high": week.get("max"),
            "52w_low": week.get("min"),
            "isin": (quote.get("info") or {}).get("isin"),
            "nse_available": True,
            "source": "NSE India",
        }
    except Exception:
        return _screener_quote_fallback(symbol)


def _normalise_deal_table(frame):
    if frame.empty:
        return frame
    table = frame.copy()
    table.columns = [str(c).strip() for c in table.columns]
    # NSE archive CSVs have used slightly different casing over time.
    rename = {}
    for column in table.columns:
        key = re.sub(r"[^a-z0-9]", "", column.lower())
        aliases = {
            "date": "date",
            "symbol": "symbol",
            "name": "name",
            "securityname": "name",
            "clientname": "clientName",
            "buysell": "buySell",
            "qty": "qty",
            "quantity": "qty",
            "watp": "watp",
            "tradeprice": "watp",
            "remarks": "remarks",
        }
        if key in aliases:
            rename[column] = aliases[key]
    table = table.rename(columns=rename)
    return table


def _archive_deals(symbol, mode):
    filename = "bulk.csv" if mode == "bulk_deals" else "block.csv"
    url = f"{NSE_ARCHIVES_BASE}/content/equities/{filename}"
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    if not response.content.strip():
        return pd.DataFrame()
    table = pd.read_csv(StringIO(response.text))
    table = _normalise_deal_table(table)
    symbol_column = next((c for c in table.columns if str(c).lower() == "symbol"), None)
    if symbol_column is None:
        return pd.DataFrame()
    return table[table[symbol_column].astype(str).str.strip().str.upper() == symbol].copy()


def _large_deals(symbol, mode):
    # The public NSE archive CSVs are served from nsearchives.nseindia.com and
    # avoid the Cloudflare/WAF restrictions affecting NSE's /api endpoints.
    return _archive_deals(symbol, mode)


def fetch_nse_deals(symbol):
    try:
        bulk = _large_deals(symbol, "bulk_deals")
        block = _large_deals(symbol, "block_deals")
        return {
            "bulk": bulk,
            "block": block,
            "nse_available": True,
            "source": "NSE official archive CSV",
        }
    except Exception:
        # Keep the API as a secondary fallback if the archive host is
        # temporarily unavailable.
        try:
            return {
                "bulk": _api_large_deals(symbol, "bulk_deals"),
                "block": _api_large_deals(symbol, "block_deals"),
                "nse_available": True,
                "source": "NSE large-deal API",
            }
        except Exception:
            return {
                "bulk": pd.DataFrame(),
                "block": pd.DataFrame(),
                "nse_available": False,
                "source": "NSE large-deal feed unavailable from this app server",
            }


def _api_large_deals(symbol, mode):
    session = _nse_session(symbol)
    payload = _request(
        f"{NSE_BASE}/api/snapshot-capital-market-largedeal",
        session=session,
        params={"mode": mode},
    ).json()
    key = "BULK_DEALS_DATA" if mode == "bulk_deals" else "BLOCK_DEALS_DATA"
    rows = payload.get(key) or []
    filtered = [row for row in rows if str(row.get("symbol", "")).strip().upper() == symbol]
    return pd.DataFrame(filtered)
