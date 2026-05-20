---
id: installation
title: Installation
description: Install WASP on any Linux host (or macOS / Windows via WSL2) in one command.
---

# Installation

WASP installs in one command on any Docker-capable Linux box. Default install path is `/opt/wasp`. Total time from clean OS to running agent: **~10 minutes** (most of it is the Docker build).

## One-line install

```bash
sudo bash -c "$(curl -fsSL https://agentwasp.com/install.sh)"
```

That command:

1. Detects your distro (Debian / Ubuntu / RHEL / AlmaLinux / Rocky / Fedora / Arch / openSUSE / Alpine / macOS).
2. Installs Docker + compose plugin if missing.
3. Downloads the WASP release tarball (clean 2.1 MB allowlist-built archive).
4. Generates secure secrets (`POSTGRES_PASSWORD`, `DASHBOARD_SECRET`, `MEDIA_SIGNING_SECRET`) with `openssl rand`.
5. Launches the onboarding wizard (timezone, Telegram, provider keys, dashboard credentials).
6. Builds the container images.
7. Starts the stack.
8. Runs the health probe.

Windows: see [Windows installer](#windows-via-wsl2) below.

## Prerequisites

| Requirement | Notes |
|---|---|
| OS | Debian 11+, Ubuntu 22.04+, RHEL/AlmaLinux/Rocky 9+, Fedora 38+, Arch, openSUSE Tumbleweed, Alpine 3.18+, macOS 13+. Windows via WSL2 + Docker Desktop. |
| CPU / RAM / Disk | **Minimum**: 2 cores, 4 GB RAM, 10 GB disk. **Recommended**: 4 cores, 8 GB RAM, 20 GB disk. |
| Internet egress | Outbound HTTPS for LLM provider APIs, Telegram (if used), and any integrations you enable. |
| Optional: Telegram bot | Created via [@BotFather](https://t.me/BotFather). You need the bot token AND your own numeric Telegram user ID. |
| Required: an LLM | At least one of: Anthropic, OpenAI, xAI, Google. Or run Ollama locally (slower with small models). |

The installer aborts early if your host is below the hard floors (≥2 GB RAM, ≥5 GB disk).

## What the installer does

```
[1/10]  Pre-flight checks (OS, RAM, disk, port 8080/5432/6379 collisions)
[2/10]  Install system packages (curl, git, ca-certificates, jq, openssl, tzdata, rsync, tar)
[3/10]  Install Docker (skipped if already present and compose plugin works)
[4/10]  Prepare install dir   ($WASP_INSTALL_DIR, default /opt/wasp)
[5/10]  Download source        (tarball / git / local; tarball is default)
[6/10]  Symlink wasp CLI       (/usr/local/bin/wasp)
[7/10]  Generate .env          (auto-secrets via openssl rand)
[8/10]  Onboarding wizard      (TTY only; --yes / WASP_NON_INTERACTIVE=true skips)
[9/10]  docker compose build --pull
[10/10] docker compose up -d   (skipped with --no-start)
        Health probe
```

## Installer flags

```bash
# Default — tarball method, full stack
sudo bash -c "$(curl -fsSL https://agentwasp.com/install.sh)"

# Custom install dir (default /opt/wasp)
curl -fsSL https://agentwasp.com/install.sh -o install.sh && sudo bash install.sh --install-dir /home/me/wasp

# Use git clone instead of the tarball
curl -fsSL https://agentwasp.com/install.sh -o install.sh && sudo bash install.sh --install-method git

# Stop after Docker is installed (do not run any WASP step)
curl -fsSL https://agentwasp.com/install.sh -o install.sh && sudo bash install.sh --docker-only

# Install but do not start services
curl -fsSL https://agentwasp.com/install.sh -o install.sh && sudo bash install.sh --no-start

# Fully non-interactive (no onboarding wizard; use existing .env or defaults)
curl -fsSL https://agentwasp.com/install.sh -o install.sh && sudo bash install.sh --yes
```

| Flag | Default | Effect |
|---|---|---|
| `--install-method tarball\|git\|local` | `auto` (→ `tarball`) | How to fetch source. `local` requires `--local-source <DIR>`. |
| `--install-dir <DIR>` | `/opt/wasp` | Where to install. |
| `--branch <NAME>` | `main` | Git branch (when method is `git`). |
| `--docker-only` | off | Install Docker, then exit. |
| `--no-start` | off | Lay down files and `.env` but do not run `docker compose up`. |
| `--yes` / `-y` / `--non-interactive` | off | Skip prompts. |

Environment overrides: `WASP_INSTALL_DIR`, `WASP_TARBALL_URL`, `WASP_REPO_URL`, `WASP_BRANCH`, `WASP_LOCAL_SOURCE`, `WASP_NON_INTERACTIVE`.

## Onboarding wizard

The wizard asks for, in order:

| Question | What to enter |
|---|---|
| Timezone | An IANA timezone — `America/Santiago`, `Europe/Berlin`, etc. Default `UTC`. |
| Telegram bot token | From [@BotFather](https://t.me/BotFather). Leave blank to disable Telegram entirely. |
| Your numeric Telegram user ID | **Required if you set a bot token.** 5–15 digits (get yours from [@userinfobot](https://t.me/userinfobot)). Replicated to both `TELEGRAM_ALLOWED_USERS` and `SCHEDULER_NOTIFY_CHAT_ID`. There is no public-bot mode. |
| Default LLM provider | `anthropic`, `openai`, `xai`, `google`, or `local` (for Ollama). |
| Provider API key | Your key for the provider above. |
| Dashboard username | Default: `admin`. |
| Dashboard password | Stored in `.env`. Pick something strong (≥ 12 chars). |
| Public dashboard URL | Optional — if you're behind a reverse proxy with TLS. |

Re-run any time with `wasp onboard`.

## Verify it's running

```bash
wasp status    # all containers should be healthy
wasp health    # runs the full health probe suite
wasp logs      # tail agent-core logs
```

Then open the dashboard. It binds to `127.0.0.1:8080` by default, so from the VPS itself use `http://localhost:8080`. From another machine, the simplest option is an SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 user@your-vps
```

Then browse to `http://localhost:8080` on your local machine. See [Dashboard Access](/getting-started/dashboard-access) for reverse-proxy and other options. Default credentials are the ones you just set.

## Windows (via WSL2)

```powershell
# In PowerShell as Administrator
iwr -useb https://agentwasp.com/install.ps1 | iex
```

This auto-installs WSL2 if missing and runs the Linux installer inside a Debian distro. Docker Desktop is required.

## Local LLM (Ollama) — fully self-hosted

If you'd rather not use a commercial provider:

```bash
# Ollama ships with the stack but downloads no models by default.
# Pull a model from the dashboard "/models" page, or:
docker exec agent-ollama ollama pull qwen2.5:7b
```

Notes:
- 7B-class local models work but feel slow with the full ~40 KB system prompt. See [Status & Limits](/known-limitations).
- Vision and code-heavy tasks benefit from a commercial provider.

## Updating

```bash
wasp update
```

Pulls the latest tarball, rebuilds, restarts, runs the health probe. Safe to re-run anytime; data volumes are preserved.

## Uninstalling

```bash
wasp uninstall
```

Asks twice:
1. Remove data volumes? — deletes Postgres, Redis, memory, screenshots, browser sessions.
2. Remove the install directory? — deletes `/opt/wasp` itself.

Saying "no" to both leaves your data and install in place; only the running containers stop and the `wasp` symlink is removed.

## Next steps

- [Docker Setup](/getting-started/docker-setup) — services, volumes, network
- [Environment Variables](/getting-started/environment-variables) — full configuration reference
- [First Launch](/getting-started/first-launch) — verification and first message
- [Operator Commands](/operations/commands) — the `wasp` CLI
