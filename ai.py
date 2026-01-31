import os
from openai import OpenAI
import requests
import xml.etree.ElementTree as ET
import db
import json

# 配置
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com") 

def get_google_news(symbol):
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+stock+news&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return []
        root = ET.fromstring(response.content)
        news_items = []
        count = 0
        for item in root.findall('.//item'):
            if count >= 5: break
            title = item.find('title').text
            link = item.find('link').text
            pub_date = item.find('pubDate').text
            if db.is_news_sent(link): continue
            news_items.append(f"{title} ({pub_date})")
            db.mark_news_sent(link)
            count += 1
        return news_items
    except Exception as e:
        print(f"⚠️ News Error: {e}")
        return []

def get_latest_news(symbol):
    news = get_google_news(symbol)
    return news if news else ["暂无新闻"]

# 🔥 核心修复：这里必须接受 tech_data 参数
def analyze_market_move(symbol, change_pct, news_list, tech_data=None):
    if not LLM_API_KEY:
        return {"summary": "无Key", "left_side_analysis": "-", "right_side_analysis": "-"}

    client = OpenAI(
        api_key=LLM_API_KEY, 
        base_url=LLM_BASE_URL,
        timeout=30.0,
        max_retries=1
    )
    
    # 构建技术面上下文
    tech_context = "暂无数据"
    if tech_data:
        indi = tech_data.get('indicators', {})
        sigs = tech_data.get('signals', {})
        tech_context = f"""
        RSI: {indi.get('rsi')}
        MACD: {indi.get('macd')}
        左侧信号: {sigs.get('left_side')}
        右侧信号: {sigs.get('right_side')}
        """

    prompt = f"""
    分析 {symbol} (涨跌 {change_pct:.2f}%)。
    
    [技术面]
    {tech_context}
    
    [新闻]
    {json.dumps(news_list[:3])}
    
    请扮演【左侧交易员】(逆势)和【右侧交易员】(顺势)进行辩论。
    返回JSON:
    {{
        "summary": "一句话摘要",
        "left_side_analysis": "左侧交易员的观点(抄底还是逃顶?)",
        "right_side_analysis": "右侧交易员的观点(追涨还是止损?)"
    }}
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat", 
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"} 
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ AI Error: {e}")
        return {"summary": f"Error: {str(e)[:30]}", "left_side_analysis": "-", "right_side_analysis": "-"}