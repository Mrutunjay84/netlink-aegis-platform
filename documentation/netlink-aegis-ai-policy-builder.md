# AI Policy Builder (Netlink Aegis module)

> Docmost placement: add a new top-level **Modules** section and put this page
> under it as **AI Policy Builder**. Paste this file's content there once the
> feature has been verified live on the dev VM.

## What it does

The AI Policy Builder generates a brand-new, professional governance policy from
a few structured inputs:

- **Industry / sector** (e.g. BFSI, Healthcare, IT/SaaS) so the language and
  risks are relevant.
- **Compliance framework** (e.g. ISO 27001, SOC 2, PCI DSS, HIPAA, GDPR, NIST
  CSF) so the policy references the right controls.
- **Policy topic** and any **additional context**.

It is pure generation: nothing from the existing policy register is read or
reused. The AI authors the document; the user then refines it in a **Word-like
rich-text editor** (headings, bold/italic/underline, lists, quotes, etc.) and
can:

- **Save it to the Policy register** as a new Policy in a chosen domain, and
- **Download it as a Word (.docx) or PDF file**.

It is human-in-the-loop by design: the AI only *proposes* a draft; nothing is
written to the register until the user clicks **Save to policy register**.

Find it in the sidebar under **Governance -> Policy Builder**
(`/policy-builder`).

## How to use it

1. Open **Governance -> Policy Builder**.
2. Enter a **Policy topic** (e.g. "Acceptable Use Policy"). Choose an
   **Industry** and a **Compliance framework** (or pick "Other" and type your
   own). Add optional context.
3. Pick the **AI provider** and **model** (see configuration below). You can
   type a custom model name if needed.
4. Click **Generate policy**. The AI returns a structured document (Purpose,
   Scope, Policy Statements, Roles, Enforcement, Review) loaded directly into
   the editor.
5. **Review and edit** the document in the rich-text editor. Adjust the policy
   name and optional reference ID.
6. Then either:
   - **Download DOCX** / **Download PDF** to get a file, and/or
   - choose a **domain** and click **Save to policy register**.

Saving requires the "add applied control" permission **in the selected domain**.

## AI provider configuration (multi-model)

The builder supports three hosted providers, each reached through its
OpenAI-compatible endpoint:

| Provider | Setting key | Default base URL |
| --- | --- | --- |
| Google Gemini | `netlink_ai_google_key` | `https://generativelanguage.googleapis.com/v1beta/openai` |
| OpenAI (ChatGPT) | `netlink_ai_openai_key` | `https://api.openai.com/v1` |
| Anthropic (Claude) | `netlink_ai_anthropic_key` | `https://api.anthropic.com/v1` |

**Admins** configure the API keys once, directly in the Policy Builder UI:

1. Open **Policy Builder** and click **AI providers** (top right; visible only to
   admins).
2. Paste the API key for each provider you want to enable. Optionally override
   the base URL. Pick a default provider.
3. Save. Keys are stored on the server (in the `general` global-settings record,
   under `netlink_ai_*` keys) and are never displayed again -- the panel only
   shows whether each provider is "Configured". Leaving a key field blank keeps
   the existing key.

Only providers that have a key configured appear in the provider picker for end
users. End users never see or enter API keys.

Recommended budget-friendly default for testing: **Google Gemini Flash** (the
free tier works with `gemini-2.0-flash` / `gemini-1.5-flash`).

> Cost: this is pay-per-use (per request to the provider). Drafting one policy is
> a single short request, so cost is minimal. Drafting is rate-limited per user
> (60/hour).

## Export (DOCX / PDF)

Export is done server-side from the edited HTML, so the downloaded file matches
what you see in the editor:

- **PDF** is rendered with WeasyPrint (already a platform dependency) using a
  clean A4 document stylesheet.
- **DOCX** is produced with `python-docx` via `htmldocx`.

Both are reachable through `POST /api/netlink-policy-builder/export/` and the
frontend proxy route `/policy-builder/export`.

## Company document template (letterhead / watermark)

Exports can be branded with a reusable company template so every policy comes
out on the same letterhead:

- **Header / footer + watermark fields** - set a company name, watermark text
  (defaults to the company name), and optional header/footer text. Applied to
  both **DOCX** and **PDF** (PDF also gets page numbers).
- **Uploaded Word letterhead (.docx)** - an admin uploads a `.docx` whose
  header, footer, watermark and logo are designed in Word. Generated content is
  appended into that document for **DOCX** export, so the result keeps the full
  custom branding. (PDF export still uses the fields above.)

**Admins** configure this in **Policy Builder -> AI providers** panel, under
**Company document template**: toggle "apply by default", fill the fields,
optionally upload a `.docx`, and Save. The uploaded file is stored base64 in the
`general` global-settings record (`netlink_doc_*` keys), so it persists with the
database and needs no media volume.

**Every export has its own toggle** ("Apply company template", next to the
Download buttons) so a user can produce an unbranded copy when needed. It
defaults to the admin's "apply by default" setting.

API: `GET|PUT /api/netlink-policy-builder/doc-template/` (GET is non-secret and
available to all users for the toggle default; PUT is admin-only). The export
endpoint honours an `apply_template` boolean in its body.

## API surface

All under `/api/netlink-policy-builder/`:

- `GET  /config/` - which providers are configured + their model presets (no
  secrets). Used to populate the picker.
- `POST /draft/` - generate a draft (`topic`, `industry`, `framework`,
  `additional_context`, `provider`, `model`). Returns `{name, html, markdown}`.
  Proposal only; nothing is saved. Rate-limited.
- `POST /save/` - create a Policy (`folder`, `name`, `description`, `ref_id`)
  after a per-domain `add_appliedcontrol` permission check.
- `POST /export/` - render `{html, format: docx|pdf, title}` to a downloadable
  file.
- `GET|PUT /settings/` - **admin only**: read masked settings / update provider
  keys, base URLs, and default provider.

## How it is built (architecture note)

The module lives entirely in the Netlink overlay so upstream merges stay clean.
No community (`backend/`, `frontend/`) source is modified.

- Backend app: `netlink/backend/netlink_policies/`
  - `providers.py` - provider registry + key lookup/storage in
    `GlobalSettings("general")` under `netlink_ai_*`.
  - `drafting.py` - prompt construction + Markdown-to-HTML rendering.
  - `views.py` - the `config` / `draft` / `save` / `export` / `settings`
    endpoints. Registered via `netlink_core.settings.ROUTES`.
- Frontend route: `netlink/frontend/src/routes/(app)/(internal)/policy-builder/`
  - `+page.svelte` - inputs, provider/model picker, editor, downloads, admin
    panel.
  - `+page.server.ts` - load (folders + provider catalog + admin settings) and
    the `draft` / `save` / `saveSettings` actions.
  - `export/+server.ts` - streams the generated DOCX/PDF back to the browser.
  - `RichTextEditor.svelte` (`$lib/components/PolicyBuilder/`) - TipTap WYSIWYG
    editor.
- Build-time wiring (no community file edited):
  - Sidebar entry + i18n keys: `netlink/frontend/feature-patch.mjs`.
  - TipTap packages: added via `pnpm add` in `netlink/frontend/Dockerfile`.
  - `htmldocx`: added via `pip install` in `netlink/backend/Dockerfile`.
