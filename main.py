import yfinance as yf
import pandas as pd
import pandas_ta as ta
import pytz
from datetime import datetime, time
import db
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import numpy as np

# --- 核心配置 ---
STOCKS = ['AAPL', 'NVDA', 'TSLA', 'AMD', 'MSFT']
TIMEZONE = pytz.timezone('US/Eastern')

# 状态定义
LEVEL_NORMAL = 0
LEVEL_NOTICE = 1   # 异常分 > 2.0 (微小异动)
LEVEL_WARNING = 2  # 异常分 > 3.0 (重点关注)
LEVEL_CRITICAL = 3 # 异常分 > 4.5 (极端行情)

def is_trading_time():
    """交易时间检查 (保持不变)"""
    now = datetime.now(TIMEZONE)
    if now.weekday() >= 5: return 0, "周末休市"
    current_time = now.time()
    if current_time < time(9, 30): return 1, "盘前时段"
    elif current_time > time(16, 0): return 1, "盘后时段"
    return 2, "盘中交易"

def calculate_anomaly_score(symbol, current_price):
    """
    核心算法：计算波动异常分 (Z-Score 变体)
    使用 MAD (中位数绝对偏差) 代替标准差，对极端值更稳健
    """
    try:
        # 拉取过去 1 个月数据计算波动率基准
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1mo")
        
        if len(hist) < 20: return 0.0 # 数据不足

        # 计算每日收益率
        returns = hist['Close'].pct_change().dropna()
        
        # 计算今日的涨跌幅
        prev_close = hist['Close'].iloc[-2]
        current_pct = (current_price - prev_close) / prev_close
        
        # 计算历史波动基准 (MAD)
        median_ret = returns.median()
        # MAD = median(|x - median|)
        mad = np.abs(returns - median_ret).median()
        
        if mad == 0: mad = 0.001 # 防止除零

        # 异常分 = |今日涨跌 - 历史中位数| / (MAD * 常数)
        # 1.4826 是正态分布下的调整因子
        robust_sigma = 1.4826 * mad
        score = np.abs(current_pct - median_ret) / robust_sigma
        
        return score, current_pct * 100
    except Exception as e:
        print(f"算法错误 {symbol}: {e}")
        return 0.0, 0.0

def determine_level(score):
    """根据异常分决定报警级别"""
    if score >= 4.5: return LEVEL_CRITICAL
    if score >= 3.0: return LEVEL_WARNING
    if score >= 2.0: return LEVEL_NOTICE
    return LEVEL_NORMAL

def send_alert_email(symbol, level, price, change_pct, score):
    """发送报警邮件"""
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver_env = os.environ.get('MAIL_RECEIVER')
    
    if not sender or not password or not receiver_env:
        print("❌ 未配置邮箱 Secrets，跳过发送")
        return

    receivers = receiver_env.split(',') if ',' in receiver_env else [receiver_env]
    
    level_tags = {
        LEVEL_NOTICE: "🟡 异动提醒",
        LEVEL_WARNING: "🟠 异常警告",
        LEVEL_CRITICAL: "🔴 熔断级警报"
    }
    
    title = f"{level_tags.get(level, '通知')}：{symbol} 波动异常 ({change_pct:+.2f}%)"
    
    content = f"""
    【量化监控报警】
    
    标的：{symbol}
    现价：${price:.2f}
    涨跌幅：{change_pct:+.2f}%
    
    --- 量化指标 ---
    异常评分：{score:.1f} (正常值 < 2.0)
    判定级别：Level {level}
    
    触发时间：{datetime.now(TIMEZONE).strftime('%H:%M:%S ET')}
    """
    
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = sender
    message['To'] = ",".join(receivers)
    message['Subject'] = Header(title, 'utf-8')

    try:
        smtp_obj = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, receivers, message.as_string())
        smtp_obj.quit()
        print(f"📧 报警邮件已发送: {symbol}")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

def run_monitor():
    db.init_db()
    status_code, status_msg = is_trading_time()
    
    print(f"🚀 启动监控 - {status_msg}")
    
    # 状态机：如果不在盘中，我们依然可以运行数据更新，但不发 Level 2 以下的报警
    # 这里为了演示，我们假设任何时候都可以测试
    
    today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
    
    for symbol in STOCKS:
        try:
            # 1. 获取最新数据
            ticker = yf.Ticker(symbol)
            current_price = ticker.fast_info['last_price']
            
            # 2. 计算量化指标
            score, change_pct = calculate_anomaly_score(symbol, current_price)
            current_level = determine_level(score)
            
            # 3. 读取数据库中的旧状态
            prev_state = db.get_stock_state(symbol)
            prev_level = prev_state['level'] if prev_state else 0
            
            print(f"🔍 {symbol}: ${current_price:.2f} | 涨跌: {change_pct:+.2f}% | 异常