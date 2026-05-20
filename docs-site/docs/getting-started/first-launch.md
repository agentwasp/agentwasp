---
id: first-launch
title: First Launch
description: Verifying the installation and sending the first message.
---

# First Launch

After `docker compose up -d` completes, verify the deployment and send your first message.

## Verify services

```bash
wasp status
```

Or, equivalently:

```bash
docker compose ps
```

Every service should show as `healthy` or `up`. If any service is `restarting` or `unhealthy`, check its logs:

```bash
wasp logs <service>          # or: docker compose logs <service> --tail=80
```

## Verify the health endpoint

```bash
curl -s http://localhost:8080/health | jq
```

You should get a JSON response with `status: "ok"` and component statuses.

## Verify the bot

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" | jq
```

`.ok` should be `true` and the `username` should match your bot.

## Sign in to the dashboard

The dashboard binds to `127.0.0.1:8080` by default (loopback only). From the host itself, open `http://localhost:8080`. From another machine, you have three options — SSH tunnel, TLS reverse proxy, or `DASHBOARD_BIND=0.0.0.0` for short-lived LAN testing. See [Dashboard Access](/getting-started/dashboard-access) for the full guide.

Sign in with `DASHBOARD_USER` / `DASHBOARD_PASSWORD`.

If you didn't set those in onboarding, a temporary password was printed to stderr on first boot. Tail the agent-core logs to find it:

```bash
wasp logs | grep -i 'dashboard.*credentials'
```

The first page is the **Overview** dashboard. The sidebar groups pages into five sections:

- **Dashboard** — Overview, Chat, Command palette
- **Configurations** — Identity, Config Center, Skills, Models, Integrations
- **System** — Scheduler, Agents, Goals, Subscriptions, Health
- **Governance** — Self-Improve, Behavioral Rules, Audit, Reset
- **Observability** — Traces, Live, Metrics, Cognitive, Memory, Knowledge Graph, World Model, Vector Memory

## Send the first message

Open Telegram, find your bot by username, and send any message — for example:

> What's the time?

The first message after a fresh start triggers the **boot sequence**:

1. Telegram connectivity check.
2. Active model liveness ping (8 s timeout, `max_tokens=1`). Reports "live ✓" or "unreachable ✗".
3. Knowledge graph readiness.
4. Browser session capability.
5. Memory subsystem.

The boot message includes a cognitive-state warning when the system is post-reset, telling you that all knowledge has been cleared and rebuild will take a few sessions.

After the boot message, the agent processes your actual question and replies normally.

## Verify a trace

After the first response, open the dashboard at `/traces`. Find your message; you should see:

- `request_id`
- `path` = `telegram`
- `request_tier` = `simple` / `normal` / `complex`
- `detected_language`
- `allowed_skills` (which skills the LLM tried to call)
- `blocked_skills` (which the policy layer dropped, with reason)
- `guard_actions` (which guards fired)
- `latency_ms`

The trace tells the full story of why the response is what it is. If you ever see surprising behavior, this is the first place to look.

## Verify the audit log

Send a controlled-skill request — for example:

> Set a reminder to back up the disk in 30 minutes.

Then open `/audit` in the dashboard. You should see a row for `skill.reminders` with the redacted input/output.

## Set a default model

If you have multiple model providers configured, open `/models` and choose a default. The model router (`models/router.py`) classifies each request (vision / code / quick / complex / default) and suggests a model when none is pinned.

## Lock down access

Before considering the deployment "live":

- Verify `TELEGRAM_ALLOWED_USERS` is restricted to your user IDs only.
- Verify TLS certificates are valid (if using HTTPS).
- Configure an external uptime check against `/health`.
- Set up daily backups (see [Deployment](/operations/scaling#backups)).

## Troubleshooting

If the bot doesn't respond, the first message produces an error, or the dashboard returns 500: see [Troubleshooting → Common Errors](/troubleshooting/common-errors).

## Next steps

- [Operator Guide](/operations/commands) — daily usage
- [Telegram](/integrations/telegram) — input types, commands, progress
- [Dashboard](/integrations/dashboard) — page-by-page reference
- [Safety and Policy](/security/skill-safety) — policy layer
- [Scheduler](/core-concepts/scheduler) — recurring tasks
