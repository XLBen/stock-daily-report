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
import ai  # 引入我们的大脑模块

# --- 核心配置 ---
# 你可以在这里把你想监控的股票都加进去
STOCKS = ['NVDA', 'AAPL', 'TSLA', 'AMD', 'MSFT', 'META', 'GOOGL']
TIMEZONE = pytz.timezone('US/Eastern')

# 状态定义
LEVEL_NORMAL = 0
LEVEL_NOTICE = 1   # 异常分 > 2.0 (微小异动，只记录不发邮件，或仅存日志)
LEVEL_WARNING = 2  # 异常分 > 3.0 (值得关注，调用 AI)
LEVEL_CRITICAL = 3 # 异常分 > 4.5 (极端行情，调用 AI + 紧急标记)

def is_trading_time():
    """
    真实交易时间检查
    返回: (status_code, message)
    0: 休市/周末
    1: 盘前/盘后 (只更新数据，不报警)
    2: 盘中 (全功能监控)
    """
    now = datetime.now(TIMEZONE)
    
    # 1. 周末检查 (周六=5, 周日=6)
    if now.weekday() >= 5:
        return 0, "周末休市"
    
    current_time = now.time()
    
    # 2. 时段检查 (美东时间)
    # 盘前: 04:00 - 09:30
    # 盘中: 09:30 - 16:00
    # 盘后: 16:00 - 20:00
    if current_time < time(9, 30):
        return 1, "盘前时段"
    elif current_time > time(16, 0):
        return 1, "盘后时段"
    
    return 2, "盘中交易"

def calculate_anomaly_score(symbol, current_price):
    """
    核心算法：基于 MAD (中位数绝对偏差) 的稳健波动率计算
    """
    try:
        # 拉取过去 1 个月数据作为基准
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1mo")
        
        if len(hist) < 20: return 0.0, 0.0

        # 1. 计算每日收益率
        returns = hist['Close'].pct_change().dropna()
        
        # 2. 计算今日实时涨跌幅 (相对于昨收)
        prev_close = hist['Close'].iloc[-2]
        if prev_close == 0: return 0.0, 0.0
        
        current_pct = ((current_price - prev_close) / prev_close) * 100
        
        # 3. 计算 MAD 基准
        median_ret = returns.median()
        # MAD = median(|x - median|)
        mad = np.abs(returns - median_ret).median()
        
        if mad == 0: mad = 0.001 # 防止除零

        # 4. 计算异常分 (Z-Score 变体)
        # 1.4826 是正态分布的一致性常数
        robust_sigma = 1.4826 * mad
        
        # 将当前涨跌幅转回小数进行比较 (current_pct/100)
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
    
    if not sender or not password or not receiver_env:
        print("❌ 邮箱 Secrets 未配置，跳过发送")
        return

    receivers = receiver_env.split(',') if ',' in receiver_env else [receiver_env]
    
    # --- AI 介入逻辑 ---
    # 策略：只有 Level 2 (Warning) 及以上，或者跌幅超过 3% 时才调用 AI
    # 这样可以节省 Token，且只关注重要波动
    analysis = {}
    news = []
    
    if level >= LEVEL_WARNING or abs(change_pct) > 3.0:
        print(f"🧠 [AI] 正在分析 {symbol} 的波动原因...")
        news = ai.get_latest_news(symbol)
        try:
            analysis = ai.analyze_market_move(symbol, change_pct, news)
        except Exception as e:
            print(f"AI 调用失败: {e}")
            analysis = {"summary": "AI服务暂时不可用", "category": "系统错误", "risk_level": "未知"}
    else:
        analysis = {"summary": "波动未达 AI 分析阈值", "category": "常规波动", "risk_level": "低"}
        # 依然抓取新闻用于展示，但不送给 AI 分析
        news = ai.get_latest_news(symbol)

    # --- 邮件构建 ---
    level_tags = {
        LEVEL_NOTICE: "🟡 异动提醒",
        LEVEL_WARNING: "🟠 异常警告",
        LEVEL_CRITICAL: "🔴 熔断级警报"
    }
    
    color = "red" if change_pct < 0 else "green"
    arrow = "📉" if change_pct < 0 else "📈"
    
    title = f"{level_tags.get(level, '通知')}：{symbol} {arrow} {change_pct:+.2f}% | {analysis.get('category', '未知')}"
    
    content = f"""
    <html>
    <body>
        <h2>{level_tags.get(level)}: {symbol}</h2>
        <p style="font-size: 16px;">
            <strong>现价:</strong> ${price:.2f} 
            (<span style="color: {color}; font-weight: bold;">{change_pct:+.2f}%</span>)
        </p>
        <p><strong>异常评分:</strong> {score:.1f} (Level {level})</p>
        
        <hr/>
        <h3>🧠 AI 归因分析</h3>
        <div style="background-color: #f0f0f0; padding: 15px; border-radius: 5px;">
            <p><strong>原因:</strong> {analysis.get('summary', '暂无')}</p>
            <p><strong>分类:</strong> {analysis.get('category', '暂无')}</p>
            <p><strong>风险:</strong> {analysis.get('risk_level', '暂无')}</p>
            <p><strong>建议:</strong> {analysis.get('action_suggestion', '暂无')}</p>
        </div>
        
        <hr/>
        <h3>📰 最新相关新闻</h3>
        <ul>
            {''.join([f'<li>{n}</li>' for n in news[:5]])}
        </ul>
        
        <p style="font-size: small; color: gray;">
            生成时间: {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S ET')}
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
        print(f"❌ 邮件发送失败: {e}")

def run_monitor():
    # 1. 初始化数据库
    db.init_db()
    
    # 2. 检查时间
    status_code, status_msg = is_trading_time()
    print(f"🚀 启动监控 - {status_msg}")
    
    if status_code == 0:
        print("😴 市场休眠中...")
        db.log_system_run("SKIPPED", "Market Closed")
        return

    today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
    
    for symbol in STOCKS:
        try:
            # 获取实时价格
            ticker = yf.Ticker(symbol)
            try:
                # 尝试获取 fast_info，如果失败则回退到 history
                current_price = ticker.fast_info['last_price']
            except:
                hist = ticker.history(period='1d')
                if hist.empty:
                    print(f"⚠️ {symbol} 无法获取数据，跳过")
                    continue
                current_price = hist['Close'].iloc[-1]
            
            # 计算指标
            score, change_pct = calculate_anomaly_score(symbol, current_price)
            current_level = determine_level(score)
            
            # 读取上一时刻的状态
            prev_state = db.get_stock_state(symbol)
            prev_level = prev_state['level'] if prev_state else 0
            
            print(f"🔍 {symbol}: ${current_price:.2f} ({change_pct:+.2f}%) | Score: {score:.1f} | Level: {current_level}")
            
            # --- 核心状态机逻辑 ---
            # 触发条件：
            # 1. 级别升级 (例如 0 -> 2)
            # 2. 已经是 Level 3 (熔断) 且没有降级 (持续高危，每轮都报可能太吵，可以考虑加时间间隔锁，这里暂保持敏感)
            # 3. 必须达到 Notice 以上才考虑报警
            
            is_level_up = (current_level > prev_level)
            is_critical = (current_level == LEVEL_CRITICAL)
            
            if (is_level_up and current_level >= LEVEL_NOTICE) or is_critical:
                print(f"🔔 触发报警: {symbol} (Level {prev_level} -> {current_level})")
                
                # 注意：Level 1 (Notice) 通常不建议发 AI 邮件，只发简单提醒
                # 这里已经在 send_alert_email 内部做了判断，如果不到 Warning 级别不调 AI
                send_alert_email(symbol, current_level, current_price, change_pct, score)
            
            # 更新数据库状态
            db.update_stock_state(symbol, today_str, current_level, current_price, score)
            
        except Exception as e:
            print(f"❌ 监控 {symbol} 发生异常: {e}")

    db.log_system_run("SUCCESS", "Cycle Completed")

def run_monitor():
    # 1. 初始化数据库
    db.init_db()
    
    # 2. 【核心新增】执行健康检查 (发启动邮件、测试邮件、日报)
    # 无论是否休市，健康检查都要运行，确保 0 点日报能发出
    try:
        health.check_system_health()
    except Exception as e:
        print(f"健康检查模块出错: {e}")

    # 3. 检查市场时间
    status_code, status_msg = is_trading_time()
    print(f"🚀 启动监控 - {status_msg}")
    
    if status_code == 0:
        print("😴 市场休眠中...")
        db.log_system_run("SKIPPED", "Market Closed")
        return

    today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
    
    for symbol in STOCKS:
        # ... (之前的监控循环逻辑完全保持不变) ...
        # 为了节省篇幅，这里省略中间的监控代码，直接用你上一个版本的即可
        pass 
        # ... 

    db.log_system_run("SUCCESS", "Cycle Completed")

if __name__ == "__main__":
    try:
        # 全局异常捕获
        run_monitor()
    except Exception as e:
        # 如果程序彻底崩了 (比如代码写错了)，死之前发个邮件通知
        error_msg = f"量化主程序发生未捕获异常，即将退出。\n错误信息:\n{str(e)}\n\n{traceback.format_exc()}"
        print("❌ 致命错误")
        print(error_msg)
        health.send_system_email("☠️ [严重] 系统崩溃通知", error_msg)
        exit(1) # 退出并返回错误码，让 GitHub Actions 知道失败了