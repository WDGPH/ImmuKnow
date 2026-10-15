"""Write native build records only inside wheel or source-distribution staging."""

import json
import shutil
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from immuknow.build_info import create_build_info, source_details  # noqa: E402


def write_build_record(package: Path, application_version: str, kind: str) -> None:
    source = source_details(ROOT)
    if kind == "sdist":
        source["source_inputs"] = source_details(package.parent)["source_inputs"]
    record = create_build_info(package, application_version, source, kind=kind)
    (package / "build.json").unlink(missing_ok=True)
    (package / "build.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )


class NativeBuild(build_py):
    def run(self) -> None:
        package = Path(self.build_lib).resolve() / "immuknow"
        if package == ROOT / "immuknow" or package.is_relative_to(ROOT / "immuknow"):
            raise ValueError("Build output must be separate from package source")
        if package.exists():
            shutil.rmtree(package)
        super().run()
        write_build_record(package, self.distribution.get_version(), "wheel")


class NativeSource(sdist):
    def copy_file(
        self,
        infile,
        outfile,
        preserve_mode=True,
        preserve_times=True,
        link=None,
        level=1,
    ):
        # Setuptools rewrites the staged setup.cfg. Make that copy writable
        # without changing permissions on, or linking back to, its source.
        if Path(infile).name == "setup.cfg":
            preserve_mode, link = False, None
        return super().copy_file(
            infile, outfile, preserve_mode, preserve_times, link, level
        )

    def make_release_tree(self, base_dir, files) -> None:
        super().make_release_tree(base_dir, files)
        package = Path(base_dir) / "immuknow"
        # A rebuilt source distribution may contain a hard-linked build record.
        # Unlink that staged copy before replacing it; never write through it.
        (package / "build.json").unlink(missing_ok=True)
        write_build_record(package, self.distribution.get_version(), "sdist")


setup(cmdclass={"build_py": NativeBuild, "sdist": NativeSource})
