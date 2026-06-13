#!/usr/bin/env python3
"""
Telegram Trading Bot — Main Entry Point

Handles:
- CLI commands: python main.py <command>
- Cron jobs: python main.py cron
- Webhook: python main.py webhook

Usage:
    python main.py score
    python main.py risk
    python main.py cron
    python main.py webhook
"""

import asyncio
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bot import (
    handle_score, handle_risk, handle_setups, handle_coaching,
    handle_campaigns, handle_experiments, handle_help,
    send_daily_briefing, check_risk_alerts, check_setup_alerts,
    send_telegram_message, load_config,
)

async def run_command(command: str):
    """Run a single command and print result."""
    handlers = {
        "score": handle_score,
        "risk": handle_risk,
        "setups": handle_setups,
        "coaching": handle_coaching,
        "campaigns": handle_campaigns,
        "experiments": handle_experiments,
        "help": handle_help,
    }

    if command in handlers:
        result = await handlers[command]()
        print(result)
    else:
        print(f"Unknown command: {command}")
        print("Available: score, risk, setups, coaching, campaigns, experiments, help")

async def run_cron():
    """Run scheduled cron jobs."""
    from bot import check_risk_alerts, check_setup_alerts
    print(f"[{datetime.now()}] Running cron jobs...")
    await check_risk_alerts()
    await check_setup_alerts()
    print("Cron jobs completed.")

async def send_briefing():
    """Send daily briefing manually."""
    from bot import send_daily_briefing
    await send_daily_briefing()

def test_message(target: str, message: str):
    """Test sending a message."""
    from bot import send_telegram_message
    success = send_telegram_message(target, message)
    print(f"Send {'success' if success else 'failed'}")

def main():
    parser = argparse.ArgumentParser(description="Hermes Telegram Trading Bot")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Bot commands
    subparsers.add_parser("score", help="Show confluence score")
    subparsers.add_parser("risk", help="Show risk status")
    subparsers.add_parser("setups", help="Show recent setups")
    subparsers.add_parser("coaching", help="Show coaching signal")
    subparsers.add_parser("campaigns", help="Show active campaigns")
    subparsers.add_parser("experiments", help="Show recent experiments")
    subparsers.add_parser("help", help="Show help")

    # System commands
    cron_parser = subparsers.add_parser("cron", help="Run cron jobs")
    subparsers.add_parser("briefing", help="Send daily briefing now")
    
    # Test commands
    test_parser = subparsers.add_parser("test-msg", help="Test send message")
    test_parser.add_argument("target", help="Target (e.g., telegram:Wali)")
    test_parser.add_argument("message", nargs="?", default="Test message", help="Message to send")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Async commands
    async_commands = {"score", "risk", "setups", "coaching", "campaigns", "experiments", "help", "cron", "briefing"}
    
    if args.command in async_commands:
        if args.command == "cron":
            asyncio.run(run_cron())
        elif args.command == "briefing":
            asyncio.run(send_briefing())
        else:
            asyncio.run(run_command(args.command))
    elif args.command == "test-msg":
        from bot import send_telegram_message, load_config
        config = load_config()
        target = args.target if args.target else config["targets"]["primary_dm"]
        success = send_telegram_message(target, args.message)
        print(f"Message send {'success' if success else 'failed'}")
    else:
        print(f"Unknown command: {args.command}")

# Import at bottom to avoid circular import
from datetime import datetime

if __name__ == "__main__":
    main()