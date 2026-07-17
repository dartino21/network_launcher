"""HTTP-сервер со SPA-fallback: 404 → index.html."""

from __future__ import annotations

import argparse
import logging
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


LOGGER = logging.getLogger(__name__)


class SpaHandler(SimpleHTTPRequestHandler):
    """Отдаёт статику и использует index.html только для SPA-навигации."""

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.exists(path):
            return super().send_head()
        requested_path = Path(urlsplit(self.path).path)
        if requested_path.suffix:
            return super().send_head()
        index = Path(self.directory) / "index.html"
        if index.is_file():
            self.path = "/index.html"
        return super().send_head()

    def log_message(self, message_format, *args) -> None:
        """Do not write request logs to missing stderr in a windowed EXE."""
        LOGGER.debug(
            "%s - %s",
            self.address_string(),
            message_format % args,
        )

    def log_error(self, message_format, *args) -> None:
        LOGGER.warning(
            "%s - %s",
            self.address_string(),
            message_format % args,
        )


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
