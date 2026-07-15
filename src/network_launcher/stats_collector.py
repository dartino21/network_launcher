"""Сбор статистики посещений через локальный API ngrok."""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from .tunnel_manager import NGROK_API

WINDOW = timedelta(minutes=5)


def _parse_request_time(raw) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # ngrok sometimes uses unix seconds/ms
        ts = float(raw)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(raw, str):
        text = raw.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


class StatsCollector:
    def __init__(self):
        self._session_ips: set[str] = set()
        self._current_visitors = 0
        self._history: list[tuple[str, int]] = []
        self._started_at: Optional[datetime] = None
        self._local_url = ""
        self._public_url = ""
        self._project_path = ""

    def set_session_meta(
        self,
        project_path: str = "",
        local_url: str = "",
        public_url: str = "",
    ) -> None:
        self._project_path = project_path
        self._local_url = local_url
        self._public_url = public_url
        if self._started_at is None:
            self._started_at = datetime.now()

    def update_stats(self) -> dict:
        now = datetime.now(timezone.utc)
        cutoff = now - WINDOW
        current_ips: set[str] = set()

        try:
            resp = requests.get(f"{NGROK_API}/requests/http", timeout=2)
            resp.raise_for_status()
            requests_list = resp.json().get("requests", [])
        except requests.RequestException:
            requests_list = []

        for req in requests_list:
            ip = req.get("client_ip")
            if not ip:
                continue
            when = _parse_request_time(req.get("start") or req.get("time"))
            if when is None or when >= cutoff:
                current_ips.add(ip)
                self._session_ips.add(ip)

        self._current_visitors = len(current_ips)
        label = datetime.now().strftime("%H:%M")
        # ponytail: one point per poll; merge same minute
        if self._history and self._history[-1][0] == label:
            self._history[-1] = (label, self._current_visitors)
        else:
            self._history.append((label, self._current_visitors))

        return {
            "current": self._current_visitors,
            "total": len(self._session_ips),
            "history": list(self._history),
        }

    def get_current_visitors(self) -> int:
        return self._current_visitors

    def get_total_visitors(self) -> int:
        return len(self._session_ips)

    def history_for_chart(self) -> list[tuple[str, int]]:
        return list(self._history)

    def generate_report(self, path: str) -> str:
        started = (
            self._started_at.strftime("%Y-%m-%d %H:%M:%S")
            if self._started_at
            else "—"
        )
        rows = "".join(
            f"<tr><td>{html.escape(t)}</td><td>{n}</td></tr>"
            for t, n in self._history
        ) or "<tr><td colspan='2'>Нет данных</td></tr>"

        body = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <title>Network Launcher — отчёт сессии</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; background:#1e1e1e; color:#e0e0e0; padding:24px; }}
    a {{ color:#64b5f6; }}
    table {{ border-collapse: collapse; margin-top:16px; }}
    th, td {{ border:1px solid #555; padding:6px 12px; text-align:left; }}
  </style>
</head>
<body>
  <h1>Отчёт сессии</h1>
  <p>Начало: {html.escape(started)}</p>
  <p>Проект: {html.escape(self._project_path or "—")}</p>
  <p>Локальный URL: {html.escape(self._local_url or "—")}</p>
  <p>Публичный URL: <a href="{html.escape(self._public_url)}">{html.escape(self._public_url or "—")}</a></p>
  <p>Сейчас (5 мин): {self.get_current_visitors()}</p>
  <p>Всего за сессию: {self.get_total_visitors()}</p>
  <h2>История</h2>
  <table>
    <tr><th>Время</th><th>Посетители</th></tr>
    {rows}
  </table>
</body>
</html>
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        return path

    def reset(self) -> None:
        self._session_ips.clear()
        self._current_visitors = 0
        self._history.clear()
        self._started_at = None
        self._local_url = ""
        self._public_url = ""
        self._project_path = ""
