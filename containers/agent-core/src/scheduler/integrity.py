"""Self-Integrity Monitor — cross-checks self-model claims against observed reality.

Runs every 6 hours. Performs three checks:

  1. Strength validation: claimed strengths in self-model vs actual skill success rates
  2. Epistemic drift: domain confidence values vs skill execution outcomes
  3. Audit anomalies: error spikes in audit_log over last 24h

Findings are written to Redis key ``agent:integrity_report`` as structured JSON
so the cognitive dashboard and the agent itself can inspect them.

If discrepancies exceed severity thresholds, the self-model is automatically
corrected and improvement items are queued.
"""
from __future__ import annotations

import json
import structlog
from datetime import datetime, timezone
from sqlalchemy import text

import redis.asyncio as aioredis

from ..db.session import async_session

logger = structlog.get_logger()

INTEGRITY_REPORT_KEY = "agent:integrity_report"
# How many execution samples are needed before we trust a skill rate
MIN_SAMPLES = 3
# A "strength" requires ≥ 70% success rate to be considered valid
STRENGTH_MIN_SUCCESS_RATE = 0.70
# Epistemic drift threshold: flag if |epistemic_conf - actual_rate| > this value
EPISTEMIC_DRIFT_THRESHOLD = 0.20

# Skill name → domain mapping (same domains as epistemic.py)
_SKILL_TO_DOMAIN: dict[str, str] = {
    "web_search":       "web_scraping",
    "browser":          "web_scraping",
    "fetch_url":        "web_scraping",
    "scrape":           "web_scraping",
    "python_exec":      "programming",
    "shell":            "programming",
    "http_request":     "programming",
    "read_file":        "programming",
    "write_file":       "programming",
    "calculate":        "data_analysis",
    "summarize":        "data_analysis",
    "subscribe":        "automation",
    "reminder":         "automation",
    "skill_manager":    "programming",
    "self_improve":     "programming",
    "integration":      "automation",
    "memory_search":    "programming",
    "memory_store":     "programming",
}

# Strength keywords → likely skill names they refer to
_STRENGTH_KEYWORDS: dict[str, list[str]] = {
    "web scraping":        ["browser", "fetch_url", "scrape", "web_search"],
    "scraping":            ["browser", "fetch_url", "scrape"],
    "browser":             ["browser"],
    "python":              ["python_exec"],
    "shell":               ["shell"],
    "python_exec":         ["python_exec"],
    "búsqueda web":        ["web_search"],
    "web_search":          ["web_search"],
    "búsqueda":            ["web_search"],
    "crypto":              ["web_search", "http_request", "fetch_url"],
    "automatización":      ["shell", "python_exec"],
    "automatizacion":      ["shell", "python_exec"],
    "automation":          ["shell", "python_exec"],
    "análisis":            ["calculate", "python_exec"],
    "analisis":            ["calculate", "python_exec"],
    "http":                ["http_request", "fetch_url"],
    "api":                 ["http_request", "fetch_url"],
}


class SelfIntegrityMonitorJob:
    """Cross-checks self-model claims against reality every 6 hours."""

    def __init__(self, redis_url: str, bus=None, notify_chat_id: str = "") -> None:
        self.redis_url = redis_url
        self.bus = bus
        self.notify_chat_id = notify_chat_id

    async def __call__(self) -> str:
        try:
            return await self._run()
        except Exception:
            logger.exception("integrity_monitor.error")
            return "integrity_monitor: error (see logs)"

    async def _run(self) -> str:
        r = aioredis.from_url(self.redis_url, decode_responses=True)
        try:
            self_model = await self._load_self_model(r)
            epistemic = await self._load_epistemic(r)
            audit_anomalies = await self._check_audit_log()
        finally:
            await r.aclose()

        skill_rates = self_model.get("skill_success_rates", {})
        findings: list[dict] = []
        corrections: list[str] = []

        # ── Check 1: Strength validation ──────────────────────────────────
        strengths = self_model.get("strengths", [])
        invalid_strengths: list[str] = []
        for strength in strengths:
            relevant_skills = self._resolve_skills_for_strength(strength)
            if not relevant_skills:
                continue  # Can't evaluate — skip
            rates = []
            for skill in relevant_skills:
                entry = skill_rates.get(skill)
                if entry:
                    total = entry.get("success", 0) + entry.get("failure", 0)
                    if total >= MIN_SAMPLES:
                        rates.append(entry.get("success", 0) / total)
            if not rates:
                continue  # No data yet — skip
            avg_rate = sum(rates) / len(rates)
            if avg_rate < STRENGTH_MIN_SUCCESS_RATE:
                findings.append({
                    "type": "invalid_strength",
                    "severity": "medium",
                    "claim": strength,
                    "actual_rate": round(avg_rate, 2),
                    "threshold": STRENGTH_MIN_SUCCESS_RATE,
                    "detail": (
                        f"Claimed strength '{strength}' has only {avg_rate:.0%} actual "
                        f"success rate (min {STRENGTH_MIN_SUCCESS_RATE:.0%})"
                    ),
                })
                invalid_strengths.append(strength)

        # ── Check 2: Epistemic drift ───────────────────────────────────────
        domain_confidence = epistemic.get("domain_confidence", {})
        for skill_name, domain in _SKILL_TO_DOMAIN.items():
            entry = skill_rates.get(skill_name)
            if not entry:
                continue
            total = entry.get("success", 0) + entry.get("failure", 0)
            if total < MIN_SAMPLES:
                continue
            actual_rate = entry.get("success", 0) / total
            epistemic_conf = domain_confidence.get(domain)
            if epistemic_conf is None:
                continue
            drift = abs(epistemic_conf - actual_rate)
            if drift > EPISTEMIC_DRIFT_THRESHOLD:
                findings.append({
                    "type": "epistemic_drift",
                    "severity": "low" if drift < 0.35 else "medium",
                    "domain": domain,
                    "skill": skill_name,
                    "epistemic_confidence": round(epistemic_conf, 2),
                    "actual_rate": round(actual_rate, 2),
                    "drift": round(drift, 2),
                    "detail": (
                        f"Domain '{domain}' epistemic confidence={epistemic_conf:.0%} "
                        f"but skill '{skill_name}' actual rate={actual_rate:.0%} "
                        f"(drift={drift:.0%})"
                    ),
                })

        # ── Check 3: Audit log anomalies ──────────────────────────────────
        findings.extend(audit_anomalies)

        # ── Check 4: Cognitive system heartbeats ──────────────────────────
        # For each cognitive subsystem in the ownership map, verify it has
        # written something in the last 24h. A silent producer is a
        # regression even when no error appears in logs.
        try:
            heartbeat_findings = await self._check_cognitive_heartbeats()
            findings.extend(heartbeat_findings)
        except Exception:
            logger.exception("integrity_monitor.heartbeat_error")

        # ── Auto-corrections ───────────────────────────────────────────────
        if invalid_strengths:
            await self._remove_invalid_strengths(invalid_strengths)
            for s in invalid_strengths:
                corrections.append(f"Removed low-accuracy strength: '{s}'")
                improvement = (
                    f"Improve reliability of {s}: success rate below {STRENGTH_MIN_SUCCESS_RATE:.0%}"
                )
                await self._queue_improvement(improvement)

        # ── Actuator: correct epistemic drift automatically ────────────────
        for f in findings:
            if f["type"] == "epistemic_drift" and f.get("drift", 0) > EPISTEMIC_DRIFT_THRESHOLD:
                await self._correct_epistemic(f["domain"], f["actual_rate"])
                corrections.append(f"Corrected epistemic {f['domain']} confidence → {f['actual_rate']:.0%}")

        # ── Write report ───────────────────────────────────────────────────
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "findings": findings,
            "corrections": corrections,
            "summary": {
                "total_findings": len(findings),
                "invalid_strengths": len(invalid_strengths),
                "epistemic_drifts": sum(1 for f in findings if f["type"] == "epistemic_drift"),
                "audit_anomalies": len(audit_anomalies),
                "auto_corrections": len(corrections),
            },
        }
        r2 = aioredis.from_url(self.redis_url, decode_responses=True)
        try:
            await r2.set(INTEGRITY_REPORT_KEY, json.dumps(report))
        finally:
            await r2.aclose()

        severity_counts = {"medium": 0, "low": 0}
        for f in findings:
            severity_counts[f.get("severity", "low")] = severity_counts.get(f.get("severity", "low"), 0) + 1

        logger.info(
            "integrity_monitor.complete",
            findings=len(findings),
            corrections=len(corrections),
            medium=severity_counts.get("medium", 0),
        )

        # ── Notify user if medium-severity issues found ────────────────────
        medium_findings = [f for f in findings if f.get("severity") == "medium"]
        if medium_findings and self.bus and self.notify_chat_id:
            lines = ["⚠️ *Integridad del agente — hallazgos:*"]
            for mf in medium_findings[:3]:
                lines.append(f"• {mf['detail']}")
            if corrections:
                lines.append(f"\n✅ Auto-correcciones: {len(corrections)}")
            try:
                from ..events.types import EventType
                await self.bus.publish("events:outgoing", {
                    "event_type": EventType.TELEGRAM_RESPONSE,
                    "chat_id": str(self.notify_chat_id),
                    "text": "\n".join(lines),
                })
            except Exception:
                pass

        return (
            f"integrity_monitor: {len(findings)} findings "
            f"({severity_counts.get('medium', 0)} medium, "
            f"{severity_counts.get('low', 0)} low), "
            f"{len(corrections)} auto-corrections"
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _check_cognitive_heartbeats(self) -> list[dict]:
        """For each cognitive system, verify it has fresh writes (last 24h).

        Mirrors docs/cognitive_systems.md ownership map. A silent producer
        is a real regression even with no errors in logs.

        Returns a list of findings (severity=low).
        """
        findings: list[dict] = []
        # DB-backed systems — table name MUST match db/models.py __tablename__.
        # ts_col is the canonical "last touched" column for that system.
        DB_TABLES = [
            ("knowledge_nodes",   "knowledge_graph", "updated_at"),
            ("world_timeline",    "timeline",        "observed_at"),
            ("visual_memory",     "visual_memory",   "created_at"),
            ("memory_entries",    "episodic",        "timestamp"),
            ("procedural_memory", "procedural",      "created_at"),
            ("behavioral_rules",  "behavioral",      "created_at"),
            ("dream_log",         "dream",           "created_at"),
            ("goal_memory",       "goal_memory",     "created_at"),
        ]
        # Each table gets its OWN session — a failure on one table (e.g. it
        # doesn't exist on this install, or its column was renamed) must not
        # poison the connection for the rest.
        # Defense-in-depth: DB_TABLES is hard-coded above but we re-check each
        # identifier against a strict regex so a future refactor wiring user
        # input here fails loudly instead of enabling SQL injection.
        import re as _re_ident
        _SAFE_IDENT = _re_ident.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
        for table, system_name, ts_col in DB_TABLES:
            if not _SAFE_IDENT.match(table) or not _SAFE_IDENT.match(ts_col):
                logger.warning("integrity.unsafe_identifier_skipped",
                               table=table, ts_col=ts_col)
                continue
            try:
                async with async_session() as session:
                    result = await session.execute(text(
                        f"SELECT COUNT(*) AS recent FROM {table} "
                        f"WHERE {ts_col} > NOW() - INTERVAL '24 hours'"
                    ))
                    row = result.fetchone()
                    recent = int(row[0]) if row and row[0] is not None else 0
                    if recent == 0:
                        findings.append({
                            "type": "cognitive_silent",
                            "severity": "low",
                            "system": system_name,
                            "table": table,
                            "detail": (
                                f"Cognitive system '{system_name}' has had ZERO writes "
                                f"to '{table}' in the last 24h. Producer may be broken."
                            ),
                        })
            except Exception as e:
                # Table may not exist on a fresh install OR column renamed.
                # Log at debug; do NOT bubble — heartbeat check is best-effort.
                logger.debug("integrity.heartbeat.skip", table=table, ts_col=ts_col, error=str(e)[:120])

        # Redis-backed systems
        REDIS_KEYS = [
            ("agent:self_model", "self_model"),
            ("agent:epistemic",  "epistemic"),
        ]
        try:
            r = aioredis.from_url(self.redis_url, decode_responses=True)
            try:
                for key, system_name in REDIS_KEYS:
                    raw = await r.get(key)
                    if not raw:
                        findings.append({
                            "type": "cognitive_silent",
                            "severity": "low",
                            "system": system_name,
                            "key": key,
                            "detail": (
                                f"Cognitive system '{system_name}' has NO record in Redis "
                                f"({key}). Producer may have never fired."
                            ),
                        })
            finally:
                await r.aclose()
        except Exception:
            logger.exception("integrity.heartbeat.redis_error")

        return findings

    async def _load_self_model(self, r) -> dict:
        try:
            raw = await r.get("agent:self_model")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return {}

    async def _load_epistemic(self, r) -> dict:
        try:
            raw = await r.get("agent:epistemic")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return {}

    async def _check_audit_log(self) -> list[dict]:
        """Detect error spikes in the last 24 hours from audit_log.

        Groups by BOTH event_type AND action so the cognitive decision layer
        can match findings to specific skills (e.g. 'skill.read_file') rather
        than just umbrella categories ('skill.restricted').
        """
        anomalies: list[dict] = []
        try:
            async with async_session() as session:
                result = await session.execute(text("""
                    SELECT
                        event_type,
                        action,
                        COUNT(*) AS total,
                        COUNT(CASE WHEN error IS NOT NULL THEN 1 END) AS errors
                    FROM audit_log
                    WHERE timestamp > NOW() - INTERVAL '24 hours'
                    GROUP BY event_type, action
                    HAVING COUNT(*) >= 5
                    ORDER BY errors DESC
                    LIMIT 10
                """))
                for row in result.fetchall():
                    event_type, action_name, total, errors = row[0], row[1], row[2], row[3]
                    if total > 0 and errors / total > 0.5:
                        # The cognitive layer matches by skill name in event_type.
                        # Use the more specific 'action' (e.g. 'skill.read_file')
                        # as the event_type so per-skill matching fires.
                        specific_event = action_name or event_type
                        anomalies.append({
                            "type": "audit_error_spike",
                            "severity": "medium" if errors / total > 0.7 else "low",
                            "event_type": specific_event,
                            "umbrella_event_type": event_type,
                            "error_rate": round(errors / total, 2),
                            "total_events": total,
                            "detail": (
                                f"'{specific_event}' has {errors}/{total} errors "
                                f"in last 24h ({errors / total:.0%} error rate)"
                            ),
                        })
        except Exception:
            pass
        return anomalies

    def _resolve_skills_for_strength(self, strength: str) -> list[str]:
        """Map a strength description to likely skill names."""
        strength_lower = strength.lower()
        for keyword, skills in _STRENGTH_KEYWORDS.items():
            if keyword in strength_lower:
                return skills
        return []

    async def _remove_invalid_strengths(self, to_remove: list[str]) -> None:
        """Remove falsely claimed strengths from the self-model."""
        try:
            r = aioredis.from_url(self.redis_url, decode_responses=True)
            try:
                raw = await r.get("agent:self_model")
                if not raw:
                    return
                model = json.loads(raw)
                model["strengths"] = [
                    s for s in model.get("strengths", []) if s not in to_remove
                ]
                model["updated_at"] = datetime.now(timezone.utc).isoformat()
                await r.set("agent:self_model", json.dumps(model))
                await r.incr("agent:self_model:version")
            finally:
                await r.aclose()
        except Exception:
            pass

    async def _correct_epistemic(self, domain: str, actual_rate: float) -> None:
        """Nudge epistemic confidence toward observed reality."""
        try:
            r = aioredis.from_url(self.redis_url, decode_responses=True)
            try:
                raw = await r.get("agent:epistemic")
                if not raw:
                    return
                state = json.loads(raw)
                current = state.get("domain_confidence", {}).get(domain)
                if current is None:
                    return
                # Move halfway toward actual rate (conservative correction)
                corrected = round(current + (actual_rate - current) * 0.5, 3)
                state["domain_confidence"][domain] = max(0.02, min(0.98, corrected))
                await r.set("agent:epistemic", json.dumps(state))
                logger.info("integrity_monitor.epistemic_corrected", domain=domain,
                            old=current, new=corrected, actual=actual_rate)
            finally:
                await r.aclose()
        except Exception:
            pass

    async def _queue_improvement(self, item: str) -> None:
        """Add item to self-model improvement_queue."""
        try:
            r = aioredis.from_url(self.redis_url, decode_responses=True)
            try:
                raw = await r.get("agent:self_model")
                if not raw:
                    return
                model = json.loads(raw)
                queue = model.setdefault("improvement_queue", [])
                if item not in queue:
                    queue.append(item)
                    model["improvement_queue"] = queue[-10:]
                    model["updated_at"] = datetime.now(timezone.utc).isoformat()
                    await r.set("agent:self_model", json.dumps(model))
            finally:
                await r.aclose()
        except Exception:
            pass
