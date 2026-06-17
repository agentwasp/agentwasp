"""Config Center — prime.md editor and feature flag controls."""
from __future__ import annotations

import json
import os

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()
logger = structlog.get_logger()

PRIME_PATH = "/data/config/prime.md"
PRIME_DEFAULT_PATH = "/data/config/prime.default.md"
CONFIG_OVERRIDES_KEY = "config:overrides"


def _read_prime() -> str:
    try:
        with open(PRIME_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


async def _get_overrides(redis_url: str) -> dict:
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(redis_url, decode_responses=True)
        raw = await r.get(CONFIG_OVERRIDES_KEY)
        await r.aclose()
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


@router.get("/", response_class=HTMLResponse)
async def config_page(request: Request):
    from ...config import settings

    prime_content = _read_prime()
    overrides = await _get_overrides(request.app.state.redis_url)

    # Build feature flags list from settings
    feature_flags = [
        {"key": "sovereign_mode",           "label": "Sovereign Mode",          "desc": "Full autonomy, max skill rounds, doubled budgets", "value": overrides.get("sovereign_mode", settings.sovereign_mode), "group": "autonomy"},
        {"key": "plan_critic_enabled",       "label": "Plan Critic",             "desc": "Second LLM pass validates TaskGraph before execution", "value": overrides.get("plan_critic_enabled", settings.plan_critic_enabled), "group": "execution"},
        {"key": "skill_evolution_enabled",   "label": "Skill Evolution",         "desc": "Auto-synthesise composite skills from recurring patterns", "value": overrides.get("skill_evolution_enabled", settings.skill_evolution_enabled), "group": "learning"},
        {"key": "temporal_reasoning_enabled","label": "Temporal Reasoning",      "desc": "Generate [TEMPORAL INSIGHTS] in LLM context", "value": overrides.get("temporal_reasoning_enabled", settings.temporal_reasoning_enabled), "group": "learning"},
        {"key": "vector_memory_enabled",     "label": "Vector Memory",           "desc": "Semantic search with embeddings (falls back to hash)", "value": overrides.get("vector_memory_enabled", settings.vector_memory_enabled), "group": "memory"},
        {"key": "supermemory_ingest_enabled", "label": "Supermemory Sync",        "desc": "Mirror memory writes to Supermemory when backend is tandem/supermemory", "value": overrides.get("supermemory_ingest_enabled", settings.supermemory_ingest_enabled), "group": "memory"},
        {"key": "memory_ranking_enabled",    "label": "Memory Ranking",          "desc": "Composite relevance scoring before context injection", "value": overrides.get("memory_ranking_enabled", settings.memory_ranking_enabled), "group": "memory"},
        {"key": "world_model_enabled",       "label": "World Model",             "desc": "Structured world-state tracking from KG + temporal data", "value": overrides.get("world_model_enabled", settings.world_model_enabled), "group": "memory"},
        {"key": "goal_engine_enabled",       "label": "Goal Engine",             "desc": "Multi-step goal planning and execution", "value": overrides.get("goal_engine_enabled", settings.goal_engine_enabled), "group": "execution"},
        {"key": "agents_enabled",            "label": "Multi-Agent",             "desc": "Sub-agent orchestration and parallel execution", "value": overrides.get("agents_enabled", settings.agents_enabled), "group": "execution"},
        {"key": "integrations_enabled",      "label": "Integrations",            "desc": "External integration platform with circuit breakers", "value": overrides.get("integrations_enabled", settings.integrations_enabled), "group": "autonomy"},
        {"key": "governor_enabled",          "label": "Resource Governor",       "desc": "Rate limits on tasks, goals, agents and LLM calls", "value": overrides.get("governor_enabled", settings.governor_enabled), "group": "safety"},
        {"key": "scheduler_enabled",         "label": "Scheduler",               "desc": "Background jobs: health, dream, perception, autonomous", "value": overrides.get("scheduler_enabled", settings.scheduler_enabled), "group": "autonomy"},
    ]

    # Runtime params (read-only display)
    runtime_params = {
        "skills_max_rounds":            settings.skills_max_rounds,
        "goal_budget_max_replans":      settings.goal_budget_max_replans,
        "goal_tick_interval":           f"{settings.goal_tick_interval}s",
        "agents_tick_interval":         f"{settings.agents_tick_interval}s",
        "goal_max_concurrent":          settings.goal_max_concurrent,
        "agents_max_active":            settings.agents_max_active,
        "goal_budget_max_tokens_planning": settings.goal_budget_max_tokens_planning,
        "memory_episodic_max":          settings.memory_episodic_max,
        "memory_semantic_max":          settings.memory_semantic_max,
        "memory_backend":               settings.memory_backend,
        "supermemory_base_url":         settings.supermemory_base_url,
        "supermemory_scope":            settings.supermemory_scope,
        "supermemory_context_budget_chars": settings.supermemory_context_budget_chars,
        "supermemory_timeout_seconds":  f"{settings.supermemory_timeout_seconds}s",
        "supermemory_search_limit":     settings.supermemory_search_limit,
        "embedding_provider":           settings.embedding_provider,
        "integrations_policy_mode":     settings.integrations_policy_mode,
        "goal_default_autonomy_mode":   settings.goal_default_autonomy_mode,
        "proactive_max_daily":          settings.proactive_max_daily,
        "timezone":                     settings.timezone,
    }

    return request.app.state.templates.TemplateResponse(request, "config_center.html", {
        "prime_content": prime_content,
        "feature_flags": feature_flags,
        "runtime_params": runtime_params,
        "prime_path": PRIME_PATH,
        "overrides": overrides,
    })


@router.post("/api/prime")
async def save_prime(request: Request):
    try:
        body = await request.json()
        content = body.get("content", "")
        os.makedirs(os.path.dirname(PRIME_PATH), exist_ok=True)
        with open(PRIME_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("config.prime_saved", length=len(content))
        return JSONResponse({"ok": True, "length": len(content)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e).splitlines()[0][:120]}, status_code=500)


@router.get("/api/prime/default")
async def get_prime_default(request: Request):
    """Return the default generic prime.md content."""
    try:
        with open(PRIME_DEFAULT_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        return JSONResponse({"ok": True, "content": content})
    except FileNotFoundError:
        return JSONResponse({"ok": False, "error": "Default template not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e).splitlines()[0][:120]}, status_code=500)


# Flags that require a container restart to fully take effect (they wire subsystems at startup)
_RESTART_REQUIRED_FLAGS = {
    "goal_engine_enabled",
    "agents_enabled",
    "scheduler_enabled",
    "integrations_enabled",
    "governor_enabled",
}


@router.post("/api/flag")
async def toggle_flag(request: Request):
    try:
        body = await request.json()
        key = body.get("key", "")
        value = body.get("value")
        if not key:
            return JSONResponse({"ok": False, "error": "key required"}, status_code=400)
        overrides = await _get_overrides(request.app.state.redis_url)
        overrides[key] = value
        import redis.asyncio as aioredis
        r = aioredis.from_url(request.app.state.redis_url, decode_responses=True)
        await r.set(CONFIG_OVERRIDES_KEY, json.dumps(overrides))
        await r.aclose()

        # Apply immediately to the live settings singleton so runtime checks
        # (context_builder, handlers, plan_validator) pick up the change
        # without a container restart.
        try:
            from ...config import settings as _live_settings
            if hasattr(_live_settings, key) and isinstance(value, bool):
                setattr(_live_settings, key, value)
                logger.info("config.flag_applied_live", key=key, value=value)
        except Exception as _e:
            logger.warning("config.flag_live_apply_failed", key=key, error=str(_e))

        restart_required = key in _RESTART_REQUIRED_FLAGS
        logger.info("config.flag_set", key=key, value=value, restart_required=restart_required)
        return JSONResponse({"ok": True, "key": key, "value": value, "restart_required": restart_required})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e).splitlines()[0][:120]}, status_code=500)
