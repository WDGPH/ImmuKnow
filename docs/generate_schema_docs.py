from pathlib import Path
import json

SCHEMA_FILE = Path("immuknow/config/input_schema.json")
OUTPUT_FILE = Path("docs/user_guide/input_schema.md")

schema = json.loads(SCHEMA_FILE.read_text())

lines = []

lines.append(f"# {schema.get('title', 'Schema')}\n\n")

if schema.get("description"):
    lines.append(f"{schema['description']}\n\n")

lines.append("## Schema Information\n\n")
lines.append("| Property | Value |\n")
lines.append("|----------|-------|\n")
lines.append(f"| Fields | {len(schema['fields'])} |\n")
lines.append(f"| Field Matching | {', '.join(schema.get('fieldsMatch', []))} |\n")

missing_values = ", ".join(f"`{v}`" for v in schema.get("missingValues", []))
lines.append(f"| Missing Values | {missing_values} |\n\n")

lines.append("## Field Summary\n\n")
lines.append("| Field | Type | Description |\n")
lines.append("|-------|------|-------------|\n")

for field in schema["fields"]:
    description = field.get("description", "")
    lines.append(f"| {field['name']} | {field['type']} | {description} |\n")

OUTPUT_FILE.write_text("".join(lines), encoding="utf-8")

print(f"Generated {OUTPUT_FILE}")
