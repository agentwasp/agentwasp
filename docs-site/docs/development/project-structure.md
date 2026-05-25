---
id: project-structure
title: Project Structure
description: Source tree, key modules, and where to find things.
---

# Project Structure

```
$WASP_INSTALL_DIR/                            -- default: /opt/wasp
├── README.md                                 -- repo-level intro
├── CHANGELOG.md                              -- public version history (v2.7 baseline)
├── LICENSE.md                                -- Apache License 2.0
├── VERSION                                   -- semantic version (current: 2.7)
├── docs/                                     -- canonical operator docs (Markdown)
├── bin/wasp                                  -- CLI symlinked to /usr/local/bin/wasp
├── lib/ui.sh                                 -- shared shell UI helpers
├── scripts/
│   ├── onboard.sh                            -- interactive .env wizard
│   ├── health.sh                             -- health probe suite
│   └── build-release.sh                      -- allowlist tarball builder (operator use)
├── install.sh                                -- one-line cross-distro installer
├── install.ps1                               -- Windows / WSL2 installer
├── docker-compose.yml                        -- public 6-service stack
├── .env.example                              -- canonical, commented env reference
├── .env                                      -- runtime config (NOT committed)
└── containers/
    ├── agent-core/                           -- main runtime
    │   ├── Dockerfile
    │   ├── tailwind-build/                   -- Tailwind CSS build stage
    │   ├── tests/                            -- 622 passing tests
    │   ├── config/
    │   │   ├── prime.md                      -- operator override (mounted at /data/config/prime.md)
    │   │   └── prime.default.md              -- canonical reference (must equal prime.md)
    │   └── src/
    │       ├── main.py                       -- entrypoint, scheduler registration (41 jobs)
    │       ├── config.py                     -- Pydantic Settings
    │       ├── agent/                        -- self_model, epistemic, cpi, identity
    │       ├── agent_manager/                -- AgentRuntime
    │       ├── communication/                -- formatter
    │       ├── dashboard/                    -- FastAPI app: 151 HTTP endpoints + templates + static
    │       ├── db/                           -- SQLAlchemy models (28 tables) + session
    │       ├── events/                       -- EventBus, EventHandler, handlers.py
    │       ├── goal_orchestrator/            -- planner, critic, executor, stability
    │       ├── governance/                   -- ResourceGovernor
    │       ├── health/
    │       ├── identity/
    │       ├── integrations/                 -- registry, vault, 40+ connectors
    │       ├── intent/
    │       ├── memory/                       -- 10 layers, embeddings, ranking
    │       ├── models/                       -- ModelManager, router, 5 providers (Anthropic, OpenAI-compat, Google, xAI via OpenAI-compat, Ollama)
    │       ├── observability/
    │       ├── policy/                       -- intent_gate, response_guard, action_announcer, decision_trace, regression_checks
    │       ├── reasoning/
    │       ├── runtime/                      -- HealthState, SaccadicVision daemon
    │       ├── scheduler/                    -- 41 registered jobs
    │       ├── skills/                       -- 37 built-in + custom loader + executor
    │       ├── utils/                        -- redaction, network_safety (SSRF), helpers
    │       ├── validation/                   -- ResponseValidator, IntentEngine
    │       └── world/
    ├── agent-telegram/                       -- Telegram polling bridge (fail-closed)
    ├── agent-broker/                         -- Privileged Docker proxy with endpoint allowlist
    └── (agent-nginx)                         -- operator-only; NOT in the public tarball
```

Data lives in Docker named volumes managed by Compose — not host bind mounts. See [Docker Setup → Volumes](/getting-started/docker-setup) for the volume inventory.

## Key directories in `agent-core/src`

### `policy/`

Deterministic guards. The most safety-critical code in the project.

- `intent_gate.py` — `SIDE_EFFECT_SKILLS`, intent regexes, placeholder detection
- `action_announcer.py` — strips unverified action claims, surfaces failures
- `response_guard.py` — `enforce_factual_grounding`, `enforce_schedule_honesty`, `sanitize_markdown`
- `decision_trace.py` — `DecisionTrace` dataclass + Redis persistence
- `regression_checks.py` — 20 check functions + 50+ regression cases (run at build time)
- `control_layer.py` — `DomainLock` and cross-turn anchor binding
- `response_grounder.py` — universal grounding checks (Checks 5–9)

### `events/handlers.py`

The largest single file (~10k lines). Contains:

- `EventHandler.handle_message()` — main pipeline
- `_is_low_intent()` — Cold-start guard
- `_AGENT_NAME_PATTERNS` — non-greedy multi-word name extraction
- Multi-URL aggregator
- `_run_boot_sequence()`
- `_detect_correction()` for behavioral learning
- `_clean_telegram_output()` — final sanitization
- `_safe_publish_response()` — truth-layer chain

### `skills/`

- `builtin/` — 40 first-party skills (browser, gmail, shell, python_exec, http_request, fetch_url, scrape, reminders, monitors, self_improve, …)
- `executor.py` — `SkillExecutor`, parallel groups, anticipatory simulation
- `registry.py` — `SkillRegistry`, capability levels (SAFE / MONITORED / CONTROLLED / RESTRICTED / PRIVILEGED)
- `openclaw/` — custom-skill loader (`load_all_python_skills()`)

### `memory/`

10 layers. Each layer has its own module + integration with `MemoryManager`.

### `scheduler/`

One file per job, plus `scheduler.py` for the runner. `main.py` registers all **41 jobs** at startup.

### `dashboard/`

- `routes/` — one file per dashboard page (151 HTTP endpoints total)
- `templates/` — Jinja2 HTML templates (reload from disk per request — hot-copy works)
- `static/` — `app.js` (SPA navigation + WaspActions dispatcher), CSS (Tailwind), images

### `db/`

- `models.py` — 28 SQLAlchemy table definitions
- `session.py` — async engine, `init_db()`, `ensure_indexes()`

## Naming conventions

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions: `snake_case`
- Frozensets / sentinels: `_UPPER_SNAKE_CASE` (leading underscore for module-private)
- Async functions: same as sync; `await` is a runtime concern
- Test files: `tests/test_<area>.py`

## Where to add new code

| What | Where |
|------|-------|
| New skill | `src/skills/builtin/<name>.py` + register in `__init__.py` |
| New scheduler job | `src/scheduler/<name>.py` + register in `main.py` |
| New connector | `src/integrations/connectors/<name>.py` + register |
| New memory layer | `src/memory/<name>.py` + inject into `build_context()` |
| New dashboard page | `src/dashboard/routes/<name>.py` + add to nav + template |
| New policy check | `src/policy/regression_checks.py` + add regression case |
| New env variable | `src/config.py` Pydantic model + `.env.example` + the env-vars docs page |

## Building

```bash
docker compose build agent-core
docker compose up -d agent-core
```

`docker compose restart` is NOT enough after a rebuild — it doesn't pick up new image content. Always `up -d` after `build`.

HTML/Jinja templates and `prime.md` reload from disk per request, so `docker cp` is enough for those.

## Tests

```bash
docker exec agent-core python -m pytest tests/ -q
```

Current suite: **622 passing**. Build-time enforcement: `tests/test_policy_regressions.py` runs as a Docker build step; the build fails if any regression case fails.

## See also

- [Creating Skills](/development/creating-skills)
- [Extending](/development/extending)
- [Architecture](/core-concepts/agent-architecture)
