"""Multi-provider LLM configuration for the Netlink Aegis Policy Builder.

The policy builder supports three hosted LLM providers, each reached through
its OpenAI-compatible ``/chat/completions`` endpoint so a single client
(``chat.providers.OpenAICompatibleLLM``) handles all of them:

  - ``google``    -> Gemini (OpenAI-compatible endpoint). Recommended for
                     testing: the free tier works with ``gemini-*-flash``.
  - ``openai``    -> OpenAI / ChatGPT.
  - ``anthropic`` -> Claude (Anthropic's OpenAI-compatible endpoint).

API keys (and optional base-URL overrides) are configured *once* by an admin
and stored in ``GlobalSettings(name="general").value`` under ``netlink_ai_*``
keys. End users never see or enter keys; they only pick a provider + model in
the builder UI. The set of providers offered in the UI is derived from which
keys are configured (see :func:`provider_catalog`).

Storing the config in the existing ``general`` settings row keeps it alongside
the community chat settings without a new model/migration (the overlay app has
no migrations of its own).
"""

from __future__ import annotations

import re
import time

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# LLM call execution with retry/backoff
# ---------------------------------------------------------------------------
class LLMError(Exception):
    """Classified LLM failure. ``code`` is one of: rate_limited, overloaded,
    auth, generation_failed."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


# HTTP statuses worth retrying (transient provider conditions).
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def _status_from_exc(exc: Exception) -> int | None:
    """Best-effort extraction of an HTTP status code from a provider error."""
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    if isinstance(code, int):
        return code
    match = re.search(r"\b(400|401|403|404|408|409|429|500|502|503|504)\b", str(exc))
    return int(match.group(1)) if match else None


def _classify(status: int | None, exc: Exception) -> LLMError:
    if status == 429:
        return LLMError("rate_limited", str(exc))
    if status in (500, 502, 503, 504):
        return LLMError("overloaded", str(exc))
    if status in (401, 403):
        return LLMError("auth", str(exc))
    return LLMError("generation_failed", str(exc))


def generate_with_retry(
    llm,
    prompt: str,
    *,
    context: str = "",
    history: list | None = None,
    attempts: int = 3,
) -> str:
    """Call ``llm.generate`` with retry/backoff on transient provider errors.

    Retries 429/5xx with exponential backoff (1.5s, 3s). On final failure raises
    a classified :class:`LLMError` so callers can show an actionable message.
    """
    history = history or []
    last_exc: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            return llm.generate(prompt=prompt, context=context, history=history)
        except Exception as exc:  # noqa: BLE001 - provider clients raise varied types
            last_exc = exc
            status = _status_from_exc(exc)
            if status in _RETRYABLE_STATUSES and i < attempts - 1:
                time.sleep(1.5 * (2 ** i))
                continue
            raise _classify(status, exc) from exc
    # Should not reach here, but be safe.
    raise _classify(_status_from_exc(last_exc) if last_exc else None, last_exc or Exception("unknown"))


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------
# Model lists are presets for the picker only; the UI always allows a free-text
# override because provider model names drift frequently. ``default_base_url``
# can be overridden per provider via the matching ``*_base_url`` setting.
PROVIDERS: dict[str, dict] = {
    "google": {
        "label": "Google Gemini",
        "key_field": "netlink_ai_google_key",
        "base_url_field": "netlink_ai_google_base_url",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-pro",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ],
        "default_model": "gemini-2.5-flash",
    },
    "openai": {
        "label": "OpenAI (ChatGPT)",
        "key_field": "netlink_ai_openai_key",
        "base_url_field": "netlink_ai_openai_base_url",
        "default_base_url": "https://api.openai.com/v1",
        "models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
        ],
        "default_model": "gpt-4o-mini",
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "key_field": "netlink_ai_anthropic_key",
        "base_url_field": "netlink_ai_anthropic_base_url",
        "default_base_url": "https://api.anthropic.com/v1",
        "models": [
            "claude-sonnet-4-5",
            "claude-opus-4-1",
            "claude-3-7-sonnet-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
        ],
        "default_model": "claude-3-7-sonnet-latest",
    },
    "openrouter": {
        # Single key, hundreds of models (OpenAI/Anthropic/Google/Meta/etc.).
        # Model names are namespaced, e.g. "anthropic/claude-3.7-sonnet".
        "label": "OpenRouter (multi-model gateway)",
        "key_field": "netlink_ai_openrouter_key",
        "base_url_field": "netlink_ai_openrouter_base_url",
        "default_base_url": "https://openrouter.ai/api/v1",
        "models": [
            "openai/gpt-4o",
            "anthropic/claude-3.7-sonnet",
            "google/gemini-2.5-flash",
            "meta-llama/llama-3.3-70b-instruct",
            "deepseek/deepseek-chat",
            "mistralai/mistral-large",
        ],
        "default_model": "openai/gpt-4o",
    },
    "mistral": {
        "label": "Mistral AI",
        "key_field": "netlink_ai_mistral_key",
        "base_url_field": "netlink_ai_mistral_base_url",
        "default_base_url": "https://api.mistral.ai/v1",
        "models": [
            "mistral-large-latest",
            "mistral-small-latest",
            "open-mistral-nemo",
            "codestral-latest",
        ],
        "default_model": "mistral-large-latest",
    },
    "groq": {
        # Very fast inference for open models.
        "label": "Groq (fast open models)",
        "key_field": "netlink_ai_groq_key",
        "base_url_field": "netlink_ai_groq_base_url",
        "default_base_url": "https://api.groq.com/openai/v1",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "gemma2-9b-it",
            "mixtral-8x7b-32768",
        ],
        "default_model": "llama-3.3-70b-versatile",
    },
    "deepseek": {
        "label": "DeepSeek",
        "key_field": "netlink_ai_deepseek_key",
        "base_url_field": "netlink_ai_deepseek_base_url",
        "default_base_url": "https://api.deepseek.com/v1",
        "models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "default_model": "deepseek-chat",
    },
    "xai": {
        "label": "xAI (Grok)",
        "key_field": "netlink_ai_xai_key",
        "base_url_field": "netlink_ai_xai_base_url",
        "default_base_url": "https://api.x.ai/v1",
        "models": [
            "grok-4",
            "grok-3",
            "grok-3-mini",
            "grok-2-latest",
        ],
        "default_model": "grok-3",
    },
    "perplexity": {
        "label": "Perplexity",
        "key_field": "netlink_ai_perplexity_key",
        "base_url_field": "netlink_ai_perplexity_base_url",
        "default_base_url": "https://api.perplexity.ai",
        "models": [
            "sonar",
            "sonar-pro",
            "sonar-reasoning",
        ],
        "default_model": "sonar-pro",
    },
}

# Field names that hold secrets; never echoed back to clients in clear text.
SECRET_FIELDS = {p["key_field"] for p in PROVIDERS.values()}

# All netlink_ai_* fields the admin settings endpoint manages.
MANAGED_FIELDS = SECRET_FIELDS | {
    p["base_url_field"] for p in PROVIDERS.values()
} | {"netlink_ai_default_provider"}


# ---------------------------------------------------------------------------
# GlobalSettings access
# ---------------------------------------------------------------------------
def _general_value() -> dict:
    """Return the ``general`` GlobalSettings value dict (empty if absent)."""
    try:
        from global_settings.models import GlobalSettings

        gs = GlobalSettings.objects.filter(name="general").first()
        if gs and isinstance(gs.value, dict):
            return gs.value
    except Exception as e:  # table missing during migrate, etc.
        logger.warning("netlink_ai_settings_load_failed", error=str(e))
    return {}


def get_ai_settings() -> dict:
    """Read the netlink_ai_* settings into a plain dict (secrets included)."""
    value = _general_value()
    out: dict[str, str] = {}
    for field in MANAGED_FIELDS:
        out[field] = str(value.get(field, "") or "")
    return out


def save_ai_settings(updates: dict) -> dict:
    """Merge ``updates`` (only managed fields) into the general settings row.

    Empty-string values clear a field; values are stripped. Returns the masked
    settings (see :func:`masked_ai_settings`). Creates the ``general`` row if it
    does not exist, preserving any unrelated keys (e.g. chat settings).
    """
    from global_settings.models import GlobalSettings

    gs, _ = GlobalSettings.objects.get_or_create(name="general", defaults={"value": {}})
    value = gs.value if isinstance(gs.value, dict) else {}

    for field, raw in updates.items():
        if field not in MANAGED_FIELDS:
            continue
        value[field] = ("" if raw is None else str(raw)).strip()

    gs.value = value
    gs.save(update_fields=["value"])
    logger.info("netlink_ai_settings_saved", fields=sorted(updates.keys()))
    return masked_ai_settings()


def masked_ai_settings() -> dict:
    """Admin-facing view of the settings: secrets replaced by a boolean flag.

    Returns ``{ "<provider>": {configured, base_url}, default_provider }`` so the
    admin UI can show which keys are set and edit base URLs without ever
    receiving the stored key material.
    """
    settings = get_ai_settings()
    providers: dict[str, dict] = {}
    for pid, spec in PROVIDERS.items():
        providers[pid] = {
            "label": spec["label"],
            "configured": bool(settings.get(spec["key_field"], "").strip()),
            "base_url": settings.get(spec["base_url_field"], "").strip(),
            "default_base_url": spec["default_base_url"],
        }
    return {
        "providers": providers,
        "default_provider": settings.get("netlink_ai_default_provider", "").strip(),
    }


# ---------------------------------------------------------------------------
# Picker catalog + client construction
# ---------------------------------------------------------------------------
def provider_catalog() -> dict:
    """Non-secret catalog for the builder UI: only providers with a key set.

    Returns ``{ providers: [{id, label, models, default_model}], default }``.
    """
    settings = get_ai_settings()
    configured: list[dict] = []
    for pid, spec in PROVIDERS.items():
        if not settings.get(spec["key_field"], "").strip():
            continue
        configured.append(
            {
                "id": pid,
                "label": spec["label"],
                "models": list(spec["models"]),
                "default_model": spec["default_model"],
            }
        )

    default = settings.get("netlink_ai_default_provider", "").strip()
    valid_ids = {p["id"] for p in configured}
    if default not in valid_ids:
        default = configured[0]["id"] if configured else ""

    return {"providers": configured, "default": default}


def _base_url(provider_id: str, settings: dict) -> str:
    spec = PROVIDERS[provider_id]
    override = settings.get(spec["base_url_field"], "").strip()
    return override or spec["default_base_url"]


def build_llm(provider_id: str, model: str, system_prompt: str):
    """Construct an OpenAI-compatible LLM client for ``provider_id``.

    Returns the client, or ``None`` when the provider is unknown or has no API
    key configured (so callers can surface an "AI not configured" message).
    ``model`` falls back to the provider's default when blank.
    """
    spec = PROVIDERS.get(provider_id)
    if spec is None:
        logger.warning("netlink_ai_unknown_provider", provider=provider_id)
        return None

    settings = get_ai_settings()
    api_key = settings.get(spec["key_field"], "").strip()
    if not api_key:
        return None

    try:
        from chat.providers import OpenAICompatibleLLM
    except Exception as e:
        logger.warning("netlink_ai_import_failed", error=str(e))
        return None

    return OpenAICompatibleLLM(
        model=(model or "").strip() or spec["default_model"],
        base_url=_base_url(provider_id, settings),
        system_prompt=system_prompt,
        api_key=api_key,
    )
