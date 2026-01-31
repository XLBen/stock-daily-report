import smtplib
from email.mime.text import MIMEText
from email.header import Header
import yfinance as yf
import os
from datetime import datetime
import base64

STOCKS = ['AAPL', 'MSFT', 'NVDA']

def get_stock_data():
    msg_content = "今日股票快报：\n\n"
    for symbol in STOCKS:
        try:
            ticker = yf.Ticker(symbol)
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
    sender = os.environ.get('MAIL_USER')
    password = os.environ.get('MAIL_PASS')
    receiver = os.environ.get('MAIL_RECEIVER')

    if not all([sender, password, receiver]):
        raise RuntimeError("邮箱环境变量未正确设置")

    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = sender
    message['To'] = receiver
    subject = f"股票更新 - {datetime.now().strftime('%Y-%m-%d')}"
    message['Subject'] = Header(subject, 'utf-8')

    try:
        smtp = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        smtp.ehlo()

        # 手动 AUTH PLAIN（关键）
        auth_string = f"\0{sender}\0{password}"
        auth_bytes = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
        smtp.docmd("AUTH", "PLAIN " + auth_bytes)

        smtp.sendmail(sender, receiver, message.as_string())
        smtp.quit()
        print("邮件发送成功")

    except Exception as e:
        print("邮件发送失败：", e)
        raise

if __name__ == "__main__":
    stock_info = get_stock_data()
    print(stock_info)
    send_email(stock_info)
