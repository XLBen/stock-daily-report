# QuantBot — AI-Powered Alpaca Paper Trading System

Three AI traders (Contrarian / Trend-Following / Extreme Speculator) independently scan the full US stock market, design weekly quantitative trading plans, and execute paper trades through separate Alpaca accounts.

## Architecture

```
glowing-knight/
├── main.py                   Entry point (scheduler or single-run mode)
├── config.py                 All configuration (3 accounts, risk, LLM, Discord)
├── scheduler.py              Cron jobs (13 scheduled tasks)
├── db.py                     SQLite (11 tables)
├── run.bat                   Windows one-click launcher
│
├── data/                     Data fetching layer
│   ├── fetcher.py            Yahoo Finance (history / prices / fundamentals)
│   ├── news_fetcher.py       Google News RSS
│   └── universe.py           2000+ stock universe builder + pre-filter
│
├── traders/                  Three AI traders
│   ├── base_trader.py        Two-pass LLM pipeline + self-awareness context
│   ├── left_trader.py        Contrarian (oversold reversals, tight stops, 24h+ holds)
│   ├── right_trader.py       Trend follower (MA/MACD confirmed, trailing stops)
│   └── extreme_trader.py     Volatility speculator (high beta, limit orders, 30% positions)
│
├── plans/                    Weekly planning system
│   ├── plan_schema.py        JSON schemas (selection + rules)
│   ├── plan_pool.py          Plan CRUD (save / read / modify / archive)
│   ├── weekly_planner.py     Sunday 4-step pipeline (universe → sieve → select → deep dive)
│   └── plan_executor.py      Real-time condition evaluation (25 indicators)
│
├── execution/                Trade execution layer
│   ├── alpaca_client.py      Alpaca REST API (orders / positions / account)
│   ├── risk_manager.py       Risk controls (cooldown, min-hold, daily limits, meltdown)
│   ├── paper_trader.py       Main trading loop (evaluate → risk-check → submit → log)
│   └── portfolio.py          Portfolio tracking (equity / P&L / snapshots)
│
├── reporting/                Discord integration
│   ├── discord.py            Webhook push + Bot slash commands
│   ├── formatter.py          Embed formatters (trades / portfolio / alerts)
│   └── portfolio_monitor.py  Scheduled portfolio reports + major move alerts
│
├── technical.py              25 technical indicators (RSI, MACD, ADX, Stoch, CCI, Beta...)
├── quant_engine.py           Quantitative analysis (pairs/MM/momentum)
├── plotter.py                Chart generation (daily candlestick + intraday)
└── ai.py                     Legacy LLM utilities (preserved)
```

## Quick Start

```powershell
# Set environment variables (or use run.bat)
$env:LLM_API_KEY = "sk-xxx"
$env:ALPACA_KEY_LEFT = "PKxxx"
$env:ALPACA_SECRET_LEFT = "xxx"
# ... same for RIGHT, EXTREME
$env:ALPACA_PAPER = "true"

# Test (no orders submitted)
python main.py --test-cycle --dry-run

# Single full cycle (plan + trade)
python main.py --test-cycle

# Server daemon (runs forever)
python main.py --log-file quant.log
```

Or use `.\run.bat --test-cycle --dry-run` (pre-configured with your keys).

## Three Traders

| | Left | Right | Extreme |
|---|---|---|---|
| **Philosophy** | Buy fear, sell greed | Follow confirmed trends | Ride volatility breakouts |
| **Entry signals** | RSI < 35, BB lower band | ADX > 25, MACD golden cross | BB Width > 6%, CCI > 200 |
| **Position size** | 5%~12% | 10%~18% | 15%~30% |
| **Stop loss** | 3%~5% tight | 5%~8% + trailing | 8%~12% wide |
| **Min hold** | 24 hours | 6 hours | 1 hour |
| **Cooldown** | 12 hours | 4 hours | 2 hours |

## Weekly Cycle

```
Sunday 20:00 ET → Plan generation (4 steps)
  Step 0: Build universe (~2000 stocks → top 300 by attention)
  Step 1: AI writes filter criteria (per-trader)
  Step 2: Programmatic filtering (300 → 2~25 candidates)
  Step 3: AI selects 3~5 stocks from candidates
  Step 4: Deep dive (news + fundamentals + holdings) → trading rules

Mon/Wed/Fri 10:00 ET → Trade execution
  Load plans → evaluate conditions → risk checks → submit orders → log trades

Every 15 minutes → Stop loss / take profit / trailing stop + major move alerts

Friday 16:00 ET → Weekly settlement (close all + archive plans)
```

## Risk Controls (per account)

| Tier | Rule |
|---|---|
| Daily meltdown | Pause trading if loss ≥ 5% |
| Single stock cap | Left 15% / Right 20% / Extreme 30% |
| Max positions | Left 6 / Right 8 / Extreme 4 |
| Min hold | Left 24h / Right 6h / Extreme 1h |
| Cooldown | Left 12h / Right 4h / Extreme 2h |
| Daily trade limit | Left 3 / Right 5 / Extreme 8 |

## Discord

- **Real-time push**: BUY/SELL/STOP_LOSS/TAKE_PROFIT/LIMIT_ORDER executions
- **Portfolio reports**: Opening bell / 1-hour check / midday / closing (4x daily)
- **Major move alerts**: Stock moves ≥10% with candlestick chart attachment
- **Commands**: `/history <trader>` `/status <trader>` `/status_all`

## Environment Variables

```bash
LLM_API_KEY           # DeepSeek / OpenAI API key
LLM_BASE_URL          # Default: https://api.deepseek.com
LLM_MODEL             # Default: deepseek-chat

ALPACA_KEY_LEFT       # Left trader API key
ALPACA_SECRET_LEFT    # Left trader secret
ALPACA_KEY_RIGHT      # Right trader API key
ALPACA_SECRET_RIGHT   # Right trader secret
ALPACA_KEY_EXTREME    # Extreme trader API key
ALPACA_SECRET_EXTREME # Extreme trader secret
ALPACA_PAPER          # "true" = paper trading

DISCORD_BOT_TOKEN     # Bot token for slash commands
DISCORD_WEBHOOK_URL   # Webhook URL for push notifications
DRY_RUN               # "true" = simulation mode
MAJOR_MOVE_PCT        # Alert threshold (default 10.0)
```

## Database

SQLite (`quant_state.db`), 11 tables:

| Table | Purpose |
|---|---|
| `stock_universe` | Full market stock pool ranked by attention |
| `trading_plans` | Weekly trading plans (JSON) |
| `plan_rules` | Plan rule index (symbol/action) |
| `plan_execution_log` | Condition evaluation results |
| `trade_order_log` | Alpaca order tracking |
| `trade_journal` | Complete trade audit log |
| `daily_snapshot` | Daily portfolio snapshots |
| `news_history` | News deduplication |
| `system_logs` | System event log |
| `stock_states` | Legacy state tracking |
| `system_meta` | Key-value config store |

## Requirements

```
pip install -r requirements.txt
```

- yfinance, pandas, numpy, pytz, openai
- matplotlib, mplfinance, scipy
- alpaca-py, apscheduler, discord.py
- requests, lxml, websockets
