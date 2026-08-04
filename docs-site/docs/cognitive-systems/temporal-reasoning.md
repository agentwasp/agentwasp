---
id: temporal-reasoning
title: Temporal Reasoning
description: WorldTimeline observations, history queries, change detection.
---

# Temporal Reasoning

`memory/temporal.py` records time-series observations of entities and provides retrieval by entity, time window, or change delta. It is the time-dimension of WASP's memory.

## Storage

```
WorldTimeline(
    observed_at,           -- timestamptz
    entity,                -- e.g., "BTC", "cpu", "errors"
    observation_type,      -- price | event | state | mention | metric
    value,                 -- string (numbers as decimal strings)
    source,                -- which skill or job recorded it
    confidence,            -- 0..1
    chat_id,               -- attribution
    expires_at             -- TTL
)
```

Rows are append-only. Pruning by `expires_at` is automatic; observations live ~30 days by default.

## Extraction

Rule-based extraction from skill outputs:

| Pattern set | Example matches |
|-------------|------------------|
| `_PRICE_PATTERNS` | "BTC: $43,250", "ETH 3,500 USD" |
| `_EVENT_PATTERNS` | "deployed at 14:00", "alert fired" |
| `_STATE_PATTERNS` | "online/offline", "healthy/degraded" |
| `_NUMERIC_METRIC_PATTERNS` | "CPU 75%", "latency 230 ms" |

Filtered by `_CONTAMINATION_GUARDS` and `_is_valid_user_state()` to reject garbage extractions (URL fragments mistaken for prices, etc.).

Index-based group extraction prevents inverted entity/value pairs.

## API

```python
add_observation(entity, observation_type, value, ...)
get_entity_history(entity, since=None) → list[WorldTimeline]
detect_change(entity, threshold_pct=4.0) → ChangeReport | None
format_for_context(chat_id) → str  # injected into system prompt
```

## Injection into prompts

`format_for_context()` produces a labeled "Temporal Observations" block (rendered in user's detected language):

```
[Temporal Observations]
- BTC: $43,250 (+2.1% in 24h)
- CPU: 45% (stable for 2h)
- Last deploy: 3h ago, success
```

Block size is bounded; only entities relevant to the current message are included.

## Change detection

The Background Perception job calls `detect_change(entity)` for assets in the Knowledge Graph. When the change exceeds the threshold (4% by default), it asks the LLM whether the change is notable; if yes, sends a Telegram alert.

Notification rate-limited to 3/day; respects quiet hours (`quiet_hours_start_local`, `quiet_hours_end_local`).

## Use cases

- "How has BTC moved this week?" → `get_entity_history("BTC", since=week_ago)`
- "Has CPU spiked?" → `detect_change("cpu", threshold_pct=20)`
- "What did I mention about X?" → `WorldTimeline WHERE entity ILIKE %X%`

## Dashboard

`/world-model` charts the timeline per entity. `/cognitive` summarizes recent changes.

## See also

- [World Model](/cognitive-systems/world-model) — current snapshots
- [Knowledge Graph](/core-concepts/knowledge-graph) — entity registry
- [Memory](/core-concepts/memory) — overall memory layers
- [Scheduler → perception](/core-concepts/scheduler#cognitive-systems)
