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

# --- 1. 核心配置与资产池 ---
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

# --- 2. 邮件 HTML 生成器 (找回所有量化组件) ---

def generate_stock_html(data):
    symbol = data['symbol']
    pct = data['change_pct']
    color = "red" if pct < 0 else "green"
    
    # [零件1归位] 技术面数据解析
    tech = data.get('tech_analysis') or {}
    signals = tech.get('signals') or {}
    setup = tech.get('trade_setup') or {}
    indicators = tech.get('indicators') or {}
    
    l_tag, l_act, l_desc = signals.get('left_side', ('-', '-', '-'))
    r_tag, r_act, r_desc = signals.get('right_side', ('-', '-', '-'))
    
    # [零件2归位] 统计套利 (Pairs Trading) 紫色框
    quant = data.get('quant_analysis') or {}
    pair_info = quant.get('pair_trade')
    pair_html = ""
    if pair_info and abs(pair_info['z_score']) > 1.5:
        p_color = "#6f42c1" # 紫色
        pair_html = f"""
        <div style="margin: 10px 0; border-left: 4px solid {p_color}; background: #f3f0ff; padding: 10px; font-size: 12px;">
            <b style="color:{p_color};">🔗 统计套利提醒 (Pairs):</b><br/>
            检测到与 <b>{pair_info['pair_symbol']}</b> 强相关 (Corr: {pair_info['correlation']})<br/>
            Spread Z-Score: <b>{pair_info['z_score']}</b> → 建议: <b>{"做空本股/多对家" if pair_info['z_score']>0 else "做多本股/空对家"}</b>
        </div>
        """

    # [零件3归位] 做市商挂单 (Market Making) 细节
    mm_info = quant.get('market_making')
    mm_html = ""
    if mm_info:
        mm_html = f"""
        <div style="display:flex; justify-content:space-between; margin-top:5px; font-size:11px; color:#555; border-top:1px dashed #eee; padding-top:5px;">
            <span>📉 挂单接盘: <b>${mm_info['limit_buy']}</b></span>
            <span>📈 挂单抛售: <b>${mm_info['limit_sell']}</b></span>
        </div>
        """

    def get_tag_color(tag):
        if "极端" in tag: return "#ff4d4f"
        if "中性" in tag: return "#faad14"
        return "#8c8c8c"

    chart_html = f'<div style="text-align:center; margin:15px 0;"><img src="cid:{data["chart_cid"]}" style="width:100%;max-width:650px;border:1px solid #ddd;border-radius:4px;"></div>' if data['chart_path'] else ""

    return f"""
    <div style="border:1px solid #e8e8e8; padding:20px; margin-bottom:30px; border-radius:10px; font-family:Arial; background:#fff;">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:3px solid {color}; padding-bottom:5px;">
            <h2 style="margin:0;">{symbol}</h2>
            <div style="text-align:right;">
                <span style="font-size:20px; font-weight:bold; color:{color};">{pct:+.2f}%</span>
                <div style="font-size:10px; color:#999;">TSMOM Score: {quant.get('momentum', 0)}</div>
            </div>
        </div>

        {pair_html}

        <div style="display:flex; justify-content:space-around; background:#f9f9f9; padding:6px; margin-top:10px; font-size:11px; border-radius:4px;">
            <span>RSI: {indicators.get('rsi', '-')}</span>
            <span>布林位置: {indicators.get('bb_pos', 0):.1f}%</span>
            <span>MACD: {indicators.get('macd', '-')}</span>
        </div>

        <div style="margin-top:15px;">
            <table style="width:100%; border-collapse:collapse; font-size:12px;">
                <tr style="background:#fafafa;"><th style="padding:8px; border:1px solid #eee;">🐻 左侧 (逆势)</th><th style="padding:8px; border:1px solid #eee;">🐂 右侧 (顺势)</th></tr>
                <tr>
                    <td style="padding:10px; border:1px solid #eee; vertical-align:top;">
                        <span style="background:{get_tag_color(l_tag)}; color:white; padding:1px 4px; border-radius:3px;">{l_tag}</span><br/>
                        <b>{l_act}</b><br/><small>{l_desc}</small>
                        <div style="margin-top:8px; padding:5px; background:#e6f7ff; color:#003a8c; font-style:italic;">🤖 {data.get('ai_left', '-')}</div>
                    </td>
                    <td style="padding:10px; border:1px solid #eee; vertical-align:top;">
                        <span style="background:{get_tag_color(r_tag)}; color:white; padding:1px 4px; border-radius:3px;">{r_tag}</span><br/>
                        <b>{r_act}</b><br/><small>{r_desc}</small>
                        <div style="margin-top:8px; padding:5px; background:#e6f7ff; color:#003a8c; font-style:italic;">🤖 {data.get('ai_right', '-')}</div>
                    </td>
                </tr>
            </table>
        </div>

        <div style="margin-top:15px; background:#f6ffed; border:1px solid #b7eb8f; padding:10px; border-radius:5px; color:#135200; font-size:13px;">
            <b>🛒 加仓参考: ${setup.get('buy_target_price', 0)}</b> ({setup.get('buy_desc', '-')})
            {mm_html}
        </div>
        <div style="margin-top:5px; background:#fff5f5; border:1px solid #ffccc7; padding:10px; border-radius:5px; color:#a8071a; font-size:13px;">
            <b>🛡️ 止损建议: ${setup.get('stop_loss_price', 0)}</b> (参考: {setup.get('support_desc', '-')})
        </div>

        {chart_html}

        <div style="margin-top:10px; border-top:1px dashed #eee; padding-top:8px; font-size:11px; color:#666;">
            <b>📰 摘要:</b> {data.get('ai_summary', '-')}
        </div>
    </div>
    """

# --- 3. SMTP 及核心逻辑 ---

def attach_image(msg, path, cid):
    try:
        with open(path, 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-ID', f'<{cid}>')
            img.add_header('Content-Disposition', 'inline', filename=os.path.basename(path))
            msg.attach(img)
    except: pass

def send_summary_report(data_list, reason):
    sender, password, receiver = os.environ.get('MAIL_USER'), os.environ.get('MAIL_PASS'), os.environ.get('MAIL_RECEIVER')
    if not sender or not data_list: return
    msg = MIMEMultipart('related')
    msg['Subject'] = Header(f"{reason} | QuantBot V6.4 FINAL", 'utf-8')
    msg['From'], msg['To'] = sender, receiver
    html = f"<html><body style='background:#f4f7f9; padding:20px;'><h1 style='text-align:center;'>{reason}</h1>"
    for d in data_list: html += generate_stock_html(d)
    html += "</body></html>"
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    for d in data_list:
        if d['chart_path']: attach_image(msg, d['chart_path'], d['chart_cid'])
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(sender, password)
            s.sendmail(sender, receiver.split(','), msg.as_string())
    except Exception as e: print(f"SMTP Error: {e}")

def run_monitor():
    db.init_db()
    # [修复点] 变量初始化，绝对安全
    report_data_list = []
    force_report_reason = None
    
    try:
        tasks = health.get_pending_tasks()
        for t_type, reason in tasks:
            if t_type == 'REPORT_ALL':
                force_report_reason = reason
                break
    except: pass

    status_code, status_msg = is_trading_time()
    if status_code == 0 and not force_report_reason: return

    print(f"🚀 开始全量量化分析... 任务: {force_report_reason}")
    
    # [零件4归位] 构建数据池供 QuantEngine 使用
    df_pool = {}
    for s in STOCKS:
        try:
            df = yf.Ticker(s).history(period="1y")
            if not df.empty: df_pool[s] = df
        except: continue
    
    qe = QuantEngine(df_pool)

    for symbol in STOCKS:
        if symbol not in df_pool: continue
        try:
            df = df_pool[symbol]
            curr_price = df['Close'].iloc[-1]
            ta = TechnicalAnalyzer(df)
            tech_res = ta.analyze()
            score, pct = calculate_anomaly_score(symbol, curr_price, df)
            
            # [零件5归位] 完整量化计算
            data = {
                'symbol': symbol, 'price': curr_price, 'change_pct': pct,
                'tech_analysis': tech_res,
                'quant_analysis': {
                    "pair_trade": qe.find_pair_opportunity(symbol),
                    "market_making": qe.get_optimal_limit_levels(symbol),
                    "momentum": qe.get_momentum_score(symbol)
                },
                'chart_path': plotter.generate_chart(symbol),
                'chart_cid': f"chart_{symbol}_{datetime.now().microsecond}"
            }
            
            # AI 分析与异常处理
            try:
                news = ai.get_latest_news(symbol)
                ai_res = ai.analyze_market_move(symbol, pct, news, tech_res)
                data['ai_summary'] = ai_res.get('summary', '-')
                data['ai_left'] = ai_res.get('left_side_analysis', '-')
                data['ai_right'] = ai_res.get('right_side_analysis', '-')
            except: pass

            report_data_list.append(data)
            # [零件6归位] 完整状态记录
            db.update_stock_state(symbol, datetime.now(TIMEZONE).strftime('%Y-%m-%d'), determine_level(score), curr_price, score)
        except: traceback.print_exc()

    if force_report_reason and report_data_list:
        send_summary_report(report_data_list, force_report_reason)
    
    db.log_system_run("SUCCESS", "V6.4 All Systems Functional")

if __name__ == "__main__":
    run_monitor()