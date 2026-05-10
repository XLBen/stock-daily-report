import os
import pytz

# ============================================================
# 资产池
# ============================================================
STOCKS = [
    'MSFT', 'MA', 'META', 'RKLB', 'GOOGL', 'NVDA', 'POET', 'STLD', 'KO',
    'AMD', 'INTC', 'TSLA', 'AAPL', 'AMZN', 'PLTR', 'SOFI'
]

BENCHMARK = 'SPY'
TIMEZONE = pytz.timezone('US/Eastern')

# ============================================================
# 三个 Alpaca 模拟盘账户 (含风控/持仓纪律, 每交易员一份完整配置)
# ============================================================
ACCOUNTS = {
    "left_trader": {
        # API
        "api_key": os.environ.get("ALPACA_KEY_LEFT", ""),
        "secret_key": os.environ.get("ALPACA_SECRET_LEFT", ""),
        "paper": os.environ.get("ALPACA_PAPER", "true").lower() == "true",
        # 仓位
        "max_positions": 6,
        "max_single_pct": 0.15,
        "total_capital": 10000,
        # 持仓纪律
        "min_hold_hours": 24,
        "cooldown_hours": 12,
        "max_daily_trades": 3,
        "trailing_stop_activation": 0.05,
        "tag": "left",
    },
    "right_trader": {
        "api_key": os.environ.get("ALPACA_KEY_RIGHT", ""),
        "secret_key": os.environ.get("ALPACA_SECRET_RIGHT", ""),
        "paper": os.environ.get("ALPACA_PAPER", "true").lower() == "true",
        "max_positions": 8,
        "max_single_pct": 0.20,
        "total_capital": 10000,
        "min_hold_hours": 6,
        "cooldown_hours": 4,
        "max_daily_trades": 5,
        "trailing_stop_activation": 0.03,
        "tag": "right",
    },
    "extreme_trader": {
        "api_key": os.environ.get("ALPACA_KEY_EXTREME", ""),
        "secret_key": os.environ.get("ALPACA_SECRET_EXTREME", ""),
        "paper": os.environ.get("ALPACA_PAPER", "true").lower() == "true",
        "max_positions": 4,
        "max_single_pct": 0.30,
        "total_capital": 10000,
        "min_hold_hours": 1,
        "cooldown_hours": 2,
        "max_daily_trades": 8,
        "trailing_stop_activation": 0.08,
        "tag": "extreme",
    },
}

# ============================================================
# LLM 配置
# ============================================================
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

# ============================================================
# 风控全局参数
# ============================================================
RISK = {
    "daily_loss_limit_pct": 0.05,
    "default_stop_loss_pct": 0.07,
    "default_take_profit_pct": 0.15,
    "trailing_stop_pct": 0.03,
}

# ============================================================
# 交易时间
# ============================================================
MARKET_OPEN = 9, 30
MARKET_CLOSE = 16, 0

# ============================================================
# 数据拉取
# ============================================================
DATA_HISTORY_PERIOD = "1y"
INTRADAY_INTERVAL = "5m"
INTRADAY_PERIOD = "5d"

# ============================================================
# 周度方案
# ============================================================
PLAN_GENERATION_DAY = "sun"
PLAN_GENERATION_HOUR = 20

# ============================================================
# 运行模式
# ============================================================
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

# ============================================================
# Discord 汇报
# ============================================================
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
DISCORD_ENABLED = bool(DISCORD_BOT_TOKEN) or bool(DISCORD_WEBHOOK_URL)

# ============================================================
# 持仓监控
# ============================================================
MAJOR_MOVE_THRESHOLD_PCT = float(os.environ.get("MAJOR_MOVE_PCT", "10.0"))

# ============================================================
# [DEPRECATED] 邮件推送配置 — 未来新闻机器人用
# ============================================================
# MAIL_USER = os.environ.get("MAIL_USER", "")
# MAIL_PASS = os.environ.get("MAIL_PASS", "")
# MAIL_RECEIVER = os.environ.get("MAIL_RECEIVER", "")
