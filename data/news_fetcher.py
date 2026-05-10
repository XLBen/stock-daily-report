import requests
import xml.etree.ElementTree as ET
import db

def get_google_news(symbol):
    try:
        import urllib.parse
        q = urllib.parse.quote(f"{symbol} stock news")
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return []
        root = ET.fromstring(response.content)
        news_items = []
        count = 0
        for item in root.findall('.//item'):
            if count >= 5:
                break
            title = item.find('title').text
            link = item.find('link').text
            pub_date = item.find('pubDate').text
            if db.is_news_sent(link):
                continue
            news_items.append(f"{title} ({pub_date})")
            db.mark_news_sent(link)
            count += 1
        return news_items
    except Exception as e:
        print(f"⚠️  News Error for {symbol}: {e}")
        return []

def get_latest_news(symbol):
    news = get_google_news(symbol)
    return news if news else ["No recent news"]

def fetch_all_news(symbols):
    all_news = {}
    for s in symbols:
        all_news[s] = get_latest_news(s)
    return all_news
