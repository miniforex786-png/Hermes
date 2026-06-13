#!/usr/bin/env python3
"""
Behaviour Analysis — Module 5

Analyzes your trading behaviour from tagged campaign data:
- Hold time distributions
- Sizing patterns
- Revenge trade detection
- Session bias
- Win/loss streaks
- P&L skew (avg win vs avg loss)
- Campaign-level autopsy
- Probe vs Discretionary comparison
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
import warnings
warnings.filterwarnings("ignore")

# ============ CONFIG ============
INPUT_FILE = Path(r"C:\Hermes\behaviour_analysis\trades_raw.csv")
OUT_DIR = Path(r"C:\Hermes\behaviour_analysis\outputs")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ============ LOAD ============
def load_data():
    df = pd.read_csv(INPUT_FILE)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
    # Filter untagged
    df = df[df["campaign_id"] != "UNTAGGED"].copy()
    return df

# ============ ANALYSIS FUNCTIONS ============
def analyze_hold_times(df):
    """Hold time distributions by campaign type and outcome."""
    results = {}
    
    for camp_type in ["probe", "discretionary"]:
        camp_df = df[df["campaign_type"] == camp_type]
        if len(camp_df) == 0:
            continue
        
        results[camp_type] = {
            "overall": {
                "mean_hours": camp_df["hold_time_hours"].mean(),
                "median_hours": camp_df["hold_time_hours"].median(),
                "std_hours": camp_df["hold_time_hours"].std(),
                "p25": camp_df["hold_time_hours"].quantile(0.25),
                "p75": camp_df["hold_time_hours"].quantile(0.75),
                "max_hours": camp_df["hold_time_hours"].max(),
            },
            "wins": {
                "mean_hours": camp_df[camp_df["pnl_usd"] > 0]["hold_time_hours"].mean(),
                "median_hours": camp_df[camp_df["pnl_usd"] > 0]["hold_time_hours"].median(),
            },
            "losses": {
                "mean_hours": camp_df[camp_df["pnl_usd"] < 0]["hold_time_hours"].mean(),
                "median_hours": camp_df[camp_df["pnl_usd"] < 0]["hold_time_hours"].median(),
            }
        }
    
    return results


def analyze_sizing(df):
    """Position sizing consistency."""
    results = {}
    
    for camp_type in ["probe", "discretionary"]:
        camp_df = df[df["campaign_type"] == camp_type]
        if len(camp_df) == 0:
            continue
        
        sizes = camp_df["size_usd"]
        results[camp_type] = {
            "mean_size": sizes.mean(),
            "median_size": sizes.median(),
            "std_size": sizes.std(),
            "cv": sizes.std() / sizes.mean() if sizes.mean() > 0 else 0,  # coefficient of variation
            "min_size": sizes.min(),
            "max_size": sizes.max(),
            "size_by_outcome": {
                "wins": camp_df[camp_df["pnl_usd"] > 0]["size_usd"].mean(),
                "losses": camp_df[camp_df["pnl_usd"] < 0]["size_usd"].mean(),
            }
        }
    
    return results


def analyze_revenge_trades(df, cooldown_minutes=30):
    """Detect revenge trades: re-entry within cooldown after a loss."""
    df = df.sort_values("entry_time").copy()
    results = {}
    
    for camp_type in ["probe", "discretionary"]:
        camp_df = df[df["campaign_type"] == camp_type].copy()
        if len(camp_df) < 2:
            continue
        
        revenge_flags = []
        for i in range(1, len(camp_df)):
            prev_exit = camp_df.iloc[i-1]["exit_time"]
            curr_entry = camp_df.iloc[i]["entry_time"]
            prev_pnl = camp_df.iloc[i-1]["pnl_usd"]
            
            minutes_since = (curr_entry - prev_exit).total_seconds() / 60
            is_revenge = (minutes_since < cooldown_minutes) and (prev_pnl < 0)
            revenge_flags.append(is_revenge)
        
        camp_df = camp_df.iloc[1:].copy()
        camp_df["is_revenge"] = revenge_flags
        
        revenge_trades = camp_df[camp_df["is_revenge"]]
        normal_trades = camp_df[~camp_df["is_revenge"]]
        
        results[camp_type] = {
            "total_trades": len(camp_df),
            "revenge_count": int(revenge_flags.count(True)),
            "revenge_rate": revenge_flags.count(True) / len(revenge_flags),
            "revenge_pnl": revenge_trades["pnl_usd"].sum() if len(revenge_trades) > 0 else 0,
            "revenge_win_rate": (revenge_trades["pnl_usd"] > 0).mean() if len(revenge_trades) > 0 else 0,
            "normal_win_rate": (normal_trades["pnl_usd"] > 0).mean() if len(normal_trades) > 0 else 0,
        }
    
    return results


def analyze_session_bias(df):
    """When you trade vs when you win."""
    results = {}
    
    for camp_type in ["probe", "discretionary"]:
        camp_df = df[df["campaign_type"] == camp_type]
        if len(camp_df) == 0:
            continue
        
        session_stats = camp_df.groupby("session_entry").agg(
            trades=("pnl_usd", "count"),
            net_pnl=("pnl_usd", "sum"),
            win_rate=("pnl_usd", lambda x: (x > 0).mean()),
            avg_pnl=("pnl_usd", "mean")
        ).to_dict("index")
        
        results[camp_type] = session_stats
    
    return results


def analyze_streaks(df):
    """Win/loss streaks."""
    results = {}
    
    for camp_type in ["probe", "discretionary"]:
        camp_df = df[df["campaign_type"] == camp_type].sort_values("entry_time")
        if len(camp_df) == 0:
            continue
        
        outcomes = (camp_df["pnl_usd"] > 0).astype(int)
        streaks = []
        current_streak = 1
        current_type = outcomes.iloc[0]
        
        for val in outcomes.iloc[1:]:
            if val == current_type:
                current_streak += 1
            else:
                streaks.append({"type": "win" if current_type == 1 else "loss", "length": current_streak})
                current_streak = 1
                current_type = val
        streaks.append({"type": "win" if current_type == 1 else "loss", "length": current_streak})
        
        streak_df = pd.DataFrame(streaks)
        
        results[camp_type] = {
            "max_win_streak": streak_df[streak_df["type"] == "win"]["length"].max() if len(streak_df[streak_df["type"] == "win"]) > 0 else 0,
            "max_loss_streak": streak_df[streak_df["type"] == "loss"]["length"].max() if len(streak_df[streak_df["type"] == "loss"]) > 0 else 0,
            "avg_win_streak": streak_df[streak_df["type"] == "win"]["length"].mean() if len(streak_df[streak_df["type"] == "win"]) > 0 else 0,
            "avg_loss_streak": streak_df[streak_df["type"] == "loss"]["length"].mean() if len(streak_df[streak_df["type"] == "loss"]) > 0 else 0,
            "current_streak": streak_df.iloc[-1]["length"],
            "current_streak_type": streak_df.iloc[-1]["type"],
        }
    
    return results


def analyze_pnl_skew(df):
    """P&L distribution: avg win vs avg loss, expectancy."""
    results = {}
    
    for camp_type in ["probe", "discretionary"]:
        camp_df = df[df["campaign_type"] == camp_type]
        if len(camp_df) == 0:
            continue
        
        wins = camp_df[camp_df["pnl_usd"] > 0]["pnl_usd"]
        losses = camp_df[camp_df["pnl_usd"] < 0]["pnl_usd"]
        
        win_rate = len(wins) / len(camp_df)
        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = losses.mean() if len(losses) > 0 else 0
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
        profit_factor = abs(wins.sum() / losses.sum()) if losses.sum() != 0 else np.inf
        
        results[camp_type] = {
            "n_trades": len(camp_df),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "avg_win_avg_loss_ratio": abs(avg_win / avg_loss) if avg_loss != 0 else np.inf,
            "expectancy_per_trade": expectancy,
            "profit_factor": profit_factor,
            "total_pnl": camp_df["pnl_usd"].sum(),
            "largest_win": wins.max() if len(wins) > 0 else 0,
            "largest_loss": losses.min() if len(losses) > 0 else 0,
        }
    
    return results


def analyze_campaigns(df):
    """Campaign-level autopsy."""
    campaigns = df.groupby("campaign_id").agg(
        type=("campaign_type", "first"),
        n_trades=("trade_id", "count"),
        net_pnl=("pnl_usd", "sum"),
        win_rate=("pnl_usd", lambda x: (x > 0).mean()),
        start_time=("entry_time", "min"),
        end_time=("exit_time", "max"),
        max_drawdown=("pnl_usd", lambda x: (x.cumsum().cummax() - x.cumsum()).max()),
        avg_hold_hours=("hold_time_hours", "mean"),
        unique_setups=("setup_tag", "nunique"),
    ).reset_index()
    
    # Duration in hours
    campaigns["duration_hours"] = (campaigns["end_time"] - campaigns["start_time"]).dt.total_seconds() / 3600
    
    return campaigns


# ============ MAIN ============
def main():
    print("=" * 60)
    print("Behaviour Analysis — Module 5")
    print("=" * 60)
    
    df = load_data()
    print(f"\nLoaded {len(df)} trades")
    print(f"Date range: {df['entry_time'].min()} to {df['entry_time'].max()}")
    print(f"Campaigns: {df['campaign_id'].nunique()}")
    
    # Run all analyses
    print("\n[1/6] Hold times...")
    hold_times = analyze_hold_times(df)
    
    print("[2/6] Sizing...")
    sizing = analyze_sizing(df)
    
    print("[3/6] Revenge trades...")
    revenge = analyze_revenge_trades(df)
    
    print("[4/6] Session bias...")
    session = analyze_session_bias(df)
    
    print("[5/6] Streaks...")
    streaks = analyze_streaks(df)
    
    print("[6/6] P&L skew & Campaigns...")
    pnl_skew = analyze_pnl_skew(df)
    campaigns = analyze_campaigns(df)
    
    # Save outputs
    print("\nSaving results...")
    
    # Save campaigns
    campaigns.to_csv(OUT_DIR / "campaign_autopsy.csv", index=False)
    
    # Save summary JSON
    summary = {
        "hold_times": hold_times,
        "sizing": sizing,
        "revenge_trades": revenge,
        "session_bias": session,
        "streaks": streaks,
        "pnl_skew": pnl_skew,
        "campaigns": campaigns.to_dict("records"),
        "generated_at": pd.Timestamp.now().isoformat(),
    }
    
    with open(OUT_DIR / "behaviour_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    
    # Print key findings
    print("\n" + "=" * 60)
    print("KEY FINDINGS")
    print("=" * 60)
    
    print("\n--- P&L Skew ---")
    for ct in ["probe", "discretionary"]:
        if ct in pnl_skew:
            s = pnl_skew[ct]
            print(f"  {ct.upper()}: WR={s['win_rate']:.1%}, Avg Win=${s['avg_win']:.0f}, Avg Loss=${s['avg_loss']:.0f}, Ratio={s['avg_win_avg_loss_ratio']:.2f}, Expectancy=${s['expectancy_per_trade']:.0f}, PF={s['profit_factor']:.2f}")
    
    print("\n--- Revenge Trades ---")
    for ct in ["probe", "discretionary"]:
        if ct in revenge:
            r = revenge[ct]
            print(f"  {ct.upper()}: {r['revenge_count']}/{r['total_trades']} ({r['revenge_rate']:.1%}) revenge, Revenge WR={r['revenge_win_rate']:.1%} vs Normal WR={r['normal_win_rate']:.1%}")
    
    print("\n--- Sizing (CV = std/mean) ---")
    for ct in ["probe", "discretionary"]:
        if ct in sizing:
            s = sizing[ct]
            print(f"  {ct.upper()}: Mean=${s['mean_size']:.0f}, CV={s['cv']:.2f}, WinSize=${s['size_by_outcome']['wins']:.0f}, LossSize=${s['size_by_outcome']['losses']:.0f}")
    
    print("\n--- Session Bias ---")
    for ct in ["probe", "discretionary"]:
        if ct in session:
            print(f"  {ct.upper()}:")
            for sess, stats in session[ct].items():
                print(f"    {sess:8s}: {stats['trades']} trades, WR={stats['win_rate']:.1%}, Net=${stats['net_pnl']:.0f}")
    
    print("\n--- Streaks ---")
    for ct in ["probe", "discretionary"]:
        if ct in streaks:
            s = streaks[ct]
            print(f"  {ct.upper()}: MaxWinStreak={s['max_win_streak']}, MaxLossStreak={s['max_loss_streak']}, Current={s['current_streak']} {s['current_streak_type']}")
    
    print("\n--- Campaign Autopsy ---")
    print(campaigns[["campaign_id", "type", "n_trades", "net_pnl", "win_rate", "duration_hours", "max_drawdown"]].to_string(index=False))
    
    print(f"\n✓ Results saved to {OUT_DIR}")
    return summary


if __name__ == "__main__":
    main()