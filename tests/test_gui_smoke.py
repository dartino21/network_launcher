from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QApplication, QLabel, QLineEdit, QTextBrowser

from network_launcher import gui
from network_launcher.publish_profile import PublishProfile, save_profile_to_config


class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(gui.DARK_QSS)

    def setUp(self):
        self.config = {
            "config_version": 2,
            "project_path": "",
            "port": 8080,
            "autostart": False,
            "projects": {},
        }
        self.load_patch = patch("network_launcher.gui.load_config", return_value=self.config)
        self.save_patch = patch("network_launcher.gui.save_config")
        self.web_patch = patch("network_launcher.gui.HAS_WEBENGINE", False)
        self.load_patch.start()
        self.save_patch.start()
        self.web_patch.start()
        self.window = gui.MainWindow()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.web_patch.stop()
        self.save_patch.stop()
        self.load_patch.stop()

    def test_window_has_expected_tabs_and_idle_state(self):
        self.assertEqual(self.window.main_tabs.count(), 4)
        self.assertEqual(
            [self.window.main_tabs.tabText(index) for index in range(4)],
            ["Обзор", "Предпросмотр", "Логи", "Настройки"],
        )
        self.assertFalse(self.window.start_btn.isEnabled())
        self.assertFalse(self.window.stop_btn.isEnabled())
        self.assertEqual(self.window.state_badge.property("state"), "idle")

    def test_project_profile_is_loaded_and_start_enabled(self):
        project = str(Path(__file__).parent / "fixtures" / "dev_project")
        profile = PublishProfile.from_dict(
            {
                "frontend": "web",
                "backend": "5050",
                "backend_prefixes": ["/api", "/ws"],
                "dev_compatibility": "on",
                "preserve_host": "off",
                "public_url_env_names": ["APP_URL"],
            }
        )
        save_profile_to_config(self.window._config, project, profile)

        self.window._set_project_path(project, save=False, maybe_autostart=False)

        self.assertTrue(self.window.start_btn.isEnabled())
        self.assertEqual(self.window.frontend_edit.text(), "web")
        self.assertEqual(self.window.backend_edit.text(), "5050")
        self.assertEqual(self.window.prefixes_edit.text(), "/api, /ws")
        self.assertEqual(self.window.mode_card.property("tone"), "info")

    def test_connected_and_reset_states_toggle_url_actions(self):
        url = "https://example.ngrok.app"
        self.window._set_tunnel_connected(url)

        self.assertTrue(self.window.copy_url_btn.isEnabled())
        self.assertTrue(self.window.open_url_btn.isEnabled())
        self.assertEqual(self.window._public_url, url)
        self.assertEqual(self.window.tunnel_card.property("tone"), "success")

        self.window._reset_tunnel_ui()

        self.assertFalse(self.window.copy_url_btn.isEnabled())
        self.assertFalse(self.window.open_url_btn.isEnabled())
        self.assertEqual(self.window._public_url, "")
        self.assertEqual(self.window.tunnel_card.property("tone"), "neutral")

    def test_help_button_opens_dialog(self):
        self.assertTrue(self.window.help_btn.isEnabled())

        dialog = gui.HelpDialog(self.window)
        browser = dialog.findChild(QTextBrowser, "helpBrowser")
        self.assertIsNotNone(browser)
        dialog.show()
        self.app.processEvents()
        background = browser.palette().color(QPalette.Base)
        foreground = browser.palette().color(QPalette.Text)
        self.assertGreater(foreground.lightness(), background.lightness())
        dialog.close()

    def test_start_worker_does_not_expose_unverified_url(self):
        server = MagicMock()
        tunnel = MagicMock()
        server.prepare_launch.return_value = {"ok": True, "proxy_port": 18080}
        server.start_proxy.return_value = {"ok": True}
        tunnel.start_tunnel.return_value = {
            "ok": True,
            "public_url": "https://example.ngrok.app",
        }
        server.start_prepared.return_value = {"ok": True}
        server.verify_public_url.return_value = {"public_ok": True, "status": 200}
        worker = gui.StartWorker(server, tunnel, "C:/project", 8080, PublishProfile())
        exposed = []
        finished = []
        worker.public_url_ready.connect(exposed.append)
        worker.finished_start.connect(finished.append)

        worker.run()

        self.assertEqual(exposed, [])
        self.assertTrue(finished[0]["ok"])

    def test_ngrok_token_controls_are_safe_and_colored(self):
        self.assertEqual(self.window.ngrok_token_edit.echoMode(), QLineEdit.Password)
        link = self.window.findChild(QLabel, "ngrokHelpLink")
        self.assertIsNotNone(link)
        self.assertIn("dashboard.ngrok.com", link.text())
        self.window._set_ngrok_auth_status(False, "Токен не настроен")
        self.assertEqual(self.window.ngrok_auth_status.property("state"), "missing")
        self.window._set_ngrok_auth_status(True, "Токен настроен")
        self.assertEqual(self.window.ngrok_auth_status.property("state"), "configured")

    def test_log_is_bounded(self):
        self.assertEqual(self.window.log.document().maximumBlockCount(), 3000)
        for index in range(3050):
            self.window.log.appendPlainText(str(index))
        self.assertLessEqual(self.window.log.document().blockCount(), 3000)

    def test_runtime_poll_does_not_redraw_unchanged_history(self):
        self.window._running = True
        self.window.chart.redraw = MagicMock()
        payload = {
            "ok": True,
            "public_url": "https://example.ngrok.app",
            "stats": {"current": 1, "total": 2},
            "history": [("12:00", 1)],
        }

        self.window._on_runtime_poll_ready(payload)
        self.window._on_runtime_poll_ready(payload)

        self.window.chart.redraw.assert_called_once_with([("12:00", 1)])

    def test_runtime_poll_only_schedules_background_worker(self):
        worker = MagicMock()
        worker.isRunning.return_value = False
        self.window._running = True
        with patch("network_launcher.gui.RuntimePollWorker", return_value=worker):
            self.window._poll_tunnel_stats()

        worker.start.assert_called_once_with()
        self.assertIs(self.window._poll_worker, worker)


if __name__ == "__main__":
    unittest.main()
