"""Factual payload structure and bounded authored-project staging."""

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from immuknow.generate_notices import (
    build_notice_data,
    prepare_render_jobs,
    reject_overlap,
)
from immuknow.render_payload import validate_render_payload
from tests.unit.test_preprocess import prepare, source_rows


@pytest.mark.unit
def test_staged_resources_and_facts_use_row_keys_not_client_ids(tmp_path: Path):
    prepared, _ = prepare(source_rows())
    client = prepared.clients[0]
    templates = tmp_path / "run/resources/templates"
    templates.mkdir(parents=True)
    (templates / "overdue_diseases_v1.fr.typ").write_text('#import "settings.typ": *')
    (templates / "settings.typ").write_text("// authored settings")
    jobs = prepare_render_jobs([client], tmp_path / "run", {})
    job = jobs[0]
    assert job.workspace == tmp_path / "run"
    assert (
        job.template == tmp_path / "run/resources/templates/overdue_diseases_v1.fr.typ"
    )
    assert job.data.name == "row-000001.json"
    assert job.pdf.name == "row-000001.pdf"
    payload = json.loads(job.data.read_text())
    validate_render_payload(payload)
    assert payload["client_data"]["province"] == "QC"
    assert not any((tmp_path / "run").glob("*manifest*"))
    for retired in (
        "received",
        "qr",
        "qr_url",
        "rendering_defaults",
        "include_dose",
        "chart_diseases",
    ):
        assert retired not in payload
    payload["qr_url"] = "retired"
    with pytest.raises(ValidationError):
        validate_render_payload(payload)


@pytest.mark.unit
def test_payload_is_structural_and_keeps_unknown_age():
    frame = source_rows()
    frame.loc[1, "imms_given"] = ""
    prepared, _ = prepare(frame)
    from dataclasses import replace

    client = replace(prepared.clients[1], version_id="custom", language="en")
    payload = build_notice_data(client, {})
    validate_render_payload(payload)
    assert payload["client_data"]["age"] is None
    assert payload["client_data"]["over_16"] is None
    assert "unparsed_history" not in payload
    payload["history"] = [{"date_given": "not a date"}]
    with pytest.raises(ValidationError):
        validate_render_payload(payload)


def test_bad_history_cannot_be_passed_to_rendering_directly():
    prepared, _ = prepare(source_rows())
    with pytest.raises(ValueError, match="History contains invalid fragments"):
        build_notice_data(prepared.clients[1], {})


@pytest.mark.unit
def test_overlap_resolution_catches_symlink_and_both_ancestor_directions(
    tmp_path: Path,
):
    source = tmp_path / "source"
    source.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    for destination in (source, source / "child", alias / "child"):
        with pytest.raises(ValueError, match="overlaps output workspace"):
            reject_overlap(source, destination)
        with pytest.raises(ValueError, match="overlaps output workspace"):
            reject_overlap(destination, source)
