"""Focused checks at the source-data and persisted-artifact boundary."""

from __future__ import annotations

import json
import shutil

import pandas as pd
from contextlib import nullcontext
from pathlib import Path

import pytest

from immuknow import preprocess
from immuknow.assignment_manifest import ManifestRow
from immuknow.data_models import ClientRecord
from immuknow.version_notices import load_catalog
from tests.fixtures import sample_input
from tests.integration.test_native_pipeline import (
    ROOT,
    prepare_cohort,
    run_cli,
    read_render_jobs,
)


def assigned_manifest(df, language: str) -> dict[str, ManifestRow]:
    return {
        client_id: ManifestRow(
            client_id=client_id,
            version_id="overdue_agents_v1",
            language=language,
            experiment_id=None,
            experiment_arm=None,
        )
        for client_id in df["client_id"]
    }


def catalog():
    selected = load_catalog(preprocess.CONFIG_DIR)
    assert selected is not None
    return selected


@pytest.mark.integration
def test_prepared_client_data_survive_artifact_round_trip(
    tmp_path: Path, default_vaccine_reference: dict
) -> None:
    df = sample_input.create_test_input_dataframe(num_clients=1)
    df["overdue_disease"] = ["Poliomyelitis - 12; Measles"]
    df["overdue_agent"] = ["IPV; MMR"]
    config = {
        "date_of_delivery": "2025-04-08",
        "preprocess": {"include_dose": False},
    }

    result, _ = preprocess.build_preprocess_result(
        preprocess.clean_csv_text(df),
        default_vaccine_reference,
        [],
        config=config,
        config_dir=preprocess.CONFIG_DIR,
        catalog=catalog(),
        manifest=assigned_manifest(df, "fr"),
    )
    path = preprocess.write_artifact(tmp_path, "prepared-clients", result)
    payload = json.loads(path.read_text(encoding="utf-8"))
    client = ClientRecord(**payload["clients"][0])

    assert client.version_id == "overdue_agents_v1"
    assert client.language == "fr"
    assert client.overdue_diseases == [
        {"disease": "Polio", "dose": 12},
        {"disease": "Measles", "dose": None},
    ]
    assert client.overdue_agents == ["IPV", "MMR"]
    assert client.person["date_of_birth_iso"] == "2015-01-02"
    assert "date_of_birth" not in client.person
    assert "vaccines_due_list" not in payload["clients"][0]


@pytest.mark.integration
def test_school_mapping_from_selected_config_preserves_prepared_clients(
    tmp_path: Path, default_vaccine_reference: dict
) -> None:
    df = sample_input.create_test_input_dataframe(num_clients=1)
    mapping = {"phus": {"Test PHU": {"TUNNEL ACADEMY": "001"}}}
    (tmp_path / "school_reference.json").write_text(
        json.dumps(mapping), encoding="utf-8"
    )
    config = {
        "school_validation": {
            "enabled": True,
            "reference_file": "school_reference.json",
            "target_phu": "Test PHU",
        }
    }

    enriched, warnings = preprocess.run_school_validation(
        preprocess.clean_csv_text(df), tmp_path, config=config, config_dir=tmp_path
    )
    result, _ = preprocess.build_preprocess_result(
        enriched,
        default_vaccine_reference,
        [],
        config=config,
        config_dir=preprocess.CONFIG_DIR,
        catalog=catalog(),
        manifest=assigned_manifest(enriched, "en"),
    )

    assert not warnings
    assert enriched.loc[0, "school_match_type"] == "inexact"
    assert result.clients[0].client_id == df.loc[0, "client_id"]
    assert result.clients[0].overdue_diseases
    assert "school_match_type" not in result.clients[0].metadata


@pytest.mark.integration
@pytest.mark.parametrize(
    ("configured", "authored", "succeeds"),
    [(True, "auto", False), (False, "true", False), (True, "false", True)],
)
def test_mixed_validity_is_checked_after_template_override(
    tmp_path: Path,
    configured: bool,
    authored: str,
    succeeds: bool,
) -> None:
    command, output, _ = prepare_cohort(tmp_path, show_validity_markers=configured)
    source = Path(command[3])
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame["imms_given"] = ["May 1, 2020 - DTaP - Valid", "Jun 15, 2021 - MMR"]
    frame.to_csv(source, index=False)
    templates = tmp_path / "templates"
    shutil.copytree(ROOT / "immuknow/templates", templates)
    for entry in templates.glob("overdue_agents_v1.*.typ"):
        entry.write_text(
            entry.read_text().replace(
                "#let history-show-validity = auto",
                f"#let history-show-validity = {authored}",
            )
        )
    command.extend(["--templates", str(templates)])
    result = run_cli(command, tmp_path)
    if succeeds:
        assert result.returncode == 0, result.stdout + result.stderr
        jobs = read_render_jobs(output / "artifacts")
        assert len(jobs) == 2
        assert all(
            json.loads(job.data.read_text())["validity_coverage"] == "mixed"
            for job in jobs
        )
    else:
        assert result.returncode == 1
        assert "mixed cohort validity coverage" in result.stdout + result.stderr
        assert not list((output / "metadata").glob("completion_*.json"))
        assert not list(output.rglob("*.zip"))


@pytest.mark.integration
@pytest.mark.parametrize("first_name", ["Alice", "   "])
def test_configuration_cannot_replace_the_packaged_input_contract(
    tmp_path: Path, first_name: str
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    # A deliberately permissive local descriptor must have no effect.
    (config_dir / "input_schema.json").write_text('{"fields": []}')
    frame = sample_input.create_test_input_dataframe(num_clients=1)
    frame["first_name"] = first_name
    source = tmp_path / "clients.csv"
    frame.to_csv(source, index=False)
    expected = (
        pytest.raises(ValueError, match="first_name")
        if not first_name.strip()
        else nullcontext()
    )
    with expected:
        result, _ = preprocess.prepare_clients(
            source,
            tmp_path / "output",
            {},
            config_dir,
            catalog(),
            {},
            ("overdue_diseases_v1", "en"),
        )
        assert result.clients[0].person["first_name"] == "Alice"
