#!/usr/bin/env python3
"""
MT5 Historical Data Extractor — Chunked Pulls for Full History

Run on your LOCAL PC with MT5 installed and Python environment.
Outputs Parquet files per symbol/timeframe with complete history.
"""

import MetaTrader5 as mt5
import pandas as pd
from pathlib import Path
import time

# ============ CONFIG ============
MT5_PATH = r"C:\Program Files\MT5 5430 X64 - Hermes\terminal64.exe"

SYMBOLS = ["XAUUSD", "XAUUSDc"]

TIMEFRAMES = {
    "M12": mt5.TIMEFRAME_M12,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "H6":  mt5.TIMEFRAME_H6,
    "D1":  mt5.TIMEFRAME_D1,
}

# Target bars per timeframe (None = get ALL available history)
TARGET_BARS = {
    "M12": 400000,
    "H1":  100000,
    "H4":  50000,
    "H6":  50000,
    "D1":  10000,
}

CHUNK_SIZE = 50000
# Output to mt5_data_full alongside existing mt5_data
OUT_DIR = Path(r"C:\Hermes\mt5_data_full")
OUT_DIR.mkdir(exist_ok=True)

# ============ HELPERS ============
def init_mt5():
    if not mt5.initialize(path=MT5_PATH):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    acc = mt5.account_info()
    print(f"✓ Connected: {acc.login} @ {acc.server} ({acc.currency})")
    return True

def ensure_symbol(symbol):
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Symbol {symbol} not found or not enabled in Market Watch")
    info = mt5.symbol_info(symbol)
    print(f"✓ {symbol}: {info.description}, spread={info.spread}, digits={info.digits}")
    return True

def pull_chunk(symbol, tf_const, start_pos, count):
    rates = mt5.copy_rates_from_pos(symbol, tf_const, start_pos, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df = df[["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]]
    df.columns = ["open", "high", "low", "close", "volume", "spread", "real_volume"]
    return df

def pull_full_history(symbol, tf_name, tf_const, target_bars):
    print(f"\n  {symbol} {tf_name}: pulling up to {target_bars:,} bars...")
    
    all_chunks = []
    total_pulled = 0
    start_pos = 0
    
    while True:
        remaining = target_bars - total_pulled if target_bars else CHUNK_SIZE
        pull_count = min(CHUNK_SIZE, remaining) if target_bars else CHUNK_SIZE
        
        chunk = pull_chunk(symbol, tf_const, start_pos, pull_count)
        if chunk is None or len(chunk) == 0:
            print(f"    End of history at position {start_pos}")
            break
        
        all_chunks.append(chunk)
        pulled = len(chunk)
        total_pulled += pulled
        start_pos += pulled
        
        oldest = chunk.index.min().strftime("%Y-%m-%d")
        newest = chunk.index.max().strftime("%Y-%m-%d")
        print(f"    Chunk {len(all_chunks)}: {pulled:,} bars ({oldest} → {newest}), total={total_pulled:,}")
        
        if target_bars and total_pulled >= target_bars:
            print(f"    Reached target {target_bars:,} bars")
            break
        if pulled < pull_count:
            print(f"    Partial chunk — end of history")
            break
        
        time.sleep(0.05)
    
    if not all_chunks:
        return None
    
    df = pd.concat(reversed(all_chunks))
    df = df[~df.index.duplicated(keep="first")]
    df.sort_index(inplace=True)
    return df

def save_parquet(df, symbol, tf_name):
    out_file = OUT_DIR / f"{symbol}_{tf_name}.parquet"
    df.to_parquet(out_file, compression="zstd")
    size_mb = out_file.stat().st_size / (1024 * 1024)
    print(f"  ✓ Saved: {out_file.name} ({len(df):,} bars, {size_mb:.1f} MB)")
    return out_file

# ============ MAIN ============
if __name__ == "__main__":
    print("=" * 60)
    print("MT5 Historical Data Extractor — Full History")
    print("Output:", OUT_DIR)
    print("=" * 60)
    
    try:
        init_mt5()
        
        for symbol in SYMBOLS:
            ensure_symbol(symbol)
            
            for tf_name, tf_const in TIMEFRAMES.items():
                target = TARGET_BARS.get(tf_name)
                df = pull_full_history(symbol, tf_name, tf_const, target)
                
                if df is None or len(df) == 0:
                    print(f"  ✗ No data for {symbol} {tf_name}")
                    continue
                
                save_parquet(df, symbol, tf_name)
        
        print("\n" + "=" * 60)
        print("DONE — Files in:", OUT_DIR)
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        mt5.shutdown()