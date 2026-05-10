import yfinance as yf
import pandas as pd
import time
from config import STOCKS, BENCHMARK, DATA_HISTORY_PERIOD, INTRADAY_INTERVAL


def _retry_yahoo(func, *args, max_retries=3, base_delay=2, **kwargs):
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            if result is not None:
                return result
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
            else:
                raise
    return None


def fetch_history(symbol, period=DATA_HISTORY_PERIOD):
    df = yf.Ticker(symbol).history(period=period)
    if df.empty:
        print(f"  {symbol}: no history data")
        return None
    return df


def fetch_all():
    pool = {}
    for s in STOCKS:
        try:
            df = fetch_history(s)
            if df is not None:
                pool[s] = df
        except Exception as e:
            print(f"  {s} fetch error: {e}")
    try:
        bench = fetch_history(BENCHMARK)
        if bench is not None:
            pool[BENCHMARK] = bench
    except:
        pass
    return pool


def fetch_intraday(symbol, period="5d", interval=None):
    if interval is None:
        interval = INTRADAY_INTERVAL
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval)
        return df if not df.empty else None
    except:
        return None


def get_current_price(symbol):
    try:
        df = _retry_yahoo(yf.Ticker(symbol).history, period="1d", max_retries=2, base_delay=1)
        if df is not None and not df.empty:
            return float(df['Close'].iloc[-1])
    except:
        pass
    return None


def get_current_prices(symbols):
    result = {}
    for s in symbols:
        p = get_current_price(s)
        if p is not None:
            result[s] = p
    return result


def fetch_fundamentals(symbol):
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}

        def safe_float(key, default=None):
            v = info.get(key)
            if v is None:
                return default
            try:
                return round(float(v), 4)
            except (ValueError, TypeError):
                return default

        def safe_str(key, default=""):
            v = info.get(key, default)
            return str(v) if v is not None else default

        result = {
            "pe_ratio": safe_float("trailingPE"),
            "forward_pe": safe_float("forwardPE"),
            "market_cap": info.get("marketCap"),
            "sector": safe_str("sector"),
            "industry": safe_str("industry"),
            "beta": safe_float("beta", 1.0),
            "revenue_growth": safe_float("revenueGrowth"),
            "earnings_growth": safe_float("earningsGrowth"),
            "profit_margins": safe_float("profitMargins"),
            "short_ratio": safe_float("shortRatio"),
            "fifty_day_avg": safe_float("fiftyDayAverage"),
            "two_hundred_day_avg": safe_float("twoHundredDayAverage"),
            "recommendation": safe_str("recommendationKey", "-"),
            "target_mean_price": safe_float("targetMeanPrice"),
        }
        return result
    except Exception as e:
        print(f"  {symbol} fundamentals error: {e}")
        return {}
