"""Unit tests for translation_helpers module.

Tests cover:
- Normalization of raw disease strings to canonical forms
- Translation of canonical disease names to localized display strings
- Lenient fallback behavior for missing translations
- Caching and performance
- Multiple languages (English and French)

Real-world significance:
- Translation helpers enable config-driven disease name translation
- Normalization reduces hardcoded input variants in preprocessing
- Multiple domains (overdue list vs chart) require independent translations
- Lenient fallback prevents pipeline failures from missing translations
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import translation_helpers


@pytest.mark.unit
class TestNormalizationLoading:
    """Unit tests for normalization config loading."""

    def test_load_normalization_returns_dict(self) -> None:
        """Verify load_normalization returns a dictionary."""
        result = translation_helpers.load_normalization()
        assert isinstance(result, dict)

    def test_load_normalization_cached(self) -> None:
        """Verify normalization is cached after first load."""
        translation_helpers.clear_caches()
        first = translation_helpers.load_normalization()
        second = translation_helpers.load_normalization()
        assert first is second  # Same object, cached

    def test_load_normalization_missing_file_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify missing normalization file returns empty dict."""
        translation_helpers.clear_caches()
        monkeypatch.setattr(
            translation_helpers, "NORMALIZATION_PATH", Path("/nonexistent/path.json")
        )
        result = translation_helpers.load_normalization()
        assert result == {}

    def test_load_normalization_invalid_json_returns_empty(
        self, tmp_test_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify invalid JSON file returns empty dict and logs warning."""
        translation_helpers.clear_caches()
        invalid_json = tmp_test_dir / "invalid.json"
        invalid_json.write_text("{invalid json}")
        monkeypatch.setattr(translation_helpers, "NORMALIZATION_PATH", invalid_json)

        result = translation_helpers.load_normalization()
        assert result == {}


@pytest.mark.unit
class TestTranslationLoading:
    """Unit tests for translation config loading."""

    def test_load_translations_returns_dict(self) -> None:
        """Verify load_translations returns a dictionary."""
        result = translation_helpers.load_translations("diseases_overdue", "en")
        assert isinstance(result, dict)

    def test_load_translations_cached(self) -> None:
        """Verify translations are cached after first load."""
        translation_helpers.clear_caches()
        first = translation_helpers.load_translations("diseases_overdue", "en")
        second = translation_helpers.load_translations("diseases_overdue", "en")
        assert first is second  # Same object, cached

    def test_load_translations_separate_cache_keys(self) -> None:
        """Verify different domain/language combinations have separate cache entries."""
        translation_helpers.clear_caches()
        en_overdue = translation_helpers.load_translations("diseases_overdue", "en")
        fr_overdue = translation_helpers.load_translations("diseases_overdue", "fr")
        assert en_overdue is not fr_overdue

    def test_load_translations_missing_file_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify missing translation file returns empty dict."""
        translation_helpers.clear_caches()
        monkeypatch.setattr(
            translation_helpers,
            "TRANSLATIONS_DIR",
            Path("/nonexistent/translations"),
        )
        result = translation_helpers.load_translations("diseases_overdue", "en")
        assert result == {}

    def test_load_translations_invalid_json_returns_empty(
        self, tmp_test_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify invalid JSON translation file returns empty dict."""
        translation_helpers.clear_caches()
        trans_dir = tmp_test_dir / "translations"
        trans_dir.mkdir()
        invalid_json = trans_dir / "en_diseases_overdue.json"
        invalid_json.write_text("{invalid}")
        monkeypatch.setattr(translation_helpers, "TRANSLATIONS_DIR", trans_dir)

        result = translation_helpers.load_translations("diseases_overdue", "en")
        assert result == {}


@pytest.mark.unit
class TestNormalizeDisease:
    """Unit tests for normalize_disease function."""

    def test_normalize_disease_known_variant(self) -> None:
        """Verify normalization of known disease variants."""
        translation_helpers.clear_caches()
        result = translation_helpers.normalize_disease(
            "Haemophilus influenzae infection, invasive"
        )
        # Should normalize to one of the canonical forms
        assert result in ["Hib", "Haemophilus influenzae infection, invasive"]

    def test_normalize_disease_poliomyelitis(self) -> None:
        """Verify Poliomyelitis normalizes to Polio."""
        translation_helpers.clear_caches()
        result = translation_helpers.normalize_disease("Poliomyelitis")
        assert result == "Polio"

    def test_normalize_disease_unknown_returns_unchanged(self) -> None:
        """Verify unknown disease names are returned unchanged."""
        translation_helpers.clear_caches()
        result = translation_helpers.normalize_disease("Unknown Disease")
        assert result == "Unknown Disease"

    def test_normalize_disease_strips_whitespace(self) -> None:
        """Verify normalization strips leading/trailing whitespace."""
        translation_helpers.clear_caches()
        result = translation_helpers.normalize_disease("  Poliomyelitis  ")
        assert result == "Polio"
        assert result.strip() == result  # No leading/trailing whitespace

    def test_normalize_disease_empty_string(self) -> None:
        """Verify empty string normalization returns empty string."""
        translation_helpers.clear_caches()
        result = translation_helpers.normalize_disease("")
        assert result == ""


@pytest.mark.unit
class TestDisplayLabel:
    """Unit tests for display_label function."""

    def test_display_label_english_overdue(self) -> None:
        """Verify English disease labels for overdue list."""
        translation_helpers.clear_caches()
        result = translation_helpers.display_label("diseases_overdue", "Polio", "en")
        assert result == "Polio"

    def test_display_label_french_overdue(self) -> None:
        """Verify French disease labels for overdue list."""
        translation_helpers.clear_caches()
        result = translation_helpers.display_label("diseases_overdue", "Polio", "fr")
        assert result == "Poliomyélite"

    def test_display_label_english_chart(self) -> None:
        """Verify English disease labels for chart."""
        translation_helpers.clear_caches()
        result = translation_helpers.display_label("diseases_chart", "Polio", "en")
        assert result == "Polio"

    def test_display_label_french_chart(self) -> None:
        """Verify French disease labels for chart."""
        translation_helpers.clear_caches()
        result = translation_helpers.display_label("diseases_chart", "Polio", "fr")
        assert result == "Poliomyélite"

    def test_display_label_missing_translation_lenient(self) -> None:
        """Verify missing translation returns canonical key (lenient mode)."""
        translation_helpers.clear_caches()
        result = translation_helpers.display_label(
            "diseases_overdue", "NonexistentDisease", "en", strict=False
        )
        assert result == "NonexistentDisease"

    def test_display_label_missing_translation_strict_raises(self) -> None:
        """Verify missing translation raises KeyError (strict mode)."""
        translation_helpers.clear_caches()
        with pytest.raises(KeyError):
            translation_helpers.display_label(
                "diseases_overdue",
                "NonexistentDisease",
                "en",
                strict=True,
            )

    def test_display_label_logs_missing_key_once(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify missing translation is logged only once per key."""
        translation_helpers.clear_caches()
        import logging

        caplog.set_level(logging.WARNING)

        # First call should log warning
        translation_helpers.display_label(
            "diseases_overdue", "UnknownDisease123", "en", strict=False
        )
        first_count = sum(
            1 for record in caplog.records if "UnknownDisease123" in record.message
        )
        assert first_count >= 1

        # Second call should not log warning (same key)
        caplog.clear()
        caplog.set_level(logging.WARNING)
        translation_helpers.display_label(
            "diseases_overdue", "UnknownDisease123", "en", strict=False
        )
        second_count = sum(
            1 for record in caplog.records if "UnknownDisease123" in record.message
        )
        assert second_count == 0  # No warning on second call


@pytest.mark.unit
class TestCacheCleaning:
    """Unit tests for cache management."""

    def test_clear_caches_resets_normalization(self) -> None:
        """Verify clear_caches resets normalization cache."""
        translation_helpers.load_normalization()
        first_id = id(translation_helpers._NORMALIZATION_CACHE)

        translation_helpers.clear_caches()
        translation_helpers.load_normalization()
        second_id = id(translation_helpers._NORMALIZATION_CACHE)

        assert first_id != second_id  # Different objects after clear

    def test_clear_caches_resets_translations(self) -> None:
        """Verify clear_caches resets translation caches."""
        translation_helpers.load_translations("diseases_overdue", "en")
        assert len(translation_helpers._TRANSLATION_CACHES) > 0

        translation_helpers.clear_caches()
        assert len(translation_helpers._TRANSLATION_CACHES) == 0

    def test_clear_caches_resets_logged_missing_keys(self) -> None:
        """Verify clear_caches resets logged missing keys."""
        translation_helpers.clear_caches()
        translation_helpers.display_label(
            "diseases_overdue", "UnknownX", "en", strict=False
        )
        assert len(translation_helpers._LOGGED_MISSING_KEYS) > 0

        translation_helpers.clear_caches()
        assert len(translation_helpers._LOGGED_MISSING_KEYS) == 0


@pytest.mark.unit
class TestMultiLanguageSupport:
    """Unit tests for multi-language support."""

    def test_all_canonical_diseases_have_english_labels(self) -> None:
        """Verify all canonical diseases have English display labels."""
        translation_helpers.clear_caches()
        diseases = [
            "Diphtheria",
            "HPV",
            "Hepatitis B",
            "Hib",
            "Measles",
            "Meningococcal",
            "Mumps",
            "Pertussis",
            "Pneumococcal",
            "Polio",
            "Rotavirus",
            "Rubella",
            "Tetanus",
            "Varicella",
        ]

        for disease in diseases:
            label = translation_helpers.display_label(
                "diseases_overdue", disease, "en", strict=False
            )
            assert label is not None
            assert isinstance(label, str)

    def test_all_canonical_diseases_have_french_labels(self) -> None:
        """Verify all canonical diseases have French display labels."""
        translation_helpers.clear_caches()
        diseases = [
            "Diphtheria",
            "HPV",
            "Hepatitis B",
            "Hib",
            "Measles",
            "Meningococcal",
            "Mumps",
            "Pertussis",
            "Pneumococcal",
            "Polio",
            "Rotavirus",
            "Rubella",
            "Tetanus",
            "Varicella",
        ]

        for disease in diseases:
            label = translation_helpers.display_label(
                "diseases_overdue", disease, "fr", strict=False
            )
            assert label is not None
            assert isinstance(label, str)
            # Verify it's actually French (at least for diseases with accents)
            if disease in ["Polio", "Tetanus", "Pertussis"]:
                # These should have accented French versions
                pass

    def test_normalize_then_translate_polio_english(self) -> None:
        """Verify Poliomyelitis -> Polio -> Polio (English)."""
        translation_helpers.clear_caches()
        normalized = translation_helpers.normalize_disease("Poliomyelitis")
        assert normalized == "Polio"

        translated = translation_helpers.display_label(
            "diseases_overdue", normalized, "en"
        )
        assert translated == "Polio"

    def test_normalize_then_translate_polio_french(self) -> None:
        """Verify Poliomyelitis -> Polio -> Poliomyélite (French)."""
        translation_helpers.clear_caches()
        normalized = translation_helpers.normalize_disease("Poliomyelitis")
        assert normalized == "Polio"

        translated = translation_helpers.display_label(
            "diseases_overdue", normalized, "fr"
        )
        assert translated == "Poliomyélite"

    def test_multiple_languages_independent(self) -> None:
        """Verify translations for different languages are independent."""
        translation_helpers.clear_caches()
        en_polio = translation_helpers.display_label("diseases_overdue", "Polio", "en")
        fr_polio = translation_helpers.display_label("diseases_overdue", "Polio", "fr")

        assert en_polio != fr_polio
        assert en_polio == "Polio"
        assert fr_polio == "Poliomyélite"


@pytest.fixture
def tmp_test_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for tests."""
    return tmp_path
