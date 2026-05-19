"""Metrics and economics dashboard routes."""

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

from ...db.session import async_session

router = APIRouter()
logger = structlog.get_logger()


@router.get("/", response_class=HTMLResponse)
async def metrics_page(request: Request):
    summary = {}
    econ = {}
    perf_status = {}
    deg_status = {}
    recent = []
    projections = {"hourly_rate": 0, "daily": 0, "weekly": 0, "monthly": 0}

    try:
        from ...observability.metrics import metrics as mc
        from ...observability.economics import economics as ec
        from ...observability.performance import concurrency_guard, degradation_detector

        summary = mc.get_summary()
        econ = ec.get_summary()
        perf_status = concurrency_guard.status()
        deg_status = degradation_detector.get_stats()
        recent = mc.get_recent_tasks(limit=20)

        # Cost projection based on today's burn rate
        now = datetime.now(timezone.utc)
        hours_elapsed = max(now.hour + now.minute / 60, 0.5)  # avoid div/0, min 30 min
        today_cost = econ.get("today", {}).get("cost_usd", 0.0)
        hourly_rate = today_cost / hours_elapsed
        projections = {
            "hourly_rate": round(hourly_rate, 8),
            "daily":       round(hourly_rate * 24, 6),
            "weekly":      round(hourly_rate * 24 * 7, 4),
            "monthly":     round(hourly_rate * 24 * 30, 4),
        }
    except Exception:
        logger.exception("metrics_page.load_error")

    return request.app.state.templates.TemplateResponse(request, "metrics.html", {
        "summary": summary,
        "economics": econ,
        "concurrency": perf_status,
        "degradation": deg_status,
        "recent_tasks": recent,
        "projections": projections,
    })


@router.get("/api/summary")
async def metrics_api(request: Request):
    """JSON endpoint for metrics summary."""
    try:
        from ...observability.metrics import metrics as mc
        from ...observability.economics import economics as ec
        return JSONResponse({
            "metrics": mc.get_summary(),
            "economics": ec.get_summary(),
        })
    except Exception as exc:
        logger.exception("metrics_api.error")
        return JSONResponse({"ok": False, "error": str(exc).splitlines()[0][:120]}, status_code=500)


@router.get("/api/trend")
async def metrics_trend(
    request: Request,
    time_range: str = Query(default="24h", alias="range", pattern="^(24h|7d|30d)$"),
):
    """Audit-log based trend data for time-range selectors.

    Returns hourly (24h) or daily (7d/30d) event/error counts and avg latency.
    """
    now = datetime.now(timezone.utc)

    if time_range == "24h":
        cutoff = now - timedelta(hours=24)
        bucket_sql = "date_trunc('hour', timestamp)"
        bucket_fmt = "%Y-%m-%dT%H:00"
        n_buckets = 24
        delta = timedelta(hours=1)
    elif time_range == "7d":
        cutoff = now - timedelta(days=7)
        bucket_sql = "date_trunc('day', timestamp)"
        bucket_fmt = "%Y-%m-%d"
        n_buckets = 7
        delta = timedelta(days=1)
    else:  # 30d
        cutoff = now - timedelta(days=30)
        bucket_sql = "date_trunc('day', timestamp)"
        bucket_fmt = "%Y-%m-%d"
        n_buckets = 30
        delta = timedelta(days=1)

    # Defense-in-depth: bucket_sql is set above from a hard-coded if/elif chain
    # and is never user-controlled. Re-validate before interpolating into raw
    # SQL so any future refactor that introduces user input will fail loudly
    # rather than silently enable SQL injection.
    _ALLOWED_BUCKET_EXPRS = frozenset({
        "date_trunc('hour', timestamp)",
        "date_trunc('day', timestamp)",
    })
    if bucket_sql not in _ALLOWED_BUCKET_EXPRS:
        raise ValueError(f"invalid bucket expression: {bucket_sql!r}")

    try:
        async with async_session() as session:
            rows = await session.execute(
                text(
                    f"SELECT {bucket_sql} as bucket, "
                    "COUNT(*) as total, "
                    "SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors, "
                    "AVG(latency_ms) as avg_latency "
                    "FROM audit_log "
                    "WHERE timestamp >= :cutoff "
                    "GROUP BY bucket "
                    "ORDER BY bucket"
                ),
                {"cutoff": cutoff},
            )
            raw = {
                str(row.bucket.replace(tzinfo=None) if hasattr(row.bucket, "tzinfo") and row.bucket.tzinfo else row.bucket):
                (row.total, row.errors, float(row.avg_latency or 0))
                for row in rows
            }
    except Exception:
        logger.exception("metrics_trend.db_error")
        raw = {}

    # Fill gaps with zeros (all buckets in range)
    buckets = []
    ptr = cutoff
    if time_range == "24h":
        ptr = ptr.replace(minute=0, second=0, microsecond=0)
    else:
        ptr = ptr.replace(hour=0, minute=0, second=0, microsecond=0)

    for _ in range(n_buckets):
        key = ptr.strftime(bucket_fmt)
        total, errors, avg_lat = raw.get(str(ptr.replace(tzinfo=None)), (0, 0, 0.0))
        buckets.append({"label": key, "total": int(total), "errors": int(errors), "avg_latency": round(avg_lat, 1)})
        ptr += delta

    total_events   = sum(b["total"]       for b in buckets)
    total_errors   = sum(b["errors"]      for b in buckets)
    nonzero_lats   = [b["avg_latency"]   for b in buckets if b["avg_latency"] > 0]

    return JSONResponse({
        "range": time_range,
        "buckets": buckets,
        "summary": {
            "total":           total_events,
            "errors":          total_errors,
            "error_rate_pct":  round(total_errors / max(total_events, 1) * 100, 1),
            "avg_latency":     round(sum(nonzero_lats) / max(len(nonzero_lats), 1), 1),
        },
    })


# ── i18n translator metrics ───────────────────────────────────────────────────
@router.get("/api/i18n")
async def i18n_metrics(request: Request) -> JSONResponse:
    """Telemetry for the canonical-message translator.

    Returns Redis-counted metrics (cache hits/misses, LLM calls, failures,
    average latency) for both all-time and the current day. Plus per-day
    counts for the last 7 days. Plus the current cache size and per-language
    breakdown by sampling.
    """
    from datetime import date, timedelta
    import redis.asyncio as aioredis

    redis_url = request.app.state.redis_url
    out: dict = {
        "total": {},
        "today": {},
        "last_7_days": [],
        "cache": {},
    }

    def _hash_to_dict(raw):
        if not raw:
            return {}
        d = {}
        for k, v in raw.items():
            try:
                d[k] = int(v)
            except (TypeError, ValueError):
                d[k] = v
        return d

    def _enrich(metrics: dict) -> dict:
        hits = int(metrics.get("cache_hits", 0))
        misses = int(metrics.get("cache_misses", 0))
        calls = int(metrics.get("llm_calls", 0))
        fails = int(metrics.get("llm_failures", 0))
        lat_sum = int(metrics.get("latency_ms_sum", 0))
        lat_n = int(metrics.get("latency_count", 0))
        total_attempts = hits + misses
        return {
            **metrics,
            "hit_rate_pct": round(hits / total_attempts * 100, 2) if total_attempts else 0.0,
            "fail_rate_pct": round(fails / max(calls + fails, 1) * 100, 2) if (calls or fails) else 0.0,
            "avg_llm_latency_ms": round(lat_sum / lat_n) if lat_n else 0,
        }

    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        try:
            total_raw = await r.hgetall("i18n:metrics:total")
            out["total"] = _enrich(_hash_to_dict(total_raw))

            today = date.today().isoformat()
            today_raw = await r.hgetall(f"i18n:metrics:day:{today}")
            out["today"] = _enrich(_hash_to_dict(today_raw))

            for i in range(7):
                d = (date.today() - timedelta(days=i)).isoformat()
                day_raw = await r.hgetall(f"i18n:metrics:day:{d}")
                out["last_7_days"].append({"date": d, **_enrich(_hash_to_dict(day_raw))})

            # Cache size — sample with SCAN, capped to avoid blocking on huge sets.
            cursor = 0
            total = 0
            by_lang: dict[str, int] = {}
            scanned = 0
            while True:
                cursor, keys = await r.scan(cursor, match="i18n:*", count=300)
                for k in keys:
                    if k.startswith("i18n:metrics"):
                        continue
                    total += 1
                    parts = k.split(":")
                    if len(parts) >= 3:
                        lang = parts[1]
                        by_lang[lang] = by_lang.get(lang, 0) + 1
                scanned += len(keys)
                if cursor == 0 or scanned > 5000:
                    break
            out["cache"] = {
                "total_entries": total,
                "by_lang": dict(sorted(by_lang.items(), key=lambda kv: -kv[1])),
                "scanned": scanned,
            }
        finally:
            await r.aclose()
    except Exception as e:
        logger.warning("metrics.i18n_failed", error=str(e)[:120])
        out["error"] = str(e)[:200]

    return JSONResponse(out)


# ── Truth / security / scheduler metrics (Phase 3 closure) ────────────────────
@router.get("/api/truth")
async def truth_metrics(request: Request) -> JSONResponse:
    """Telemetry for truth-enforcement and security guards.

    Returns counters from ``truth:metrics:total`` and the per-day buckets
    for the last 7 days. Operator can answer:
      - what failed?           (task_outcome_*)
      - how often?             (counter values)
      - which task is unhealthy? (custom_tasks failure_count via /tasks)
      - how often did truth-guards intervene? (honesty_layer_*, url_substitution_blocked, python_exec_security_violation)
    """
    from datetime import date, timedelta
    import redis.asyncio as aioredis

    redis_url = request.app.state.redis_url
    out: dict = {
        "total": {},
        "today": {},
        "last_7_days": [],
    }

    def _hash_to_dict(raw):
        if not raw:
            return {}
        d = {}
        for k, v in raw.items():
            try:
                d[k] = int(v)
            except (TypeError, ValueError):
                d[k] = v
        return d

    def _enrich(metrics: dict) -> dict:
        completed = int(metrics.get("task_outcome_completed", 0))
        timeout = int(metrics.get("task_outcome_timeout", 0))
        exception = int(metrics.get("task_outcome_exception", 0))
        total_outcomes = completed + timeout + exception
        return {
            **metrics,
            "task_failure_rate_pct": round(
                (timeout + exception) / max(total_outcomes, 1) * 100, 2
            ) if total_outcomes else 0.0,
        }

    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        try:
            total_raw = await r.hgetall("truth:metrics:total")
            out["total"] = _enrich(_hash_to_dict(total_raw))

            today = date.today().isoformat()
            today_raw = await r.hgetall(f"truth:metrics:day:{today}")
            out["today"] = _enrich(_hash_to_dict(today_raw))

            for i in range(7):
                d = (date.today() - timedelta(days=i)).isoformat()
                day_raw = await r.hgetall(f"truth:metrics:day:{d}")
                out["last_7_days"].append({"date": d, **_enrich(_hash_to_dict(day_raw))})
        finally:
            await r.aclose()
    except Exception as e:
        logger.warning("metrics.truth_failed", error=str(e)[:120])
        out["error"] = str(e)[:200]

    return JSONResponse(out)
