"""Serve the assembled artifact at its configured project subpath for local QA."""

import http.server
import os
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)
BASE = urlsplit(CONFIG["site_url"]).path.rstrip("/")
PROXY_PREFIX = os.environ.get("IMMUKNOW_PROXY_PREFIX", "").rstrip("/")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Notebook proxies normally strip their prefix. Also accept the full
        # path for local verification or proxies configured to preserve it.
        if PROXY_PREFIX and self.path.startswith(PROXY_PREFIX + "/"):
            self.path = self.path[len(PROXY_PREFIX) :]
        if not self.path.startswith(BASE + "/"):
            self.send_error(404)
            return
        self.path = self.path[len(BASE) :]
        super().do_GET()


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(
        ("localhost", 4173), partial(Handler, directory=str(ROOT / "site"))
    ).serve_forever()
