"""Netlink Aegis - Policy builder API.

Registered on the community DRF router via ``netlink_core.settings.ROUTES``
(consumed by ``backend/core/urls.py``), so it is reachable under
``/api/netlink-policy-builder/``:

  - GET  /api/netlink-policy-builder/config/    -> picker catalog (which
         providers are configured + their model presets). Non-secret.
  - POST /api/netlink-policy-builder/draft/     -> AI draft (proposal only)
  - POST /api/netlink-policy-builder/save/      -> persist as a Policy
  - POST /api/netlink-policy-builder/export/    -> download DOCX / PDF
  - GET|PUT /api/netlink-policy-builder/settings/ -> admin: provider API keys

Human-in-the-loop by design: ``draft`` never writes; ``save`` creates a
``Policy`` only after a per-folder permission check; ``settings`` is admin-only.
"""

from __future__ import annotations

import base64
import io
import os
import re
import tempfile

import structlog

from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from . import doc_template
from .drafting import draft_policy
from .providers import (
    PROVIDERS,
    masked_ai_settings,
    provider_catalog,
    save_ai_settings,
)

logger = structlog.get_logger(__name__)


class PolicyDraftThrottle(UserRateThrottle):
    # Hosted LLM calls cost money per request; cap drafting per user.
    scope = "netlink_policy_draft"
    rate = "60/hour"


def _is_ai_admin(user) -> bool:
    """Whether ``user`` may view/change the AI provider settings.

    Superusers always qualify. Otherwise we honour a global
    ``change_globalsettings`` permission via the community RBAC model, so an
    admin role can manage keys without being a Django superuser.
    """
    if getattr(user, "is_superuser", False):
        return True
    try:
        from django.contrib.auth.models import Permission
        from iam.models import Folder, RoleAssignment

        perm = Permission.objects.get(codename="change_globalsettings")
        return RoleAssignment.is_access_allowed(
            user=user, perm=perm, folder=Folder.get_root_folder()
        )
    except Exception:
        return False


def _safe_filename(title: str, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (title or "").strip()).strip("_")
    return f"{base[:80] or 'policy'}.{ext}"


def _wrap_html(title: str, body_html: str, branding: dict | None = None) -> str:
    """Wrap editor HTML in a styled, standalone document for PDF rendering.

    ``branding`` (optional) carries extra ``css`` (running header/footer +
    watermark style) and ``watermark_html`` injected for the company template.
    """
    safe_title = (title or "Policy").replace("<", "&lt;").replace(">", "&gt;")
    branding_css = (branding or {}).get("css", "")
    watermark_html = (branding or {}).get("watermark_html", "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{safe_title}</title>
<style>
  @page {{ size: A4; margin: 2.2cm 2cm; }}
  body {{ font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
          font-size: 11pt; line-height: 1.5; color: #1a1a1a; }}
  h1 {{ font-size: 20pt; margin: 0 0 0.6em; border-bottom: 2px solid #444;
        padding-bottom: 0.2em; }}
  h2 {{ font-size: 14pt; margin: 1.2em 0 0.4em; }}
  h3 {{ font-size: 12pt; margin: 1em 0 0.3em; }}
  p, li {{ margin: 0.3em 0; }}
  ul, ol {{ padding-left: 1.4em; }}
  img {{ max-width: 100%; height: auto; }}
  a {{ color: #1d4ed8; }}
  mark {{ padding: 0 2px; }}
  blockquote {{ border-left: 3px solid #cbd5e1; color: #475569;
                padding-left: 1em; margin: 0.6em 0; }}
  pre {{ background: #f1f5f9; padding: 0.75em 1em; border-radius: 4px;
         overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; margin: 0.6em 0; }}
  th, td {{ border: 1px solid #bbb; padding: 6px 8px; text-align: left;
            vertical-align: top; }}
  th {{ background: #f0f0f0; }}
{branding_css}
</style>
</head>
<body>
{watermark_html}
{body_html}
</body>
</html>"""


def _prepare_html_for_docx(html: str):
    """Make editor HTML safe for htmldocx, which cannot read base64 images.

    Data-URI ``<img>`` sources (e.g. an inserted company logo) are decoded and
    written to temp files; the ``src`` is rewritten to the file path so
    python-docx can embed them. Returns ``(html, [temp_paths])``; the caller
    must delete the temp files after the document is built.
    """
    temp_files: list[str] = []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return html, temp_files

    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src.startswith("data:"):
            continue
        try:
            header, b64 = src.split(",", 1)
            mime = header.split(";")[0].split(":")[1]
            ext = mime.split("/")[1] if "/" in mime else "png"
            if ext == "jpg":
                ext = "jpeg"
            data = base64.b64decode(b64)
            fd, path = tempfile.mkstemp(prefix="polimg_", suffix="." + ext, dir="/tmp")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            img["src"] = path
            temp_files.append(path)
        except Exception:
            img.decompose()
    return str(soup), temp_files


class PolicyBuilderViewSet(viewsets.ViewSet):
    """AI-assisted policy drafting, save-as-Policy, export, and provider config."""

    permission_classes = [IsAuthenticated]

    # -- Provider picker catalog (non-secret) --------------------------------
    @action(detail=False, methods=["get"], url_path="config")
    def config(self, request):
        """Which providers are configured + their model presets, for the UI."""
        return Response(provider_catalog(), status=status.HTTP_200_OK)

    # -- Admin: provider API keys --------------------------------------------
    @action(detail=False, methods=["get", "put"], url_path="settings")
    def provider_settings(self, request):
        """Read (masked) or update the AI provider settings. Admin only.

        Note: must NOT be named ``settings`` -- that shadows DRF's
        ``APIView.settings`` attribute and breaks request handling.
        """
        if not _is_ai_admin(request.user):
            return Response(
                {"detail": "Administrator access is required to manage AI providers."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if request.method == "GET":
            return Response(masked_ai_settings(), status=status.HTTP_200_OK)

        # PUT: accept a structured payload and map to managed fields. Only
        # fields explicitly present are changed, so omitting an api_key leaves
        # the stored key untouched (the masked GET never returns secrets).
        updates: dict[str, str] = {}
        payload_providers = request.data.get("providers") or {}
        if isinstance(payload_providers, dict):
            for pid, spec in PROVIDERS.items():
                conf = payload_providers.get(pid)
                if not isinstance(conf, dict):
                    continue
                if "api_key" in conf:
                    updates[spec["key_field"]] = conf.get("api_key") or ""
                if "base_url" in conf:
                    updates[spec["base_url_field"]] = conf.get("base_url") or ""

        if "default_provider" in request.data:
            updates["netlink_ai_default_provider"] = (
                request.data.get("default_provider") or ""
            )

        masked = save_ai_settings(updates)
        return Response(masked, status=status.HTTP_200_OK)

    # -- Company document template (letterhead / watermark) ------------------
    @action(detail=False, methods=["get", "put"], url_path="doc-template")
    def doc_template_settings(self, request):
        """Read (any user) or update (admin) the company export template.

        GET returns non-secret fields + flags so the editor can default the
        per-export toggle and show whether a .docx letterhead is uploaded. PUT
        accepts the text fields, the enable flag, and an optional base64 .docx
        (or ``remove_docx`` to clear it).
        """
        if request.method == "GET":
            return Response(
                doc_template.masked_template_settings(), status=status.HTTP_200_OK
            )

        if not _is_ai_admin(request.user):
            return Response(
                {"detail": "Administrator access is required to manage the template."},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data or {}
        updates: dict[str, str] = {}

        if "enabled" in data:
            updates[doc_template.ENABLED] = "true" if data.get("enabled") else ""
        for key, field in (
            ("company_name", doc_template.COMPANY),
            ("watermark_text", doc_template.WATERMARK),
            ("header_text", doc_template.HEADER),
            ("footer_text", doc_template.FOOTER),
        ):
            if key in data:
                updates[field] = (data.get(key) or "").strip()

        if data.get("remove_docx"):
            updates[doc_template.DOCX_B64] = ""
            updates[doc_template.DOCX_NAME] = ""
        elif data.get("docx_base64"):
            b64 = str(data.get("docx_base64") or "").strip()
            # Tolerate a data-URI prefix from the browser.
            if "," in b64 and b64.lower().startswith("data:"):
                b64 = b64.split(",", 1)[1]
            if not doc_template.validate_docx_b64(b64):
                return Response(
                    {"detail": "The uploaded file is not a valid .docx document."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            updates[doc_template.DOCX_B64] = b64
            updates[doc_template.DOCX_NAME] = (
                str(data.get("docx_name") or "template.docx").strip()[:200]
            )

        masked = doc_template.save_template_settings(updates)
        return Response(masked, status=status.HTTP_200_OK)

    # -- AI drafting (proposal only) -----------------------------------------
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
            industry=(request.data.get("industry") or "").strip(),
            framework=(request.data.get("framework") or "").strip(),
            extra=(request.data.get("additional_context") or "").strip(),
            provider=(request.data.get("provider") or "").strip(),
            model=(request.data.get("model") or "").strip(),
        )
        return Response(draft, status=status.HTTP_200_OK)

    # -- Export to DOCX / PDF ------------------------------------------------
    @action(detail=False, methods=["post"], url_path="export")
    def export(self, request):
        """Render the (edited) policy HTML to a downloadable DOCX or PDF.

        When ``apply_template`` is truthy, the configured company template
        (uploaded .docx for DOCX, or header/footer + watermark fields) is
        applied. Clients pass the per-export toggle so users can opt out.
        """
        fmt = (request.data.get("format") or "").strip().lower()
        body_html = request.data.get("html") or ""
        title = (request.data.get("title") or "policy").strip() or "policy"
        apply_template = bool(request.data.get("apply_template"))

        if fmt not in ("pdf", "docx"):
            return Response(
                {"detail": "format must be 'pdf' or 'docx'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not body_html.strip():
            return Response(
                {"detail": "html content is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tpl_settings = doc_template.get_template_settings() if apply_template else {}

        if fmt == "pdf":
            try:
                from weasyprint import HTML
            except Exception as e:
                logger.error("policy_export_pdf_unavailable", error=str(e))
                return Response(
                    {"detail": "PDF export is not available on this server."},
                    status=status.HTTP_501_NOT_IMPLEMENTED,
                )
            branding = doc_template.pdf_branding(tpl_settings) if apply_template else None
            pdf_bytes = HTML(string=_wrap_html(title, body_html, branding)).write_pdf()
            resp = HttpResponse(pdf_bytes, content_type="application/pdf")
            resp["Content-Disposition"] = (
                f'attachment; filename="{_safe_filename(title, "pdf")}"'
            )
            return resp

        # DOCX
        try:
            from docx import Document
            from htmldocx import HtmlToDocx
        except Exception as e:
            logger.error("policy_export_docx_unavailable", error=str(e))
            return Response(
                {"detail": "DOCX export is not available on this server."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        # Use the uploaded .docx letterhead as the base when configured;
        # otherwise start blank and apply field-based branding afterwards.
        base_doc = doc_template.open_base_document(tpl_settings) if apply_template else None
        document = base_doc or Document()
        prepared_html, temp_files = _prepare_html_for_docx(body_html)
        try:
            HtmlToDocx().add_html_to_document(prepared_html, document)
        finally:
            for path in temp_files:
                try:
                    os.remove(path)
                except OSError:
                    pass
        if apply_template and base_doc is None:
            doc_template.apply_docx_branding(document, tpl_settings)
        buffer = io.BytesIO()
        document.save(buffer)
        resp = HttpResponse(
            buffer.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        )
        resp["Content-Disposition"] = (
            f'attachment; filename="{_safe_filename(title, "docx")}"'
        )
        return resp

    # -- Save as a Policy in the register ------------------------------------
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
