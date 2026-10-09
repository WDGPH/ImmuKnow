"""Compare actual PDF semantics, text geometry and rasterized pages."""

from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageStat
from pypdf import PdfReader


def text_runs(page):
    runs = []

    def visit(text, cm, tm, font, size):
        if text.strip():
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            runs.append((text.strip(), x, y, size))

    page.extract_text(visitor_text=visit)
    return runs


def compare_pdf(
    native_path: Path, browser_path: Path, images: Path | None = None
) -> dict:
    native, browser = PdfReader(native_path), PdfReader(browser_path)
    name = browser_path.name
    assert len(native.pages) == len(browser.pages), f"{name}: page count"
    maximum_delta = 0.0
    for n_page, b_page in zip(native.pages, browser.pages):
        assert n_page.mediabox == b_page.mediabox, f"{name}: page size"
        assert " ".join(n_page.extract_text().split()) == " ".join(
            b_page.extract_text().split()
        ), f"{name}: semantic text"
        n_runs, b_runs = text_runs(n_page), text_runs(b_page)
        assert len(n_runs) == len(b_runs), f"{name}: text run count"
        for n_run, b_run in zip(n_runs, b_runs):
            assert n_run[0] == b_run[0], f"{name}: wrapping/text run order"
            delta = max(abs(a - b) for a, b in zip(n_run[1:], b_run[1:]))
            maximum_delta = max(maximum_delta, delta)
            # 0.01pt permits serialization rounding, not changed wrapping.
            assert delta <= 0.01, f"{name}: text geometry differs by {delta}pt"
    with pymupdf.open(native_path) as n_render, pymupdf.open(browser_path) as b_render:
        for index in range(len(n_render)):
            n_pix = n_render[index].get_pixmap(dpi=144)
            b_pix = b_render[index].get_pixmap(dpi=144)
            n_image = Image.frombytes("RGB", (n_pix.width, n_pix.height), n_pix.samples)
            b_image = Image.frombytes("RGB", (b_pix.width, b_pix.height), b_pix.samples)
            assert n_image.size == b_image.size
            difference = ImageChops.difference(n_image, b_image)
            assert max(ImageStat.Stat(difference).mean) <= 0.05, (
                f"{name}: raster difference"
            )
            if images:
                images.mkdir(parents=True, exist_ok=True)
                n_image.save(
                    images
                    / f"{native_path.stem.removesuffix('.native')}.page-{index + 1}.png"
                )
    return {"pages": len(native.pages), "max_text_delta_pt": maximum_delta}
