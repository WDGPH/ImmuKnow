"""Real setup failures retain prior output and save their available source evidence."""

import json
from pathlib import Path

import pytest
import yaml

from immuknow.orchestrator import run_pipeline
from tests.integration.test_native_pipeline import prepare_cohort

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "failure",
    [
        "configuration",
        "mapping_list",
        "mapping_false",
        "mapping_zero",
        "missing_source",
        "non_csv",
    ],
)
def test_setup_failure_is_recorded_without_purging_prior_output(
    tmp_path: Path, failure: str
):
    command, output, config_dir = prepare_cohort(tmp_path, ("en",))
    source = Path(command[3])
    manifest = Path(command[command.index("--notice-assignments") + 1])
    if failure == "configuration":
        config_path = config_dir / "parameters.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["encryption"] = {
            "enabled": True,
            "password": {"template": "{date_of_birth}"},
        }
        config_path.write_text(yaml.safe_dump(config))
        error, diagnostic = ValueError, "date_of_birth_iso"
    elif failure.startswith("mapping_"):
        value = {"mapping_list": "[]", "mapping_false": "false", "mapping_zero": "0"}[
            failure
        ]
        (config_dir / "parameters.yaml").write_text(value)
        error, diagnostic = ValueError, "Configuration must be a mapping"
    elif failure == "missing_source":
        source = tmp_path / "missing.csv"
        error, diagnostic = FileNotFoundError, "Input file not found"
    else:
        source = tmp_path / "legacy.xlsx"
        source.write_bytes(b"not a CSV")
        error, diagnostic = ValueError, "CSV"
    output.mkdir()
    sentinel = output / "prior.txt"
    sentinel.write_text("prior output")
    with pytest.raises(error, match=diagnostic):
        run_pipeline(source, output, notice_assignments=manifest, config_dir=config_dir)
    assert sentinel.read_text() == "prior output"
    record_path = next(output.glob("*/run.json"))
    record = json.loads(record_path.read_text())
    assert record["status"] == "failed_setup"
    assert (record_path.parent / "report.html").is_file()
    assert not record["delivery_attempts"]
    if failure == "configuration" or failure.startswith("mapping_"):
        assert len(record["entries"]) == 1
        assert record["entries"][0]["source"]["values"]["client_id"] == "0000000001"
        assert record["entries"][0]["original"]["status"] == "not_run"
    else:
        assert not record["entries"]
    assert not list(output.rglob("*.pdf"))
