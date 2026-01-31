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
    """
    tasks = []
    now = datetime.now(TIMEZONE)
    today_str = now.strftime('%Y-%m-%d')
    
    # --- 1. 相对时间检查 (系统启动后的关键测试节点) ---
    start_time_str = db.get_meta(KEY_START_TIME)
    
    if not start_time_str:
        # 第一次运行：记录启动时间并触发初始化报告
        db.set_meta(KEY_START_TIME, now.isoformat())
        tasks.append(("REPORT_ALL", "🚀 系统启动初始化报告"))
        db.set_meta(KEY_SENT_STARTUP, "1")
        print(f"DEBUG: 数据库已初始化，启动时间设为: {now.isoformat()}")
    else:
        # 计算已运行时长
        try:
            start_time = datetime.fromisoformat(start_time_str)
            if start_time.tzinfo is None:
                start_time = TIMEZONE.localize(start_time)
            
            uptime = (now - start_time).total_seconds()
            print(f"DEBUG: 系统已运行 {int(uptime)} 秒")

            # 20分钟报告 (1200秒) - 增加追补逻辑：只要时间到了且没发过，必发
            if uptime >= 1200 and not db.get_meta(KEY_SENT_20MIN):
                tasks.append(("REPORT_ALL", "⏱️ 运行满20分钟测试报告"))
                db.set_meta(KEY_SENT_20MIN, "1")
                
            # 1小时报告 (3600秒)
            if uptime >= 3600 and not db.get_meta(KEY_SENT_1HOUR):
                tasks.append(("REPORT_ALL", "⏱️ 运行满1小时测试报告"))
                db.set_meta(KEY_SENT_1HOUR, "1")
                
            # 3小时报告 (10800秒)
            if uptime >= 10800 and not db.get_meta(KEY_SENT_3HOUR):
                tasks.append(("REPORT_ALL", "⏱️ 运行满3小时测试报告"))
                db.set_meta(KEY_SENT_3HOUR, "1")
        except Exception as e:
            print(f"DEBUG: 解析启动时间失败: {e}")

    # --- 2. 绝对时间检查 (日常定时任务) ---
    for target_time, label in SCHEDULED_TIMES:
        target_dt = TIMEZONE.localize(datetime.combine(now.date(), target_time))
        
        # 只要当前时间超过了目标时间，且今天还没发过，就执行
        # 这样即使 GitHub Actions 延迟了半小时启动，它也会补发刚才错过的报告
        if now >= target_dt:
            task_key = f"SCHED_{target_time.strftime('%H%M')}"
            if not db.check_daily_task_done(task_key, today_str):
                tasks.append(("REPORT_ALL", f"⏰ {label}"))
                db.mark_daily_task_done(task_key, today_str)

    # --- 3. 周末/非交易时段的心跳包 (每隔1小时强制运行一次作为存活证明) ---
    # 这能解决你“休市期间不敢信它还在工作”的疑虑
    heartbeat_key = f"HEARTBEAT_{now.hour}"
    if not db.check_daily_task_done(heartbeat_key, today_str):
        # 仅在非交易日且没有其他任务时作为备份发送
        if not tasks and now.weekday() >= 5:
            tasks.append(("REPORT_ALL", f"💓 系统周末心跳检查 ({now.strftime('%H:00')})"))
            db.mark_daily_task_done(heartbeat_key, today_str)

    return tasks