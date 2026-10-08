"""Validate QR/password placeholders and build values from a resolved client."""

from __future__ import annotations

from string import Formatter
from typing import Any

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

    if "date_of_birth" in placeholders:
        raise ValueError(
            "{date_of_birth} is retired; use {date_of_birth_iso} or "
            "{date_of_birth_iso_compact} explicitly"
        )

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


def build_client_context(client: ClientRecord) -> dict[str, str]:
    """Build stable QR/password values from one resolved client record."""
    person = client.person
    contact = client.contact

    # QR and password dates are stable ISO values, independent of PDF presentation.
    dob_iso = person.get("date_of_birth_iso", "")

    # Extract name components (from authoritative first/last fields)
    first_name = person.get("first_name", "")
    last_name = person.get("last_name", "")
    # Combine for display purposes
    full_name = " ".join(filter(None, [first_name, last_name])).strip()

    return {
        "client_id": string_or_empty(client.client_id),
        "first_name": string_or_empty(first_name),
        "last_name": string_or_empty(last_name),
        "name": string_or_empty(full_name),
        "date_of_birth_iso": string_or_empty(dob_iso),
        "date_of_birth_iso_compact": string_or_empty(
            dob_iso.replace("-", "") if dob_iso else ""
        ),
        "school": string_or_empty(client.school.get("name", "")),
        "board": string_or_empty(client.board.get("name", "")),
        "postal_code": string_or_empty(contact.get("postal_code", "")),
        "city": string_or_empty(contact.get("city", "")),
        "province": string_or_empty(contact.get("province", "")),
        "street_address": string_or_empty(contact.get("street", "")),
        "language_code": client.language,
    }
