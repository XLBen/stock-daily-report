import time
from datetime import datetime, time as dtime
import pytz
import db
from config import MARKET_OPEN, MARKET_CLOSE, TIMEZONE, DRY_RUN as CFG_DRY_RUN


def is_trading_time():
    now = datetime.now(TIMEZONE)
    if now.weekday() >= 5:
        return False, "weekend"
    ct = now.time()
    mo = dtime(*MARKET_OPEN)
    mc = dtime(*MARKET_CLOSE)
    if mo <= ct <= mc:
        return True, "market_open"
    return False, "after_hours"


def setup_scheduler(scheduler_instance):
    s = scheduler_instance

    s.add_job(
        _trading_cycle_job,
        "cron",
        day_of_week="mon,wed,fri",
        hour=10, minute=0,
        timezone=TIMEZONE,
        id="trading_cycle",
        name="Trading Cycle (Mon/Wed/Fri 10AM)",
        misfire_grace_time=600,
    )

    s.add_job(
        _weekly_plan_job,
        "cron",
        day_of_week="sun",
        hour=20, minute=0,
        timezone=TIMEZONE,
        id="weekly_plan",
        name="Sunday Plan Generation",
        misfire_grace_time=900,
    )

    s.add_job(
        _stop_loss_check_job,
        "interval",
        minutes=15,
        timezone=TIMEZONE,
        id="stop_loss_check",
        name="Stop Loss Check (15 min)",
    )

    s.add_job(
        _weekly_settlement_job,
        "cron",
        day_of_week="fri",
        hour=16, minute=0,
        timezone=TIMEZONE,
        id="weekly_settlement",
        name="Friday Settlement",
        misfire_grace_time=600,
    )

    s.add_job(
        _daily_reset_job,
        "cron",
        day_of_week="mon,wed,fri",
        hour=9, minute=0,
        timezone=TIMEZONE,
        id="daily_reset",
        name="Daily Risk Reset",
        misfire_grace_time=300,
    )

    s.add_job(
        _portfolio_report_open_job,
        "cron",
        day_of_week="mon-fri",
        hour=9, minute=35,
        timezone=TIMEZONE,
        id="portfolio_open",
        name="Portfolio Report - Open",
        misfire_grace_time=120,
    )

    s.add_job(
        _portfolio_report_1hour_job,
        "cron",
        day_of_week="mon-fri",
        hour=10, minute=30,
        timezone=TIMEZONE,
        id="portfolio_1hour",
        name="Portfolio Report - 1 Hour",
        misfire_grace_time=120,
    )

    s.add_job(
        _portfolio_report_midday_job,
        "cron",
        day_of_week="mon-fri",
        hour=13, minute=0,
        timezone=TIMEZONE,
        id="portfolio_midday",
        name="Portfolio Report - Midday",
        misfire_grace_time=120,
    )

    s.add_job(
        _portfolio_report_close_job,
        "cron",
        day_of_week="mon-fri",
        hour=16, minute=0,
        timezone=TIMEZONE,
        id="portfolio_close",
        name="Portfolio Report - Close",
        misfire_grace_time=120,
    )

    print("Scheduler registered:")
    for job in s.get_jobs():
        print(f"  [{job.id}] {job.name}")


def _trading_cycle_job():
    from execution.paper_trader import PaperTrader
    for name in ["left_trader", "right_trader", "extreme_trader"]:
        try:
            pt = PaperTrader(name, dry_run=CFG_DRY_RUN)
            if not pt.client.is_account_valid():
                continue
            pt.run_cycle()
        except Exception as e:
            print(f"  [{name}] cycle error: {e}")


def _weekly_plan_job():
    from plans.weekly_planner import generate_weekly_plans
    generate_weekly_plans()


def _stop_loss_check_job():
    from execution.paper_trader import PaperTrader
    from reporting.portfolio_monitor import PortfolioMonitor
    for name in ["left_trader", "right_trader", "extreme_trader"]:
        try:
            pt = PaperTrader(name, dry_run=CFG_DRY_RUN)
            if not pt.client.is_account_valid():
                continue
            if pt.client.get_positions():
                pt.check_stop_losses()
                pm = PortfolioMonitor(pt.client)
                pm.check_major_moves()
        except Exception as e:
            print(f"  [{name}] stop loss error: {e}")


def _weekly_settlement_job():
    from execution.paper_trader import PaperTrader
    from plans.plan_pool import PlanPool
    from execution.portfolio import PortfolioTracker
    print("\nFriday Settlement: close all + archive plans\n")
    for name in ["left_trader", "right_trader", "extreme_trader"]:
        try:
            pt = PaperTrader(name, dry_run=CFG_DRY_RUN)
            PortfolioTracker(pt.client).print_summary()
            pt.close_all()
        except Exception as e:
            print(f"  [{name}] settlement error: {e}")
    PlanPool().archive_all_active()
    db.log_system_run("weekly_settlement", "positions closed")


def _daily_reset_job():
    from execution.paper_trader import PaperTrader
    for name in ["left_trader", "right_trader", "extreme_trader"]:
        try:
            pt = PaperTrader(name, dry_run=True)
            pt.risk.reset_daily_limits()
            print(f"  [{name}] risk reset")
        except:
            pass


def _portfolio_report(which):
    from execution.paper_trader import PaperTrader
    from reporting.portfolio_monitor import PortfolioMonitor
    for name in ["left_trader", "right_trader", "extreme_trader"]:
        try:
            pt = PaperTrader(name, dry_run=CFG_DRY_RUN)
            if not pt.client.is_account_valid():
                continue
            pm = PortfolioMonitor(pt.client)
            pm.send_report(which)
        except Exception as e:
            print(f"  [{name}] portfolio report error: {e}")


def _portfolio_report_open_job():
    _portfolio_report("open")


def _portfolio_report_1hour_job():
    _portfolio_report("1hour")


def _portfolio_report_midday_job():
    _portfolio_report("midday")


def _portfolio_report_close_job():
    _portfolio_report("close")
