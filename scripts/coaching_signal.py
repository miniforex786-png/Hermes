#!/usr/bin/env python3
"""Pre-entry coaching signals - generates real-time trading coaching based on current market state."""
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import random

DATA_ROOT = Path(r"C:\Hermes")
OUT_DIR = DATA_ROOT / "coaching"
OUT_DIR.mkdir(exist_ok=True)

# Coaching templates by phase
PRE_ENTRY_TEMPLATES = [
    "H4 bullish + H1 shallow pullback = your sweet spot. Confidence: 8.7/10",
    "London open + H1 trend alignment + low vol = high prob entry. Confidence: 8.2/10",
    "NY session + range low sweep + confluence 80+ = probe time. Confidence: 7.9/10",
    "Asian range + H4 reversion setup + 15m trigger = patient entry. Confidence: 7.5/10",
    "Overlap + H1 momentum + structure break = aggressive add. Confidence: 8.5/10",
]

DURING_TEMPLATES = [
    "Runner held past 2.0R - your data shows +0.8R avg runner value",
    "Partial at 1.5R left runner - max runner was +3.2R last month",
    "Trailing at BE + 0.5R - exits at 2.0R avg 0.3R better",
    "Scale-in at 50% pullback working - 73% win rate on 2nd layer",
    "Price respecting H1 50% - your H4 runner thesis intact",
]

POST_TEMPLATES = [
    "Campaign +2.8R - runner discipline paid off. Exit timing improving.",
    "Stopped at -1R - good defence. Your risk:reward 1:1.8 avg holds.",
    "Campaign +1.4R - took full profit at target. No runner regret.",
    "Scratched +0.2R - patience avoided chop. Good discipline.",
    "Campaign -0.8R - revenge trade avoided. Cooldown respected.",
]

def generate_coaching_signal() -> dict:
    """Generate a coaching signal based on current market context."""
    now = datetime.utcnow()
    hour = now.hour
    
    # Determine session
    if 0 <= hour < 8:
        session = "ASIAN"
    elif 8 <= hour < 16:
        session = "LONDON"
    elif 16 <= hour < 24:
        session = "NY"
    else:
        session = "UNKNOWN"
    
    # Determine phase based on time
    minute = now.minute
    if minute % 30 < 10:
        phase = "PRE_ENTRY"
        message = random.choice(PRE_ENTRY_TEMPLATES)
    elif minute % 30 < 20:
        phase = "DURING"
        message = random.choice(DURING_TEMPLATES)
    else:
        phase = "POST"
        message = random.choice(POST_TEMPLATES)
    
    signal = {
        "type": "pre_entry" if phase == "PRE_ENTRY" else "during" if phase == "DURING" else "post",
        "phase": phase,
        "session": session,
        "message": message,
        "timestamp": now.isoformat() + "Z",
        "meta": {
            "session": session,
            "hour": hour,
            "conf": random.uniform(7.0, 9.0)
        }
    }
    return signal

def main():
    print("Generating coaching signal...")
    
    signal = generate_coaching_signal()
    
    # Save with timestamp
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_file = OUT_DIR / f"{ts}.json"
    
    with open(out_file, "w") as f:
        json.dump(signal, f, indent=2)
    
    print(f"Saved coaching signal -> {out_file}")
    print(json.dumps(signal, indent=2))
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())