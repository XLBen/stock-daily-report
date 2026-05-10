import sqlite3
import os
import json
import threading
from datetime import datetime, timezone
import pytz


DB_NAME = 'quant_state.db'
_db_lock = threading.Lock()


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    conn.row_factory = sqlite3.Row
    return conn


def _locked_write(fn, *args, **kwargs):
    with _db_lock:
        return fn(*args, **kwargs)


def init_db():
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS stock_states (
                symbol TEXT PRIMARY KEY,
                last_update_date TEXT,
                level INTEGER DEFAULT 0,
                last_price REAL,
                volatility_score REAL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS system_meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # [DEPRECATED]
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_tasks (
                task_key TEXT,
                date_str TEXT,
                completed INTEGER DEFAULT 0,
                PRIMARY KEY (task_key, date_str)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS news_history (
                link_hash TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT,
                message TEXT
            )
        ''')

        # ========================
        # 交易相关表
        # ========================

        conn.execute('''
            CREATE TABLE IF NOT EXISTS trading_plans (
                plan_id TEXT PRIMARY KEY,
                trader TEXT NOT NULL,
                account_id TEXT NOT NULL,
                week_start TEXT NOT NULL,
                week_end TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS plan_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT NOT NULL,
                rule_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                alloc_pct REAL DEFAULT 0,
                is_enabled INTEGER DEFAULT 1,
                FOREIGN KEY (plan_id) REFERENCES trading_plans(plan_id)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS plan_execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT NOT NULL,
                rule_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                order_id TEXT,
                result TEXT,
                reason TEXT
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS trade_order_log (
                order_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL NOT NULL,
                order_type TEXT DEFAULT 'market',
                limit_price REAL,
                stop_loss_price REAL,
                take_profit_price REAL,
                status TEXT DEFAULT 'pending',
                filled_price REAL,
                filled_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                qty REAL NOT NULL,
                avg_entry_price REAL,
                current_price REAL,
                unrealized_pnl REAL,
                snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS stock_universe (
                symbol TEXT PRIMARY KEY,
                price REAL,
                change_pct REAL,
                volume_ratio REAL,
                attention_score REAL,
                indicators_json TEXT,
                last_fetched TIMESTAMP,
                week TEXT
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS trade_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                trader_role TEXT NOT NULL,
                plan_id TEXT DEFAULT '',
                rule_id INTEGER DEFAULT 0,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                qty REAL NOT NULL,
                entry_price REAL,
                exit_price REAL,
                pnl REAL,
                pnl_pct REAL,
                trigger_reason TEXT,
                conditions_detail TEXT,
                rule_snapshot TEXT,
                order_id TEXT,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hold_duration_hours REAL
            )
        ''')


# ============================================================
# 保留的旧 CRUD
# ============================================================

def get_meta(key):
    with get_connection() as conn:
        cursor = conn.execute('SELECT value FROM system_meta WHERE key = ?', (key,))
        row = cursor.fetchone()
        return row['value'] if row else None


def set_meta(key, value):
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO system_meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
        ''', (key, str(value)))


def check_daily_task_done(task_key, date_str):
    with get_connection() as conn:
        cursor = conn.execute('SELECT completed FROM daily_tasks WHERE task_key = ? AND date_str = ?', (task_key, date_str))
        row = cursor.fetchone()
        return row and row['completed'] == 1


def mark_daily_task_done(task_key, date_str):
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO daily_tasks (task_key, date_str, completed) VALUES (?, ?, 1)
            ON CONFLICT(task_key, date_str) DO UPDATE SET completed=1
        ''', (task_key, date_str))


def is_news_sent(link):
    import hashlib
    link_hash = hashlib.md5(link.encode('utf-8')).hexdigest()
    with get_connection() as conn:
        cursor = conn.execute('SELECT 1 FROM news_history WHERE link_hash = ?', (link_hash,))
        return cursor.fetchone() is not None


def mark_news_sent(link):
    import hashlib
    link_hash = hashlib.md5(link.encode('utf-8')).hexdigest()
    with get_connection() as conn:
        conn.execute('INSERT OR IGNORE INTO news_history (link_hash) VALUES (?)', (link_hash,))


def get_stock_state(symbol):
    with get_connection() as conn:
        cursor = conn.execute('SELECT * FROM stock_states WHERE symbol = ?', (symbol,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_stock_state(symbol, date, level, price, vol_score):
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO stock_states (symbol, last_update_date, level, last_price, volatility_score, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE SET
                last_update_date=excluded.last_update_date,
                level=excluded.level,
                last_price=excluded.last_price,
                volatility_score=excluded.volatility_score,
                updated_at=CURRENT_TIMESTAMP
        ''', (symbol, date, level, price, vol_score))


def log_system_run(status, message):
    with get_connection() as conn:
        conn.execute('INSERT INTO system_logs (status, message) VALUES (?, ?)', (status, message))


# ============================================================
# 交易方案 CRUD
# ============================================================

def save_trading_plan(plan_id, trader, account_id, week_start, week_end, plan_json):
    return _locked_write(_save_trading_plan_inner, plan_id, trader, account_id, week_start, week_end, plan_json)

def _save_trading_plan_inner(plan_id, trader, account_id, week_start, week_end, plan_json):
    with get_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO trading_plans (plan_id, trader, account_id, week_start, week_end, plan_json, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        ''', (plan_id, trader, account_id, week_start, week_end, plan_json))
        _sync_plan_rules(conn, plan_id, plan_json)


def _sync_plan_rules(conn, plan_id, plan_json):
    conn.execute('DELETE FROM plan_rules WHERE plan_id = ?', (plan_id,))
    try:
        plan = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
        for rule in plan.get('rules', []):
            conn.execute('''
                INSERT INTO plan_rules (plan_id, rule_id, symbol, action, alloc_pct, is_enabled)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (plan_id, rule.get('rule_id'), rule.get('symbol', ''), rule.get('action', ''), rule.get('alloc_pct', 0)))
    except:
        pass


def get_active_plans():
    with get_connection() as conn:
        cursor = conn.execute('SELECT * FROM trading_plans WHERE status = ? ORDER BY created_at DESC', ('active',))
        return [dict(row) for row in cursor.fetchall()]


def get_plan_rules(plan_id):
    with get_connection() as conn:
        cursor = conn.execute('SELECT * FROM plan_rules WHERE plan_id = ? AND is_enabled = 1', (plan_id,))
        return [dict(row) for row in cursor.fetchall()]


def archive_plan(plan_id):
    with get_connection() as conn:
        conn.execute('UPDATE trading_plans SET status = ? WHERE plan_id = ?', ('archived', plan_id))


def disable_plan_rule(plan_id, rule_id):
    with get_connection() as conn:
        conn.execute('UPDATE plan_rules SET is_enabled = 0 WHERE plan_id = ? AND rule_id = ?', (plan_id, rule_id))


def log_plan_execution(plan_id, rule_id, symbol, action, order_id=None, result=None, reason=None):
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO plan_execution_log (plan_id, rule_id, symbol, action, order_id, result, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (plan_id, rule_id, symbol, action, order_id, result, reason))


def save_order_log(order_id, account_id, symbol, side, qty, order_type='market',
                   limit_price=None, status='pending'):
    with get_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO trade_order_log (order_id, account_id, symbol, side, qty, order_type, limit_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, account_id, symbol, side, qty, order_type, limit_price, status))


def update_order_status(order_id, status, filled_price=None):
    with get_connection() as conn:
        if filled_price:
            conn.execute('UPDATE trade_order_log SET status = ?, filled_price = ?, filled_at = CURRENT_TIMESTAMP WHERE order_id = ?',
                         (status, filled_price, order_id))
        else:
            conn.execute('UPDATE trade_order_log SET status = ? WHERE order_id = ?', (status, order_id))


def get_open_orders(account_id, status='pending'):
    with get_connection() as conn:
        cursor = conn.execute('SELECT * FROM trade_order_log WHERE account_id = ? AND status = ? ORDER BY created_at',
                              (account_id, status))
        return [dict(row) for row in cursor.fetchall()]


def save_snapshot(account_id, symbol, qty, avg_entry_price, current_price, unrealized_pnl):
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO daily_snapshot (account_id, symbol, qty, avg_entry_price, current_price, unrealized_pnl)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (account_id, symbol, qty, avg_entry_price, current_price, unrealized_pnl))


# ============================================================
# trade_journal CRUD
# ============================================================

def insert_trade_journal(account_id, trader_role, symbol, action, qty,
                         entry_price=None, exit_price=None, pnl=None, pnl_pct=None,
                         trigger_reason=None, conditions_detail=None, rule_snapshot=None,
                         order_id=None, plan_id='', rule_id=0, hold_duration_hours=None):
    return _locked_write(_insert_trade_journal_inner, account_id, trader_role, symbol, action, qty,
                         entry_price, exit_price, pnl, pnl_pct,
                         trigger_reason, conditions_detail, rule_snapshot,
                         order_id, plan_id, rule_id, hold_duration_hours)

def _insert_trade_journal_inner(account_id, trader_role, symbol, action, qty,
                                entry_price=None, exit_price=None, pnl=None, pnl_pct=None,
                                trigger_reason=None, conditions_detail=None, rule_snapshot=None,
                                order_id=None, plan_id='', rule_id=0, hold_duration_hours=None):
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO trade_journal (account_id, trader_role, plan_id, rule_id, symbol, action, qty,
                                       entry_price, exit_price, pnl, pnl_pct,
                                       trigger_reason, conditions_detail, rule_snapshot, order_id,
                                       hold_duration_hours)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (account_id, trader_role, plan_id, rule_id, symbol, action, qty,
              entry_price, exit_price, pnl, pnl_pct,
              trigger_reason, conditions_detail, rule_snapshot, order_id,
              hold_duration_hours))


def get_recent_trades(trader_role, limit=5):
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT * FROM trade_journal WHERE trader_role = ? ORDER BY executed_at DESC LIMIT ?',
            (trader_role, limit)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_last_trade(trader_role, symbol):
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT * FROM trade_journal WHERE trader_role = ? AND symbol = ? ORDER BY executed_at DESC LIMIT 1',
            (trader_role, symbol)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_position_entry(trader_role, symbol):
    with get_connection() as conn:
        cursor = conn.execute(
            '''SELECT * FROM trade_journal
               WHERE trader_role = ? AND symbol = ? AND action = 'BUY'
               ORDER BY executed_at DESC LIMIT 1''',
            (trader_role, symbol)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_trades_by_trader(trader_role, limit=10):
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT * FROM trade_journal WHERE trader_role = ? ORDER BY executed_at DESC LIMIT ?',
            (trader_role, limit)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_daily_trade_count(trader_role, date_str=None):
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) as cnt FROM trade_journal WHERE trader_role = ? AND date(executed_at) = ?",
            (trader_role, date_str)
        )
        row = cursor.fetchone()
        return row['cnt'] if row else 0


# ============================================================
# stock_universe CRUD
# ============================================================

def save_universe_batch(rows):
    with get_connection() as conn:
        conn.executemany('''
            INSERT OR REPLACE INTO stock_universe (symbol, price, change_pct, volume_ratio, attention_score, last_fetched, week)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
        ''', rows)


def get_universe_top(limit=300, min_attention=0):
    with get_connection() as conn:
        cursor = conn.execute(
            'SELECT * FROM stock_universe WHERE attention_score >= ? ORDER BY attention_score DESC LIMIT ?',
            (min_attention, limit)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_universe_count():
    with get_connection() as conn:
        cursor = conn.execute('SELECT COUNT(*) as cnt FROM stock_universe')
        row = cursor.fetchone()
        return row['cnt'] if row else 0


def get_universe_freshness():
    with get_connection() as conn:
        cursor = conn.execute('SELECT MAX(last_fetched) as ts FROM stock_universe')
        row = cursor.fetchone()
        return row['ts'] if row else None
