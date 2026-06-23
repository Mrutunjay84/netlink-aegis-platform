# Netlink Aegis — Maintenance & Operations Runbook

Practical, copy-paste guide for running, updating, restarting and backing up the
Netlink Aegis deployment (the plain-HTTP stack), and for pulling upstream updates
from intuitem (CISO Assistant). For *why* things are structured this way, see
`netlink-aegis-architecture.md`.

> **Server:** `185.255.131.241` (domain `ciso.dialex.in` points here directly).
> **Project dir:** `/home/flash/aegis-build/netlink-aegis-platform`
> **Stack file:** `docker-compose-http.yml`  ·  **Env file:** `.env.http`

---

## 0. The one command to remember

Every command below uses the same prefix. To save typing, set an alias for your
shell session:

```bash
cd /home/flash/aegis-build/netlink-aegis-platform
alias dc='docker compose --env-file .env.http -f docker-compose-http.yml'
```

Then you can use `dc ps`, `dc logs`, `dc up -d`, etc. (If you open a new
terminal, set the alias again, or just type the full command.)

Services in the stack: **caddy** (web :80) · **frontend** (UI) · **backend**
(API + SQLite) · **huey** (background worker) · **qdrant** (vector DB).

---

## 1. Everyday operations

```bash
# Status of all containers
dc ps

# Live logs (all, or one service). Ctrl+C to stop watching.
dc logs -f
dc logs -f backend
dc logs -f frontend

# Restart everything (no rebuild) — safe, ~1 min
dc restart

# Restart just one service
dc restart backend
dc restart frontend

# Stop the whole stack (keeps data)
dc down

# Start it again
dc up -d

# Quick health check
docker ps --format '{{.Names}} {{.Status}}'
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/login -H "Host: 185.255.131.241"   # expect 200
```

`dc down` stops and removes the containers but **keeps your data** (the SQLite DB
in `./db` and the `qdrant_data` volume persist). It does **not** delete anything
important. Use `dc up -d` to bring it back.

> Never run `dc down -v` unless you intend to **delete the qdrant volume**.

---

## 2. Applying YOUR OWN changes (you edited the code)

Rebuild only what changed, then recreate that service. Images are tagged
`:latest`, so `up -d` recreates the container when the image changes.

```bash
# Frontend change (UI: routes, components, theme in netlink/frontend/...)
dc build frontend
dc up -d frontend
# ~14-17 min build. Needs ~8 GB RAM/swap (see §6 if it gets OOM-killed).

# Backend change (anything in netlink/backend/netlink_policies/...)
dc build backend
dc up -d backend huey      # recreate BOTH backend and the worker
# Fast (no node build).

# Changed both
dc build backend frontend
dc up -d
```

After ANY frontend rebuild: **hard-refresh the browser** (Ctrl+Shift+R /
Cmd+Shift+R) or use an incognito window. The UI assets are content-hashed and
cached aggressively, so a normal refresh can keep showing the old version.

### Persist the change in git
```bash
git add -A
git commit -m "describe your change"
git push origin netlink-policy-builder-v2
```

---

## 3. Pulling updates FROM intuitem (upstream CISO Assistant)

All Netlink code lives under `netlink/` and is applied at build time on top of a
*vendored copy* of upstream (`frontend/`, `backend/`). That keeps upstream merges
clean. The two remotes:

```bash
git remote -v
# intuitem  https://github.com/intuitem/ciso-assistant-community.git   (upstream)
# origin    https://github.com/Mrutunjay84/netlink-aegis-platform.git  (your fork)
```
Currently synced to upstream **v3.16.3**.

### Step-by-step upstream update

```bash
cd /home/flash/aegis-build/netlink-aegis-platform

# 1. Safety: commit/stash any local work and snapshot the DB (see §4).
git status            # should be clean
git checkout netlink-policy-builder-v2

# 2. Fetch upstream and see what versions exist
git fetch intuitem --tags

# 3. Merge a specific upstream release tag (recommended over 'main').
#    Replace v3.17.0 with the version you want.
git merge v3.17.0

# 4. Resolve conflicts if any.
#    - Conflicts in frontend/ or backend/ (vendored upstream): almost always
#      "take upstream" — our features are NOT in those folders.
#        git checkout --theirs <path> && git add <path>
#    - Conflicts in netlink/ (our code): keep ours / merge by hand.
#    Then finish:  git commit

# 5. Rebuild both images and redeploy
dc build backend frontend
dc up -d

# 6. Apply DB migrations brought by the upstream release
docker exec backend poetry run python manage.py migrate

# 7. Verify, then push
docker ps --format '{{.Names}} {{.Status}}'
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/login -H "Host: 185.255.131.241"
git push origin netlink-policy-builder-v2
```

### If an upstream update breaks our overlay
The build patches are **idempotent and self-skipping**: if upstream renames a
file or class we patch, the patch becomes a no-op (it won't crash the build, the
tweak just won't apply). Check the build log for `[brand-patch] ... not found`
warnings and re-point the patch in:
- `netlink/frontend/brand-patch.mjs` (branding + theme inject + sidebar polish)
- `netlink/frontend/feature-patch.mjs` (sidebar nav + i18n for our pages)
- `netlink/frontend/deploy-patch.mjs` (HTTP cookie flag)
- `netlink/frontend/src/routes/(app)/+layout.svelte` (full shell overlay — if
  upstream heavily changes the layout, re-copy it and re-apply our markup).

> **Tip:** test an upstream merge on a throwaway branch first
> (`git checkout -b test-upstream && git merge vX.Y.Z && dc build ...`). If it's
> good, repeat on `netlink-policy-builder-v2`.

---

## 4. Backups & restore

Two things hold all state: the **SQLite DB** (`./db`) and the **qdrant** volume.

```bash
# --- Backup (do this before any update) ---
# 1. SQLite DB + uploaded files (the whole db folder). Stop writers for a clean copy:
dc stop backend huey
sudo tar czf ~/aegis-db-backup-$(date +%F-%H%M).tar.gz -C /home/flash/aegis-build/netlink-aegis-platform db
dc start backend huey

# 2. qdrant vector store
docker run --rm -v netlink-aegis-platform_qdrant_data:/data -v ~:/backup alpine \
  tar czf /backup/aegis-qdrant-backup-$(date +%F-%H%M).tar.gz -C /data .
```

```bash
# --- Restore the SQLite DB ---
dc down
sudo rm -rf db && sudo tar xzf ~/aegis-db-backup-YYYY-MM-DD-HHMM.tar.gz -C /home/flash/aegis-build/netlink-aegis-platform
# DB must be writable by the container user:
docker run --rm -v "$(pwd)/db:/db" alpine sh -c "chown -R 1001:1001 /db"
dc up -d
```

Keep backups off-server (download the `.tar.gz` files). Automate with a cron job
if you want daily snapshots.

---

## 5. Admin tasks

```bash
# Create / reset a superuser (admin) account
docker exec -e DJANGO_SUPERUSER_EMAIL=you@example.com \
  -e DJANGO_SUPERUSER_PASSWORD='change-me' backend \
  poetry run python manage.py createsuperuser --noinput

# Open a Django shell
docker exec -it backend poetry run python manage.py shell

# Run migrations manually (normally only needed after upstream updates)
docker exec backend poetry run python manage.py migrate
```

AI provider API keys are **not** in any file — they're set in the UI
(**Policy Builder → AI providers**, admin only) and stored in the database. They
survive restarts and updates; back them up via the DB backup above.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| UI looks unchanged after a rebuild | browser cached old assets | hard refresh (Ctrl/Cmd+Shift+R) or incognito; verify with `curl` from §1 |
| `DisallowedHost` in backend logs | accessing via a host not allowed | add it to `ALLOWED_HOSTS`/`CISO_FQDN` in the compose/env, `dc up -d backend huey` |
| Login silently fails over HTTP | `Secure` cookies dropped on plain HTTP | already handled (`SECURE_COOKIES=false`); use a fresh login / incognito |
| Logout doesn't sign you out | Secure cookie not cleared over HTTP | fixed in `deploy-patch.mjs` (env-driven secure on cookie deletes incl. `+server.ts`); rebuild frontend |
| Frontend build killed (exit 137) | out of memory | lower `NODE_BUILD_HEAP_MB` in `.env.http`, or add swap (below), or stop idle apps during build |
| AI returns nothing / 502 | provider quota/outage | retry, switch model/provider, or add another key in **AI providers** |
| `sqlite ... unable to open database file` | `./db` not writable by container user | `docker run --rm -v "$(pwd)/db:/db" alpine sh -c "chown -R 1001:1001 /db"` |
| Container keeps restarting | check its logs | `dc logs --tail 100 <service>` |

```bash
# Temporarily grow swap (helps the frontend build on low-RAM hosts)
sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
# (remove later with: sudo swapoff /swapfile && sudo rm /swapfile)
```

---

## 7. Deploy fresh on a brand-new server

```bash
git clone -b netlink-policy-builder-v2 https://github.com/Mrutunjay84/netlink-aegis-platform.git
cd netlink-aegis-platform
cp .env.http .env.http.local        # edit CISO_FQDN to the new host's IP/domain
docker compose --env-file .env.http -f docker-compose-http.yml up -d --build
# create the first admin (see §5), then open http://<CISO_FQDN>/
```

For HTTPS on a real domain, front the stack with TLS (Caddy auto-TLS or a
TLS-terminating proxy) and set `CISO_FQDN` to the domain. See the architecture
doc, §6.

---

## 8. Golden rules

1. **Back up the `db` folder before every update** (§4).
2. **Only edit code under `netlink/`** — never the vendored `frontend/` /
   `backend/` trees (your changes there would be lost on upstream merges).
3. **Rebuild the right service** after a change, then **hard-refresh** the browser.
4. **Commit and push** to `netlink-policy-builder-v2` so the repo always reflects
   what's deployed.
5. **Test upstream merges on a scratch branch** before applying to the deploy branch.
```
