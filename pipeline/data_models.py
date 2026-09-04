"""Unified data models for the immunization pipeline.

This module provides all core dataclasses used throughout the pipeline,
ensuring consistency and type safety across processing steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class ClientRecord:
    """Unified client record across all pipeline steps.

    This dataclass represents a single client (student) record passed through
    the entire pipeline. It contains all necessary information for:
    
    - Generating personalized notices
    - Creating QR codes
    - Encrypting PDFs
    - Batching outputs

    Fields
    ------
    sequence : str
        Zero-padded sequence number for the client (e.g., '00001').

    client_id : str
        Unique client identifier.

    language : str
        ISO 639-1 language code ('en' or 'fr'). Must be a valid Language enum value
        (see pipeline.enums.Language). Validated using Language.from_string() at entry
        points (CLI, configuration loading, preprocessing). All functions assume this
        field contains a valid language code; invalid codes should be caught before
        ClientRecord instantiation.

    person : Dict[str, Any]

        - Person details:
            - first_name: Given name
            - last_name: Family name
            - date_of_birth: Display format (e.g., "Jan 8, 2025")
            - date_of_birth_iso: ISO format (YYYY-MM-DD)
            - date_of_birth_display: Localized display format
            - age: Calculated age in years (as string)
            - over_16: Boolean flag for age >= 16

    school : Dict[str, Any]
        School information: name, id.

    board : Dict[str, Any]
        School board information: name, id.

    contact : Dict[str, Any]
        Contact address: street, city, province, postal_code.

    vaccines_due : Optional[str]
        Comma-separated string of vaccines due (display format).

    vaccines_due_list : Optional[List[str]]
        List of canonical disease names due.

    vaccines_due_agent_list : Optional[List[str]]
        List of vaccine agent names due.

    received : Optional[Sequence[Dict[str, object]]]
        List of vaccine records already received (structured data).

    metadata : Dict[str, object]
        Custom pipeline metadata (warnings, flags, etc.).
        
    qr : Optional[Dict[str, Any]]
    
        - QR code information (if generated):
            - payload: URL encoded in QR code (same string that becomes QR PNG data)
            - filename: PNG filename (e.g., "qr_code_00001_1234567890.png")
            - path: Relative path to PNG file
    """

    sequence: str
    client_id: str
    language: str
    person: Dict[str, Any]
    school: Dict[str, Any]
    board: Dict[str, Any]
    contact: Dict[str, Any]
    vaccines_due: Optional[str]
    vaccines_due_list: Optional[List[str]]
    vaccines_due_agent_list: Optional[List[str]]
    received: Optional[Sequence[Dict[str, object]]]
    metadata: Dict[str, object]
    qr: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class PreprocessResult:
    """Result of preprocessing step.

    The output of Step 2 (preprocessing) that contains normalized client data
    and any warnings generated during processing.

    Parameters
    ----------
    clients : List[ClientRecord]
        Processed and validated client records.
    warnings : List[str]
        Non-fatal warnings encountered during preprocessing (e.g., missing
        optional fields, unrecognized vaccine codes).
    """

    clients: List[ClientRecord]
    warnings: List[str]


@dataclass(frozen=True)
class ArtifactPayload:
    """Preprocessed artifact with metadata.

    The JSON artifact written by Step 2 (preprocessing) and read by downstream
    steps. Contains all normalized client data and provenance information.

    Parameters
    ----------
    run_id : str
        Unique pipeline run identifier (timestamp-based).
    language : str
        ISO 639-1 language code ('en' or 'fr'). Must be a valid Language enum value
        (see pipeline.enums.Language). All clients in the artifact must have language
        codes that match this field; validation ensures consistency across all
        notices generated in a single run.
    clients : List[ClientRecord]
        All processed client records.
    warnings : List[str]
        All preprocessing warnings.
    created_at : str
        ISO 8601 timestamp when artifact was created.
    input_file : Optional[str]
        Name of the input file processed (for audit trail).
    total_clients : int
        Total number of clients in artifact (convenience field).
    """

    run_id: str
    language: str
    clients: List[ClientRecord]
    warnings: List[str]
    created_at: str
    input_file: Optional[str] = None
    total_clients: int = 0
    assignment_mode: str = "fixed"       # "fixed" | "manifest"
    default_version: Optional[str] = None


@dataclass(frozen=True)
class PdfRecord:
    """Compiled PDF with client metadata.

    Represents a single generated PDF notice with its associated client
    data and page count. Used during batching (Step 8) to group PDFs
    and generate manifests.

    Parameters
    ----------
    sequence : str
        Zero-padded sequence number matching the PDF filename.
    client_id : str
        Client identifier matching the PDF filename.
    pdf_path : Path
        Absolute path to the generated PDF file.
    page_count : int
        Number of pages in the PDF (usually 2 for immunization notices).
    client : Dict[str, Any]
        Full client data dict for manifest generation and batching.
    """

    sequence: str
    client_id: str
    pdf_path: Path
    page_count: int
    client: Dict[str, Any]
