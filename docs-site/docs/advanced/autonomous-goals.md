---
id: autonomous-goals
title: Autonomous Goals and Background Consolidation
description: Autonomous Goal Generator, Background Consolidation cycle, perception, and CPI gating.
---

# Autonomous Goals and Background Consolidation

Two background systems can generate Goals without operator input: the **Autonomous Goal Generator** (reactive, threshold-driven) and the **Background Consolidation Cycle** (idle-time consolidation).

## Autonomous Goal Generator

`scheduler/autonomous.py`. Feature-flagged via `autonomous_goal_enabled` (default `true`).

### Cadence

Runs every 30 min by default. Skipped when `agent:cpi_high` is set.

### What it does

Each tick gathers world state via `psutil` and DB queries:

- Disk usage %
- RAM usage %
- CPU usage %
- Recent error count (`audit_log` last 1 h)
- Active task count

### Critical thresholds (no LLM)

These bypass the LLM and create a goal directly:

| Metric | Threshold | Auto-action |
|--------|-----------|-------------|
| Disk | > 95% | Create cleanup goal |
| RAM | > 95% | Create RAM-pressure mitigation goal |

### Non-critical evaluation (LLM)

Non-critical states are evaluated by the LLM with a prompt asking whether any *proactive* action would help. The LLM's decision must propose a concrete `agent_manager` or `task_manager` action; if it returns "no action", the cycle ends.

### Rate limits

- 1 goal per hour.
- Maximum 5 goals per day.

State stored in `agent:autonomous_state` (Redis).

### Notification

When the generator creates a goal, the operator receives a Telegram notification:

```
🤖 Proactive action: Cleaning up temporary files
Reason: Disk at 88% — clearing space to maintain optimal performance
```

## Background Consolidation Cycle

`scheduler/dream.py`. Feature-flagged via `dream_enabled` (default `true`). Internally the implementation module retains the legacy `dream` name; the runtime concept and operator-facing label are "background consolidation".

### Activation conditions

ALL must hold:

- Operator inactive > 2 h
- (Night 1–7 am local time) OR (operator inactive > 4 h)
- Last consolidation > 6 h ago
- `agent:cpi_high` flag NOT set

### Activities

When activated, the cycle:

1. **Memory consolidation** via `PromotionEngine` — promotes recurring/important episodic entries to semantic memory.
2. **Knowledge graph extraction** for any unprocessed conversations.
3. **LLM reflection** — short narrative on the day's activity, written to `consolidation_log` (table name in DB: `dream_log`).
4. **Crypto prefetch** — for assets in the KG, fetch latest prices into the temporal world model so the next morning's first message has fresh data.
5. **Failure pattern analysis** — query `audit_log` for errors in the past 7 days; classify into `FailurePattern(tool, error_type, frequency, first_seen, last_seen)`; upsert into `self_model["known_failures"]`.

### Storage

```
DreamLog(
    started_at, duration_seconds,
    memories_consolidated, kg_nodes_added,
    reflection,                  -- LLM narrative
    improvements_proposed,
    improvements_json,           -- proposed self_improve diffs
    prefetch_done
)
```

## Background Perception

`scheduler/perception.py`. Feature-flagged via `perception_enabled` (default `true`).

### Cadence

Every 15 min. Skipped when `agent:cpi_high` is set.

### What it does

- Scans temporal world model for assets in the KG.
- For each asset, calls `detect_change(entity, threshold_pct=4)`.
- If change > 4%, asks LLM: is this notable?
- If yes → Telegram alert.

### Rate limits

Max 3 notifications per day. Respects quiet hours configured via `quiet_hours_start_local` and `quiet_hours_end_local`.

## CPI gating

All three systems above check the `agent:cpi_high` Redis flag and skip if set. CPI > 80 indicates pressure (high CPU, latency, error rate, or memory growth). See [Monitoring → CPI](/operations/monitoring#cognitive-pressure-index-cpi).

## Self-Integrity Monitor

`scheduler/integrity.py`. Every 6 h, cross-checks declared self-model strengths against actual skill success rates and flags drift. Writes `agent:integrity_report` JSON in Redis. Visible at `/cognitive` (Integrity tab). Drift larger than threshold triggers a Telegram alert.

## Disabling autonomy

To run WASP purely reactively (no autonomous behavior):

```bash
# In .env or via /config:
DREAM_ENABLED=false
AUTONOMOUS_GOAL_ENABLED=false
PERCEPTION_ENABLED=false
```

This stops all token spend from background autonomy. The agent only acts when you message it.

## See also

- [Scheduler](/core-concepts/scheduler) — full job inventory
- [Goal Engine](/core-concepts/goal-engine)
- [Reflection Engine](/cognitive-systems/reflection-engine)
- [Monitoring → CPI](/operations/monitoring#cognitive-pressure-index-cpi)
- [Known Limitations](/known-limitations) — token-cost trade-offs
