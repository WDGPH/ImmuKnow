"""Focused native-worker parity checks suggested by the critical review."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from immuknow import compile_notices
from immuknow.data_models import RenderJob
from transport import NativeSession
from pypdf import PdfReader
import pymupdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    ROOT = args.out.resolve()
    worker = args.worker.resolve()
    ROOT.mkdir(exist_ok=False)
    os.environ.update(
        TYPST_FONT_PATHS="/usr/share/fonts/truetype/freefont",
        TYPST_IGNORE_SYSTEM_FONTS="true",
    )
    template = ROOT / "probe.typ"
    wrapper = ROOT / "entry.typ"
    wrapper.write_text(
        '#include sys.inputs.at("immuknow-template-path")\n#context pdf.attach("/immuknow-evidence.json", bytes(json.encode(query(<immuknow-report>).map(it => it.value))), mime-type: "application/json")'
    )
    stamp = 1793842452
    host = NativeSession(ROOT, worker, direct_report=True)
    rows = []

    def compare(key, text, inputs=None, notice=None, timestamp=stamp):
        template.write_text(text)
        inputs = {
            "immuknow-template-path": "/probe.typ",
            "data": "/facts.json",
            **(inputs or {}),
        }
        notice = notice or {"case": key}
        (ROOT / "facts.json").write_text(json.dumps(notice))
        cold, warm = ROOT / f"{key}-cli.pdf", ROOT / f"{key}-native.pdf"
        command = [
            "typst",
            "compile",
            "--root",
            str(ROOT),
            "--jobs",
            "1",
            "--creation-timestamp",
            str(timestamp),
        ]
        for k, v in inputs.items():
            command += ["--input", f"{k}={v}"]
        compile_notices.run_typst(
            [*command, str(wrapper), str(cold)], timeout=30, operation="boundary parity"
        )
        result = host.request(
            {
                "id": key,
                "notice": notice,
                "inputs": inputs,
                "output": str(warm),
                "timestamp": timestamp,
                "direct_report": True,
            }
        )
        assert result["ok"], result
        a, b = PdfReader(cold), PdfReader(warm)
        assert result["reports"] == json.loads(
            a.attachments["immuknow-evidence.json"][0]
        ), key
        assert dict(a.metadata or {}) == dict(b.metadata or {}), key

        def links(reader):
            return [
                [
                    (
                        str(x.get_object().get("/Rect")),
                        str(x.get_object().get("/A")),
                        str(x.get_object().get("/Dest")),
                    )
                    for x in page.get("/Annots", [])
                ]
                for page in reader.pages
            ]

        assert links(a) == links(b), key
        assert {
            k: list(v)
            for k, v in a.attachments.items()
            if k != "immuknow-evidence.json"
        } == {k: list(v) for k, v in b.attachments.items()}, key
        with pymupdf.open(cold) as x, pymupdf.open(warm) as y:
            assert len(x) == len(y)
            assert x.get_toc() == y.get_toc(), key
            assert all(
                pa.get_pixmap(dpi=120).samples == pb.get_pixmap(dpi=120).samples
                for pa, pb in zip(x, y)
            ), key
        rows.append(key)

    try:
        compare(
            "default-fonts",
            '= Default text\nCode: `sample`\nMath: $sum_(i=1)^5 i$\n#link("https://example.org/check")[Clickable]\n#pdf.attach("/user.txt", bytes("retained user attachment"), mime-type: "text/plain")',
        )
        state_source = """#import "/helper.typ": answer
#set text(font: "FreeSans")
#image("/picture.svg", width: 15mm)
#context [#metadata((answer: answer, today: datetime.today().display(), optional: sys.inputs.at("optional", default: "absent"), notice: json(sys.inputs.at("data")))) <immuknow-report>]
"""

        def assets(answer, color):
            (ROOT / "helper.typ").write_text(f'#let answer = "{answer}"')
            (ROOT / "picture.svg").write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20" fill="{color}"/></svg>'
            )

        assets("one", "red")
        compare("state-a", state_source, {"optional": "present"}, {"case": "A"})
        assets("two", "blue")
        compare("state-b", state_source, notice={"case": "B"}, timestamp=stamp + 86400)
        assets("one", "red")
        compare(
            "state-a-restored", state_source, {"optional": "present"}, {"case": "A"}
        )
        for filename in ["helper.typ", "picture.svg"]:
            saved = (ROOT / filename).read_bytes()
            (ROOT / filename).unlink()
            result = host.request(
                {
                    "id": "deleted-" + filename,
                    "notice": {},
                    "inputs": {
                        "immuknow-template-path": "/probe.typ",
                        "data": "/facts.json",
                    },
                    "output": str(ROOT / "deleted.pdf"),
                    "timestamp": stamp,
                    "direct_report": True,
                }
            )
            assert not result["ok"], result
            (ROOT / filename).write_bytes(saved)
            compare("restored-" + filename, state_source)

        # A reserved template attachment is already rejected by the CLI wrapper
        # (duplicate attachment path). Direct mode must also refuse publication.
        text = '#pdf.attach("/immuknow-evidence.json", bytes("private facts"), mime-type: "application/json")'
        template.write_text(text)
        reserved = host.request(
            {
                "id": "reserved",
                "notice": {},
                "inputs": {"immuknow-template-path": "/probe.typ"},
                "output": str(ROOT / "reserved.pdf"),
                "timestamp": stamp,
                "direct_report": True,
            }
        )
        assert not reserved["ok"] and "reserved" in reserved["error"]
        assert not (ROOT / "reserved.pdf").exists()
        try:
            compile_notices.run_typst(
                [
                    "typst",
                    "compile",
                    "--root",
                    str(ROOT),
                    "--input",
                    "immuknow-template-path=/probe.typ",
                    str(wrapper),
                    str(ROOT / "reserved-cli.pdf"),
                ],
                timeout=30,
                operation="reserved attachment parity",
            )
            raise AssertionError(
                "Stock CLI unexpectedly accepted the reserved attachment"
            )
        except subprocess.CalledProcessError:
            assert not (ROOT / "reserved-cli.pdf").exists()

        # Missing/malformed reports retain the PDF through the actual Core caller.

        def native_run(
            command: list[str], *, timeout: float, operation: str
        ) -> subprocess.CompletedProcess[str]:
            return host.compile_command(command, timeout)

        def direct_report(content: bytes) -> tuple[bytes, list[bytes], bool]:
            return content, [json.dumps(host.last_reports).encode()], False

        notice = {
            "row_key": "row-edge",
            "client_id": "edge",
            "language": "en",
            "version_id": "edge",
            "template": "probe.typ",
        }
        (ROOT / "facts.json").write_text(json.dumps(notice))
        with (
            patch.object(compile_notices, "run_typst", native_run),
            patch.object(compile_notices, "_strip_evidence", direct_report),
        ):
            for key, text in [
                ("missing", "Readable without a report."),
                (
                    "malformed",
                    "Readable invalid report. #metadata((unexpected: true)) <immuknow-report>",
                ),
            ]:
                template.write_text(text)
                job = RenderJob(
                    "row-edge",
                    "edge",
                    "en",
                    "edge",
                    ROOT,
                    template,
                    ROOT / "facts.json",
                    ROOT / f"{key}.pdf",
                    stamp,
                )
                _, summary, error = compile_notices.compile_render_job(
                    job, "typst", timeout=30, jobs=1
                )
                assert summary is None and error is not None
                assert len(PdfReader(job.pdf).pages) == 1
                assert "immuknow-evidence.json" not in PdfReader(job.pdf).attachments
                rows.append(key + "-retains-readable-pdf")
    finally:
        host.close()

    # The deadline also covers a child stopped before reading a large request.
    blocked = NativeSession(ROOT, worker, direct_report=True)
    try:
        os.kill(blocked.process.pid, signal.SIGSTOP)
        start = time.monotonic()
        try:
            blocked.request(
                {
                    "id": "blocked-write",
                    "notice": {"large": "x" * 1_000_000},
                    "inputs": {},
                    "output": str(ROOT / "never.pdf"),
                    "timestamp": stamp,
                },
                timeout=0.1,
            )
            raise AssertionError("Blocked transmission did not time out")
        except TimeoutError:
            elapsed = time.monotonic() - start
            assert blocked.process.poll() is not None and elapsed < 6
            rows.append("blocked-transmission-deadline")
    finally:
        blocked.close()
    (ROOT / "analysis.json").write_text(
        json.dumps(
            {
                "passed": rows,
                "reserved_attachment_rejected": True,
                "all_checks_passed": True,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"passed": rows, "all_checks_passed": True}))


if __name__ == "__main__":
    main()
