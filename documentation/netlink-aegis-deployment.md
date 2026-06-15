# Netlink Aegis — Deployment Guide

End-to-end guide to deploy Netlink Aegis (the white-labeled CISO Assistant fork)
on a fresh server. For day-2 operations (restart, backup, upstream updates) see
`netlink-aegis-maintenance.md`; for *how* the build overlay works see
`netlink-aegis-architecture.md`.

There are two supported topologies:

- **HTTP (IP or internal)** — fastest path, plain `:80`. Recommended for staging,
  internal networks, or an IP-only host. This is the current production setup.
- **HTTPS (public domain)** — same images, fronted by TLS. See §6.

---

## 1. Prerequisites

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | Linux x86-64 (Ubuntu 22.04+/Debian 12+) | same |
| CPU / RAM | 2 vCPU / 4 GB | 4 vCPU / 8 GB |
| Disk | 20 GB free | 40 GB+ (DB + vectors + images) |
| Swap | required if RAM < 8 GB | 8 GB (frontend build is memory-heavy) |
| Software | Docker Engine 24+ and the Docker Compose plugin (`docker compose`) | latest |
| Network | inbound TCP **80** open (and **443** for HTTPS) | + outbound HTTPS for AI providers |

Verify Docker:
```bash
docker --version && docker compose version
docker run --rm hello-world      # should succeed
```

> **Build memory:** the frontend (SvelteKit) build needs ~8 GB of RAM+swap. On a
> 4 GB host, add swap **before** building:
> ```bash
> sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile
> sudo mkswap /swapfile && sudo swapon /swapfile
> echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab   # persist
> ```

---

## 2. What gets deployed

Five containers (defined in `docker-compose-http.yml`):

| Service | Image | Role | Port |
|---|---|---|---|
| `caddy` | `caddy:2.11.2` | web entrypoint / reverse proxy | **80** (host) |
| `frontend` | `netlink-aegis-frontend:latest` | SvelteKit UI (branded) | 3000 (internal) |
| `backend` | `netlink-aegis-backend:latest` | Django REST API + SQLite | 8000 (internal) |
| `huey` | `netlink-aegis-backend:latest` | background worker | internal |
| `qdrant` | `qdrant/qdrant:v1.14.0` | vector DB (AI features) | internal |

State lives in two places: the **SQLite DB + uploads** in `./db`, and the
**`qdrant_data`** Docker volume. Everything else is rebuildable.

---

## 3. Deploy over HTTP (recommended fast path)

```bash
# 1. Get the code (deploy branch)
git clone -b netlink-policy-builder-v2 \
  https://github.com/Mrutunjay84/netlink-aegis-platform.git
cd netlink-aegis-platform

# 2. Configure the host (see §4 for the full env reference)
cp .env.http .env.http.local       # optional: keep a per-host copy
#   edit CISO_FQDN to this server's public IP or domain, e.g. 185.255.131.241

# 3. Build the branded images and start everything
docker compose --env-file .env.http -f docker-compose-http.yml up -d --build
#   First build pulls base images and compiles the UI: ~15-20 min.

# 4. Watch it come up
docker compose --env-file .env.http -f docker-compose-http.yml ps
#   Wait until 'backend' is (healthy) and all are Up.
```

Create the first admin and log in — see §5.

> Tip: alias the long command for the session —
> `alias dc='docker compose --env-file .env.http -f docker-compose-http.yml'`
> then `dc up -d`, `dc ps`, `dc logs -f`, etc.

---

## 4. Environment reference (`.env.http`)

The key knobs (edit before first `up`):

| Variable | Purpose | Typical value |
|---|---|---|
| `CISO_FQDN` | host the app is reached at (IP or domain). Feeds `ALLOWED_HOSTS` + the API base URL | `185.255.131.241` or `ciso.example.com` |
| `SECURE_COOKIES` | must be **false** on plain HTTP, **true** behind HTTPS | `false` (HTTP) |
| `NODE_BUILD_HEAP_MB` | Node heap cap for the frontend build (lower on tiny hosts) | `8192` |
| `POSTGRES_*` / `DATABASE_URL` | only if you switch off SQLite (optional) | unset = SQLite |
| `EMAIL_*` | outbound SMTP for notifications/invites (optional) | unset = console |

After editing env, recreate the affected services:
```bash
dc up -d backend huey      # backend-side env
dc build frontend && dc up -d frontend   # CISO_FQDN affects the built API URL
```

> AI provider API keys are **not** in env files — set them in the UI under
> **Policy Builder → AI providers** (admin only). They're stored in the DB and
> survive restarts/updates.

---

## 5. First admin & login

```bash
docker exec \
  -e DJANGO_SUPERUSER_EMAIL=admin@example.com \
  -e DJANGO_SUPERUSER_PASSWORD='choose-a-strong-password' \
  backend poetry run python manage.py createsuperuser --noinput
```

Then open `http://<CISO_FQDN>/` and sign in. (Over HTTP, if login seems to do
nothing, use an incognito window — `SECURE_COOKIES=false` already handles the
plain-HTTP cookie case.)

---

## 6. Deploy over HTTPS (public domain)

The same images run HTTPS — it's environment + TLS termination, nothing rebuilt.

1. Point an **A record** for your domain at the server's public IP.
2. In the env file set `CISO_FQDN=your.domain.com` and `SECURE_COOKIES=true`.
3. Terminate TLS one of two ways:
   - **Caddy auto-TLS (simplest):** use the HTTPS compose/Caddyfile so Caddy
     fetches a Let's Encrypt cert automatically for `CISO_FQDN`. Open **443**.
   - **External proxy:** terminate TLS at an upstream LB / nginx and forward to
     Caddy/frontend.
4. Rebuild the frontend (the API base URL is baked from `CISO_FQDN`) and bring up:
   ```bash
   dc build frontend && dc up -d
   ```

A worked HTTPS-on-a-VM example (with Caddyfile specifics) lives in
`deployment-vm-https-ip.md`.

---

## 7. Verify the deployment

```bash
# Containers
docker ps --format '{{.Names}} {{.Status}}'      # backend should be (healthy)

# Web entrypoint (expect 200 after redirect to /login)
curl -sL -o /dev/null -w 'home %{http_code}\n'  http://<CISO_FQDN>/
curl -s  -o /dev/null -w 'login %{http_code}\n' http://<CISO_FQDN>/login   # 200
curl -s  -o /dev/null -w 'api %{http_code}\n'   http://<CISO_FQDN>/api/build/ # 401 = up, auth required

# Backend logs
docker logs backend --since 10m 2>&1 | tail -50
```

All green → log in and confirm the branded UI, Policy Builder, and AI providers
screen load.

---

## 8. Updates, rollback & security

- **Apply your own code changes / pull upstream / back up & restore:** see
  `netlink-aegis-maintenance.md`.
- **Rollback:** images are tagged `:latest`. To roll back, `git checkout` the
  previous commit, `dc build`, `dc up -d`; restore `./db` from a backup if a
  migration changed the schema (always back up `./db` before updating).
- **Dependency/security posture:** vulnerabilities are tracked via Dependabot and
  `pnpm audit` / `pip-audit`. See `netlink-aegis-architecture.md` §10 for the
  current remediation status, the deferred build-only `esbuild` advisory, and the
  re-audit commands.

---

## 9. Quick checklist

- [ ] Docker + Compose installed, `hello-world` runs
- [ ] Swap added if RAM < 8 GB
- [ ] Inbound 80 (and 443 for HTTPS) open
- [ ] `CISO_FQDN` set; `SECURE_COOKIES` correct for HTTP/HTTPS
- [ ] `up -d --build` completed, `backend` is (healthy)
- [ ] First admin created, login works
- [ ] `/login` returns 200; `/api/build/` returns 401
- [ ] AI provider key added in the UI (if using AI features)
- [ ] `./db` backup scheduled
