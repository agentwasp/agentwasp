---
id: dashboard-access
title: Dashboard Access
description: Three supported ways to reach the WASP dashboard from another machine.
---

# Dashboard Access

Since v2.7.1 the WASP dashboard binds to `127.0.0.1:8080` by default. This means the dashboard is reachable **only from the host itself** — `http://VPS-IP:8080` from your laptop will not work out of the box, and that is intentional.

The dashboard sits in front of every cognitive subsystem of the agent (skill executor, goal engine, self-improve patches, secret vault). A dashboard exposed to the public internet without TLS leaks the session cookie on the first request, and a leaked cookie is full operator access. The default is loopback-only because the safe path is to put a TLS layer in front, and the safe path should be the default.

This page covers the three supported access patterns.

## Option 1 — SSH tunnel (recommended for personal use)

The simplest option. No DNS, no certs, no firewall changes. Open an SSH session that forwards the dashboard port to your local machine:

```bash
ssh -L 8080:127.0.0.1:8080 user@your-vps
```

While that session is open, browse to `http://localhost:8080` on your laptop and sign in with `DASHBOARD_USER` / `DASHBOARD_PASSWORD` from `.env`.

When you close the SSH session the tunnel closes too. This is the right pattern if you're the only operator and you don't need always-on access.

Add `-N` to the SSH command if you only want the tunnel and not an interactive shell, and `-f` to background it:

```bash
ssh -fN -L 8080:127.0.0.1:8080 user@your-vps
```

To tear down the backgrounded tunnel later: `pkill -f 'ssh -fN -L 8080'`.

## Option 2 — TLS reverse proxy (recommended for permanent access)

If you want the dashboard reachable from anywhere without an SSH tunnel — for example because you check it from your phone, or because someone else on your team needs access — put a TLS reverse proxy in front of it.

Caddy is the shortest path because it provisions Let's Encrypt certificates automatically. Install Caddy on the VPS, point a subdomain (e.g. `wasp.your-domain.com`) at the VPS IP, and create a `Caddyfile`:

```caddy
wasp.your-domain.com {
    reverse_proxy 127.0.0.1:8080
}
```

Then:

```bash
sudo systemctl reload caddy
```

Caddy fetches the certificate, terminates TLS on port 443, and forwards plaintext traffic to the dashboard on `127.0.0.1:8080`. Leave `DASHBOARD_BIND=127.0.0.1` in `.env`. The dashboard is not directly exposed; only Caddy is.

The equivalent nginx configuration:

```nginx
server {
    listen 443 ssl;
    server_name wasp.your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/wasp.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wasp.your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Set `DASHBOARD_PUBLIC_URL=https://wasp.your-domain.com` in `.env` so the dashboard generates correct redirect and media URLs.

## Option 3 — Expose publicly without TLS (testing only)

For local-network testing — for example, you want to open the dashboard from your laptop on the same LAN as the VPS, and you have not yet set up a reverse proxy — you can bind the dashboard to all interfaces:

```bash
# in /opt/wasp/.env
DASHBOARD_BIND=0.0.0.0
```

Then restart the agent-core container:

```bash
cd /opt/wasp && docker compose up -d agent-core
```

The dashboard is now reachable at `http://VPS-IP:8080`.

**Warning.** The session cookie and your dashboard password are sent in plaintext on every request. Anyone on the same network — or anywhere on the public internet if the VPS firewall allows port 8080 — can capture them. Use this option only on a trusted LAN, only briefly, and revert to `127.0.0.1` plus a reverse proxy before you finish for the day.

If the host has UFW, the installer does **not** open port 8080 for you. You would need to do that manually with `sudo ufw allow 8080/tcp`, which is a second deliberate step. That second step is also the moment to reconsider whether you really want plaintext exposure.

## Which option should you use?

| Use case | Option |
|---|---|
| Solo operator, occasional access | **Option 1** (SSH tunnel) |
| Always-on access from multiple devices | **Option 2** (Caddy / nginx with TLS) |
| Quick check from same-LAN laptop, no DNS available | **Option 3** (`DASHBOARD_BIND=0.0.0.0`, briefly) |
| Production deployment | **Option 2** — never Option 3 |

## See also

- [Environment Variables](/getting-started/environment-variables) — full reference for `DASHBOARD_BIND`, `DASHBOARD_PORT`, `DASHBOARD_PUBLIC_URL`.
- [First Launch](/getting-started/first-launch) — what to do after the installer finishes.
- [Configuration](/operations/configuration) — runtime config via the dashboard `/config` page.
