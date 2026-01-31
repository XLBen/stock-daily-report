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

# --- 📧 邮件 HTML 生成 (重点修改) ---

def generate_stock_html(data, is_summary=False):
    symbol = data['symbol']
    pct = data['change_pct']
    color_pct = "red" if pct < 0 else "green"
    
    tech = data.get('tech_analysis') or {}
    signals = tech.get('signals') or {}
    setup = tech.get('trade_setup') or {} # 获取买卖建议
    
    left_sig = signals.get('left_side', ('-', '-', '-'))
    right_sig = signals.get('right_side', ('-', '-', '-'))
    
    # 图表
    chart_html = ""
    if data['chart_path']:
        chart_html = f'<div style="text-align: center; margin: 10px 0;"><img src="cid:{data["chart_cid"]}" style="width: 100%; max-width: 600px; border: 1px solid #ddd;"></div>'
    else:
        chart_html = f'<p style="color:red; text-align:center;">[图表生成失败]</p>'

    # AI 内容处理 (如果 AI 没返回，显示特定提示)
    ai_summary = data.get('ai_summary', 'AI未返回数据')
    ai_left = data.get('ai_left', '-')
    ai_right = data.get('ai_right', '-')
    
    return f"""
    <div style="margin-bottom: 30px; border: 1px solid #eee; padding: 15px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); font-family: Arial, sans-serif;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid {color_pct}; padding-bottom: 5px;">
            <h2 style="margin: 0; color: #333;">{symbol}</h2>
            <div style="text-align: right;">
                <span style="font-size: 20px; font-weight: bold; color: {color_pct};">{pct:+.2f}%</span>
                <span style="font-size: 12px; color: #888;"> ${data['price']:.2f}</span>
            </div>
        </div>

        <div style="margin-top: 15px;">
            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <tr style="background-color: #f4f4f4;">
                    <th style="padding: 8px; text-align: left; width: 50%;">🐻 左侧 (逆势)</th>
                    <th style="padding: 8px; text-align: left; width: 50%;">🐂 右侧 (顺势)</th>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #eee; vertical-align: top;">
                        <strong>{left_sig[0]} - {left_sig[1]}</strong>
                        <p style="margin: 5px 0; color: #666; font-size: 11px;">{left_sig[2]}</p>
                        <div style="background-color: #f0f8ff; padding: 5px; border-radius: 4px; font-style: italic; color: #0056b3;">
                            🤖 {ai_left}
                        </div>
                    </td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee; vertical-align: top; border-left: 1px solid #eee;">
                        <strong>{right_sig[0]} - {right_sig[1]}</strong>
                        <p style="margin: 5px 0; color: #666; font-size: 11px;">{right_sig[2]}</p>
                        <div style="background-color: #f0f8ff; padding: 5px; border-radius: 4px; font-style: italic; color: #0056b3;">
                            🤖 {ai_right}
                        </div>
                    </td>
                </tr>
            </table>
        </div>

        <div style="margin-top: 10px; background-color: #f0fff4; border: 1px solid #c6f6d5; padding: 10px; border-radius: 5px; color: #2f855a; font-size: 13px;">
            <strong>🛒 机会/加仓参考:</strong><br/>
            关注 <strong>${setup.get('buy_target_price', 0)}</strong> 附近 ({setup.get('buy_desc', '-')})。<br/>
            <span style="font-size: 11px; opacity: 0.8;">逻辑: 支撑位低吸或趋势回踩。</span>
        </div>

        <div style="margin-top: 5px; background-color: #fff5f5; border: 1px solid #fed7d7; padding: 10px; border-radius: 5px; color: #c53030; font-size: 13px;">
            <strong>🛡️ 风险/止损参考:</strong><br/>
            跌破 <strong>${setup.get('stop_loss_price', 0)}</strong> (2倍ATR) 建议止损。<br/>
            <span style="font-size: 11px; opacity: 0.8;">关键支撑: {setup.get('support_desc', '-')}</span>
        </div>

        {chart_html}

        <div style="font-size: 12px; color: #666; margin-top: 5px; border-top: 1px dashed #ccc; padding-top: 5px;">
            <strong>📰 摘要:</strong> {ai_summary}
        </div>
    </div>
    """

def attach_image(msg, path, cid):
    try:
        with open(path, 'rb') as f:
            msg.attach(MIMEImage(f.read(), name=os.path.basename(path), _subtype="png", content_id=f'<{cid}>'))
    except: pass

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
    
    # 排序：极端信号优先
    data_list.sort(key=lambda x: "极端" not in str(x.get('tech_analysis')), reverse=False)

    msg = MIMEMultipart()
    msg['Subject'] = Header(f"{reason} | 量化投顾 V5.1 (UI Upgrade)", 'utf-8')
    msg['From'] = sender
    msg['To'] = ",".join(receivers)

    html = f"""<html><body style="max-width:800px; margin:0 auto;">
    <h2 style="text-align:center; color:#2c3e50;">🤖 QuantBot V5.1</h2>
    <p style="text-align:center; color:gray;">{reason}</p>"""
    for d in data_list: html += generate_stock_html(d)
    html += "</body></html>"
    
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    for d in data_list: 
        if d['chart_path']: attach_image(msg, d['chart_path'], d['chart_cid'])

    send_smtp(sender, password, receivers, msg)
    print("✅ 邮件已发送")

def run_monitor():
    db.init_db()
    
    # 强制调试逻辑
    force_reason = None
    if datetime.now(TIMEZONE).weekday() >= 5: force_reason = "🚀 V5.1 调试报告"
    
    # 正常任务检查
    try:
        tasks = health.get_pending_tasks()
        for t, r in tasks: 
            if t == 'REPORT_ALL': force_reason = r
    except: pass

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
                'chart_cid': f"chart_{symbol}_{datetime.now().strftime('%H%M%S')}"
            }
            
            # AI 调用 (增加详细日志)
            print(f"🧠 AI Thinking: {symbol}...")
            if not os.environ.get("LLM_BASE_URL"): os.environ["LLM_BASE_URL"] = "https://api.deepseek.com"
            
            try:
                ai_res = ai.analyze_market_move(symbol, pct, data['news'], tech_res)
                # 🔥 调试打印：把 AI 返回的原始 JSON 打印出来，看看到底是不是空的
                print(f"🔍 AI Raw Response: {ai_res}") 
                
                data['ai_summary'] = ai_res.get('summary', 'AI数据为空')
                data['ai_left'] = ai_res.get('left_side_analysis', '-')
                data['ai_right'] = ai_res.get('right_side_analysis', '-')
            except Exception as e:
                print(f"❌ AI Error: {e}")
                data['ai_summary'] = f"AI Error: {str(e)}"

            report_data.append(data)
            db.update_stock_state(symbol, today, determine_level(score), curr_price, score)
        except Exception as e:
            traceback.print_exc()

    if force_reason and report_data:
        send_summary_report(report_data, force_reason)

if __name__ == "__main__":
    run_monitor()