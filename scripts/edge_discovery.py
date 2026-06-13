#!/usr/bin/env python3
"""
Setup Labeling + Expectancy Engine — Module 2 → 3

Loads aligned M12 data, defines setups on higher TFs,
labels each M12 bar, measures forward returns, computes expectancy.
Outputs setup performance tables for Opportunity Window Discovery.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# ============ CONFIG ============
ALIGNED_FILE = Path(r"C:\Hermes\aligned_data\XAUUSD_M12_aligned.parquet")
OUT_DIR = Path(r"C:\Hermes\edge_discovery")
OUT_DIR.mkdir(exist_ok=True)

SYMBOL = "XAUUSD"

# Forward return horizons (in M12 bars)
HORIZONS = {
    "M12_2": 2,      # next 2 M12 bars (~24 min)
    "M12_5": 5,      # next 5 M12 bars (~1 hour)
    "M12_10": 10,    # next 10 M12 bars (~2 hours)
    "H1_1": 5,       # next 1 H1 bar (~5 M12 bars)
    "H1_3": 15,      # next 3 H1 bars
}

# ============ SETUP DEFINITIONS ============
def label_setups(df):
    """
    Label each M12 bar with setup occurrences.
    All lookbacks use forward-filled higher-TF data (no look-ahead).
    """
    labels = pd.DataFrame(index=df.index)
    
    # --- D1 Setups ---
    # D1 Bullish Engulfing: prev D1 bearish, curr D1 bullish, body engulfs prev body
    d1_open = df["D1_open"]
    d1_close = df["D1_close"]
    d1_prev_open = d1_open.shift(1)
    d1_prev_close = d1_close.shift(1)
    
    d1_bull_engulf = (
        (d1_prev_close < d1_prev_open) &                    # prev bearish
        (d1_close > d1_open) &                               # curr bullish
        (d1_open <= d1_prev_close) &                         # open <= prev close
        (d1_close >= d1_prev_open)                           # close >= prev open
    )
    labels["setup_d1_bull_engulf"] = d1_bull_engulf.astype(int)
    
    # D1 Bearish Engulfing
    d1_bear_engulf = (
        (d1_prev_close > d1_prev_open) &                     # prev bullish
        (d1_close < d1_open) &                               # curr bearish
        (d1_open >= d1_prev_close) &                         # open >= prev close
        (d1_close <= d1_prev_open)                           # close <= prev open
    )
    labels["setup_d1_bear_engulf"] = d1_bear_engulf.astype(int)
    
    # D1 Breakout: close > max high of last 5 D1 bars (resistance break)
    d1_high_5 = df["D1_high"].rolling(5).max().shift(1)
    d1_breakout_up = (d1_close > d1_high_5)
    labels["setup_d1_breakout_up"] = d1_breakout_up.astype(int)
    
    d1_low_5 = df["D1_low"].rolling(5).min().shift(1)
    d1_breakout_down = (d1_close < d1_low_5)
    labels["setup_d1_breakout_down"] = d1_breakout_down.astype(int)
    
    # --- H4 Setups ---
    h4_open = df["H4_open"]
    h4_close = df["H4_close"]
    h4_high = df["H4_high"]
    h4_low = df["H4_low"]
    h4_prev_open = h4_open.shift(1)
    h4_prev_close = h4_close.shift(1)
    
    h4_bull_engulf = (
        (h4_prev_close < h4_prev_open) &
        (h4_close > h4_open) &
        (h4_open <= h4_prev_close) &
        (h4_close >= h4_prev_open)
    )
    labels["setup_h4_bull_engulf"] = h4_bull_engulf.astype(int)
    
    h4_bear_engulf = (
        (h4_prev_close > h4_prev_open) &
        (h4_close < h4_open) &
        (h4_open >= h4_prev_close) &
        (h4_close <= h4_prev_open)
    )
    labels["setup_h4_bear_engulf"] = h4_bear_engulf.astype(int)
    
    # H4 Volatility Compression: ATR(14) < 0.5 * ATR(50)
    h4_atr_14 = (h4_high - h4_low).rolling(14).mean()
    h4_atr_50 = (h4_high - h4_low).rolling(50).mean()
    h4_vol_compress = (h4_atr_14 < 0.5 * h4_atr_50)
    labels["setup_h4_vol_compress"] = h4_vol_compress.astype(int)
    
    # --- H1 Setups ---
    h1_open = df["H1_open"]
    h1_close = df["H1_close"]
    h1_high = df["H1_high"]
    h1_low = df["H1_low"]
    h1_prev_open = h1_open.shift(1)
    h1_prev_close = h1_close.shift(1)
    
    h1_bull_engulf = (
        (h1_prev_close < h1_prev_open) &
        (h1_close > h1_open) &
        (h1_open <= h1_prev_close) &
        (h1_close >= h1_prev_open)
    )
    labels["setup_h1_bull_engulf"] = h1_bull_engulf.astype(int)
    
    h1_bear_engulf = (
        (h1_prev_close > h1_prev_open) &
        (h1_close < h1_open) &
        (h1_open >= h1_prev_close) &
        (h1_close <= h1_prev_open)
    )
    labels["setup_h1_bear_engulf"] = h1_bear_engulf.astype(int)
    
    # H1 Trend Pullback: H1 trend up (ema20 > ema50) + M12 pullback to H1 EMA20
    h1_trend_up = df["H1_trend_20_50"] > 0
    m12_close = df["M12_close"]
    h1_ema20 = df["H1_close"].ewm(span=20, adjust=False).mean()
    m12_pullback_to_h1ema = (m12_close <= h1_ema20 * 1.002) & (m12_close >= h1_ema20 * 0.998)
    labels["setup_h1_trend_pullback_long"] = (h1_trend_up & m12_pullback_to_h1ema).astype(int)
    
    # --- Confluence Setups (multi-TF) ---
    # D1 bullish + H4 bullish + H1 pullback
    d1_trend_up = df["D1_trend_20_50"] > 0
    h4_trend_up = df["H4_trend_20_50"] > 0
    labels["confluence_d1_h4_h1_long"] = (
        d1_trend_up & h4_trend_up & h1_trend_up & m12_pullback_to_h1ema
    ).astype(int)
    
    # D1 bearish + H4 bearish + H1 pullback short
    d1_trend_down = df["D1_trend_20_50"] < 0
    h4_trend_down = df["H4_trend_20_50"] < 0
    h1_trend_down = df["H1_trend_20_50"] < 0
    m12_pullback_to_h1ema_short = (m12_close >= h1_ema20 * 0.998) & (m12_close <= h1_ema20 * 1.002)
    labels["confluence_d1_h4_h1_short"] = (
        d1_trend_down & h4_trend_down & h1_trend_down & m12_pullback_to_h1ema_short
    ).astype(int)
    
    return labels


def compute_forward_returns(df, horizons):
    """Compute forward log returns for each horizon."""
    m12_close = df["M12_close"]
    fwd = pd.DataFrame(index=df.index)
    
    for name, bars in horizons.items():
        fwd[f"fwd_ret_{name}"] = np.log(m12_close.shift(-bars) / m12_close)
    
    return fwd


def compute_expectancy(labels, fwd_returns, min_trades=30):
    """
    Compute expectancy per setup × horizon.
    Returns DataFrame with: setup, horizon, n, win_rate, avg_win, avg_loss, expectancy, profit_factor, sharpe
    """
    results = []
    
    setup_cols = [c for c in labels.columns if c.startswith("setup_") or c.startswith("confluence_")]
    
    for setup in setup_cols:
        setup_mask = labels[setup] == 1
        n_setups = setup_mask.sum()
        
        if n_setups < min_trades:
            continue
        
        for horizon in fwd_returns.columns:
            rets = fwd_returns.loc[setup_mask, horizon].dropna()
            
            if len(rets) < min_trades:
                continue
            
            wins = rets[rets > 0]
            losses = rets[rets < 0]
            
            win_rate = len(wins) / len(rets)
            avg_win = wins.mean() if len(wins) > 0 else 0
            avg_loss = losses.mean() if len(losses) > 0 else 0
            
            # Expectancy per trade (in log-return space)
            expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
            
            # Profit factor
            gross_profit = wins.sum() if len(wins) > 0 else 0
            gross_loss = abs(losses.sum()) if len(losses) > 0 else 1
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
            
            # Sharpe (annualized-ish: M12 bars per year ~ 43800)
            sharpe = rets.mean() / rets.std() * np.sqrt(43800) if rets.std() > 0 else 0
            
            # Max drawdown of equity curve
            equity = (1 + rets).cumprod()
            dd = (equity / equity.cummax() - 1).min()
            
            results.append({
                "setup": setup,
                "horizon": horizon,
                "n": len(rets),
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "expectancy": expectancy,
                "profit_factor": profit_factor,
                "sharpe": sharpe,
                "max_dd": dd,
                "total_return": rets.sum(),
            })
    
    return pd.DataFrame(results)


def analyze_by_session(labels, fwd_returns):
    """Analyze setup performance by trading session."""
    # This will be added when we merge session features
    pass


# ============ MAIN ============
def main():
    print("=" * 60)
    print("Setup Labeling + Expectancy Engine")
    print(f"Source: {ALIGNED_FILE}")
    print(f"Output: {OUT_DIR}")
    print("=" * 60)
    
    # Load aligned data
    print("\n[1/4] Loading aligned data...")
    df = pd.read_parquet(ALIGNED_FILE)
    print(f"  Shape: {df.shape}")
    print(f"  Date range: {df.index.min()} → {df.index.max()}")
    
    # Label setups
    print("\n[2/4] Labeling setups...")
    labels = label_setups(df)
    setup_cols = [c for c in labels.columns if c.startswith("setup_") or c.startswith("confluence_")]
    print(f"  Defined {len(setup_cols)} setups:")
    for s in setup_cols:
        count = int(labels[s].sum())
        print(f"    {s}: {count:,} occurrences")
    
    # Compute forward returns
    print("\n[3/4] Computing forward returns...")
    fwd = compute_forward_returns(df, HORIZONS)
    print(f"  Horizons: {list(HORIZONS.keys())}")
    
    # Compute expectancy
    print("\n[4/4] Computing expectancy...")
    expectancy_df = compute_expectancy(labels, fwd, min_trades=20)
    
    # Save results
    labels_file = OUT_DIR / f"{SYMBOL}_setup_labels.parquet"
    labels.to_parquet(labels_file, compression="zstd")
    
    fwd_file = OUT_DIR / f"{SYMBOL}_forward_returns.parquet"
    fwd.to_parquet(fwd_file, compression="zstd")
    
    expectancy_file = OUT_DIR / f"{SYMBOL}_expectancy.csv"
    expectancy_df.to_csv(expectancy_file, index=False)
    
    # Print top setups
    print(f"\n✓ Results saved to {OUT_DIR}")
    print(f"\nTop 10 setups by expectancy (all horizons):")
    top = expectancy_df.nlargest(10, "expectancy")[["setup", "horizon", "n", "win_rate", "expectancy", "profit_factor", "sharpe"]]
    pd.set_option("display.float_format", "{:.6f}".format)
    print(top.to_string(index=False))
    
    print(f"\nTop 10 by profit factor:")
    top_pf = expectancy_df.nlargest(10, "profit_factor")[["setup", "horizon", "n", "win_rate", "expectancy", "profit_factor", "sharpe"]]
    print(top_pf.to_string(index=False))
    
    # Save detailed breakdown per setup
    for setup in setup_cols:
        setup_df = expectancy_df[expectancy_df["setup"] == setup].sort_values("horizon")
        if len(setup_df) > 0:
            print(f"\n--- {setup} ---")
            print(setup_df[["horizon", "n", "win_rate", "expectancy", "profit_factor", "sharpe"]].to_string(index=False))
    
    return expectancy_df, labels, fwd


if __name__ == "__main__":
    expectancy_df, labels, fwd = main()