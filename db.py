import sqlite3
import os
from datetime import datetime
import pytz

DB_NAME = 'quant_state.db'

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.row_factory = sqlite3.Row
    return conn

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
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_tasks (
                task_key TEXT,
                date_str TEXT,
                completed INTEGER DEFAULT 0,
                PRIMARY KEY (task_key, date_str)
            )
        ''')
        # --- 新增：新闻历史表 ---
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

# --- 新闻去重逻辑 ---
def is_news_sent(link):
    import hashlib
    # 用链接的哈希值做主键，节省空间
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