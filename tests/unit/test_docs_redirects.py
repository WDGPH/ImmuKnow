"""Protect legacy documentation deep links during the hub migration."""

from pathlib import Path

import pytest

from tools.build_docs_redirects import HUB_ROOT, build_redirects


def test_redirect_artifact_retains_known_routes_without_building_a_manual(
    tmp_path: Path,
):
    site = tmp_path / "redirects"
    build_redirects(site)

    page = site / "user_guide/getting_started/index.html"
    assert HUB_ROOT + "user_guide/getting_started/" in page.read_text()
    generated = site / "user_guide/input_schema/index.html"
    assert HUB_ROOT + "user_guide/input_schema/" in generated.read_text()
    assert HUB_ROOT in (site / "index.html").read_text()
    assert (site / "404.html").is_file()
    assert (site / ".nojekyll").exists()
    assert not (site / "assets").exists()


def test_redirect_builder_refuses_to_replace_existing_files(tmp_path: Path):
    (tmp_path / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="new or empty directory"):
        build_redirects(tmp_path)
    assert (tmp_path / "keep.txt").read_text() == "keep"
