"""Fetch and verify the same FreeFont archive pinned by native CI."""

import hashlib
import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

ARCHIVE = "fonts-freefont-ttf_20120503-10build1_all.deb"
SHA256 = "d1424c9d47b2a6bd0d5149ca66f2bab9b4365237bfbb6063659d961bab2f8ccb"
URL = "https://archive.ubuntu.com/ubuntu/pool/main/f/fonts-freefont/" + ARCHIVE
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    target = ROOT / "public/generated/fonts"
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="immuknow-fonts-") as tmp:
        archive = Path(tmp) / ARCHIVE
        urllib.request.urlretrieve(URL, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
            raise ValueError("FreeFont archive checksum mismatch")
        subprocess.run(["dpkg-deb", "--extract", str(archive), tmp], check=True)
        fonts = Path(tmp) / "usr/share/fonts/truetype/freefont"
        checksums = {}
        for path in sorted(fonts.glob("*.ttf")):
            shutil.copyfile(path, target / path.name)
            checksums[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        shutil.copyfile(
            Path(tmp) / "usr/share/doc/fonts-freefont-ttf/copyright",
            target / "LICENSE",
        )
        (target / "manifest.json").write_text(json.dumps(checksums, indent=2) + "\n")


if __name__ == "__main__":
    main()
