"""Netlink Aegis - Audit Evidence Assistant API.

Registered on the community DRF router via ``netlink_core.settings.ROUTES``
(consumed by ``backend/core/urls.py``), reachable under
``/api/netlink-audit-evidence/``:

  - GET  /api/netlink-audit-evidence/config/    -> provider picker catalog
         (which providers are configured + model presets). Non-secret.
  - POST /api/netlink-audit-evidence/guidance/  -> AI evidence guidance for one
         control, grounded on a pasted technology scope.

The scope is supplied per request by the client (kept in the browser) and is
used only as private grounding; the model is instructed never to reveal it. See
:mod:`netlink_policies.audit_guidance`.
"""

from __future__ import annotations

import structlog

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .audit_guidance import evidence_guidance
from .providers import provider_catalog

logger = structlog.get_logger(__name__)


class AuditEvidenceThrottle(UserRateThrottle):
    # Hosted LLM calls cost money per request; cap guidance lookups per user.
    scope = "netlink_audit_evidence"
    rate = "120/hour"


class AuditEvidenceViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="config")
    def config(self, request):
        """Provider/model catalog for the picker (no secrets)."""
        return Response(provider_catalog())

    @action(
        detail=False,
        methods=["post"],
        url_path="guidance",
        throttle_classes=[AuditEvidenceThrottle],
    )
    def guidance(self, request):
        """Generate evidence guidance for a single control.

        Body: ``{control_ref, control_name, control_description,
        typical_evidence, framework, scope, provider, model}``. The control
        details are non-confidential framework text; ``scope`` is the user's
        private technology context (never echoed back).
        """
        data = request.data or {}

        def _s(key: str) -> str:
            return str(data.get(key, "") or "").strip()

        control_name = _s("control_name")
        control_description = _s("control_description")
        if not control_name and not control_description:
            return Response(
                {"detail": "A control name or description is required."},
                status=400,
            )

        result = evidence_guidance(
            control_ref=_s("control_ref"),
            control_name=control_name,
            control_description=control_description,
            typical_evidence=_s("typical_evidence"),
            framework=_s("framework"),
            scope=_s("scope"),
            provider=_s("provider"),
            model=_s("model"),
        )

        if not result.get("ai_available", False):
            return Response(
                {
                    "detail": (
                        "No AI provider is configured. An administrator must add "
                        "an API key in Policy Builder > AI providers."
                    ),
                    "ai_available": False,
                },
                status=503,
            )
        if result.get("error"):
            code = result["error"]
            messages = {
                "rate_limited": (
                    "The AI provider is rate-limited or out of quota right now "
                    "(for example the Google Gemini free-tier limit). Wait about a "
                    "minute and try again, or pick a different model/provider in "
                    "step 1."
                ),
                "overloaded": (
                    "The AI provider is temporarily overloaded (it was retried "
                    "automatically). Please try again in a few moments, or switch "
                    "to a different model/provider in step 1."
                ),
                "auth": (
                    "The AI provider rejected the API key. An administrator should "
                    "re-check the key in Policy Builder > AI providers."
                ),
            }
            detail = messages.get(code, "AI generation failed. Please try again.")
            return Response({"detail": detail, "error": code}, status=502)

        return Response({"html": result["html"], "markdown": result["markdown"]})
