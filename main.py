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

# --- 核心配置 ---
STOCKS = ['NVDA', 'AAPL', 'TSLA', 'AMD', 'MSFT', 'META', 'GOOGL']
TIMEZONE = pytz.timezone('US/Eastern')

# 状态定义
LEVEL_NORMAL = 0
LEVEL_NOTICE = 1   
LEVEL_WARNING = 2  
LEVEL_CRITICAL = 3 

def is_trading_time():
    """交易时间检查"""
    now = datetime.now(TIMEZONE)
    if now.weekday() >= 5: return 0, "周末休市"
    current_time = now.time()
    if current_time < time(9, 30): return 1, "盘前时段"
    elif current_time > time(16, 0): return 1, "盘后时段"
    return 2, "盘中交易"

def get_valuation_data(symbol):
    """获取估值数据"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "pe": info.get('trailingPE'),
            "f_pe": info.get('forwardPE'),
            "peg": info.get('pegRatio'),
            "pb": info.get('priceToBook'),
            "low_52": info.get('fiftyTwoWeekLow'),
            "high_52": info.get('fiftyTwoWeekHigh'),
            "current": info.get('currentPrice') or info.get('regularMarketPrice')
        }
    except:
        return None

def calculate_anomaly_score(symbol, current_price):
    """计算异常分"""
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
    except:
        return 0.0, 0.0

def determine_level(score):
    if score >= 4.5: return LEVEL_CRITICAL
    if score >= 3.0: return LEVEL_WARNING
    if score >= 2.0: return LEVEL_NOTICE
    return LEVEL_NORMAL

# --- 统一的邮件发送函数 (可处理报警 或 强制报告) ---
def send_email_report(symbol, current_price, change_pct, score, level, is_alert=False, report_reason=None):
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver_env = os.environ.get('MAIL_RECEIVER')
    if not sender: return
    receivers = receiver_env.split(',') if ',' in receiver_env else [receiver_env]
    
    # 1. 抓取新闻
    news = ai.get_latest_news(symbol)
    
    # 2. 调用 AI 分析
    # 如果是强制报告，提示词稍微温和一点；如果是报警，提示词紧急一点
    analysis = {}
    try:
        # 这里我们在 ai.py 内部并没有区分 prompt，但可以通过“change_pct”的大小传达信息
        # 未来可以优化 ai.py 接受 extra_instruction
        analysis = ai.analyze_market_move(symbol, change_pct, news)
        if not is_alert and report_reason:
             # 如果只是定时报告且波动不大，手动覆盖 AI 的“无消息”摘要，避免尴尬
             if abs(change_pct) < 1.0 and analysis.get('category') == '无消息':
                 analysis['summary'] = f"当前走势平稳，{report_reason}。"
    except:
        analysis = {"summary": "AI服务暂时不可用", "category": "系统错误"}

    # 3. 估值数据
    val = get_valuation_data(symbol)
    val_html = ""
    if val:
        peg = val['peg']
        peg_eval = "✅低估" if peg and peg < 1.0 else ("❌高估" if peg and peg > 2.0 else "合理")
        
        # 计算52周位置
        pos_pct = 50.0
        if val['high_52'] and val['low_52'] and val['current'] and val['high_52'] != val['low_52']:
            pos_pct = ((val['current'] - val['low_52']) / (val['high_52'] - val['low_52'])) * 100
            
        val_html = f"""
        <div style="background-color: #f0f8ff; padding: 10px; border-radius: 5px; margin: 10px 0;">
            <p><strong>📊 估值数据:</strong></p>
            <table style="width: 100%; font-size: 13px;">
                <tr><td>PE(静): {val['pe']}</td><td>PEG: {val['peg']} ({peg_eval})</td></tr>
                <tr><td colspan="2">52周位置: <span style="color: {'green' if pos_pct<20 else 'red' if pos_pct>80 else 'black'}">{pos_pct:.1f}%</span></td></tr>
            </table>
        </div>
        """

    # 4. 生成K线图
    chart_path = plotter.generate_chart(symbol)
    chart_html = f'<div style="text-align: center;"><img src="cid:chart_image" style="width: 100%; max-width: 600px;"></div>' if chart_path else ""

    # 5. 构建邮件
    msg = MIMEMultipart()
    
    if is_alert:
        level_tags = {LEVEL_NOTICE: "🟡", LEVEL_WARNING: "🟠", LEVEL_CRITICAL: "🔴"}
        subject = f"{level_tags.get(level)}报警：{symbol} {change_pct:+.2f}% | {analysis.get('category')}"
        title_color = "red" if change_pct < 0 else "green"
        header_text = f"{symbol} 异常波动报警 (Level {level})"
    else:
        # 定时报告模式
        subject = f"{report_reason}：{symbol} {change_pct:+.2f}% | 状态分析"
        title_color = "#333"
        header_text = f"{symbol} 市场状态报告 - {report_reason}"

    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = sender
    msg['To'] = ",".join(receivers)

    content = f"""
    <html>
    <body>
        <h2 style="color: {title_color}; border-bottom: 2px solid #eee;">{header_text}</h2>
        <p><strong>现价: ${current_price:.2f}</strong> (<span style="color:{'red' if change_pct < 0 else 'green'}">{change_pct:+.2f}%</span>)</p>
        
        {val_html}
        {chart_html}
        
        <div style="background-color: #fafafa; padding: 15px; margin-top: 15px; border-left: 4px solid #007bff;">
            <h3>🧠 AI 状态分析</h3>
            <p><strong>摘要:</strong> {analysis.get('summary')}</p>
            <p><strong>分类:</strong> {analysis.get('category')} | <strong>风险:</strong> {analysis.get('risk_level')}</p>
            <p><strong>建议:</strong> {analysis.get('action_suggestion')}</p>
        </div>
        
        <h4>📰 最新资讯</h4>
        <ul>{''.join([f'<li>{n}</li>' for n in news[:3]])}</ul>
        
        <p style="color: gray; font-size: 10px;">Generated by QuantBot at {datetime.now(TIMEZONE).strftime('%H:%M ET')}</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(content, 'html', 'utf-8'))

    if chart_path:
        with open(chart_path, 'rb') as f:
            mime_img = MIMEImage(f.read())
            mime_img.add_header('Content-ID', '<chart_image>')
            msg.attach(mime_img)
        os.remove(chart_path)

    try:
        smtp_obj = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, receivers, msg.as_string())
        smtp_obj.quit()
        print(f"✅ 报告已发送: {symbol} ({'报警' if is_alert else '报告'})")
    except Exception as e:
        print(f"❌ 发送失败: {e}")

def run_monitor():
    db.init_db()
    
    # 1. 获取调度任务 (health.py 负责判断是否需要发报告)
    # 返回格式: [('REPORT_ALL', '启动报告'), ...]
    tasks = []
    try:
        tasks = health.get_pending_tasks()
    except Exception as e:
        print(f"⚠️ 调度检查失败: {e}")
        traceback.print_exc()

    # 检查是否有“全员报告”任务
    force_report_reason = None
    for task_type, reason in tasks:
        if task_type == 'REPORT_ALL':
            force_report_reason = reason
            print(f"📋 触发全员报告任务: {reason}")
            break

    # 2. 市场状态检查
    status_code, status_msg = is_trading_time()
    print(f"🚀 启动监控 - {status_msg}")

    # 如果市场休市，但有强制报告任务（比如 20:00 的晚报），依然要执行
    # 如果没有任务且休市，则退出
    if status_code == 0 and not force_report_reason:
        print("😴 市场休眠且无定时任务...")
        return

    today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')

    for symbol in STOCKS:
        try:
            # 获取数据
            ticker = yf.Ticker(symbol)
            try:
                current_price = ticker.fast_info['last_price']
            except:
                hist = ticker.history(period='1d')
                if hist.empty: continue
                current_price = hist['Close'].iloc[-1]

            score, change_pct = calculate_anomaly_score(symbol, current_price)
            current_level = determine_level(score)
            
            # --- 逻辑分叉 ---
            
            # 路径 A: 强制报告 (定时任务)
            if force_report_reason:
                print(f"📤 发送定时报告: {symbol}")
                send_email_report(symbol, current_price, change_pct, score, current_level, is_alert=False, report_reason=force_report_reason)
            
            # 路径 B: 异常报警 (原有逻辑)
            else:
                prev_state = db.get_stock_state(symbol)
                prev_level = prev_state['level'] if prev_state else 0
                
                is_level_up = (current_level > prev_level)
                is_critical = (current_level == LEVEL_CRITICAL)
                
                # 只有在市场开启时才报警
                if status_code != 0:
                    if (is_level_up and current_level >= LEVEL_NOTICE) or is_critical:
                        print(f"🔔 触发异常报警: {symbol}")
                        send_email_report(symbol, current_price, change_pct, score, current_level, is_alert