"""Source rows, normalized administrations and explicit assignments remain inspectable."""

import csv
from pathlib import Path

import pandas as pd
import pytest

from immuknow import preprocess
from immuknow.assignment_manifest import ManifestRow
from immuknow.generate_notices import build_notice_data
from immuknow.render_payload import validate_render_payload
from immuknow.version_notices import load_catalog


def source_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            dict(
                client_id="0000000001",
                school_name="Z School",
                first_name=" Alice ",
                last_name="Smith",
                date_of_birth="2010-10-12",
                city="Town",
                province="QC",
                postal_code="A1A 1A1",
                street_address_line_1="1 Main",
                imms_given="May 1, 2020 - MMR - Valid",
                overdue_disease="Poliomyelitis - 2",
                overdue_agent="IPV",
            ),
            dict(
                client_id="0000000002",
                school_name="A School",
                first_name="Bob",
                last_name="Jones",
                date_of_birth="bad date",
                city="",
                province="BC",
                postal_code="",
                street_address_line_1="",
                imms_given="unparsed history; Feb 31, 2020 - MMR",
                overdue_disease="",
                overdue_agent="",
            ),
        ]
    )


def prepare(frame: pd.DataFrame):
    return preprocess.build_preprocess_result(
        frame,
        {"MMR": ["Measles", "Mumps", "Rubella"]},
        preprocess.UNSPECIFIED_AGENTS,
        config={"date_of_delivery": "2026-10-12"},
        config_dir=preprocess.CONFIG_DIR,
        catalog=load_catalog(preprocess.CONFIG_DIR),
        manifest={
            "0000000001": ManifestRow(
                "0000000001", "overdue_diseases_v1", "fr", None, None
            )
        },
    )


@pytest.mark.unit
def test_every_source_row_keeps_its_key_raw_values_and_unknown_state(tmp_path: Path):
    frame = source_rows()
    path = tmp_path / "source.csv"
    frame.to_csv(path, index=False)
    raw = preprocess.read_input(path)
    assert raw.loc[0, "first_name"] == " Alice "
    result, assignment = prepare(raw)
    assert [c.sequence for c in result.clients] == ["row-000001", "row-000002"]
    assert result.source_rows["row-000001"]["first_name"] == " Alice "
    assert result.clients[0].person["first_name"] == "Alice"
    assert result.clients[0].person["age"] == 16
    assert result.clients[0].person["over_16"] is True
    assert result.clients[0].contact["province"] == "QC"
    assert result.clients[0].overdue_diseases == [{"disease": "Polio", "dose": 2}]
    assert result.clients[1].person["age"] is None
    assert result.clients[1].person["over_16"] is None
    assert result.clients[1].person["date_of_birth_iso"] == ""
    assert result.clients[1].version_id is None
    assert result.clients[1].unparsed_history == [
        "unparsed history",
        " Feb 31, 2020 - MMR",
    ]
    assert any(
        c.code == "source.address_incomplete" for c in result.row_checks["row-000002"]
    )
    assert assignment.findings[0].kind == "missing_assignment"
    assert assignment.findings[0].row_key == "row-000002"
    errors = [
        check
        for check in result.row_checks["row-000002"]
        if check.code == "source.history_invalid"
    ]
    assert len(errors) == 2
    assert all(check.status == "fail" for check in errors)


@pytest.mark.parametrize(
    "fragment",
    [
        "May 1, 2020 - MMR - valid",
        "May 1, 2020 - MMR - invalid",
        "May 1, 2020 - MMR - VALID",
        "May 1, 2020 - MMR - INVALID",
        "May 1, 2020 - MMR - VaLiD",
        "May 1, 2020 - MMR - Invalid - Valid",
        "Feb 30, 2020 - MMR - Valid",
        "Feb 29, 2021 - MMR - Valid",
        "May 0, 2020 - MMR",
        "May 1, 2020 - ",
        "May 1, 2020 - MMR - ",
        "May 1, 2020 - MMR -Invalid",
        "May 1, 2020 -  MMR",
        "May 1, 2020 - MMR - Unknown",
        "May 1, 2020 - MMR;",
        ";May 1, 2020 - MMR",
        "May 1, 2020 - MMR;;May 2, 2020 - MMR",
    ],
)
def test_history_refuses_bad_status_dates_separators_and_empty_fragments(fragment):
    assert preprocess.parse_history(fragment).issues


def test_history_valid_tokens_hyphens_and_defined_whitespace_preserve_upstream_facts():
    parsed = preprocess.parse_history(
        "\tFeb 29, 2020 - COVID-19 mRNA - Invalid ;\n May 01, 2020 - HB-unspecified\r\n"
    )
    assert not parsed.issues
    assert parsed.doses == [
        {"date_given": "2020-02-29", "vaccine": "COVID-19 mRNA", "validity": "invalid"},
        {
            "date_given": "2020-05-01",
            "vaccine": "HB-unspecified",
            "validity": "unknown",
        },
    ]


def test_history_checks_excluded_and_duplicate_entries_before_building_rows(
    monkeypatch,
):
    frame = source_rows()
    frame.loc[0, "imms_given"] = (
        "May 1, 2020 - MMR - Valid; May 1, 2020 - MMR - INVALID; Feb 31, 2020 - Not Specified - Valid"
    )
    frame.loc[1, "imms_given"] = "May 1, 2020 - Not Specified"
    parse = preprocess.parse_history
    seen = []

    def counted(raw):
        seen.append(raw)
        return parse(raw)

    monkeypatch.setattr(preprocess, "parse_history", counted)
    result, _ = prepare(frame)
    assert len(seen) == len(frame)
    errors = [
        check
        for check in result.row_checks["row-000001"]
        if check.code == "source.history_invalid"
    ]
    assert [check.measurements["fragment_number"] for check in errors] == [2, 3]
    assert result.clients[0].history[0]["validity"] == "valid"
    assert result.clients[0].validity_coverage == "mixed"
    assert not result.clients[1].history


@pytest.mark.unit
@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ("Valid; Invalid", "valid"),
        ("Invalid; Valid", "valid"),
        ("Invalid; Invalid", "invalid"),
        ("Valid; absent", "unknown"),
        ("absent; Invalid", "unknown"),
    ],
)
def test_same_agent_same_date_validity_precedence(states: str, expected: str):
    raw = "; ".join(
        "May 1, 2020 - MMR" + (" - " + value if value != "absent" else "")
        for value in states.split("; ")
    )
    history = preprocess.build_history_items(
        preprocess.parse_history(raw).doses,
        [],
        {"MMR": ["Measles", "Mumps", "Rubella"]},
    )
    assert history == [
        {
            "date_given": "2020-05-01",
            "agent": "MMR",
            "display_name": "MMR",
            "diseases": ["Measles", "Mumps", "Rubella"],
            "validity": expected,
        }
    ]


@pytest.mark.unit
def test_history_keeps_complete_disease_maps_and_named_display_exclusions():
    history = preprocess.build_history_items(
        preprocess.parse_history(
            "May 1, 2020 - HB-unspecified - Valid; May 1, 2020 - Ig; May 1, 2020 - Not Specified"
        ).doses,
        preprocess.UNSPECIFIED_AGENTS,
        {"HB-unspecified": ["Hepatitis B"]},
    )
    assert [row["agent"] for row in history] == ["HB-unspecified", "Ig"]
    assert history[0]["display_name"] == "HB*"
    assert history[0]["diseases"] == ["Hepatitis B"]


@pytest.mark.unit
def test_validity_coverage_sees_whole_cohort_before_dedup_and_display():
    frame = source_rows()
    frame.loc[1, "imms_given"] = "May 1, 2020 - MMR"
    result, _ = prepare(frame)
    assert all(c.validity_coverage == "mixed" for c in result.clients)
    assert (
        preprocess.classify_dataset_validity([preprocess.parse_history("")])
        == "all_absent"
    )


@pytest.mark.unit
def test_invalid_overdue_doses_remain_source_facts():
    warnings = set()
    result = preprocess.parse_overdue_diseases(
        "Poliomyelitis - 2; Mumps - ; Rubella - no dose",
        {"Poliomyelitis": "Polio"},
        client_id="C001",
        warnings=warnings,
    )
    assert result == [
        {"disease": "Polio", "dose": 2},
        {"disease": "Mumps", "dose": None, "dose_raw": ""},
        {"disease": "Rubella", "dose": None, "dose_raw": "no dose"},
    ]
    assert len(warnings) == 2


@pytest.mark.unit
def test_required_columns_fail_setup_but_blank_cells_do_not():
    frame = source_rows()
    with pytest.raises(ValueError, match="imms_given"):
        preprocess.validate_input(frame.drop(columns="imms_given"))
    frame.loc[0, "first_name"] = ""
    assert len(preprocess.validate_input(frame)) == 2


@pytest.mark.unit
def test_disabled_school_lookup_ignores_source_match_columns_and_absent_history():
    frame = source_rows()
    frame["school_match_type"] = ["exact", "no_match"]
    frame.loc[1, "imms_given"] = ""
    result, _ = prepare(frame)
    assert not any(
        c.code == "data.school_match" for c in result.row_checks["row-000002"]
    )
    assert not any(c.component == "history" for c in result.row_checks["row-000002"])
    assert result.clients[1].school["id"] == ""
    assert result.clients[1].board["id"] == ""


@pytest.mark.unit
def test_one_file_selector_can_render_missing_ids_without_changing_language(
    tmp_path: Path,
):
    frame = source_rows()
    frame["client_id"] = ""
    frame.loc[1, "imms_given"] = ""
    path = tmp_path / "source.csv"
    frame.to_csv(path, index=False)
    result, assignment = preprocess.prepare_clients(
        preprocess.read_input(path),
        tmp_path,
        {"date_of_delivery": "2026-10-12"},
        preprocess.CONFIG_DIR,
        load_catalog(preprocess.CONFIG_DIR),
        {},
        ("overdue_diseases_v1", "fr"),
    )
    assert len(result.clients) == 2
    assert all(
        c.language == "fr" and c.version_id == "overdue_diseases_v1"
        for c in result.clients
    )
    assert not any(f.status == "fail" for f in assignment.findings)
    assert any(
        c.code == "source.client_id_missing" for c in result.row_checks["row-000001"]
    )
    assert result.source_rows["row-000001"]["first_name"] == " Alice "


@pytest.mark.unit
@pytest.mark.parametrize("delimiter", [",", ";"])
def test_extra_csv_fields_fail_without_shifting_identifiers(tmp_path: Path, delimiter):
    source = tmp_path / "extra.csv"
    with source.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(
            [
                "school_name",
                "client_id",
                "first_name",
                "last_name",
                "date_of_birth",
                "city",
                "imms_given",
            ]
        )
        writer.writerow(
            [
                "Example School",
                "0000000001",
                "Alice",
                "Example",
                "2015-01-02",
                "Demo City",
                "May 1, 2020 - MMR",
                "EXTRA",
            ]
        )
    original = source.read_bytes()
    with pytest.raises(ValueError, match="more fields than the header"):
        preprocess.read_input(source)
    assert source.read_bytes() == original


@pytest.mark.parametrize("encoding", ["utf-8-sig", "cp1252"])
@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_csv_preserves_quoted_text_windows_punctuation_and_leading_zeros(
    tmp_path, encoding, delimiter
):
    path = tmp_path / "clients.csv"
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(
            ["client_id", "first_name", "last_name", "street_address_line_1"]
        )
        writer.writerow(
            ["0000000001", " Zoë ", "O’Neil", "12 Main St., Unit 4\nSecond line"]
        )
        writer.writerow(["0000000002", "NA", "NULL", ""])
    frame = preprocess.read_input(path)
    assert frame.attrs == {"encoding": encoding, "delimiter": delimiter}
    assert frame.iloc[0].tolist() == [
        "0000000001",
        " Zoë ",
        "O’Neil",
        "12 Main St., Unit 4\nSecond line",
    ]
    assert frame.iloc[1].tolist() == ["0000000002", "NA", "NULL", ""]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("client_id,client_id\n0000000001,0000000002\n", "Repeated CSV headers"),
        ("client_id, first_name\n0000000001,Alice\n", "surrounding whitespace"),
        ("client_id,\n0000000001,Alice\n", "nonempty names"),
        ("client_id,first_name\n0000000001\n", "fewer fields"),
        ('client_id,first_name\n0000000001,"unfinished\n', "structure is invalid"),
        ("client_id,first_name\n0000000001,A\x00lice\n", "control characters"),
    ],
)
def test_invalid_csv_cannot_silently_change_source_fields(tmp_path, text, message):
    path = tmp_path / "clients.csv"
    path.write_text(text)
    with pytest.raises(ValueError, match=message):
        preprocess.read_input(path)


def test_explicit_encoding_is_respected_and_control_bytes_are_refused(tmp_path):
    path = tmp_path / "clients.csv"
    path.write_bytes("client_id,first_name\n0000000001,Zoë\n".encode("latin-1"))
    frame = preprocess.read_input(path, encoding="latin-1")
    assert frame.attrs["encoding"] == "latin-1"
    assert frame.iloc[0]["first_name"] == "Zoë"
    with pytest.raises(ValueError, match="cannot be read"):
        preprocess.read_input(path, encoding="utf-8-sig")
    path.write_bytes(b"client_id,first_name\n0000000001,A\x81lice\n")
    with pytest.raises(ValueError, match="control characters"):
        preprocess.read_input(path)


@pytest.mark.unit
def test_empty_agent_fragments_keep_source_warning_and_valid_independent_facts(
    tmp_path: Path,
):
    frame = source_rows()
    frame.loc[0, "overdue_agent"] = "\"\"; MMR; ''"
    frame.loc[1, "imms_given"] = ""
    frame.loc[0, "overdue_disease"] = '"  "; Measles - 2'
    source = tmp_path / "clients.csv"
    frame.to_csv(source, index=False)
    result, assignment = preprocess.prepare_clients(
        preprocess.read_input(source),
        tmp_path,
        {},
        preprocess.CONFIG_DIR,
        load_catalog(preprocess.CONFIG_DIR),
        {},
        ("overdue_agents_v1", "en"),
    )
    assert len(result.clients) == 2
    assert result.clients[0].overdue_agents == ["MMR"]
    assert result.clients[0].overdue_diseases == [{"disease": "Measles", "dose": 2}]
    assert result.source_rows["row-000001"]["overdue_disease"] == '"  "; Measles - 2'

    assert result.source_rows["row-000001"]["overdue_agent"] == "\"\"; MMR; ''"
    findings = [
        c
        for c in result.row_checks["row-000001"]
        if c.code == "source.overdue_unusable"
    ]
    assert any('""' in c.message and c.status == "warn" for c in findings)
    assert not any(f.status == "fail" for f in assignment.findings)
    for client in result.clients:
        validate_render_payload(build_notice_data(client, {}))
