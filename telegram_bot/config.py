#!/usr/bin/env python3
"""
Telegram Trading Bot — Configuration
"""

import json
from pathlib import Path

CONFIG_FILE = Path(r"C:\Hermes\telegram_bot\config.json")
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "targets": {
        "primary_dm": "telegram:Wali",
        "primary_group": "telegram:Hermes Super",
        "alerts_topic": "telegram:Hermes Super / topic 2"
    },
    "commands": {
        "enabled": True,
        "prefix": "/",
        "admin_only": [],  # commands restricted to admin users
        "cooldown_seconds": 5
    },
    "daily_briefing": {
        "enabled": True,
        "time": "08:00",  # UTC
        "timezone": "UTC",
        "include": ["confluence", "risk", "session_outlook", "active_setups"]
    },
    "risk_alerts": {
        "enabled": True,
        "levels": ["WARNING", "CRITICAL", "EMERGENCY"],
        "throttle_minutes": 15
    },
    "setup_alerts": {
        "enabled": True,
        "setups": [
            "setup_h4_bull_engulf",
            "setup_h1_bull_engulf",
            "setup_d1_breakout_up",
            "confluence_d1_h4_h1_long",
            "setup_h4_vol_compress"
        ],
        "min_confluence": 60
    },
    "coaching": {
        "enabled": True,
        "pre_entry": True,
        "during_trade": True,
        "post_campaign": True
    },
    "experiments": {
        "enabled": True,
        "on_complete": True
    }
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

if __name__ == "__main__":
    save_config(DEFAULT_CONFIG)
    print(f"Default config saved to {CONFIG_FILE}")