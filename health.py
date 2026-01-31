import db
from datetime import datetime, timedelta, time
import pytz

# 相对时间 Key
KEY_START_TIME = 'system_start_timestamp'
KEY_SENT_STARTUP = 'report_startup_done'
KEY_SENT_20MIN = 'report_20min_done'
KEY_SENT_1HOUR = 'report_1hour_done'
KEY_SENT_3HOUR = 'report_3hour_done'

# 绝对时间配置 (美东时间 ET)
# 对应: 早上8点, 8点半, 12点, 2点15, 3点, 4点
SCHEDULED_TIMES = [
    (time(8, 0), "盘前早报 (08:00)"),
    (time(8, 30), "盘前数据 (08:30)"),
    (time(12, 0), "午间复盘 (12:00)"),
    (time(14, 15), "午后盯盘 (14:15)"),
    (time(15, 0), "尾盘时刻 (15:00)"),
    (time(16, 0), "收盘总结 (16:00)")
]

TIMEZONE = pytz.timezone('US/Eastern')

def get_pending_tasks():
    """
    检查所有时间表，返回需要执行的任务列表
    返回格式: [ ("REPORT_ALL", "启动立即报告"), ("REPORT_ALL", "定时: 08:00") ]
    """
    tasks = []
    now = datetime.now(TIMEZONE)
    today_str = now.strftime('%Y-%m-%d')
    
    # --- 1. 相对时间检查 (启动后 X 时间) ---
    start_time_str = db.get_meta(KEY_START_TIME)
    
    if not start_time_str:
        # 第一次运行，记录启动时间
        db.set_meta(KEY_START_TIME, now.isoformat())
        # 任务：启动立即报告
        if not db.get_meta(KEY_SENT_STARTUP):
            tasks.append(("REPORT_ALL", "🚀 系统启动初始化报告"))
            db.set_meta(KEY_SENT_STARTUP, "1")
    else:
        # 计算运行时长
        start_time = datetime.fromisoformat(start_time_str)
        # 确保 start_time 带时区，如果是 naive 的假定为 ET
        if start_time.tzinfo is None:
            start_time = TIMEZONE.localize(start_time)
            
        uptime = (now - start_time).total_seconds()
        
        # 20分钟报告 (1200秒)
        if uptime >= 1200 and not db.get_meta(KEY_SENT_20MIN):
            tasks.append(("REPORT_ALL", "⏱️ 运行满20分钟报告"))
            db.set_meta(KEY_SENT_20MIN, "1")
            
        # 1小时报告 (3600秒)
        if uptime >= 3600 and not db.get_meta(KEY_SENT_1HOUR):
            tasks.append(("REPORT_ALL", "⏱️ 运行满1小时报告"))
            db.set_meta(KEY_SENT_1HOUR, "1")
            
        # 3小时报告 (10800秒)
        if uptime >= 10800 and not db.get_meta(KEY_SENT_3HOUR):
            tasks.append(("REPORT_ALL", "⏱️ 运行满3小时报告"))
            db.set_meta(KEY_SENT_3HOUR, "1")

    # --- 2. 绝对时间检查 (每天 8点, 12点...) ---
    # 逻辑：当前时间在目标时间的前后 15 分钟内，且今天没发过
    for target_time, label in SCHEDULED_TIMES:
        # 构建今天的完整目标时间
        target_dt = TIMEZONE.localize(datetime.combine(now.date(), target_time))
        
        # 计算时间差 (秒)
        diff = abs((now - target_dt).total_seconds())
        
        # 窗口期：前后 15 分钟 (900秒)
        if diff <= 900:
            task_key = f"SCHED_{target_time.strftime('%H%M')}"
            if not db.check_daily_task_done(task_key, today_str):
                tasks.append(("REPORT_ALL", f"⏰ {label}"))
                db.mark_daily_task_done(task_key, today_str)

    return tasks