# CISO Assistant — VM Deployment Runbook (HTTPS on a bare IP)

> Step-by-step record of how we deployed CISO Assistant on a VM that is reachable
> **only by IP address** (`192.168.186.128`) with **no public DNS name and no real TLS
> certificate**. Includes every important change, every problem we hit, and how we
> fixed it. Safe to import into Notion or Docmost (Import -> Markdown).

- **Target VM IP:** `192.168.186.128`
- **Public URL:** `https://192.168.186.128:8443`
- **Edition:** Community
- **Runtime:** Docker Compose (prebuilt images from GHCR)
- **Database:** SQLite (default), stored in `./db` on the host
- **TLS:** Caddy self-signed (`tls internal`) — browser shows a "not secure" warning, which we accept on purpose

---

## 1. Why this approach (decision log)

We needed to deploy a working baseline **before making any code changes**, so we could
test changes against it later.

The VM is **IP-only with no TLS**. We considered two options:

| Option | What it means | Verdict |
|--------|---------------|---------|
| **A. Keep HTTPS with a self-signed cert bound to the IP** | Caddy's `tls internal` mints a self-signed cert for the IP. Browser warns once; you click through. | Chosen — no code changes, secure cookies keep working |
| B. Plain HTTP (no TLS at all) | Serve over `http://`. | Rejected — the frontend hardcodes `secure: true` on session cookies, so browsers refuse to store them over HTTP and **login breaks**. Would require editing app code + rebuilding images. |

**Key insight:** the frontend sets auth cookies (`token`, `allauth_session_token`) with
`secure: true` in several files (`login/+page.server.ts`, `hooks.server.ts`,
`sso/authenticate/+page.server.ts`, `(app)/+layout.server.ts`). `Secure` cookies are
only stored over HTTPS. So **staying on HTTPS (even self-signed) is the low-effort,
no-code-change path.**

---

## 2. Prerequisites

- Docker Engine >= 27 with the Compose plugin. (We had Docker 29.5.2 + Compose v5.1.4.)
- The host user is in the `docker` group (so `docker` runs without sudo).
- Inbound TCP **8443** open in the VM firewall / cloud security group (only needed if
  accessing from a different machine than the VM).

Check:

```bash
docker --version
docker compose version
id        # confirm your user is in the 'docker' group
```

---

## 3. Configuration changes we made

All changes are in `docker-compose.yml`. Two distinct edits:

### 3.1 Point all URLs/hosts at the VM IP (5 lines across 4 services)

```yaml
# backend service
- ALLOWED_HOSTS=backend,localhost,192.168.186.128
- CISO_ASSISTANT_URL=https://192.168.186.128:8443

# huey service
- CISO_ASSISTANT_URL=https://192.168.186.128:8443

# frontend service
- PUBLIC_BACKEND_API_URL=http://backend:8000/api                    # unchanged (internal container-to-container)
- PUBLIC_BACKEND_API_EXPOSED_URL=https://192.168.186.128:8443/api   # changed (browser-facing)

# caddy service
- CISO_ASSISTANT_URL=https://192.168.186.128:8443
```

> `PUBLIC_BACKEND_API_URL` stays as the internal Docker hostname `http://backend:8000/api`.
> Only `PUBLIC_BACKEND_API_EXPOSED_URL` (what the browser talks to) becomes the IP URL.

### 3.2 Add Caddy `default_sni` so TLS works over an IP

**Before** (default — only works for `localhost`):

```yaml
    command: |
      sh -c 'echo $$CISO_ASSISTANT_URL "{
      reverse_proxy /api/* backend:8000
      reverse_proxy /* frontend:3000
      tls internal
      }" > Caddyfile && caddy run'
```

**After** (adds a global options block with `default_sni`):

```yaml
    command: |
      sh -c 'echo "{
      default_sni 192.168.186.128
      }" > Caddyfile && echo $$CISO_ASSISTANT_URL "{
      reverse_proxy /api/* backend:8000
      reverse_proxy /* frontend:3000
      tls internal
      }" >> Caddyfile && caddy run'
```

This produces the following `Caddyfile` inside the container:

```caddyfile
{
default_sni 192.168.186.128
}
https://192.168.186.128:8443 {
reverse_proxy /api/* backend:8000
reverse_proxy /* frontend:3000
tls internal
}
```

(Why this is needed is explained in Problem #3 below.)

---

## 4. Deployment — step by step

### Step 1 — Fix the `./db` folder ownership

The container runs as user `1001:1001` and must own `./db`. On our VM the folder
existed but was owned by `root`, and passwordless `sudo` was **not** available.
We used a throwaway Docker container (Docker runs as root) to set ownership:

```bash
cd /home/flash/projects/netlink-aegis-platform
docker run --rm -v "$PWD/db:/db" busybox sh -c "chown -R 1001:1001 /db"
stat -c '%u:%g' db    # should print: 1001:1001
```

> If `sudo` *is* available on your machine, the simpler equivalent is:
> `sudo chown -R 1001:1001 db`

### Step 2 — Pull the images

```bash
docker compose pull
```

> The backend image is large (~3.3 GB, bundles PyTorch) and the frontend ~1.1 GB.
> See Problem #2 if the pull appears to "hang".

### Step 3 — Bring up the stack

Because `pull_policy: always` can re-trigger a registry check, and our images were
already local, we started with `--pull never`:

```bash
docker compose up -d --pull never
```

`up -d` blocks until the **backend** passes its health check (first boot runs DB
migrations + loads framework libraries; `start_period` is 150s). Only then do
`frontend`, `caddy`, and `huey` start (they `depend_on: service_healthy`).

> **Note on the init script:** the repo ships `./docker-compose.sh` for first-time setup,
> but it **refuses to run if `./db` already exists** and it creates the superuser
> *interactively*. Since `./db` existed and we needed a non-interactive flow, we used
> `docker compose up -d` directly instead.

### Step 4 — Create the superuser (non-interactive)

```bash
docker compose exec -T \
  -e DJANGO_SUPERUSER_EMAIL="study.mrutunjay@gmail.com" \
  -e DJANGO_SUPERUSER_PASSWORD="<YOUR_PASSWORD>" \
  backend poetry run python manage.py createsuperuser --noinput
```

Expected output: `Superuser created successfully.`

- **Admin email:** `study.mrutunjay@gmail.com`
- **Password:** store in your password manager — do **not** commit it to the repo or paste it into shared docs.

### Step 5 — Verify

```bash
# containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# API + frontend through Caddy (-k ignores the self-signed cert)
curl -sk -o /dev/null -w "health: HTTP %{http_code}\n" https://192.168.186.128:8443/api/health/
curl -sk -o /dev/null -w "front:  HTTP %{http_code}\n" https://192.168.186.128:8443/
curl -sk https://192.168.186.128:8443/api/health/
```

**Expected results:**

| Check | Result | Meaning |
|-------|--------|---------|
| `backend` status | `Up (healthy)` | OK |
| `/api/health/` | `HTTP 200` -> `{"status":"ok"}` | API reachable |
| `/api/build/` | `HTTP 401` | OK (endpoint needs auth) |
| `/` (frontend) | `HTTP 302` | OK (redirects to `/login`) |

### Step 6 — Log in from a browser

1. Open **https://192.168.186.128:8443**
2. Accept the self-signed cert warning (**Advanced -> Proceed**).
3. Log in with the superuser email + password.

---

## 5. Problems we faced and how we fixed them

### Problem #1 — `./db` owned by root, and no passwordless sudo
- **Symptom:** `sudo chown` failed with `a terminal is required to read the password`; container (uid 1001) couldn't write to a root-owned `./db`.
- **Root cause:** leftover root-owned folder; no interactive sudo in the automation shell.
- **Fix:** used Docker itself (root inside the container) to chown the bind-mounted folder:
  ```bash
  docker run --rm -v "$PWD/db:/db" busybox sh -c "chown -R 1001:1001 /db"
  ```

### Problem #2 — Image pull looked "stuck" for ~1 hour
- **Symptom:** `docker compose pull` byte counters froze at the same values for ~58 minutes (e.g. `166.7MB`), looking like an extremely slow download.
- **Root cause:** a **transient stall** on a GHCR layer/manifest re-check. The actual image *data* had already fully downloaded — `docker images` showed `backend` at 3.31 GB and `frontend` at 1.14 GB (complete images have an ID + full size; partial pulls don't).
- **Fix:** killed the hung pull, confirmed images were present and that registry connectivity was fine (`curl https://ghcr.io/v2/` -> fast `HTTP 401`), then started with local images:
  ```bash
  pkill -f "docker compose.*pull"
  docker images | grep -E "ciso|caddy|qdrant"
  docker compose up -d --pull never
  ```
- **Lesson:** if a pull's numbers don't change for many minutes, it's stalled (not slow). Kill + retry; completed layers are cached.

### Problem #3 — TLS handshake failed over the IP (`tlsv1 alert internal error`)
- **Symptom:** `curl https://192.168.186.128:8443/...` returned `HTTP 000`, exit code 35; verbose showed:
  `TLSv1.3 (IN), TLS alert, internal error (592)` / `error:0A000438:SSL routines::tlsv1 alert internal error`.
- **Root cause:** **SNI.** Clients (browsers, curl) **don't send an SNI server name when connecting to an IP literal**. Caddy couldn't match the SNI-less connection to its `192.168.186.128` site/certificate, so it aborted the handshake. (This is exactly the SNI caveat the project README warns about.)
- **Fix:** added Caddy's **`default_sni`** global option so Caddy serves the IP's certificate when no SNI is presented (see section 3.2). After recreating Caddy:
  ```bash
  docker compose up -d --pull never caddy
  ```
  Result: `/api/health/` -> `HTTP 200`, frontend -> `HTTP 302`.

### Problem #4 (avoided) — secure cookies over plain HTTP
- **Why we never used plain HTTP:** the frontend hardcodes `secure: true` on session cookies, so over HTTP the browser silently drops them and login loops back to `/login`. Avoided by keeping HTTPS (self-signed). See the decision log in section 1.

---

## 5b. Production deployment (FQDN + custom certs + PostgreSQL)

The IP/self-signed setup above is the **dev/test baseline**. Production uses a real
domain name and your own certificate files, so the dev-only TLS workarounds are dropped.

### Why the dev TLS hacks disappear in production

The `default_sni` / `tls internal` workaround exists **only** because we connect by raw
IP. A client does not send an SNI server name when connecting to an IP literal, so Caddy
cannot match the connection to a certificate. With a real **FQDN**, the browser always
sends SNI, the proxy matches its site, and serves your certificate normally — so in prod
we use `tls /etc/caddy/cert.pem /etc/caddy/key.pem` with **no `default_sni` and no
`tls internal`**.

### Dev vs production at a glance

| Aspect | Dev (`docker-compose.yml`) | Production (`docker-compose-prod.yml`) |
|--------|----------------------------|-----------------------------------------|
| Address | `https://192.168.186.128:8443` (IP) | `https://<FQDN>` (port 443) |
| Database | SQLite (`./db`) | PostgreSQL (`postgres` service, `./db/pg`) |
| TLS | `tls internal` + `default_sni` (self-signed) | `tls /etc/caddy/cert.pem /etc/caddy/key.pem` (your certs) |
| `DJANGO_DEBUG` | `True` | `False` |
| Secret key | auto-generated in `./db` | fixed via `DJANGO_SECRET_KEY` |
| WebAuthn/passkey MFA | not available (self-signed) | works (real HTTPS) |

### Files involved

- `docker-compose-prod.yml` — the production stack (Postgres + FQDN + custom-cert Caddy).
- `.env.prod.example` — template of required values; copy to `.env.prod` (gitignored) and fill in.

All values come from `.env.prod` via `${VAR}` interpolation:

```
CISO_FQDN=grc.example.com
CERT_PATH=/etc/ssl/ciso/fullchain.pem   # host path to full chain cert
KEY_PATH=/etc/ssl/ciso/privkey.pem      # host path to private key
POSTGRES_NAME=ciso-assistant
POSTGRES_USER=ciso
POSTGRES_PASSWORD=<strong-password>
DJANGO_SECRET_KEY=<long-random-string>  # python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Certificate placement

Put your corporate/CA-issued cert and key on the production host (e.g. under
`/etc/ssl/ciso/`) and point `CERT_PATH` / `KEY_PATH` at them. They are mounted read-only
into the Caddy container as `/etc/caddy/cert.pem` and `/etc/caddy/key.pem`. `CERT_PATH`
should be the **full chain** (leaf certificate + any intermediates).

### Production bring-up

```bash
cd /home/flash/projects/netlink-aegis-platform

# 1. Prepare secrets/values
cp .env.prod.example .env.prod
$EDITOR .env.prod                       # set FQDN, cert paths, Postgres creds, secret key

# 2. db/attachments folder ownership (host user 1001:1001)
docker run --rm -v "$PWD/db:/db" busybox sh -c "chown -R 1001:1001 /db"

# 3. Bring up the production stack
docker compose --env-file .env.prod -f docker-compose-prod.yml up -d

# 4. Create the superuser (non-interactive)
docker compose --env-file .env.prod -f docker-compose-prod.yml exec -T \
  -e DJANGO_SUPERUSER_EMAIL="admin@yourcompany.com" \
  -e DJANGO_SUPERUSER_PASSWORD="<password>" \
  backend poetry run python manage.py createsuperuser --noinput

# 5. Verify (no -k needed: real cert)
curl -s https://<FQDN>/api/health/    # -> {"status":"ok"}
```

> Open inbound TCP **443** on the production host/firewall. Port 80 is only needed if you
> later add an HTTP->HTTPS redirect.

### Production day-to-day commands

Always pass both `--env-file` and `-f` for prod:

```bash
docker compose --env-file .env.prod -f docker-compose-prod.yml up -d        # start
docker compose --env-file .env.prod -f docker-compose-prod.yml down         # stop
docker compose --env-file .env.prod -f docker-compose-prod.yml ps           # status
docker compose --env-file .env.prod -f docker-compose-prod.yml logs -f backend
```

---

## 6. Day-to-day operations

```bash
cd /home/flash/projects/netlink-aegis-platform

docker compose up -d            # start the stack
docker compose down             # stop the stack (data persists in ./db)
docker compose ps               # status
docker compose logs -f backend  # tail backend logs
docker compose restart caddy    # restart a single service
```

### Reset to a clean database
```bash
docker compose down
docker run --rm -v "$PWD/db:/db" busybox sh -c "rm -rf /db/*"   # wipes DB + attachments
docker compose up -d --pull never
# then recreate the superuser (Step 4)
```

### Apply code changes later (switch to building from source)
The prebuilt images run the *published* version, not local source. When we start editing
code, rebuild instead:
```bash
docker compose down
./docker-compose-build.sh        # builds backend + frontend from ./backend and ./frontend
```

---

## 7. Notes, caveats & gotchas

- **Self-signed cert:** browsers will warn every fresh session/profile. Click through, or
  import Caddy's root CA into the client's trust store to silence it.
- **WebAuthn / passkey MFA will NOT work** on a self-signed-cert origin. Password login and
  **TOTP** MFA work fine.
- **Firewall:** to reach the VM from another machine, open inbound TCP **8443**
  (e.g. `sudo ufw allow 8443/tcp`, or the cloud security group).
- **Qdrant** (port 6333) is only used when `ENABLE_CHAT=true`; it's harmless otherwise.
- **If you later get a real domain name (FQDN):** switch the three `CISO_ASSISTANT_URL`
  values + `PUBLIC_BACKEND_API_EXPOSED_URL` to `https://<fqdn>:8443`, add the FQDN to
  `ALLOWED_HOSTS`, and you can drop `default_sni` and use real Let's Encrypt TLS. An FQDN
  removes the SNI problem entirely.
- **Secrets:** never commit the superuser password or `DJANGO_SECRET_KEY` to the repo.
  The secret key is auto-generated into `db/django_secret_key` on first boot.

---

## 8. Quick reference — the whole thing in one block

```bash
cd /home/flash/projects/netlink-aegis-platform

# 1. db ownership
docker run --rm -v "$PWD/db:/db" busybox sh -c "chown -R 1001:1001 /db"

# 2. (docker-compose.yml already edited: IP URLs + Caddy default_sni)

# 3. bring up
docker compose up -d --pull never

# 4. superuser
docker compose exec -T \
  -e DJANGO_SUPERUSER_EMAIL="study.mrutunjay@gmail.com" \
  -e DJANGO_SUPERUSER_PASSWORD="<YOUR_PASSWORD>" \
  backend poetry run python manage.py createsuperuser --noinput

# 5. verify
curl -sk https://192.168.186.128:8443/api/health/    # -> {"status":"ok"}

# 6. open https://192.168.186.128:8443 and log in
```
