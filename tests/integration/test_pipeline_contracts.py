"""Focused checks at the source-data and persisted-artifact boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from immuknow import preprocess
from immuknow.assignment_manifest import ManifestRow
from immuknow.generate_notices import prepare_render_jobs
import shutil
from immuknow.version_notices import load_catalog
from tests.fixtures import sample_input


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
def test_prepared_facts_survive_staged_json_round_trip(
    tmp_path: Path, default_vaccine_reference: dict
) -> None:
    df = sample_input.create_test_input_dataframe(num_clients=1)
    df["overdue_disease"] = ["Poliomyelitis - 12; Measles"]
    df["overdue_agent"] = ["IPV; MMR"]
    config = {"date_of_delivery": "2025-04-08"}

    result, _ = preprocess.build_preprocess_result(
        preprocess.clean_csv_text(df),
        default_vaccine_reference,
        [],
        config=config,
        config_dir=preprocess.CONFIG_DIR,
        catalog=catalog(),
        manifest=assigned_manifest(df, "fr"),
    )
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "immuknow/templates",
        tmp_path / "resources/templates",
    )
    job = prepare_render_jobs(result.clients, tmp_path, config)[0]
    payload = json.loads(job.data.read_text())
    client = result.clients[0]

    assert client.version_id == "overdue_agents_v1"
    assert client.language == "fr"
    assert client.overdue_diseases == [
        {"disease": "Polio", "dose": 12},
        {"disease": "Measles", "dose": None},
    ]
    assert client.overdue_agents == ["IPV", "MMR"]
    assert client.person["date_of_birth_iso"] == "2015-01-02"
    assert "date_of_birth" not in client.person
    assert payload["overdue_diseases"] == client.overdue_diseases
    assert payload["history"] == client.history
    assert payload["row_key"] == "row-000001"


@pytest.mark.integration
def test_school_mapping_from_selected_config_preserves_prepared_clients(
    tmp_path: Path, default_vaccine_reference: dict
) -> None:
    df = sample_input.create_test_input_dataframe(num_clients=2)
    df["school_id"] = ["0007", "0008"]
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

    assert warnings
    assert len(enriched) == len(df) == len(result.clients) == 2
    assert enriched.loc[0, "school_match_type"] == "inexact"
    assert result.clients[0].client_id == df.loc[0, "client_id"]
    assert result.clients[0].overdue_diseases
    assert "school_match_type" not in result.clients[0].metadata
    assert result.clients[1].school["id"] == "0008"
    assert enriched.loc[1, "school_match_type"] == "no_match"
    assert any(
        c.code == "data.school_match" and c.status == "fail"
        for c in result.row_checks["row-000002"]
    )


@pytest.mark.integration
@pytest.mark.parametrize("first_name", ["Alice", "   "])
def test_configuration_cannot_replace_the_packaged_input_contract(
    tmp_path: Path, first_name: str
) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree(preprocess.CONFIG_DIR, config_dir)
    (config_dir / "input_schema.json").write_text('{"fields": []}')
    frame = sample_input.create_test_input_dataframe(num_clients=1)
    frame["first_name"] = first_name
    source = tmp_path / "clients.csv"
    frame.to_csv(source, index=False)
    result, _ = preprocess.prepare_clients(
        preprocess.read_input(source),
        tmp_path / "output",
        {},
        config_dir,
        catalog(),
        {},
        ("overdue_diseases_v1", "en"),
    )
    assert len(result.clients) == 1
    assert result.clients[0].person["first_name"] == first_name.strip()
    if not first_name.strip():
        assert any(
            c.code == "source.first_name_missing"
            for c in result.row_checks["row-000001"]
        )
    # A missing required source column still fails under the packaged contract.
    frame.drop(columns="client_id").to_csv(source, index=False)
    with pytest.raises(ValueError, match="client_id"):
        preprocess.prepare_clients(
            preprocess.read_input(source),
            tmp_path / "output",
            {},
            config_dir,
            catalog(),
            {},
            ("overdue_diseases_v1", "en"),
        )
