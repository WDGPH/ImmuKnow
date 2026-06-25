"""Unit tests for data_models module - core pipeline data structures.

Tests cover:
- ClientRecord integration with Language validation logic

Real-world significance:
- These immutable dataclasses enforce consistent data structure across pipeline
- Language field validation is critical for downstream localization
"""

from __future__ import annotations

import pytest

from pipeline import data_models
from pipeline.enums import Language


@pytest.mark.unit
class TestClientRecord:
    """Unit tests for ClientRecord dataclass."""

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
