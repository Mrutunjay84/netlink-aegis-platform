# Netlink Aegis — Deployment guide

Netlink Aegis is the white-labeled edition of CISO Assistant. All editions below build
the **Netlink-branded images** (logo, name, favicon) from the `netlink/` overlay — so no
matter which mode you choose, you get Netlink branding.

You pick a **deployment mode** by choosing which compose file you run. Each mode sets up
the application and the Caddy web server differently. You can deploy anywhere (any server
/ IP / domain) — just set the host once in an env file.

---

## 0. Quickstart (one command)

On a fresh server with Docker installed, clone the repo and run the bootstrap script.
It auto-detects the host IP, tunes the frontend build memory for small machines, writes
the env file, and brings the stack up:

```bash
git clone https://github.com/Mrutunjay84/netlink-aegis-platform
cd netlink-aegis-platform

./deploy.sh                      # Plain HTTP on this host's auto-detected IP
./deploy.sh 192.168.1.50         # Plain HTTP on a specific IP/hostname
./deploy.sh grc.example.com --https   # Self-signed HTTPS
```

Then create your first admin account (printed at the end of the script):

```bash
docker compose --env-file .env.http -f docker-compose-http.yml exec backend \
  poetry run python manage.py createsuperuser
```

Prefer to do it by hand, or need a real-certificate production setup? Use the manual
modes below.

---

## 1. Which mode should I use?

| Mode | File | Encryption | Certificates needed | Database | Use when |
|------|------|-----------|---------------------|----------|----------|
| **Plain HTTP** | `docker-compose-http.yml` | ❌ none | none | SQLite | Quick internal test on a trusted private LAN |
| **Self-signed HTTPS** | `docker-compose-https.yml` | ✅ yes (self-signed) | none | SQLite | Deploy anywhere securely without buying certs (one-time browser warning) |
| **Production HTTPS** | `docker-compose-prod.yml` | ✅ yes (real cert) | your real cert + key | PostgreSQL | Real production with a proper domain & certificate |

> **Recommendation:** prefer **Self-signed HTTPS** over Plain HTTP whenever you can — it
> needs no certificates either, but your traffic (including passwords) is encrypted.
> Use **Plain HTTP** only on a network you fully trust.

There is also `netlink/docker-compose-build.yml` — the original development stack with a
fixed IP baked in. The three files above supersede it for portable deployments.

---

## 2. One-time prerequisites (on any target machine)

- Docker + Docker Compose installed.
- This repository cloned:
  `git clone https://github.com/Mrutunjay84/netlink-aegis-platform`
- Enough RAM for the frontend build (~8 GB recommended). On a small host, set
  `NODE_BUILD_HEAP_MB` to a lower value (e.g. `6144`) in the env file.

The first launch **builds** the images from source, so it takes a while. Later launches
reuse the built images and are fast.

---

## 3. Mode A — Plain HTTP (no TLS)

> Traffic is **unencrypted**. Trusted private networks only.

```bash
cd netlink-aegis-platform
cp .env.http.example .env.http
# edit .env.http: set CISO_FQDN to this host's IP or hostname (no http://, no port)

docker compose --env-file .env.http -f docker-compose-http.yml up -d --build
```

Open: `http://<CISO_FQDN>/`

**How it works:** Caddy listens on port **80** and reverse-proxies to the app with **no
TLS**. The image is built so the login cookies' `Secure` flag is driven by an environment
variable, and this file sets `SECURE_COOKIES=false` — that's what lets login succeed over
plain HTTP (otherwise browsers drop the auth cookie).

---

## 4. Mode B — Self-signed HTTPS (encrypted, no purchased certs)

```bash
cd netlink-aegis-platform
cp .env.https.example .env.https
# edit .env.https: set CISO_FQDN to this host's IP or hostname (no https://, no port)

docker compose --env-file .env.https -f docker-compose-https.yml up -d --build
```

Open: `https://<CISO_FQDN>/` — your browser will warn "your connection is not private"
the first time. That's expected for a self-signed certificate; click **Advanced →
Proceed**. After that it works normally.

**How it works:** Caddy listens on port **443** and generates its own internal certificate
(`tls internal`). `default_sni` is set so it also works when you browse to a bare IP
address. Auth cookies stay `Secure` (the default) because the connection is HTTPS — no
cookie workaround needed.

---

## 5. Mode C — Production HTTPS (real certificate)

Requires a real domain name and a certificate + private key file on the host.

```bash
cd netlink-aegis-platform
cp .env.prod.example .env.prod
# edit .env.prod: set CISO_FQDN (domain), CERT_PATH, KEY_PATH, POSTGRES_* and DJANGO_SECRET_KEY

docker compose --env-file .env.prod -f docker-compose-prod.yml up -d --build
```

Open: `https://<your-domain>/`

**How it works:** Caddy listens on **443** and serves your **real certificate**
(`CERT_PATH` / `KEY_PATH`, mounted read-only). Data is stored in **PostgreSQL** (a
`postgres` service) rather than SQLite, and a fixed `DJANGO_SECRET_KEY` keeps logins valid
across restarts.

---

## 6. The Caddy differences at a glance

| Mode | Port | Caddy TLS line | App URL scheme |
|------|------|----------------|----------------|
| Plain HTTP | 80 | *(none)* | `http://` |
| Self-signed HTTPS | 443 | `tls internal` | `https://` |
| Production HTTPS | 443 | `tls /etc/caddy/cert.pem /etc/caddy/key.pem` | `https://` |

---

## 7. Switching a running server between modes

1. Stop the current stack (use the file it was started with):
   `docker compose -f docker-compose-http.yml down`   *(or the file you used)*
2. Start the new mode with its own file + env file (Section 3/4/5).

Notes:
- HTTP and self-signed HTTPS both use the **SQLite** `./db` folder, so data carries over
  between those two modes on the same machine.
- Production uses **PostgreSQL**, so moving to/from production is a data migration, not a
  simple switch — back up first (see the Backups guide).

---

## 8. Updating the host address (moving to a new server / IP / domain)

You don't edit the compose files — just change `CISO_FQDN` in the relevant `.env.*` file
and re-run the `up -d` command. The logo/branding always travels with the build.

---

## 9. Security notes

- **Plain HTTP** sends everything (including passwords) in clear text. Never expose it to
  the internet; use it only on a trusted LAN.
- **Self-signed HTTPS** encrypts traffic; the browser warning is only because the
  certificate isn't from a public authority — the connection itself is secure.
- **Production** should always use a real certificate and a strong, secret
  `DJANGO_SECRET_KEY` (never commit it).
- `.env.http`, `.env.https`, and `.env.prod` are gitignored. Only the `*.example` files
  are committed. Never commit real secrets.
