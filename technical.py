import pandas as pd
import numpy as np

class TechnicalAnalyzer:
    def __init__(self, df):
        """
        初始化分析器
        :param df: 包含 'Close', 'High', 'Low' 列的 DataFrame
        """
        self.df = df.copy()
        if len(self.df) < 30:
            print("⚠️ 数据不足 30 天，技术指标可能不准确")
        
        # 预先计算所有指标
        self._calculate_indicators()

    def _calculate_indicators(self):
        """计算核心技术指标"""
        close = self.df['Close']
        high = self.df['High']
        low = self.df['Low']

        # 1. 移动平均线 (MA)
        self.df['MA5'] = close.rolling(window=5).mean()
        self.df['MA20'] = close.rolling(window=20).mean() # 生命线
        self.df['MA50'] = close.rolling(window=50).mean() # 中期趋势

        # 2. RSI (相对强弱指标) - 14天
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        self.df['RSI'] = 100 - (100 / (1 + rs))

        # 3. Bollinger Bands (布林带) - 20天, 2倍标准差
        std = close.rolling(window=20).std()
        self.df['BB_Upper'] = self.df['MA20'] + (std * 2)
        self.df['BB_Lower'] = self.df['MA20'] - (std * 2)

        # 4. MACD (12, 26, 9)
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        self.df['MACD'] = exp1 - exp2
        self.df['Signal'] = self.df['MACD'].ewm(span=9, adjust=False).mean()
        self.df['Hist'] = self.df['MACD'] - self.df['Signal']

        # 5. ATR (平均真实波幅) - 用于计算止损
        # TR = Max((High-Low), Abs(High-PrevClose), Abs(Low-PrevClose))
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        self.df['ATR'] = tr.rolling(window=14).mean()

    def analyze(self):
        """生成综合分析报告"""
        if self.df.empty: return None

        # 获取最新一行数据
        curr = self.df.iloc[-1]
        
        result = {
            "price": curr['Close'],
            "indicators": {
                "rsi": round(curr['RSI'], 2) if not pd.isna(curr['RSI']) else 50,
                "ma20": round(curr['MA20'], 2) if not pd.isna(curr['MA20']) else 0,
                "macd": round(curr['MACD'], 4) if not pd.isna(curr['MACD']) else 0,
                "bb_pos": self._get_bb_position(curr)
            },
            "signals": {
                "left_side": self._get_left_side_signal(curr),
                "right_side": self._get_right_side_signal(curr)
            },
            "risk_control": self._get_risk_advice(curr)
        }
        return result

    def _get_bb_position(self, row):
        """计算当前价格在布林带的位置 (0% = 下轨, 100% = 上轨)"""
        if pd.isna(row['BB_Upper']) or pd.isna(row['BB_Lower']): return 50
        width = row['BB_Upper'] - row['BB_Lower']
        if width == 0: return 50
        return ((row['Close'] - row['BB_Lower']) / width) * 100

    def _get_left_side_signal(self, row):
        """
        左侧交易逻辑 (逆势: 抄底/逃顶)
        返回: (策略名称, 建议方向, 描述)
        """
        rsi = row['RSI']
        close = row['Close']
        lower = row['BB_Lower']
        upper = row['BB_Upper']

        # --- 买入逻辑 (抄底) ---
        # 1. 极端: 跌破布林下轨
        if close < lower:
            return ("🌪️ 极端", "强力买入", "跌破布林下轨，极度超卖，此时不接飞刀更待何时？")
        # 2. 中性: RSI < 30
        if rsi < 30:
            return ("😐 中性", "买入", "RSI进入超卖区，处于底部区域，建议分批建仓。")
        # 3. 保守: RSI < 40 且 站回 MA5 (止跌信号)
        if rsi < 40 and close > row['MA5']:
            return ("🛡️ 保守", "试探买入", "超卖后出现止跌回升迹象，右侧确认前可轻仓试错。")

        # --- 卖出逻辑 (逃顶) ---
        # 1. 极端: 突破布林上轨
        if close > upper:
            return ("🌪️ 极端", "强力卖出", "突破布林上轨，极度超买，谨防冲高回落。")
        # 2. 中性: RSI > 70
        if rsi > 70:
            return ("😐 中性", "卖出", "RSI进入超买区，贪婪时刻，建议逐步止盈。")
        # 3. 保守: RSI > 60 且 跌破 MA5 (滞涨信号)
        if rsi > 60 and close < row['MA5']:
            return ("🛡️ 保守", "减仓", "高位滞涨并跌破短均线，建议获利了结。")

        return ("😴 观望", "持有/空仓", "指标处于中间区域，无明显左侧信号。")

    def _get_right_side_signal(self, row):
        """
        右侧交易逻辑 (顺势: 追涨/杀跌)
        返回: (策略名称, 建议方向, 描述)
        """
        close = row['Close']
        ma20 = row['MA20']
        macd = row['MACD']
        signal = row['Signal']
        prev_row = self.df.iloc[-2] # 前一天，用于判断金叉死叉

        # --- 趋势判断 ---
        is_uptrend = close > ma20
        
        # --- 买入逻辑 (做多) ---
        # 1. 极端: 创20日新高 (突破策略)
        # (简单用收盘价 > 上轨做近似，或需要遍历过去20天)
        if close > row['BB_Upper']:
             return ("🚀 极端", "追涨", "股价突破布林上轨，动能极强，适合激进追涨。")
        
        # 2. 中性: MACD 金叉 (水上或水下) 且 站上 MA20
        macd_golden_cross = (prev_row['MACD'] < prev_row['Signal']) and (macd > signal)
        if macd_golden_cross and is_uptrend:
             return ("😐 中性", "加仓", "MACD金叉且站稳生命线，趋势确立，建议加仓。")
             
        # 3. 保守: 上升趋势中回踩 MA20 (均线战法)
        # 价格在 MA20 上方 2% 以内
        if is_uptrend and (close <= ma20 * 1.02) and (close >= ma20):
             return ("🛡️ 保守", "低吸", "上升趋势中的黄金回踩点，风险收益比极佳。")

        # --- 卖出逻辑 (做空/离场) ---
        # 1. 极端: 跌破 ATR 止损 (这里用跌破下轨代替趋势崩塌)
        if close < row['BB_Lower']:
             return ("🌪️ 极端", "清仓", "趋势完全崩塌，跌破下轨，必须离场。")
             
        # 2. 中性: 死叉 或 跌破 MA20
        if close < ma20:
             return ("😐 中性", "离场", "跌破20日生命线，中期趋势转弱，建议离场观望。")
             
        return ("😴 观望", "持有", "当前处于趋势之中或震荡，无明确开仓/平仓信号。")

    def _get_risk_advice(self, row):
        """
        计算止损位和持仓建议
        """
        close = row['Close']
        atr = row['ATR'] if not pd.isna(row['ATR']) else (close * 0.03)
        ma20 = row['MA20'] if not pd.isna(row['MA20']) else close
        
        # 1. 吊灯止损 (Chandelier Exit): 最高价回撤 2-3倍 ATR (这里简化为现价 - 2ATR)
        stop_loss_price = close - (2 * atr)
        
        # 2. 支撑位
        support_price = ma20 # 以生命线为支撑
        
        return {
            "stop_loss_price": round(stop_loss_price, 2),
            "support_price": round(support_price, 2),
            "atr": round(atr, 2),
            "advice": f"如果你的成本在 ${round(ma20, 2)} 以上，当前跌破概率增加，建议设好 ${round(stop_loss_price, 2)} 的硬止损。"
        }