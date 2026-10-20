"""Native compilation refuses packages outside the saved project, without network access."""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from immuknow.compile_notices import run_typst
from immuknow.orchestrator import run_pipeline
from tests.integration.test_run_accounting import prepare_inputs

pytestmark = pytest.mark.integration


@contextmanager
def network_requests(monkeypatch):
    """A local proxy records any attempted download; no public service is contacted."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_CONNECT(self):
            requests.append(self.path)
            self.send_error(502)

        def do_GET(self):
            requests.append(self.path)
            self.send_error(502)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    proxy = f"http://127.0.0.1:{server.server_port}"
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, proxy)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(name, "")
    try:
        yield requests
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def external_package(root: Path, namespace: str) -> None:
    package = root / namespace / "example" / "0.1.0"
    package.mkdir(parents=True)
    (package / "typst.toml").write_text(
        '[package]\nname = "example"\nversion = "0.1.0"\nentrypoint = "lib.typ"\n'
    )
    (package / "lib.typ").write_text('#let label = "Outside project"\n')


@pytest.mark.parametrize("namespace", ["local", "preview"])
@pytest.mark.parametrize("operation", ["compile", "eval"])
def test_cached_packages_are_refused_even_for_computed_imports(
    tmp_path, monkeypatch, namespace, operation
):
    external = tmp_path / "external"
    external_package(external, namespace)
    monkeypatch.setenv("TYPST_PACKAGE_PATH", str(external))
    monkeypatch.setenv("TYPST_PACKAGE_CACHE_PATH", str(external))
    monkeypatch.delenv("TYPST_CERT", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    source = project / "notice.typ"
    source.write_text(
        '#set text(font: "FreeSans")\n'
        f'#let prefix = "@{namespace}/"\n'
        '#import (prefix + "example:0.1.0"): label\n'
        "#metadata(label) <external>\n#label\n"
    )
    options = [
        "--root",
        str(project),
    ]
    native = os.environ.get("TYPST_BIN", "typst")
    with network_requests(monkeypatch) as requests:
        # Establish that this exact compiler can load the outside package without
        # ImmuKnow's process settings. The actual refusal must not be a bad fixture.
        subprocess.run(
            [native, "compile", *options, str(source), str(tmp_path / "control.pdf")],
            check=True,
            capture_output=True,
            timeout=10,
        )
        command = (
            [native, "compile", *options, str(source), str(tmp_path / "blocked.pdf")]
            if operation == "compile"
            else [
                native,
                "eval",
                *options,
                "--in",
                str(source),
                "query(<external>).map(it => it.value)",
            ]
        )
        with pytest.raises(subprocess.CalledProcessError) as error:
            run_typst(command, timeout=10, operation=operation)
        assert "Package imports are not supported" in error.value.stderr
        assert not (tmp_path / "blocked.pdf").exists()
        assert requests == []
        source.write_text(
            source.read_text().replace('(prefix + "example:0.1.0")', '"helper.typ"')
        )
        (project / "helper.typ").write_text('#let label = "Inside project"')
        run_typst(command, timeout=10, operation=operation)
        assert requests == []


def test_uncached_download_is_refused_before_connecting(tmp_path, monkeypatch):
    source = tmp_path / "notice.typ"
    source.write_text('#include "@preview/example:0.1.0"')
    with network_requests(monkeypatch) as requests:
        with pytest.raises(subprocess.CalledProcessError) as error:
            run_typst(
                [
                    os.environ.get("TYPST_BIN", "typst"),
                    "compile",
                    str(source),
                    str(tmp_path / "notice.pdf"),
                ],
                timeout=10,
                operation="notice compilation",
            )
        assert "Package imports are not supported" in error.value.stderr
        assert requests == []
        assert not (tmp_path / "notice.pdf").exists()
        # Prove that a download by this executable would reach the recorder.
        # The proxy refuses it locally, without contacting a public registry.
        empty = tmp_path / "empty-packages"
        empty.mkdir()
        environment = {
            key: value for key, value in os.environ.items() if key != "TYPST_CERT"
        }
        environment.update(
            TYPST_PACKAGE_PATH=str(empty), TYPST_PACKAGE_CACHE_PATH=str(empty)
        )
        control = subprocess.run(
            [
                os.environ.get("TYPST_BIN", "typst"),
                "compile",
                str(source),
                str(tmp_path / "control.pdf"),
            ],
            env=environment,
            check=False,
            capture_output=True,
            timeout=10,
        )
        assert control.returncode != 0
        assert requests == ["packages.typst.org:443"]


def test_package_failure_does_not_stop_an_independent_notice(tmp_path, monkeypatch):
    source, config, templates, assignments = prepare_inputs(tmp_path)
    external = tmp_path / "external"
    external_package(external, "local")
    monkeypatch.setenv("TYPST_PACKAGE_PATH", str(external))
    selected = templates / "overdue_agents_v1.en.typ"
    selected.write_text(
        '#import "@local/example:0.1.0": label\n' + selected.read_text()
    )
    with network_requests(monkeypatch) as requests:
        report = run_pipeline(
            source,
            tmp_path / "runs",
            config_dir=config,
            template_dir=templates,
            notice_assignments=assignments,
        )
        record = json.loads(report.read_text())
        first, second = record["entries"]
        assert first["original"]["status"] == "failed"
        assert any(
            "Package imports are not supported" in check["message"]
            for check in first["checks"]
        )
        assert second["original"]["status"] == "completed"
        assert requests == []
