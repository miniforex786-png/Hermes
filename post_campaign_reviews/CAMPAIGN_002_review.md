# Post-Campaign Review: CAMPAIGN_002
**Type:** DISCRETIONARY | **Date:** 2026-06-13 | **Outcome:** FAIL

## Executive Summary
- **Net P&L:** $-77,282.20
- **Total Trades:** 70
- **Win Rate:** 60.0%
- **Expectancy:** $-1104.03/trade
- **Profit Factor:** 0.07
- **Max Drawdown:** $80,941.00
- **Duration:** 83.8 hours

## Phase Scores
- **Setup Quality:** 27.3/100 (mixed)
- **Execution:** 10.0/100 (chaotic sizing, 26 revenge trades)
- **Risk Management:** 10/100 (no_runners runner management)

## Setup Breakdown
- 153072542: 70 trades

## Behaviour vs Personal Baseline
- win_rate: worse ❌
- avg_win: worse ❌
- avg_loss: worse ❌
- sizing_consistency: worse ❌
- revenge_rate: better ✅

## Key Strengths

## Key Weaknesses
- ❌ Campaign loss: $-77282
- ❌ Negative expectancy: $-1104/trade
- ❌ 26 revenge trades ($-48673 P&L)
- ❌ Sizing discipline: chaotic (CV=1.82)
- ❌ Major losses in sub-optimal session
- ❌ Extended duration: 84h
- ❌ Risk breach: Max layers 23 > 5
- ❌ Risk breach: Campaign DD $80941 > $5000
- ❌ Risk breach: Max daily loss $48153 > $2000

## Action Items
- [Next session] **Self**: Review all losing trades for common patterns
- [Immediate] **System**: Enforce 60min cooldown post-loss via Risk Guardian
- [Next campaign] **Self**: Implement fixed fractional sizing (e.g., 1% risk per trade)
- [Immediate] **System**: Restrict trading to high-WR sessions (London for Probe, avoid NY for Discretionary)
- [Next campaign] **Risk Guardian**: Set campaign time limit (max 48h auto-pause)