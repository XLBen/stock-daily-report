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

# --- 核心配置 ---
# 剔除报错的 XAUUSD，确保流程通畅
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

def generate_stock_html(data):
    symbol = data['symbol']
    pct = data['change_pct']
    color = "red" if pct < 0 else "green"
    tech = data.get('tech_analysis', {})
    sigs = tech.get('signals', {})
    setup = tech.get('trade_setup', {})

    chart_html = f'<div style="text-align:center; margin:15px 0;"><img src="cid:{data["chart_cid"]}" style="width:100%;max-width:600px;border:1px solid #ddd;"></div>' if data['chart_path'] else ""

    return f"""
    <div style="border:1px solid #eee; padding:20px; margin-bottom:30px; border-radius:8px; font-family:Arial;">
        <div style="border-bottom:2px solid {color}; padding-bottom:5px;">
            <h2 style="margin:0;">{symbol} <span style="color:{color};">{pct:+.2f}%</span></h2>
        </div>
        <div style="margin-top:10px;">
            <table style="width:100%; font-size:13px; border-collapse:collapse;">
                <tr style="background:#f8f9fa;"><th>🐻 左侧 (逆势)</th><th>🐂 右侧 (顺势)</th></tr>
                <tr>
                    <td style="padding:10px; border-right:1px solid #eee;">
                        <b>{sigs.get('left_side', '-')[1]}</b><br/>
                        <div style="color:#0056b3; font-style:italic; margin-top:5px;">🤖 {data.get('ai_left', '-')}</div>
                    </td>
                    <td style="padding:10px;">
                        <b>{sigs.get('right_side', '-')[1]}</b><br/>
                        <div style="color:#0056b3; font-style:italic; margin-top:5px;">🤖 {data.get('ai_right', '-')}</div>
                    </td>
                </tr>
            </table>
        </div>
        <div style="background:#f0fff4; padding:8px; margin-top:10px; border-radius:4px; color:#276749;">
            🛒 机会/加仓参考: <b>${setup.get('buy_target_price', 0)}</b> ({setup.get('buy_desc', '-')})
        </div>
        <div style="background:#fff5f5; padding:8px; margin-top:5px; border-radius:4px; color:#c53030;">
            🛡️ 风险/止损参考: 跌破 <b>${setup.get('stop_loss_price', 0)}</b>
        </div>
        {chart_html}
        <div style="font-size:12px; color:#666; border-top:1px dashed #ccc; padding-top:10px;">
            <b>📰 摘要:</b> {data.get('ai_summary', '-')}
        </div>
    </div>
    """

def attach_image(msg, path, cid):
    try:
        with open(path, 'rb') as f:
            img = MIMEImage(f.read(), _subtype="png")
            img.add_header('Content-ID', f'<{cid}>')
            img.add_header('Content-Disposition', 'inline', filename=os.path.basename(path))
            msg.attach(img)
    except Exception as e:
        print(f"⚠️ 图片嵌入失败: {e}")

def send_summary_report(data_list, reason):
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver = os.environ.get('MAIL_RECEIVER')
    if not sender or not data_list: return

    msg = MIMEMultipart('related')
    msg['Subject'] = Header(f"{reason} | QuantBot V5.2 修复版", 'utf-8')
    msg['From'] = sender
    msg['To'] = receiver

    html_body = f"<html><body><h1 style='text-align:center; color:#333;'>{reason}</h1>"
    for d in data_list: html_body += generate_stock_html(d)
    html_body += "</body></html>"
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    for d in data_list:
        if d['chart_path']: attach_image(msg, d['chart_path'], d['chart_cid'])

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(sender, password)
            s.sendmail(sender, receiver.split(','), msg.as_string())
    except Exception as e: print(f"❌ SMTP 发送失败: {e}")

def run_monitor():
    db.init_db()
    
    # 🔥 核心修复：预先定义变量，防止 NameError
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
        print(f"😴 {status_msg}，无任务。")
        return

    print(f"🚀 开始分析流程... 任务类型: {force_report_reason}")
    
    for symbol in STOCKS:
        try:
            print(f"📊 正在处理: {symbol}...")
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="6mo")
            if df.empty: continue
            
            curr_price = df['Close'].iloc[-1]
            ta = TechnicalAnalyzer(df)
            tech_res = ta.analyze()
            score, pct = calculate_anomaly_score(symbol, curr_price, df)
            
            data = {
                'symbol': symbol, 'price': curr_price, 'change_pct': pct,
                'tech_analysis': tech_res,
                'chart_path': plotter.generate_chart(symbol),
                'chart_cid': f"chart_{symbol}_{datetime.now().microsecond}"
            }
            
            # AI 分析部分
            try:
                news = ai.get_latest_news(symbol)
                # 确保这里传入 4 个参数，前提是你的 ai.py 已经按上一轮要求改好了
                ai_res = ai.analyze_market_move(symbol, pct, news, tech_res)
                data['ai_summary'] = ai_res.get('summary', '-')
                data['ai_left'] = ai_res.get('left_side_analysis', '-')
                data['ai_right'] = ai_res.get('right_side_analysis', '-')
            except Exception as e:
                print(f"⚠️ AI 调用失败: {e}")
                data['ai_summary'] = "AI分析不可用"

            report_data_list.append(data)
        except Exception as e:
            print(f"❌ {symbol} 失败: {e}")
            traceback.print_exc()

    if force_report_reason and report_data_list:
        send_summary_report(report_data_list, force_report_reason)
        
    db.log_system_run("SUCCESS", "V5.2 Cycle Done")

if __name__ == "__main__":
    run_monitor()