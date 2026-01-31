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
        # 1. 股票状态表
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
        
        # 2. 系统元数据表 (用于一次性任务，如启动后20分钟)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS system_meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 3. 日常任务表 (新增：用于每日定时任务，如 8:00 报告)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_tasks (
                task_key TEXT,
                date_str TEXT,
                completed INTEGER DEFAULT 0,
                PRIMARY KEY (task_key, date_str)
            )
        ''')
        
        # 4. 日志表
        conn.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT,
                message TEXT
            )
        ''')

# --- 元数据操作 (用于相对时间任务) ---
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

# --- 日常任务操作 (新增：用于绝对时间任务) ---
def check_daily_task_done(task_key, date_str):
    """检查今天的某个定时任务是否做过"""
    with get_connection() as conn:
        cursor = conn.execute('SELECT completed FROM daily_tasks WHERE task_key = ? AND date_str = ?', (task_key, date_str))
        row = cursor.fetchone()
        return row and row['completed'] == 1

def mark_daily_task_done(task_key, date_str):
    """标记今天的任务已完成"""
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO daily_tasks (task_key, date_str, completed) VALUES (?, ?, 1)
            ON CONFLICT(task_key, date_str) DO UPDATE SET completed=1
        ''', (task_key, date_str))

# --- 股票状态操作 ---
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