"""Validate school/daycare names in the input DataFrame against the PHIX mapping file.

The mapping file is produced by a separate script and contains a PHU-keyed dict
of normalized school names → PHIX facility IDs.

Match categories
----------------
`exact`: normalized name found in the target PHU's mapping AND facility ID matches

`inexact`: name found but no ID provided for comparison (name_only), name found but provided ID differs from mapping (id_mismatch),
or ID found under a different name (id_only)

`no_match`: neither name nor ID found for the target PHU

Usage (called from preprocess.run_phix_validation)
-----
    df, warnings = validate_schools(
        df=df,
        mapping_path=config_dir / "phix_mapping.json",
        target_phu="Wellington Dufferin Guelph Public Health",
        output_dir=output_dir,
    )
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def normalize_school_name(name: str) -> str:
    """Uppercase and collapse whitespace.

    Must produce the same keys as build_phix_mapping.py so lookups match.
    """
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.upper().strip())


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------


def parse_input_entry(entry: str) -> tuple[str, str]:
    """Split a raw input cell into (school_name, facility_id).

    Input data sometimes carries the facility ID appended as
    ``"SCHOOL NAME - 019186"``. We split on the rightmost ``" - "``
    so names that themselves contain dashes are handled correctly.

    Returns ``(entry, "")`` when no separator is found.
    """
    entry = str(entry).strip()
    parts = entry.rsplit(" - ", maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return entry, ""


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class PHIXMatchResult:
    """Outcome of matching one input school entry against the PHIX mapping."""

    input_name: str
    input_id: str  # "" when not provided in input
    match_type: str  # "exact" | "inexact" | "no_match"
    matched_name: str | None = None  # name from the school mapping
    matched_id: str | None = None  # facility ID from mapping
    mismatch_reason: str | None = None  # "name_only" | "id_mismatch" | "id_only"


# ---------------------------------------------------------------------------
# Mapping loader
# ---------------------------------------------------------------------------


def load_mapping(
    mapping_path: Path,
    target_phu: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Load ``phix_mapping.json`` and return lookup dicts for *target_phu*.

    The ``by_id`` reverse lookup is built here from the flat name→id mapping.

    Parameters
    ----------
    mapping_path:
        Path to the JSON file produced by ``build_phix_mapping.py``.
    target_phu:
        Exact PHU key string as it appears in the JSON (e.g.
        ``"Wellington Dufferin Guelph Public Health"``).

    Returns
    -------
    name_to_id : dict
        ``{normalized_school_name: facility_id}``
    id_to_name : dict
        ``{facility_id: normalized_school_name}``

    Raises
    ------
    FileNotFoundError
        When the mapping file does not exist.
    KeyError
        When *target_phu* is not present in the mapping, with available PHUs
        listed in the message.
    """
    if not mapping_path.exists():
        raise FileNotFoundError(f"PHIX mapping file not found: {mapping_path}")

    data = json.loads(mapping_path.read_text(encoding="utf-8"))
    phus: dict = data.get("phus", {})

    if target_phu not in phus:
        available = ", ".join(f'"{p}"' for p in sorted(phus))
        raise KeyError(
            f"PHU '{target_phu}' not found in {mapping_path.name}. "
            f"Available PHUs: {available}"
        )

    name_to_id: dict[str, str] = phus[target_phu]
    id_to_name: dict[str, str] = {fid: name for name, fid in name_to_id.items() if fid}
    return name_to_id, id_to_name


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_match(
    input_name: str,
    input_id: str,
    name_to_id: dict[str, str],
    id_to_name: dict[str, str],
) -> PHIXMatchResult:
    """Classify one input entry against the PHU's school/ID mapping.

    Parameters
    ----------
    input_name:
        Raw school name from the input (before normalisation).
    input_id:
        Facility ID extracted from the input cell, or ``""`` if absent.
    name_to_id:
        ``{normalized_name: facility_id}`` for the target PHU.
    id_to_name:
        ``{facility_id: normalized_name}`` for the target PHU.
    """
    normalized = normalize_school_name(input_name)

    if normalized in name_to_id:
        mapping_id = name_to_id[normalized]

        if not input_id:
            return PHIXMatchResult(
                input_name=input_name,
                input_id=input_id,
                match_type="inexact",
                matched_name=input_name,
                matched_id=mapping_id,
                mismatch_reason="name_only",
            )
        if input_id == mapping_id:
            return PHIXMatchResult(
                input_name=input_name,
                input_id=input_id,
                match_type="exact",
                matched_name=input_name,
                matched_id=mapping_id,
            )
        return PHIXMatchResult(
            input_name=input_name,
            input_id=input_id,
            match_type="inexact",
            matched_name=input_name,
            matched_id=mapping_id,
            mismatch_reason="id_mismatch",
        )

    # Name not found — try reverse ID lookup
    if input_id and input_id in id_to_name:
        mapped_name = id_to_name[input_id]
        return PHIXMatchResult(
            input_name=input_name,
            input_id=input_id,
            match_type="inexact",
            matched_name=mapped_name,
            matched_id=input_id,
            mismatch_reason="id_only",
        )

    return PHIXMatchResult(
        input_name=input_name,
        input_id=input_id,
        match_type="no_match",
    )


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------


def _write_csv(results: list[PHIXMatchResult], path: Path) -> None:
    """Serialise a list of match results to CSV. No-op when results is empty."""
    if not results:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "input_name": r.input_name,
                "input_id": r.input_id,
                "matched_name": r.matched_name or "",
                "matched_id": r.matched_id or "",
                "mismatch_reason": r.mismatch_reason or "",
            }
            for r in results
        ]
    ).to_csv(path, index=False)
    LOG.info("Wrote %d entries to %s", len(results), path.name)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_schools(
    df: pd.DataFrame,
    mapping_path: Path,
    target_phu: str,
    output_dir: Path,
    school_column: str = "school_name",
    unmatched_behavior: str = "warn",
    column_prefix: str = "phix_",
) -> tuple[pd.DataFrame, list[str]]:
    """Validate school names in *df* against the PHIX mapping for *target_phu*.

    Adds four columns to the DataFrame (with *column_prefix*):

    - ``{prefix}facility_id`` :   Matched facility ID, or ``""``
    - ``{prefix}match_type`` :    ``"exact"`` | ``"inexact"`` | ``"no_match"``
    - ``{prefix}matched_name`` :  Name from the school mapping, or ``""``
    - ``{prefix}matched_phu`` :   *target_phu* for matched rows, ``""`` otherwise



    Writes three CSV files to *output_dir*:

    * ``phix_exact.csv``
    * ``phix_inexact.csv``
    * ``phix_no_match.csv``

    Parameters
    ----------
    df:
        Input DataFrame (not mutated; a copy is returned).
    mapping_path:
        Path to ``phix_mapping.json``.
    target_phu:
        Exact PHU key in the mapping JSON.
    output_dir:
        Directory for CSV output files.
    school_column:
        Column in *df* containing school/daycare names.
    unmatched_behavior:

        ``"warn"``  — log warning, return all rows.

        ``"error"`` — raise ``ValueError`` if any ``no_match`` results.

        ``"skip"``  — filter out rows whose school has no match.

    column_prefix:
        Prefix applied to all output column names.

    Returns
    -------
    tuple[DataFrame, list[str]]
        Enriched DataFrame and a list of human-readable warning strings.
    """
    warnings: list[str] = []

    if school_column not in df.columns:
        LOG.warning(
            "Column '%s' not found in DataFrame — skipping PHIX validation.",
            school_column,
        )
        return df, warnings

    name_to_id, id_to_name = load_mapping(mapping_path, target_phu)
    LOG.info("Loaded %d schools for PHU '%s'.", len(name_to_id), target_phu)

    # Classify each unique input value (deduplicated for efficiency)
    results: dict[str, PHIXMatchResult] = {}
    for raw in df[school_column].dropna().unique():
        name, fac_id = parse_input_entry(str(raw))
        results[str(raw)] = classify_match(name, fac_id, name_to_id, id_to_name)

    # Enrich DataFrame
    df = df.copy()

    def _attr(raw_val: object, attr: str, default: str = "") -> str:
        r = results.get(str(raw_val))
        return getattr(r, attr, default) if r else default

    def col(suffix: str) -> str:
        return f"{column_prefix}{suffix}"

    df[col("facility_id")] = df[school_column].apply(
        lambda x: _attr(x, "matched_id") if pd.notna(x) else ""
    )
    df[col("match_type")] = df[school_column].apply(
        lambda x: _attr(x, "match_type", "no_match") if pd.notna(x) else "no_match"
    )
    df[col("matched_name")] = df[school_column].apply(
        lambda x: _attr(x, "matched_name") if pd.notna(x) else ""
    )
    df[col("matched_phu")] = df[school_column].apply(
        lambda x: target_phu
        if pd.notna(x) and _attr(x, "match_type", "no_match") != "no_match"
        else ""
    )

    # Split into categories
    exact = [r for r in results.values() if r.match_type == "exact"]
    inexact = [r for r in results.values() if r.match_type == "inexact"]
    no_match = [r for r in results.values() if r.match_type == "no_match"]

    # Write CSVs
    _write_csv(exact, output_dir / "phix_exact.csv")
    _write_csv(inexact, output_dir / "phix_inexact.csv")
    _write_csv(no_match, output_dir / "phix_no_match.csv")

    LOG.info(
        "PHIX validation complete: %d exact, %d inexact, %d no_match",
        len(exact),
        len(inexact),
        len(no_match),
    )

    if no_match:
        no_match_names = sorted(r.input_name for r in no_match)
        msg = (
            f"{len(no_match)} school(s) had no PHIX match for PHU '{target_phu}'. "
            f"See phix_no_match.csv for details."
        )
        warnings.append(msg)
        LOG.warning("%s First unmatched: %s", msg, no_match_names[:5])

        if unmatched_behavior == "error":
            raise ValueError(msg)
        elif unmatched_behavior == "skip":
            matched_inputs = {
                raw for raw, r in results.items() if r.match_type != "no_match"
            }
            before = len(df)
            df = df[df[school_column].isin(matched_inputs)]
            skipped = before - len(df)
            warnings.append(f"Skipped {skipped} record(s) with no PHIX match.")
            LOG.info(
                "Skipped %d records with no PHIX match, %d remaining.", skipped, len(df)
            )

    return df, warnings
