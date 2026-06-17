"""Supermemory backend adapter for Agent Wasp.

This module intentionally talks to Supermemory over HTTP instead of importing the
SDK. Agent Wasp already ships with httpx, and an HTTP adapter keeps the memory
contract explicit, mockable, and usable against both hosted Supermemory and the
self-hosted local binary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from ..utils.redaction import redact

logger = structlog.get_logger()


@dataclass(frozen=True)
class SupermemorySettings:
    enabled: bool
    api_key: str
    base_url: str
    container_tag: str
    scope: str
    timeout_seconds: float
    context_budget_chars: int
    search_limit: int
    search_threshold: float
    rerank: bool
    rewrite_query: bool
    ingest_enabled: bool
    strict: bool

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_key and self.base_url)


def _normalise_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    return value or "https://api.supermemory.ai"


def _clip(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _get_nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


class SupermemoryClient:
    """Small async client for Supermemory profile/search/ingest paths."""

    def __init__(self, config: SupermemorySettings):
        self.config = config

    @classmethod
    def from_settings(cls, settings) -> "SupermemoryClient":
        backend = str(getattr(settings, "memory_backend", "internal") or "internal").lower()
        return cls(
            SupermemorySettings(
                enabled=backend in {"supermemory", "tandem"},
                api_key=str(getattr(settings, "supermemory_api_key", "") or "").strip(),
                base_url=_normalise_base_url(str(getattr(settings, "supermemory_base_url", "") or "")),
                container_tag=str(getattr(settings, "supermemory_container_tag", "agentwasp") or "agentwasp").strip() or "agentwasp",
                scope=str(getattr(settings, "supermemory_scope", "chat") or "chat").lower(),
                timeout_seconds=float(getattr(settings, "supermemory_timeout_seconds", 1.5) or 1.5),
                context_budget_chars=int(getattr(settings, "supermemory_context_budget_chars", 1800) or 1800),
                search_limit=int(getattr(settings, "supermemory_search_limit", 3) or 3),
                search_threshold=float(getattr(settings, "supermemory_search_threshold", 0.35) or 0.35),
                rerank=bool(getattr(settings, "supermemory_rerank", False)),
                rewrite_query=bool(getattr(settings, "supermemory_rewrite_query", False)),
                ingest_enabled=bool(getattr(settings, "supermemory_ingest_enabled", True)),
                strict=bool(getattr(settings, "supermemory_strict", False)),
            )
        )

    @property
    def configured(self) -> bool:
        return self.config.configured

    def container_for(self, chat_id: str = "", project_id: str | None = None) -> str:
        """Resolve the Supermemory container tag for this request.

        `chat` scope prevents cross-chat leakage. `project` scope lets operators
        share memory across a project. `global` scope uses the raw container tag.
        """
        base = self.config.container_tag
        if self.config.scope == "global":
            return base
        if self.config.scope == "project" and project_id:
            return f"{base}:project:{project_id}"
        if chat_id:
            return f"{base}:chat:{chat_id}"
        return base

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "configured": self.config.configured,
            "base_url": self.config.base_url,
            "container_tag": self.config.container_tag,
            "scope": self.config.scope,
            "timeout_seconds": self.config.timeout_seconds,
            "context_budget_chars": self.config.context_budget_chars,
            "search_limit": self.config.search_limit,
            "strict": self.config.strict,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.config.configured:
            raise RuntimeError("Supermemory is not configured")
        url = f"{self.config.base_url}{path}"
        timeout = httpx.Timeout(self.config.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            if response.content:
                return response.json()
            return {}

    async def add_document(
        self,
        content: str,
        *,
        chat_id: str = "",
        project_id: str | None = None,
        custom_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ingest raw content through Supermemory's document/memory pipeline."""
        if not self.config.ingest_enabled or not self.config.configured:
            return {"ok": False, "skipped": True, "reason": "not_configured_or_disabled"}
        payload: dict[str, Any] = {
            "content": _clip(content, 10_000),
            "containerTag": self.container_for(chat_id, project_id),
        }
        if custom_id:
            payload["customId"] = custom_id
        if metadata:
            payload["metadata"] = metadata
        try:
            data = await self._post("/v3/documents", payload)
            return {"ok": True, "data": data}
        except Exception as exc:  # fail-open by default; memory must not break chat
            logger.warning("supermemory.add_document_failed", error=redact(str(exc))[:180])
            if self.config.strict:
                raise
            return {"ok": False, "error": redact(str(exc))[:180]}

    async def create_memory(
        self,
        content: str,
        *,
        chat_id: str = "",
        project_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        is_static: bool = False,
    ) -> dict[str, Any]:
        """Create an exact memory without running document extraction."""
        if not self.config.ingest_enabled or not self.config.configured:
            return {"ok": False, "skipped": True, "reason": "not_configured_or_disabled"}
        payload = {
            "memories": [{
                "content": _clip(content, 10_000),
                "isStatic": bool(is_static),
                "metadata": metadata or {},
            }],
            "containerTag": self.container_for(chat_id, project_id),
        }
        try:
            data = await self._post("/v4/memories", payload)
            return {"ok": True, "data": data}
        except Exception as exc:
            logger.warning("supermemory.create_memory_failed", error=redact(str(exc))[:180])
            if self.config.strict:
                raise
            return {"ok": False, "error": redact(str(exc))[:180]}

    async def profile(self, query: str, *, chat_id: str = "", project_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "containerTag": self.container_for(chat_id, project_id),
        }
        if query:
            payload.update({
                "q": _clip(query, 1000),
                "threshold": self.config.search_threshold,
                "limit": self.config.search_limit,
                "rerank": self.config.rerank,
                "rewriteQuery": self.config.rewrite_query,
            })
        return await self._post("/v4/profile", payload)

    async def format_context(self, query: str, *, chat_id: str = "", project_id: str | None = None) -> str:
        """Return a compact, budget-bounded Supermemory context block."""
        if not self.config.configured:
            if self.config.enabled:
                return "[SUPERMEMORY: enabled but not configured — set SUPERMEMORY_API_KEY and SUPERMEMORY_BASE_URL]"
            return ""
        try:
            data = await self.profile(query, chat_id=chat_id, project_id=project_id)
        except Exception as exc:
            logger.warning("supermemory.context_failed", error=redact(str(exc))[:180])
            if self.config.strict:
                raise
            return "[SUPERMEMORY: unavailable this turn — continuing with local context]"
        return self._format_profile_response(data)

    def _format_profile_response(self, data: dict[str, Any]) -> str:
        profile = data.get("profile") if isinstance(data, dict) else {}
        if profile is None:
            profile = {}
        static = [str(x).strip() for x in _as_list(profile.get("static")) if str(x).strip()]
        dynamic = [str(x).strip() for x in _as_list(profile.get("dynamic")) if str(x).strip()]

        search_obj = data.get("searchResults") or data.get("search_results") or {}
        results = search_obj.get("results") if isinstance(search_obj, dict) else []
        memories: list[str] = []
        for result in _as_list(results):
            if isinstance(result, dict):
                memory = result.get("memory") or result.get("content") or result.get("summary") or result.get("title")
                score = result.get("similarity") or result.get("score")
                if memory:
                    prefix = f"({float(score):.2f}) " if isinstance(score, (int, float)) else ""
                    memories.append(prefix + str(memory).strip())
            elif result:
                memories.append(str(result).strip())

        lines: list[str] = []
        if static:
            lines.append("Static profile:")
            lines.extend(f"- {_clip(item, 220)}" for item in static[:4])
        if dynamic:
            lines.append("Recent context:")
            lines.extend(f"- {_clip(item, 220)}" for item in dynamic[:3])
        if memories:
            lines.append("Relevant memories:")
            lines.extend(f"- {_clip(item, 260)}" for item in memories[: self.config.search_limit])
        if not lines:
            return ""

        block = "[SUPERMEMORY CONTEXT]\n" + "\n".join(lines)
        return _clip(block, self.config.context_budget_chars)
