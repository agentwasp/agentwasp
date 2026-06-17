import json
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from .context_builder import ContextBuilder, ContextPacket
from .forgetting import ForgettingEngine
from .index import MemoryIndex
from .promotion import PromotionEngine
from .snapshot import SnapshotManager
from .store import MemoryStore
from .types import MemoryContent, MemoryQuery, MemoryType, SnapshotInfo

logger = structlog.get_logger()


class MemoryManager:
    """High-level memory API combining filesystem store and PostgreSQL index.

    Integrates:
    - PromotionEngine: topic recurrence → semantic memory
    - ForgettingEngine: TTL + importance decay
    - ContextBuilder: structured context packets for LLM
    """

    def __init__(self):
        from ..config import settings
        from .supermemory_client import SupermemoryClient

        self.backend = str(getattr(settings, "memory_backend", "internal") or "internal").lower()
        self.store = MemoryStore()
        self.index = MemoryIndex()
        self.snapshots = SnapshotManager(self.store)
        self.promotion = PromotionEngine(self)
        self.forgetting = ForgettingEngine(self)
        self.context_builder = ContextBuilder(self)
        self.supermemory = SupermemoryClient.from_settings(settings)

    @property
    def use_internal_store(self) -> bool:
        return self.backend in {"internal", "tandem"}

    @property
    def use_supermemory(self) -> bool:
        return self.backend in {"supermemory", "tandem"}

    async def supermemory_context(self, user_text: str, chat_id: str = "", project_id: str | None = None) -> str:
        if not self.use_supermemory:
            return ""
        return await self.supermemory.format_context(user_text, chat_id=chat_id, project_id=project_id)

    def supermemory_status(self) -> dict:
        status = self.supermemory.status()
        status["backend"] = self.backend
        status["mode"] = "supermemory-only" if self.backend == "supermemory" else self.backend
        return status

    async def store_memory(
        self,
        session: AsyncSession,
        memory_type: MemoryType,
        content: dict,
        summary: str = "",
        tags: list[str] | None = None,
        project_id: str | None = None,
        expires_at: str | None = None,
        importance: float = 0.5,
        mention_count: int = 0,
        source: str = "conversation",
    ) -> MemoryContent:
        """Store a new memory entry (filesystem + index)."""
        entry = MemoryContent(
            memory_type=memory_type,
            project_id=project_id,
            tags=tags or [],
            summary=summary,
            content=content,
            expires_at=expires_at,
            importance_score=importance,
            mention_count=mention_count,
            source=source,
        )

        if self.backend == "supermemory":
            await self.supermemory.create_memory(
                summary or json.dumps(content, ensure_ascii=False),
                project_id=project_id,
                metadata={
                    "memory_type": memory_type.value,
                    "tags": ",".join(tags or []),
                    "source": source,
                    "importance": importance,
                },
                is_static=memory_type in {MemoryType.FACTS, MemoryType.POLICY},
            )
            logger.info(
                "memory.supermemory_only_stored",
                memory_type=memory_type,
                summary=summary[:80] if summary else "",
            )
            return entry

        file_path = self.store.write(entry)
        content_hash = self.store.content_hash(entry)
        await self.index.upsert(session, entry, file_path, content_hash)

        if self.backend == "tandem" and memory_type != MemoryType.EPISODIC:
            await self.supermemory.create_memory(
                summary or json.dumps(content, ensure_ascii=False),
                project_id=project_id,
                metadata={
                    "memory_type": memory_type.value,
                    "tags": ",".join(tags or []),
                    "source": source,
                    "importance": importance,
                    "internal_memory_id": entry.id,
                },
                is_static=memory_type in {MemoryType.FACTS, MemoryType.POLICY},
            )

        logger.info(
            "memory.stored",
            id=entry.id,
            memory_type=memory_type,
            summary=summary[:80] if summary else "",
        )
        return entry

    async def store_working(
        self,
        session: AsyncSession,
        content: dict,
        summary: str = "",
        tags: list[str] | None = None,
        project_id: str | None = None,
        ttl_hours: float | None = None,
        importance: float = 0.5,
    ) -> MemoryContent:
        """Store a working memory entry with optional TTL.

        Working memory is short-lived operational state: reminders,
        tasks, monitors. Set ttl_hours to auto-expire.
        """
        expires_at = None
        if ttl_hours is not None:
            exp = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
            expires_at = exp.isoformat()

        return await self.store_memory(
            session,
            memory_type=MemoryType.WORKING,
            content=content,
            summary=summary,
            tags=tags,
            project_id=project_id,
            expires_at=expires_at,
            importance=importance,
            source="auto",
        )

    async def retrieve(
        self, session: AsyncSession, query: MemoryQuery
    ) -> list[MemoryContent]:
        """Search memory using the PostgreSQL index, then load from filesystem."""
        if self.backend == "supermemory":
            query_text = query.text_search or (query.memory_type.value if query.memory_type else "recent memory")
            block = await self.supermemory.format_context(query_text, project_id=query.project_id)
            if not block:
                return []
            return [MemoryContent(
                memory_type=query.memory_type or MemoryType.SEMANTIC,
                project_id=query.project_id,
                tags=query.tags + ["supermemory"],
                summary=block[:240],
                content={"source": "supermemory", "text": block},
                source="supermemory",
            )]

        rows = await self.index.search(session, query)
        entries = []
        for row in rows:
            entry = self.store.read(MemoryType(row.memory_type), row.id)
            if entry:
                entries.append(entry)
        return entries

    async def get(
        self, session: AsyncSession, memory_type: MemoryType, memory_id: str
    ) -> MemoryContent | None:
        """Get a specific memory entry."""
        return self.store.read(memory_type, memory_id)

    async def update(
        self,
        session: AsyncSession,
        memory_type: MemoryType,
        memory_id: str,
        content: dict | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> MemoryContent | None:
        """Update an existing memory entry."""
        entry = self.store.read(memory_type, memory_id)
        if not entry:
            return None

        if content is not None:
            entry.content = content
        if summary is not None:
            entry.summary = summary
        if tags is not None:
            entry.tags = tags

        entry.version += 1
        entry.updated_at = datetime.now(timezone.utc).isoformat()

        file_path = self.store.write(entry)
        content_hash = self.store.content_hash(entry)
        await self.index.upsert(session, entry, file_path, content_hash)

        return entry

    async def delete(
        self, session: AsyncSession, memory_type: MemoryType, memory_id: str
    ) -> bool:
        """Delete a memory entry from both store and index."""
        deleted = self.store.delete(memory_type, memory_id)
        if deleted:
            await self.index.remove(session, memory_id)
        return deleted

    # Maximum chars per episodic chunk before splitting into multiple entries
    _EPISODIC_CHUNK_SIZE = 2000

    # Importance keywords — entries containing these score higher
    _HIGH_IMPORTANCE_KEYWORDS = frozenset({
        "error", "fail", "crash", "bug", "critical", "urgent", "important",
        "remember", "never forget", "config", "password", "secret", "key",
        "api key", "token", "rebuild", "restart", "delete", "remove", "archive",
        "created agent", "agent created", "skill created", "goal", "deployed",
        "learned", "discovered", "found", "confirmed",
    })

    def _compute_importance(
        self, user_input: str, agent_response: str, skills_used: list[str] | None
    ) -> float:
        """Heuristic importance score for an episodic entry."""
        score = 0.5  # baseline
        combined = (user_input + " " + agent_response).lower()
        # Boost for high-importance keywords
        for kw in self._HIGH_IMPORTANCE_KEYWORDS:
            if kw in combined:
                score += 0.05
        # Boost for skill usage (richer interaction)
        if skills_used:
            score += min(0.1 * len(skills_used), 0.2)
        # Clamp
        return min(score, 1.0)

    async def store_episodic(
        self,
        session: AsyncSession,
        event_type: str,
        user_input: str,
        agent_response: str,
        user_id: str = "",
        chat_id: str = "",
        tags: list[str] | None = None,
        skills_used: list[str] | None = None,
    ) -> MemoryContent:
        """Store an episodic memory from a conversation event.

        Long inputs/responses are chunked into overlapping entries so no
        content is lost. Each chunk references the original turn via tags.
        Automatically triggers the PromotionEngine to scan for recurring topics.
        """
        if self.backend == "supermemory":
            timestamp = datetime.now(timezone.utc).isoformat()
            content_text = (
                f"event_type: {event_type}\n"
                f"user_id: {user_id}\n"
                f"chat_id: {chat_id}\n"
                f"timestamp: {timestamp}\n\n"
                f"user: {user_input}\nassistant: {agent_response}"
            )
            entry = MemoryContent(
                memory_type=MemoryType.EPISODIC,
                tags=list(tags or ["conversation"]) + ([f"chat:{chat_id}"] if chat_id else []),
                summary=f"User: {user_input[:120]}",
                content={
                    "event_type": event_type,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "user_input": user_input,
                    "agent_response": agent_response,
                    "timestamp": timestamp,
                    "supermemory_only": True,
                },
                importance_score=self._compute_importance(user_input, agent_response, skills_used),
                source="supermemory",
            )
            # Use exact `/v4/memories` ingestion for conversation turns. The
            # document extraction path is still available via add_document(),
            # but exact memory writes are lower-latency and work reliably with
            # self-hosted/local Supermemory deployments whose extraction agent
            # may be weaker than the main chat model.
            await self.supermemory.create_memory(
                content_text,
                chat_id=chat_id,
                metadata={
                    "event_type": event_type,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "skills_used": ",".join(skills_used or []),
                    "internal_memory_id": entry.id,
                    "ingest_mode": "exact_memory",
                },
            )
            return entry

        all_tags = list(tags or ["conversation"])
        if skills_used:
            all_tags.append("skill_used")
        # Chat-scope tag — enables chat_id-filtered retrieval at the index
        # level. Without this, _episodic() in build_context loads the last N
        # episodic memories from the WHOLE DB regardless of chat, which
        # leaks context across chats and triggers LLM hallucinations
        # ("haz lo mismo" replied with another chat's package status).
        if chat_id:
            all_tags.append(f"chat:{chat_id}")

        importance = self._compute_importance(user_input, agent_response, skills_used)
        timestamp = datetime.now(timezone.utc).isoformat()

        # Determine if we need to chunk (total content too long for one entry)
        total_len = len(user_input) + len(agent_response)
        chunk_size = self._EPISODIC_CHUNK_SIZE
        last_entry = None

        if total_len <= chunk_size:
            # Single entry — fast path
            content = {
                "event_type": event_type,
                "user_id": user_id,
                "chat_id": chat_id,
                "user_input": user_input,
                "agent_response": agent_response,
                "timestamp": timestamp,
            }
            if skills_used:
                content["skills_used"] = skills_used

            summary = f"User: {user_input[:120]}"
            last_entry = await self.store_memory(
                session,
                memory_type=MemoryType.EPISODIC,
                content=content,
                summary=summary,
                tags=all_tags,
                source="conversation",
                importance=importance,
            )
        else:
            # Chunk long content into overlapping pieces
            # Strategy: chunk agent_response into segments, keep full user_input
            overlap = 200
            response_chunks = []
            pos = 0
            while pos < len(agent_response):
                end = pos + chunk_size - len(user_input)
                if end <= pos:
                    end = pos + 500  # safety fallback
                response_chunks.append(agent_response[pos:end])
                next_pos = end - overlap
                if next_pos <= pos:
                    next_pos = end
                pos = next_pos

            total_chunks = len(response_chunks)
            chunk_tags = all_tags + ["chunked"]
            for idx, chunk_text in enumerate(response_chunks):
                content = {
                    "event_type": event_type,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "user_input": user_input if idx == 0 else f"[chunk {idx+1}/{total_chunks}]",
                    "agent_response": chunk_text,
                    "timestamp": timestamp,
                    "chunk_index": idx,
                    "chunk_total": total_chunks,
                }
                if skills_used and idx == 0:
                    content["skills_used"] = skills_used

                summary = (
                    f"User: {user_input[:80]}"
                    if idx == 0
                    else f"[chunk {idx+1}/{total_chunks}] {chunk_text[:60]}"
                )
                last_entry = await self.store_memory(
                    session,
                    memory_type=MemoryType.EPISODIC,
                    content=content,
                    summary=summary,
                    tags=chunk_tags,
                    source="conversation",
                    importance=importance,
                )

        # Non-blocking promotion analysis (only for last chunk)
        if last_entry:
            try:
                await self.promotion.process_new_episodic(session, last_entry)
            except Exception:
                logger.warning("memory.promotion_analysis_failed", entry_id=last_entry.id)

        if self.backend == "tandem" and last_entry:
            await self.supermemory.create_memory(
                (
                    f"event_type: {event_type}\n"
                    f"user_id: {user_id}\n"
                    f"chat_id: {chat_id}\n"
                    f"timestamp: {timestamp}\n\n"
                    f"user: {user_input}\nassistant: {agent_response}"
                ),
                chat_id=chat_id,
                metadata={
                    "event_type": event_type,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "internal_memory_id": last_entry.id,
                    "skills_used": ",".join(skills_used or []),
                    "ingest_mode": "exact_memory",
                },
            )

        return last_entry

    async def get_context_packet(
        self,
        session: AsyncSession,
        project_id: str | None = None,
        max_interactions: int = 20,
    ):
        """Build a structured ContextPacket for LLM context assembly."""
        return await self.context_builder.build(
            session,
            project_id=project_id,
            max_interactions=max_interactions,
        )

    def migration_preview(self, limit: int = 500) -> dict:
        """Return a safe local preview for memory backend migration."""
        entries = self.store.list_all() if self.use_internal_store else []
        clipped = entries[: max(0, int(limit or 0))]
        by_type = {mt.value: 0 for mt in MemoryType}
        total_chars = 0
        for entry in clipped:
            by_type[entry.memory_type.value] = by_type.get(entry.memory_type.value, 0) + 1
            total_chars += len(entry.summary or "") + len(json.dumps(entry.content, ensure_ascii=False))
        return {
            "backend": self.backend,
            "internal_enabled": self.use_internal_store,
            "supermemory_enabled": self.use_supermemory,
            "internal_total": len(entries),
            "preview_count": len(clipped),
            "by_type": by_type,
            "estimated_payload_chars": total_chars,
            "supermemory": self.supermemory_status(),
            "directions": [
                {
                    "key": "internal_to_supermemory",
                    "label": "Internal → Supermemory",
                    "status": "available" if self.supermemory.configured and entries else "needs_configuration_or_memory",
                    "note": "Copies local Agent Wasp memory entries into scoped Supermemory exact memories without deleting local data.",
                },
                {
                    "key": "supermemory_to_internal",
                    "label": "Supermemory → Internal",
                    "status": "available" if self.supermemory.configured and self.use_internal_store else "needs_configuration_or_internal_store",
                    "note": "Imports listed Supermemory memories back into Agent Wasp JSON/PostgreSQL memory as rollback/portability entries.",
                },
            ],
        }

    async def export_internal_to_supermemory(
        self,
        session: AsyncSession,
        *,
        limit: int = 500,
        dry_run: bool = True,
        chat_id: str = "",
        project_id: str | None = None,
    ) -> dict:
        """Copy internal memory entries into Supermemory exact memories."""
        entries = self.store.list_all()[: max(0, min(int(limit or 500), 5000))]
        if not self.supermemory.configured:
            return {"ok": False, "error": "Supermemory is not configured", "dry_run": dry_run, "planned": len(entries), "copied": 0}
        copied = 0
        failures: list[str] = []
        for entry in entries:
            summary = entry.summary or json.dumps(entry.content, ensure_ascii=False)[:500]
            payload_text = (
                f"memory_type: {entry.memory_type.value}\n"
                f"source: agentwasp-internal\n"
                f"created_at: {entry.created_at}\n"
                f"tags: {', '.join(entry.tags)}\n\n"
                f"summary: {summary}\n"
                f"content: {json.dumps(entry.content, ensure_ascii=False)}"
            )
            if dry_run:
                copied += 1
                continue
            result = await self.supermemory.create_memory(
                payload_text,
                chat_id=chat_id,
                project_id=project_id or entry.project_id,
                metadata={
                    "migration": "internal_to_supermemory",
                    "internal_memory_id": entry.id,
                    "memory_type": entry.memory_type.value,
                    "source": entry.source,
                    "tags": ",".join(entry.tags),
                },
                is_static=entry.memory_type in {MemoryType.FACTS, MemoryType.POLICY},
            )
            if result.get("ok"):
                copied += 1
            else:
                failures.append(str(result.get("error") or result.get("reason") or "unknown")[:160])
        return {"ok": not failures, "dry_run": dry_run, "planned": len(entries), "copied": copied, "failed": len(failures), "failures": failures[:5]}

    async def import_supermemory_to_internal(
        self,
        session: AsyncSession,
        *,
        limit: int = 100,
        dry_run: bool = True,
        chat_id: str = "",
        project_id: str | None = None,
    ) -> dict:
        """Import listed Supermemory memories into the internal store/index."""
        if not self.supermemory.configured:
            return {"ok": False, "error": "Supermemory is not configured", "dry_run": dry_run, "planned": 0, "imported": 0}
        try:
            data = await self.supermemory.list_memories(chat_id=chat_id, project_id=project_id, limit=limit)
        except Exception as exc:
            return {"ok": False, "error": str(exc).splitlines()[0][:160], "dry_run": dry_run, "planned": 0, "imported": 0}
        items = data.get("memoryEntries") or data.get("memories") or []
        imported = 0
        for item in items[: max(0, min(int(limit or 100), 1000))]:
            text = item.get("memory") or item.get("content") if isinstance(item, dict) else str(item)
            if not text:
                continue
            imported += 1
            if dry_run:
                continue
            entry = MemoryContent(
                memory_type=MemoryType.SEMANTIC,
                project_id=project_id,
                tags=["supermemory-import", "migration"],
                summary=str(text)[:240],
                content={"source": "supermemory", "text": str(text), "supermemory_id": item.get("id") if isinstance(item, dict) else None},
                source="supermemory-import",
            )
            file_path = self.store.write(entry)
            content_hash = self.store.content_hash(entry)
            await self.index.upsert(session, entry, file_path, content_hash)
        return {"ok": True, "dry_run": dry_run, "planned": len(items), "imported": imported, "pagination": data.get("pagination")}

    def get_stats(self) -> dict:
        """Get memory statistics."""
        if self.backend == "supermemory":
            stats: dict = {"total": 0, "size_bytes": 0}
            for mt in MemoryType:
                stats[mt.value] = 0
            stats["backend"] = "supermemory"
            stats["supermemory"] = self.supermemory_status()
            return stats

        stats: dict = {"total": self.store.count(), "size_bytes": self.store.total_size_bytes()}
        for mt in MemoryType:
            stats[mt.value] = self.store.count(mt)
        stats["backend"] = self.backend
        stats["supermemory"] = self.supermemory_status()
        return stats

    def create_snapshot(self, label: str, trigger: str = "manual") -> SnapshotInfo:
        return self.snapshots.create(label, trigger)

    def list_snapshots(self) -> list[SnapshotInfo]:
        return self.snapshots.list_snapshots()

    def restore_snapshot(self, snapshot_id: str) -> SnapshotInfo:
        return self.snapshots.restore(snapshot_id)
