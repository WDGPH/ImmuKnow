"""Utility functions for immunization pipeline processing.

Provides template rendering utilities and context building functions shared
across pipeline steps, particularly for QR code generation, PDF encryption,
and template variable substitution. All functions handle string conversions
and safe formatting of client data for use in downstream templates."""

from __future__ import annotations

from string import Formatter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .data_models import ClientRecord

# Template formatter for extracting field names from format strings
_FORMATTER = Formatter()


def string_or_empty(value: Any) -> str:
    """Safely convert value to string, returning empty string for None/NaN.

    Parameters
    ----------
    value : Any
        Value to convert (may be None, empty string, or any type)

    Returns
    -------
    str
        Stringified value or empty string for None/NaN values
    """
    if value is None:
        return ""
    return str(value).strip()


def extract_template_fields(template: str) -> set[str]:
    """Extract placeholder names from a format string template.

    Parameters
    ----------
    template : str
        Format string like "https://example.com?id={client_id}&dob={date_of_birth_iso}"

    Returns
    -------
    set[str]
        Set of placeholder names found in template

    Raises
    ------
    ValueError
        If template contains invalid format string syntax

    Examples
    --------
    >>> extract_template_fields("{client_id}_{date_of_birth_iso}")
    {'client_id', 'date_of_birth_iso'}
    """
    try:
        return {
            field_name
            for _, field_name, _, _ in _FORMATTER.parse(template)
            if field_name
        }
    except ValueError as exc:
        raise ValueError(f"Invalid template format: {exc}") from exc


def validate_and_format_template(
    template: str,
    context: dict[str, str],
    allowed_fields: set[str] | None = None,
) -> str:
    """Format template and validate placeholders against allowed set.

    Ensures that:
    
    1. All placeholders in template exist in context
    2. All placeholders are in the allowed_fields set (if provided)
    3. Template is successfully rendered

    Parameters
    ----------
    template : str
        Format string template with placeholders
    context : dict[str, str]
        Context dict with placeholder values
    allowed_fields : set[str] | None
        Set of allowed placeholder names. If None, allows any placeholder
        that exists in context.

    Returns
    -------
    str
        Rendered template

    Raises
    ------
    KeyError
        If template contains placeholders not in context
    ValueError
        If template contains disallowed placeholders (when allowed_fields provided)

    Examples
    --------
    >>> ctx = {"client_id": "12345", "date_of_birth_iso": "2015-03-15"}
    >>> validate_and_format_template(
    ...     "{client_id}_{date_of_birth_iso}",
    ...     ctx,
    ...     allowed_fields={"client_id", "date_of_birth_iso"}
    ... )
    '12345_2015-03-15'
    """
    placeholders = extract_template_fields(template)

    # Check for missing placeholders in context
    unknown_fields = placeholders - context.keys()
    if unknown_fields:
        raise KeyError(
            f"Unknown placeholder(s) {sorted(unknown_fields)} in template. "
            f"Available: {sorted(context.keys())}"
        )

    # Check for disallowed placeholders (if whitelist provided)
    if allowed_fields is not None:
        disallowed = placeholders - allowed_fields
        if disallowed:
            raise ValueError(
                f"Disallowed placeholder(s) {sorted(disallowed)} in template. "
                f"Allowed: {sorted(allowed_fields)}"
            )

    return template.format(**context)


def build_client_context(
    client_data,
    language: str | None = None,
) -> dict[str, str]:
    """Build template context dict from client metadata for templating.

    Extracts and formats all available client fields for use in templates,
    supporting both QR code payloads and PDF encryption passwords.

    Accepts either a dict (from JSON) or a ClientRecord dataclass instance.
    Both provide the same fields; the function handles both transparently.

    Parameters
    ----------
    client_data : dict or ClientRecord
        Client data as either:
        - A dict (from preprocessed artifact JSON) with nested structure:
          {
              "client_id": "...",
              "person": {"first_name": "...", "last_name": "...", "date_of_birth_iso": "..."},
              "school": {"name": "..."},
              "board": {"name": "..."},
              "contact": {"postal_code": "...", "city": "...", ...}
          }
        - A ClientRecord dataclass instance with same nested fields.
    language : str, optional
        ISO 639-1 language code ('en' or 'fr'). When omitted, falls back to the
        client's own language field if present, otherwise an empty string.

    Returns
    -------
    dict[str, str]
        Context dict with keys:
        - client_id
        - first_name, last_name, name
        - date_of_birth (display format)
        - date_of_birth_iso (YYYY-MM-DD)
        - date_of_birth_iso_compact (YYYYMMDD)
        - school, board
        - postal_code, city, province, street_address
        - language_code ('en' or 'fr')

    Examples
    --------
    >>> client_dict = {
    ...     "client_id": "12345",
    ...     "person": {"first_name": "John", "last_name": "Doe", "date_of_birth_iso": "2015-03-15"},
    ...     "school": {"name": "Lincoln School"},
    ...     "contact": {"postal_code": "M5V 3A8"}
    ... }
    >>> ctx = build_client_context(client_dict)
    >>> ctx["client_id"]
    '12345'
    >>> ctx["first_name"]
    'John'
    """
    # Handle both dict and ClientRecord: extract nested fields uniformly
    if isinstance(client_data, dict):
        person = client_data.get("person", {})
        contact = client_data.get("contact", {})
        school = client_data.get("school", {})
        board = client_data.get("board", {})
        client_id = client_data.get("client_id", "")
        client_language = client_data.get("language", "")
    else:
        # Assume ClientRecord dataclass
        person = client_data.person or {}
        contact = client_data.contact or {}
        school = client_data.school or {}
        board = client_data.board or {}
        client_id = client_data.client_id
        client_language = client_data.language

    # Get DOB in ISO format
    dob_iso = person.get("date_of_birth_iso") or person.get("date_of_birth", "")
    dob_display = person.get("date_of_birth_display", "") or dob_iso

    # Extract name components (from authoritative first/last fields)
    first_name = person.get("first_name", "")
    last_name = person.get("last_name", "")
    # Combine for display purposes
    full_name = " ".join(filter(None, [first_name, last_name])).strip()

    language_code = string_or_empty(language or client_language)

    # Build context dict for template rendering
    context = {
        "client_id": string_or_empty(client_id),
        "first_name": string_or_empty(first_name),
        "last_name": string_or_empty(last_name),
        "name": string_or_empty(full_name),
        "date_of_birth": string_or_empty(dob_display),
        "date_of_birth_iso": string_or_empty(dob_iso),
        "date_of_birth_iso_compact": string_or_empty(
            dob_iso.replace("-", "") if dob_iso else ""
        ),
        "school": string_or_empty(school.get("name", "")),
        "board": string_or_empty(board.get("name", "")),
        "postal_code": string_or_empty(contact.get("postal_code", "")),
        "city": string_or_empty(contact.get("city", "")),
        "province": string_or_empty(contact.get("province", "")),
        "street_address": string_or_empty(contact.get("street", "")),
        "language_code": language_code,
    }

    return context


def deserialize_client_record(client_dict: dict) -> ClientRecord:
    """Deserialize a dict to a ClientRecord dataclass instance.

    Constructs a ClientRecord from a dict (typically from JSON), handling
    all required and optional fields uniformly. This is the canonical
    deserialization utility shared across modules for type safety and
    reduced code duplication.

    Parameters
    ----------
    client_dict : dict
        Client dict with structure:
        {
            "sequence": "...",
            "client_id": "...",
            "language": "...",
            "person": {...},
            "school": {...},
            "board": {...},
            "contact": {...},
            "vaccines_due": "...",
            "vaccines_due_list": [...],
            "received": [...],
            "metadata": {...},
            "qr": {...}  (optional)
        }

    Returns
    -------
    ClientRecord
        Constructed dataclass instance.

    Raises
    ------
    TypeError
        If dict cannot be converted (missing required fields or type mismatch).
    """
    from .data_models import ClientRecord

    try:
        return ClientRecord(
            sequence=client_dict.get("sequence", ""),
            client_id=client_dict.get("client_id", ""),
            language=client_dict.get("language", ""),
            person=client_dict.get("person", {}),
            school=client_dict.get("school", {}),
            board=client_dict.get("board", {}),
            contact=client_dict.get("contact", {}),
            vaccines_due=client_dict.get("vaccines_due"),
            vaccines_due_list=client_dict.get("vaccines_due_list"),
            vaccines_due_agent_list=client_dict.get("vaccines_due_agent_list"),
            received=client_dict.get("received"),
            metadata=client_dict.get("metadata", {}),
            qr=client_dict.get("qr"),
        )
    except TypeError as exc:
        raise TypeError(f"Cannot deserialize dict to ClientRecord: {exc}") from exc
