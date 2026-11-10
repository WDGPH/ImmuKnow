"""Build deterministic fictional workloads; no production inputs are read."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

HISTORY_AGENTS = (
    "DTaP-IPV",
    "MMR",
    "Var",
    "Men-C-C",
    "Pneu-C-13",
    "HPV-9",
    "Hib",
    "Rota-1",
)
TYPICAL_LENGTHS = (
    10,
    12,
    14,
    15,
    16,
    17,
    18,
    18,
    19,
    19,
    19,
    20,
    20,
    21,
    21,
    22,
    23,
    24,
    25,
    26,
)


def history_length(index: int) -> int:
    position = index % 1000
    if position < 23:
        return 0
    if position < 44:
        return 1 + index % 9
    if position < 970:
        return TYPICAL_LENGTHS[index % len(TYPICAL_LENGTHS)]
    if position < 995:
        return 30 + index % 10
    return 40 + index % 17


def create(output: Path, count: int, style: str, template: Path) -> dict:
    if count < 1:
        raise ValueError("Rows must be positive")
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    output.mkdir(parents=True)
    project = output / "project"
    for name in ("templates", "config"):
        shutil.copytree(
            template / name,
            project / name,
            ignore=shutil.ignore_patterns("lib", "__pycache__"),
        )
    settings_path = project / "templates/settings.typ"
    settings = settings_path.read_text()
    if style == "styled":
        settings = settings.replace(
            "corner-foreground: auto,", 'corner-foreground: rgb("#9d2038"),', 1
        )
        settings = settings.replace(
            "alignment-foreground: auto,", 'alignment-foreground: rgb("#254f8c"),', 1
        )
    elif style == "runs":
        settings = settings.replace(
            '#let accent-color = rgb("#005568")',
            "#let accent-color = cmyk(100%, 20%, 0%, 40%)",
            1,
        )
    settings = settings.replace(
        '"https://example.org/update"',
        '"https://example.org/immunization/record/update"',
        1,
    )
    settings = settings.replace(
        "    lang: notice.language,",
        '    lang: notice.language,\n    reference: notice.client_id + "-fictional-immunization-notice-2026",',
        1,
    )
    if style == "styled":
        assert 'corner-foreground: rgb("#9d2038"),' in settings
        assert 'alignment-foreground: rgb("#254f8c"),' in settings
    if style == "runs":
        assert "#let accent-color = cmyk(100%, 20%, 0%, 40%)" in settings
    assert (
        'reference: notice.client_id + "-fictional-immunization-notice-2026"'
        in settings
    )
    settings_path.write_text(settings)
    parameters_path = project / "config/parameters.yaml"
    parameters = parameters_path.read_text().replace(
        "  group_by: null", "  group_by: [school, notice_variant]", 1
    )
    parameters = parameters.replace(
        "  # sort_by: last_name_dob", "  sort_by: last_name_dob", 1
    )
    assert "group_by: [school, notice_variant]" in parameters
    assert "  sort_by: last_name_dob" in parameters
    parameters_path.write_text(parameters)
    with (template / "input/sample/sample_students.csv").open(newline="") as f:
        headers = csv.DictReader(f).fieldnames
    assert headers
    headers = [
        *headers,
        *(name for name in ("school_id", "board_id") if name not in headers),
    ]
    rows, assignments, lengths = [], [], []
    for index in range(count):
        client_id = str(9000000000 + index)
        school = (index // 2) % 32
        board = school % 4
        birth = dt.date(2009 + index % 7, 1, 15) + dt.timedelta(days=index % 280)
        length = history_length(index)
        lengths.append(length)
        doses = []
        for dose in range(length):
            given = birth + dt.timedelta(days=120 + (dose // 2) * 35 + index % 11)
            agent = HISTORY_AGENTS[(dose + index) % len(HISTORY_AGENTS)]
            validity = "Invalid" if (dose + index) % 17 == 0 else "Valid"
            doses.append(f"{given.isoformat()} - {agent} - {validity}")
        row = dict.fromkeys(headers, "")
        row.update(
            school_name=f"Fictional School {school + 1:02d}",
            school_id=f"S{school + 1:03d}",
            board_name=f"Fictional Board {board + 1}",
            board_id=f"B{board + 1}",
            client_id=client_id,
            first_name=f"Example{index + 1:05d}",
            last_name=f"Benchmark{(index * 37) % count:05d}",
            date_of_birth=birth.isoformat(),
            street_address_line_1=f"{1 + index % 999} Example Lane",
            city="Sampleton",
            province="ON",
            postal_code="N1A 1A1",
            intended_reader="guardian",
            overdue_disease="Diphtheria; Tetanus; Pertussis; Polio; Measles; Mumps; Rubella; Varicella;",
            overdue_agent="DTaP-IPV; MMR; Var;",
            immunizations_given="; ".join(doses) + (";" if doses else ""),
        )
        rows.append(row)
        assignments.append(
            {
                "client_id": client_id,
                "template": (
                    "overdue_agents.en.typ" if index % 2 else "overdue_diseases.en.typ"
                ),
            }
        )
    with (output / "clients.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    (output / "assignments.json").write_text(json.dumps(assignments, indent=2) + "\n")
    metadata = {
        "fictional": True,
        "rows": count,
        "style": style,
        "variants": {
            "overdue_agents.en.typ": count // 2,
            "overdue_diseases.en.typ": (count + 1) // 2,
        },
        "history_entries": sum(lengths),
        "history_min": min(lengths, default=0),
        "history_max": max(lengths, default=0),
        "history_median": sorted(lengths)[len(lengths) // 2] if lengths else 0,
        "encryption": False,
        "group_by": ["school", "notice_variant"],
        "sort_by": "last_name_dob",
        "inputs_sha256": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name in ("clients.csv", "assignments.json")
        },
    }
    metadata["authored_project_sha256"] = {
        str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(project.rglob("*"))
        if path.is_file()
    }
    (output / "workload.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--template-project", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--style", choices=("styled", "svg", "runs"), default="styled")
    args = parser.parse_args()
    print(
        json.dumps(
            create(args.output, args.rows, args.style, args.template_project.resolve()),
            indent=2,
        )
    )
