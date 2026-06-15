#!/usr/bin/env python3
"""Module 2: Multi-TF Alignment - Align M12/H1/H4/H6/D1 data for XAUUSD."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path(r"C:\Hermes")
MT5_DIR = DATA_ROOT / "mt5_data_full"
OUT_DIR = DATA_ROOT / "aligned_data"
OUT_DIR.mkdir(exist_ok=True)

TIMEFRAMES = ["M12", "H1", "H4", "H6", "D1"]

def resample_to_tf(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Resample tick/OHLC data to target timeframe."""
    if tf == "M12":
        # 12-minute bars
        return df.resample("12min").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna()
    elif tf == "H1":
        return df.resample("1H").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna()
    elif tf == "H4":
        return df.resample("4H").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna()
    elif tf == "H6":
        return df.resample("6H").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna()
    elif tf == "D1":
        return df.resample("1D").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna()
    return df

def main():
    print("Aligning multi-timeframe data for XAUUSD...")
    
    # Find M1 or tick data as source
    source_files = list(MT5_DIR.glob("XAUUSD_M1*.parquet"))
    if not source_files:
        source_files = list(MT5_DIR.glob("XAUUSD_*.parquet"))
    
    if not source_files:
        print("No MT5 source data found")
        return 1
    
    # Use the most recent/largest file
    source_file = max(source_files, key=lambda f: f.stat().st_size)
    print(f"Reading from: {source_file}")
    
    df = pd.read_parquet(source_file)
    df.index = pd.to_datetime(df.index)
    
    # Ensure OHLC columns exist
    if "open" not in df.columns:
        # Try to find close/price column
        if "close" in df.columns:
            df["open"] = df["close"].shift(1)
            df["high"] = df[["close", "open"]].max(axis=1)
            df["low"] = df[["close", "open"]].min(axis=1)
        else:
            print("No OHLC data found")
            return 1
    
    # Resample to each timeframe
    for tf in TIMEFRAMES:
        resampled = resample_to_tf(df, tf)
        out_file = OUT_DIR / f"XAUUSD_{tf}_aligned.parquet"
        resampled.to_parquet(out_file)
        print(f"Saved {tf}: {len(resampled)} bars -> {out_file}")
    
    print("Multi-TF alignment complete")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())