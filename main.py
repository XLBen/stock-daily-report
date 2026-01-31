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
    receiver_env = os.environ.get('MAIL_RECEIVER') # 获取那串长字符串

    # --- 关键修改：处理多个邮箱 ---
    if ',' in receiver_env:
        # 如果发现有逗号，就切割成一个列表 ['a@a.com', 'b@b.com']
        receivers = receiver_env.split(',')
    else:
        # 如果只有一个邮箱，就把它放进列表里
        receivers = [receiver_env]
    
    # 邮件构建
    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = sender
    # 邮件头部的 "To" 显示所有收件人，用逗号连接
    message['To'] = ",".join(receivers)
    
    subject = f"股票更新 - {datetime.now().strftime('%Y-%m-%d')}"
    message['Subject'] = Header(subject, 'utf-8')

    try:
        smtp_obj = smtplib.SMTP_SSL('smtp.gmail.com', 465) 
        # 注意：如果你用的是 QQ 邮箱，记得把上面改成 'smtp.qq.com'
        
        smtp_obj.login(sender, password)
        
        # --- 关键修改：发送给列表里的所有人 ---
        smtp_obj.sendmail(sender, receivers, message.as_string())
        
        smtp_obj.quit()
        print(f"邮件已成功发送给: {receivers}")
    except smtplib.SMTPException as e:
        print(f"邮件发送失败: {e}")
        
if __name__ == "__main__":
    stock_info = get_stock_data()
    print(stock_info)
    send_email(stock_info)
