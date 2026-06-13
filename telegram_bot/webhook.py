#!/usr/bin/env python3
"""
Telegram Webhook Handler for Hermes

This runs as an HTTP server to receive Telegram updates
and route commands to the trading bot handlers.

Requires: pip install aiohttp
"""

from aiohttp import web
import json
import asyncio
import os
from bot import (
    COMMAND_HANDLERS,
    load_config,
    send_daily_briefing,
    check_risk_alerts,
    check_setup_alerts,
)

# ============ CONFIG ============
WEBHOOK_HOST = "0.0.0.0"
WEBHOOK_PORT = 8443
WEBHOOK_PATH = "/webhook/telegram"
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "hermes_trading_bot")

# ============ REQUEST HANDLERS ============
async def handle_webhook(request: web.Request) -> web.Response:
    """Handle incoming Telegram webhook."""
    try:
        # Verify secret
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
            return web.Response(status=403, text="Forbidden")
        
        update = await request.json()
        
        # Process message
        if "message" in update:
            await process_message(update["message"])
        elif "callback_query" in update:
            await process_callback(update["callback_query"])
        
        return web.Response(text="OK")
    except Exception as e:
        print(f"Webhook error: {e}")
        return web.Response(status=500, text=str(e))

async def process_message(message: dict):
    """Process a Telegram message."""
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()
    user_id = str(message.get("from", {}).get("id", ""))
    username = message.get("from", {}).get("username", "")
    
    print(f"Message from {username} ({user_id}): {text}")
    
    # Handle commands
    if text.startswith("/"):
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd in COMMAND_HANDLERS:
            try:
                response = await COMMAND_HANDLERS[cmd]()
                await send_telegram_message(chat_id, response)
            except Exception as e:
                await send_telegram_message(chat_id, f"❌ Error: {e}")
        else:
            await send_telegram_message(chat_id, f"Unknown command: {cmd}. Use /help")

async def process_callback(callback: dict):
    """Process a callback query (inline button press)."""
    callback_id = callback.get("id")
    data = callback.get("data", "")
    chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    
    # Acknowledge callback
    await answer_callback(callback_id)
    
    # Handle callback data
    if data.startswith("cmd:"):
        cmd = data[4:]
        if cmd in COMMAND_HANDLERS:
            try:
                response = await COMMAND_HANDLERS[cmd]()
                await send_telegram_message(chat_id, response)
            except Exception as e:
                await send_telegram_message(chat_id, f"❌ Error: {e}")

async def send_telegram_message(chat_id: str, text: str, parse_mode: str = "Markdown"):
    """Send a message via Telegram Bot API."""
    # Use Hermes send_message tool
    try:
        from hermes_tools import send_message
        # Map chat_id to target format
        target = f"telegram:{chat_id}"
        send_message(action="send", target=target, message=text)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

async def answer_callback(callback_id: str):
    """Answer a callback query."""
    # Just acknowledge - no UI change needed
    pass

async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.Response(text="OK")

# ============ APP ============
def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/health", health_check)
    return app

def run_webhook():
    """Run the webhook server."""
    app = create_app()
    web.run_app(app, host=WEBHOOK_HOST, port=WEBHOOK_PORT)

if __name__ == "__main__":
    run_webhook()