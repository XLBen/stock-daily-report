import smtplib
from email.mime.text import MIMEText
from email.header import Header
import yfinance as yf
import os
from datetime import datetime

# 你的关注列表
STOCKS = ['AAPL', 'MSFT', 'NVDA']

def get_stock_data():
    msg_content = "今日量化简报 (MA5策略观察)：\n\n"
    
    for symbol in STOCKS:
        try:
            ticker = yf.Ticker(symbol)
            # 修改点1：我们需要更多历史数据来计算均线，这里拉取过去1个月
            hist = ticker.history(period="1mo")
            
            if len(hist) >= 5:
                # 获取最新一天的收盘价
                current_price = hist['Close'].iloc[-1]
                
                # 修改点2：计算 5日移动平均线 (MA5)
                # rolling(5) 表示取5天窗口，mean() 表示求平均
                hist['MA5'] = hist['Close'].rolling(window=5).mean()
                ma5_price = hist['MA5'].iloc[-1]
                
                # 修改点3：进行逻辑判断 (量化分析的核心)
                if current_price > ma5_price:
                    trend = "📈 强势 (高于均线)"
                else:
                    trend = "📉 弱势 (低于均线)"
                
                # 计算偏离度 (看看现在的价格偏离平均值多少百分比)
                diff_percent = ((current_price - ma5_price) / ma5_price) * 100
                
                msg_content += f"【{symbol}】\n"
                msg_content += f"现价: ${current_price:.2f}\n"
                msg_content += f"MA5均价: ${ma5_price:.2f}\n"
                msg_content += f"趋势判断: {trend}\n"
                msg_content += f"偏离幅度: {diff_percent:+.2f}%\n"
                msg_content += "-" * 20 + "\n"
                
            else:
                msg_content += f"{symbol}: 数据不足，无法计算均线\n"
                
        except Exception as e:
            msg_content += f"{symbol}: 分析出错 ({str(e)})\n"
            
    return msg_content

def send_email(content):
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver_env = os.environ.get('MAIL_RECEIVER')
    
    if not sender or not password or not receiver_env:
        print("环境配置错误，请检查 Secrets")
        return

    if ',' in receiver_env:
        receivers = receiver_env.split(',')
    else:
        receivers = [receiver_env]
    
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = sender
    message['To'] = ",".join(receivers)
    
    subject = f"股票量化日报 - {datetime.now().strftime('%Y-%m-%d')}"
    message['Subject'] = Header(subject, 'utf-8')

    try:
        # 如果是 QQ 邮箱请改用 smtp.qq.com
        smtp_obj = smtplib.SMTP_SSL('smtp.gmail.com', 465) 
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, receivers, message.as_string())
        smtp_obj.quit()
        print(f"分析报告已发送给: {receivers}")
    except smtplib.SMTPException as e:
        print(f"发送失败: {e}")

if __name__ == "__main__":
    analysis = get_stock_data()
    print(analysis) # 在日志里打印出来方便检查
    send_email(analysis)