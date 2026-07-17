from __future__ import annotations

import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from network_launcher.process_utils import ensure_windowed_stdio, hidden_process_kwargs
from network_launcher.server_manager import ServerManager


def test_windows_hidden_process_flags_are_configured():
    kwargs = hidden_process_kwargs()
    if os.name == "nt":
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
        assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
        assert kwargs["startupinfo"].wShowWindow == subprocess.SW_HIDE
    else:
        assert kwargs == {}


def test_windowed_build_gets_safe_writable_stdio():
    stdout = StringIO()
    stderr = StringIO()
    with patch.object(sys, "stdout", None), patch.object(sys, "stderr", None), patch(
        "network_launcher.process_utils.open",
        side_effect=[stdout, stderr],
    ):
        ensure_windowed_stdio()
        assert sys.stdout is stdout
        assert sys.stderr is stderr
        print("stdout works")
        print("stderr works", file=sys.stderr)

    assert stdout.getvalue() == "stdout works\n"
    assert stderr.getvalue() == "stderr works\n"


def test_project_process_merges_stderr_and_is_hidden():
    project_path = Path(__file__).parent / "fixtures" / "dev_project"
    process = MagicMock()
    with patch("network_launcher.server_manager.subprocess.Popen", return_value=process) as popen:
        ServerManager()._start_local_project(
            {
                "project_path": str(project_path),
                "type": "node",
                "frontend_port": 3000,
            },
            {},
        )

    kwargs = popen.call_args.kwargs
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.STDOUT
    if os.name == "nt":
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
