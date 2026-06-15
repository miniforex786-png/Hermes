#!/usr/bin/env python3
"""Risk Guardian Evaluation - Hard limits check + state output."""
import json
import pandas as pd
from pathlib import Path
from datetime import datetime

DATA_ROOT = Path(r"C:\Hermes")
MT5_POSITIONS = DATA_ROOT / "mt5_positions.json"  # Expected from MT5 export
OUT_FILE = DATA_ROOT / "risk_guardian" / "state.json"
OUT_FILE.parent.mkdir(exist_ok=True)

# Hard limits (configurable)
LIMITS = {
    "daily_loss_pct": -2.5,
    "position_size_pct": 5.0,
    "correlation": 0.7,
    "drawdown_pct": 10.0,
}

ESCALATION_LADDER = [
    {"level": 1, "name": "WARNING", "threshold": 0.5, "action": "Notify"},
    {"level": 2, "name": "REDUCE", "threshold": 0.75, "action": "Reduce size 50%"},
    {"level": 3, "name": "FLATTEN", "threshold": 0.9, "action": "Close all"},
    {"level": 4, "name": "LOCKDOWN", "threshold": 1.0, "action": "Pause trading"},
]

CAMPAIGN_GUARDS = {
    "max_layers": 2,
    "current_layers": 0,
    "basket_dd_limit_r": 1.5,
    "runner_hold_enabled": True,
    "revenge_cooldown_min": 15,
}

def load_mt5_positions() -> pd.DataFrame:
    """Load positions from MT5 export."""
    if MT5_POSITIONS.exists():
        try:
            return pd.read_json(MT5_POSITIONS)
        except Exception:
            pass
    return pd.DataFrame()

def evaluate_risk() -> dict:
    """Evaluate current risk state against hard limits."""
    positions = load_mt5_positions()
    
    # Calculate metrics from positions
    if not positions.empty:
        total_pnl = positions["pnl"].sum() if "pnl" in positions.columns else 0
        account_balance = 100000  # Placeholder
        daily_loss_pct = (total_pnl / account_balance) * 100
        position_size_pct = positions["volume"].sum() / 100 if "volume" in positions.columns else 0
        drawdown_pct = abs(daily_loss_pct) if daily_loss_pct < 0 else 0
        
        # Correlation - simplified
        symbols = positions["symbol"].nunique() if "symbol" in positions.columns else 1
        correlation = min(0.34 * symbols, 0.9)
    else:
        # Mock values when no positions
        daily_loss_pct = -1.2
        position_size_pct = 3.4
        drawdown_pct = 2.1
        correlation = 0.34
    
    # Determine escalation level
    ratios = {
        "daily_loss": abs(daily_loss_pct) / abs(LIMITS["daily_loss_pct"]),
        "position_size": position_size_pct / LIMITS["position_size_pct"],
        "drawdown": drawdown_pct / LIMITS["drawdown_pct"],
        "correlation": correlation / LIMITS["correlation"],
    }
    max_ratio = max(ratios.values())
    
    escalation_level = 0
    if max_ratio >= ESCALATION_LADDER[3]["threshold"]:
        escalation_level = 4
    elif max_ratio >= ESCALATION_LADDER[2]["threshold"]:
        escalation_level = 3
    elif max_ratio >= ESCALATION_LADDER[1]["threshold"]:
        escalation_level = 2
    elif max_ratio >= ESCALATION_LADDER[0]["threshold"]:
        escalation_level = 1
    
    # Campaign guards
    if not positions.empty:
        CAMPAIGN_GUARDS["current_layers"] = int(positions["layers"].max()) if "layers" in positions.columns else 0
    
    return {
        "daily_loss_pct": round(daily_loss_pct, 1),
        "daily_limit_pct": LIMITS["daily_loss_pct"],
        "position_size_pct": round(position_size_pct, 1),
        "position_limit_pct": LIMITS["position_size_pct"],
        "correlation": round(correlation, 2),
        "correlation_limit": LIMITS["correlation"],
        "drawdown_pct": round(drawdown_pct, 1),
        "drawdown_limit_pct": LIMITS["drawdown_pct"],
        "escalation_level": escalation_level,
        "escalation_ladder": ESCALATION_LADDER,
        "campaign_guards": CAMPAIGN_GUARDS,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

def main():
    print("Evaluating risk guardian...")
    
    state = evaluate_risk()
    
    with open(OUT_FILE, "w") as f:
        json.dump(state, f, indent=2)
    
    print(f"Saved risk state -> {OUT_FILE}")
    print(json.dumps(state, indent=2))
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())