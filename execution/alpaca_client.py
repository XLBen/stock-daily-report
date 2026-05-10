from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus, QueryOrderStatus
from config import ACCOUNTS


class AlpacaPaperClient:
    def __init__(self, trader_name):
        cfg = ACCOUNTS[trader_name]
        self.trader = trader_name
        self.account_id = trader_name
        self.max_positions = cfg["max_positions"]
        self.max_single_pct = cfg["max_single_pct"]
        self.total_capital = cfg["total_capital"]
        self.client = None
        self._valid = False
        if cfg["api_key"] and cfg["secret_key"]:
            try:
                self.client = TradingClient(
                    api_key=cfg["api_key"],
                    secret_key=cfg["secret_key"],
                    paper=cfg["paper"],
                )
                self._valid = True
            except Exception as e:
                print(f"  [{self.trader}] Alpaca init failed: {e}")
        else:
            print(f"  [{self.trader}] Alpaca API Key not configured (simulation mode)")

    def get_account(self):
        if not self._valid: return None
        try:
            return self.client.get_account()
        except Exception as e:
            print(f"  [{self.trader}] get_account error: {e}")
            return None

    def get_buying_power(self):
        acc = self.get_account()
        if acc:
            return float(acc.buying_power)
        return 0

    def get_cash(self):
        acc = self.get_account()
        if acc:
            return float(acc.cash)
        return 0

    def get_positions(self):
        if not self._valid: return []
        try:
            return self.client.get_all_positions()
        except Exception as e:
            print(f"  [{self.trader}] get_positions error: {e}")
            return []

    def get_position_count(self):
        return len(self.get_positions())

    def get_position_for_symbol(self, symbol):
        if not self._valid: return None
        try:
            return self.client.get_open_position(symbol)
        except:
            return None

    def submit_market_order(self, symbol, qty, side):
        if not self._valid or qty <= 0:
            return None
        try:
            order_data = MarketOrderRequest(
                symbol=symbol, qty=qty,
                side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            order = self.client.submit_order(order_data)
            print(f"  [{self.trader}] {side} {qty} {symbol} @ MARKET -> {order.id}")
            return order
        except Exception as e:
            print(f"  [{self.trader}] order error ({symbol} {side}): {e}")
            return None

    def submit_limit_order(self, symbol, qty, side, limit_price, time_in_force=None):
        if not self._valid or qty <= 0:
            return None
        if time_in_force is None:
            time_in_force = TimeInForce.DAY
        try:
            order_data = LimitOrderRequest(
                symbol=symbol, qty=qty,
                side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
                limit_price=limit_price,
                time_in_force=time_in_force,
            )
            order = self.client.submit_order(order_data)
            print(f"  [{self.trader}] {side} {qty} {symbol} @ LIMIT ${limit_price:.2f} -> {order.id}")
            return order
        except Exception as e:
            print(f"  [{self.trader}] limit order error ({symbol} {side}): {e}")
            return None

    def cancel_all_orders(self):
        if not self._valid: return
        try:
            self.client.cancel_orders()
        except: pass

    def cancel_order(self, order_id):
        if not self._valid: return
        try:
            self.client.cancel_order_by_id(order_id)
        except: pass

    def close_position(self, symbol):
        if not self._valid: return
        try:
            self.client.close_position(symbol)
            print(f"  [{self.trader}] closed position: {symbol}")
        except: pass

    def close_all_positions(self):
        if not self._valid: return
        try:
            self.client.close_all_positions()
            print(f"  [{self.trader}] all positions closed")
        except: pass

    def get_order(self, order_id):
        if not self._valid: return None
        try:
            return self.client.get_order_by_id(order_id)
        except:
            return None

    def is_account_valid(self):
        return self._valid
