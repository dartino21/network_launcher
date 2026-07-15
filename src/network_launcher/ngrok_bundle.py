"""Локальный ngrok в bin/: автоскачивание без системной установки."""

from __future__ import annotations

import io
import os
import platform
import stat
import sys
import zipfile
from typing import Optional

import requests

from .config import app_dir

# Официальный CDN ngrok v3 stable
_CDN = "https://bin.equinox.io/c/bNyj1mQVY4c"


def _platform_zip_name() -> str:
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        return "ngrok-v3-stable-windows-amd64.zip"
    if system == "Darwin":
        if machine in ("arm64", "aarch64"):
            return "ngrok-v3-stable-darwin-arm64.zip"
        return "ngrok-v3-stable-darwin-amd64.zip"
    if machine in ("arm64", "aarch64"):
        return "ngrok-v3-stable-linux-arm64.zip"
    return "ngrok-v3-stable-linux-amd64.zip"


def _binary_name() -> str:
    return "ngrok.exe" if platform.system() == "Windows" else "ngrok"


def local_ngrok_path() -> str:
    """Куда качаем/храним ngrok рядом с приложением: bin/ngrok[.exe]."""
    return os.path.join(app_dir(), "bin", _binary_name())


def _bundled_ngrok_path() -> Optional[str]:
    """Бинарник из сборки PyInstaller (sys._MEIPASS)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    path = os.path.join(meipass, "bin", _binary_name())
    return path if os.path.isfile(path) else None


def ensure_ngrok() -> str:
    """
    Гарантирует наличие ngrok.
    Порядок: уже в bin/ → из бандла PyInstaller → скачать в bin/.
    """
    path = local_ngrok_path()
    if os.path.isfile(path):
        return path

    bundled = _bundled_ngrok_path()
    if bundled:
        return bundled

    bin_dir = os.path.dirname(path)
    os.makedirs(bin_dir, exist_ok=True)

    zip_name = _platform_zip_name()
    url = f"{_CDN}/{zip_name}"
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Не удалось скачать ngrok в bin/: {exc}. Проверьте интернет."
        ) from exc

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            members = zf.namelist()
            target_names = ("ngrok.exe", "ngrok")
            member = next(
                (m for m in members if os.path.basename(m) in target_names), None
            )
            if not member:
                raise RuntimeError(f"В архиве ngrok нет бинарника: {members}")
            data = zf.read(member)
    except zipfile.BadZipFile as exc:
        raise RuntimeError("Повреждённый архив ngrok.") from exc

    with open(path, "wb") as f:
        f.write(data)

    if platform.system() != "Windows":
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return path


def resolve_prefer_local() -> Optional[str]:
    """Локальный bin/ или бандл из exe, иначе None."""
    path = local_ngrok_path()
    if os.path.isfile(path):
        return path
    return _bundled_ngrok_path()


if __name__ == "__main__":
    print(ensure_ngrok())
