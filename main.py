import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime, time
import db
import os
import smtplib
# --- 邮件库升级 ---
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header
# ----------------
import numpy as np
import ai
import health
import plotter # <--- 引入画家模块
import traceback

# --- 核心配置 ---
STOCKS = ['NVDA', 'AAPL', 'TSLA', 'AMD', 'MSFT', 'META', 'GOOGL']
TIMEZONE = pytz.timezone('US/Eastern')

LEVEL_NORMAL = 0
LEVEL_NOTICE = 1   
LEVEL_WARNING = 2  
LEVEL_CRITICAL = 3 

# ... (is_trading_time 函数保持不变) ...
def is_trading_time():
    now = datetime.now(TIMEZONE)
    if now.weekday() >= 5: return 0, "周末休市"
    current_time = now.time()
    if current_time < time(9, 30): return 1, "盘前时段"
    elif current_time > time(16, 0): return 1, "盘后时段"
    return 2, "盘中交易"

# ... (get_valuation_data 函数保持不变) ...
def get_valuation_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        trailing_pe = info.get('trailingPE')
        forward_pe = info.get('forwardPE')
        peg_ratio = info.get('pegRatio')
        price_to_book = info.get('priceToBook')
        high_52 = info.get('fiftyTwoWeekHigh')
        low_52 = info.get('fiftyTwoWeekLow')
        current = info.get('currentPrice') or info.get('regularMarketPrice')
        position_52w = 0.5
        if high_52 and low_52 and current and high_52 != low_52:
            position_52w = (current - low_52) / (high_52 - low_52)
        return {"pe": trailing_pe, "f_pe": forward_pe, "peg": peg_ratio, "pb": price_to_book, "pos_52w": position_52w, "low_52": low_52, "high_52": high_52}
    except Exception as e:
        print(f"[{symbol}] 估值数据获取失败: {e}")
        return None

# ... (calculate_anomaly_score 函数保持不变) ...
def calculate_anomaly_score(symbol, current_price):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1mo")
        if len(hist) < 20: return 0.0, 0.0
        returns = hist['Close'].pct_change().dropna()
        prev_close = hist['Close'].iloc[-2]
        if prev_close == 0: return 0.0, 0.0
        current_pct = ((current_price - prev_close) / prev_close) * 100
        median_ret = returns.median()
        mad = np.abs(returns - median_ret).median()
        if mad == 0: mad = 0.001 
        robust_sigma = 1.4826 * mad
        score = np.abs((current_pct/100) - median_ret) / robust_sigma
        return score, current_pct
    except Exception as e:
        print(f"[{symbol}] 算法计算错误: {e}")
        return 0.0, 0.0

# ... (determine_level 函数保持不变) ...
def determine_level(score):
    if score >= 4.5: return LEVEL_CRITICAL
    if score >= 3.0: return LEVEL_WARNING
    if score >= 2.0: return LEVEL_NOTICE
    return LEVEL_NORMAL

# --- 🔥 核心修改：升级版发邮件函数 ---
def send_alert_email(symbol, level, price, change_pct, score):
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver_env = os.environ.get('MAIL_RECEIVER')
    if not sender: return
    receivers = receiver_env.split(',') if ',' in receiver_env else [receiver_env]
    
    # 1. 准备数据 (AI & 估值)
    analysis = {}
    news = []
    if level >= LEVEL_WARNING or abs(change_pct) > 3.0:
        print(f"🧠 [AI] 正在分析 {symbol}...")
        news = ai.get_latest_news(symbol)
        try:
            analysis = ai.analyze_market_move(symbol, change_pct, news)
        except:
            analysis = {"summary": "AI不可用", "category": "错误", "risk_level": "未知"}
    else:
        analysis = {"summary": "波动未达阈值", "category": "常规", "risk_level": "低"}
        news = ai.get_latest_news(symbol)

    val = get_valuation_data(symbol)
    val_html = ""
    if val:
        peg_eval = "✅低估" if val['peg'] and val['peg'] < 1.0 else ("❌高估" if val['peg'] and val['peg'] > 2.0 else "合理")
        pos_pct = val['pos_52w'] * 100
        val_html = f"""
        <div style="background-color: #f0f8ff; padding: 12px; border-radius: 6px; margin: 15px 0; border: 1px solid #cceeff;">
            <p style="margin: 0 0 10px 0;"><strong>📊 估值安全垫:</strong></p>
            <table style="width: 100%; font-size: 14px;">
                <tr><td>PE(静): <strong>{val['pe']}</strong></td><td>PEG: <strong>{val['peg']} ({peg_eval})</strong></td></tr>
                <tr><td colspan="2">52周位置: <span style="color: {'green' if pos_pct<20 else 'red' if pos_pct>80 else 'black'}">{pos_pct:.1f}%</span></td></tr>
            </table>
        </div>
        """

    # 2. 生成图表
    chart_path = plotter.generate_chart(symbol)
    chart_html = ""
    if chart_path:
        # cid:chart_image 是邮件协议里引用附件图片的标准写法
        chart_html = f'<div style="text-align: center; margin: 15px 0;"><img src="cid:chart_image" style="max-width: 100%; border: 1px solid #ddd;"></div>'

    # 3. 构建邮件对象 (Multipart)
    msg = MIMEMultipart()
    level_tags = {LEVEL_NOTICE: "🟡", LEVEL_WARNING: "🟠", LEVEL_CRITICAL: "🔴"}
    color = "red" if change_pct < 0 else "green"
    
    msg['Subject'] = Header(f"{level_tags.get(level)}：{symbol} {change_pct:+.2f}% | {analysis.get('category')}", 'utf-8')
    msg['From'] = sender
    msg['To'] = ",".join(receivers)

    # 4. 组装 HTML 正文
    content = f"""
    <html>
    <body>
        <h2 style="border-bottom: 2px solid {color};">{symbol} 异常波动监控</h2>
        <p>现价: <strong>${price:.2f}</strong> (<span style="color:{color}">{change_pct:+.2f}%</span>)</p>
        <p>异常分: {score:.1f}</p>
        
        {val_html}
        {chart_html} <hr/>
        <h3>🧠 AI 归因</h3>
        <div style="background-color: #fafafa; padding: 10px; border-left: 4px solid #333;">
            <p><strong>{analysis.get('summary')}</strong></p>
            <p>建议: {analysis.get('action_suggestion', '暂无')}</p>
        </div>
        
        <hr/>
        <h3>📰 新闻</h3>
        <ul>{''.join([f'<li>{n}</li>' for n in news[:3]])}</ul>
        <p style="color: gray; font-size: 10px;">Generated at {datetime.now(TIMEZONE).strftime('%H:%M ET')}</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(content, 'html', 'utf-8'))

    # 5. 嵌入图片附件
    if chart_path:
        with open(chart_path, 'rb') as f:
            mime_img = MIMEImage(f.read())
            # 定义 Content-ID，让 HTML 里的 cid:chart_image 能找到这张图
            mime_img.add_header('Content-ID', '<chart_image>')
            msg.attach(mime_img)
        # 发完删掉临时文件，保持整洁
        os.remove(chart_path)

    try:
        smtp_obj = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, receivers, msg.as_string())
        smtp_obj.quit()
        print(f"✅ 带图邮件已发送: {symbol}")
    except Exception as e:
        print(f"❌ 发送失败: {e}")

# ... (run_monitor 函数保持不变，为了节省篇幅就不重复了，它不需要修改) ...
def run_monitor():
    db.init_db()
    try:
        health.check_system_health()
    except Exception as e:
        traceback.print_exc()

    status_code, status_msg = is_trading_time()
    print(f"🚀 启动监控 - {status_msg}")
    
    if status_code == 0:
        print("😴 市场休眠中...")
        return

    today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
    
    for symbol in STOCKS:
        try:
            ticker = yf.Ticker(symbol)
            try:
                current_price = ticker.fast_info['last_price']
            except:
                hist = ticker.history(period='1d')
                if hist.empty: continue
                current_price = hist['Close'].iloc[-1]
            
            score, change_pct = calculate_anomaly_score(symbol, current_price)
            current_level = determine_level(score)
            
            prev_state = db.get_stock_state(symbol)
            prev_level = prev_state['level'] if prev_state else 0
            
            print(f"🔍 {symbol}: {change_pct:+.2f}% (Lv{current_level})")
            
            is_level_up = (current_level > prev_level)
            is_critical = (current_level == LEVEL_CRITICAL)
            
            if (is_level_up and current_level >= LEVEL_NOTICE) or is_critical:
                print(f"🔔 触发报警: {symbol}")
                send_alert_email(symbol, current_level, current_price, change_pct, score)
            
            db.update_stock_state(symbol, today_str, current_level, current_price, score)
            
        except Exception as e:
            print(f"❌ {symbol} 错误: {e}")
            traceback.print_exc()

    db.log_system_run("SUCCESS", "Cycle Completed")

if __name__ == "__main__":
    try:
        run_monitor()
    except Exception as e:
        health.send_system_email("☠️ 系统崩溃", str(e))
        exit(1)