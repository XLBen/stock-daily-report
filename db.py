import sqlite3
import os
from datetime import datetime

DB_NAME = 'quant_state.db'

def get_connection():
    """获取数据库连接，启用 WAL 模式以提高并发安全性"""
    conn = sqlite3.connect(DB_NAME)
    # 开启 Write-Ahead Logging 模式，适合频繁读写
    conn.execute('PRAGMA journal_mode=WAL')
    conn.row_factory = sqlite3.Row  # 让返回结果像字典一样既可通过下标访问，也可通过列名访问
    return conn

def init_db():
    """初始化数据库表结构"""
    with get_connection() as conn:
        # 创建状态表
        # symbol: 股票代码
        # last_update_date: 最后更新日期 (用于每日重置)
        # level: 当前报警级别 (0=Normal, 1=Notice, 2=Warning, 3=Critical)
        # last_price: 上次记录的价格
        # volatility_score: 记录当前的波动率异常分
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
        
        # 创建系统日志表 (用于监控运行健康度)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT,
                message TEXT
            )
        ''')

def get_stock_state(symbol):
    """查询单只股票的状态"""
    with get_connection() as conn:
        cursor = conn.execute('SELECT * FROM stock_states WHERE symbol = ?', (symbol,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def update_stock_state(symbol, date, level, price, vol_score):
    """更新股票状态 (Upsert: 有则更新，无则插入)"""
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
    """记录系统运行日志"""
    with get_connection() as conn:
        conn.execute('INSERT INTO system_logs (status, message) VALUES (?, ?)', (status, message))