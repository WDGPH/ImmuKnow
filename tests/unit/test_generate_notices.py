"""Unit tests for generate_notices module - notice generation from templates.

Tests cover:
- Template variable substitution
- Language-specific content handling (English and French)
- Data escaping for Typst syntax
- Error handling for missing data/files
- QR code reference integration

Real-world significance:
- Step 4 of pipeline: generates Typst template files for each client
- Template content directly appears in compiled PDF notices
- Language correctness is critical for bilingual support (en/fr)
- Must properly escape special characters for Typst syntax
"""

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

        with pytest.raises(Exception):  # json.JSONDecodeError or similar
            generate_notices.read_artifact(artifact_path)


# ---------------------------------------------------------------------------
# build_template_registry (manifest mode)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# generate_typst_files — manifest mode branch
# ---------------------------------------------------------------------------
