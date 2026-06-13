#!/usr/bin/env python3
"""
Real-Time Coaching — Module 6

Combines:
- Confluence Score (Module 4) — setup quality
- Risk Guardian (Module 10) — risk state
- Behaviour Analysis (Module 5) — personal patterns

Outputs structured coaching messages for pre-entry, during-trade, post-campaign.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings("ignore")

# ============ CONFIG ============
CONFLUENCE_FILE = Path(r"C:\Hermes\confluence_score\XAUUSD_confluence_score.parquet")
RISK_CONFIG = Path(r"C:\Hermes\risk_guardian\config.json")
BEHAVIOUR_FILE = Path(r"C:\Hermes\behaviour_analysis\outputs\behaviour_summary.json")
OUT_DIR = Path(r"C:\Hermes\coaching")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ============ ENUMS ============
class CoachingPhase(Enum):
    PRE_ENTRY = "pre_entry"
    DURING_TRADE = "during_trade"
    POST_CAMPAIGN = "post_campaign"
    RISK_ALERT = "risk_alert"

class CoachingAction(Enum):
    PROCEED = "proceed"
    PROCEED_WITH_CAUTION = "proceed_with_caution"
    REDUCE_SIZE = "reduce_size"
    SKIP = "skip"
    BLOCK = "block"
    TRAIL_STOP = "trail_stop"
    TAKE_PARTIAL = "take_partial"
    CLOSE_NOW = "close_now"
    REVIEW = "review"

class Severity(Enum):
    INFO = 1
    ADVISORY = 2
    WARNING = 3
    CRITICAL = 4
    EMERGENCY = 5


# ============ DATA CLASSES ============
@dataclass
class CoachingSignal:
    phase: CoachingPhase
    timestamp: datetime
    action: CoachingAction
    severity: Severity
    headline: str
    details: List[str]
    metrics: Dict[str, Any]
    campaign_id: Optional[str] = None
    trade_id: Optional[str] = None


@dataclass
class MarketContext:
    """Current market state for coaching."""
    confluence_score: float
    confluence_tier: str
    active_setups: List[str]
    session: str
    price: float
    timestamp: datetime


@dataclass
class RiskContext:
    """Current risk state from Risk Guardian."""
    overall_level: str
    daily_loss_pct: float
    weekly_loss_pct: float
    monthly_loss_pct: float
    total_layers: int
    max_layers_pct: float
    campaign_states: Dict[str, Dict]
    active_alerts: List[Dict]


@dataclass
class BehaviourContext:
    """Personal behaviour patterns from Module 5."""
    revenge_rate: float
    avg_loss_to_win_ratio: float
    sizing_cv: float
    session_bias: Dict
    max_loss_streak: int
    current_streak: Dict


# ============ COACHING ENGINE ============
class CoachingEngine:
    """Generates real-time coaching signals."""
    
    def __init__(self):
        self.confluence_data = None
        self.behaviour = None
        self._load_data()
    
    def _load_data(self):
        """Load reference data."""
        # Confluence score (latest)
        if CONFLUENCE_FILE.exists():
            df = pd.read_parquet(CONFLUENCE_FILE)
            self.confluence_data = df
        
        # Behaviour summary
        if BEHAVIOUR_FILE.exists():
            with open(BEHAVIOUR_FILE) as f:
                self.behaviour = json.load(f)
    
    def get_current_confluence(self, timestamp: datetime = None) -> MarketContext:
        """Get confluence snapshot at timestamp (or latest)."""
        if self.confluence_data is None:
            return MarketContext(50, "NEUTRAL", [], "unknown", 0, timestamp or datetime.now())
        
        if timestamp is None:
            row = self.confluence_data.iloc[-1]
        else:
            # Find closest bar
            idx = self.confluence_data.index.get_indexer([timestamp], method="nearest")[0]
            row = self.confluence_data.iloc[idx]
        
        active = row["active_setups"].split(";") if row["active_setups"] else []
        
        # Determine session
        hour = row.name.hour if hasattr(row.name, 'hour') else timestamp.hour
        if 0 <= hour < 8:
            session = "asian"
        elif 8 <= hour < 13:
            session = "london"
        elif 13 <= hour < 16:
            session = "overlap"
        elif 16 <= hour < 21:
            session = "ny"
        else:
            session = "asian"
        
        return MarketContext(
            confluence_score=row["confluence_score"],
            confluence_tier=row["tier"],
            active_setups=active,
            session=session,
            price=row.get("M12_close", 0),
            timestamp=timestamp or datetime.now()
        )
    
    def get_risk_context(self, risk_guardian_state: Dict) -> RiskContext:
        """Extract coaching-relevant risk state."""
        dims = risk_guardian_state.get("dimensions", {})
        return RiskContext(
            overall_level=risk_guardian_state.get("overall_level", "ADVISORY"),
            daily_loss_pct=dims.get("daily_loss", {}).get("utilization_pct", 0),
            weekly_loss_pct=dims.get("weekly_loss", {}).get("utilization_pct", 0),
            monthly_loss_pct=dims.get("monthly_loss", {}).get("utilization_pct", 0),
            total_layers=dims.get("max_layers", {}).get("current", 0),
            max_layers_pct=dims.get("max_layers", {}).get("utilization_pct", 0),
            campaign_states=risk_guardian_state.get("campaigns", {}),
            active_alerts=risk_guardian_state.get("recent_alerts", [])
        )
    
    def get_behaviour_context(self, campaign_type: str) -> BehaviourContext:
        """Get personal behaviour patterns for campaign type."""
        if not self.behaviour:
            return BehaviourContext(0, 1, 0, {}, 0, {"type": "win", "length": 0})
        
        ct = campaign_type.lower()
        rv = self.behaviour.get("revenge_trades", {}).get(ct, {})
        sz = self.behaviour.get("sizing", {}).get(ct, {})
        pnl = self.behaviour.get("pnl_skew", {}).get(ct, {})
        st = self.behaviour.get("streaks", {}).get(ct, {})
        ss = self.behaviour.get("session_bias", {}).get(ct, {})
        
        return BehaviourContext(
            revenge_rate=rv.get("revenge_rate", 0),
            avg_loss_to_win_ratio=abs(pnl.get("avg_loss", -1) / pnl.get("avg_win", 1)) if pnl.get("avg_win") else 1,
            sizing_cv=sz.get("cv", 0),
            session_bias=ss,
            max_loss_streak=st.get("max_loss_streak", 0),
            current_streak={"type": st.get("current_streak_type", "win"), "length": st.get("current_streak", 0)}
        )
    
    # ---- PRE-ENTRY COACHING ----
    
    def coach_pre_entry(self, market: MarketContext, risk: RiskContext, 
                        behaviour: BehaviourContext, campaign_type: str,
                        proposed_size_usd: float = None) -> CoachingSignal:
        """Generate pre-entry coaching signal."""
        details = []
        action = CoachingAction.PROCEED
        severity = Severity.INFO
        
        # 1. Confluence check
        if market.confluence_tier in ["STRONG_LONG", "STRONG_SHORT"]:
            details.append(f"✅ Confluence {market.confluence_score:.0f} ({market.confluence_tier}) — high quality setup")
        elif market.confluence_tier in ["MODERATE_LONG", "MODERATE_SHORT"]:
            details.append(f"⚠️ Confluence {market.confluence_score:.0f} ({market.confluence_tier}) — moderate quality")
            action = CoachingAction.PROCEED_WITH_CAUTION
            severity = Severity.ADVISORY
        else:
            details.append(f"❌ Confluence {market.confluence_score:.0f} ({market.confluence_tier}) — low quality")
            action = CoachingAction.SKIP
            severity = Severity.WARNING
        
        # 2. Risk Guardian check
        if risk.overall_level in ["CRITICAL", "EMERGENCY"]:
            details.append(f"🛑 Risk {risk.overall_level} — hard limits breached")
            action = CoachingAction.BLOCK
            severity = Severity.EMERGENCY
        elif risk.overall_level == "WARNING":
            details.append(f"⚠️ Risk WARNING — daily loss {risk.daily_loss_pct:.0f}%, layers {risk.total_layers}")
            if action == CoachingAction.PROCEED:
                action = CoachingAction.REDUCE_SIZE
            severity = Severity(max(severity.value, Severity.WARNING.value))
        elif risk.daily_loss_pct > 50:
            details.append(f"⚠️ Daily loss at {risk.daily_loss_pct:.0f}% (warning at 70%)")
            severity = Severity(max(severity.value, Severity.ADVISORY.value))
        
        # 3. Campaign-specific risk
        for camp_id, camp in risk.campaign_states.items():
            if camp.get("paused"):
                details.append(f"🛑 Campaign {camp_id} PAUSED: {camp.get('pause_reason')}")
                action = CoachingAction.BLOCK
                severity = Severity.CRITICAL
            if camp.get("drawdown_pct", 0) > 8:
                details.append(f"⚠️ Campaign {camp_id} DD: {camp['drawdown_pct']:.1f}%")
                severity = Severity(max(severity.value, Severity.WARNING.value))

        # 4. Behaviour patterns
        if behaviour.revenge_rate > 0.25:
            details.append(f"🧠 High revenge rate ({behaviour.revenge_rate:.0%}) — ensure cooldown respected")
            severity = Severity(max(severity.value, Severity.ADVISORY.value))

        if behaviour.avg_loss_to_win_ratio > 2:
            details.append(f"📉 Loss/Win ratio {behaviour.avg_loss_to_win_ratio:.1f}x — size losers smaller")
            if action == CoachingAction.PROCEED:
                action = CoachingAction.REDUCE_SIZE

        if behaviour.sizing_cv > 1.0:
            details.append(f"📏 Sizing inconsistent (CV={behaviour.sizing_cv:.2f}) — use fixed risk per trade")

        # 5. Session bias
        session_key = market.session
        if session_key in behaviour.session_bias:
            sess_stats = behaviour.session_bias[session_key]
            if sess_stats.get("win_rate", 0) < 0.45:
                details.append(f"🕐 {session_key.capitalize()} session WR only {sess_stats['win_rate']:.0%} — consider skipping")
                if action == CoachingAction.PROCEED:
                    action = CoachingAction.PROCEED_WITH_CAUTION

        # 6. Streak awareness
        if behaviour.current_streak["type"] == "loss" and behaviour.current_streak["length"] >= 3:
            details.append(f"🔴 Current loss streak: {behaviour.current_streak['length']} — extra caution")
            severity = Severity(max(severity.value, Severity.ADVISORY.value))
        
        # 7. Active setups
        if market.active_setups:
            details.append(f"🎯 Active: {', '.join(market.active_setups)}")
        
        # Headline
        if action == CoachingAction.BLOCK:
            headline = "BLOCKED — Risk/Quality thresholds not met"
        elif action == CoachingAction.SKIP:
            headline = "SKIP — Low confluence, wait for better setup"
        elif action == CoachingAction.REDUCE_SIZE:
            headline = "REDUCE SIZE — Proceed with smaller position"
        elif action == CoachingAction.PROCEED_WITH_CAUTION:
            headline = "CAUTION — Proceed but manage risk tightly"
        else:
            headline = "PROCEED — Setup quality and risk acceptable"
        
        return CoachingSignal(
            phase=CoachingPhase.PRE_ENTRY,
            timestamp=datetime.now(),
            action=action,
            severity=severity,
            headline=headline,
            details=details,
            metrics={
                "confluence_score": market.confluence_score,
                "confluence_tier": market.confluence_tier,
                "risk_level": risk.overall_level,
                "daily_loss_pct": risk.daily_loss_pct,
                "session": market.session,
            }
        )
    
    # ---- DURING-TRADE COACHING ----
    
    def coach_during_trade(self, market: MarketContext, risk: RiskContext,
                           behaviour: BehaviourContext, campaign_id: str,
                           position: Dict) -> CoachingSignal:
        """Generate during-trade coaching signal."""
        details = []
        action = CoachingAction.PROCEED
        severity = Severity.INFO
        
        entry_price = position.get("entry_price", 0)
        current_price = market.price
        direction = position.get("direction", "long")
        hold_hours = position.get("hold_hours", 0)
        unrealized_pnl_pct = position.get("unrealized_pnl_pct", 0)
        is_runner = position.get("is_runner", False)
        
        # 1. Runner management
        if is_runner:
            max_hold = 48 if behaviour.current_streak.get("type") == "win" else 24  # placeholder
            if hold_hours > max_hold:
                details.append(f"🏃 Runner held {hold_hours:.1f}h (max {max_hold}h) — consider trailing or closing")
                action = CoachingAction.TAKE_PARTIAL
                severity = Severity.WARNING
            elif hold_hours > max_hold * 0.75:
                details.append(f"🏃 Runner at {hold_hours:.1f}h — start trailing stop")
                action = CoachingAction.TRAIL_STOP
                severity = Severity.ADVISORY
        
        # 2. Unrealized P&L
        if unrealized_pnl_pct > 0.02:  # >2% profit
            details.append(f"💰 Unrealized +{unrealized_pnl_pct:.1%} — consider partial at 1.5-2R")
            action = CoachingAction.TAKE_PARTIAL
        elif unrealized_pnl_pct < -0.015:  # >1.5% loss
            details.append(f"📉 Unrealized {unrealized_pnl_pct:.1%} — review stop placement")
            severity = Severity.ADVISORY
        
        # 3. Time-based exits
        if hold_hours > 4 and unrealized_pnl_pct < 0.005:  # 4h, not working
            details.append(f"⏱️ Stale trade {hold_hours:.1f}h with minimal profit — consider closing")
            action = CoachingAction.CLOSE_NOW
            severity = Severity.WARNING
        
        # 4. Confluence decay
        if market.confluence_tier in ["WEAK_SHORT", "STRONG_SHORT"] and direction == "long":
            details.append(f"📊 Confluence flipped to {market.confluence_tier} — thesis weakening")
            action = CoachingAction.CLOSE_NOW
            severity = Severity.WARNING
        
        # 5. Risk escalation
        if risk.overall_level in ["CRITICAL", "EMERGENCY"]:
            details.append(f"🛑 Risk {risk.overall_level} — reduce/close immediately")
            action = CoachingAction.CLOSE_NOW
            severity = Severity.EMERGENCY
        
        headline = "HOLD — Position within parameters"
        if action == CoachingAction.CLOSE_NOW:
            headline = "CLOSE NOW — Thesis invalid or risk critical"
        elif action == CoachingAction.TAKE_PARTIAL:
            headline = "TAKE PARTIAL — Lock in profits"
        elif action == CoachingAction.TRAIL_STOP:
            headline = "TRAIL STOP — Protect gains"
        
        return CoachingSignal(
            phase=CoachingPhase.DURING_TRADE,
            timestamp=datetime.now(),
            action=action,
            severity=severity,
            headline=headline,
            details=details,
            metrics={
                "hold_hours": hold_hours,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "is_runner": is_runner,
                "confluence_tier": market.confluence_tier,
            },
            campaign_id=campaign_id,
            trade_id=position.get("trade_id")
        )
    
    # ---- POST-CAMPAIGN COACHING ----
    
    def coach_post_campaign(self, campaign_id: str, campaign_data: Dict,
                            behaviour: BehaviourContext) -> CoachingSignal:
        """Generate post-campaign review coaching."""
        details = []
        action = CoachingAction.REVIEW
        severity = Severity.INFO
        
        net_pnl = campaign_data.get("net_pnl", 0)
        n_trades = campaign_data.get("n_trades", 0)
        win_rate = campaign_data.get("win_rate", 0)
        max_dd = campaign_data.get("max_drawdown", 0)
        duration_h = campaign_data.get("duration_hours", 0)
        camp_type = campaign_data.get("type", "unknown")
        
        # P&L assessment
        if net_pnl > 0:
            details.append(f"✅ Campaign profitable: ${net_pnl:.0f} over {n_trades} trades")
        else:
            details.append(f"❌ Campaign loss: ${net_pnl:.0f} over {n_trades} trades")
            severity = Severity.WARNING
        
        # Win rate vs expectancy
        if win_rate > 0.6:
            details.append(f"📊 Win rate {win_rate:.0%} — good")
        else:
            details.append(f"📊 Win rate {win_rate:.0%} — below target")
        
        # Drawdown
        if max_dd > abs(net_pnl) * 2:
            details.append(f"⚠️ Max DD ${max_dd:.0f} > 2x net result — exits too late")
            severity = Severity.WARNING
        
        # Duration
        if duration_h > 72:
            details.append(f"⏱️ Long campaign ({duration_h:.0f}h) — consider time limits")
        
        # Behaviour comparison
        if camp_type == "discretionary" and behaviour.avg_loss_to_win_ratio > 2:
            details.append(f"🧠 Discretionary loss/win ratio {behaviour.avg_loss_to_win_ratio:.1f}x — review sizing discipline")
        
        if behaviour.revenge_rate > 0.25:
            revenge_in_camp = campaign_data.get("revenge_trades", 0)
            if revenge_in_camp > 0:
                details.append(f"🔴 {revenge_in_camp} revenge trades in this campaign")
        
        headline = f"REVIEW — {camp_type.upper()} campaign {'profitable' if net_pnl > 0 else 'loss'}"
        
        return CoachingSignal(
            phase=CoachingPhase.POST_CAMPAIGN,
            timestamp=datetime.now(),
            action=action,
            severity=severity,
            headline=headline,
            details=details,
            metrics=campaign_data,
            campaign_id=campaign_id
        )
    
    # ---- FORMAT OUTPUT ----
    
    def format_signal(self, signal: CoachingSignal) -> str:
        """Format coaching signal for display/Telegram."""
        severity_emoji = {
            Severity.INFO: "ℹ️",
            Severity.ADVISORY: "⚠️",
            Severity.WARNING: "🟠",
            Severity.CRITICAL: "🔴",
            Severity.EMERGENCY: "🚨"
        }
        
        action_emoji = {
            CoachingAction.PROCEED: "✅",
            CoachingAction.PROCEED_WITH_CAUTION: "⚠️",
            CoachingAction.REDUCE_SIZE: "📉",
            CoachingAction.SKIP: "⏭️",
            CoachingAction.BLOCK: "🛑",
            CoachingAction.TRAIL_STOP: "📈",
            CoachingAction.TAKE_PARTIAL: "💰",
            CoachingAction.CLOSE_NOW: "🔚",
            CoachingAction.REVIEW: "📋"
        }
        
        lines = [
            f"{severity_emoji[signal.severity]} {action_emoji[signal.action]} **{signal.headline}**",
            f"Phase: {signal.phase.value.upper()}",
            f"Time: {signal.timestamp.strftime('%H:%M:%S UTC')}",
            ""
        ]
        
        for detail in signal.details:
            lines.append(f"  {detail}")
        
        if signal.metrics:
            lines.append("")
            lines.append("Metrics:")
            for k, v in signal.metrics.items():
                if isinstance(v, float):
                    lines.append(f"  {k}: {v:.3f}" if v < 1 else f"  {k}: {v:.1f}")
                else:
                    lines.append(f"  {k}: {v}")
        
        return "\n".join(lines)


# ============ DEMO ============
def run_demo():
    print("=" * 60)
    print("Real-Time Coaching — Module 6 Demo")
    print("=" * 60)
    
    engine = CoachingEngine()
    
    # Mock current market state (latest confluence)
    market = engine.get_current_confluence()
    print(f"\nMarket Context: Score={market.confluence_score:.0f} ({market.confluence_tier}), Session={market.session}")
    
    # Mock risk state (from Risk Guardian)
    risk_state = {
        "overall_level": "ADVISORY",
        "dimensions": {
            "daily_loss": {"utilization_pct": 45, "current": 900, "hard_limit": 2000},
            "weekly_loss": {"utilization_pct": 30, "current": 1500, "hard_limit": 5000},
            "max_layers": {"utilization_pct": 20, "current": 1, "hard_limit": 5},
        },
        "campaigns": {
            "CAMPAIGN_001": {"type": "probe", "drawdown_pct": 2, "paused": False, "layers": 1},
        },
        "recent_alerts": []
    }
    risk = engine.get_risk_context(risk_state)
    
    # Behaviour context for probe
    behaviour = engine.get_behaviour_context("probe")
    print(f"Behaviour: Revenge={behaviour.revenge_rate:.0%}, Loss/Win={behaviour.avg_loss_to_win_ratio:.1f}x, CV={behaviour.sizing_cv:.2f}")
    
    # ---- PRE-ENTRY DEMO ----
    print("\n" + "=" * 60)
    print("PRE-ENTRY COACHING")
    print("=" * 60)
    
    signal = engine.coach_pre_entry(market, risk, behaviour, "probe", proposed_size_usd=1000)
    print(engine.format_signal(signal))
    
    # ---- DURING-TRADE DEMO ----
    print("\n" + "=" * 60)
    print("DURING-TRADE COACHING")
    print("=" * 60)
    
    position = {
        "trade_id": "POS_12345",
        "entry_price": 1980.50,
        "direction": "long",
        "hold_hours": 2.5,
        "unrealized_pnl_pct": 0.012,  # +1.2%
        "is_runner": True,
    }
    
    signal = engine.coach_during_trade(market, risk, behaviour, "CAMPAIGN_001", position)
    print(engine.format_signal(signal))
    
    # ---- POST-CAMPAIGN DEMO ----
    print("\n" + "=" * 60)
    print("POST-CAMPAIGN COACHING")
    print("=" * 60)
    
    campaign_data = {
        "campaign_id": "CAMPAIGN_001",
        "type": "probe",
        "net_pnl": 6856,
        "n_trades": 187,
        "win_rate": 0.679,
        "max_drawdown": 2054,
        "duration_hours": 102,
        "revenge_trades": 59,
    }
    
    signal = engine.coach_post_campaign("CAMPAIGN_001", campaign_data, behaviour)
    print(engine.format_signal(signal))
    
    print("\n" + "=" * 60)
    print("Demo complete. Coaching engine ready for integration.")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()