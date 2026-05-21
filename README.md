<div align="center">

<img src=".github/assets/logo.png" alt="WASP" width="420" />

**A serious agent. Built to evolve.**

Self-hosted autonomous AI agent. Plans, executes, and improves itself running on infrastructure you own.

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-F5C542?style=flat-square)](LICENSE.md)
[![Version](https://img.shields.io/badge/version-2.7.2-F5C542?style=flat-square)](CHANGELOG.md)
[![Docs](https://img.shields.io/badge/docs-agentwasp.com-F5C542?style=flat-square)](https://docs.agentwasp.com)
[![Install](https://img.shields.io/badge/install-1%20line-F5C542?style=flat-square)](#install)
[![Python](https://img.shields.io/badge/python-3.12-F5C542?style=flat-square)](https://www.python.org)
[![Docker](https://img.shields.io/badge/docker-required-F5C542?style=flat-square)](https://docs.docker.com)

[**Website**](https://agentwasp.com) · [**Docs**](https://docs.agentwasp.com) · [**Quick Start**](#install) · [**Architecture**](#architecture) · [**License**](LICENSE.md)

</div>

---

WASP is not a chat-UI wrapper. There is real architecture underneath: an event bus, a goal orchestrator, a 41-job scheduler, layered memory, a truth/policy layer that grounds responses against actual actions, and a self-repair loop that can rewrite its own code.

<div align="center">

https://github.com/user-attachments/assets/0a14bd31-871a-4747-a48e-5d35ed6f8619

<sub><em>Inside the WASP brain — all running together.</em></sub>

</div>

## Install

```bash
sudo bash -c "$(curl -fsSL https://agentwasp.com/install.sh)"
```

That single line:

1. Detects your distro (8 Linux flavors + macOS supported)
2. Installs Docker + compose plugin if missing
3. Pulls the source tarball (clean, 2.1 MB, allowlist-built)
4. Generates secure secrets with `openssl rand`
5. Walks you through onboarding (Telegram, provider keys, dashboard credentials)
6. Builds the containers and starts the stack

Default install path: `/opt/wasp`. The dashboard binds to `127.0.0.1:8080` (loopback only) for safety — to reach it from another machine, use an SSH tunnel or put a TLS reverse proxy in front. See [Dashboard Access](https://docs.agentwasp.com/getting-started/dashboard-access) for the three supported options.

### Verify the installer (optional, recommended)

Prefer to inspect the script before piping it into `bash`? Verify the SHA-256 against the published checksum:

```bash
curl -fsSL https://agentwasp.com/install.sh -o install.sh
curl -fsSL https://agentwasp.com/install.sh.sha256 | sha256sum -c -
# install.sh: OK
sudo bash install.sh
```

The Windows installer has the same option: `https://agentwasp.com/install.ps1.sha256`.

### Post-install

```bash
wasp status      # see what's running
wasp logs        # tail logs
wasp health      # run health probes
```

## What WASP does

- **Conversational agent** with memory that persists across sessions: episodic, semantic, working, procedural, behavioral rules, knowledge graph, temporal world model.
- **37 built-in skills**: web search, browser automation (nodriver + Selenium), email (Gmail with allowlist), scraping, scheduling, file ops, Python execution (sandboxed), reminders, RSS subscriptions, monitoring, self-improvement, and more.
- **Goal orchestrator**: long-running plans broken into TaskGraph steps, retried on failure, replanned when blocked, validated by a Plan Critic before execution.
- **Dashboard**: browser UI with 151 endpoints — chat, traces, tasks, scheduler, memory, knowledge graph, world model, agents, integrations, audit log, self-improve.
- **Telegram bridge**: optional — natural language to your agent from your phone. Multi-language welcome (EN/ES/PT/FR).
- **Self-improvement loop**: corrections you write become persistent behavioral rules. Recurring action patterns get abstracted into reusable procedures. The agent can read, patch, and rebuild its own source.
- **Truth layer**: response binding, URL substitution guard, scheduler honesty, capability-claim verification, prompt-leak redaction — designed to make the agent's text match the actions it actually took.

## What WASP is not

- Not a hosted SaaS. You run it yourself on a server or workstation.
- Not a coding agent like Claude Code or Cursor — it is a general-purpose agent.
- Not multi-tenant. One operator per install.
- Not magic. The underlying LLM is probabilistic; the policy and truth layers reduce — but don't eliminate — hallucinations.

## Requirements

- Linux x86_64 (Ubuntu 22.04+ / Debian 12+ recommended) — or macOS / Windows via WSL2.
- 4 GB RAM minimum, 8 GB recommended.
- 10 GB free disk.
- At least one LLM provider key (Anthropic / OpenAI / xAI / Google) — or Ollama for fully self-hosted (slower with small models; see [STATUS_AND_LIMITS.md](docs/STATUS_AND_LIMITS.md)).

## Installer flags

```bash
# Default — tarball method, full stack
sudo bash -c "$(curl -fsSL https://agentwasp.com/install.sh)"

# Use git clone instead of the tarball (for contributors)
curl -fsSL https://agentwasp.com/install.sh -o install.sh && sudo bash install.sh --install-method git

# Stop after Docker is installed (don't start WASP)
curl -fsSL https://agentwasp.com/install.sh -o install.sh && sudo bash install.sh --docker-only

# Install but don't start services (manual control)
curl -fsSL https://agentwasp.com/install.sh -o install.sh && sudo bash install.sh --no-start

# Fully non-interactive (no onboarding wizard)
curl -fsSL https://agentwasp.com/install.sh -o install.sh && sudo bash install.sh --yes
```

## CLI

```
wasp onboard         Re-run the configuration wizard
wasp start           Start the stack
wasp stop            Stop the stack
wasp restart         Restart all services
wasp status          Container status + health checks
wasp logs [service]  Stream logs (default: agent-core)
wasp health          Run the full health probe suite
wasp update          Pull latest tarball, rebuild, restart, verify
wasp backup          Create a timestamped backup archive (Postgres + volumes)
wasp restore <file>  Restore from a backup archive
wasp reset           Wipe runtime state but keep volumes
wasp uninstall       Remove WASP (asks before deleting data)
wasp help            Show command reference
```

## Architecture

```
┌────────────┐                    ┌─────────────────┐
│  Telegram  │ ─── Redis Streams ─┤                 │
└────────────┘                    │   agent-core    │
                                  │  · 41 schedulers│
┌────────────┐                    │  · 37 skills    │
│ Dashboard  │ ─── HTTP/SSE ──────┤  · goal engine  │
│  (browser) │                    │  · truth layer  │
└────────────┘                    │                 │
                                  └────────┬────────┘
                                           │
                              ┌────────────┴────────────┐
                              │                         │
                       ┌──────▼──────┐          ┌──────▼──────┐
                       │  Postgres   │          │    Redis    │
                       │  28 tables  │          │  cache + KV │
                       └─────────────┘          └─────────────┘
```

See [docs.agentwasp.com](https://docs.agentwasp.com) for the full architecture reference.

## Docs

- [docs/INSTALL.md](docs/INSTALL.md) — full install reference, env vars, distro notes
- [docs/QUICKSTART.md](docs/QUICKSTART.md) — first 10 minutes
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — VPS + local + reverse-proxy guidance
- [docs/SECURITY.md](docs/SECURITY.md) — threat model, fail-closed defaults, secret handling
- [docs/STATUS_AND_LIMITS.md](docs/STATUS_AND_LIMITS.md) — **honest** map of what works and what's experimental
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — common errors with fixes
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — dev setup, release process, BSL implications
- [CHANGELOG.md](CHANGELOG.md) — version history (v2.7 is the first public release; pre-OSS history at [docs.agentwasp.com/changelog](https://docs.agentwasp.com/changelog))

## Status

WASP v2.7 is the first public OSS release. The core systems (event bus, goal orchestrator, skills, scheduler, memory, truth layer, dashboard) are stable and have been running in production. Some cognitive subsystems (procedural memory, behavioral rules, learning examples) accumulate value with usage and may be empty on a fresh install — see [STATUS_AND_LIMITS.md](docs/STATUS_AND_LIMITS.md) for the full maturity map.

## License

WASP is released under the [Business Source License 1.1](LICENSE.md). Plain English: you can self-host, evaluate, modify, and use it freely — including in production and even offering services to third parties — **as long as your aggregate annual revenue from products incorporating WASP stays below USD $1,000,000**. Above that threshold, a commercial license is required. The license auto-converts to Apache 2.0 on **2029-05-13** (3 years from launch).

This is a one-paragraph summary, not legal advice — read the full license before using WASP commercially.

## Support

- Bug reports & feature requests: GitHub issues (use the templates).
- Security: see [docs/SECURITY.md](docs/SECURITY.md) for responsible disclosure.
- Other inquiries: **lab@agentwasp.com**

---

<div align="center">

WASP is a young public project (v2.7 is the first release outside the original operator's environment). Expect rough edges. Pull requests welcome — see [CONTRIBUTING.md](docs/CONTRIBUTING.md).

<br/>

**[agentwasp.com](https://agentwasp.com)** · Built to evolve.

</div>
