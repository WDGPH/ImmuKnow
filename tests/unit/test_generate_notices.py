"""Expected-output accounting and safe native workspace preparation."""

from __future__ import annotations

from pathlib import Path

import pytest

from immuknow import generate_notices
from immuknow.compile_notices import check_expected_notices
from immuknow.data_models import RenderJob
from tests.fixtures.sample_input import create_test_artifact_payload


@pytest.mark.unit
def test_render_jobs_reject_duplicate_expected_pdf(tmp_path: Path) -> None:
    """One output path cannot stand in for two expected client notices."""
    clients = create_test_artifact_payload(num_clients=2).clients
    jobs = [
        RenderJob(
            sequence=client.sequence,
            client_id=client.client_id,
            version_id=client.version_id,
            language=client.language,
            workspace=tmp_path,
            template=tmp_path / "template.typ",
            data=tmp_path / f"{client.sequence}.json",
            pdf=tmp_path / "same.pdf",
        )
        for client in clients
    ]
    with pytest.raises(ValueError, match="prepared client list exactly once"):
        check_expected_notices(clients, jobs)


@pytest.mark.unit
def test_workspace_overlap_is_rejected_before_deletion(tmp_path: Path) -> None:
    """A selected source inside the output cannot be removed by workspace cleanup."""
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    source = artifact_dir / "render" / "templates"
    source.mkdir(parents=True)
    sentinel = source / "keep.typ"
    sentinel.write_text("preserve")
    manifest = artifact_dir / "render_jobs.json"
    manifest.write_text("preserve")
    config_dir = tmp_path / "configuration"
    config_dir.mkdir()

    with pytest.raises(ValueError, match="overlaps output workspace"):
        generate_notices.prepare_render_jobs(
            [],
            artifact_dir,
            source,
            {"date_data_cutoff": "2025-08-31"},
            config_dir,
            "run-1",
        )
    assert sentinel.read_text() == "preserve"
    assert manifest.read_text() == "preserve"


@pytest.mark.unit
def test_overlap_resolution_catches_symlink_and_both_ancestor_directions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    for destination in (source, source / "child", alias / "child"):
        with pytest.raises(ValueError, match="overlaps output workspace"):
            generate_notices.reject_overlap(source, destination)
        with pytest.raises(ValueError, match="overlaps output workspace"):
            generate_notices.reject_overlap(destination, source)


@pytest.mark.unit
def test_nested_template_link_cannot_copy_the_workspace_into_itself(
    tmp_path: Path,
) -> None:
    """Copying a source-tree link must not recurse into a newly created render root."""
    templates = tmp_path / "templates"
    templates.mkdir()
    artifact_dir = tmp_path / "artifacts"
    workspace = artifact_dir / "render"
    workspace.mkdir(parents=True)
    sentinel = workspace / "keep"
    sentinel.write_text("preserve")
    (templates / "nested").symlink_to(workspace, target_is_directory=True)
    with pytest.raises(ValueError, match="overlaps output workspace"):
        generate_notices.prepare_render_jobs(
            [], artifact_dir, templates, {}, tmp_path / "config", "run"
        )
    assert sentinel.read_text() == "preserve"


@pytest.mark.unit
@pytest.mark.parametrize("language", [None, "EN", "Fr", "", "es"])
def test_template_selection_requires_explicit_lowercase_language(
    tmp_path: Path, language
) -> None:
    # Even an existing filename cannot bypass the notice-language contract.
    (tmp_path / f"overdue_diseases_v1.{language}.typ").touch()
    with pytest.raises(ValueError, match="Unsupported language"):
        generate_notices.select_template(tmp_path, "overdue_diseases_v1", language)
