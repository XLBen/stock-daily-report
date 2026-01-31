import os
from openai import OpenAI
import requests
import xml.etree.ElementTree as ET
import re
import db  # 引入数据库进行去重检查

# 配置
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com") 

def get_google_news(symbol):
    """
    抓取 Google News RSS (比 yfinance 更稳定)
    """
    try:
        # 针对美股的 RSS 搜索链接
        url = f"https://news.google.com/rss/search?q={symbol}+stock+news&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            return []
            
        root = ET.fromstring(response.content)
        news_items = []
        
        # 解析前 5 条新闻
        count = 0
        for item in root.findall('.//item'):
            if count >= 5: break
            
            title = item.find('title').text
            link = item.find('link').text
            pub_date = item.find('pubDate').text
            
            # --- 核心去重逻辑 ---
            # 检查这条链接是否已经发送过
            if db.is_news_sent(link):
                continue
            
            news_items.append(f"{title} ({pub_date})")
            # 标记为已读 (暂时存入，等发送成功后再 commit)
            db.mark_news_sent(link)
            
            count += 1
            
        return news_items
    except Exception as e:
        print(f"⚠️ Google News 获取失败: {e}")
        return []

def get_latest_news(symbol):
    """
    获取新闻入口
    """
    # 优先用 Google News
    news = get_google_news(symbol)
    if not news:
        return ["暂无最新相关新闻"]
    return news

def analyze_market_move(symbol, change_pct, news_list):
    """
    调用 LLM 进行分析
    """
    if not LLM_API_KEY:
        return {"summary": "未配置 AI Key", "category": "未知", "risk_level": "未知"}

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    
    news_text = "\n".join(news_list[:3])
    
    prompt = f"""
    分析股票 {symbol} 今天涨跌幅 {change_pct:.2f}% 的原因。
    基于以下新闻（如果没有相关新闻，请基于市场常识推测）：
    {news_text}
    
    请用 JSON 格式返回，包含字段：
    - summary: 一句话摘要原因（30字内）
    - category: 分类（如：业绩/宏观/情绪/无消息）
    - risk_level: 风险等级（高/中/低）
    - action_suggestion: 操作建议（观望/止盈/抄底/减仓）
    
    如果新闻里没有具体原因，请直说“无直接消息，疑似技术性调整”。
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat", # 或 gpt-3.5-turbo
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
            response_format={"type": "json_object"} 
        )
        import json
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI 分析失败: {e}")
        return {"summary": "AI 分析暂时不可用", "category": "错误", "risk_level": "未知"}