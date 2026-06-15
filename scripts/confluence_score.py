#!/usr/bin/env python3
"""Module 4: Confluence Score - Real-time scoring for XAUUSD setups."""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_ROOT = Path(r"C:\Hermes")
ALIGNED_DIR = DATA_ROOT / "aligned_data"
OUT_DIR = DATA_ROOT / "confluence_score"
OUT_DIR.mkdir(exist_ok=True)

def calculate_confluence(row) -> dict:
    """Calculate confluence score from aligned multi-TF data."""
    score = 0
    components = {}
    
    # Trend alignment (H4, H6, D1)
    trend_tfs = ["H4", "H6", "D1"]
    trend_scores = []
    for tf in trend_tfs:
        col = f"{tf}_close"
        if col in row:
            sma_20 = row.get(f"{tf}_sma_20", row[col])
            trend_scores.append(1 if row[col] > sma_20 else -1)
    if trend_scores:
        trend_align = np.mean(trend_scores)
        components["trend_alignment"] = (trend_align + 1) / 2  # 0-1
        score += components["trend_alignment"] * 0.3
    
    # Volatility regime (H1 ATR vs H4 ATR)
    h1_atr = row.get("H1_atr", 1)
    h4_atr = row.get("H4_atr", 1)
    if h4_atr > 0:
        vol_ratio = h1_atr / h4_atr
        if 0.5 <= vol_ratio <= 1.5:
            components["volatility_regime"] = 0.8
        elif 0.3 <= vol_ratio <= 2.0:
            components["volatility_regime"] = 0.6
        else:
            components["volatility_regime"] = 0.4
        score += components["volatility_regime"] * 0.25
    
    # Session favorability
    hour = row.name.hour if hasattr(row.name, 'hour') else 12
    if 7 <= hour <= 10:  # London open
        components["session_favorability"] = 0.9
    elif 12 <= hour <= 15:  # NY open
        components["session_favorability"] = 0.95
    elif 15 <= hour <= 17:  # Overlap
        components["session_favorability"] = 1.0
    else:
        components["session_favorability"] = 0.5
    score += components["session_favorability"] * 0.25
    
    # Structure score (placeholder)
    components["structure_score"] = 0.8
    score += components["structure_score"] * 0.2
    
    # Determine tier
    if score >= 0.8:
        tier = "STRONG_LONG"
    elif score >= 0.6:
        tier = "LONG"
    elif score >= 0.4:
        tier = "NEUTRAL"
    elif score >= 0.2:
        tier = "SHORT"
    else:
        tier = "STRONG_SHORT"
    
    return {
        "confluence_score": round(score * 100, 1),
        "tier": tier,
        "confidence": round(score, 2),
        "active_setups": "H1 MOMENTUM;H4 REVERSION" if score > 0.6 else "H4 REVERSION",
        **components
    }

def main():
    print("Calculating confluence scores...")
    
    # Load M12 aligned data as primary
    m12_file = ALIGNED_DIR / "XAUUSD_M12_aligned.parquet"
    if not m12_file.exists():
        print("M12 aligned data not found")
        return 1
    
    df = pd.read_parquet(m12_file)
    
    # Add SMA and ATR if not present
    if "sma_20" not in df.columns:
        df["sma_20"] = df["close"].rolling(20).mean()
    if "atr" not in df.columns:
        df["tr"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                np.abs(df["high"] - df["close"].shift(1)),
                np.abs(df["low"] - df["close"].shift(1))
            )
        )
        df["atr"] = df["tr"].rolling(14).mean()
    
    # Add H4, H6, D1 data if available
    for tf in ["H4", "H6", "D1"]:
        tf_file = ALIGNED_DIR / f"XAUUSD_{tf}_aligned.parquet"
        if tf_file.exists():
            tf_df = pd.read_parquet(tf_file)
            tf_df = tf_df.add_prefix(f"{tf}_")
            df = df.join(tf_df, how="left")
    
    # Calculate confluence for last 100 bars
    results = []
    for idx, row in df.tail(100).iterrows():
        conf = calculate_confluence(row)
        conf["timestamp"] = idx
        results.append(conf)
    
    out_df = pd.DataFrame(results).set_index("timestamp")
    out_file = OUT_DIR / "XAUUSD_confluence_score.parquet"
    out_df.to_parquet(out_file)
    print(f"Saved confluence scores: {len(out_df)} rows -> {out_file}")
    print(f"Latest: {out_df.iloc[-1].to_dict()}")
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())