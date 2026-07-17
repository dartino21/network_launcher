"""Общие параметры запуска фоновых процессов без консольных окон."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TextIO


_WINDOWED_STREAMS: list[TextIO] = []


def ensure_windowed_stdio() -> None:
    """Provide writable stdio streams for a PyInstaller ``console=False`` app."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is not None:
            continue
        stream = open(os.devnull, "w", encoding="utf-8", buffering=1)
        setattr(sys, name, stream)
        _WINDOWED_STREAMS.append(stream)


def hidden_process_kwargs() -> dict:
    """Return Windows-only flags that keep console programs invisible."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }
