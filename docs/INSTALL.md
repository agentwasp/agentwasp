# Install reference

Full reference for `install.sh` flags, environment overrides, and the `.env` file.

## One-line install

```bash
curl -fsSL https://agentwasp.com/install.sh | bash
```

Default behavior:
- Install dir: `/opt/wasp`
- Method: `tarball` (downloads the latest release tarball from `agentwasp.com`)
- Branch: `main` (only used when method is `git`)
- Onboarding: interactive (prompts in your terminal)

Source-fetch methods:
- **`tarball`** (default) — downloads the published release tarball. No git required on the host.
- **`git`** — `git clone` the repo. Useful for development / tracking `main`.
- **`local`** — copy from an existing checkout: `--install-method=local --local-source $PWD`.

## Flags

| Flag | Default | Effect |
|---|---|---|
| `--install-method tarball\|git\|local` | `auto` (→ `tarball`) | How to fetch source. `local` requires `--local-source <DIR>`. |
| `--local-source <DIR>` | (none) | Copy source from this directory instead of cloning. Implies `--install-method=local`. |
| `--install-dir <DIR>` | `/opt/wasp` | Where to install. |
| `--branch <NAME>` | `main` | Git branch (when method is `git`). |
| `--docker-only` | off | Install Docker, then exit. |
| `--no-start` | off | Lay down files and `.env` but do not run `docker compose build` / `up`. |
| `--yes`, `-y`, `--non-interactive` | off | Skip prompts. Use only after onboarding once. |

Pass flags through curl-pipe with `--`:

```bash
curl -fsSL https://agentwasp.com/install.sh | bash -s -- --install-dir /home/me/wasp --install-method=git
```

## Environment overrides

| Variable | Effect |
|---|---|
| `WASP_INSTALL_DIR` | Same as `--install-dir`. |
| `WASP_INSTALL_URL` | Override the canonical install URL (used in messages). |
| `WASP_REPO_URL` | Override the git source. Useful for forks. |
| `WASP_BRANCH` | Same as `--branch`. |
| `WASP_LOCAL_SOURCE` | Same as `--local-source`. |
| `WASP_NON_INTERACTIVE` | `true` skips prompts. |

## What the installer does

1. **Pre-flight**: checks OS family + version, RAM (≥2 GB hard floor), disk (≥5 GB hard floor), port collisions on 8080/5432/6379.
2. **System packages**: `curl git ca-certificates jq openssl tzdata rsync tar`. (On AlmaLinux/Rocky, `dnf` runs with `--allowerasing` to swap `curl-minimal` for `curl`.)
3. **Docker**: official Docker repo, `docker-ce` + `docker-compose-plugin`.
4. **Source**: downloads the release tarball (default), or `git clone`, or `rsync` from `--local-source` — depending on `--install-method`.
5. **CLI**: symlinks `bin/wasp` → `/usr/local/bin/wasp`.
6. **`.env`**: copied from `.env.example`, with `POSTGRES_PASSWORD`, `DASHBOARD_SECRET`, and `MEDIA_SIGNING_SECRET` filled with `openssl rand -hex` values.
7. **Onboard**: launches `wasp onboard --first-run` if no `.wasp-onboarded` marker exists and stdin is a TTY. The wizard asks for: timezone, Telegram bot token (skippable), required Telegram user ID, provider keys, dashboard credentials.
8. **Build**: `docker compose build --pull`.
9. **Start**: `docker compose up -d` (unless `--no-start`).
10. **Health**: runs `wasp health --quiet`. Reports failures but does NOT undo the install.

## Idempotency

Re-running `install.sh` is safe:

- Existing `.env` is **kept** (secrets preserved).
- Existing volumes are **kept** (data preserved).
- Existing `.wasp-onboarded` marker means onboarding is **skipped**.
- Source is updated via `git pull --ff-only` (no rebase, no force).
- Containers are rebuilt and recreated only if their image changed.

To wipe and start fresh: `wasp uninstall` (will ask before removing data).

## Environment variables (`.env`)

See `.env.example` for the canonical, commented list. Highlights:

| Variable | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | Postgres password (auto-generated). Don't change unless you reset the DB. |
| `DASHBOARD_SECRET` | HMAC signing key for dashboard sessions (auto-generated). |
| `MEDIA_SIGNING_SECRET` | HMAC signing key for media URLs (auto-generated). |
| `DASHBOARD_USER` / `DASHBOARD_PASSWORD` | Login for the dashboard. If unset on first boot, a temporary password is generated and printed to stderr. |
| `TIMEZONE` | IANA timezone, e.g. `America/Santiago`. Default `UTC`. |
| `TELEGRAM_BOT_TOKEN` | From @BotFather. Empty = bot disabled (the bridge exits cleanly). |
| `TELEGRAM_ALLOWED_USERS` | **Required if** `TELEGRAM_BOT_TOKEN` is set. Comma-separated numeric Telegram user IDs. Empty + token set = bridge **refuses to start** (fail-closed; no public-bot mode). |
| `SCHEDULER_NOTIFY_CHAT_ID` | Chat ID where the scheduler sends proactive notifications. The wizard replicates `TELEGRAM_ALLOWED_USERS` here so notifications reach the operator. |
| `GMAIL_RECIPIENT_ALLOWLIST` | Comma-separated emails (`alice@example.com`) or domains (`@company.com`). When set, the `gmail send` skill refuses to email anyone not on the list. Empty = no restriction. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `XAI_API_KEY` / `GOOGLE_API_KEY` | At least one required (or use Ollama for fully self-hosted). |
| `DEFAULT_PROVIDER` | `anthropic` (default) / `openai` / `xai` / `google` / `ollama`. |
| `MEMORY_BACKEND` | `internal`, `supermemory`, or `tandem` (default in this branch). See `docs/SUPERMEMORY.md`. |
| `SUPERMEMORY_API_KEY` / `SUPERMEMORY_BASE_URL` | Optional hosted/local Supermemory backend credentials. Use `http://localhost:6767` for self-hosted local Supermemory. |
| `SUPERMEMORY_CONTEXT_BUDGET_CHARS` / `SUPERMEMORY_TIMEOUT_SECONDS` | Bounds Supermemory context injection and latency so tandem mode does not bloat prompts. |
| `LOG_LEVEL` | `INFO` (default), `DEBUG`, `WARNING`. |
| `SOVEREIGN_MODE` | `true` (default) — full skill round budget + operator prime block. |
| `WASP_HOST_DIR` | Path on the host where WASP is installed. Used by the agent's self-repair prompts so they reference the correct rebuild directory. The installer / wizard sets this automatically. |

After editing `.env`, apply changes with `wasp restart`.

## Uninstall

```bash
wasp uninstall
```

Asks twice before destructive actions:
1. Remove data volumes? (y/N) — this deletes Postgres + Redis + memory + screenshots.
2. Remove the install directory? (y/N) — this deletes `/opt/wasp` itself.

Saying No twice leaves everything in place; only the containers are stopped and the `wasp` symlink is removed.
