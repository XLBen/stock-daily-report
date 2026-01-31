import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime, time
import db
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import numpy as np
import ai

# --- 核心配置 ---
STOCKS = ['AAPL', 'NVDA', 'TSLA', 'AMD', 'MSFT']
TIMEZONE = pytz.timezone('US/Eastern')

# 状态定义
LEVEL_NORMAL = 0
LEVEL_NOTICE = 1   # 异常分 > 2.0
LEVEL_WARNING = 2  # 异常分 > 3.0
LEVEL_CRITICAL = 3 # 异常分 > 4.5

def is_trading_time():
    """交易时间检查"""
    now = datetime.now(TIMEZONE)
    # 暂时把周末检查注释掉，方便你现在测试
    # if now.weekday() >= 5: return 0, "周末休市"
    
    current_time = now.time()
    # 稍微放宽一点时间，方便测试
    if current_time < time(4, 0): return 1, "盘前等待"
    return 2, "盘中/盘后交易"

# --- 替代 pandas_ta 的原生计算函数 ---
def calculate_rsi_native(series, period=14):
    """手写 RSI 指标计算 (基于 Wilder's Smoothing)"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    
    # 使用指数加权移动平均 (EWM) 模拟 Wilder 平滑
    avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_anomaly_score(symbol, current_price):
    """
    计算波动异常分 (Z-Score / MAD)
    """
    try:
        # 拉取过去 1 个月数据
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1mo")
        
        if len(hist) < 20: return 0.0, 0.0

        # --- 这里的计算不再依赖 pandas_ta ---
        
        # 1. 计算每日收益率
        returns = hist['Close'].pct_change().dropna()
        
        # 2. 计算今日涨跌幅
        prev_close = hist['Close'].iloc[-2]
        current_pct = (current_price - prev_close) / prev_close
        
        # 3. 计算 MAD (中位数绝对偏差)
        median_ret = returns.median()
        mad = np.abs(returns - median_ret).median()
        if mad == 0: mad = 0.001 

        robust_sigma = 1.4826 * mad
        score = np.abs(current_pct - median_ret) / robust_sigma
        return 5.0, -8.5
        return score, current_pct * 100
    except Exception as e:
        print(f"算法错误 {symbol}: {e}")
        return 0.0, 0.0

def determine_level(score):
    if score >= 4.5: return LEVEL_CRITICAL
    if score >= 3.0: return LEVEL_WARNING
    if score >= 2.0: return LEVEL_NOTICE
    return LEVEL_NORMAL

def send_alert_email(symbol, level, price, change_pct, score):
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver_env = os.environ.get('MAIL_RECEIVER')
    
    if not sender: return

    receivers = receiver_env.split(',') if ',' in receiver_env else [receiver_env]
    
    # --- AI 介入开始 ---
    print(f"🧠 正在调用 AI 分析 {symbol} 的波动原因...")
    
    # 1. 抓新闻
    news = ai.get_latest_news(symbol)
    
    # 2. 只有 Level 2 以上才花钱调 AI，省钱技巧
    if level >= LEVEL_WARNING or abs(change_pct) > 3.0:
        analysis = ai.analyze_market_move(symbol, change_pct, news)
    else:
        analysis = {"summary": "波动较小，未触发 AI 分析", "category": "常规波动", "risk": "低"}
    # --- AI 介入结束 ---

    level_tags = {
        LEVEL_NOTICE: "🟡 异动",
        LEVEL_WARNING: "🟠 警告",
        LEVEL_CRITICAL: "🔴 熔断"
    }
    
    title = f"{level_tags.get(level, '通知')}：{symbol} {change_pct:+.2f}% | {analysis['category']}"
    
    # 构造 HTML 邮件 (比纯文本好看)
    content = f"""
    <html>
    <body>
        <h2>🚨 量化监控报警: {symbol}</h2>
        <p><strong>现价:</strong> ${price:.2f} (<span style="color: {'red' if change_pct < 0 else 'green'}">{change_pct:+.2f}%</span>)</p>
        <p><strong>异常评分:</strong> {score:.1f} (Level {level})</p>
        
        <hr/>
        <h3>🧠 AI 归因分析</h3>
        <ul>
            <li><strong>原因:</strong> {analysis['summary']}</li>
            <li><strong>分类:</strong> {analysis['category']}</li>
            <li><strong>风险等级:</strong> {analysis['risk_level']}</li>
        </ul>
        
        <hr/>
        <h3>📰 相关新闻</h3>
        <p>{'<br/>'.join(news[:3])}</p>
        
        <p style="font-size: small; color: gray;">生成时间: {datetime.now(TIMEZONE).strftime('%H:%M:%S ET')}</p>
    </body>
    </html>
    """
    
    message = MIMEText(content, 'html', 'utf-8') # 注意这里改成了 'html'
    message['From'] = sender
    message['To'] = ",".join(receivers)
    message['Subject'] = Header(title, 'utf-8')

    try:
        smtp_obj = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, receivers, message.as_string())
        smtp_obj.quit()
        print(f"📧 智能报警邮件已发送: {symbol}")
    except Exception as e:
        print(f"❌ 发送失败: {e}")



def run_monitor():
    db.init_db()
    status_code, status_msg = is_trading_time()
    
    print(f"🚀 启动监控 - {status_msg}")
    
    # 如果是休市，直接退出（为了测试，我在上面把周末判断临时关了）
    if status_code == 0:
        print("😴 休市中")
        return

    today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
    
    for symbol in STOCKS:
        try:
            ticker = yf.Ticker(symbol)
            # 使用 fast_info 获取实时价格
            try:
                current_price = ticker.fast_info['last_price']
            except:
                # 容错：如果 fast_info 拿不到，就拿历史数据最后一行
                current_price = ticker.history(period='1d')['Close'].iloc[-1]
            
            score, change_pct = calculate_anomaly_score(symbol, current_price)
            current_level = determine_level(score)
            
            # 读取旧状态
            prev_state = db.get_stock_state(symbol)
            prev_level = prev_state['level'] if prev_state else 0
            
            print(f"🔍 {symbol}: ${current_price:.2f} | 涨跌: {change_pct:+.2f}% | 异常分: {score:.2f}")
            
            # 状态机升级判断
            if current_level > prev_level and current_level >= LEVEL_NOTICE:
                print(f"🔔 升级报警: {symbol}")
                send_alert_email(symbol, current_level, current_price, change_pct, score)
            
            db.update_stock_state(symbol, today_str, current_level, current_price, score)
            
        except Exception as e:
            print(f"❌ {symbol} 失败: {e}")

    db.log_system_run("SUCCESS", "Checked")

if __name__ == "__main__":
    run_monitor()