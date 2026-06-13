#!/usr/bin/env python3
"""
Risk Guardian — Module 10

Real-time risk monitoring with hard limits, escalating warnings,
and campaign-level guards. Fully configurable thresholds.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings("ignore")

# ============ CONFIG ============
CONFIG_FILE = Path(r"C:\Hermes\risk_guardian\config.json")
STATE_FILE = Path(r"C:\Hermes\risk_guardian\state.json")
LOG_DIR = Path(r"C:\Hermes\risk_guardian\logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ============ ENUMS ============
class AlertLevel(Enum):
    ADVISORY = 1      # Info: approaching threshold
    WARNING = 2       # Caution: at threshold, reduce risk
    CRITICAL = 3      # Danger: exceeded threshold, block new risk
    EMERGENCY = 4     # Catastrophic: force close / halt

class ActionType(Enum):
    NONE = "none"
    LOG_ONLY = "log_only"
    NOTIFY = "notify"
    BLOCK_NEW = "block_new_entries"
    REDUCE_POSITION = "reduce_position"
    PAUSE_CAMPAIGN = "pause_campaign"
    FORCE_CLOSE = "force_close_all"
    HALT_SYSTEM = "halt_trading"

class Dimension(Enum):
    DAILY_LOSS = "daily_loss"
    WEEKLY_LOSS = "weekly_loss"
    MONTHLY_LOSS = "monthly_loss"
    MAX_LAYERS = "max_layers"
    CAMPAIGN_DD = "campaign_drawdown"
    EXPOSURE_CONCENTRATION = "exposure_concentration"

# ============ DATA CLASSES ============
@dataclass
class ThresholdConfig:
    """Two-tier threshold for a risk dimension."""
    warning_pct: float      # % of limit at warning level (e.g., 0.7 = 70%)
    hard_limit: float       # Absolute limit (e.g., 5000 = $5000 daily loss)
    unit: str               # "usd", "pct", "count", "ratio"
    
    @property
    def warning_value(self) -> float:
        return self.hard_limit * self.warning_pct


@dataclass
class DimensionState:
    """Current state of a risk dimension."""
    dimension: Dimension
    current_value: float = 0.0
    peak_value: float = 0.0
    threshold: Optional[ThresholdConfig] = None
    level: AlertLevel = AlertLevel.ADVISORY
    last_alert_time: Optional[datetime] = None
    alert_count: int = 0


@dataclass
class RiskAlert:
    """A risk alert event."""
    timestamp: datetime
    dimension: Dimension
    level: AlertLevel
    current_value: float
    threshold_value: float
    message: str
    action: ActionType
    campaign_id: Optional[str] = None
    acknowledged: bool = False


@dataclass
class CampaignRiskState:
    """Risk state for a specific campaign."""
    campaign_id: str
    campaign_type: str  # "probe" or "discretionary"
    entry_time: datetime
    initial_equity: float
    current_equity: float
    peak_equity: float
    layers: int = 0
    max_layers_allowed: int = 3
    basket_risk_pct: float = 0.0
    runner_active: bool = False
    runner_entry_time: Optional[datetime] = None
    last_entry_time: Optional[datetime] = None
    entry_count_today: int = 0
    paused: bool = False
    pause_reason: Optional[str] = None


# ============ DEFAULT CONFIG ============
DEFAULT_CONFIG = {
    "dimensions": {
        "daily_loss": {
            "warning_pct": 0.7,
            "hard_limit": 2000.0,      # $2000/day
            "unit": "usd"
        },
        "weekly_loss": {
            "warning_pct": 0.7,
            "hard_limit": 5000.0,      # $5000/week
            "unit": "usd"
        },
        "monthly_loss": {
            "warning_pct": 0.6,
            "hard_limit": 15000.0,     # $15000/month
            "unit": "usd"
        },
        "max_layers": {
            "warning_pct": 0.8,
            "hard_limit": 5,           # Max 5 concurrent layers
            "unit": "count"
        },
        "campaign_drawdown": {
            "warning_pct": 0.5,
            "hard_limit": 0.10,        # 10% campaign DD
            "unit": "pct"
        },
        "exposure_concentration": {
            "warning_pct": 0.7,
            "hard_limit": 0.50,        # 50% in single symbol
            "unit": "ratio"
        }
    },
    "campaign_guards": {
        "probe": {
            "max_layers": 3,
            "basket_risk_cap_pct": 0.03,   # 3% total risk across basket
            "runner_max_hold_hours": 48,
            "revenge_cooldown_minutes": 30,
            "max_entries_per_hour": 4
        },
        "discretionary": {
            "max_layers": 2,
            "basket_risk_cap_pct": 0.05,
            "runner_max_hold_hours": 168,  # 1 week
            "revenge_cooldown_minutes": 60,
            "max_entries_per_hour": 2
        }
    },
    "escalation": {
        "advisory_cooldown_minutes": 60,
        "warning_cooldown_minutes": 30,
        "critical_cooldown_minutes": 15,
        "emergency_cooldown_minutes": 5
    },
    "notifications": {
        "enabled": True,
        "webhook_url": "",
        "email": ""
    }
}


# ============ RISK GUARDIAN ENGINE ============
class RiskGuardian:
    """Main risk monitoring engine."""
    
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.config = self._load_config()
        self.dimensions: Dict[Dimension, DimensionState] = {}
        self.campaigns: Dict[str, CampaignRiskState] = {}
        self.alerts: List[RiskAlert] = []
        self.alert_log_path = LOG_DIR / f"alerts_{datetime.now().strftime('%Y%m%d')}.jsonl"
        self._init_dimensions()
    
    def _load_config(self) -> dict:
        if self.config_path.exists():
            with open(self.config_path) as f:
                return json.load(f)
        return DEFAULT_CONFIG.copy()
    
    def save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def _init_dimensions(self):
        for dim_name, cfg in self.config["dimensions"].items():
            dim = Dimension(dim_name)
            self.dimensions[dim] = DimensionState(
                dimension=dim,
                threshold=ThresholdConfig(**cfg)
            )
    
    # ---- Core Update Methods ----
    
    def update_daily_loss(self, pnl: float):
        """Update daily P&L (negative = loss)."""
        self.dimensions[Dimension.DAILY_LOSS].current_value = abs(min(0, pnl))
        self.dimensions[Dimension.DAILY_LOSS].peak_value = max(
            self.dimensions[Dimension.DAILY_LOSS].peak_value,
            self.dimensions[Dimension.DAILY_LOSS].current_value
        )
    
    def update_weekly_loss(self, pnl: float):
        self.dimensions[Dimension.WEEKLY_LOSS].current_value = abs(min(0, pnl))
        self.dimensions[Dimension.WEEKLY_LOSS].peak_value = max(
            self.dimensions[Dimension.WEEKLY_LOSS].peak_value,
            self.dimensions[Dimension.WEEKLY_LOSS].current_value
        )
    
    def update_monthly_loss(self, pnl: float):
        self.dimensions[Dimension.MONTHLY_LOSS].current_value = abs(min(0, pnl))
        self.dimensions[Dimension.MONTHLY_LOSS].peak_value = max(
            self.dimensions[Dimension.MONTHLY_LOSS].peak_value,
            self.dimensions[Dimension.MONTHLY_LOSS].current_value
        )
    
    def update_layers(self, total_layers: int):
        self.dimensions[Dimension.MAX_LAYERS].current_value = total_layers
        self.dimensions[Dimension.MAX_LAYERS].peak_value = max(
            self.dimensions[Dimension.MAX_LAYERS].peak_value,
            total_layers
        )
    
    def update_campaign_dd(self, campaign_id: str, current_equity: float, peak_equity: float):
        if peak_equity > 0:
            dd = (peak_equity - current_equity) / peak_equity
            self.dimensions[Dimension.CAMPAIGN_DD].current_value = max(
                self.dimensions[Dimension.CAMPAIGN_DD].current_value, dd
            )
        # Also update campaign-specific state
        if campaign_id in self.campaigns:
            c = self.campaigns[campaign_id]
            c.current_equity = current_equity
            c.peak_equity = max(c.peak_equity, current_equity)
            self._check_campaign_guards(campaign_id)
    
    def update_exposure(self, symbol_exposures: Dict[str, float], total_equity: float):
        """symbol_exposures = {symbol: notional_value}"""
        if total_equity > 0 and symbol_exposures:
            max_concentration = max(abs(v) for v in symbol_exposures.values()) / total_equity
            self.dimensions[Dimension.EXPOSURE_CONCENTRATION].current_value = max_concentration
            self.dimensions[Dimension.EXPOSURE_CONCENTRATION].peak_value = max(
                self.dimensions[Dimension.EXPOSURE_CONCENTRATION].peak_value,
                max_concentration
            )
    
    # ---- Campaign Management ----
    
    def register_campaign(self, campaign_id: str, campaign_type: str, 
                          initial_equity: float, max_layers: Optional[int] = None):
        guards = self.config["campaign_guards"].get(campaign_type, 
                                                    self.config["campaign_guards"]["probe"])
        self.campaigns[campaign_id] = CampaignRiskState(
            campaign_id=campaign_id,
            campaign_type=campaign_type,
            entry_time=datetime.now(),
            initial_equity=initial_equity,
            current_equity=initial_equity,
            peak_equity=initial_equity,
            max_layers_allowed=max_layers or guards["max_layers"]
        )
        return self.campaigns[campaign_id]
    
    def record_entry(self, campaign_id: str, layer_size: float = 1.0):
        """Record a new entry/layer for a campaign."""
        if campaign_id not in self.campaigns:
            return False, "Campaign not registered"
        
        c = self.campaigns[campaign_id]
        guards = self.config["campaign_guards"][c.campaign_type]
        now = datetime.now()
        
        # Check max layers
        if c.layers >= c.max_layers_allowed:
            return False, f"Max layers ({c.max_layers_allowed}) reached"
        
        # Check entries per hour
        if c.last_entry_time:
            hours_since = (now - c.last_entry_time).total_seconds() / 3600
            if hours_since < 1 and c.entry_count_today >= guards["max_entries_per_hour"]:
                return False, f"Max entries per hour ({guards['max_entries_per_hour']}) reached"
            if hours_since >= 1:
                c.entry_count_today = 0
        
        # Revenge trade cooldown
        if c.last_entry_time:
            minutes_since = (now - c.last_entry_time).total_seconds() / 60
            if minutes_since < guards["revenge_cooldown_minutes"]:
                return False, f"Revenge cooldown active ({guards['revenge_cooldown_minutes']} min)"
        
        # All checks passed
        c.layers += 1
        c.last_entry_time = now
        c.entry_count_today += 1
        return True, "Entry recorded"
    
    def record_exit(self, campaign_id: str, layer_size: float = 1.0):
        """Record an exit (reduce layer count)."""
        if campaign_id in self.campaigns:
            self.campaigns[campaign_id].layers = max(0, self.campaigns[campaign_id].layers - 1)
    
    def start_runner(self, campaign_id: str):
        """Mark a runner position as active."""
        if campaign_id in self.campaigns:
            c = self.campaigns[campaign_id]
            c.runner_active = True
            c.runner_entry_time = datetime.now()
    
    def end_runner(self, campaign_id: str):
        if campaign_id in self.campaigns:
            self.campaigns[campaign_id].runner_active = False
            self.campaigns[campaign_id].runner_entry_time = None
    
    def abandon_runner(self, campaign_id: str):
        """Alert: runner abandoned (early exit)."""
        if campaign_id in self.campaigns:
            self._raise_alert(
                dimension=Dimension.CAMPAIGN_DD,
                level=AlertLevel.WARNING,
                message=f"Runner abandoned early for campaign {campaign_id}",
                action=ActionType.NOTIFY,
                campaign_id=campaign_id
            )
            self.end_runner(campaign_id)
    
    # ---- Campaign Guard Checks ----
    
    def _check_campaign_guards(self, campaign_id: str):
        c = self.campaigns[campaign_id]
        guards = self.config["campaign_guards"][c.campaign_type]
        now = datetime.now()
        
        # Basket risk cap
        if c.initial_equity > 0:
            basket_risk = (c.initial_equity - c.current_equity) / c.initial_equity
            c.basket_risk_pct = basket_risk
            if basket_risk > guards["basket_risk_cap_pct"]:
                self._raise_alert(
                    dimension=Dimension.CAMPAIGN_DD,
                    level=AlertLevel.CRITICAL,
                    message=f"Campaign {campaign_id} basket risk {basket_risk:.1%} exceeds cap {guards['basket_risk_cap_pct']:.1%}",
                    action=ActionType.PAUSE_CAMPAIGN,
                    campaign_id=campaign_id
                )
                c.paused = True
                c.pause_reason = "basket_risk_cap_exceeded"
        
        # Runner max hold time
        if c.runner_active and c.runner_entry_time:
            hold_hours = (now - c.runner_entry_time).total_seconds() / 3600
            if hold_hours > guards["runner_max_hold_hours"]:
                self._raise_alert(
                    dimension=Dimension.CAMPAIGN_DD,
                    level=AlertLevel.WARNING,
                    message=f"Runner held {hold_hours:.1f}h > max {guards['runner_max_hold_hours']}h for {campaign_id}",
                    action=ActionType.NOTIFY,
                    campaign_id=campaign_id
                )
    
    # ---- Alert Engine ----
    
    def _raise_alert(self, dimension: Dimension, level: AlertLevel, 
                     message: str, action: ActionType, campaign_id: Optional[str] = None):
        """Raise an alert if cooldown allows."""
        dim_state = self.dimensions[dimension]
        now = datetime.now()
        
        # Check cooldown
        cooldown_map = {
            AlertLevel.ADVISORY: self.config["escalation"]["advisory_cooldown_minutes"],
            AlertLevel.WARNING: self.config["escalation"]["warning_cooldown_minutes"],
            AlertLevel.CRITICAL: self.config["escalation"]["critical_cooldown_minutes"],
            AlertLevel.EMERGENCY: self.config["escalation"]["emergency_cooldown_minutes"],
        }
        cooldown = cooldown_map.get(level, 60)
        
        if dim_state.last_alert_time:
            minutes_since = (now - dim_state.last_alert_time).total_seconds() / 60
            if minutes_since < cooldown:
                return  # Suppressed by cooldown
        
        # Determine threshold value
        threshold_val = dim_state.threshold.warning_value if level in [AlertLevel.ADVISORY, AlertLevel.WARNING] \
                       else dim_state.threshold.hard_limit
        
        alert = RiskAlert(
            timestamp=now,
            dimension=dimension,
            level=level,
            current_value=dim_state.current_value,
            threshold_value=threshold_val,
            message=message,
            action=action,
            campaign_id=campaign_id
        )
        
        self.alerts.append(alert)
        dim_state.last_alert_time = now
        dim_state.alert_count += 1
        dim_state.level = max(dim_state.level, level, key=lambda x: x.value)
        
        self._log_alert(alert)
        self._execute_action(alert)
    
    def _log_alert(self, alert: RiskAlert):
        """Log alert to JSONL file."""
        record = {
            "timestamp": alert.timestamp.isoformat(),
            "dimension": alert.dimension.value,
            "level": alert.level.name,
            "current_value": alert.current_value,
            "threshold_value": alert.threshold_value,
            "message": alert.message,
            "action": alert.action.value,
            "campaign_id": alert.campaign_id
        }
        with open(self.alert_log_path, 'a') as f:
            f.write(json.dumps(record) + '\n')
    
    def _execute_action(self, alert: RiskAlert):
        """Execute the alert action (placeholder for integration)."""
        # This would integrate with:
        # - Order management (block/reduce/close)
        # - Campaign manager (pause)
        # - Notification system (webhook/email)
        # - Coaching stream (for Module 6)
        pass
    
    # ---- Monitoring Loop ----
    
    def evaluate_all(self):
        """Evaluate all dimensions and raise alerts as needed."""
        now = datetime.now()
        
        for dim, state in self.dimensions.items():
            if not state.threshold:
                continue
            
            current = state.current_value
            warning_val = state.threshold.warning_value
            hard_val = state.threshold.hard_limit
            
            # Determine level
            if current >= hard_val:
                level = AlertLevel.EMERGENCY
                action = ActionType.FORCE_CLOSE
            elif current >= warning_val:
                level = AlertLevel.WARNING if current < hard_val * 0.9 else AlertLevel.CRITICAL
                action = ActionType.BLOCK_NEW if level == AlertLevel.WARNING else ActionType.REDUCE_POSITION
            elif current >= warning_val * 0.5:
                level = AlertLevel.ADVISORY
                action = ActionType.NOTIFY
            else:
                continue  # No alert needed
            
            # Only escalate, don't de-escalate automatically
            if level.value > state.level.value:
                self._raise_alert(
                    dimension=dim,
                    level=level,
                    message=f"{dim.value}: {current:.2f} {state.threshold.unit} "
                           f"({'exceeds' if level.value >= AlertLevel.CRITICAL.value else 'approaches'} "
                           f"{'hard limit' if level.value >= AlertLevel.CRITICAL.value else 'warning threshold'} "
                           f"{hard_val if level.value >= AlertLevel.CRITICAL.value else warning_val:.2f})",
                    action=action
                )
    
    def get_status(self) -> dict:
        """Get current risk status summary."""
        return {
            "timestamp": datetime.now().isoformat(),
            "dimensions": {
                dim.value: {
                    "current": state.current_value,
                    "peak": state.peak_value,
                    "warning_threshold": state.threshold.warning_value if state.threshold else None,
                    "hard_limit": state.threshold.hard_limit if state.threshold else None,
                    "level": state.level.name,
                    "utilization_pct": (state.current_value / state.threshold.hard_limit * 100) 
                                       if state.threshold and state.threshold.hard_limit > 0 else 0
                }
                for dim, state in self.dimensions.items()
            },
            "campaigns": {
                cid: {
                    "type": c.campaign_type,
                    "layers": c.layers,
                    "max_layers": c.max_layers_allowed,
                    "current_equity": c.current_equity,
                    "drawdown_pct": (c.peak_equity - c.current_equity) / c.peak_equity * 100 
                                   if c.peak_equity > 0 else 0,
                    "basket_risk_pct": c.basket_risk_pct * 100,
                    "runner_active": c.runner_active,
                    "paused": c.paused,
                    "pause_reason": c.pause_reason
                }
                for cid, c in self.campaigns.items()
            },
            "recent_alerts": [
                {
                    "time": a.timestamp.isoformat(),
                    "dimension": a.dimension.value,
                    "level": a.level.name,
                    "message": a.message,
                    "action": a.action.value
                }
                for a in self.alerts[-10:]
            ],
            "overall_level": max((s.level for s in self.dimensions.values()), 
                                 key=lambda x: x.value).name if self.dimensions else "ADVISORY"
        }
    
    def reset_daily(self):
        """Reset daily counters (call at session rollover)."""
        self.dimensions[Dimension.DAILY_LOSS].current_value = 0
        self.dimensions[Dimension.DAILY_LOSS].level = AlertLevel.ADVISORY
        for c in self.campaigns.values():
            c.entry_count_today = 0
    
    def reset_weekly(self):
        self.dimensions[Dimension.WEEKLY_LOSS].current_value = 0
        self.dimensions[Dimension.WEEKLY_LOSS].level = AlertLevel.ADVISORY
    
    def reset_monthly(self):
        self.dimensions[Dimension.MONTHLY_LOSS].current_value = 0
        self.dimensions[Dimension.MONTHLY_LOSS].level = AlertLevel.ADVISORY


# ============ DEMO / TEST ============
def run_demo():
    """Demonstrate Risk Guardian with simulated scenarios."""
    print("=" * 60)
    print("Risk Guardian — Module 10 Demo")
    print("=" * 60)
    
    rg = RiskGuardian()
    
    # Register campaigns
    rg.register_campaign("PROBE_001", "probe", 10000.0)
    rg.register_campaign("DISC_001", "discretionary", 20000.0)
    
    print("\n[1] Initial state:")
    print(json.dumps(rg.get_status(), indent=2, default=str))
    
    # Simulate daily loss accumulating
    print("\n[2] Simulating daily loss accumulation...")
    for loss in [500, 1000, 1500, 1800, 2000, 2200]:
        rg.update_daily_loss(-loss)
        rg.evaluate_all()
        status = rg.get_status()
        dim = status["dimensions"]["daily_loss"]
        print(f"  Daily loss: ${loss:,} | Level: {dim['level']:10s} | Utilization: {dim['utilization_pct']:.0f}%")
    
    # Simulate campaign drawdown
    print("\n[3] Campaign PROBE_001 drawdown...")
    for equity in [9800, 9500, 9200, 9000, 8800]:
        rg.update_campaign_dd("PROBE_001", equity, 10000)
        rg.evaluate_all()
    
    # Simulate layer stacking
    print("\n[4] Adding layers to PROBE_001...")
    for i in range(4):
        success, msg = rg.record_entry("PROBE_001")
        print(f"  Layer {i+1}: {'✓' if success else '✗'} {msg}")
    
    # Simulate exposure concentration
    print("\n[5] High exposure concentration...")
    rg.update_exposure({"XAUUSD": 12000, "EURUSD": 3000}, 20000)
    rg.evaluate_all()
    
    # Final status
    print("\n[6] Final status:")
    print(json.dumps(rg.get_status(), indent=2, default=str))
    
    print("\n" + "=" * 60)
    print("Demo complete. Risk Guardian ready for integration.")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()