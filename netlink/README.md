# Netlink Aegis edition

A white-labeled, internally-deployed edition of CISO Assistant, branded as
**Netlink Aegis**. It is implemented as an **overlay** on top of the AGPLv3
community core (mirroring how `enterprise/` overlays the core), so the
community source is never edited in place and upstream updates from intuitem
stay easy to merge.

## Layout

```
netlink/
  backend/
    netlink_core/        # Django app: settings overlay + URL/route hooks
      settings.py        #   `from ciso_assistant.settings import *` + our additions
      urls.py            #   mounted under /api/ via the MODULES hook (empty in Phase 0)
      apps.py
    manage.sh            # runs backend/manage.py --settings=netlink_core.settings
    Dockerfile           # community backend + netlink_core overlay
  frontend/
    brand-patch.mjs      # build-time white-label of i18n + hardcoded literals
    Makefile             # rsync community + netlink overlay, brand-patch, build (local dev)
    Dockerfile           # community frontend + netlink overlay + brand-patch
    src/...              # asset overrides (logo, etc.)
    static/...           # favicon
  docker-compose-build.yml  # builds both images from source (dev VM: IP + default_sni)
  LICENSE.md
```

## How the overlay works

- **Backend.** `netlink_core.settings` inherits the entire community
  configuration via `from ciso_assistant.settings import *`, then:
  - inserts `netlink_core` at the front of `INSTALLED_APPS` (so its
    `templates/` directory wins in the app-directories template loader, used
    for branded email/PDF overrides);
  - mutates the `ROUTES` / `MODULES` extension hooks consumed by
    `backend/core/urls.py` (empty in Phase 0, reserved for Phase 2/3 AI
    modules);
  - applies settings-level branding (OpenAPI title, default from-email).
- **Frontend.** The community tree is copied, the `netlink/frontend` overlay is
  layered on top (asset overrides win), and `brand-patch.mjs` rebrands the
  "CISO Assistant" phrase across all `messages/*.json` locales plus a small set
  of hardcoded Svelte literals.

## Build & run (dev VM, HTTPS over bare IP)

The existing `docker-compose.yml` runs the prebuilt community images. To run
**our** code/branding, build from source with the netlink compose file. It
reuses the repo-root `./db` and keeps the `default_sni` Caddy workaround for
IP-only TLS.

```bash
cd /home/flash/projects/netlink-aegis-platform

# Build the netlink images and start the stack (reuses ../db).
docker compose -f netlink/docker-compose-build.yml up -d --build

# Verify
curl -sk https://192.168.186.128:8443/api/health/   # -> {"status":"ok"}
```

> Build context for both images is the repository root, so always invoke the
> compose file by path (`-f netlink/docker-compose-build.yml`) from the repo
> root.

## Roadmap

- Phase 0 - overlay foundation (this scaffold). Done.
- Phase 1 - white-label to "Netlink Aegis". Done.
- Phase 2 - AI policy/standard builder (local LLM + RAG).
- Phase 3 - AI evidence/artifact validator (local OCR + local LLM).
