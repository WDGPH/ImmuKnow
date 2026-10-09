"""Retain installed dependency license and notice files in the static artifact."""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def license_texts(directory: Path) -> list[tuple[str, str]]:
    result = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name.lower().startswith(
            ("license", "licence", "copying", "notice", "copyright")
        ):
            result.append((path.name, path.read_text(errors="replace")))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-source", type=Path, required=True)
    args = parser.parse_args()
    chunks = [
        "ImmuKnow playground third-party notices\n\nCompiler sources are pinned in source-revision.txt. FreeFont's license and exception are in ../fonts/LICENSE.\n"
    ]
    lock = json.loads((ROOT / "package-lock.json").read_text())
    for name, entry in sorted(lock["packages"].items()):
        if not name or entry.get("dev") or name.startswith("node_modules/@napi-rs/"):
            continue
        directory = ROOT / name
        if entry.get("optional") and not directory.exists():
            continue
        package = json.loads((directory / "package.json").read_text())
        chunks.append(
            f"\n=== {package['name']} {package['version']} ({package.get('license', '')}) ===\n{package.get('authors', [])}\n{package.get('repository', '')}\n"
        )
        texts = license_texts(directory)
        if not texts and package["name"].startswith("@myriaddreamin/"):
            texts = license_texts(args.compiler_source)
        if not texts:
            raise ValueError(f"Missing license files: {name}")
        chunks.extend(f"\n--- {name} ---\n{text}" for name, text in texts)
    metadata = json.loads(
        subprocess.check_output(
            [
                "cargo",
                "+1.92.0",
                "metadata",
                "--locked",
                "--format-version",
                "1",
                "--filter-platform",
                "wasm32-unknown-unknown",
            ],
            cwd=args.compiler_source,
        )
    )
    tree = subprocess.check_output(
        [
            "cargo",
            "+1.92.0",
            "tree",
            "--locked",
            "--target",
            "wasm32-unknown-unknown",
            "-p",
            "typst-ts-web-compiler",
            "--no-default-features",
            "--features",
            "web,pdf",
            "--edges",
            "normal",
            "--prefix",
            "none",
            "--format",
            "{p}",
        ],
        cwd=args.compiler_source,
        text=True,
    )
    included = {" ".join(line.split()[:2]) for line in tree.splitlines()}
    packages = {
        p["id"]: p
        for p in metadata["packages"]
        if f"{p['name']} v{p['version']}" in included
    }
    for key in sorted(packages):
        package = packages[key]
        directory = Path(package["manifest_path"]).parent
        texts = license_texts(directory)
        # Workspace members may share the source repository's root license.
        parent = directory
        while not texts and parent.parent != parent:
            parent = parent.parent
            texts = license_texts(parent)
        if not texts and "Apache-2.0" in (package.get("license") or ""):
            texts = [
                (
                    "Apache-2.0 (selected license alternative)",
                    (args.compiler_source / "LICENSE").read_text(),
                )
            ]
        if not texts:
            retained = ROOT / "licenses" / f"{package['name']}.txt"
            if retained.exists():
                texts = [(retained.name, retained.read_text())]
        if not texts:
            raise ValueError(f"Missing license files: {key}")
        chunks.append(
            f"\n=== {package['name']} {package['version']} ({package.get('license', '')}) ===\n{package.get('authors', [])}\n{package.get('repository', '')}\n"
        )
        chunks.extend(f"\n--- {name} ---\n{text}" for name, text in texts)
    output = ROOT / "public/generated/compiler/THIRD_PARTY_NOTICES.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(chunks))


if __name__ == "__main__":
    main()
