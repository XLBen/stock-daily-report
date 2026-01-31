import matplotlib
matplotlib.use('Agg')
import mplfinance as mpf
import yfinance as yf
import pandas as pd
import numpy as np
import os
from scipy.stats import linregress

def calculate_regression(series):
    try:
        y = series.values
        x = np.arange(len(y))
        slope, intercept, _, _, _ = linregress(x, y)
        reg_line = slope * x + intercept
        residuals = y - reg_line
        std_dev = np.std(residuals)
        return reg_line, reg_line + (2 * std_dev), reg_line - (2 * std_dev)
    except:
        return None, None, None

def generate_chart(symbol, filename=None):
    if not filename: filename = f"{symbol}_chart.png"
    if os.path.exists(filename):
        try: os.remove(filename)
        except: pass

    try:
        print(f"🎨 [绘图] {symbol}...")
        ticker = yf.Ticker(symbol)
        df = pd.DataFrame()
        for p in ["6mo", "3mo", "1mo"]:
            df = ticker.history(period=p, interval="1d", auto_adjust=True)
            if not df.empty and len(df)>20: break
        
        if df.empty: return None

        df.index.name = 'Date'
        ma20 = df['Close'].rolling(window=20).mean()
        reg_line, upper, lower = calculate_regression(df['Close'])
        
        add_plots = []
        # 🔵 MA20: 蓝色实线
        if not ma20.isnull().all():
            add_plots.append(mpf.make_addplot(ma20, color='blue', width=1.5, label='MA20'))
            
        # 🟠 回归通道: 橙色中轴, 灰色虚线边框
        if reg_line is not None:
            add_plots.append(mpf.make_addplot(reg_line, color='#FF8C00', width=2.0)) # DarkOrange
            add_plots.append(mpf.make_addplot(upper, color='gray', width=1.0, linestyle='dashed'))
            add_plots.append(mpf.make_addplot(lower, color='gray', width=1.0, linestyle='dashed'))

        s = mpf.make_mpf_style(base_mpf_style='charles', rc={'font.size': 8})
        
        mpf.plot(
            df, type='candle', volume=True, addplot=add_plots, style=s,
            title=f"{symbol} (Blue=MA20, Orange=Trend)",
            savefig=dict(fname=filename, dpi=80, bbox_inches='tight'),
            figsize=(10, 5), tight_layout=True
        )
        return filename
    except Exception as e:
        print(f"❌ 绘图失败: {e}")
        return None