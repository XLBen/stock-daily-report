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

# --- 📧 邮件发送模块 ---

def send_single_alert(data):
    """发送单只股票的报警邮件 (仅用于异常报警)"""
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver_env = os.environ.get('MAIL_RECEIVER')
    if not sender: return
    receivers = receiver_env.split(',') if ',' in receiver_env else [receiver_env]

    symbol = data['symbol']
    change_pct = data['change_pct']
    level = data['level']
    
    # 标题
    level_tags = {LEVEL_NOTICE: "🟡", LEVEL_WARNING: "🟠", LEVEL_CRITICAL: "🔴"}
    subject = f"{level_tags.get(level)}报警：{symbol} {change_pct:+.2f}% | {data['ai_category']}"
    
    msg = MIMEMultipart()
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = sender
    msg['To'] = ",".join(receivers)

    # 生成正文 HTML
    body_html = generate_stock_html(data, is_summary=False)
    msg.attach(MIMEText(body_html, 'html', 'utf-8'))

    # 嵌入图片
    if data['chart_path']:
        attach_image(msg, data['chart_path'], data['chart_cid'])

    send_smtp(sender, password, receivers, msg)
    print(f"🔔 单独报警已发送: {symbol}")

def send_summary_report(data_list, report_reason):
    """发送汇总报告邮件 (包含所有股票)"""
    if not data_list: return
    
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver_env = os.environ.get('MAIL_RECEIVER')
    if not sender: return
    receivers = receiver_env.split(',') if ',' in receiver_env else [receiver_env]

    # 汇总标题
    # 挑出涨跌幅最大的作为标题亮点
    sorted_stocks = sorted(data_list, key=lambda x: abs(x['change_pct']), reverse=True)
    top_stock = sorted_stocks[0]
    subject = f"{report_reason}：{top_stock['symbol']} {top_stock['change_pct']:+.2f}% 等{len(data_list)}只 | 市场概览"

    msg = MIMEMultipart()
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = sender
    msg['To'] = ",".join(receivers)

    # 拼接所有股票的 HTML
    full_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
        <h2 style="text-align: center; color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px;">
            📋 {report_reason}
        </h2>
        <p style="text-align: center; color: gray; font-size: 12px;">
            生成时间: {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S ET')}
        </p>
    """
    
    for data in data_list:
        full_content += generate_stock_html(data, is_summary=True)
        full_content += "<hr style='border: 0; border-top: 4px solid #eee; margin: 30px 0;' />"
        
    full_content += "</body></html>"
    msg.attach(MIMEText(full_content, 'html', 'utf-8'))

    # 批量嵌入所有图片
    for data in data_list:
        if data['chart_path']:
            attach_image(msg, data['chart_path'], data['chart_cid'])

    send_smtp(sender, password, receivers, msg)
    print(f"✅ 汇总报告已发送: {report_reason}")

# --- 🛠 辅助函数 ---

def generate_stock_html(data, is_summary=False):
    """生成单只股票的 HTML 卡片"""
    symbol = data['symbol']
    pct = data['change_pct']
    color = "red" if pct < 0 else "green"
    
    # 估值部分
    val_html = ""
    val = data['valuation']
    if val:
        peg_eval = "✅低估" if val['peg'] and val['peg'] < 1.0 else ("❌高估" if val['peg'] and val['peg'] > 2.0 else "合理")
        pos_pct = 50.0
        if val['high_52'] and val['low_52'] and val['high_52'] != val['low_52']:
            pos_pct = ((val['current'] - val['low_52']) / (val['high_52'] - val['low_52'])) * 100
        
        val_html = f"""
        <div style="background-color: #f8f9fa; padding: 10px; border-radius: 5px; font-size: 13px; margin: 10px 0;">
            <table style="width: 100%;">
                <tr><td>PE(静): {val['pe']}</td><td>PEG: {val['peg']} ({peg_eval})</td></tr>
                <tr><td colspan="2">52周: <span style="color: {'green' if pos_pct<20 else 'red' if pos_pct>80 else 'black'}">{pos_pct:.1f}%</span> (Low ${val['low_52']} - High ${val['high_52']})</td></tr>
            </table>
        </div>
        """

    # 图片部分 (注意 cid 的引用)
    chart_html = ""
    if data['chart_path']:
        chart_html = f'<div style="text-align: center; margin: 10px 0;"><img src="cid:{data["chart_cid"]}" style="width: 100%; max-width: 600px; border: 1px solid #ddd;"></div>'
    else:
        chart_html = f'<p style="color:red; text-align:center;">[图表生成失败]</p>'

    return f"""
    <div style="margin-bottom: 20px;">
        <h3 style="margin: 0;">
            {symbol} <span style="color: {color}; font-size: 18px;">{pct:+.2f}%</span> 
            <span style="font-size: 14px; color: #666; font-weight: normal;">(${data['price']:.2f})</span>
        </h3>
        
        {val_html}
        {chart_html}
        
        <div style="background-color: #eef6fc; padding: 10px; border-left: 3px solid #007bff; font-size: 14px;">
            <strong>🧠 AI:</strong> {data['ai_summary']}
        </div>
        
        <div style="font-size: 12px; color: #666; margin-top: 5px;">
            <strong>📰 新闻:</strong> {' | '.join(data['news'][:2])}
        </div>
    </div>
    """

def attach_image(msg, path, cid):
    """将图片作为附件嵌入邮件"""
    try:
        with open(path, 'rb') as f:
            mime_img = MIMEImage(f.read())
            # 这里的 cid 必须要带尖括号 <>
            mime_img.add_header('Content-ID', f'<{cid}>')
            msg.attach(mime_img)
        # 发送完如果需要可以删除，或者最后统一删除
    except Exception as e:
        print(f"⚠️ 图片嵌入失败 {path}: {e}")

def send_smtp(sender, password, receivers, msg):
    try:
        smtp_obj = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, receivers, msg.as_string())
        smtp_obj.quit()
    except Exception as e:
        print(f"❌ SMTP 发送失败: {e}")

# --- 🚀 主程序 ---

def run_monitor():
    db.init_db()
    
    # 1. 获取调度任务
    tasks = []
    try:
        tasks = health.get_pending_tasks()
    except:
        traceback.print_exc()

    force_report_reason = None
    for task_type, reason in tasks:
        if task_type == 'REPORT_ALL':
            force_report_reason = reason
            print(f"📋 触发全员报告任务: {reason}")
            break

    status_code, status_msg = is_trading_time()
    print(f"🚀 启动监控 - {status_msg}")

    # 如果休市且无报告任务，退出
    if status_code == 0 and not force_report_reason:
        print("😴 休市且无任务...")
        return

    today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
    report_data_list = [] # 用于收集所有股票数据

    for symbol in STOCKS:
        try:
            # A. 获取数据
            ticker = yf.Ticker(symbol)
            try:
                current_price = ticker.fast_info['last_price']
            except:
                hist = ticker.history(period='1d')
                if hist.empty: 
                    print(f"⚠️ {symbol} 无数据")
                    continue
                current_price = hist['Close'].iloc[-1]

            score, change_pct = calculate_anomaly_score(symbol, current_price)
            current_level = determine_level(score)
            
            # B. 准备数据包
            stock_data = {
                'symbol': symbol,
                'price': current_price,
                'change_pct': change_pct,
                'level': current_level,
                'score': score,
                'valuation': get_valuation_data(symbol),
                'news': ai.get_latest_news(symbol),
                # 预留 AI 字段
                'ai_summary': 'AI分析中...',
                'ai_category': '未知',
                # 画图 (带唯一ID)
                'chart_path': plotter.generate_chart(symbol),
                'chart_cid': f"chart_{symbol}_{datetime.now().strftime('%H%M%S')}" # 唯一CID
            }
            
            # C. 调用 AI (如果需要)
            # 策略：如果是强制报告，或者有报警，都调 AI
            if force_report_reason or current_level >= LEVEL_WARNING or abs(change_pct) > 2.0:
                try:
                    analysis = ai.analyze_market_move(symbol, change_pct, stock_data['news'])
                    stock_data['ai_summary'] = analysis.get('summary', '无')
                    stock_data['ai_category'] = analysis.get('category', '常规')
                except:
                    stock_data['ai_summary'] = "AI 服务不可用"
            else:
                stock_data['ai_summary'] = "波动较小，维持关注"

            # D. 逻辑分叉
            
            # 1. 异常报警：立即单独发！
            # 只有在开盘期间，且级别够高时才发
            if status_code != 0:
                prev_state = db.get_stock_state(symbol)
                prev_level = prev_state['level'] if prev_state else 0
                is_level_up = (current_level > prev_level)
                
                if (is_level_up and current_level >= LEVEL_NOTICE) or current_level == LEVEL_CRITICAL:
                    print(f"🔔 触发单独报警: {symbol}")
                    send_single_alert(stock_data)

            # 2. 收集数据用于汇总报告
            report_data_list.append(stock_data)
            
            # 更新数据库
            db.update_stock_state(symbol, today_str, current_level, current_price, score)

        except Exception as e:
            print(f"❌ 处理 {symbol} 失败: {e}")
            traceback.print_exc()

    # E. 循环结束，发送汇总报告
    if force_report_reason and report_data_list:
        print(f"📤 正在生成汇总报告 ({len(report_data_list)}只股票)...")
        send_summary_report(report_data_list, force_report_reason)
        
    # 清理临时图片
    for data in report_data_list:
        if data.get('chart_path') and os.path.exists(data['chart_path']):
            try:
                os.remove(data['chart_path'])
            except:
                pass

    db.log_system_run("SUCCESS", "Cycle Completed")

if __name__ == "__main__":
    try:
        run_monitor()
    except Exception as e:
        print(f"❌ 致命错误: {e}")
        exit(1)