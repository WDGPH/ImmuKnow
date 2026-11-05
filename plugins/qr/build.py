"""Rebuild or verify the bundled QR plugin; ordinary Core builds need no Rust."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    project = Path(__file__).resolve().parent
    root = project.parents[1]
    toolchain = tomllib.loads((project / "rust-toolchain.toml").read_text())[
        "toolchain"
    ]["channel"]
    destination = root / "immuknow/typst/vendor/qr/qr.wasm"
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")).resolve()
    sysroot = subprocess.check_output(
        ["rustc", "+" + toolchain, "--print", "sysroot"], text=True
    ).strip()
    with tempfile.TemporaryDirectory(prefix="immuknow-qr-build-") as temporary:
        target = Path(temporary)
        environment = dict(os.environ)
        environment["CARGO_TARGET_DIR"] = str(target)
        environment.pop("RUSTFLAGS", None)
        environment["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(
            f"--remap-path-prefix={source}={replacement}"
            for source, replacement in (
                (root, "/immuknow"),
                (cargo_home, "/cargo"),
                (target, "/target"),
                (sysroot, "/rust-toolchain"),
            )
        )
        subprocess.run(
            [
                "cargo",
                "+" + toolchain,
                "build",
                "--locked",
                "--release",
                "--target",
                "wasm32-unknown-unknown",
            ],
            cwd=project,
            env=environment,
            check=True,
        )
        built = target / "wasm32-unknown-unknown/release/immuknow_qr.wasm"
        if options.check:
            if built.read_bytes() != destination.read_bytes():
                raise SystemExit(
                    "QR plugin differs; rebuild with python plugins/qr/build.py"
                )
        else:
            shutil.copyfile(built, destination)
        print(f"QR plugin {'verified' if options.check else 'built'}: {destination}")


if __name__ == "__main__":
    main()
