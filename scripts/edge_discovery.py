#!/usr/bin/env python3
"""Setup labeling + expectancy analysis for XAUUSD."""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_ROOT = Path(r"C:\Hermes")
CONFLUENCE_DIR = DATA_ROOT / "confluence_score"
OUT_DIR = DATA_ROOT / "edge_discovery"
OUT_DIR.mkdir(exist_ok=True)

SETUP_RULES = {
    "H1_MOMENTUM": {"min_score": 70, "direction": "LONG", "tf": "H1"},
    "H4_REVERSION": {"min_score": 65, "direction": "LONG", "tf": "H4"},
    "H4_BREAKOUT": {"min_score": 75, "direction": "LONG", "tf": "H4"},
}

FWD_WINDOWS = {"5m": 5, "15m": 15, "30m": 30}  # minutes

def label_setups(confluence_df: pd.DataFrame, m12_df: pd.DataFrame) -> pd.DataFrame:
    """Label each bar with setup type and calculate forward returns."""
    results = []
    
    for idx, conf_row in confluence_df.iterrows():
        score = conf_row["confluence_score"]
        tier = conf_row["tier"]
        
        setup_name = None
        direction = None
        
        for setup, rules in SETUP_RULES.items():
            if score >= rules["min_score"] and "LONG" in tier:
                setup_name = setup
                direction = rules["direction"]
                break
        
        if setup_name is None:
            continue
        
        # Get M12 price at this timestamp
        if idx not in m12_df.index:
            continue
        entry_price = m12_df.loc[idx, "close"]
        
        # Calculate forward returns
        fwd_returns = {}
        for name, minutes in FWD_WINDOWS.items():
            fwd_idx = idx + pd.Timedelta(minutes=minutes)
            # Find closest future index
            future_idx = m12_df.index[m12_df.index >= fwd_idx]
            if len(future_idx) > 0:
                exit_price = m12_df.loc[future_idx[0], "close"]
                ret_pct = (exit_price - entry_price) / entry_price * 10000  # pips
                fwd_returns[name] = round(ret_pct, 1)
            else:
                fwd_returns[name] = 0
        
        results.append({
            "timestamp": idx,
            "setup_name": setup_name,
            "direction": direction,
            "confluence_score": score,
            "tier": tier,
            "regime": conf_row.get("trend_alignment", 0) > 0.6 and "TRENDING" or "RANGING",
            "session": "LONDON" if 7 <= idx.hour <= 16 else "ASIA",
            **fwd_returns
        })
    
    return pd.DataFrame(results).set_index("timestamp")

def main():
    print("Running edge discovery / setup labeling...")
    
    confluence_file = CONFLUENCE_DIR / "XAUUSD_confluence_score.parquet"
    m12_file = DATA_ROOT / "aligned_data" / "XAUUSD_M12_aligned.parquet"
    
    if not confluence_file.exists() or not m12_file.exists():
        print("Required input files not found")
        return 1
    
    confluence_df = pd.read_parquet(confluence_file)
    m12_df = pd.read_parquet(m12_file)
    
    # Label setups
    labeled = label_setups(confluence_df, m12_df)
    
    out_file = OUT_DIR / "XAUUSD_setup_labels.parquet"
    labeled.to_parquet(out_file)
    print(f"Saved setup labels: {len(labeled)} rows -> {out_file}")
    
    # Print summary
    if len(labeled) > 0:
        print(f"Setups found: {labeled['setup_name'].value_counts().to_dict()}")
        print(f"Avg 30m return: {labeled['fwd_return_30m'].mean():.1f} pips")
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())