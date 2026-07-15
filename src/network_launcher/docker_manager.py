"""Обнаружение и жизненный цикл Docker Compose проектов."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Any, Callable, Optional

import requests
import yaml

from .config import data_dir

ProgressFn = Callable[[str], None]


def _noop_progress(_msg: str) -> None:
    pass


COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
OVERRIDE_NAME = ".network_launcher.override.yml"  # legacy; новые версии пишут только во временную папку
_FRONTEND_HINTS = ("frontend", "front", "web", "ui", "client")
_BACKEND_HINTS = ("backend", "back", "api", "server", "django", "flask", "fastapi")
_GATEWAY_HINTS = ("gateway", "proxy", "traefik", "caddy", "edge")
_DB_HINTS = ("db", "database", "postgres", "mysql", "mongo", "redis", "mariadb")
_NGINX_AS_FRONTEND = ("nginx", "app")
_DB_PORTS = {5432, 5433, 3306, 27017, 6379}


def override_path(project_path: str) -> str:
    return os.path.join(project_path, OVERRIDE_NAME)


def clear_public_url_override(project_path: str) -> None:
    """Удаляет legacy override, который могли оставить старые версии программы."""
    try:
        path = override_path(project_path)
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def find_compose_file(project_path: str) -> Optional[str]:
    for name in COMPOSE_NAMES:
        path = os.path.join(project_path, name)
        if os.path.isfile(path):
            return path
    return None


def detect_docker_project(project_path: str) -> bool:
    return find_compose_file(project_path) is not None


def _compose_cmd() -> Optional[list[str]]:
    if shutil.which("docker"):
        try:
            result = subprocess.run(
                ["docker", "compose", "version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return ["docker", "compose"]
        except (OSError, subprocess.TimeoutExpired):
            pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return None


def docker_available() -> tuple[bool, str]:
    if not shutil.which("docker"):
        return False, "Docker не установлен. Установите и запустите Docker Desktop."
    if not _compose_cmd():
        return False, "Команда docker compose недоступна. Обновите Docker Desktop."
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Не удалось проверить Docker: {exc}"
    if result.returncode != 0:
        return False, "Docker установлен, но daemon не запущен. Откройте Docker Desktop."
    return True, ""


def _parse_host_port(mapping: Any) -> Optional[int]:
    if isinstance(mapping, int):
        return mapping
    if isinstance(mapping, dict):
        value = mapping.get("published")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
    if not isinstance(mapping, str):
        return None
    value = mapping.split("/")[0]
    parts = value.split(":")
    try:
        if len(parts) == 1:
            return int(parts[0])
        return int(parts[-2])
    except ValueError:
        return None


class DockerManager:
    def __init__(self, project_path: str = "", progress: Optional[ProgressFn] = None):
        self.project_path = project_path
        self._progress = progress or _noop_progress
        self._runtime_override_path: Optional[str] = None

    def set_progress(self, progress: Optional[ProgressFn]) -> None:
        self._progress = progress or _noop_progress

    def detect_docker_project(self, project_path: str) -> bool:
        return detect_docker_project(project_path)

    def parse_docker_compose(self, project_path: str) -> dict:
        compose_path = find_compose_file(project_path)
        if not compose_path:
            return {"services": {}, "error": "docker-compose.yml/compose.yml не найден"}
        try:
            with open(compose_path, encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:
            return {"services": {}, "error": f"Ошибка YAML в compose: {exc}"}
        except OSError as exc:
            return {"services": {}, "error": str(exc)}

        services: dict[str, dict] = {}
        for name, cfg in (data.get("services") or {}).items():
            if not isinstance(cfg, dict):
                continue
            ports = []
            for mapping in cfg.get("ports") or []:
                port = _parse_host_port(mapping)
                if port is not None:
                    ports.append(port)
            environment = cfg.get("environment") or {}
            if isinstance(environment, list):
                environment_keys = [str(item).split("=", 1)[0] for item in environment]
            elif isinstance(environment, dict):
                environment_keys = [str(key) for key in environment]
            else:
                environment_keys = []
            services[name] = {
                "ports": ports,
                "role": self._guess_role(name),
                "environment_keys": environment_keys,
                "command": cfg.get("command") or "",
            }

        return {
            "services": services,
            "frontend_port": self._pick_port(services, "frontend"),
            "backend_port": self._pick_port(services, "backend"),
            "compose_file": compose_path,
            "compose_data": data,
        }

    def start_docker(
        self,
        project_path: str,
        *,
        runtime_env: Optional[dict[str, str]] = None,
        frontend: Any = "auto",
        backend: Any = "auto",
    ) -> dict:
        self._progress("Проверка Docker…")
        ok, message = docker_available()
        if not ok:
            return {"ok": False, "error": message}
        self.project_path = project_path
        parsed = self.parse_docker_compose(project_path)
        if parsed.get("error"):
            return {"ok": False, "error": parsed["error"], "logs": ""}

        services = parsed.get("services") or {}
        frontend_port = self.resolve_port(services, frontend, "frontend")
        backend_port = self.resolve_port(services, backend, "backend")
        parsed["frontend_port"] = frontend_port
        parsed["backend_port"] = backend_port
        self._progress(
            f"Compose: сервисы {', '.join(services) or '—'}. "
            f"FE-порт={frontend_port}, API-порт={backend_port}"
        )

        cmd = _compose_cmd()
        assert cmd is not None
        compose_file = parsed["compose_file"]
        args = cmd + ["-f", compose_file]
        app_service = self.resolve_service(services, frontend, "frontend")
        if runtime_env and app_service:
            try:
                self._runtime_override_path = self._write_runtime_override(app_service, runtime_env)
            except OSError as exc:
                return {"ok": False, "error": f"Не удалось создать временный override: {exc}"}
            args += ["-f", self._runtime_override_path]
            self._progress(
                f"Публичное окружение передано сервису {app_service} через временный override"
            )
        args += ["up", "-d", "--remove-orphans"]
        self._progress("docker compose up -d (сборка может занять несколько минут)…")
        try:
            completed = subprocess.run(
                args,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except FileNotFoundError:
            self.cleanup_runtime_override()
            return {"ok": False, "error": "Docker не найден"}
        except subprocess.TimeoutExpired:
            self.cleanup_runtime_override()
            return {"ok": False, "error": "docker compose up превысил таймаут 10 минут"}
        except OSError as exc:
            self.cleanup_runtime_override()
            return {"ok": False, "error": str(exc)}
        if completed.returncode != 0:
            logs = self.get_docker_logs(project_path)
            error = (completed.stderr or completed.stdout or "").strip()
            self.cleanup_runtime_override()
            return {
                "ok": False,
                "error": f"docker compose up завершился с ошибкой:\n{error[-1200:]}",
                "logs": logs,
            }
        self._progress("docker compose up — контейнеры подняты")
        return {
            "ok": True,
            "parsed": parsed,
            "frontend_port": frontend_port,
            "backend_port": backend_port,
            "runtime_env_service": app_service if runtime_env else None,
        }

    def stop_docker(self, project_path: str) -> dict:
        cmd = _compose_cmd()
        if not cmd:
            self.cleanup_runtime_override()
            return {"ok": False, "error": "docker compose недоступен"}
        try:
            completed = subprocess.run(
                cmd + ["stop"], cwd=project_path, capture_output=True, text=True, timeout=120
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.cleanup_runtime_override()
            return {"ok": False, "error": str(exc)}
        self.cleanup_runtime_override()
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout or "").strip()
            return {"ok": False, "error": error[-500:] or "docker compose stop failed"}
        return {"ok": True}

    def apply_public_base_url(self, project_path: str, public_url: str) -> dict:
        return {
            "ok": False,
            "error": "Публичный URL должен передаваться до запуска через runtime override",
        }

    def _write_runtime_override(self, service: str, runtime_env: dict[str, str]) -> str:
        self.cleanup_runtime_override()
        runtime_dir = os.path.join(data_dir(), "runtime")
        os.makedirs(runtime_dir, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".network-launcher.yml",
            prefix="network-launcher-",
            delete=False,
            dir=runtime_dir,
        )
        try:
            yaml.safe_dump(
                {"services": {service: {"environment": runtime_env}}},
                handle,
                default_flow_style=False,
                allow_unicode=True,
            )
        finally:
            handle.close()
        return handle.name

    def cleanup_runtime_override(self) -> None:
        path = self._runtime_override_path
        self._runtime_override_path = None
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    def resolve_service(self, services: dict, selection: Any, role: str) -> Optional[str]:
        if isinstance(selection, str) and selection not in {"", "auto", "none"}:
            if selection in services:
                return selection
        if role == "backend" and selection in {None, "none"}:
            return None
        for name, info in services.items():
            if info.get("role") == role and info.get("ports"):
                return name
        if role == "frontend":
            for name, info in services.items():
                if info.get("role") not in {"db", "gateway"} and info.get("ports"):
                    return name
        return None

    def resolve_port(self, services: dict, selection: Any, role: str) -> Optional[int]:
        if isinstance(selection, int):
            return selection
        if isinstance(selection, str) and selection.isdigit():
            return int(selection)
        if role == "backend" and selection in {None, "none"}:
            return None
        service = self.resolve_service(services, selection, role)
        if service:
            ports = services[service].get("ports") or []
            if ports:
                return int(ports[0])
        return self._pick_port(services, role)

    def _pick_app_service(self, services: dict) -> Optional[str]:
        return self.resolve_service(services, "auto", "frontend")

    def get_container_status(self, project_path: str) -> dict:
        parsed = self.parse_docker_compose(project_path)
        services = parsed.get("services") or {}
        status = {
            name: {"state": "unknown", "role": info.get("role", "other"), "ports": info.get("ports", [])}
            for name, info in services.items()
        }
        cmd = _compose_cmd()
        if not cmd:
            return status
        try:
            completed = subprocess.run(
                cmd + ["ps", "--format", "json"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return status
        if completed.returncode != 0:
            return self._parse_ps_table(completed.stdout or "", status)
        text = (completed.stdout or "").strip()
        rows: list[dict] = []
        try:
            decoded = json.loads(text) if text else []
            rows = decoded if isinstance(decoded, list) else [decoded]
        except json.JSONDecodeError:
            for line in text.splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        for row in rows:
            service = row.get("Service") or row.get("service") or ""
            state = str(row.get("State") or row.get("state") or "").lower()
            if service in status:
                status[service]["state"] = "running" if "run" in state else (state or "unknown")
        return status

    def get_docker_logs(self, project_path: str, service: Optional[str] = None) -> str:
        cmd = _compose_cmd()
        if not cmd:
            return "docker compose недоступен"
        args = cmd + ["logs", "--tail", "200", "--no-color"]
        if service:
            args.append(service)
        try:
            completed = subprocess.run(
                args, cwd=project_path, capture_output=True, text=True, timeout=60
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return str(exc)
        output = (completed.stdout or "") + (completed.stderr or "")
        return output[-8000:] if output else "(пусто)"

    def wait_for_service(self, port: int, timeout: int = 60) -> bool:
        self._progress(f"Ожидание порта :{port} (до {timeout} с)…")
        deadline = time.time() + timeout
        last_report = 0.0
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    self._progress(f"Порт :{port} готов")
                    return True
            elapsed = timeout - max(0, deadline - time.time())
            if elapsed - last_report >= 15:
                last_report = elapsed
                self._progress(f"Ещё ждём :{port}… осталось ~{int(deadline - time.time())} с")
            time.sleep(0.5)
        return False

    def _guess_role(self, name: str) -> str:
        low = name.lower()
        if any(item in low for item in _GATEWAY_HINTS):
            return "gateway"
        if any(item in low for item in _FRONTEND_HINTS):
            return "frontend"
        if any(item in low for item in _NGINX_AS_FRONTEND):
            return "frontend"
        if any(item in low for item in _BACKEND_HINTS):
            return "backend"
        if any(item in low for item in _DB_HINTS):
            return "db"
        return "other"

    def _pick_port(self, services: dict, role: str) -> Optional[int]:
        for info in services.values():
            if info.get("role") != role:
                continue
            for port in info.get("ports") or []:
                if role != "frontend" or port not in _DB_PORTS:
                    return int(port)
        if role == "frontend":
            for info in services.values():
                if info.get("role") in {"db", "gateway"}:
                    continue
                for port in info.get("ports") or []:
                    if port not in _DB_PORTS:
                        return int(port)
        return None

    def _parse_ps_table(self, text: str, status: dict) -> dict:
        for line in text.splitlines()[1:]:
            low = line.lower()
            for name in status:
                if name.lower() in low:
                    status[name]["state"] = "running" if "up" in low or "running" in low else "exited"
        return status


def check_backend_health(port: int, timeout: float = 3.0) -> tuple[bool, str]:
    for path in ("/health", "/api/health", "/"):
        url = f"http://127.0.0.1:{port}{path}"
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code < 500:
                return True, url
        except requests.RequestException:
            continue
    return False, f"http://127.0.0.1:{port}/health"


if __name__ == "__main__":
    manager = DockerManager()
    assert manager._pick_app_service(
        {"db": {"role": "db", "ports": [5433]}, "app": {"role": "frontend", "ports": [3000]}}
    ) == "app"
    print("docker_manager self-check ok")
