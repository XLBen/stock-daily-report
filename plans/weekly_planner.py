from data.fetcher import fetch_all, fetch_fundamentals, get_current_prices
from data.news_fetcher import fetch_all_news
from data.universe import build_universe, pre_filter, apply_criteria
from technical import TechnicalAnalyzer
from quant_engine import QuantEngine
from traders.left_trader import LeftTrader
from traders.right_trader import RightTrader
from traders.extreme_trader import ExtremeTrader
from plans.plan_pool import PlanPool
from config import STOCKS, ACCOUNTS, TIMEZONE
from datetime import datetime, timedelta
import db
import json
import traceback


def generate_weekly_plans():
    print(f"\n{'#'*60}")
    print(f"#  Sunday Plan Generation — {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}\n")

    now = datetime.now(TIMEZONE)
    week_start = now.strftime('%Y-%m-%d')
    week_end = (now + timedelta(days=5)).strftime('%Y-%m-%d')

    pool = PlanPool()
    pool.archive_all_active()

    # ============================================================
    # Step 0: 建宇宙池
    # ============================================================
    print("[Step 0] Building stock universe...")
    universe_size = build_universe()
    print(f"  Universe ready: {universe_size} stocks\n")

    # ============================================================
    # Step 0.5: 预筛 Top 300
    # ============================================================
    print("[Step 0.5] Pre-filtering top candidates...")
    candidate_symbols = pre_filter(top_n=300)
    print(f"  Selected {len(candidate_symbols)} for detailed analysis\n")

    # ============================================================
    # 对 Top 300 计算完整 25 指标
    # ============================================================
    print(f"[Indicator Calc] Computing 25 indicators for pre-filtered stocks...")

    import yfinance as yf
    import pandas as pd
    batch = candidate_symbols[:300]
    df_pool = {}
    print(f"  Downloading 3mo history for {len(batch)} stocks...")
    for i, sym in enumerate(batch):
        try:
            df = yf.Ticker(sym).history(period="3mo")
            if df is not None and not df.empty and len(df) >= 30:
                df_pool[sym] = df
        except:
            continue
        if (i+1) % 25 == 0:
            print(f"  Progress: {i+1}/{len(batch)} ({len(df_pool)} valid)")
    print(f"  Complete: {len(df_pool)}/{len(batch)} stocks have valid history")

    qe = QuantEngine(df_pool)

    market_data = {}
    for sym in df_pool:
        df = df_pool[sym]
        try:
            ta = TechnicalAnalyzer(df)
            analysis = ta.analyze()
            if analysis is None:
                continue
            indicators = analysis.get("indicators", {})
            curr_price = df['Close'].iloc[-1]
            prev_price = df['Close'].iloc[-2] if len(df) > 1 else curr_price
            market_data[sym] = {
                "price": round(float(curr_price), 2),
                "change_pct": round(float((curr_price - prev_price) / prev_price * 100), 2),
                "indicators": indicators,
                "news": [],
                "fundamentals": {},
                "quant": {
                    "momentum": qe.get_momentum_score(sym),
                }
            }
        except Exception as e:
            continue

    print(f"  Indicators computed for {len(market_data)} stocks\n")

    # Also include original STOCKS (guaranteed coverage)
    pool_data = fetch_all()
    for sym in STOCKS:
        df = pool_data.get(sym)
        if df is None or sym in market_data:
            continue
        try:
            ta = TechnicalAnalyzer(df)
            analysis = ta.analyze()
            if analysis is None:
                continue
            indicators = analysis.get("indicators", {})
            curr_price = df['Close'].iloc[-1]
            prev_price = df['Close'].iloc[-2] if len(df) > 1 else curr_price
            market_data[sym] = {
                "price": round(float(curr_price), 2),
                "change_pct": round(float((curr_price - prev_price) / prev_price * 100), 2),
                "indicators": indicators,
                "news": [],
                "fundamentals": {},
                "quant": {"momentum": qe.get_momentum_score(sym) if qe else 0},
            }
        except:
            continue

    print(f"  Total analysis pool: {len(market_data)} stocks\n")

    # ============================================================
    # Per-Trader: Step 1-4
    # ============================================================
    traders = {
        "left_trader": LeftTrader(),
        "right_trader": RightTrader(),
        "extreme_trader": ExtremeTrader(),
    }

    plans = {}
    for name, trader in traders.items():
        print(f"[{name}] Step 1: AI writes filter criteria...")
        criteria = trader.generate_criteria()
        print(f"  Criteria: {json.dumps(criteria, ensure_ascii=False)[:200]}")

        print(f"[{name}] Step 2: applying criteria to {len(market_data)} stocks...")
        matched_syms, matched_data = apply_criteria(criteria, market_data)
        print(f"  Matched: {len(matched_syms)} stocks")

        if not matched_syms:
            print(f"  No matches, falling back to top attention stocks")
            fallback = sorted(market_data.items(), key=lambda x: abs(x[1].get('change_pct', 0)), reverse=True)[:20]
            matched_syms = [f[0] for f in fallback]
            matched_data = [f[1] for f in fallback]

        print(f"[{name}] Step 3: AI selects 3-5 from {len(matched_syms)} candidates...")
        selection_market = {}
        for i, sym in enumerate(matched_syms):
            if i >= 40:
                break
            if sym in market_data:
                selection_market[sym] = market_data[sym]
        selection = trader.select_candidates(selection_market)
        selected = selection.get('selections', [])
        selected_symbols = [s['symbol'] for s in selected]
        print(f"  Selected: {selected_symbols}")

        print(f"[{name}] Step 4: deep dive + generating rules...")
        news_all = fetch_all_news(selected_symbols) if selected_symbols else {}
        fundamentals_all = {}
        for sym in selected_symbols:
            fundamentals_all[sym] = fetch_fundamentals(sym)

        candidate_data = {}
        for sym in selected_symbols:
            md = market_data.get(sym)
            if md is None:
                continue
            md_copy = dict(md)
            md_copy["news"] = news_all.get(sym, [])
            md_copy["fundamentals"] = fundamentals_all.get(sym, {})
            candidate_data[sym] = md_copy

        acct = ACCOUNTS.get(name, {})
        current_positions = []
        if acct.get("api_key"):
            try:
                from execution.alpaca_client import AlpacaPaperClient
                c = AlpacaPaperClient(name)
                if c.is_account_valid():
                    for p in c.get_positions():
                        current_positions.append({
                            "symbol": p.symbol,
                            "qty": float(p.qty),
                            "entry_price": float(p.avg_entry_price),
                        })
            except:
                pass

        plan = trader.generate_rules(candidate_data, current_positions)
        if plan is None:
            plan = trader._fallback_rules(candidate_data)

        plan["week_start"] = week_start
        plan["week_end"] = week_end
        plan["generated_at"] = now.isoformat()
        plan["selections"] = selected
        plan["criteria"] = criteria
        plans[name] = plan
        print(f"  [{name}] Done: {len(plan.get('rules', []))} rules\n")

    if plans:
        pool.save_plans(plans)
        pool.print_active_summary()
    else:
        print("No plans generated!")

    db.log_system_run("weekly_plan", f"generated {len(plans)} plans from {len(market_data)} stocks")
    print("Sunday plan generation complete\n")
    return plans
