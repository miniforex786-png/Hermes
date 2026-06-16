#!/usr/bin/env python3
"""Extract MT5 account PnL and equity to JSON for live PnL dashboard."""
import MetaTrader5 as mt5
import json
from pathlib import Path
from datetime import datetime, timedelta

MT5_PATH = r"C:\Program Files\MT5 5430 X64 - Hermes\terminal64.exe"
OUT_FILE = Path(r"C:\Hermes\live_pnl.json")

def init_mt5():
    if not mt5.initialize(path=MT5_PATH):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    acc = mt5.account_info()
    print(f"Connected: {acc.login} @ {acc.server}")
    return True

def extract_pnl():
    acc = mt5.account_info()
    if acc is None:
        return {}
    
    # Get daily PnL from deals
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    thresh = today_start - timedelta(days=30)  # monthly
    
    deals = mt5.history_deals_get(thresh, now)
    daily_realized = 0
    weekly_realized = 0
    monthly_realized = 0
    
    if deals:
        for d in deals:
            if d.profit != 0:
                deal_time = datetime.fromtimestamp(d.time)
                if deal_time >= today_start:
                    daily_realized += d.profit
                if deal_time >= today_start - timedelta(days=7):
                    weekly_realized += d.profit
                monthly_realized += d.profit
    
    return {
        "account": acc.login,
        "server": acc.server,
        "currency": acc.currency,
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.margin_free,
        "margin_level": acc.margin_level,
        "profit": acc.profit,  # unrealized
        "net_pnl": acc.equity - acc.balance,  # total unrealized + realized today
        "daily_pnl": daily_realized,
        "weekly_pnl": weekly_realized,
        "monthly_pnl": monthly_realized,
        "risk_used_pct": round((acc.margin / acc.equity * 100) if acc.equity else 0, 1),
        "max_drawdown_pct": 0,  # Would need history to calc
    }

def main():
    try:
        init_mt5()
        pnl = extract_pnl()
        
        if not pnl:
            print("✗ Failed to get account info")
            return 1
        
        data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "net_pnl": round(pnl["net_pnl"], 2),
            "realized_pnl": round(pnl["daily_pnl"], 2),
            "unrealized_pnl": round(pnl["profit"], 2),
            "equity": round(pnl["equity"], 2),
            "balance": round(pnl["balance"], 2),
            "max_drawdown_pct": pnl["max_drawdown_pct"],
            "risk_used_pct": pnl["risk_used_pct"],
            "daily_pnl": round(pnl["daily_pnl"], 2),
            "weekly_pnl": round(pnl["weekly_pnl"], 2),
            "monthly_pnl": round(pnl["monthly_pnl"], 2),
            "open_positions": 0,  # Will be filled by positions script
            "mock": False
        }
        
        with open(OUT_FILE, "w") as f:
            json.dump(data, f, indent=2)
        
        print(f"✓ Exported PnL → {OUT_FILE}")
        print(json.dumps(data, indent=2))
        return 0
        
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    import sys
    sys.exit(main())