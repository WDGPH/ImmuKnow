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

import json
import logging
import re
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from string import Formatter
from typing import Any, Dict, List, Optional, overload
import pandas as pd
import yaml
from babel.dates import format_date
from rapidfuzz import fuzz, process

from .data_models import (
    ArtifactPayload,
    ClientRecord,
    PreprocessResult,
)
from .enums import Language
from .translation_helpers import normalize_disease

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"
VACCINE_REFERENCE_PATH = CONFIG_DIR / "vaccine_reference.json"
PARAMETERS_PATH = CONFIG_DIR / "parameters.yaml"

LOG = logging.getLogger(__name__)

_FORMATTER = Formatter()

REPLACE_UNSPECIFIED = [
    "-unspecified",
    "unspecified",
    "Not Specified",
    "Not specified",
    "Not Specified-unspecified",
]

REQUIRED_COLUMNS = [
    "SCHOOL NAME",
    "CLIENT ID",
    "FIRST NAME",
    "LAST NAME",
    "DATE OF BIRTH",
    "CITY",
    "POSTAL CODE",
    "PROVINCE/TERRITORY",
    "OVERDUE DISEASE",
    "IMMS GIVEN",
    "STREET ADDRESS LINE 1",
    "STREET ADDRESS LINE 2",
]

THRESHOLD = 80


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


def check_addresses_complete(df: pd.DataFrame) -> pd.DataFrame:
    """
    Check if address fields are complete in the DataFrame.

    Adds a boolean 'address_complete' column based on presence of
    street address, city, province, and postal code.
    """

    df = df.copy()

    # Normalize text fields: convert to string, strip whitespace, convert "" to NA
    address_cols = [
        "STREET_ADDRESS_LINE_1",
        "STREET_ADDRESS_LINE_2",
        "CITY",
        "PROVINCE",
        "POSTAL_CODE",
    ]

    for col in address_cols:
        df[col] = df[col].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA})

    # Build combined address line
    df["ADDRESS"] = (
        df["STREET_ADDRESS_LINE_1"].fillna("")
        + " "
        + df["STREET_ADDRESS_LINE_2"].fillna("")
    ).str.strip()

    df["ADDRESS"] = df["ADDRESS"].replace({"": pd.NA})

    # Check completeness
    df["address_complete"] = (
        df["ADDRESS"].notna()
        & df["CITY"].notna()
        & df["PROVINCE"].notna()
        & df["POSTAL_CODE"].notna()
    )

    if not df["address_complete"].all():
        incomplete_count = (~df["address_complete"]).sum()
        LOG.warning(
            "There are %d records with incomplete address information.",
            incomplete_count,
        )
        print(
            f"⚠️ There are {incomplete_count} records with incomplete address information."
        )

        incomplete_records = df.loc[~df["address_complete"]]

        incomplete_path = Path("output/incomplete_addresses.csv")
        incomplete_records.to_csv(incomplete_path, index=False)
        LOG.info("Incomplete address records written to %s", incomplete_path)
        print(f"Incomplete address records written to {incomplete_path}")

    # Return only rows with complete addresses
    return df.loc[df["address_complete"]].drop(columns=["address_complete"])


def check_client_info_complete(df: pd.DataFrame) -> pd.DataFrame:
    """
    Check if client fields are complete in the DataFrame.

    Adds a boolean 'client_info_complete' column based on presence of
    first name, last name, DOB, school name, overdue disease, immunizations given, and client ID.

    Check that client ID is valid (10 digits), and recover if in float format.
    """

    df = df.copy()

    # Normalize text fields: convert to string, strip whitespace, convert "" to NA
    client_info_cols = [
        "SCHOOL_NAME",
        "CLIENT_ID",
        "FIRST_NAME",
        "LAST_NAME",
        "DATE_OF_BIRTH",
        "OVERDUE_DISEASE",
        "IMMS_GIVEN",
    ]

    for col in client_info_cols:
        df[col] = df[col].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA})

    # Check client ID formatting - expects 10-digit number, recover if in float format with '.0'
    df["CLIENT_ID"] = df["CLIENT_ID"].str.replace(r"\.0$", "", regex=True)
    df["client_id_valid"] = df["CLIENT_ID"].str.isdigit() & (
        df["CLIENT_ID"].str.len() == 10
    )
    if len(df[~df["client_id_valid"]]) > 0:
        print(f"Invalid client IDs: {len(df[~df['client_id_valid']])}")

    # Check completeness
    df["client_info_complete"] = (
        df["FIRST_NAME"].notna()
        & df["LAST_NAME"].notna()
        & df["CLIENT_ID"].notna()
        & df["DATE_OF_BIRTH"].notna()
        & df["OVERDUE_DISEASE"].notna()
        & df["IMMS_GIVEN"].notna()
        & df["client_id_valid"]
    )

    df = df.drop(columns=["client_id_valid"])

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

        incomplete_path = Path("output/incomplete_clients.csv")
        incomplete_records.to_csv(incomplete_path, index=False)
        LOG.info("Incomplete client records written to %s", incomplete_path)
        print(f"Incomplete client records written to {incomplete_path}")

    # Return only rows with complete addresses
    return df.loc[df["client_info_complete"]].drop(columns=["client_info_complete"])


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


def over_16_check(date_of_birth, date_notice_delivery):
    """Check if a client is over 16 years old on notice delivery date.

    Parameters
    ----------
    date_of_birth : str
        Date of birth in YYYY-MM-DD format.
    date_notice_delivery : str
        Notice delivery date in YYYY-MM-DD format.

    Returns
    -------
    bool
        True if the client is over 16 years old on date_notice_delivery, False otherwise.
    """

    birth_datetime = datetime.strptime(date_of_birth, "%Y-%m-%d")

    if isinstance(date_notice_delivery, datetime):
        date_notice_delivery = str(date_notice_delivery.date())

    delivery_datetime = datetime.strptime(str(date_notice_delivery), "%Y-%m-%d")

    age = delivery_datetime.year - birth_datetime.year

    # Adjust if birthday hasn't occurred yet in the DOV month
    if (delivery_datetime.month < birth_datetime.month) or (
        delivery_datetime.month == birth_datetime.month
        and delivery_datetime.day < birth_datetime.day
    ):
        age -= 1

    return age >= 16


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
            df = pd.read_excel(file_path, engine="openpyxl", dtype={"CLIENT ID": str})
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


def normalize(col: str) -> str:
    """Normalize formatting prior to matching."""

    # Trim whitespaces
    col_normalized = col.lower().strip().replace("_", " ").replace("-", " ")

    # Check to see if double whitespace
    col_normalized = re.sub(r"\s+", " ", col_normalized)

    return col_normalized


def map_columns(df: pd.DataFrame, required_columns=REQUIRED_COLUMNS):
    """
    Map dataframe columns to a set of required column names using fuzzy matching.
    Parameters
    ----------
    df : pandas.DataFrame
        Input dataframe whose columns will be matched and optionally renamed.
    required_columns : Sequence[str], optional
        Sequence of expected/required column names to match against. Defaults to REQUIRED_COLUMNS.
    Returns
    -------
    tuple[pandas.DataFrame, dict]
        A tuple (renamed_df, col_map) where `renamed_df` is `df` with columns renamed according to successful matches,
        and `col_map` is a dict mapping original column names (keys) to matched required column names (values).
    Behavior
    --------
    - Normalizes input column names and required column names using `normalize(...)` before matching.
    - For each normalized input column, finds the best fuzzy match among normalized `required_columns` using
      `process.extractOne(..., scorer=fuzz.partial_ratio)`.
    - If the best match score is >= 80 (threshold in the implementation), the original input column name is mapped to the
      corresponding required column name; the mapping is recorded and the dataframe is renamed accordingly.
    - A debug line is printed for each accepted match: "Matching '<normalized_input>' to '<best_match>' with score <score>".
    - Columns with a best match score < 80 are ignored (not included in `col_map`); matches with score 0 are effectively dropped.
    - The code resolves the original column name by locating the first column whose normalized form equals the normalized input.
      If multiple original columns normalize to the same value, the first encountered is used.
    Notes
    -----
    - The function depends on external helpers: `normalize`, `process.extractOne`, and `fuzz.partial_ratio`.
    - The match threshold (80) is adjustable; lowering it makes matching more permissive, raising it makes it stricter.
    - A `StopIteration` may occur if a normalized input column cannot be resolved back to an original column name.
    - `required_columns` should be an iterable of strings; `df.columns` are expected to be convertible to strings.
    Examples
    --------
    # Example usage (illustrative only):
    # renamed_df, mapping = map_columns(df, required_columns=['state', 'date', 'count'])
    """
    input_cols = df.columns
    col_map = {}

    # Normalize input columns for matching
    normalized_input_cols = [normalize(c) for c in input_cols]

    # Check each input column against required columns
    for input_col in normalized_input_cols:
        col_name, score, index = process.extractOne(
            query=input_col,
            choices=[normalize(req) for req in required_columns],
            scorer=fuzz.partial_ratio,
        )

        # Remove column if it has a score of 0
        best_match = required_columns[index]

        if score >= THRESHOLD:  # adjustable threshold
            # Map the original column name, not the normalized one
            actual_in_col = next(c for c in input_cols if normalize(c) == input_col)
            # col_map[actual_in_col] = best_match

            # print colname and score for debugging
            print(f"Matching '{input_col}' to '{best_match}' with score {score}")

            # Check if column already has an assigned mapping
            if best_match not in col_map.values():
                print(
                    f"The value {best_match} does not exist in the dictionary - adding value."
                )
                col_map[actual_in_col] = best_match
            # else:
            #     print(f"The value {best_match} does not exist.")

    return df.rename(columns=col_map), col_map


@overload
def filter_columns(
    df: pd.DataFrame, required_columns: list[str] = REQUIRED_COLUMNS
) -> pd.DataFrame: ...


@overload
def filter_columns(
    df: None, required_columns: list[str] = REQUIRED_COLUMNS
) -> None: ...


def filter_columns(
    df: pd.DataFrame | None,
    required_columns: list[str] = REQUIRED_COLUMNS,
    keep_columns: list[str] = [],
) -> pd.DataFrame | None:
    """Filter dataframe to only include required columns."""
    if df is None or df.empty:
        return df

    return df[[col for col in df.columns if col in required_columns + keep_columns]]


def ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names and validate that all required columns are present.

    Standardizes column names to uppercase and underscores, then validates that
    the DataFrame contains all required columns for immunization processing.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame with client data (column names may have mixed case/spacing).

    Returns
    -------
    pd.DataFrame
        Copy of input DataFrame with normalized column names.

    Raises
    ------
    ValueError
        If any required columns are missing from the DataFrame.
    """
    df = df.copy()
    df.columns = [col.strip().upper() for col in df.columns]
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns: {missing} \n Found columns: {list(df.columns)} "
        )

    df.rename(columns=lambda x: x.replace(" ", "_"), inplace=True)
    df.rename(columns={"PROVINCE/TERRITORY": "PROVINCE"}, inplace=True)
    return df


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize data types and fill missing values in the input DataFrame.

    Ensures consistent data types across all columns:
    - String columns are filled with empty strings and trimmed
    - DATE_OF_BIRTH is converted to datetime
    - AGE is converted to numeric (if present)
    - Missing board/school data is initialized with empty dicts

    This normalization is critical for downstream processing as it ensures
    every client record has the expected structure.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame with raw client data.

    Returns
    -------
    pd.DataFrame
        Copy of DataFrame with normalized types and filled values.
    """
    working = df.copy()
    string_columns = [
        "SCHOOL_NAME",
        "FIRST_NAME",
        "LAST_NAME",
        "CITY",
        "PROVINCE",
        "POSTAL_CODE",
        "STREET_ADDRESS_LINE_1",
        "STREET_ADDRESS_LINE_2",
        "SCHOOL_TYPE",
        "BOARD_NAME",
        "BOARD_ID",
        "SCHOOL_ID",
        "UNIQUE_ID",
    ]

    for column in string_columns:
        if column not in working.columns:
            working[column] = ""
        working[column] = working[column].fillna(" ").astype(str).str.strip()

    working["DATE_OF_BIRTH"] = pd.to_datetime(working["DATE_OF_BIRTH"], errors="coerce")
    if "AGE" in working.columns:
        working["AGE"] = pd.to_numeric(working["AGE"], errors="coerce")
    else:
        working["AGE"] = pd.NA

    if "BOARD_NAME" not in working.columns:
        working["BOARD_NAME"] = ""
    if "BOARD_ID" not in working.columns:
        working["BOARD_ID"] = ""
    if "SCHOOL_TYPE" not in working.columns:
        working["SCHOOL_TYPE"] = ""

    return working


def synthesize_identifier(existing: str, source: str, prefix: str) -> str:
    """Generate a deterministic identifier if one is not provided."""
    existing = (existing or "").strip()
    if existing:
        return existing

    base = (source or "").strip().lower() or "unknown"
    digest = sha1(base.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def process_vaccines_due(vaccines_due: Any, language: str) -> str:
    """Map overdue diseases to canonical disease names.

    Normalizes raw input disease strings to canonical disease names using
    config/disease_normalization.json. Returns a comma-separated string of
    canonical disease names.

    Parameters
    ----------
    vaccines_due : Any
        Raw string of comma-separated disease names from input.
    language : str
        Language code (e.g., "en", "fr"). Used for logging.

    Returns
    -------
    str
        Comma-separated string of canonical disease names (English).
        Empty string if input is empty or invalid.
    """
    if not isinstance(vaccines_due, str) or not vaccines_due.strip():
        return ""

    items: List[str] = []
    for token in vaccines_due.split(","):
        # Normalize: raw input -> canonical disease name
        normalized = normalize_disease(token.strip())
        items.append(normalized)

    # Filter empty items and clean quotes
    return ", ".join(
        item.replace("'", "").replace('"', "") for item in items if item.strip()
    )


def process_received_agents(
    received_agents: Any, replace_unspecified: List[str]
) -> List[Dict[str, Any]]:
    """Extract and normalize vaccination history from received_agents string."""
    if not isinstance(received_agents, str) or not received_agents.strip():
        return []

    pattern = re.compile(r"\w{3} \d{1,2}, \d{4} - [^,]+")
    matches = pattern.findall(received_agents)
    rows: List[Dict[str, Any]] = []

    for match in matches:
        date_str, vaccine = match.split(" - ", maxsplit=1)
        vaccine = vaccine.strip()
        if vaccine in replace_unspecified:
            continue
        date_iso = convert_date_iso(date_str.strip())
        rows.append({"date_given": date_iso, "vaccine": vaccine})

    rows.sort(key=lambda item: item["date_given"])
    grouped: List[Dict[str, Any]] = []
    for entry in rows:
        if not grouped or grouped[-1]["date_given"] != entry["date_given"]:
            grouped.append(
                {
                    "date_given": entry["date_given"],
                    "vaccine": [entry["vaccine"]],
                }
            )
        else:
            grouped[-1]["vaccine"].append(entry["vaccine"])

    return grouped


def enrich_grouped_records(
    grouped: List[Dict[str, Any]],
    vaccine_reference: Dict[str, Any],
    language: str,
    chart_diseases_header: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Enrich grouped vaccine records with disease information.

    If chart_diseases_header is provided, diseases not in the list are
    collapsed into the "Other" category.

    Parameters
    ----------
    grouped : List[Dict[str, Any]]
        Grouped vaccine records with date_given and vaccine list.
    vaccine_reference : Dict[str, Any]
        Map of vaccine codes to disease names.
    language : str
        Language code for logging.
    chart_diseases_header : List[str], optional
        List of diseases to include in chart. Diseases not in this list
        are mapped to "Other".

    Returns
    -------
    List[Dict[str, Any]]
        Enriched records with date_given, vaccine, and diseases fields.
    """
    enriched: List[Dict[str, Any]] = []
    for item in grouped:
        vaccines = [
            v.replace("-unspecified", "*").replace(" unspecified", "*")
            for v in item["vaccine"]
        ]
        diseases: List[str] = []
        for vaccine in vaccines:
            ref = vaccine_reference.get(vaccine, vaccine)
            if isinstance(ref, list):
                diseases.extend(ref)
            else:
                diseases.append(ref)

        # Collapse diseases not in chart to "Other"
        if chart_diseases_header:
            filtered_diseases: List[str] = []
            has_unmapped = False
            for disease in diseases:
                if disease in chart_diseases_header:
                    filtered_diseases.append(disease)
                else:
                    has_unmapped = True
            if has_unmapped and "Other" not in filtered_diseases:
                filtered_diseases.append("Other")
            diseases = filtered_diseases

        enriched.append(
            {
                "date_given": item["date_given"],
                "vaccine": vaccines,
                "diseases": diseases,
            }
        )
    return enriched


def build_preprocess_result(
    df: pd.DataFrame,
    language: str,
    vaccine_reference: Dict[str, Any],
    replace_unspecified: List[str],
) -> PreprocessResult:
    """Process and normalize client data into structured artifact.

    Calculates per-client age at time of delivery for determining
    communication recipient (parent vs. student).

    Filters received vaccine diseases to only include those in the
    chart_diseases_header configuration, mapping unmapped diseases
    to "Other".
    """
    warnings: set[str] = set()
    working = normalize_dataframe(df)

    # Load parameters for date_notice_delivery and chart_diseases_header
    params = {}
    if PARAMETERS_PATH.exists():
        params = yaml.safe_load(PARAMETERS_PATH.read_text(encoding="utf-8")) or {}
    date_notice_delivery: Optional[str] = params.get("date_notice_delivery")
    chart_diseases_header: List[str] = params.get("chart_diseases_header", [])

    working["SCHOOL_ID"] = working.apply(
        lambda row: synthesize_identifier(
            row.get("SCHOOL_ID", ""), row["SCHOOL_NAME"], "sch"
        ),
        axis=1,
    )
    working["BOARD_ID"] = working.apply(
        lambda row: synthesize_identifier(
            row.get("BOARD_ID", ""), row.get("BOARD_NAME", ""), "brd"
        ),
        axis=1,
    )

    if (working["BOARD_NAME"] == "").any():
        affected = (
            working.loc[working["BOARD_NAME"] == "", "SCHOOL_NAME"].unique().tolist()
        )
        warnings.add(
            "Missing board name for: " + ", ".join(sorted(filter(None, affected)))
            if affected
            else "Missing board name for one or more schools."
        )

    sorted_df = working.sort_values(
        by=["SCHOOL_NAME", "LAST_NAME", "FIRST_NAME", "CLIENT_ID"],
        kind="stable",
    ).reset_index(drop=True)
    sorted_df["SEQUENCE"] = [f"{idx + 1:05d}" for idx in range(len(sorted_df))]

    clients: List[ClientRecord] = []
    for row in sorted_df.itertuples(index=False):
        client_id = str(row.CLIENT_ID)  # type: ignore[attr-defined]
        sequence = row.SEQUENCE  # type: ignore[attr-defined]
        dob_iso = (
            row.DATE_OF_BIRTH.strftime("%Y-%m-%d")  # type: ignore[attr-defined]
            if pd.notna(row.DATE_OF_BIRTH)  # type: ignore[attr-defined]
            else None
        )
        if dob_iso is None:
            warnings.add(f"Missing date of birth for client {client_id}")

        language_enum = Language.from_string(language)
        formatted_dob = (
            convert_date_string(dob_iso, locale="fr")
            if language_enum == Language.FRENCH and dob_iso
            else (convert_date_string(dob_iso, locale="en") if dob_iso else None)
        )
        vaccines_due = process_vaccines_due(row.OVERDUE_DISEASE, language)  # type: ignore[attr-defined]
        vaccines_due_list = [
            item.strip() for item in vaccines_due.split(",") if item.strip()
        ]
        received_grouped = process_received_agents(row.IMMS_GIVEN, replace_unspecified)  # type: ignore[attr-defined]
        received = enrich_grouped_records(
            received_grouped, vaccine_reference, language, chart_diseases_header
        )

        postal_code = row.POSTAL_CODE if row.POSTAL_CODE else "Not provided"  # type: ignore[attr-defined]
        address_line = " ".join(
            filter(None, [row.STREET_ADDRESS_LINE_1, row.STREET_ADDRESS_LINE_2])  # type: ignore[attr-defined]
        ).strip()

        if not pd.isna(row.AGE):  # type: ignore[attr-defined]
            over_16 = bool(row.AGE >= 16)  # type: ignore[attr-defined]
        elif dob_iso and date_notice_delivery:
            over_16 = over_16_check(dob_iso, datetime.now())
        else:
            over_16 = False

        person = {
            "first_name": row.FIRST_NAME or "",  # type: ignore[attr-defined]
            "last_name": row.LAST_NAME or "",  # type: ignore[attr-defined]
            "date_of_birth": dob_iso or "",
            "date_of_birth_display": formatted_dob or "",
            "date_of_birth_iso": dob_iso or "",
            "age": str(row.AGE) if not pd.isna(row.AGE) else "",  # type: ignore[attr-defined]
            "over_16": over_16,
        }

        school = {
            "name": row.SCHOOL_NAME,  # type: ignore[attr-defined]
            "id": row.SCHOOL_ID,  # type: ignore[attr-defined]
        }

        board = {
            "name": row.BOARD_NAME or "",  # type: ignore[attr-defined]
            "id": row.BOARD_ID,  # type: ignore[attr-defined]
        }

        contact = {
            "street": address_line,
            "city": row.CITY,  # type: ignore[attr-defined]
            "province": row.PROVINCE,  # type: ignore[attr-defined]
            "postal_code": postal_code,
        }

        client = ClientRecord(
            sequence=sequence,
            client_id=client_id,
            language=language,
            person=person,
            school=school,
            board=board,
            contact=contact,
            vaccines_due=vaccines_due if vaccines_due else None,
            vaccines_due_list=vaccines_due_list if vaccines_due_list else None,
            received=received if received else None,
            metadata={
                "unique_id": row.UNIQUE_ID or None,  # type: ignore[attr-defined]
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

    return PreprocessResult(
        clients=clients,
        warnings=list(warnings),
    )


def write_artifact(
    output_dir: Path, language: str, run_id: str, result: PreprocessResult
) -> Path:
    """Write preprocessed result to JSON artifact file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create ArtifactPayload with rich metadata
    artifact_payload = ArtifactPayload(
        run_id=run_id,
        language=language,
        clients=result.clients,
        warnings=result.warnings,
        created_at=datetime.now(timezone.utc).isoformat(),
        total_clients=len(result.clients),
    )

    # Serialize to JSON (clients are dataclasses, so convert to dict)
    payload_dict = {
        "run_id": artifact_payload.run_id,
        "language": artifact_payload.language,
        "created_at": artifact_payload.created_at,
        "total_clients": artifact_payload.total_clients,
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
