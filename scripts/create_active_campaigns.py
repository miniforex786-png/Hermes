#!/usr/bin/env python3
"""Create active_campaigns.json from trading_journal.json for R2 upload."""
import json
from pathlib import Path

INPUT_FILE = Path(r"C:\Hermes\trading_journal.json")
OUTPUT_FILE = Path(r"C:\Hermes\active_campaigns.json")

with open(INPUT_FILE) as f:
    data = json.load(f)

campaigns = data.get("campaigns", {})
active = {}
for camp_id, camp_data in campaigns.items():
    trades = camp_data.get("trades", [])
    out_trades = [t for t in trades if t.get("entry") == "OUT"]
    total_pnl = sum(t.get("profit", 0) for t in out_trades)
    wins = sum(1 for t in out_trades if t.get("profit", 0) > 0)
    losses = sum(1 for t in out_trades if t.get("profit", 0) <= 0)
    win_rate = wins / len(out_trades) if out_trades else 0
    
    active[camp_id] = {
        "id": camp_id,
        "type": camp_data.get("type", "unknown"),
        "symbol": camp_data.get("symbol", "XAUUSD"),
        "total_trades": len(trades),
        "closed_trades": len(out_trades),
        "total_pnl": total_pnl,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "last_trade": trades[-1]["time"] if trades else None
    }

output = {
    "timestamp": data.get("timestamp"),
    "total_campaigns": len(active),
    "campaigns": active
}

with open(OUTPUT_FILE, "w") as f:
    json.dump(output, f, indent=2)

print(f"[OK] Created {OUTPUT_FILE} with {len(active)} campaigns")
for camp_id, c in active.items():
    print(f"  {camp_id}: type={c['type']}, trades={c['closed_trades']}, pnl={c['total_pnl']:.2f}, wr={c['win_rate']:.1%}")
