# Supermemory memory backends

Agent Wasp can run with its original local memory stack, with Supermemory as the primary conversational memory backend, or with both systems in tandem.

## Modes

| `MEMORY_BACKEND` | Behavior | Best use |
|---|---|---|
| `internal` | Original Agent Wasp memory only: filesystem JSON entries, PostgreSQL index, Redis-backed cognitive state, KG, procedural memory, vector memory, temporal/world model blocks. | Offline/default compatibility or when Supermemory is not configured. |
| `supermemory` | Supermemory-only conversational memory. Agent Wasp stores turns to Supermemory and injects only the bounded Supermemory context block. Local memory/graph pages remain as compatibility/read-only operational surfaces, but local conversational recall is skipped. | Evaluating whether Supermemory can replace the in-app memory stack. |
| `tandem` | Supermemory profile/search plus the original Agent Wasp memory layers. Supermemory is capped by timeout/result/budget settings and runs alongside local recall. | Recommended evaluation mode when you want better long-term recall without losing local KG/procedural/temporal behavior. |

## Configuration

```env
MEMORY_BACKEND=tandem
SUPERMEMORY_BASE_URL=https://api.supermemory.ai
SUPERMEMORY_API_KEY=
SUPERMEMORY_CONTAINER_TAG=agentwasp
SUPERMEMORY_SCOPE=chat
SUPERMEMORY_TIMEOUT_SECONDS=1.5
SUPERMEMORY_CONTEXT_BUDGET_CHARS=1800
SUPERMEMORY_SEARCH_LIMIT=3
SUPERMEMORY_SEARCH_THRESHOLD=0.35
SUPERMEMORY_INGEST_ENABLED=true
```

For local self-hosted Supermemory, set `SUPERMEMORY_BASE_URL=http://localhost:6767` and use the API key printed by `supermemory-server` on first boot. Do not paste keys into chat, GitHub, screenshots, or support threads.

## Latency and token controls

The integration is intentionally bounded:

- one Supermemory `/v4/profile` call per LLM context build;
- `SUPERMEMORY_TIMEOUT_SECONDS` defaults to `1.5` seconds;
- `SUPERMEMORY_SEARCH_LIMIT` defaults to `3`;
- `SUPERMEMORY_CONTEXT_BUDGET_CHARS` defaults to `1800`;
- rerank and query rewriting are off by default to avoid extra latency;
- failures are fail-open unless `SUPERMEMORY_STRICT=true` is added in code/config.

In `tandem` mode, the Supermemory block is injected before local cognitive layers so static/current profile facts frame local KG/vector/procedural recall without duplicating full history.

## Scope model

`SUPERMEMORY_SCOPE=chat` is the safe default. It resolves the container tag to `agentwasp:chat:<chat_id>` and prevents cross-chat leakage. `project` shares memory by active project/goal id, and `global` uses the raw `SUPERMEMORY_CONTAINER_TAG` for broad recall.

## Dashboard copy

The Memory Hub shows a Supermemory status card with backend mode, configured state, scope, context budget, and timeout. Config Center surfaces Supermemory Sync and the main runtime parameters. It never displays the API key.

## Security notes

- `SUPERMEMORY_API_KEY` is redacted by the secret scrubber (`sm_***REDACTED***`).
- Authorization/Bearer headers are redacted by existing generic patterns.
- Supermemory failures log redacted exception summaries only.
- `supermemory` mode does not delete existing local memory files or tables; it bypasses local conversational recall. Destructive migration/cleanup must be a separate explicit operator action.

## Testing

Relevant tests:

```bash
cd containers/agent-core
MEDIA_SIGNING_DEBUG=true TIMEZONE=UTC DATABASE_URL=postgresql+asyncpg://wasp:wasp@localhost:5432/wasp_test \
  uv run --with-requirements requirements.txt python -m pytest tests/test_supermemory_backend.py -q
```

## Benchmarking Supermemory vs internal memory

See [`docs/MEMORY_BENCHMARKS.md`](MEMORY_BENCHMARKS.md) for the reproducible AgentWASP memory benchmark harness. It compares `internal`, `supermemory`, and `tandem` backends with the same local reader model and reports answer accuracy, retrieval support, contamination, latency, prompt size, and category-level results.

The harness uses exact `/v4/memories` ingestion for benchmark facts because that path is deterministic and works with self-hosted/local Supermemory deployments even when document extraction agents are unavailable or weaker than the main reader model.

## Switching and migration

Memory Hub includes a **Memory Switchboard** preview. It shows how many local AgentWASP memories would be copied, estimated payload size, and available transfer directions:

- `internal_to_supermemory`: copies local AgentWASP memories into scoped Supermemory exact memories without deleting local data.
- `supermemory_to_internal`: imports listed Supermemory memories back into AgentWASP JSON/PostgreSQL memory for rollback/portability.

The migration API is dry-run first:

```bash
curl -s http://localhost:8000/memory/api/supermemory/migration-preview
curl -s -X POST http://localhost:8000/memory/api/supermemory/migrate \
  -H 'Content-Type: application/json' \
  -d '{"direction":"internal_to_supermemory","dry_run":true,"limit":500}'
```

Run destructive cleanup only as a separate explicit operator action; switching modes never deletes either memory system.
