#!/usr/bin/env python3
"""Cron wrapper: Run risk_guardian_eval then upload to R2."""
import subprocess
import sys
import os

SYSTEM_PYTHON = r"C:\Users\Boboi Kusni\AppData\Local\Programs\Python\Python312\python.exe"
SCRIPTS_DIR = r"C:\Hermes\scripts"

def run_script(script_name: str) -> bool:
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"Script not found: {script_path}")
        return False
    
    print(f"Running: {script_name}")
    result = subprocess.run(
        [SYSTEM_PYTHON, "-I", script_path],
        capture_output=True,
        text=True,
        encoding='utf-8',
        cwd=r"C:\Hermes",
        timeout=300
    )
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    if result.returncode != 0:
        print(f"{script_name} failed with exit code {result.returncode}")
        return False
    
    print(f"{script_name} completed")
    return True

def upload_outputs():
    """Upload risk state, P&L, campaigns to R2."""
    for upload_script in ["upload_risk.py", "upload_pnl.py", "upload_campaigns.py"]:
        script_path = os.path.join(SCRIPTS_DIR, upload_script)
        if os.path.exists(script_path):
            print(f"\nRunning: {upload_script}")
            result = subprocess.run(
                [SYSTEM_PYTHON, "-I", script_path],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=60
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

def main():
    print("=" * 60)
    print("risk_guardian_eval Cron Job")
    print("=" * 60)
    
    # Run risk_guardian_eval
    if not run_script("risk_guardian_eval.py"):
        print("risk_guardian_eval failed")
        return 1
    
    # Upload to R2
    print("\nUploading to R2...")
    upload_outputs()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())