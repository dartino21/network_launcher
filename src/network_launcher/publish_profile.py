"""Настройки публикации проекта и безопасная preflight-диагностика."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


DEFAULT_BACKEND_PREFIXES = ["/api", "/health", "/ws", "/socket.io", "/graphql"]
DEFAULT_PUBLIC_URL_ENVS = ["NEXTAUTH_URL", "AUTH_URL"]
_BROWSER_EXTENSIONS = {".html", ".js", ".jsx", ".mjs", ".ts", ".tsx", ".vue", ".svelte"}
_SKIP_DIRS = {
    ".git",
    ".next",
    ".npm-cache",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "vendor",
    "__pycache__",
}
_LOOPBACK_URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?", re.IGNORECASE)


def _selection(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, int):
        return value if 0 < value <= 65535 else default
    text = str(value).strip()
    if not text:
        return default
    if text.isdigit():
        port = int(text)
        return port if 0 < port <= 65535 else default
    return text


def normalize_prefix(value: str) -> Optional[str]:
    value = (value or "").strip()
    if not value:
        return None
    if not value.startswith("/"):
        value = "/" + value
    if len(value) > 1:
        value = value.rstrip("/")
    return value


@dataclass(slots=True)
class PublishProfile:
    frontend: int | str = "auto"
    backend: int | str | None = "auto"
    backend_prefixes: list[str] = field(default_factory=lambda: list(DEFAULT_BACKEND_PREFIXES))
    dev_compatibility: str = "auto"
    preserve_host: str = "auto"
    public_url_env_names: list[str] = field(default_factory=lambda: list(DEFAULT_PUBLIC_URL_ENVS))

    @classmethod
    def from_dict(cls, raw: Optional[dict[str, Any]]) -> "PublishProfile":
        raw = raw or {}
        prefixes = []
        for item in raw.get("backend_prefixes") or DEFAULT_BACKEND_PREFIXES:
            prefix = normalize_prefix(str(item))
            if prefix and prefix not in prefixes:
                prefixes.append(prefix)
        env_names = []
        for item in raw.get("public_url_env_names") or DEFAULT_PUBLIC_URL_ENVS:
            name = str(item).strip()
            if name and name.replace("_", "").isalnum() and name not in env_names:
                env_names.append(name)
        dev = str(raw.get("dev_compatibility", "auto")).lower()
        preserve = str(raw.get("preserve_host", "auto")).lower()
        return cls(
            frontend=_selection(raw.get("frontend"), "auto"),
            backend=_selection(raw.get("backend"), "auto"),
            backend_prefixes=prefixes or list(DEFAULT_BACKEND_PREFIXES),
            dev_compatibility=dev if dev in {"auto", "on", "off"} else "auto",
            preserve_host=preserve if preserve in {"auto", "on", "off"} else "auto",
            public_url_env_names=env_names,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def project_key(project_path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(project_path)))


def profile_from_config(config: dict[str, Any], project_path: str) -> PublishProfile:
    projects = config.get("projects")
    raw = projects.get(project_key(project_path), {}) if isinstance(projects, dict) else {}
    return PublishProfile.from_dict(raw if isinstance(raw, dict) else {})


def save_profile_to_config(
    config: dict[str, Any], project_path: str, profile: PublishProfile
) -> None:
    projects = config.setdefault("projects", {})
    if not isinstance(projects, dict):
        projects = {}
        config["projects"] = projects
    projects[project_key(project_path)] = profile.to_dict()


def detect_dev_project(project_path: str, compose_data: Optional[dict[str, Any]] = None) -> bool:
    """Определяет dev-серверы, которым нужна нормализация HMR Origin."""
    package_path = Path(project_path) / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        package = {}
    deps: dict[str, Any] = {}
    for key in ("dependencies", "devDependencies"):
        value = package.get(key)
        if isinstance(value, dict):
            deps.update(value)
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    script_text = " ".join(str(value).lower() for value in scripts.values())
    if any(name in deps for name in ("next", "vite", "webpack", "react-scripts")):
        if any(token in script_text for token in ("next dev", "vite", "webpack serve", "react-scripts start")):
            return True
    if compose_data:
        services = compose_data.get("services") or {}
        for cfg in services.values():
            if not isinstance(cfg, dict):
                continue
            command = cfg.get("command", "")
            if isinstance(command, list):
                command = " ".join(str(x) for x in command)
            low = str(command).lower()
            if any(token in low for token in ("next dev", "vite", "webpack serve", "react-scripts start", "npm run dev")):
                return True
    return False


def resolve_toggle(value: str, auto_value: bool) -> bool:
    if value == "on":
        return True
    if value == "off":
        return False
    return auto_value


def find_loopback_browser_urls(
    project_path: str,
    limit: int = 10,
    timeout: float = 2.0,
) -> list[dict[str, Any]]:
    """Ищет browser-side абсолютные loopback URL, не читая зависимости и секреты."""
    root = Path(project_path)
    findings: list[dict[str, Any]] = []
    deadline = time.monotonic() + max(0.0, timeout)
    try:
        for current_dir, directories, files in os.walk(root):
            directories[:] = [name for name in directories if name not in _SKIP_DIRS]
            if time.monotonic() >= deadline:
                break
            for name in files:
                if len(findings) >= limit or time.monotonic() >= deadline:
                    return findings
                path = Path(current_dir, name)
                if path.suffix.lower() not in _BROWSER_EXTENSIONS:
                    continue
                try:
                    if path.stat().st_size > 1_000_000:
                        continue
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for line_no, line in enumerate(text.splitlines(), 1):
                    match = _LOOPBACK_URL_RE.search(line)
                    if match:
                        findings.append(
                            {
                                "file": os.path.relpath(path, root),
                                "line": line_no,
                                "url": match.group(0),
                            }
                        )
                        break
    except OSError:
        return findings
    return findings
