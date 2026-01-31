import pandas as pd
import numpy as np

class TechnicalAnalyzer:
    def __init__(self, df):
        self.df = df.copy()
        if len(self.df) < 30:
            print("⚠️ 数据不足")
        self._calculate_indicators()

    def _calculate_indicators(self):
        close = self.df['Close']
        high = self.df['High']
        low = self.df['Low']

        # 1. 均线
        self.df['MA5'] = close.rolling(window=5).mean()
        self.df['MA20'] = close.rolling(window=20).mean()

        # 2. RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        self.df['RSI'] = 100 - (100 / (1 + rs))

        # 3. 布林带
        std = close.rolling(window=20).std()
        self.df['BB_Upper'] = self.df['MA20'] + (std * 2)
        self.df['BB_Lower'] = self.df['MA20'] - (std * 2)

        # 4. MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        self.df['MACD'] = exp1 - exp2
        self.df['Signal'] = self.df['MACD'].ewm(span=9, adjust=False).mean()

        # 5. ATR (用于止损)
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        self.df['ATR'] = tr.rolling(window=14).mean()

    def analyze(self):
        if self.df.empty: return None
        curr = self.df.iloc[-1]
        
        return {
            "price": curr['Close'],
            "indicators": {
                "rsi": round(curr['RSI'], 2) if not pd.isna(curr['RSI']) else 50,
                "bb_pos": self._get_bb_position(curr),
                "macd": round(curr['MACD'], 4) if not pd.isna(curr['MACD']) else 0
            },
            "signals": {
                "left_side": self._get_left_side_signal(curr),
                "right_side": self._get_right_side_signal(curr)
            },
            # 此处包含风控和加仓建议
            "trade_setup": self._get_trade_setup(curr)
        }

    def _get_bb_position(self, row):
        if pd.isna(row['BB_Upper']) or pd.isna(row['BB_Lower']): return 50
        width = row['BB_Upper'] - row['BB_Lower']
        if width == 0: return 50
        return ((row['Close'] - row['BB_Lower']) / width) * 100

    def _get_left_side_signal(self, row):
        # 简化版逻辑
        if row['Close'] < row['BB_Lower']: return ("🌪️ 极端", "强力买入", "跌破下轨超卖")
        if row['RSI'] < 30: return ("😐 中性", "买入", "RSI超卖")
        if row['Close'] > row['BB_Upper']: return ("🌪️ 极端", "强力卖出", "突破上轨超买")
        if row['RSI'] > 70: return ("😐 中性", "卖出", "RSI超买")
        return ("😴 观望", "持有", "无明显信号")

    def _get_right_side_signal(self, row):
        is_uptrend = row['Close'] > row['MA20']
        if row['Close'] > row['BB_Upper']: return ("🚀 极端", "追涨", "突破上轨加速")
        if is_uptrend and row['MACD'] > row['Signal']: return ("😐 中性", "加仓", "趋势向上且金叉")
        if row['Close'] < row['BB_Lower']: return ("🌪️ 极端", "清仓", "趋势崩塌")
        if row['Close'] < row['MA20']: return ("😐 中性", "离场", "跌破生命线")
        return ("😴 观望", "持有", "趋势延续中")

    def _get_trade_setup(self, row):
        """
        计算具体的买卖点位建议
        """
        close = row['Close']
        atr = row['ATR'] if not pd.isna(row['ATR']) else close * 0.03
        ma20 = row['MA20']
        bb_lower = row['BB_Lower']
        
        # 1. 止损建议 (Sell/Stop Logic)
        stop_loss = close - (2 * atr)
        
        # 2. 加仓建议 (Buy/Add Logic)
        # 如果是上升趋势(价格>MA20)，建议在 MA20 附近低吸
        # 如果是下降趋势(价格<MA20)，建议在 布林下轨 附近博反弹
        if close > ma20:
            buy_target = ma20
            buy_desc = "趋势线(MA20)附近"
        else:
            buy_target = bb_lower
            buy_desc = "布林下轨支撑位"
            
        return {
            "stop_loss_price": round(stop_loss, 2),
            "support_desc": f"MA20(${round(ma20, 2)})",
            "buy_target_price": round(buy_target, 2),
            "buy_desc": buy_desc
        }