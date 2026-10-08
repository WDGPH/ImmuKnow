"""Failures at workflow boundaries cannot be reported as completed notice runs."""

from pathlib import Path

import pytest
import yaml

from immuknow.orchestrator import run_pipeline
from tests.integration.test_native_pipeline import prepare_cohort

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "section,value,diagnostic",
    [
        ("qr", {"enabled": True}, "qr.payload_template"),
        (
            "qr",
            {
                "enabled": True,
                "payload_template": "https://example.test/{date_of_birth}",
            },
            "date_of_birth_iso",
        ),
        (
            "encryption",
            {"enabled": True, "password": {"template": "{date_of_birth}"}},
            "date_of_birth_iso",
        ),
    ],
)
def test_invalid_delivery_config_fails_before_output_preparation(
    tmp_path: Path, section: str, value: dict, diagnostic: str
) -> None:
    command, output_dir, config_dir = prepare_cohort(tmp_path, ("en",))
    config_path = config_dir / "parameters.yaml"
    config = yaml.safe_load(config_path.read_text())
    config[section] = value
    config_path.write_text(yaml.safe_dump(config))
    manifest = Path(command[command.index("--notice-assignments") + 1])
    with pytest.raises(ValueError, match=diagnostic):
        run_pipeline(
            Path(command[3]),
            output_dir,
            notice_assignments=manifest,
            config_dir=config_dir,
        )
    assert not output_dir.exists()


def test_missing_source_is_reported_before_output_preparation(tmp_path: Path) -> None:
    command, output, config_dir = prepare_cohort(tmp_path, ("en",))
    manifest = Path(command[command.index("--notice-assignments") + 1])
    with pytest.raises(FileNotFoundError, match="Input file not found"):
        run_pipeline(
            tmp_path / "missing.csv",
            output,
            notice_assignments=manifest,
            config_dir=config_dir,
        )
    assert not output.exists()


def test_non_csv_source_is_rejected_before_existing_output_is_purged(
    tmp_path: Path,
) -> None:
    """A prior successful delivery survives a rejected legacy Excel input."""
    command, output, config_dir = prepare_cohort(tmp_path, ("en",))
    manifest = Path(command[command.index("--notice-assignments") + 1])
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("prior output")
    excel = tmp_path / "legacy.xlsx"
    excel.write_bytes(b"not a CSV")
    with pytest.raises(ValueError, match="CSV"):
        run_pipeline(
            excel,
            output,
            notice_assignments=manifest,
            config_dir=config_dir,
        )
    assert sentinel.read_text() == "prior output"
