from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from network_launcher.publish_profile import PublishProfile
from network_launcher.server_manager import (
    STATIC_READY_TIMEOUT,
    ServerManager,
    find_free_port,
)


STATIC_PROJECT = Path(__file__).parent / "fixtures" / "static_project"


def _start_static_server() -> tuple[ServerManager, str, int]:
    manager = ServerManager()
    port = find_free_port(28080)
    manager._start_spa(str(STATIC_PROJECT), port)
    return manager, f"http://127.0.0.1:{port}", port


def test_static_server_works_without_console_streams(monkeypatch):
    manager, url, _ = _start_static_server()
    try:
        with monkeypatch.context() as context:
            context.setattr(sys, "stdout", None)
            context.setattr(sys, "stderr", None)
            response = requests.get(url + "/", timeout=3)
        assert response.status_code == 200
        assert "Static project works" in response.text
    finally:
        manager.stop_server()


def test_static_server_serves_assets_spa_routes_and_real_404():
    manager, url, _ = _start_static_server()
    try:
        css = requests.get(url + "/css/style.css", timeout=3)
        script = requests.get(url + "/js/app.js", timeout=3)
        nested = requests.get(url + "/assets/data/info.json", timeout=3)
        spa = requests.get(url + "/projects/demo", timeout=3)
        missing_asset = requests.get(url + "/js/missing.js", timeout=3)

        assert css.status_code == 200
        assert "rgb(20, 30, 40)" in css.text
        assert script.status_code == 200
        assert "staticFixture" in script.text
        assert nested.status_code == 200
        assert nested.json() == {"status": "ready"}
        assert spa.status_code == 200
        assert "Static project works" in spa.text
        assert missing_asset.status_code == 404
        assert "Static project works" not in missing_asset.text
    finally:
        manager.stop_server()


def test_stopping_static_server_releases_port():
    manager, _, port = _start_static_server()
    assert manager._http_thread is not None and manager._http_thread.is_alive()

    manager.stop_server()

    assert manager._http_thread is None
    assert find_free_port(port) == port


def test_static_readiness_has_short_timeout_and_actionable_error():
    manager = ServerManager()
    manager._gateway = MagicMock()
    plan = {
        "type": "static",
        "project_path": str(STATIC_PROJECT),
        "frontend_port": 28080,
        "proxy_port": 28081,
        "profile": PublishProfile(),
    }
    with patch.object(
        manager,
        "_start_local_project",
        return_value="SPA http://127.0.0.1:28080",
    ), patch.object(
        manager,
        "_probe_http",
        return_value={"ok": False, "error": "connection closed"},
    ) as probe:
        result = manager.start_prepared(plan, "https://example.ngrok.app")

    assert result["ok"] is False
    assert "Встроенный static-сервер" in result["error"]
    assert f"за {STATIC_READY_TIMEOUT} с" in result["error"]
    assert probe.call_args.kwargs["timeout"] == STATIC_READY_TIMEOUT
