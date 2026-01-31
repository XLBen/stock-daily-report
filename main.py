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

STOCKS = ['NVDA', 'AAPL', 'TSLA', 'AMD', 'MSFT', 'META', 'GOOGL']
TIMEZONE = pytz.timezone('US/Eastern')
LEVEL_NORMAL = 0
LEVEL_NOTICE = 1   
LEVEL_WARNING = 2  
LEVEL_CRITICAL = 3 

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
        current_pct = ((current_price - df_hist['Close'].iloc[-2]) / df_hist['Close'].iloc[-2]) * 100
        mad = np.abs(returns - returns.median()).median()
        if mad == 0: mad = 0.001
        score = np.abs((current_pct/100) - returns.median()) / (1.4826 * mad)
        return score, current_pct
    except: return 0.0, 0.0

def determine_level(score):
    if score >= 4.5: return LEVEL_CRITICAL
    if score >= 3.0: return LEVEL_WARNING
    if score >= 2.0: return LEVEL_NOTICE
    return LEVEL_NORMAL

# --- 邮件组件 ---

def generate_stock_html(data, is_summary=False):
    symbol = data['symbol']
    pct = data['change_pct']
    color_pct = "red" if pct < 0 else "green"
    
    tech = data.get('tech_analysis') or {}
    signals = tech.get('signals') or {}
    setup = tech.get('trade_setup') or {}
    
    left_sig = signals.get('left_side', ('-', '-', '-'))
    right_sig = signals.get('right_side', ('-', '-', '-'))
    
    # 这里的 src="cid:..." 必须和 attach_image 里的 Content-ID 对应
    chart_html = ""
    if data['chart_path']:
        chart_html = f'<div style="text-align: center; margin: 15px 0;"><img src="cid:{data["chart_cid"]}" style="width: 100%; max-width: 650px; border: 1px solid #ddd; border-radius: 4px;"></div>'

    ai_summary = data.get('ai_summary', 'AI未返回')
    ai_left = data.get('ai_left', '-')
    ai_right = data.get('ai_right', '-')
    
    return f"""
    <div style="margin-bottom: 30px; border: 1px solid #e0e0e0; padding: 20px; border-radius: 8px; background-color: #fff; font-family: Arial, sans-serif;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid {color_pct}; padding-bottom: 8px;">
            <h2 style="margin: 0; color: #222;">{symbol}</h2>
            <div style="text-align: right;">
                <span style="font-size: 22px; font-weight: bold; color: {color_pct};">{pct:+.2f}%</span>
                <span style="font-size: 13px; color: #666;"> ${data['price']:.2f}</span>
            </div>
        </div>

        <div style="margin-top: 15px;">
            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <tr style="background-color: #f8f9fa;">
                    <th style="padding: 10px; text-align: left; width: 50%; border-bottom: 2px solid #ddd;">🐻 左侧 (逆势)</th>
                    <th style="padding: 10px; text-align: left; width: 50%; border-bottom: 2px solid #ddd;">🐂 右侧 (顺势)</th>
                </tr>
                <tr>
                    <td style="padding: 10px; border-right: 1px solid #eee; vertical-align: top;">
                        <strong style="font-size: 14px;">{left_sig[0]} - {left_sig[1]}</strong>
                        <p style="margin: 5px 0; color: #555; font-size: 12px;">{left_sig[2]}</p>
                        <div style="background-color: #e3f2fd; padding: 6px; border-radius: 4px; font-style: italic; color: #0d47a1; margin-top: 5px;">
                            🤖 {ai_left}
                        </div>
                    </td>
                    <td style="padding: 10px; vertical-align: top;">
                        <strong style="font-size: 14px;">{right_sig[0]} - {right_sig[1]}</strong>
                        <p style="margin: 5px 0; color: #555; font-size: 12px;">{right_sig[2]}</p>
                        <div style="background-color: #e3f2fd; padding: 6px; border-radius: 4px; font-style: italic; color: #0d47a1; margin-top: 5px;">
                            🤖 {ai_right}
                        </div>
                    </td>
                </tr>
            </table>
        </div>

        <div style="margin-top: 15px; background-color: #f0fff4; border: 1px solid #c6f6d5; padding: 10px; border-radius: 5px; color: #276749; font-size: 13px;">
            <strong>🛒 机会/加仓参考:</strong> 关注 <strong>${setup.get('buy_target_price', 0)}</strong> ({setup.get('buy_desc', '-')})
        </div>

        <div style="margin-top: 8px; background-color: #fff5f5; border: 1px solid #fed7d7; padding: 10px; border-radius: 5px; color: #c53030; font-size: 13px;">
            <strong>🛡️ 风险/止损参考:</strong> 跌破 <strong>${setup.get('stop_loss_price', 0)}</strong> (支撑: {setup.get('support_desc', '-')})
        </div>

        {chart_html}

        <div style="font-size: 12px; color: #666; margin-top: 10px; border-top: 1px dashed #ccc; padding-top: 8px;">
            <strong>📰 摘要:</strong> {ai_summary}
        </div>
    </div>
    """

# 🔥 核心修复：图片附件处理
def attach_image(msg, path, cid):
    try:
        with open(path, 'rb') as f:
            img_data = f.read()
            mime_img = MIMEImage(img_data, _subtype="png")
            # 关键1：Content-ID 必须有尖括号
            mime_img.add_header('Content-ID', f'<{cid}>')
            # 关键2：Content-Disposition: inline 强制内嵌显示，而不是作为附件文件
            mime_img.add_header('Content-Disposition', 'inline', filename=os.path.basename(path))
            msg.attach(mime_img)
    except Exception as e:
        print(f"⚠️ 图片嵌入失败 {path}: {e}")

def send_smtp(sender, password, receivers, msg):
    try:
        s = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        s.login(sender, password)
        s.sendmail(sender, receivers, msg.as_string())
        s.quit()
    except Exception as e: print(f"❌ SMTP Error: {e}")

def send_summary_report(data_list, reason):
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver_env = os.environ.get('MAIL_RECEIVER')
    if not sender: return
    receivers = receiver_env.split(',') if ',' in receiver_env else [receiver_env]
    
    data_list.sort(key=lambda x: "极端" not in str(x.get('tech_analysis')), reverse=False)

    msg = MIMEMultipart('related') # 使用 related 类型，更有利于内嵌图片
    msg['Subject'] = Header(f"{reason} | QuantBot V5.2", 'utf-8')
    msg['From'] = sender
    msg['To'] = ",".join(receivers)

    html_body = f"""<html><body style="max-width:800px; margin:0 auto; background-color: #f9f9f9; padding: 20px;">
    <h2 style="text-align:center; color:#2c3e50;">🤖 QuantBot V5.2</h2>
    <p style="text-align:center; color:gray; font-size:12px;">{reason}</p>"""
    for d in data_list: html_body += generate_stock_html(d)
    html_body += "</body></html>"
    
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    
    # 附加图片
    for d in data_list: 
        if d['chart_path']: attach_image(msg, d['chart_path'], d['chart_cid'])

    send_smtp(sender, password, receivers, msg)
    print("✅ 邮件已发送")

def run_monitor():
    db.init_db()
    TEST_MODE = True 
    
    force_reason = None
    if TEST_MODE:
        force_reason = "🚀 测试周全程监控报告"
    elif datetime.now(TIMEZONE).weekday() >= 5:
        force_reason = "🚀 V5.2 调试报告"
    # --- 修改结束 ---

    # 这里的逻辑会因为 force_reason 有值而跳过 return
    status_code, _ = is_trading_time()
    if status_code == 0 and not force_reason:
        print("😴 休市...")
        return

    today = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
    report_data = []

    for symbol in STOCKS:
        try:
            print(f"📊 {symbol}...")
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
                'news': ai.get_latest_news(symbol),
                'chart_path': plotter.generate_chart(symbol),
                'chart_cid': f"chart_{symbol}_{datetime.now().strftime('%H%M%S')}" # 唯一ID
            }
            
            print(f"🧠 AI: {symbol}...")
            # 现在传4个参数不会报错了
            if not os.environ.get("LLM_BASE_URL"): os.environ["LLM_BASE_URL"] = "https://api.deepseek.com"
            
            ai_res = ai.analyze_market_move(symbol, pct, data['news'], tech_res)
            
            data['ai_summary'] = ai_res.get('summary', 'AI空数据')
            data['ai_left'] = ai_res.get('left_side_analysis', '-')
            data['ai_right'] = ai_res.get('right_side_analysis', '-')
            
            report_data.append(data)
            db.update_stock_state(symbol, today, determine_level(score), curr_price, score)
        except Exception as e:
            traceback.print_exc()

    if force_reason and report_data:
        send_summary_report(report_data, force_reason)
        
    for d in report_data:
        if d['chart_path'] and os.path.exists(d['chart_path']):
            try: os.remove(d['chart_path'])
            except: pass

    db.log_system_run("SUCCESS", "Cycle Completed")

if __name__ == "__main__":
    run_monitor()