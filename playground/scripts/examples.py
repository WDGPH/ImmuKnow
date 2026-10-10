"""Prepare deterministic synthetic examples through the real production boundary.

Run ``uv run python -m playground.scripts.examples`` to regenerate; add
``--check`` to verify committed payloads and still assemble browser assets.
No source parsing, age calculation, or eligibility rules are reimplemented here.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import tempfile
from pathlib import Path

import yaml

from immuknow.generate_notices import prepare_render_jobs
from immuknow.generate_qr_codes import generate_qr_codes
from immuknow.load_config import load_config
from immuknow.preprocess import prepare_clients
from immuknow.version_notices import load_catalog

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "playground/examples"
CONFIG = ROOT / "immuknow/config"
TEMPLATES = ROOT / "immuknow/templates"


def write_csv(path: Path, sources: list[dict[str, str]]) -> None:
    """Write unchanged authored source fields, including stable leading-zero IDs."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(sources[0]))
        writer.writeheader()
        writer.writerows(sources)


def example_config() -> dict:
    """Fixed demonstration dates and harmless QR destination; production defaults."""
    config = load_config(CONFIG / "parameters.yaml")
    config.update(date_as_of="2026-01-15", date_of_delivery="2026-02-01")
    config["preprocess"].update(include_dose=True, show_validity_markers=True)
    config["qr"].update(
        enabled=True, payload_template="https://example.invalid/immuknow-demo"
    )
    return config


def generate() -> tuple[dict, dict[str, bytes]]:
    """Return prepared examples and deduplicated project resources from real jobs."""
    scenarios = json.loads((EXAMPLES / "scenarios.json").read_text())
    config = example_config()
    catalog = load_catalog(CONFIG)
    assert catalog is not None
    examples = []
    resources: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="immuknow-examples-") as scratch:
        root = Path(scratch)
        for scenario in scenarios:
            source = scenario["source"]
            path = root / f"{scenario['id']}.csv"
            write_csv(path, [source])
            # These are authored compatibility candidates. Production eligibility
            # below must accept every offered variant; it is never bypassed.
            variants = (
                ["affirmative_schedule_v1.en.typ"]
                if scenario["id"] == "affirmative"
                else [
                    f"{version}.{language}.typ"
                    for version in ("overdue_diseases_v1", "overdue_agents_v1")
                    for language in ("en", "fr")
                ]
            )
            payloads = {}
            for filename in variants:
                version, language, _ = filename.split(".")
                output = root / scenario["id"] / filename
                output.mkdir(parents=True)
                prepared, _ = prepare_clients(
                    path, output, config, CONFIG, catalog, {}, (version, language)
                )
                assert len(prepared.clients) == 1, (
                    f"Synthetic client unexpectedly excluded: {scenario['id']}"
                )
                artifacts = output / "artifacts"
                clients, _ = generate_qr_codes(prepared.clients, artifacts, config)
                (job,) = prepare_render_jobs(
                    clients, artifacts, TEMPLATES, config, CONFIG, "synthetic-examples"
                )
                payloads[filename] = json.loads(job.data.read_text())
                for resource in sorted(job.workspace.rglob("*")):
                    if not resource.is_file() or resource.is_relative_to(
                        job.workspace / "data"
                    ):
                        continue
                    key = resource.relative_to(job.workspace).as_posix()
                    value = resource.read_bytes()
                    assert key not in resources or resources[key] == value, (
                        f"Conflicting resource: {key}"
                    )
                    resources[key] = value
            examples.append(
                {key: scenario[key] for key in ("id", "label", "description")}
                | {"payloads": payloads}
            )
    # Complete project exports include the selected production configuration.
    for path in sorted(CONFIG.glob("*")):
        if path.is_file() and path.suffix in (".json", ".yaml"):
            resources["config/" + path.name] = path.read_bytes()
    resources["config/parameters.yaml"] = yaml.safe_dump(
        config, sort_keys=True, allow_unicode=True
    ).encode()
    # Runtime /translations and production config overrides share identical bytes.
    for key, value in list(resources.items()):
        if key.startswith("translations/"):
            resources["config/" + key] = value
    with tempfile.TemporaryDirectory(prefix="immuknow-example-sources-") as scratch:
        for name, subset in {
            "known-overdue": [
                item
                for item in scenarios
                if item["id"] not in ("unknown-validity", "affirmative")
            ],
            "unknown-overdue": [
                item for item in scenarios if item["id"] == "unknown-validity"
            ],
            "affirmative": [item for item in scenarios if item["id"] == "affirmative"],
        }.items():
            source_file = Path(scratch) / (name + ".csv")
            write_csv(source_file, [item["source"] for item in subset])
            resources["examples/" + source_file.name] = source_file.read_bytes()
        known = [
            item
            for item in scenarios
            if item["id"] not in ("unknown-validity", "affirmative")
        ]
        assignments = [
            {
                "client_id": item["source"]["client_id"],
                "template": (
                    "overdue_diseases_v1.en.typ"
                    if index % 2 == 0
                    else "overdue_agents_v1.fr.typ"
                ),
            }
            for index, item in enumerate(known)
        ]
        resources["examples/assignments.json"] = (
            json.dumps(assignments, indent=2) + "\n"
        ).encode()
    resources["examples/README.md"] = (EXAMPLES / "README.md").read_bytes()
    resources["README.md"] = (EXAMPLES / "PROJECT.md").read_bytes()
    prepared = {"schemaVersion": 1, "synthetic": True, "examples": examples}
    return prepared, resources


def assemble(prepared: dict, resources: dict[str, bytes], destination: Path) -> None:
    """Write a static browser bundle; source files remain exact canonical bytes."""
    destination.mkdir(parents=True, exist_ok=True)
    bundle = {
        **prepared,
        "files": {
            key: base64.b64encode(value).decode()
            for key, value in sorted(resources.items())
        },
        "hashes": {
            key: hashlib.sha256(value).hexdigest()
            for key, value in sorted(resources.items())
        },
        "compilerVersion": "0.15.1",
        "packageVersion": "0.1.0",
    }
    (destination / "project.json").write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed synthetic payloads are stale",
    )
    args = parser.parse_args()
    prepared, resources = generate()
    text = json.dumps(prepared, ensure_ascii=False, indent=2) + "\n"
    target = EXAMPLES / "prepared.json"
    if args.check:
        if not target.is_file() or target.read_text() != text:
            raise SystemExit(
                "Synthetic fixtures are stale. Run uv run python -m playground.scripts.examples"
            )
    else:
        target.write_text(text)
    assemble(prepared, resources, ROOT / "playground/public/generated")
    print(
        f"Prepared {len(prepared['examples'])} synthetic scenarios and {sum(len(item['payloads']) for item in prepared['examples'])} eligible template variants"
    )


if __name__ == "__main__":
    main()
