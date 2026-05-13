"""Validate schools and daycares against PHIX Reference List.

This module provides validation of school/daycare names against a canonical
PHIX reference list. It supports strict exact matching plus PHU alias
scoping to prevent cross-jurisdiction matches.

**Input Contract:**
- PHIX reference Excel file must exist at configured path
- Reference file must contain 'Schools & Day Cares' sheet
- Each column is a PHU, values are "FACILITY NAME - ID" format

**Output Contract:**
- Returns validation results with matched facility IDs and confidence scores
- Writes unmatched facilities to CSV for PHU review
- Raises or warns based on configured `unmatched_behavior`

**Usage:**
    Called from preprocess.py after address validation, before building results.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

import pandas as pd
import yaml

LOG = logging.getLogger(__name__)


# ============================================================================
# Output Column Definitions (1.2: Extract to Constants)
# ============================================================================

PHIX_OUTPUT_COLUMNS = {
    "id": "FACILITY_ID",
    "confidence": "PHIX_MATCH_CONFIDENCE",
    "match_type": "PHIX_MATCH_TYPE",
    "phu_name": "PHIX_MATCHED_PHU",
    "phu_code": "PHIX_MATCHED_PHU_CODE",
    "target_phu_code": "PHIX_TARGET_PHU_CODE",
    "target_phu_label": "PHIX_TARGET_PHU_LABEL",
}


# ============================================================================
# Caching Classes (1.1: Replace Global State)
# ============================================================================


class PHIXReferenceCache:
    """Thread-safe in-memory cache for PHIX reference data."""

    def __init__(self, cache_enabled: bool = True) -> None:
        """Initialize the cache.
        
        Parameters
        ----------
        cache_enabled : bool
            If False, disables caching (useful for testing)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._enabled = cache_enabled

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached data by path key.
        
        Parameters
        ----------
        path : str
            Resolved path key (str of Path.resolve())
        
        Returns
        -------
        Dict or None
            Cached data, or None if not in cache or caching disabled
        """
        if not self._enabled:
            return None
        return self._cache.get(path)

    def set(self, path: str, data: Dict[str, Any]) -> None:
        """Store data in cache.
        
        Parameters
        ----------
        path : str
            Resolved path key (str of Path.resolve())
        data : Dict
            Data to cache (should include "_cache_path" key)
        """
        if self._enabled:
            self._cache[path] = data

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()


# Global instances for backward compatibility
_PHIX_REFERENCE_LOADER = PHIXReferenceCache(cache_enabled=True)
_PHU_MAPPING_LOADER = PHIXReferenceCache(cache_enabled=True)


@dataclass
class PHIXFacility:
    """A facility entry from the PHIX reference list."""

    facility_id: str
    name: str
    phu: str  # Public Health Unit that owns this facility

    def __hash__(self) -> int:
        return hash((self.facility_id, self.name, self.phu))


@dataclass
class PHIXMatchResult:
    """Result of matching a facility against PHIX reference."""

    input_name: str
    matched: bool
    facility_id: Optional[str] = None
    phix_name: Optional[str] = None
    phu_name: Optional[str] = None
    phu_code: Optional[str] = None
    confidence: int = 0
    match_type: str = "none"  # exact, no_facility_id, wrong_facility_id, or none


def parse_facility_entry(entry: str, phu: str) -> Optional[PHIXFacility]:
    """Parse a PHIX facility entry in 'NAME - ID' format.

    Parameters
    ----------
    entry : str
        Raw entry from Excel like "ANNA MCCREA PUBLIC SCHOOL - 019186"
    phu : str
        Name of the Public Health Unit column

    Returns
    -------
    PHIXFacility or None
        Parsed facility, or None if entry is empty/invalid
    """
    if not entry or pd.isna(entry):
        return None

    entry = str(entry).strip()
    if not entry:
        return None

    # Parse "NAME - ID" format, where ID is the last segment after " - "
    # Some names contain " - " so we split from the right
    parts = entry.rsplit(" - ", maxsplit=1)
    if len(parts) == 2:
        name = parts[0].strip()
        facility_id = parts[1].strip()
    else:
        # No ID separator found, use entire string as name
        name = entry
        facility_id = ""

    return PHIXFacility(facility_id=facility_id, name=name, phu=phu)


def load_phix_reference(
    reference_path: Path,
    sheet_name: str = "Schools & Day Cares",
) -> Dict[str, Any]:
    """Load and parse the PHIX reference Excel file.

    Caches the result for subsequent calls with the same path.

    Parameters
    ----------
    reference_path : Path
        Path to the PHIX reference Excel file
    sheet_name : str
        Name of the sheet containing school/daycare data

    Returns
    -------
    Dict with keys:
        - facilities: List[PHIXFacility] - all parsed facilities
        - by_name: Dict[str, PHIXFacility] - lookup by normalized name
        - by_name_phu: Dict[str, Dict[str, PHIXFacility]] - lookup by PHU column
        - phus: List[str] - list of PHU column names
    """
    cache_key = str(reference_path.resolve())
    
    # Check cache first
    cached = _PHIX_REFERENCE_LOADER.get(cache_key)
    if cached is not None:
        return cached

    if not reference_path.exists():
        raise FileNotFoundError(f"PHIX reference file not found: {reference_path}")

    LOG.info("Loading PHIX reference from %s", reference_path)
    df = pd.read_excel(reference_path, sheet_name=sheet_name)

    facilities: List[PHIXFacility] = []
    by_name: Dict[str, PHIXFacility] = {}
    by_name_phu: Dict[str, Dict[str, PHIXFacility]] = {}
    seen_names: Set[str] = set()

    for phu_column in df.columns:
        for entry in df[phu_column].dropna():
            facility = parse_facility_entry(entry, phu_column)
            if facility:
                facilities.append(facility)
                # Use normalized name as key for exact matching
                normalized = normalize_facility_name(facility.name)
                by_name_phu.setdefault(normalized, {})[phu_column] = facility
                if normalized not in seen_names:
                    by_name[normalized] = facility
                    seen_names.add(normalized)

    LOG.info(
        "Loaded %d facilities from %d PHUs", len(facilities), len(df.columns)
    )

    result = {
        "_cache_path": cache_key,
        "facilities": facilities,
        "by_name": by_name,
        "by_name_phu": by_name_phu,
        "phus": list(df.columns),
    }
    _PHIX_REFERENCE_LOADER.set(cache_key, result)
    return result


def normalize_phu_code(code: str) -> str:
    """Normalize a PHU acronym/template key for comparison."""
    if not code:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", "_", code.strip().lower())
    return normalized.strip("_")


def normalize_phu_label(label: str) -> str:
    """Normalize PHU names/aliases for lookup."""
    if not label:
        return ""
    return re.sub(r"\s+", " ", str(label).strip().upper())


def load_phu_aliases(mapping_path: Path) -> Dict[str, Any]:
    """Load canonical PHU aliases from YAML mapping file."""
    cache_key = str(mapping_path.resolve())
    
    # Check cache first
    cached = _PHU_MAPPING_LOADER.get(cache_key)
    if cached is not None:
        return cached

    if not mapping_path.exists():
        raise FileNotFoundError(f"PHU alias mapping file not found: {mapping_path}")

    raw = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    entries = raw.get("phu_aliases")
    if not isinstance(entries, dict):
        raise ValueError(
            f"Invalid PHU alias mapping format in {mapping_path}. "
            "Expected top-level 'phu_aliases' dictionary."
        )

    alias_to_code: Dict[str, str] = {}
    code_to_display: Dict[str, str] = {}
    code_to_aliases: Dict[str, Set[str]] = {}

    for code, meta in entries.items():
        normalized_code = normalize_phu_code(code)
        if not normalized_code:
            continue

        meta = meta or {}
        display_name = str(meta.get("display_name") or code).strip()
        code_to_display[normalized_code] = display_name

        aliases = meta.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]

        alias_candidates = set(
            filter(
                None,
                [
                    *[str(alias) for alias in aliases],
                    code,
                    display_name,
                ],
            )
        )

        for alias in alias_candidates:
            normalized_alias = normalize_phu_label(alias)
            if not normalized_alias:
                continue
            alias_to_code[normalized_alias] = normalized_code
            code_to_aliases.setdefault(normalized_code, set()).add(str(alias).strip())

    result = {
        "_cache_path": cache_key,
        "alias_to_code": alias_to_code,
        "code_to_display": code_to_display,
        "code_to_aliases": code_to_aliases,
    }
    _PHU_MAPPING_LOADER.set(cache_key, result)
    return result


def normalize_facility_name(name: str) -> str:
    """Normalize a facility name for comparison.

    Converts to uppercase, removes extra whitespace, and standardizes
    common abbreviations.

    Parameters
    ----------
    name : str
        Raw facility name

    Returns
    -------
    str
        Normalized name for comparison
    """
    if not name:
        return ""

    # Uppercase and strip
    normalized = name.upper().strip()

    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized


def match_facility(
    input_name: str,
    reference: Dict[str, Any],
    facility_phu_codes: Optional[Dict[str, Optional[str]]] = None,
) -> PHIXMatchResult:
    """Match a single facility name against PHIX reference using exact match."""
    if not input_name or not input_name.strip():
        return PHIXMatchResult(
            input_name=input_name or "",
            matched=False,
            match_type="none",
        )

    # Input normalization - split facility ID if present in column
    normalized_entry = parse_facility_entry(input_name, phu="")
    normalized_input = normalize_facility_name(normalized_entry.name)
    by_name = reference["by_name"]

    # Try exact match first
    if normalized_input in by_name:
        facility = by_name[normalized_input]

        phu_code = facility_phu_codes.get(normalized_input) if facility_phu_codes else None

        if normalized_entry.facility_id and by_name[normalized_input].facility_id == normalized_entry.facility_id:
            return PHIXMatchResult(
                input_name=input_name,
                matched=True,
                facility_id=facility.facility_id,
                phix_name=facility.name,
                phu_name=facility.phu,
                phu_code=phu_code,
                confidence=100,
                match_type="exact",
            )
        elif normalized_entry.facility_id:
            return PHIXMatchResult(
                input_name=input_name,
                matched=False,
                facility_id=facility.facility_id,
                phix_name=facility.name,
                phu_name=facility.phu,
                phu_code=phu_code,
                confidence=100,
                match_type="wrong_facility_id",
            )
        else:
            return PHIXMatchResult(
                input_name=input_name,
                matched=True,
                facility_id=facility.facility_id,
                phix_name=facility.name,
                phu_name=facility.phu,
                phu_code=phu_code,
                confidence=100,
                match_type="no_facility_id",
            )

    return PHIXMatchResult(
        input_name=input_name,
        matched=False,
        match_type="none",
    )


def _enrich_dataframe_with_phix(
    df: pd.DataFrame,
    school_column: str,
    match_results: Dict[str, PHIXMatchResult],
    target_codes_str: Optional[str],
    target_display: Optional[str],
    column_prefix: str = "PHIX_",
) -> pd.DataFrame:
    """Enrich DataFrame with PHIX validation columns.
    
    Consolidates all PHIX output columns in a single operation using
    the PHIX_OUTPUT_COLUMNS constant for maintainability.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to enrich (assumed to be a copy)
    school_column : str
        Name of the facility name column
    match_results : Dict[str, PHIXMatchResult]
        Lookup of facility names to match results
    target_codes_str : Optional[str]
        Target PHU codes as comma-separated string
    target_display : Optional[str]
        Target PHU display label
    column_prefix : str
        Prefix for output column names (default: "PHIX_")
    
    Returns
    -------
    pd.DataFrame
        DataFrame with PHIX columns added
    """
    # Helper to get match result or default
    def get_result(facility_name: str) -> PHIXMatchResult:
        if pd.isna(facility_name):
            return PHIXMatchResult(str(facility_name) if facility_name is not None else "", False)
        return match_results.get(str(facility_name), PHIXMatchResult(str(facility_name), False))
    
    # Build column names with custom prefix
    col_names = {
        "id": f"{column_prefix}ID",
        "confidence": f"{column_prefix}MATCH_CONFIDENCE",
        "match_type": f"{column_prefix}MATCH_TYPE",
        "phu_name": f"{column_prefix}MATCHED_PHU",
        "phu_code": f"{column_prefix}MATCHED_PHU_CODE",
        "target_phu_code": f"{column_prefix}TARGET_PHU_CODE",
        "target_phu_label": f"{column_prefix}TARGET_PHU_LABEL",
    }
    
    # Populate fields from mapping
    for field_name, col_name in col_names.items():
        if field_name.startswith("target_"):
            # Target fields are constants (not from results)
            if field_name == "target_phu_code":
                df[col_name] = target_codes_str
            elif field_name == "target_phu_label":
                df[col_name] = target_display
        else:
            # Result fields are extracted from match results
            if field_name == "id":
                df[col_name] = df[school_column].apply(
                    lambda x: get_result(x).facility_id if pd.notna(x) else None
                )
            elif field_name == "confidence":
                df[col_name] = df[school_column].apply(
                    lambda x: get_result(x).confidence if pd.notna(x) else 0
                )
            elif field_name == "match_type":
                df[col_name] = df[school_column].apply(
                    lambda x: get_result(x).match_type if pd.notna(x) else "none"
                )
            elif field_name == "phu_name":
                df[col_name] = df[school_column].apply(
                    lambda x: get_result(x).phu_name if pd.notna(x) else None
                )
            elif field_name == "phu_code":
                df[col_name] = df[school_column].apply(
                    lambda x: get_result(x).phu_code if pd.notna(x) else None
                )
    
    return df


def validate_facilities(
    df: pd.DataFrame,
    reference_path: Path,
    output_dir: Path,
    unmatched_behavior: str = "warn",
    school_column: Union[str, List[str]] = "SCHOOL_NAME",
    target_phu_codes: Optional[Iterable[str]] = None,
    phu_mapping_path: Optional[Path] = None,
    reference_sheet_name: str = "Schools & Day Cares",
    column_prefix: str = "PHIX_",
) -> Tuple[pd.DataFrame, List[str]]:
    """Validate facilities in DataFrame against PHIX reference.

    Supports validation of one or more facility columns in a single pass.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame with facility names
    reference_path : Path
        Path to PHIX reference Excel file
    output_dir : Path
        Directory to write unmatched facilities CSV
    unmatched_behavior : str
        How to handle unmatched facilities:
        - 'warn': Log warning, continue processing all records
        - 'error': Raise ValueError if any unmatched
        - 'skip': Filter out unmatched records
    school_column : str or List[str]
        Name of column(s) containing facility names. Can be a single column name
        or a list of column names to validate multiple facility types (e.g.,
        ["SCHOOL_NAME", "DAYCARE_NAME"]).
    target_phu_codes : Iterable[str], optional
        Canonical PHU codes (matching template folders) to restrict validation.
        When provided, only facilities that belong to these PHUs are considered.
    phu_mapping_path : Path, optional
        Path to YAML mapping file that links PHIX column names to canonical PHU
        codes. Required when target_phu_codes are provided.
    reference_sheet_name : str
        Name of the Excel sheet containing facility data (default: "Schools & Day Cares")
    column_prefix : str
        Prefix for output column names (default: "PHIX_")

    Returns
    -------
    Tuple[pd.DataFrame, List[str]]
        - DataFrame with PHIX validation columns added
        - List of warning messages

    Raises
    ------
    ValueError
        If unmatched_behavior is 'error' and unmatched facilities exist
    """
    # Normalize school_column to list for uniform processing
    columns_to_validate: List[str] = (
        [school_column] if isinstance(school_column, str) else list(school_column)
    )
    
    warnings: List[str] = []
    
    # Validate and process each column
    for column in columns_to_validate:
        df, column_warnings = _validate_single_column(
            df=df,
            reference_path=reference_path,
            output_dir=output_dir,
            unmatched_behavior=unmatched_behavior,
            school_column=column,
            target_phu_codes=target_phu_codes,
            phu_mapping_path=phu_mapping_path,
            reference_sheet_name=reference_sheet_name,
            column_prefix=column_prefix,
        )
        warnings.extend(column_warnings)
    
    return df, warnings


def _validate_single_column(
    df: pd.DataFrame,
    reference_path: Path,
    output_dir: Path,
    unmatched_behavior: str = "warn",
    school_column: str = "SCHOOL_NAME",
    target_phu_codes: Optional[Iterable[str]] = None,
    phu_mapping_path: Optional[Path] = None,
    reference_sheet_name: str = "Schools & Day Cares",
    column_prefix: str = "PHIX_",
) -> Tuple[pd.DataFrame, List[str]]:
    """Validate a single facility column against PHIX reference.
    
    This is the internal implementation called by validate_facilities().
    Users should call validate_facilities() instead.
    
    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame with facility names
    reference_path : Path
        Path to PHIX reference Excel file
    output_dir : Path
        Directory to write unmatched facilities CSV
    unmatched_behavior : str
        How to handle unmatched facilities
    school_column : str
        Name of column containing facility names
    target_phu_codes : Iterable[str], optional
        Canonical PHU codes to restrict validation
    phu_mapping_path : Path, optional
        Path to YAML mapping file for PHU codes
    reference_sheet_name : str
        Name of Excel sheet containing facility data
    column_prefix : str
        Prefix for output column names
    
    Returns
    -------
    Tuple[pd.DataFrame, List[str]]
        DataFrame with PHIX validation columns and warning messages
    """
    warnings: List[str] = []

    if school_column not in df.columns:
        LOG.warning("Column '%s' not found, skipping PHIX validation", school_column)
        return df, warnings

    # Load reference with configurable sheet name
    reference = load_phix_reference(reference_path, sheet_name=reference_sheet_name)

    phu_mapping_data: Optional[Dict[str, Any]] = None
    alias_lookup: Dict[str, str] = {}
    if phu_mapping_path:
        phu_mapping_data = load_phu_aliases(phu_mapping_path)
        alias_lookup = phu_mapping_data.get("alias_to_code", {})

    normalized_target_codes: Set[str] = set()
    if target_phu_codes:
        for code in target_phu_codes:
            normalized = normalize_phu_code(code)
            if normalized:
                normalized_target_codes.add(normalized)
        if normalized_target_codes and not phu_mapping_data:
            LOG.error(
                "PHU scoping requires phu_mapping_file to be configured. "
                "Either: (1) set target_phu_code: null in phix_validation config, or "
                "(2) ensure phix_validation.phu_mapping_file points to config/phu_aliases.yaml"
            )
            raise ValueError(
                "Target PHU codes provided but phu_mapping_file is not configured. "
                "Update phix_validation.phu_mapping_file to scope validation."
            )

    if normalized_target_codes and phu_mapping_data:
        code_to_display = phu_mapping_data.get("code_to_display", {})
        missing_codes = sorted(
            code for code in normalized_target_codes if code not in code_to_display
        )
        if missing_codes:
            LOG.error(
                "The following PHU codes from target_phu_code are not defined in %s: %s. "
                "Add these codes to phu_aliases.yaml under 'phu_aliases' section.",
                phu_mapping_path,
                ", ".join(missing_codes),
            )
            raise ValueError(
                f"Template PHU codes not defined in {phu_mapping_path}: "
                f"{', '.join(missing_codes)}. Update config/phu_aliases.yaml."
            )

    phu_column_codes: Dict[str, str] = {}
    if alias_lookup:
        for phu_column in reference["phus"]:
            canonical_code = alias_lookup.get(normalize_phu_label(phu_column))
            if canonical_code:
                phu_column_codes[phu_column] = canonical_code

    reference_for_matching = reference
    target_display: Optional[str] = None
    target_codes_str: Optional[str] = None

    if normalized_target_codes:
        allowed_phu_columns = [
            column
            for column, code in phu_column_codes.items()
            if code in normalized_target_codes
        ]
        if not allowed_phu_columns:
            raise ValueError(
                "No PHIX columns mapped to the requested PHU codes. "
                f"Template codes: {', '.join(sorted(normalized_target_codes))}. "
                "Confirm config/phu_aliases.yaml contains the PHIX column names."
            )

        by_name_phu: Dict[str, Dict[str, PHIXFacility]] = reference.get(
            "by_name_phu", {}
        )
        filtered_by_name: Dict[str, PHIXFacility] = {}
        filtered_name_list: List[str] = []
        for normalized_name, facilities_by_phu in by_name_phu.items():
            for phu_label in allowed_phu_columns:
                facility = facilities_by_phu.get(phu_label)
                if facility:
                    filtered_by_name[normalized_name] = facility
                    filtered_name_list.append(normalized_name)
                    break

        if not filtered_by_name:
            raise ValueError(
                "No PHIX reference entries found for the requested PHU columns. "
                f"Columns: {', '.join(sorted(allowed_phu_columns))}. "
                "Verify the mapping file includes every PHIX alias."
            )

        reference_for_matching = dict(reference)
        reference_for_matching["by_name"] = filtered_by_name
        reference_for_matching["name_list"] = filtered_name_list

        code_to_display = phu_mapping_data.get("code_to_display", {}) if phu_mapping_data else {}
        target_display = ", ".join(
            code_to_display.get(code, code).strip() for code in sorted(normalized_target_codes)
        )
        target_codes_str = ",".join(sorted(normalized_target_codes))
        LOG.info(
            "Restricting PHIX validation to PHU(s): %s",
            target_display or target_codes_str,
        )

    facility_phu_codes_for_matching: Dict[str, Optional[str]] = {}
    if alias_lookup:
        for normalized_name, facility in reference_for_matching["by_name"].items():
            canonical_code = alias_lookup.get(normalize_phu_label(facility.phu))
            if canonical_code:
                facility_phu_codes_for_matching[normalized_name] = canonical_code

    # Match each unique facility
    unique_facilities = df[school_column].dropna().unique()
    match_results: Dict[str, PHIXMatchResult] = {}

    for facility_name in unique_facilities:
        result = match_facility(
            str(facility_name),
            reference_for_matching,
            facility_phu_codes=(
                facility_phu_codes_for_matching
                if facility_phu_codes_for_matching
                else None
            ),
        )
        match_results[str(facility_name)] = result

    # Add validation columns to DataFrame using consolidated logic
    df = df.copy()
    df = _enrich_dataframe_with_phix(
        df,
        school_column,
        match_results,
        target_codes_str,
        target_display,
        column_prefix=column_prefix,
    )


    # Classify match outcomes
    exact_matches = [r for r in match_results.values() if r.match_type == "exact"]
    inexact_matches = [r for r in match_results.values() if r.match_type == "no_facility_id"]
    wrong_facility_id_matches = [r for r in match_results.values() if r.match_type == "wrong_facility_id"]
    none_matches = [r for r in match_results.values() if r.match_type == "none"]

    # Identify unmatched facilities
    unmatched = wrong_facility_id_matches + none_matches



    if unmatched:
        unmatched_names = sorted(set(r.input_name for r in unmatched))
        LOG.warning(
            "%d facilities failed strict PHIX validation (name not found or facility ID mismatch): %s",
            len(unmatched_names),
            unmatched_names[:5],  # Log first 5
        )

        # Write unmatched to CSV
        output_dir.mkdir(parents=True, exist_ok=True)
        unmatched_path = output_dir / "unmatched_facilities.csv"
        unmatched_df = pd.DataFrame(
            [
                {
                    "facility_name": r.input_name,
                    "match_type": r.match_type,
                    "confidence": r.confidence,
                    "matched_phix_name": r.phix_name,
                    "matched_facility_id": r.facility_id,
                    "matched_phu": r.phu_name,
                    "matched_phu_code": r.phu_code,
                    "target_phu_code": target_codes_str or "",
                    "target_phu_label": target_display or "",
                }
                for r in unmatched
            ]
        )
        unmatched_df.to_csv(unmatched_path, index=False)
        LOG.info("Wrote %d unmatched facilities to %s", len(unmatched), unmatched_path)

        warnings.append(
            f"{len(none_matches)} facilities had no PHIX name match and "
            f"{len(wrong_facility_id_matches)} facilities had a facility ID mismatch (name matched, ID differed). "
            f"See {unmatched_path} for details."
        )

        if unmatched_behavior == "error":
            raise ValueError(
                f"{len(unmatched_names)} facilities failed strict PHIX validation (missing PHIX name match or facility ID mismatch): "
                f"{', '.join(unmatched_names[:10])}"
                + (f" (and {len(unmatched_names) - 10} more)" if len(unmatched_names) > 10 else "")
            )
        elif unmatched_behavior == "skip":
            # Filter out rows with unmatched facilities
            matched_names = {r.input_name for r in match_results.values() if r.matched}
            original_count = len(df)
            df = df[df[school_column].isin(matched_names)]
            filtered_count = original_count - len(df)
            LOG.info(
                "Filtered %d records that failed strict PHIX validation (no name match or ID mismatch), %d remaining",
                filtered_count,
                len(df),
            )
            warnings.append(
                f"Filtered {filtered_count} records that failed strict PHIX validation (no name match or ID mismatch)."
            )

    if inexact_matches:
        inexact_names = sorted(set(r.input_name for r in inexact_matches))
        LOG.warning(
            "%d facilities matched PHIX by name only (input facility ID missing): %s",
            len(inexact_names),
            inexact_names[:5],  # Log first 5
        )

        # Write unmatched to CSV
        output_dir.mkdir(parents=True, exist_ok=True)
        inexact_path = output_dir / "inexact_matched_facilities.csv"
        inexact_df = pd.DataFrame(
            [
                {
                    "facility_name": r.input_name,
                    "match_type": r.match_type,
                    "confidence": r.confidence,
                    "matched_phix_name": r.phix_name,
                    "matched_facility_id": r.facility_id,
                    "matched_phu": r.phu_name,
                    "matched_phu_code": r.phu_code,
                    "target_phu_code": target_codes_str or "",
                    "target_phu_label": target_display or "",
                }
                for r in inexact_matches
            ]
        )
        inexact_df.to_csv(inexact_path, index=False)
        LOG.info("Wrote %d inexact matched facilities to %s", len(inexact_matches), inexact_path)
        warnings.append(
            f"{len(inexact_names)} facilities matched by name without facility ID. "
            f"See {inexact_path} for details."
        )

    # Save exact matches
    if exact_matches:
         # Write exact matched to CSV
        output_dir.mkdir(parents=True, exist_ok=True)
        exact_path = output_dir / "exact_matched_facilities.csv"
        exact_df = pd.DataFrame(
            [
                {
                    "facility_name": r.input_name,
                    "match_type": r.match_type,
                    "confidence": r.confidence,
                    "matched_phix_name": r.phix_name,
                    "matched_facility_id": r.facility_id,
                    "matched_phu": r.phu_name,
                    "matched_phu_code": r.phu_code,
                    "target_phu_code": target_codes_str or "",
                    "target_phu_label": target_display or "",
                }
                for r in exact_matches
            ]
        )
        exact_df.to_csv(exact_path, index=False)


    # Log summary
    matched_count = sum(1 for r in match_results.values() if r.matched)
    LOG.info(
        "PHIX validation complete: %d matched (exact=%d, no_facility_id=%d), %d unmatched (wrong_facility_id=%d, none=%d)",
        matched_count,
        len(exact_matches),
        len(inexact_matches),
        len(unmatched),
        len(wrong_facility_id_matches),
        len(none_matches),
    )

    return df, warnings


def clear_cache() -> None:
    """Clear the PHIX reference cache. Useful for testing."""
    _PHIX_REFERENCE_LOADER.clear()
    _PHU_MAPPING_LOADER.clear()
