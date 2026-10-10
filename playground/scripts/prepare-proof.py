"""Produce real CLI render jobs for the browser/native integration proof.

Run from the repository root with ``uv run python -m
playground.scripts.prepare-proof``. Only synthetic source records are used.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import yaml

from tests.integration.test_native_pipeline import ROOT, prepare_cohort


def main() -> None:
    output = ROOT / "playground" / "public" / "generated"
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    for version, languages in (
        ("overdue_diseases_v1", ("en", "fr")),
        ("overdue_agents_v1", ("en", "fr")),
        ("affirmative_schedule_v1", ("en",)),
    ):
        with tempfile.TemporaryDirectory(prefix="immuknow-proof-") as tmp:
            command, notices, config_dir = prepare_cohort(
                Path(tmp), languages, qr=True, include_dose=True
            )
            config_path = config_dir / "parameters.yaml"
            config = yaml.safe_load(config_path.read_text())
            config.update(date_as_of="2026-01-15", date_of_delivery="2026-02-01")
            config["qr"]["payload_template"] = "https://example.invalid/immuknow-demo"
            config_path.write_text(yaml.safe_dump(config))
            assignments = Path(command[command.index("--notice-assignments") + 1])
            rows = json.loads(assignments.read_text())
            for row, language in zip(rows, languages):
                row["template"] = f"{version}.{language}.typ"
            assignments.write_text(json.dumps(rows))
            if version == "affirmative_schedule_v1":
                source = Path(command[3])
                frame = pd.read_csv(source, dtype=str, keep_default_na=False)
                frame["overdue_disease"] = ""
                frame["overdue_agent"] = ""
                frame.to_csv(source, index=False)
            subprocess.run(
                command,
                cwd=tmp,
                check=True,
                env={
                    **os.environ,
                    "TYPST_FONT_PATHS": "/usr/share/fonts/truetype/freefont",
                    "TYPST_IGNORE_SYSTEM_FONTS": "true",
                },
            )
            jobs = json.loads((notices / "artifacts/render_jobs.json").read_text())
            for job in jobs["jobs"]:
                workspace = Path(job["workspace"])
                key = f"{version}.{job['language']}"
                files = {
                    "/" + path.relative_to(workspace).as_posix(): base64.b64encode(
                        path.read_bytes()
                    ).decode()
                    for path in sorted(workspace.rglob("*"))
                    if path.is_file()
                }
                cases.append(
                    {
                        "name": key,
                        "files": files,
                        "mainFilePath": "/"
                        + Path(job["template"]).relative_to(workspace).as_posix(),
                        "inputs": {
                            "data": "/"
                            + Path(job["data"]).relative_to(workspace).as_posix()
                        },
                    }
                )
                (output / f"{key}.native.pdf").write_bytes(
                    Path(job["pdf"]).read_bytes()
                )
    (output / "proof.json").write_text(json.dumps(cases, ensure_ascii=False))


if __name__ == "__main__":
    main()
