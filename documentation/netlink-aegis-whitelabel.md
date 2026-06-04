# Netlink Aegis - White-Label Runbook (for non-developers)

> Plain-language guide to how "CISO Assistant" was turned into **Netlink Aegis**,
> how to change the logo / branding later, how to rebuild and deploy, and how to
> keep everything safely tracked in GitHub.
> Safe to import into Docmost (Import -> Markdown).

- **App URL (dev VM):** `https://192.168.186.128:8443`
- **What this covers:** branding only (name + logo + favicon + texts). Not the AI features (those are later phases).
- **Golden rule:** we do **NOT** edit the original CISO Assistant code. All our changes live in one folder: `netlink/`. This keeps us able to pull future updates from the original makers (intuitem) without conflicts.

---

## 1. The big idea (read this once)

Think of the app as a cake that someone else bakes (the "community" CISO Assistant).
We don't re-bake the cake. We add our own **icing layer** on top, called `netlink/`.

- The cake (original code) stays untouched, in folders like `backend/` and `frontend/`.
- Our icing (everything Netlink) lives in `netlink/`.
- When we build the app, the computer copies the cake, spreads our icing on top, and
  serves the result. Where our icing covers a spot, ours shows; everywhere else the
  original shows through.

Because the original code is never edited, we can safely receive updates from the
original makers later (see Section 7).

**The "icing" does three jobs:**

1. Swaps the **logo** and **favicon** for ours.
2. Rewrites every "CISO Assistant" wording to "**Netlink Aegis**" automatically (in 25
   languages, in emails, and in PDFs).
3. Sets up an empty, ready slot for the future AI features.

---

## 2. Where everything lives (map)

```
netlink/
  README.md                         <- short technical readme
  LICENSE.md                        <- our ownership/license note
  docker-compose-build.yml          <- the file used to BUILD & RUN our version

  frontend/                         <- everything the user SEES in the browser
    src/lib/assets/netlink-logo.png <- *** THE LOGO FILE ***
    src/lib/components/Logo/Logo.svelte  <- tells the app to use our logo
    static/favicon.svg              <- the little browser-tab icon
    brand-patch.mjs                 <- auto-rewrites "CISO Assistant" -> "Netlink Aegis" (frontend)
    Dockerfile / Makefile           <- build instructions (don't need to touch)

  backend/                          <- the server side (emails, PDFs, API)
    brand_patch.py                  <- auto-rewrites "CISO Assistant" -> "Netlink Aegis" (emails/PDFs)
    netlink_core/                   <- our settings module (app title, sender email, etc.)
    Dockerfile / manage.sh          <- build instructions (don't need to touch)
```

The two files you are most likely to ever touch:

| If you want to change... | Edit this file |
|--------------------------|----------------|
| The **logo**             | `netlink/frontend/src/lib/assets/netlink-logo.png` |
| The **brand name** ("Netlink Aegis") | `BRAND_NEW` in both `netlink/frontend/brand-patch.mjs` **and** `netlink/backend/brand_patch.py` |
| The **favicon** (tab icon) | `netlink/frontend/static/favicon.svg` |

---

## 3. How to change the LOGO (step by step)

The logo appears on the login screen, the welcome screens, and the top of the sidebar.

### Step 1 - Replace the logo file

Put your new logo where the old one is, **using the exact same name** so no code needs
to change. From the project folder:

```bash
cd /home/flash/projects/netlink-aegis-platform

# Copy your new logo over the existing one (replace the source path with yours):
cp /path/to/your-new-logo.png netlink/frontend/src/lib/assets/netlink-logo.png
```

Logo tips:
- **PNG with a transparent background** works best.
- A **square** image (e.g. 512x512 or 1024x1024) looks right; the app shows it in a
  200x200 box. A very wide image will look small.
- If your new file is **not** a `.png` (say it's `.svg`), tell your developer/AI to also
  update the one-line `import` in `netlink/frontend/src/lib/components/Logo/Logo.svelte`.
  If you keep it as `netlink-logo.png`, nothing else needs changing.

### Step 2 - Rebuild and restart the front end

The app serves a pre-built version, so a file swap alone is not enough - you must
rebuild. This takes roughly **8-10 minutes**.

```bash
cd /home/flash/projects/netlink-aegis-platform

# 1) Rebuild just the front end with the new logo baked in
docker compose -f netlink/docker-compose-build.yml build frontend

# 2) Swap the running front end for the freshly built one
docker compose -f netlink/docker-compose-build.yml up -d --no-deps frontend
```

### Step 3 - See it

Open `https://192.168.186.128:8443/login` and do a **hard refresh** so your browser
doesn't show the old cached logo:
- Windows/Linux: `Ctrl + Shift + R`
- Mac: `Cmd + Shift + R`

### Step 4 (optional) - Confirm it really took

```bash
curl -sk https://192.168.186.128:8443/login | grep -o 'netlink-logo[^"]*\.png'
```
If it prints something like `netlink-logo.xxxx.png`, the new logo is live.

---

## 4. How to change the brand NAME or the favicon

### Change the favicon (the tiny tab icon)
Replace `netlink/frontend/static/favicon.svg` with your icon (a small, square,
icon-only mark works best - text is unreadable at tiny sizes). Then rebuild the front
end exactly like Section 3, Step 2.

### Change the brand name (e.g. from "Netlink Aegis" to something else)
The name is applied automatically by two small scripts. Change the value in **both**:

- `netlink/frontend/brand-patch.mjs` -> the line `const BRAND_NEW = 'Netlink Aegis';`
- `netlink/backend/brand_patch.py`  -> the line `BRAND_NEW = "Netlink Aegis"`

Then rebuild **both** images (see Section 5). These scripts find every "CISO Assistant"
in the original app and replace it with your name - across all 25 languages, emails, and
PDFs - without touching the original files.

> The API title and the default email sender address are set separately in
> `netlink/backend/netlink_core/settings.py` (search for "Netlink Aegis"). Change them
> there if needed.

---

## 5. Rebuilding & running the whole thing (cheat sheet)

Always run these from the project root: `/home/flash/projects/netlink-aegis-platform`,
and always include `-f netlink/docker-compose-build.yml`.

```bash
cd /home/flash/projects/netlink-aegis-platform

# Build BOTH images from our code (front end ~10 min, back end is large/slower)
docker compose -f netlink/docker-compose-build.yml build

# Start (or restart) the whole stack
docker compose -f netlink/docker-compose-build.yml up -d

# Check everything is running
docker compose -f netlink/docker-compose-build.yml ps

# See logs if something looks wrong
docker compose -f netlink/docker-compose-build.yml logs -f backend

# Stop everything (your data in ./db is kept)
docker compose -f netlink/docker-compose-build.yml down

# Quick health check
curl -sk https://192.168.186.128:8443/api/health/    # should print {"status":"ok"}
```

To rebuild only one part: add `frontend` or `backend` at the end of the `build` command.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| New logo doesn't appear | Browser cached the old one | Hard refresh (`Ctrl/Cmd + Shift + R`), or open a private window |
| New logo doesn't appear | You didn't rebuild + restart | Re-run Section 3, Step 2 |
| Build dies with "Killed" / exit 137 | Not enough RAM | The VM needs ~9-10 GB RAM. We set the build memory limit in `netlink/frontend/Dockerfile` (`NODE_BUILD_HEAP_MB`) |
| Build dies with "heap out of memory" / exit 134 | Memory limit set too low | Raise `NODE_BUILD_HEAP_MB` in `netlink/frontend/Dockerfile` (we use 8192 on a 9.5 GB VM) |
| Page still says "CISO Assistant" somewhere | A rare hardcoded spot we left as a minor exception | Note where you saw it and ask your developer/AI to add it to the brand-patch |

> Note: the build is slow on purpose-safe ordering. The wording-replacement step must run
> before the language files are compiled, so we cannot use the usual caching shortcut.
> Expect ~8-12 minutes per front-end rebuild.

---

## 7. Tracking everything in GitHub (for non-developers)

**Why bother?** GitHub is your **safety net and history book**. Every saved change can be
undone, compared, and recovered. If the VM dies, your work is still on GitHub.

Your repository: `https://github.com/Mrutunjay84/netlink-aegis-platform`
Your work lives on the **`main`** branch (your source of truth). The white-label and
deployment work is already committed and pushed there.

### 7.1 The 3-command routine (do this after each change that WORKS)

Think of it as "Save to the cloud". After you change the logo (or anything) and confirm
it works in the browser:

```bash
cd /home/flash/projects/netlink-aegis-platform

# 1) Stage your changes (the "what to save")
git add netlink/ documentation/

# 2) Save them with a short note about WHAT you did
git commit -m "Update Netlink Aegis logo"

# 3) Upload to GitHub
git push
```

That's it. Repeat whenever you make a change you want to keep.

### 7.2 What NOT to save

Never commit secrets or data. These are already set to be ignored, but as a rule:
- Do **not** commit passwords, the `DJANGO_SECRET_KEY`, or any `.env.prod` file.
- Do **not** commit the `db/` folder (that's your live database/uploads).

If you're unsure whether something is a secret, ask before pushing.

### 7.3 Good commit messages (just describe what you did)

- `Update Netlink Aegis logo`
- `Change favicon to new icon`
- `Rebrand name from Netlink Aegis to <new name>`
- `Add white-label runbook documentation`

### 7.4 When to do what (simple rhythm)

| Moment | Action |
|--------|--------|
| You changed a file and it works | Do the 3-command routine (7.1) |
| You're about to try something risky | Commit first, so you can go back |
| End of a working session | Commit + push, so GitHub has the latest |
| You broke something and want the last good version | Ask your developer/AI to "revert to the last commit" |

### 7.5 Branches (the short version)

A **branch** is a separate workspace so experiments don't disturb the main version.
- For everyday changes (logo, favicon, name tweaks), you work directly on `main` and use
  the 3-command routine (7.1). That's all you need.
- For a big new feature (e.g. the future AI policy builder), your developer will create a
  separate, clearly-named branch, then **merge** it back into `main` via a "Pull Request"
  on GitHub once it's solid. Leave that part to your developer.

### 7.6 Getting future updates from the original makers (intuitem) - advanced

Because all our changes are isolated in `netlink/`, we can pull improvements from the
original project later with minimal conflict. This is a one-time setup plus an
occasional update, and is best done **with a developer present** the first time:

```bash
# One-time: tell git where the original project lives
git remote add upstream https://github.com/intuitem/ciso-assistant-community.git

# Occasionally: fetch their latest and merge it in
git fetch upstream
git merge upstream/main      # your developer resolves anything that overlaps
```

After an update like this, **rebuild** (Section 5) and re-test. Don't do this right before
an important demo.

---

## 8. One-page summary

- All our changes live in `netlink/`. The original app is never edited.
- **Change logo:** replace `netlink/frontend/src/lib/assets/netlink-logo.png`, then
  `build frontend` + `up -d --no-deps frontend`, then hard-refresh the browser.
- **Rebuild everything:** `docker compose -f netlink/docker-compose-build.yml build` then
  `... up -d`.
- **Save your work:** `git add netlink/ documentation/` -> `git commit -m "..."` -> `git push`.
- **Never commit:** passwords, secret keys, `.env.prod`, or the `db/` folder.
- **Updates from intuitem:** possible and low-conflict thanks to the `netlink/` design; do
  it with a developer the first time.
