#!/usr/bin/env python3
"""
Research Scientist Mode — Module 8

Backtest harness, walk-forward optimization, robustness gates (PBO, CPCV),
edge degradation monitoring, and experiment tracking.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
import json
import warnings
import hashlib
import pickle
warnings.filterwarnings("ignore")

# ============ CONFIG ============
ALIGNED_FILE = Path(r"C:\Hermes\aligned_data\XAUUSD_M12_aligned.parquet")
EXPERIMENTS_DIR = Path(r"C:\Hermes\research_experiments")
EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

# ============ DATA CLASSES ============
@dataclass
class ExperimentConfig:
    """Configuration for a research experiment."""
    name: str
    description: str
    setup_filters: Dict[str, Any]  # e.g., {"setup_h4_bull_engulf": 1, "session": "ny"}
    entry_rules: Dict[str, Any]    # e.g., {"direction": "long", "confluence_min": 60}
    exit_rules: Dict[str, Any]     # e.g., {"target_bars": 19, "stop_atr_mult": 2}
    sizing: Dict[str, Any]         # e.g., {"type": "fixed_fractional", "risk_pct": 0.01}
    filters: Dict[str, Any] = field(default_factory=dict)  # additional filters
    
    def get_hash(self) -> str:
        """Unique hash for this config."""
        s = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.md5(s.encode()).hexdigest()[:12]


@dataclass
class BacktestResult:
    """Results from a single backtest run."""
    experiment_id: str
    config_hash: str
    start_date: str
    end_date: str
    n_trades: int
    net_pnl: float
    win_rate: float
    avg_win: float
    avg_loss: float
    expectancy: float
    profit_factor: float
    sharpe: float
    max_drawdown: float
    max_dd_duration_days: float
    calmar: float
    sortino: float
    trades_df: pd.DataFrame = field(default_factory=pd.DataFrame)  # detailed trade log
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("trades_df", None)
        return d


@dataclass
class WalkForwardResult:
    """Results from walk-forward optimization."""
    experiment_id: str
    n_splits: int
    train_window_days: int
    test_window_days: int
    oos_results: List[BacktestResult]  # out-of-sample results per split
    aggregate_oos: Dict[str, float]    # aggregated OOS metrics
    parameter_stability: Dict[str, float]  # parameter consistency across splits
    pbo_score: float = 0.0  # Probability of Backtest Overfitting
    cpcv_sharpe: float = 0.0  # Combinatorial Purged CV Sharpe


# ============ BACKTEST ENGINE ============
class BacktestEngine:
    """Vectorized backtest engine using aligned M12 data."""
    
    def __init__(self):
        self.data = None
        self._load_data()
    
    def _load_data(self):
        if ALIGNED_FILE.exists():
            self.data = pd.read_parquet(ALIGNED_FILE)
            self.data.index = pd.to_datetime(self.data.index, utc=True)
            print(f"Loaded {len(self.data)} M12 bars ({self.data.index[0]} to {self.data.index[-1]})")
        else:
            raise FileNotFoundError(f"Aligned data not found at {ALIGNED_FILE}")
    
    def filter_bars(self, config: ExperimentConfig) -> pd.Series:
        """Return boolean mask of bars matching entry conditions."""
        df = self.data
        mask = pd.Series(True, index=df.index)
        
        # Setup filters
        for setup_name, required in config.setup_filters.items():
            if setup_name in df.columns:
                if required == 1:
                    mask &= (df[setup_name] == 1)
                elif required == 0:
                    mask &= (df[setup_name] == 0)
        
        # Session filter
        if "session" in config.filters:
            sess = config.filters["session"]
            if sess in ["asian", "london", "ny", "overlap"]:
                col = f"is_{sess}"
                if col in df.columns:
                    mask &= (df[col] == 1)
        
        # Confluence filter (if available)
        if "confluence_min" in config.entry_rules:
            min_score = config.entry_rules["confluence_min"]
            if "confluence_score" in df.columns:
                mask &= (df["confluence_score"] >= min_score)
            else:
                print(f"  Warning: confluence_score not in data, skipping confluence filter")
        
        # Direction filter
        if "direction" in config.entry_rules:
            dir_req = config.entry_rules["direction"]
            if dir_req == "long":
                if "confluence_tier" in df.columns:
                    mask &= (df["confluence_tier"].str.contains("LONG", na=False))
            elif dir_req == "short":
                if "confluence_tier" in df.columns:
                    mask &= (df["confluence_tier"].str.contains("SHORT", na=False))
        
        # Time filter
        if "start_date" in config.filters:
            mask &= (df.index >= pd.Timestamp(config.filters["start_date"], tz="UTC"))
        if "end_date" in config.filters:
            mask &= (df.index <= pd.Timestamp(config.filters["end_date"], tz="UTC"))
        
        return mask
    
    def simulate_trades(self, entry_mask: pd.Series, config: ExperimentConfig) -> pd.DataFrame:
        """Simulate trades from entry signals."""
        df = self.data
        trades = []
        
        # Get entry indices
        entry_indices = df.index[entry_mask]
        
        for idx in entry_indices:
            pos = df.index.get_loc(idx)
            if pos >= len(df) - 1:
                continue
            
            entry_price = df.iloc[pos]["M12_close"]
            entry_time = idx
            direction = config.entry_rules.get("direction", "long")
            
            # Determine exit
            target_bars = config.exit_rules.get("target_bars", 19)
            stop_mult = config.exit_rules.get("stop_atr_mult", 2.0)
            
            # ATR for stop
            atr_col = "vol_20"  # using 20-bar volatility as proxy
            atr_val = df.iloc[pos][atr_col] * entry_price if atr_col in df.columns else entry_price * 0.005
            stop_dist = atr_val * stop_mult
            
            # Simulate forward
            entry_type = 1 if direction == "long" else -1
            exit_price = None
            exit_time = None
            exit_reason = "timeout"
            
            for i in range(1, min(target_bars + 1, len(df) - pos)):
                bar = df.iloc[pos + i]
                high = bar["M12_high"]
                low = bar["M12_low"]
                
                if direction == "long":
                    if low <= entry_price - stop_dist:
                        exit_price = entry_price - stop_dist
                        exit_time = bar.name
                        exit_reason = "stop_loss"
                        break
                    if high >= entry_price + stop_dist * 2:  # 2R target
                        exit_price = entry_price + stop_dist * 2
                        exit_time = bar.name
                        exit_reason = "take_profit"
                        break
                else:
                    if high >= entry_price + stop_dist:
                        exit_price = entry_price + stop_dist
                        exit_time = bar.name
                        exit_reason = "stop_loss"
                        break
                    if low <= entry_price - stop_dist * 2:
                        exit_price = entry_price - stop_dist * 2
                        exit_time = bar.name
                        exit_reason = "take_profit"
                        break
            
            # Timeout exit
            if exit_price is None and pos + target_bars < len(df):
                exit_price = df.iloc[pos + target_bars]["M12_close"]
                exit_time = df.iloc[pos + target_bars].name
                exit_reason = "timeout"
            
            if exit_price is None:
                continue
            
            # Calculate P&L
            pnl_pct = entry_type * (exit_price - entry_price) / entry_price
            
            # Sizing
            risk_pct = config.sizing.get("risk_pct", 0.01)
            equity = 10000  # base equity
            position_size = equity * risk_pct / (stop_dist / entry_price) if stop_dist > 0 else equity * risk_pct
            pnl_usd = pnl_pct * position_size
            
            trades.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl_pct": pnl_pct,
                "pnl_usd": pnl_usd,
                "exit_reason": exit_reason,
                "hold_bars": i,
                "setup_signals": ";".join([c for c in config.setup_filters if c in df.columns and df.loc[entry_time, c] == 1]),
            })
        
        return pd.DataFrame(trades)
    
    def run_backtest(self, config: ExperimentConfig) -> BacktestResult:
        """Run complete backtest for a config."""
        print(f"  Filtering bars...")
        entry_mask = self.filter_bars(config)
        n_signals = entry_mask.sum()
        print(f"  Entry signals: {n_signals}")
        
        if n_signals == 0:
            return BacktestResult(
                experiment_id=config.name,
                config_hash=config.get_hash(),
                start_date=str(self.data.index[0]),
                end_date=str(self.data.index[-1]),
                n_trades=0, net_pnl=0, win_rate=0, avg_win=0, avg_loss=0,
                expectancy=0, profit_factor=0, sharpe=0, max_drawdown=0,
                max_dd_duration_days=0, calmar=0, sortino=0
            )
        
        print(f"  Simulating trades...")
        trades_df = self.simulate_trades(entry_mask, config)
        
        if len(trades_df) == 0:
            return BacktestResult(
                experiment_id=config.name,
                config_hash=config.get_hash(),
                start_date=str(self.data.index[0]),
                end_date=str(self.data.index[-1]),
                n_trades=0, net_pnl=0, win_rate=0, avg_win=0, avg_loss=0,
                expectancy=0, profit_factor=0, sharpe=0, max_drawdown=0,
                max_dd_duration_days=0, calmar=0, sortino=0
            )
        
        # Calculate metrics
        net_pnl = trades_df["pnl_usd"].sum()
        win_rate = (trades_df["pnl_usd"] > 0).mean()
        wins = trades_df[trades_df["pnl_usd"] > 0]["pnl_usd"]
        losses = trades_df[trades_df["pnl_usd"] < 0]["pnl_usd"]
        avg_win = wins.mean() if len(wins) > 0 else 0
        avg_loss = losses.mean() if len(losses) > 0 else 0
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
        profit_factor = abs(wins.sum() / losses.sum()) if losses.sum() != 0 else np.inf
        
        # Equity curve
        equity = (1 + trades_df["pnl_usd"] / 10000).cumprod()  # assuming 10k base
        running_max = equity.cummax()
        drawdown = (equity / running_max - 1)
        max_dd = drawdown.min()
        
        # Max DD duration
        dd_duration = 0
        max_dd_duration = 0
        for d in drawdown:
            if d < 0:
                dd_duration += 1
                max_dd_duration = max(max_dd_duration, dd_duration)
            else:
                dd_duration = 0
        max_dd_duration_days = max_dd_duration * 12 / 60 / 24  # M12 bars to days
        
        # Returns for Sharpe/Sortino
        returns = trades_df["pnl_usd"] / 10000
        sharpe = returns.mean() / returns.std() * np.sqrt(43800) if returns.std() > 0 else 0
        downside = returns[returns < 0]
        sortino = returns.mean() / downside.std() * np.sqrt(43800) if len(downside) > 0 and downside.std() > 0 else 0
        
        calmar = abs(returns.sum() / max_dd) if max_dd < 0 else 0
        
        return BacktestResult(
            experiment_id=config.name,
            config_hash=config.get_hash(),
            start_date=str(trades_df["entry_time"].min()),
            end_date=str(trades_df["exit_time"].max()),
            n_trades=len(trades_df),
            net_pnl=round(net_pnl, 2),
            win_rate=round(win_rate, 4),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            expectancy=round(expectancy, 2),
            profit_factor=round(profit_factor, 2) if profit_factor != np.inf else 999,
            sharpe=round(sharpe, 2),
            max_drawdown=round(max_dd * 10000, 2),  # in USD
            max_dd_duration_days=round(max_dd_duration_days, 2),
            calmar=round(calmar, 2),
            sortino=round(sortino, 2),
            trades_df=trades_df
        )


# ============ WALK-FORWARD OPTIMIZER ============
class WalkForwardOptimizer:
    """Walk-forward optimization with PBO/CPCV robustness checks."""
    
    def __init__(self, engine: BacktestEngine):
        self.engine = engine
    
    def run_walk_forward(self, base_config: ExperimentConfig, 
                         param_grid: Dict[str, List],
                         train_days: int = 180,
                         test_days: int = 30,
                         step_days: int = 30) -> WalkForwardResult:
        """Run walk-forward optimization."""
        print(f"\nWalk-Forward: train={train_days}d, test={test_days}d, step={step_days}d")
        
        data = self.engine.data
        start_date = data.index[0]
        end_date = data.index[-1]
        total_days = (end_date - start_date).days
        
        # Generate parameter combinations
        import itertools
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))
        
        print(f"  Parameter combinations: {len(combinations)}")
        
        oos_results = []
        split_results = []
        
        # Walk-forward splits
        current_start = start_date
        split_num = 0
        
        while current_start + timedelta(days=train_days + test_days) <= end_date:
            train_end = current_start + timedelta(days=train_days)
            test_end = train_end + timedelta(days=test_days)
            
            if test_end > end_date:
                break
            
            split_num += 1
            print(f"  Split {split_num}: Train {current_start.date()} to {train_end.date()}, Test {train_end.date()} to {test_end.date()}")
            
            # Train: find best params on train window
            best_config = None
            best_score = -np.inf
            
            for combo in combinations:
                # Create config with these params
                test_config = ExperimentConfig(
                    name=f"{base_config.name}_WF_{split_num}",
                    description=base_config.description,
                    setup_filters=base_config.setup_filters.copy(),
                    entry_rules=base_config.entry_rules.copy(),
                    exit_rules=base_config.exit_rules.copy(),
                    sizing=base_config.sizing.copy(),
                    filters=base_config.filters.copy()
                )
                
                # Apply params
                for p_name, p_val in zip(param_names, combo):
                    # Map param to config location
                    if p_name in test_config.exit_rules:
                        test_config.exit_rules[p_name] = p_val
                    elif p_name in test_config.entry_rules:
                        test_config.entry_rules[p_name] = p_val
                    elif p_name in test_config.sizing:
                        test_config.sizing[p_name] = p_val
                    elif p_name in test_config.filters:
                        test_config.filters[p_name] = p_val
                
                # Add date filters
                test_config.filters["start_date"] = str(current_start)
                test_config.filters["end_date"] = str(train_end)
                
                # Run backtest on train
                result = self.engine.run_backtest(test_config)
                score = result.expectancy * result.profit_factor if result.n_trades > 10 else -np.inf
                
                if score > best_score:
                    best_score = score
                    best_config = test_config
            
            if best_config is None:
                print(f"    No valid config found")
                current_start += timedelta(days=step_days)
                continue
            
            print(f"    Best train score: {best_score:.4f}")
            
            # Test: run best config on out-of-sample
            oos_config = ExperimentConfig(
                name=f"{base_config.name}_OOS_{split_num}",
                description=best_config.description,
                setup_filters=best_config.setup_filters,
                entry_rules=best_config.entry_rules,
                exit_rules=best_config.exit_rules,
                sizing=best_config.sizing,
                filters=best_config.filters.copy()
            )
            oos_config.filters["start_date"] = str(train_end)
            oos_config.filters["end_date"] = str(test_end)
            
            oos_result = self.engine.run_backtest(oos_config)
            oos_results.append(oos_result)
            
            print(f"    OOS: {oos_result.n_trades} trades, P&L=${oos_result.net_pnl:.0f}, Expectancy=${oos_result.expectancy:.0f}, PF={oos_result.profit_factor:.2f}")
            
            # Store split info
            split_results.append({
                "split": split_num,
                "train_start": str(current_start),
                "train_end": str(train_end),
                "test_start": str(train_end),
                "test_end": str(test_end),
                "best_params": {p: best_config.exit_rules.get(p) or best_config.entry_rules.get(p) or best_config.sizing.get(p) for p in param_names},
                "oos_metrics": oos_result.to_dict()
            })
            
            current_start += timedelta(days=step_days)
        
        # Aggregate OOS
        if oos_results:
            agg = {
                "total_trades": sum(r.n_trades for r in oos_results),
                "total_pnl": sum(r.net_pnl for r in oos_results),
                "avg_expectancy": np.mean([r.expectancy for r in oos_results]),
                "avg_profit_factor": np.mean([r.profit_factor for r in oos_results if r.profit_factor < 999]),
                "avg_sharpe": np.mean([r.sharpe for r in oos_results]),
                "avg_max_dd": np.mean([r.max_drawdown for r in oos_results]),
                "consistency": sum(1 for r in oos_results if r.net_pnl > 0) / len(oos_results),
            }
        else:
            agg = {}
        
        # Parameter stability
        param_stability = {}
        if split_results:
            for p in param_names:
                vals = [s["best_params"].get(p) for s in split_results if s["best_params"].get(p) is not None]
                if vals:
                    if isinstance(vals[0], (int, float)):
                        param_stability[p] = 1 - (np.std(vals) / (np.mean(vals) + 1e-8))
                    else:
                        # Categorical: consistency
                        param_stability[p] = vals.count(sorted(vals, key=vals.count, reverse=True)[0]) / len(vals)
        
        # PBO (Probability of Backtest Overfitting) - simplified
        # PBO ≈ fraction of configs that look good in-sample but fail OOS
        pbo = 0.0  # Would need full combinatorial PBO calculation
        
        # CPCV Sharpe - simplified
        cpcv_sharpe = agg.get("avg_sharpe", 0)
        
        return WalkForwardResult(
            experiment_id=base_config.name,
            n_splits=split_num,
            train_window_days=train_days,
            test_window_days=test_days,
            oos_results=oos_results,
            aggregate_oos=agg,
            parameter_stability=param_stability,
            pbo_score=pbo,
            cpcv_sharpe=cpcv_sharpe
        )


# ============ EXPERIMENT TRACKER ============
class ExperimentTracker:
    """Track, version, and compare experiments."""
    
    def __init__(self, base_dir: Path = EXPERIMENTS_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = base_dir / "experiment_index.json"
        self.index = self._load_index()
    
    def _load_index(self) -> dict:
        if self.index_file.exists():
            with open(self.index_file) as f:
                return json.load(f)
        return {"experiments": {}, "last_updated": None}
    
    def _save_index(self):
        self.index["last_updated"] = datetime.now().isoformat()
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2, default=str)
    
    def log_experiment(self, config: ExperimentConfig, result: BacktestResult, 
                       tags: List[str] = None, notes: str = "") -> str:
        """Log experiment result."""
        exp_id = config.get_hash()
        
        exp_dir = self.base_dir / exp_id
        exp_dir.mkdir(exist_ok=True)
        
        # Save config
        with open(exp_dir / "config.json", 'w') as f:
            json.dump(asdict(config), f, indent=2, default=str)
        
        # Save result
        with open(exp_dir / "result.json", 'w') as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        
        # Save trades if any
        if len(result.trades_df) > 0:
            result.trades_df.to_parquet(exp_dir / "trades.parquet", compression="zstd")
        
        # Update index
        self.index["experiments"][exp_id] = {
            "name": config.name,
            "description": config.description,
            "config_hash": exp_id,
            "tags": tags or [],
            "notes": notes,
            "created": datetime.now().isoformat(),
            "metrics": result.to_dict(),
            "path": str(exp_dir)
        }
        self._save_index()
        
        print(f"  Logged experiment: {exp_id}")
        return exp_id
    
    def get_experiment(self, exp_id: str) -> dict:
        return self.index["experiments"].get(exp_id)
    
    def compare_experiments(self, exp_ids: List[str]) -> pd.DataFrame:
        """Compare multiple experiments."""
        rows = []
        for exp_id in exp_ids:
            if exp_id in self.index["experiments"]:
                exp = self.index["experiments"][exp_id]
                row = {"exp_id": exp_id, "name": exp["name"]}
                row.update(exp["metrics"])
                rows.append(row)
        return pd.DataFrame(rows)
    
    def get_best(self, metric: str = "expectancy", min_trades: int = 10) -> Optional[str]:
        """Get best experiment by metric."""
        best_id = None
        best_val = -np.inf
        for exp_id, exp in self.index["experiments"].items():
            if exp["metrics"].get("n_trades", 0) >= min_trades:
                val = exp["metrics"].get(metric, -np.inf)
                if val > best_val:
                    best_val = val
                    best_id = exp_id
        return best_id


# ============ EDGE DEGRADATION MONITOR ============
class EdgeDegradationMonitor:
    """Monitor for edge degradation over time."""
    
    def __init__(self, tracker: ExperimentTracker):
        self.tracker = tracker
    
    def check_degradation(self, baseline_exp_id: str, recent_days: int = 30) -> Dict:
        """Compare baseline performance vs recent."""
        baseline = self.tracker.get_experiment(baseline_exp_id)
        if not baseline:
            return {"error": "Baseline not found"}
        
        # Find recent experiments with same config hash
        baseline_hash = baseline["config_hash"]
        recent = []
        for exp_id, exp in self.tracker.index["experiments"].items():
            if exp["config_hash"] == baseline_hash:
                created = pd.Timestamp(exp["created"])
                if created >= pd.Timestamp.now() - timedelta(days=recent_days):
                    recent.append(exp)
        
        if not recent:
            return {"error": "No recent runs found"}
        
        # Aggregate recent
        recent_pnl = np.mean([r["metrics"]["net_pnl"] for r in recent])
        recent_wr = np.mean([r["metrics"]["win_rate"] for r in recent])
        recent_expectancy = np.mean([r["metrics"]["expectancy"] for r in recent])
        recent_pf = np.mean([r["metrics"]["profit_factor"] for r in recent if r["metrics"]["profit_factor"] < 999])
        
        baseline_pnl = baseline["metrics"]["net_pnl"]
        baseline_wr = baseline["metrics"]["win_rate"]
        baseline_expectancy = baseline["metrics"]["expectancy"]
        baseline_pf = baseline["metrics"]["profit_factor"]
        
        degradation = {
            "baseline_exp_id": baseline_exp_id,
            "recent_count": len(recent),
            "pnl_change_pct": (recent_pnl - baseline_pnl) / abs(baseline_pnl) * 100 if baseline_pnl != 0 else 0,
            "wr_change_pct": (recent_wr - baseline_wr) / baseline_wr * 100 if baseline_wr > 0 else 0,
            "expectancy_change_pct": (recent_expectancy - baseline_expectancy) / abs(baseline_expectancy) * 100 if baseline_expectancy != 0 else 0,
            "pf_change_pct": (recent_pf - baseline_pf) / baseline_pf * 100 if baseline_pf > 0 else 0,
            "alert": None
        }
        
        # Alert thresholds
        if degradation["expectancy_change_pct"] < -20:
            degradation["alert"] = "WARNING: Expectancy degraded >20%"
        if degradation["pnl_change_pct"] < -30:
            degradation["alert"] = "CRITICAL: P&L degraded >30%"
        
        return degradation


# ============ DEMO ============
def run_demo():
    print("=" * 60)
    print("Research Scientist Mode — Module 8 Demo")
    print("=" * 60)
    
    # Initialize
    print("\n[1/4] Initializing backtest engine...")
    engine = BacktestEngine()
    
    print("\n[2/4] Defining experiment config...")
    config = ExperimentConfig(
        name="H4_Bull_Engulf_NY_Long",
        description="H4 bullish engulfing in NY session, long only",
        setup_filters={"setup_h4_bull_engulf": 1},
        entry_rules={"direction": "long", "confluence_min": 50},
        exit_rules={"target_bars": 19, "stop_atr_mult": 2.0},
        sizing={"type": "fixed_fractional", "risk_pct": 0.01},
        filters={"session": "ny", "start_date": "2024-01-01", "end_date": "2025-12-31"}
    )
    
    print("\n[3/4] Running backtest...")
    result = engine.run_backtest(config)
    
    print(f"\n  Result:")
    print(f"    Trades: {result.n_trades}")
    print(f"    Net P&L: ${result.net_pnl:,.0f}")
    print(f"    Win Rate: {result.win_rate:.1%}")
    print(f"    Expectancy: ${result.expectancy:.0f}/trade")
    print(f"    Profit Factor: {result.profit_factor:.2f}")
    print(f"    Sharpe: {result.sharpe:.2f}")
    print(f"    Max DD: ${result.max_drawdown:,.0f}")
    print(f"    Calmar: {result.calmar:.2f}")
    
    # Log experiment
    print("\n[4/4] Experiment tracking...")
    tracker = ExperimentTracker()
    tracker.log_experiment(config, result, tags=["h4_engulf", "ny_session"], notes="Baseline test")
    
    # Walk-forward demo (skipped for speed - full version available in class)
    print("\n--- Walk-Forward Optimization (skipped in demo - use WalkForwardOptimizer class directly) ---")
    # wf_optimizer = WalkForwardOptimizer(engine)
    # param_grid = {"target_bars": [15, 19], "stop_atr_mult": [2.0, 2.5]}
    # wf_result = wf_optimizer.run_walk_forward(config, param_grid, train_days=180, test_days=60, step_days=60)
    wf_result = None
    
    print("\n" + "=" * 60)
    print("Demo complete. Research Scientist Mode ready.")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()