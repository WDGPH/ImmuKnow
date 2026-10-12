"""Prepare a small deterministic Studio cohort through the native facts contract.

Run ``uv run python -m studio.scripts.examples`` to regenerate. ``--check``
verifies committed facts and still assembles the browser project, fonts and
current build metadata. Clinical facts never change to fit a selected notice.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from immuknow.assignment_manifest import load_manifest
from immuknow.data_models import CheckResult
from immuknow.generate_notices import build_notice_data, prepare_render_jobs
from immuknow.load_config import load_config
from immuknow.preprocess import prepare_clients, read_input
from immuknow.version_notices import load_catalog, template_identity
from .build_info import project_build

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "studio/examples"
PACKAGE = Path(str(files("immuknow")))
CONFIG = PACKAGE / "config"
TEMPLATES = PACKAGE / "templates"


def write_csv(path: Path, source: dict[str, str]) -> None:
    """Save authored source values, preserving leading-zero identifiers and punctuation."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(source))
        writer.writeheader()
        writer.writerow(source)


def localized_source(scenario: dict[str, Any], language: str) -> dict[str, str]:
    """Use explicitly authored names/addresses while retaining the same clinical facts."""
    source = scenario["source"]
    overrides = scenario.get("source_by_language", {}).get(language, {})
    for key in (
        "client_id",
        "date_of_birth",
        "overdue_disease",
        "overdue_agent",
        "imms_given",
    ):
        if key in overrides and overrides[key] != source[key]:
            raise ValueError(
                f"Example localization must not change {key}: {scenario['id']}"
            )
    return source | overrides


def generate() -> tuple[dict[str, Any], dict[str, bytes]]:
    """Prepare every explicit variant and return unchanged project/export resources."""
    authored = json.loads((EXAMPLES / "scenarios.json").read_text(encoding="utf-8"))
    config = load_config(CONFIG / "parameters.yaml")
    config.update(authored["dates"])
    catalog = load_catalog(CONFIG)
    examples = []
    resources = {
        "templates/" + path.relative_to(TEMPLATES).as_posix(): path.read_bytes()
        for path in sorted(TEMPLATES.rglob("*"))
        if path.is_file()
    }
    resources.update(
        {
            "config/" + path.relative_to(CONFIG).as_posix(): path.read_bytes()
            for path in sorted(CONFIG.rglob("*"))
            if path.is_file()
        }
    )
    resources["config/parameters.yaml"] = yaml.safe_dump(
        config, sort_keys=True, allow_unicode=True
    ).encode("utf-8")
    config["creation_timestamp"] = authored["creationTimestamp"]
    with tempfile.TemporaryDirectory(prefix="immuknow-studio-examples-") as scratch:
        workspace = Path(scratch)
        shutil.copytree(TEMPLATES, workspace / "resources/templates")
        for scenario in authored["scenarios"]:
            payloads, preparation_checks, inputs = {}, {}, {}
            for filename in scenario["variants"]:
                version, language = template_identity(TEMPLATES / filename)
                source = localized_source(scenario, language)
                csv_path = workspace / "client.csv"
                write_csv(csv_path, source)
                csv_key = f"examples/clients/{scenario['id']}.{language}.csv"
                resources[csv_key] = csv_path.read_bytes()
                assignments = [{"client_id": source["client_id"], "template": filename}]
                assignment_path = workspace / "assignment.json"
                assignment_path.write_text(
                    json.dumps(assignments, indent=2) + "\n", encoding="utf-8"
                )
                assignment_key = (
                    f"examples/assignments/{scenario['id']}.{version}.{language}.json"
                )
                resources[assignment_key] = assignment_path.read_bytes()
                manifest = load_manifest(assignment_path, TEMPLATES)
                prepared, reconciliation = prepare_clients(
                    read_input(csv_path),
                    workspace / "work",
                    config,
                    CONFIG,
                    catalog,
                    manifest,
                    None,
                )
                if (
                    len(prepared.clients) != 1
                    or any(f.status == "fail" for f in reconciliation.findings)
                    or any(
                        check.status == "fail"
                        for checks in prepared.row_checks.values()
                        for check in checks
                    )
                ):
                    raise ValueError(
                        f"Example variant is unrenderable: {scenario['id']} / {filename}"
                    )
                client = prepared.clients[0]
                (job,) = prepare_render_jobs([client], workspace, config)
                payload = json.loads(job.data.read_text(encoding="utf-8"))
                if payload != build_notice_data(client, config):
                    raise ValueError(
                        f"Staged facts disagree with native producer: {filename}"
                    )
                payloads[filename] = payload
                preparation_checks[filename] = (
                    [check.to_dict() for check in prepared.row_checks[client.sequence]]
                    + [
                        CheckResult(
                            "data.preparation_warning", "preparation", "warn", message
                        ).to_dict()
                        for message in prepared.warnings
                    ]
                    + [
                        CheckResult(
                            f"assignment.{finding.kind}",
                            "assignment",
                            finding.status,
                            finding.reason,
                        ).to_dict()
                        for finding in reconciliation.findings
                    ]
                )
                inputs[filename] = {"csv": csv_key, "assignments": assignment_key}
            examples.append(
                {key: scenario[key] for key in ("id", "label", "description")}
                | {
                    "payloads": payloads,
                    "preparationChecks": preparation_checks,
                    "inputs": inputs,
                }
            )
    resources["examples/README.md"] = (EXAMPLES / "README.md").read_bytes()
    resources["README.md"] = (EXAMPLES / "PROJECT.md").read_bytes()
    resources["build.json"] = (json.dumps(project_build(), indent=2) + "\n").encode()
    prepared = {
        "schemaVersion": 1,
        "synthetic": True,
        "creationTimestamp": authored["creationTimestamp"],
        "examples": examples,
    }
    return prepared, resources


def assemble(
    prepared: dict[str, Any], resources: dict[str, bytes], destination: Path
) -> None:
    """Write verified project bytes and central provenance without embedding font binaries."""
    destination.mkdir(parents=True, exist_ok=True)
    bundle = {
        **prepared,
        "build": json.loads(resources["build.json"]),
        "files": {
            key: base64.b64encode(value).decode("ascii")
            for key, value in sorted(resources.items())
        },
        "hashes": {
            key: hashlib.sha256(value).hexdigest()
            for key, value in sorted(resources.items())
        },
    }
    (destination / "project.json").write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (destination / "build.json").write_bytes(resources["build.json"])
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "studio/scripts/prepare-fonts.py"),
            "--destination",
            str(destination / "fonts"),
        ],
        check=True,
        cwd=ROOT,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Reject stale committed facts and still assemble assets",
    )
    parser.add_argument(
        "--destination", type=Path, default=ROOT / "studio/public/generated"
    )
    args = parser.parse_args()
    prepared, resources = generate()
    rendered = json.dumps(prepared, ensure_ascii=False, indent=2) + "\n"
    target = EXAMPLES / "prepared.json"
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
            raise SystemExit(
                "Example files are stale. Run uv run python -m studio.scripts.examples"
            )
    else:
        target.write_text(rendered, encoding="utf-8")
    assemble(prepared, resources, args.destination)
    count = sum(len(example["payloads"]) for example in prepared["examples"])
    print(
        f"Prepared {len(prepared['examples'])} example scenarios and {count} notice variants"
    )


if __name__ == "__main__":
    main()
