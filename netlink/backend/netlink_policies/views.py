"""Netlink Aegis - Policy builder API.

Registered on the community DRF router via ``netlink_core.settings.ROUTES``
(consumed by ``backend/core/urls.py``), so it is reachable under
``/api/netlink-policy-builder/``:

  - POST /api/netlink-policy-builder/draft/  -> AI draft (proposal only)
  - POST /api/netlink-policy-builder/save/   -> persist as a Policy

Human-in-the-loop by design: ``draft`` never writes; ``save`` creates a
``Policy`` only after a per-folder permission check.
"""

from __future__ import annotations

import structlog

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .drafting import draft_policy

logger = structlog.get_logger(__name__)


class PolicyDraftThrottle(UserRateThrottle):
    # Hosted LLM calls cost money per request; cap drafting per user.
    scope = "netlink_policy_draft"
    rate = "60/hour"


class PolicyBuilderViewSet(viewsets.ViewSet):
    """AI-assisted policy drafting + save-as-Policy."""

    permission_classes = [IsAuthenticated]

    @action(
        detail=False,
        methods=["post"],
        url_path="draft",
        throttle_classes=[PolicyDraftThrottle],
    )
    def draft(self, request):
        """Generate a draft policy document. Proposal only -- nothing saved."""
        topic = (request.data.get("topic") or "").strip()
        if not topic:
            return Response(
                {"detail": "topic is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        draft = draft_policy(
            topic,
            audience=(request.data.get("audience") or "").strip(),
            framework=(request.data.get("framework") or "").strip(),
            extra=(request.data.get("additional_context") or "").strip(),
        )
        return Response(draft, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="save")
    def save(self, request):
        """Persist a (possibly user-edited) draft as a Policy in a folder.

        Requires the ``add_appliedcontrol`` permission *in the target folder*
        -- holding it globally is not enough, matching the per-folder RBAC
        model used elsewhere (e.g. chat ``create_and_retry``).
        """
        from django.contrib.auth.models import Permission
        from django.core.exceptions import ValidationError as DjangoValidationError

        from core.models import Policy
        from iam.models import Folder, RoleAssignment

        folder_id = request.data.get("folder")
        name = (request.data.get("name") or "").strip()
        description = (request.data.get("description") or "").strip()
        ref_id = (request.data.get("ref_id") or "").strip()[:100]

        if not folder_id:
            return Response(
                {"detail": "folder is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not name:
            return Response(
                {"detail": "name is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            folder = Folder.objects.get(id=folder_id)
        except (Folder.DoesNotExist, ValueError, DjangoValidationError):
            return Response(
                {"detail": "Folder not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            add_perm = Permission.objects.get(codename="add_appliedcontrol")
        except Permission.DoesNotExist:
            return Response(
                {"detail": "Server permission state is inconsistent."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        if not RoleAssignment.is_access_allowed(
            user=request.user, perm=add_perm, folder=folder
        ):
            return Response(
                {
                    "detail": "You do not have permission to add a policy in "
                    "this folder."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        policy_kwargs = {
            "folder": folder,
            "name": name[:200],
            "description": description,
        }
        if ref_id:
            policy_kwargs["ref_id"] = ref_id

        policy = Policy.objects.create(**policy_kwargs)
        logger.info(
            "netlink_policy_created",
            policy_id=str(policy.id),
            folder_id=str(folder.id),
            user=str(getattr(request.user, "id", "")),
        )

        return Response(
            {
                "id": str(policy.id),
                "name": policy.name,
                "url": f"/policies/{policy.id}",
            },
            status=status.HTTP_201_CREATED,
        )
