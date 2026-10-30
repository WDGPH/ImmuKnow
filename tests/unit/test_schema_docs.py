"""The documentation build produces a readable field reference from the schema."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.unit
def test_generate_csv_field_reference(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2]
    project = tmp_path / "project"
    (project / "docs/user_guide").mkdir(parents=True)
    (project / "immuknow/schemas").mkdir(parents=True)
    script = project / "docs/generate_schema_docs.py"
    shutil.copyfile(source / "docs/generate_schema_docs.py", script)
    schema_path = source / "immuknow/schemas/input_schema.json"
    shutil.copyfile(schema_path, project / "immuknow/schemas/input_schema.json")

    # Exercise the build command without relying on its caller's working directory.
    subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, check=True, capture_output=True
    )
    rendered = (project / "docs/user_guide/input_schema.md").read_text(encoding="utf-8")
    assert rendered.startswith("# CSV input fields\n")
    assert "Schema Information" not in rendered
    assert "s, u, b, s, e, t" not in rendered
    assert "Extra columns are accepted" in rendered
    assert "client_id</code> | Yes | string |" in rendered
    assert "postal_code</code> | No | string |" in rendered
    for field in json.loads(schema_path.read_text(encoding="utf-8"))["fields"]:
        assert f"{field['name']}</code> |" in rendered
