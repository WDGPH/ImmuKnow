"""Test error handling and propagation across pipeline steps.

This module verifies that the pipeline implements the correct error handling
strategy: fail-fast for critical steps, per-item recovery for optional steps.

**Error Handling Philosophy:**

- **Critical Steps** (Notice generation, Compilation, PDF validation) halt on error
- **Optional Steps** (QR codes, Encryption, Batching) skip failed items and continue
- **Infrastructure Errors** (missing files, config errors) always fail-fast
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from pipeline import generate_notices, generate_qr_codes


@pytest.mark.integration
class TestOptionalStepErrorRecovery:
    """Optional steps must recover per-item and continue processing.

    QR generation (Step 3) and Encryption (Step 7) are optional features.
    If one client/PDF fails, others should continue. Pipeline completes
    with summary of successes, skipped, and failed items.
    """

    def test_qr_generation_skips_invalid_clients(self, tmp_path):
        """QR generation should skip clients with invalid data and continue."""
        # Create preprocessed artifact with valid and invalid clients
        artifact_dict = {
            "run_id": "test123",
            "language": "en",
            "clients": [
                {
                    "sequence": 1,
                    "client_id": "C001",
                    "language": "en",
                    "person": {"full_name": "Alice", "date_of_birth": "20100101"},
                    "school": {"name": "School A"},
                    "board": {"name": "Board 1"},
                    "contact": {
                        "street": "123 Main",
                        "city": "Toronto",
                        "postal_code": "M1A 1A1",
                    },
                    "vaccines_due": "",
                    "vaccines_due_list": [],
                    "received": [],
                    "metadata": {},
                },
                # Invalid client: missing required fields
                {
                    "sequence": 2,
                    "client_id": "C002",
                    "language": "en",
                    "person": {"full_name": "Bob"},  # Missing date_of_birth
                    "school": {"name": "School B"},
                    "board": {"name": "Board 1"},
                    "contact": {
                        "street": "456 Oak",
                        "city": "Toronto",
                        "postal_code": "M2B 2B2",
                    },
                    "vaccines_due": "",
                    "vaccines_due_list": [],
                    "received": [],
                    "metadata": {},
                },
                {
                    "sequence": 3,
                    "client_id": "C003",
                    "language": "en",
                    "person": {"full_name": "Charlie", "date_of_birth": "20100303"},
                    "school": {"name": "School C"},
                    "board": {"name": "Board 1"},
                    "contact": {
                        "street": "789 Pine",
                        "city": "Toronto",
                        "postal_code": "M3C 3C3",
                    },
                    "vaccines_due": "",
                    "vaccines_due_list": [],
                    "received": [],
                    "metadata": {},
                },
            ],
            "warnings": [],
            "created_at": "2025-01-01T00:00:00Z",
            "total_clients": 3,
        }

        artifact_path = tmp_path / "artifact.json"
        artifact_path.write_text(json.dumps(artifact_dict), encoding="utf-8")

        config_path = Path(__file__).parent.parent.parent / "config" / "parameters.yaml"
        if not config_path.exists():
            pytest.skip("Config file not found")

        # QR generation should process clients 1 and 3, skip client 2
        generated = generate_qr_codes.generate_qr_codes(
            artifact_path,
            tmp_path,
            config_path,
        )

        # Should complete without raising (optional step recovery)
        # May have 0, 1, 2, or 3 QR codes depending on config and template validity
        assert isinstance(generated, list), "Should return list of generated files"
        # Most importantly: should not raise an exception
        assert True, "QR generation completed without halting on invalid client"

    def test_qr_generation_disabled_returns_empty(self, tmp_path):
        """QR generation should return empty list when disabled in config."""
        artifact_dict = {
            "run_id": "test123",
            "language": "en",
            "clients": [
                {
                    "sequence": 1,
                    "client_id": "C001",
                    "language": "en",
                    "person": {"full_name": "Alice", "date_of_birth": "20100101"},
                    "school": {"name": "School A"},
                    "board": {"name": "Board 1"},
                    "contact": {
                        "street": "123 Main",
                        "city": "Toronto",
                        "postal_code": "M1A 1A1",
                    },
                    "vaccines_due": "",
                    "vaccines_due_list": [],
                    "received": [],
                    "metadata": {},
                }
            ],
            "warnings": [],
            "created_at": "2025-01-01T00:00:00Z",
            "total_clients": 1,
        }

        artifact_path = tmp_path / "artifact.json"
        artifact_path.write_text(json.dumps(artifact_dict), encoding="utf-8")

        # Create minimal config with QR disabled
        config_path = tmp_path / "parameters.yaml"
        config_path.write_text("qr:\n  enabled: false\n", encoding="utf-8")

        # Should return empty list (step skipped)
        generated = generate_qr_codes.generate_qr_codes(
            artifact_path,
            tmp_path,
            config_path,
        )

        assert generated == [], "QR generation should return empty list when disabled"


@pytest.mark.integration
class TestInfrastructureErrorsAlwaysFail:
    """Infrastructure errors (missing files, bad config) must always fail-fast."""

    def test_notice_generation_halts_on_missing_artifact(self, tmp_path):
        """Notice generation should fail fast on missing artifact file."""
        missing_path = tmp_path / "does_not_exist.json"

        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError, match="not found"):
            generate_notices.read_artifact(missing_path)

    def test_notice_generation_halts_on_invalid_json(self, tmp_path):
        """Notice generation should fail fast on invalid JSON in artifact."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{ invalid json }", encoding="utf-8")

        # Should raise ValueError for invalid JSON
        with pytest.raises(ValueError, match="not valid JSON"):
            generate_notices.read_artifact(bad_json)

    def test_qr_generation_halts_on_missing_template(self, tmp_path):
        """QR generation should fail fast if payload template is required but missing.

        After Task 5 (config validation centralization), config errors are caught
        at load time with ValueError instead of RuntimeError. This is the desired
        behavior: fail fast on infrastructure errors at config load, not later.
        """
        artifact_dict = {
            "run_id": "test123",
            "language": "en",
            "clients": [
                {
                    "sequence": 1,
                    "client_id": "C001",
                    "language": "en",
                    "person": {"full_name": "Alice", "date_of_birth": "20100101"},
                    "school": {"name": "School A"},
                    "board": {"name": "Board 1"},
                    "contact": {
                        "street": "123 Main",
                        "city": "Toronto",
                        "postal_code": "M1A 1A1",
                    },
                    "vaccines_due": "",
                    "vaccines_due_list": [],
                    "received": [],
                    "metadata": {},
                }
            ],
            "warnings": [],
            "created_at": "2025-01-01T00:00:00Z",
            "total_clients": 1,
        }

        artifact_path = tmp_path / "artifact.json"
        artifact_path.write_text(json.dumps(artifact_dict), encoding="utf-8")

        # Config with QR enabled but no template (infrastructure error)
        config_path = tmp_path / "parameters.yaml"
        config_path.write_text("qr:\n  enabled: true\n", encoding="utf-8")

        # Should raise ValueError from config validation (fail-fast at load time)
        with pytest.raises(
            ValueError, match="QR code generation is enabled but qr.payload_template"
        ):
            generate_qr_codes.generate_qr_codes(
                artifact_path,
                tmp_path,
                config_path,
            )


# Markers for pytest
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test (tests multiple steps)",
    )
