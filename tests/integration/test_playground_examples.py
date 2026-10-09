"""Browser examples use real prepared facts and compile unchanged native sources."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

from playground.scripts.examples import EXAMPLES, generate
from immuknow.validate_pdfs import validate_pdf_structure

SCENARIOS = json.loads((EXAMPLES / "scenarios.json").read_text())
PREPARED = json.loads((EXAMPLES / "prepared.json").read_text())
VARIANTS = [
    (example["id"], template)
    for example in PREPARED["examples"]
    for template in example["payloads"]
]
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def example_project(tmp_path_factory):
    prepared, resources = generate()
    assert prepared == PREPARED, (
        "Regenerate playground examples through the production preparation path"
    )
    workspace = tmp_path_factory.mktemp("synthetic-project")
    for name, contents in resources.items():
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
    return workspace, prepared


def test_synthetic_scenarios_preserve_required_facts(example_project):
    _, prepared = example_project
    assert len(prepared["examples"]) >= 10
    examples = {
        example["id"]: next(iter(example["payloads"].values()))
        for example in prepared["examples"]
    }
    assert len(examples["long-history"]["history"]) == 70
    assert examples["older-client"]["client_data"]["over_16"] is True
    assert examples["unknown-validity"]["validity_coverage"] == "all_absent"
    assert {item["validity"] for item in examples["unknown-validity"]["history"]} == {
        "unknown"
    }
    same = examples["same-date"]["history"]
    assert len(same) == 3  # Duplicate MMR administration normalized by production.
    assert len({item["date_given"] for item in same}) == 1
    assert [(item["agent"], item["validity"]) for item in same] == [
        ("MMR", "valid"),
        ("MMR-Var", "invalid"),
        ("IPV", "valid"),
    ]
    excluded = examples["excluded-agents"]
    assert {item["agent"] for item in excluded["history"]} == {"MMR", "Ig", "VarIg"}
    assert {"Ig", "VarIg"} <= set(excluded["rendering_defaults"]["ignore_agents"])
    other = examples["other-column"]["history"]
    assert "Hepatitis B" in other[0]["diseases"]
    assert "Diphtheria" in other[0]["diseases"]
    assert other[1]["diseases"] == ["HPV"]
    assert examples["affirmative"]["overdue_diseases"] == []
    assert examples["affirmative"]["overdue_agents"] == []
    for example in prepared["examples"]:
        for template, payload in example["payloads"].items():
            assert (
                payload["client_data"]["qr_url"]
                == "https://example.invalid/immuknow-demo"
            )
            assert f"{payload['version_id']}.{payload['language']}.typ" == template
            assert payload["validity_coverage"] != "mixed"
            if example["id"] != "affirmative":
                assert payload["overdue_diseases"] and payload["overdue_agents"]


@pytest.mark.parametrize(("scenario", "template"), VARIANTS)
def test_each_offered_example_compiles_with_maintained_source(
    example_project, scenario, template
):
    workspace, prepared = example_project
    item = next(
        example for example in prepared["examples"] if example["id"] == scenario
    )
    payload = item["payloads"][template]
    data = workspace / "notice.json"
    data.write_text(json.dumps(payload, ensure_ascii=False))
    entry = workspace / "templates" / template
    before = entry.read_bytes()
    pdf = workspace / "notice.pdf"
    result = subprocess.run(
        [
            os.environ.get("TYPST_BIN", "typst"),
            "compile",
            "--root",
            str(workspace),
            "--input",
            "data=/notice.json",
            str(entry),
            str(pdf),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "did not converge" not in result.stderr
    assert entry.read_bytes() == before
    reader = PdfReader(pdf)
    text = " ".join("\n".join(page.extract_text() for page in reader.pages).split())
    assert payload["client_id"] in text
    assert "".join(payload["client_data"]["name"].split()) in "".join(text.split())
    assert reader.root_object["/Lang"] == payload["language"] + "-CA"
    if scenario == "long-history":
        assert len(reader.pages) >= 4
        assert text.count("MMR") >= 23
    if scenario == "unknown-validity":
        assert "#text(fill:red)[literal]" in "".join(text.split())
        assert "?" in text
        assert (
            "Validity unknown" if payload["language"] == "en" else "Validité inconnue"
        ) in text
    if scenario == "older-client":
        assert ("To:" if payload["language"] == "en" else "Au:") in text
        assert "Parent/Guardian" not in text and "parent ou tuteur" not in text
    checked = validate_pdf_structure(
        pdf,
        enabled_rules={
            "client_id_presence": "error",
            "envelope_window": "error",
            "exactly_two_pages": "disabled",
            "signature_overflow": "disabled",
        },
        client_id_map={pdf.name: payload["client_id"]},
    )
    assert checked.passed, checked.warnings


@pytest.mark.parametrize("selector", ["single", "manifest"])
def test_assembled_examples_run_through_real_cli(example_project, tmp_path, selector):
    """The resource bundle supplies both production selectors without source edits."""
    workspace, prepared = example_project
    output = tmp_path / "delivery"
    command = [
        sys.executable,
        "-m",
        "immuknow.orchestrator",
        str(workspace / "examples/known-overdue.csv"),
        "--config",
        str(workspace / "config"),
        "--output",
        str(output),
    ]
    if selector == "single":
        command += [
            "--template",
            str(workspace / "templates/overdue_diseases_v1.en.typ"),
        ]
    else:
        command += [
            "--notice-assignments",
            str(workspace / "examples/assignments.json"),
            "--templates",
            str(workspace / "templates"),
        ]
    originals = {
        path: path.read_bytes()
        for path in (workspace / "templates").rglob("*")
        if path.is_file()
    }
    result = subprocess.run(
        command, cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "did not converge" not in result.stderr
    assert all(path.read_bytes() == contents for path, contents in originals.items())
    (completion,) = (output / "metadata").glob("completion_*.json")
    assert completion.is_file()
    jobs = json.loads((output / "artifacts/render_jobs.json").read_text())["jobs"]
    assert len(jobs) == 8
    by_id = {
        next(iter(example["payloads"].values()))["client_id"]: example
        for example in prepared["examples"]
    }
    for job in jobs:
        actual = json.loads(Path(job["data"]).read_text())
        expected = copy.deepcopy(
            by_id[job["client_id"]]["payloads"][Path(job["template"]).name]
        )
        actual_qr = actual["client_data"].pop("qr_img")
        expected_qr = expected["client_data"].pop("qr_img")
        assert actual == expected
        assert (Path(job["workspace"]) / actual_qr.lstrip("/")).read_bytes() == (
            workspace / expected_qr.lstrip("/")
        ).read_bytes()
