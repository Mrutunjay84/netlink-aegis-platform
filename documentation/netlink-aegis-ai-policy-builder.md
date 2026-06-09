# AI Policy Builder (Netlink Aegis module)

> Docmost placement: add a new top-level **Modules** section and put this page
> under it as **AI Policy Builder**. Paste this file's content there once the
> feature has been verified live on the dev VM.

## What it does

The AI Policy Builder lets a user describe a policy in plain language (a topic,
optional audience, an optional framework to align to, and any extra context),
generates a complete draft policy document with AI, and -- after the user
reviews and edits it -- saves it as a **Policy** in a chosen domain.

It is human-in-the-loop by design: the AI only *proposes* a draft; nothing is
written until the user clicks **Save as policy**.

Find it in the sidebar under **Governance -> Policy Builder** (`/policy-builder`).
Saved policies appear in the normal **Policies** list.

## How to use it

1. Open **Governance -> Policy Builder**.
2. Enter a **Policy topic** (e.g. "Acceptable Use Policy"). Optionally fill in
   audience, a framework to align to, and additional context.
3. Click **Generate draft**. The AI returns a structured Markdown policy
   (Purpose, Scope, Policy Statements, Roles, Enforcement, Review).
4. Review and edit the **name** and **body**, pick a **domain**, optionally set a
   **Reference ID**.
5. Click **Save as policy**. A link to the new policy appears on success.

Saving requires the "add applied control" permission **in the selected domain**.

## AI provider configuration (where the API key goes)

The module reuses the platform's existing LLM settings, so it is fully
config-driven -- no code change to switch providers. Configure it in
**Global Settings** (the same settings the chat assistant uses):

- `llm_provider = openai_compatible`
- `openai_api_base` = the provider's OpenAI-compatible base URL
- `openai_model` = the model name
- `openai_api_key` = your API key

Recommended budget-friendly default: **Google Gemini Flash** via its
OpenAI-compatible endpoint. Any OpenAI-compatible API works (OpenAI, DeepSeek,
OpenRouter, ...).

If no provider is configured, the Generate step returns no draft and the UI
tells the user they can still write the policy manually.

> Cost: this is pay-per-use (per request to the API). Drafting one policy is a
> single short request, so cost is minimal. Drafting is rate-limited per user.

## Swapping or upgrading the AI later

Because the provider is just configuration, you can change it at any time with
no code change:

1. **Now:** hosted API (e.g. Gemini Flash) -- cheapest to start.
2. **Later (if budget approved):** point `openai_api_base` at a self-hosted
   open model (or set `llm_provider = ollama`).
3. **Optional:** a fine-tuned / in-house model -- still just an endpoint behind
   the same settings.

## How it is built (architecture note)

The module lives entirely in the Netlink overlay so upstream merges stay clean:

- Backend app: `netlink/backend/netlink_policies/` (a `draft` endpoint that calls
  the LLM, and a `save` endpoint that creates a `Policy` after a per-domain
  permission check). Registered via `netlink_core.settings.ROUTES` ->
  `/api/netlink-policy-builder/`.
- Frontend route: `netlink/frontend/src/routes/(app)/(internal)/policy-builder/`
  (additive overlay file).
- Sidebar entry + i18n keys: injected at build time by
  `netlink/frontend/feature-patch.mjs` (same pattern as `brand-patch.mjs`), so
  no community file is edited.

No community (`backend/`, `frontend/`) source is modified.
