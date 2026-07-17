from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from network_launcher.server_manager import (
    ServerManager,
    find_project_python,
    is_ready_http_status,
    launch_prerequisite_error,
)


PROJECT = "C:/demo-project"


def test_node_missing_npm_has_actionable_message():
    with patch("network_launcher.server_manager.shutil.which", return_value=None):
        error = launch_prerequisite_error(PROJECT, "node")
    assert error is not None
    assert "Node.js/npm" in error


def test_flask_prefers_project_virtual_environment():
    expected = os.path.join(PROJECT, ".venv", "Scripts", "python.exe")
    with patch("network_launcher.server_manager.os.path.isfile", side_effect=lambda path: path == expected):
        assert find_project_python(PROJECT) == expected


def test_flask_missing_package_has_actionable_message():
    with patch("network_launcher.server_manager.find_project_python", return_value="python"), patch(
        "network_launcher.server_manager.subprocess.run",
        return_value=MagicMock(returncode=1),
    ):
        error = launch_prerequisite_error(PROJECT, "flask")
    assert error is not None
    assert "Flask не установлен" in error


def test_docker_unavailable_has_actionable_message():
    with patch(
        "network_launcher.server_manager.docker_available",
        return_value=(False, "Docker Desktop не запущен"),
    ):
        error = launch_prerequisite_error(PROJECT, "docker")
    assert error == "Docker Desktop не запущен"


def _response(status: int, url: str = "http://127.0.0.1:8080") -> MagicMock:
    response = MagicMock(status_code=status, url=url)
    return response


def test_readiness_retries_404_until_200():
    manager = ServerManager()
    with patch(
        "network_launcher.server_manager.requests.get",
        side_effect=[_response(404), _response(200)],
    ), patch("network_launcher.server_manager.time.sleep"):
        result = manager._probe_http("http://127.0.0.1:8080", timeout=1)
    assert result["ok"] is True
    assert result["status"] == 200


def test_persistent_404_is_not_ready():
    manager = ServerManager()
    with patch("network_launcher.server_manager.requests.get", return_value=_response(404)), patch(
        "network_launcher.server_manager.time.sleep"
    ), patch("network_launcher.server_manager.time.time", side_effect=[0, 0, 2]):
        result = manager._probe_http("http://127.0.0.1:8080", timeout=1)
    assert result == {"ok": False, "error": "HTTP 404"}


def test_ready_status_policy_and_public_check_header():
    assert is_ready_http_status(200)
    assert is_ready_http_status(302)
    assert is_ready_http_status(401)
    assert is_ready_http_status(403)
    assert not is_ready_http_status(404)
    assert not is_ready_http_status(502)

    manager = ServerManager()
    with patch("network_launcher.server_manager.requests.get", return_value=_response(200)) as get:
        result = manager.verify_public_url("https://demo.ngrok.app", timeout=1)
    assert result["public_ok"] is True
    assert get.call_args.kwargs["headers"] == {"ngrok-skip-browser-warning": "1"}
