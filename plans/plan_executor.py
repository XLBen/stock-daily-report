import json
import yfinance as yf
from technical import TechnicalAnalyzer

SUPPORTED_OPS = {"gt", "lt", "gte", "lte", "eq", "cross_above", "cross_below"}


def evaluate_condition(condition, current_indicators):
    indicator = condition.get("indicator", "")
    op = condition.get("op", "gt")
    target = condition.get("value", 0)
    current_value = current_indicators.get(indicator)
    if current_value is None:
        return False
    try:
        cv = float(current_value)
    except (ValueError, TypeError):
        cv = None
    if op == "gt":
        return cv is not None and cv > target
    elif op == "lt":
        return cv is not None and cv < target
    elif op == "gte":
        return cv is not None and cv >= target
    elif op == "lte":
        return cv is not None and cv <= target
    elif op == "eq":
        return cv is not None and abs(cv - target) < 0.01
    elif op in ("cross_above", "cross_below"):
        prev_key = f"prev_{indicator}"
        prev = current_indicators.get(prev_key)
        if prev is None:
            return False
        try:
            pv = float(prev)
        except (ValueError, TypeError):
            return False
        if op == "cross_above":
            return pv < target and cv is not None and cv >= target
        elif op == "cross_below":
            return pv > target and cv is not None and cv <= target
    return False


def evaluate_plan_conditions(rule, symbol, current_price):
    conditions = rule.get('conditions', {})
    must_all = conditions.get('must_all', [])
    must_any = conditions.get('must_any', [])

    try:
        df = yf.Ticker(symbol).history(period="3mo")
        if df is None or df.empty or len(df) < 30:
            return False, "no_data"

        ta = TechnicalAnalyzer(df)
        analysis = ta.analyze()
        if analysis is None:
            return False, "no_analysis"

        indicators = analysis.get("indicators", {})
        enriched = dict(indicators)
        enriched["price"] = current_price

        if hasattr(ta, 'df') and len(ta.df) > 2:
            prev_row = ta.df.iloc[-2]
            for key in ("rsi", "macd", "adx", "stoch_k", "cci", "volume_ratio", "williams_r", "bb_position", "sharpe", "momentum_score"):
                cols = ["RSI", "MACD", "ADX", "Stoch_K", "CCI", "Volume_Ratio", "Williams_R", "OBV", "Sharpe"]
                col_map = {
                    "rsi": "RSI", "macd": "MACD", "adx": "ADX",
                    "stoch_k": "Stoch_K", "cci": "CCI",
                    "volume_ratio": "Volume_Ratio", "williams_r": "Williams_R",
                    "bb_position": "RSI", "sharpe": "Sharpe", "momentum_score": "RSI",
                }
                col = col_map.get(key, "RSI")
                try:
                    if col in ta.df.columns:
                        prev_val = float(prev_row[col]) if not hasattr(prev_row[col], '__iter__') else None
                        if prev_val is not None and not hasattr(prev_val, 'isna'):
                            enriched[f"prev_{key}"] = prev_val
                except:
                    continue

            enriched["prev_rsi"] = enriched.get("prev_rsi")
            enriched["change_pct"] = ((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100) if len(df) > 1 else 0

        for cond in must_all:
            if not evaluate_condition(cond, enriched):
                return False, f"must_all fail: {cond.get('indicator', '?')}"

        if must_any:
            any_pass = False
            for cond in must_any:
                if evaluate_condition(cond, enriched):
                    any_pass = True
                    break
            if not any_pass:
                return False, "must_any fail"

        matched = [c.get('indicator', '?') for c in must_all]
        return True, json.dumps({"matched": matched, "reason": "all_conditions_met"})

    except Exception as e:
        return False, f"eval_error: {str(e)[:80]}"
