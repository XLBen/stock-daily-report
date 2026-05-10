PLAN_SCHEMA = {
    "type": "object",
    "required": ["market_outlook", "macro_bias", "rules"],
    "properties": {
        "market_outlook": {"type": "string"},
        "macro_bias": {"type": "string", "enum": ["bullish", "bearish", "neutral", "volatile"]},
        "rules": {
            "type": "array",
            "minItems": 0,
            "maxItems": 15,
            "items": {
                "type": "object",
                "required": ["rule_id", "symbol", "action", "alloc_pct", "conditions"],
                "properties": {
                    "rule_id": {"type": "integer", "minimum": 1},
                    "symbol": {"type": "string"},
                    "action": {"type": "string", "enum": ["BUY", "SELL"]},
                    "alloc_pct": {"type": "number", "minimum": 0.02, "maximum": 0.35},
                    "conditions": {
                        "type": "object",
                        "required": ["must_all", "must_any"],
                        "properties": {
                            "must_all": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["indicator", "op", "value"],
                                    "properties": {
                                        "indicator": {"type": "string"},
                                        "op": {"type": "string", "enum": ["gt", "lt", "gte", "lte", "eq", "cross_above", "cross_below"]},
                                        "value": {"type": "number"}
                                    }
                                }
                            },
                            "must_any": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["indicator", "op", "value"],
                                    "properties": {
                                        "indicator": {"type": "string"},
                                        "op": {"type": "string", "enum": ["gt", "lt", "gte", "lte", "eq", "cross_above", "cross_below"]},
                                        "value": {"type": "number"}
                                    }
                                }
                            }
                        }
                    },
                    "order": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["market", "limit"], "default": "market"},
                            "limit_price": {"type": "number"},
                            "price_offset_pct": {"type": "number", "default": 0},
                            "time_in_force": {"type": "string", "enum": ["day", "gtc"], "default": "day"},
                            "cancel_if_not_filled_hours": {"type": "number", "default": 24}
                        }
                    },
                    "risk": {
                        "type": "object",
                        "properties": {
                            "stop_loss_pct": {"type": "number", "minimum": 0.02, "maximum": 0.20, "default": 0.07},
                            "take_profit_pct": {"type": "number", "minimum": 0.05, "maximum": 0.40, "default": 0.15},
                            "max_hold_hours": {"type": "number", "minimum": 1, "maximum": 120, "default": 48},
                            "trailing_stop_pct": {"type": "number", "minimum": 0.01, "maximum": 0.10, "default": 0.03}
                        }
                    }
                }
            }
        }
    }
}


SELECTION_SCHEMA = {
    "type": "object",
    "required": ["selections", "market_outlook", "macro_bias"],
    "properties": {
        "market_outlook": {"type": "string"},
        "macro_bias": {"type": "string", "enum": ["bullish", "bearish", "neutral", "volatile"]},
        "selections": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": ["symbol", "rank", "direction", "reason"],
                "properties": {
                    "symbol": {"type": "string"},
                    "rank": {"type": "integer", "minimum": 1, "maximum": 5},
                    "direction": {"type": "string", "enum": ["BUY", "SELL"]},
                    "reason": {"type": "string"}
                }
            }
        }
    }
}


SUPPORTED_INDICATORS = [
    "rsi", "bb_position", "macd", "adx", "plus_di", "minus_di",
    "ma20_trend", "ma50_trend", "ma_cross",
    "volume_ratio", "obv_trend",
    "stoch_k", "stoch_d", "williams_r", "cci",
    "bb_width", "beta", "sharpe", "max_drawdown",
    "momentum_score", "atr_pct", "price", "change_pct"
]
