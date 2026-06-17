#!/usr/bin/env python3
"""
FastAPI server for Hermes Trading Office PWA.
Provides REST endpoints + WebSocket for live data.
"""
import asyncio
import io
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import boto3
import pandas as pd
from botocore.config import Config as BotoConfig
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configuration
API_KEY = os.getenv("HERMES_API_KEY", "hermes-trading-office-2024")
DATA_ROOT = Path(__file__).parent.parent
STATIC_DIR = Path(__file__).parent

# R2 Configuration
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID") or os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY") or os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET", "hermes-pipeline")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")

r2_client = None
if R2_ACCOUNT_ID and R2_ACCESS_KEY and R2_SECRET_KEY:
    try:
        r2_client = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto"
        )
        print(f"R2 client initialized: {R2_ACCOUNT_ID}.r2.cloudflarestorage.com/{R2_BUCKET}")
    except Exception as e:
        print(f"R2 client init failed: {e}")
        r2_client = None
else:
    print("R2 credentials not set, using local filesystem fallback")

app = FastAPI(
    title="Hermes Trading Office API",
    description="REST + WebSocket API for 24/7 Campaign Intelligence Dashboard",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                pass

manager = ConnectionManager()

async def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

async def read_r2_parquet(key: str) -> Optional["pd.DataFrame"]:
    if not r2_client:
        return None
    try:
        response = r2_client.get_object(Bucket=R2_BUCKET, Key=key)
        return pd.read_parquet(io.BytesIO(response["Body"].read()))
    except Exception as e:
        print(f"R2 read parquet failed for {key}: {e}")
        return None

async def read_r2_csv(key: str) -> Optional["pd.DataFrame"]:
    if not r2_client:
        return None
    try:
        response = r2_client.get_object(Bucket=R2_BUCKET, Key=key)
        return pd.read_csv(io.BytesIO(response["Body"].read()))
    except Exception as e:
        print(f"R2 read csv failed for {key}: {e}")
        return None

async def read_r2_json(key: str) -> Optional[Dict]:
    if not r2_client:
        return None
    try:
        response = r2_client.get_object(Bucket=R2_BUCKET, Key=key)
        return json.loads(response["Body"].read().decode("utf-8"))
    except Exception as e:
        print(f"R2 read json failed for {key}: {e}")
        return None

async def read_r2_file_age(key: str) -> Optional[float]:
    if not r2_client:
        return None
    try:
        response = r2_client.head_object(Bucket=R2_BUCKET, Key=key)
        last_modified = response.get("LastModified")
        if last_modified:
            return time.time() - last_modified.timestamp()
    except Exception:
        pass
    return None


def read_mt5_pnl() -> Optional[Dict]:
    try:
        pnl_path = DATA_ROOT / "live_pnl.json"
        if pnl_path.exists():
            with open(pnl_path) as f:
                return json.load(f)
        return None
    except Exception:
        return None

def read_mt5_positions() -> List[Dict]:
    return []

@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat() + "Z"}

@app.get("/api/v1/debug/r2")
async def debug_r2(_: bool = Depends(verify_api_key)):
    return {
        "r2_client_initialized": r2_client is not None,
        "env_vars": {
            "R2_ACCOUNT_ID": bool(os.getenv("R2_ACCOUNT_ID")),
            "R2_ACCESS_KEY_ID": bool(os.getenv("R2_ACCESS_KEY_ID")),
            "R2_ACCESS_KEY": bool(os.getenv("R2_ACCESS_KEY")),
            "R2_SECRET_ACCESS_KEY": bool(os.getenv("R2_SECRET_ACCESS_KEY")),
            "R2_SECRET_KEY": bool(os.getenv("R2_SECRET_KEY")),
            "R2_BUCKET": os.getenv("R2_BUCKET"),
        },
        "resolved": {
            "account_id": os.getenv("R2_ACCOUNT_ID"),
            "access_key": os.getenv("R2_ACCESS_KEY_ID") or os.getenv("R2_ACCESS_KEY"),
            "secret_key": "***" if (os.getenv("R2_SECRET_ACCESS_KEY") or os.getenv("R2_SECRET_KEY")) else None,
            "bucket": os.getenv("R2_BUCKET"),
        }
    }

@app.get("/api/v1/debug/r2-read")
async def debug_r2_read(key: str = "confluence_score/XAUUSD_confluence_score.parquet", _: bool = Depends(verify_api_key)):
    if not r2_client:
        return {"error": "R2 client not initialized"}
    try:
        response = r2_client.get_object(Bucket=R2_BUCKET, Key=key)
        body = response["Body"].read()
        return {
            "key": key,
            "size": len(body),
            "content_type": response.get("ContentType"),
            "last_modified": str(response.get("LastModified")),
            "first_100_bytes": body[:100].hex() if body else None
        }
    except Exception as e:
        return {"key": key, "error": str(e), "type": type(e).__name__}

@app.get("/api/v1/debug/pyarrow")
async def debug_pyarrow(_: bool = Depends(verify_api_key)):
    try:
        import pyarrow
        import pyarrow.parquet as pq
        pyarrow_ok = True
        pyarrow_version = pyarrow.__version__
    except Exception as e:
        pyarrow_ok = False
        pyarrow_version = str(e)

    try:
        import pandas as pd
        pandas_ok = True
        pandas_version = pd.__version__
    except Exception as e:
        pandas_ok = False
        pandas_version = str(e)

    try:
        import io
        response = r2_client.get_object(Bucket=R2_BUCKET, Key="confluence_score/XAUUSD_confluence_score.parquet")
        body = response["Body"].read()
        df = pd.read_parquet(io.BytesIO(body))
        parquet_read_ok = True
        parquet_shape = str(df.shape)
        parquet_cols = list(df.columns)[:5]
    except Exception as e:
        parquet_read_ok = False
        parquet_shape = str(e)
        parquet_cols = []

    return {
        "pyarrow": {"ok": pyarrow_ok, "version": pyarrow_version},
        "pandas": {"ok": pandas_ok, "version": pandas_version},
        "parquet_read": {"ok": parquet_read_ok, "shape": parquet_shape, "cols": parquet_cols},
        "r2_client": r2_client is not None
    }


@app.get("/api/v1/system/health")
async def system_health(_: bool = Depends(verify_api_key)):
    checks = {
        "pipeline": {"status": "unknown", "details": {}},
        "data_freshness": {},
        "cron_jobs": {},
        "mt5_export": None
    }

    key_files = {
        "confluence_score": "confluence_score/XAUUSD_confluence_score.parquet",
        "setups": "edge_discovery/XAUUSD_setup_labels.parquet",
        "behaviour": "behaviour_analysis/outputs/behaviour_summary.json",
        "aligned": "aligned_data/XAUUSD_M12_aligned.parquet",
        "risk_guardian": "risk_guardian/state.json",
    }

    max_age = 0
    stale_files = []
    for name, key in key_files.items():
        age = None
        if r2_client:
            try:
                age = await read_r2_file_age(key)
            except Exception:
                pass
        if age is None:
            path = DATA_ROOT / key
            age = get_file_age(path)

        if age is not None:
            checks["data_freshness"][name] = {
                "age_seconds": round(age),
                "age_human": f"{round(age/60)} min ago" if age < 3600 else f"{round(age/3600)} hrs ago",
                "stale": age > 1800
            }
            max_age = max(max_age, age)
            if age > 1800:
                stale_files.append(name)
        else:
            checks["data_freshness"][name] = {"status": "missing"}
            stale_files.append(name)

    if not stale_files:
        checks["pipeline"]["status"] = "healthy"
    elif len(stale_files) <= 2:
        checks["pipeline"]["status"] = "degraded"
    else:
        checks["pipeline"]["status"] = "down"

    mt5_files = list((DATA_ROOT / "mt5_data_full").glob("*.parquet"))
    if mt5_files:
        mt5_age = min(get_file_age(f) for f in mt5_files)
        checks["mt5_export"] = {
            "age_seconds": round(mt5_age) if mt5_age else None,
            "files": len(mt5_files),
            "stale": mt5_age > 86400 if mt5_age else True
        }

    return checks

@app.get("/api/v1/confluence")
async def get_confluence(_: bool = Depends(verify_api_key)):
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    logger.debug("=== ENTERING get_confluence endpoint ===")
    try:
        # Try R2 first
        df = None
        if r2_client:
            try:
                import io
                response = r2_client.get_object(Bucket=R2_BUCKET, Key="confluence_score/XAUUSD_confluence_score.parquet")
                body = response["Body"].read()
                df = pd.read_parquet(io.BytesIO(body))
                logger.debug(f"Read from R2: {df.shape}")
            except Exception as e:
                logger.debug(f"R2 read failed: {e}")
        
        # Fallback to local
        if df is None or df.empty:
            path = DATA_ROOT / "confluence_score" / "XAUUSD_confluence_score.parquet"
            logger.debug(f"Confluence path: {path}")
            logger.debug(f"Path exists: {path.exists()}")
            df = read_parquet_safe(path)
            logger.debug(f"read_parquet_safe returned: {df is not None}")

        if df is None or df.empty:
            logger.debug("Returning mock data")
            return {
                "score": 87.0,
                "tier": "STRONG_LONG",
                "confidence": 0.87,
                "active_setups": ["H1 MOMENTUM", "H4 REVERSION"],
                "components": {
                    "trend_alignment": 0.82,
                    "volatility_regime": 0.75,
                    "session_favorability": 0.91,
                    "structure_score": 0.88
                },
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "mock": True
            }

        latest = df.iloc[-1]
        return {
            "score": float(latest.get("confluence_score", 0)),
            "tier": str(latest.get("tier", "NEUTRAL")),
            "confidence": float(latest.get("confidence", 0)),
            "active_setups": str(latest.get("active_setups", "")).split(";") if latest.get("active_setups") else [],
            "components": {
                "trend_alignment": float(latest.get("trend_alignment", 0)),
                "volatility_regime": float(latest.get("volatility_regime", 0)),
                "session_favorability": float(latest.get("session_favorability", 0)),
                "structure_score": float(latest.get("structure_score", 0)),
            },
            "timestamp": str(latest.name) if hasattr(latest, 'name') else datetime.utcnow().isoformat(),
            "mock": False
        }
    except Exception as e:
        logger.error(f"Exception in get_confluence: {e}", exc_info=True)
        raise

@app.get("/api/v1/setups")
async def get_setups(limit: int = 50, _: bool = Depends(verify_api_key)):
    # Try R2 first
    df = None
    if r2_client:
        try:
            import io
            response = r2_client.get_object(Bucket=R2_BUCKET, Key="edge_discovery/XAUUSD_setup_labels.parquet")
            body = response["Body"].read()
            df = pd.read_parquet(io.BytesIO(body))
        except Exception:
            pass

    # Fallback to local
    if df is None or df.empty:
        path = DATA_ROOT / "edge_discovery" / "XAUUSD_setup_labels.parquet"
        df = read_parquet_safe(path)

    if df is None or df.empty:
        return {
            "setups": [
                {"timestamp": (datetime.utcnow() - timedelta(minutes=i*15)).isoformat() + "Z",
                 "setup_name": "H1 MOMENTUM", "direction": "LONG",
                 "fwd_return_5m": 0.12, "fwd_return_15m": 0.28, "fwd_return_30m": 0.45,
                 "confluence_score": 87, "regime": "TRENDING", "session": "LONDON"}
                for i in range(min(limit, 20))
            ],
            "count": min(limit, 20),
            "mock": True
        }

    recent = df.tail(limit)
    setups = []
    for _, row in recent.iterrows():
        setups.append({
            "timestamp": str(row.name) if hasattr(row, 'name') else str(row.get("timestamp", "")),
            "setup_name": str(row.get("setup_name", "")),
            "direction": str(row.get("direction", "")),
            "fwd_return_5m": float(row.get("fwd_return_5m", 0)),
            "fwd_return_15m": float(row.get("fwd_return_15m", 0)),
            "fwd_return_30m": float(row.get("fwd_return_30m", 0)),
            "confluence_score": float(row.get("confluence_score", 0)),
            "regime": str(row.get("regime", "")),
            "session": str(row.get("session", ""))
        })
    return {"setups": setups, "count": len(setups)}

@app.get("/api/v1/opportunity-windows")
async def get_opportunity_windows(_: bool = Depends(verify_api_key)):
    stats = {}

    path = DATA_ROOT / "opportunity_windows" / "session_stats.csv"
    df = read_csv_safe(path)
    if df is not None:
        stats["session"] = df.to_dict('records')
    else:
        stats["session"] = [
            {"session": "ASIA", "win_rate": 0.62, "avg_r": 0.45, "count": 142, "expectancy": 0.12},
            {"session": "LONDON", "win_rate": 0.68, "avg_r": 0.67, "count": 289, "expectancy": 0.28},
            {"session": "NY", "win_rate": 0.64, "avg_r": 0.52, "count": 201, "expectancy": 0.19},
            {"session": "OVERLAP", "win_rate": 0.71, "avg_r": 0.82, "count": 156, "expectancy": 0.41}
        ]
        stats["mock"] = True

    path = DATA_ROOT / "opportunity_windows" / "dow_stats.csv"
    df = read_csv_safe(path)
    if df is not None:
        stats["dow"] = df.to_dict('records')
    else:
        stats["dow"] = [
            {"dow": "MONDAY", "win_rate": 0.65, "avg_r": 0.58, "count": 178},
            {"dow": "TUESDAY", "win_rate": 0.67, "avg_r": 0.62, "count": 192},
            {"dow": "WEDNESDAY", "win_rate": 0.66, "avg_r": 0.59, "count": 185},
            {"dow": "THURSDAY", "win_rate": 0.69, "avg_r": 0.71, "count": 203},
            {"dow": "FRIDAY", "win_rate": 0.63, "avg_r": 0.51, "count": 167}
        ]

    path = DATA_ROOT / "opportunity_windows" / "context_stats.csv"
    df = read_csv_safe(path)
    if df is not None:
        stats["context"] = df.to_dict('records')
    else:
        stats["context"] = [
            {"context": "QUIET_TREND", "win_rate": 0.72, "avg_r": 0.78, "count": 145},
            {"context": "ELEVATED_RANGE", "win_rate": 0.68, "avg_r": 0.65, "count": 234},
            {"context": "EXTREME_BREAKOUT", "win_rate": 0.58, "avg_r": 1.12, "count": 89}
        ]

    return stats

@app.get("/api/v1/risk")
async def get_risk(_: bool = Depends(verify_api_key)):
    path = DATA_ROOT / "risk_guardian" / "state.json"
    data = None
    if r2_client:
        try:
            data = await read_r2_json("risk_guardian/state.json")
        except Exception:
            pass
    if data is None and path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            pass

    if data:
        return data

    return {
        "daily_loss_pct": -1.2,
        "daily_limit_pct": -2.5,
        "position_size_pct": 3.4,
        "position_limit_pct": 5.0,
        "correlation": 0.34,
        "correlation_limit": 0.7,
        "drawdown_pct": 2.1,
        "drawdown_limit_pct": 10.0,
        "escalation_level": 0,
        "escalation_ladder": [
            {"level": 1, "name": "WARNING", "threshold": 0.5, "action": "Notify"},
            {"level": 2, "name": "REDUCE", "threshold": 0.75, "action": "Reduce size 50%"},
            {"level": 3, "name": "FLATTEN", "threshold": 0.9, "action": "Close all"},
            {"level": 4, "name": "LOCKDOWN", "threshold": 1.0, "action": "Pause trading"}
        ],
        "campaign_guards": {
            "max_layers": 2,
            "current_layers": 0,
            "basket_dd_limit_r": 1.5,
            "runner_hold_enabled": True,
            "revenge_cooldown_min": 15
        },
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mock": True
    }

@app.get("/api/v1/pnl")
async def get_pnl(_: bool = Depends(verify_api_key)):
    path = DATA_ROOT / "live_pnl.json"
    data = None
    if r2_client:
        try:
            data = await read_r2_json("live_pnl.json")
        except Exception:
            pass
    if data is None and path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            pass

    if data:
        return data

    mt5_pnl = read_mt5_pnl()
    if mt5_pnl:
        return mt5_pnl

    return {
        "net_pnl": 12847.32,
        "realized_pnl": 8234.15,
        "unrealized_pnl": 4613.17,
        "max_drawdown_pct": -2.1,
        "risk_used_pct": 67,
        "daily_pnl": 1247.32,
        "weekly_pnl": 8234.15,
        "monthly_pnl": 28471.32,
        "open_positions": 3,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mock": True
    }

@app.get("/api/v1/sharpe")
async def get_sharpe(_: bool = Depends(verify_api_key)):
    """Calculate Sharpe Ratio from trade history."""
    # Try R2 first, then local
    trades_df = None
    if r2_client:
        try:
            trades_data = await read_r2_json("trading_journal.json")
            if trades_data:
                trades = trades_data.get("trades", [])
                out_trades = [t for t in trades if t.get("entry") == "OUT" and t.get("profit") is not None]
                if out_trades:
                    trades_df = pd.DataFrame(out_trades)
        except Exception:
            pass
    
    if trades_df is None:
        # Fallback to local
        try:
            with open(DATA_ROOT / "trading_journal.json") as f:
                trades_data = json.load(f)
            trades = trades_data.get("trades", [])
            out_trades = [t for t in trades if t.get("entry") == "OUT" and t.get("profit") is not None]
            if out_trades:
                trades_df = pd.DataFrame(out_trades)
        except Exception:
            pass
    
    if trades_df is None or trades_df.empty:
        return {
            "sharpe_ratio": 1.85,
            "sortino_ratio": 2.41,
            "periods_per_year": 252,
            "days_analyzed": 90,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "mock": True
        }
    
    # Calculate returns
    returns = trades_df["profit"].values / 10000.0  # Normalize
    if len(returns) < 2:
        return {"error": "Insufficient trades", "mock": True}
    
    mean_return = np.mean(returns)
    std_return = np.std(returns, ddof=1)
    downside_returns = returns[returns < 0]
    downside_std = np.std(downside_returns, ddof=1) if len(downside_returns) > 1 else std_return
    
    # Annualize (assuming daily trades)
    periods = 252
    sharpe = (mean_return * periods) / (std_return * np.sqrt(periods)) if std_return > 0 else 0
    sortino = (mean_return * periods) / (downside_std * np.sqrt(periods)) if downside_std > 0 else 0
    
    return {
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "mean_daily_return": round(mean_return, 6),
        "volatility": round(std_return, 6),
        "downside_volatility": round(downside_std, 6),
        "total_trades": len(returns),
        "periods_per_year": periods,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mock": False
    }

@app.get("/api/v1/profit-factor")
async def get_profit_factor(_: bool = Depends(verify_api_key)):
    """Calculate Profit Factor from trade history."""
    trades_df = None
    if r2_client:
        try:
            trades_data = await read_r2_json("trading_journal.json")
            if trades_data:
                trades = trades_data.get("trades", [])
                out_trades = [t for t in trades if t.get("entry") == "OUT" and t.get("profit") is not None]
                if out_trades:
                    trades_df = pd.DataFrame(out_trades)
        except Exception:
            pass
    
    if trades_df is None:
        try:
            with open(DATA_ROOT / "trading_journal.json") as f:
                trades_data = json.load(f)
            trades = trades_data.get("trades", [])
            out_trades = [t for t in trades if t.get("entry") == "OUT" and t.get("profit") is not None]
            if out_trades:
                trades_df = pd.DataFrame(out_trades)
        except Exception:
            pass
    
    if trades_df is None or trades_df.empty:
        return {
            "profit_factor": 1.68,
            "gross_profit": 45231.50,
            "gross_loss": -26928.30,
            "net_profit": 18303.20,
            "total_trades": 266,
            "winning_trades": 172,
            "losing_trades": 94,
            "win_rate": 0.647,
            "avg_win": 262.97,
            "avg_loss": -286.47,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "mock": True
        }
    
    profits = trades_df[trades_df["profit"] > 0]["profit"]
    losses = trades_df[trades_df["profit"] <= 0]["profit"]
    
    gross_profit = profits.sum()
    gross_loss = abs(losses.sum())
    net_profit = gross_profit - gross_loss
    
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    return {
        "profit_factor": round(profit_factor, 3),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_profit": round(net_profit, 2),
        "total_trades": len(trades_df),
        "winning_trades": len(profits),
        "losing_trades": len(losses),
        "win_rate": round(len(profits) / len(trades_df), 4),
        "avg_win": round(profits.mean(), 2) if len(profits) > 0 else 0,
        "avg_loss": round(losses.mean(), 2) if len(losses) > 0 else 0,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mock": False
    }


@app.get("/api/v1/journal")
async def get_journal(_: bool = Depends(verify_api_key)):
    """Return today's trade journal stats from trading_journal.json."""
    # Try R2 first, then local
    trades_data = None
    if r2_client:
        try:
            trades_data = await read_r2_json("trading_journal.json")
        except Exception:
            pass
    if trades_data is None:
        try:
            path = DATA_ROOT / "trading_journal.json"
            if path.exists():
                with open(path) as f:
                    trades_data = json.load(f)
        except Exception:
            pass

    if trades_data:
        import re as _re
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        all_trades = trades_data.get("trades", [])

        # Filter today's XAUUSD trades
        today_symbol = [
            t for t in all_trades
            if t.get("symbol") == "XAUUSD"
            and t.get("time", "").startswith(today_str)
        ]
        today_in = [t for t in today_symbol if t.get("entry") == "IN"]
        today_out = [t for t in today_symbol if t.get("entry") == "OUT"]

        today_trades = len(today_out)
        today_wins = sum(1 for t in today_out if t.get("profit", 0) > 0)
        today_losses = sum(1 for t in today_out if t.get("profit", 0) <= 0)
        total_profit = sum(t.get("profit", 0) for t in today_out)
        win_rate = today_wins / today_trades if today_trades > 0 else 0.0
        avg_profit = total_profit / today_trades if today_trades > 0 else 0.0

        # Estimate R as median winning trade profit
        win_profits = [t.get("profit", 0) for t in today_out if t.get("profit", 0) > 0]
        r_estimate = sorted(win_profits)[len(win_profits)//2] if win_profits else 100.0
        avg_exit_r = avg_profit / r_estimate if r_estimate > 0 else 0.0

        # --- NEW: Real computable metrics ---
        tp_trades = 0
        total_slippage = 0.0
        total_pts = 0.0
        hold_times_min = []
        used_ins = set()

        # Match each OUT to its closest prior IN by ticket/time proximity
        for out in sorted(today_out, key=lambda t: t.get("time", "")):
            out_time_str = out.get("time", "")
            out_price = out.get("price", 0) or 0
            out_profit = out.get("profit", 0) or 0

            # Extract TP price from comment
            tp_match = _re.search(r'tp\s*([\d.]+)', out.get("comment", ""))
            tp_price = float(tp_match.group(1)) if tp_match else None

            # Slippage = exit vs TP
            if tp_price and out_price:
                slippage = abs(out_price - tp_price)
            else:
                slippage = 0.0

            # Point gain (for BUY long: exit - entry; for SELL short: entry - exit)
            pts_gained = 0.0

            # Find closest IN before this OUT
            best_in = None
            best_delta = None
            for inn in today_in:
                in_idx = id(inn)
                if in_idx in used_ins:
                    continue
                in_time_str = inn.get("time", "")
                if in_time_str > out_time_str:
                    continue
                try:
                    delta = (datetime.fromisoformat(out_time_str.replace("Z", "+00:00"))
                             - datetime.fromisoformat(in_time_str.replace("Z", "+00:00"))).total_seconds()
                except Exception:
                    delta = None
                if delta is not None and delta > 0 and (best_delta is None or delta < best_delta):
                    best_in = inn
                    best_delta = delta

            if best_in:
                used_ins.add(id(best_in))
                entry_price = best_in.get("price", 0) or 0
                if best_in.get("type") == "BUY":
                    pts_gained = out_price - entry_price
                else:
                    pts_gained = entry_price - out_price
                hold_times_min.append(best_delta / 60.0)
            else:
                pts_gained = abs(out_profit) / 20.0  # fallback: rough estimate

            if tp_price is not None:
                tp_trades += 1
            total_slippage += slippage
            total_pts += max(pts_gained, 0)

        tp_hit_pct = (tp_trades / today_trades * 100.0) if today_trades > 0 else 0.0
        avg_slippage_pts = total_slippage / today_trades if today_trades > 0 else 0.0
        avg_pts = total_pts / today_trades if today_trades > 0 else 0.0
        avg_hold_min = sum(hold_times_min) / len(hold_times_min) if hold_times_min else 0.0

        return {
            "today_trades": today_trades,
            "today_wins": today_wins,
            "today_losses": today_losses,
            "win_rate": round(win_rate, 4),
            "total_profit": round(total_profit, 2),
            "avg_profit": round(avg_profit, 2),
            "avg_entry_r": 0.0,
            "avg_exit_r": round(avg_exit_r, 2),
            "r_estimate": round(r_estimate, 2),
            "tp_hit_pct": round(tp_hit_pct, 1),
            "avg_slippage_pts": round(avg_slippage_pts, 3),
            "avg_hold_time_min": round(avg_hold_min, 1),
            "avg_pts_gained": round(avg_pts, 2),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "mock": False
        }

    # Fallback: no data file
    return {
        "today_trades": 14,
        "today_wins": 9,
        "today_losses": 5,
        "win_rate": 0.643,
        "total_profit": 523.40,
        "avg_profit": 37.39,
        "avg_entry_r": 0.3,
        "avg_exit_r": -0.1,
        "mfe_capture_pct": 72.0,
        "mae_control_pct": 88.0,
        "r_estimate": 100.0,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mock": True
    }


@app.get("/api/v1/campaigns")
async def get_campaigns(_: bool = Depends(verify_api_key)):
    path = DATA_ROOT / "active_campaigns.json"
    data = None
    if r2_client:
        try:
            data = await read_r2_json("active_campaigns.json")
        except Exception:
            pass
    if data is None and path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            pass

    if data:
        return data

    return {
        "active": [
            {"id": "PROBE-234", "type": "probe", "symbol": "XAUUSD", "layers": 2, "pnl_r": 2.4, "status": "active"},
            {"id": "PROBE-235", "type": "probe", "symbol": "XAUUSD", "layers": 1, "pnl_r": 0.8, "status": "active"},
            {"id": "DISCR-089", "type": "discretionary", "symbol": "XAUUSD", "pnl_r": 3.1, "status": "active"},
            {"id": "DISCR-090", "type": "discretionary", "symbol": "XAUUSD", "pnl_r": -0.5, "status": "active"}
        ],
        "closed_today": 14,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mock": True
    }

@app.get("/api/v1/behaviour")
async def get_behaviour(_: bool = Depends(verify_api_key)):
    path = DATA_ROOT / "behaviour_analysis" / "outputs" / "behaviour_summary.json"
    data = None
    if r2_client:
        try:
            data = await read_r2_json("behaviour_analysis/outputs/behaviour_summary.json")
        except Exception:
            pass
    if data is None and path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            pass

    if data:
        return data

    return {
        "session_bias": {"best": "London/NY", "worst": "Asian"},
        "campaign_type": {"probe": 0.6, "discretionary": 1.4},
        "exit_tendency": "cuts_winners_early",
        "runner_impact": "+0.3R",
        "optimal_layers": 2,
        "optimal_adds": 2,
        "risk_consistency": 0.92,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mock": True
    }

@app.get("/api/v1/coaching")
async def get_coaching(_: bool = Depends(verify_api_key)):
    if r2_client:
        try:
            response = r2_client.list_objects_v2(Bucket=R2_BUCKET, Prefix="coaching/")
            if "Contents" in response:
                signals = []
                for obj in sorted(response["Contents"], key=lambda x: x["Key"])[-10:]:
                    try:
                        obj_data = await read_r2_json(obj["Key"])
                        if obj_data:
                            signals.append(obj_data)
                    except Exception:
                        pass
                if signals:
                    return {"signals": signals, "count": len(signals), "mock": False}
        except Exception:
            pass

    coaching_dir = DATA_ROOT / "coaching"
    signals = []
    if coaching_dir.exists():
        for f in sorted(coaching_dir.glob("*.json"))[-10:]:
            try:
                with open(f) as fp:
                    signals.append(json.load(fp))
            except Exception:
                pass

    if not signals:
        signals = [
            {"type": "pre_entry", "phase": "PRE_ENTRY", "message": "H4 bullish + H1 shallow pullback = your sweet spot. Confidence: 8.7/10", "timestamp": (datetime.utcnow() - timedelta(minutes=15)).isoformat()+"Z"},
            {"type": "during", "phase": "DURING", "message": "Runner held past 2.0R - your data shows +0.8R avg runner value", "timestamp": (datetime.utcnow() - timedelta(minutes=8)).isoformat()+"Z"},
            {"type": "post", "phase": "POST", "message": "Campaign +2.8R - runner discipline paid off. Exit timing improving.", "timestamp": (datetime.utcnow() - timedelta(minutes=2)).isoformat()+"Z"}
        ]

    return {"signals": signals, "count": len(signals), "mock": not coaching_dir.exists()}

async def fetch_live_snapshot() -> dict:
    snapshot = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "confluence": None,
        "pnl": None,
        "risk": None,
        "pipeline": None
    }

    try:
        path = DATA_ROOT / "confluence_score" / "XAUUSD_confluence_score.parquet"
        df = read_parquet_safe(path)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            snapshot["confluence"] = {
                "score": float(latest.get("confluence_score", 0)),
                "tier": str(latest.get("tier", "NEUTRAL")),
                "active_setups": str(latest.get("active_setups", "")).split(";") if latest.get("active_setups") else []
            }
    except Exception:
        pass

    try:
        pnl_path = DATA_ROOT / "live_pnl.json"
        data = None
        if r2_client:
            try:
                data = await read_r2_json("live_pnl.json")
            except Exception:
                pass
        if data is None and pnl_path.exists():
            with open(pnl_path) as f:
                data = json.load(f)
        if data:
            snapshot["pnl"] = data
    except Exception:
        pass

    try:
        risk_path = DATA_ROOT / "risk_guardian" / "state.json"
        data = None
        if r2_client:
            try:
                data = await read_r2_json("risk_guardian/state.json")
            except Exception:
                pass
        if data is None and risk_path.exists():
            with open(risk_path) as f:
                data = json.load(f)
        if data:
            snapshot["risk"] = data
    except Exception:
        pass

    try:
        path = DATA_ROOT / "confluence_score" / "XAUUSD_confluence_score.parquet"
        age = get_file_age(path)
        if age:
            snapshot["pipeline"] = {
                "status": "healthy" if age < 1800 else "degraded" if age < 3600 else "down",
                "last_update_seconds_ago": round(age)
            }
    except Exception:
        pass

    return snapshot

@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json(await fetch_live_snapshot())
        while True:
            await asyncio.sleep(5)
            await websocket.send_json(await fetch_live_snapshot())
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)

async def broadcast_loop():
    while True:
        await asyncio.sleep(5)
        if manager.active_connections:
            data = await fetch_live_snapshot()
            await manager.broadcast(data)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcast_loop())

def get_file_age(path: Path) -> Optional[float]:
    try:
        if path.exists():
            return time.time() - path.stat().st_mtime
    except Exception:
        pass
    return None

if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config

    config = Config()
    config.bind = ["0.0.0.0:8080"]
    config.log_level = "INFO"
    config.worker_class = "asyncio"
    config.workers = 1

    hypercorn.asyncio.run(app, config)

def read_parquet_safe(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def read_csv_safe(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def read_json_safe(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

