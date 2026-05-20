---
id: api
title: API
description: Dashboard HTTP endpoints, authentication, and the integration registry.
---

# API

The dashboard exposes a small HTTP API for programmatic access. Authentication is via session cookie (same as the UI) — there is no separate API token system out of the box.

## Authentication

```bash
# Sign in (returns Set-Cookie: session=...)
curl -c cookies.txt -X POST https://your-host/auth/login \
  -d "username=admin&password=$DASHBOARD_PASSWORD"

# Use the cookie for subsequent calls
curl -b cookies.txt https://your-host/health
```

Sessions expire after the configured timeout (default 7 days). CSRF tokens are required for POST/PUT/DELETE on most endpoints — fetch the token from the relevant page first or include the cookie's `csrftoken` value.

## Health

```bash
curl https://your-host/health
```

Returns JSON:

```json
{
  "status": "ok",
  "version": "2.7.2",
  "components": {
    "model": {"status": "ok", "provider": "anthropic", "name": "claude-sonnet-4-6"},
    "redis": {"status": "ok"},
    "postgres": {"status": "ok"},
    "browser": {"status": "ok", "active_sessions": 0},
    "queues": {
      "events_incoming": 0,
      "events_outgoing": 0,
      "behavioral_pending": 3
    },
    "cpi": 12,
    "cpi_high": false
  }
}
```

Use this for external uptime monitoring.

## Chat

```bash
# Synchronous
curl -b cookies.txt -X POST https://your-host/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "what is the current BTC price?", "chat_id": "dashboard-1"}'

# Streaming (SSE)
curl -b cookies.txt -N -X POST https://your-host/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"text": "summarize today\'s news", "chat_id": "dashboard-1"}'
```

The streaming endpoint returns Server-Sent Events with `progress`, `chunk`, and `done` event types.

## Goals

```bash
# List goals
curl -b cookies.txt https://your-host/api/goals

# Create a goal
curl -b cookies.txt -X POST https://your-host/api/goals \
  -H "Content-Type: application/json" \
  -d '{"objective": "Daily news summary", "priority": 5}'

# Pause a goal
curl -b cookies.txt -X POST https://your-host/api/goals/{goal_id}/pause

# Archive a goal
curl -b cookies.txt -X POST https://your-host/api/goals/{goal_id}/archive
```

## Agents

```bash
# List agents
curl -b cookies.txt https://your-host/api/agents

# Create an agent
curl -b cookies.txt -X POST https://your-host/api/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "research_agent",
    "objective": "Daily: check top AI news and summarize to memory",
    "priority": 5
  }'
```

## Self-Improve

```bash
# List proposals
curl -b cookies.txt https://your-host/api/self-improve/proposals

# Apply a proposal
curl -b cookies.txt -X POST https://your-host/api/self-improve/{proposal_id}/apply

# Reject a proposal
curl -b cookies.txt -X POST https://your-host/api/self-improve/{proposal_id}/reject
```

The Apply endpoint returns:

```json
{
  "ok": true,
  "applied_path": "/app/src/skills/builtin/your_skill.py",
  "backup_path": "/data/src_patches/backup_20260430T150000_your_skill.py"
}
```

If syntax validation fails:

```json
{
  "ok": false,
  "error": "Syntax error — patch rejected: invalid syntax (line 42)"
}
```

## AuditLog

```bash
# Recent audit entries
curl -b cookies.txt "https://your-host/api/audit?since=24h&limit=100"
```

Keyset pagination via `?cursor=<timestamp>|<id>`. See the dashboard `/audit` page for the full filter UI.

## Decision Traces

```bash
# Recent traces
curl -b cookies.txt "https://your-host/api/traces?chat_id=...&limit=50"

# Specific trace
curl -b cookies.txt https://your-host/api/traces/{request_id}
```

## Integrations

The IntegrationRegistry exposes a uniform interface for 40+ connectors:

```bash
curl -b cookies.txt -X POST https://your-host/api/integrations/{integration_id}/execute \
  -H "Content-Type: application/json" \
  -d '{"action": "send_message", "params": {"channel": "general", "text": "hi"}}'
```

The registry enforces:

- Existence check
- Action allowlist per connector
- PolicyEngine gate (risk_level)
- Secret injection from `SecretVault`
- CircuitBreaker (CLOSED / OPEN / HALF_OPEN)
- Metrics recording

Circuit breaker state persists in Redis (`cb:state:{integration_id}`) across restarts.

## Rate limiting

Endpoints are subject to the Resource Governor caps. See [Resource Governor](/core-concepts/resource-governor).

## Notes

- This API is designed for **operator use** — programmatic access by the operator's own scripts. It is NOT designed for third-party apps; there is no OAuth or API-token system.
- For public-facing API access, deploy a thin proxy in front of the dashboard with your own auth layer.

## See also

- [Dashboard](/integrations/dashboard) — UI reference
- [Telegram](/integrations/telegram) — alternative interface
- [Configuration](/operations/configuration)
