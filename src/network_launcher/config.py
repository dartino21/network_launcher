"""Загрузка и сохранение настроек приложения (config.json)."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


DEFAULTS: dict[str, Any] = {
    "config_version": 2,
    "project_path": "",
    "port": 8080,
    "autostart": False,
    "projects": {},
}


def app_dir() -> str:
    """Каталог рядом с exe (PyInstaller) или с исходниками."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def data_dir() -> str:
    """Writable application data, separate from source and release files."""
    path = os.path.join(app_dir(), "data")
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def load_config() -> dict[str, Any]:
    path = config_path()
    data = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data.update(loaded)
    except (OSError, json.JSONDecodeError):
        pass
    if not isinstance(data.get("projects"), dict):
        data["projects"] = {}
    data["config_version"] = 2
    return data


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    out = dict(DEFAULTS)
    out.update(data)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
