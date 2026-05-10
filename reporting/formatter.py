def format_trade_embed(action, trader, symbol, price, qty, reason, pnl_pct=None, hold_hours=None, order_id=None):
    """
    Build a Discord embed dict for a trade event.
    Caller wraps in list and sends via Discord bot/webhook.
    """
    EMERALD = 0x00C853
    RED = 0xFF1744
    GOLD = 0xFFD600
    BLUE = 0x2979FF
    GRAY = 0x78909C

    action_map = {
        "BUY": ("BUY", EMERALD, "entry_price"),
        "SELL": ("SELL", GRAY, "exit_price"),
        "STOP_LOSS": ("STOP LOSS", RED, "exit_price"),
        "TAKE_PROFIT": ("TAKE PROFIT", EMERALD, "exit_price"),
        "TRAILING_STOP": ("TRAILING STOP", BLUE, "exit_price"),
        "LIMIT_ORDER": ("LIMIT ORDER", GOLD, "limit_price"),
    }

    label, color, price_field = action_map.get(action, (action, GRAY, "price"))

    title = f"{get_emoji(action)} {label}: {symbol}"
    description = f"**Trader:** {trader}\n"
    description += f"**Price:** ${price:.2f}\n"
    description += f"**Qty:** {qty}\n"

    if pnl_pct is not None:
        pnl_sign = "+" if pnl_pct >= 0 else ""
        description += f"**P&L:** {pnl_sign}{pnl_pct:.2f}%\n"
    if hold_hours is not None:
        description += f"**Hold:** {hold_hours:.1f}h\n"

    if reason:
        desc = str(reason)[:300]
        if "{" in desc:
            try:
                import json
                d = json.loads(desc)
                if "matched" in d:
                    description += f"**Conditions:** {', '.join(d['matched'])}\n"
            except:
                description += f"**Reason:** {desc}\n"
        else:
            description += f"**Reason:** {desc}\n"

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": None,
    }

    return embed


def get_emoji(action):
    emoji_map = {
        "BUY": "\U0001F7E2",
        "SELL": "\U0001F534",
        "STOP_LOSS": "\U0001F534",
        "TAKE_PROFIT": "\U0001F7E2",
        "TRAILING_STOP": "\U0001F535",
        "LIMIT_ORDER": "\U0001F7E1",
    }
    return emoji_map.get(action, "\u26AA")


def format_plan_summary(trader_name, selection_count, rule_count, outlook):
    return {
        "title": f"\U0001F4CB [{trader_name}] Weekly Plan Generated",
        "description": (
            f"**Selections:** {selection_count} stocks\n"
            f"**Rules:** {rule_count}\n"
            f"**Outlook:** {outlook}\n"
        ),
        "color": 0xFFD600,
    }


def format_account_status(trader_name, equity, cash, positions_count, pnl_summary):
    return {
        "title": f"\U0001F4CA [{trader_name}] Account Status",
        "description": (
            f"**Equity:** ${equity:.2f}\n"
            f"**Cash:** ${cash:.2f}\n"
            f"**Positions:** {positions_count}\n"
            f"**P&L:** {pnl_summary}\n"
        ),
        "color": 0x2979FF,
    }


def format_history_trade(t):
    action = t.get('action', '?')
    symbol = t.get('symbol', '?')
    price = t.get('entry_price') or t.get('exit_price') or 0
    pnl = t.get('pnl_pct')
    reason = t.get('trigger_reason', '-')
    ts = str(t.get('executed_at', ''))[:19]
    return format_trade_embed(
        action, t.get('trader_role', '?'), symbol, price,
        t.get('qty', 0), reason, pnl_pct=pnl, hold_hours=t.get('hold_duration_hours')
    )


def format_portfolio_report(trader_name, holdings, report_type):
    labels = {
        "open": "Opening Bell",
        "1hour": "1 Hour Check",
        "midday": "Midday Snapshot",
        "close": "Closing Summary",
    }
    label = labels.get(report_type, report_type)
    emoji_map = {
        "open": "\U0001F4C8", "1hour": "\u23F1\uFE0F", "midday": "\U0001F4CA", "close": "\U0001F4C9"
    }
    emoji = emoji_map.get(report_type, "\U0001F4CA")

    total_value = sum(h['market_value'] for h in holdings)
    lines = []
    for h in holdings:
        direction = "\U0001F7E2" if h['change_pct'] >= 0 else "\U0001F534"
        lines.append(
            f"{direction} **{h['symbol']}**  {h['qty']}sh @ ${h['entry_price']:.2f} → ${h['current_price']:.2f} "
            f"({h['change_pct']:+.1f}%) | ${h['market_value']:.0f}"
        )

    trader_tag = trader_name.replace('_trader', '')
    description = "\n".join(lines) if lines else "(no holdings)"
    description += f"\n\n**Total:** ${total_value:.0f} | **Positions:** {len(holdings)}"

    return {
        "title": f"{emoji} {label} — {trader_tag}",
        "description": description,
        "color": 0x2979FF,
    }


def format_major_move_alert(trader_name, symbol, qty, entry_price, current_price,
                            open_price, day_change, total_change):
    direction_emoji = "\U0001F7E2" if day_change > 0 else "\U0001F534"
    trader_tag = trader_name.replace('_trader', '')
    caption = f"{direction_emoji} **{symbol}** moved {day_change:+.1f}% today (held by **{trader_tag}**)"

    description = (
        f"**Held by:** {trader_tag}\n"
        f"**Shares:** {qty}\n"
        f"**Open:** ${open_price:.2f} → **Now:** ${current_price:.2f}  ({day_change:+.1f}%)\n"
        f"**Entry:** ${entry_price:.2f}  |  **P&L:** {total_change:+.1f}%  |  "
        f"${(current_price - entry_price) * qty:+.2f}\n"
    )

    embed = {
        "title": f"{direction_emoji} Major Move — {symbol}",
        "description": description,
        "color": 0x00C853 if day_change > 0 else 0xFF1744,
    }
    return embed, caption
