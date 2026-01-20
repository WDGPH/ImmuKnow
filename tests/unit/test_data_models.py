"""Unit tests for data_models module - core pipeline data structures.

Tests cover:
- ClientRecord dataclass structure and serialization
- PreprocessResult aggregation
- ArtifactPayload metadata and schema
- PdfRecord for compiled notice tracking

Real-world significance:
- These immutable dataclasses enforce consistent data structure across pipeline
- Type hints and frozen dataclasses prevent bugs from data corruption
- Schema must remain stable for artifacts to be shareable between pipeline runs
"""

from __future__ import annotations

import pytest

from pipeline import data_models
from pipeline.enums import Language


@pytest.mark.unit
class TestClientRecord:
    """Unit tests for ClientRecord dataclass."""

    def test_client_record_creation(self) -> None:
        """Verify ClientRecord can be created with all required fields.

        Real-world significance:
        - ClientRecord is the core data structure for each student notice
        """
        client = data_models.ClientRecord(
            sequence="00001",
            client_id="C00001",
            language="en",
            person={"first_name": "Alice", "last_name": "Zephyr", "over_16": False},
            school={"name": "Tunnel Academy"},
            board={"name": "Guelph Board"},
            contact={"street": "123 Main St"},
            vaccines_due="Measles/Mumps/Rubella",
            vaccines_due_list=["Measles", "Mumps", "Rubella"],
            received=[],
            metadata={},
        )

        assert client.sequence == "00001"
        assert client.client_id == "C00001"
        assert client.language == "en"

    def test_client_record_is_frozen(self) -> None:
        """Verify ClientRecord is immutable (frozen).

        Real-world significance:
        - Prevents accidental modification of client data after preprocessing
        - Ensures data integrity through pipeline
        """
        client = data_models.ClientRecord(
            sequence="00001",
            client_id="C00001",
            language="en",
            person={},
            school={},
            board={},
            contact={},
            vaccines_due=None,
            vaccines_due_list=None,
            received=None,
            metadata={},
        )

        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            client.sequence = "00002"  # type: ignore[misc]

    def test_client_record_optional_qr_field(self) -> None:
        """Verify ClientRecord has optional qr field.

        Real-world significance:
        - QR code added in Step 2, may be None before then
        """
        client = data_models.ClientRecord(
            sequence="00001",
            client_id="C00001",
            language="en",
            person={},
            school={},
            board={},
            contact={},
            vaccines_due=None,
            vaccines_due_list=None,
            received=None,
            metadata={},
            qr=None,
        )

        assert client.qr is None

        client_with_qr = data_models.ClientRecord(
            sequence="00001",
            client_id="C00001",
            language="en",
            person={},
            school={},
            board={},
            contact={},
            vaccines_due=None,
            vaccines_due_list=None,
            received=None,
            metadata={},
            qr={"payload": "test_payload", "filename": "test.png"},
        )

        assert client_with_qr.qr is not None
        assert client_with_qr.qr["payload"] == "test_payload"

    def test_client_record_language_must_be_valid_enum_value(self) -> None:
        """Verify ClientRecord language must be a valid Language enum value.

        Real-world significance:
        - Language field should contain ISO 639-1 codes validated against
          Language enum. All downstream functions assume language is valid.
        """
        # Valid English language code
        client_en = data_models.ClientRecord(
            sequence="00001",
            client_id="C00001",
            language=Language.ENGLISH.value,  # 'en'
            person={},
            school={},
            board={},
            contact={},
            vaccines_due=None,
            vaccines_due_list=None,
            received=None,
            metadata={},
        )
        assert client_en.language == "en"
        assert Language.from_string(client_en.language) == Language.ENGLISH

        # Valid French language code
        client_fr = data_models.ClientRecord(
            sequence="00002",
            client_id="C00002",
            language=Language.FRENCH.value,  # 'fr'
            person={},
            school={},
            board={},
            contact={},
            vaccines_due=None,
            vaccines_due_list=None,
            received=None,
            metadata={},
        )
        assert client_fr.language == "fr"
        assert Language.from_string(client_fr.language) == Language.FRENCH

    def test_client_record_invalid_language_rejected_by_enum_validation(
        self,
    ) -> None:
        """Verify invalid language codes are caught by Language.from_string().

        Real-world significance:
        - Invalid language codes should never reach ClientRecord. They must be
          caught during preprocessing or config loading and validated using
          Language.from_string(), which provides clear error messages.
        """
        # This test demonstrates the validation at entry point, not in the dataclass
        # (dataclass accepts any string, but Language.from_string() validates it)

        # Invalid language 'es' should raise ValueError when validated
        with pytest.raises(ValueError, match="Unsupported language: es"):
            Language.from_string("es")

        # Create a ClientRecord with invalid language (for testing purposes)
        # This should NOT happen in production; Language.from_string() catches it first
        client_invalid = data_models.ClientRecord(
            sequence="00003",
            client_id="C00003",
            language="es",  # Invalid - will fail if passed to Language.from_string()
            person={},
            school={},
            board={},
            contact={},
            vaccines_due=None,
            vaccines_due_list=None,
            received=None,
            metadata={},
        )

        # Verify that attempting to validate this language raises error
        with pytest.raises(ValueError, match="Unsupported language: es"):
            Language.from_string(client_invalid.language)


@pytest.mark.unit
class TestPreprocessResult:
    """Unit tests for PreprocessResult dataclass."""

    def test_preprocess_result_creation(self) -> None:
        """Verify PreprocessResult aggregates clients and warnings.

        Real-world significance:
        - Output of Step 1 (Preprocess), input to Steps 2-3
        """
        clients = [
            data_models.ClientRecord(
                sequence="00001",
                client_id="C00001",
                language="en",
                person={},
                school={},
                board={},
                contact={},
                vaccines_due=None,
                vaccines_due_list=None,
                received=None,
                metadata={},
            )
        ]

        result = data_models.PreprocessResult(
            clients=clients,
            warnings=["Warning 1"],
        )

        assert len(result.clients) == 1
        assert len(result.warnings) == 1

    def test_preprocess_result_empty_warnings(self) -> None:
        """Verify PreprocessResult works with no warnings.

        Real-world significance:
        - Clean input should have empty warnings list
        """
        result = data_models.PreprocessResult(
            clients=[],
            warnings=[],
        )

        assert result.warnings == []


@pytest.mark.unit
class TestArtifactPayload:
    """Unit tests for ArtifactPayload dataclass."""

    def test_artifact_payload_creation(self) -> None:
        """Verify ArtifactPayload stores metadata and clients.

        Real-world significance:
        - Artifacts are JSON files with client data and metadata
        - Must include run_id for comparing pipeline runs
        """
        clients = []
        payload = data_models.ArtifactPayload(
            run_id="test_run_001",
            language="en",
            clients=clients,
            warnings=[],
            created_at="2025-01-01T12:00:00Z",
            input_file="test.xlsx",
            total_clients=0,
        )

        assert payload.run_id == "test_run_001"
        assert payload.language == "en"
        assert payload.total_clients == 0

    def test_artifact_payload_optional_input_file(self) -> None:
        """Verify ArtifactPayload has optional input_file field.

        Real-world significance:
        - Not all artifacts know their source file
        """
        payload_with_file = data_models.ArtifactPayload(
            run_id="test_run_001",
            language="en",
            clients=[],
            warnings=[],
            created_at="2025-01-01T12:00:00Z",
            input_file="input.xlsx",
        )

        assert payload_with_file.input_file == "input.xlsx"


@pytest.mark.unit
class TestPdfRecord:
    """Unit tests for PdfRecord dataclass."""

    def test_pdf_record_creation(self, tmp_path) -> None:
        """Verify PdfRecord tracks compiled PDF metadata.

        Real-world significance:
        - Used in Step 6 (Count PDFs) to verify all notices compiled
        """
        pdf_path = tmp_path / "00001_C00001.pdf"

        record = data_models.PdfRecord(
            sequence="00001",
            client_id="C00001",
            pdf_path=pdf_path,
            page_count=1,
            client={"first_name": "Alice"},
        )

        assert record.sequence == "00001"
        assert record.client_id == "C00001"
        assert record.page_count == 1
