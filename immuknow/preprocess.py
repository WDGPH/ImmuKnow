"""Prepare every source row as facts and reconcile its explicit notice assignment.

Blank or unusable values remain visible through row findings and saved source
values. Python normalizes administrations; Typst chooses their presentation.
"""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import replace
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from frictionless import Schema

from . import validate_schools
from .assignment_manifest import ManifestRow, ReconciliationResult, reconcile
from .data_models import CheckResult, ClientRecord, PreprocessResult
from .version_notices import NoticeVersionCatalog, attach_notice

CONFIG_DIR = Path(str(files("immuknow").joinpath("config")))
INPUT_SCHEMA_PATH = Path(str(files("immuknow").joinpath("schemas/input_schema.json")))
UNSPECIFIED_AGENTS = [
    "-unspecified",
    "unspecified",
    "Not Specified",
    "Not specified",
    "Not Specified-unspecified",
]


def prepare_clients(
    input_path: Path,
    output_dir: Path,
    config: dict,
    config_dir: Path,
    catalog: NoticeVersionCatalog,
    manifest: dict[str, ManifestRow],
    selected_notice: tuple[str, str] | None,
) -> tuple[PreprocessResult, ReconciliationResult]:
    """Prepare all source rows; malformed shared resources raise during setup."""
    raw_frame = read_input(input_path)
    frame = validate_input(clean_csv_text(raw_frame))
    frame, school_warnings = run_school_validation(
        frame, output_dir, config=config, config_dir=config_dir
    )
    if selected_notice is not None:
        version, language = selected_notice
        manifest = {
            cid: ManifestRow(
                cid, version, language, None, None, assignment_source="template"
            )
            for cid in frame["client_id"]
        }
    reference = config_dir / "vaccine_reference.json"
    vaccine_reference = json.loads(reference.read_text(encoding="utf-8"))
    if not isinstance(vaccine_reference, dict) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, (str, list))
        or isinstance(value, str)
        and not value
        or isinstance(value, list)
        and any(not isinstance(item, str) or not item for item in value)
        for key, value in vaccine_reference.items()
    ):
        raise ValueError(
            "Vaccine reference must map agent names to disease strings or lists"
        )
    result, reconciliation = build_preprocess_result(
        frame,
        vaccine_reference,
        UNSPECIFIED_AGENTS,
        config=config,
        config_dir=config_dir,
        catalog=catalog,
        manifest=manifest,
    )
    source_rows = {
        f"row-{index:06d}": row
        for index, row in enumerate(raw_frame.to_dict(orient="records"), 1)
    }
    return replace(
        result, warnings=school_warnings + result.warnings, source_rows=source_rows
    ), reconciliation


def validate_csv_path(file_path: Path) -> None:
    """Require an existing CSV file."""
    if not file_path.is_file():
        raise FileNotFoundError(f"Input file not found: {file_path}")
    if file_path.suffix.lower() != ".csv":
        raise ValueError(f"Input must be a CSV file: {file_path}")


def read_input(file_path: Path) -> pd.DataFrame:
    """Read original strings once; trimming and validation belong to preparation."""
    validate_csv_path(file_path)
    for encoding in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            # Without this guard pandas can treat an extra field as an implicit
            # index and shift every source value beneath the wrong column.
            with warnings.catch_warnings():
                warnings.simplefilter("error", pd.errors.ParserWarning)
                frame = pd.read_csv(
                    file_path,
                    sep=None,
                    encoding=encoding,
                    engine="python",
                    dtype=str,
                    keep_default_na=False,
                    index_col=False,
                )
        except pd.errors.ParserWarning:
            raise ValueError(
                "CSV rows contain more fields than the header; source values would be lost"
            ) from None
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        return frame
    raise ValueError("Could not decode CSV with common encodings or delimiters")


def clean_csv_text(df: pd.DataFrame) -> pd.DataFrame:
    """Trim source strings; blank cells stay blank rather than becoming NA names."""
    return df.fillna("").astype(str).apply(lambda column: column.str.strip())


def validate_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Check source columns, then leave per-row values for row findings."""
    schema = Schema.from_descriptor(
        json.loads(INPUT_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    missing = [field.name for field in schema.fields if field.name not in frame.columns]
    required = [
        field.name
        for field in schema.fields
        if field.name in missing and field.constraints.get("required")
    ]
    if required:
        raise ValueError(
            "Input file is missing required columns: " + ", ".join(required)
        )
    return frame.reindex(columns=[*frame.columns, *missing], fill_value="")


def run_school_validation(
    df: pd.DataFrame,
    output_dir: Path,
    *,
    config: dict[str, Any],
    config_dir: Path,
) -> tuple[pd.DataFrame, list[str]]:
    """Retain all rows while checking schools against a fully configured reference.

    A disabled lookup returns the frame unchanged. Enabled lookup requires its
    source file and target PHU; incomplete shared settings fail setup.
    """
    school_config = config.get("school_validation", {})

    if not school_config.get("enabled", False):
        return df, []

    reference_file = school_config.get("reference_file")
    target_phu = school_config.get("target_phu")
    for field, value in (
        ("reference_file", reference_file),
        ("target_phu", target_phu),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"school_validation.{field} must be a nonempty string when enabled"
            )

    reference_path = Path(reference_file)
    if not reference_path.is_absolute():
        reference_path = (config_dir / reference_path).resolve()

    return validate_schools.validate_schools(
        df=df,
        reference_path=reference_path,
        target_phu=target_phu,
        output_dir=output_dir,
        column_prefix=school_config.get("column_prefix", "school_"),
    )


def build_preprocess_result(
    df: pd.DataFrame,
    vaccine_reference: dict[str, Any],
    excluded_agents: list[str],
    *,
    config: dict[str, Any],
    config_dir: Path,
    catalog: NoticeVersionCatalog,
    manifest: dict[str, ManifestRow],
) -> tuple[PreprocessResult, ReconciliationResult]:
    """Prepare original-order row keys, cohort validity coverage and explicit assignments."""
    normalization_path = config_dir / "disease_normalization.json"
    normalization = load_normalization(normalization_path)
    delivery = config.get("date_of_delivery") or ""
    for field in ("date_of_delivery", "date_as_of"):
        value = config.get(field) or ""
        if value and (
            not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        ):
            raise ValueError(f"{field} must be an ISO calendar date")
        if value:
            date.fromisoformat(value)
    raw_rows = df.fillna("").astype(str).to_dict(orient="records")
    rows = validate_input(clean_csv_text(df)).to_dict(orient="records")
    coverage = classify_dataset_validity(pd.Series([row["imms_given"] for row in rows]))
    clients: list[ClientRecord] = []
    row_checks: dict[str, list[CheckResult]] = {}
    source_rows: dict[str, dict[str, Any]] = {}
    birth_field = Schema.from_descriptor(
        json.loads(INPUT_SCHEMA_PATH.read_text())
    ).get_field("date_of_birth")
    for index, row in enumerate(rows, 1):
        key = f"row-{index:06d}"
        source_rows[key] = raw_rows[index - 1]
        checks: list[CheckResult] = []
        row_checks[key] = checks
        match_field = (
            config.get("school_validation", {}).get("column_prefix", "school_")
            + "match_type"
        )
        if row.get(match_field) == "no_match":
            checks.append(
                CheckResult(
                    "data.school_unmatched",
                    "preparation",
                    "warn",
                    "Source school has no reference match",
                )
            )
        for field in (
            "client_id",
            "first_name",
            "last_name",
            "school_name",
            "board_name",
        ):
            if not row.get(field):
                checks.append(
                    CheckResult(
                        f"source.{field}_missing",
                        "preparation",
                        "warn",
                        f"Source {field.replace('_', ' ')} is missing",
                    )
                )
        if row["client_id"] and not re.fullmatch(r"\d{10}", row["client_id"]):
            checks.append(
                CheckResult(
                    "source.client_id_format",
                    "preparation",
                    "warn",
                    "Source client ID is not a ten-digit identifier",
                )
            )
        street = " ".join(
            filter(None, [row["street_address_line_1"], row["street_address_line_2"]])
        )
        if not all((street, row["city"], row["province"], row["postal_code"])):
            checks.append(
                CheckResult(
                    "source.address_incomplete",
                    "preparation",
                    "warn",
                    "Source mailing address is incomplete",
                    component="address",
                )
            )
        birth, birth_notes = birth_field.read_cell(row["date_of_birth"])
        dob = birth.isoformat() if birth is not None and not birth_notes else ""
        age = calculate_age_at_date(dob, delivery) if dob and delivery else None
        if age is not None and age < 0:
            age = None
        if age is None:
            checks.append(
                CheckResult(
                    "source.age_unknown",
                    "preparation",
                    "warn",
                    "Age is unknown; source birth date or delivery date is absent or unusable",
                )
            )
        overdue_warnings: set[str] = set()
        overdue = parse_overdue_diseases(
            row["overdue_disease"],
            normalization,
            client_id=row["client_id"],
            warnings=overdue_warnings,
        )
        overdue_agents = parse_overdue_agents(
            row["overdue_agent"], warnings=overdue_warnings
        )
        for warning in sorted(overdue_warnings):
            checks.append(
                CheckResult("source.overdue_unusable", "preparation", "warn", warning)
            )
        unparsed: list[str] = []
        history = build_history_items(
            row["imms_given"], excluded_agents, vaccine_reference, unparsed=unparsed
        )
        if unparsed:
            checks.append(
                CheckResult(
                    "source.history_unparsed",
                    "preparation",
                    "warn",
                    "Unusable history fragments were preserved",
                    component="history",
                )
            )
        clients.append(
            ClientRecord(
                sequence=key,
                client_id=row["client_id"],
                language="",
                person={
                    "first_name": row["first_name"],
                    "last_name": row["last_name"],
                    "date_of_birth_iso": dob,
                    "age": age,
                    "over_16": age >= 16 if age is not None else None,
                },
                school={"name": row["school_name"], "id": row["school_id"]},
                board={"name": row["board_name"], "id": row["board_id"]},
                contact={
                    "street": street,
                    "city": row["city"],
                    "province": row["province"],
                    "postal_code": row["postal_code"],
                },
                overdue_diseases=overdue,
                overdue_agents=overdue_agents,
                metadata={"row_key": key},
                version_id=row["version_id"] or None,
                history=history,
                validity_coverage=coverage,
                unparsed_history=unparsed,
            )
        )
    reconciliation = reconcile(clients, manifest, catalog)
    clients = [
        attach_notice(client, reconciliation.resolved_notices[client.sequence])
        if client.sequence in reconciliation.resolved_notices
        else replace(client, version_id=None)
        for client in clients
    ]
    return PreprocessResult(clients, [], row_checks, source_rows), reconciliation


def load_normalization(path: Path) -> dict[str, str]:
    """Read the selected normalization resource for one pipeline run."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(value, str)
        or not value.strip()
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
        original = token.strip()
        if not original:
            continue
        token = original.replace("'", "").replace('"', "").strip()
        if not token:
            warnings.add(
                f"Unusable overdue disease fragment: {original!r}. Original source value retained."
            )
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
            warnings.add(f"Unusable overdue disease for client {client_id}: {token!r}")
            continue
        if dose_raw.isdecimal() and int(dose_raw) > 0:
            entries.append({"disease": disease, "dose": int(dose_raw)})
            continue

        warnings.add(
            f"Invalid overdue dose for client {client_id}: {disease} - {dose_raw!r}. "
            "Displaying disease without a dose number."
        )
        entries.append({"disease": disease, "dose": None, "dose_raw": dose_raw})

    return entries


def parse_overdue_agents(raw: Any, *, warnings: set[str]) -> list[str]:
    """Clean agent tokens and report unusable fragments retained in source rows."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    agents = []
    for token in raw.split(";"):
        token = token.strip()
        if not token:
            continue
        agent = token.replace("'", "").replace('"', "").strip()
        if agent:
            agents.append(agent)
        else:
            warnings.add(
                f"Unusable overdue agent fragment: {token!r}. Original source value retained."
            )
    return agents


def calculate_age_at_date(date_of_birth, date_of_delivery):
    """Calculate a client's age on notice delivery date.

    Parameters
    ----------
    date_of_birth : str
        Date of birth in YYYY-MM-DD format.
    date_of_delivery : str
        Notice delivery date in YYYY-MM-DD format.

    Returns
    -------
    int
        The client's age on date_of_delivery.
    """

    birth_datetime = datetime.strptime(date_of_birth, "%Y-%m-%d")
    delivery_datetime = datetime.strptime(date_of_delivery, "%Y-%m-%d")

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
    """Classify all recognizable source administrations before deduplication or display."""
    states: set[bool] = set()
    for raw in imms_given_series:
        for dose in parse_dose_segments(raw, []):
            states.add(dose["validity"] != "unknown")
    if len(states) > 1:
        return "mixed"
    return "all_present" if True in states else "all_absent"


def parse_dose_segments(
    raw: Any, excluded_agents: list[str], *, unparsed: list[str] | None = None
) -> list[dict[str, str]]:
    """Parse whole fragments and preserve unusable fragments for display and review."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    doses: list[dict[str, str]] = []
    pattern = re.compile(
        r"(\w{3} \d{1,2}, \d{4}) - (.+?)(?:\s+-\s+([Vv]alid|[Ii]nvalid))?"
    )
    for fragment in raw.split(";"):
        fragment = fragment.strip()
        if not fragment:
            continue
        match = pattern.fullmatch(fragment)
        try:
            given = convert_date_iso(match[1]) if match else None
        except ValueError:
            given = None
        if not match or given is None:
            if unparsed is not None:
                unparsed.append(fragment)
            continue
        agent = match[2].strip()
        if agent in excluded_agents:
            continue
        doses.append(
            {
                "date_given": given,
                "vaccine": agent,
                "validity": normalize_validity_status(match[3]),
            }
        )
    return sorted(doses, key=lambda item: item["date_given"])


def build_history_items(
    raw: Any,
    placeholder_agents: list[str],
    vaccine_reference: dict[str, Any],
    *,
    unparsed: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Keep full mappings; duplicates follow unknown > valid > invalid precedence."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for dose in parse_dose_segments(raw, placeholder_agents, unparsed=unparsed):
        grouped.setdefault((dose["date_given"], dose["vaccine"]), []).append(
            dose["validity"]
        )
    result = []
    for (given, agent), states in grouped.items():
        validity = (
            "unknown"
            if "unknown" in states
            else "valid"
            if "valid" in states
            else "invalid"
        )
        mapped = vaccine_reference.get(agent, agent)
        diseases = mapped if isinstance(mapped, list) else [mapped]
        result.append(
            {
                "date_given": given,
                "agent": agent,
                "display_name": agent.replace("-unspecified", "*").replace(
                    " unspecified", "*"
                ),
                "diseases": list(dict.fromkeys(diseases)),
                "validity": validity,
            }
        )
    return result


def convert_date_iso(date_str: str) -> str:
    """Normalize the source export's English administration date."""
    return datetime.strptime(date_str, "%b %d, %Y").date().isoformat()


def normalize_validity_status(raw_status: Any) -> str:
    """Keep absent validity separate from an invalid dose."""
    if raw_status in ("valid", "Valid"):
        return "valid"
    if raw_status in ("invalid", "Invalid"):
        return "invalid"
    return "unknown"
