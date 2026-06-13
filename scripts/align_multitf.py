#!/usr/bin/env python3
"""
Multi-Timeframe Alignment Pipeline — Module 2 Foundation

Loads M12 (execution) + H1/H4/H6/D1 (context), aligns to M12 grid,
forward-fills higher-TF context, computes core features.
Outputs analysis-ready Parquet for edge discovery.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ============ CONFIG ============
DATA_DIR = Path(r"C:\Hermes\mt5_data_full")  # or /tmp/Hermes_full/mt5_data_full on cloud
SYMBOL = "XAUUSD"
OUT_DIR = Path(r"C:\Hermes\aligned_data")
OUT_DIR.mkdir(exist_ok=True)

TIMEFRAMES = {
    "M12": "12min",   # execution timeframe
    "H1":  "1h",
    "H4":  "4h",
    "H6":  "6h",
    "D1":  "1D",
}

# Session definitions (UTC)
SESSIONS = {
    "asian":   (0, 8),
    "london":  (8, 16),
    "ny":      (13, 21),
    "overlap": (13, 16),  # London/NY overlap
}

# ============ HELPERS ============
def load_tf(tf_name):
    """Load a single timeframe parquet."""
    f = DATA_DIR / f"{SYMBOL}_{tf_name}.parquet"
    if not f.exists():
        raise FileNotFoundError(f"{f} not found")
    df = pd.read_parquet(f)
    df.index = pd.to_datetime(df.index, utc=True)
    return df

def resample_to_m12(df, tf_name):
    """Resample higher TF to M12 grid using forward-fill (no look-ahead)."""
    # Target M12 index
    m12_idx = pd.date_range(
        start=df.index.min().floor("12min"),
        end=df.index.max().ceil("12min"),
        freq="12min",
        tz="UTC"
    )
    
    # Reindex with forward-fill (last known higher-TF bar)
    df_m12 = df.reindex(m12_idx, method="ffill")
    df_m12.index.name = "time"
    
    # Prefix columns
    df_m12.columns = [f"{tf_name}_{c}" for c in df_m12.columns]
    return df_m12

def compute_m12_features(df):
    """Compute core M12 features."""
    out = pd.DataFrame(index=df.index)
    
    # Returns
    out["ret_1"] = df["M12_close"].pct_change()
    out["ret_5"] = df["M12_close"].pct_change(5)
    out["ret_20"] = df["M12_close"].pct_change(20)
    
    # Log returns
    out["log_ret_1"] = np.log(df["M12_close"] / df["M12_close"].shift(1))
    
    # Volatility (rolling std of log returns)
    out["vol_20"] = out["log_ret_1"].rolling(20).std() * np.sqrt(20 * 12 / 60)  # annualized-ish
    out["vol_50"] = out["log_ret_1"].rolling(50).std() * np.sqrt(50 * 12 / 60)
    
    # Range
    out["range_pct"] = (df["M12_high"] - df["M12_low"]) / df["M12_close"]
    out["body_pct"] = abs(df["M12_close"] - df["M12_open"]) / df["M12_close"]
    out["wick_up_pct"] = (df["M12_high"] - df[["M12_open", "M12_close"]].max(axis=1)) / df["M12_close"]
    out["wick_down_pct"] = (df[["M12_open", "M12_close"]].min(axis=1) - df["M12_low"]) / df["M12_close"]
    
    # Volume
    out["vol_rel_20"] = df["M12_volume"] / df["M12_volume"].rolling(20).mean()
    out["vol_rel_50"] = df["M12_volume"] / df["M12_volume"].rolling(50).mean()
    
    # Spread
    out["spread_rel"] = df["M12_spread"] / df["M12_spread"].rolling(50).mean()
    
    # Trend (EMA alignment)
    out["ema_20"] = df["M12_close"].ewm(span=20, adjust=False).mean()
    out["ema_50"] = df["M12_close"].ewm(span=50, adjust=False).mean()
    out["ema_200"] = df["M12_close"].ewm(span=200, adjust=False).mean()
    out["trend_20_50"] = (out["ema_20"] - out["ema_50"]) / df["M12_close"]
    out["trend_50_200"] = (out["ema_50"] - out["ema_200"]) / df["M12_close"]
    out["price_vs_ema20"] = (df["M12_close"] - out["ema_20"]) / df["M12_close"]
    
    # RSI
    delta = df["M12_close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi_14"] = 100 - (100 / (1 + rs))
    
    return out

def add_session_features(df):
    """Add trading session features."""
    out = pd.DataFrame(index=df.index)
    hour = df.index.hour
    minute = df.index.minute
    tod = hour + minute / 60  # time of day as float
    
    out["hour"] = hour
    out["tod"] = tod
    out["is_asian"] = ((hour >= 0) & (hour < 8)).astype(int)
    out["is_london"] = ((hour >= 8) & (hour < 16)).astype(int)
    out["is_ny"] = ((hour >= 13) & (hour < 21)).astype(int)
    out["is_overlap"] = ((hour >= 13) & (hour < 16)).astype(int)
    out["is_weekend"] = (df.index.dayofweek >= 5).astype(int)
    
    # Session progress (0-1 within session)
    out["london_progress"] = np.where(out["is_london"], (tod - 8) / 8, 0)
    out["ny_progress"] = np.where(out["is_ny"], (tod - 13) / 8, 0)
    
    return out

def add_higher_tf_features(df):
    """Compute features from higher-TF context columns."""
    out = pd.DataFrame(index=df.index)
    
    # Higher-TF returns (on their native TF, but forward-filled to M12)
    for tf in ["H1", "H4", "H6", "D1"]:
        close_col = f"{tf}_close"
        if close_col not in df.columns:
            continue
        out[f"{tf}_ret_1"] = df[close_col].pct_change()
        out[f"{tf}_ret_5"] = df[close_col].pct_change(5)
        
        # Higher-TF trend
        ema_20 = df[close_col].ewm(span=20, adjust=False).mean()
        ema_50 = df[close_col].ewm(span=50, adjust=False).mean()
        out[f"{tf}_trend_20_50"] = (ema_20 - ema_50) / df[close_col]
    
    # Multi-TF alignment signals
    # Price vs higher-TF EMAs
    for tf in ["H1", "H4", "H6", "D1"]:
        ema_col = f"{tf}_ema_20"
        if ema_col not in df.columns:
            df[ema_col] = df[f"{tf}_close"].ewm(span=20, adjust=False).mean()
        out[f"price_vs_{tf.lower()}_ema20"] = (df["M12_close"] - df[ema_col]) / df["M12_close"]
    
    # Confluence: same direction across TFs
    trend_cols = [c for c in df.columns if c.endswith("_trend_20_50")]
    if trend_cols:
        out["tf_confluence"] = df[trend_cols].apply(lambda row: np.sign(row).sum(), axis=1)
    
    return out

# ============ MAIN PIPELINE ============
def main():
    print("=" * 60)
    print("Multi-TF Alignment Pipeline")
    print(f"Symbol: {SYMBOL}")
    print(f"Source: {DATA_DIR}")
    print(f"Output: {OUT_DIR}")
    print("=" * 60)
    
    # 1. Load all timeframes
    print("\n[1/5] Loading timeframes...")
    dfs = {}
    for tf in TIMEFRAMES:
        dfs[tf] = load_tf(tf)
        print(f"  {tf}: {len(dfs[tf]):,} bars ({dfs[tf].index.min()} → {dfs[tf].index.max()})")
    
    # 2. Resample higher TFs to M12 grid
    print("\n[2/5] Resampling to M12 grid...")
    m12_base = dfs["M12"][["open", "high", "low", "close", "volume", "spread", "real_volume"]].copy()
    m12_base.columns = [f"M12_{c}" for c in m12_base.columns]
    
    aligned = [m12_base]
    for tf in ["H1", "H4", "H6", "D1"]:
        print(f"  Resampling {tf}...")
        tf_aligned = resample_to_m12(dfs[tf], tf)
        aligned.append(tf_aligned)
    
    # 3. Combine all
    print("\n[3/5] Combining...")
    combined = pd.concat(aligned, axis=1)
    combined = combined.loc[m12_base.index]  # ensure exact M12 index
    print(f"  Combined shape: {combined.shape}")
    
    # 4. Compute features
    print("\n[4/5] Computing features...")
    feat_m12 = compute_m12_features(combined)
    feat_session = add_session_features(combined)
    feat_htf = add_higher_tf_features(combined)
    
    # 5. Final dataset
    print("\n[5/5] Assembling final dataset...")
    final = pd.concat([combined, feat_m12, feat_session, feat_htf], axis=1)
    
    # Drop initial NaN rows (warmup period)
    warmup = 200  # enough for all rolling windows
    final = final.iloc[warmup:]
    
    # Save
    out_file = OUT_DIR / f"{SYMBOL}_M12_aligned.parquet"
    final.to_parquet(out_file, compression="zstd")
    size_mb = out_file.stat().st_size / (1024 * 1024)
    
    print(f"\n✓ Done! Saved: {out_file}")
    print(f"  Rows: {len(final):,}")
    print(f"  Columns: {len(final.columns)}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"  Date range: {final.index.min()} → {final.index.max()}")
    print(f"\nColumn groups:")
    raw_cols = [c for c in final.columns if c.startswith(('M12_', 'H1_', 'H4_', 'H6_', 'D1_')) and not any(x in c for x in ['ret', 'trend', 'ema', 'confluence'])]
    m12_feat_cols = [c for c in final.columns if c.startswith(('ret_', 'log_', 'vol_', 'range', 'body', 'wick', 'spread', 'ema_', 'trend_', 'rsi'))]
    sess_cols = [c for c in final.columns if c.startswith(('hour', 'tod', 'is_', 'london_', 'ny_'))]
    htf_cols = [c for c in final.columns if any(c.startswith(f'{tf}_') for tf in ['H1', 'H4', 'H6', 'D1']) and ('ret' in c or 'trend' in c or 'price_vs' in c or 'confluence' in c)]
    print(f"  Raw OHLCV: {raw_cols}")
    print(f"  M12 features: {m12_feat_cols}")
    print(f"  Session: {sess_cols}")
    print(f"  Higher-TF: {htf_cols}")
    
    return final

if __name__ == "__main__":
    df = main()