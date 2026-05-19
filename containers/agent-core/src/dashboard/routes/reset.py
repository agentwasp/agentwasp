"""Panic Reset — wipes agent cognitive state, triggers boot sequence on next message."""

import json
import os
import shutil
from datetime import datetime, timezone
from uuid import uuid4

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

from ...db.models import AuditLog
from ...db.session import async_session, engine

router = APIRouter()
logger = structlog.get_logger()

CONFIRM_PHRASE = "RESET WASP"  # legacy: panic-only callers
_CONFIRM_PHRASES = {
    "panic":   "RESET WASP",
    "factory": "FACTORY RESET WASP",
}
LOCK_KEY = "agent:reset_in_progress"
LOCK_TTL = 60  # seconds — safety TTL in case the process dies mid-reset

# Rate limit: max 3 reset attempts per user per 5 minutes
_RESET_RATE_KEY_PREFIX = "agent:reset_rate:"
_RESET_RATE_WINDOW = 300       # seconds (5 minutes)
_RESET_RATE_MAX = 3            # max attempts per window


async def _verify_admin(user_id: str) -> bool:
    """Defense-in-depth: confirm the session user_id maps to an admin_users row.

    Reset has CSRF + confirmation phrase + per-user rate limit; this is the
    final identity check that prevents a hijacked session from triggering a
    full brain wipe.
    """
    if not user_id:
        return False
    try:
        from ...db.models import AdminUser
        from sqlalchemy import select
        async with async_session() as session:
            result = await session.execute(
                select(AdminUser.id).where(AdminUser.id == user_id).limit(1)
            )
            return result.scalar_one_or_none() is not None
    except Exception:
        logger.exception("reset.admin_verify_error")
        return False


async def _check_rate_limit(redis_url: str, user_id: str) -> tuple[bool, int]:
    """Sliding-window rate limit on reset attempts. Returns (allowed, count_in_window)."""
    if not user_id:
        return False, 0
    try:
        _r = await _redis_conn(redis_url)
        try:
            key = f"{_RESET_RATE_KEY_PREFIX}{user_id}"
            count = await _r.incr(key)
            if count == 1:
                await _r.expire(key, _RESET_RATE_WINDOW)
            return count <= _RESET_RATE_MAX, int(count)
        finally:
            await _r.aclose()
    except Exception:
        # Fail-closed on rate-limit errors — better to block reset than allow flood
        logger.exception("reset.rate_limit_error")
        return False, _RESET_RATE_MAX + 1

# Redis key patterns to delete (NEVER touches: sessions, csrf, login-rate, subscriptions, apikeys)
_REDIS_WIPE_PATTERNS = [
    "agent:*",
    "cb:*",
    "behavioral:*",
    "self_improve:*",
    "metrics:*",
    "kg:node:*",
    "dream:*",
    "cpi:*",
    "epistemic:*",
    "temporal:*",
    "saccadic:*",
    "goal:*",          # Per-goal state (was leaking across resets)
    "capability:*",    # Capability engine state
    "exec:*",          # Execution traces
    "reflection:*",    # Per-reflection state
    "economics:*",     # Token / cost ledger
    "perception:*",    # Background perception state
]
_REDIS_WIPE_EXACT = [
    "goals",
    "agents",
    "custom_tasks",
    "events:saccadic",
    "scheduler:job_state",
]

# Filesystem dirs cleared by PANIC reset (contents only).
# Panic NEVER includes /data/browser_sessions (login state, expensive to recreate)
# or /data/logs (forensic value — needed to diagnose what triggered the panic).
_FS_WIPE_DIRS = [
    "/data/memory",                # episodic + self_model.json file backup
    "/data/src_patches",           # self-improve patches re-applied at boot
    "/data/self_improve_backups",  # self-improve change history
    "/data/patches",               # legacy patches dir
    "/data/skills",                # custom Python skills can be the cause of runaway
    "/data/chat-uploads",          # was "/data/uploads" — wrong path bug
    "/data/screenshots",
    "/data/shared",
]

# FACTORY reset adds these on top of _FS_WIPE_DIRS.
# Factory wipes everything Panic wipes PLUS browser logins and forensic logs —
# leaves the platform "as if never used". Use case: pre-release prep, demo
# handoff, GitHub baseline. Cannot wipe .env from inside container (use
# scripts/factory_reset.sh --wipe-env for that).
_FACTORY_EXTRA_FS_DIRS = [
    "/data/browser_sessions",
    "/data/logs",
]

# Config files to restore from canonical default rather than delete.
# Operator (or self-improve) edits to prime.md can be the SOURCE of cognitive
# corruption, so panic reset must restore it to the byte-identical default.
_CONFIG_RESTORE_PAIRS = [
    ("/data/config/prime.md", "/data/config/prime.default.md"),
]

# DB tables to truncate (children before parents — FK-safe order)
_TRUNCATE_TABLES = [
    "knowledge_relations",
    "knowledge_nodes",
    "learning_examples",
    "behavioral_rules",
    "world_timeline",
    "procedural_memory",
    "visual_memory",
    "memory_embeddings",
    "memory_entries",
    "memory_snapshots",
    "execution_reflections",
    "execution_knowledge",
    "goal_memory",
    "entity_states",
    "state_predictions",
    "dream_log",
    "skill_patterns",
    "agent_messages",
    "agents",         # persistent agent registry
    "capabilities",   # capability engine state
    "opportunities",  # opportunity engine feed
    # Phase 5 additions — memory truth model. Without these, factory reset
    # would leave declared user attributes (cat name, favourite colour, etc.)
    # in place across a "clean wipe", contradicting the operator's expectation.
    "user_attribute_history",
    "user_attributes",
]

_SELF_MODEL_EMPTY = {
    "version": "1.0",
    "initialized_at": "",
    "strengths": [],
    "known_failures": [],
    "user_preferences": {},   # dict, not list — template calls .items()
    "weekly_stats": {},
    "skill_success_rates": {},
    "notes": "Fresh initialization after panic reset.",
}

# Base cognitive state written to Redis after wipe so agent never starts "broken"
def _base_epistemic(ts: str) -> dict:
    return {"domains": {}, "version": "1.0", "initialized_at": ts}

def _base_cpi(ts: str) -> dict:
    return {
        "cpi": 0, "cpu_percent": 0, "avg_latency_ms": 0,
        "memory_growth": 0, "active_goals": 0, "error_rate": 0,
        "timestamp": ts,
    }


async def _redis_conn(redis_url: str):
    import redis.asyncio as aioredis
    return aioredis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)


@router.get("/", response_class=HTMLResponse)
async def reset_page(request: Request):
    return request.app.state.templates.TemplateResponse(request, "reset.html", {})


@router.post("/execute")
async def reset_execute(request: Request):
    """Execute agent reset. Mode: 'panic' (cognitive only) or 'factory' (full wipe).
    CSRF (via middleware) + body confirmation phrase required."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400)

    mode = (body.get("mode") or "panic").lower()
    if mode not in _CONFIRM_PHRASES:
        return JSONResponse(
            {"ok": False, "error": f"Invalid mode '{mode}'. Use 'panic' or 'factory'."},
            status_code=400,
        )
    confirm_phrase = _CONFIRM_PHRASES[mode]
    factory = (mode == "factory")

    confirm = body.get("confirm", "")
    if confirm != confirm_phrase:
        return JSONResponse(
            {"ok": False, "error": f"Type exactly: {confirm_phrase}"},
            status_code=400,
        )

    user_id = getattr(request.state, "user_id", "")
    scheduler = request.app.state.scheduler
    redis_url = request.app.state.redis_url

    # ── Defense-in-depth: verify session user is an actual admin row ──────────
    if not await _verify_admin(user_id):
        logger.warning("reset.admin_verify_failed", user_id=user_id[:12])
        try:
            async with async_session() as session:
                session.add(AuditLog(
                    id=str(uuid4()),
                    event_type="security.reset_blocked",
                    source="dashboard",
                    action="admin.panic_reset",
                    input_summary=f"user_id={user_id[:32]}",
                    output_summary="non-admin session attempted reset",
                    timestamp=datetime.now(timezone.utc),
                    latency_ms=0,
                    user_id="",
                    chat_id="",
                ))
                await session.commit()
        except Exception:
            pass
        return JSONResponse(
            {"ok": False, "error": "Reset requires admin privileges."},
            status_code=403,
        )

    # ── Rate limit: max 3 attempts per user per 5 minutes ─────────────────────
    allowed, attempt_count = await _check_rate_limit(redis_url, user_id)
    if not allowed:
        logger.warning("reset.rate_limited", user_id=user_id[:12], count=attempt_count)
        try:
            async with async_session() as session:
                session.add(AuditLog(
                    id=str(uuid4()),
                    event_type="security.reset_rate_limited",
                    source="dashboard",
                    action="admin.panic_reset",
                    input_summary=f"user_id={user_id[:32]}",
                    output_summary=f"attempt={attempt_count} window={_RESET_RATE_WINDOW}s",
                    timestamp=datetime.now(timezone.utc),
                    latency_ms=0,
                    user_id="",
                    chat_id="",
                ))
                await session.commit()
        except Exception:
            pass
        return JSONResponse(
            {"ok": False, "error": (
                f"Too many reset attempts. "
                f"Max {_RESET_RATE_MAX} per {_RESET_RATE_WINDOW//60} minutes. "
                "Wait before trying again."
            )},
            status_code=429,
        )

    # ── PART 0: Reset lock — prevent double reset / race conditions ───────────
    try:
        _r = await _redis_conn(redis_url)
        try:
            already = await _r.get(LOCK_KEY)
            if already:
                return JSONResponse(
                    {"ok": False, "error": "Reset already in progress — try again in a moment."},
                    status_code=409,
                )
            await _r.set(LOCK_KEY, "1", ex=LOCK_TTL)
        finally:
            await _r.aclose()
    except Exception as exc:
        logger.exception("reset.lock_error")
        return JSONResponse(
            {"ok": False, "error": f"Could not acquire reset lock: {str(exc).splitlines()[0][:80]}"},
            status_code=500,
        )

    steps: list[dict] = []
    paused_jobs: list[str] = []

    try:
        # ── STEP 1: Pause all scheduler jobs ──────────────────────────────────
        try:
            if scheduler:
                for job in scheduler.list_jobs():
                    name = job["name"]
                    await scheduler.pause(name)
                    paused_jobs.append(name)
            steps.append({"step": "scheduler_paused", "ok": True,
                          "detail": f"{len(paused_jobs)} jobs paused"})
        except Exception:
            logger.exception("reset.pause_scheduler_error")
            steps.append({"step": "scheduler_paused", "ok": False, "detail": "Pause error — continuing"})

        # ── STEP 2: Clear active goals from Redis ──────────────────────────────
        try:
            _r = await _redis_conn(redis_url)
            try:
                goal_count = await _r.hlen("goals")
                await _r.delete("goals")
            finally:
                await _r.aclose()
            steps.append({"step": "goals_cleared", "ok": True,
                          "detail": f"{goal_count} goals removed"})
        except Exception:
            logger.exception("reset.clear_goals_error")
            steps.append({"step": "goals_cleared", "ok": False, "detail": "Goals clear error"})

        # ── STEP 3: Database cleanup ───────────────────────────────────────────
        truncated: list[str] = []
        db_errors: list[str] = []
        try:
            async with async_session() as session:
                # Defense-in-depth: _TRUNCATE_TABLES is a module-level constant,
                # but we re-check each entry against a strict identifier regex
                # so any future code that mutates the list (or wires user input
                # into it) fails loudly instead of enabling SQL injection.
                import re as _re_ident
                _SAFE_IDENT = _re_ident.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
                for table in _TRUNCATE_TABLES:
                    if not _SAFE_IDENT.match(table):
                        db_errors.append(f"{table}: rejected (unsafe identifier)")
                        continue
                    try:
                        await session.execute(text(f"DELETE FROM {table}"))
                        truncated.append(table)
                    except Exception as te:
                        db_errors.append(f"{table}: {str(te).splitlines()[0][:50]}")

                # Audit log: panic keeps last 100 rows for forensics; factory wipes all
                try:
                    if factory:
                        await session.execute(text("DELETE FROM audit_log"))
                        truncated.append("audit_log(full)")
                    else:
                        await session.execute(text("""
                            DELETE FROM audit_log
                            WHERE id NOT IN (
                                SELECT id FROM audit_log
                                ORDER BY timestamp DESC
                                LIMIT 100
                            )
                        """))
                        truncated.append("audit_log(trimmed)")
                except Exception as te:
                    db_errors.append(f"audit_log: {str(te).splitlines()[0][:50]}")

                await session.commit()


            steps.append({
                "step": "db_cleaned", "ok": len(db_errors) == 0,
                "detail": f"{len(truncated)} tables cleared" +
                          (f" — errors: {'; '.join(db_errors[:3])}" if db_errors else ""),
            })
        except Exception:
            logger.exception("reset.db_cleanup_error")
            steps.append({"step": "db_cleaned", "ok": False, "detail": "DB cleanup failed"})

        # ── STEP 3b: VACUUM FULL — reclaim disk space (must run outside transaction) ──
        try:
            async with engine.connect() as conn:
                await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn.execute(text("VACUUM FULL ANALYZE"))
            steps.append({"step": "db_vacuumed", "ok": True, "detail": "disk space reclaimed"})
        except Exception:
            logger.exception("reset.vacuum_error")
            steps.append({"step": "db_vacuumed", "ok": False, "detail": "VACUUM error — data still cleared"})

        # ── STEP 4: Redis cleanup ──────────────────────────────────────────────
        # Panic: pattern-based wipe (preserves sessions, csrf, login-rate, vault).
        # Factory: full FLUSHDB then re-set lock (everything goes — sessions
        # invalidated, vault reloads from .env at next boot).
        try:
            _r = await _redis_conn(redis_url)
            try:
                if factory:
                    # Full wipe — re-set lock immediately to prevent races
                    await _r.flushdb()
                    await _r.set(LOCK_KEY, "1", ex=LOCK_TTL)
                    # ── Option A: post-factory-reset NO_REHYDRATE sentinel ─────
                    # The agent-core boot logic checks this key. When present
                    # it suppresses all .env-based auto-imports (Telegram vault
                    # mirror, Gmail credential seed, LLM provider auto-detect).
                    # Survives any number of restarts until manually cleared
                    # via dashboard. Forces operator to configure all secrets
                    # explicitly via the Integrations panel — symmetric reset.
                    await _r.set("system:no_rehydrate", "1")
                    deleted_count = -1  # signal "all"
                else:
                    deleted_count = 0
                    for pattern in _REDIS_WIPE_PATTERNS:
                        cursor = 0
                        while True:
                            cursor, keys = await _r.scan(cursor, match=pattern, count=200)
                            if keys:
                                safe_keys = [k for k in keys if k != LOCK_KEY]
                                if safe_keys:
                                    await _r.delete(*safe_keys)
                                    deleted_count += len(safe_keys)
                            if cursor == 0:
                                break
                    for key in _REDIS_WIPE_EXACT:
                        if key != LOCK_KEY and await _r.exists(key):
                            await _r.delete(key)
                            deleted_count += 1
            finally:
                await _r.aclose()
            detail = "FLUSHDB (factory mode)" if factory else f"{deleted_count} keys deleted"
            steps.append({"step": "redis_cleaned", "ok": True, "detail": detail})
        except Exception:
            logger.exception("reset.redis_cleanup_error")
            steps.append({"step": "redis_cleaned", "ok": False, "detail": "Redis clean error"})

        # ── STEP 5: Filesystem cleanup ─────────────────────────────────────────
        effective_fs_dirs = _FS_WIPE_DIRS + (_FACTORY_EXTRA_FS_DIRS if factory else [])
        fs_cleaned = 0
        fs_errors: list[str] = []
        for dirpath in effective_fs_dirs:
            if not os.path.isdir(dirpath):
                continue
            try:
                for entry in os.listdir(dirpath):
                    full = os.path.join(dirpath, entry)
                    try:
                        if os.path.isfile(full) or os.path.islink(full):
                            os.unlink(full)
                        elif os.path.isdir(full):
                            shutil.rmtree(full)
                        fs_cleaned += 1
                    except Exception as fe:
                        fs_errors.append(f"{entry}: {str(fe)[:40]}")
            except Exception as de:
                fs_errors.append(f"{dirpath}: {str(de)[:40]}")
        steps.append({
            "step": "filesystem_cleaned", "ok": len(fs_errors) == 0,
            "detail": f"{fs_cleaned} items removed" +
                      (f" — errors: {'; '.join(fs_errors[:3])}" if fs_errors else ""),
        })

        # ── STEP 5b: Restore canonical config files (prime.md → default) ───────
        cfg_restored = 0
        cfg_errors: list[str] = []
        for target, source in _CONFIG_RESTORE_PAIRS:
            try:
                if not os.path.isfile(source):
                    cfg_errors.append(f"{os.path.basename(source)}: source missing")
                    continue
                # Unlink target before copy: handles ownership mismatch when target
                # was created by another UID (e.g., root-owned prime.md from a host
                # `cp` while agent-core runs as UID 1000). The directory is agent-
                # owned, so unlink is permitted regardless of file owner.
                if os.path.exists(target):
                    try:
                        os.unlink(target)
                    except OSError:
                        pass  # let copyfile try anyway and surface the real error
                shutil.copyfile(source, target)
                cfg_restored += 1
            except Exception as ce:
                cfg_errors.append(f"{os.path.basename(target)}: {str(ce)[:50]}")
        steps.append({
            "step": "config_restored", "ok": len(cfg_errors) == 0,
            "detail": f"{cfg_restored} file(s) restored from default" +
                      (f" — errors: {'; '.join(cfg_errors[:3])}" if cfg_errors else ""),
        })

        # ── STEP 6: Failsafe reinit — write minimal valid cognitive state ──────
        # Ensures agent never starts in a broken state after the Redis wipe.
        reinit_errors: list[str] = []
        ts_now = datetime.now(timezone.utc).isoformat()
        try:
            os.makedirs("/data/memory", exist_ok=True)
            sm = dict(_SELF_MODEL_EMPTY)
            sm["initialized_at"] = ts_now
            with open("/data/memory/self_model.json", "w") as f:
                json.dump(sm, f, indent=2)
        except Exception as e:
            reinit_errors.append(f"self_model: {str(e).splitlines()[0][:50]}")

        try:
            _r = await _redis_conn(redis_url)
            try:
                await _r.set("agent:epistemic", json.dumps(_base_epistemic(ts_now)))
                await _r.set("agent:cpi",       json.dumps(_base_cpi(ts_now)))
            finally:
                await _r.aclose()
        except Exception as e:
            reinit_errors.append(f"redis_reinit: {str(e).splitlines()[0][:50]}")

        # Reset agent identity (born_at → now, total_xp → 0) so life/experience counters restart
        try:
            async with async_session() as session:
                await session.execute(text(
                    "UPDATE agent_identity SET born_at = :ts, total_xp = 0 WHERE id = 1"
                ), {"ts": datetime.now(timezone.utc)})
                await session.commit()
        except Exception as e:
            reinit_errors.append(f"identity_reset: {str(e).splitlines()[0][:50]}")

        steps.append({
            "step": "failsafe_reinit", "ok": len(reinit_errors) == 0,
            "detail": "self_model + epistemic + CPI + identity initialized" if not reinit_errors
                      else f"partial: {'; '.join(reinit_errors)}",
        })

        # ── STEP 7: Set fresh boot flag ────────────────────────────────────────
        try:
            _r = await _redis_conn(redis_url)
            try:
                await _r.set("agent:is_fresh", "1")
                await _r.set("agent:days_alive", "0")
            finally:
                await _r.aclose()
            steps.append({"step": "fresh_flag_set", "ok": True, "detail": "agent:is_fresh = 1"})
        except Exception:
            logger.exception("reset.fresh_flag_error")
            steps.append({"step": "fresh_flag_set", "ok": False, "detail": "Fresh flag error"})

        # ── STEP 8: Resume all scheduler jobs ─────────────────────────────────
        try:
            resumed = 0
            if scheduler:
                for name in paused_jobs:
                    await scheduler.resume(name)
                    resumed += 1
            steps.append({"step": "scheduler_resumed", "ok": True,
                          "detail": f"{resumed} jobs resumed"})
        except Exception:
            logger.exception("reset.resume_scheduler_error")
            steps.append({"step": "scheduler_resumed", "ok": False, "detail": "Resume error"})

        # ── STEP 9: Audit log ──────────────────────────────────────────────────
        try:
            async with async_session() as session:
                session.add(AuditLog(
                    id=str(uuid4()),
                    event_type="AGENT_FACTORY_RESET_EXECUTED" if factory else "AGENT_RESET_EXECUTED",
                    source="dashboard",
                    action="admin.factory_reset" if factory else "admin.panic_reset",
                    input_summary=f"user={user_id} mode={mode}",
                    output_summary=f"{len(steps)} steps, ok={sum(1 for s in steps if s['ok'])}",
                    timestamp=datetime.now(timezone.utc),
                    latency_ms=0,
                ))
                await session.commit()
            steps.append({"step": "audit_logged", "ok": True, "detail": f"user={user_id} mode={mode}"})
        except Exception:
            logger.exception("reset.audit_log_error")
            steps.append({"step": "audit_logged", "ok": False, "detail": "Audit log error"})

    finally:
        # ── STEP 10: Release lock — always, even on unexpected exception ───────
        try:
            _r = await _redis_conn(redis_url)
            await _r.delete(LOCK_KEY)
            await _r.aclose()
        except Exception:
            logger.exception("reset.lock_release_error")

    overall_ok = all(s["ok"] for s in steps)
    logger.info("agent.panic_reset_completed", user_id=user_id,
                ok=overall_ok, steps_total=len(steps),
                steps_ok=sum(1 for s in steps if s["ok"]))

    return JSONResponse({
        "ok": overall_ok,
        "steps": steps,
        "message": (
            "Agent brain reset complete. Boot sequence will activate on first message."
            if overall_ok else
            "Reset completed with errors — check steps for details."
        ),
    })
