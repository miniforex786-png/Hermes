#!/usr/bin/env python3
"""Extract current MT5 positions to JSON for live risk monitoring."""
import MetaTrader5 as mt5
import json
from pathlib import Path
from datetime import datetime

MT5_PATH = r"C:\Program Files\MT5 5430 X64 - Hermes\terminal64.exe"
OUT_FILE = Path(r"C:\Hermes\mt5_positions.json")

def init_mt5():
    if not mt5.initialize(path=MT5_PATH):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    acc = mt5.account_info()
    print(f"Connected: {acc.login} @ {acc.server}")
    return True

def extract_positions():
    positions = mt5.positions_get()
    if positions is None:
        return []
    
    pos_list = []
    for p in positions:
        pos_list.append({
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": p.volume,
            "price_open": p.price_open,
            "price_current": p.price_current,
            "sl": p.sl,
            "tp": p.tp,
            "pnl": p.profit,
            "swap": p.swap,
            "comment": p.comment,
            "magic": p.magic,
            "time_open": datetime.fromtimestamp(p.time).isoformat() + "Z",
            "time_update": datetime.fromtimestamp(p.time_update).isoformat() + "Z" if p.time_update else None,
        })
    return pos_list

def main():
    try:
        init_mt5()
        positions = extract_positions()
        
        data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "count": len(positions),
            "positions": positions
        }
        
        with open(OUT_FILE, "w") as f:
            json.dump(data, f, indent=2)
        
        print(f"✓ Exported {len(positions)} positions → {OUT_FILE}")
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