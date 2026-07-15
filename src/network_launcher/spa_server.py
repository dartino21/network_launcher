"""HTTP-сервер со SPA-fallback: 404 → index.html."""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class SpaHandler(SimpleHTTPRequestHandler):
    """Отдаёт статику; неизвестные пути — index.html (client-side routing)."""

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isfile(path):
            return super().send_head()
        index = Path(self.directory) / "index.html"
        if index.is_file():
            self.path = "/index.html"
        return super().send_head()


def main() -> None:
    parser = argparse.ArgumentParser(description="SPA static server")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--directory", default=".")
    args = parser.parse_args()

    handler = partial(SpaHandler, directory=args.directory)
    with ThreadingHTTPServer((args.bind, args.port), handler) as httpd:
        print(f"Serving SPA on http://{args.bind}:{args.port}", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
