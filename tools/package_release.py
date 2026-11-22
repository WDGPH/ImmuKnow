"""Package a native executable and exercise the extracted copy (CI only)."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile


def verify_resources(root: Path, exported: Path) -> None:
    """Compare the executable's resources with the committed bytes."""
    tracked = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "-z", "HEAD", "--", "resources"],
        cwd=root,
    )
    expected = {
        path.removeprefix("resources/"): path
        for path in tracked.decode("utf-8").split("\0")
        if path
    }
    actual = {
        path.relative_to(exported).as_posix()
        for path in exported.rglob("*")
        if path.is_file()
    }
    actual.discard("resource-manifest.json")
    if actual != expected.keys():
        missing = sorted(expected.keys() - actual)
        extra = sorted(actual - expected.keys())
        raise RuntimeError(
            f"Exported resource paths differ. Missing: {missing}. Extra: {extra}."
        )
    for path, tracked_path in expected.items():
        committed = subprocess.check_output(
            ["git", "cat-file", "blob", f"HEAD:{tracked_path}"], cwd=root
        )
        if (exported / path).read_bytes() != committed:
            raise RuntimeError(f"Exported resource differs from the committed bytes: {tracked_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=[
        "linux-x86_64", "windows-x86_64", "macos-aarch64", "macos-x86_64",
    ])
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "Cargo.toml").read_text())["package"]["version"]
    executable = "immuknow.exe" if args.platform.startswith("windows-") else "immuknow"
    args.output.mkdir(parents=True, exist_ok=True)
    suffix = ".zip" if executable.endswith(".exe") else ".tar.gz"
    archive = args.output.resolve() / f"immuknow-{version}-{args.platform}{suffix}"
    with tempfile.TemporaryDirectory(prefix="immuknow-package-") as temporary:
        stage = Path(temporary) / "stage"
        unpacked = Path(temporary) / "extracted"
        stage.mkdir()
        unpacked.mkdir()
        shutil.copy2(args.binary, stage / executable)
        shutil.copy2(root / "LICENSE", stage / "LICENSE")
        files = [stage / executable, stage / "LICENSE"]
        if suffix == ".zip":
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
                for file in files:
                    output.write(file, file.name)
            with zipfile.ZipFile(archive) as output:
                output.extractall(unpacked)
        else:
            with tarfile.open(archive, "w:gz") as output:
                for file in files:
                    output.add(file, arcname=file.name)
            with tarfile.open(archive) as output:
                output.extractall(unpacked, filter="data")
        binary = unpacked / executable
        reported = subprocess.check_output([str(binary), "--version"], cwd=unpacked, text=True)
        if reported.strip() != f"immuknow {version}":
            raise RuntimeError(f"Unexpected executable version: {reported!r}")
        exported = unpacked / "resources"
        subprocess.run([str(binary), "resources", "--output", str(exported)],
                       cwd=unpacked, check=True)
        verify_resources(root, exported)
    print(f"Tested release archive: {archive}", flush=True)


if __name__ == "__main__":
    main()
