import matplotlib
matplotlib.use('Agg') # 🔥 核心修复：强制使用非交互式后端，解决服务器报错
import mplfinance as mpf
import yfinance as yf
import pandas as pd
import os

def generate_chart(symbol, filename=None):
    """
    生成 K 线图并保存为文件
    """
    if not filename:
        filename = f"{symbol}_chart.png"
        
    try:
        # 1. 拉取数据 (过去 3 个月)
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3mo")
        
        # 容错：如果没有数据，尝试缩短周期
        if df.empty:
            print(f"⚠️ {symbol} 3mo 数据为空，尝试 1mo...")
            df = ticker.history(period="1mo")
            
        if df.empty:
            print(f"❌ {symbol} 无法获取K线数据")
            return None

        # 2. 设置样式 (红涨绿跌)
        mc = mpf.make_marketcolors(up='green', down='red', inherit=True)
        s  = mpf.make_mpf_style(marketcolors=mc, style='yahoo')

        # 3. 画图并保存
        mpf.plot(
            df, 
            type='candle', 
            mav=(5, 10, 20), # 均线
            volume=True, 
            style=s, 
            title=f"{symbol} Daily",
            savefig=dict(fname=filename, dpi=100, bbox_inches='tight'),
            figsize=(10, 5)
        )
        
        if os.path.exists(filename):
            return filename
        else:
            return None
            
    except Exception as e:
        print(f"❌ 画图代码报错: {e}")
        return None