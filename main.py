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
import ai      # 引入 AI 模块
import health  # 引入健康监控模块
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
    """真实交易时间检查"""
    now = datetime.now(TIMEZONE)
    if now.weekday() >= 5: return 0, "周末休市"
    current_time = now.time()
    if current_time < time(9, 30): return 1, "盘前时段"
    elif current_time > time(16, 0): return 1, "盘后时段"
    return 2, "盘中交易"

def get_valuation_data(symbol):
    """
    【新增】获取估值数据 (PE, Forward PE, PEG, 52周位置)
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # 获取核心指标
        trailing_pe = info.get('trailingPE')
        forward_pe = info.get('forwardPE')
        peg_ratio = info.get('pegRatio')
        price_to_book = info.get('priceToBook')
        
        # 计算当前价格在 52 周范围内的位置 (0% = 最低, 100% = 最高)
        high_52 = info.get('fiftyTwoWeekHigh')
        low_52 = info.get('fiftyTwoWeekLow')
        current = info.get('currentPrice') or info.get('regularMarketPrice')
        
        position_52w = 0.5 # 默认中间
        if high_52 and low_52 and current and high_52 != low_52:
            position_52w = (current - low_52) / (high_52 - low_52)
            
        return {
            "pe": trailing_pe,
            "f_pe": forward_pe,
            "peg": peg_ratio,
            "pb": price_to_book,
            "pos_52w": position_52w,
            "low_52": low_52,
            "high_52": high_52
        }
    except Exception as e:
        print(f"[{symbol}] 估值数据获取失败: {e}")
        return None

def calculate_anomaly_score(symbol, current_price):
    """核心算法：基于 MAD 的稳健波动率计算"""
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
    
    # 1. AI 分析
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

    # 2. 【新增】获取估值看板
    val = get_valuation_data(symbol)
    val_html = ""
    if val:
        # 简单的估值评价
        peg_eval = "✅低估" if val['peg'] and val['peg'] < 1.0 else ("❌高估" if val['peg'] and val['peg'] > 2.0 else "合理")
        pos_pct = val['pos_52w'] * 100
        
        val_html = f"""
        <div style="background-color: #f0f8ff; padding: 12px; border-radius: 6px; margin: 15px 0; border: 1px solid #cceeff;">
            <p style="margin: 0 0 10px 0;"><strong>📊 估值安全垫分析:</strong></p>
            <table style="width: 100%; font-size: 14px; border-collapse: collapse;">
                <tr>
                    <td style="padding: 4px;">PE (静): <strong>{val['pe'] if val['pe'] else '-'}</strong></td>
                    <td style="padding: 4px;">PE (动): <strong>{val['f_pe'] if val['f_pe'] else '-'}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 4px;">PEG: <strong>{val['peg'] if val['peg'] else '-'} ({peg_eval})</strong></td>
                    <td style="padding: 4px;">PB: <strong>{val['pb'] if val['pb'] else '-'}</strong></td>
                </tr>
                <tr>
                    <td colspan="2" style="padding: 4px; border-top: 1px dashed #ccc; padding-top: 8px;">
                        <strong>52周位置:</strong> 
                        <span style="color: {'green' if pos_pct < 20 else 'red' if pos_pct > 80 else 'black'}">{pos_pct:.1f}%</span> 
                        <br/>
                        <span style="font-size: 11px; color: gray;">(Low ${val['low_52']} ⟷ High ${val['high_52']})</span>
                    </td>
                </tr>
            </table>
        </div>
        """

    level_tags = {LEVEL_NOTICE: "🟡", LEVEL_WARNING: "🟠", LEVEL_CRITICAL: "🔴"}
    color = "red" if change_pct < 0 else "green"
    
    title = f"{level_tags.get(level)}：{symbol} {change_pct:+.2f}% | {analysis.get('category')}"
    
    content = f"""
    <html>
    <body>
        <h2 style="border-bottom: 2px solid {color}; padding-bottom: 5px;">{symbol} 异常波动监控</h2>
        <p style="font-size: 16px;">
            现价: <strong>${price:.2f}</strong> 
            (<span style="color:{color}">{change_pct:+.2f}%</span>)
        </p>
        <p>异常评分: {score:.1f} (Level {level})</p>
        
        {val_html} <hr style="border: 0; border-top: 1px solid #eee;" />
        
        <h3>🧠 AI 归因分析</h3>
        <div style="background-color: #fafafa; padding: 10px; border-left: 4px solid #333;">
            <p><strong>原因:</strong> {analysis.get('summary')}</p>
            <p><strong>分类:</strong> {analysis.get('category')} | <strong>风险:</strong> {analysis.get('risk_level')}</p>
            <p><strong>建议:</strong> {analysis.get('action_suggestion', '暂无')}</p>
        </div>
        
        <hr style="border: 0; border-top: 1px solid #eee;" />
        
        <h3>📰 最新新闻</h3>
        <ul>{''.join([f'<li>{n}</li>' for n in news[:3]])}</ul>
        
        <p style="font-size: 10px; color: gray; text-align: right;">
            Generated by QuantBot | {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S ET')}
        </p>
    </body>
    </html>
    """
    
    message = MIMEText(content, 'html', 'utf-8')
    message['From'] = sender
    message['To'] = ",".join(receivers)
    message['Subject'] = Header(title, 'utf-8')

    try:
        smtp_obj = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, receivers, message.as_string())
        smtp_obj.quit()
        print(f"✅ 邮件已发送: {symbol}")
    except Exception as e:
        print(f"❌ 发送失败: {e}")

def run_monitor():
    db.init_db()
    try:
        health.check_system_health()
    except Exception as e:
        print(f"⚠️ 健康检查异常: {e}")
        traceback.print_exc()

    status_code, status_msg = is_trading_time()
    print(f"🚀 启动监控 - {status_msg}")
    
    if status_code == 0:
        print("😴 市场休眠中...")
        db.log_system_run("SKIPPED", "Market Closed")
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
            
            # 报警触发逻辑
            if (is_level_up and current_level >= LEVEL_NOTICE) or is_critical:
                print(f"🔔 触发报警: {symbol}")
                send_alert_email(symbol, current_level, current_price, change_pct, score)
            
            db.update_stock_state(symbol, today_str, current_level, current_price, score)
            
        except Exception as e:
            print(f"❌ {symbol} 错误: {e}")

    db.log_system_run("SUCCESS", "Cycle Completed")

if __name__ == "__main__":
    try:
        run_monitor()
    except Exception as e:
        error_msg = f"系统崩溃: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        try:
            health.send_system_email("☠️ 系统崩溃", error_msg)
        except:
            pass
        exit(1)