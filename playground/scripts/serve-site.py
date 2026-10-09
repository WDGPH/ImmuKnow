"""Serve the assembled artifact at its configured project subpath for local QA."""

import http.server
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)
BASE = urlsplit(CONFIG["site_url"]).path.rstrip("/")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith(BASE + "/"):
            self.send_error(404)
            return
        self.path = self.path[len(BASE) :]
        super().do_GET()


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(
        ("localhost", 4173), partial(Handler, directory=str(ROOT / "site"))
    ).serve_forever()
