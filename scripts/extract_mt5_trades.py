#!/usr/bin/env python3
"""Extract MT5 trade history (deals) to JSON for trading journal & behaviour analysis."""
import MetaTrader5 as mt5
import json
from pathlib import Path
from datetime import datetime, timedelta

MT5_PATH = r"C:\Program Files\MT5 5430 X64 - Hermes\terminal64.exe"
OUT_FILE = Path(r"C:\Hermes\trading_journal.json")

def init_mt5():
    if not mt5.initialize(path=MT5_PATH):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    acc = mt5.account_info()
    print(f"Connected: {acc.login} @ {acc.server}")
    return True

def extract_trades(days_back=90):
    now = datetime.now()
    thresh = now - timedelta(days=days_back)
    
    deals = mt5.history_deals_get(thresh, now)
    if deals is None:
        return []
    
    # Group deals by position to reconstruct trades
    deals_list = []
    for d in deals:
        deals_list.append({
            "ticket": d.ticket,
            "position_id": d.position_id,
            "symbol": d.symbol,
            "type": "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL",
            "entry": "IN" if d.entry == mt5.DEAL_ENTRY_IN else "OUT" if d.entry == mt5.DEAL_ENTRY_OUT else "REVERSE",
            "volume": d.volume,
            "price": d.price,
            "profit": d.profit,
            "swap": d.swap,
            "commission": d.commission,
            "comment": d.comment,
            "magic": d.magic,
            "time": datetime.fromtimestamp(d.time).isoformat() + "Z",
        })
    
    return deals_list

def build_campaigns(deals):
    """Group trades by campaign (magic number / comment pattern)."""
    campaigns = {}
    for d in deals:
        # Determine campaign from magic or comment
        magic = d.get("magic", 0)
        comment = d.get("comment", "")
        
        if magic > 100000:
            camp_id = f"PROBE-{magic}"
            camp_type = "probe"
        elif "DISCR" in comment.upper():
            camp_id = f"DISCR-{magic}"
            camp_type = "discretionary"
        else:
            camp_id = f"AUTO-{magic}"
            camp_type = "auto"
        
        if camp_id not in campaigns:
            campaigns[camp_id] = {
                "id": camp_id,
                "type": camp_type,
                "symbol": d["symbol"],
                "trades": [],
                "total_pnl": 0,
                "layers": 0
            }
        
        campaigns[camp_id]["trades"].append(d)
        if d["entry"] == "OUT":
            campaigns[camp_id]["total_pnl"] += d["profit"]
    
    return campaigns

def main():
    try:
        init_mt5()
        deals = extract_trades(90)
        campaigns = build_campaigns(deals)
        
        data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_trades": len(deals),
            "trades": deals,
            "campaigns": campaigns
        }
        
        with open(OUT_FILE, "w") as f:
            json.dump(data, f, indent=2)
        
        print(f"[OK] Exported {len(deals)} trades across {len(campaigns)} campaigns -> {OUT_FILE}")
        print(json.dumps({"trades": len(deals), "campaigns": len(campaigns)}, indent=2))
        return 0
        
    except Exception as e:
        print(f"[FAIL] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    import sys
    sys.exit(main())
