"""Жизненный цикл ngrok и чтение локального Agent API."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Callable, Optional

import requests

from .ngrok_bundle import ensure_ngrok, resolve_prefer_local

NGROK_API = "http://127.0.0.1:4040/api"
ProgressFn = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


def resolve_ngrok_binary() -> Optional[str]:
    local = resolve_prefer_local()
    if local:
        return local
    return shutil.which("ngrok.exe") or shutil.which("ngrok")


class TunnelManager:
    """Управляет только ngrok; состояние приложений проверяет ServerManager."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._public_url: Optional[str] = None
        self._local_port: Optional[int] = None
        self._progress: ProgressFn = _noop

    def set_progress(self, progress: Optional[ProgressFn]) -> None:
        self._progress = progress or _noop

    def start_tunnel(self, local_port: int, project_path: Optional[str] = None) -> dict:
        del project_path  # совместимость со старым интерфейсом
        if self._process and self._process.poll() is None:
            return {"ok": False, "error": "Туннель уже запущен"}
        self._progress("Подготовка ngrok…")
        try:
            ngrok = ensure_ngrok()
        except RuntimeError as exc:
            ngrok = resolve_ngrok_binary()
            if not ngrok:
                return {"ok": False, "error": str(exc)}

        self._progress(f"Запуск ngrok http {local_port}…")
        try:
            self._process = subprocess.Popen(
                [ngrok, "http", str(local_port), "--log=stdout"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=os.environ.copy(),
            )
        except FileNotFoundError:
            self._process = None
            return {"ok": False, "error": "ngrok не найден"}
        except OSError as exc:
            self._process = None
            return {"ok": False, "error": f"Не удалось запустить ngrok: {exc}"}

        self._local_port = local_port
        self._progress("Ожидание public URL от ngrok Agent API…")
        public_url = self._wait_for_public_url()
        if not public_url:
            error = self._diagnose_startup_failure()
            self.stop_tunnel()
            return {"ok": False, "error": error}
        self._public_url = public_url
        self._progress(f"Публичный URL: {public_url}")
        return {"ok": True, "public_url": public_url, "local_port": local_port}

    def stop_tunnel(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        self._process = None
        self._public_url = None
        self._local_port = None

    def get_public_url(self) -> Optional[str]:
        if self._public_url:
            return self._public_url
        url = self._fetch_public_url()
        if url:
            self._public_url = url
        return url

    def get_active_connections(self) -> int:
        try:
            response = requests.get(f"{NGROK_API}/requests/http", timeout=2)
            response.raise_for_status()
            addresses = {
                row.get("client_ip")
                for row in response.json().get("requests", [])
                if row.get("client_ip")
            }
            return len(addresses)
        except requests.RequestException:
            return 0

    def _wait_for_public_url(self) -> Optional[str]:
        for _ in range(20):
            if self._process and self._process.poll() is not None:
                return None
            url = self._fetch_public_url()
            if url:
                return url
            time.sleep(0.5)
        return None

    def _fetch_public_url(self) -> Optional[str]:
        try:
            response = requests.get(f"{NGROK_API}/tunnels", timeout=2)
            response.raise_for_status()
            tunnels = response.json().get("tunnels", [])
        except requests.RequestException:
            return None
        urls = [item.get("public_url") for item in tunnels if item.get("public_url")]
        return next((url for url in urls if url.startswith("https://")), urls[0] if urls else None)

    def _diagnose_startup_failure(self) -> str:
        if self._process and self._process.poll() is not None:
            error_tail = ""
            try:
                if self._process.stderr:
                    error_tail = (self._process.stderr.read() or "")[-600:]
            except OSError:
                pass
            if error_tail.strip():
                return f"ngrok завершился с ошибкой: {error_tail.strip()}"
            hint = ""
            if not os.environ.get("NGROK_AUTHTOKEN"):
                hint = " Укажите NGROK_AUTHTOKEN или выполните ngrok config add-authtoken."
            return f"ngrok завершился сразу после старта.{hint}"
        try:
            requests.get(f"{NGROK_API}/tunnels", timeout=2)
        except requests.ConnectionError:
            return "Agent API ngrok недоступен: проверьте сеть и порт 4040"
        except requests.Timeout:
            return "Agent API ngrok не ответил вовремя"
        except requests.RequestException as exc:
            return f"Ошибка Agent API ngrok: {exc}"
        return "Не удалось получить public URL от ngrok"
