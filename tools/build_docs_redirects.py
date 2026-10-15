"""Build only redirects for the retired ImmuKnow documentation site."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

HUB_ROOT = "https://wdgph.github.io/docs/immuknow/latest/"
LEGACY_ROOT = "/ImmuKnow/"

# Published source: 195918b7f8453c61c038a66a434d810414f859a2
# Retain these old paths when source pages change.
LEGACY_PATHS = (
    "",
    "developer_guide/code_analysis/",
    "developer_guide/contributing/",
    "developer_guide/documentation/",
    "developer_guide/testing/",
    "reference/api/",
    "reference/architecture/",
    "user_guide/configuration/",
    "user_guide/email_package/",
    "user_guide/email_package/email_template_text/",
    "user_guide/email_package/phu_checklist/",
    "user_guide/email_package/template_overview/",
    "user_guide/getting_started/",
    "user_guide/input_schema/",
    "user_guide/pdf_validation/",
    "user_guide/phu_templates/",
)


def redirect_page(page_path: str) -> str:
    """Keep deep links, queries and fragments, including previously published pages."""
    fallback = HUB_ROOT + page_path
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>ImmuKnow documentation has moved</title>
<link rel="canonical" href="{html.escape(fallback, quote=True)}">
<script>
const root = {json.dumps(HUB_ROOT)};
const legacyRoot = {json.dumps(LEGACY_ROOT)};
const path = window.location.pathname;
const relative = path === legacyRoot.slice(0, -1) ? "" :
  path.startsWith(legacyRoot) ? path.slice(legacyRoot.length).replace(/^\\/+/, "") :
  {json.dumps(page_path)};
window.location.replace(root + relative + window.location.search + window.location.hash);
</script>
</head>
<body>
<p>ImmuKnow documentation has moved to the shared documentation hub.</p>
<p><a href="{html.escape(fallback, quote=True)}">Continue to the documentation</a></p>
</body>
</html>
"""


def build_redirects(site: Path) -> None:
    """Write a redirect-only artifact without replacing an existing manual or files."""
    if site.exists() and any(site.iterdir()):
        raise ValueError(f"Use a new or empty directory for redirects: {site}")
    site.mkdir(parents=True, exist_ok=True)
    for relative in LEGACY_PATHS:
        target = site / relative / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(redirect_page(relative), encoding="utf-8")
    (site / "404.html").write_text(redirect_page(""), encoding="utf-8")
    (site / ".nojekyll").touch()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "site", type=Path, help="A new or empty redirect output directory"
    )
    args = parser.parse_args()
    build_redirects(args.site)


if __name__ == "__main__":
    main()
