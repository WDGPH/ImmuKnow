"""Compare the five initial browser/native compiler proof PDFs."""

import json
from pathlib import Path

from playground.scripts.pdf_compare import compare_pdf

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    results = []
    for native in sorted((ROOT / "public/generated").glob("*.native.pdf")):
        name = native.name.removesuffix(".native.pdf")
        browser = ROOT / "test-results/proof" / f"{name}.browser.pdf"
        results.append(
            {
                "template": name,
                **compare_pdf(native, browser, ROOT / "test-results/proof"),
            }
        )
    assert len(results) == 5
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
