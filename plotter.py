import matplotlib
matplotlib.use('Agg') # 强制后台画图
import mplfinance as mpf
import yfinance as yf
import pandas as pd
import os

def generate_chart(symbol, filename=None):
    """
    生成 K 线图并保存为文件 (V4.2 强力版)
    """
    if not filename:
        filename = f"{symbol}_chart.png"
    
    # 清理旧文件
    if os.path.exists(filename):
        try: os.remove(filename)
        except: pass

    try:
        print(f"🎨 [绘图] 正在获取 {symbol} 数据...")
        
        # 1. 尝试获取数据 (阶梯式降级策略)
        # 很多时候 GitHub IP 会被限制，导致长周期数据拉不到，我们尝试缩短周期
        ticker = yf.Ticker(symbol)
        df = pd.DataFrame()
        
        for period in ["3mo", "1mo", "5d"]:
            try:
                # auto_adjust=True 可以修正拆股和分红导致的断层
                df = ticker.history(period=period, interval="1d", auto_adjust=True)
                if not df.empty and len(df) >= 3: # 至少要有3根K线才能画图
                    print(f"   ✅ 获取到 {period} 数据: {len(df)} 行")
                    break
            except Exception as e:
                print(f"   ⚠️ 获取 {period} 失败: {e}")
                continue
        
        if df.empty:
            print(f"❌ {symbol} 所有周期数据获取均失败，无法画图")
            return None

        # 2. 数据清洗 (mplfinance 对索引格式要求很严)
        df.index.name = 'Date'

        # 3. 设置样式
        # 使用最简单的 'charles' 风格，兼容性最好
        s = mpf.make_mpf_style(base_mpf_style='charles', rc={'font.size': 8})

        # 4. 画图
        # volume=True 如果数据里没有 Volume 列会报错，这里做个判断
        has_volume = 'Volume' in df.columns
        
        mpf.plot(
            df, 
            type='candle', 
            mav=(5, 10), 
            volume=has_volume, 
            style=s, 
            title=f"{symbol}",
            savefig=dict(fname=filename, dpi=80, bbox_inches='tight'), # 降低 DPI 提高速度
            figsize=(8, 4),
            tight_layout=True
        )
        
        if os.path.exists(filename):
            print(f"✅ 图表已保存: {filename}")
            return filename
        else:
            print(f"❌ 图表保存失败: 文件未生成")
            return None
            
    except Exception as e:
        # 这里会打印出具体的报错原因，非常重要！
        print(f"❌ {symbol} 画图崩溃: {str(e)}")
        import traceback
        traceback.print_exc()
        return None