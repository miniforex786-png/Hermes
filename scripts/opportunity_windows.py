#!/usr/bin/env python3
"""
Opportunity Window Discovery — Module 3

Analyzes WHEN winning setups work best:
- Session dependency (Asian/London/NY/Overlap)
- Day of week
- Higher-TF context strength
- Temporal edge decay (forward return distribution by bar)
- False signal rate
- Conditional expectancy given context
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ============ CONFIG ============
ALIGNED_FILE = Path(r"C:\Hermes\aligned_data\XAUUSD_M12_aligned.parquet")
LABELS_FILE = Path(r"C:\Hermes\edge_discovery\XAUUSD_setup_labels.parquet")
FWD_FILE = Path(r"C:\Hermes\edge_discovery\XAUUSD_forward_returns.parquet")
OUT_DIR = Path(r"C:\Hermes\opportunity_windows")
OUT_DIR.mkdir(exist_ok=True)

SYMBOL = "XAUUSD"

# Winning setups from expectancy analysis
WINNING_SETUPS = [
    "setup_h4_bull_engulf",
    "setup_h1_bull_engulf", 
    "setup_d1_breakout_up",
    "confluence_d1_h4_h1_long",
    "setup_h4_vol_compress",
    "setup_h1_trend_pullback_long",
]

HORIZONS = {
    "M12_2": 2,
    "M12_5": 5,
    "M12_10": 10,
    "H1_1": 5,
    "H1_3": 15,
}

# ============ HELPERS ============
def load_data():
    df = pd.read_parquet(ALIGNED_FILE)
    labels = pd.read_parquet(LABELS_FILE)
    fwd = pd.read_parquet(FWD_FILE)
    return df, labels, fwd


def analyze_session_performance(df, labels, fwd, setup):
    """Analyze setup performance by trading session."""
    setup_mask = labels[setup] == 1
    if setup_mask.sum() < 20:
        return None
    
    results = []
    sessions = {
        "asian": df["is_asian"] == 1,
        "london": df["is_london"] == 1,
        "ny": df["is_ny"] == 1,
        "overlap": df["is_overlap"] == 1,
    }
    
    for session_name, session_mask in sessions.items():
        combined = setup_mask & session_mask
        n = combined.sum()
        if n < 20:
            continue
        
        for horizon_name in HORIZONS:
            col = f"fwd_ret_{horizon_name}"
            if col not in fwd.columns:
                continue
            rets = fwd.loc[combined, col].dropna()
            if len(rets) < 20:
                continue
            
            wins = rets[rets > 0]
            losses = rets[rets < 0]
            win_rate = len(wins) / len(rets)
            avg_win = wins.mean() if len(wins) > 0 else 0
            avg_loss = losses.mean() if len(losses) > 0 else 0
            expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
            pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() < 0 else np.inf
            
            results.append({
                "setup": setup,
                "session": session_name,
                "horizon": horizon_name,
                "n": len(rets),
                "win_rate": win_rate,
                "expectancy": expectancy,
                "profit_factor": pf,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
            })
    
    return pd.DataFrame(results)


def analyze_day_of_week(df, labels, fwd, setup):
    """Analyze setup performance by day of week."""
    setup_mask = labels[setup] == 1
    if setup_mask.sum() < 20:
        return None
    
    results = []
    df["dow"] = df.index.dayofweek  # 0=Mon, 4=Fri
    
    for dow in range(5):  # Mon-Fri
        dow_mask = df["dow"] == dow
        combined = setup_mask & dow_mask
        n = combined.sum()
        if n < 20:
            continue
        
        for horizon_name in HORIZONS:
            col = f"fwd_ret_{horizon_name}"
            if col not in fwd.columns:
                continue
            rets = fwd.loc[combined, col].dropna()
            if len(rets) < 20:
                continue
            
            wins = rets[rets > 0]
            losses = rets[rets < 0]
            win_rate = len(wins) / len(rets)
            avg_win = wins.mean() if len(wins) > 0 else 0
            avg_loss = losses.mean() if len(losses) > 0 else 0
            expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
            pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() < 0 else np.inf
            
            dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
            results.append({
                "setup": setup,
                "day_of_week": dow_names[dow],
                "horizon": horizon_name,
                "n": len(rets),
                "win_rate": win_rate,
                "expectancy": expectancy,
                "profit_factor": pf,
            })
    
    return pd.DataFrame(results)


def analyze_temporal_decay(df, labels, fwd, setup):
    """
    Analyze how edge decays over M12 bars after setup trigger.
    Returns per-bar forward return distribution.
    """
    setup_mask = labels[setup] == 1
    setup_indices = df.index[setup_mask]
    
    if len(setup_indices) < 20:
        return None
    
    m12_close = df["M12_close"]
    max_bars = 20  # analyze up to 20 M12 bars forward (~4 hours)
    
    results = []
    for bar in range(1, max_bars + 1):
        rets = []
        for idx in setup_indices:
            idx_pos = df.index.get_loc(idx)
            if idx_pos + bar < len(df):
                entry_price = m12_close.iloc[idx_pos]
                exit_price = m12_close.iloc[idx_pos + bar]
                ret = np.log(exit_price / entry_price)
                rets.append(ret)
        
        rets = np.array(rets)
        if len(rets) < 20:
            continue
        
        wins = rets[rets > 0]
        losses = rets[rets < 0]
        win_rate = len(wins) / len(rets)
        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = losses.mean() if len(losses) > 0 else 0
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
        median_ret = np.median(rets)
        std_ret = np.std(rets)
        
        results.append({
            "setup": setup,
            "bars_forward": bar,
            "minutes_forward": bar * 12,
            "n": len(rets),
            "win_rate": win_rate,
            "median_ret": median_ret,
            "mean_ret": np.mean(rets),
            "expectancy": expectancy,
            "std_ret": std_ret,
            "sharpe": np.mean(rets) / std_ret * np.sqrt(43800 / bar) if std_ret > 0 else 0,
        })
    
    return pd.DataFrame(results)


def analyze_context_conditioning(df, labels, fwd, setup):
    """Analyze performance conditioned on higher-TF state at setup time."""
    setup_mask = labels[setup] == 1
    if setup_mask.sum() < 50:
        return None
    
    results = []
    
    # D1 trend strength at setup time
    d1_trend = df.loc[setup_mask, "D1_trend_20_50"]
    d1_trend_strong_up = d1_trend > d1_trend.quantile(0.75)
    d1_trend_strong_down = d1_trend < d1_trend.quantile(0.25)
    d1_trend_neutral = (~d1_trend_strong_up) & (~d1_trend_strong_down)
    
    # H4 trend
    h4_trend = df.loc[setup_mask, "H4_trend_20_50"]
    h4_trend_up = h4_trend > 0
    h4_trend_down = h4_trend < 0
    
    # H1 trend
    h1_trend = df.loc[setup_mask, "H1_trend_20_50"]
    h1_trend_up = h1_trend > 0
    h1_trend_down = h1_trend < 0
    
    # Volatility regime
    m12_vol = df.loc[setup_mask, "vol_20"]
    vol_low = m12_vol < m12_vol.quantile(0.33)
    vol_high = m12_vol > m12_vol.quantile(0.66)
    vol_normal = (~vol_low) & (~vol_high)
    
    contexts = {
        "d1_strong_up": d1_trend_strong_up,
        "d1_strong_down": d1_trend_strong_down,
        "d1_neutral": d1_trend_neutral,
        "h4_up": h4_trend_up,
        "h4_down": h4_trend_down,
        "h1_up": h1_trend_up,
        "h1_down": h1_trend_down,
        "vol_low": vol_low,
        "vol_high": vol_high,
        "vol_normal": vol_normal,
    }
    
    for ctx_name, ctx_mask in contexts.items():
        combined = setup_mask & ctx_mask
        n = combined.sum()
        if n < 20:
            continue
        
        for horizon_name in HORIZONS:
            col = f"fwd_ret_{horizon_name}"
            if col not in fwd.columns:
                continue
            rets = fwd.loc[combined, col].dropna()
            if len(rets) < 20:
                continue
            
            wins = rets[rets > 0]
            losses = rets[rets < 0]
            win_rate = len(wins) / len(rets)
            avg_win = wins.mean() if len(wins) > 0 else 0
            avg_loss = losses.mean() if len(losses) > 0 else 0
            expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
            pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and losses.sum() < 0 else np.inf
            
            results.append({
                "setup": setup,
                "context": ctx_name,
                "horizon": horizon_name,
                "n": len(rets),
                "win_rate": win_rate,
                "expectancy": expectancy,
                "profit_factor": pf,
            })
    
    return pd.DataFrame(results)


def analyze_false_signal_rate(df, labels, fwd, setup):
    """
    False signal = setup occurs but price moves against direction within window.
    For long setups: false if max drawdown > threshold before target reached.
    """
    setup_mask = labels[setup] == 1
    setup_indices = df.index[setup_mask]
    
    if len(setup_indices) < 20:
        return None
    
    m12_high = df["M12_high"]
    m12_low = df["M12_low"]
    m12_close = df["M12_close"]
    
    max_lookforward = 20  # M12 bars
    results = []
    
    for idx in setup_indices:
        idx_pos = df.index.get_loc(idx)
        entry = m12_close.iloc[idx_pos]
        
        # Track max adverse excursion (MAE) and max favorable excursion (MFE)
        mae = 0  # max drawdown from entry
        mfe = 0  # max run-up from entry
        
        for bar in range(1, max_lookforward + 1):
            if idx_pos + bar >= len(df):
                break
            high = m12_high.iloc[idx_pos + bar]
            low = m12_low.iloc[idx_pos + bar]
            
            # For long setups
            dd = (entry - low) / entry
            ru = (high - entry) / entry
            
            mae = max(mae, dd)
            mfe = max(mfe, ru)
        
        results.append({
            "setup": setup,
            "mae": mae,
            "mfe": mfe,
            "mfe_mae_ratio": mfe / mae if mae > 0 else np.inf,
        })
    
    return pd.DataFrame(results)


# ============ MAIN ============
def main():
    print("=" * 60)
    print("Opportunity Window Discovery — Module 3")
    print(f"Source: {ALIGNED_FILE}")
    print(f"Output: {OUT_DIR}")
    print("=" * 60)
    
    df, labels, fwd = load_data()
    print(f"\nLoaded: {len(df):,} bars, {len(labels.columns)} setups")
    
    all_session = []
    all_dow = []
    all_decay = []
    all_context = []
    all_mae_mfe = []
    
    for setup in WINNING_SETUPS:
        if setup not in labels.columns:
            print(f"\n⚠ {setup} not found in labels, skipping")
            continue
        
        count = int(labels[setup].sum())
        print(f"\n--- {setup} ({count:,} occurrences) ---")
        
        # Session analysis
        print("  Session analysis...")
        sess = analyze_session_performance(df, labels, fwd, setup)
        if sess is not None:
            all_session.append(sess)
        
        # Day of week
        print("  Day of week...")
        dow = analyze_day_of_week(df, labels, fwd, setup)
        if dow is not None:
            all_dow.append(dow)
        
        # Temporal decay
        print("  Temporal decay...")
        decay = analyze_temporal_decay(df, labels, fwd, setup)
        if decay is not None:
            all_decay.append(decay)
        
        # Context conditioning
        print("  Context conditioning...")
        ctx = analyze_context_conditioning(df, labels, fwd, setup)
        if ctx is not None:
            all_context.append(ctx)
        
        # MAE/MFE
        print("  MAE/MFE analysis...")
        mae_mfe = analyze_false_signal_rate(df, labels, fwd, setup)
        if mae_mfe is not None:
            all_mae_mfe.append(mae_mfe)
    
    # Combine and save
    print("\n" + "=" * 60)
    print("Saving results...")
    
    if all_session:
        session_df = pd.concat(all_session, ignore_index=True)
        session_df.to_csv(OUT_DIR / f"{SYMBOL}_session_analysis.csv", index=False)
        print(f"  Session: {len(session_df)} rows")
    
    if all_dow:
        dow_df = pd.concat(all_dow, ignore_index=True)
        dow_df.to_csv(OUT_DIR / f"{SYMBOL}_dow_analysis.csv", index=False)
        print(f"  Day of week: {len(dow_df)} rows")
    
    if all_decay:
        decay_df = pd.concat(all_decay, ignore_index=True)
        decay_df.to_csv(OUT_DIR / f"{SYMBOL}_temporal_decay.csv", index=False)
        print(f"  Temporal decay: {len(decay_df)} rows")
    
    if all_context:
        ctx_df = pd.concat(all_context, ignore_index=True)
        ctx_df.to_csv(OUT_DIR / f"{SYMBOL}_context_analysis.csv", index=False)
        print(f"  Context: {len(ctx_df)} rows")
    
    if all_mae_mfe:
        mae_df = pd.concat(all_mae_mfe, ignore_index=True)
        mae_df.to_csv(OUT_DIR / f"{SYMBOL}_mae_mfe.csv", index=False)
        print(f"  MAE/MFE: {len(mae_df)} rows")
    
    # Print key insights
    print("\n" + "=" * 60)
    print("KEY INSIGHTS")
    print("=" * 60)
    
    if all_session:
        sess_df = pd.concat(all_session)
        print("\n--- Best Session per Setup (H1_3 horizon) ---")
        for setup in WINNING_SETUPS:
            h13 = sess_df[(sess_df["setup"] == setup) & (sess_df["horizon"] == "H1_3")]
            if len(h13) > 0:
                best = h13.loc[h13["expectancy"].idxmax()]
                print(f"  {setup}: {best['session']:8s} (WR={best['win_rate']:.1%}, Exp={best['expectancy']*10000:.1f}bps, n={best['n']})")
    
    if all_decay:
        decay_df = pd.concat(all_decay)
        print("\n--- Optimal Exit Window (peak expectancy) ---")
        for setup in WINNING_SETUPS:
            sdecay = decay_df[decay_df["setup"] == setup]
            if len(sdecay) > 0:
                peak = sdecay.loc[sdecay["expectancy"].idxmax()]
                print(f"  {setup}: {int(peak['bars_forward'])} bars ({int(peak['minutes_forward'])} min) — Exp={peak['expectancy']*10000:.1f}bps, WR={peak['win_rate']:.1%}")
    
    if all_context:
        ctx_df = pd.concat(all_context)
        print("\n--- Best Context per Setup (H1_3 horizon) ---")
        for setup in WINNING_SETUPS:
            h13 = ctx_df[(ctx_df["setup"] == setup) & (ctx_df["horizon"] == "H1_3")]
            if len(h13) > 0:
                best = h13.loc[h13["expectancy"].idxmax()]
                print(f"  {setup}: {best['context']:15s} (WR={best['win_rate']:.1%}, Exp={best['expectancy']*10000:.1f}bps, n={best['n']})")
    
    if all_mae_mfe:
        mae_df = pd.concat(all_mae_mfe)
        print("\n--- MAE/MFE Summary (20 bars forward) ---")
        for setup in WINNING_SETUPS:
            smae = mae_df[mae_df["setup"] == setup]
            if len(smae) > 0:
                print(f"  {setup}: MAE={smae['mae'].median()*100:.2f}% (med), MFE={smae['mfe'].median()*100:.2f}% (med), Ratio={smae['mfe_mae_ratio'].median():.2f}")
    
    return all_session, all_dow, all_decay, all_context, all_mae_mfe


if __name__ == "__main__":
    main()