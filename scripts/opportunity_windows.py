#!/usr/bin/env python3
"""Module 3: Opportunity Windows - Session/DOW/Context statistics."""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_ROOT = Path(r"C:\Hermes")
SETUPS_FILE = DATA_ROOT / "edge_discovery" / "XAUUSD_setup_labels.parquet"
OUT_DIR = DATA_ROOT / "opportunity_windows"
OUT_DIR.mkdir(exist_ok=True)

def calculate_stats(df: pd.DataFrame) -> dict:
    """Calculate session, DOW, and context statistics."""
    stats = {}
    
    # Session stats
    df["session"] = df.index.hour.apply(lambda h: 
        "ASIA" if 0 <= h < 7 else
        "LONDON" if 7 <= h < 12 else
        "NY" if 12 <= h < 17 else
        "OVERLAP" if 17 <= h < 19 else "NY"
    )
    session_stats = df.groupby("session").agg(
        win_rate=("fwd_return_30m", lambda x: (x > 0).mean()),
        avg_r=("fwd_return_30m", "mean"),
        count=("fwd_return_30m", "count"),
        expectancy=("fwd_return_30m", lambda x: (x > 0).sum() / len(x) * x[x > 0].mean() + (x <= 0).sum() / len(x) * x[x <= 0].mean() if len(x) > 0 else 0)
    ).round(4)
    stats["session"] = session_stats.reset_index().to_dict('records')
    
    # DOW stats
    df["dow"] = df.index.dayofweek.map({0: "MONDAY", 1: "TUESDAY", 2: "WEDNESDAY", 3: "THURSDAY", 4: "FRIDAY", 5: "SATURDAY", 6: "SUNDAY"})
    dow_stats = df.groupby("dow").agg(
        win_rate=("fwd_return_30m", lambda x: (x > 0).mean()),
        avg_r=("fwd_return_30m", "mean"),
        count=("fwd_return_30m", "count")
    ).round(4)
    stats["dow"] = dow_stats.reset_index().to_dict('records')
    
    # Context stats (volatility regime + trend)
    df["context"] = df.apply(lambda r: 
        "QUIET_TREND" if r.get("volatility_regime", 0) > 0.7 and r.get("trend_alignment", 0) > 0.6 else
        "ELEVATED_RANGE" if r.get("volatility_regime", 0) > 0.5 else
        "EXTREME_BREAKOUT", axis=1)
    context_stats = df.groupby("context").agg(
        win_rate=("fwd_return_30m", lambda x: (x > 0).mean()),
        avg_r=("fwd_return_30m", "mean"),
        count=("fwd_return_30m", "count")
    ).round(4)
    stats["context"] = context_stats.reset_index().to_dict('records')
    
    return stats

def main():
    print("Calculating opportunity windows...")
    
    if not SETUPS_FILE.exists():
        print("Setup labels not found")
        return 1
    
    df = pd.read_parquet(SETUPS_FILE)
    stats = calculate_stats(df)
    
    # Save CSVs
    for name, records in stats.items():
        out_file = OUT_DIR / f"{name}_stats.csv"
        pd.DataFrame(records).to_csv(out_file, index=False)
        print(f"Saved {name}: {len(records)} rows -> {out_file}")
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())