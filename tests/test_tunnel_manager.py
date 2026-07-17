from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from network_launcher.tunnel_manager import TunnelManager


def test_agent_api_selects_only_current_proxy_port():
    response = MagicMock()
    response.json.return_value = {
        "tunnels": [
            {
                "public_url": "https://stale.ngrok.app",
                "config": {"addr": "http://localhost:9000"},
            },
            {
                "public_url": "https://current.ngrok.app",
                "config": {"addr": "localhost:18080"},
            },
        ]
    }
    with patch("network_launcher.tunnel_manager.requests.get", return_value=response):
        assert TunnelManager()._fetch_public_url(18080) == "https://current.ngrok.app"


def test_agent_api_does_not_return_stale_tunnel():
    response = MagicMock()
    response.json.return_value = {
        "tunnels": [
            {
                "public_url": "https://stale.ngrok.app",
                "config": {"addr": "localhost:9000"},
            }
        ]
    }
    with patch("network_launcher.tunnel_manager.requests.get", return_value=response):
        assert TunnelManager()._fetch_public_url(18080) is None


def test_ngrok_errors_are_actionable():
    blocked = TunnelManager._friendly_ngrok_error("ERROR ERR_NGROK_9040")
    auth = TunnelManager._friendly_ngrok_error("authentication failed: missing authtoken")
    assert "VPN" in blocked and "ERR_NGROK_9040" in blocked
    assert "add-authtoken" in auth


def test_auth_status_is_green_only_for_valid_config():
    config_path = Path(__file__).parent / "fixtures" / "ngrok_config_valid.yml"
    completed = MagicMock(returncode=0, stdout="Valid configuration", stderr="")
    with patch.dict(os.environ, {"NGROK_AUTHTOKEN": ""}), patch("network_launcher.tunnel_manager.resolve_ngrok_binary", return_value="ngrok"), patch(
        "network_launcher.tunnel_manager.default_ngrok_config_path",
        return_value=str(config_path),
    ), patch("network_launcher.tunnel_manager.subprocess.run", return_value=completed) as run:
        result = TunnelManager().check_auth_status()

    assert result["configured"] is True
    assert run.call_args.args[0] == ["ngrok", "config", "check"]


def test_missing_auth_token_is_reported_without_running_cli():
    config_path = Path(__file__).parent / "fixtures" / "ngrok_config_missing.yml"
    with patch.dict(os.environ, {"NGROK_AUTHTOKEN": ""}), patch("network_launcher.tunnel_manager.resolve_ngrok_binary", return_value="ngrok"), patch(
        "network_launcher.tunnel_manager.default_ngrok_config_path",
        return_value=str(config_path),
    ), patch("network_launcher.tunnel_manager.subprocess.run") as run:
        result = TunnelManager().check_auth_status()

    assert result["configured"] is False
    assert "не настроен" in result["message"].lower()
    run.assert_not_called()


def test_save_authtoken_never_returns_the_secret():
    secret = "top-secret-authtoken"
    completed = MagicMock(returncode=0, stdout="saved", stderr="")
    manager = TunnelManager()
    with patch("network_launcher.tunnel_manager.ensure_ngrok", return_value="ngrok"), patch(
        "network_launcher.tunnel_manager.subprocess.run", return_value=completed
    ) as run, patch.object(
        manager,
        "check_auth_status",
        return_value={"ok": True, "configured": True, "message": "Токен настроен"},
    ):
        result = manager.save_authtoken(secret)

    assert run.call_args.args[0] == ["ngrok", "config", "add-authtoken", secret]
    assert secret not in str(result)
    assert result["configured"] is True
