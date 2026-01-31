import mplfinance as mpf
import yfinance as yf
import pandas as pd
import os

def generate_chart(symbol, filename="chart_tmp.png"):
    """
    生成 K 线图并保存为文件
    包含: K线, MA5/MA20均线, 成交量
    """
    try:
        # 1. 拉取数据 (过去 3 个月)
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3mo")
        
        if df.empty:
            return None

        # 2. 设置样式
        # 使用 'yahoo' 风格，最接近大家习惯的红涨绿跌
        mc = mpf.make_marketcolors(up='green', down='red', inherit=True)
        s  = mpf.make_mpf_style(marketcolors=mc, style='yahoo')

        # 3. 添加均线 (MA5, MA20)
        # mplfinance 会自动计算并画上去
        mav = (5, 20)

        # 4. 画图并保存
        # type='candle': 蜡烛图
        # volume=True: 显示成交量
        # savefig: 保存路径
        mpf.plot(
            df, 
            type='candle', 
            mav=mav, 
            volume=True, 
            style=s, 
            title=f"{symbol} Daily Chart",
            savefig=dict(fname=filename, dpi=100, bbox_inches='tight'),
            figsize=(10, 6) # 图片尺寸
        )
        
        return filename
    except Exception as e:
        print(f"❌ 画图失败: {e}")
        return None