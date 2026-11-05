"""Benchmark the unchanged Python/pikepdf pipeline using this exact warm compiler.

This is a benchmark adapter, not a production compiler transport. Run it under
an external time/memory supervisor: the synchronous pipe has no notice deadline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "core",
        "binary",
        "csv",
        "assignments",
        "config",
        "templates",
        "output",
        "metrics",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.core.resolve()))
    from immuknow import bundle_pdfs, compile_notices, encrypt_notices
    from immuknow.orchestrator import run_pipeline

    original_run = compile_notices.run_typst
    child = None
    reports = None
    durations = {
        "render_seconds": 0.0,
        "encryption_seconds": 0.0,
        "delivery_seconds": 0.0,
    }

    def native(command, *, timeout, operation):
        nonlocal child, reports
        if command[1] != "compile":
            return original_run(command, timeout=timeout, operation=operation)
        root = Path(command[command.index("--root") + 1])
        inputs = {}
        for i, flag in enumerate(command):
            if flag == "--input":
                key, value = command[i + 1].split("=", 1)
                inputs[key] = value
        if child is None:
            child = subprocess.Popen(
                [str(args.binary), "serve", "--root", str(root)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
        request = {
            "id": inputs["data"],
            "inputs": inputs,
            "notice": json.loads((root / inputs["data"].lstrip("/")).read_text()),
            "output": command[-1],
            "timestamp": int(command[command.index("--creation-timestamp") + 1]),
            "direct_report": True,
        }
        child.stdin.write(json.dumps(request) + "\n")
        child.stdin.flush()
        result = json.loads(child.stdout.readline())
        assert result["id"] == request["id"]
        if not result["ok"]:
            raise subprocess.CalledProcessError(1, command, stderr=result["error"])
        reports = result["reports"]
        return subprocess.CompletedProcess(command, 0, "", result["diagnostics"])

    compile_notices.run_typst = native
    compile_notices._strip_evidence = lambda content: (
        content,
        [json.dumps(reports).encode()],
        False,
    )

    def instrument(module, name, key):
        original = getattr(module, name)

        def call(*positional, **keywords):
            started = time.perf_counter()
            try:
                return original(*positional, **keywords)
            finally:
                durations[key] += time.perf_counter() - started

        setattr(module, name, call)

    instrument(compile_notices, "compile_render_job", "render_seconds")
    instrument(encrypt_notices, "encrypt_many", "encryption_seconds")
    instrument(bundle_pdfs, "_bundle_run", "delivery_seconds")
    started = time.perf_counter()
    try:
        path = run_pipeline(
            args.csv,
            args.output,
            notice_assignments=args.assignments,
            template_dir=args.templates,
            config_dir=args.config,
            workers=1,
        )
    finally:
        if child is not None:
            child.stdin.close()
            child.wait(timeout=10)
            child.stdout.close()
    wall = time.perf_counter() - started
    record = json.loads(path.read_text())
    metrics = {
        "pipeline_seconds": wall,
        **durations,
        "record": str(path),
        "status": record["status"],
        "entries": len(record["entries"]),
        "application_workers": 1,
        "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        "scope": "Unchanged Python policies/validation/encryption/bundling; only direct-report compiler replaced; same binary as Rust run.",
    }
    args.metrics.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))
    assert record["status"] in ("completed", "completed_with_warnings")


if __name__ == "__main__":
    main()
