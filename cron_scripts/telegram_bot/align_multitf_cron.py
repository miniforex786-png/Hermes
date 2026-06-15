#!/usr/bin/env python3
"""Cron wrapper: Run align_multitf then upload aligned data to R2."""
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

def main():
    print("=" * 60)
    print("align_multitf Cron Job")
    print("=" * 60)
    
    # Run align_multitf
    if not run_script("align_multitf.py"):
        print("align_multitf failed")
        return 1
    
    # Upload aligned data to R2
    print("\nUploading aligned data to R2...")
    result = subprocess.run(
        [SYSTEM_PYTHON, "-I", os.path.join(SCRIPTS_DIR, "upload_to_r2.py")],
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=60
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())