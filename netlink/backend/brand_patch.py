#!/usr/bin/env python3
"""
Netlink Aegis - build-time backend white-label patch.

Runs against a *copy* of the community backend tree inside the Docker image
(``/code``), never the committed community source, so it is safe to re-run
after every upstream merge.

It rebrands the "CISO Assistant" phrase in the text of email templates
(YAML + HTML) and PDF templates. These are loaded by a hardcoded filesystem
path / Django template loader rather than from settings, so they cannot be
rebranded via ``netlink_core.settings`` alone.

Hosted asset URLs (e.g. ``https://intuitem.com/ciso-assistant.png`` and
``https://intuitem.com/``) are intentionally left untouched so the emails keep
working; only the human-readable brand phrase is replaced.

Usage: ``python brand_patch.py [CODE_ROOT]``  (default CODE_ROOT=/code)
"""
import sys
from pathlib import Path

BRAND_NEW = "Netlink Aegis"
# Case-sensitive, hyphen/space variants. Deliberately does NOT match the
# lowercase "ciso-assistant" used in asset URLs.
REPLACEMENTS = [
    ("CISO Assistant", BRAND_NEW),
    ("CISO-Assistant", BRAND_NEW),
]

# (relative directory, glob) pairs of text templates to rebrand.
TARGETS = [
    ("core/templates/emails", "**/*.yaml"),
    ("core/templates/registration", "*.html"),
    ("core/templates/tprm", "*.html"),
    ("doc_management/templates/doc_management", "*.html"),
]


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/code")
    print(f"[backend-brand-patch] root: {root}")
    changed = 0
    scanned = 0
    for subdir, pattern in TARGETS:
        base = root / subdir
        if not base.exists():
            print(f"[backend-brand-patch] target dir missing: {subdir}")
            continue
        for path in base.glob(pattern):
            if not path.is_file():
                continue
            scanned += 1
            original = path.read_text(encoding="utf-8")
            patched = original
            for old, new in REPLACEMENTS:
                patched = patched.replace(old, new)
            if patched != original:
                path.write_text(patched, encoding="utf-8")
                changed += 1
    print(f"[backend-brand-patch] scanned {scanned} file(s), rebranded {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
