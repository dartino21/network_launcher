"""Планирование, запуск и остановка локального проекта и publish-proxy."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer
from typing import Callable, Optional

import psutil
import requests

from .docker_manager import DockerManager, check_backend_health, detect_docker_project, docker_available
from .gateway_proxy import GatewayProxy, detect_existing_gateway_port
from .publish_profile import (
    PublishProfile,
    detect_dev_project,
    find_loopback_browser_urls,
    resolve_toggle,
)
from .spa_server import SpaHandler

ProgressFn = Callable[[str], None]


def _noop(_msg: str) -> None:
    pass


def find_free_port(start_port: int = 8080, excluded: Optional[set[int]] = None) -> int:
    excluded = excluded or set()
    port = start_port
    while port <= 65535:
        if port in excluded:
            port += 1
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    raise OSError("Нет свободных TCP-портов")


def detect_project_type(path: str) -> str:
    if detect_docker_project(path):
        return "docker"
    if os.path.isfile(os.path.join(path, "index.html")):
        return "static"
    if os.path.isfile(os.path.join(path, "package.json")):
        return "node"
    if os.path.isfile(os.path.join(path, "app.py")):
        return "flask"
    return "unknown"


def _npm_cmd(name: str) -> str:
    return f"{name}.cmd" if sys.platform == "win32" else name


def find_project_python(project_path: str) -> Optional[str]:
    """Prefer the selected project's virtual environment over the launcher EXE."""
    names = (".venv", "venv", "env")
    executable = "python.exe" if sys.platform == "win32" else "python"
    for name in names:
        candidate = os.path.join(project_path, name, "Scripts" if sys.platform == "win32" else "bin", executable)
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("python") or shutil.which("python3")


def launch_prerequisite_error(project_path: str, project_type: str) -> Optional[str]:
    """Return an actionable message before starting a long-running subprocess."""
    if project_type == "node":
        if not shutil.which(_npm_cmd("npm")):
            return "Node.js/npm не найден. Установите Node.js LTS и перезапустите программу."
    elif project_type == "docker":
        # DockerManager performs the full daemon and Compose validation.
        ok, message = docker_available()
        if not ok:
            return message
    elif project_type == "flask":
        python = find_project_python(project_path)
        if not python:
            return "Не найден Python проекта. Создайте .venv с Flask или установите Python в PATH."
        try:
            probe = subprocess.run(
                [python, "-c", "import flask"], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"Не удалось проверить Python/Flask: {exc}"
        if probe.returncode:
            return "Flask не установлен в Python проекта. Выполните: python -m pip install flask"
    return None


def _kill_tree(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
    except psutil.Error:
        return
    children = parent.children(recursive=True)
    for process in children:
        try:
            process.terminate()
        except psutil.Error:
            pass
    try:
        parent.terminate()
    except psutil.Error:
        pass
    _, alive = psutil.wait_procs(children + [parent], timeout=3)
    for process in alive:
        try:
            process.kill()
        except psutil.Error:
            pass


class ServerManager:
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None
        self._project_type: Optional[str] = None
        self._project_path: Optional[str] = None
        self._port: Optional[int] = None
        self._url: Optional[str] = None
        self._backend_port: Optional[int] = None
        self.docker_manager: Optional[DockerManager] = None
        self._gateway: Optional[GatewayProxy] = None
        self._gateway_mode: Optional[str] = None
        self._prepared: Optional[dict] = None
        self._progress: ProgressFn = _noop

    def set_progress(self, progress: Optional[ProgressFn]) -> None:
        self._progress = progress or _noop

    def detect_project_type(self, project_path: str) -> str:
        return detect_project_type(project_path)

    def prepare_launch(
        self,
        project_path: str,
        preferred_port: Optional[int] = None,
        profile: Optional[PublishProfile] = None,
    ) -> dict:
        if self._is_busy():
            return {"ok": False, "error": "Сервер или proxy уже запущен"}
        profile = profile or PublishProfile()
        project_type = detect_project_type(project_path)
        self._progress(f"Тип проекта: {project_type}")
        if project_type == "unknown":
            return {
                "ok": False,
                "error": "Неизвестный тип проекта: нужен compose-файл, index.html, package.json или app.py",
            }

        prerequisite_error = launch_prerequisite_error(project_path, project_type)
        if prerequisite_error:
            return {"ok": False, "error": prerequisite_error}

        compose_data = None
        services: dict = {}
        gateway_mode = "proxy"
        if project_type == "docker":
            manager = DockerManager(project_path, progress=self._progress)
            parsed = manager.parse_docker_compose(project_path)
            if parsed.get("error"):
                return {"ok": False, "error": parsed["error"]}
            services = parsed.get("services") or {}
            compose_data = parsed.get("compose_data") or {}
            frontend_port = manager.resolve_port(services, profile.frontend, "frontend")
            backend_port = manager.resolve_port(services, profile.backend, "backend")
            existing_gateway = detect_existing_gateway_port(services)
            if existing_gateway:
                frontend_port = existing_gateway
                backend_port = None
                gateway_mode = "compose+proxy"
            if not frontend_port:
                return {
                    "ok": False,
                    "error": "В compose не найден опубликованный frontend-порт. Укажите его в расширенных настройках.",
                }
        else:
            selection = profile.frontend
            if isinstance(selection, int):
                frontend_port = selection
            elif isinstance(selection, str) and selection.isdigit():
                frontend_port = int(selection)
            else:
                start = preferred_port or (5000 if project_type == "flask" else 8080)
                frontend_port = find_free_port(start)
            backend = profile.backend
            if isinstance(backend, int):
                backend_port = backend
            elif isinstance(backend, str) and backend.isdigit():
                backend_port = int(backend)
            else:
                backend_port = None

        dev_detected = detect_dev_project(project_path, compose_data)
        dev_compatibility = resolve_toggle(profile.dev_compatibility, dev_detected)
        preserve_host = resolve_toggle(profile.preserve_host, not dev_compatibility)
        used_ports = {frontend_port}
        if backend_port:
            used_ports.add(backend_port)
        proxy_port = find_free_port(18080, used_ports)
        self._progress("Проверка браузерных URL и настроек проекта…")
        findings = find_loopback_browser_urls(project_path)
        plan = {
            "ok": True,
            "type": project_type,
            "project_path": project_path,
            "preferred_port": preferred_port,
            "frontend_port": frontend_port,
            "backend_port": backend_port,
            "proxy_port": proxy_port,
            "profile": profile,
            "services": services,
            "gateway_mode": gateway_mode,
            "dev_compatibility": dev_compatibility,
            "preserve_host": preserve_host,
            "preflight_findings": findings,
        }
        self._prepared = plan
        return plan

    def start_proxy(self, plan: dict) -> dict:
        if not plan.get("ok"):
            return plan
        if self._gateway is not None:
            return {"ok": False, "error": "Publish proxy уже запущен"}
        self._progress(
            f"Запуск publish proxy :{plan['proxy_port']} -> FE :{plan['frontend_port']}"
            + (f", API :{plan['backend_port']}" if plan.get("backend_port") else "")
        )
        try:
            gateway = GatewayProxy(
                plan["frontend_port"],
                plan.get("backend_port"),
                plan["proxy_port"],
                plan["profile"].backend_prefixes,
                dev_compatibility=plan["dev_compatibility"],
                preserve_host=plan["preserve_host"],
            )
            gateway.start()
        except OSError as exc:
            return {"ok": False, "error": f"Не удалось запустить publish proxy: {exc}"}
        self._gateway = gateway
        self._port = plan["proxy_port"]
        self._url = gateway.url
        self._gateway_mode = plan["gateway_mode"]
        return {"ok": True, "port": plan["proxy_port"], "url": gateway.url}

    def start_prepared(self, plan: dict, public_url: str) -> dict:
        if self._gateway is None:
            return {"ok": False, "error": "Publish proxy не запущен"}
        project_path = plan["project_path"]
        project_type = plan["type"]
        profile: PublishProfile = plan["profile"]
        # Состояние задаётся до запуска, чтобы любой последующий сбой корректно
        # остановил уже созданные процессы/контейнеры.
        self._project_type = project_type
        self._project_path = project_path
        runtime_env = {
            name: public_url.rstrip("/") for name in profile.public_url_env_names if name
        }
        runtime_env["NETWORK_LAUNCHER_PUBLIC_URL"] = public_url.rstrip("/")

        if project_type == "docker":
            result = self._start_docker(plan, runtime_env)
            if not result.get("ok"):
                return result
            cmd = "docker compose up -d + publish proxy"
            services = result.get("services", {})
            backend_ok = result.get("backend_ok")
            health_url = result.get("backend_health_url")
        else:
            if project_type == "node":
                install_error = self._ensure_npm_install(project_path)
                if install_error:
                    return {"ok": False, "error": install_error}
            try:
                cmd = self._start_local_project(plan, runtime_env)
            except OSError as exc:
                return {"ok": False, "error": str(exc)}
            if not self._wait_for_http(f"http://127.0.0.1:{plan['frontend_port']}", timeout=180):
                return {
                    "ok": False,
                    "error": (
                        f"Сайт не ответил на локальном порту :{plan['frontend_port']} за 180 с. "
                        "Проверьте команды и ошибки сайта на вкладке «Логи»."
                    ),
                }
            services = {}
            backend_ok = None
            health_url = None

        self._backend_port = plan.get("backend_port")
        checks = self.verify_proxy(timeout=30)
        if not checks.get("http_ok"):
            return {
                "ok": False,
                "error": f"Приложение запущено, но proxy-проверка не прошла: {checks.get('error', 'нет ответа')}",
            }
        self._progress(
            f"Proxy-проверка: HTTP {checks.get('status')}, WebSocket relay готов, dev compatibility="
            f"{'on' if plan['dev_compatibility'] else 'off'}"
        )
        return {
            "ok": True,
            "type": project_type,
            "port": plan["proxy_port"],
            "proxy_port": plan["proxy_port"],
            "preferred_port": plan.get("preferred_port") or plan["frontend_port"],
            "port_changed": False,
            "url": self._url,
            "local_url": self._url,
            "public_url": public_url,
            "upstream_url": f"http://127.0.0.1:{plan['frontend_port']}",
            "cmd": cmd,
            "frontend_port": plan["frontend_port"],
            "backend_port": plan.get("backend_port"),
            "backend_ok": backend_ok,
            "backend_health_url": health_url,
            "gateway_mode": plan["gateway_mode"],
            "services": services,
            "checks": checks,
            "dev_compatibility": plan["dev_compatibility"],
            "backend_prefixes": profile.backend_prefixes,
            "preflight_findings": plan.get("preflight_findings", []),
            "auth_url_applied": bool(profile.public_url_env_names),
        }

    def start_server(
        self,
        project_path: str,
        preferred_port: Optional[int] = None,
        public_url: str = "",
        profile: Optional[PublishProfile] = None,
    ) -> dict:
        """Совместимый синхронный путь для старых callers без управления ngrok."""
        plan = self.prepare_launch(project_path, preferred_port, profile)
        if not plan.get("ok"):
            return plan
        proxy = self.start_proxy(plan)
        if not proxy.get("ok"):
            return proxy
        return self.start_prepared(plan, public_url or proxy["url"])

    def _start_docker(self, plan: dict, runtime_env: dict[str, str]) -> dict:
        manager = DockerManager(plan["project_path"], progress=self._progress)
        self.docker_manager = manager
        result = manager.start_docker(
            plan["project_path"],
            runtime_env=runtime_env,
            frontend=plan["profile"].frontend,
            backend=plan["profile"].backend,
        )
        if not result.get("ok"):
            return result
        if not manager.wait_for_service(plan["frontend_port"], timeout=180):
            logs = manager.get_docker_logs(plan["project_path"])
            return {
                "ok": False,
                "error": f"Приложение не ответило на :{plan['frontend_port']}.\nЛоги:\n{logs[-2500:]}",
            }
        backend_ok = None
        health_url = None
        if plan.get("backend_port"):
            if not manager.wait_for_service(plan["backend_port"], timeout=60):
                return {"ok": False, "error": f"Backend-порт {plan['backend_port']} не открылся"}
            backend_ok, health_url = check_backend_health(plan["backend_port"])
        return {
            "ok": True,
            "services": (result.get("parsed") or {}).get("services", {}),
            "backend_ok": backend_ok,
            "backend_health_url": health_url,
        }

    def _start_local_project(self, plan: dict, runtime_env: dict[str, str]) -> str:
        project_path = plan["project_path"]
        project_type = plan["type"]
        port = plan["frontend_port"]
        if project_type == "static":
            self._start_spa(project_path, port)
            return f"SPA http://127.0.0.1:{port}"
        command, env = self._build_command(project_path, project_type, port, runtime_env)
        kwargs = {
            "args": command,
            "cwd": project_path,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,
            "env": env,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        self._process = subprocess.Popen(**kwargs)
        return " ".join(command)

    def verify_proxy(self, timeout: int = 30) -> dict:
        if not self._url:
            return {"http_ok": False, "websocket_ready": False, "error": "Нет proxy URL"}
        deadline = time.time() + timeout
        last_error = ""
        while time.time() < deadline:
            try:
                response = requests.get(self._url, timeout=5, allow_redirects=True)
                if response.status_code < 500:
                    return {
                        "http_ok": True,
                        "websocket_ready": True,
                        "status": response.status_code,
                        "final_url": response.url,
                    }
                last_error = f"HTTP {response.status_code}"
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(0.5)
        return {"http_ok": False, "websocket_ready": True, "error": last_error}

    def stop_server(self) -> None:
        if self._project_type == "docker" and self._project_path:
            manager = self.docker_manager or DockerManager(self._project_path)
            manager.stop_docker(self._project_path)
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        if self._process is not None and self._process.poll() is None:
            _kill_tree(self._process.pid)
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    self._process.kill()
                except OSError:
                    pass
        if self._gateway is not None:
            self._gateway.stop()
        self._clear()

    def get_server_status(self) -> dict:
        return {
            "running": self._is_busy(),
            "type": self._project_type,
            "port": self._port,
            "url": self._url,
            "backend_port": self._backend_port,
            "project_path": self._project_path,
            "pid": self._process.pid if self._process and self._process.poll() is None else None,
        }

    def get_process(self) -> Optional[subprocess.Popen]:
        return self._process

    def get_docker_manager(self) -> Optional[DockerManager]:
        return self.docker_manager

    def apply_public_base_url(self, public_url: str) -> dict:
        return {"ok": True, "skipped": True, "reason": "URL уже применён до запуска"}

    def _is_busy(self) -> bool:
        if self._gateway is not None:
            return True
        if self._project_type == "docker" and self._project_path and self.docker_manager:
            return True
        if self._process is not None and self._process.poll() is None:
            return True
        return bool(self._httpd and self._http_thread and self._http_thread.is_alive())

    def _clear(self) -> None:
        if self.docker_manager:
            self.docker_manager.cleanup_runtime_override()
        self._process = None
        self._httpd = None
        self._http_thread = None
        self._project_type = None
        self._project_path = None
        self._port = None
        self._url = None
        self._backend_port = None
        self.docker_manager = None
        self._gateway = None
        self._gateway_mode = None
        self._prepared = None

    def _start_spa(self, directory: str, port: int) -> None:
        handler = partial(SpaHandler, directory=directory)
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._httpd = server
        self._http_thread = thread

    def _ensure_npm_install(self, project_path: str) -> Optional[str]:
        if os.path.isdir(os.path.join(project_path, "node_modules")):
            return None
        try:
            completed = subprocess.run(
                [_npm_cmd("npm"), "install"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except FileNotFoundError:
            return "npm не найден. Установите Node.js."
        except subprocess.TimeoutExpired:
            return "npm install превысил таймаут 10 минут"
        except OSError as exc:
            return f"npm install: {exc}"
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout or "")[-500:]
            return f"npm install завершился с ошибкой: {error.strip()}"
        return None

    def _build_command(
        self,
        project_path: str,
        project_type: str,
        port: int,
        runtime_env: Optional[dict[str, str]] = None,
    ) -> tuple[list[str], dict]:
        env = os.environ.copy()
        env.update(runtime_env or {})
        env["PORT"] = str(port)
        if project_type == "node":
            build_dir = os.path.join(project_path, "build")
            if os.path.isdir(build_dir):
                return [_npm_cmd("npx"), "serve", "-s", "build", "-l", str(port)], env
            return [_npm_cmd("npm"), "start"], env
        python = find_project_python(project_path)
        if not python:
            raise OSError("Не найден Python для Flask-проекта")
        env["FLASK_RUN_PORT"] = str(port)
        return [
            python,
            "-m",
            "flask",
            "--app",
            "app",
            "run",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ], env

    def _wait_for_http(self, url: str, timeout: int) -> bool:
        deadline = time.time() + timeout
        self._progress(f"Ожидание HTTP {url} (до {timeout} с)…")
        while time.time() < deadline:
            if self._process is not None and self._process.poll() is not None:
                return False
            try:
                response = requests.get(url, timeout=3, allow_redirects=False)
                if response.status_code < 500:
                    return True
            except requests.RequestException:
                pass
            time.sleep(0.5)
        return False
