import pandas as pd
import numpy as np

class TechnicalAnalyzer:
    def __init__(self, df):
        self.df = df.copy()
        if len(self.df) < 30:
            print("⚠️  数据不足 (<30 行)")
        self._calculate_all()

    def _calculate_all(self):
        self._calc_ma()
        self._calc_rsi()
        self._calc_bb()
        self._calc_macd()
        self._calc_atr()
        self._calc_adx()
        self._calc_stoch_rsi()
        self._calc_williams_r()
        self._calc_cci()
        self._calc_volume()
        self._calc_risk_metrics()

    def _calc_ma(self):
        close = self.df['Close']
        self.df['MA5'] = close.rolling(5).mean()
        self.df['MA20'] = close.rolling(20).mean()
        self.df['MA50'] = close.rolling(50).mean()
        self.df['MA200'] = close.rolling(200).mean() if len(close) >= 200 else pd.Series([np.nan] * len(close), index=close.index)

    def _calc_rsi(self, period=14):
        close = self.df['Close']
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / (loss + 1e-10)
        self.df['RSI'] = 100 - (100 / (1 + rs))
        self.df['RSI'] = self.df['RSI'].clip(0, 100)

    def _calc_bb(self, period=20, std_mult=2):
        close = self.df['Close']
        ma = close.rolling(period).mean()
        std = close.rolling(period).std()
        self.df['BB_Mid'] = ma
        self.df['BB_Upper'] = ma + std * std_mult
        self.df['BB_Lower'] = ma - std * std_mult
        self.df['BB_Width'] = (self.df['BB_Upper'] - self.df['BB_Lower']) / (ma + 1e-10) * 100

    def _calc_macd(self, fast=12, slow=26, signal=9):
        close = self.df['Close']
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        self.df['MACD'] = ema_fast - ema_slow
        self.df['MACD_Signal'] = self.df['MACD'].ewm(span=signal, adjust=False).mean()
        self.df['MACD_Hist'] = self.df['MACD'] - self.df['MACD_Signal']

    def _calc_atr(self, period=14):
        high, low, close = self.df['High'], self.df['Low'], self.df['Close'].shift(1)
        tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
        self.df['ATR'] = tr.rolling(period).mean()

    def _calc_adx(self, period=14):
        high, low, close = self.df['High'], self.df['Low'], self.df['Close']
        tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        up = high.diff()
        down = -low.diff()
        plus_dm = up.where((up > down) & (up > 0), 0)
        minus_dm = down.where((down > up) & (down > 0), 0)
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / (atr + 1e-10))
        minus_di = 100 * (minus_dm.rolling(period).mean() / (atr + 1e-10))
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
        self.df['ADX'] = dx.rolling(period).mean().round(2)
        self.df['Plus_DI'] = plus_di.round(2)
        self.df['Minus_DI'] = minus_di.round(2)

    def _calc_stoch_rsi(self, period=14, smooth_k=3, smooth_d=3):
        rsi = self.df['RSI'].fillna(50)
        rsi_min = rsi.rolling(period).min()
        rsi_max = rsi.rolling(period).max()
        stoch = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-10) * 100
        self.df['Stoch_K'] = stoch.rolling(smooth_k).mean()
        self.df['Stoch_D'] = self.df['Stoch_K'].rolling(smooth_d).mean()

    def _calc_williams_r(self, period=14):
        high, low, close = self.df['High'], self.df['Low'], self.df['Close']
        highest = high.rolling(period).max()
        lowest = low.rolling(period).min()
        self.df['Williams_R'] = ((highest - close) / (highest - lowest + 1e-10)) * -100

    def _calc_cci(self, period=20):
        tp = (self.df['High'] + self.df['Low'] + self.df['Close']) / 3
        sma = tp.rolling(period).mean()
        mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        self.df['CCI'] = (tp - sma) / (0.015 * mad + 1e-10)

    def _calc_volume(self):
        self.df['Volume_SMA20'] = self.df['Volume'].rolling(20).mean()
        self.df['Volume_Ratio'] = self.df['Volume'] / (self.df['Volume_SMA20'] + 1e-10)
        self.df['OBV'] = (np.sign(self.df['Close'].diff()) * self.df['Volume']).cumsum()
        self.df['OBV_MA20'] = self.df['OBV'].rolling(20).mean()

    def _calc_risk_metrics(self, lookback=60):
        close = self.df['Close']
        returns = close.pct_change().dropna()

        if len(returns) < lookback:
            lookback = max(len(returns), 20)

        recent_ret = returns.iloc[-lookback:]
        annual_factor = 252

        self.df['Sharpe'] = np.nan
        self.df['Max_DD'] = np.nan
        self.df['Return_60d'] = np.nan

        if len(recent_ret) > 0:
            mean_ret = recent_ret.mean()
            std_ret = recent_ret.std()
            sharpe = (mean_ret / (std_ret + 1e-10)) * np.sqrt(annual_factor)
            cumulative = (1 + recent_ret).cumprod()
            peak = cumulative.cummax()
            drawdown = (cumulative - peak) / peak
            max_dd = drawdown.min()

            rolling_sharpe = pd.Series(
                [sharpe] * len(self.df),
                index=self.df.index
            )
            rolling_maxdd = pd.Series(
                [max_dd] * len(self.df),
                index=self.df.index
            )
            self.df['Sharpe'] = rolling_sharpe.fillna(0)
            self.df['Max_DD'] = rolling_maxdd.fillna(0)
            self.df['Return_60d'] = (close / close.shift(lookback) - 1).fillna(0)

    def analyze(self):
        if self.df.empty:
            return None
        curr = self.df.iloc[-1]
        prev = self.df.iloc[-2] if len(self.df) > 1 else curr

        bb_pos = self._get_bb_position(curr)

        ma20_trend = "flat"
        if not pd.isna(curr['MA20']) and not pd.isna(curr['Close']):
            ma20_slope = curr['MA20'] - self.df['MA20'].iloc[-5] if len(self.df) >= 5 else 0
            ma20_trend = "above" if curr['Close'] > curr['MA20'] else "below"
            if ma20_slope > 0:
                ma20_trend += "_rising"
            elif ma20_slope < 0:
                ma20_trend += "_falling"

        ma_cross = "none"
        if not pd.isna(curr.get('MA20')) and not pd.isna(curr.get('MA50')):
            prev_ma20, prev_ma50 = self.df['MA20'].iloc[-2], self.df['MA50'].iloc[-2]
            curr_ma20, curr_ma50 = curr['MA20'], curr['MA50']
            if prev_ma20 <= prev_ma50 and curr_ma20 > curr_ma50:
                ma_cross = "golden_cross"
            elif prev_ma20 >= prev_ma50 and curr_ma20 < curr_ma50:
                ma_cross = "death_cross"

        obv_trend = "flat"
        if not pd.isna(curr.get('OBV')) and not pd.isna(curr.get('OBV_MA20')):
            obv_trend = "up" if curr['OBV'] > curr['OBV_MA20'] else "down"

        atr_pct = round(float(curr['ATR'] / curr['Close'] * 100), 2) if not pd.isna(curr.get('ATR')) and curr['Close'] != 0 else 0

        return {
            "price": round(float(curr['Close']), 2),
            "indicators": {
                "rsi": round(float(curr['RSI']), 2) if not pd.isna(curr['RSI']) else 50,
                "bb_position": round(bb_pos, 2),
                "macd": round(float(curr['MACD']), 4) if not pd.isna(curr['MACD']) else 0,
                "macd_signal": round(float(curr['MACD_Signal']), 4) if not pd.isna(curr.get('MACD_Signal')) else 0,
                "macd_hist": round(float(curr['MACD_Hist']), 4) if not pd.isna(curr.get('MACD_Hist')) else 0,
                "adx": round(float(curr['ADX']), 2) if not pd.isna(curr.get('ADX')) else 0,
                "plus_di": round(float(curr['Plus_DI']), 2) if not pd.isna(curr.get('Plus_DI')) else 0,
                "minus_di": round(float(curr['Minus_DI']), 2) if not pd.isna(curr.get('Minus_DI')) else 0,
                "stoch_k": round(float(curr['Stoch_K']), 2) if not pd.isna(curr.get('Stoch_K')) else 50,
                "stoch_d": round(float(curr['Stoch_D']), 2) if not pd.isna(curr.get('Stoch_D')) else 50,
                "williams_r": round(float(curr['Williams_R']), 2) if not pd.isna(curr.get('Williams_R')) else -50,
                "cci": round(float(curr['CCI']), 2) if not pd.isna(curr.get('CCI')) else 0,
                "bb_width": round(float(curr['BB_Width']), 2) if not pd.isna(curr.get('BB_Width')) else 0,
                "volume_ratio": round(float(curr['Volume_Ratio']), 2) if not pd.isna(curr.get('Volume_Ratio')) else 1,
                "obv_trend": obv_trend,
                "atr_pct": atr_pct,
                "beta": round(float(self._calc_beta()), 2),
                "sharpe": round(float(curr['Sharpe']), 3) if not pd.isna(curr.get('Sharpe')) else 0,
                "max_drawdown": round(float(curr['Max_DD']) * 100, 2) if not pd.isna(curr.get('Max_DD')) else 0,
                "return_60d": round(float(curr['Return_60d']) * 100, 2) if not pd.isna(curr.get('Return_60d')) else 0,
                "ma20": round(float(curr['MA20']), 2) if not pd.isna(curr.get('MA20')) else 0,
                "ma50": round(float(curr['MA50']), 2) if not pd.isna(curr.get('MA50')) else 0,
                "ma200": round(float(curr['MA200']), 2) if not pd.isna(curr.get('MA200')) else 0,
                "ma20_trend": ma20_trend,
                "ma_cross": ma_cross,
            },
            "signals": {
                "left_side": self._get_left_side_signal(curr),
                "right_side": self._get_right_side_signal(curr)
            },
            "trade_setup": self._get_trade_setup(curr)
        }

    def _get_bb_position(self, row):
        if pd.isna(row['BB_Upper']) or pd.isna(row['BB_Lower']):
            return 50
        width = row['BB_Upper'] - row['BB_Lower']
        if width == 0:
            return 50
        return ((row['Close'] - row['BB_Lower']) / width) * 100

    def _get_left_side_signal(self, row):
        rsi_val = row['RSI'] if not pd.isna(row['RSI']) else 50
        bb_lower = row['BB_Lower'] if not pd.isna(row['BB_Lower']) else 0
        bb_upper = row['BB_Upper'] if not pd.isna(row['BB_Upper']) else 0
        will_val = row['Williams_R'] if not pd.isna(row.get('Williams_R')) else -50

        if row['Close'] < bb_lower or will_val < -90:
            return ("🌪️ 极端", "强力买入", "跌破下轨 + 极度超卖")
        if rsi_val < 30:
            return ("😐 中性", "买入", "RSI超卖")
        if row['Close'] > bb_upper or will_val > -10:
            return ("🌪️ 极端", "强力卖出", "突破上轨 + 极度超买")
        if rsi_val > 70:
            return ("😐 中性", "卖出", "RSI超买")
        return ("😴 观望", "持有", "无明显信号")

    def _get_right_side_signal(self, row):
        is_uptrend = not pd.isna(row.get('MA20')) and row['Close'] > row['MA20']
        macd_val = row['MACD'] if not pd.isna(row['MACD']) else 0
        signal_val = row['MACD_Signal'] if not pd.isna(row.get('MACD_Signal')) else 0
        adx_val = row['ADX'] if not pd.isna(row.get('ADX')) else 0

        if row['Close'] > row['BB_Upper'] and adx_val > 25:
            return ("🚀 极端", "追涨", "突破上轨 + 强趋势")
        if is_uptrend and macd_val > signal_val and macd_val > 0:
            return ("😐 中性", "加仓", "趋势向上且金叉")
        if row['Close'] < row['BB_Lower']:
            return ("🌪️ 极端", "清仓", "趋势崩塌")
        if not is_uptrend:
            return ("😐 中性", "离场", "跌破生命线")
        return ("😴 观望", "持有", "趋势延续中")

    def _get_trade_setup(self, row):
        close = row['Close']
        atr = row['ATR'] if not pd.isna(row['ATR']) else close * 0.03
        ma20 = row['MA20'] if not pd.isna(row['MA20']) else close
        bb_lower = row['BB_Lower'] if not pd.isna(row['BB_Lower']) else close * 0.95

        stop_loss = close - (2 * atr)
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

    def _calc_rsi_at(self, df, position):
        if len(df) < abs(position) + 14:
            return None
        idx = df.index[position]
        if idx not in df.index:
            return None
        return round(float(df.loc[idx, 'RSI']), 2) if not pd.isna(df.loc[idx, 'RSI']) else None

    def _calc_beta(self, lookback=60):
        close = self.df['Close']
        returns = close.pct_change().dropna()
        if len(returns) < lookback:
            lookback = max(2, len(returns))
        recent = returns.iloc[-lookback:]
        std = recent.std()
        if std is None or np.isnan(std) or std == 0:
            return 1.0
        implied_vol = std * np.sqrt(252)
        return round(implied_vol / 0.15, 2)
