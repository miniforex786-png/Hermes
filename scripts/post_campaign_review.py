#!/usr/bin/env python3
"""
Post-Campaign Review — Module 7

Formal structured review using:
- Campaign trade data (Module 5)
- Behaviour patterns (Module 5)
- Coaching engine (Module 6)
- Confluence context (Module 4)
- Risk Guardian state (Module 10)

Outputs: Structured review document (Markdown/JSON) for each campaign.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings("ignore")

# ============ CONFIG ============
TRADES_FILE = Path(r"C:\Hermes\behaviour_analysis\trades_raw.csv")
BEHAVIOUR_FILE = Path(r"C:\Hermes\behaviour_analysis\outputs\behaviour_summary.json")
CONFLUENCE_FILE = Path(r"C:\Hermes\confluence_score\XAUUSD_confluence_score.parquet")
OUT_DIR = Path(r"C:\Hermes\post_campaign_reviews")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ============ DATA CLASSES ============
@dataclass
class CampaignReview:
    """Complete post-campaign review."""
    campaign_id: str
    campaign_type: str
    review_date: str
    
    # Executive Summary
    net_pnl: float
    total_trades: int
    win_rate: float
    expectancy_per_trade: float
    profit_factor: float
    max_drawdown: float
    duration_hours: float
    outcome: str  # "PASS" / "FAIL" / "CONDITIONAL"
    
    # Phase 1: Setup Quality
    setup_quality_score: float  # 0-100
    confluence_alignment: str  # "aligned" / "mixed" / "misaligned"
    setup_breakdown: Dict[str, int]
    
    # Phase 2: Execution Quality
    execution_score: float  # 0-100
    sizing_discipline: str  # "excellent" / "good" / "poor" / "chaotic"
    revenge_trade_count: int
    revenge_trade_pnl: float
    session_adherence: str  # "followed" / "mixed" / "ignored"
    
    # Phase 3: Risk Management
    risk_score: float  # 0-100
    risk_limit_breaches: List[str]
    max_concurrent_layers: int
    runner_management: str  # "good" / "acceptable" / "poor"
    
    # Phase 4: Behaviour Comparison
    vs_personal_baseline: Dict[str, str]  # metric -> "better" / "same" / "worse"
    vs_campaign_type_baseline: Dict[str, str]
    
    # Phase 5: Lessons & Actions
    key_strengths: List[str]
    key_weaknesses: List[str]
    action_items: List[Dict[str, str]]  # {"action": "...", "deadline": "...", "owner": "..."}
    
    # Raw data reference
    trade_ids: List[str] = field(default_factory=list)


# ============ REVIEW ENGINE ============
class PostCampaignReviewEngine:
    """Generates formal post-campaign reviews."""
    
    def __init__(self):
        self.trades_df = None
        self.behaviour = None
        self.confluence_data = None
        self._load_data()
    
    def _load_data(self):
        # Trades
        if TRADES_FILE.exists():
            df = pd.read_csv(TRADES_FILE)
            df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
            df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
            self.trades_df = df[df["campaign_id"] != "UNTAGGED"].copy()
        
        # Behaviour baseline
        if BEHAVIOUR_FILE.exists():
            with open(BEHAVIOUR_FILE) as f:
                self.behaviour = json.load(f)
        
        # Confluence data
        if CONFLUENCE_FILE.exists():
            self.confluence_data = pd.read_parquet(CONFLUENCE_FILE)
    
    def generate_review(self, campaign_id: str) -> CampaignReview:
        """Generate full review for a campaign."""
        camp_trades = self.trades_df[self.trades_df["campaign_id"] == campaign_id].copy()
        if len(camp_trades) == 0:
            raise ValueError(f"No trades found for {campaign_id}")
        
        camp_type = camp_trades["campaign_type"].iloc[0]
        
        # ---- Core Metrics ----
        net_pnl = camp_trades["pnl_usd"].sum()
        total_trades = len(camp_trades)
        win_rate = (camp_trades["pnl_usd"] > 0).mean()
        
        wins = camp_trades[camp_trades["pnl_usd"] > 0]["pnl_usd"]
        losses = camp_trades[camp_trades["pnl_usd"] < 0]["pnl_usd"]
        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = losses.mean() if len(losses) > 0 else 0
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
        profit_factor = abs(wins.sum() / losses.sum()) if losses.sum() != 0 else np.inf
        
        # Max drawdown
        cum_pnl = camp_trades["pnl_usd"].cumsum()
        max_dd = (cum_pnl.cummax() - cum_pnl).max()
        
        # Duration
        duration_hours = (camp_trades["exit_time"].max() - camp_trades["entry_time"].min()).total_seconds() / 3600
        
        # Outcome classification
        if net_pnl > 0 and profit_factor > 1.5 and max_dd < abs(net_pnl) * 2:
            outcome = "PASS"
        elif net_pnl <= 0 or profit_factor < 1.0:
            outcome = "FAIL"
        else:
            outcome = "CONDITIONAL"
        
        # ---- Phase 1: Setup Quality ----
        setup_quality_score, confluence_alignment, setup_breakdown = self._analyze_setup_quality(camp_trades)
        
        # ---- Phase 2: Execution Quality ----
        execution_score, sizing_discipline, revenge_count, revenge_pnl, session_adherence = self._analyze_execution(camp_trades, camp_type)
        
        # ---- Phase 3: Risk Management ----
        risk_score, risk_breaches, max_layers, runner_mgmt = self._analyze_risk(camp_trades)
        
        # ---- Phase 4: Behaviour Comparison ----
        vs_personal, vs_type = self._compare_behaviour(camp_trades, camp_type)
        
        # ---- Phase 5: Lessons & Actions ----
        strengths, weaknesses, actions = self._generate_lessons(
            camp_trades, camp_type, net_pnl, win_rate, expectancy, profit_factor,
            max_dd, duration_hours, revenge_count, revenge_pnl,
            sizing_discipline, session_adherence, risk_breaches
        )
        
        return CampaignReview(
            campaign_id=campaign_id,
            campaign_type=camp_type,
            review_date=datetime.now().isoformat(),
            net_pnl=round(net_pnl, 2),
            total_trades=total_trades,
            win_rate=round(win_rate, 4),
            expectancy_per_trade=round(expectancy, 2),
            profit_factor=round(profit_factor, 2) if profit_factor != np.inf else 999,
            max_drawdown=round(max_dd, 2),
            duration_hours=round(duration_hours, 2),
            outcome=outcome,
            setup_quality_score=setup_quality_score,
            confluence_alignment=confluence_alignment,
            setup_breakdown=setup_breakdown,
            execution_score=execution_score,
            sizing_discipline=sizing_discipline,
            revenge_trade_count=revenge_count,
            revenge_trade_pnl=round(revenge_pnl, 2),
            session_adherence=session_adherence,
            risk_score=risk_score,
            risk_limit_breaches=risk_breaches,
            max_concurrent_layers=max_layers,
            runner_management=runner_mgmt,
            vs_personal_baseline=vs_personal,
            vs_campaign_type_baseline=vs_type,
            key_strengths=strengths,
            key_weaknesses=weaknesses,
            action_items=actions,
            trade_ids=camp_trades["trade_id"].tolist()
        )
    
    def _analyze_setup_quality(self, camp_trades: pd.DataFrame) -> tuple:
        """Analyze setup quality using confluence data."""
        if self.confluence_data is None:
            return 50, "unknown", {}
        
        # Get confluence scores at entry times
        scores = []
        for _, trade in camp_trades.iterrows():
            idx = self.confluence_data.index.get_indexer([trade["entry_time"]], method="nearest")[0]
            if 0 <= idx < len(self.confluence_data):
                scores.append(self.confluence_data.iloc[idx]["confluence_score"])
        
        if not scores:
            return 50, "unknown", {}
        
        avg_score = np.mean(scores)
        
        # Count setups
        setup_counts = camp_trades["setup_tag"].value_counts().to_dict()
        
        # Alignment: were setups aligned with confluence direction?
        aligned = 0
        for _, trade in camp_trades.iterrows():
            idx = self.confluence_data.index.get_indexer([trade["entry_time"]], method="nearest")[0]
            if 0 <= idx < len(self.confluence_data):
                tier = self.confluence_data.iloc[idx]["tier"]
                direction = trade["direction"]
                if (direction == "long" and "LONG" in tier) or (direction == "short" and "SHORT" in tier):
                    aligned += 1
        
        alignment_pct = aligned / len(camp_trades) if len(camp_trades) > 0 else 0
        if alignment_pct > 0.7:
            confluence_alignment = "aligned"
        elif alignment_pct > 0.4:
            confluence_alignment = "mixed"
        else:
            confluence_alignment = "misaligned"
        
        # Score = avg confluence * alignment
        setup_quality_score = min(100, avg_score * alignment_pct)
        
        return round(setup_quality_score, 1), confluence_alignment, setup_counts
    
    def _analyze_execution(self, camp_trades: pd.DataFrame, camp_type: str) -> tuple:
        """Analyze execution quality."""
        # Sizing discipline (CV)
        sizes = camp_trades["size_usd"]
        cv = sizes.std() / sizes.mean() if sizes.mean() > 0 else 0
        
        if cv < 0.3:
            sizing_discipline = "excellent"
        elif cv < 0.6:
            sizing_discipline = "good"
        elif cv < 1.0:
            sizing_discipline = "poor"
        else:
            sizing_discipline = "chaotic"
        
        # Revenge trades (entry within 30min after loss)
        camp_trades = camp_trades.sort_values("entry_time").copy()
        revenge_flags = []
        for i in range(1, len(camp_trades)):
            prev_exit = camp_trades.iloc[i-1]["exit_time"]
            curr_entry = camp_trades.iloc[i]["entry_time"]
            prev_pnl = camp_trades.iloc[i-1]["pnl_usd"]
            minutes_since = (curr_entry - prev_exit).total_seconds() / 60
            is_revenge = (minutes_since < 30) and (prev_pnl < 0)
            revenge_flags.append(is_revenge)
        
        camp_trades = camp_trades.iloc[1:].copy()
        camp_trades["is_revenge"] = revenge_flags
        revenge_trades = camp_trades[camp_trades["is_revenge"]]
        revenge_count = len(revenge_trades)
        revenge_pnl = revenge_trades["pnl_usd"].sum()
        
        # Session adherence
        session_pnl = camp_trades.groupby("session_entry")["pnl_usd"].sum()
        best_session = session_pnl.idxmax() if len(session_pnl) > 0 else "none"
        worst_session = session_pnl.idxmin() if len(session_pnl) > 0 else "none"
        worst_pnl = session_pnl.min() if len(session_pnl) > 0 else 0
        
        if worst_pnl < -abs(camp_trades["pnl_usd"].sum()) * 0.5:
            session_adherence = "ignored"
        elif len(session_pnl) == 1:
            session_adherence = "focused"
        else:
            session_adherence = "followed"
        
        # Execution score components
        sizing_score = max(0, 100 - cv * 100) if cv < 1 else 0
        revenge_score = max(0, 100 - (revenge_count / len(camp_trades)) * 300) if len(camp_trades) > 0 else 100
        session_score = 100 if session_adherence == "followed" else (70 if session_adherence == "mixed" else 30)
        
        execution_score = round((sizing_score + revenge_score + session_score) / 3, 1)
        
        return execution_score, sizing_discipline, revenge_count, round(revenge_pnl, 2), session_adherence
    
    def _analyze_risk(self, camp_trades: pd.DataFrame) -> tuple:
        """Analyze risk management."""
        breaches = []
        
        # Max concurrent layers (approximate from overlapping trades)
        max_layers = 1
        # Simplified: count trades per day
        daily_counts = camp_trades.groupby(camp_trades["entry_time"].dt.date).size()
        max_layers = int(daily_counts.max()) if len(daily_counts) > 0 else 1
        
        if max_layers > 5:
            breaches.append(f"Max layers {max_layers} > 5")
        
        # Drawdown
        cum_pnl = camp_trades["pnl_usd"].cumsum()
        max_dd = (cum_pnl.cummax() - cum_pnl).max()
        if max_dd > 5000:
            breaches.append(f"Campaign DD ${max_dd:.0f} > $5000")
        
        # Daily loss (approximate)
        daily_pnl = camp_trades.groupby(camp_trades["entry_time"].dt.date)["pnl_usd"].sum()
        max_daily_loss = abs(daily_pnl.min()) if len(daily_pnl) > 0 else 0
        if max_daily_loss > 2000:
            breaches.append(f"Max daily loss ${max_daily_loss:.0f} > $2000")
        
        # Runner management
        runners = camp_trades[camp_trades["comment"].str.contains("runner", case=False, na=False)]
        if len(runners) > 0:
            runner_holds = runners["hold_time_hours"]
            if runner_holds.max() > 72:
                runner_mgmt = "poor"
            elif runner_holds.max() > 24:
                runner_mgmt = "acceptable"
            else:
                runner_mgmt = "good"
        else:
            runner_mgmt = "no_runners"
        
        # Risk score
        breach_penalty = len(breaches) * 20
        dd_penalty = min(30, max_dd / 10000 * 30)
        risk_score = max(0, 100 - breach_penalty - dd_penalty)
        
        return round(risk_score, 1), breaches, max_layers, runner_mgmt
    
    def _compare_behaviour(self, camp_trades: pd.DataFrame, camp_type: str) -> tuple:
        """Compare vs personal baseline and campaign type baseline."""
        if not self.behaviour:
            return {}, {}
        
        ct = camp_type
        personal = self.behaviour.get("pnl_skew", {}).get(ct, {})
        rv = self.behaviour.get("revenge_trades", {}).get(ct, {})
        sz = self.behaviour.get("sizing", {}).get(ct, {})
        
        # Campaign metrics
        camp_wr = (camp_trades["pnl_usd"] > 0).mean()
        camp_avg_win = camp_trades[camp_trades["pnl_usd"] > 0]["pnl_usd"].mean()
        camp_avg_loss = camp_trades[camp_trades["pnl_usd"] < 0]["pnl_usd"].mean()
        camp_cv = camp_trades["size_usd"].std() / camp_trades["size_usd"].mean() if camp_trades["size_usd"].mean() > 0 else 0
        
        vs_personal = {}
        vs_type = {}
        
        # Win rate
        if personal.get("win_rate", 0) > 0:
            vs_personal["win_rate"] = "better" if camp_wr > personal["win_rate"] else "worse"
        
        # Avg win
        if personal.get("avg_win", 0) > 0:
            vs_personal["avg_win"] = "better" if camp_avg_win > personal["avg_win"] else "worse"
        
        # Avg loss (less negative is better)
        if personal.get("avg_loss", 0) < 0:
            vs_personal["avg_loss"] = "better" if camp_avg_loss > personal["avg_loss"] else "worse"
        
        # Sizing CV
        if sz.get("cv", 0) > 0:
            vs_personal["sizing_consistency"] = "better" if camp_cv < sz["cv"] else "worse"
        
        # Revenge rate
        if rv.get("revenge_rate", 0) > 0:
            camp_revenge_rate = camp_trades.get("is_revenge", pd.Series([False]*len(camp_trades))).mean() if "is_revenge" in camp_trades.columns else 0
            vs_personal["revenge_rate"] = "better" if camp_revenge_rate < rv["revenge_rate"] else "worse"
        
        return vs_personal, vs_type
    
    def _generate_lessons(self, camp_trades: pd.DataFrame, camp_type: str,
                          net_pnl: float, win_rate: float, expectancy: float,
                          profit_factor: float, max_dd: float, duration_hours: float,
                          revenge_count: int, revenge_pnl: float,
                          sizing_discipline: str, session_adherence: str,
                          risk_breaches: List[str]) -> tuple:
        """Generate strengths, weaknesses, and action items."""
        strengths = []
        weaknesses = []
        actions = []
        
        # Profitability
        if net_pnl > 0:
            strengths.append(f"Campaign profitable: ${net_pnl:.0f}")
            if profit_factor > 2:
                strengths.append(f"Excellent profit factor: {profit_factor:.2f}")
        else:
            weaknesses.append(f"Campaign loss: ${net_pnl:.0f}")
            actions.append({
                "action": "Review all losing trades for common patterns",
                "deadline": "Next session",
                "owner": "Self"
            })
        
        # Win rate
        if win_rate > 0.65:
            strengths.append(f"Strong win rate: {win_rate:.0%}")
        elif win_rate < 0.5:
            weaknesses.append(f"Low win rate: {win_rate:.0%}")
        
        # Expectancy
        if expectancy > 0:
            strengths.append(f"Positive expectancy: ${expectancy:.0f}/trade")
        else:
            weaknesses.append(f"Negative expectancy: ${expectancy:.0f}/trade")
        
        # Revenge trading
        if revenge_count > 0:
            weaknesses.append(f"{revenge_count} revenge trades (${revenge_pnl:.0f} P&L)")
            actions.append({
                "action": f"Enforce {30 if camp_type == 'probe' else 60}min cooldown post-loss via Risk Guardian",
                "deadline": "Immediate",
                "owner": "System"
            })
        
        # Sizing
        if sizing_discipline in ["poor", "chaotic"]:
            weaknesses.append(f"Sizing discipline: {sizing_discipline} (CV={camp_trades['size_usd'].std()/camp_trades['size_usd'].mean():.2f})")
            actions.append({
                "action": "Implement fixed fractional sizing (e.g., 1% risk per trade)",
                "deadline": "Next campaign",
                "owner": "Self"
            })
        else:
            strengths.append(f"Sizing discipline: {sizing_discipline}")
        
        # Session adherence
        if session_adherence == "ignored":
            weaknesses.append("Major losses in sub-optimal session")
            actions.append({
                "action": "Restrict trading to high-WR sessions (London for Probe, avoid NY for Discretionary)",
                "deadline": "Immediate",
                "owner": "System"
            })
        elif session_adherence == "focused":
            strengths.append("Session focus maintained")
        
        # Drawdown
        if max_dd > abs(net_pnl) * 2:
            weaknesses.append(f"Max drawdown ${max_dd:.0f} > 2x net result")
            actions.append({
                "action": "Set tighter campaign-level DD limit (5% warning, 10% hard stop)",
                "deadline": "Next campaign",
                "owner": "Risk Guardian"
            })
        
        # Duration
        if duration_hours > 72:
            weaknesses.append(f"Extended duration: {duration_hours:.0f}h")
            actions.append({
                "action": "Set campaign time limit (max 48h auto-pause)",
                "deadline": "Next campaign",
                "owner": "Risk Guardian"
            })
        
        # Risk breaches
        for breach in risk_breaches:
            weaknesses.append(f"Risk breach: {breach}")
        
        return strengths, weaknesses, actions
    
    def save_review(self, review: CampaignReview):
        """Save review as JSON and Markdown."""
        # JSON
        json_file = OUT_DIR / f"{review.campaign_id}_review.json"
        with open(json_file, 'w') as f:
            json.dump(asdict(review), f, indent=2, default=str)
        
        # Markdown
        md_file = OUT_DIR / f"{review.campaign_id}_review.md"
        self._write_markdown(review, md_file)
        
        print(f"  Saved: {json_file}")
        print(f"  Saved: {md_file}")
    
    def _write_markdown(self, r: CampaignReview, path: Path):
        md = [
            f"# Post-Campaign Review: {r.campaign_id}",
            f"**Type:** {r.campaign_type.upper()} | **Date:** {r.review_date[:10]} | **Outcome:** {r.outcome}",
            "",
            "## Executive Summary",
            f"- **Net P&L:** ${r.net_pnl:,.2f}",
            f"- **Total Trades:** {r.total_trades}",
            f"- **Win Rate:** {r.win_rate:.1%}",
            f"- **Expectancy:** ${r.expectancy_per_trade:.2f}/trade",
            f"- **Profit Factor:** {r.profit_factor:.2f}",
            f"- **Max Drawdown:** ${r.max_drawdown:,.2f}",
            f"- **Duration:** {r.duration_hours:.1f} hours",
            "",
            "## Phase Scores",
            f"- **Setup Quality:** {r.setup_quality_score}/100 ({r.confluence_alignment})",
            f"- **Execution:** {r.execution_score}/100 ({r.sizing_discipline} sizing, {r.revenge_trade_count} revenge trades)",
            f"- **Risk Management:** {r.risk_score}/100 ({r.runner_management} runner management)",
            "",
            "## Setup Breakdown",
        ]
        for setup, count in r.setup_breakdown.items():
            md.append(f"- {setup}: {count} trades")
        
        md.extend([
            "",
            "## Behaviour vs Personal Baseline",
        ])
        for metric, comparison in r.vs_personal_baseline.items():
            emoji = "✅" if comparison == "better" else "❌" if comparison == "worse" else "➖"
            md.append(f"- {metric}: {comparison} {emoji}")
        
        md.extend([
            "",
            "## Key Strengths",
        ])
        for s in r.key_strengths:
            md.append(f"- ✅ {s}")
        
        md.extend([
            "",
            "## Key Weaknesses",
        ])
        for w in r.key_weaknesses:
            md.append(f"- ❌ {w}")
        
        md.extend([
            "",
            "## Action Items",
        ])
        for a in r.action_items:
            md.append(f"- [{a['deadline']}] **{a['owner']}**: {a['action']}")
        
        path.write_text("\n".join(md))


# ============ MAIN ============
def main():
    print("=" * 60)
    print("Post-Campaign Review — Module 7")
    print("=" * 60)
    
    engine = PostCampaignReviewEngine()
    
    if engine.trades_df is None:
        print("No trade data found")
        return
    
    campaigns = engine.trades_df["campaign_id"].unique()
    print(f"\nFound {len(campaigns)} campaigns to review")
    
    for camp_id in campaigns:
        if camp_id == "UNTAGGED":
            continue
        print(f"\nGenerating review for {camp_id}...")
        review = engine.generate_review(camp_id)
        engine.save_review(review)
        
        # Print summary
        print(f"  Outcome: {review.outcome} | P&L: ${review.net_pnl:,.0f} | WR: {review.win_rate:.1%} | PF: {review.profit_factor:.2f}")
        print(f"  Scores: Setup={review.setup_quality_score}, Exec={review.execution_score}, Risk={review.risk_score}")
        print(f"  Revenge: {review.revenge_trade_count} trades (${review.revenge_trade_pnl:,.0f})")
        print(f"  Sizing: {review.sizing_discipline} | Session: {review.session_adherence}")
        if review.action_items:
            print(f"  Actions: {len(review.action_items)} items")
    
    print(f"\n✓ All reviews saved to {OUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()