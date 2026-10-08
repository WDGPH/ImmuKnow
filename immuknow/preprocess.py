"""Read source records, apply health rules, and build the prepared client list."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from datetime import date, datetime, timezone
from hashlib import sha1
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import pandas as pd
from frictionless import Detector, Schema
from frictionless import validate as fl_validate

from . import validate_schools
from .assignment_manifest import (
    ManifestRow,
    ReconciliationError,
    ReconciliationResult,
    has_errors,
    reconcile,
)
from .data_models import (
    ClientRecord,
    PreprocessResult,
)
from .notice_versioning import NoticeVersionCatalog, attach_notice

CONFIG_DIR = Path(str(files("immuknow").joinpath("config")))
VACCINE_REFERENCE_PATH = CONFIG_DIR / "vaccine_reference.json"

LOG = logging.getLogger(__name__)

UNSPECIFIED_AGENTS = [
    "-unspecified",
    "unspecified",
    "Not Specified",
    "Not specified",
    "Not Specified-unspecified",
]

INPUT_SCHEMA_PATH = Path(str(files("immuknow").joinpath("schemas/input_schema.json")))


def prepare_clients(
    input_path: Path,
    output_dir: Path,
    config: dict,
    config_dir: Path,
    catalog: NoticeVersionCatalog,
    manifest: dict[str, ManifestRow],
    selected_notice: tuple[str, str] | None,
) -> tuple[PreprocessResult, ReconciliationResult]:
    """Prepare the cohort and return its assignment findings for run reporting.

    Raises ReconciliationError with findings when assignments fail preflight.
    """
    frame = read_input(input_path)
    frame = check_addresses_complete(frame, drop_incomplete=True, output_dir=output_dir)
    frame = check_client_info_complete(
        frame,
        drop_incomplete=True,
        output_dir=output_dir,
    )
    frame, warnings = run_school_validation(
        frame, output_dir, config=config, config_dir=config_dir
    )
    if selected_notice is not None:
        version_id, language = selected_notice
        manifest = {
            client_id: ManifestRow(
                client_id,
                version_id,
                language,
                None,
                None,
                assignment_source="template",
            )
            for client_id in frame["client_id"]
        }
    reference = config_dir / "vaccine_reference.json"
    if not reference.exists():
        reference = VACCINE_REFERENCE_PATH
    result, reconciliation = build_preprocess_result(
        frame,
        json.loads(reference.read_text(encoding="utf-8")),
        UNSPECIFIED_AGENTS,
        config=config,
        config_dir=config_dir,
        catalog=catalog,
        manifest=manifest,
    )
    return PreprocessResult(result.clients, warnings + result.warnings), reconciliation


def validate_csv_path(file_path: Path) -> None:
    """Require an existing file with a .csv extension; do not read its contents."""
    if not file_path.is_file():
        raise FileNotFoundError(f"Input file not found: {file_path}")
    if file_path.suffix.lower() != ".csv":
        raise ValueError(f"Input must be a CSV file: {file_path}")


def read_input(file_path: Path) -> pd.DataFrame:
    """Read and trim CSV text once, then validate it against the packaged input contract."""
    validate_csv_path(file_path)
    for encoding in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            frame = pd.read_csv(
                file_path,
                sep=None,
                encoding=encoding,
                engine="python",
                dtype=str,
                keep_default_na=False,
            )
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        LOG.info("Loaded %s rows from %s", len(frame), file_path)
        return validate_input(normalize_dataframe(frame))
    raise ValueError("Could not decode CSV with common encodings or delimiters")


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare all CSV fields as trimmed strings, with empty strings for blanks."""
    return df.fillna("").astype(str).apply(lambda column: column.str.strip())


def validate_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate prepared values and supply empty strings for absent optional fields."""
    descriptor = json.loads(INPUT_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema = Schema.from_descriptor(descriptor)
    missing = [field.name for field in schema.fields if field.name not in frame.columns]
    report = fl_validate(
        [list(frame.columns), *frame.values.tolist()],
        schema=schema,
        detector=Detector(schema_sync=True),
    )

    if not report.valid:
        errors = report.flatten(["message"])
        raise ValueError(
            "Input file does not conform to expected schema:\n"
            + "\n".join(f"  - {e[0]}" for e in errors)
        )

    prepared = frame.reindex(columns=[*frame.columns, *missing], fill_value="")
    for field in schema.fields:
        if field.type == "date":
            prepared[field.name] = [
                value.isoformat() if value is not None else ""
                for value, _ in map(field.read_cell, prepared[field.name])
            ]
    return prepared


def check_addresses_complete(
    df: pd.DataFrame, drop_incomplete=True, output_dir: Path | None = None
) -> pd.DataFrame:
    """
    Check prepared address fields without changing their source values.

    Adds a temporary boolean 'address_complete' column based on presence of
    street address, city, province, and postal code.
    """

    df = df.copy()

    # Build combined address line
    df["address"] = (
        df["street_address_line_1"] + " " + df["street_address_line_2"]
    ).str.strip()

    # Check completeness
    df["address_complete"] = (
        df["address"].ne("")
        & df["city"].ne("")
        & df["province"].ne("")
        & df["postal_code"].ne("")
    )

    if not df["address_complete"].all():
        incomplete_count = (~df["address_complete"]).sum()
        LOG.warning(
            "There are %d records with incomplete address information.",
            incomplete_count,
        )

        incomplete_records = df.loc[~df["address_complete"]]

        incomplete_path = (
            output_dir or Path.cwd() / "output"
        ) / "incomplete_addresses.csv"
        incomplete_path.parent.mkdir(parents=True, exist_ok=True)
        incomplete_records.to_csv(incomplete_path, index=False)
        LOG.info("Incomplete address records written to %s", incomplete_path)

    # Return only rows with complete addresses based on drop_incomplete flag
    if drop_incomplete:
        return df.loc[df["address_complete"]].drop(columns=["address_complete"])
    else:
        return df.drop(columns=["address_complete"])


def check_client_info_complete(
    df: pd.DataFrame,
    drop_incomplete=True,
    output_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Check prepared client fields without repeating text cleanup.

    Adds a temporary boolean 'client_info_complete' column based on presence of
    first name, last name, DOB, school name, immunizations given, and client ID.
    """

    df = df.copy()

    client_info_cols = [
        "school_name",
        "client_id",
        "first_name",
        "last_name",
        "date_of_birth",
        "imms_given",
    ]

    # Check completeness
    df["client_info_complete"] = df[client_info_cols].ne("").all(axis=1)

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

        incomplete_path = (
            output_dir or Path.cwd() / "output"
        ) / "incomplete_clients.csv"
        incomplete_path.parent.mkdir(parents=True, exist_ok=True)
        incomplete_records.to_csv(incomplete_path, index=False)
        LOG.info("Incomplete client records written to %s", incomplete_path)
        print(f"Incomplete client records written to {incomplete_path}")

    # Return only rows with complete client info based on drop_incomplete flag
    if drop_incomplete:
        return df.loc[df["client_info_complete"]].drop(columns=["client_info_complete"])
    else:
        return df.drop(columns=["client_info_complete"])


def run_school_validation(
    df: pd.DataFrame,
    output_dir: Path,
    *,
    config: dict[str, Any],
    config_dir: Path,
) -> tuple[pd.DataFrame, list[str]]:
    """Validate school names against the school reference file.

    Reads supplied ``school_validation`` config. Returns the
    DataFrame unchanged (with no warnings) when validation is disabled or
    ``reference_file`` is not set.

    Parameters
    ----------
    df:
        Normalized DataFrame (output of ``check_addresses_complete``).
    output_dir:
        Directory where result CSVs (``school_exact.csv``, etc.) are written.

    Returns
    -------
    tuple[DataFrame, list[str]]
        Enriched DataFrame and a (possibly empty) list of warning strings.
    """
    school_config = config.get("school_validation", {})

    if not school_config.get("enabled", False):
        return df, []

    reference_file = school_config.get("reference_file", "")
    if not reference_file:
        LOG.warning("school_validation.enabled is true but reference_file is not set.")
        return df, []

    target_phu = school_config.get("target_phu", "")
    if not target_phu:
        LOG.warning(
            "school_validation.target_phu is not set — skipping school validation."
        )
        return df, []

    reference_path = Path(reference_file)
    if not reference_path.is_absolute():
        reference_path = (config_dir / reference_path).resolve()

    return validate_schools.validate_schools(
        df=df,
        reference_path=reference_path,
        target_phu=target_phu,
        output_dir=output_dir,
        unmatched_behavior=school_config.get("unmatched_behavior", "warn"),
        column_prefix=school_config.get("column_prefix", "school_"),
    )


def build_preprocess_result(
    df: pd.DataFrame,
    vaccine_reference: Dict[str, Any],
    excluded_agents: List[str],
    *,
    config: dict[str, Any],
    config_dir: Path,
    catalog: NoticeVersionCatalog,
    manifest: Dict[str, ManifestRow],
) -> Tuple[PreprocessResult, ReconciliationResult]:
    """Build client records, then reconcile their notice assignments.

    Sort by school, surname, given name, and client ID to assign the notice
    sequence. Parse disease names and vaccine history, calculate age at
    delivery, and attach each eligible notice's version and language.

    Return the prepared records with source warnings and assignment findings.
    Inconsistent validity indicators raise when markers are requested;
    assignment errors raise ReconciliationError before rendering begins.
    """
    warnings: set[str] = set()
    working = df.copy()

    normalization_path = config_dir / "disease_normalization.json"
    if not normalization_path.exists():
        normalization_path = CONFIG_DIR / "disease_normalization.json"
    normalization = load_normalization(normalization_path)
    date_notice_delivery: Optional[str] = config.get("date_notice_delivery")
    if date_notice_delivery is not None:
        if not isinstance(date_notice_delivery, str):
            raise ValueError(
                "date_notice_delivery must be an ISO calendar date (YYYY-MM-DD)"
            )
        try:
            if (
                date.fromisoformat(date_notice_delivery).isoformat()
                != date_notice_delivery
            ):
                raise ValueError
        except ValueError as exc:
            raise ValueError(
                "date_notice_delivery must be an ISO calendar date (YYYY-MM-DD)"
            ) from exc
    chart_diseases_header: List[str] = config.get("chart_diseases_header", [])
    preprocess_config: Dict[str, Any] = config.get("preprocess", {})
    show_validity_markers: bool = preprocess_config.get("show_validity_markers", False)

    # Assignment reconciliation policy
    notice_versioning_config: Dict[str, Any] = config.get("notice_versioning", {})
    extra_manifest_rows: str = notice_versioning_config.get(
        "extra_manifest_rows", "error"
    )

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

    missing_board = working.get("board_name", pd.Series("", index=working.index)).eq("")
    if missing_board.any():
        affected = working.loc[missing_board, "school_name"].unique().tolist()
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

    # Client records are prepared before assigning notices or translating labels.

    # Combine placeholder cleanup with the selected history-only exclusions.
    excluded_history_agents = [*excluded_agents, *config.get("ignore_agents", [])]
    clients: List[ClientRecord] = []
    for row in sorted_df.to_dict(orient="records"):
        client_id = str(row["client_id"])
        sequence = row["sequence"]
        dob_iso = row["date_of_birth"] or None
        if dob_iso is None:
            warnings.add(f"Missing date of birth for client {client_id}")

        overdue_diseases = parse_overdue_diseases(
            row["overdue_disease"],
            normalization,
            client_id=client_id,
            warnings=warnings,
        )
        overdue_agents = parse_overdue_agents(row["overdue_agent"])

        received = build_received_rows(
            row["imms_given"],
            excluded_history_agents,
            vaccine_reference,
            chart_diseases_header,
            show_validity_markers,
        )

        postal_code = row["postal_code"] if row["postal_code"] else "Not provided"
        address_line = " ".join(
            filter(None, [row["street_address_line_1"], row["street_address_line_2"]])
        ).strip()

        if dob_iso and date_notice_delivery:
            age = calculate_age_at_date(dob_iso, date_notice_delivery)
            over_16 = age >= 16
        else:
            age = None
            over_16 = False

        person = {
            "first_name": row["first_name"] or "",
            "last_name": row["last_name"] or "",
            "date_of_birth_iso": dob_iso or "",
            "age": age,
            "over_16": over_16,
        }

        school = {
            "name": row["school_name"],
            "id": row["school_id"],
        }

        board = {
            "name": row.get("board_name", ""),
            "id": row["board_id"],
        }

        contact = {
            "street": address_line,
            "city": row["city"],
            "province": row["province"],
            "postal_code": postal_code,
        }

        client = ClientRecord(
            sequence=sequence,
            client_id=client_id,
            language="",
            person=person,
            school=school,
            board=board,
            contact=contact,
            overdue_diseases=overdue_diseases,
            overdue_agents=overdue_agents,
            received=received if received else None,
            metadata={},
            version_id=row.get("version_id") or None,
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
                "Each source row will receive a separate notice with the same assignment."
            )

    reconciliation_result = reconcile(clients, manifest, catalog, extra_manifest_rows)

    if has_errors(reconciliation_result, extra_manifest_rows):
        raise ReconciliationError(reconciliation_result)

    rebuilt = [
        attach_notice(client, reconciliation_result.resolved_notices[client.client_id])
        for client in clients
    ]

    return (
        PreprocessResult(clients=rebuilt, warnings=list(warnings)),
        reconciliation_result,
    )


def synthesize_identifier(existing: str, source: str, prefix: str) -> str:
    """Generate a deterministic identifier if one is not provided."""
    existing = (existing or "").strip()
    if existing:
        return existing

    base = (source or "").strip().lower() or "unknown"
    digest = sha1(base.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def load_normalization(path: Path) -> dict[str, str]:
    """Read the selected normalization resource for one pipeline run."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in data.items()
    ):
        raise ValueError(f"Disease normalization must be a string mapping: {path}")
    return data


def normalize_disease(token: str, normalization: dict[str, str]) -> str:
    """Look up the configured disease name, keeping unlisted names unchanged."""
    token = token.strip()
    return normalization.get(token, token)


def parse_overdue_diseases(
    raw: Any,
    normalization: dict[str, str],
    *,
    client_id: str,
    warnings: set[str],
) -> list[dict[str, object]]:
    """Preserve configured disease names and source dose information without display wording."""
    if not isinstance(raw, str) or not raw.strip():
        return []

    entries: list[dict[str, object]] = []
    for token in raw.split(";"):
        token = token.strip().replace("'", "").replace('"', "")
        if not token:
            continue
        disease, separator, dose_raw = token.rpartition(" -")
        if not separator:
            entries.append(
                {"disease": normalize_disease(token, normalization), "dose": None}
            )
            continue

        disease = normalize_disease(disease, normalization)
        dose_raw = dose_raw.strip()
        if not disease:
            raise ValueError(f"Empty overdue disease for client {client_id}: {token!r}")
        if dose_raw.isdecimal() and int(dose_raw) > 0:
            entries.append({"disease": disease, "dose": int(dose_raw)})
            continue

        warnings.add(
            f"Invalid overdue dose for client {client_id}: {disease} - {dose_raw!r}. "
            "Displaying disease without a dose number."
        )
        entries.append({"disease": disease, "dose": None, "dose_raw": dose_raw})

    return entries


def parse_overdue_agents(raw: Any) -> list[str]:
    """Keep source agent names separate from disease eligibility."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    return [
        token.strip().replace("'", "").replace('"', "")
        for token in raw.split(";")
        if token.strip()
    ]


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

    # Subtract one year if the birthday falls after the notice delivery date.
    if (delivery_datetime.month < birth_datetime.month) or (
        delivery_datetime.month == birth_datetime.month
        and delivery_datetime.day < birth_datetime.day
    ):
        age -= 1

    return age


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
    applies before any notice is rendered.

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


def build_received_rows(
    received_agents: Any,
    excluded_agents: List[str],
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
    excluded_agents : List[str]
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
    flat = parse_dose_segments(received_agents, excluded_agents)
    if not flat:
        return []

    by_date: Dict[str, List[Dict[str, str]]] = {}
    for dose in flat:
        by_date.setdefault(dose["date_given"], []).append(
            {"vaccine": dose["vaccine"], "validity": dose["validity"]}
        )

    rows: List[Dict[str, Any]] = []
    for given_date, doses in by_date.items():
        vaccines = _deduplicate_vaccines_for_date(doses, vaccine_reference)
        date_rows: List[Dict[str, Any]]
        if show_validity_markers:
            date_rows = _split_into_rows(vaccines, chart_diseases_header)
        else:
            columns = compute_column_statuses(vaccines, chart_diseases_header)
            date_rows = [{"vaccines": vaccines, "columns": columns}]
        n = len(date_rows)
        for i, row in enumerate(date_rows):
            rows.append(
                {
                    "date_given": given_date,
                    "date_rowspan": n if i == 0 else 0,
                    "vaccines": [v["vaccine"] for v in row["vaccines"]],
                    "columns": row["columns"],
                }
            )

    return rows


def parse_dose_segments(
    received_agents: Any, excluded_agents: List[str]
) -> List[Dict[str, str]]:
    """Parse an imms_given string into a flat sorted list of individual dose entries.

    Extracts individual dose entries from a semicolon-delimited string,
    normalizes dates to ISO format, normalizes validity to one of
    ``"valid"`` / ``"invalid"`` / ``"unknown"``, and filters unwanted
    vaccine names. ``build_received_rows`` then groups doses by date and
    looks up the diseases covered by each vaccine.

    Parameters
    ----------
    received_agents : Any
        Raw imms_given cell value.  Must be a non-empty ``str`` to be
        parsed; any other type returns ``[]``.
        Expected format per segment: ``"MMM D, YYYY - VaccineName"`` or
        ``"MMM D, YYYY - VaccineName - Valid|Invalid"``.
    excluded_agents : List[str]
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
        if vaccine in excluded_agents:
            continue
        vaccine = vaccine.replace("-unspecified", "*").replace(" unspecified", "*")
        if vaccine in excluded_agents:
            continue
        rows.append(
            {
                "date_given": convert_date_iso(date_str.strip()),
                "vaccine": vaccine,
                "validity": normalize_validity_status(raw_valid),
            }
        )

    rows.sort(key=lambda item: item["date_given"])
    return rows


def convert_date_iso(date_str: str) -> str:
    """Parse a source immunization date and return an ISO calendar date.

    Expects "Mon DD, YYYY" (e.g., "May 8, 2025") in the source export.

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


def normalize_validity_status(raw_status: Any) -> str:
    """Normalize a raw validity token to one of three supported statuses.

    Only the exact casings "valid"/"Valid" and "invalid"/"Invalid" are
    accepted as known statuses; everything else — typos, alternate casings,
    empty strings, None, NaN — maps to "unknown". This strict gate prevents
    ambiguous data from silently influencing validity markers on notices.

    Parameters
    ----------
    raw_status : Any
        Raw value extracted from an imms_given segment, or any value that
        needs to be converted to a supported status. Typically a str, but
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


def write_artifact(
    output_dir: Path,
    run_id: str,
    result: PreprocessResult,
) -> Path:
    """Save the prepared client records and source warnings for this run."""
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "run_id": run_id,
        "clients": [asdict(client) for client in result.clients],
        "warnings": result.warnings,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_clients": len(result.clients),
    }
    artifact_path = output_dir / f"preprocessed_clients_{run_id}.json"
    artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    LOG.info("Wrote normalized artifact to %s", artifact_path)
    return artifact_path
