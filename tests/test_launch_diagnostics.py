from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from network_launcher.server_manager import (
    find_project_python,
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
