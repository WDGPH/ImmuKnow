"""Unit tests for utils module - shared utility functions.

Tests cover:
- Template field extraction and validation
- Template formatting with placeholder substitution
- Client context building from nested data structures
- String conversion and None/NaN handling
- Error handling for invalid templates and missing placeholders
- Support for configuration-driven templates (QR codes, encryption passwords)

Real-world significance:
- Utilities are used by multiple pipeline steps (generate_qr_codes, encrypt_notice)
- Bugs in utils affect all downstream modules
- Template validation catches configuration errors early
- Used for QR payload generation and PDF password templates
- Critical for data integrity in notices
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from immuknow import utils
from tests.fixtures import sample_input


@pytest.mark.unit
class TestStringOrEmpty:
    """Unit tests for string_or_empty function."""

    def test_string_or_empty_converts_string(self) -> None:
        """Verify string values are returned as-is.

        Real-world significance:
        - Most client fields are already strings
        - Should not modify existing strings
        """
        result = utils.string_or_empty("John")
        assert result == "John"

    def test_string_or_empty_handles_none(self) -> None:
        """Verify None converts to empty string.

        Real-world significance:
        - Some client fields might be None/NaN
        - Should safely return empty string instead of "None"
        """
        result = utils.string_or_empty(None)
        assert result == ""

    def test_string_or_empty_converts_number(self) -> None:
        """Verify numbers are stringified.

        Real-world significance:
        - Client ID might be integer in some contexts
        - Should convert to string for template rendering
        """
        result = utils.string_or_empty(12345)
        assert result == "12345"

    def test_string_or_empty_handles_whitespace(self) -> None:
        """Verify leading/trailing whitespace is stripped.

        Real-world significance:
        - Excel input might have extra spaces
        - Templates expect trimmed values
        """
        result = utils.string_or_empty("  John Doe  ")
        assert result == "John Doe"

    def test_string_or_empty_handles_empty_string(self) -> None:
        """Verify empty string stays empty.

        Real-world significance:
        - Some optional fields might be empty
        - Should preserve empty state
        """
        result = utils.string_or_empty("")
        assert result == ""


@pytest.mark.unit
class TestExtractTemplateFields:
    """Unit tests for extract_template_fields function."""

    def test_extract_single_field(self) -> None:
        """Verify extraction of single placeholder.

        Real-world significance:
        - Simple templates like "{client_id}"
        - Should extract just the placeholder
        """
        result = utils.extract_template_fields("{client_id}")
        assert result == {"client_id"}

    def test_extract_multiple_fields(self) -> None:
        """Verify extraction of multiple placeholders.

        Real-world significance:
        - Complex templates with multiple fields
        - E.g., QR URL: "https://example.com?id={client_id}&dob={date_of_birth_iso}"
        """
        result = utils.extract_template_fields(
            "https://example.com?id={client_id}&dob={date_of_birth_iso}"
        )
        assert result == {"client_id", "date_of_birth_iso"}

    def test_extract_duplicate_fields(self) -> None:
        """Verify duplicates are returned as single entry.

        Real-world significance:
        - Template might use same field twice
        - set() naturally deduplicates
        """
        result = utils.extract_template_fields("{client_id}_{client_id}")
        assert result == {"client_id"}

    def test_extract_no_fields(self) -> None:
        """Verify empty set for template with no placeholders.

        Real-world significance:
        - Static templates with no variables
        - Should return empty set
        """
        result = utils.extract_template_fields("https://example.com/fixed-url")
        assert result == set()

    def test_extract_nested_braces(self) -> None:
        """Verify extraction with complex format strings.

        Real-world significance:
        - Format strings might have format specs: {client_id:>5}
        - Should extract field names correctly
        """
        result = utils.extract_template_fields("{client_id:>5}")
        assert "client_id" in result

    def test_extract_invalid_template_raises_error(self) -> None:
        """Verify error for malformed templates.

        Real-world significance:
        - Invalid templates should be caught early
        - Prevents downstream formatting errors
        """
        with pytest.raises(ValueError, match="Invalid template format"):
            utils.extract_template_fields("{client_id")


@pytest.mark.unit
class TestValidateAndFormatTemplate:
    """Unit tests for validate_and_format_template function."""

    def test_validate_and_format_simple_template(self) -> None:
        """Verify simple template formatting works.

        Real-world significance:
        - Basic case: template with available placeholders
        - Should render successfully
        """
        template = "Client: {client_id}"
        context = {"client_id": "12345"}
        result = utils.validate_and_format_template(template, context)
        assert result == "Client: 12345"

    def test_validate_and_format_multiple_fields(self) -> None:
        """Verify template with multiple placeholders.

        Real-world significance:
        - Password template: "{client_id}_{date_of_birth_iso_compact}"
        - Should substitute all fields
        """
        template = "{client_id}_{date_of_birth_iso_compact}"
        context = {
            "client_id": "12345",
            "date_of_birth_iso_compact": "20150315",
        }
        result = utils.validate_and_format_template(template, context)
        assert result == "12345_20150315"

    def test_validate_and_format_missing_placeholder_raises_error(self) -> None:
        """Verify error when placeholder not in context.

        Real-world significance:
        - Configuration typo: template uses unknown field
        - Should fail early with clear error message
        """
        template = "{client_id}_{unknown_field}"
        context = {"client_id": "12345"}

        with pytest.raises(KeyError, match="Unknown placeholder"):
            utils.validate_and_format_template(template, context)

    def test_validate_and_format_with_allowed_fields(self) -> None:
        """Verify validation against whitelist of fields.

        Real-world significance:
        - Security: QR template should only use certain fields
        - Prevents accidental exposure of sensitive data
        """
        template = "{client_id}"
        context = {"client_id": "12345", "secret": "password"}
        allowed = {"client_id"}

        result = utils.validate_and_format_template(
            template, context, allowed_fields=allowed
        )
        assert result == "12345"

    def test_validate_and_format_disallowed_field_raises_error(self) -> None:
        """Verify error when template uses disallowed placeholder.

        Real-world significance:
        - Security: template tries to use restricted field
        - Should reject with clear error
        """
        template = "{secret}"
        context = {"secret": "password", "client_id": "12345"}
        allowed = {"client_id"}

        with pytest.raises(ValueError, match="Disallowed placeholder"):
            utils.validate_and_format_template(
                template, context, allowed_fields=allowed
            )

    def test_validate_and_format_with_none_allowed_fields(self) -> None:
        """Verify None allowed_fields means no restriction.

        Real-world significance:
        - allowed_fields=None: allow any field in context
        - Default behavior for flexible templates
        """
        template = "{any_field}"
        context = {"any_field": "value"}

        result = utils.validate_and_format_template(
            template, context, allowed_fields=None
        )
        assert result == "value"

    def test_validate_and_format_empty_template(self) -> None:
        """Verify empty template with no placeholders.

        Real-world significance:
        - Some templates might be static
        - Should work fine with empty context
        """
        template = ""
        context = {}

        result = utils.validate_and_format_template(template, context)
        assert result == ""

    def test_validate_and_format_extra_context_fields(self) -> None:
        """Verify extra context fields don't cause error.

        Real-world significance:
        - Context might have more fields than template uses
        - Should allow partial use of context
        """
        template = "{client_id}"
        context = {
            "client_id": "12345",
            "first_name": "John",
            "last_name": "Doe",
        }

        result = utils.validate_and_format_template(template, context)
        assert result == "12345"


@pytest.mark.unit
class TestBuildClientContext:
    """Unit tests for build_client_context function."""

    def test_build_context_basic_client(self) -> None:
        """Verify context building for basic client record.

        Real-world significance:
        - Creates dict for template rendering
        - Used by QR code and encryption password templates
        """
        client = sample_input.create_test_client_record(
            client_id="12345",
            first_name="John",
            last_name="Doe",
            date_of_birth="2015-03-15",
            school_name="Lincoln School",
        )
        client = replace(client, contact={"postal_code": "M5V 3A8", "city": "Toronto"})

        context = utils.build_client_context(client)

        assert context["client_id"] == "12345"
        assert context["first_name"] == "John"
        assert context["last_name"] == "Doe"
        assert context["name"] == "John Doe"
        assert context["date_of_birth_iso"] == "2015-03-15"
        assert context["date_of_birth_iso_compact"] == "20150315"
        assert context["school"] == "Lincoln School"
        assert context["city"] == "Toronto"
        assert context["language_code"] == "en"

    def test_build_context_extracts_name_components(self) -> None:
        """Verify first/last name are used directly from data.

        Real-world significance:
        - First/last names are stored directly in data
        - Templates use individual name parts
        """
        client = sample_input.create_test_client_record(
            first_name="John", last_name="Quincy"
        )
        context = utils.build_client_context(client)

        assert context["first_name"] == "John"
        assert context["last_name"] == "Quincy"
        assert context["name"] == "John Quincy"

    def test_build_context_handles_single_name(self) -> None:
        """Verify handling of single name (no last name).

        Real-world significance:
        - Some clients might have single name
        - Last name can be empty string
        - This test documents current behavior
        """
        client = sample_input.create_test_client_record(first_name="Cher", last_name="")
        context = utils.build_client_context(client)

        assert context["first_name"] == "Cher"
        assert context["last_name"] == ""
        assert context["name"] == "Cher"

    def test_build_context_handles_missing_fields(self) -> None:
        """Verify safe handling of missing nested fields.

        Real-world significance:
        - Some client records might be incomplete
        - Should return empty strings, not crash
        """
        client = sample_input.create_test_client_record(client_id="12345")
        client = replace(client, person={}, school={}, contact={}, board={})
        context = utils.build_client_context(client)

        assert context["client_id"] == "12345"
        assert context["first_name"] == ""
        assert context["school"] == ""
        assert context["postal_code"] == ""

    def test_build_context_date_of_birth_compact_format(self) -> None:
        """Verify DOB compact format (YYYYMMDD) generation.

        Real-world significance:
        - Encryption password might use compact format
        - Should remove dashes from ISO date
        """
        client = sample_input.create_test_client_record(date_of_birth="2015-03-15")
        context = utils.build_client_context(client)

        assert context["date_of_birth_iso_compact"] == "20150315"

    def test_build_context_language_variants(self) -> None:
        """Verify language_code is set correctly.

        Real-world significance:
        - Template might format output based on language
        - Should preserve language code
        """
        context_en = utils.build_client_context(
            sample_input.create_test_client_record(language="en")
        )
        context_fr = utils.build_client_context(
            sample_input.create_test_client_record(language="fr")
        )

        assert context_en["language_code"] == "en"
        assert context_fr["language_code"] == "fr"

    def test_build_context_with_whitespace(self) -> None:
        """Verify whitespace is trimmed from fields.

        Real-world significance:
        - Excel input might have extra spaces
        - Templates should work with trimmed values
        """
        client = sample_input.create_test_client_record(
            first_name="  John", last_name="Doe  ", school_name="  Lincoln School  "
        )
        context = utils.build_client_context(client)

        assert context["first_name"] == "John"
        assert context["last_name"] == "Doe"
        assert context["school"] == "Lincoln School"

    def test_build_context_handles_all_contact_fields(self) -> None:
        """Verify all contact fields are extracted.

        Real-world significance:
        - QR template might use various contact fields
        - Should capture all available fields
        """
        client = sample_input.create_test_client_record()
        client = replace(
            client,
            contact={
                "postal_code": "M5V 3A8",
                "city": "Toronto",
                "province": "ON",
                "street": "123 Main St",
            },
        )
        context = utils.build_client_context(client)

        assert context["postal_code"] == "M5V 3A8"
        assert context["city"] == "Toronto"
        assert context["province"] == "ON"
        assert context["street_address"] == "123 Main St"
