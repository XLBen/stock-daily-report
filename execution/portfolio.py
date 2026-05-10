import db
from datetime import datetime

class PortfolioTracker:
    def __init__(self, alpaca_client):
        self.client = alpaca_client

    def snapshot(self):
        positions = self.client.get_positions()
        current_prices = {}
        from data.fetcher import get_current_prices
        symbols = [p.symbol for p in positions]
        if symbols:
            current_prices = get_current_prices(symbols)

        for pos in positions:
            symbol = pos.symbol
            qty = float(pos.qty)
            avg_entry = float(pos.avg_entry_price)
            current_price = current_prices.get(symbol, avg_entry)
            unrealized_pnl = (current_price - avg_entry) * qty
            db.save_snapshot(
                self.client.account_id, symbol, qty,
                avg_entry, current_price, round(unrealized_pnl, 2)
            )

    def get_pnl_summary(self):
        acc = self.client.get_account()
        if not acc:
            return {"equity": 0, "cash": 0, "unrealized_pnl": 0, "positions": 0}
        unrealized = 0
        try:
            mv = float(acc.long_market_value) + float(acc.short_market_value)
            cb = float(acc.last_equity) if hasattr(acc, 'last_equity') and float(acc.last_equity) > 0 else float(acc.cash)
            unrealized = round(mv - cb, 2) if mv and cb else 0
        except:
            pass
        return {
            "trader": self.client.trader,
            "equity": round(float(acc.equity), 2),
            "cash": round(float(acc.cash), 2),
            "buying_power": round(float(acc.buying_power), 2),
            "unrealized_pnl": unrealized,
            "positions": self.client.get_position_count(),
        }

    def print_summary(self):
        s = self.get_pnl_summary()
        print(f"\n📊 [{s['trader']}] Equity=${s['equity']} | Cash=${s['cash']} | Positions={s['positions']} | BuyingPower=${s['buying_power']}")
