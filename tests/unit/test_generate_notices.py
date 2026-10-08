"""Artifact reading errors before native render job preparation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import generate_notices


@pytest.mark.unit
class TestReadArtifact:
    """Unit tests for read_artifact function."""

    def test_read_artifact_with_valid_json(self, tmp_test_dir: Path) -> None:
        """Verify artifact is read and deserialized correctly.

        Real-world significance:
        - Must load artifact JSON from preprocessing step
        - Should parse all client records with required fields
        """
        artifact_data = {
            "run_id": "test_001",
            "language": "en",
            "total_clients": 1,
            "warnings": [],
            "created_at": "2025-01-01T12:00:00Z",
            "clients": [
                {
                    "sequence": "00001",
                    "client_id": "C001",
                    "language": "en",
                    "person": {
                        "first_name": "John",
                        "last_name": "Doe",
                        "date_of_birth": "2015-01-01",
                        "date_of_birth_display": "Jan 01, 2015",
                        "date_of_birth_iso": "2015-01-01",
                    },
                    "school": {"name": "Test School"},
                    "board": {"name": "Test Board"},
                    "contact": {
                        "street": "123 Main St",
                        "city": "Toronto",
                        "province": "ON",
                        "postal_code": "M1A1A1",
                    },
                    "vaccines_due": "Measles",
                    "vaccines_due_list": ["Measles"],
                    "received": [],
                    "metadata": {},
                }
            ],
        }
        artifact_path = tmp_test_dir / "artifact.json"
        artifact_path.write_text(json.dumps(artifact_data))

        payload = generate_notices.read_artifact(artifact_path)

        assert payload.run_id == "test_001"
        assert payload.language == "en"
        assert len(payload.clients) == 1
        assert payload.clients[0].client_id == "C001"
        assert payload.clients[0].person.get("first_name") == "John"
        assert payload.clients[0].person.get("last_name") == "Doe"

    def test_read_artifact_missing_file_raises_error(self, tmp_test_dir: Path) -> None:
        """Verify error when artifact file doesn't exist.

        Real-world significance:
        - Artifact should exist from preprocessing step
        - Missing file indicates pipeline failure
        """
        with pytest.raises(FileNotFoundError):
            generate_notices.read_artifact(tmp_test_dir / "nonexistent.json")

    def test_read_artifact_invalid_json_raises_error(self, tmp_test_dir: Path) -> None:
        """Verify error when JSON is invalid.

        Real-world significance:
        - Corrupted artifact from preprocessing indicates pipeline failure
        - Must fail early with clear error
        """
        artifact_path = tmp_test_dir / "bad.json"
        artifact_path.write_text("not valid json {{{")

        with pytest.raises(ValueError, match="Preprocessed artifact is not valid JSON"):
            generate_notices.read_artifact(artifact_path)


@pytest.mark.unit
def test_render_jobs_reject_duplicate_expected_pdf(tmp_path: Path) -> None:
    """One output path cannot stand in for two expected client notices."""
    job = {
        "sequence": "00001",
        "client_id": "A",
        "language": "en",
        "version_id": "overdue_standard_v1",
        "workspace": str(tmp_path),
        "template": str(tmp_path / "template.typ"),
        "data": str(tmp_path / "notice.json"),
        "pdf": str(tmp_path / "notice.pdf"),
    }
    other = {**job, "sequence": "00002", "client_id": "B"}
    (tmp_path / "render_jobs.json").write_text(
        json.dumps({"run_id": "test", "total_clients": 2, "jobs": [job, other]})
    )

    with pytest.raises(ValueError, match="every expected notice exactly once"):
        generate_notices.read_render_jobs(tmp_path)
