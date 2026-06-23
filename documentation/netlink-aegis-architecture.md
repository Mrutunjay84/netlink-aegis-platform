# Netlink Aegis — Architecture & Code-Change Guide

Netlink Aegis is a **white-labeled, feature-extended fork of
[CISO Assistant Community](https://github.com/intuitem/ciso-assistant-community)**.
It keeps the full upstream GRC product and layers Netlink branding plus extra
AI features **on top at build time**, so the upstream source is never edited and
upstream merges stay clean.

This document explains how the project is structured, how the build overlay
works, what we added, and exactly how to change/extend and redeploy it.

---

## 1. High-level model

```
intuitem/ciso-assistant-community   (upstream, vendored under frontend/ + backend/)
                │
                ▼
        netlink/ overlay            (our branding, theme, features, deploy config)
                │   applied at Docker build (copy-on-top + patch scripts)
                ▼
   netlink-aegis-frontend:latest  +  netlink-aegis-backend:latest   (built images)
                │
                ▼
        docker-compose-http.yml     (Caddy + frontend + backend + huey + qdrant)
```

Two guiding rules:

1. **Never edit the vendored upstream tree** (`frontend/`, `backend/`) for our
   changes. Everything Netlink lives under `netlink/` and is applied during the
   build, either by **copy-on-top** (overlay files win) or by **idempotent patch
   scripts** that rewrite the build copy only.
2. **The same image runs HTTP or HTTPS** — environment-driven, not baked.

---

## 2. Repository layout

```
.
├── frontend/                     # vendored upstream SvelteKit app (do not edit for our features)
├── backend/                      # vendored upstream Django app (do not edit for our features)
├── netlink/
│   ├── backend/
│   │   ├── Dockerfile            # builds branded backend image
│   │   ├── netlink_core/settings.py   # overlay settings; registers our DRF routes
│   │   └── netlink_policies/     # our Django overlay app (all backend features)
│   │       ├── providers.py      # multi-provider LLM registry + retry/backoff
│   │       ├── drafting.py       # Policy Builder AI drafting
│   │       ├── views.py          # Policy Builder API (config/draft/save/settings/export/doc-template)
│   │       ├── audit_guidance.py # Audit Evidence AI prompt + call
│   │       ├── audit_views.py    # Audit Evidence API (config/guidance)
│   │       └── doc_template.py   # (dormant) export letterhead/watermark helpers
│   └── frontend/
│       ├── Dockerfile            # builds branded frontend image (overlay + patches)
│       ├── Makefile              # local-dev overlay/build helpers
│       ├── brand-patch.mjs       # white-label i18n/literals + inject theme
│       ├── deploy-patch.mjs      # env-driven Secure flag on cookie set+delete (HTTP/HTTPS); scans +server.ts too
│       ├── feature-patch.mjs     # add sidebar nav entries + i18n keys for our pages
│       └── src/
│           ├── netlink-theme.css # minimalistic UI theme overlay (fonts/tokens)
│           ├── lib/components/PolicyBuilder/RichTextEditor.svelte
│           └── routes/(app)/(internal)/
│               ├── policy-builder/        # Policy Builder page + server + proxies
│               └── audit-evidence/        # Audit Evidence page + server + proxies
├── docker-compose-http.yml       # plain-HTTP production stack
├── .env.http                     # deployment vars (CISO_FQDN, build heap)
└── documentation/                # this folder
```

---

## 3. The build overlay (how branding & features get in)

### Frontend (`netlink/frontend/Dockerfile`)

1. Copy upstream `frontend/` into `/app`.
2. **Copy `netlink/frontend/` on top** → overlay files (our routes, components,
   `netlink-theme.css`, Dockerfile, patch scripts) win over upstream.
3. Run patch scripts against the build copy (never the committed tree):
   - `brand-patch.mjs` — replaces "CISO Assistant" → "Netlink Aegis" across all
     `messages/*.json` and a few hardcoded literals; sets the favicon; and
     **injects `@import './netlink-theme.css';` into `app.css`** so our theme
     loads after the upstream theme and wins.
   - `deploy-patch.mjs` — rewrites cookie writes so the **`Secure` flag is driven
     by `SECURE_COOKIES`** (lets login work over plain HTTP). Also injects the same
     env-driven `secure` flag into `cookies.delete(...)` calls so **logout** clears
     cookies over HTTP. Scans all of `src`, including `+server.ts`/`+server.js`
     route endpoints (e.g. the logout endpoint), not just `*.server.ts`.
   - `feature-patch.mjs` — inserts the **Policy Builder** and **Audit Evidence**
     sidebar nav items and their i18n keys.
4. `pnpm install --frozen-lockfile`, then `pnpm add` our extra deps (TipTap
   editor + `@fontsource-variable/inter`) **after** the frozen install so the
   committed community lockfile stays untouched (merge-safe).
5. `pnpm run build` → adapter-node output served by `node server`.

`NODE_BUILD_HEAP_MB` (build arg, default 8192) caps V8 heap so the build fits in
RAM on small hosts (avoids OOM exit 137).

### Backend (`netlink/backend/Dockerfile`)

Builds the upstream Django app and adds the overlay app `netlink_policies` plus
the overlay `netlink_core/settings.py`, which:

- adds `netlink_policies` to `INSTALLED_APPS`,
- registers our API routes on the community DRF router via `ROUTES`:
  - `netlink-policy-builder` → `netlink_policies.views.PolicyBuilderViewSet`
  - `netlink-audit-evidence` → `netlink_policies.audit_views.AuditEvidenceViewSet`
- raises `DATA_UPLOAD_MAX_MEMORY_SIZE` (for large editor/template payloads).

The overlay app has **no migrations**; all config is stored in the existing
`GlobalSettings(name="general")` row, so no DB schema changes are needed.

---

## 4. Features we added

### 4.1 AI Policy Builder  (`/policy-builder`)
- Generate a tailored governance policy from industry + framework + topic using
  any configured LLM; edit in a **Word-like WYSIWYG editor** (TipTap: headings,
  fonts, sizes, colors, highlight, alignment, lists, tables, images/logos,
  links); **export to DOCX/PDF**; **save to the policy register**.
- Backend: `views.py` (config/draft/save/settings/export), `drafting.py`.
- See `netlink-aegis-ai-policy-builder.md`.

### 4.2 Audit Evidence Assistant  (`/audit-evidence`)
- Paste a **technology scope** (kept in the browser), pick an audit or framework,
  load its controls, and get **per-control AI guidance**: what evidence to
  collect and exactly where to capture it — referencing only the relevant
  technology/service names, **never** revealing the scope.
- Backend: `audit_views.py`, `audit_guidance.py`.
- See `netlink-aegis-audit-evidence.md`.

### 4.3 Multi-provider AI layer  (`providers.py`)
- One OpenAI-compatible client serves **9 providers**: Google Gemini, OpenAI,
  Anthropic (Claude), OpenRouter (gateway to many models), Mistral, Groq,
  DeepSeek, xAI (Grok), Perplexity.
- API keys/base URLs are stored (admin-only) in `GlobalSettings` under
  `netlink_ai_*` fields; users pick **provider + model** (presets or custom) in
  the UI. Only providers with a key appear in the picker.
- `generate_with_retry()` adds exponential backoff on transient 429/5xx and
  raises a **classified `LLMError`** (`rate_limited` / `overloaded` / `auth` /
  `generation_failed`) so the UI shows an actionable message.

### 4.4 Minimalistic UI theme  (`netlink-theme.css`)
- Self-hosted **Inter** font and a full, cohesive **color palette** plus refined
  shape tokens — themes the **whole app** (sidebar, top bar, buttons, cards,
  inputs, badges, tables, charts, our pages) purely through Skeleton design
  tokens, so there are **no per-component overrides** and it stays merge-safe.
- Palette (overrides the upstream ramps after `ciso-theme.css`, via
  `html[data-theme='cisotheme']` so it always wins):
  - `primary` = **Blue** (deliberately distinct from upstream's violet),
    `secondary` = **Teal**, `tertiary` = **Violet**
  - `success` = **Emerald**, `warning` = **Amber**, `error` = **Rose**
  - `surface` = refined **Slate** (cool, clean neutrals)
- Typography/shape: Inter variable, heading weight 650, slight negative
  letter-spacing, antialiasing, softer radii (`--radius-base` 0.55rem /
  `--radius-container` 0.85rem), and a thin brand-tinted scrollbar.
- To re-skin: edit the token values in `netlink/frontend/src/netlink-theme.css`
  and rebuild the frontend. (Contrast/text-on-color tokens auto-follow because
  ciso-theme maps them to each color's 50/950 shade, which we set.)

**App shell redesign (layout/placement):** upstream hardcodes violet/pink in the
shell (outside the token system), so we restyle the shell too:
- `netlink/frontend/src/routes/(app)/+layout.svelte` (overlay) — minimalist,
  airy header: **breadcrumb on top**, a large clean solid page title (no
  gradient), a refined search pill and a minimal primary "Get Started" button,
  and a **flat `slate-50` content background** (replacing the violet→slate
  gradient). It keeps all upstream logic; only the markup/classes changed. (As a
  full overlay it won't auto-pick upstream layout changes — re-apply on big
  upstream layout updates.)
- Sidebar polish via `brand-patch.mjs` literal patches — a clean white panel with
  a hairline right border (was gray + heavy shadow) and a stronger active-item
  highlight (blue pill + left accent bar). Whitespace-safe, no-op if upstream
  renames the classes.

---

## 5. AI provider configuration (runtime)

1. Log in as an admin → **Policy Builder → "AI providers"** (top-right).
2. Each provider shows an **API key** field (+ optional Base URL override). Paste
   keys for the providers you want and set a **Default provider**, then save.
3. Keys are write-only (never returned to the browser). Any provider with a key
   immediately appears in the provider/model pickers in **both** Policy Builder
   and Audit Evidence.

Storage: `GlobalSettings(name="general").value`, keys `netlink_ai_<provider>_key`
and `netlink_ai_<provider>_base_url`, plus `netlink_ai_default_provider`.

---

## 6. Deployment

### Stack (`docker-compose-http.yml`)
`caddy` (:80, reverse-proxies `/api/*`→backend, `/*`→frontend) · `frontend`
(node) · `backend` (Django, SQLite in `./db`) · `huey` (task worker) · `qdrant`.

### Config (`.env.http`)
- `CISO_FQDN` — the **canonical public address** (IP or domain). Drives
  `ALLOWED_HOSTS`, `CISO_ASSISTANT_URL`, and the browser API URL. Access the app
  at exactly this address. (Additional accepted hosts are listed in
  `ALLOWED_HOSTS` in the compose file.)
- `NODE_BUILD_HEAP_MB` — frontend build heap ceiling.

### Fresh deploy from this repo
```bash
git clone https://github.com/Mrutunjay84/netlink-aegis-platform.git
cd netlink-aegis-platform
cp .env.http .env.http.local   # edit CISO_FQDN to your host's IP/domain
docker compose --env-file .env.http -f docker-compose-http.yml up -d --build
# first run: create an admin
docker exec -e DJANGO_SUPERUSER_EMAIL=you@example.com \
  -e DJANGO_SUPERUSER_PASSWORD='change-me' backend \
  poetry run python manage.py createsuperuser --noinput
```
Open `http://<CISO_FQDN>/` and log in.

> Plain HTTP sends credentials unencrypted. For a public host, front it with
> HTTPS (Caddy auto-TLS on a real domain, or a TLS-terminating proxy) and set
> `CISO_FQDN` to the domain.

---

## 7. How to make changes

### Rebuild & redeploy one service
```bash
cd /home/flash/aegis-build/netlink-aegis-platform
docker compose --env-file .env.http -f docker-compose-http.yml build backend   # or frontend
docker compose --env-file .env.http -f docker-compose-http.yml up -d backend huey   # frontend: up -d frontend
```
- **Backend Python changes** (anything in `netlink_policies/`): rebuild
  `backend`, recreate `backend` + `huey`. Fast (no node build).
- **Frontend changes** (routes/components/theme): rebuild `frontend`, recreate
  `frontend`. Slower (SvelteKit build; needs ~8 GB heap/swap).

### Add a new AI provider
Edit `netlink/backend/netlink_policies/providers.py` → add an entry to
`PROVIDERS` (label, `key_field`, `base_url_field`, `default_base_url`, `models`,
`default_model`). Nothing else needed — the admin panel, picker, save logic and
key storage are all derived from `PROVIDERS`. Rebuild backend + frontend.

### Add a new backend API endpoint
Add a `@action` to a ViewSet in `netlink_policies/`, or a new ViewSet registered
in `netlink_core/settings.py` `ROUTES`. Reach it at `/api/<route>/...`.

### Add a new page
Create `netlink/frontend/src/routes/(app)/(internal)/<name>/+page.svelte`
(+ `+page.server.ts` for loads/actions, `+server.ts` proxies for client fetches
that need backend auth). Add a sidebar entry + i18n keys in `feature-patch.mjs`.

### Restyle globally
Edit `netlink/frontend/src/netlink-theme.css` (prefer overriding Skeleton tokens
on `[data-theme='cisotheme']`). Rebuild frontend.

---

## 8. Operations runbook (gotchas we hit)

| Symptom | Cause | Fix |
|---|---|---|
| `DisallowedHost: ...` in backend logs | accessing via a host not in `ALLOWED_HOSTS` (e.g. a new domain) | add the host to `ALLOWED_HOSTS`/`CISO_FQDN`, recreate backend |
| Login silently fails over HTTP | `Secure` cookies dropped on plain HTTP | `SECURE_COOKIES=false` (already wired by `deploy-patch.mjs`); use a fresh/incognito login |
| Logout doesn't log you out (stays signed in) | `cookies.delete` defaults `secure:true`; over plain HTTP the browser drops the deletion cookie. `+server.ts` route endpoints were also not scanned by the deploy patch | `deploy-patch.mjs` now injects env-driven `secure` into `cookies.delete(...)` and scans `+server.ts`/`+server.js` too |
| Download/Save buttons dead, page not interactive | client-side hydration crash (e.g. wrapping a TipTap `Editor` in `$state`) | use `$state.raw` for editor; keep mount in try/catch (already done) |
| AI returns nothing / 502 | provider quota/outage (e.g. Gemini free tier 429/503) | retry, switch model/provider, or add a paid/other key; UI now shows the reason |
| Frontend build killed (exit 137) | OOM | lower `NODE_BUILD_HEAP_MB` or add swap; stop idle containers during build |

Health checks:
```bash
docker ps --format '{{.Names}} {{.Status}}'
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/login -H 'Host: <CISO_FQDN>'
docker logs backend --since 10m 2>&1 | tail -50
```

---

## 9. Source & branches

- Fork (deploy source): `https://github.com/Mrutunjay84/netlink-aegis-platform`
- Upstream remote: `intuitem` (`ciso-assistant-community`)
- Synced to upstream **v3.16.3**.

To pull upstream updates: merge the upstream tag into the overlay branch; because
all Netlink changes are overlay/patches, conflicts are minimal. Rebuild both
images and redeploy.

---

## 10. Security & dependency hardening

Dependency advisories are tracked with GitHub Dependabot and audited locally with
`pnpm audit` (frontend) and `pip-audit` (backend). Because we vendor upstream,
security fixes are applied as **minimal, surgical version pins** rather than wide
upgrades, so upstream merges stay clean.

### Frontend (npm / pnpm)
Fixes are expressed in `frontend/package.json` under `pnpm.overrides` (forces
patched versions everywhere a package appears, including transitive deps) plus a
few direct `devDependencies` bumps, then `pnpm-lock.yaml` is regenerated with the
pinned `pnpm@10.33.2`. Patched in this round:

| Package | Was | Now | Severity | Notes |
|---|---|---|---|---|
| `@sveltejs/kit` | 2.57.1 | ≥2.60.1 | moderate | `query.batch` cross-talk — **runtime** |
| `joi` (via superforms) | <17.13.4 | ≥17.13.4 | moderate | recursive-schema DoS — **runtime** |
| `protocol-buffers-schema` (via unovis/maplibre) | <3.6.1 | ≥3.6.1 | moderate | prototype pollution — **runtime** |
| `vite` | 6.4.2 | ≥6.4.3 | moderate/high | `server.fs.deny` bypass, launch-editor NTLM |
| `ws` (via jsdom) | <8.21.0 | ≥8.21.0 | high/moderate | DoS / uninitialized memory |
| `tar` | <7.5.16 | ≥7.5.16 | moderate | PAX long-name parser confusion |
| `js-yaml` | ≤4.1.1 | ≥4.2.0 | moderate | merge-key quadratic DoS |
| `brace-expansion` | <5.0.6 | ≥5.0.6 | moderate | range DoS |
| `vitest` / `@vitest/*` | 3.2.4 | ≥3.2.6 | critical | Vitest UI arbitrary file read/exec |

Result: `pnpm audit` reports **0 critical / high (runtime) / moderate / low**,
with one **knowingly-deferred** advisory below.

**Deferred: `esbuild` (high + low, build-time only).** The only patched release
(`≥0.28.1`) regresses the SvelteKit/Svelte compile — esbuild fails with
*"Transforming destructuring to the configured target environment … is not
supported yet"* on Svelte-generated chunks (reproduced on 0.28.1 and 0.27.7).
`esbuild` is therefore **pinned to the known-good `0.27.3`**. Risk is negligible
for us because:
- esbuild is a **build/dev tool**, not shipped at runtime — the production image
  runs `pnpm prune` (and a dedicated runner stage), so `esbuild`, `vite`,
  `vitest`, `jsdom`, `eslint` etc. are **not present in the deployed container**;
- both advisories require an attacker-controlled build/dev environment
  (malicious `NPM_CONFIG_REG` / Windows dev-server file read), which does not
  exist in our CI/build flow.

Re-check after each upstream bump: if esbuild ≥0.28.x later transpiles Svelte
output cleanly, raise the pin and re-run the audit.

### Backend (Python / Poetry)
Audited with `pip-audit`. Patched via `poetry update <pkg> --lock` (no
`pyproject.toml` change needed — the existing constraints already allow the fix):

| Package | Was | Now | Why |
|---|---|---|---|
| `django` | 6.0.5 | 6.0.6 | 5 advisories: signed-cookie salt, cache `Vary`/`Cache-Control` leaks, STARTTLS reuse |
| `pyjwt` | 2.12.1 | 2.13.0 | algorithm-confusion (JWK as HMAC secret), JWKS SSRF/DoS, detached-JWS amplification |

**Deferred: `torch` (CVE-2025-3000) and `transformers` (RCE in checkpoint /
Trainer load).** Both require **major** upgrades (transformers → 5.x) and are not
in our attack surface — we never load untrusted model checkpoints, and the
`torch.jit.script` path is a local-only vector. Revisit when upstream
(`sentence-transformers`) moves to a compatible major.

### How to re-audit
```bash
# Frontend (run from repo root)
docker run --rm -v "$(pwd)/frontend":/app -w /app node:24-slim sh -lc \
  "corepack enable >/dev/null; corepack prepare pnpm@10.33.2 --activate >/dev/null; pnpm audit"

# Backend (against the built image's actual installed versions)
docker exec backend poetry run pip freeze > /tmp/be.txt
docker run --rm -v /tmp/be.txt:/r.txt python:3.12-slim sh -lc \
  "pip install -q pip-audit && pip-audit -r /r.txt --no-deps"
```
After changing pins, regenerate the lockfile (`pnpm install --lockfile-only` or
`poetry update <pkg> --lock`), **rebuild and redeploy**, then re-audit.
