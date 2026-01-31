import matplotlib
matplotlib.use('Agg') # 强制后台画图，修复 GitHub Actions 报错
import mplfinance as mpf
import yfinance as yf
import pandas as pd
import os

def generate_chart(symbol, filename=None):
    """生成 K 线图"""
    if not filename:
        filename = f"{symbol}_chart.png"
        
    try:
        # 1. 拉取数据
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3mo")
        
        if df.empty:
            print(f"❌ {symbol} 历史数据为空")
            return None

        # 2. 设置样式
        mc = mpf.make_marketcolors(up='green', down='red', inherit=True)
        s  = mpf.make_mpf_style(marketcolors=mc, style='yahoo')
        mav = (5, 20)

        # 3. 画图
        mpf.plot(
            df, 
            type='candle', 
            mav=mav, 
            volume=True, 
            style=s, 
            title=f"{symbol} Daily Chart",
            savefig=dict(fname=filename, dpi=100, bbox_inches='tight'),
            figsize=(10, 6)
        )
        print(f"🎨 图表已生成: {filename}")
        return filename
    except Exception as e:
        print(f"❌ 画图失败: {e}")
        return None