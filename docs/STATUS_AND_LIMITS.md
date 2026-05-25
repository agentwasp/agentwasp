# WASP — Status & Limits

This document is the **honest** map of what works, what's experimental, and what's known broken in the current WASP release (v2.7 — first public OSS release; full pre-OSS history at https://docs.agentwasp.com/changelog). Treat README/CHANGELOG as marketing-adjacent; treat this file as the source of truth.

## Status legend
- **Stable** — exercised continuously, has tests, used in production.
- **Beta** — works for the documented happy path; rough edges in error cases.
- **Experimental** — code path is present and wired up, but accumulates data only with usage; no claim of accuracy.
- **Broken / disabled** — known issue; do not rely on.

---

## Core surfaces

| Feature | Status | Notes |
|---|---|---|
| One-line installer (`install.sh`) | Stable | Cross-distro (Debian, RHEL, Fedora, Arch, SUSE, Alpine, macOS). |
| Windows installer (`install.ps1`) | Beta | Requires WSL2 + Docker Desktop. Auto-installs WSL2 if missing. |
| Dashboard (login → overview → chat/traces/tasks/...) | Stable | 151 HTTP endpoints across the dashboard, all auth-protected; CSRF session-bound. Tab bars, filter pills, and pagination verified across all list pages (v2.7 fix). |
| Telegram bridge | Stable | 15 commands, multi-language welcome, photo/voice/video support. |
| Goal orchestrator | Stable | Replan budget=5, storm threshold=5, chain-break recovery. |
| Truth/honesty layer (`_safe_publish_response`) | Stable | URL substitution + domain lock + numeric grounding + capability check + final language guard, all wired. |
| SSRF guard (`utils/network_safety.py`) | Stable | DNS rebinding protected, redirect re-validation, 19 unit tests. |
| Backup / restore | Beta | Volume-aware (`docker run alpine tar` per named volume). Verify the archive contains `vol-*.tar.gz` entries after backup. |

## Skills

| Skill | Status | Notes |
|---|---|---|
| browser (capture/navigate/click/fill) | Stable | nodriver primary for capture/navigate, Selenium for form fill. |
| http_request | Stable | SSRF-guarded with redirect re-validation. |
| fetch_url | Stable | SSRF-guarded with redirect re-validation. |
| scrape | Stable | SSRF-guarded with redirect re-validation. |
| shell | Stable | DANGEROUS-pattern blocklist, audit-logged, cwd locked to /data. |
| python_exec | Stable | subprocess sandbox + RLIMIT + import blocker. Static AST scanner is defense-in-depth. |
| reminders | Stable | Postgres-backed, fires through scheduler. |
| monitors | Stable | SSRF-guarded; polls URLs at configurable intervals. |
| email (Gmail) | Beta | Send + inbox + search work. Recipient allowlist enforced via `GMAIL_RECIPIENT_ALLOWLIST` (per-address or `@domain.com` entries). Empty allowlist = no restriction; set it before connecting Gmail in environments that handle untrusted input. |
| skill_manager (Python skills) | Beta | Persists Python skills to /data/skills/<slug>/skill.py; loaded at startup. |
| self_improve | Beta | Containment to `/app/src/`, AST validation, automatic backup before every write, daily cap. Now supports `dry_run="true"` for both `write` and `patch` — returns unified diff + AST verdict without touching the file. Use with care. |
| web_search | Beta | ddgs library; Google direct + scraping has rate limits. |

## Cognitive systems

| System | Status | Notes |
|---|---|---|
| Knowledge graph (entities + relations) | Experimental | Rule-based extraction; tends to be sparse until extended conversations accumulate. |
| Procedural memory | Experimental | Triggers on >2 rounds AND >2 unique skills; may stay empty under low traffic. |
| Behavioral rules (correction learning) | Experimental | Queue-based; only fires on detected user corrections. |
| Learning examples (few-shots) | Experimental | Populated by detected positive/negative feedback. |
| Visual memory (screenshot index) | Stable | Written on every browser capture. |
| Temporal world model (`world_timeline`) | Beta | Crypto prices + user-state changes tracked. |
| Self-model | Beta | Strengths, failures, preferences updated each message; file-backed at `/data/memory/self_model.json`. |
| Epistemic state | Beta | Per-domain confidence (programming, legal, etc.). |
| Background consolidation cycle | Beta | Runs every hour when idle (>2h or 1-7am); consolidates memory + extracts KG. |
| Autonomous goal generator | Beta | Rate-limited (1/hr, 5/day); critical-threshold checks bypass LLM. |
| CPI monitor (cognitive pressure index) | Stable | 5-min cadence; pauses heavy jobs when >80. |
| Self-integrity monitor | Stable | 6h cadence; cross-checks self-model vs actual rates. |

## Integrations

40+ integration connectors are present (Slack, Discord, Telegram, WhatsApp, Notion, GitHub, Google Calendar, Spotify, Trello, etc.). Each is **Beta** at minimum — connector code is implemented but the OAuth/setup flow has been exercised only for a subset:

- **Stable**: Gmail, Google Calendar (OAuth tested end-to-end).
- **Beta**: Slack, Discord, GitHub, Notion, Webhook, MCP.
- **Experimental**: everything else — code is present; production validation is pending.

See `dashboard → Integrations` for the current connection status of each in your install.

## Known broken / disabled
- `wasp restore` cannot restore a Postgres dump that pre-dates a schema change without manual intervention; pair restore with a matching WASP version.
- Backup rotation is bounded only inside the agent-core data volume (`/data/backups`). Host-side backups (`${WASP_DIR}/backups`) are NOT auto-rotated; prune them with your usual operator hygiene.
- `procedural_memory`, `behavioral_rules`, `learning_examples` may show zero rows on a fresh install — this is expected, not a bug.
- 17track shipping tracking depends on JavaScript rendering — Cloudflare may block automated requests. WASP routes through the browser skill, but tracking pages with strong bot detection can still fail.

## Reporting issues

If something documented as "Stable" or "Beta" doesn't work for you, please open an issue with: WASP version (`cat VERSION`), OS/distro, `wasp logs agent-core --tail=100`, and the exact input that reproduced the problem.

For security issues: see SECURITY.md.
