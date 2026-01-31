import os
import json
from openai import OpenAI
import yfinance as yf

# 获取环境变量
API_KEY = os.environ.get("LLM_API_KEY")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")

def get_latest_news(symbol):
    """抓取 yfinance 的新闻标题"""
    try:
        ticker = yf.Ticker(symbol)
        news_list = ticker.news
        if not news_list:
            return []
        
        # 只提取最近的 5 条新闻标题
        headlines = [n['title'] for n in news_list[:5]]
        return headlines
    except Exception as e:
        print(f"新闻抓取失败: {e}")
        return []

def analyze_market_move(symbol, change_pct, headlines):
    """
    核心函数：调用 AI 进行归因分析
    返回：结构化的字典 (Summary, Category, Confidence)
    """
    if not API_KEY:
        return {"summary": "未配置 AI Key，无法分析", "category": "未知", "risk": "未知"}
    
    if not headlines:
        return {"summary": "未找到相关新闻，可能是市场情绪波动", "category": "无消息", "risk": "低"}

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    # 精心设计的 Prompt (提示词)
    prompt = f"""
    你是一个华尔街资深交易员。股票 {symbol} 今天波动幅度为 {change_pct:.2f}%。
    以下是最近的新闻标题：
    {headlines}

    请根据新闻分析波动原因，并严格按照以下 JSON 格式输出（不要输出任何 Markdown 格式）：
    {{
        "summary": "一句话概括原因（中文，30字以内）",
        "category": "财报 / 宏观 / 行业 / 监管 / 情绪",
        "risk_level": "高 / 中 / 低",
        "action_suggestion": "观察 / 止损 / 抄底"
    }}
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat", # 如果用 OpenAI 请改为 gpt-4o-mini 或 gpt-3.5-turbo
            messages=[
                {"role": "system", "content": "你是一个输出 JSON 格式的金融分析助手。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        content = response.choices[0].message.content
        # 清洗一下返回内容，防止 AI 加了 ```json
        content = content.replace("```json", "").replace("```", "").strip()
        
        return json.loads(content)
        
    except Exception as e:
        print(f"AI 分析失败: {e}")
        return {"summary": "AI 脑子瓦特了", "category": "系统错误", "risk": "未知"}