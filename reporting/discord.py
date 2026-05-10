import threading
import json
import os
import requests
from config import DISCORD_BOT_TOKEN, DISCORD_WEBHOOK_URL, DISCORD_ENABLED
from reporting.formatter import (
    format_trade_embed, format_plan_summary, format_account_status, format_history_trade
)
import db


class DiscordReporter:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.enabled = DISCORD_ENABLED
        self.webhook_url = DISCORD_WEBHOOK_URL
        self.bot_token = DISCORD_BOT_TOKEN
        self.bot = None
        self.bot_thread = None

        if DISCORD_WEBHOOK_URL:
            print("  Discord: Webhook push enabled")

        if DISCORD_BOT_TOKEN:
            self._start_bot()

    # ============================================================
    # Webhook 推送 (实时通知)
    # ============================================================

    def _send_webhook(self, embed_data):
        if not self.webhook_url:
            return
        try:
            payload = {"embeds": [embed_data]}
            requests.post(self.webhook_url, json=payload, timeout=5)
        except Exception as e:
            print(f"  Discord webhook error: {e}")

    def send_trade(self, trader_name, symbol, action, price, qty, reason, **kwargs):
        embed_data = format_trade_embed(
            action, trader_name.replace('_trader', ''), symbol, price, qty, reason,
            pnl_pct=kwargs.get('pnl_pct'),
            hold_hours=kwargs.get('hold_hours'),
        )
        self._send_webhook(embed_data)

    def send_plan_summary(self, trader_name, selection_count, rule_count, outlook):
        embed_data = format_plan_summary(trader_name, selection_count, rule_count, outlook)
        self._send_webhook(embed_data)

    def send_chart(self, caption, embed_data, chart_path=None):
        if not self.webhook_url:
            return
        try:
            if chart_path and os.path.exists(chart_path):
                with open(chart_path, 'rb') as f:
                    payload = {
                        'content': caption,
                        'embeds': [embed_data]
                    }
                    files = {'file': (os.path.basename(chart_path), f, 'image/png')}
                    data = {'payload_json': json.dumps(payload)}
                    requests.post(self.webhook_url, data=data, files=files, timeout=10)
            else:
                payload = {
                    'content': caption,
                    'embeds': [embed_data]
                }
                requests.post(self.webhook_url, json=payload, timeout=5)
        except Exception as e:
            print(f"  Discord chart send error: {e}")

    # ============================================================
    # Bot 命令 (交互查询)
    # ============================================================

    def _start_bot(self):
        try:
            import discord
            from discord.ext import commands

            intents = discord.Intents.default()
            intents.message_content = False
            self.discord_bot = commands.Bot(command_prefix="/", intents=intents)

            @self.discord_bot.event
            async def on_ready():
                print(f"  Discord Bot logged in as {self.discord_bot.user}")
                try:
                    synced = await self.discord_bot.tree.sync()
                    print(f"  Discord slash commands synced: {len(synced)}")
                except Exception as e:
                    print(f"  Discord sync error: {e}")

            @self.discord_bot.tree.command(name="history", description="View recent trades for a trader (left/right/extreme)")
            async def history(interaction: discord.Interaction, trader: str, count: int = 10):
                if trader not in ("left", "right", "extreme"):
                    await interaction.response.send_message("Valid traders: left, right, extreme", ephemeral=True)
                    return
                trades = db.get_trades_by_trader(trader, min(count, 20))
                if not trades:
                    await interaction.response.send_message(f"No trades for **{trader}**", ephemeral=True)
                    return
                embeds = []
                for t in trades[:count]:
                    embeds.append(discord.Embed.from_dict(format_history_trade(t)))
                await interaction.response.send_message(embeds=embeds[:10], ephemeral=False)

            @self.discord_bot.tree.command(name="status", description="View recent activity for a trader")
            async def status(interaction: discord.Interaction, trader: str):
                if trader not in ("left", "right", "extreme"):
                    await interaction.response.send_message("Valid traders: left, right, extreme", ephemeral=True)
                    return
                trades = db.get_trades_by_trader(trader, 5)
                if not trades:
                    await interaction.response.send_message(f"No trades for **{trader}** yet.", ephemeral=True)
                    return
                lines = [f"**{trader}** recent trades:"]
                for t in trades[:5]:
                    pnl_str = f" ({t.get('pnl_pct',''):+.1f}%)" if t.get('pnl_pct') is not None else ""
                    lines.append(f"- {t['action']} {t['symbol']} @ ${t.get('entry_price') or t.get('exit_price') or 0:.2f}{pnl_str} | {t.get('trigger_reason','-')[:40]}")
                await interaction.response.send_message("\n".join(lines), ephemeral=False)

            @self.discord_bot.tree.command(name="status_all", description="View all three traders summary")
            async def status_all(interaction: discord.Interaction):
                lines = []
                for t in ("left", "right", "extreme"):
                    trades = db.get_trades_by_trader(t, 3)
                    if trades:
                        actions = [f"{x['action']} {x['symbol']}" for x in trades[:3]]
                        lines.append(f"**{t}**: {', '.join(actions)}")
                    else:
                        lines.append(f"**{t}**: no trades yet")
                await interaction.response.send_message("\n".join(lines), ephemeral=False)

            def run_bot():
                self.discord_bot.run(self.bot_token)

            self.bot_thread = threading.Thread(target=run_bot, daemon=True)
            self.bot_thread.start()
            self.bot = self.discord_bot
            print("  Discord Bot: /history /status /status_all")

        except ImportError:
            print("  Discord: discord.py not installed")
        except Exception as e:
            print(f"  Discord Bot error: {e}")
