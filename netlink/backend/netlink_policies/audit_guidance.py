"""AI evidence guidance for the Netlink Aegis Audit Evidence Assistant.

For a single audit control/requirement plus the organization's technology
*scope*, the model explains to the auditee what evidence demonstrates
compliance and exactly where/how to capture it (console navigation paths,
screenshots, exportable reports, policy/legal documents).

Confidentiality is the core constraint: the scope text is sent to the model
only as private grounding. The model must NEVER restate, quote, summarize, or
otherwise reveal the scope. It may only reference the specific technology /
service / product *names* that are relevant to the control at hand (e.g.
"Azure SQL Database", "Microsoft Entra ID") -- never the wider environment,
counts, owners, or any other scope detail.

The provider/model is resolved through :mod:`netlink_policies.providers`
(OpenAI / Anthropic / Gemini, admin-configured keys), exactly like the policy
builder. Output is Markdown, rendered to HTML for the UI.
"""

from __future__ import annotations

import structlog

from .drafting import _markdown_to_html
from .providers import LLMError, build_llm, generate_with_retry

logger = structlog.get_logger(__name__)


EVIDENCE_SYSTEM_PROMPT = (
    "You are a senior information-security auditor and evidence-collection "
    "advisor for frameworks such as ISO/IEC 27001, SOC 2, PCI DSS and NIST. "
    "For a single control you tell the auditee, in practical terms, what "
    "evidence proves the control is met and exactly where and how to capture "
    "it -- the navigation path inside the relevant product console, what a good "
    "screenshot or export looks like, and which policy or legal documents help. "
    "If a relevant technology appears to lack the control (e.g. encryption not "
    "enabled), advise enabling it and how.\n\n"
    "STRICT CONFIDENTIALITY RULES (never break these):\n"
    "- You are given the organization's internal SCOPE only as private context.\n"
    "- NEVER restate, quote, paraphrase, summarize, or list the scope.\n"
    "- NEVER reveal counts, names of people/teams, environments, locations, or "
    "any organizational detail from the scope.\n"
    "- You MAY use only the generic NAMES of technologies / cloud services / "
    "products that are relevant to THIS control, to make guidance concrete.\n"
    "- If the scope does not clearly relate to this control, give general "
    "best-practice evidence guidance without inventing specifics.\n\n"
    "Be concise, concrete and actionable. Output ONLY Markdown -- no preamble."
)


def _build_prompt(
    *,
    control_ref: str,
    control_name: str,
    control_description: str,
    typical_evidence: str,
    framework: str,
    scope: str,
) -> str:
    lines = []
    if framework:
        lines.append(f"Audit framework / standard: {framework}.")
    lines.append("Control under review:")
    if control_ref:
        lines.append(f"- Reference: {control_ref}")
    if control_name:
        lines.append(f"- Title: {control_name}")
    if control_description:
        lines.append(f"- Requirement: {control_description}")
    if typical_evidence:
        lines.append(f"- Typical evidence (from the framework): {typical_evidence}")

    lines += [
        "",
        "Organization technology SCOPE (PRIVATE CONTEXT -- never reveal, only "
        "use relevant service/technology names):",
        '"""',
        scope.strip() or "(no scope provided)",
        '"""',
        "",
        "Now write evidence-collection guidance for THIS control only, in "
        "Markdown, using these sections:",
        "",
        "**Evidence to collect** - a short bullet list of what proves this "
        "control is in place.",
        "",
        "**Where to capture it** - concrete, step-by-step navigation paths for "
        "the relevant technologies (e.g. 'Service > section > setting'). Name "
        "only the technology/service, not the wider scope.",
        "",
        "**Acceptable formats** - screenshot / configuration export / signed "
        "policy / contract, etc.",
        "",
        "**If not configured** - what to enable or remediate, and where.",
        "",
        "Keep it tight. Do not echo the scope text back.",
    ]
    return "\n".join(lines)


def evidence_guidance(
    *,
    control_ref: str = "",
    control_name: str = "",
    control_description: str = "",
    typical_evidence: str = "",
    framework: str = "",
    scope: str = "",
    provider: str = "",
    model: str = "",
) -> dict:
    """Synchronous LLM call producing evidence guidance for one control.

    Returns ``{html, markdown, ai_available, error}``.
    """
    result = {"html": "", "markdown": "", "ai_available": True, "error": ""}

    llm = build_llm(provider, model, EVIDENCE_SYSTEM_PROMPT)
    if llm is None:
        result["ai_available"] = False
        return result

    prompt = _build_prompt(
        control_ref=control_ref,
        control_name=control_name,
        control_description=control_description,
        typical_evidence=typical_evidence,
        framework=framework,
        scope=scope,
    )
    try:
        body = generate_with_retry(llm, prompt)
    except LLMError as e:
        logger.warning("audit_evidence_generation_failed", error=str(e), code=e.code)
        result["error"] = e.code
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("audit_evidence_generation_failed", error=str(e))
        result["error"] = "generation_failed"
        return result

    body = (body or "").strip()
    result["markdown"] = body
    result["html"] = _markdown_to_html(body)
    return result
