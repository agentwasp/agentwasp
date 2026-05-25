---
id: reflection-engine
title: Reflection Engine
description: Per-goal post-mortem insights and background consolidation reflection.
---

# Reflection Engine

WASP has two reflection layers:

1. **Goal Meta-Reflection** — post-mortem after every goal completion or failure.
2. **Consolidation reflection** — narrative reflection during the background consolidation cycle.

## Goal Meta-Reflection

`scheduler/goal_meta_reflection.py` (or `goal_orchestrator/reflection_job.py`). Feature-flagged via `goal_meta_reflection_enabled` (default `true`).

When a goal completes or fails, the reflection job runs once and produces structured insights:

```
ExecutionReflection(
    timestamp,
    chat_id,
    intent,                 -- inferred from goal objective
    skills_used,
    duration_ms,
    success,
    efficiency_score,       -- 0..1
    issues,                 -- JSON array
    insight,                -- short LLM-generated note
    suggestion,             -- improvement proposal
    pattern_key,            -- normalized for SkillPattern detection
    recurring_pattern       -- True if this matches a known SkillPattern
)
```

## Insights surfaced

Stored in Redis with TTL 7 days; injected into context for similar future goals. Examples:

- "Took 3 retries to find the right CSS selector. Consider using `browser_smart_navigate` instead of `browser` for sites with unpredictable DOM."
- "Repeated the same web_search 4 times. Cache the result on first hit."
- "Email send blocked by intent gate. The user did not explicitly request it; the agent was over-eager."

Maximum 3 reflections per goal.

## Consolidation reflection

`scheduler/dream.py` (gated). When the background consolidation cycle activates, it runs an LLM reflection over the day's activity and writes:

```
DreamLog(
    started_at, duration_seconds,
    memories_consolidated, kg_nodes_added,
    reflection,                 -- short LLM narrative
    improvements_proposed,
    improvements_json,          -- proposed self_improve diffs
    prefetch_done               -- crypto prices, news headlines
)
```

The reflection is informal: a paragraph of "what went well today, what could be better." It is NOT a behavioral rule and does NOT modify code on its own — improvements are proposed for operator review at `/self-improve`.

## Dashboard

`/cognitive` shows recent reflections (Goal Meta and Consolidation).

## CPI gating

Both reflection layers skip when `agent:cpi_high` is set.

## See also

- [Goal Engine](/core-concepts/goal-engine)
- [Background Consolidation](/advanced/autonomous-goals#background-consolidation-cycle)
- [Self-Improve](/integrations/dashboard) — proposal review
- [Behavioral Learning](/cognitive-systems/behavioral-learning) — separate but complementary: rules from corrections
