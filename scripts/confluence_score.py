#!/usr/bin/env python3
"""
Confluence Score (Pre-Entry) — Module 4

Real-time scoring combining:
- Active setup signals (weighted by historical expectancy)
- Session/context multipliers (from Module 3)
- Temporal decay (bars since signal)
- Higher-TF trend alignment
- Volatility regime

Output: 0-100 score per M12 bar with tiered interpretation.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ============ CONFIG ============
ALIGNED_FILE = Path(r"C:\Hermes\aligned_data\XAUUSD_M12_aligned.parquet")
LABELS_FILE = Path(r"C:\Hermes\edge_discovery\XAUUSD_setup_labels.parquet")
OPP_DIR = Path(r"C:\Hermes\opportunity_windows")
OUT_DIR = Path(r"C:\Hermes\confluence_score")
OUT_DIR.mkdir(exist_ok=True)

SYMBOL = "XAUUSD"

# Base weights from expectancy analysis (log expectancy * frequency)
# These will be calibrated from Module 3 results
SETUP_BASE_WEIGHTS = {
    "setup_h4_bull_engulf":      1.00,  # 30bps * 349 = highest impact
    "setup_h1_bull_engulf":      0.85,  # 15bps * 1414
    "setup_d1_breakout_up":      0.70,  # 17bps * 249
    "confluence_d1_h4_h1_long":  0.90,  # 10bps * 29750 = high frequency
    "setup_h4_vol_compress":     0.30,  # 2bps * 6696
    "setup_h1_trend_pullback_long": 0.25, # 3bps * 45522
    # Bearish setups (negative weight)
    "setup_h4_bear_engulf":     -0.80,
    "setup_h1_bear_engulf":     -0.75,
    "setup_d1_bear_engulf":     -0.40,
    "setup_d1_breakout_down":   -0.50,
    "confluence_d1_h4_h1_short": -0.60,
}

# Session multipliers (from Module 3, H1_3 horizon)
SESSION_MULTIPLIERS = {
    "setup_h4_bull_engulf":      {"asian": 0.70, "london": 0.85, "ny": 1.25, "overlap": 1.10},
    "setup_h1_bull_engulf":      {"asian": 0.80, "london": 0.90, "ny": 1.15, "overlap": 1.05},
    "setup_d1_breakout_up":      {"asian": 1.20, "london": 1.00, "ny": 0.85, "overlap": 1.00},
    "confluence_d1_h4_h1_long":  {"asian": 0.90, "london": 1.00, "ny": 1.05, "overlap": 1.15},
    "setup_h4_vol_compress":     {"asian": 0.80, "london": 0.90, "ny": 1.00, "overlap": 1.20},
    "setup_h1_trend_pullback_long": {"asian": 0.85, "london": 0.95, "ny": 1.10, "overlap": 1.05},
    # Bearish defaults
    "default_bearish":           {"asian": 0.90, "london": 1.00, "ny": 1.10, "overlap": 1.00},
}

# Context multipliers (D1 trend up = amplifier)
CONTEXT_MULTIPLIERS = {
    "d1_strong_up":     1.25,
    "d1_strong_down":   0.60,
    "d1_neutral":       1.00,
    "h4_up":            1.10,
    "h4_down":          0.85,
    "h1_up":            1.05,
    "h1_down":          0.90,
    "vol_low":          1.10,
    "vol_high":         1.00,
    "vol_normal":       1.00,
}

# Temporal decay curves (from Module 3 temporal_decay.csv)
# Peak expectancy at N bars forward, then decay
TEMPORAL_PEAK = {
    "setup_h4_bull_engulf":      19,
    "setup_h1_bull_engulf":      11,
    "setup_d1_breakout_up":      20,
    "confluence_d1_h4_h1_long":  20,
    "setup_h4_vol_compress":     20,
    "setup_h1_trend_pullback_long": 20,
    "default":                   10,
}

# ============ HELPERS ============
def temporal_weight(setup, bars_since_signal):
    """Weight based on bars since setup triggered (0 = just triggered)."""
    peak = TEMPORAL_PEAK.get(setup, TEMPORAL_PEAK["default"])
    
    if bars_since_signal < 0:
        return 0.0  # signal hasn't happened yet
    if bars_since_signal == 0:
        return 0.8  # just triggered, not full confidence yet
    if bars_since_signal <= peak:
        # Ramp up to peak
        return 0.8 + 0.2 * (bars_since_signal / peak)
    if bars_since_signal <= peak * 2:
        # Gradual decay after peak
        progress = (bars_since_signal - peak) / peak
        return 1.0 - 0.4 * progress
    # Long decay tail
    return 0.3 * np.exp(-(bars_since_signal - peak * 2) / 10)


def get_session_multiplier(setup, session):
    """Get session multiplier for a setup."""
    if setup in SESSION_MULTIPLIERS:
        return SESSION_MULTIPLIERS[setup].get(session, 1.0)
    if "bear" in setup or "short" in setup:
        return SESSION_MULTIPLIERS["default_bearish"].get(session, 1.0)
    return 1.0


def get_context_multipliers(df_row):
    """Compute combined context multiplier from row features."""
    mult = 1.0
    
    # D1 trend
    d1_trend = df_row.get("D1_trend_20_50", 0)
    if d1_trend > df_row.get("D1_trend_20_50_75pct", 0.02):  # placeholder
        mult *= CONTEXT_MULTIPLIERS["d1_strong_up"]
    elif d1_trend < -0.02:
        mult *= CONTEXT_MULTIPLIERS["d1_strong_down"]
    else:
        mult *= CONTEXT_MULTIPLIERS["d1_neutral"]
    
    # H4 trend
    h4_trend = df_row.get("H4_trend_20_50", 0)
    mult *= CONTEXT_MULTIPLIERS["h4_up"] if h4_trend > 0 else CONTEXT_MULTIPLIERS["h4_down"]
    
    # H1 trend
    h1_trend = df_row.get("H1_trend_20_50", 0)
    mult *= CONTEXT_MULTIPLIERS["h1_up"] if h1_trend > 0 else CONTEXT_MULTIPLIERS["h1_down"]
    
    # Volatility regime
    vol_20 = df_row.get("vol_20", 0)
    vol_50 = df_row.get("vol_50", 0)
    if vol_20 < vol_50 * 0.7:
        mult *= CONTEXT_MULTIPLIERS["vol_low"]
    elif vol_20 > vol_50 * 1.3:
        mult *= CONTEXT_MULTIPLIERS["vol_high"]
    else:
        mult *= CONTEXT_MULTIPLIERS["vol_normal"]
    
    return mult


def compute_bars_since_signal(labels, setup_col):
    """Compute bars since each setup last triggered."""
    mask = labels[setup_col] == 1
    bars_since = pd.Series(index=labels.index, dtype=float)
    
    last_signal = -999
    for i, idx in enumerate(labels.index):
        if mask.iloc[i]:
            last_signal = i
        bars_since.iloc[i] = i - last_signal if last_signal >= 0 else -1
    
    return bars_since


# ============ MAIN SCORING ============
def compute_confluence_score(df, labels):
    """Compute confluence score for each M12 bar."""
    scores = pd.DataFrame(index=df.index)
    setup_cols = [c for c in labels.columns if c.startswith("setup_") or c.startswith("confluence_")]
    
    # Session for each bar
    session_map = {}
    for sess in ["asian", "london", "ny", "overlap"]:
        session_map[sess] = df[f"is_{sess}"] == 1
    
    # Component scores
    component_scores = pd.DataFrame(index=df.index)
    
    for setup in setup_cols:
        if setup not in SETUP_BASE_WEIGHTS:
            continue
        
        base_weight = SETUP_BASE_WEIGHTS[setup]
        
        # Bars since signal
        bars_since = compute_bars_since_signal(labels, setup)
        temp_weights = bars_since.apply(lambda b: temporal_weight(setup, b))
        
        # Session multiplier (vectorized)
        sess_weights = pd.Series(1.0, index=df.index)
        for sess_name, sess_mask in session_map.items():
            mult = get_session_multiplier(setup, sess_name)
            sess_weights[sess_mask] = mult
        
        # Context multiplier (row-wise, will compute in loop)
        # For now use base session weight
        
        # Active signal contribution
        active = labels[setup] == 1
        contrib = pd.Series(0.0, index=df.index)
        
        for i in range(len(df)):
            if active.iloc[i]:
                # Signal just triggered
                contrib.iloc[i] = base_weight * sess_weights.iloc[i]
            elif bars_since.iloc[i] > 0:
                # Within window
                ctx_mult = get_context_multipliers(df.iloc[i])
                contrib.iloc[i] = base_weight * temp_weights.iloc[i] * sess_weights.iloc[i] * ctx_mult
        
        component_scores[setup] = contrib
    
    # Long score (sum of positive setups)
    long_setups = [s for s, w in SETUP_BASE_WEIGHTS.items() if w > 0]
    short_setups = [s for s, w in SETUP_BASE_WEIGHTS.items() if w < 0]
    
    scores["long_score_raw"] = component_scores[long_setups].sum(axis=1)
    scores["short_score_raw"] = component_scores[short_setups].sum(axis=1)  # negative values
    scores["net_score_raw"] = scores["long_score_raw"] + scores["short_score_raw"]
    
    # Normalize to 0-100
    # Use rolling percentiles for adaptive normalization
    window = 5000  # ~70 days
    scores["long_pctl"] = scores["long_score_raw"].rolling(window, min_periods=100).rank(pct=True) * 100
    scores["short_pctl"] = (-scores["short_score_raw"]).rolling(window, min_periods=100).rank(pct=True) * 100
    scores["net_pctl"] = scores["net_score_raw"].rolling(window, min_periods=100).rank(pct=True) * 100
    
    # Final confluence score (0-100, 50 = neutral)
    scores["confluence_score"] = 50 + (scores["long_pctl"] - scores["short_pctl"]) / 2
    scores["confluence_score"] = scores["confluence_score"].clip(0, 100)
    
    # Tier interpretation
    def tier(score):
        if score >= 75: return "STRONG_LONG"
        if score >= 60: return "MODERATE_LONG"
        if score >= 45: return "NEUTRAL"
        if score >= 30: return "MODERATE_SHORT"
        if score >= 15: return "WEAK_SHORT"
        return "STRONG_SHORT"
    
    scores["tier"] = scores["confluence_score"].apply(tier)
    
    # Active setups list (for explainability)
    def active_setups(row):
        active = []
        for setup in setup_cols:
            if setup in SETUP_BASE_WEIGHTS and labels.loc[row.name, setup] == 1:
                active.append(setup)
        return ";".join(active) if active else ""
    
    scores["active_setups"] = df.apply(active_setups, axis=1)
    
    # Component breakdown for top contributors
    scores["top_long"] = component_scores[long_setups].idxmax(axis=1)
    scores["top_short"] = component_scores[short_setups].idxmin(axis=1)
    
    return scores, component_scores


# ============ MAIN ============
def main():
    print("=" * 60)
    print("Confluence Score — Module 4")
    print(f"Source: {ALIGNED_FILE}")
    print(f"Output: {OUT_DIR}")
    print("=" * 60)
    
    print("\n[1/3] Loading data...")
    df = pd.read_parquet(ALIGNED_FILE)
    labels = pd.read_parquet(LABELS_FILE)
    print(f"  Aligned: {len(df):,} bars")
    print(f"  Labels: {len(labels.columns)} setups")
    
    print("\n[2/3] Computing confluence scores...")
    scores, components = compute_confluence_score(df, labels)
    
    print("\n[3/3] Saving results...")
    scores_file = OUT_DIR / f"{SYMBOL}_confluence_score.parquet"
    scores.to_parquet(scores_file, compression="zstd")
    
    components_file = OUT_DIR / f"{SYMBOL}_score_components.parquet"
    components.to_parquet(components_file, compression="zstd")
    
    # Summary stats
    print(f"\n✓ Saved: {scores_file}")
    print(f"  Date range: {scores.index.min()} → {scores.index.max()}")
    print(f"  Score range: {scores['confluence_score'].min():.1f} - {scores['confluence_score'].max():.1f}")
    print(f"  Mean: {scores['confluence_score'].mean():.1f}")
    
    print("\nTier distribution:")
    print(scores["tier"].value_counts())
    
    # Recent scores
    print("\nLast 20 bars:")
    recent = scores.tail(20)[["confluence_score", "tier", "active_setups", "long_score_raw", "short_score_raw", "net_score_raw"]]
    pd.set_option("display.max_colwidth", 60)
    print(recent.to_string())
    
    # Score vs forward returns (validation)
    print("\n--- Score vs Next 5 M12 Return (In-Sample Check) ---")
    fwd_ret_5 = np.log(df["M12_close"].shift(-5) / df["M12_close"])
    
    for tier_name in ["STRONG_LONG", "MODERATE_LONG", "NEUTRAL", "MODERATE_SHORT", "STRONG_SHORT"]:
        mask = scores["tier"] == tier_name
        if mask.sum() > 0:
            mean_ret = fwd_ret_5[mask].mean() * 10000  # bps
            win_rate = (fwd_ret_5[mask] > 0).mean()
            print(f"  {tier_name:15s}: n={mask.sum():5d}, mean_fwd_5M12={mean_ret:+.1f}bps, WR={win_rate:.1%}")
    
    return scores, components


if __name__ == "__main__":
    scores, components = main()