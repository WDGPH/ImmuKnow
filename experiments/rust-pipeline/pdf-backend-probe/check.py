"""Compare PDF backends on six fictional notices and focused PDF preservation cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pikepdf
import pymupdf

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--binary", type=Path, required=True)
parser.add_argument("--record", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
base, binary, run = args.output, args.binary, args.record.parent
base.mkdir(parents=True, exist_ok=False)
record = json.loads(args.record.read_text())
assert len(record["entries"]) >= 6, "Provide a completed six-case fictional cohort"
results: list[dict[str, object]] = []


def pixels(p: pymupdf.Page) -> str:
    return hashlib.sha256(
        p.get_pixmap(colorspace=pymupdf.csGRAY, dpi=96).samples
    ).hexdigest()


def link_details(page: pymupdf.Page) -> list[dict[str, object]]:
    return [
        {key: value for key, value in link.items() if key not in {"xref", "id"}}
        for link in page.get_links()
    ]


def invoke(backend: str, *args: object, password: str = "héllo-世界") -> None:
    r = subprocess.run(
        [str(binary), "--backend", backend, *map(str, args)],
        capture_output=True,
        text=True,
        env=dict(os.environ, IMMUKNOW_PROBE_PASSWORD=password),
        timeout=120,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)


def check(backend: str, name: str, f: Callable[[], None]) -> None:
    try:
        f()
        results.append({"backend": backend, "case": name, "passed": True})
    except Exception as e:
        results.append(
            {"backend": backend, "case": name, "passed": False, "error": repr(e)}
        )
    print(results[-1], flush=True)


for backend in ["lopdf", "oxide"]:

    def notices(password: str, suffix: str) -> None:
        for i, e in enumerate(record["entries"][:6]):
            source = run / e["original"]["path"]
            out = base / f"{backend}-{suffix}-notice-{i}.pdf"
            invoke(
                backend,
                "encrypt",
                "--input",
                source,
                "--output",
                out,
                "--password-env",
                "IMMUKNOW_PROBE_PASSWORD",
                password=password,
            )
            with pikepdf.open(out, password=password) as pdf:
                assert (
                    pdf.trailer.Encrypt.R == 6
                    and pdf.trailer.Encrypt.V == 5
                    and pdf.trailer.Encrypt.Length == 256
                )
                assert "/StructTreeRoot" in pdf.Root
                version = pdf.pdf_version
                extensions = str(pdf.Root.get("/Extensions", ""))
                adobe = pdf.Root.get("/Extensions", {}).get("/ADBE", {})
                valid_header = version == "2.0" or (
                    version == "1.7"
                    and str(adobe.get("/BaseVersion", "")) == "/1.7"
                    and int(adobe.get("/ExtensionLevel", 0)) >= 8
                )
            with pymupdf.open(source) as a, pymupdf.open(out) as b:
                assert b.authenticate(password)
                assert len(a) == len(b)
                for x, y in zip(a, b):
                    assert pixels(x) == pixels(y)
                    assert link_details(x) == link_details(y)
            try:
                pikepdf.open(out, password="")
            except pikepdf.PasswordError:
                pass
            else:
                raise AssertionError("Empty password accepted")
        results.append(
            {
                "backend": backend,
                "case": f"encrypted-header-{suffix}",
                "passed": valid_header,
                "version": version,
                "extensions": extensions,
            }
        )

    check(
        backend,
        "six-notice-ascii-encryption-pixels-links-tags",
        lambda: notices("20100101", "ascii"),
    )
    check(
        backend,
        "six-notice-unicode-encryption-pixels-links-tags",
        lambda: notices("héllo-世界", "unicode"),
    )

    def notices_merge() -> None:
        sources = [run / e["original"]["path"] for e in record["entries"][:6]]
        out = base / f"{backend}-notices-merged.pdf"
        invoke(backend, "merge", "--output", out, *sources)
        with pymupdf.open(out) as merged:
            cursor = 0
            for source in sources:
                with pymupdf.open(source) as pdf:
                    for page in pdf:
                        copied = merged[cursor]
                        assert pixels(copied) == pixels(page), (cursor, "pixels")
                        assert link_details(page) == link_details(copied), (
                            cursor,
                            "links",
                        )
                        cursor += 1
            assert len(merged) == cursor

    check(backend, "six-notice-bundle-pixels-links", notices_merge)

    def inherited() -> None:
        source = base / f"{backend}-inherit.pdf"
        out = base / f"{backend}-inherit-merged.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=180, height=240)
        page.insert_text((20, 40), "Inherited geometry and font resources")
        doc.save(source)
        doc.close()
        with pikepdf.open(source, allow_overwriting_input=True) as pdf:
            parent = pdf.pages[0].obj.Parent
            page = pdf.pages[0].obj
            for name in ["/MediaBox", "/Resources"]:
                parent[name] = page[name]
                del page[name]
            parent.Rotate = 90
            pdf.save(source)
        invoke(backend, "merge", "--output", out, source, source)
        with pymupdf.open(source) as a, pymupdf.open(out) as b:
            assert len(b) == 2
            for p in b:
                assert p.rotation == a[0].rotation, (
                    "rotation",
                    p.rotation,
                    a[0].rotation,
                )
                assert p.rect == a[0].rect, ("page box", p.rect, a[0].rect)
                assert pixels(p) == pixels(a[0]), "inherited resources/pixels"

    check(backend, "inherited-resources-mediabox-rotation", inherited)

    def links() -> None:
        source = base / f"{backend}-links.pdf"
        out = base / f"{backend}-links-merged.pdf"
        second_source = base / f"{backend}-links-distinct.pdf"
        for label, path in [("A", source), ("B", second_source)]:
            doc = pymupdf.open()
            doc.new_page(width=180, height=240)
            doc.new_page(width=180, height=240)
            doc[0].insert_text((20, 40), f"First {label}")
            doc[1].insert_text((20, 40), f"Second {label}")
            doc[0].insert_link(
                {
                    "kind": pymupdf.LINK_GOTO,
                    "from": pymupdf.Rect(20, 50, 100, 65),
                    "page": 1,
                }
            )
            doc.save(path)
            doc.close()
        invoke(backend, "merge", "--output", out, source, second_source)
        with (
            pymupdf.open(source) as a,
            pymupdf.open(second_source) as c,
            pymupdf.open(out) as b,
        ):
            assert len(b) == 4
            for i in range(4):
                assert pixels(b[i]) == pixels((a if i < 2 else c)[i % 2])
            first, second = b[0].get_links(), b[2].get_links()
            assert first and first[0].get("page") == 1, ("first target", first)
            assert second and second[0].get("page") == 3, ("second target", second)

    check(backend, "cross-page-link-targets", links)
(base / "results.json").write_text(json.dumps(results, indent=2) + "\n")

# Independently diagnose files rejected by the shared Rust verifier. A tolerant
# viewer opening a file is not evidence that other readers can open it.
diagnostics: list[dict[str, object]] = []
for partial in base.glob("*.partial.pdf"):
    password = "20100101" if "-ascii-" in partial.name else "héllo-世界"
    item: dict[str, object] = {"path": partial.name}
    try:
        with pikepdf.open(partial, password=password) as opened:
            item["qpdf_opened"] = True
    except pikepdf.PdfError as error:
        item["qpdf_opened"] = False
        item["qpdf_error"] = str(error)
    with pymupdf.open(partial) as opened:
        item["mupdf_authentication"] = opened.authenticate(password)
        _, reference = opened.xref_get_key(-1, "Encrypt")
        encryption_id = int(reference.split()[0])
        item["perms_type"] = opened.xref_get_key(encryption_id, "Perms")[0]
    diagnostics.append(item)
(base / "encryption-diagnostics.json").write_text(
    json.dumps(diagnostics, indent=2) + "\n"
)
