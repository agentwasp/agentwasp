---
id: changelog
title: Changelog
description: Full version history and release notes for WASP.
---

# Changelog

All notable changes to WASP are documented here. Versions follow a semantic versioning scheme after the initial phase-based development (Phases 1–18).

---

## v2.7.2 — May 20, 2026

**Focus: Installer hotfix on top of v2.7.1. One-line fix for a regression introduced by PR #9.**

### Fixed

- **#11 / PR #12**: Fresh install aborts at step 9/10 with `Install failed at line 559`. The PR #9 UFW gating logic grepped for `DASHBOARD_BIND=` in `.env` without `|| true`; under `set -Eeuo pipefail` a missing match returned exit 1 and aborted the installer. The shipped `.env.example` did not include the key, so every new install hit the error. Fix wraps both grep call sites and adds `DASHBOARD_BIND=127.0.0.1` to `.env.example` with inline documentation.

### Docs (follow-up — same v2.7.2 cycle, no new tag)

- **Dashboard access not documented after the v2.7.1 binding change.** The v2.7.1 release moved the dashboard to `127.0.0.1:8080` by default, but the README still claimed `Default dashboard: http://<your-host>:8080` and the docs-site had only a single passing reference. A new operator following the README would conclude the dashboard was broken. Fixed:
  - README updated to point at the new page.
  - New page [Dashboard Access](/getting-started/dashboard-access) covering the three supported patterns: SSH tunnel, TLS reverse proxy (Caddy + nginx examples), and the `DASHBOARD_BIND=0.0.0.0` opt-in for short-lived LAN testing.
  - [Environment Variables](/getting-started/environment-variables) now lists `DASHBOARD_BIND` (was missing despite shipping in `.env.example`).
  - [First Launch](/getting-started/first-launch) and [Installation](/getting-started/installation) link to the new page.

### Notes

- Maintainer-self-reported. Bug shipped in the v2.7.1 tarball but is not exploitable; it only blocks the installer.
- Existing v2.7 to v2.7.1 upgrades via `wasp update` were not affected — only fresh installs.

---

## v2.7.1 — May 19, 2026

**Focus: Security patch release. Four issues from an external 9-engine security audit ([@Lucky3mc](https://github.com/Lucky3mc) via Debuggix), plus the post-launch hardening commits that landed between the v2.7 tag and this release.**

### ⚠️ Breaking change for VPS installs

The dashboard host port is now bound to `127.0.0.1` by default. v2.7 installs that accessed the dashboard at `http://VPS-IP:8080` lose remote access after `wasp update`. Migration options:

1. SSH tunnel: `ssh -L 8080:127.0.0.1:8080 user@vps`, then open `http://localhost:8080` locally.
2. Reverse proxy with TLS (nginx, Caddy, Traefik) pointing at `127.0.0.1:8080`.
3. `DASHBOARD_BIND=0.0.0.0` in `.env` to opt back in (only after option 2 is in place).

### Security fixes

- **#2 / PR #6**: Path traversal in `image_path` and `audio_path` parameters across four model providers. Crafted paths could exfiltrate arbitrary files readable by the container process to the LLM provider. New helper `src/utils/path_safety.py::validate_media_path()` realpath-resolves inputs and rejects anything outside the legitimate media dirs.
- **#3 / PR #7**: SQL identifier interpolation hardening in `metrics.py`, `reset.py`, `integrity.py`. Not exploitable today (values come from constants), but each call site now explicitly validates against an allowlist or strict identifier regex before interpolation.
- **#4 / PR #9**: Dashboard exposed publicly by default. `docker-compose.yml` now binds to `${DASHBOARD_BIND:-127.0.0.1}` and `install.sh` only opens UFW port 8080 on explicit opt-in.
- **#5 / PR #8**: 38 vulnerabilities in docs-site dependencies (lodash, fast-uri, DOMPurify, Mermaid, serialize-javascript, and more). Docusaurus bumped 3.9.2 → 3.10.1, `serialize-javascript` overridden to `^7.0.5`, `@docusaurus/faster` added. Audit now clean.

### Post-launch fixes shipped in v2.7.1

- **#1**: Installer on macOS. Pre-flight checks branch on `$PKG_FAMILY`.
- **PowerShell installer logo**: replaced misaligned ASCII with ANSI Shadow Unicode blocks, forced UTF-8 console output.
- **Published installer SHA-256 checksums** at `https://agentwasp.com/install.sh.sha256` and `/install.ps1.sha256` for verify-before-pipe.
- **Official contact email**: `lab@agentwasp.com`.
- **Discord community link** on the landing page.
- **Removed `containers/agent-nginx/`** from the public source tree (operator-only landing-page container, not part of the agent runtime).

---

## v2.7 — May 13, 2026

**Focus: First public OSS release — installer, packaging hygiene, cross-distro validation, dashboard UX bug fixes, security hardening.**

### Highlights

- **First public release**: WASP is now installable in one line on any clean Linux host (Debian, Ubuntu, RHEL/AlmaLinux/Rocky, Fedora, Arch, openSUSE, Alpine) plus macOS and Windows via WSL2.
- **Dashboard navigation bugs fixed**: tab bars, filter pills, and pagination on every list page (Memory, Tasks, Cognitive, World Model, Skill Evolution, Vector Memory, Goals) silently failed under SPA navigation. Two root-cause fixes in `base.html` repair the whole class of bugs.
- **Cross-distro installer**: real bugs caught by smoke-running `install.sh` against fresh Debian 12, AlmaLinux 9, and Alpine 3 containers.
- **Public release packaging**: dedicated `scripts/build-release.sh` produces a clean tarball with a forbidden-pattern scan that refuses to package operator-specific identifiers.

### Dashboard fixes

- **SPA same-path query-string no-op**: `_navigate` in `base.html` compared only `location.pathname`, ignoring query strings. Clicking `/memory?tab=kg` from `/memory?tab=store` was a silent no-op. Fixed by comparing the full URL.
- **Tab init scripts dying on re-visit**: pages that declared `const TABS = ...` or `let _activeTab = ...` at top level (cognitive, world-model, skill-evolution, vector-memory, goals, tasks) threw `SyntaxError: redeclaration of const X` the second time you visited them via SPA. The SPA loader now wraps re-injected inline scripts in an IIFE.

### CheckIn job

- Refused to send the "¿Necesitas ayuda con algo?" proactive message when there is zero episodic memory (fresh install). Previously the very first message a brand-new install ever sent could be this proactive prompt before the user said anything.

### Telegram bridge

- **Welcome message** rewritten for warmth and clarity. `/start` shows a concise capability summary with restrained emoji use; the long command reference moved to `/help`. Translated EN / ES / PT / FR.
- **Fail-closed start**: Telegram bridge refuses to start if `TELEGRAM_ALLOWED_USERS` is empty. No public-bot mode. No escape hatch.
- **Wizard simplified**: requires one numeric Telegram id, replicates it to both `TELEGRAM_ALLOWED_USERS` and `SCHEDULER_NOTIFY_CHAT_ID`.

### Security & hardening

- **`gmail send`** enforces `GMAIL_RECIPIENT_ALLOWLIST` when set (per-address or `@domain.com`). Defense-in-depth vs prompt injection.
- **Docker socket** no longer mounted into `agent-core` on the public default. Only `agent-broker` retains socket access for compose orchestration.
- **Self-improve `dry_run`**: `write` and `patch` accept `dry_run="true"` — returns unified diff + AST validation without touching the file.
- **SSRF centralized** in `utils/network_safety.py` with DNS-rebinding protection and manual redirect re-validation. Applied to `http_request`, `fetch_url`, `scrape`, `monitors`, `subscriptions`.
- **Self-repair prompts** use `${WASP_HOST_DIR}` (set by the installer) instead of any hardcoded path.

### Cross-distro installer fixes

| Bug | Where | Fix |
|---|---|---|
| `df -BG ""` crash for top-level install dirs | line ~275 | Fallback parent to `/` |
| `hostname -I` fails on BusyBox/Alpine | line ~564 | Fallback chain: `ip → localhost` |
| `dnf install curl` blocked by `curl-minimal` | `pkg_install` | Added `--allowerasing` for rhel/fedora |

### Testing

- 38 new tests for the four Experimental cognitive subsystems (learning feedback detection, procedural sequence checks, behavioral conflict detection, dream module load). Suite total: 622 passing.

### Removed

- Public `TELEGRAM_ALLOW_PUBLIC` escape hatch — gone.
- Internal `agent-nginx` container and `docs/reports/` excluded from the public tarball.
- Operator secret-rotation tracker removed from the public archive (kept only in the operator vault).

### Migration notes

Existing v2.6 deployments don't need to migrate — internal compatibility is preserved. The new packaging path (`scripts/build-release.sh`) is only for producing the public release artifact; running `wasp update` continues to work the same way.

| Metric | v2.6 | v2.7 |
|---|---|---|
| Public-facing installer | none | `install.sh` (8 distros + macOS + WSL2) |
| Tarball | n/a | 2.1 MB, 484 files, allowlist-built |
| Tests passing | (internal) | 622 |
| Documented commands | 13 | 13 (+ wizard hardening) |
| Public Docker socket exposure in agent-core | yes (ro) | no (broker only) |

---

## v2.6 — April 30, 2026

**Focus: Edge Fix Pass (6 surgical fixes) + Final Pre-Production Hardening Pass (10 fixes) + Panic Reset dashboard page**

### Highlights

- **6 edge-case fixes** that close specific hallucination and correctness failure modes without changing golden-path behavior.
- **10 pre-production hardening fixes** covering security, reliability, observability, and learning quality.
- **Panic Reset page** — single-operation hard reset with confirmation gate.

---

### Edge Fix Pass (April 30, 2026)

Six surgical fixes applied across `events/handlers.py` and `policy/response_guard.py`. Each fix targets a specific hallucination or correctness failure mode.

#### 1. Low-Intent Cold-Start Guard (`events/handlers.py`)

Short messages on a fresh chat without prior context are one of the most reliable hallucination triggers. Without an anchor in chat memory, a single token like "ok" or a context-required phrase like "do the same" gives the LLM nothing to ground on, and it reaches for training-data noise.

New deterministic guard:

- `_LOW_INTENT_TOKENS` frozenset — single-token confirmations and acknowledgements (multilingual).
- `_LOW_INTENT_EMOJI_RE` — emoji / digit / punctuation-only messages.
- `_CONTEXT_REQUIRED_PHRASES_RE` — phrases like "do the same", "again", "same as before" that *require* prior context to be meaningful.

`_is_low_intent()` returns True when: single ambiguous token, emoji-only, context-required phrase without anchor, or ≤2 tokens all in the ambiguous set. When low-intent + no scheduled-language match + no `last_exchange` anchor, the handler returns a clarification fast-path in the user's detected language and **never invokes the LLM**.

Greetings ("hello" / "hi" / "hey" / "ping") intentionally excluded — they have a dedicated friendly-response path. Bypassed for `[RETRY OF PREVIOUS:` messages (those have explicit anchor).

#### 2. Multi-URL Aggregator: `Error:` Prefix Detection (`events/handlers.py` ~line 5385)

When auto-detect resolves multiple URLs in a single user message, the multi-URL aggregator builds a deterministic per-URL outcome list. The browser skill returns `success=True` even when its output begins with `Error: URL blocked...` (SSRF blocklist hit, file:// block, RFC-1918 block) — `success` only means "the skill itself didn't crash", not "the URL was reachable".

**Before:** SSRF-blocked URLs labeled ✅ navigated.
**After:** `Error:` prefix detected first; URL labeled ❌ with the first-line error message.

Outcome icons:

| Icon | Meaning |
|------|---------|
| ✅ navegado / navigated | Browser reached the URL successfully without screenshot |
| ✅ captura enviada / screenshot sent | Screenshot captured and attached |
| 🚫 bloqueado / blocked | Login wall or captcha (`[CAPTURE_VALID: false]`) |
| ❌ &lt;error line&gt; | `Error:` prefix detected (SSRF, file://, RFC-1918, etc.) — first 120 chars |

Test case (passes): `captura https://192.168.0.1 y https://10.0.0.1` → both URLs correctly labeled ❌.

#### 3. Agent Name Preservation: Non-Greedy Regex (`events/handlers.py`)

`_AGENT_NAME_PATTERNS` (multilingual alternations matching `named X` and equivalent constructions) was greedy — for an input like `create an agent named Crypto Watcher that monitors prices every 3 hours`, the regex captured the entire phrase as the name.

Fix: non-greedy multi-token capture `[\w-]+(?:\s+[\w-]+){0,4}?` with a lookahead stop-set on clause connectors (`that`/`to`/`with`/`for`/`on`/`in` and equivalents) and punctuation. Quoted form (`named "Foo Bar"`) takes priority via the first alternation group.

| Input | Extracted Name |
|-------|----------------|
| `create an agent named Bob to track news` | `Bob` |
| `create an agent named "Crypto Watcher" for BTC alerts` | `Crypto Watcher` |
| `create an agent named News Watcher that monitors RSS feeds every hour` | `News Watcher` |

#### 4. Schedule Honesty Bidirectional (`policy/response_guard.py`)

`task_manager` only supports interval scheduling. It does NOT support fixed clock times (`at 9am`) or daypart phrases (`in the morning`). Two directions of dishonesty were possible:

1. **Agent-side lie** (existing): response asserts a clock time → guard strips it.
2. **NEW user-side silent misinterpretation**: user requests a clock time or daypart, agent creates an interval task without disclosing the gap. Operator believes their schedule was honored.

New behavior:

- **User-side clock-time branch**: when the user requested a specific clock time (matches AM/PM, `:`, or `o'clock`) AND `has_real_task_create(skill_results)` returns True → response is appended with a disclaimer that the task does not run at the requested clock time and that `task_manager` only supports interval scheduling (every N hours from creation time).
- **NEW daypart branch** (`DAYPART_CLAIM_RE`): matches phrases like `in the morning`, `every evening`, `at dawn`, `at noon`, `at midnight`, and equivalents in supported languages → identical disclaimer family.

Trace fields: `had_real_create=True`, `claimed_time=<requested>`, `origin in {"user_text", "user_text_daypart"}`. Guard skipped when numeric match without AM/PM/colon (likely an interval expression).

#### 5. Markdown Link Sanitizer (`policy/response_guard.py`)

The sanitizer previously handled image syntax `![alt](url)` only. Plain `[text](url)` markdown links leaked through and rendered literally in Telegram.

Fix: new `_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\((https?://[^\s)]+)\)")`. Matches collapse to `text (url)` form so the URL stays accessible without raw markdown chars rendering literally. Negative lookbehind `(?<!!)` prevents double-handling of image syntax.

Example:

- Before: `See more details at [this page](https://example.com/foo)` → renders with literal `[]()` brackets
- After: `See more details at this page (https://example.com/foo)` → readable

Trace records `stripped: ["link"]` for post-hoc analysis.

#### 6. Entity-Proximity Verdict Check (`policy/response_guard.py`)

The verdict-evidence check guards against tracking-code hallucinations: when a user pastes a postal/courier tracking code, the browser may navigate to a tracking-site home page that contains words like "delivered" as static UI labels for unrelated shipments. Without entity proximity, the LLM could stitch these unrelated labels with the user's specific tracking code into a fabricated claim.

The previous check was too lenient — verdict word *anywhere* in body counted as evidence.

Fix: 200-character proximity window between any user-named entity and any verdict occurrence:

- `_user_named_entities()` extracts user-specified codes via `_USER_ENTITY_RE`:
  - `[A-Z]{2}\d{9}[A-Z]{2}` — China Post / EMS format
  - `1Z[A-Z0-9]{16}` — UPS format
  - `\d{12,22}` — generic long numeric (FedEx etc.)
  - `[A-Z]{4,6}\d{6,10}` — alphanumeric mix
- `_skill_output_supports_verdict()` extended with `user_entities` parameter.
- When entities present and verdict never co-occurs within 200 chars of any entity in any successful skill body → not evidence → honest fallback returned.
- `_has_useful_skill_data()` also extended: outputs that don't contain user-specified entities don't count as useful data for factual grounding.

Verdict keywords cover delivery states in supported languages (`delivered`, `in transit`, `out for delivery`, `pending`, `received`, `in customs`, and equivalents).

---

### Final Pre-Production Hardening Pass (April 15, 2026 — 10 Fixes)

#### New

- **Panic Reset page** (`/reset`): hard-confirmation UI (must type "RESET WASP", paste blocked) that wipes all 17 DB tables, 12+ Redis key patterns, agent identity XP/birth date, self-model, and runs `VACUUM FULL`. Progress streams live to the page; result shows in a green-bordered card with `WaspToast` notification. AuditLog entry written for every reset.
- **Weekly VACUUM ANALYZE** (`scheduler/db_maintenance.py`): `DbMaintenanceJob` runs every 604,800 s (weekly) outside a transaction (`AUTOCOMMIT`) — reclaims dead-row space and updates PostgreSQL planner statistics without table locking.
- **Shell invocation audit logging** (`skills/builtin/shell.py`): every `shell` skill call writes one `AuditLog` row with `action="skill.shell"`, redacted command (strips sk-*, AIza*, xai-*, hf_*, key=value passwords), exit code, and optional `goal_id` context. Fire-and-forget via `asyncio.ensure_future()`.
- **Health dashboard: behavioral queue depth**: new "Learning Queue" panel in the Safety & Execution Control grid shows `behavioral:pending` queue depth / 50 cap with progress bar — green (0–19), yellow (≥20), red (≥40, LLM storm risk).

#### Security

- **SSRF blocklist on `fetch_url`** (`skills/builtin/fetch_url.py`): imported `_is_ssrf_target()` from `http_request.py`; blocks RFC-1918, loopback, and cloud metadata endpoints before any HTTP connection. `fetch_url` now matches `http_request` SSRF protection.
- **Self-improve syntax validation + backup** (`dashboard/routes/self_improve.py`): `ast.parse()` validates Python content before write (rejects with HTTP 400 on `SyntaxError`); `shutil.copy2()` creates timestamped backup at `/data/src_patches/backup_{ts}_{filename}` before overwrite; `backup_path` returned in success JSON.

#### Reliability

- **Boot model liveness ping** (`events/handlers.py`): `_run_boot_sequence()` performs an 8 s timeout, `max_tokens=1` LLM ping; boot message shows "live ✓" or "unreachable ✗"; explicit warning when unreachable directs operator to `/models`.
- **Boot cognitive-state warning** (`events/handlers.py`): fresh/post-reset boot message warns that all memory has been cleared and sets expectations for the rebuild period.
- **Behavioral queue drop-count logging** (`memory/behavioral.py`): existing 50-item cap enhanced with precise `before`/`after` llen tracking; logs `behavioral.queue_cap_trimmed` with `dropped` count when items are evicted.

#### Learning Quality

- **Behavioral rule conflict detection** (`memory/behavioral.py`): `_NEGATION_WORDS` frozenset + `_has_conflict()` function; detects contradictions (35% core-word overlap + negation asymmetry); logs `behavioral.rule_conflict_detected` — rule is saved but conflict is surfaced for operator review.

---

### Scale update

| Metric | v2.5 | v2.6 |
|--------|------|------|
| Scheduler jobs | 40 | 41 |
| AuditLog action types | `skill.self_improve` | + `skill.shell`, `agent.reset` |
| Health panel count | 3 | 4 |
| Dashboard pages | 23 | 24 (+ `/reset`) |
| Response-guard checks | 9 | 11 (entity-proximity, schedule daypart) |

---

## v2.5 — April 7, 2026

**Focus: Dashboard restructure, production audit fixes, 2026 model catalog update, new cognitive subsystems**

### New

- **Dashboard full restructure**: sidebar reorganized into 5 sections (Overview, Cognition, Memory, Tools, Operations); 5 new pages added:
  - `/self-improve` — read/propose/apply/reject code patches with diff view and syntax validation
  - `/behavioral` — view, filter, and delete behavioral rules learned from corrections
  - `/knowledge` — browse knowledge graph nodes and relations with entity type filters
  - `/subscriptions` — manage RSS feeds and price alert subscriptions
  - `/config` — runtime config overrides (`config:overrides` Redis hash) without container restart
- **HealthState Adaptive Execution**: `HealthMonitor` evaluates composite health score every 60s; when score drops below 70, `health_state=DEGRADED` flag set in Redis; scheduler jobs and anticipatory simulation check flag and downgrade to lightweight mode
- **SaccadicVision Change Detection Daemon** (`scheduler/saccadic.py`): `SaccadicVisionJob` runs every 600s; takes periodic browser screenshots of monitored URLs; pixel-diff comparison via `Pillow`; sends Telegram alert when visual change exceeds 8% threshold; state stored in `saccadic_vision` DB table
- **Dream Failure Pattern Analysis**: `DreamJob` now includes a failure-pattern phase — queries last 48h of `audit_log` for error spikes, identifies top-3 failing skills, injects findings into dream reflection prompt for proactive repair suggestions
- **Self-Improve Soft Safety Gate** (`dashboard/routes/self_improve.py`): `_self_improve_soft_gate()` deterministic pattern check runs before any write; BLOCK if content targets critical paths (`sandbox.py`, `control_layer.py`, `behavioral.py`, `response_grounder.py`) AND contains safety-weakening patterns (`disable sandbox`, `bypass guard`, `_HIGH_RISK_ACTIONS=frozenset()`); WARN on large patches to critical paths; all decisions logged to `audit_log`
- **Self-Improve diff-awareness precision patch**: patch apply logic uses `old_text`/`new_text` pairs with exact context matching; rejects ambiguous patches where `old_text` appears more than once in the file

### Security

- **SHA-256 sidecar verification** (`utils/patch_integrity.py`): every file written by `self_improve` patch action generates a `.sha256` sidecar at `/data/src_patches/{filename}.sha256`; `apply_persisted_patches()` at startup verifies hash before applying — tampered patches are rejected with `CRITICAL` log
- **CSP `unsafe-eval` documented**: Content-Security-Policy header audit confirmed `unsafe-eval` required by Jinja2 template rendering; documented in security page with mitigation notes
- **`config:overrides` runtime**: sensitive config keys (`ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `DB_URL`) blocked from override via `_BLOCKED_OVERRIDE_KEYS` set; all override writes logged to `audit_log`

### Reliability

- **Audit log retention job** (`scheduler/audit_retention.py`): `AuditRetentionJob` runs every 86,400s (daily); hard-deletes rows older than 90 days from `audit_log`; logs `audit_retention.deleted count=N`
- **Bounded Redis Streams**: `events:incoming` and `events:outgoing` streams capped at 10,000 entries via `MAXLEN ~10000` on every `XADD`; prevents unbounded memory growth during Telegram polling storms
- **PEL (Pending Entry List) recovery**: `StreamConsumerJob` checks PEL length every tick; entries idle >30min are claimed and re-delivered; prevents message loss on container crash mid-processing
- **Keyset pagination for memory queries** (`memory/learning.py`): `get_recent_examples()` and related queries migrated from `OFFSET` to `id > last_seen_id` keyset pagination; eliminates O(n) table scans on large `learning_examples` tables
- **Composite DB index** (`db/models.py`): `Index("ix_audit_log_chat_created", AuditLog.chat_id, AuditLog.timestamp)` added; reduces audit-log query latency from ~400ms to ~12ms on 100k-row tables
- **SaccadicVision lifecycle**: `SaccadicVisionJob` cleans up screenshot files older than 7 days from `/data/screenshots/`; prevents disk exhaustion on long-running instances
- **`_vault`/`_policy` Redis key fix** (`memory/behavioral.py`): behavioral rule keys namespaced under `behavioral:rules:{id}` (was `_vault:{id}`) — eliminates collision with integration vault keys

### Model Catalog Update

- All 11 providers updated to 2026 model catalogs: Anthropic (Claude 4.6 family), OpenAI (GPT-5 family), Google (Gemini 2.5 family), xAI (Grok-3 family), Mistral (Mistral Large 3), Cohere (Command R+ 2025), Fireworks, Together AI, Perplexity, Groq, Ollama
- Model router updated with new capability classifications for vision, code, reasoning, and quick-response task types

### Scale update

| Metric | v2.4 | v2.5 |
|--------|------|------|
| Scheduler jobs | 35 | 40 |
| Dashboard pages | 18 | 23 |
| DB tables | 17 | 21 |
| Supported model providers | 8 | 11 |

---

## v2.4 — April 3, 2026

**Focus: Response grounding hardening, domain lock precision, evidence-state typed flags**

### New

- **Response Grounding Engine Checks 5–9** (`skills/response_validator.py`): five new validation gates added to `ResponseGrounder.validate()`:
  - **Check 5 — Weak-response rejection**: detects responses consisting primarily of apologies or capability disclaimers (`I'm sorry`, `I can't`, `as an AI`) when the agent has the required skill; forces skill invocation instead
  - **Check 6 — Generic phrase filter**: blocks filler responses (`Let me check that for you`, `Great question!`, `Certainly!`) when no substantive answer follows; triggers `should_retry=True`
  - **Check 7 — Status-marker validation**: if response contains `✅`/`❌` status markers, validates that a corresponding skill result exists in the conversation round; prevents fabricated status reports
  - **Check 8 — Intent evidence gate**: for information-seeking queries, requires at least one `MONITORED` or higher skill call in the response round; blocks pure hallucinated answers
  - **Check 9 — Anti-hallucination guard for numeric claims**: detects responses with specific numbers (prices, dates, counts) that lack a verifiable skill-result source; injects `[REQUIRES_GROUNDING]` flag and forces re-run with web search
- **DomainLock Hardening** (`skills/response_validator.py`): four precision fixes to the domain lock subsystem:
  - **Root normalization**: `example.co.uk` and `www.example.co.uk` now treated as same domain (strips `www.`, handles multi-part TLDs)
  - **Semantic category guards**: domains in the same semantic category (e.g., two crypto exchanges, two news sites) no longer cross-lock; prevents false positives where agent searched two legitimate sources
  - **Anchor domain field**: `DomainLock` object now stores `anchor_domain` (the first-seen domain that triggered the lock); logged with every lock decision for debugging
  - **Cross-turn stale lock clearance**: domain locks older than 3 conversation turns are automatically cleared; prevents stale locks from blocking legitimate follow-up queries
- **EvidenceState typed flags** (`agent/evidence.py`): new `EvidenceState` dataclass replaces ad-hoc boolean flags; fields: `has_skill_result`, `has_grounded_number`, `has_status_marker`, `has_intent_evidence`, `grounding_source`; passed through `ResponseGrounder` and stored in round context for post-hoc audit

### Fixed

- `response_validator.py`: domain lock was triggering on `fetch_url` calls to the same base domain as a prior `web_search` result — fixed by adding `fetch_url` to the `_SAME_DOMAIN_EXEMPT_SKILLS` set
- `orchestrator.py` (goal): chain-break condition checked wrong action strings (`"blocked"` instead of `"autonomy_blocked"`, `"sandbox_denied"`, `"budget_exceeded"`) — goals with blocked tasks were retrying indefinitely instead of failing
- `handlers.py`: `results.index(result)` for browser URL tracking raised `ValueError` on duplicate results — fixed with `enumerate()` + index tracking

### Scale update

| Metric | v2.3 | v2.4 |
|--------|------|------|
| Response grounding checks | 4 | 9 |
| Domain lock precision fixes | 0 | 4 |
| EvidenceState flags | 0 | 5 |

---

## v2.3 — March 28, 2026

**Focus: Universal Interaction Validation Layer, SPA support, browser reliability**

### New

- **Universal Interaction Validation Layer** (`skills/builtin/browser.py`): four-phase validation wrapper around every browser click and form interaction:
  - **Phase 1 — Pre-click validation**: verifies element is visible, enabled, and not obscured before dispatching click; raises `InteractionError` with screenshot evidence if any check fails
  - **Phase 2 — Post-click interference detection**: after click, scans for modal overlays, cookie banners, CAPTCHA iframes, and anti-bot challenges; automatically dismisses cookie banners; pauses and logs on CAPTCHA detection
  - **Phase 3 — Result-state confirmation**: waits for DOM stabilization (network idle + no pending XHR); compares URL and key DOM checksum before/after click to confirm navigation or state change occurred
  - **Phase 4 — Validated screenshot capture**: final screenshot taken only after all three prior phases pass; screenshot path and interaction outcome logged to `audit_log` with `action="browser.interaction"`
- **div-button SPA support**: JavaScript-rendered `<div role="button">` and `<span>` click targets now handled by `_click_spa_element()` helper; dispatches both `mousedown` + `mouseup` + `click` synthetic events; supports React/Vue SPAs that use non-form click targets for parcel-tracking and similar flows
- **Browser handler timeout increase**: `handle_browser_action()` timeout raised from 90s to 150s for navigation-heavy operations; `handle_page_load()` raised from 150s to 180s for JavaScript-heavy SPAs

### Fixed

- **Enforcement loop fix** (`skills/builtin/browser.py`): `_action_terminal_detected()` guard was combined with `and not` logic that caused the enforcement loop to exit prematurely on the first non-terminal action; fixed to check terminal state independently per loop iteration
- `handlers.py`: generator nesting inverted in `all_skill_calls_raw` comprehension — learning loop was always receiving empty results; fixed by swapping `for` clause order
- `executor.py`: `result.output[:500]` and `result.error[:300]` crashed with `TypeError` when `output` or `error` was `None`; fixed with `(result.output or "")[:500]` guards

### Scale update

| Metric | v2.2 | v2.3 |
|--------|------|------|
| Browser interaction phases | 1 | 4 |
| Handler timeout (navigation) | 90s | 150s |
| Handler timeout (page load) | 150s | 180s |
| SPA click targets supported | div[onclick] | div[role=button], span, custom |

---

## v2.2 — March 24, 2026

**Focus: deep_scraper hardening, security fixes, capability map completeness**

### New
- `deep_scraper` promoted from custom OpenClaw skill → permanent built-in skill (`src/skills/builtin/deep_scraper.py`)
- `deep_scraper` SSRF protection: `_is_safe_url()` resolves all A/AAAA records via `getaddrinfo()`, blocks loopback/private/link-local/reserved IPs, fails closed on DNS failure; runs via `asyncio.to_thread()` (non-blocking)

### Fixed
- `auto_detect.py`: YouTube URL detection was routing to `shell` skill with raw docker command (security bypass) — now correctly routes to `deep_scraper(url=...)` with full capability enforcement
- `skills/builtin/__init__.py`: `delete_reminder` and `meta_orchestrate` added to `_CAPABILITY_MAP` (were relying on default fallback — now explicitly declared)
- `response_validator.py`: `deep_scraper` added to `_PRICE_GROUNDING_SKILLS` (consistent with `browser_deep_scrape`)

### Cleanup
- `/data/skills/deep-scraper/` custom skill directory removed — eliminates phantom custom skill entry in the Skills dashboard page

---

## v2.1 — March 23, 2026

**Focus: production audit, browser CPU fix, security hardening, multilingual support**

### New
- **Browser Session Idle Reaper**: daemon thread closes Chromium sessions idle >300s — fixes chronic 80%→0.25% CPU exhaustion from stale sessions
- **Browser URL blocklist**: blocks `file://`, `javascript:`, `data:`, `vbscript:` schemes and RFC-1918/loopback/cloud metadata IMDS addresses
- **Multilingual Auto-Detect**: `lang_detect.py` — browser/screenshot/navigation patterns in EN, ES, PT, FR, DE, ZH, JA, KO, AR, RU; localized fallback responses in 10 languages
- **Domain Drift Protection**: validator catches browser→crypto/email substitution attempts; `should_retry=False` on confirmed substitution; Capability Engine skips when auto-detect already handled the request

### Fixed (6 bugs from production audit)
- `autonomous.py`: autonomy_mode was set to `"auto"` (invalid enum) — goal creation was completely broken; fixed to `autonomy_mode=None`
- `handlers.py`: recovery round used wrong `generate()` signature — recovery never executed; fixed to `ModelRequest(...)`
- `handlers.py`: `_can_recover` was overriding validator's `should_retry=False` via `or reason=="drift"` — now respects validator decision
- `handlers.py`: screenshot path collection used `search` (first match only); fixed to `finditer` (all paths); `browser_screenshot_full_page` added to filter
- `handlers.py`: Capability Engine was running even when auto-detect already handled the request — potential double-execution; now gated by `not auto_calls`
- `behavioral_learner.py`: Telegram notifications were published to `"agent:outgoing"` (dead stream) — silently lost; fixed to `"events:outgoing"`

### Security
- `self_improve.py`: `_list_files()` path containment now uses `realpath()` (matches existing check in `_read_file()`) — prevents symlink traversal
- `redaction.py`: AIza pattern broadened to `{25,}` (was `{35}`); AKIA pattern to `{12,}` (was `{16}`)
- `capability_engine.py`: blocks raw skill output in email body (`Screenshot saved to`, `/data/screenshots/` paths, `⚠️ Verify the title`)

---

## v2.0

**Focus: Active Flow Context Lock, Planning Mode override, Response Contract, Intent Completeness**

### New
- **Active Flow Context Lock**: per-chat Redis state (TTL 15 min) survives LLM failures; follow-up messages anchored to the same domain; `[ACTIVE FLOW — CONTEXT LOCK]` block injected into system prompt — eliminates cross-domain hallucination (e.g., crypto question answered with weather data)
- **Planning Mode Hard Override**: 5-layer execution block (auto-detect → Decision Layer → Capability Engine → LLM loop → Validation safeguard); when user says "no ejecutes / solo analiza / antes de ejecutar", zero skills run regardless of LLM output
- **Universal Response Contract**: `_detect_response_type()` classifies each request (comparison / multipart / list / explanation / action / chat); type-specific structure rule injected into every system prompt via `_build_cognitive_control_block()`
- **Intent Completeness Engine**: `intent_engine.py` — deterministic multi-part intent extraction (4 strategies: colon list, numbered list, conjunctive chain, multi-question); one completeness-retry per turn with exact missing-section correction prompt
- `flow_state.py` (new): `save_active_flow()`, `load_active_flow()`, `clear_active_flow()`, `is_explicit_domain_switch()`, `is_crypto_recovery_followup()`, `detect_flow_assets()`

### Improved
- `ResponseValidator.validate()` now accepts `planning_mode=True` — new `_check_planning_mode_violation()` fires first when active
- `ResponseValidator._check_completeness_multipart()` — blocks structurally incomplete multi-part answers (≥2 `?`, enumeration starts, conjunctive markers)
- `render_report.py` (crypto): premium terminal-grade format with aligned columns, volume in B/M notation, price arrows inline, separate email/Telegram renderers

### Tests
- 34 new tests: `tests/test_flow_state.py` (all passing)

---

## v1.9

**Focus: Response Validation, voice input, audio pipeline, production fixes**

### New
- **Response Validation & Recovery Engine**: deterministic post-LLM validator — `grounding_fail` / `incomplete` / `drift` / `screenshot_incomplete` checks; 2-retry auto-recovery; no LLM calls in validation path
- **RecoveryMemory**: Redis FIFO store (50 entries, 7-day TTL) — only validated successful recoveries stored; no noise from failed attempts
- **Voice/Audio Input**: Telegram voice messages fully operational — `handle_voice()` in bridge downloads to `/data/shared/uploads/voice_{uuid}.ogg`; `transcribe_audio_sync()` calls OpenAI Whisper API via `asyncio.to_thread()` with 12s hard timeout; transcription fed into full LLM+skill pipeline
- `extract_fields.py` skill: extract named fields from previous skill output by path (e.g., `field_name:var_name`)
- Telegram typing indicator with 95s response timeout guard — `_pending` dict + `_response_timeout_guard()` — prevents stuck typing indicator on long responses

### Fixed
- Critical metadata decode bug: `bus.py` auto-decodes all Redis stream fields as JSON — handlers now accept both `dict` and `str` for metadata
- `_skill_round_count` UnboundLocalError (was used before assignment in some code paths)
- `check_screenshot_completeness()` now trace-based only (execution skills set) — no brittle response string matching

### Scale
- Scheduler: 25 → 27 background jobs
- Skills: 26 → 27 built-in skills (`extract_fields.py` added)
- DB: 18 → 21 tables (`AgentRecord`, `AgentMessage`, `BehavioralRule` added)

---

## v1.8

**Focus: Capability Engine production hardening, quality scoring, degradation detection**

### New
- **Capability Engine v2**: strict template validation — `_HARD_ARGS` abort, `_OPTIONAL_ARGS` → empty string, all others required
- **Weighted scoring**: `(kw_hits×2) + (success_rate×5) + (avg_completeness×3) + recency_bonus - latency_penalty`
- **Pre-execution static validation**: `_pre_validate()` checks all template vars before any step runs
- **Output completeness guarantee**: blocks incomplete renders; validates email body ≥50 chars
- **Improvement loop**: `completeness_history` (last 10 runs), EMA latency tracking, auto-degradation detection
- **AgentManagerSkill**: LLM can create/list/pause/resume/archive agents via natural language (`agent_manager` skill); late-wired to `AgentOrchestrator` in `main.py`

### Improved
- Goal Priority Axis: `Goal.priority` (1-10) + `Goal.source` fields; user goals=8, agent goals=6, autonomous=3; `tick()` sorts by priority descending
- Self-Integrity Monitor: `SelfIntegrityMonitorJob` every 6h — cross-checks self-model strengths vs actual skill success rates, detects epistemic drift, checks audit_log error spikes

---

## v1.7

**Focus: Memory & Resource Governance, Opportunity Engine, Self-Reflection Engine**

### New
- **Opportunity Engine** (`scheduler/opportunity_engine.py`): scans episodic memory for automation patterns (crypto, news, website, reports, API); max 2 suggestions/day, 48h dedup
- **Self-Reflection Engine**: LLM post-mortem insights after goal completion/failure; max 3/goal; Redis TTL 7d; injected into future context
- **Resource Governor**: Redis-backed rate limiting — goal slots (10), LLM/min (30), API/min (60), tasks/hour (50)
- **Goal-scoped Memory** (`goal_memory` table): episodic memory scoped to a specific goal's execution context — prevents cross-goal pollution
- **Memory Ranking System**: score = 0.5×similarity + 0.3×recency + 0.2×importance; applied before context injection
- `build_context()` accepts `goal_id` parameter; injects goal-scoped memory + reflection insights when provided

### Scale
- Scheduler: 23 → 25 background jobs (`opportunity_engine` added; `vector_index` already counted)
- Memory: 9 → 11 primary layers (goal_memory + self-model/epistemic)
- DB: new `goal_memory` table (auto-created via SQLAlchemy `create_all`)

### Observability
- New structured logs: `memory_retrieved`, `memory_ranked`, `goal_memory_added`, `goal_memory_used`, `opportunity_detected`, `opportunity_suggested`, `reflection_triggered`, `reflection_saved`

---

## v1.6

**Focus: Decision Layer, Production Hardening v2, Goal Engine improvements**

### New
- **Decision Layer** (`src/decision_layer.py`): pure heuristic pre-LLM classifier with 5 strategies — `DIRECT_RESPONSE` / `GOAL` / `SCHEDULED_TASK` / `SUB_AGENT` / `SCRIPT`; `SCHEDULED_TASK` and `SUB_AGENT` call skills directly without LLM (zero hallucination risk); `GOAL` routes directly to GoalOrchestrator
- **Behavioral Learning Loop**: `_detect_correction()` in handlers.py; correction queued to Redis `behavioral:pending`; `BehavioralLearnerJob` (every 120s) → LLM analysis → rule saved to `behavioral_rules` DB table → injected in every system prompt; rule types: refusal / hallucination / wrong_skill / missing_context
- **Cognitive Pressure Index (CPI)**: 0–100 composite metric (active goals 20%, error rate 25%, latency 20%, memory growth 15%, CPU 20%); background jobs skip when >80
- **Self-Integrity Monitor**: `SelfIntegrityMonitorJob` every 6h; cross-validates self-model against actual performance; JSON report at `agent:integrity_report`
- **Circuit Breaker Redis persistence**: circuit breaker state saved to `cb:state:{integration_id}` on every transition; TTL = max(86400, recovery_timeout×10)
- **Sovereign Mode**: `SOVEREIGN_MODE=true` (default); raises `MAX_SKILL_ROUNDS` to 12; injects `⚡ SOVEREIGN MODE ACTIVE` block; doubles cognitive budgets
- `delete_reminder` skill: deletes by keyword match or `keyword="all"`
- Self-repair: `patch(file, old_text, new_text)` surgical edits + `install(package)` runtime pip installs; all patches auto-persisted to `/data/src_patches/` and re-applied on rebuild

### Goal Engine
- **Plan Lock**: `goal.plan_locked = True` after first task succeeds — blocks spurious replanning while the plan is working
- **8-step cap**: plans exceeding 8 steps automatically truncated in topological order
- **Duplicate Goal Detection**: Jaccard word overlap ≥60% → return existing goal instead of creating duplicate
- **Structured observability events**: `plan_created` / `plan_locked` / `plan_replan` / `plan_completed`
- **Replan storm**: threshold 3 replans / 5 min (was 6 / 10 min); now marks goal FAILED with partial outputs collected (was PAUSED silently)
- **Planner step preference**: deterministic tool first → existing skill → LLM as last resort

### Fixed
- Duplicate task execution (removed immediate execution override — tasks now scheduled at `now + interval`)
- Month-boundary date parsing bug (`parsed.replace(day=parsed.day+1)` → `parsed + timedelta(days=1)`)
- PAUSED goals blocking agent forever — `runtime.tick()` auto-resumes after backoff, fails after 10min paused
- `_clean_telegram_output()`: strips markdown, prompt leakage (`[TAREA PROGRAMADA:]`, `EJECUTA AHORA`), execution summaries from all outgoing messages
- Auto-detect "nuevo agente" false positive — `_AGENT_CREATE_VETO_PATTERNS` blocks complaint text from triggering agent creation

### Scale
- Scheduler: 22 → 23 background jobs (`world_model` added)

---

## v1.5

**Focus: Next-Gen Cognitive Systems, Vector Memory, Security Hardening**

### New Cognitive Systems (6)
- **Vector Semantic Memory**: PostgreSQL `memory_embeddings` table; Ollama `nomic-embed-text` embeddings or deterministic SHA-512 fallback; cosine similarity search (top-K); injected into the system prompt as a labeled semantic-memory block; feature-flagged `VECTOR_MEMORY_ENABLED`
- **Plan Critic**: LLM validates TaskGraph before execution; enabled via `PLAN_CRITIC_ENABLED`
- **Meta-Agent Supervisor**: `meta_orchestrate` skill decomposes goal into coordinated agent team; `META_AGENT_ENABLED`
- **World Model**: `EntityState` table tracks real-world entity states (BTC price, trend, change %); `WorldModelJob` every 15min; entity cards on dashboard
- **Skill Evolution Engine**: `skill_patterns` table; detects recurring multi-skill sequences (min 5 occurrences); LLM synthesizes composite Python skill; AST validation before write; `SKILL_EVOLUTION_ENABLED`
- **Temporal Reasoner**: trend summaries injected as `[TEMPORAL INSIGHTS]`; `TEMPORAL_REASONING_ENABLED`

### Security Hardening (7 fixes)
- `self_improve`: all operations (`read`, `write`, `patch`) now use `realpath()` — closes symlink-based path traversal
- LLM-generated skill code: AST validation before write (blocks `subprocess`, `os.system`, `eval`, `exec`, etc.)
- CSRF: token now session-bound (rejects unauthenticated `"anon"` sessions before Redis lookup)
- `/data/memory` removed from `/chat/media` search dirs — prevents internal snapshots from being served publicly
- `skills.py`: slug re-validated on toggle/edit/delete via `_safe_skill_dir()` — prevents directory traversal
- `http_request`: `_is_ssrf_target()` blocks RFC-1918 + cloud metadata endpoints
- Error responses: `str(e)` replaced with first line only, capped at 120 chars — prevents internal info leakage

### Dashboard
- 3 new pages: Vector Memory (`/vector-memory`), World Model (`/world-model`), Skill Evolution (`/skill-evolution`)

### Scale
- Scheduler: 20 → 22 background jobs
- Memory: 8 → 9 persistent layers
- DB: 14 → 18 tables (`memory_embeddings`, `skill_patterns`, `entity_states`, `state_predictions`)
- 12 new configuration feature-flag variables

---

## Phases 1–18 (Core Development)

The initial 18 development phases built the foundational architecture of WASP:

| Phase | Key Systems |
|-------|-------------|
| 1–3 | Event-driven architecture (Redis Streams), core agent loop, episodic memory (PostgreSQL) |
| 4–6 | Skill system (SkillBase, SkillExecutor, PolicyEngine), custom skills, task scheduler |
| 7 | Health monitor, SelfHealer, Introspector |
| 8 | Dashboard (Quart), session auth, CSRF protection, audit logging |
| 9 | Agent autonomy — shell, Python execution, browser (Selenium + Chromium), named sessions |
| 10 | Knowledge Graph (PostgreSQL + Redis cache, rule-based NLP extraction) |
| 11 | Self-Model (Redis `agent:self_model`), Epistemic State, domain confidence |
| 12 | Procedural Memory (`abstract_procedure()`, keyword retrieval, few-shot injection) |
| 13 | Temporal World Model (`world_timeline` table, price/state extraction, trend detection) |
| 14 | Anticipatory Simulation (pre-execution consequence analysis for privileged skills) |
| 15 | Multi-agent orchestration v1 (AgentOrchestrator, AgentRuntime, CapabilitySandbox, inter-agent PostgreSQL bus) |
| 16 | Dream Mode (`DreamJob`: memory consolidation, KG enrichment, LLM reflection, world pre-fetch) |
| 17 | Autonomous Goal Generator (proactive LLM-evaluated goal creation, rate limiting, CPI guard) |
| 18 | QA/SRE audit — 208 tests (unit/integration/e2e/chaos/security), 9 connector ID fixes, Makefile |

---

## Statistics at v2.6

| Metric | Count |
|--------|-------|
| Built-in skills | 37 |
| Background scheduler jobs | 41 |
| Memory layers | 18 (11 primary + 7 auxiliary) |
| PostgreSQL tables | 20 |
| Integration connectors | 40+ |
| LLM providers | 11 |
| Max LLM rounds (Sovereign) | 12 |
| Max concurrent goals | 3 |
| Max concurrent agents | 10 |
| Test suite | 208 tests |
| AuditLog action types | skill.shell, skill.self_improve, agent.reset, + all goal/task actions |
| Dashboard pages | 24 |
