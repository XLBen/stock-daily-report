import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import numpy as np
from scipy import stats
import os
import traceback

CHART_DIR = 'charts'
os.makedirs(CHART_DIR, exist_ok=True)


def generate_daily_chart(symbol, df=None):
    try:
        if df is None:
            import yfinance as yf
            df = yf.Ticker(symbol).history(period="3mo")
        if df.empty or len(df) < 20:
            return None

        df = df.copy()
        df.index.name = 'Date'
        df['MA20'] = df['Close'].rolling(window=20).mean()

        add_plots = [
            mpf.make_addplot(df['MA20'], color='blue', width=0.8, label='MA20'),
        ]

        if len(df) >= 30:
            x = np.arange(len(df))
            y = df['Close'].values
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            reg_line = slope * x + intercept
            std_dev = np.std(y - reg_line)
            upper = reg_line + 2 * std_dev
            lower = reg_line - 2 * std_dev
            add_plots.append(mpf.make_addplot(reg_line, color='orange', width=0.6, linestyle='--', label='Regression'))
            add_plots.append(mpf.make_addplot(upper, color='gray', width=0.4, linestyle=':', label='Upper 2σ'))
            add_plots.append(mpf.make_addplot(lower, color='gray', width=0.4, linestyle=':', label='Lower 2σ'))

        filepath = os.path.join(CHART_DIR, f"{symbol.replace('.', '_')}_daily.png")
        mpf.plot(df, type='candle', style='charles',
                 title=f'{symbol} - 3 Month Daily',
                 ylabel='Price (USD)',
                 volume=False,
                 addplot=add_plots,
                 figsize=(10, 6),
                 savefig=filepath)
        plt.close('all')
        return filepath
    except:
        traceback.print_exc()
        return None


def generate_intraday_chart(symbol, df=None):
    try:
        if df is None:
            import yfinance as yf
            df = yf.Ticker(symbol).history(period="5d", interval="5m")
        if df.empty or len(df) < 20:
            return None

        df = df.copy()
        df.index.name = 'Time'
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['VWAP'] = (df['Volume'] * (df['High'] + df['Low'] + df['Close']) / 3).cumsum() / df['Volume'].cumsum()

        add_plots = [
            mpf.make_addplot(df['MA20'], color='blue', width=0.6, label='MA20'),
            mpf.make_addplot(df['VWAP'], color='purple', width=0.6, linestyle='-.', label='VWAP'),
        ]

        filepath = os.path.join(CHART_DIR, f"{symbol.replace('.', '_')}_intraday.png")
        mpf.plot(df, type='candle', style='charles',
                 title=f'{symbol} - 5 Day Intraday',
                 ylabel='Price (USD)',
                 volume=False,
                 addplot=add_plots,
                 figsize=(12, 6),
                 savefig=filepath)
        plt.close('all')
        return filepath
    except:
        traceback.print_exc()
        return None
