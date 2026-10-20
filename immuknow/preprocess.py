"""Prepare every source row as facts and reconcile its explicit notice assignment.

Blank or unusable values remain visible through row findings and saved source
values. Python normalizes administrations; Typst chooses their presentation.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime
from importlib.resources import files
from io import StringIO
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from frictionless import Schema

from . import validate_schools
from .assignment_manifest import ManifestRow, ReconciliationResult, reconcile
from .data_models import CheckResult, ClientRecord, PreprocessResult
from .version_notices import NoticeVersionCatalog, attach_notice
from .structured_input import read_json
from .load_config import validate_dates

CONFIG_DIR = Path(str(files("immuknow").joinpath("config")))
INPUT_SCHEMA_PATH = Path(str(files("immuknow").joinpath("schemas/input_schema.json")))
CSV_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
UNSPECIFIED_AGENTS = [
    "-unspecified",
    "unspecified",
    "Not Specified",
    "Not specified",
    "Not Specified-unspecified",
]


def prepare_clients(
    raw_frame: pd.DataFrame,
    output_dir: Path,
    config: dict,
    config_dir: Path,
    catalog: NoticeVersionCatalog,
    manifest: dict[str, ManifestRow],
    selected_notice: tuple[str, str] | None,
) -> tuple[PreprocessResult, ReconciliationResult]:
    """Prepare all source rows; malformed shared resources raise during setup."""
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
    vaccine_reference = read_json(reference)
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


def read_input(file_path: Path, *, encoding: str | None = None) -> pd.DataFrame:
    """Read exact strings and reject damaged rows before assigning source row keys."""
    validate_csv_path(file_path)
    if encoding is not None and encoding not in CSV_ENCODINGS:
        raise ValueError("CSV encoding must be utf-8-sig, cp1252 or latin-1")
    content = file_path.read_bytes()
    selected = ""
    text = ""
    for candidate in (encoding,) if encoding is not None else CSV_ENCODINGS:
        try:
            text = content.decode(candidate)
        except UnicodeDecodeError:
            continue
        selected = candidate
        break
    if not selected:
        raise ValueError(
            f"CSV cannot be read using {encoding}; check the file encoding"
        )
    controls = sorted(
        {
            ord(char)
            for char in text
            if ord(char) < 32 and char not in "\t\r\n" or 127 <= ord(char) <= 159
        }
    )
    if controls:
        raise ValueError(
            "CSV contains unsupported control characters after reading as "
            + selected
            + ": "
            + ", ".join(f"U+{code:04X}" for code in controls)
            + ". Check the source file and its encoding."
        )
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if not first_line:
        raise ValueError("CSV is empty")
    try:
        dialect = (
            csv.Sniffer().sniff(first_line, delimiters=",;\t|")
            if any(char in first_line for char in ",;\t|")
            else csv.excel
        )
        reader = csv.reader(
            StringIO(text, newline=""),
            delimiter=dialect.delimiter,
            strict=True,
            skipinitialspace=False,
        )
        header = next(row for row in reader if row)
        if any(
            not name or name != name.strip() or "\n" in name or "\r" in name
            for name in header
        ):
            raise ValueError(
                "CSV headers must be nonempty names without surrounding whitespace or line breaks"
            )
        duplicates = sorted(
            name for name, count in Counter(header).items() if count > 1
        )
        if duplicates:
            raise ValueError("Repeated CSV headers: " + ", ".join(duplicates))
        rows = []
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                direction = "more" if len(row) > len(header) else "fewer"
                raise ValueError(
                    f"CSV line {reader.line_num} contains {direction} fields than the header; expected {len(header)}, found {len(row)}"
                )
            rows.append(row)
    except csv.Error as exc:
        raise ValueError(f"CSV structure is invalid: {exc}") from None
    frame = pd.DataFrame(rows, columns=pd.Index(header), dtype=str)
    frame.attrs["encoding"] = selected
    frame.attrs["delimiter"] = dialect.delimiter
    return frame


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
    validate_dates(config)
    delivery = config.get("date_of_delivery") or ""
    raw_rows = df.fillna("").astype(str).to_dict(orient="records")
    rows = validate_input(clean_csv_text(df)).to_dict(orient="records")
    histories = [parse_history(row["imms_given"]) for row in raw_rows]
    coverage = classify_dataset_validity(histories)
    clients: list[ClientRecord] = []
    row_checks: dict[str, list[CheckResult]] = {}
    source_rows: dict[str, dict[str, Any]] = {}
    school_config = config.get("school_validation", {})
    school_reference = df.attrs.get("school_reference", {})
    if school_config.get("enabled") and not school_reference:
        raise ValueError("Enabled school validation has no reference results")
    birth_field = Schema.from_descriptor(
        json.loads(INPUT_SCHEMA_PATH.read_text())
    ).get_field("date_of_birth")
    for index, (row, parsed) in enumerate(zip(rows, histories), 1):
        key = f"row-{index:06d}"
        source_rows[key] = raw_rows[index - 1]
        checks: list[CheckResult] = []
        row_checks[key] = checks
        if school_config.get("enabled"):
            prefix = school_config.get("column_prefix", "school_")
            match = row[prefix + "match_type"]
            reason = row[prefix + "mismatch_reason"]
            if match == "exact":
                status, message = (
                    "pass",
                    "Source school matches the selected reference.",
                )
            elif reason == "name_only":
                status, message = (
                    "warn",
                    "School name matches, but no facility ID was supplied.",
                )
            else:
                status = "fail"
                message = {
                    "id_mismatch": "School facility ID differs from the reference for this name.",
                    "id_only": "School name differs from the reference for this facility ID.",
                    "": "School was not found in the selected PHU reference.",
                }[reason]
            checks.append(
                CheckResult(
                    "data.school_match",
                    "preparation",
                    status,
                    message,
                    measurements={
                        **school_reference,
                        "source_school": row["school_name"],
                        "match_type": match,
                        "reason": reason
                        or ("exact" if match == "exact" else "not_found"),
                        "matched_name": row[prefix + "matched_name"],
                        "matched_id": row[prefix + "facility_id"],
                    },
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
        if row["client_id"] and not re.fullmatch(r"[0-9]{10}", row["client_id"]):
            checks.append(
                CheckResult(
                    "source.client_id_format",
                    "preparation",
                    "fail",
                    "Source Panorama client ID must contain ten digits (0–9)",
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
        required = {str(entry["disease"]) for entry in overdue}
        covered: set[str] = set()
        unmapped = []
        for agent in overdue_agents:
            if agent not in vaccine_reference:
                unmapped.append(agent)
                continue
            diseases = vaccine_reference[agent]
            for disease in diseases if isinstance(diseases, list) else [diseases]:
                covered.add(normalize_disease(disease, normalization))
        missing, extra = required - covered, covered - required
        if missing:
            status, message = (
                "fail",
                "Forecasted agents do not cover every overdue disease. Correct the forecast or its lookup.",
            )
        elif extra or unmapped:
            status, message = (
                "warn",
                "Forecasted agents cover the overdue diseases, but add other diseases or include an agent absent from the lookup.",
            )
        elif required or overdue_agents:
            status, message = "pass", "Forecasted agents cover all overdue diseases."
        else:
            status, message = (
                "not_applicable",
                "No overdue diseases or forecasted agents were supplied.",
            )
        checks.append(
            CheckResult(
                "data.forecast_coverage",
                "preparation",
                status,
                message,
                measurements={
                    "missing_diseases": sorted(missing),
                    "extra_diseases": sorted(extra),
                    "unmapped_agents": sorted(set(unmapped)),
                },
            )
        )
        history = build_history_items(parsed.doses, excluded_agents, vaccine_reference)
        for issue in parsed.issues:
            checks.append(
                CheckResult(
                    "source.history_invalid",
                    "preparation",
                    "fail",
                    f"Row {index}, imms_given fragment {issue.number}: {issue.reason}. Expected 'Mon D, YYYY - Agent', optionally followed by ' - Valid' or ' - Invalid', with every entry ending in ';'.",
                    component="history",
                    measurements={
                        "column": "imms_given",
                        "fragment_number": issue.number,
                        "fragment": issue.fragment,
                    },
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
                unparsed_history=[issue.fragment for issue in parsed.issues],
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
    data = read_json(path)
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


@dataclass(frozen=True)
class HistoryIssue:
    number: int
    fragment: str
    reason: str


@dataclass(frozen=True)
class ParsedHistory:
    doses: list[dict[str, str]]
    issues: list[HistoryIssue]


_HISTORY_DATE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) ([0-9]{1,2}), ([0-9]{4})"
)
_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ),
        1,
    )
}


def parse_history(raw: str) -> ParsedHistory:
    """Parse each fragment once, before exclusions, and retain every syntax error."""
    doses: list[dict[str, str]] = []
    issues = []
    stripped = raw.strip(" \t\r\n")
    if not stripped:
        return ParsedHistory(doses, issues)
    # Panorama ends every history with one ";" and writes "-;" (or "-  -;" when
    # validity is exported) for no history. A missing final ";" is an error.
    text = stripped.removesuffix(";")
    terminated = text != stripped
    if terminated and text.rstrip(" \t\r\n") in ("-", "-  -"):
        return ParsedHistory(doses, issues)
    fragments = text.split(";")
    for number, fragment in enumerate(fragments, 1):
        parts = fragment.strip(" \t\r\n").split(" - ")
        reason = ""
        if len(parts) not in (2, 3):
            reason = "Use one date, one agent and at most one validity status"
        elif len(parts) == 3 and parts[2] not in ("Valid", "Invalid"):
            reason = "Validity must be exactly Valid or Invalid"
        elif (
            not parts[1]
            or parts[1] != parts[1].strip()
            or any(char in parts[1] for char in "\r\n\t")
            or re.search(r"\s-|-\s", parts[1])
        ):
            reason = (
                "Agent must be nonempty and cannot contain an extra field separator"
            )
        else:
            match = _HISTORY_DATE.fullmatch(parts[0])
            try:
                if match is None:
                    raise ValueError
                given = date(
                    int(match[3]), _MONTHS[match[1]], int(match[2])
                ).isoformat()
            except ValueError:
                reason = "Date must be a real calendar date in Mon D, YYYY form"
        if not reason and not terminated and number == len(fragments):
            reason = "History must end with ';'"
        if reason:
            issues.append(HistoryIssue(number, fragment, reason))
            continue
        doses.append(
            {
                "date_given": given,
                "vaccine": parts[1],
                "validity": {"Valid": "valid", "Invalid": "invalid"}[parts[2]]
                if len(parts) == 3
                else "unknown",
            }
        )
    return ParsedHistory(sorted(doses, key=lambda item: item["date_given"]), issues)


def classify_dataset_validity(
    histories: list[ParsedHistory],
) -> Literal["all_present", "all_absent", "mixed"]:
    """Use all parsed administrations before exclusions or deduplication."""
    states = {
        dose["validity"] != "unknown" for history in histories for dose in history.doses
    }
    if len(states) > 1:
        return "mixed"
    return "all_present" if True in states else "all_absent"


def build_history_items(
    doses: list[dict[str, str]],
    placeholder_agents: list[str],
    vaccine_reference: dict[str, Any],
) -> list[dict[str, Any]]:
    """Keep full mappings; duplicates follow unknown > valid > invalid precedence."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for dose in doses:
        if dose["vaccine"] in placeholder_agents:
            continue
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
