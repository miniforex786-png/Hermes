#!/usr/bin/env python3
"""Upload generated data files to Cloudflare R2."""
import os
import boto3
from pathlib import Path

# Load .env file if exists (for cron jobs)
def load_dotenv():
    env_paths = [
        Path(__file__).parent / ".env",
        Path(r"C:\Users\Boboi Kusni\AppData\Local\hermes\scripts\telegram_bot\.env"),
        Path(r"C:\Hermes\.env"),
    ]
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k not in os.environ:  # Don't override existing env
                            os.environ[k] = v
            break

load_dotenv()

# R2 Config (read from env or use defaults)
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID") or os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY") or os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET", "hermes-pipeline")

if not (R2_ACCOUNT_ID and R2_ACCESS_KEY and R2_SECRET_KEY):
    print("ERROR: Missing R2 credentials in environment")
    exit(1)

r2_client = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    region_name="auto",
)

DATA_ROOT = Path(r"C:\Hermes")

# Files to upload: local_path -> r2_key
# Keys must match what health endpoint expects
FILES = [
    (DATA_ROOT / "confluence_score" / "XAUUSD_confluence_score.parquet", "confluence_score/XAUUSD_confluence_score.parquet"),
    (DATA_ROOT / "edge_discovery" / "XAUUSD_setup_labels.parquet", "edge_discovery/XAUUSD_setup_labels.parquet"),
    (DATA_ROOT / "behaviour_analysis" / "outputs" / "behaviour_summary.json", "behaviour_analysis/outputs/behaviour_summary.json"),
    (DATA_ROOT / "aligned_data" / "XAUUSD_M12_aligned.parquet", "aligned_data/XAUUSD_M12_aligned.parquet"),
    (DATA_ROOT / "mt5_data_full" / "XAUUSD_M12.parquet", "mt5_data/XAUUSD_M12.parquet"),
    (DATA_ROOT / "opportunity_windows" / "session_stats.csv", "opportunity_windows/session_stats.csv"),
    (DATA_ROOT / "risk_guardian" / "state.json", "risk_guardian/state.json"),
    (DATA_ROOT / "mt5_positions.json", "mt5_positions.json"),
    (DATA_ROOT / "live_pnl.json", "live_pnl.json"),
    (DATA_ROOT / "trading_journal.json", "trading_journal.json"),
    (DATA_ROOT / "active_campaigns.json", "active_campaigns.json"),
]

def upload_coaching():
    """Upload latest coaching signals to R2."""
    coaching_dir = DATA_ROOT / "coaching"
    if not coaching_dir.exists():
        return 0
    
    signals = sorted(coaching_dir.glob("*.json"))[-10:]  # Last 10
    uploaded = 0
    for f in signals:
        try:
            r2_key = f"coaching/{f.name}"
            r2_client.upload_file(str(f), R2_BUCKET, r2_key)
            print(f"[OK] Uploaded: {r2_key}")
            uploaded += 1
        except Exception as e:
            print(f"[FAIL] Failed {r2_key}: {e}")
    return uploaded

def upload_file(local_path: Path, r2_key: str):
    if not local_path.exists():
        print(f"[WARN] Missing: {local_path}")
        return False
    try:
        r2_client.upload_file(str(local_path), R2_BUCKET, r2_key)
        print(f"[OK] Uploaded: {r2_key} ({local_path.stat().st_size} bytes)")
        return True
    except Exception as e:
        print(f"[FAIL] Failed {r2_key}: {e}")
        return False

if __name__ == "__main__":
    print(f"Uploading to R2 bucket: {R2_BUCKET}")
    print(f"Account: {R2_ACCOUNT_ID}")
    print("-" * 50)
    
    success = 0
    for local, key in FILES:
        if upload_file(local, key):
            success += 1
    
    # Upload coaching signals
    coaching_uploaded = upload_coaching()
    success += coaching_uploaded
    
    print("-" * 50)
    print(f"Done: {success}/{len(FILES)} files + {coaching_uploaded} coaching signals uploaded")
    exit(0 if success >= len(FILES) else 1)