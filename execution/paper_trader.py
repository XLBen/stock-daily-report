from execution.alpaca_client import AlpacaPaperClient
from execution.risk_manager import RiskManager
from execution.portfolio import PortfolioTracker
from data.fetcher import get_current_prices
from plans.plan_pool import PlanPool
from plans.plan_executor import evaluate_plan_conditions
from config import ACCOUNTS, RISK
from alpaca.trading.enums import TimeInForce
import db
import time
import json
from datetime import datetime, timedelta


class PaperTrader:

    def __init__(self, trader_name, dry_run=False):
        self.trader_name = trader_name
        self.dry_run = dry_run
        self.cfg = ACCOUNTS.get(trader_name, {})
        self.client = AlpacaPaperClient(trader_name)
        self.risk = RiskManager(self.client)
        self.portfolio = PortfolioTracker(self.client)
        self.plan_pool = PlanPool()

    # ================================================================
    # 交易周期
    # ================================================================

    def run_cycle(self):
        print(f"\n{'='*60}")
        print(f"[{self.trader_name}] trading cycle {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        if not self.client.is_account_valid():
            print(f"  [{self.trader_name}] Alpaca not configured, skipping")
            return

        self.manage_limit_orders()

        self.portfolio.snapshot()
        self.portfolio.print_summary()

        plans = self.plan_pool.get_active_plans()
        trader_plans = [p for p in plans if p.get('trader') == self.trader_name or p.get('account_id') == self.trader_name]

        now = datetime.now()
        for p in trader_plans:
            week_end = p.get('week_end', '')
            try:
                end_date = datetime.strptime(week_end, '%Y-%m-%d')
                if now > end_date + timedelta(days=1):
                    db.archive_plan(p['plan_id'])
                    print(f"  [{self.trader_name}] archived stale plan: {p['plan_id']} (ended {week_end})")
            except:
                pass

        trader_plans = [p for p in trader_plans if p.get('status') == 'active']
        if not trader_plans:
            print(f"  [{self.trader_name}] No active plans")
            return

        print(f"  [{self.trader_name}] Loading {len(trader_plans)} plans")

        all_symbols = set()
        for p in trader_plans:
            try:
                plan_data = json.loads(p['plan_json']) if isinstance(p['plan_json'], str) else p['plan_json']
                for r in plan_data.get('rules', []):
                    all_symbols.add(r.get('symbol', ''))
            except:
                pass
        all_symbols.discard('')
        current_prices = get_current_prices(list(all_symbols))

        executions = 0
        for p in trader_plans:
            try:
                plan_data = json.loads(p['plan_json']) if isinstance(p['plan_json'], str) else p['plan_json']
                plan_id = p['plan_id']
                for rule in plan_data.get('rules', []):
                    symbol = rule.get('symbol', '')
                    action = rule.get('action', 'BUY')
                    alloc_pct = rule.get('alloc_pct', 0.1)
                    current_price = current_prices.get(symbol)
                    rule_id = rule.get('rule_id', 0)
                    if not current_price:
                        continue

                    ok, reason = evaluate_plan_conditions(rule, symbol, current_price)
                    if not ok:
                        continue

                    pos = self.client.get_position_for_symbol(symbol)
                    can_trade, risk_reason = self.risk.can_open_position(
                        symbol, alloc_pct, action,
                        current_position_check=(pos is not None)
                    )
                    if not can_trade:
                        print(f"  [{self.trader_name}] {symbol} risk denied: {risk_reason}")
                        db.log_plan_execution(plan_id, rule_id, symbol, action, result="risk_denied", reason=risk_reason)
                        continue

                    qty = self.risk.calculate_qty(symbol, current_price, alloc_pct)
                    if qty <= 0:
                        print(f"  [{self.trader_name}] {symbol} qty=0 (price ${current_price:.2f}, alloc {alloc_pct*100:.0f}%)")
                        continue
                    order_config = rule.get('order', {})
                    risk_config = rule.get('risk', {})

                    if self.dry_run:
                        print(f"  [DRY-RUN] {action} {qty} {symbol} @ ${current_price:.2f} (alloc {alloc_pct*100:.0f}%)")
                        self._log_trade(plan_id, rule_id, symbol, action, qty,
                                        entry_price=current_price,
                                        trigger_reason=reason,
                                        rule_snapshot=json.dumps(rule, ensure_ascii=False),
                                        order_id="DRY_RUN")
                    else:
                        order_type = order_config.get('type', 'market')
                        if order_type == 'limit':
                            limit_price = order_config.get('limit_price')
                            if limit_price is None and 'price_offset_pct' in order_config:
                                offset = order_config['price_offset_pct']
                                if side.upper() == 'BUY':
                                    limit_price = round(current_price * (1 - abs(offset)), 2)
                                else:
                                    limit_price = round(current_price * (1 + abs(offset)), 2)
                            if limit_price is None:
                                limit_price = current_price
                            tif = order_config.get('time_in_force', 'day')
                            tif_map = {'day': TimeInForce.DAY, 'gtc': TimeInForce.GTC}
                            tif_enum = tif_map.get(tif.lower() if isinstance(tif, str) else str(tif).lower(), TimeInForce.DAY)
                            result = self.client.submit_limit_order(symbol, qty, action, limit_price, tif_enum)
                            if result:
                                db.save_order_log(result.id, self.trader_name, symbol, action, qty,
                                                  order_type='limit', limit_price=limit_price, status='pending')
                                db.log_plan_execution(plan_id, rule_id, symbol, action,
                                                      order_id=result.id, result="pending",
                                                      reason=f"limit ${limit_price:.2f}")
                                print(f"  LIMIT order: {action} {qty} {symbol} @ ${limit_price:.2f} -> {result.id}")
                            else:
                                db.log_plan_execution(plan_id, rule_id, symbol, action,
                                                      result="failed", reason="api_error")
                        else:
                            result = self.client.submit_market_order(symbol, qty, action)
                            if result:
                                db.save_order_log(result.id, self.trader_name, symbol, action, qty,
                                                  order_type='market', status='filled', limit_price=current_price)
                                db.update_order_status(result.id, 'filled', filled_price=current_price)
                                self._log_trade(plan_id, rule_id, symbol, action, qty,
                                                entry_price=current_price,
                                                trigger_reason=reason,
                                                rule_snapshot=json.dumps(rule, ensure_ascii=False),
                                                order_id=result.id)
                                db.log_plan_execution(plan_id, rule_id, symbol, action,
                                                      order_id=result.id, result="executed",
                                                      reason=f"market @ {current_price}")
                                print(f"  [{self.trader_name}] {action} {qty} {symbol} @ ${current_price:.2f} | {result.id}")
                            else:
                                db.log_plan_execution(plan_id, rule_id, symbol, action,
                                                      result="failed", reason="api_error")
                                print(f"  [{self.trader_name}] order FAILED: {action} {symbol}")

                    executions += 1
                    time.sleep(0.3)

            except Exception as e:
                print(f"  [{self.trader_name}] plan error: {e}")

        if executions == 0:
            print(f"  [{self.trader_name}] no signals triggered")

        self.portfolio.snapshot()
        print(f"[{self.trader_name}] cycle done\n")

    # ================================================================
    # 限价单追踪
    # ================================================================

    def manage_limit_orders(self):
        pending = db.get_open_orders(self.trader_name, 'pending')
        if not pending:
            return
        print(f"  [{self.trader_name}] checking {len(pending)} open limit orders...")

        for order in pending:
            order_id = order.get('order_id')
            if not order_id:
                continue
            alpaca_order = self.client.get_order(order_id)
            if alpaca_order is None:
                continue

            status = str(alpaca_order.status)
            filled_price = float(alpaca_order.filled_avg_price) if getattr(alpaca_order, 'filled_avg_price', None) else None

            if status == 'filled':
                db.update_order_status(order_id, 'filled', filled_price=filled_price)
                plan_logs = self._get_plan_logs_for_order(order_id)
                if plan_logs:
                    pl = plan_logs[0]
                    self._log_trade(pl.get('plan_id'), pl.get('rule_id'), order['symbol'], order['side'],
                                    order['qty'], entry_price=filled_price,
                                    trigger_reason=f"limit filled @ ${filled_price:.2f}",
                                    order_id=order_id)
                print(f"  [{self.trader_name}] limit filled: {order['symbol']} @ ${filled_price:.2f}")

            elif status in ('expired', 'canceled', 'rejected'):
                db.update_order_status(order_id, status)
                print(f"  [{self.trader_name}] limit {status}: {order['symbol']}")

            else:
                created = order.get('created_at')
                if created:
                    try:
                        if isinstance(created, str):
                            created = created.replace('Z', '+00:00')
                            created_dt = datetime.fromisoformat(created) if '+' in created else datetime.now()
                        else:
                            created_dt = created
                        now_utc = datetime.now().replace(tzinfo=None) if (isinstance(created_dt, str) or (hasattr(created_dt, 'tzinfo') and created_dt.tzinfo is None)) else datetime.now()
                        hours = abs((datetime.now().replace(tzinfo=None) - (created_dt.replace(tzinfo=None) if hasattr(created_dt, 'tzinfo') else created_dt)).total_seconds() / 3600)
                        if hours > 24:
                            self.client.cancel_order(order_id)
                            db.update_order_status(order_id, 'cancelled')
                            print(f"  [{self.trader_name}] cancelled stale limit: {order['symbol']} ({hours:.0f}h)")
                    except Exception as e:
                        pass

    def _get_plan_logs_for_order(self, order_id):
        import sqlite3
        with db.get_connection() as conn:
            cursor = conn.execute('SELECT * FROM plan_execution_log WHERE order_id = ?', (order_id,))
            return [dict(row) for row in cursor.fetchall()]

    # ================================================================
    # 止损 / 止盈
    # ================================================================

    def check_stop_losses(self):
        positions = self.client.get_positions()
        if not positions:
            return

        current_prices = get_current_prices([p.symbol for p in positions])
        plans = self.plan_pool.get_active_plans()

        for pos in positions:
            symbol = pos.symbol
            current_price = current_prices.get(symbol)
            entry_price = float(pos.avg_entry_price)
            if not current_price:
                continue

            trade_journal_entry = db.get_position_entry(self.trader_name, symbol)
            hold_hours = 0
            if trade_journal_entry and trade_journal_entry.get('executed_at'):
                try:
                    et = trade_journal_entry['executed_at']
                    if isinstance(et, str):
                        et = datetime.fromisoformat(et.replace('Z', '+00:00'))
                    hold_hours = abs((datetime.now() - et.replace(tzinfo=None) if et.tzinfo else datetime.now()).total_seconds() / 3600)
                except:
                    pass

            min_h = self.cfg.get('min_hold_hours', 1)
            if hold_hours < min_h:
                continue

            stop_pct = RISK.get('default_stop_loss_pct', 0.07)
            take_profit_pct = RISK.get('default_take_profit_pct', 0.15)
            trailing_pct = RISK.get('trailing_stop_pct', 0.03)
            trailing_activation = self.cfg.get('trailing_stop_activation', 0.05)

            for p in plans:
                try:
                    plan_data = json.loads(p['plan_json']) if isinstance(p['plan_json'], str) else p['plan_json']
                    for r in plan_data.get('rules', []):
                        if r.get('symbol') == symbol:
                            rc = r.get('risk', {})
                            stop_pct = rc.get('stop_loss_pct', stop_pct)
                            take_profit_pct = rc.get('take_profit_pct', take_profit_pct)
                            trailing_pct = rc.get('trailing_stop_pct', trailing_pct)
                            break
                except:
                    pass

            change_pct = (current_price - entry_price) / entry_price

            exit_type = None
            exit_reason = ""

            if change_pct <= -stop_pct:
                exit_type = "STOP_LOSS"
                exit_reason = f"loss {change_pct*100:.1f}% >= limit {stop_pct*100:.1f}%"

            elif change_pct >= trailing_activation:
                trailing_price = max(entry_price, current_price * (1 - trailing_pct))
                if current_price <= trailing_price:
                    exit_type = "TRAILING_STOP"
                    exit_reason = f"trailing stop: profit peaked, now {change_pct*100:.1f}%"

            if exit_type is None and change_pct >= take_profit_pct:
                exit_type = "TAKE_PROFIT"
                exit_reason = f"profit {change_pct*100:.1f}% >= target {take_profit_pct*100:.1f}%"

            if exit_type:
                print(f"  [{self.trader_name}] {exit_type}: {symbol} {change_pct*100:.1f}% ({hold_hours:.1f}h) - {exit_reason}")
                if not self.dry_run:
                    self.client.close_position(symbol)
                self._log_trade("", 0, symbol, exit_type, float(pos.qty),
                                entry_price=entry_price, exit_price=current_price,
                                pnl=(current_price - entry_price) * float(pos.qty),
                                pnl_pct=change_pct * 100,
                                trigger_reason=exit_reason,
                                hold_duration_hours=hold_hours)

    # ================================================================
    # 通用交易日志
    # ================================================================

    def _log_trade(self, plan_id, rule_id, symbol, action, qty,
                   entry_price=None, exit_price=None, pnl=None, pnl_pct=None,
                   trigger_reason=None, conditions_detail=None, rule_snapshot=None,
                   order_id=None, hold_duration_hours=None):
        trader_role = self.cfg.get('tag', self.trader_name)
        db.insert_trade_journal(
            account_id=self.trader_name,
            trader_role=trader_role,
            plan_id=plan_id or '',
            rule_id=rule_id or 0,
            symbol=symbol,
            action=action,
            qty=qty,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            trigger_reason=str(trigger_reason)[:200] if trigger_reason else None,
            conditions_detail=conditions_detail,
            rule_snapshot=rule_snapshot,
            order_id=order_id,
            hold_duration_hours=hold_duration_hours,
        )

    def close_all(self):
        self.client.close_all_positions()
