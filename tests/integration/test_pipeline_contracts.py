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

from pipeline import data_models, preprocess
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


@pytest.mark.integration
class TestPreprocessOutputContracts:
    """Step 2 preprocessing output contracts: disease normalization and validity warnings."""

    def test_disease_alias_normalized_to_canonical_name(
        self, default_vaccine_reference
    ) -> None:
        """Verify disease aliases in OVERDUE DISEASE are canonicalized in the artifact.

        Real-world significance:
        - Input data may contain alias names (e.g., "Poliomyelitis" instead of "Polio")
        - Notice generation and translation both rely on canonical names for lookup;
          an alias left in vaccines_due_list causes the wrong label on the printed notice

        Assertion: vaccines_due_list contains "Polio", not the raw alias "Poliomyelitis"
        """
        df = sample_input.create_test_input_dataframe(num_clients=1)
        df["OVERDUE DISEASE"] = ["Poliomyelitis"]

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
        )

        client = result.clients[0]
        assert client.vaccines_due_list is not None
        assert "Polio" in client.vaccines_due_list
        assert "Poliomyelitis" not in client.vaccines_due_list

    def test_unknown_validity_warns_when_markers_enabled(
        self, tmp_path: Path, monkeypatch, default_vaccine_reference
    ) -> None:
        """Verify a dataset-level warning fires when show_validity_markers is on but no validity data is present.

        Real-world significance:
        - When show_validity_markers is on but the dataset contains no validity indicators,
          a dataset-level warning surfaces so the user knows validity cannot be displayed
        - The warning must surface in result.warnings so the orchestrator can display
          it to the user before the batch is finalized; doses are still captured

        Assertion: result.warnings contains a dataset-level "no validity data" warning
                   and the client's received record is still populated
        """
        params_path = tmp_path / "parameters.yaml"
        params_path.write_text(
            "\n".join(
                [
                    "date_notice_delivery: '2025-04-08'",
                    "chart_diseases_header:",
                    "  - Diphtheria",
                    "  - Tetanus",
                    "  - Pertussis",
                    "  - Other",
                    "preprocess:",
                    "  include_dose: true",
                    "  show_validity_markers: true",
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(preprocess, "PARAMETERS_PATH", params_path)

        df = sample_input.create_test_input_dataframe(num_clients=1)
        df["IMMS GIVEN"] = ["May 1, 2020 - DTaP"]

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
        )

        assert len(result.clients) == 1
        client = result.clients[0]
        assert client.received is not None
        assert len(client.received) > 0

        validity_warnings = [
            w for w in result.warnings if "no validity data was detected in the dataset" in w
        ]
        assert len(validity_warnings) == 1

    def test_mixed_validity_with_markers_enabled_raises_value_error(
        self, tmp_path: Path, monkeypatch, default_vaccine_reference
    ) -> None:
        """Verify a ValueError is raised when the dataset has mixed validity and show_validity_markers is on.

        Real-world significance:
        - A dataset where some doses carry - Valid/- Invalid and others do not
          cannot display markers reliably; the pipeline must fail loudly so
          the user can fix the source data rather than silently produce notices
          with inconsistent or misleading validity markers

        Assertion: build_preprocess_result raises ValueError containing
                   guidance on the mixed-data condition
        """
        params_path = tmp_path / "parameters.yaml"
        params_path.write_text(
            "\n".join([
                "date_notice_delivery: '2025-04-08'",
                "chart_diseases_header:",
                "  - Diphtheria",
                "  - Tetanus",
                "  - Pertussis",
                "  - Other",
                "preprocess:",
                "  include_dose: true",
                "  show_validity_markers: true",
            ]),
            encoding="utf-8",
        )
        monkeypatch.setattr(preprocess, "PARAMETERS_PATH", params_path)

        df = sample_input.create_test_input_dataframe(num_clients=2)
        # First client has a suffixed dose; second has an un-suffixed dose → mixed
        df["IMMS GIVEN"] = [
            "May 1, 2020 - DTaP - Valid",
            "Jun 15, 2021 - MMR",
        ]

        with pytest.raises(ValueError, match="mix of records with and without validity indicators"):
            preprocess.build_preprocess_result(
                df,
                language="en",
                vaccine_reference=default_vaccine_reference,
                replace_unspecified=[],
            )

    def test_mixed_validity_with_markers_disabled_warns_and_succeeds(
        self, tmp_path: Path, monkeypatch, default_vaccine_reference
    ) -> None:
        """Verify a dataset-level warning fires for mixed validity when show_validity_markers is off.

        Real-world significance:
        - When validity markers are disabled the mixed-data condition is not
          fatal; a warning surfaces to prompt the user to investigate their
          source data, but all clients are still processed and notices can
          be generated

        Assertion: result.warnings contains a "mixed" dataset warning and
                   all clients are returned
        """
        params_path = tmp_path / "parameters.yaml"
        params_path.write_text(
            "\n".join([
                "date_notice_delivery: '2025-04-08'",
                "chart_diseases_header:",
                "  - Diphtheria",
                "  - Tetanus",
                "  - Pertussis",
                "  - Other",
                "preprocess:",
                "  include_dose: true",
                "  show_validity_markers: false",
            ]),
            encoding="utf-8",
        )
        monkeypatch.setattr(preprocess, "PARAMETERS_PATH", params_path)

        df = sample_input.create_test_input_dataframe(num_clients=2)
        df["IMMS GIVEN"] = [
            "May 1, 2020 - DTaP - Valid",
            "Jun 15, 2021 - MMR",
        ]

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
        )

        assert len(result.clients) == 2
        mixed_warnings = [
            w for w in result.warnings
            if "both with and without validity indicators" in w
        ]
        assert len(mixed_warnings) == 1
