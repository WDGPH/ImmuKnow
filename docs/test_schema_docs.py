"""Check the generated field reference without installing the native test tools."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class SchemaDocsTest(unittest.TestCase):
    def test_generate_csv_field_reference(self) -> None:
        source = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project = workspace / "project"
            (project / "docs/user_guide").mkdir(parents=True)
            (project / "immuknow/schemas").mkdir(parents=True)
            script = project / "docs/generate_schema_docs.py"
            shutil.copyfile(source / "docs/generate_schema_docs.py", script)
            schema_path = source / "immuknow/schemas/input_schema.json"
            shutil.copyfile(schema_path, project / "immuknow/schemas/input_schema.json")

            # The build command must work without relying on its caller's directory.
            subprocess.run(
                [sys.executable, str(script)],
                cwd=workspace,
                check=True,
                capture_output=True,
            )
            rendered = (project / "docs/user_guide/input_schema.md").read_text(
                encoding="utf-8"
            )
            self.assertTrue(rendered.startswith("# CSV input fields\n"))
            self.assertNotIn("Schema Information", rendered)
            self.assertNotIn("s, u, b, s, e, t", rendered)
            self.assertIn("Extra columns are accepted", rendered)
            self.assertIn("client_id</code> | Yes | string |", rendered)
            self.assertIn("postal_code</code> | No | string |", rendered)
            for field in json.loads(schema_path.read_text(encoding="utf-8"))["fields"]:
                self.assertIn(f"{field['name']}</code> |", rendered)
