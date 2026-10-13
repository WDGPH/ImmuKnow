"""Compare a downloaded Typst project using the separately installed native engine."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import pymupdf
import zxingcpp
from PIL import Image, ImageChops, ImageStat
from pypdf import PdfReader


def inspect_pdf(path: Path) -> dict:
    reader = PdfReader(path)
    urls = set()
    with pymupdf.open(path) as rendered:
        for page in rendered:
            urls.update(
                code.text
                for code in zxingcpp.read_barcodes(page.get_pixmap(dpi=150).pil_image())
            )
    return {
        "text": [" ".join(page.extract_text().split()) for page in reader.pages],
        "pageSizes": [
            [float(page.mediabox.width), float(page.mediabox.height)]
            for page in reader.pages
        ],
        "qrUrls": sorted(urls),
        "language": str(reader.root_object.get("/Lang")),
    }


def text_coverage(preview: str, pdf: str) -> float:
    def words(value: str) -> Counter[str]:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return Counter(re.findall(r"\w+", normalized))

    pdf_words = words(pdf)
    preview_words = words(preview)
    if not pdf_words:
        return 1.0 if not preview_words else 0.0
    return sum((preview_words & pdf_words).values()) / sum(pdf_words.values())


def raster_difference(preview: Image.Image, reference: Image.Image) -> dict:
    assert preview.size == reference.size
    mean = sum(ImageStat.Stat(ImageChops.difference(preview, reference)).mean) / 3
    preview_ink = sum(preview.convert("L").histogram()[:245])
    reference_ink = sum(reference.convert("L").histogram()[:245])
    assert reference_ink > 0, "Reference page has no visible ink"
    ink_ratio = preview_ink / reference_ink
    return {"mean": mean, "inkRatio": ink_ratio}


def inspect_preview(evidence: Path, pdf: dict) -> dict:
    pages = json.loads((evidence / "preview-pages.json").read_text())
    assert len(pages) == len(pdf["text"]), "Preview/PDF page count differs"
    urls: set[str] = set()
    coverage = []
    pixel_difference = []
    with pymupdf.open(evidence / "browser.pdf") as rendered:
        for index, (page, pdf_text, size) in enumerate(
            zip(pages, pdf["text"], pdf["pageSizes"], strict=True), start=1
        ):
            with Image.open(evidence / f"preview-page-{index}.png") as image:
                assert image.size == (page["width"], page["height"])
                expected_pixels = (math.ceil(size[0] * 2), math.ceil(size[1] * 2))
                assert image.size == expected_pixels, (
                    f"Preview/PDF page {index} dimensions differ: {image.size} vs {expected_pixels}"
                )
                reference = (
                    rendered[index - 1].get_pixmap(dpi=144).pil_image().convert("RGB")
                )
                assert image.size == reference.size
                preview_rgb = image.convert("RGB")
                preview_corner = preview_rgb.getpixel((10, 10))
                reference_corner = reference.getpixel((10, 10))
                assert isinstance(preview_corner, tuple)
                assert isinstance(reference_corner, tuple)
                assert all(
                    preview_corner[channel] >= 245
                    and abs(preview_corner[channel] - reference_corner[channel]) <= 5
                    for channel in range(3)
                ), f"Preview page {index} background differs from the PDF"
                difference = raster_difference(preview_rgb, reference)
                assert difference["mean"] < 5, (
                    f"Preview/PDF page {index} pixels differ: {difference['mean']:.1f}"
                )
                assert 0.9 <= difference["inkRatio"] <= 1.1, (
                    f"Preview/PDF page {index} ink differs: {difference['inkRatio']:.2f}"
                )
                pixel_difference.append(difference)
                urls.update(code.text for code in zxingcpp.read_barcodes(image))
                coverage.append(text_coverage(page["plainText"], pdf_text))
    assert min(coverage) >= 0.9, f"Preview text coverage too low: {coverage}"
    assert sorted(urls) == pdf["qrUrls"], "Preview/PDF QR destinations differ"
    return {
        "pages": len(pages),
        "textCoverage": coverage,
        "meanPixelDifference": pixel_difference,
        "qrUrls": sorted(urls),
    }


def main(evidence: Path) -> None:
    evidence = evidence.resolve()
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"VIRTUAL_ENV", "PYTHONPATH", "UV_PROJECT_ENVIRONMENT"}
    }
    with tempfile.TemporaryDirectory(
        prefix="immuknow-downloaded-project-"
    ) as temporary:
        workspace = Path(temporary)
        extracted = workspace / "Extracted project"
        with ZipFile(evidence / "typst-project.zip") as archive:
            archive.extractall(extracted)
        project = workspace / "Relocated projet Élodie"
        extracted.rename(project)
        assert not project.is_relative_to(Path(__file__).resolve().parents[2])

        def run(*arguments: str) -> str:
            result = subprocess.run(
                [sys.executable, "-m", *arguments],
                cwd=project,
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            with (evidence / "native-commands.log").open("a") as log:
                log.write(f"{arguments!r}\n{result.stdout}\n{result.stderr}\n")
            assert result.returncode == 0, result.stdout + result.stderr
            return result.stdout

        selected = json.loads((evidence / "selected-example.json").read_text())
        browser = inspect_pdf(evidence / "browser.pdf")
        preview = inspect_preview(evidence, browser)
        comparison = {
            **selected,
            "browser": browser,
            "preview": preview,
            "selectors": [],
            "rebundled": False,
        }
        for selector, arguments in (
            ("template", ["--template", selected["template"]]),
            (
                "assignments",
                [
                    "--notice-assignments",
                    selected["input"]["assignments"],
                    "--templates",
                    str(Path(selected["template"]).parent),
                ],
            ),
        ):
            run(
                "immuknow.orchestrator",
                selected["input"]["csv"],
                "--config",
                "config",
                "--output",
                selector,
                *arguments,
            )
            (record_path,) = (project / selector).glob("*/run.json")
            run_dir = record_path.parent
            # Preserve real outputs even if a later comparison fails.
            shutil.copytree(run_dir, evidence / selector)
            record = json.loads(record_path.read_text())
            assert record["status"] in {"completed", "completed_with_warnings"}
            (entry,) = record["entries"]
            assert entry["original"]["status"] == "completed"
            original = run_dir / entry["original"]["path"]
            assert (
                sha256(original.read_bytes()).hexdigest() == entry["original"]["sha256"]
            )
            native = inspect_pdf(original)
            assert native["pageSizes"] == browser["pageSizes"], (
                f"{selector}: native/browser page count or size differs"
            )
            assert native["qrUrls"] == browser["qrUrls"], (
                f"{selector}: native/browser QR destinations differ"
            )
            assert native["language"] == browser["language"]
            native_text, browser_text = (
                " ".join(native["text"]),
                " ".join(browser["text"]),
            )
            coverage = [
                text_coverage(native_text, browser_text),
                text_coverage(browser_text, native_text),
            ]
            assert min(coverage) >= 0.95, (
                f"{selector}: native/browser text coverage too low: {coverage}"
            )
            if selector == "template":
                with pymupdf.open(original) as rendered:
                    for index, page in enumerate(rendered, start=1):
                        page.get_pixmap(dpi=144).save(
                            evidence / f"native-page-{index}.png"
                        )
                native_raster = []
                for index in range(1, len(native["text"]) + 1):
                    with (
                        Image.open(evidence / f"preview-page-{index}.png") as raw,
                        Image.open(evidence / f"native-page-{index}.png") as output,
                    ):
                        difference = raster_difference(
                            raw.convert("RGB"), output.convert("RGB")
                        )
                        native_raster.append(difference)
                comparison["preview"]["nativeRasterDifference"] = native_raster
            assert sorted(entry["render_summary"]["qr_urls"]) == native["qrUrls"]
            assert entry["render_summary"]["page_count"] == len(native["text"])
            findings = sorted(
                {
                    f"{check['code']}:{check['status']}"
                    for check in entry["checks"]
                    if check["status"] in {"warn", "fail"}
                }
            )
            comparison["selectors"].append(
                {
                    "pdf": native,
                    "textCoverage": coverage,
                    "qrUrls": sorted(entry["render_summary"]["qr_urls"]),
                    "findings": findings,
                    "summary": entry["render_summary"],
                }
            )

        if selected["example"] == "source-warnings":
            assert record["status"] == "completed_with_warnings"
            assert entry["routing"]["destination"] == "review"
            original_record = entry["original"].copy()
            original_checks = entry["checks"].copy()
            membership = entry["bundle"]
            review = PdfReader(run_dir / membership["path"])
            review_text = " ".join(page.extract_text() for page in review.pages)
            assert "source.age_unknown" in review_text and "REVIEW" in review_text
            # Saved originals must suffice after removing authored inputs.
            for directory in ("templates", "config", "examples"):
                shutil.rmtree(project / directory)
            tokens = list(
                record["delivery_attempts"][-1]["evaluations"][entry["row_key"]][
                    "warning_tokens"
                ].values()
            )
            run(
                "immuknow.rebundle",
                str(run_dir),
                *[arg for token in tokens for arg in ("--accept-warning", token)],
                "--reason",
                "Reviewed original PDF",
            )
            rebundled = json.loads(record_path.read_text())
            (after,) = rebundled["entries"]
            assert after["original"] == original_record
            assert after["checks"] == original_checks
            assert after["routing"]["destination"] == "delivery"
            assert rebundled["status"] == "completed_with_warnings"
            assert (
                len(rebundled["delivery_attempts"])
                == len(record["delivery_attempts"]) + 1
            )
            assert inspect_pdf(run_dir / after["original"]["path"]) == native
            delivery = inspect_pdf(run_dir / after["bundle"]["path"])
            assert delivery["text"] == native["text"]
            assert delivery["qrUrls"] == native["qrUrls"]
            shutil.copytree(run_dir, evidence / "rebundled")
            comparison["rebundled"] = True
        (evidence / "comparison.json").write_text(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
