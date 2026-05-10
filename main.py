import sys
import signal
import time
import argparse
import io
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except (AttributeError, ValueError):
    pass

import db
from config import TIMEZONE, DRY_RUN as CFG_DRY_RUN
from scheduler import setup_scheduler

DRY_RUN = CFG_DRY_RUN
LOG_FILE = None
RESTART_DELAY = 10  # seconds before auto-restart on crash


def log(msg):
    print(msg)
    if LOG_FILE:
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().isoformat()}] {msg}\n")
        except:
            pass


def parse_args():
    parser = argparse.ArgumentParser(description='AI-Powered Alpaca Paper Trading System')
    parser.add_argument('--dry-run', action='store_true', default=False)
    parser.add_argument('--plan-now', action='store_true', default=False)
    parser.add_argument('--test-cycle', action='store_true', default=False)
    parser.add_argument('--log-file', type=str, default=None)
    parser.add_argument('--no-restart', action='store_true', default=False, help='Disable auto-restart on crash')
    return parser.parse_args()


def run_once(mode):
    if mode == 'plan':
        from plans.weekly_planner import generate_weekly_plans
        generate_weekly_plans()
    elif mode == 'cycle':
        from execution.paper_trader import PaperTrader
        for name in ["left_trader", "right_trader", "extreme_trader"]:
            pt = PaperTrader(name, dry_run=DRY_RUN)
            pt.run_cycle()


def _run_scheduler():
    scheduler = BackgroundScheduler(timezone=pytz.UTC)
    setup_scheduler(scheduler)

    def shutdown(sig, frame):
        log("\nReceived exit signal, shutting down...")
        scheduler.shutdown(wait=False)
        log("System stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    scheduler.start()
    log(f"System started - {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    log("  Ctrl+C to stop\n")

    db.log_system_run("STARTUP", f"system started, dry_run={DRY_RUN}")

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        shutdown(None, None)


def main():
    global DRY_RUN, LOG_FILE
    args = parse_args()

    if args.dry_run:
        DRY_RUN = True

    if args.log_file:
        LOG_FILE = args.log_file
        log(f"--- QuantBot started at {datetime.now().isoformat()} ---")

    log("\n" + "="*60)
    log("  AI-Powered Alpaca Paper Trading System")
    log("  Three Traders: Left | Right | Extreme")
    log(f"  Mode: {'DRY-RUN (Simulation)' if DRY_RUN else 'LIVE Trading'}")
    log("="*60 + "\n")

    db.init_db()

    from reporting.discord import DiscordReporter
    DiscordReporter()

    if args.plan_now:
        log("--plan-now: generating weekly plan\n")
        try:
            run_once('plan')
        except Exception as e:
            log(f"Plan generation failed: {e}")
            import traceback
            traceback.print_exc()
        log("\nPlan generation complete.")
        return

    if args.test_cycle:
        if not DRY_RUN:
            now = datetime.now(TIMEZONE)
            is_weekend = now.weekday() >= 5
            is_before_open = now.hour < 9 or (now.hour == 9 and now.minute < 30)
            is_after_close = now.hour >= 16
            if is_weekend or is_before_open or is_after_close:
                log("\nWARNING: Market is currently CLOSED (after-hours or weekend).")
                log("Orders will execute at next market open.")
                resp = input("Continue? [y/N] ").strip().lower()
                if resp != 'y':
                    log("Aborted.")
                    return

        log("--test-cycle: running one full cycle\n")
        try:
            from plans.weekly_planner import generate_weekly_plans
            generate_weekly_plans()
            run_once('cycle')
        except Exception as e:
            log(f"Test cycle failed: {e}")
            import traceback
            traceback.print_exc()
        log("\nTest cycle complete.")
        return

    while True:
        try:
            _run_scheduler()
        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            log(f"\nFATAL: Scheduler crashed: {e}")
            import traceback
            log(traceback.format_exc())
            db.log_system_run("CRASH", f"scheduler crashed: {str(e)[:200]}")
            if args.no_restart:
                log("--no-restart set, exiting.")
                break
            log(f"Restarting in {RESTART_DELAY}s...")
            time.sleep(RESTART_DELAY)


if __name__ == "__main__":
    main()
