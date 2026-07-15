from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from network_launcher import config
from network_launcher.docker_manager import DockerManager
from network_launcher.publish_profile import (
    PublishProfile,
    detect_dev_project,
    find_loopback_browser_urls,
    profile_from_config,
    save_profile_to_config,
)


class ProfileTests(unittest.TestCase):
    def test_profile_round_trip_and_project_key(self):
        data = {"projects": {}}
        profile = PublishProfile.from_dict(
            {
                "frontend": "web",
                "backend": "5050",
                "backend_prefixes": ["api", "/socket.io/"],
                "dev_compatibility": "on",
                "preserve_host": "off",
                "public_url_env_names": ["NEXTAUTH_URL", "APP_URL"],
            }
        )
        save_profile_to_config(data, ".", profile)
        loaded = profile_from_config(data, ".")
        self.assertEqual(loaded.frontend, "web")
        self.assertEqual(loaded.backend, 5050)
        self.assertEqual(loaded.backend_prefixes, ["/api", "/socket.io"])

    def test_config_v1_migration(self):
        content = json.dumps({"project_path": "demo", "port": 9000})
        with patch("builtins.open", mock_open(read_data=content)):
            loaded = config.load_config()
        self.assertEqual(loaded["config_version"], 2)
        self.assertEqual(loaded["project_path"], "demo")
        self.assertEqual(loaded["port"], 9000)
        self.assertEqual(loaded["projects"], {})

    def test_dev_detection_and_loopback_preflight(self):
        root = Path(__file__).parent / "fixtures" / "dev_project"
        self.assertTrue(detect_dev_project(str(root)))
        findings = find_loopback_browser_urls(str(root))
        self.assertEqual(findings[0]["file"], os.path.join("src", "client.ts"))

    def test_runtime_override_is_outside_project_and_removed(self):
        project = str(Path(__file__).parent / "fixtures" / "dev_project")
        manager = DockerManager(project)
        fake = MagicMock()
        fake.name = os.path.join(os.path.dirname(project), "runtime-override.yml")
        with patch("network_launcher.docker_manager.tempfile.NamedTemporaryFile", return_value=fake):
            path = manager._write_runtime_override("app", {"NEXTAUTH_URL": "https://public"})
        self.assertNotEqual(os.path.dirname(path), os.path.realpath(project))
        manager._runtime_override_path = path
        with patch("network_launcher.docker_manager.os.remove") as remove:
            manager.cleanup_runtime_override()
            remove.assert_called_once_with(path)


if __name__ == "__main__":
    unittest.main()
