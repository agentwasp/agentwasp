# Changelog

All notable changes to WASP are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions: [SemVer](https://semver.org/). Full pre-OSS history (v2.3 → v2.6) lives at https://docs.agentwasp.com/changelog — the entries below cover the public-release work on top of that baseline.

## [2.7.2] — 2026-05-20 (installer hotfix)

Single-bug hotfix on top of v2.7.1. The v2.7.1 installer aborted at step 9/10 on fresh installs because the new UFW gating logic introduced in PR #9 grepped for `DASHBOARD_BIND=` in `.env` without tolerating a missing match under `set -Eeuo pipefail`. The shipped `.env.example` did not include the key, so every new install hit the error. Existing v2.7 to v2.7.1 upgrades via `wasp update` were not affected (the installer is only used for fresh installs).

### Fixed

- **Fresh install fails at step 9/10** (#11, PR #12). `install.sh` lines 559 and 621 now wrap the `grep` in `{ grep ... || true; }` so a missing key falls back to the default `127.0.0.1` instead of triggering pipefail. `.env.example` now ships with `DASHBOARD_BIND=127.0.0.1` plus a comment documenting the SSH tunnel and the `0.0.0.0` opt-in path.

### Notes

- This is a maintainer-self-reported regression. The bug ships in the v2.7.1 tarball but is not exploitable; it just blocks the installer. The fix is mechanical and changes no runtime behavior.
- v2.7.1 users who already have a working install do not need to update — nothing changes for them. v2.7.2 is only relevant for anyone running `install.sh` from scratch.

## [2.7.1] — 2026-05-19 (security patch release)

Security-focused patch release. Closes a security audit reported by [@Lucky3mc](https://github.com/Lucky3mc) using the 9-engine Debuggix scan, plus the post-launch hardening commits that landed between the v2.7 tag and this release.

### ⚠️ Breaking change for VPS installs

The dashboard host port is now bound to `127.0.0.1` by default (issue #4). v2.7 installs that accessed the dashboard at `http://VPS-IP:8080` will lose remote access after running `wasp update`. Choose one of:

1. SSH tunnel: `ssh -L 8080:127.0.0.1:8080 user@vps`, then open `http://localhost:8080` on your local machine.
2. Put a reverse proxy with TLS in front (nginx, Caddy, Traefik) and have it talk to `127.0.0.1:8080`.
3. Explicitly opt back in by setting `DASHBOARD_BIND=0.0.0.0` in `.env` (only after option 2 is in place).

### Security

- **Path traversal in media handling** (#2, PR #6). Four model providers (`anthropic_provider.py`, `google_provider.py`, `ollama_provider.py`, `openai_provider.py`) opened user-supplied image paths with `open(path, "rb")` and no validation. A crafted path like `../../etc/passwd` or `/etc/passwd` would be base64-encoded and sent to the LLM, a file-exfiltration primitive. The Whisper `audio_path` had the same bug in the same module. Fix: new helper `src/utils/path_safety.py::validate_media_path()` that realpath-resolves the input and rejects anything outside `/data/chat-uploads`, `/data/shared`, `/data/screenshots`, `/data/screenshot`.

- **SQL identifier hardening** (#3, PR #7). Three call sites built raw SQL with f-strings interpolating identifiers (`metrics.py:109` bucket expression, `reset.py:339` table name, `integrity.py:283` table + column). Not exploitable today because the values come from hard-coded constants, but a fragile pattern. Each call site now validates against a strict allowlist (`frozenset` or `^[a-zA-Z_][a-zA-Z0-9_]*$`) before interpolation, so any future refactor wiring user input through these constants will fail loudly rather than silently enable SQL injection.

- **Dashboard bound to all host interfaces by default** (#4, PR #9). `docker-compose.yml` mapped port 8080 to `0.0.0.0` and `install.sh` ran `ufw allow 8080/tcp` on hosts with UFW, exposing the dashboard publicly without TLS or fronting on a default VPS install. The original report suggested changing `config.py:48` (the in-container bind), but that would break the operator's reverse-proxy deployment; the real surface was the host port mapping. Fix: `docker-compose.yml` now maps to `${DASHBOARD_BIND:-127.0.0.1}`, `install.sh` only adds the UFW rule when `DASHBOARD_BIND=0.0.0.0` is explicitly set, and the post-install summary shows a copy-paste SSH-tunnel command for remote access.

- **docs-site dependency CVEs** (#5, PR #8). `npm audit` reported 38 vulnerabilities (8 moderate, 30 high) in the docs-site, covering lodash, fast-uri, DOMPurify, Mermaid, picomatch, path-to-regexp, follow-redirects, brace-expansion, ws, webpack-dev-server, uuid, `@babel/plugin-transform-modules-systemjs`, serialize-javascript (transitively), and several other packages. Fix: Docusaurus bumped from 3.9.2 to 3.10.1, `@docusaurus/faster` added as an explicit dependency (required by Docusaurus 3.10 when `future.v4` is enabled), and an `overrides` block pins `serialize-javascript` to `^7.0.5`. Audit is now clean (0 vulnerabilities); build succeeds; `https://docs.agentwasp.com/` serves the new build.

### Fixed (between v2.7 and v2.7.1)

- **Installer on macOS** (#1). Pre-flight checks now branch on `$PKG_FAMILY`: `sysctl hw.memsize` instead of `/proc/meminfo`, `df -g` instead of `df -BG`, `lsof` instead of `ss`, skip `usermod` on Darwin. `OS_ID` defaults to `"macos"` instead of `"unknown"`.
- **PowerShell installer logo rendering** on Windows. Replaced misaligned ASCII art with ANSI Shadow Unicode blocks matching `install.sh`. Forced UTF-8 console output so box-drawing characters render.

### Added (between v2.7 and v2.7.1)

- **Published installer SHA-256 checksums**: `install.sh.sha256` and `install.ps1.sha256` are now served from `agentwasp.com`. README documents a verify-before-pipe flow (`curl ... .sha256 | sha256sum -c -`).
- **Official contact email**: `lab@agentwasp.com` (in README, SECURITY.md, CODE_OF_CONDUCT).
- **Discord community link** on the landing page (https://discord.gg/DCxTeVtTjg).

### Removed (between v2.7 and v2.7.1)

- **Operator-only `containers/agent-nginx/`** from the public source tree. It was the production landing-page container for `agentwasp.com`, not part of the agent runtime. Public installs do not need it.

## [2.7] — 2026-05-13 (first public OSS release)

### Fixed
- **Dashboard navigation**: same-path query-string clicks were silent no-ops. `/memory?tab=...`, `/tasks?status=...`, every `?page=N`, and every filter pill across the dashboard worked exactly once. Fix in `base.html::_navigate` compares full URL (path + query), not just path.
- **Tab bars broken on re-visit**: pages with top-level `const`/`let` (cognitive, world-model, skill-evolution, vector-memory, goals, tasks) threw `SyntaxError: redeclaration of const X` the second time you visited them, aborting their init scripts. SPA loader now wraps inline scripts in an IIFE before re-injection.
- **CheckIn job spammed fresh installs**: `¿Necesitas ayuda con algo?` could be the very first message a brand-new install ever sent, before the user said anything. The job now refuses to fire when there is zero episodic memory.
- **Installer cross-distro**: three real bugs caught by a smoke run against Debian 12, Alpine 3, and AlmaLinux 9:
  - `df -BG "${INSTALL_DIR%/*}"` crashed for top-level install dirs (`/wasp`) — added fallback to `/`.
  - `hostname -I` is GNU-only; BusyBox on Alpine exits non-zero — added `ip` and `localhost` fallbacks.
  - AlmaLinux's `curl-minimal` blocked `dnf install curl` — added `--allowerasing` to the rhel/fedora path.

### Added
- **Self-improve `dry_run`**: `write` and `patch` accept `dry_run="true"`. The skill returns the unified diff plus the AST validation verdict without touching the file, creating a backup, or persisting anything. Lets the agent (and operators) preview the impact of a change before committing.
- **Gmail recipient allowlist**: `gmail send` enforces `GMAIL_RECIPIENT_ALLOWLIST` when set (per-address `alice@example.com` or per-domain `@company.com`). Defense-in-depth against prompt injection asking the agent to email arbitrary recipients.
- **Tests for Experimental cognitive subsystems**: 38 new tests covering learning feedback detection, procedural sequence checks, behavioral conflict detection, formatting helpers, dream module load. Suite total: 622 passing.
- **Public release packaging script**: `release-prep/scripts/build-release.sh` builds the public tarball from an allowlist staging copy. Refuses to package if any forbidden operator-specific identifier (private host paths, mailbox, bot handle, IPs) appears in the staged tree.

### Changed
- **Telegram welcome message**: rewritten for warmth and clarity. `/start` shows a concise capability summary with a few well-placed emojis; the long command reference moved to `/help`. Translated EN / ES / PT / FR.
- **Docker socket policy** (public default): socket is no longer mounted into `agent-core`. Only `agent-broker` retains socket access for compose orchestration. The integration-manager's auto-restart path now prints a manual `docker restart` instruction instead of silently calling the API.
- **Self-repair prompts** use `${WASP_HOST_DIR}` (set by the installer / wizard) instead of any hardcoded path. The agent learns the right rebuild directory for its install.

### Removed
- **Public `TELEGRAM_ALLOW_PUBLIC` escape hatch**: there is no longer a way to start the Telegram bridge without a numeric allowlist. Empty `TELEGRAM_ALLOWED_USERS` makes the bridge refuse to start. Wizard requires the operator's numeric Telegram id (5–15 digits) and replicates it to both `TELEGRAM_ALLOWED_USERS` and `SCHEDULER_NOTIFY_CHAT_ID`.
- **Operator-only artifacts** from the public archive: internal `containers/agent-core/docs/reports/` audit reports, the production-specific `agent-nginx` container, and the operator secret-rotation tracker are all excluded from the tarball.

## [2.7-rc] — 2026-05-12 (public-release scaffolding work)

The work in this entry is what made v2.7 publishable as an OSS project on top of the v2.6 internal codebase. Bundled into the v2.7 release; called out separately here because it touches the public surface (installer, docs, hosting) rather than the agent's behavior.

### Added
- One-line installer (`install.sh`) with cross-distro support: Debian/Ubuntu, RHEL/AlmaLinux/Rocky/CentOS, Fedora, Arch, openSUSE, Alpine, macOS.
- PowerShell installer (`install.ps1`) for Windows via WSL2.
- `wasp` CLI: `onboard`, `start`, `stop`, `restart`, `status`, `logs`, `health`, `update`, `backup`, `restore`, `reset`, `uninstall`, `help`.
- Interactive onboarding wizard with format validation for Telegram tokens and provider keys.
- Self-hosted dashboard (151 HTTP endpoints across chat, traces, tasks, scheduler, memory, knowledge graph, world model, skills, agents, goals, integrations, metrics, audit log, self-improve, cognitive health).
- Telegram bridge with 15 commands and multi-language welcome (en/es/pt/fr).
- 40 built-in skills including browser (nodriver + Selenium), email (Gmail), shell, python_exec (subprocess sandbox), http_request, fetch_url, scrape, reminders, monitors, self_improve, skill_manager, web_search.
- OpenClaw external-skill registry: install third-party skills with `/openclaw install <slug>`.
- Goal orchestrator with replan budget, stability tracking, chain-break recovery, and circuit breaker.
- 41 scheduler jobs (perception, dream, autonomous, self-integrity, CPI monitor, behavioral learner, etc.) with persistent state and catch-up logic on restart.
- Truth/honesty layer: URL substitution guard, follow-up domain lock, numeric grounding, capability claim verification, action announcer, scheduler honesty, prompt-leak redaction.
- Centralized SSRF guard (`utils/network_safety.py`) with DNS rebinding protection and manual redirect re-validation.
- Volume-aware `wasp backup` / `wasp restore` covering Postgres + named Docker volumes (redis, ollama, memory, logs, screenshots, browser sessions, uploads).
- Public docs: README, INSTALL, QUICKSTART, DEPLOYMENT, TROUBLESHOOTING, SECURITY, CONTRIBUTING.
- BSL 1.1 license with Change Date 2029-05-13 → Apache 2.0. Production use permitted under USD $1M annual revenue threshold.

### Security
- Fail-closed defaults: Telegram refuses startup if `TELEGRAM_ALLOWED_USERS` is empty. There is no public-bot mode and no escape hatch.
- Dashboard generates strong temporary credentials on first boot if no `DASHBOARD_USER`/`DASHBOARD_PASSWORD` provided; credentials printed once to stderr.
- Path-traversal containment on dashboard self-improve apply (`os.path.realpath` against `/app/src/`).
- Argon2 password hashing, CSRF tokens session-bound, login rate limit (5/5min).
- Python_exec runtime sandbox via subprocess with RLIMIT_CPU/AS/NOFILE and import-blocker for network/ctypes/subprocess modules.
- Shell skill blocklist for destructive patterns (rm -rf /, fork bombs, /dev/tcp, LD_PRELOAD, metadata IPs, etc.).
- Redaction patterns for AWS/Stripe/Slack/SendGrid/OpenAI/Anthropic/Google/HuggingFace credentials in audit logs.

### Known limits
- Some cognitive systems (procedural memory, behavioral rules, learning examples, opportunities) require accumulated usage before they show data. See `docs/STATUS_AND_LIMITS.md`.
- BSL 1.1 prohibits production use by entities with >USD $1M annual revenue from WASP-incorporating products until 2029-05-13.
- Single-operator design: there is no built-in multi-tenancy. The dashboard supports multiple admin accounts but every operator shares the same memory, scheduler, and skill surface.

### Removed
- Site-preference hardcoding (17track, coinmarketcap, named news sites). Site resolution now happens at runtime via `web_search`.
- Dead installer flags (`--dev`, `firewall_open()`, `VPS_IP` env var).
