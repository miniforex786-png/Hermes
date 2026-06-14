#!/usr/bin/env python3
"""
FastAPI server for Hermes Trading Office PWA.
Provides REST endpoints + WebSocket for live data.
"""
import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configuration
API_KEY = os.getenv("HERMES_API_KEY", "hermes-trading-office-2024")  # Set in production
DATA_ROOT = Path(__file__).parent  # Railway rootDirectory=trading-office puts files at /app
STATIC_DIR = DATA_ROOT  # index.html is in same folder

app = FastAPI(
    title="Hermes Trading Office API",
    description="REST + WebSocket API for 24/7 Campaign Intelligence Dashboard",
    version="1.0.0"
)

# CORS for PWA
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# WebSocket connection manager
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

# Auth dependency
async def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# Helper functions
def read_parquet_safe(path: Path) -> Optional["pd.DataFrame"]:
    """Safely read parquet file, return None if not found or empty."""
    try:
        if path.exists() and path.stat().st_size > 0:
            return pd.read_parquet(path)
    except Exception as e:
        print(f"Error reading {path}: {e}")
    return None

def read_csv_safe(path: Path) -> Optional["pd.DataFrame"]:
    """Safely read CSV file."""
    try:
        if path.exists() and path.stat().st_size > 0:
            return pd.read_csv(path)
    except Exception as e:
        print(f"Error reading {path}: {e}")
    return None

def get_file_age(path: Path) -> Optional[float]:
    """Get file age in seconds."""
    try:
        if path.exists():
            return time.time() - path.stat().st_mtime
    except Exception:
        pass
    return None

# ==================== API ENDPOINTS ====================

@app.get("/")
async def root():
    """Serve the PWA index.html"""
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/v1/health")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat() + "Z"}

@app.get("/api/v1/system/health")
async def system_health(_: bool = Depends(verify_api_key)):
    """Pipeline health status for dashboard"""
    import time
    
    checks = {
        "pipeline": {"status": "unknown", "details": {}},
        "data_freshness": {},
        "cron_jobs": {},
        "mt5_export": None
    }
    
    # Check key parquet files
    key_files = {
        "confluence_score": DATA_ROOT / "confluence_score" / "XAUUSD_confluence_score.parquet",
        "setups": DATA_ROOT / "edge_discovery" / "XAUUSD_setup_labels.parquet",
        "behaviour": DATA_ROOT / "behaviour_analysis" / "outputs" / "behaviour_summary.json",
        "aligned": DATA_ROOT / "aligned_data" / "XAUUSD_M12_aligned.parquet",
    }
    
    max_age = 0
    stale_files = []
    for name, path in key_files.items():
        age = get_file_age(path)
        if age is not None:
            checks["data_freshness"][name] = {
                "age_seconds": round(age),
                "age_human": f"{round(age/60)} min ago" if age < 3600 else f"{round(age/3600)} hrs ago",
                "stale": age > 1800  # 30 min
            }
            max_age = max(max_age, age)
            if age > 1800:
                stale_files.append(name)
        else:
            checks["data_freshness"][name] = {"status": "missing"}
            stale_files.append(name)
    
    # Determine overall pipeline status
    if not stale_files:
        checks["pipeline"]["status"] = "healthy"
    elif len(stale_files) <= 2:
        checks["pipeline"]["status"] = "degraded"
    else:
        checks["pipeline"]["status"] = "down"
    
    # MT5 export freshness
    mt5_files = list((DATA_ROOT / "mt5_data_full").glob("*.parquet"))
    if mt5_files:
        mt5_age = min(get_file_age(f) for f in mt5_files)
        checks["mt5_export"] = {
            "age_seconds": round(mt5_age) if mt5_age else None,
            "files": len(mt5_files),
            "stale": mt5_age > 86400 if mt5_age else True  # 24 hrs
        }
    
    return checks

@app.get("/api/v1/confluence")
async def get_confluence(_: bool = Depends(verify_api_key)):
    """Latest confluence score"""
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    
    logger.debug("=== ENTERING get_confluence endpoint ===")
    try:
        path = DATA_ROOT / "confluence_score" / "XAUUSD_confluence_score.parquet"
        logger.debug(f"Confluence path: {path}")
        logger.debug(f"Path exists: {path.exists()}")
        
        df = read_parquet_safe(path)
        logger.debug(f"read_parquet_safe returned: {df is not None}")
        logger.debug(f"df is None: {df is None}")
        if df is not None:
            logger.debug(f"df.empty: {df.empty}")
        
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
            "timestamp": str(latest.name) if hasattr(latest, 'name') else datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Exception in get_confluence: {e}", exc_info=True)
        raise

@app.get("/api/v1/setups")
async def get_setups(limit: int = 50, _: bool = Depends(verify_api_key)):
    """Recent setup labels with forward returns"""
    path = DATA_ROOT / "edge_discovery" / "XAUUSD_setup_labels.parquet"
    df = read_parquet_safe(path)
    
    if df is None or df.empty:
        # Mock data for development
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
    """Session/DOW/context stats from opportunity windows"""
    stats = {}
    
    # Session stats
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
    
    # DOW stats
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
    
    # Context stats
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
    """Risk Guardian state - 6 dimensions + escalation"""
    # Read from risk_guardian if available, else from MT5 live
    risk_path = DATA_ROOT / "risk_guardian" / "state.json"
    
    if risk_path.exists():
        try:
            with open(risk_path) as f:
                return json.load(f)
        except Exception:
            pass
    
    # Mock data for development
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
    """Current P&L from MT5 / campaign data"""
    # Try to read from a live P&L file if exists
    pnl_path = DATA_ROOT / "live_pnl.json"
    if pnl_path.exists():
        try:
            with open(pnl_path) as f:
                return json.load(f)
        except Exception:
            pass
    
    # Mock structure for development
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

@app.get("/api/v1/campaigns")
async def get_campaigns(_: bool = Depends(verify_api_key)):
    """Active campaigns from MT5 positions + comment tags"""
    campaigns_path = DATA_ROOT / "active_campaigns.json"
    if campaigns_path.exists():
        try:
            with open(campaigns_path) as f:
                return json.load(f)
        except Exception:
            pass
    
    # Mock structure for development
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
    """Behaviour analysis summary"""
    path = DATA_ROOT / "behaviour_analysis" / "outputs" / "behaviour_summary.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    
    # Mock data for development
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
    """Latest coaching signals"""
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
        # Mock data for development
        signals = [
            {"type": "pre_entry", "phase": "PRE_ENTRY", "message": "H4 bullish + H1 shallow pullback = your sweet spot. Confidence: 8.7/10", "timestamp": (datetime.utcnow() - timedelta(minutes=15)).isoformat()+"Z"},
            {"type": "during", "phase": "DURING", "message": "Runner held past 2.0R - your data shows +0.8R avg runner value", "timestamp": (datetime.utcnow() - timedelta(minutes=8)).isoformat()+"Z"},
            {"type": "post", "phase": "POST", "message": "Campaign +2.8R - runner discipline paid off. Exit timing improving.", "timestamp": (datetime.utcnow() - timedelta(minutes=2)).isoformat()+"Z"}
        ]
    
    return {"signals": signals, "count": len(signals), "mock": not coaching_dir.exists()}

# ==================== WEBSOCKET ====================

async def fetch_live_snapshot() -> dict:
    """Fetch all live data for WebSocket push"""
    snapshot = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "confluence": None,
        "pnl": None,
        "risk": None,
        "pipeline": None
    }
    
    try:
        # Confluence
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
        # P&L
        pnl_path = DATA_ROOT / "live_pnl.json"
        if pnl_path.exists():
            with open(pnl_path) as f:
                snapshot["pnl"] = json.load(f)
    except Exception:
        pass
    
    try:
        # Risk
        risk_path = DATA_ROOT / "risk_guardian" / "state.json"
        if risk_path.exists():
            with open(risk_path) as f:
                snapshot["risk"] = json.load(f)
    except Exception:
        pass
    
    try:
        # Pipeline health
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
    """WebSocket for real-time dashboard updates"""
    await manager.connect(websocket)
    try:
        # Send initial snapshot
        await websocket.send_json(await fetch_live_snapshot())
        
        # Send updates every 5 seconds
        while True:
            await asyncio.sleep(5)
            await websocket.send_json(await fetch_live_snapshot())
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# Background task to broadcast to all connections
async def broadcast_loop():
    while True:
        await asyncio.sleep(5)
        if manager.active_connections:
            data = await fetch_live_snapshot()
            await manager.broadcast(data)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcast_loop())

# ==================== MAIN ====================

if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config
    
    config = Config()
    config.bind = ["0.0.0.0:8080"]
    config.log_level = "INFO"
    config.worker_class = "asyncio"
    config.workers = 1
    
    hypercorn.asyncio.run(app, config)