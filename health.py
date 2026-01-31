import db
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta
import pytz

# 系统启动时间 (Key)
KEY_START_TIME = 'system_start_timestamp'
# 里程碑标记 (Keys)
KEY_SENT_10MIN = 'milestone_10min_sent'
KEY_SENT_1HOUR = 'milestone_1hour_sent'
KEY_SENT_3HOUR = 'milestone_3hour_sent'
# 上次发送日报的日期
KEY_LAST_DAILY_REPORT = 'last_uptime_report_date'

def send_system_email(subject, content):
    """发送系统级通知邮件"""
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver = os.environ.get('MAIL_RECEIVER')
    
    if not sender: return

    receivers = receiver.split(',') if ',' in receiver else [receiver]
    
    msg = MIMEText(content, 'plain', 'utf-8')
    msg['From'] = sender
    msg['To'] = ",".join(receivers)
    msg['Subject'] = Header(subject, 'utf-8')

    try:
        smtp = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        smtp.login(sender, password)
        smtp.sendmail(sender, receivers, msg.as_string())
        smtp.quit()
        print(f"📧 [System] 邮件已发送: {subject}")
    except Exception as e:
        print(f"❌ [System] 邮件发送失败: {e}")

def check_system_health():
    """核心健康检查逻辑"""
    now = datetime.now(pytz.utc) # 统一使用 UTC 时间
    
    # 1. 检查或初始化启动时间
    start_time_str = db.get_meta(KEY_START_TIME)
    
    if not start_time_str:
        # 第一次运行！
        db.set_meta(KEY_START_TIME, now.isoformat())
        send_system_email(
            "🚀 量化系统已启动 (System Start)", 
            f"系统首次初始化成功。\n启动时间 (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n接下来将在运行 10分钟、1小时、3小时后发送测试邮件。"
        )
        return # 第一次刚启动，不需要检查后面的里程碑
    
    # 计算运行时长
    start_time = datetime.fromisoformat(start_time_str)
    uptime = now - start_time
    total_seconds = uptime.total_seconds()
    
    print(f"⏱️ 系统已运行: {uptime}")

    # 2. 检查里程碑 (10分钟, 1小时, 3小时)
    # 注意：因为 Cron 是 20分钟一次，所以 10分钟的测试可能会在第 20 分钟收到，这是正常的
    
    # 10分钟测试 (600秒)
    if total_seconds >= 600 and not db.get_meta(KEY_SENT_10MIN):
        send_system_email("✅ 测试: 运行满 10 分钟", f"系统已稳定运行 {uptime}。\n邮件发送功能正常。")
        db.set_meta(KEY_SENT_10MIN, "1")

    # 1小时测试 (3600秒)
    if total_seconds >= 3600 and not db.get_meta(KEY_SENT_1HOUR):
        send_system_email("✅ 测试: 运行满 1 小时", f"系统已稳定运行 {uptime}。")
        db.set_meta(KEY_SENT_1HOUR, "1")

    # 3小时测试 (10800秒)
    if total_seconds >= 10800 and not db.get_meta(KEY_SENT_3HOUR):
        send_system_email("✅ 测试: 运行满 3 小时", f"系统已稳定运行 {uptime}。")
        db.set_meta(KEY_SENT_3HOUR, "1")

    # 3. 每日 0 点汇报 (Uptime Report)
    # 逻辑：如果是 0点~1点之间，且今天还没发过
    current_date_str = now.strftime('%Y-%m-%d')
    last_report_date = db.get_meta(KEY_LAST_DAILY_REPORT)
    
    if now.hour == 0 and last_report_date != current_date_str:
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        report_content = f"""
        【量化系统运行日报】
        📅 日期: {current_date_str}
        
        ⏱️ 累计运行时长: {days}天 {hours}小时 {minutes}分
        🚀 初始启动时间: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}
        
        系统状态: 正常运行中
        """
        send_system_email(f"📊 每日运行报告 ({current_date_str})", report_content)
        db.set_meta(KEY_LAST_DAILY_REPORT, current_date_str)