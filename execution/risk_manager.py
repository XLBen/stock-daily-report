import db
from config import RISK, ACCOUNTS
from datetime import datetime


class RiskManager:
    def __init__(self, alpaca_client):
        self.client = alpaca_client
        self.trader_name = alpaca_client.trader
        self.cfg = ACCOUNTS.get(self.trader_name, {})
        self.daily_loss_pct = 0
        self.daily_start_equity = None
        self.trade_disabled = False

    def _refresh_equity(self):
        acc = self.client.get_account()
        if acc:
            equity = float(acc.equity)
            if self.daily_start_equity is None:
                self.daily_start_equity = equity
            return equity
        return None

    def check_daily_loss_limit(self):
        equity = self._refresh_equity()
        if equity is None:
            return True
        if self.daily_start_equity is not None and self.daily_start_equity > 0:
            self.daily_loss_pct = (self.daily_start_equity - equity) / self.daily_start_equity
        if self.daily_loss_pct >= RISK.get("daily_loss_limit_pct", 0.05):
            print(f"  [{self.trader_name}] daily loss {self.daily_loss_pct*100:.1f}% >= limit, MELTDOWN")
            self.trade_disabled = True
            return False
        return True

    def check_cooldown(self, symbol):
        last = db.get_last_trade(self.trader_name, symbol)
        if last and last.get('action') in ('SELL', 'STOP_LOSS', 'TAKE_PROFIT'):
            et = last.get('executed_at')
            if et:
                try:
                    if isinstance(et, str):
                        et = datetime.fromisoformat(et.replace('Z', '+00:00'))
                    hours_since = (datetime.now().replace(tzinfo=et.tzinfo) if et.tzinfo else datetime.now()) - et.replace(tzinfo=None) if et.tzinfo is None else datetime.now(et.tzinfo) - et
                    hours_since = abs(hours_since.total_seconds() / 3600)
                    cooldown_h = self.cfg.get('cooldown_hours', 4)
                    if hours_since < cooldown_h:
                        return False, f"cooldown: {hours_since:.1f}h < {cooldown_h}h"
                except:
                    pass
        return True, "ok"

    def check_min_hold(self, symbol, action):
        if action not in ('SELL',):
            return True, "ok"
        entry = db.get_position_entry(self.trader_name, symbol)
        if entry:
            et = entry.get('executed_at')
            if et:
                try:
                    if isinstance(et, str):
                        et = datetime.fromisoformat(et.replace('Z', '+00:00'))
                    now = datetime.now()
                    hours_held = abs((now - et.replace(tzinfo=None) if et.tzinfo else (now.replace(tzinfo=et.tzinfo) - et)).total_seconds() / 3600)
                    min_h = self.cfg.get('min_hold_hours', 1)
                    if hours_held < min_h:
                        return False, f"min_hold: {hours_held:.1f}h < {min_h}h"
                except:
                    pass
        return True, "ok"

    def check_already_holding(self, symbol, action, current_position_check=None):
        if action != 'BUY':
            return True, "ok"
        if current_position_check is not None:
            if current_position_check:
                print(f"  [{self.trader_name}] {symbol} already held, checking limit...")
                existing = self.client.get_position_for_symbol(symbol)
                if existing:
                    current_pct = float(existing.market_value) / max(self._get_equity(), 1)
                    max_single = self.cfg.get("max_single_pct", 0.15)
                    if current_pct >= max_single:
                        return False, f"position_full: {current_pct*100:.0f}% >= {max_single*100:.0f}%"
                return True, "ok"
        pos = self.client.get_position_for_symbol(symbol)
        if pos:
            print(f"  [{self.trader_name}] {symbol} already held ({float(pos.qty)} shares)")
        return True, "ok"

    def check_daily_trade_limit(self):
        count = db.get_daily_trade_count(self.trader_name)
        max_trades = self.cfg.get('max_daily_trades', 5)
        if count >= max_trades:
            print(f"  [{self.trader_name}] daily trades {count} >= limit {max_trades}")
            return False, "daily_trade_limit"
        return True, "ok"

    def can_open_position(self, symbol, alloc_pct, side="BUY", current_position_check=None):
        if self.trade_disabled:
            return False, "meltdown"

        if not self.check_daily_loss_limit():
            return False, "daily_loss_limit"

        if not self.check_daily_trade_limit():
            return False, "daily_trade_limit"

        ok, reason = self.check_cooldown(symbol)
        if not ok:
            return False, reason

        if side.upper() == "BUY":
            ok, reason = self.check_already_holding(symbol, side, current_position_check)
            if not ok:
                return False, reason

        if side.upper() == "SELL":
            ok, reason = self.check_min_hold(symbol, side)
            if not ok:
                return False, reason

        max_pos = self.cfg.get("max_positions", 6)
        if self.client.get_position_count() >= max_pos and side.upper() == "BUY":
            found = False
            for p in self.client.get_positions():
                if p.symbol == symbol:
                    found = True
                    break
            if not found:
                return False, "max_positions"

        max_single = self.cfg.get("max_single_pct", 0.15)
        if side.upper() == "BUY":
            existing = self.client.get_position_for_symbol(symbol)
            if existing:
                current_pct = float(existing.market_value) / self.cfg.get("total_capital", 10000)
                if current_pct >= max_single:
                    return False, "single_stock_limit"

        if alloc_pct > max_single:
            return False, "single_stock_limit"

        return True, "ok"

    def _get_equity(self):
        acc = self.client.get_account()
        if acc:
            return float(acc.equity)
        return self.cfg.get("total_capital", 10000)

    def calculate_qty(self, symbol, current_price, alloc_pct):
        equity = self._get_equity()
        allocated = equity * alloc_pct
        if current_price <= 0 or allocated <= 0:
            return 0
        qty = int(allocated / current_price)
        return qty

    def get_trailing_stop_price(self, entry_price, current_price, trailing_pct):
        return round(max(entry_price, current_price * (1 - trailing_pct)), 2)

    def get_stop_loss_price(self, entry_price, pct=0.07):
        return round(entry_price * (1 - pct), 2)

    def get_take_profit_price(self, entry_price, pct=0.15):
        return round(entry_price * (1 + pct), 2)

    def reset_daily_limits(self):
        self.daily_start_equity = None
        self.daily_loss_pct = 0
        self.trade_disabled = False
