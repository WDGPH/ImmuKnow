"""Scratch Python interface to the official-library worker; no production changes."""

from __future__ import annotations
import itertools
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

COUNTER = itertools.count()


class NativeSession:
    def __init__(self, root: Path, worker: Path, direct_report: bool = False):
        self.root = root
        self.direct_report = direct_report
        self.last_reports = None
        self.directory = root / "work" / f"native-probe-{next(COUNTER)}"
        self.directory.mkdir(parents=True)
        self.log = (self.directory / "worker.stderr").open("w+b")
        self.process = subprocess.Popen(
            [str(worker), str(root)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        assert self.process.stdin is not None and self.process.stdout is not None
        self.stdin, self.stdout = self.process.stdin, self.process.stdout
        self.closed = False
        self.requests = queue.Queue()
        self.responses = queue.Queue()
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        # One I/O thread owns both blocking pipe directions. The caller's deadline
        # covers transmission as well as receipt, including a cold blocked child.
        while (data := self.requests.get()) is not None:
            try:
                self.stdin.write(data)
                self.stdin.flush()
                line = self.stdout.readline()
            except (OSError, ValueError):
                line = None
            self.responses.put(line or None)
            if not line:
                return

    def request(self, data: dict, timeout: float = 120):
        deadline = time.monotonic() + timeout
        self.requests.put(json.dumps(data, ensure_ascii=False) + "\n")
        try:
            line = self.responses.get(timeout=max(0, deadline - time.monotonic()))
        except queue.Empty:
            self.close()
            raise TimeoutError(
                "Native worker exceeded its per-notice deadline"
            ) from None
        if line is None:
            self.log.seek(0)
            raise RuntimeError(
                "Native worker exited: " + self.log.read().decode(errors="replace")
            )
        result = json.loads(line)
        if result["id"] != data["id"]:
            self.close()
            raise RuntimeError("Native worker returned another notice identity")
        return result

    def compile_command(
        self, command: list[str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        options, inputs = {}, {}
        for i in range(2, len(command) - 2, 2):
            key, value = command[i : i + 2]
            if key == "--input":
                name, item = value.split("=", 1)
                inputs[name] = item
            else:
                options[key] = value
        notice = json.loads((self.root / inputs["data"].lstrip("/")).read_text())
        result = self.request(
            {
                "id": notice["row_key"],
                "notice": notice,
                "inputs": inputs,
                "output": command[-1],
                "timestamp": int(options["--creation-timestamp"]),
                "direct_report": self.direct_report,
            },
            timeout,
        )
        self.last_reports = result.get("reports")
        if not result["ok"]:
            raise subprocess.CalledProcessError(
                1, command, stderr=result["error"] or result["diagnostics"]
            )
        return subprocess.CompletedProcess(command, 0, "", result["diagnostics"])

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.requests.put(None)
        self.reader.join(timeout=1)
        self.stdin.close()
        self.stdout.close()
        self.log.close()
