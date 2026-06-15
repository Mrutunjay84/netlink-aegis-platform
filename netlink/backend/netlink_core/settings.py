"""
Netlink Aegis settings.

This is the Netlink edition settings module. It overlays the community
CISO Assistant settings (``ciso_assistant.settings``) instead of duplicating
them, so that upstream changes to the community settings are inherited
automatically and merges stay clean.

Launched via ``netlink/backend/manage.sh`` (or ``DJANGO_SETTINGS_MODULE=
netlink_core.settings``). The active ``ROOT_URLCONF`` remains
``ciso_assistant.urls``, which consumes the ``ROUTES`` / ``MODULES`` hooks
populated below.
"""

# Inherit the entire community configuration. BASE_DIR, database, storage,
# allauth, REST framework, logging, etc. all come from here unchanged.
from ciso_assistant.settings import *  # noqa: F401,F403
from ciso_assistant.settings import (
    INSTALLED_APPS,
    MODULES,
    ROUTES,
    SPECTACULAR_SETTINGS,
    logger,
)

logger.info("Launching Netlink Aegis")

# ---------------------------------------------------------------------------
# Extension hooks
# ---------------------------------------------------------------------------
# ``ROUTES``, ``MODULES``, ``MODULE_PATHS`` and ``FEATURE_FLAGS`` are imported
# (as the same dict objects) from the community settings via the star-import
# above. We mutate them in place so that ``backend/core/urls.py`` registers our
# viewsets / urlconfs.
MODULES["netlink_core"] = {
    "path": "",
    "module": "netlink_core.urls",
}

# AI Policy Builder. Registers PolicyBuilderViewSet on the community DRF router
# (see backend/core/urls.py), reachable under /api/netlink-policy-builder/. The
# viewset lives in the overlay app netlink_policies (copied into the image by
# netlink/backend/Dockerfile).
ROUTES["netlink-policy-builder"] = {
    "viewset": "netlink_policies.views.PolicyBuilderViewSet",
    "basename": "netlink-policy-builder",
}

# Audit Evidence Assistant. Registers AuditEvidenceViewSet on the community DRF
# router, reachable under /api/netlink-audit-evidence/. Shares the same overlay
# app (netlink_policies) and provider config as the Policy Builder.
ROUTES["netlink-audit-evidence"] = {
    "viewset": "netlink_policies.audit_views.AuditEvidenceViewSet",
    "basename": "netlink-audit-evidence",
}

# ---------------------------------------------------------------------------
# App registration
# ---------------------------------------------------------------------------
# Insert the Netlink overlay apps BEFORE the community apps so netlink_core's
# templates/ directory takes priority in the app-directories template loader
# (used for branded email / PDF template overrides in Phase 1).
INSTALLED_APPS = ["netlink_core", "netlink_policies", *INSTALLED_APPS]

# ---------------------------------------------------------------------------
# Branding (Phase 1) - settings-level overrides
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS["TITLE"] = "Netlink Aegis API - Experimental"
SPECTACULAR_SETTINGS["DESCRIPTION"] = (
    "Netlink Aegis - API Documentation for automating all your GRC needs"
)

# Allow larger JSON request bodies: the Policy Builder document template lets an
# admin upload a .docx letterhead, sent base64-encoded in a JSON PUT.
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024  # 15 MB

# Default sender address when none is configured via DEFAULT_FROM_EMAIL.
if not os.environ.get("DEFAULT_FROM_EMAIL"):
    DEFAULT_FROM_EMAIL = "noreply@netlink-aegis.local"

# Console email backend in mail-debug mode uses a branded noreply sender.
if MAIL_DEBUG:
    DEFAULT_FROM_EMAIL = "noreply@netlink-aegis.local"

logger.info(
    "Netlink Aegis startup information",
    feature_flags=FEATURE_FLAGS,
    module_paths=MODULE_PATHS,
)
