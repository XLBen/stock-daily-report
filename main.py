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
import ai  # 确保你已经创建了 ai.py

# --- 核心配置 ---
STOCKS = ['NVDA', 'AAPL', 'TSLA'] # 我们主要测试 NVDA
TIMEZONE = pytz.timezone('US/Eastern')

# 状态定义
LEVEL_NORMAL = 0
LEVEL_NOTICE = 1   
LEVEL_WARNING = 2  
LEVEL_CRITICAL = 3 

def is_trading_time():
    """
    【强制测试版】
    无视真实时间，强制返回“盘中交易”状态
    """
    return 2, "🔥 强制测试模式 (上帝模式生效中)"

def calculate_anomaly_score(symbol, current_price):
    """
    【强制测试版】
    无视真实股价，强制制造“惨案”
    """
    # ⚠️ 作弊代码：如果是 NVDA，强制返回暴跌数据
    if symbol == 'NVDA':
        fake_score = 5.5   # 超过 4.5 就是 Level 3 (熔断)
        fake_pct = -8.88   # 假装跌了 8.88%
        return fake_score, fake_pct
    
    # 其他股票保持正常（因为是周末，可能返回 0）
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
    
    if not sender: 
        print("❌ 邮箱未配置")
        return

    receivers = receiver_env.split(',') if ',' in receiver_env else [receiver_env]
    
    # --- AI 介入 ---
    print(f"🧠 [测试] 正在调用 AI 分析 {symbol} ...")
    
    # 抓取真实新闻（虽然股价是假的，但新闻是真的）
    news = ai.get_latest_news(symbol)
    
    # 调用 AI
    try:
        analysis = ai.analyze_market_move(symbol, change_pct, news)
    except Exception as e:
        analysis = {"summary": f"AI调用失败: {str(e)}", "category": "错误", "risk_level": "未知"}
    
    level_tags = {
        LEVEL_NOTICE: "🟡 异动",
        LEVEL_WARNING: "🟠 警告",
        LEVEL_CRITICAL: "🔴 熔断"
    }
    
    title = f"【测试报警】{symbol} {change_pct:.2f}% | {analysis.get('category', '未知')}"
    
    # HTML 邮件模板
    content = f"""
    <html>
    <body>
        <h2 style="color: red;">🚨 量化监控测试 (Level {level})</h2>
        <p><strong>标的:</strong> {symbol}</p>
        <p><strong>模拟涨跌:</strong> <span style="color: red; font-size: large;">{change_pct:.2f}%</span></p>
        <p><strong>异常评分:</strong> {score:.1f}</p>
        
        <hr/>
        <h3>🧠 AI 归因分析 (DeepSeek/OpenAI)</h3>
        <div style="background-color: #f9f9f9; padding: 15px; border-left: 5px solid red;">
            <p><strong>原因:</strong> {analysis.get('summary', '无内容')}</p>
            <p><strong>分类:</strong> {analysis.get('category', '无')}</p>
            <p><strong>风险:</strong> {analysis.get('risk_level', '无')}</p>
            <p><strong>建议:</strong> {analysis.get('action_suggestion', '无')}</p>
        </div>
        
        <hr/>
        <h3>📰 真实抓取的新闻</h3>
        <ul>
            {''.join([f'<li>{n}</li>' for n in news[:3]])}
        </ul>
        
        <p style="color: gray; font-size: 12px;">系统生成时间: {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S ET')}</p>
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
        print(f"✅ 邮件发送成功: {symbol}")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

def run_monitor():
    db.init_db()
    
    # 强制获取开盘状态
    status_code, status_msg = is_trading_time()
    print(f"🚀 启动监控 - {status_msg}")
    
    today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
    
    # 我们只测试列表里的股票
    for symbol in STOCKS:
        try:
            # 获取价格 (为了不报错，还是正常获取一下，虽然下面会用假数据覆盖)
            ticker = yf.Ticker(symbol)
            try:
                current_price = ticker.fast_info['last_price']
            except:
                current_price = 100.0 # 容错兜底
            
            # 使用作弊函数计算指标
            score, change_pct = calculate_anomaly_score(symbol, current_price)
            current_level = determine_level(score)
            
            print(f"🔍 [测试] {symbol} | 模拟跌幅: {change_pct}% | Level: {current_level}")
            
            # 这里的逻辑修改了：只要是测试模式 (Level 3)，且是 NVDA，就强制发邮件
            # 暂时无视状态机锁，确保你能收到邮件
            if symbol == 'NVDA': 
                print(f"🔔 触发测试报警: {symbol}")
                send_alert_email(symbol, current_level, current_price, change_pct, score)
            
            # 更新数据库 (假戏真做)
            db.update_stock_state(symbol, today_str, current_level, current_price, score)
            
        except Exception as e:
            print(f"❌ 处理 {symbol} 出错: {e}")
            import traceback
            traceback.print_exc()

    db.log_system_run("TEST_SUCCESS", "Forced Test Completed")

if __name__ == "__main__":
    run_monitor()