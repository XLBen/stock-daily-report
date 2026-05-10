import os
import json
import time
from datetime import datetime
from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, ACCOUNTS
from plans.plan_schema import SELECTION_SCHEMA, PLAN_SCHEMA, SUPPORTED_INDICATORS
import db


class BaseTrader:
    ROLE_NAME = "base"
    ROLE_PROMPT = ""
    TEMPERATURE = 0.3

    def __init__(self):
        self._has_llm = bool(LLM_API_KEY)
        self.cfg = ACCOUNTS.get(self.ROLE_NAME, {})
        self._min_hold = self.cfg.get("min_hold_hours", 1)
        self._cooldown = self.cfg.get("cooldown_hours", 2)
        self._max_daily = self.cfg.get("max_daily_trades", 5)
        if self._has_llm:
            self.client = OpenAI(
                api_key=LLM_API_KEY,
                base_url=LLM_BASE_URL,
                timeout=120.0,
                max_retries=2
            )
        else:
            self.client = None
            print(f"  [{self.ROLE_NAME}] LLM_API_KEY not set, using fallback")

    # ============================================================
    # Pass 1: 纯技术选股
    # ============================================================

    def select_candidates(self, market_data):
        if not self._has_llm:
            return self._fallback_selection(market_data)

        context = self._build_selection_context(market_data)

        system_prompt = f"{self.ROLE_PROMPT}\n\n当前阶段: 选股筛选 (output as JSON)。仅基于技术指标从{len(market_data)}只股票中选出3~5只。"

        user_prompt = f"""
[纯技术面数据 (json)]
{json.dumps(context['stocks'], ensure_ascii=False, indent=2)}

请选出 3~5 只最值得本周操作的股票。只看技术指标, 暂时不考虑新闻。

输出 JSON 格式:
{json.dumps(SELECTION_SCHEMA, ensure_ascii=False, indent=2)}
"""

        plan = self._call_llm(system_prompt, user_prompt, SELECTION_SCHEMA)
        if plan is None:
            return self._fallback_selection(market_data)
        return plan

    def _build_selection_context(self, market_data):
        stocks = []
        for symbol, data in market_data.items():
            row = {
                "symbol": symbol,
                "price": data.get('price'),
                "change_pct": data.get('change_pct', 0),
            }
            indi = data.get('indicators', {})
            for k, v in indi.items():
                if isinstance(v, float):
                    row[k] = round(v, 4)
                elif isinstance(v, str) and v in ("above", "below", "up", "down", "flat", "none", "above_rising", "below_falling"):
                    row[k] = v
                else:
                    row[k] = v
            stocks.append(row)
        return {"stocks": stocks}

    def _fallback_selection(self, market_data):
        top = sorted(market_data.items(), key=lambda x: abs(x[1].get('change_pct', 0)), reverse=True)[:4]
        selections = []
        for i, (sym, data) in enumerate(top):
            direction = "BUY" if data.get("change_pct", 0) < 0 else "SELL"
            selections.append({
                "symbol": sym, "rank": i + 1, "direction": direction,
                "reason": f"fallback: change_pct={data.get('change_pct', 0):.2f}%"
            })
        return {"selections": selections, "market_outlook": "fallback", "macro_bias": "neutral"}

    # ============================================================
    # Step 1: AI 写筛选条件 (Programmatic Filter Criteria)
    # ============================================================

    def generate_criteria(self):
        if not self._has_llm:
            return self._fallback_criteria()

        criteria_schema = {
            "type": "object",
            "required": ["must", "must_not", "prefer", "max_results", "explanation"],
            "properties": {
                "explanation": {"type": "string"},
                "must": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["indicator", "op", "value"],
                        "properties": {
                            "indicator": {"type": "string"},
                            "op": {"type": "string", "enum": ["gt", "lt", "gte", "lte", "eq"]},
                            "value": {}
                        }
                    }
                },
                "must_not": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["indicator", "op", "value"],
                        "properties": {
                            "indicator": {"type": "string"},
                            "op": {"type": "string", "enum": ["gt", "lt", "gte", "lte", "eq"]},
                            "value": {}
                        }
                    }
                },
                "prefer": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["indicator", "op", "value"],
                        "properties": {
                            "indicator": {"type": "string"},
                            "op": {"type": "string", "enum": ["gt", "lt", "gte", "lte", "eq"]},
                            "value": {}
                        }
                    }
                },
                "max_results": {"type": "integer", "minimum": 10, "maximum": 50}
            }
        }

        system_prompt = f"""{self.ROLE_PROMPT}

当前阶段: 设计筛选条件 (output as JSON)。你将输出一个 JSON，程序会用它从上万只股票中筛出候选。

可用的指标 (从 25 个技术指标中选):
{json.dumps(SUPPORTED_INDICATORS, ensure_ascii=False)}
"""

        user_prompt = f"""请基于你的交易风格设计一套筛选条件 (output as JSON)。

[筛选规则]
- must: 所有条件必须全部满足才入选 (1-3 个核心条件)
- must_not: 所有条件必须全部不满足 (排除坏股, 1-2 个)
- prefer: 加分项, 满足越多排名越靠前 (2-4 个)
- max_results: 最多返回多少只 (10-40)
- explanation: 用一段话解释这套筛子的逻辑

格式示例 (严格按此 JSON 格式):
{{
  "must": [{{"indicator": "rsi", "op": "lt", "value": 35}}],
  "must_not": [{{"indicator": "ma20_trend", "op": "eq", "value": "below_falling"}}],
  "prefer": [{{"indicator": "sharpe", "op": "gt", "value": 0.3}}],
  "max_results": 25,
  "explanation": "..."
}}

op 只能用: gt, lt, gte, lte, eq
value 用数字, 字符串值仅用于 ma20_trend/ma_cross/obv_trend 这类指标
"""

        for attempt in range(2):
            try:
                resp = self.client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                result = json.loads(resp.choices[0].message.content)
                if "must" in result and "explanation" in result:
                    print(f"  [{self.ROLE_NAME}] criteria: {result.get('explanation','')[:60]}")
                    return result
            except Exception as e:
                print(f"  [{self.ROLE_NAME}] criteria LLM failed: {e}")
                time.sleep(1)
        return self._fallback_criteria()

    def _fallback_criteria(self):
        return {
            "must": [
                {"indicator": "rsi", "op": "lt", "value": 40},
            ],
            "must_not": [
                {"indicator": "ma20_trend", "op": "eq", "value": "below_falling"},
            ],
            "prefer": [
                {"indicator": "sharpe", "op": "gt", "value": 0.3},
                {"indicator": "volume_ratio", "op": "gt", "value": 1.2},
            ],
            "max_results": 25,
            "explanation": "fallback: look for oversold stocks with positive Sharpe"
        }

    # ============================================================
    # Pass 2: 深度决策
    # ============================================================

    def _build_decision_context(self, candidate_data, current_positions):
        candidates = []
        for symbol, data in candidate_data.items():
            row = {
                "symbol": symbol,
                "price": data.get('price'),
                "change_pct": data.get('change_pct', 0),
                "news": data.get('news', [])[:3],
                "fundamentals": data.get('fundamentals', {}),
                "quant": data.get('quant', {}),
            }
            indi = data.get('indicators', {})
            for k, v in indi.items():
                if isinstance(v, (int, float)):
                    row[k] = round(float(v), 4)
                elif isinstance(v, str) and v in ("above", "below", "up", "down", "flat", "none", "above_rising", "below_falling"):
                    row[k] = v
            candidates.append(row)

        recent_trades_raw = db.get_recent_trades(self.ROLE_NAME, 5) if self.ROLE_NAME != "base" else []
        recent_trades = []
        for t in recent_trades_raw:
            recent_trades.append({
                "symbol": t['symbol'],
                "action": t['action'],
                "price": t.get('entry_price') or t.get('exit_price'),
                "pnl_pct": t.get('pnl_pct'),
                "reason": t.get('trigger_reason', ''),
                "executed_at": str(t.get('executed_at', '')),
                "hold_hours": t.get('hold_duration_hours'),
            })

        cooldown_symbols = []
        now = datetime.now()
        for t in recent_trades_raw:
            if t.get('action') in ('SELL', 'STOP_LOSS', 'TAKE_PROFIT'):
                et = t.get('executed_at')
                if et:
                    try:
                        delta_hours = abs((now - et.replace(tzinfo=None) if hasattr(et, 'tzinfo') else (now - et)).total_seconds() / 3600 if isinstance(et, datetime) else abs((now - datetime.fromisoformat(str(et)[:19])).total_seconds() / 3600))
                        if delta_hours < self._cooldown:
                            cooldown_symbols.append(t['symbol'])
                    except:
                        pass

        return {
            "candidates": candidates,
            "holdings": current_positions or [],
            "recent_trades": recent_trades,
            "cooldown_symbols": list(set(cooldown_symbols)),
        }

    def generate_rules(self, candidate_data, current_positions=None):
        if not self._has_llm:
            return self._fallback_rules(candidate_data)

        context = self._build_decision_context(candidate_data, current_positions)

        recent = context.get('recent_trades', [])
        cooldown_list = context.get('cooldown_symbols', [])
        holdings = context.get('holdings', {})

        discipline_block = f"""
交易纪律 (系统强制, 必须遵守):
- 最小持仓: {self._min_hold} 小时 (SELL 规则会在此时间后才可能执行)
- 同股卖出冷却: {self._cooldown} 小时内不重新买入
- 每日最大交易: {self._max_daily} 笔
- 冷却期中的股票: {json.dumps(cooldown_list, ensure_ascii=False)}
- 当前已持有: {json.dumps([h.get('symbol') for h in (holdings or [])], ensure_ascii=False)}
"""

        if recent:
            discipline_block += f"\n近 5 笔交易:\n{json.dumps(recent, ensure_ascii=False, indent=2)}\n"

        system_prompt = f"{self.ROLE_PROMPT}\n\n{discipline_block}"

        user_prompt = f"""
以下是你选中的候选股, 含完整数据(技术+新闻+基本面):

[候选股数据 (json)]
{json.dumps(context['candidates'], ensure_ascii=False, indent=2)}

请为这些股票设计具体的交易规则, 以 json 格式输出。

{json.dumps(PLAN_SCHEMA, ensure_ascii=False, indent=2)}

规则要求:
- conditions 只用技术指标 (indicator/op/value)
- order.type 可以是 market 或 limit
- 限价单必须给出 limit_price 或 price_offset_pct
"""

        plan = self._call_llm(system_prompt, user_prompt, PLAN_SCHEMA)
        if plan is None:
            return self._fallback_rules(candidate_data)
        plan = self._sanitize_rules(plan, candidate_data)
        return plan

    def _sanitize_rules(self, plan, candidate_data):
        from plans.plan_schema import SUPPORTED_INDICATORS
        valid_ops = {"gt", "lt", "gte", "lte", "eq", "cross_above", "cross_below"}
        valid_symbols = set(candidate_data.keys()) if candidate_data else set()

        cleaned = []
        for rule in plan.get('rules', []):
            sym = rule.get('symbol', '').upper()
            if valid_symbols and sym not in valid_symbols:
                print(f"  [{self.ROLE_NAME}] sanitize: dropped unknown symbol {sym}")
                continue

            alloc = rule.get('alloc_pct', 0.1)
            if not (0.02 <= alloc <= 0.35):
                rule['alloc_pct'] = max(0.02, min(0.35, alloc))

            rule['symbol'] = sym
            rule['action'] = rule.get('action', 'BUY').upper()
            if rule['action'] not in ('BUY', 'SELL'):
                rule['action'] = 'BUY'

            conds = rule.get('conditions', {})
            for which in ('must_all', 'must_any'):
                lst = conds.get(which, [])
                valid_conds = []
                for c in lst:
                    ind = c.get('indicator', '')
                    if ind not in SUPPORTED_INDICATORS:
                        print(f"  [{self.ROLE_NAME}] sanitize: dropped invalid indicator '{ind}' in {which}")
                        continue
                    op = c.get('op', 'gt')
                    if op not in valid_ops:
                        op = 'gt'
                    c['op'] = op
                    valid_conds.append(c)
                conds[which] = valid_conds
            rule['conditions'] = conds

            risk = rule.get('risk', {})
            risk.setdefault('stop_loss_pct', 0.07)
            risk.setdefault('take_profit_pct', 0.15)
            risk.setdefault('max_hold_hours', 48)
            risk.setdefault('trailing_stop_pct', 0.03)
            rule['risk'] = risk

            order = rule.get('order', {})
            order.setdefault('type', 'market')
            order.setdefault('time_in_force', 'day')
            rule['order'] = order

            cleaned.append(rule)

        plan['rules'] = cleaned
        return plan

    # ============================================================
    # LLM helper
    # ============================================================

    def _call_llm(self, system_prompt, user_prompt, output_schema):
        for attempt in range(3):
            try:
                resp = self.client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=self.TEMPERATURE,
                    response_format={"type": "json_object"},
                )
                text = resp.choices[0].message.content
                plan = json.loads(text)
                return plan
            except Exception as e:
                print(f"  [{self.ROLE_NAME}] LLM call failed (attempt {attempt+1}): {e}")
                time.sleep(2)
        return None

    # ============================================================
    # 兼容旧接口 (单次调用: 选股+规则一起)
    # ============================================================

    def generate_plan(self, market_data, current_positions, output_schema):
        selection = self.select_candidates(market_data)
        selected_symbols = [s['symbol'] for s in selection.get('selections', [])]
        candidate_market = {s: market_data.get(s) for s in selected_symbols if s in market_data}
        if not candidate_market:
            candidate_market = dict(list(market_data.items())[:4])
        rules = self.generate_rules(candidate_market, current_positions)
        rules["market_outlook"] = selection.get("market_outlook", "")
        rules["macro_bias"] = selection.get("macro_bias", "neutral")
        return rules
