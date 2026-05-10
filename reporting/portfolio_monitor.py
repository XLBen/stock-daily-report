from datetime import datetime
from data.fetcher import get_current_prices, fetch_intraday
from reporting.formatter import format_portfolio_report, format_major_move_alert
from reporting.discord import DiscordReporter
from config import MAJOR_MOVE_THRESHOLD_PCT, TIMEZONE


class PortfolioMonitor:

    def __init__(self, alpaca_client):
        self.client = alpaca_client
        self.trader_name = alpaca_client.trader
        self.discord = DiscordReporter()

    def _get_holdings(self):
        positions = self.client.get_positions()
        if not positions:
            return []
        symbols = [p.symbol for p in positions]
        prices = get_current_prices(symbols)
        holdings = []
        for pos in positions:
            sym = pos.symbol
            cp = prices.get(sym)
            if cp is None:
                continue
            try:
                entry = float(pos.avg_entry_price)
                qty = float(pos.qty)
                change_pct = (cp - entry) / entry * 100 if entry > 0 else 0
                holdings.append({
                    'symbol': sym,
                    'qty': qty,
                    'entry_price': entry,
                    'current_price': cp,
                    'change_pct': round(change_pct, 2),
                    'market_value': round(cp * qty, 2),
                })
            except:
                continue
        return holdings

    def send_report(self, report_type):
        holdings = self._get_holdings()
        if not holdings:
            return
        embed = format_portfolio_report(self.trader_name, holdings, report_type)
        self.discord._send_webhook(embed)

    def check_major_moves(self):
        positions = self.client.get_positions()
        if not positions:
            return
        symbols = [p.symbol for p in positions]
        prices = get_current_prices(symbols)

        for pos in positions:
            sym = pos.symbol
            cp = prices.get(sym)
            if cp is None:
                continue
            try:
                df = fetch_intraday(sym, period="1d")
                if df is None or df.empty or len(df) < 3:
                    continue
                open_price = float(df['Open'].iloc[0])
                day_change = (cp - open_price) / open_price * 100 if open_price > 0 else 0
            except:
                day_change = 0

            if abs(day_change) >= MAJOR_MOVE_THRESHOLD_PCT:
                try:
                    entry = float(pos.avg_entry_price)
                    qty = float(pos.qty)
                    change_pct = (cp - entry) / entry * 100 if entry > 0 else 0
                    embed, caption = format_major_move_alert(
                        self.trader_name, sym, qty, entry, cp,
                        open_price, round(day_change, 2), round(change_pct, 2)
                    )
                    if caption and embed:
                        chart_path = None
                        try:
                            from plotter import generate_daily_chart
                            chart_path = generate_daily_chart(sym)
                        except:
                            pass
                        self.discord.send_chart(caption, embed, chart_path)
                except:
                    continue
