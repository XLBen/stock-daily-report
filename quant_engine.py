import pandas as pd
import numpy as np
from scipy.stats import linregress

class QuantEngine:
    def __init__(self, df_dict):
        """
        :param df_dict: 一个字典，包含所有股票的 DataFrame, key 是 symbol
        """
        self.data_pool = df_dict

    # --- 1. Statistical Arbitrage (Pairs Trading) ---
    def find_pair_opportunity(self, target_symbol):
        """
        寻找与目标股票最相关的“对子”，并计算价差 Z-Score
        """
        target_df = self.data_pool.get(target_symbol)
        if target_df is None or len(target_df) < 60: return None

        best_pair = None
        highest_corr = 0
        
        # 1. 在资产池中寻找相关性最高的股票 (Correlation)
        target_closes = target_df['Close'].iloc[-60:] # 观察过去60个交易日
        
        for symbol, df in self.data_pool.items():
            if symbol == target_symbol: continue
            
            other_closes = df['Close'].iloc[-60:]
            if len(other_closes) != len(target_closes): continue
            
            # 计算皮尔逊相关系数
            corr = np.corrcoef(target_closes, other_closes)[0, 1]
            if abs(corr) > abs(highest_corr):
                highest_corr = corr
                best_pair = symbol

        # 如果相关性太低（小于0.8），判定为无有效对冲标的
        if abs(highest_corr) < 0.8: 
            return None

        # 2. 计算价差 (Spread) 和 Z-Score
        pair_df = self.data_pool[best_pair]
        # 对齐索引确保计算准确
        common_idx = target_df.index.intersection(pair_df.index)
        s1 = target_df.loc[common_idx]['Close']
        s2 = pair_df.loc[common_idx]['Close']
        
        ratio = s1 / s2
        mean = ratio.rolling(window=20).mean()
        std = ratio.rolling(window=20).std()
        
        # 计算当前的 Z-Score
        current_ratio = ratio.iloc[-1]
        current_mean = mean.iloc[-1]
        current_std = std.iloc[-1]
        
        if current_std == 0: return None
        zscore = (current_ratio - current_mean) / current_std
        
        return {
            "pair_symbol": best_pair,
            "correlation": round(highest_corr, 2),
            "z_score": round(zscore, 2),
            "action": "Pair Diverged" if abs(zscore) > 2.0 else "Pair Converged"
        }

    # --- 2. Market Making (Inventory-based Limit Orders) ---
    def get_optimal_limit_levels(self, symbol, risk_aversion=0.5):
        """
        基于 Avellaneda-Stoikov 模型的简化适配：
        计算基于波动率的理论最佳挂单位置。
        """
        df = self.data_pool.get(symbol)
        if df is None or len(df) < 20: return None
        
        curr_price = df['Close'].iloc[-1]
        
        # 计算日化波动率
        returns = df['Close'].pct_change().dropna()
        daily_vol = returns.std()
        
        # 风险调整项：波动率越大，挂单距离现价越远
        # 这里的简化逻辑是基于 1 倍日波动率作为散户做市的参考安全边际
        limit_buy = curr_price * (1 - daily_vol * risk_aversion * 2) 
        limit_sell = curr_price * (1 + daily_vol * risk_aversion * 2) 
        
        return {
            "limit_buy": round(limit_buy, 2),
            "limit_sell": round(limit_sell, 2),
            "volatility": round(daily_vol * 100, 2)
        }

    # --- 3. Trend Following (Momentum) ---
    def get_momentum_score(self, symbol):
        """
        计算 TSMOM (时间序列动量) 
        逻辑：收益率 / 波动率 (Risk-adjusted momentum)
        """
        df = self.data_pool.get(symbol)
        if df is None or len(df) < 20: return 0
        
        closes = df['Close']
        lookback = 20 # 20日动量
        
        past_price = closes.iloc[-lookback]
        curr_price = closes.iloc[-1]
        
        returns = closes.pct_change()
        vol = returns.rolling(window=lookback).std().iloc[-1]
        
        if vol == 0 or np.isnan(vol): vol = 0.01
        
        # 动量得分 = 收益率 / 波动率
        raw_ret = (curr_price - past_price) / past_price
        score = raw_ret / vol
        
        return round(score, 2)