"""Translation and normalization helpers for disease names.

Provides utilities to normalize input disease names to canonical English forms
and translate canonical names to localized display strings for multiple domains
(overdue list, immunization history chart).

**Contracts:**

- Canonical disease names are English strings from vaccine_reference.json (e.g., "Diphtheria", "Polio")
- Normalization maps raw input strings to canonical names using config/disease_normalization.json
- Translation maps canonical names to localized display strings using config/translations/*.json
- Missing translations fall back leniently (return canonical name + log warning) unless strict=True
- Missing normalization keys return the input unchanged; they may map via disease_map.json later
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from importlib.resources import files
from typing import Dict, Literal, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = Path(str(files("config")))
NORMALIZATION_PATH = CONFIG_DIR / "disease_normalization.json"
TRANSLATIONS_DIR = CONFIG_DIR / "translations"

LOG = logging.getLogger(__name__)

# Cache for loaded configs; populated on first use per run
_NORMALIZATION_CACHE: Optional[Dict[str, str]] = None
_TRANSLATION_CACHES: Dict[tuple[str, str, str], Dict[str, str]] = {}
_LOGGED_MISSING_KEYS: set = set()


def load_normalization() -> Dict[str, str]:
    """Load disease normalization map from config.

    Returns
    -------
    Dict[str, str]
        Map from raw disease strings to canonical disease names.
        Returns empty dict if file does not exist.
    """
    global _NORMALIZATION_CACHE
    if _NORMALIZATION_CACHE is not None:
        return _NORMALIZATION_CACHE

    if not NORMALIZATION_PATH.exists():
        _NORMALIZATION_CACHE = {}
        return _NORMALIZATION_CACHE

    try:
        with open(NORMALIZATION_PATH, encoding="utf-8") as f:
            _NORMALIZATION_CACHE = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        LOG.warning(f"Failed to load normalization config: {e}")
        _NORMALIZATION_CACHE = {}

    return _NORMALIZATION_CACHE


def load_translations(
    domain: Literal["diseases_overdue", "diseases_chart"],
    lang: str,
    config_dir: Path | None = None,
) -> Dict[str, str]:
    """Load translation map for a domain and language from config.

    Parameters
    ----------
    domain : Literal["diseases_overdue", "diseases_chart"]
        Display domain (overdue list or chart).
    lang : str
        Language code (e.g., "en", "fr").

    Returns
    -------
    Dict[str, str]
        Map from canonical disease names to localized display strings.
        Returns empty dict if file does not exist.
    """
    directory = (
        config_dir / "translations" if config_dir is not None else TRANSLATIONS_DIR
    )
    cache_key = (str(directory.resolve()), domain, lang)
    if cache_key in _TRANSLATION_CACHES:
        return _TRANSLATION_CACHES[cache_key]

    translation_file = directory / f"{lang}_{domain}.json"
    if config_dir is not None and not translation_file.exists():
        translation_file = TRANSLATIONS_DIR / f"{lang}_{domain}.json"
    if not translation_file.exists():
        _TRANSLATION_CACHES[cache_key] = {}
        return _TRANSLATION_CACHES[cache_key]

    try:
        with open(translation_file, encoding="utf-8") as f:
            _TRANSLATION_CACHES[cache_key] = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        LOG.warning(f"Failed to load translations for {lang}_{domain}: {e}")
        _TRANSLATION_CACHES[cache_key] = {}

    return _TRANSLATION_CACHES[cache_key]


def normalize_disease(token: str) -> str:
    """Normalize a raw disease string to canonical form.

    Applies the normalization map from config/disease_normalization.json.
    If the token is not in the normalization map, returns it unchanged (it may
    be normalized via disease_map.json later in preprocessing).

    Parameters
    ----------
    token : str
        Raw disease string from input data.

    Returns
    -------
    str
        Canonical disease name or unchanged token if not found.

    Examples
    --------
    >>> normalize_disease("Poliomyelitis")
    "Polio"
    >>> normalize_disease("Unknown Disease")
    "Unknown Disease"
    """
    token = token.strip()
    normalization = load_normalization()
    return normalization.get(token, token)


def display_label(
    domain: Literal["diseases_overdue", "diseases_chart"],
    key: str,
    lang: str,
    *,
    strict: bool = False,
    config_dir: Path | None = None,
) -> str:
    """Translate a canonical disease name to a localized display label.

    Loads translations from `config/translations/{domain}.{lang}.json`.
    Falls back leniently to the canonical key if missing (unless strict=True),
    and logs a single warning per unique missing key.

    Parameters
    ----------
    domain : Literal["diseases_overdue", "diseases_chart"]
        Display domain (overdue list or chart).
    key : str
        Canonical disease name (English).
    lang : str
        Language code (e.g., "en", "fr").
    strict : bool, optional
        If True, raise KeyError on missing translation. If False (default),
        return the canonical key and log a warning.

    Returns
    -------
    str
        Localized display label or canonical key (if not strict and missing).

    Raises
    ------
    KeyError
        If strict=True and translation is missing.

    Examples
    --------
    >>> display_label("diseases_overdue", "Polio", "en")
    "Polio"
    >>> display_label("diseases_overdue", "Polio", "fr")
    "Poliomyélite"
    """
    translations = load_translations(domain, lang, config_dir)
    if key in translations:
        return translations[key]

    missing_key = f"{domain}:{lang}:{key}"
    if missing_key not in _LOGGED_MISSING_KEYS:
        _LOGGED_MISSING_KEYS.add(missing_key)
        LOG.warning(
            f"Missing translation for {domain} in language {lang}: {key}. "
            f"Using canonical name."
        )

    if strict:
        raise KeyError(f"Missing translation for {domain} in language {lang}: {key}")

    return key


def clear_caches() -> None:
    """Clear all translation and normalization caches.

    Useful for testing or reloading configs during runtime.
    """
    global _NORMALIZATION_CACHE, _TRANSLATION_CACHES, _LOGGED_MISSING_KEYS
    _NORMALIZATION_CACHE = None
    _TRANSLATION_CACHES.clear()
    _LOGGED_MISSING_KEYS.clear()
