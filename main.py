import smtplib
from email.mime.text import MIMEText
from email.header import Header
import yfinance as yf
import os
from datetime import datetime

# 配置部分：你想关注的股票代码（例如：AAPL=苹果, MSFT=微软, 0700.HK=腾讯）
STOCKS = ['AAPL', 'MSFT', 'NVDA']

def get_stock_data():
    msg_content = "今日股票快报：\n\n"
    for symbol in STOCKS:
        try:
            ticker = yf.Ticker(symbol)
            # 获取当天的最新数据
            hist = ticker.history(period="1d")
            if not hist.empty:
                close_price = hist['Close'].iloc[0]
                msg_content += f"{symbol}: ${close_price:.2f}\n"
            else:
                msg_content += f"{symbol}: 无法获取数据\n"
        except Exception as e:
            msg_content += f"{symbol}: 获取出错 ({str(e)})\n"
    return msg_content

def send_email(content):
    # 从环境变量获取敏感信息
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver = os.environ.get('MAIL_RECEIVER')
    
    # 邮件构建
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = sender
    message['To'] = receiver
    subject = f"股票更新 - {datetime.now().strftime('%Y-%m-%d')}"
    message['Subject'] = Header(subject, 'utf-8')

    try:
        # 这里以 Gmail 为例，如果是 QQ 邮箱使用 smtp.qq.com，端口 465 (SSL)
        smtp_obj = smtplib.SMTP_SSL('smtp.gmail.com', 465) 
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, receiver, message.as_string())
        smtp_obj.quit()
        print("邮件发送成功")
    except smtplib.SMTPException as e:
        print(f"邮件发送失败: {e}")

if __name__ == "__main__":
    stock_info = get_stock_data()
    print(stock_info) # 在 Action 日志中打印以便调试
    send_email(stock_info)