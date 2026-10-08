"""Focused checks at the source-data and persisted-artifact boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from immuknow import preprocess
from immuknow.data_models import ClientRecord
from tests.fixtures import sample_input


@pytest.mark.integration
def test_preprocessed_canonical_facts_survive_artifact_round_trip(
    tmp_path: Path, default_vaccine_reference: dict
) -> None:
    df = sample_input.create_test_input_dataframe(num_clients=1)
    df["overdue_disease"] = ["Poliomyelitis - 12; Measles"]
    df["overdue_agent"] = ["IPV; MMR"]
    config = {
        "date_notice_delivery": "2025-04-08",
        "preprocess": {"include_dose": False},
    }

    result, _ = preprocess.build_preprocess_result(
        df,
        "fr",
        default_vaccine_reference,
        [],
        config=config,
        config_dir=preprocess.CONFIG_DIR,
    )
    path = preprocess.write_artifact(tmp_path, "fr", "canonical", result)
    payload = json.loads(path.read_text(encoding="utf-8"))
    client = ClientRecord(**payload["clients"][0])

    assert client.version_id == "legacy_overdue_v1"
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
def test_phix_mapping_from_selected_config_preserves_canonical_cohort(
    tmp_path: Path, default_vaccine_reference: dict
) -> None:
    df = sample_input.create_test_input_dataframe(num_clients=1)
    mapping = {"phus": {"Test PHU": {"TUNNEL ACADEMY": "001"}}}
    (tmp_path / "phix_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")
    config = {
        "phix_validation": {
            "enabled": True,
            "mapping_file": "phix_mapping.json",
            "target_phu": "Test PHU",
        }
    }

    enriched, warnings = preprocess.run_phix_validation(
        preprocess.normalize_dataframe(df), tmp_path, config=config, config_dir=tmp_path
    )
    result, _ = preprocess.build_preprocess_result(
        enriched,
        "en",
        default_vaccine_reference,
        [],
        config=config,
        config_dir=preprocess.CONFIG_DIR,
    )

    assert not warnings
    assert enriched.loc[0, "phix_match_type"] == "inexact"
    assert result.clients[0].client_id == df.loc[0, "client_id"]
    assert result.clients[0].overdue_diseases
    assert "phix_match_type" not in result.clients[0].metadata


@pytest.mark.integration
def test_mixed_validity_with_markers_is_rejected(
    default_vaccine_reference: dict,
) -> None:
    df = sample_input.create_test_input_dataframe(num_clients=2)
    df["imms_given"] = [
        "May 1, 2020 - DTaP - Valid",
        "Jun 15, 2021 - MMR",
    ]

    with pytest.raises(
        ValueError, match="mix of records with and without validity indicators"
    ):
        preprocess.build_preprocess_result(
            df,
            "en",
            default_vaccine_reference,
            [],
            config={"preprocess": {"show_validity_markers": True}},
            config_dir=preprocess.CONFIG_DIR,
        )
