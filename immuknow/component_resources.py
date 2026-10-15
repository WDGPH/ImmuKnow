"""Check project components against the files supplied by the installed engine."""

from importlib.resources import files
from pathlib import Path


def verify_components(templates: Path) -> None:
    """Require the complete, unchanged library; project manifests cannot replace it."""
    supplied = Path(str(files("immuknow").joinpath("templates/lib/immuknow")))
    library = templates / "lib/immuknow"
    if (templates / "lib").is_symlink() or library.is_symlink():
        raise ValueError("The supplied ImmuKnow library must not use linked paths.")
    paths = list(library.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("The supplied ImmuKnow library must not use linked paths.")
    expected = {
        path.relative_to(supplied).as_posix(): path
        for path in supplied.rglob("*")
        if path.is_file()
    }
    actual = {
        path.relative_to(library).as_posix(): path for path in paths if path.is_file()
    }
    if actual.keys() != expected.keys():
        raise ValueError(
            "Use the complete supplied lib/immuknow directory. "
            "Extra, renamed or missing library files are not supported."
        )
    for name, path in actual.items():
        if path.read_bytes() != expected[name].read_bytes():
            raise ValueError(
                f"ImmuKnow library file differs from the supplied version: {name}"
            )
