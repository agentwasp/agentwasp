"""Supermemory backend adapter tests."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.agent.context import build_context
from src.memory.supermemory_client import SupermemoryClient, SupermemorySettings
from src.utils.redaction import redact


def make_client(**overrides) -> SupermemoryClient:
    cfg = SupermemorySettings(
        enabled=True,
        api_key="sm_" + "x" * 32,
        base_url="http://localhost:6767",
        container_tag="agentwasp",
        scope="chat",
        timeout_seconds=1.5,
        context_budget_chars=500,
        search_limit=2,
        search_threshold=0.35,
        rerank=False,
        rewrite_query=False,
        ingest_enabled=True,
        strict=False,
    )
    data = cfg.__dict__ | overrides
    return SupermemoryClient(SupermemorySettings(**data))


@pytest.mark.asyncio
async def test_context_format_is_budgeted_and_parses_profile_search() -> None:
    client = make_client(context_budget_chars=220, search_limit=2)

    async def fake_profile(query: str, *, chat_id: str = "", project_id: str | None = None):
        return {
            "profile": {
                "static": ["User prefers concise answers", "User runs Agent Wasp on a homelab"],
                "dynamic": ["User is evaluating memory backend tradeoffs"],
            },
            "searchResults": {
                "results": [
                    {"memory": "Prior discussion: keep Supermemory context compact", "similarity": 0.91},
                    {"memory": "Local KG remains useful for procedural recall", "similarity": 0.82},
                ]
            },
        }

    client.profile = fake_profile  # type: ignore[method-assign]
    block = await client.format_context("memory tradeoffs", chat_id="chat-1")

    assert block.startswith("[SUPERMEMORY CONTEXT]")
    assert "Static profile:" in block
    assert "Relevant memories:" in block
    assert len(block) <= 220


@pytest.mark.asyncio
async def test_add_document_payload_uses_chat_scope_and_custom_id() -> None:
    client = make_client()
    captured = {}

    async def fake_post(path: str, payload: dict):
        captured["path"] = path
        captured["payload"] = payload
        return {"id": "doc_123", "status": "queued"}

    client._post = fake_post  # type: ignore[method-assign]
    result = await client.add_document(
        "user: hello\nassistant: hi",
        chat_id="abc",
        custom_id="turn-1",
        metadata={"event_type": "dashboard.chat"},
    )

    assert result["ok"] is True
    assert captured["path"] == "/v3/documents"
    assert captured["payload"]["containerTag"] == "agentwasp:chat:abc"
    assert captured["payload"]["customId"] == "turn-1"
    assert captured["payload"]["metadata"]["event_type"] == "dashboard.chat"


def test_supermemory_keys_are_redacted() -> None:
    key = "sm_" + "a" * 36
    assert key not in redact(f"SUPERMEMORY_API_KEY={key}")
    assert "sm_***REDACTED***" in redact(f"SUPERMEMORY_API_KEY={key}")


@pytest.mark.asyncio
async def test_supermemory_only_context_skips_internal_memory(monkeypatch) -> None:
    from src.config import settings
    import src.agent.context as context_mod

    class FakeMemory:
        async def supermemory_context(self, user_text: str, chat_id: str = "", project_id: str | None = None):
            return "[SUPERMEMORY CONTEXT]\nStatic profile:\n- User prefers bounded memory."

    monkeypatch.setattr(settings, "memory_backend", "supermemory")
    monkeypatch.setattr(context_mod, "load_installed_skills", lambda: [])

    messages = await build_context(
        session=SimpleNamespace(),
        memory=FakeMemory(),
        user_text="what should you remember?",
        chat_id="chat-1",
        model_name="test-model",
        provider_name="openai",
        is_light_mode=True,
    )

    system = messages[0].content
    assert "[SUPERMEMORY CONTEXT]" in system
    assert "legacy Agent Wasp filesystem/PostgreSQL memory layers are not used" in system
    assert "Knowledge Graph: graph of entities" not in system
    assert messages[-1].content == "what should you remember?"


@pytest.mark.asyncio
async def test_unconfigured_supermemory_returns_operator_status_block() -> None:
    client = make_client(api_key="")
    block = await client.format_context("anything", chat_id="abc")
    assert "enabled but not configured" in block
