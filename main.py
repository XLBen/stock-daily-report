import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime, time
import db
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header
import numpy as np
import ai
import health
import plotter
import traceback
from technical import TechnicalAnalyzer
from quant_engine import QuantEngine 

# --- 核心配置 ---
# 建议将 XAUUSD=X 暂时移除，或确认后替换
STOCKS = [
    'SGLN.L', 'GDGB.L', 'MSFT', 'MA', 'META', 
    'USAR', 'RKLB', 'GOOGL', 'EQGB.L', 'EQQQ.L', 
    'NVDA', 'QQQ3.L', 'VUAG.L', 'POET', 'STLD', 'KO'
]
TIMEZONE = pytz.timezone('US/Eastern')

def is_trading_time():
    now = datetime.now(TIMEZONE)
    if now.weekday() >= 5: return 0, "周末休市"
    current_time = now.time()
    if current_time < time(9, 30): return 1, "盘前时段"
    elif current_time > time(16, 0): return 1, "盘后时段"
    return 2, "盘中交易"

def calculate_anomaly_score(symbol, current_price, df_hist):
    try:
        if len(df_hist) < 20: return 0.0, 0.0
        returns = df_hist['Close'].pct_change().dropna()
        prev_close = df_hist['Close'].iloc[-2]
        current_pct = ((current_price - prev_close) / prev_close) * 100
        mad = np.abs(returns - returns.median()).median()
        score = np.abs((current_pct/100) - returns.median()) / (1.4826 * mad + 1e-6)
        return score, current_pct
    except: return 0.0, 0.0

def determine_level(score):
    if score >= 4.5: return 3
    if score >= 3.0: return 2
    if score >= 2.0: return 1
    return 0

def generate_stock_html(data):
    symbol = data['symbol']
    pct = data['change_pct']
    color = "red" if pct < 0 else "green"
    tech = data.get('tech_analysis', {})
    sigs = tech.get('signals', {})
    setup = tech.get('trade_setup', {})
    quant = data.get('quant_analysis', {})

    chart_html = f'<div style="text-align:center;"><img src="cid:{data["chart_cid"]}" style="width:100%;max-width:600px;"></div>' if data['chart_path'] else ""

    return f"""
    <div style="border:1px solid #ddd; padding:15px; margin-bottom:20px; border-radius:8px;">
        <h2 style="margin:0; border-bottom:2px solid {color};">{symbol} <span style="color:{color};">{pct:+.2f}%</span></h2>
        <p>价格: ${data['price']:.2f} | 动量分: {quant.get('momentum', 0)}</p>
        <table style="width:100%; font-size:12px;">
            <tr style="background:#f9f9f9;"><th>左侧信号</th><th>右侧信号</th></tr>
            <tr>
                <td>{sigs.get('left_side', '-')[1]}<br/><i>AI: {data.get('ai_left', '-')}</i></td>
                <td>{sigs.get('right_side', '-')[1]}<br/><i>AI: {data.get('ai_right', '-')}</i></td>
            </tr>
        </table>
        <div style="background:#f0fff4; padding:5px; margin-top:5px;">🛒 加仓参考: ${setup.get('buy_target_price', 0)}</div>
        <div style="background:#fff5f5; padding:5px; margin-top:5px;">🛡️ 止损参考: ${setup.get('stop_loss_price', 0)}</div>
        {chart_html}
    </div>
    """

def send_summary_report(data_list, reason):
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver = os.environ.get('MAIL_RECEIVER')
    if not sender or not data_list: return

    msg = MIMEMultipart('related')
    msg['Subject'] = Header(f"{reason} | V6.2 Fix", 'utf-8')
    msg['From'] = sender
    msg['To'] = receiver

    html_body = f"<html><body><h1 style='text-align:center;'>{reason}</h1>"
    for d in data_list: html_body += generate_stock_html(d)
    html_body += "</body></html>"
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    for d in data_list:
        if d['chart_path']:
            try:
                with open(d['chart_path'], 'rb') as f:
                    img = MIMEImage(f.read())
                    img.add_header('Content-ID', f'<{data["chart_cid"]}>')
                    img.add_header('Content-Disposition', 'inline')
                    msg.attach(img)
            except: pass

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(sender, password)
            s.sendmail(sender, receiver.split(','), msg.as_string())
    except Exception as e: print(f"SMTP Error: {e}")

def run_monitor():
    db.init_db()
    
    # --- 核心修复：变量初始化 ---
    report_data_list = []  
    force_report_reason = None 
    
    try:
        tasks = health.get_pending_tasks()
        for t_type, reason in tasks:
            if t_type == 'REPORT_ALL':
                force_report_reason = reason
                break
    except Exception as e:
        print(f"Health Check Error: {e}")

    status_code, status_msg = is_trading_time()
    if status_code == 0 and not force_report_reason:
        print("休市中...")
        return

    print(f"开始分析... 任务: {force_report_reason}")
    df_pool = {}
    for s in STOCKS:
        try:
            df = yf.Ticker(s).history(period="1y")
            if not df.empty: df_pool[s] = df
        except: pass
    
    qe = QuantEngine(df_pool)

    for symbol in STOCKS:
        if symbol not in df_pool: continue
        try:
            df = df_pool[symbol]
            curr_price = df['Close'].iloc[-1]
            ta = TechnicalAnalyzer(df)
            tech_res = ta.analyze()
            score, pct = calculate_anomaly_score(symbol, curr_price, df)
            
            data = {
                'symbol': symbol, 'price': curr_price, 'change_pct': pct,
                'tech_analysis': tech_res,
                'quant_analysis': {
                    "momentum": qe.get_momentum_score(symbol)
                },
                'chart_path': plotter.generate_chart(symbol),
                'chart_cid': f"chart_{symbol}_{datetime.now().microsecond}"
            }
            
            # AI 分析
            try:
                news = ai.get_latest_news(symbol)
                ai_res = ai.analyze_market_move(symbol, pct, news, tech_res)
                data['ai_left'] = ai_res.get('left_side_analysis', '-')
                data['ai_right'] = ai_res.get('right_side_analysis', '-')
            except: pass

            report_data_list.append(data)
        except: traceback.print_exc()

    if force_report_reason and report_data_list:
        send_summary_report(report_data_list, force_report_reason)
        
    db.log_system_run("SUCCESS", "V6.2 Cycle Done")

if __name__ == "__main__":
    run_monitor()