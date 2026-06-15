"""AI drafting for the Netlink Aegis policy builder.

Pure generation: the model authors a brand-new policy document from the
caller's inputs (industry + compliance framework + topic + free-text context).
Nothing from the existing policy register is read or reused.

The selected provider/model is resolved through :mod:`netlink_policies.providers`
(OpenAI / Anthropic / Gemini, admin-configured keys). The model is asked for
well-structured Markdown, which we also render to HTML here so the frontend can
load it directly into the WYSIWYG editor (the user never sees raw Markdown).
"""

from __future__ import annotations

import re

import structlog

from .providers import LLMError, build_llm, generate_with_retry

logger = structlog.get_logger(__name__)


POLICY_SYSTEM_PROMPT = (
    "You are a senior Governance, Risk and Compliance (GRC) policy author. "
    "You write clear, professional, standards-aligned organizational policy "
    "documents in well-structured Markdown. Be specific and actionable, and "
    "tailor the content to the stated industry and compliance framework. "
    "Avoid vague placeholders where a sensible default can be stated. "
    "Output ONLY the policy document itself -- no preamble, no explanation, "
    "and no commentary before or after the document."
)


def _build_prompt(
    topic: str,
    *,
    industry: str = "",
    framework: str = "",
    extra: str = "",
) -> str:
    lines = [
        "Draft a complete, professional organizational policy document.",
        "",
        f"Policy topic: {topic}",
    ]
    if industry:
        lines.append(
            f"Industry / sector: {industry}. Use terminology, risks, and "
            f"regulatory expectations relevant to this industry."
        )
    if framework:
        lines.append(
            f"Align the policy with this compliance framework / standard and "
            f"reference its relevant clauses where appropriate: {framework}."
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
        "title. Use level-2 headings for each section. Return ONLY the Markdown "
        "policy document.",
    ]
    return "\n".join(lines)


def _markdown_to_html(md: str) -> str:
    """Render Markdown to HTML for the WYSIWYG editor.

    Uses the ``markdown`` library (already a backend dependency). Falls back to
    a minimal paragraph wrap if rendering fails for any reason.
    """
    md = (md or "").strip()
    if not md:
        return ""
    try:
        import markdown as md_lib

        return md_lib.markdown(
            md,
            extensions=["extra", "sane_lists", "nl2br"],
        )
    except Exception as e:
        logger.warning("policy_markdown_render_failed", error=str(e))
        escaped = (
            md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return "".join(
            f"<p>{block}</p>" for block in escaped.split("\n\n") if block.strip()
        )


def _extract_title(md: str, fallback: str) -> str:
    """Pull the document title from the first level-1 Markdown heading."""
    for line in (md or "").splitlines():
        stripped = line.strip()
        m = re.match(r"^#\s+(.*)$", stripped)
        if m and m.group(1).strip():
            return m.group(1).strip()[:200]
    return (fallback or "").strip()[:200]


def draft_policy(
    topic: str,
    *,
    industry: str = "",
    framework: str = "",
    extra: str = "",
    provider: str = "",
    model: str = "",
) -> dict:
    """Synchronous LLM call producing a draft policy document.

    Returns ``{name, markdown, html, ai_available, error}``. This is a
    *proposal only* -- nothing is persisted. The user reviews and edits in the
    WYSIWYG editor before anything is saved or exported.
    """
    topic = (topic or "").strip()
    result = {
        "name": topic[:200],
        "markdown": "",
        "html": "",
        "ai_available": True,
        "error": "",
    }

    llm = build_llm(provider, model, POLICY_SYSTEM_PROMPT)
    if llm is None:
        result["ai_available"] = False
        return result

    prompt = _build_prompt(topic, industry=industry, framework=framework, extra=extra)
    try:
        body = generate_with_retry(llm, prompt)
    except LLMError as e:
        logger.warning("policy_draft_generation_failed", error=str(e), code=e.code)
        result["error"] = e.code
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("policy_draft_generation_failed", error=str(e))
        result["error"] = "generation_failed"
        return result

    body = (body or "").strip()
    result["markdown"] = body
    result["html"] = _markdown_to_html(body)
    result["name"] = _extract_title(body, topic)
    return result
