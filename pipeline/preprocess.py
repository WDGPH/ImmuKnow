"""Preprocessing pipeline for immunization-charts.

Normalizes and structures input data into a single JSON artifact for downstream
pipeline steps. Handles data validation, client sorting, and vaccine processing.
QR code generation is handled by a separate step after preprocessing.

**Input Contract:**

- Reads raw client data from CSV or Excel file (.xlsx, .xls, .csv)
- Validates file type and encoding (tries multiple encodings for CSV)
- Validates all required columns are present

**Output Contract:**

- Writes preprocessed artifact JSON to output/artifacts/preprocessed_clients_*.json
- Artifact contains all valid client records with normalized data types
- Artifact includes metadata (run_id, language, created_at, warnings)
- Downstream steps assume artifact is valid; preprocessing is the sole validation step

**Error Handling:**

- File I/O errors (missing file, unsupported format) raise immediately (infrastructure)
- Missing required columns raise immediately (data error in required step)
- Invalid data (missing DOB, unparseable date) logged as warnings; processing continues
- Fail-fast for structural issues; warn-and-continue for data quality issues

**Validation Contract:**

What this module validates:

- Input file exists and is readable
- Input file is supported format (.xlsx, .xls, .csv)
- File encoding (tries UTF-8, Latin-1, etc. for CSV)
- All required columns are present in input data
- Client data normalization (DOB parsing, vaccine processing)
- Language code is valid (from CLI argument)

What this module assumes (validated upstream):

- Language code from CLI is valid (validated by Language.from_string() at orchestrator)
- Disease and vaccine reference data are valid JSON (validated by config loading)

Note: This is the primary validation step. Downstream steps trust preprocessing output.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
import pandas as pd
import yaml
from babel.dates import format_date
from frictionless import Detector, Schema, validate as fl_validate

from .assignment_manifest import ManifestRow, ReconciliationResult, has_errors, reconcile
from .data_models import (
    ArtifactPayload,
    ClientRecord,
    PreprocessResult,
)
from .enums import Language
from .notice_versioning import NoticeVersionCatalog, ResolvedNotice, validate_eligibility
from .translation_helpers import normalize_disease

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"
VACCINE_REFERENCE_PATH = CONFIG_DIR / "vaccine_reference.json"
PARAMETERS_PATH = CONFIG_DIR / "parameters.yaml"

LOG = logging.getLogger(__name__)

REPLACE_UNSPECIFIED = [
    "-unspecified",
    "unspecified",
    "Not Specified",
    "Not specified",
    "Not Specified-unspecified",
]

INPUT_SCHEMA_PATH = CONFIG_DIR / "input_schema.json"


def convert_date_string(
    date_str: str | datetime | pd.Timestamp, locale: str = "en"
) -> str | None:
    """Convert a date to display format with locale-aware formatting.

    Uses Babel for locale-aware date formatting. Generates format like
    "May 8, 2025" (en) or "8 mai 2025" (fr) depending on locale.

    Parameters
    ----------
    date_str : str | datetime | pd.Timestamp
        Date string in YYYY-MM-DD format or datetime-like object.
    locale : str, optional
        Locale code for date formatting (default: "en").
        Examples: "en" for English, "fr" for French.

    Returns
    -------
    str | None
        Date in locale-specific format, or None if input is null.

    Raises
    ------
    ValueError
        If date_str is a string in unrecognized format.
    """
    if pd.isna(date_str):
        return None

    # If it's already a datetime or Timestamp, use it directly
    if isinstance(date_str, (pd.Timestamp, datetime)):
        date_obj = date_str
    else:
        # Parse string input
        try:
            date_obj = datetime.strptime(str(date_str).strip(), "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Unrecognized date format: {date_str}")

    return format_date(date_obj, format="long", locale=locale)


def format_iso_date_for_language(iso_date: str, language: str) -> str:
    """Format an ISO date string with locale-aware formatting for the given language.

    Converts a date from ISO format (YYYY-MM-DD) to a long, locale-specific
    display format using Babel. This function handles language-specific date
    formatting for templates.

    Parameters
    ----------
    iso_date : str
        Date in ISO format (YYYY-MM-DD), e.g., "2025-08-31".
    language : str
        ISO 639-1 language code ("en", "fr", etc.).

    Returns
    -------
    str
        Formatted date in the specified language, e.g.,
        "August 31, 2025" (en) or "31 août 2025" (fr).

    Raises
    ------
    ValueError
        If iso_date is not in YYYY-MM-DD format.
    """
    locale_map = {"en": "en_US", "fr": "fr_FR"}
    locale = locale_map.get(language, language)

    try:
        date_obj = datetime.strptime(iso_date.strip(), "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid ISO date format: {iso_date}. Expected YYYY-MM-DD.")

    return format_date(date_obj, format="long", locale=locale)


def check_addresses_complete(df: pd.DataFrame, drop_incomplete=True) -> pd.DataFrame:
    """
    Check if address fields are complete in the DataFrame.

    Adds a temporary boolean 'address_complete' column based on presence of
    street address, city, province, and postal code.
    """

    df = df.copy()

    # Normalize text fields: convert to string, strip whitespace, convert "" to NA
    address_cols = [
        "street_address_line_1",
        "street_address_line_2",
        "city",
        "province",
        "postal_code",
    ]

    for col in address_cols:
        df[col] = df[col].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA})

    # Build combined address line
    df["address"] = (
        df["street_address_line_1"].fillna("")
        + " "
        + df["street_address_line_2"].fillna("")
    ).str.strip()

    df["address"] = df["address"].replace({"": pd.NA})

    # Check completeness
    df["address_complete"] = (
        df["address"].notna()
        & df["city"].notna()
        & df["province"].notna()
        & df["postal_code"].notna()
    )

    if not df["address_complete"].all():
        incomplete_count = (~df["address_complete"]).sum()
        LOG.warning(
            "There are %d records with incomplete address information.",
            incomplete_count,
        )

        incomplete_records = df.loc[~df["address_complete"]]

        incomplete_path = SCRIPT_DIR.parent / "output" / "incomplete_addresses.csv"
        incomplete_records.to_csv(incomplete_path, index=False)
        LOG.info("Incomplete address records written to %s", incomplete_path)

    # Return only rows with complete addresses based on drop_incomplete flag
    if drop_incomplete:
        return df.loc[df["address_complete"]].drop(columns=["address_complete"])
    else:
        return df.drop(columns=["address_complete"])


def check_client_info_complete(df: pd.DataFrame, assignment_mode, drop_incomplete=True) -> pd.DataFrame:
    """
    Check if client fields are complete in the DataFrame.

    Adds a temporary boolean 'client_info_complete' column based on presence of
    first name, last name, DOB, school name, overdue disease, immunizations given, and client ID.
    """

    df = df.copy()

    # Normalize text fields: convert to string, strip whitespace, convert "" to NA
    client_info_cols = [
        "school_name",
        "client_id",
        "first_name",
        "last_name",
        "date_of_birth",
        "imms_given",
    ]

    # Default fixed mode should require non-empty overdue list
    if assignment_mode == "fixed":
        client_info_cols.extend([
            "overdue_disease",
            "overdue_agent",
        ])

    for col in client_info_cols:
        df[col] = df[col].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA})

    # Check completeness
    df["client_info_complete"] = df[client_info_cols].notna().all(axis=1)

    if not df["client_info_complete"].all():
        incomplete_count = (~df["client_info_complete"]).sum()
        LOG.warning(
            "There are %d records with incomplete/invalid client information.",
            incomplete_count,
        )
        print(
            f"⚠️ There are {incomplete_count} total records with incomplete/invalid client information."
        )

        incomplete_records = df.loc[~df["client_info_complete"]]

        incomplete_path = SCRIPT_DIR.parent / "output" / "incomplete_clients.csv"
        incomplete_records.to_csv(incomplete_path, index=False)
        LOG.info("Incomplete client records written to %s", incomplete_path)
        print(f"Incomplete client records written to {incomplete_path}")

    # Return only rows with complete client info based on drop_incomplete flag
    if drop_incomplete:
        return df.loc[df["client_info_complete"]].drop(columns=["client_info_complete"])
    else:
        return df.drop(columns=["client_info_complete"])


def convert_date_iso(date_str: str) -> str:
    """Convert a date from English display format to ISO format.

    Reverses the formatting from convert_date_string(). Expects input
    in "Mon DD, YYYY" format (e.g., "May 8, 2025").

    Parameters
    ----------
    date_str : str
        Date in English display format (e.g., "May 8, 2025").

    Returns
    -------
    str
        Date in ISO format (YYYY-MM-DD).
    """
    date_obj = datetime.strptime(date_str, "%b %d, %Y")
    return date_obj.strftime("%Y-%m-%d")


def calculate_age_at_date(date_of_birth, date_notice_delivery):
    """Calculate a client's age on notice delivery date.

    Parameters
    ----------
    date_of_birth : str
        Date of birth in YYYY-MM-DD format.
    date_notice_delivery : str
        Notice delivery date in YYYY-MM-DD format.

    Returns
    -------
    int
        The client's age on date_notice_delivery.
    """

    birth_datetime = datetime.strptime(date_of_birth, "%Y-%m-%d")
    delivery_datetime = datetime.strptime(date_notice_delivery, "%Y-%m-%d")

    age = delivery_datetime.year - birth_datetime.year

    # Adjust if birthday hasn't occurred yet in the DOV month
    if (delivery_datetime.month < birth_datetime.month) or (
        delivery_datetime.month == birth_datetime.month
        and delivery_datetime.day < birth_datetime.day
    ):
        age -= 1

    return age


def configure_logging(output_dir: Path, run_id: str) -> Path:
    """Configure file logging for the preprocessing step.

    Parameters
    ----------
    output_dir : Path
        Root output directory where logs subdirectory will be created.
    run_id : str
        Unique run identifier used in log filename.

    Returns
    -------
    Path
        Path to the created log file.
    """
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"preprocess_{run_id}.log"

    handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    return log_path


def detect_file_type(file_path: Path) -> str:
    """Detect file type by extension.

    Parameters
    ----------
    file_path : Path
        Path to the file to detect.

    Returns
    -------
    str
        File extension in lowercase (e.g., '.xlsx', '.csv').

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")
    return file_path.suffix.lower()


def read_input(file_path: Path) -> pd.DataFrame:
    """Read CSV or Excel input file into a pandas DataFrame.

    Supports .xlsx, .xls, and .csv formats with robust encoding and delimiter
    detection. This is a critical preprocessing step that loads raw client data.

    Parameters
    ----------
    file_path : Path
        Path to the input file (CSV, XLSX, or XLS).

    Returns
    -------
    pd.DataFrame
        DataFrame with raw client data loaded from the file.

    Raises
    ------
    ValueError
        If file type is unsupported or CSV cannot be decoded with common encodings.
    Exception
        If file reading fails for any reason (logged to preprocessing logs).
    """
    ext = detect_file_type(file_path)

    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path, engine="openpyxl", dtype={"client_id": str})
        elif ext == ".csv":
            # Try common encodings
            for enc in ["utf-8-sig", "latin-1", "cp1252"]:
                try:
                    # Let pandas sniff the delimiter
                    df = pd.read_csv(file_path, sep=None, encoding=enc, engine="python")
                    break
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            else:
                raise ValueError(
                    "Could not decode CSV with common encodings or delimiters"
                )
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        LOG.info("Loaded %s rows from %s", len(df), file_path)
        return df

    except Exception as exc:  # pragma: no cover - logging branch
        LOG.error("Failed to read %s: %s", file_path, exc)
        raise


def validate_input(file_path: Path) -> None:
    """Validate that the input file conforms to the expected column schema.

    Parameters
    ----------
    file_path : Path
        Path to the input file (.xlsx or .csv).

    Raises
    ------
    ValueError
        If the file does not conform to the schema defined in
        ``config/input_schema.json``.
    """
    descriptor = json.loads(INPUT_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema = Schema.from_descriptor(descriptor)
    report = fl_validate(
        file_path.name,
        basepath=str(file_path.parent),
        schema=schema,
        detector=Detector(schema_sync=True),
    )

    if not report.valid:
        errors = report.flatten(["message"])
        raise ValueError(
            "Input file does not conform to expected schema:\n"
            + "\n".join(f"  - {e[0]}" for e in errors)
        )



def split_vaccine_due_entry(item: str) -> tuple[str, str | None]:
    """Separate a disease name from its optional dose field."""

    disease, separator, dose = item.strip().rpartition(" -")
    if not separator:
        return item.strip(), None
    return disease.strip(), dose.strip()


def hide_vaccine_due_doses(vaccine_due_list: list[str]) -> list[str]:
    """Remove supplied dose fields while preserving ordinary disease labels."""

    return [split_vaccine_due_entry(item)[0] for item in vaccine_due_list]


def format_vaccine_due_list(vaccine_due_list: list[str]) -> list[str]:
    """Format dose-bearing overdue entries for display."""

    formatted: list[str] = []
    for item in vaccine_due_list:
        disease, dose = split_vaccine_due_entry(item)
        if dose is None:
            raise ValueError(
                "preprocess.include_dose requires overdue entries using the "
                "'<disease> - <dose>' schema"
            )

        if not dose:
            formatted.append(disease)
            continue

        if dose[-1] == "1":
            formatted.append(f"{disease} ({dose}st dose)")
        elif dose[-1] == "2":
            formatted.append(f"{disease} ({dose}nd dose)")
        elif dose[-1] == "3":
            formatted.append(f"{disease} ({dose}rd dose)")
        else:
            # Ensure separated section is an integer within vaccine series range
            try:
                if int(dose) < 10:
                    formatted.append(f"{disease} ({dose}th dose)")
                else:
                    LOG.warning(
                        f"Vaccine with ' - ' separator but invalid dose number: {item}"
                    )
                    formatted.append(item.strip())

            except (ValueError, TypeError):
                formatted.append(item.strip())

    return formatted


_REQUIRED_STRING_COLS = [
    "school_name",
    "first_name",
    "last_name",
    "street_address_line_1",
    "street_address_line_2",
    "city",
    "province",
    "postal_code",
    "overdue_agent",
]

_OPTIONAL_COLS = ["board_name", "board_id", "school_id", "version_id"]


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize data types on a DataFrame with snake_case column names.

    Applies string normalization, date parsing, and numeric coercion.
    """
    working = df.copy()

    for col in _REQUIRED_STRING_COLS:
        working[col] = working[col].fillna(" ").astype(str).str.strip()

    for col in _OPTIONAL_COLS:
        if col not in working.columns:
            working[col] = ""
        else:
            working[col] = working[col].fillna(" ").astype(str).str.strip()

    working["date_of_birth"] = pd.to_datetime(working["date_of_birth"], errors="coerce")

    return working


def synthesize_identifier(existing: str, source: str, prefix: str) -> str:
    """Generate a deterministic identifier if one is not provided."""
    existing = (existing or "").strip()
    if existing:
        return existing

    base = (source or "").strip().lower() or "unknown"
    digest = sha1(base.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def process_vaccines_due(vaccines_due: Any, mode: str) -> str:
    """Map overdue diseases to canonical disease names.

    Normalizes raw input disease strings to canonical disease names using
    config/disease_normalization.json. Returns a comma-separated string of
    canonical disease names.

    Parameters
    ----------
    vaccines_due : Any
        Raw string of comma-separated disease names from input.
    mode : str
        Code for whether vaccine due list contains overdue "agent" or "disease".

    Returns
    -------
    str
        Comma-separated string of canonical disease names (English).
        Empty string if input is empty or invalid.
    """
    if not isinstance(vaccines_due, str) or not vaccines_due.strip():
        return ""

    items: List[str] = []
    for token in vaccines_due.split(";"):
        token = token.strip()

        # If list ends with ';', do not create enmpty entry in items
        if not token:
            continue

        if mode == "disease":
            # Normalize: raw input -> canonical disease name
            token: str = normalize_disease(token)
        
        items.append(token)

    # Filter empty items and clean quotes
    return ", ".join(
        item.replace("'", "").replace('"', "") for item in items if item.strip()
    )


def normalize_validity_status(raw_status: Any) -> str:
    """Normalize a raw validity token to one of three canonical statuses.

    Only the exact casings "valid"/"Valid" and "invalid"/"Invalid" are
    accepted as known statuses; everything else — typos, alternate casings,
    empty strings, None, NaN — maps to "unknown". This strict gate prevents
    ambiguous data from silently influencing validity markers on notices.

    Parameters
    ----------
    raw_status : Any
        Raw value extracted from an imms_given segment, or any value that
        needs to be coerced to a canonical status. Typically a str, but
        accepts Any so callers need not guard against None or NaN.

    Returns
    -------
    str
        One of ``"valid"``, ``"invalid"``, or ``"unknown"``.

    Examples
    --------
    >>> normalize_validity_status("Valid")
    'valid'
    >>> normalize_validity_status("")
    'unknown'
    >>> normalize_validity_status(None)
    'unknown'
    """
    status = str(raw_status).strip()
    if status in {"valid", "Valid"}:
        return "valid"
    if status in {"invalid", "Invalid"}:
        return "invalid"
    return "unknown"


def collapse_validity_statuses(statuses: List[Any]) -> str:
    """Collapse multiple validity statuses using strict precedence.

    Precedence:
    
    1. mixed (if both valid and invalid are present and no unknown)
    2. valid (if at least one valid is present and no unknown)
    3. invalid (if invalid is present and no unknown)
    4. unknown (otherwise)
    """
    normalized = [normalize_validity_status(s) for s in statuses]
    
    has_valid = "valid" in normalized
    has_invalid = "invalid" in normalized
    has_unknown = "unknown" in normalized

    if has_valid and has_invalid and not has_unknown:
        return "mixed"

    # "All valid" / "all invalid" only when no unknowns are present
    if has_valid and not has_unknown:
        return "valid"
    if has_invalid and not has_unknown:
        return "invalid"

    # anything involving unknown (or empty) stays unknown
    return "unknown"


def classify_dataset_validity(
    imms_given_series: pd.Series,
) -> Literal["all_present", "all_absent", "mixed"]:
    """Scan all imms_given values and classify dataset-level validity coverage.

    Performs a pre-pass over the full dataset before the per-client loop so
    that a single, accurate dataset-level decision can be made about whether
    to show warnings, raise errors, or proceed normally. This avoids the
    unreliable alternative of accumulating per-record ``"unknown"`` counts,
    which can mask a structurally inconsistent dataset.

    Called once by ``build_preprocess_result`` immediately before the client
    loop. Its return value determines which branch of the warning/error logic
    fires; see the behaviour table in the module docstring.

    Parameters
    ----------
    imms_given_series : pd.Series
        The ``imms_given`` column of the normalized working DataFrame.
        Each element is a semicolon-delimited string of dose segments such as
        ``"May 1, 2020 - DTaP - Valid; Jun 15, 2021 - MMR"``.
        NaN values and empty strings are silently skipped.

    Returns
    -------
    Literal["all_present", "all_absent", "mixed"]
        ``"all_present"``
            Every dose segment in the dataset that contains a recognisable
            date entry also carries a ``- Valid`` or ``- Invalid`` suffix.

        ``"all_absent"``
            No dose segment carries a validity suffix, or the series
            contains no recognisable dose entries at all.
            
        ``"mixed"``
            At least one segment has a suffix and at least one does not.
            This state causes a ``ValueError`` when
            ``show_validity_markers`` is ``True``.

    Notes
    -----
    - Pure scan — no side effects, no logging.
    - O(n × d) where n is the number of rows and d is the average number
      of dose segments per row; short-circuits as soon as ``"mixed"`` is
      confirmed.
    """
    with_validity = re.compile(r" - (?:[Vv]alid|[Ii]nvalid)(?=;|$)")
    dose_entry = re.compile(r"\w{3} \d{1,2}, \d{4}")

    has_with = False
    has_without = False

    for raw in imms_given_series:
        if not isinstance(raw, str) or not raw.strip():
            continue
        for segment in raw.split(";"):
            segment = segment.strip()
            if not dose_entry.search(segment):
                continue
            if with_validity.search(segment):
                has_with = True
            else:
                has_without = True
            if has_with and has_without:
                return "mixed"

    return "all_present" if has_with else "all_absent"


def parse_dose_segments(
    received_agents: Any, replace_unspecified: List[str]
) -> List[Dict[str, str]]:
    """Parse an imms_given string into a flat sorted list of individual dose entries.

    Extracts individual dose entries from a semicolon-delimited string,
    normalizes dates to ISO format, normalizes validity to one of
    ``"valid"`` / ``"invalid"`` / ``"unknown"``, and filters unwanted
    vaccine names.  Unlike the former ``process_received_agents``, this
    function does *not* group by date — grouping and disease-expansion are
    handled by ``build_received_rows``.

    Parameters
    ----------
    received_agents : Any
        Raw imms_given cell value.  Must be a non-empty ``str`` to be
        parsed; any other type returns ``[]``.
        Expected format per segment: ``"MMM D, YYYY - VaccineName"`` or
        ``"MMM D, YYYY - VaccineName - Valid|Invalid"``.
    replace_unspecified : List[str]
        Vaccine names to silently drop (e.g. ``["Not Specified"]``).

    Returns
    -------
    List[Dict[str, str]]
        Flat list of ``{"date_given": str, "vaccine": str, "validity": str}``
        dicts, sorted ascending by date.  Returns ``[]`` if
        ``received_agents`` is not a parseable string or contains no
        recognisable dose segments after filtering.
    """
    if not isinstance(received_agents, str) or not received_agents.strip():
        return []

    pattern = re.compile(
        r"(\w{3} \d{1,2}, \d{4}) - (.*?)(?:\s*-\s*([Vv]alid|[Ii]nvalid))?(?=;|$)"
    )

    rows: List[Dict[str, str]] = []
    for date_str, vaccine, raw_valid in pattern.findall(received_agents):
        vaccine = vaccine.strip()
        vaccine = vaccine.replace("-unspecified", "*").replace(" unspecified", "*")
        if vaccine in replace_unspecified:
            continue
        rows.append({
            "date_given": convert_date_iso(date_str.strip()),
            "vaccine": vaccine,
            "validity": normalize_validity_status(raw_valid),
        })

    rows.sort(key=lambda item: item["date_given"])
    return rows


def _deduplicate_vaccines_for_date(
    date_doses: List[Dict[str, str]],
    vaccine_reference: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Collapse same-vaccine doses and expand each unique vaccine to its diseases.

    Multiple doses of the same vaccine on one date are reduced to a single
    entry whose validity follows ``unknown > valid > invalid`` precedence:
    any unknown status dominates (data quality signal), then any valid,
    then all-invalid.

    Parameters
    ----------
    date_doses : List[Dict[str, str]]
        Flat dose entries for a single date from ``parse_dose_segments``,
        each with ``{"vaccine": str, "validity": str}``.
    vaccine_reference : Dict[str, Any]
        Maps vaccine codes to a single disease name or list of disease names.

    Returns
    -------
    List[Dict[str, Any]]
        One entry per unique vaccine name with
        ``{"vaccine": str, "diseases": List[str], "validity": str}``.
    """
    by_vaccine: Dict[str, List[str]] = {}
    for dose in date_doses:
        by_vaccine.setdefault(dose["vaccine"], []).append(dose["validity"])

    result: List[Dict[str, Any]] = []
    for vaccine, statuses in by_vaccine.items():
        if "unknown" in statuses:
            validity = "unknown"
        elif "valid" in statuses:
            validity = "valid"
        else:
            validity = "invalid"

        ref = vaccine_reference.get(vaccine, vaccine)
        diseases: List[str] = ref if isinstance(ref, list) else [ref]

        result.append({"vaccine": vaccine, "diseases": diseases, "validity": validity})

    return result


def compute_column_statuses(
    vaccines: List[Dict[str, Any]],
    chart_diseases_header: List[str],
) -> Dict[str, str]:
    """Compute per-column validity status for a set of vaccine entries.

    For each named disease in the header, collects the validity of all
    vaccines that contribute to that disease and collapses using
    ``unknown > mixed > valid > invalid`` precedence.  The ``"Other"``
    column captures any vaccine that contributes at least one disease
    not found in the named-disease set.

    ``"mixed"`` is produced when both ``"valid"`` and ``"invalid"``
    contribute to a column with no ``"unknown"`` — meaning different
    vaccines have conflicting validity for that column on this date.

    Parameters
    ----------
    vaccines : List[Dict[str, Any]]
        Vaccine entries from ``_deduplicate_vaccines_for_date``, each
        with ``{"vaccine": str, "diseases": List[str], "validity": str}``.
    chart_diseases_header : List[str]
        Ordered disease column headers.  ``"Other"`` (if present) acts
        as a catch-all for unmapped diseases.

    Returns
    -------
    Dict[str, str]
        Column name → one of ``"valid"``, ``"invalid"``, ``"unknown"``,
        or ``"mixed"``.  Only columns with at least one contributing
        vaccine are included.
    """
    named = {d for d in chart_diseases_header if d != "Other"}
    has_other_col = "Other" in chart_diseases_header

    column_statuses: Dict[str, List[str]] = {}

    for vax in vaccines:
        for disease in vax["diseases"]:
            if disease in named:
                column_statuses.setdefault(disease, []).append(vax["validity"])
        if has_other_col and any(d not in named for d in vax["diseases"]):
            column_statuses.setdefault("Other", []).append(vax["validity"])

    result: Dict[str, str] = {}
    for col, statuses in column_statuses.items():
        has_unknown = "unknown" in statuses
        has_valid = "valid" in statuses
        has_invalid = "invalid" in statuses
        if has_unknown:
            result[col] = "unknown"
        elif has_valid and has_invalid:
            result[col] = "mixed"
        elif has_valid:
            result[col] = "valid"
        else:
            result[col] = "invalid"

    return result


def _split_into_rows(
    vaccines: List[Dict[str, Any]],
    chart_diseases_header: List[str],
) -> List[Dict[str, Any]]:
    """Recursively split vaccines into rows so that no column has a mixed status.

    When ``compute_column_statuses`` finds a ``"mixed"`` column, the
    vaccines are partitioned: all ``"valid"`` vaccines go to the first
    row (guaranteed non-mixed since they share no status conflicts with
    the remaining set), and all ``"invalid"``/``"unknown"`` vaccines
    recurse as the second row.  Because the second row contains no
    ``"valid"`` vaccines, it can never produce ``"mixed"``; recursion
    always terminates within one additional level.

    Parameters
    ----------
    vaccines : List[Dict[str, Any]]
        Vaccine entries for a single date (same shape as
        ``_deduplicate_vaccines_for_date`` output).
    chart_diseases_header : List[str]
        Header order; the first mixed column in this order triggers the
        split.

    Returns
    -------
    List[Dict[str, Any]]
        One or more ``{"vaccines": List[Dict], "columns": Dict[str, str]}``
        dicts.  All column statuses are non-mixed.
    """
    columns = compute_column_statuses(vaccines, chart_diseases_header)

    mixed_col = next(
        (col for col in chart_diseases_header if columns.get(col) == "mixed"),
        None,
    )

    if mixed_col is None:
        return [{"vaccines": vaccines, "columns": columns}]

    row1_vaccines = [v for v in vaccines if v["validity"] == "valid"]
    row2_vaccines = [v for v in vaccines if v["validity"] != "valid"]

    row1_columns = compute_column_statuses(row1_vaccines, chart_diseases_header)
    return [{"vaccines": row1_vaccines, "columns": row1_columns}] + _split_into_rows(
        row2_vaccines, chart_diseases_header
    )


def build_received_rows(
    received_agents: Any,
    replace_unspecified: List[str],
    vaccine_reference: Dict[str, Any],
    chart_diseases_header: List[str],
    show_validity_markers: bool = False,
) -> List[Dict[str, Any]]:
    """Parse imms_given into display rows with pre-computed per-column validity.

    Orchestrates ``parse_dose_segments`` → ``_deduplicate_vaccines_for_date``
    → ``_split_into_rows`` for each administration date.  Dates whose
    vaccines would produce a ``"mixed"`` column status are split into
    separate rows: valid vaccines on the first row, others on subsequent
    rows.  The ``date_rowspan`` field carries the row-merge count so that
    Typst can render a single merged date cell spanning all rows of a date.

    Parameters
    ----------
    received_agents : Any
        Raw imms_given cell value.
    replace_unspecified : List[str]
        Vaccine names to suppress.
    vaccine_reference : Dict[str, Any]
        Vaccine-to-disease mapping.
    chart_diseases_header : List[str]
        Ordered disease column headers (used for column assignment and
        split ordering).

    Returns
    -------
    List[Dict[str, Any]]
        Flat list of display rows, each with::

            {
                "date_given":   str,            # ISO date
                "date_rowspan": int,            # N on first row, 0 on continuations
                "vaccines":     List[str],      # display vaccine names for this row
                "columns":      Dict[str, str], # column name → validity status
            }
    """
    flat = parse_dose_segments(received_agents, replace_unspecified)
    if not flat:
        return []

    by_date: Dict[str, List[Dict[str, str]]] = {}
    for dose in flat:
        by_date.setdefault(dose["date_given"], []).append(
            {"vaccine": dose["vaccine"], "validity": dose["validity"]}
        )

    rows: List[Dict[str, Any]] = []
    for date, doses in by_date.items():
        vaccines = _deduplicate_vaccines_for_date(doses, vaccine_reference)
        if show_validity_markers:
            date_rows = _split_into_rows(vaccines, chart_diseases_header)
        else:
            columns = compute_column_statuses(vaccines, chart_diseases_header)
            date_rows = [{"vaccines": vaccines, "columns": columns}]
        n = len(date_rows)
        for i, row in enumerate(date_rows):
            rows.append({
                "date_given": date,
                "date_rowspan": n if i == 0 else 0,
                "vaccines": [v["vaccine"] for v in row["vaccines"]],
                "columns": row["columns"],
            })

    return rows


def build_preprocess_result(
    df: pd.DataFrame,
    language: str | None,
    vaccine_reference: Dict[str, Any],
    replace_unspecified: List[str],
    config_path: Path | None = None,
    catalog: Optional[NoticeVersionCatalog] = None,
    manifest: Optional[Dict[str, ManifestRow]] = None,
) -> Tuple[PreprocessResult, Optional[ReconciliationResult]]:
    """Normalize client data and produce the structured preprocessing artifact.

    Orchestrates all per-dataset and per-client normalization: column
    mapping, sorting, sequence assignment, dataset-level validity
    classification, age calculation, vaccine history parsing, and disease
    enrichment. The resulting ``PreprocessResult`` is the sole artifact
    consumed by all downstream pipeline steps.

    Parameters
    ----------
    df : pd.DataFrame
        Raw input DataFrame, typically loaded from an Excel or CSV file.
        Must have lower_snake_case column names matching the input schema.
    language : str
        Language code for this batch (``"en"`` or ``"fr"``). Stored on
        every ``ClientRecord`` and used to format display dates.
    vaccine_reference : Dict[str, Any]
        Maps vaccine codes to disease names. Passed through to
        ``enrich_grouped_records``.
    replace_unspecified : List[str]
        Vaccine names to suppress from immunization history. Passed
        through to ``build_received_rows``.
    config_path : Path, optional
        Path to ``parameters.yaml``. Defaults to the repository configuration.

    Returns
    -------
    PreprocessResult
        Contains a list of ``ClientRecord`` objects (one per input row,
        sorted by school → last name → first name → client ID) and a
        list of warning strings for data-quality issues discovered during
        processing.

    Raises
    ------
    ValueError
        If ``classify_dataset_validity`` returns ``"mixed"`` and
        ``show_validity_markers`` is ``True`` in ``parameters.yaml``.
        This indicates the source data is structurally inconsistent and
        cannot be displayed reliably.
    ValueError
        If any required columns are missing from ``df`` (raised by the
        underlying ``normalize_dataframe`` call).

    Notes
    -----
    - Reads ``config_path`` on every call to obtain ``date_notice_delivery``,
      ``chart_diseases_header``, ``preprocess.include_dose``, and
      ``preprocess.show_validity_markers``. If no path is provided,
      ``PARAMETERS_PATH`` (``config/parameters.yaml``) is used. A missing file
      is treated as empty config (all defaults apply).
    - Warns (does not raise) for: missing board name, missing date of
      birth, duplicate client IDs, ``all_absent`` validity when
      ``show_validity_markers`` is ``True``, ``mixed`` validity when
      ``show_validity_markers`` is ``False``.
    """
    warnings: set[str] = set()
    working = normalize_dataframe(df)

    # Load parameters for date_notice_delivery and chart_diseases_header
    parameters_path = config_path if config_path is not None else PARAMETERS_PATH
    params = {}
    if parameters_path.exists():
        params = yaml.safe_load(parameters_path.read_text(encoding="utf-8")) or {}
    date_notice_delivery: Optional[str] = params.get("date_notice_delivery")
    chart_diseases_header: List[str] = params.get("chart_diseases_header", [])
    preprocess_cfg: Dict[str, Any] = params.get("preprocess", {})
    include_dose: bool = preprocess_cfg.get("include_dose", False)
    show_validity_markers: bool = preprocess_cfg.get("show_validity_markers", False)

    # Manifest-mode versioning settings
    notice_versioning_cfg: Dict[str, Any] = params.get("notice_versioning", {})
    allow_unassigned: bool = notice_versioning_cfg.get("allow_unassigned", False)
    extra_manifest_rows: str = notice_versioning_cfg.get("extra_manifest_rows", "error")

    working["school_id"] = working.apply(
        lambda row: synthesize_identifier(
            row.get("school_id", ""), row["school_name"], "sch"
        ),
        axis=1,
    )
    working["board_id"] = working.apply(
        lambda row: synthesize_identifier(
            row.get("board_id", ""), row.get("board_name", ""), "brd"
        ),
        axis=1,
    )

    if (working["board_name"] == "").any():
        affected = (
            working.loc[working["board_name"] == "", "school_name"].unique().tolist()
        )
        warnings.add(
            "Missing board name for: " + ", ".join(sorted(filter(None, affected)))
            if affected
            else "Missing board name for one or more schools."
        )

    sorted_df = working.sort_values(
        by=["school_name", "last_name", "first_name", "client_id"],
        kind="stable",
    ).reset_index(drop=True)
    sorted_df["sequence"] = [f"{idx + 1:05d}" for idx in range(len(sorted_df))]

    validity_coverage = classify_dataset_validity(sorted_df["imms_given"])
    if validity_coverage == "mixed":
        if show_validity_markers:
            raise ValueError(
                "Dataset contains a mix of records with and without validity indicators. "
                "Cannot display validity markers reliably. "
                "Either fix the source data or set show_validity_markers: false."
            )
        warnings.add(
            "Dataset contains records both with and without validity indicators. "
            "Validity markers are disabled; output is unaffected."
        )
    elif validity_coverage == "all_absent" and show_validity_markers:
        warnings.add(
            "show_validity_markers is enabled but no validity data was detected in the dataset. "
            "Default indicators will be used."
        )

    # Determine first-pass language: in manifest mode language arg is None,
    # so fall back to catalog default for DOB formatting on the first pass.
    first_pass_language: str = language or (
        catalog.default_language if catalog is not None else "en"
    )

    clients: List[ClientRecord] = []
    for row in sorted_df.itertuples(index=False):
        client_id = str(row.client_id)  # type: ignore[attr-defined]
        sequence = row.sequence  # type: ignore[attr-defined]
        dob_iso = (
            row.date_of_birth.strftime("%Y-%m-%d")  # type: ignore[attr-defined]
            if pd.notna(row.date_of_birth)  # type: ignore[attr-defined]
            else None
        )
        if dob_iso is None:
            warnings.add(f"Missing date of birth for client {client_id}")

        language_enum = Language.from_string(first_pass_language)
        formatted_dob = (
            convert_date_string(dob_iso, locale="fr")
            if language_enum == Language.FRENCH and dob_iso
            else (convert_date_string(dob_iso, locale="en") if dob_iso else None)
        )
        vaccines_due = process_vaccines_due(row.overdue_disease, "disease")  # type: ignore[attr-defined]
        vaccines_due_agent = process_vaccines_due(row.overdue_agent, "agent")  # type: ignore[attr-defined]
        
        vaccines_due_list = [
            item.strip() for item in vaccines_due.split(",") if item.strip()
        ]

        vaccines_due_agent_list = [
            item.strip() for item in vaccines_due_agent.split(",") if item.strip()
        ]

        for item in vaccines_due_list:
            disease, dose = split_vaccine_due_entry(item)
            if dose == "":
                warnings.add(
                    f"Blank overdue dose number for client {client_id}: {disease}. "
                    "Displaying disease without a dose number."
                )

        if include_dose:
            vaccines_due_list = format_vaccine_due_list(vaccines_due_list)
        else:
            vaccines_due_list = hide_vaccine_due_doses(vaccines_due_list)

            
        received = build_received_rows(
            row.imms_given,  # type: ignore[attr-defined]
            replace_unspecified,
            vaccine_reference,
            chart_diseases_header,
            show_validity_markers,
        )

        postal_code = row.postal_code if row.postal_code else "Not provided"  # type: ignore[attr-defined]
        address_line = " ".join(
            filter(None, [row.street_address_line_1, row.street_address_line_2])  # type: ignore[attr-defined]
        ).strip()

        if dob_iso and date_notice_delivery:
            age = calculate_age_at_date(dob_iso, date_notice_delivery)
            over_16 = age >= 16
        else:
            age = None
            over_16 = False

        person = {
            "first_name": row.first_name or "",  # type: ignore[attr-defined]
            "last_name": row.last_name or "",  # type: ignore[attr-defined]
            "date_of_birth": dob_iso or "",
            "date_of_birth_display": formatted_dob or "",
            "date_of_birth_iso": dob_iso or "",
            "age": str(age) or "",  # type: ignore[attr-defined]
            "over_16": over_16,
        }

        school = {
            "name": row.school_name,  # type: ignore[attr-defined]
            "id": row.school_id,  # type: ignore[attr-defined]
        }

        board = {
            "name": row.board_name or "",  # type: ignore[attr-defined]
            "id": row.board_id,  # type: ignore[attr-defined]
        }

        contact = {
            "street": address_line,
            "city": row.city,  # type: ignore[attr-defined]
            "province": row.province,  # type: ignore[attr-defined]
            "postal_code": postal_code,
        }

        client = ClientRecord(
            sequence=sequence,
            client_id=client_id,
            language=first_pass_language,
            person=person,
            school=school,
            board=board,
            contact=contact,
            vaccines_due=vaccines_due if vaccines_due else None,
            vaccines_due_list=vaccines_due_list if vaccines_due_list else None,
            vaccines_due_agent_list=vaccines_due_agent_list if vaccines_due_agent_list else None,
            received=received if received else None,
            metadata={
                "version_id": row.version_id or None,  # type: ignore[attr-defined]
            },
        )

        clients.append(client)

    # Detect and warn about duplicate client IDs
    client_id_counts: dict[str, int] = {}
    for client in clients:
        client_id_counts[client.client_id] = (
            client_id_counts.get(client.client_id, 0) + 1
        )

    duplicates = {cid: count for cid, count in client_id_counts.items() if count > 1}
    if duplicates:
        for cid in sorted(duplicates.keys()):
            warnings.add(
                f"Duplicate client ID '{cid}' found {duplicates[cid]} times. "
                "Later records will overwrite earlier ones in generated notices."
            )

    # --- Fixed mode (no manifest) ---
    if catalog is None or manifest is None:
        return (
            PreprocessResult(clients=clients, warnings=list(warnings)),
            None,
        )

    # --- Manifest mode ---
    reconciliation_result = reconcile(
        clients, manifest, catalog, allow_unassigned, extra_manifest_rows
    )

    if has_errors(reconciliation_result, extra_manifest_rows):
        # Build a summary string for the error message (no PII).
        lines = [
            "Manifest preflight failed:",
            f"  Missing clients (no manifest row): {len(reconciliation_result.missing_clients)}",
            f"  Unknown versions: {len(reconciliation_result.unknown_versions)}",
            f"  Eligibility conflicts: {len(reconciliation_result.eligibility_conflicts)}",
            f"  Extra manifest rows: {len(reconciliation_result.extra_rows)} "
            f"(policy: {extra_manifest_rows})",
        ]
        raise ValueError("\n".join(lines))

    # Rebuild each ClientRecord with resolved notice values.
    rebuilt: List[ClientRecord] = []
    for first_pass_client in clients:
        cid = first_pass_client.client_id
        row_m = manifest.get(cid)

        if row_m is not None:
            resolved_lang = row_m.language or catalog.default_language
            resolved_version = row_m.notice_version
            exp_id = row_m.experiment_id
            exp_arm = row_m.experiment_arm
            source = "manifest"
        else:
            # allow_unassigned=True (has_errors would have caught False case)
            resolved_lang = catalog.default_language
            resolved_version = catalog.default_version
            exp_id = None
            exp_arm = None
            source = "default"

        catalog_version = catalog.versions[resolved_version]
        resolved = ResolvedNotice(
            notice_version=resolved_version,
            notice_kind=catalog_version.kind.value,
            language=resolved_lang,
            experiment_id=exp_id,
            experiment_arm=exp_arm,
            assignment_source=source,
        )

        # Safety net — reconcile already caught conflicts before we reach here.
        validate_eligibility(first_pass_client, resolved, catalog)

        rebuilt_client = dataclasses.replace(
            first_pass_client,
            language=resolved_lang,
            metadata={"resolved_notice": dataclasses.asdict(resolved)},
        )
        rebuilt.append(rebuilt_client)

    return (
        PreprocessResult(clients=rebuilt, warnings=list(warnings)),
        reconciliation_result,
    )


def run_phix_validation(
    df: pd.DataFrame,
    output_dir: Path,
) -> tuple[pd.DataFrame, list[str]]:
    """Validate school names against the PHIX mapping file.

    Reads ``phix_validation`` config from ``parameters.yaml``. Returns the
    DataFrame unchanged (with no warnings) when validation is disabled or
    ``mapping_file`` is not set.

    Parameters
    ----------
    df:
        Normalized DataFrame (output of ``check_addresses_complete``).
    output_dir:
        Directory where result CSVs (``phix_exact.csv``, etc.) are written.

    Returns
    -------
    tuple[DataFrame, list[str]]
        Enriched DataFrame and a (possibly empty) list of warning strings.
    """
    config = yaml.safe_load(PARAMETERS_PATH.read_text(encoding="utf-8")) or {}
    phix_config = config.get("phix_validation", {})

    if not phix_config.get("enabled", False):
        return df, []

    mapping_file = phix_config.get("mapping_file", "")
    if not mapping_file:
        LOG.warning("phix_validation.enabled is true but mapping_file is not set.")
        return df, []

    target_phu = phix_config.get("target_phu", "")
    if not target_phu:
        LOG.warning("phix_validation.target_phu is not set — skipping PHIX validation.")
        return df, []

    from . import validate_phix  # local import avoids circular dependency at module load

    mapping_path = Path(mapping_file)
    if not mapping_path.is_absolute():
        mapping_path = (SCRIPT_DIR.parent / mapping_file).resolve()

    return validate_phix.validate_schools(
        df=df,
        mapping_path=mapping_path,
        target_phu=target_phu,
        output_dir=output_dir,
        unmatched_behavior=phix_config.get("unmatched_behavior", "warn"),
        column_prefix=phix_config.get("column_prefix", "phix_"),
    )


def write_artifact(
    output_dir: Path,
    language: str,
    run_id: str,
    result: PreprocessResult,
    assignment_mode: str = "fixed",
    default_version: Optional[str] = None,
) -> Path:
    """Write preprocessed result to JSON artifact file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    artifact_payload = ArtifactPayload(
        run_id=run_id,
        language=language,
        clients=result.clients,
        warnings=result.warnings,
        created_at=datetime.now(timezone.utc).isoformat(),
        total_clients=len(result.clients),
        assignment_mode=assignment_mode,
        default_version=default_version,
    )

    payload_dict = {
        "run_id": artifact_payload.run_id,
        "language": artifact_payload.language,
        "created_at": artifact_payload.created_at,
        "total_clients": artifact_payload.total_clients,
        "assignment_mode": artifact_payload.assignment_mode,
        "default_version": artifact_payload.default_version,
        "warnings": artifact_payload.warnings,
        "clients": [
            {
                "sequence": client.sequence,
                "client_id": client.client_id,
                "language": client.language,
                "person": {
                    "first_name": client.person["first_name"],
                    "last_name": client.person["last_name"],
                    "date_of_birth": client.person["date_of_birth"],
                    "date_of_birth_display": client.person["date_of_birth_display"],
                    "date_of_birth_iso": client.person["date_of_birth_iso"],
                    "age": client.person["age"],
                    "over_16": client.person["over_16"],
                },
                "school": {
                    "name": client.school["name"],
                    "id": client.school["id"],
                },
                "board": {
                    "name": client.board["name"],
                    "id": client.board["id"],
                },
                "contact": {
                    "street": client.contact["street"],
                    "city": client.contact["city"],
                    "province": client.contact["province"],
                    "postal_code": client.contact["postal_code"],
                },
                "vaccines_due": client.vaccines_due,
                "vaccines_due_list": client.vaccines_due_list or [],
                "vaccines_due_agent_list": client.vaccines_due_agent_list or [],
                "received": client.received or [],
                "metadata": client.metadata,
            }
            for client in artifact_payload.clients
        ],
    }

    artifact_path = output_dir / f"preprocessed_clients_{run_id}.json"
    artifact_path.write_text(json.dumps(payload_dict, indent=2), encoding="utf-8")
    LOG.info("Wrote normalized artifact to %s", artifact_path)
    return artifact_path


def write_assignment_metadata(
    metadata_dir: Path,
    run_id: str,
    catalog: "NoticeVersionCatalog",
    reconciliation_result: "ReconciliationResult",
    clients: List[ClientRecord],
) -> Path:
    """Write per-client assignment metadata to a JSON file (manifest mode only).

    Records contain only client_id, sequence, and resolved notice fields.
    No name, date_of_birth, address, school name, or balancing attributes.
    """
    metadata_dir.mkdir(parents=True, exist_ok=True)

    # Compute simple per-version and per-language totals from clients.
    counts_by_version: Dict[str, int] = {}
    counts_by_language: Dict[str, int] = {}
    records = []
    for client in clients:
        resolved = client.metadata.get("resolved_notice", {})
        version = resolved.get("notice_version", "")
        lang = resolved.get("language", "")
        counts_by_version[version] = counts_by_version.get(version, 0) + 1
        counts_by_language[lang] = counts_by_language.get(lang, 0) + 1
        records.append({
            "client_id": client.client_id,
            "sequence": client.sequence,
            "notice_version": version,
            "notice_kind": resolved.get("notice_kind", ""),
            "language": lang,
            "experiment_id": resolved.get("experiment_id"),
            "experiment_arm": resolved.get("experiment_arm"),
            "assignment_source": resolved.get("assignment_source", ""),
        })

    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "assignment_mode": "manifest",
        "default_version": catalog.default_version,
        "default_language": catalog.default_language,
        "total_clients": len(clients),
        "counts_by_version": counts_by_version,
        "counts_by_language": counts_by_language,
        "records": records,
    }

    out_path = metadata_dir / f"notice_assignments_{run_id}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    LOG.info("Wrote assignment metadata to %s", out_path)
    return out_path


if __name__ == "__main__":
    import sys

    print(
        "⚠️  Direct invocation: This module is typically executed via orchestrator.py.\n"
        "   Re-running a single step is valid when pipeline artifacts are retained on disk,\n"
        "   allowing you to skip earlier steps and regenerate output.\n"
        "   Note: Output will overwrite any previous files.\n"
        "\n"
        "   For typical usage, run: uv run viper <input> <language>\n",
        file=sys.stderr,
    )
    sys.exit(1)
