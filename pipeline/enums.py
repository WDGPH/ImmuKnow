"""Enumerations for the immunization pipeline."""

from enum import Enum


class BundleStrategy(Enum):
    """Bundle grouping strategy."""

    SIZE = "size"
    SCHOOL = "school"
    BOARD = "board"

    @classmethod
    def from_string(cls, value: str | None) -> "BundleStrategy":
        """Convert string to BundleStrategy.

        Parameters
        ----------
        value : str | None
            Bundle strategy name ('size', 'school', 'board'), or None for default.

        Returns
        -------
        BundleStrategy
            Corresponding BundleStrategy enum, defaults to SIZE if value is None.

        Raises
        ------
        ValueError
            If value is not a valid strategy name.
        """
        if value is None:
            return cls.SIZE

        value_lower = value.lower()
        for strategy in cls:
            if strategy.value == value_lower:
                return strategy

        raise ValueError(
            f"Unknown bundle strategy: {value}. "
            f"Valid options: {', '.join(s.value for s in cls)}"
        )


class BundleType(Enum):
    """Type descriptor for bundle operation."""

    SIZE_BASED = "size_based"
    SCHOOL_GROUPED = "school_grouped"
    BOARD_GROUPED = "board_grouped"


class Language(Enum):
    """Supported output languages for immunization notices.

    Each language corresponds to:

    - A template renderer in templates/ (en.typ, fr.typ, etc.)
    - Localization of dates, disease names, and notice formatting
    - An artifact language code stored in preprocessed data

    Currently supports English and French; extensible for future languages.

    Attributes
    ----------
    ENGLISH : str
        English language code ('en'). Templates: templates/en.typ
    FRENCH : str
        French language code ('fr'). Templates: templates/fr.typ

    See Also
    --------
    get_language_renderer : Map Language enum to template rendering function
    """

    ENGLISH = "en"
    FRENCH = "fr"

    @classmethod
    def from_string(cls, value: str | None) -> "Language":
        """Convert string to Language enum.

        Provides safe conversion from user input or configuration strings to
        Language enum values. Used at CLI entry point and configuration loading
        to fail fast on invalid language codes.

        Parameters
        ----------
        value : str | None
            Language code ('en', 'fr'), or None for default (ENGLISH).
            Case-insensitive (normalizes to lowercase).

        Returns
        -------
        Language
            Corresponding Language enum value.

        Raises
        ------
        ValueError
            If value is not a valid language code. Error message lists
            all available options.

        Examples
        --------
        >>> Language.from_string('en')
        <Language.ENGLISH: 'en'>

        >>> Language.from_string('EN')  # Case-insensitive
        <Language.ENGLISH: 'en'>

        >>> Language.from_string(None)  # Default to English
        <Language.ENGLISH: 'en'>

        >>> Language.from_string('es')  # Unsupported
        ValueError: Unsupported language: es. Valid options: en, fr
        """
        if value is None:
            return cls.ENGLISH

        value_lower = value.lower()
        for lang in cls:
            if lang.value == value_lower:
                return lang

        raise ValueError(
            f"Unsupported language: {value}. "
            f"Valid options: {', '.join(lang.value for lang in cls)}"
        )

    @classmethod
    def all_codes(cls) -> set[str]:
        """Get set of all supported language codes.

        Returns
        -------
        set[str]
            Set of all language codes (e.g., {'en', 'fr'}).

        Examples
        --------
        >>> Language.all_codes()
        {'en', 'fr'}
        """
        return {lang.value for lang in cls}


class TemplateField(Enum):
    """Available placeholder fields for template rendering (QR codes, PDF passwords).

    These fields are dynamically generated from client data by build_client_context()
    and can be used in configuration templates for:

    - QR code payloads (qr.payload_template in parameters.yaml)
    - PDF password generation (encryption.password.template in parameters.yaml)

    All fields are validated by validate_and_format_template() to catch config errors
    early and provide clear error messages.

    Fields
    ------
    CLIENT_ID : str
        Unique client identifier

    FIRST_NAME : str
        Client's given name.

    LAST_NAME : str
        Client's family name.

    NAME : str
        Full name (first + last combined).

    DATE_OF_BIRTH : str
        Display format (e.g., "Jan 8, 2025" or "8 janvier 2025").

    DATE_OF_BIRTH_ISO : str
        ISO 8601 format: YYYY-MM-DD (e.g., "2015-03-15").

    DATE_OF_BIRTH_ISO_COMPACT : str
        Compact ISO format without hyphens: YYYYMMDD (e.g., "20150315").

    SCHOOL : str
        School name.

    BOARD : str
        School board name.

    STREET_ADDRESS : str
        Full street address.

    CITY : str
        City/municipality.

    PROVINCE : str
        Province/territory.

    POSTAL_CODE : str
        Postal/ZIP code.

    LANGUAGE_CODE : str
        ISO 639-1 language code: 'en' or 'fr'.

    See Also
    --------
    build_client_context : Generates context dict with all available fields
    validate_and_format_template : Validates templates against allowed_fields set
    """

    # Identity
    CLIENT_ID = "client_id"

    # Name fields
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    NAME = "name"

    # Date of birth (multiple formats)
    DATE_OF_BIRTH = "date_of_birth"
    DATE_OF_BIRTH_ISO = "date_of_birth_iso"
    DATE_OF_BIRTH_ISO_COMPACT = "date_of_birth_iso_compact"

    # Organization
    SCHOOL = "school"
    BOARD = "board"

    # Address
    STREET_ADDRESS = "street_address"
    CITY = "city"
    PROVINCE = "province"
    POSTAL_CODE = "postal_code"

    # Metadata
    LANGUAGE_CODE = "language_code"

    @classmethod
    def all_values(cls) -> set[str]:
        """Get set of all available field names for use as allowed_fields whitelist.

        Returns
        -------
        set[str]
            Set of all field values (e.g., {'client_id', 'first_name', ...}).

        Examples
        --------
        >>> TemplateField.all_values()
        {'client_id', 'first_name', 'last_name', 'name', ...}
        """
        return {field.value for field in cls}
