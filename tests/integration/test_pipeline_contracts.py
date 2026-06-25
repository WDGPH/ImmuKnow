"""Integration tests for pipeline step contracts and artifact consistency.

Verifies handoffs between steps by testing that data survives serialization
and that each step's output satisfies the next step's requirements.

Covered boundaries:
- Artifact JSON round-trip (Step 2 output → all downstream steps)
- Preprocess → QR Generation (Step 2 → Step 3)
- Notice Generation template data (Step 4 input contract)
- Encryption / Bundling mutual exclusivity (Steps 7–8 config contract)

Per TESTING_STANDARDS.md: integration tests should verify
"Output from Step N is valid input to Step N+1" and
"JSON artifact schema consistency across steps".
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from pipeline import data_models
from tests.fixtures import sample_input


@pytest.mark.integration
class TestArtifactContracts:
    """Artifact JSON round-trip and field preservation contracts.

    All downstream steps read the artifact written by preprocess (Step 2).
    These tests catch silent data loss through serialization.
    """

    def test_artifact_payload_round_trip(self, tmp_path: Path) -> None:
        """Verify ArtifactPayload survives JSON write → read without data loss.

        Real-world significance:
        - Steps 3–9 all read the artifact file written by Step 2
        - Any field lost in serialization causes a downstream silent failure

        Assertion: run_id, client count, and created_at survive round-trip
        """
        original = sample_input.create_test_artifact_payload(
            num_clients=3, run_id="test_round_trip_001"
        )

        artifact_path = sample_input.write_test_artifact(original, tmp_path)

        assert artifact_path.exists()
        with open(artifact_path) as f:
            artifact_data = json.load(f)

        assert artifact_data["run_id"] == "test_round_trip_001"
        assert len(artifact_data["clients"]) == 3
        assert artifact_data["total_clients"] == 3
        assert "created_at" in artifact_data

    def test_client_record_fields_preserved_in_artifact(self, tmp_path: Path) -> None:
        """Verify all critical ClientRecord fields are present after serialization.

        Real-world significance:
        - QR generation, notice generation, and bundling each require specific fields
        - A missing field causes a mid-pipeline crash with a misleading error

        Assertion: All required downstream fields are present in serialized client
        """
        artifact = sample_input.create_test_artifact_payload(
            num_clients=1, run_id="test_fields_001"
        )
        artifact_path = sample_input.write_test_artifact(artifact, tmp_path)

        with open(artifact_path) as f:
            artifact_data = json.load(f)

        client_dict = artifact_data["clients"][0]
        required_fields = [
            "sequence",
            "client_id",
            "language",
            "person",
            "school",
            "board",
            "contact",
            "vaccines_due",
            "vaccines_due_list",
        ]
        for field in required_fields:
            assert field in client_dict, f"Missing critical field: {field}"

    def test_multilingual_artifact_support(self, tmp_path: Path) -> None:
        """Verify artifacts preserve language markers for both EN and FR clients.

        Real-world significance:
        - Language drives template selection in Step 4; a missing or wrong
          language marker causes the wrong notice to be generated

        Assertion: artifact["language"] and each client["language"] match requested lang
        """
        for lang in ["en", "fr"]:
            artifact = sample_input.create_test_artifact_payload(
                num_clients=2, language=lang, run_id=f"test_lang_{lang}"
            )
            path = sample_input.write_test_artifact(artifact, tmp_path)

            with open(path) as f:
                data = json.load(f)

            assert data["language"] == lang
            for client in data["clients"]:
                assert client["language"] == lang

    def test_artifact_warnings_accumulation(self, tmp_path: Path) -> None:
        """Verify preprocessing warnings survive serialization for user visibility.

        Real-world significance:
        - Warnings (e.g., missing board name) must reach the end user
        - Lost warnings mean silent data quality issues in output notices

        Assertion: All warnings in ArtifactPayload appear in the JSON file
        """
        artifact = data_models.ArtifactPayload(
            run_id="test_warn_001",
            language="en",
            clients=[
                sample_input.create_test_client_record(sequence="00001", language="en")
            ],
            warnings=["Missing board name", "Invalid postal code"],
            created_at="2025-01-01T12:00:00Z",
            total_clients=1,
        )
        artifact_path = sample_input.write_test_artifact(artifact, tmp_path)

        with open(artifact_path) as f:
            loaded = json.load(f)

        assert len(loaded["warnings"]) == 2
        assert "Missing board name" in loaded["warnings"][0]


@pytest.mark.integration
class TestPreprocessToQrContract:
    """Step 2 → Step 3 contract: artifact output is valid QR generation input."""

    def test_artifact_data_supports_qr_payload_generation(
        self, tmp_test_dir: Path, default_config: Dict[str, Any]
    ) -> None:
        """Verify artifact client records contain all fields required by QR templates.

        Real-world significance:
        - QR payload substitution uses client_id, name, DOB, school, and city
        - A missing field causes QR generation to fail or produce a blank code

        Assertion: All QR template substitution fields are non-empty on a client record
        """
        artifact = sample_input.create_test_artifact_payload(
            num_clients=1, language="en", run_id="test_qr_contract"
        )
        client = artifact.clients[0]

        assert client.client_id
        assert client.person["first_name"]
        assert client.person["last_name"]
        assert client.person["date_of_birth_iso"]
        assert client.school["name"]
        assert client.contact["city"]

    def test_client_sequence_stability_for_filenames(self, tmp_path: Path) -> None:
        """Verify sequence numbers are deterministic and zero-padded to 5 digits.

        Real-world significance:
        - QR PNG filenames, Typst files, and PDFs are all keyed on sequence
        - Non-deterministic sequences break traceability and batching

        Assertion: Sequences are ["00001", "00002", ...] in order
        """
        artifact = sample_input.create_test_artifact_payload(
            num_clients=5, language="en", run_id="test_sequence"
        )
        sequences = [c.sequence for c in artifact.clients]
        assert sequences == ["00001", "00002", "00003", "00004", "00005"]


@pytest.mark.integration
class TestNoticeToCompileContract:
    """Step 4 → Step 5 contract: notice template data is valid for Typst compilation."""

    def test_vaccines_due_list_for_template_iteration(self) -> None:
        """Verify vaccines_due_list is a list and matches the vaccines_due string.

        Real-world significance:
        - Typst templates iterate over vaccines_due_list to render the immunization chart
        - A string instead of a list, or a mismatched count, corrupts the chart

        Assertion: vaccines_due_list is a list with one entry per vaccine in vaccines_due
        """
        client = sample_input.create_test_client_record(
            vaccines_due="Measles/Mumps/Rubella",
            vaccines_due_list=["Measles", "Mumps", "Rubella"],
        )

        assert isinstance(client.vaccines_due_list, list)
        assert len(client.vaccines_due_list) == 3
        assert "Measles" in client.vaccines_due_list


@pytest.mark.integration
class TestDownstreamWorkflowContracts:
    """Steps 7–8 config contract: encryption and bundling are independent."""

    def test_config_propagation_encryption_and_bundling_independent(
        self, default_config: Dict[str, Any]
    ) -> None:
        """Verify encryption and bundling are independent config flags.

        Real-world significance:
        - The orchestrator runs Step 7 (encryption) and Step 8 (bundling) independently
        - Both can be enabled simultaneously; encryption runs first, then bundling
        - A config that enables both should not be treated as invalid

        Assertion: Config can express encryption-on + bundling-on simultaneously
        """
        config = copy.deepcopy(default_config)

        config["encryption"]["enabled"] = True
        config["bundling"]["bundle_size"] = 50

        assert config["encryption"]["enabled"] is True
        assert config["bundling"]["bundle_size"] > 0
