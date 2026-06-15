# Audit Evidence Assistant (Netlink Aegis module)

> Docmost placement: put this page under the **Modules** section, next to
> **AI Policy Builder**. Paste this file's content there once the feature has
> been verified live on the dev VM.

## What it does

The Audit Evidence Assistant helps an auditee figure out, control by control,
**what evidence to collect and exactly where to capture it** for an audit
(e.g. ISO/IEC 27001:2022 internal), tailored to the organization's own
technology stack.

For each control it returns concrete guidance:

- **Evidence to collect** - what proves the control is in place.
- **Where to capture it** - step-by-step navigation paths in the relevant
  product console (e.g. "Azure SQL Database -> Security -> Transparent data
  encryption").
- **Acceptable formats** - screenshot, configuration export, signed policy,
  contract, etc.
- **If not configured** - what to enable or remediate, and where.

Find it in the sidebar under **Governance -> Audit Evidence**
(`/audit-evidence`).

## Scope confidentiality (important)

You provide a **scoping document / technology scope** (free text). This is used
*only* as private grounding for the AI. The model is instructed to **never
restate, quote, summarize, or reveal the scope** - it only references the
generic **names** of the technologies/services relevant to the control being
viewed (e.g. "Azure SQL Database", "Microsoft Entra ID").

- The scope is **kept in your browser** (localStorage) and sent with each
  guidance request. It is not stored on the server and not attached to the
  audit.
- Different users do not see each other's scope.

## How to use it

1. Open **Governance -> Audit Evidence**.
2. **Step 1 - Your scope & AI model:** paste your technology scope, and pick the
   AI provider/model (same providers as the Policy Builder).
3. **Step 2 - Choose the audit or framework:**
   - **Existing audit** - pick one of your compliance assessments. Its controls
     and the framework name come from your real audit data.
   - **Framework library** - pick a loaded framework (e.g. ISO 27001:2022) to
     work straight from the standard's controls.
   - Click **Load controls**.
4. **Step 3 - Controls & evidence guidance:** the assessable controls are
   listed (searchable). Click any control to expand it and generate **on-demand
   AI guidance** for that control. Guidance is cached per control for the
   session.

## AI provider configuration

This module reuses the **same** multi-provider configuration as the Policy
Builder (Google Gemini / OpenAI / Anthropic, admin-configured keys stored in the
`general` global-settings record under `netlink_ai_*`). Configure keys once in
**Policy Builder -> AI providers**; both modules pick them up.

Only providers with a key configured appear in the picker. Guidance lookups are
rate-limited per user (120/hour).

## API surface

All under `/api/netlink-audit-evidence/`:

- `GET  /config/`   - which providers are configured + model presets (no
  secrets). Used to populate the picker.
- `POST /guidance/` - generate evidence guidance for ONE control. Body:
  `{control_ref, control_name, control_description, typical_evidence,
  framework, scope, provider, model}`. Returns `{html, markdown}`. The scope is
  private grounding only and is never echoed back.

Control lists are read from the existing community API by the frontend:

- Existing audit: `GET /api/requirement-assessments/?compliance_assessment=<id>`
  (assessable rows; the requirement node is embedded).
- Framework: `GET /api/requirement-nodes/?framework=<id>` (filtered to
  `assessable === true`).

## How it is built (architecture note)

The module lives entirely in the Netlink overlay so upstream merges stay clean.
No community (`backend/`, `frontend/`) source is modified.

- Backend (in the existing `netlink_policies` overlay app):
  - `audit_guidance.py` - confidentiality-constrained prompt + Markdown->HTML.
  - `audit_views.py` - the `config` / `guidance` endpoints. Registered via
    `netlink_core.settings.ROUTES["netlink-audit-evidence"]`.
  - Reuses `providers.py` (`provider_catalog`, `build_llm`) - same keys as the
    Policy Builder.
- Frontend route: `netlink/frontend/src/routes/(app)/(internal)/audit-evidence/`
  - `+page.svelte` - scope input, provider/model picker, audit/framework picker,
    control list, per-control guidance.
  - `+page.server.ts` - load (audits + frameworks + provider catalog).
  - `controls/+server.ts` - proxy that normalizes the control list from the
    community API.
  - `guidance/+server.ts` - proxy to the backend guidance endpoint.
- Build-time wiring (no community file edited): sidebar entry + i18n keys added
  by `netlink/frontend/feature-patch.mjs`.
