"""AI drafting for the Netlink policy builder.

Reuses the community chat provider configuration (``chat.providers``) so the
LLM backend stays 100% config-driven via Global Settings:

  - ``llm_provider = "openai_compatible"`` + ``openai_api_base`` /
    ``openai_model`` / ``openai_api_key``  -> any hosted API (Gemini, OpenAI,
    DeepSeek, OpenRouter, ...). This is the recommended, budget-friendly path.
  - ``llm_provider = "ollama"`` + ``ollama_base_url`` / ``ollama_model``
    -> self-hosted model (for later, if budget allows).

Swapping providers (hosted API -> self-hosted -> fine-tuned) is a settings
change only; nothing here needs to be edited.

We build a *dedicated* LLM client with a policy-author system prompt instead
of calling ``chat.providers.get_llm()``. ``get_llm()`` returns a shared, cached
instance whose system prompt is tuned for retrieval-only Q&A ("answer ONLY from
context") -- which would make the model refuse to author a document. We must
not mutate that shared instance, so we construct our own.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


POLICY_SYSTEM_PROMPT = (
    "You are a senior Governance, Risk and Compliance (GRC) policy author. "
    "You write clear, professional, standards-aligned organizational policy "
    "documents in well-structured Markdown. Be specific and actionable. "
    "Avoid vague placeholders where a sensible default can be stated. "
    "Output ONLY the policy document itself -- no preamble, no explanation, "
    "and no commentary before or after the document."
)


def _build_prompt(
    topic: str,
    *,
    audience: str = "",
    framework: str = "",
    extra: str = "",
) -> str:
    lines = [
        "Draft a complete organizational policy document on the following topic.",
        "",
        f"Topic: {topic}",
    ]
    if audience:
        lines.append(f"Intended audience: {audience}")
    if framework:
        lines.append(
            f"Align the policy with the following standard / framework where "
            f"relevant: {framework}"
        )
    if extra:
        lines.append(f"Additional context and requirements: {extra}")
    lines += [
        "",
        "Structure the policy in Markdown with these sections, in order:",
        "1. Purpose",
        "2. Scope",
        "3. Policy Statements",
        "4. Roles and Responsibilities",
        "5. Compliance and Enforcement",
        "6. Review and Revision",
        "",
        "Begin with a single level-1 Markdown heading containing the policy "
        "title. Return ONLY the Markdown policy document.",
    ]
    return "\n".join(lines)


def _build_policy_llm():
    """Construct an LLM client from the chat provider settings, using the
    policy-author system prompt. Returns ``None`` when no provider is
    configured (so the caller can let the user write the policy manually).
    """
    try:
        from chat.providers import (
            get_chat_settings,
            OpenAICompatibleLLM,
            OllamaLLM,
        )
    except Exception as e:  # chat app unavailable / import error
        logger.warning("policy_llm_import_failed", error=str(e))
        return None

    settings = get_chat_settings()
    provider = settings.get("llm_provider", "ollama")

    if provider == "openai_compatible":
        base_url = (settings.get("openai_api_base") or "").strip()
        if not base_url:
            return None
        return OpenAICompatibleLLM(
            model=settings.get("openai_model", ""),
            base_url=base_url,
            system_prompt=POLICY_SYSTEM_PROMPT,
            api_key=settings.get("openai_api_key", ""),
        )

    base_url = (settings.get("ollama_base_url") or "").strip()
    if not base_url:
        return None
    return OllamaLLM(
        model=settings.get("ollama_model", "mistral"),
        base_url=base_url,
        system_prompt=POLICY_SYSTEM_PROMPT,
    )


def draft_policy(
    topic: str,
    *,
    audience: str = "",
    framework: str = "",
    extra: str = "",
) -> dict:
    """Synchronous LLM call producing a draft policy document.

    Returns ``{name, description, ai_available, error}`` where ``description``
    is the generated Markdown body. This is a *proposal only* -- nothing is
    persisted. The caller (and ultimately the user) reviews and edits before
    anything is saved.
    """
    topic = (topic or "").strip()
    result = {
        "name": topic[:200],
        "description": "",
        "ai_available": True,
        "error": "",
    }

    llm = _build_policy_llm()
    if llm is None:
        result["ai_available"] = False
        return result

    prompt = _build_prompt(topic, audience=audience, framework=framework, extra=extra)
    try:
        body = llm.generate(prompt=prompt, context="", history=[])
    except Exception as e:
        logger.warning("policy_draft_generation_failed", error=str(e))
        result["error"] = "generation_failed"
        return result

    result["description"] = (body or "").strip()
    return result
