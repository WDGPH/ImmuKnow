"""Unit tests for fr_template module - French Typst template generation.

Tests cover:
- Template rendering with client context (French version)
- Placeholder substitution (logo, signature, parameters paths)
- Required context key validation
- Error handling for missing context keys
- Template output structure
- Language-specific content (French)

Real-world significance:
- Renders Typst templates for French-language notices
- Part of notice generation pipeline (Step 4)
- Each client gets custom template with QR code, vaccines due, etc.
- Template errors prevent PDF compilation
- Must match English template structure for consistency
"""

from __future__ import annotations

import pytest

from templates.fr_template import (
    DYNAMIC_BLOCK,
    TEMPLATE_PREFIX,
    render_notice,
)


def _valid_context():
    """Create a valid context dict with all required keys (French).

    Helper for tests to avoid duplication.
    """
    return {
        "client_row": "()",
        "client_data": "{}",
        "vaccines_due_str": '""',
        "vaccines_due_array": "()",
        "received": "()",
        "num_rows": "0",
        "chart_diseases_translated": '("Diphtérie", "Tétanos", "Coqueluche")',
    }


@pytest.mark.unit
class TestRenderNotice:
    """Unit tests for render_notice function (French)."""

    def test_render_notice_with_valid_context(self) -> None:
        """Verify French template renders successfully with all required keys.

        Real-world significance:
        - Template must accept valid context from generate_notices
        - Output should be valid Typst code
        - French version should have same structure as English
        """
        context = {
            "client_row": '("001", "C00001", "Jean Dupont")',
            "client_data": '{name: "Jean Dupont", dob: "2015-03-15"}',
            "vaccines_due_str": '"RRO, DPT"',
            "vaccines_due_array": '("RRO", "DPT")',
            "received": '(("RRO", "2020-05-15"), ("DPT", "2019-03-15"))',
            "num_rows": "2",
            "chart_diseases_translated": '("Diphtérie", "Tétanos", "Coqueluche")',
        }

        result = render_notice(
            context,
            logo_path="/path/to/logo.png",
            signature_path="/path/to/signature.png",
        )

        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain notice and vaccine table sections
        assert "immunization_notice" in result

    def test_render_notice_missing_client_row_raises_error(self) -> None:
        """Verify error when client_row context missing (French).

        Real-world significance:
        - Missing required field should fail loudly
        - Better than producing invalid Typst
        """
        context = {
            # Missing client_row
            "client_data": "{}",
            "vaccines_due_str": '""',
            "vaccines_due_array": "()",
            "received": "()",
            "num_rows": "0",
            "chart_diseases_translated": '("Diphtérie", "Tétanos", "Coqueluche")',
        }

        with pytest.raises(KeyError, match="Missing context keys"):
            render_notice(
                context,
                logo_path="/path/to/logo.png",
                signature_path="/path/to/signature.png",
            )

    def test_render_notice_missing_multiple_keys_raises_error(self) -> None:
        """Verify error lists all missing keys (French).

        Real-world significance:
        - User can see which fields are missing
        - Helps debug generate_notices step
        """
        context = {
            # Missing multiple required keys
            "client_row": "()",
        }

        with pytest.raises(KeyError, match="Missing context keys"):
            render_notice(
                context,
                logo_path="/path/to/logo.png",
                signature_path="/path/to/signature.png",
            )

    def test_render_notice_substitutes_logo_path(self) -> None:
        """Verify logo path is substituted in template (French).

        Real-world significance:
        - Logo path must match actual file location
        - Output Typst must reference correct logo path
        """
        context = _valid_context()

        logo_path = "/custom/logo/path.png"
        result = render_notice(
            context,
            logo_path=logo_path,
            signature_path="/sig.png",
        )

        assert logo_path in result

    def test_render_notice_substitutes_signature_path(self) -> None:
        """Verify signature path is substituted in template (French).

        Real-world significance:
        - Signature path must match actual file location
        - Output Typst must reference correct signature path
        """
        context = _valid_context()

        signature_path = "/custom/signature.png"
        result = render_notice(
            context,
            logo_path="/logo.png",
            signature_path=signature_path,
        )

        assert signature_path in result

    def test_render_notice_includes_template_prefix(self) -> None:
        """Verify output includes template header and imports (French).

        Real-world significance:
        - Typst setup code must be included
        - Import statement for conf.typ is required
        """
        context = _valid_context()

        result = render_notice(
            context,
            logo_path="/logo.png",
            signature_path="/sig.png",
        )

        # Should include import statement (absolute import from project root)
        assert '#import "/templates/conf.typ"' in result

    def test_render_notice_includes_dynamic_block(self) -> None:
        """Verify output includes dynamic content section (French).

        Real-world significance:
        - Dynamic block contains client-specific data
        - Must have vaccines_due, vaccines_due_array, etc.
        """
        context = {
            "client_row": '("001", "C00001")',
            "client_data": "{}",
            "vaccines_due_str": '"RRO"',
            "vaccines_due_array": '("RRO")',
            "received": "()",
            "num_rows": "1",
            "chart_diseases_translated": '("Diphtérie", "Tétanos", "Coqueluche")',
        }

        result = render_notice(
            context,
            logo_path="/logo.png",
            signature_path="/sig.png",
        )

        # Dynamic block placeholders should be substituted
        assert "__CLIENT_ROW__" not in result  # Should be replaced
        assert "__CLIENT_DATA__" not in result  # Should be replaced
        assert '("001", "C00001")' in result  # Actual value should be in output

    def test_render_notice_with_complex_client_data(self) -> None:
        """Verify template handles complex client data structures (French).

        Real-world significance:
        - Client data might have nested structures
        - Template must accept and preserve complex Typst data structures
        """
        context = {
            "client_row": '("seq_001", "OEN_12345", "Alice Dupont")',
            "client_data": '(name: "Alice Dupont", dob: "2015-03-15", address: "123 Rue Main")',
            "vaccines_due_str": '"Rougeole, Oreillons, Rubéole"',
            "vaccines_due_array": '("Rougeole", "Oreillons", "Rubéole")',
            "received": '(("Rougeole", "2020-05-01"), ("Oreillons", "2020-05-01"))',
            "num_rows": "5",
            "chart_diseases_translated": '("Diphtérie", "Tétanos", "Coqueluche")',
        }

        result = render_notice(
            context,
            logo_path="/logo.png",
            signature_path="/sig.png",
        )

        # Verify complex values are included
        assert "Alice Dupont" in result
        assert "Rougeole" in result
        assert "Oreillons" in result

    def test_render_notice_empty_vaccines_handled(self) -> None:
        """Verify template handles no vaccines due (empty arrays) (French).

        Real-world significance:
        - Child might have all required vaccines
        - Template must handle empty vaccines_due_array
        """
        context = _valid_context()

        result = render_notice(
            context,
            logo_path="/logo.png",
            signature_path="/sig.png",
        )

        # Should still render successfully
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_notice_french_content(self) -> None:
        """Verify French-language content is rendered.

        Real-world significance:
        - Output must be in French for French-language processing
        - Key terms like "Dossier d'immunisation" must appear
        """
        context = _valid_context()

        result = render_notice(
            context,
            logo_path="/logo.png",
            signature_path="/sig.png",
        )

        # Should contain French text markers
        assert "Dossier d'immunisation" in result
        assert "Sincères salutations" in result


@pytest.mark.unit
class TestTemplateConstants:
    """Unit tests for template constant definitions (French)."""

    def test_template_prefix_contains_imports(self) -> None:
        """Verify TEMPLATE_PREFIX includes required imports (French).

        Real-world significance:
        - Typst must import conf.typ helpers
        - Setup code must be present
        - Uses absolute import from project root for generated .typ files
        """
        assert '#import "/templates/conf.typ"' in TEMPLATE_PREFIX

    def test_template_prefix_contains_function_definitions(self) -> None:
        """Verify TEMPLATE_PREFIX defines helper functions (French).

        Real-world significance:
        - immunization_notice() function must be defined
        - Functions used in dynamic block must exist
        """
        assert "immunization_notice" in TEMPLATE_PREFIX

    def test_dynamic_block_contains_placeholders(self) -> None:
        """Verify DYNAMIC_BLOCK has all substitution placeholders (French).

        Real-world significance:
        - Each placeholder corresponds to a context key
        - Missing placeholder = lost data in output
        """
        assert "__CLIENT_ROW__" in DYNAMIC_BLOCK
        assert "__CLIENT_DATA__" in DYNAMIC_BLOCK
        assert "__VACCINES_DUE_STR__" in DYNAMIC_BLOCK
        assert "__VACCINES_DUE_ARRAY__" in DYNAMIC_BLOCK
        assert "__RECEIVED__" in DYNAMIC_BLOCK
        assert "__NUM_ROWS__" in DYNAMIC_BLOCK

    def test_template_prefix_contains_placeholder_markers(self) -> None:
        """Verify TEMPLATE_PREFIX has path placeholders to substitute (French).

        Real-world significance:
        - Logo and signature paths must be replaceable
        - Parameters path no longer used (date pre-formatted in Python)
        """
        assert "__LOGO_PATH__" in TEMPLATE_PREFIX
        assert "__SIGNATURE_PATH__" in TEMPLATE_PREFIX

    def test_french_template_uses_french_client_info_function(self) -> None:
        """Verify French template calls French-specific functions.

        Real-world significance:
        - French template must call conf.client_info_tbl_fr not _en
        - Ensures French-language notice generation
        """
        assert "conf.client_info_tbl_fr" in TEMPLATE_PREFIX

    def test_french_template_has_french_disease_headers(self) -> None:
        """Verify French template references French disease headers.

        Real-world significance:
        - French notices must use French disease terminology
        - "Dossier d'immunisation" vs "Immunization Record"
        """
        assert "Dossier d'immunisation" in TEMPLATE_PREFIX
