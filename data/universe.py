import time
from datetime import datetime, timedelta
import json
import db
from config import ACCOUNTS


# ============================================================
# Step 0: 建池 (每周或首次)
# ============================================================

def build_universe():
    week = datetime.now().strftime('%Y-%W')
    count = db.get_universe_count()
    if count > 200:
        print(f"  Universe already has {count} stocks, skipping build")
        return count

    print("  Building universe...")
    symbols = set()

    symbols.update(_get_alpaca_universe())
    symbols.update(_get_wikipedia_universe())
    symbols.update(_get_yahoo_trending())

    cleaned = set()
    for s in symbols:
        s = str(s).strip().upper()
        if s and len(s) <= 5 and all(c.isalpha() or c == '.' for c in s):
            cleaned.add(s)

    print(f"  Universe: {len(cleaned)} symbols before pre-filter")

    rows = _quick_prefetch(cleaned, week)
    if rows:
        db.save_universe_batch(rows)
        print(f"  Universe saved: {len(rows)} symbols with data")
        return len(rows)
    return 0


def _get_alpaca_universe():
    try:
        for name in ["left_trader", "right_trader", "extreme_trader"]:
            cfg = ACCOUNTS.get(name, {})
            if not cfg.get("api_key"):
                continue
            from alpaca.trading.client import TradingClient
            client = TradingClient(api_key=cfg["api_key"], secret_key=cfg["secret_key"], paper=cfg.get("paper", True))
            assets = client.get_all_assets()
            tickers = []
            for a in assets:
                if a.tradable and a.asset_class == 'us_equity' and a.status == 'active' and a.shortable:
                    if a.symbol and a.symbol.isalpha() and len(a.symbol) <= 5:
                        tickers.append(a.symbol)
            print(f"  Alpaca: {len(tickers)} tradable US equities")
            return tickers
    except Exception as e:
        print(f"  Alpaca universe: {e}")
    return []


def _get_wikipedia_universe():
    import pandas as pd
    import requests
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    symbols = []
    sources = [
        ("S&P 500", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"),
        ("NASDAQ 100", "https://en.wikipedia.org/wiki/Nasdaq-100"),
    ]
    for name, url in sources:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            tables = pd.read_html(resp.text)
            for table in tables:
                for col in table.columns:
                    col_low = str(col).lower()
                    if 'symbol' in col_low or 'ticker' in col_low:
                        for s in table[col].dropna().tolist():
                            symbols.append(str(s).strip().upper())
                        break
            print(f"  {name}: found symbols")
        except Exception as e:
            print(f"  {name}: {e}")
    return list(set(symbols))


def _get_yahoo_trending():
    import requests
    symbols = []
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/trending/US?count=100"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("finance", {}).get("result", [])
            if result and isinstance(result, list):
                for quote in result[0].get("quotes", []):
                    symbols.append(quote.get("symbol", ""))
            print(f"  Yahoo trending: {len(symbols)}")
    except Exception as e:
        print(f"  Yahoo trending: {e}")
    return symbols


def _quick_prefetch(symbols, week):
    import yfinance as yf
    import pandas as pd
    rows = []
    batch = list(symbols)[:1000]
    if not batch:
        return rows

    for i in range(0, len(batch), 50):
        chunk = batch[i:i+50]
        print(f"  Universe download: {min(i+50, len(batch))}/{len(batch)} symbols")
        try:
            data = yf.download(tickers=chunk, period="5d", progress=False, auto_adjust=True, threads=False)
        except Exception as e:
            print(f"  download chunk error: {e}")
            time.sleep(2)
            continue

        close_df = None
        vol_df = None
        if isinstance(data.columns, pd.MultiIndex):
            if 'Close' in data.columns.levels[0]:
                close_df = data['Close']
            if 'Volume' in data.columns.levels[0]:
                vol_df = data['Volume']
        else:
            continue

        if close_df is None:
            continue

        for sym in chunk:
            if sym not in close_df.columns:
                continue
            try:
                series = close_df[sym].dropna()
                if len(series) < 2:
                    continue
                price = float(series.iloc[-1])
                prev = float(series.iloc[-2])
                if price < 1.5 or price > 5000:
                    continue
                change_pct = (price - prev) / prev * 100 if prev > 0 else 0
                ratio = 1.0
                if vol_df is not None and sym in vol_df.columns:
                    v = vol_df[sym].dropna()
                    if len(v) >= 5:
                        avg_vol = float(v.rolling(5).mean().iloc[-1])
                        latest_vol = float(v.iloc[-1])
                        ratio = latest_vol / avg_vol if avg_vol and avg_vol > 0 else 1.0
                attention = abs(change_pct) * max(ratio, 0.5)
                rows.append((sym, price, round(change_pct, 2), round(ratio, 2), round(attention, 2), week))
            except Exception as e:
                continue
        time.sleep(0.3)

    rows.sort(key=lambda x: x[4], reverse=True)
    return rows


# ============================================================
# Step 0.5: 预筛 Top N (按关注度排序，取前 300 计算完整指标)
# ============================================================

def pre_filter(top_n=300):
    top_stocks = db.get_universe_top(top_n, min_attention=0.5)
    if not top_stocks:
        print("  Universe empty, building...")
        build_universe()
        top_stocks = db.get_universe_top(top_n, min_attention=0)
    symbols = [s['symbol'] for s in top_stocks]
    print(f"  Pre-filter: {len(symbols)} symbols for full indicator calc")
    return symbols


# ============================================================
# Step 2: 用 AI 筛子筛鱼
# ============================================================

def apply_criteria(criteria_json, market_data):
    import json as _json
    criteria = _json.loads(criteria_json) if isinstance(criteria_json, str) else criteria_json

    must = criteria.get('must', [])
    must_not = criteria.get('must_not', [])
    prefer = criteria.get('prefer', [])
    max_results = criteria.get('max_results', 30)

    scored = []
    for sym, data in market_data.items():
        indi = data.get('indicators', {})
        ok = True
        for c in must:
            if not _check_condition(c, indi):
                ok = False
                break
        for c in must_not:
            if _check_condition(c, indi):
                ok = False
                break
        if not ok:
            continue
        score = 0
        for c in prefer:
            if _check_condition(c, indi):
                score += 1
        score += abs(data.get('change_pct', 0)) * 0.1
        scored.append((sym, score, data))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in scored[:max_results]], [s[2] for s in scored[:max_results]]


def _check_condition(condition, indicators):
    ind = condition.get('indicator', '')
    op = condition.get('op') or condition.get('operator', 'gt')
    val = condition.get('value', 0)
    cur = indicators.get(ind)
    if cur is None:
        return False

    op_map = {">": "gt", "<": "lt", ">=": "gte", "<=": "lte", "==": "eq"}
    op = op_map.get(op, op)

    try:
        cv = float(cur)
    except (ValueError, TypeError):
        if isinstance(cur, str):
            return cur == str(val)
        return False

    try:
        tv = float(val)
    except (ValueError, TypeError):
        if isinstance(val, str) and isinstance(cur, str):
            return cur == val
        try:
            other = indicators.get(str(val))
            if other is not None:
                tv = float(other)
            else:
                return False
        except:
            return False

    if op == 'gt':
        return cv > tv
    elif op == 'lt':
        return cv < tv
    elif op == 'gte':
        return cv >= tv
    elif op == 'lte':
        return cv <= tv
    elif op == 'eq':
        return abs(cv - tv) < 0.01
    return False
