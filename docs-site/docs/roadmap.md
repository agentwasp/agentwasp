---
id: roadmap
title: Roadmap
description: Completed features and planned improvements for WASP.
---

# Roadmap

## Current Status

**Current Version: v2.7.2** (May 2026 — installer hotfix on top of v2.7.1)

WASP is in active production deployment and now publishable as a self-hostable OSS project. All systems below are complete and operational.

### Completed Systems

- [x] Event-driven architecture (Redis Streams, consumer groups, at-least-once delivery)
- [x] Goal Engine with TaskGraph execution (DAG, plan critic, plan lock, duplicate detection)
- [x] Dual-layer planning (PlanGenerator + PlanCritic LLM validation)
- [x] 37 built-in skills across 5 capability levels
- [x] Custom Python skill creation and management via `skill_manager`
- [x] Skill Evolution (automatic synthesis from recurring patterns, AST validation)
- [x] 41 scheduler background jobs (health, learning, perception, pruning, weekly DB maintenance)
- [x] 18 memory systems (episodic, semantic, procedural, visual, vector, KG, self-model, temporal, goal-scoped, ranked retrieval, reflection, behavioral rules, learning examples, dream log, recovery memory, skill patterns, entity states, state predictions)
- [x] Memory ranking (composite score: 0.5×similarity + 0.3×recency + 0.2×importance)
- [x] Knowledge Graph with Redis cache (rule-based NLP extraction)
- [x] Temporal World Model (`world_timeline` table, price/state extraction, trend detection)
- [x] Multi-agent orchestration (AgentOrchestrator, AgentRuntime, CapabilitySandbox, inter-agent bus)
- [x] Dream Mode (memory consolidation, KG enrichment, LLM reflection, failure pattern analysis)
- [x] Autonomous Goal Generator (proactive LLM-evaluated goal creation, rate limited)
- [x] Background Perception (crypto price monitoring, KG-sourced assets)
- [x] Behavioral Learning Loop (correction detection, LLM rule synthesis, dedup + conflict detection)
- [x] Epistemic State tracking (domain confidence, symmetric ±0.015 calibration)
- [x] Self-Integrity Monitor (6h cross-check of self-model vs actual performance)
- [x] Cognitive Pressure Index (composite 0–100 metric, actuator guard at >80)
- [x] Opportunity Engine (proactive automation suggestions from episodic pattern detection)
- [x] Self-Reflection Engine (goal-level post-mortem insights, Redis TTL 7d)
- [x] Resource Governor (Redis-backed rate limiter: goal slots, LLM budget, API caps)
- [x] Decision Layer (pre-LLM heuristic classifier, 5 strategies, 13 fast-paths)
- [x] Response Validation & Recovery Engine (deterministic validator, 2-retry auto-recovery, RecoveryMemory)
- [x] Response Grounding Engine (9 checks: weak response, generic phrase, status marker, intent evidence gate, anti-hallucination guard)
- [x] DomainLock Hardening (root normalization, semantic category guards, immutable anchor, cross-turn stale lock clearance)
- [x] Active Flow Context Lock (per-chat Redis state, TTL 15min, cross-domain hallucination prevention)
- [x] Planning Mode Hard Override (5-layer execution block, zero skills when "don't execute")
- [x] Universal Response Contract (response-type detection, type-specific structure rules)
- [x] Intent Completeness Engine (4-strategy multi-part extraction, one completeness retry)
- [x] Voice/Audio Input (Telegram voice → Whisper transcription → full pipeline)
- [x] Video Input (Telegram video → ffmpeg first frame → vision pipeline)
- [x] Universal Interaction Validation Layer (pre-click target validation, post-click interference detection, result-state confirmation, validated screenshot capture)
- [x] div-button SPA Support (React/Vue `<div>` as submit button)
- [x] Browser Session Lifecycle (idle reaper daemon, 300s timeout, CPU: 81% → 0.25%)
- [x] Browser URL blocklist (`file://`, `javascript:`, `data:`, `vbscript:`, RFC-1918, loopback, cloud metadata)
- [x] Multilingual Auto-Detect (10 languages: EN/ES/PT/FR/DE/ZH/JA/KO/AR/RU; localized fallback responses)
- [x] Domain Drift Protection (browser→crypto/email substitution detection, should_retry=False on confirmed substitution)
- [x] HealthState Adaptive Execution (CPU/RAM/latency-based light mode hint injection)
- [x] SaccadicVision Change Detection Daemon (2s SHA-1 polling, browser content change events)
- [x] Dream Failure Pattern Analysis (7-day audit error classification into FailurePattern records)
- [x] Self-Improve Soft Safety Gate (deterministic pattern gate, BLOCK/WARN/ALLOW, 13 safety-weakening patterns)
- [x] Self-Improve SHA-256 sidecar integrity (tamper detection for persisted patches)
- [x] 40+ integration connectors (Slack, Discord, GitHub, Telegram, Notion, Gmail, smart home, etc.)
- [x] 11 LLM providers (Anthropic, OpenAI, Google, xAI, Mistral, DeepSeek, Moonshot/Kimi, OpenRouter, Perplexity, HuggingFace, Ollama local)
- [x] Dashboard v2.5 restructuring (5 sections, 24 pages, 5 new dedicated pages)
- [x] Config Center (prime.md live editor, 12 feature flags, Redis `config:overrides` persisting across restarts)
- [x] CSRF protection, audit logging (keyset pagination), secret redaction
- [x] Self-Repair (SelfHealer) + Self-Improvement (code patching, surgical edits, package install)
- [x] Sovereign Mode (MAX_SKILL_ROUNDS=12, doubled cognitive budgets)
- [x] deep_scraper built-in (Playwright/Crawlee, SSRF-protected, YouTube transcripts)
- [x] Audit Log Retention job (daily bounded deletion, configurable retention window)
- [x] Bounded Redis streams (`maxlen=10000` on all `xadd()` calls)
- [x] PEL zombie recovery (xautoclaim at startup clears idle pending entries)
- [x] Composite DB index on `audit_log(chat_id, timestamp)`
- [x] **Panic Reset page** (hard-confirmation UI, 17 table wipe, VACUUM FULL, AuditLog entry)
- [x] **SSRF protection on `fetch_url`** (matches `http_request` protection)
- [x] **Self-improve syntax validation + backup** (ast.parse + timestamped backup before overwrite)
- [x] **Shell audit logging** (every invocation logged with redacted command and goal context)
- [x] **Behavioral rule conflict detection** (negation-word analysis, 35% overlap threshold)
- [x] **Health dashboard: learning queue depth** (visual thresholds at ≥20 and ≥40)
- [x] **Boot model liveness ping** (8s timeout, shows "live ✓" / "unreachable ✗" in boot message)
- [x] **Weekly VACUUM ANALYZE** (`db_maintenance` job, AUTOCOMMIT, no table locking)
- [x] **Low-Intent Cold-Start Guard** (deterministic clarification fast-path for single-token, emoji-only, and context-required input without anchor)
- [x] **Multi-URL Aggregator `Error:` prefix detection** (SSRF-blocked URLs labeled ❌ even when `success=True`)
- [x] **Agent Name Preservation non-greedy regex** (3 patterns with `{0,4}?` + lookahead stop-set)
- [x] **Schedule Honesty Bidirectional** (clock-time + daypart user-side disclaimer when interval-only task created)
- [x] **Markdown Link Sanitizer** (`[text](url)` collapses to readable `text (url)` form)
- [x] **Entity-Proximity Verdict Check** (200-char window between user-named entity and verdict word)
- [x] **One-line public installer** (`install.sh` cross-distro: Debian/Ubuntu, RHEL/AlmaLinux/Rocky, Fedora, Arch, openSUSE, Alpine, macOS, Windows via WSL2)
- [x] **Allowlist tarball build** (`scripts/build-release.sh` refuses to package operator-specific identifiers; 2.1 MB clean public archive)
- [x] **Cross-distro installer hardening** (Alpine `hostname -I` fallback, AlmaLinux `dnf --allowerasing`, top-level install-dir `df` fix)
- [x] **Fail-closed Telegram bridge** (refuses to start without `TELEGRAM_ALLOWED_USERS`; no public-bot mode, no escape hatch)
- [x] **Gmail recipient allowlist** (`GMAIL_RECIPIENT_ALLOWLIST` defense vs prompt-injection-driven exfiltration)
- [x] **Self-improve `dry_run`** (preview write/patch as unified diff + AST verdict without touching the file)
- [x] **Centralized SSRF guard** (`utils/network_safety.py` with DNS-rebinding protection + manual redirect re-validation; applied to `http_request`, `fetch_url`, `scrape`, `monitors`, `subscriptions`)
- [x] **Dashboard SPA navigation fixes** (path+query URL compare for tabs/filters/pagination; IIFE wrap of re-injected scripts to survive same-page const re-declarations)
- [x] **CheckIn fresh-install guard** (proactive `¿Necesitas ayuda?` no longer fires on installs with zero episodic memory)
- [x] **Public test coverage of Experimental subsystems** (38 new tests for learning / procedural / behavioral / dream)

## Planned Features

### Near-Term

**Vector Memory Enhancement**
- Automatic embedding model pull on first enable
- Cross-session semantic memory search with auto-clustering
- Hybrid retrieval (vector + BM25 keyword)

**Text-to-Speech Responses**
- Voice responses via Telegram
- Wake word detection for local deployment

**Structured Output Validation**
- JSON schema validation for skill outputs
- Type-safe skill parameter validation at registration time

### Medium-Term

**MCP (Model Context Protocol) Full Support**
- Connect to any MCP server as a skill source
- MCP server hosting (expose WASP skills as MCP)
- Dynamic tool discovery from MCP endpoints

**Multi-Modal Memory**
- Store and retrieve audio, video, and document content
- Cross-modal search (text → finds related images)

**Workflow Builder**
- Visual workflow editor in the dashboard
- Trigger-based automation (webhook → goal)
- Scheduled workflow templates

**Enhanced Security**
- Skill sandboxing via container isolation (separate process per skill)
- Fine-grained permission model per user
- Hardware token support for dashboard auth

### Long-Term

**Meta-Agent Architecture (v2)**
- Fully autonomous agent team coordination
- Hierarchical goal decomposition
- Cross-agent memory sharing with privacy controls

**Federated Deployment**
- Multiple WASP instances coordinating
- Distributed goal execution across nodes

**Plugin Marketplace**
- Community skill packages
- One-click skill installation via ClawHub

## Version History

| Version | Key Features |
|---------|-------------|
| Phase 1–6 | Core agent, skills, memory, scheduler |
| Phase 7 | Health monitor, self-repair, introspector |
| Phase 8 | Security hardening, dashboard, CSRF |
| Phase 9 | Agent freedom: shell, python, browser skills |
| Phase 10–16 | Cognitive systems: KG, temporal, epistemic, dream |
| Phase 17 | Multi-agent orchestration v1 |
| Phase 18 | QA/SRE audit, 208 tests |
| v1.5 | Skill evolution, world model, behavioral learning, CPI, integrity monitor |
| v1.6 | Sovereign mode, autonomous goals, self-improvement, decision layer foundation |
| v1.7 | Opportunity Engine, Self-Reflection Engine, Resource Governor |
| v1.8 | Multi-agent v2, AgentManagerSkill, Goal Priority Axis |
| v1.9 | Response Validation & Recovery, Voice/Audio input, Behavioral Learning Loop |
| v2.0 | Active Flow Context Lock, Planning Mode Override, Response Contract, Intent Completeness |
| v2.1 | Browser Session Reaper, Multilingual Auto-Detect, Domain Drift Protection, production audit |
| v2.2 | deep_scraper built-in, dashboard streaming, 37 skills, 21-bug audit |
| v2.3 | Universal Interaction Validation, div-button SPA, enforcement loop fix |
| v2.4 | Response Grounding Engine (9 checks), DomainLock hardening |
| v2.5 | Dashboard restructuring, 5 new pages, Config Center, HealthState, SaccadicVision, Dream failure analysis, 11-fix audit |
| v2.6 | Panic Reset, SSRF on fetch_url, shell audit logging, behavioral conflict detection, weekly VACUUM ANALYZE, boot liveness ping, 10-fix hardening pass + Edge Fix Pass (low-intent guard, multi-URL aggregator, agent name preservation, schedule honesty bidirectional, markdown link sanitizer, entity-proximity verdict) |
| **v2.7** | **First public OSS release. One-line cross-distro installer (8 Linux flavors + macOS + WSL2). Allowlist tarball build with forbidden-pattern scan. Fail-closed Telegram bridge (no public-bot mode). Gmail recipient allowlist. Self-improve `dry_run`. Centralized SSRF guard. Dashboard SPA navigation fixes (tab bars + filter pills + pagination across all list pages). CheckIn fresh-install guard. 622 tests passing. Docker socket removed from `agent-core` public default.** |

## Contributing

WASP is under active development. The codebase is structured for extensibility:

- **New skills**: Add to `src/skills/builtin/` or via `skill_manager`
- **New scheduler jobs**: Add callable class to `src/scheduler/` and register in `main.py`
- **New connectors**: Add to `src/integrations/connectors/` and register in `main.py`
- **New memory types**: Add module to `src/memory/` and inject into `build_context()`

See [Extending WASP](/development/extending) for implementation guides.
