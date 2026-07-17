"""Жизненный цикл ngrok и чтение локального Agent API."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
import time
from collections import deque
from typing import Callable, Optional

import requests
import yaml

from .ngrok_bundle import ensure_ngrok, resolve_prefer_local
from .process_utils import hidden_process_kwargs

NGROK_API = "http://127.0.0.1:4040/api"
ProgressFn = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


def resolve_ngrok_binary() -> Optional[str]:
    local = resolve_prefer_local()
    if local:
        return local
    return shutil.which("ngrok.exe") or shutil.which("ngrok")


def default_ngrok_config_path() -> str:
    """Return the documented default ngrok configuration path."""
    system = platform.system()
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser(
            "~/AppData/Local"
        )
        return os.path.join(local_app_data, "ngrok", "ngrok.yml")
    if system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/ngrok/ngrok.yml")
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(config_home, "ngrok", "ngrok.yml")


class TunnelManager:
    """Управляет только ngrok; состояние приложений проверяет ServerManager."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._public_url: Optional[str] = None
        self._local_port: Optional[int] = None
        self._progress: ProgressFn = _noop
        self._output_tail: deque[str] = deque(maxlen=120)
        self._output_thread: Optional[threading.Thread] = None

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
                [ngrok, "http", str(local_port), "--log=stdout", "--log-level=info"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=os.environ.copy(),
                **hidden_process_kwargs(),
            )
        except FileNotFoundError:
            self._process = None
            return {"ok": False, "error": "ngrok не найден"}
        except OSError as exc:
            self._process = None
            return {"ok": False, "error": f"Не удалось запустить ngrok: {exc}"}

        self._output_tail.clear()
        self._output_thread = threading.Thread(
            target=self._drain_output,
            args=(self._process,),
            daemon=True,
        )
        self._output_thread.start()
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
        self._output_thread = None

    def get_public_url(self, refresh: bool = False) -> Optional[str]:
        if self._public_url and not refresh:
            return self._public_url
        if not self._process or self._process.poll() is not None or not self._local_port:
            if refresh:
                self._public_url = None
            return None
        url = self._fetch_public_url(self._local_port)
        if url:
            self._public_url = url
        elif refresh:
            self._public_url = None
        return url

    def check_auth_status(self) -> dict:
        """Check that an authtoken is present and the local ngrok config is valid."""
        if os.environ.get("NGROK_AUTHTOKEN", "").strip():
            return {
                "ok": True,
                "configured": True,
                "message": "Токен настроен через NGROK_AUTHTOKEN",
                "source": "environment",
            }
        ngrok = resolve_ngrok_binary()
        if not ngrok:
            return {
                "ok": False,
                "configured": False,
                "message": "ngrok не найден",
            }
        config_path = default_ngrok_config_path()
        if not self._config_has_authtoken(config_path):
            return {
                "ok": True,
                "configured": False,
                "message": "Токен не настроен",
            }
        try:
            completed = subprocess.run(
                [ngrok, "config", "check"],
                capture_output=True,
                text=True,
                timeout=20,
                **hidden_process_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "ok": False,
                "configured": False,
                "message": f"Не удалось проверить конфигурацию ngrok: {exc}",
            }
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").strip()
            return {
                "ok": False,
                "configured": False,
                "message": f"Конфигурация ngrok повреждена: {details[-300:]}",
            }
        return {
            "ok": True,
            "configured": True,
            "message": "Токен настроен",
            "source": "config",
        }

    def save_authtoken(self, token: str) -> dict:
        """Persist an authtoken with the official CLI without exposing the secret."""
        secret = token.strip()
        if not secret:
            return {
                "ok": False,
                "configured": False,
                "message": "Вставьте authtoken ngrok",
            }
        try:
            ngrok = ensure_ngrok()
            completed = subprocess.run(
                [ngrok, "config", "add-authtoken", secret],
                capture_output=True,
                text=True,
                timeout=30,
                **hidden_process_kwargs(),
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            safe_error = str(exc).replace(secret, "***")
            return {
                "ok": False,
                "configured": False,
                "message": f"Не удалось сохранить токен: {safe_error}",
            }
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").replace(secret, "***")
            return {
                "ok": False,
                "configured": False,
                "message": f"ngrok не сохранил токен: {details.strip()[-300:]}",
            }
        status = self.check_auth_status()
        if status.get("configured"):
            status["message"] = "Токен сохранён и настроен"
        return status

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
            url = self._fetch_public_url(self._local_port)
            if url:
                return url
            time.sleep(0.5)
        return None

    def _drain_output(self, process: subprocess.Popen) -> None:
        stream = process.stdout
        if stream is None:
            return
        try:
            for line in stream:
                text = line.rstrip("\r\n")
                if text:
                    self._output_tail.append(text)
        except (OSError, ValueError):
            pass

    @staticmethod
    def _config_has_authtoken(path: str) -> bool:
        try:
            with open(path, encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except (OSError, yaml.YAMLError):
            return False
        return isinstance(data, dict) and bool(str(data.get("authtoken") or "").strip())

    def _fetch_public_url(self, local_port: Optional[int] = None) -> Optional[str]:
        try:
            response = requests.get(f"{NGROK_API}/tunnels", timeout=2)
            response.raise_for_status()
            tunnels = response.json().get("tunnels", [])
        except requests.RequestException:
            return None
        if local_port is not None:
            tunnels = [
                item
                for item in tunnels
                if self._addr_matches_port((item.get("config") or {}).get("addr"), local_port)
            ]
        urls = [item.get("public_url") for item in tunnels if item.get("public_url")]
        return next((url for url in urls if url.startswith("https://")), urls[0] if urls else None)

    @staticmethod
    def _addr_matches_port(addr: object, local_port: int) -> bool:
        value = str(addr or "").strip().rstrip("/")
        return value == str(local_port) or value.endswith(f":{local_port}")

    @staticmethod
    def _friendly_ngrok_error(details: str) -> str:
        text = details.strip()
        lowered = text.lower()
        if "err_ngrok_9040" in lowered:
            return (
                "ngrok заблокировал текущий IP-адрес (ERR_NGROK_9040). "
                "Смените сеть или включите VPN, затем повторите запуск."
            )
        if "authtoken" in lowered or "authentication failed" in lowered:
            return (
                "ngrok не прошёл авторизацию. Выполните "
                "ngrok config add-authtoken <TOKEN> и повторите запуск."
            )
        return f"ngrok завершился с ошибкой: {text}"

    def _diagnose_startup_failure(self) -> str:
        if self._process and self._process.poll() is not None:
            if self._output_thread:
                self._output_thread.join(timeout=0.5)
            error_tail = "\n".join(self._output_tail)[-1200:]
            if error_tail.strip():
                return self._friendly_ngrok_error(error_tail)
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
        port = f" для proxy :{self._local_port}" if self._local_port else ""
        return (
            f"Agent API ngrok отвечает, но активный туннель{port} не найден. "
            "Возможно, порт 4040 занят другим процессом ngrok."
        )
