"""Generate the CSV field reference from Core's packaged input schema."""

from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "immuknow/schemas/input_schema.json"
OUTPUT_FILE = ROOT / "docs/user_guide/input_schema.md"


def main() -> None:
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    lines = [
        "# CSV input fields\n\n",
        "Use these column names in your input CSV. Required columns must be present; "
        "optional columns may be omitted. Extra columns are accepted, and columns "
        "can appear in any order.\n\n",
        "See [Prepare input](getting_started.md#prepare-input) for file formats, "
        "blank values and input checks.\n\n",
        "| Column | Required | Type | Description |\n",
        "| --- | --- | --- | --- |\n",
    ]
    for field in schema["fields"]:
        required = "Yes" if field.get("constraints", {}).get("required") else "No"
        description = (
            field.get("description", "").replace("|", "\\|").replace("\n", " ")
        )
        name = escape(field["name"])
        lines.append(
            f'| <code style="white-space: nowrap">{name}</code> | '
            f"{required} | {field['type']} | {description} |\n"
        )
    OUTPUT_FILE.write_text("".join(lines), encoding="utf-8")
    print(f"Generated {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
