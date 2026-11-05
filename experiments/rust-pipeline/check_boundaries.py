"""Exercise actual Rust CLI failures and PDF behavior with fictional fixtures."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
from pathlib import Path

import pikepdf
import pymupdf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--encryption-workers", type=int, default=0)
    parser.add_argument("--bundle-workers", type=int, default=1)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.pop("RAYON_NUM_THREADS", None)
    checked = []

    def cohort(name, modify):
        directory = args.output / name
        directory.mkdir()
        shutil.copytree(args.project / "templates", directory / "templates")
        shutil.copytree(args.project / "config", directory / "config")
        shutil.copy(args.fixture / "students.csv", directory / "students.csv")
        shutil.copy(args.fixture / "assignments.json", directory / "assignments.json")
        modify(directory)
        result = subprocess.run(
            [
                str(args.binary),
                "run",
                "--csv",
                str(directory / "students.csv"),
                "--assignments",
                str(directory / "assignments.json"),
                "--config",
                str(directory / "config"),
                "--templates",
                str(directory / "templates"),
                "--core",
                str(args.core),
                "--output",
                str(directory / "runs"),
                "--encryption-workers",
                str(args.encryption_workers),
                "--bundle-workers",
                str(args.bundle_workers),
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        records = list((directory / "runs").glob("*/run.json"))
        assert len(records) == 1, (name, result.stderr)
        record = json.loads(records[0].read_text())
        checked.append(name)
        return result, record, records[0].parent

    def append_template(directory, text):
        template = directory / "templates/overdue_diseases_v1.en.typ"
        template.write_text(template.read_text() + "\n" + text)

    result, record, run = cohort(
        "compile-failure", lambda d: append_template(d, '#panic("expected failure")')
    )
    assert result.returncode == 1
    first, *later = record["entries"]
    assert first["original"]["status"] == "failed"
    assert all(e["original"]["status"] == "completed" for e in later)
    assert not run.name.endswith(".incomplete")

    result, record, run = cohort(
        "bad-report", lambda d: append_template(d, "#metadata(123) <immuknow-report>")
    )
    assert result.returncode == 1
    first, *later = record["entries"]
    assert first["original"]["status"] == "completed"
    assert any(c["code"] == "render.evidence_failed" for c in first["checks"])
    assert all("render_report" in e for e in later)
    with pikepdf.open(run / first["original"]["path"]) as pdf:
        assert len(pdf.pages) and not pdf.attachments

    result, record, run = cohort(
        "computed-package",
        lambda d: append_template(
            d, '#let ns = "@preview/"\n#import (ns + "missing:0.1.0"): *'
        ),
    )
    assert result.returncode == 1
    assert (
        "Package imports are not supported" in record["entries"][0]["original"]["error"]
    )
    assert all(e["original"]["status"] == "completed" for e in record["entries"][1:])

    def change_rows(directory, function):
        path = directory / "students.csv"
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            rows, fields = list(reader), reader.fieldnames
        function(rows)
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    for name, mutate in (
        ("duplicate-id", lambda rows: rows[1].update(client_id=rows[0]["client_id"])),
        (
            "bad-history",
            lambda rows: rows[0].update(imms_given="2020-01-01 - MMR - valid;"),
        ),
        ("missing-forecast", lambda rows: rows[0].update(overdue_agent="")),
    ):
        result, record, run = cohort(name, lambda d, f=mutate: change_rows(d, f))
        assert result.returncode and run.name.endswith(".incomplete")
        assert not record["entries"] and not list((run / "originals").glob("*.pdf"))

    result, record, run = cohort(
        "missing-password-fact",
        lambda d: change_rows(d, lambda rows: rows[0].update(date_of_birth="")),
    )
    assert result.returncode == 1
    assert record["entries"][0]["original"]["status"] == "completed"
    assert record["entries"][0]["encryption"]["status"] == "failed"
    assert not (run / "encrypted/row-000001.pdf").exists()
    assert all(e["encryption"]["status"] == "completed" for e in record["entries"][1:])

    def repeated(directory):
        p = directory / "assignments.json"
        p.write_text(
            p.read_text().replace(
                '"client_id":', '"client_id":"duplicate", "client_id":', 1
            )
        )

    result, record, run = cohort("repeated-json-field", repeated)
    assert result.returncode and "Repeated JSON field" in record["error"]

    # Independent encryption and cross-document link/geometry checks.
    source = args.output / "links.pdf"
    doc = pymupdf.open()
    for text in ("Page one", "Page two"):
        page = doc.new_page(width=180, height=240)
        page.insert_text((20, 40), text)
    doc[0].insert_link(
        {"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(20, 50, 100, 65), "page": 1}
    )
    doc[1].insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": pymupdf.Rect(20, 50, 100, 65),
            "uri": "https://example.org/",
        }
    )
    doc.save(source)
    doc.close()
    encrypted, merged = args.output / "unicode.pdf", args.output / "merged.pdf"
    password = "héllo-世界"
    subprocess.run(
        [
            str(args.binary),
            "encrypt",
            "--input",
            str(source),
            "--output",
            str(encrypted),
            "--password-env",
            "IMMUKNOW_TEST_PASSWORD",
        ],
        env={**environment, "IMMUKNOW_TEST_PASSWORD": password},
        check=True,
        timeout=30,
    )
    with pikepdf.open(encrypted, password=password) as pdf:
        assert pdf.trailer.Encrypt.R == 6 and len(pdf.pages) == 2
    with pymupdf.open(source) as original, pymupdf.open(encrypted) as protected:
        assert protected.authenticate(password)
        for a, b in zip(original, protected):
            assert a.get_pixmap().samples == b.get_pixmap().samples
    try:
        pikepdf.open(encrypted, password="wrong")
    except pikepdf.PasswordError:
        pass
    else:
        raise AssertionError("Wrong password accepted")
    subprocess.run(
        [str(args.binary), "merge", "--output", str(merged), str(source), str(source)],
        env=environment,
        check=True,
        timeout=30,
    )
    with pymupdf.open(merged) as pdf:
        assert len(pdf) == 4
        assert pdf[0].get_links()[0]["page"] == 1
        assert pdf[2].get_links()[0]["page"] == 3
        assert (
            pdf[1].get_links()[0]["uri"]
            == pdf[3].get_links()[0]["uri"]
            == "https://example.org/"
        )
    checked += ["unicode-encryption-independent-reader", "cross-page-links-after-merge"]
    inherited = args.output / "inherited.pdf"
    with pikepdf.open(source) as pdf:
        parent = pdf.pages[0].obj.Parent
        parent.MediaBox = pdf.pages[0].obj.MediaBox
        parent.Resources = pdf.pages[0].obj.Resources
        parent.Rotate = 90
        for page in pdf.pages:
            del page.obj.MediaBox
            del page.obj.Resources
            if "/Rotate" in page.obj:
                del page.obj.Rotate
        pdf.save(inherited)
    preserved = args.output / "inherited-merged.pdf"
    subprocess.run(
        [
            str(args.binary),
            "merge",
            "--output",
            str(preserved),
            str(inherited),
            str(inherited),
        ],
        env=environment,
        check=True,
        timeout=30,
    )
    with pymupdf.open(inherited) as original, pymupdf.open(preserved) as bundle:
        for i, page in enumerate(bundle):
            want = original[i % 2]
            assert page.rect == want.rect and page.rotation == want.rotation
            assert page.get_pixmap().samples == want.get_pixmap().samples
    checked.append("inherited-resources-boxes-rotation")
    attachments = args.output / "attachment.pdf"
    with pikepdf.open(source) as pdf:
        pdf.attachments["example.txt"] = b"example attachment"
        pdf.save(attachments)
    copied_attachment_pages = args.output / "attachment-pages.pdf"
    subprocess.run(
        [
            str(args.binary),
            "merge",
            "--output",
            str(copied_attachment_pages),
            str(attachments),
        ],
        env=environment,
        check=True,
        timeout=30,
    )
    with pikepdf.open(copied_attachment_pages) as pdf:
        assert len(pdf.pages) == 2 and not pdf.attachments
    checked.append("catalog-attachments-omitted-like-baseline")
    for version in ("1.7", "2.0"):
        named = args.output / ("named-" + version + ".pdf")
        with pikepdf.open(source) as pdf:
            destination = pikepdf.Array(
                [pdf.pages[1].obj, pikepdf.Name("/XYZ"), 20, 30, 1.5]
            )
            pdf.Root.Names = pikepdf.Dictionary(
                Dests=pikepdf.Dictionary(Names=pikepdf.Array(["target", destination]))
            )
            link = pdf.make_indirect(
                pikepdf.Dictionary(
                    Type=pikepdf.Name("/Annot"),
                    Subtype=pikepdf.Name("/Link"),
                    Rect=pikepdf.Array([20, 80, 100, 95]),
                    A=pikepdf.Dictionary(
                        S=pikepdf.Name("/GoTo"), D=pikepdf.String("target")
                    ),
                )
            )
            pdf.pages[0].obj.Annots.append(link)
            pdf.save(named, force_version=version)
        combined = args.output / ("named-merged-" + version + ".pdf")
        subprocess.run(
            [
                str(args.binary),
                "merge",
                "--output",
                str(combined),
                str(named),
                str(named),
            ],
            env=environment,
            check=True,
            timeout=30,
        )
        with pymupdf.open(combined) as pdf:
            assert len(pdf) == 4
            for offset in (0, 2):
                assert all(
                    link["page"] == offset + 1 for link in pdf[offset].get_links()
                )
        with pikepdf.open(combined) as pdf:
            assert pdf.pdf_version == version
            for offset in (0, 2):
                target = pdf.pages[offset].obj.Annots[-1].A.D
                assert target[0].objgen == pdf.pages[offset + 1].obj.objgen
                assert list(target)[1:] == [pikepdf.Name("/XYZ"), 20, 30, 1.5]
        checked.append("colliding-named-destinations-coordinates-version-" + version)

    project = args.output / "compile-failure"
    overlap = subprocess.run(
        [
            str(args.binary),
            "run",
            "--csv",
            str(project / "students.csv"),
            "--assignments",
            str(project / "assignments.json"),
            "--config",
            str(project / "config"),
            "--templates",
            str(project / "templates"),
            "--core",
            str(args.core),
            "--output",
            str(project / "templates/recursive-output"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert overlap.returncode and "Output directory cannot be inside" in overlap.stderr
    checked.append("overlapping-output-refused")
    result = {"passed": checked}
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
