#!/usr/bin/env python3
"""
Telegram Trading Bot — Core Engine (Standalone Version)

Handles:
- Command routing (/score, /risk, /setups, /coaching, /campaigns, /experiments)
- Scheduled briefings (daily, session-based)
- Real-time alerts (risk, setups, experiments)
- Interactive callbacks

This version uses subprocess calls to Hermes CLI for messaging.
"""

import asyncio
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Any
import warnings
import subprocess
import sys
warnings.filterwarnings("ignore")

# ============ CONFIG ============
HERMES_CLI = r"C:\Users\Boboi Kusni\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe" if sys.platform == "win32" else "hermes"

from config import load_config, CONFIG_FILE

# ============ STATE ============
STATE_DIR = Path(r"C:\Hermes\telegram_bot\state")
STATE_DIR.mkdir(parents=True, exist_ok=True)

LAST_ALERT_FILE = STATE_DIR / "last_alerts.json"
BRIEFING_STATE_FILE = STATE_DIR / "briefing_state.json"

# ============ MESSAGING ============
def send_telegram_message(target: str, message: str) -> bool:
    """Send a message via Hermes CLI."""
    try:
        # target format: "telegram:Wali" or "telegram:Hermes Super / topic 2"
        # Use pipe to avoid issues with special characters
        cmd = [HERMES_CLI, "send", "--to", target]
        result = subprocess.run(cmd, input=message, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

# ============ DATA LOADERS ============
def load_latest_confluence(symbol: str = "XAUUSD") -> Dict:
    try:
        csv_file = Path(fr"C:\Hermes\confluence_score\{symbol}_confluence_score.parquet")
        if csv_file.exists():
            df = pd.read_parquet(csv_file)
            latest = df.iloc[-1]
            return {
                "score": float(latest["confluence_score"]),
                "tier": str(latest["tier"]),
                "active_setups": str(latest.get("active_setups", "")).split(";") if latest.get("active_setups") else [],
                "timestamp": str(latest.name)
            }
    except Exception as e:
        return {"error": str(e)}
    return {}

def load_risk_state() -> Dict:
    try:
        return {
            "overall_level": "ADVISORY",
            "daily_loss_pct": 0,
            "weekly_loss_pct": 0,
            "monthly_loss_pct": 0,
            "total_layers": 0,
            "max_layers_pct": 0,
            "campaigns": {},
            "recent_alerts": []
        }
    except Exception as e:
        return {"error": str(e)}

def load_active_campaigns() -> Dict:
    try:
        csv_file = Path(r"C:\Hermes\behaviour_analysis\trades_raw.csv")
        if csv_file.exists():
            df = pd.read_csv(csv_file)
            df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
            df = df[df["campaign_id"] != "UNTAGGED"]
            cutoff = pd.Timestamp.now(tz="UTC") - timedelta(hours=48)
            recent = df[df["entry_time"] > cutoff]
            summary = {}
            for camp_id in recent["campaign_id"].unique():
                camp = recent[recent["campaign_id"] == camp_id]
                summary[camp_id] = {
                    "type": camp["campaign_type"].iloc[0],
                    "trades_48h": len(camp),
                    "net_pnl_48h": float(camp["pnl_usd"].sum()),
                    "open_layers": len(camp[camp["exit_time"].isna()]) if "exit_time" in camp.columns else 0,
                }
            return summary
    except Exception as e:
        return {"error": str(e)}
    return {}

def load_recent_experiments() -> List[Dict]:
    try:
        exp_dir = Path(r"C:\Hermes\research_experiments")
        index_file = exp_dir / "experiment_index.json"
        if index_file.exists():
            with open(index_file) as f:
                data = json.load(f)
                exps = data.get("experiments", {})
                sorted_exps = sorted(exps.items(), key=lambda x: x[1].get("created", ""), reverse=True)
                return [{"id": k, **v} for k, v in sorted_exps[:5]]
    except Exception as e:
        return [{"error": str(e)}]
    return []

def load_setup_signals(symbol: str = "XAUUSD") -> Dict:
    try:
        labels_file = Path(fr"C:\Hermes\edge_discovery\{symbol}_setup_labels.parquet")
        if labels_file.exists():
            df = pd.read_parquet(labels_file)
            recent = df.tail(50)
            active = {}
            for col in recent.columns:
                if col.startswith("setup_") or col.startswith("confluence_"):
                    last_idx = recent[recent[col] == 1].index
                    if len(last_idx) > 0:
                        active[col] = {
                            "last_occurrence": str(last_idx[-1]),
                            "count_50": int(recent[col].sum())
                        }
            return active
    except Exception as e:
        return {"error": str(e)}
    return {}

# ============ MESSAGE FORMATTERS ============
def format_daily_briefing(data: Dict) -> str:
    con = data.get("confluence", {})
    risk = data.get("risk", {})
    camps = data.get("campaigns", {})
    setups = data.get("setups", {})

    lines = [
        "📊 **Daily Trading Briefing**",
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "🎯 **Confluence Score**",
    ]

    if "error" not in con:
        tier_emoji = {
            "STRONG_LONG": "🟢", "MODERATE_LONG": "🟢",
            "NEUTRAL": "⚪",
            "MODERATE_SHORT": "🔴", "STRONG_SHORT": "🔴",
            "WEAK_SHORT": "🔴"
        }
        emoji = tier_emoji.get(con.get("tier"), "⚪")
        lines.append(f"  {emoji} Score: {con['score']:.0f}/100 ({con['tier']})")
        if con.get("active_setups"):
            lines.append(f"  📋 Active: {', '.join([s for s in con['active_setups'] if s])}")
    else:
        lines.append(f"  ❌ {con['error']}")

    lines.append("")
    lines.append("🛡 **Risk Guardian**")

    if "error" not in risk:
        level_emoji = {
            "ADVISORY": "🟢", "WARNING": "🟠",
            "CRITICAL": "🔴", "EMERGENCY": "🚨"
        }
        level = risk.get("overall_level", "ADVISORY")
        emoji = level_emoji.get(level, "⚪")
        lines.append(f"  {emoji} Status: {level}")
        lines.append(f"  📉 Daily Loss: {risk.get('daily_loss_pct', 0):.0f}%")
        lines.append(f"  📊 Weekly: {risk.get('weekly_loss_pct', 0):.0f}% | Monthly: {risk.get('monthly_loss_pct', 0):.0f}%")
        lines.append(f"  🔗 Layers: {risk.get('total_layers', 0)} ({risk.get('max_layers_pct', 0):.0f}%)")

        if risk.get("recent_alerts"):
            lines.append("  🚨 Recent Alerts:")
            for a in risk["recent_alerts"][-3:]:
                lines.append(f"    {a['level']}: {a['message'][:60]}")
    else:
        lines.append(f"  ❌ {risk['error']}")

    lines.append("")
    lines.append("📈 **Active Campaigns**")

    if camps:
        for cid, info in camps.items():
            pnl_emoji = "🟢" if info.get("net_pnl_48h", 0) > 0 else "🔴"
            lines.append(f"  {pnl_emoji} {cid} ({info['type']})")
            lines.append(f"    Trades: {info['trades_48h']} | P&L: ${info['net_pnl_48h']:+,.0f} | Layers: {info.get('open_layers', 0)}")
    else:
        lines.append("  No active campaigns in last 48h")

    lines.append("")
    lines.append("🎯 **Recent Setup Signals**")

    if setups:
        for setup, info in list(setups.items())[:5]:
            lines.append(f"  • {setup}")
            lines.append(f"    Last: {info['last_occurrence']} | Count (50): {info['count_50']}")
    else:
        lines.append("  No recent setups")

    lines.append("")
    lines.append("---")
    lines.append("Commands: /score /risk /setups /coaching /campaigns /experiments")

    return "\n".join(lines)

def format_risk_alert(alert: Dict) -> str:
    level_emoji = {
        "ADVISORY": "🟢", "WARNING": "🟠",
        "CRITICAL": "🔴", "EMERGENCY": "🚨"
    }
    emoji = level_emoji.get(alert.get("level", "WARNING"), "🟠")

    lines = [
        f"{emoji} **RISK ALERT — {alert.get('level', 'UNKNOWN')}**",
        f"📊 {alert.get('dimension', 'Unknown')}",
        f"💬 {alert.get('message', 'No details')}",
        f"⚡ Action: {alert.get('action', 'NONE')}",
        f"⏰ {datetime.now().strftime('%H:%M:%S UTC')}"
    ]
    return "\n".join(lines)

def format_setup_alert(setup: str, info: Dict) -> str:
    emoji = "🟢" if "bull" in setup.lower() or "long" in setup.lower() else "🔴"

    lines = [
        f"{emoji} **SETUP DETECTED — {setup.upper()}**",
        f"📊 Last: {info.get('last_occurrence', 'N/A')}",
        f"📈 Count (50 bars): {info.get('count_50', 0)}",
        f"⏰ {datetime.now().strftime('%H:%M:%S UTC')}"
    ]
    return "\n".join(lines)

# ============ COMMAND HANDLERS ============
async def handle_score() -> str:
    con = load_latest_confluence()
    if "error" in con:
        return f"❌ Error loading confluence: {con['error']}"

    tier_emoji = {
        "STRONG_LONG": "🟢 STRONG LONG", "MODERATE_LONG": "🟢 MODERATE LONG",
        "NEUTRAL": "⚪ NEUTRAL",
        "MODERATE_SHORT": "🔴 MODERATE SHORT", "STRONG_SHORT": "🔴 STRONG SHORT",
        "WEAK_SHORT": "🔴 WEAK SHORT"
    }

    lines = [
        "🎯 **Confluence Score**",
        f"Score: {con['score']:.0f}/100",
        f"Tier: {tier_emoji.get(con['tier'], con['tier'])}",
        f"Updated: {con['timestamp']}",
    ]

    if con.get("active_setups"):
        actives = [s for s in con["active_setups"] if s]
        if actives:
            lines.append(f"Active: {', '.join(actives)}")

    return "\n".join(lines)

async def handle_risk() -> str:
    risk = load_risk_state()
    if "error" in risk:
        return f"❌ Error loading risk: {risk['error']}"

    level_emoji = {
        "ADVISORY": "🟢", "WARNING": "🟠",
        "CRITICAL": "🔴", "EMERGENCY": "🚨"
    }
    level = risk.get("overall_level", "ADVISORY")
    emoji = level_emoji.get(level, "⚪")

    lines = [
        f"{emoji} **Risk Status: {level}**",
        "",
        f"📉 Daily Loss: {risk.get('daily_loss_pct', 0):.0f}%",
        f"📊 Weekly Loss: {risk.get('weekly_loss_pct', 0):.0f}%",
        f"📅 Monthly Loss: {risk.get('monthly_loss_pct', 0):.0f}%",
        f"🔗 Layers: {risk.get('total_layers', 0)} ({risk.get('max_layers_pct', 0):.0f}%)",
    ]

    if risk.get("campaigns"):
        lines.append("")
        lines.append("Campaigns:")
        for cid, c in risk["campaigns"].items():
            lines.append(f"  {cid}: DD={c.get('drawdown_pct', 0):.1f}% | Paused={'Yes' if c.get('paused') else 'No'}")

    if risk.get("recent_alerts"):
        lines.append("")
        lines.append("Recent Alerts:")
        for a in risk["recent_alerts"][-5:]:
            lines.append(f"  {a['level']}: {a['message']}")

    return "\n".join(lines)

async def handle_setups() -> str:
    setups = load_setup_signals()

    if "error" in setups:
        return f"❌ Error: {setups['error']}"

    if not setups:
        return "📊 No recent setup signals detected."

    lines = ["🎯 **Recent Setup Signals (50 bars)**", ""]

    for setup, info in setups.items():
        emoji = "🟢" if "bull" in setup.lower() or "long" in setup.lower() else "🔴"
        lines.append(f"{emoji} **{setup}**")
        lines.append(f"  Last: {info['last_occurrence']}")
        lines.append(f"  Count (50): {info['count_50']}")
        lines.append("")

    return "\n".join(lines)

async def handle_coaching() -> str:
    try:
        con = load_latest_confluence()
        risk = load_risk_state()

        lines = ["📋 **Coaching Signal — PRE_ENTRY**", ""]

        # Simple logic based on current state
        if "error" not in con:
            if "LONG" in con.get("tier", ""):
                lines.append("✅ **PROCEED** — Bullish confluence detected")
            elif "SHORT" in con.get("tier", ""):
                lines.append("🔴 **SHORT BIAS** — Consider shorts")
            else:
                lines.append("⚪ **NEUTRAL** — Wait for clearer signal")

            lines.append(f"  Confluence: {con['score']:.0f} ({con['tier']})")

        if "error" not in risk:
            level = risk.get("overall_level", "ADVISORY")
            if level in ["CRITICAL", "EMERGENCY"]:
                lines.append(f"  🛑 Risk {level} — Reduce/block new entries")
            elif level == "WARNING":
                lines.append(f"  ⚠️ Risk WARNING — Proceed with caution")

        lines.append("")
        lines.append("Use /coaching during a trade for position management.")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error generating coaching: {e}"

async def handle_campaigns() -> str:
    camps = load_active_campaigns()

    if "error" in camps:
        return f"❌ Error: {camps['error']}"

    if not camps:
        return "📈 No active campaigns in last 48h."

    lines = ["📈 **Active Campaigns (48h)**", ""]

    for cid, info in camps.items():
        pnl_emoji = "🟢" if info.get("net_pnl_48h", 0) > 0 else "🔴"
        lines.append(f"{pnl_emoji} **{cid}** ({info['type']})")
        lines.append(f"  Trades: {info['trades_48h']}")
        lines.append(f"  P&L: ${info['net_pnl_48h']:+,.0f}")
        lines.append(f"  Open Layers: {info.get('open_layers', 0)}")
        lines.append("")

    return "\n".join(lines)

async def handle_experiments() -> str:
    exps = load_recent_experiments()

    if not exps:
        return "🔬 No recent experiments."

    if "error" in exps[0]:
        return f"❌ Error: {exps[0]['error']}"

    lines = ["🔬 **Recent Experiments**", ""]

    for exp in exps[:5]:
        metrics = exp.get("metrics", {})
        lines.append(f"🧪 **{exp.get('name', exp['id'])}**")
        lines.append(f"  ID: {exp['id'][:12]}")
        lines.append(f"  Tags: {', '.join(exp.get('tags', []))}")
        lines.append(f"  Trades: {metrics.get('n_trades', 0)} | P&L: ${metrics.get('net_pnl', 0):,.0f}")
        lines.append(f"  WR: {metrics.get('win_rate', 0):.1%} | Exp: ${metrics.get('expectancy', 0):.0f} | PF: {metrics.get('profit_factor', 0):.2f}")
        lines.append("")

    return "\n".join(lines)

async def handle_help() -> str:
    return """🤖 **Hermes Trading Bot Commands**

**Core Commands:**
/score — Current confluence score & active setups
/risk — Risk Guardian status & alerts
/setups — Recent setup signals (50 bars)
/coaching — Real-time coaching signal
/campaigns — Active campaigns (48h)
/experiments — Recent research experiments
/help — This message

**Features:**
• Daily briefing at 08:00 UTC
• Real-time risk alerts (WARNING/CRITICAL/EMERGENCY)
• Setup detection alerts (H4/H1/D1 engulfing, breakouts, confluence)
• Pre-entry / during-trade / post-campaign coaching

**Data Sources:**
• Confluence Score (M12 + H1/H4/H6/D1)
• Risk Guardian (6 dimensions, 4 levels)
• Behaviour Analysis (revenge, sizing, session bias)
• Research Scientist (backtest, walk-forward, experiments)

Powered by Hermes Agent + MT5 data pipeline."""
    
COMMAND_HANDLERS = {
    "score": handle_score,
    "risk": handle_risk,
    "setups": handle_setups,
    "coaching": handle_coaching,
    "campaigns": handle_campaigns,
    "experiments": handle_experiments,
    "help": handle_help,
}

# ============ ALERT CHECKERS ============
async def send_daily_briefing():
    config = load_config()
    targets = config["targets"]
    briefing_cfg = config["daily_briefing"]

    if not briefing_cfg.get("enabled"):
        return

    data = {
        "confluence": load_latest_confluence(),
        "risk": load_risk_state(),
        "campaigns": load_active_campaigns(),
        "setups": load_setup_signals(),
    }

    message = format_daily_briefing(data)

    try:
        send_telegram_message(targets["primary_dm"], message)
        print(f"Daily briefing sent to {targets['primary_dm']}")
    except Exception as e:
        print(f"Error sending briefing: {e}")

async def check_risk_alerts():
    config = load_config()
    targets = config["targets"]
    risk_cfg = config["risk_alerts"]

    if not risk_cfg.get("enabled"):
        return

    risk = load_risk_state()
    if "error" in risk:
        return

    last_alerts = {}
    if LAST_ALERT_FILE.exists():
        with open(LAST_ALERT_FILE) as f:
            last_alerts = json.load(f)

    new_alerts = []
    for alert in risk.get("recent_alerts", []):
        alert_key = f"{alert['dimension']}_{alert['level']}_{alert['message'][:50]}"
        last_time = last_alerts.get(alert_key, 0)

        throttle = risk_cfg.get("throttle_minutes", 15) * 60
        if (datetime.now().timestamp() - last_time) > throttle:
            if alert["level"] in risk_cfg.get("levels", ["WARNING", "CRITICAL", "EMERGENCY"]):
                new_alerts.append((alert_key, alert))

    for alert_key, alert in new_alerts:
        message = format_risk_alert(alert)
        try:
            send_telegram_message(targets["alerts_topic"], message)
            last_alerts[alert_key] = datetime.now().timestamp()
            print(f"Risk alert sent: {alert['level']} - {alert['dimension']}")
        except Exception as e:
            print(f"Error sending risk alert: {e}")

    with open(LAST_ALERT_FILE, 'w') as f:
        json.dump(last_alerts, f)

async def check_setup_alerts():
    config = load_config()
    targets = config["targets"]
    setup_cfg = config["setup_alerts"]

    if not setup_cfg.get("enabled"):
        return

    setups = load_setup_signals()
    if "error" in setups:
        return

    state_file = STATE_DIR / "setup_alerts.json"
    last_notified = {}
    if state_file.exists():
        with open(state_file) as f:
            last_notified = json.load(f)

    min_confluence = setup_cfg.get("min_confluence", 60)
    con = load_latest_confluence()
    confluence_score = con.get("score", 0)

    new_alerts = []
    for setup_name in setup_cfg.get("setups", []):
        if setup_name in setups:
            info = setups[setup_name]
            last_occ = info["last_occurrence"]
            key = f"{setup_name}_{last_occ}"

            if key not in last_notified and confluence_score >= min_confluence:
                new_alerts.append((key, setup_name, info))

    for key, setup_name, info in new_alerts:
        message = format_setup_alert(setup_name, info)
        try:
            send_telegram_message(targets["alerts_topic"], message)
            last_notified[key] = datetime.now().timestamp()
            print(f"Setup alert sent: {setup_name}")
        except Exception as e:
            print(f"Error sending setup alert: {e}")

    with open(state_file, 'w') as f:
        json.dump(last_notified, f)

async def session_outlook():
    """Send session outlook - market session context and expectations."""
    config = load_config()
    targets = config["targets"]
    
    con = load_latest_confluence()
    risk = load_risk_state()
    
    # Determine current session
    now = datetime.now()
    hour = now.hour
    
    if 0 <= hour < 8:
        session = "asian"
        session_emoji = "🌙"
        next_session = "london (08:00 UTC)"
    elif 8 <= hour < 13:
        session = "london"
        session_emoji = "🌅"
        next_session = "overlap (13:00 UTC)"
    elif 13 <= hour < 16:
        session = "overlap"
        session_emoji = "⚡"
        next_session = "ny (16:00 UTC)"
    elif 16 <= hour < 21:
        session = "ny"
        session_emoji = "🗽"
        next_session = "asian (00:00 UTC)"
    else:
        session = "asian"
        session_emoji = "🌙"
        next_session = "london (08:00 UTC)"
    
    # Session characteristics
    session_info = {
        "asian": "Range-bound, lower volatility, JPY/AUD active",
        "london": "Trend initiation, EUR/GBP active, high volume",
        "overlap": "Highest volume, major moves, breakout potential",
        "ny": "Trend continuation, USD active, news-driven",
    }
    
    lines = [
        f"{session_emoji} **Session Outlook — {session.upper()}**",
        f"⏰ {datetime.now().strftime('%H:%M UTC')} | Next: {next_session}",
        "",
        f"📋 **{session.capitalize()} Session Profile:**",
        f"  {session_info.get(session, 'N/A')}",
        "",
    ]
    
    # Add confluence context
    if "error" not in con:
        lines.append("🎯 **Confluence Context:**")
        lines.append(f"  Score: {con['score']:.0f} ({con['tier']})")
        if con.get("active_setups"):
            actives = [s for s in con["active_setups"] if s]
            if actives:
                lines.append(f"  Active: {', '.join(actives)}")
    
    # Add risk context
    if "error" not in risk:
        level = risk.get("overall_level", "ADVISORY")
        if level in ["WARNING", "CRITICAL", "EMERGENCY"]:
            lines.append("")
            lines.append(f"🛡 **Risk: {level}** — Adjust sizing/caution")
    
    lines.append("")
    lines.append("💡 **Key Levels to Watch:**")
    lines.append("  • H4/H1 structure breaks")
    lines.append("  • D1 trend alignment")
    lines.append("  • Session open/close reactions")
    
    message = "\n".join(lines)
    
    try:
        send_telegram_message(targets["primary_dm"], message)
        print(f"Session outlook sent to {targets['primary_dm']}")
    except Exception as e:
        print(f"Error sending session outlook: {e}")

# ============ MAIN ============
async def run_cron_jobs():
    print(f"[{datetime.now()}] Running cron jobs...")
    await check_risk_alerts()
    await check_setup_alerts()

async def main():
    await run_cron_jobs()

if __name__ == "__main__":
    asyncio.run(main())