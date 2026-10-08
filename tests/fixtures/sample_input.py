"""Synthetic source rows and canonical clients for pipeline tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pandas as pd

from immuknow import data_models


def create_test_input_dataframe(
    num_clients: int = 5,
    include_overdue: bool = True,
    include_immunization_history: bool = True,
) -> pd.DataFrame:
    """Generate a realistic input DataFrame for preprocessing tests.

    Real-world significance:
    - Simulates CSV input from school districts
    - Enables testing of data normalization without requiring actual input files
    - Supports testing of edge cases (missing fields, various formats, etc.)

    Parameters
    ----------
    num_clients : int, default 5
        Number of client rows to generate
    include_overdue : bool, default True
        Whether to include OVERDUE DISEASE column with disease names
    include_immunization_history : bool, default True
        Whether to include IMMS GIVEN column with vaccination history

    Returns
    -------
    pd.DataFrame
        DataFrame with columns matching expected CSV input format
    """
    data: Dict[str, List[Any]] = {
        "school_name": [
            "Tunnel Academy",
            "Cheese Wheel Academy",
            "Mountain Heights Public School",
            "River Valley Elementary",
            "Downtown Collegiate",
        ][:num_clients],
        "client_id": [f"{i:010d}" for i in range(1, num_clients + 1)],
        "first_name": ["Alice", "Benoit", "Chloe", "Diana", "Ethan"][:num_clients],
        "last_name": ["Zephyr", "Arnaud", "Brown", "Davis", "Evans"][:num_clients],
        "date_of_birth": [
            "2015-01-02",
            "2014-05-06",
            "2013-08-15",
            "2015-03-22",
            "2014-11-10",
        ][:num_clients],
        "board_name": [
            "Guelph Board of Education",
            "Guelph Board of Education",
            "Wellington Board of Education",
            "Wellington Board of Education",
            "Ontario Public Schools",
        ][:num_clients],
        "street_address_line_1": [
            "123 Main St",
            "456 Side Rd",
            "789 Oak Ave",
            "321 Elm St",
            "654 Maple Dr",
        ][:num_clients],
        "street_address_line_2": ["", "Suite 5", "", "Apt 12", ""][:num_clients],
        "city": ["Guelph", "Guelph", "Wellington", "Wellington", "Toronto"][
            :num_clients
        ],
        "province": ["ON", "ON", "ON", "ON", "ON"][:num_clients],
        "postal_code": ["N1H 2T2", "N1H 2T3", "N1K 1B2", "N1K 1B3", "M5V 3A8"][
            :num_clients
        ],
        "overdue_disease": (
            [
                "Measles/Mumps/Rubella",
                "Haemophilus influenzae infection, invasive",
                "Diphtheria/Tetanus/Pertussis",
                "Polio",
                "Pneumococcal infection, invasive",
            ][:num_clients]
            if include_overdue
            else [""] * num_clients
        ),
        "overdue_agent": (
            ["MMR", "Hib", "DTaP", "IPV", "PCV13"][:num_clients]
            if include_overdue
            else [""] * num_clients
        ),
        "imms_given": (
            [
                "May 01, 2020 - DTaP; Jun 15, 2021 - MMR",
                "Apr 10, 2019 - IPV",
                "Sep 05, 2020 - Varicella",
                "",
                "Jan 20, 2022 - DTaP; Feb 28, 2022 - IPV",
            ][:num_clients]
            if include_immunization_history
            else [""] * num_clients
        ),
    }

    return pd.DataFrame(data)


def create_test_client_record(
    sequence: str = "00001",
    client_id: str = "0000000001",
    language: str = "en",
    first_name: str = "Alice",
    last_name: str = "Zephyr",
    date_of_birth: str = "2015-01-02",
    school_name: str = "Tunnel Academy",
    board_name: str = "Guelph Board",
    overdue_diseases: Optional[List[str]] = None,
    has_received_vaccines: bool = False,
) -> data_models.ClientRecord:
    """Generate a realistic ClientRecord for testing downstream steps.

    Real-world significance:
    - Preprocessed client records flow through QR generation, notice compilation, etc.
    - Tests can verify each step correctly processes and transforms these records
    - Enables testing of multilingual support and edge cases

    Parameters
    ----------
    sequence : str, default "00001"
        Sequence number (00001, 00002, ...)
    client_id : str, default "0000000001"
        Unique client identifier (10-digit numeric format)
    language : str, default "en"
        Language for notice ("en" or "fr")
    first_name : str, default "Alice"
        Client first name
    last_name : str, default "Zephyr"
        Client last name
    date_of_birth : str, default "2015-01-02"
        Date of birth (ISO format)
    school_name : str, default "Tunnel Academy"
        School name
    board_name : str, default "Guelph Board"
        School board name
    overdue_diseases : Optional[List[str]], default None
        Canonical diseases requiring immunization.
    has_received_vaccines : bool, default False
        Whether to include mock vaccination history

    Returns
    -------
    ClientRecord
        Realistic client record with all required fields
    """
    person_dict: Dict[str, Any] = {
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth_iso": date_of_birth,
        "age": 9,
        "over_16": False,
    }

    contact_dict: Dict[str, Any] = {
        "street": "123 Main St",
        "city": "Guelph",
        "province": "ON",
        "postal_code": "N1H 2T2",
    }

    school_dict: Dict[str, Any] = {"id": f"sch_{sequence}", "name": school_name}

    board_dict: Dict[str, Any] = {"id": f"brd_{sequence}", "name": board_name}

    received: List[Dict[str, object]] = []
    if has_received_vaccines:
        received = [
            {
                "date_given": "2020-05-01",
                "diseases": ["Diphtheria", "Tetanus", "Pertussis"],
                "vaccine_code": "DTaP",
            },
            {
                "date_given": "2021-06-15",
                "diseases": ["Measles", "Mumps", "Rubella"],
                "vaccine_code": "MMR",
            },
        ]

    if overdue_diseases is None:
        overdue_diseases = ["Measles/Mumps/Rubella"]

    return data_models.ClientRecord(
        sequence=sequence,
        client_id=client_id,
        language=language,
        person=person_dict,
        school=school_dict,
        board=board_dict,
        contact=contact_dict,
        overdue_diseases=[
            {"disease": disease, "dose": None} for disease in overdue_diseases
        ],
        overdue_agents=[],
        received=received,
        metadata={},
        qr=None,
        version_id="overdue_diseases_v1",
    )


def create_test_preprocess_result(
    num_clients: int = 3,
    language: str = "en",
    run_id: str = "test_run_001",
    include_warnings: bool = False,
) -> data_models.PreprocessResult:
    """Generate a realistic PreprocessResult for integration/e2e tests.

    Real-world significance:
    - PreprocessResult is the artifact passed from Step 1 (Preprocess) to Steps 2-3
    - Tests can verify correct flow and schema through pipeline
    - Enables testing of multilingual pipelines

    Parameters
    ----------
    num_clients : int, default 3
        Number of clients in result
    language : str, default "en"
        Language for all clients
    run_id : str, default "test_run_001"
        Run ID for artifact tracking
    include_warnings : bool, default False
        Whether to include warning messages

    Returns
    -------
    PreprocessResult
        Complete preprocessed result with clients and metadata
    """
    clients = [
        create_test_client_record(
            sequence=f"{i + 1:05d}",
            client_id=f"{i + 1:010d}",
            language=language,
            first_name=["Alice", "Benoit", "Chloe"][i % 3],
            last_name=["Zephyr", "Arnaud", "Brown"][i % 3],
        )
        for i in range(num_clients)
    ]

    warnings = []
    if include_warnings:
        warnings = [
            "Missing board name for client 0000000002",
            "Invalid postal code for 0000000003",
        ]

    return data_models.PreprocessResult(clients=clients, warnings=warnings)


def create_test_artifact_payload(
    num_clients: int = 3,
    language: str = "en",
    run_id: str = "test_run_001",
) -> SimpleNamespace:
    """Generate a small test cohort for bundling scenarios.

    Real-world significance:
    - Artifacts are JSON files storing intermediate pipeline state
    - Schema must remain consistent across steps for pipeline to work
    - Tests verify artifact format and content

    Parameters
    ----------
    num_clients : int, default 3
        Number of clients in artifact
    language : str, default "en"
        Language of all clients
    run_id : str, default "test_run_001"
        Unique run identifier

    Returns
    -------
    SimpleNamespace
        Small cohort with clients and run labels for tests.
    """
    result = create_test_preprocess_result(
        num_clients=num_clients, language=language, run_id=run_id
    )

    return SimpleNamespace(
        run_id=run_id,
        language=language,
        clients=result.clients,
        warnings=result.warnings,
        created_at="2025-01-01T12:00:00Z",
        input_file="test_input.csv",
        total_clients=num_clients,
    )
