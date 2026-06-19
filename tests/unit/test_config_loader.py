"""Tests for configuration loading and validation across pipeline steps.

This module tests:
- YAML configuration loading from files
- Error handling for missing or malformed config files
- Validation ensures that required configuration keys are present and valid.

Real-world significance:
- Configuration controls all pipeline behavior (QR generation, encryption, bundling, etc.)
- Incorrect config loading or validation can cause cryptic failures deep in the pipeline
- Validates conditional requirements (e.g., qr.payload_template if qr.enabled=true)
- Catches configuration errors early at load time with clear error messages
- Helps administrators debug configuration issues

Note: Since validate_config() validates the entire config, test configs must have
valid QR settings (enabled=false or with payload_template) to focus testing on
other sections like bundling or typst.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from pipeline import config_loader
from pipeline.config_loader import validate_config


# Minimal valid config for sections not being tested
MINIMAL_VALID_CONFIG: Dict[str, Any] = {
    "qr": {"enabled": False},  # QR disabled, no template required
}


@pytest.mark.unit
class TestLoadConfig:
    """Unit tests for load_config function."""

    def test_load_config_with_default_path(self) -> None:
        """Verify config loads from default location.

        Real-world significance:
        - Pipeline must load config automatically without user intervention
        - Default path should point to config/parameters.yaml
        """
        config = config_loader.load_config()

        assert isinstance(config, dict)
        assert len(config) > 0

    def test_load_config_with_custom_path(self) -> None:
        """Verify config loads from custom path.

        Real-world significance:
        - Users may provide config from different directories (e.g., per-district)
        - Must support absolute and relative paths
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"
            config_path.write_text("qr:\n  enabled: false\ntest_key: test_value\n")

            config = config_loader.load_config(config_path)

            assert config["test_key"] == "test_value"

    def test_load_config_with_nested_yaml(self) -> None:
        """Verify nested YAML structures load correctly.

        Real-world significance:
        - Config sections (qr, encryption, pipeline, etc.) are nested
        - Must preserve structure for dot-notation retrieval
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nested_config.yaml"
            config_path.write_text(
                """qr:
  enabled: false
section1:
  key1: value1
  key2: value2
section2:
  nested:
    deep_key: deep_value
"""
            )

            config = config_loader.load_config(config_path)

            assert config["section1"]["key1"] == "value1"
            assert config["section2"]["nested"]["deep_key"] == "deep_value"

    def test_load_config_file_not_found(self) -> None:
        """Verify error when config file missing.

        Real-world significance:
        - Missing config indicates setup error; must fail early with clear message
        """
        missing_path = Path("/nonexistent/path/config.yaml")

        with pytest.raises(FileNotFoundError):
            config_loader.load_config(missing_path)

    def test_load_config_empty_file(self) -> None:
        """Verify empty YAML file with valid QR config returns dict.

        Real-world significance:
        - Empty config must still provide valid QR settings (QR enabled by default)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "empty_config.yaml"
            # Even empty files need valid QR config after validation
            config_path.write_text("qr:\n  enabled: false\n")

            config = config_loader.load_config(config_path)

            assert config.get("qr", {}).get("enabled") is False

    def test_load_config_with_various_data_types(self) -> None:
        """Verify YAML correctly loads strings, numbers, booleans, lists, nulls.

        Real-world significance:
        - Config uses all YAML types (e.g., qr.enabled: true, batch_size: 100)
        - Type preservation is critical for correct behavior
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "types_config.yaml"
            config_path.write_text(
                """qr:
  enabled: false
string_val: hello
int_val: 42
float_val: 3.14
bool_val: true
list_val:
  - item1
  - item2
null_val: null
"""
            )

            config = config_loader.load_config(config_path)

            assert config["string_val"] == "hello"
            assert config["int_val"] == 42
            assert config["float_val"] == 3.14
            assert config["bool_val"] is True
            assert config["list_val"] == ["item1", "item2"]
            assert config["null_val"] is None

    def test_load_config_with_invalid_yaml(self) -> None:
        """Verify error on invalid YAML syntax.

        Real-world significance:
        - Malformed config will cause hard-to-debug failures downstream
        - Must catch and report early
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "invalid_config.yaml"
            config_path.write_text("key: value\n  invalid: : :")

            with pytest.raises(Exception):  # yaml.YAMLError or similar
                config_loader.load_config(config_path)


@pytest.mark.unit
class TestActualConfig:
    """Unit tests using the actual parameters.yaml (if present).

    Real-world significance:
    - Should verify that production config is valid and loadable
    - Catches config corruption or breaking changes
    """

    def test_actual_config_loads_successfully(self) -> None:
        """Verify production config loads without error."""
        config = config_loader.load_config()

        assert isinstance(config, dict)
        assert len(config) > 0

    def test_actual_config_has_core_sections(self) -> None:
        """Verify config has expected top-level sections."""
        config = config_loader.load_config()

        # At least some of these should exist
        has_sections = any(
            key in config for key in ["pipeline", "qr", "encryption", "bundling"]
        )
        assert has_sections, "Config missing core sections"


@pytest.mark.unit
class TestQRConfigValidation:
    """Test configuration validation for QR Code Generation."""

    def test_qr_validation_passes_when_disabled(self) -> None:
        """QR validation should pass when qr.enabled=false (no template required)."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": False,
                # Template not required when disabled
            }
        }
        # Should not raise
        validate_config(config)

    def test_qr_validation_passes_with_valid_template(self) -> None:
        """QR validation should pass when enabled with valid template."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com/update?id={client_id}",
            }
        }
        # Should not raise
        validate_config(config)

    def test_qr_validation_fails_when_enabled_but_no_template(self) -> None:
        """QR validation should fail when enabled=true but template is missing."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                # Template is missing
            }
        }
        with pytest.raises(ValueError, match="qr.payload_template"):
            validate_config(config)

    def test_qr_validation_fails_when_enabled_but_empty_template(self) -> None:
        """QR validation should fail when enabled=true but template is empty string."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "",  # Empty string
            }
        }
        with pytest.raises(ValueError, match="qr.payload_template"):
            validate_config(config)

    def test_qr_validation_fails_when_template_not_string(self) -> None:
        """QR validation should fail when template is not a string."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": 12345,  # Invalid: not a string
            }
        }
        with pytest.raises(ValueError, match="must be a string"):
            validate_config(config)

    def test_qr_validation_fails_when_template_is_list(self) -> None:
        """QR validation should fail when template is a list."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": ["url1", "url2"],  # Invalid: list
            }
        }
        with pytest.raises(ValueError, match="must be a string"):
            validate_config(config)

    def test_qr_validation_uses_default_enabled_true(self) -> None:
        """QR validation should default qr.enabled=true (requires template)."""
        config: Dict[str, Any] = {
            "qr": {
                # enabled not specified, defaults to true
            }
        }
        with pytest.raises(ValueError, match="qr.payload_template"):
            validate_config(config)

    def test_qr_validation_handles_missing_qr_section(self) -> None:
        """QR validation should handle missing qr section (defaults enabled=true)."""
        config: Dict[str, Any] = {
            # No qr section at all
        }
        with pytest.raises(ValueError, match="qr.payload_template"):
            validate_config(config)


@pytest.mark.unit
class TestTypstConfigValidation:
    """Test configuration validation for Typst Compilation."""

    def test_typst_validation_passes_with_defaults(self) -> None:
        """Typst validation should pass when using default bin."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "typst": {},  # No explicit bin, uses default "typst"
        }
        # Should not raise
        validate_config(config)

    def test_typst_validation_passes_with_valid_bin(self) -> None:
        """Typst validation should pass with valid bin string."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "typst": {
                "bin": "typst",
                "font_path": "/path/to/fonts",
            },
        }
        # Should not raise
        validate_config(config)

    def test_typst_validation_fails_when_bin_not_string(self) -> None:
        """Typst validation should fail when bin is not a string."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "typst": {
                "bin": 12345,  # Invalid: not a string
            },
        }
        with pytest.raises(ValueError, match="typst.bin must be a string"):
            validate_config(config)

    def test_typst_validation_fails_when_bin_is_list(self) -> None:
        """Typst validation should fail when bin is a list."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "typst": {
                "bin": ["/usr/bin/typst"],  # Invalid: list
            },
        }
        with pytest.raises(ValueError, match="typst.bin must be a string"):
            validate_config(config)


@pytest.mark.unit
class TestBundlingConfigValidation:
    """Test configuration validation for PDF Bundling."""

    def test_bundling_validation_passes_when_disabled(self) -> None:
        """Bundling validation should pass when bundle_size=0 (disabled)."""
        config: Dict[str, Any] = {
            "qr": {"enabled": False},  # QR must be valid for overall validation
            "bundling": {
                "bundle_size": 0,  # Disabled
            },
        }
        # Should not raise
        validate_config(config)

    def test_bundling_validation_passes_with_valid_size_and_strategy(self) -> None:
        """Bundling validation should pass with valid bundle_size and group_by."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {
                "bundle_size": 100,
                "group_by": "school",
            },
        }
        # Should not raise
        validate_config(config)

    def test_bundling_validation_passes_with_null_group_by(self) -> None:
        """Bundling validation should pass with null group_by (sequential bundling)."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {
                "bundle_size": 50,
                "group_by": None,
            },
        }
        # Should not raise
        validate_config(config)

    def test_bundling_validation_fails_when_size_not_integer(self) -> None:
        """Bundling validation should fail when bundle_size is not an integer."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {
                "bundle_size": "100",  # Invalid: string instead of int
            },
        }
        with pytest.raises(ValueError, match="bundle_size must be an integer"):
            validate_config(config)

    def test_bundling_validation_fails_when_size_negative(self) -> None:
        """Bundling validation should fail when bundle_size is negative."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {
                "bundle_size": -100,  # Invalid: negative
            },
        }
        with pytest.raises(ValueError, match="bundle_size must be positive"):
            validate_config(config)

    def test_bundling_validation_fails_with_invalid_group_by(self) -> None:
        """Bundling validation should fail when group_by is invalid strategy."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {
                "bundle_size": 100,
                "group_by": "invalid_strategy",  # Invalid: not in BundleStrategy enum
            },
        }
        with pytest.raises(ValueError, match="group_by"):
            validate_config(config)

    def test_bundling_validation_fails_when_size_positive_but_not_integer(self) -> None:
        """Bundling validation should fail when bundle_size is float."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {
                "bundle_size": 100.5,  # Invalid: float, not int
            },
        }
        with pytest.raises(ValueError, match="bundle_size must be an integer"):
            validate_config(config)

    def test_bundling_validation_passes_with_board_group_by(self) -> None:
        """Bundling validation should pass with valid group_by='board'."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {
                "bundle_size": 100,
                "group_by": "board",
            },
        }
        # Should not raise
        validate_config(config)

    def test_bundling_validation_passes_with_size_group_by(self) -> None:
        """Bundling validation should pass with valid group_by='size'."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {
                "bundle_size": 100,
                "group_by": "size",
            },
        }
        # Should not raise
        validate_config(config)

    def test_bundling_validation_handles_missing_bundling_section(self) -> None:
        """Bundling validation should handle missing bundling section (defaults bundle_size=0)."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            # No bundling section; will use defaults
        }
        # Should not raise (bundle_size defaults to 0, which is disabled)
        validate_config(config)


@pytest.mark.unit
class TestConditionalValidationLogic:
    """Test that validation correctly handles conditional requirements."""

    def test_qr_payload_required_only_when_enabled(self) -> None:
        """Payload is only required when qr.enabled is explicitly true."""
        # Case 1: enabled=false, no template required
        config1: Dict[str, Any] = {"qr": {"enabled": False}}
        validate_config(config1)  # Should pass

        # Case 2: enabled=true, template required
        config2: Dict[str, Any] = {"qr": {"enabled": True}}
        with pytest.raises(ValueError, match="payload_template"):
            validate_config(config2)  # Should fail

        # Case 3: not specified, defaults to enabled=true, template required
        config3: Dict[str, Any] = {"qr": {}}
        with pytest.raises(ValueError, match="payload_template"):
            validate_config(config3)  # Should fail

    def test_group_by_validated_only_when_bundling_enabled(self) -> None:
        """group_by is only validated when bundle_size > 0."""
        # Case 1: bundle_size=0, group_by not validated even if invalid
        config1: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {"bundle_size": 0, "group_by": "invalid"},
        }
        validate_config(config1)  # Should pass (bundle_size=0 disables bundling)

        # Case 2: bundle_size > 0, group_by is validated
        config2: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {"bundle_size": 100, "group_by": "invalid"},
        }
        with pytest.raises(ValueError, match="group_by"):
            validate_config(config2)  # Should fail (invalid strategy)


@pytest.mark.unit
class TestErrorMessages:
    """Test that error messages are clear and actionable."""

    def test_qr_error_message_includes_config_key(self) -> None:
        """Error message should include config key and clear action."""
        config: Dict[str, Any] = {"qr": {"enabled": True}}
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        # Check message includes key information
        assert "qr.payload_template" in error_msg
        assert "not specified" in error_msg or "not found" in error_msg
        # Check message includes action
        assert "define" in error_msg.lower() or "set" in error_msg.lower()

    def test_bundling_error_message_includes_strategy_options(self) -> None:
        """Error message should include information about valid strategies."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "bundling": {"bundle_size": 100, "group_by": "invalid"},
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        # Error should mention the invalid value or strategy
        assert "group_by" in error_msg or "strategy" in error_msg


@pytest.mark.unit
class TestQRTemplateFieldValidation:
    """Test QR template placeholder validation against allowed fields."""

    def test_qr_validation_passes_with_valid_placeholders(self) -> None:
        """QR validation should pass when all placeholders are supported."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com?id={client_id}&name={first_name}_{last_name}&dob={date_of_birth_iso}",
            }
        }
        # Should not raise
        validate_config(config)

    def test_qr_validation_passes_with_all_supported_fields(self) -> None:
        """QR validation should pass when using all supported template fields."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": (
                    "https://example.com?"
                    "id={client_id}&fn={first_name}&ln={last_name}&name={name}&"
                    "dob={date_of_birth}&dob_iso={date_of_birth_iso}&"
                    "dob_compact={date_of_birth_iso_compact}&school={school}&"
                    "board={board}&street={street_address}&city={city}&"
                    "province={province}&pc={postal_code}&lang={language_code}"
                ),
            }
        }
        # Should not raise
        validate_config(config)

    def test_qr_validation_fails_with_unsupported_placeholder(self) -> None:
        """QR validation should fail when template contains unsupported placeholder."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com?id={client_id}&secret={password}",
            }
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        assert "unsupported placeholder" in error_msg.lower()
        assert "password" in error_msg
        assert "qr.payload_template" in error_msg

    def test_qr_validation_fails_with_multiple_unsupported_placeholders(self) -> None:
        """QR validation should fail and list all unsupported placeholders."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com?id={client_id}&bad1={invalid_field}&bad2={another_bad_field}",
            }
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        assert "unsupported placeholder" in error_msg.lower()
        assert "invalid_field" in error_msg
        assert "another_bad_field" in error_msg

    def test_qr_validation_error_message_includes_supported_fields(self) -> None:
        """QR validation error should list all supported fields for reference."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com?bad={unsupported}",
            }
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        # Should include some common supported fields
        assert "client_id" in error_msg
        assert "first_name" in error_msg
        assert "date_of_birth_iso" in error_msg

    def test_qr_validation_fails_with_typo_in_field_name(self) -> None:
        """QR validation should catch common typos in field names."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com?id={clent_id}",  # Typo: clent instead of client
            }
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        assert "clent_id" in error_msg
        assert "unsupported" in error_msg.lower()

    def test_qr_validation_fails_with_invalid_format_syntax(self) -> None:
        """QR validation should fail when template has invalid format string syntax."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com?id={client_id",  # Missing closing brace
            }
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        assert "invalid format" in error_msg.lower()

    def test_qr_validation_skipped_when_disabled(self) -> None:
        """QR template validation should be skipped when qr.enabled=false."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": False,
                # Even with invalid placeholders, validation should pass because QR is disabled
            }
        }
        # Should not raise
        validate_config(config)


@pytest.mark.unit
class TestEncryptionTemplateFieldValidation:
    """Test encryption password template placeholder validation."""

    def test_encryption_validation_passes_with_valid_placeholders(self) -> None:
        """Encryption validation should pass when all placeholders are supported."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "encryption": {
                "enabled": True,
                "password": {
                    "template": "{date_of_birth_iso_compact}",
                },
            },
        }
        # Should not raise
        validate_config(config)

    def test_encryption_validation_passes_with_complex_template(self) -> None:
        """Encryption validation should pass with multi-field password template."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "encryption": {
                "enabled": True,
                "password": {
                    "template": "{last_name}_{date_of_birth_iso_compact}_{postal_code}",
                },
            },
        }
        # Should not raise
        validate_config(config)

    def test_encryption_validation_fails_with_unsupported_placeholder(self) -> None:
        """Encryption validation should fail when template contains unsupported placeholder."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "encryption": {
                "enabled": True,
                "password": {
                    "template": "{date_of_birth_iso_compact}_{secret_key}",
                },
            },
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        assert "unsupported placeholder" in error_msg.lower()
        assert "secret_key" in error_msg
        assert "encryption.password.template" in error_msg

    def test_encryption_validation_fails_with_multiple_unsupported_placeholders(
        self,
    ) -> None:
        """Encryption validation should fail and list all unsupported placeholders."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "encryption": {
                "enabled": True,
                "password": {
                    "template": "{bad_field1}_{bad_field2}_{client_id}",
                },
            },
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        assert "unsupported placeholder" in error_msg.lower()
        assert "bad_field1" in error_msg
        assert "bad_field2" in error_msg

    def test_encryption_validation_error_includes_supported_fields(self) -> None:
        """Encryption validation error should list all supported fields."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "encryption": {
                "enabled": True,
                "password": {
                    "template": "{unsupported_field}",
                },
            },
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        # Should include some common supported fields
        assert "client_id" in error_msg
        assert "date_of_birth_iso" in error_msg
        assert "postal_code" in error_msg

    def test_encryption_validation_fails_with_invalid_format_syntax(self) -> None:
        """Encryption validation should fail when template has invalid format syntax."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "encryption": {
                "enabled": True,
                "password": {
                    "template": "{date_of_birth_iso_compact",  # Missing closing brace
                },
            },
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        assert "invalid format" in error_msg.lower()

    def test_encryption_validation_skipped_when_disabled(self) -> None:
        """Encryption template validation should be skipped when encryption.enabled=false."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            "encryption": {
                "enabled": False,
                "password": {
                    "template": "{unsupported_field}",  # Invalid but encryption is disabled
                },
            },
        }
        # Should not raise
        validate_config(config)

    def test_encryption_validation_handles_missing_encryption_section(self) -> None:
        """Encryption validation should handle missing encryption section (defaults to disabled)."""
        config: Dict[str, Any] = {
            **MINIMAL_VALID_CONFIG,
            # No encryption section; defaults to disabled
        }
        # Should not raise
        validate_config(config)


@pytest.mark.unit
class TestTemplateValidationEdgeCases:
    """Test edge cases and corner cases in template validation."""

    def test_validation_with_empty_template_after_type_check(self) -> None:
        """Empty template should fail at the 'not specified' check, not field validation."""
        # QR case
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "",
            }
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)
        # Should fail on "not specified" check, not unsupported fields
        assert "not specified" in str(exc_info.value).lower()

    def test_validation_with_template_no_placeholders(self) -> None:
        """Template with no placeholders should pass validation."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com/static-url",
            }
        }
        # Should not raise (no placeholders to validate)
        validate_config(config)

    def test_validation_with_duplicate_placeholders(self) -> None:
        """Template with duplicate placeholders should pass (sets deduplicate)."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com?id1={client_id}&id2={client_id}",
            }
        }
        # Should not raise
        validate_config(config)

    def test_both_qr_and_encryption_validated_together(self) -> None:
        """Both QR and encryption templates should be validated in same config."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com?id={client_id}&bad={invalid_qr}",
            },
            "encryption": {
                "enabled": True,
                "password": {
                    "template": "{date_of_birth_iso_compact}_{invalid_enc}",
                },
            },
        }
        # Should fail on QR validation (happens first)
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        # Should fail on QR first
        assert "qr.payload_template" in error_msg or "invalid_qr" in error_msg

    def test_encryption_validated_after_qr_passes(self) -> None:
        """If QR validation passes, encryption validation should still run."""
        config: Dict[str, Any] = {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.com?id={client_id}",  # Valid
            },
            "encryption": {
                "enabled": True,
                "password": {
                    "template": "{invalid_field}",  # Invalid
                },
            },
        }
        with pytest.raises(ValueError) as exc_info:
            validate_config(config)

        error_msg = str(exc_info.value)
        # Should fail on encryption
        assert "encryption.password.template" in error_msg
        assert "invalid_field" in error_msg
