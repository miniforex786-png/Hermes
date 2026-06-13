#!/usr/bin/env python3
"""
Telegram Bot — Cron Job Setup

Creates Hermes cron jobs for:
- Daily briefing (08:00 UTC)
- Risk alerts (every 5 minutes)
- Setup alerts (every 5 minutes)
- Session outlook (every 4 hours)
"""

from hermes_tools import cronjob

def setup_cron_jobs():
    """Create all cron jobs for the trading bot."""
    
    bot_path = r"C:\Hermes\telegram_bot\bot.py"
    
    jobs = [
        {
            "name": "Daily Briefing",
            "schedule": "0 8 * * *",  # 08:00 UTC daily
            "script": "daily_briefing",
            "prompt": f"Run daily briefing via: python {bot_path}",
            "skills": []
        },
        {
            "name": "Risk Alerts Check",
            "schedule": "every 5m",
            "script": "check_risk_alerts",
            "prompt": f"Check risk alerts via: python {bot_path}",
            "skills": []
        },
        {
            "name": "Setup Alerts Check", 
            "schedule": "every 5m",
            "script": "check_setup_alerts",
            "prompt": f"Check setup alerts via: python {bot_path}",
            "skills": []
        },
        {
            "name": "Session Outlook",
            "schedule": "every 4h",
            "script": "session_outlook",
            "prompt": f"Send session outlook via: python {bot_path}",
            "skills": []
        },
    ]
    
    created = []
    for job in jobs:
        try:
            result = cronjob(action="create", **job)
            job_id = result.get("job_id") if isinstance(result, dict) else str(result)
            created.append((job["name"], job_id))
            print(f"✓ Created: {job['name']} (ID: {job_id})")
        except Exception as e:
            print(f"✗ Failed: {job['name']} - {e}")
    
    return created

def list_cron_jobs():
    """List all cron jobs."""
    result = cronjob(action="list")
    return result

def remove_all_jobs():
    """Remove all cron jobs (for cleanup)."""
    result = cronjob(action="list")
    jobs = result.get("jobs", []) if isinstance(result, dict) else []
    
    for job in jobs:
        job_id = job.get("job_id") if isinstance(job, dict) else job
        try:
            cronjob(action="remove", job_id=job_id)
            print(f"Removed: {job_id}")
        except Exception as e:
            print(f"Error removing {job_id}: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_cron_jobs()
    elif len(sys.argv) > 1 and sys.argv[1] == "remove":
        remove_all_jobs()
    else:
        setup_cron_jobs()