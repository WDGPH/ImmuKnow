"""Compare every browser editor example download against native Typst."""

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

from playground.scripts.examples import ROOT
from playground.scripts.pdf_compare import compare_pdf


def main():
    bundle = json.loads((ROOT / "playground/public/generated/project.json").read_text())
    downloads = ROOT / "playground/test-results/examples"
    reports = []
    with tempfile.TemporaryDirectory(prefix="immuknow-parity-") as temporary:
        workspace = Path(temporary)
        for name, encoded in bundle["files"].items():
            path = workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(encoded))
        for example in bundle["examples"]:
            for template, payload in example["payloads"].items():
                name = f"{template}-{example['id']}.pdf"
                (workspace / "notice.json").write_text(
                    json.dumps(payload, ensure_ascii=False)
                )
                native = workspace / name
                result = subprocess.run(
                    [
                        os.environ.get("TYPST_BIN", "typst"),
                        "compile",
                        "--root",
                        str(workspace),
                        "--input",
                        "data=/notice.json",
                        str(workspace / "templates" / template),
                        str(native),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert result.returncode == 0, result.stderr
                assert "did not converge" not in result.stderr
                reports.append(
                    {
                        "example": example["id"],
                        "template": template,
                        **compare_pdf(native, downloads / name),
                    }
                )
    assert len(reports) == 37
    (downloads / "parity.json").write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
