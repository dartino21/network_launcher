"""Ручной end-to-end smoke runner: python tests/manual_publish_smoke.py <project>."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from network_launcher.publish_profile import PublishProfile  # noqa: E402
from network_launcher.server_manager import ServerManager  # noqa: E402
from network_launcher.tunnel_manager import TunnelManager  # noqa: E402


STATE = ROOT / "data" / "runtime" / "smoke_state.json"
STOP = ROOT / "data" / "runtime" / "smoke_stop"


def write_state(**data) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> int:
    project = str(Path(sys.argv[1]).resolve())
    server = ServerManager()
    tunnel = TunnelManager()
    progress: list[str] = []

    def report(message: str) -> None:
        progress.append(message)
        write_state(stage="progress", message=message, progress=progress[-20:])

    server.set_progress(report)
    tunnel.set_progress(report)
    try:
        STOP.unlink(missing_ok=True)
        plan = server.prepare_launch(project, 8080, PublishProfile())
        if not plan.get("ok"):
            raise RuntimeError(plan.get("error"))
        proxy = server.start_proxy(plan)
        if not proxy.get("ok"):
            raise RuntimeError(proxy.get("error"))
        tunnel_result = tunnel.start_tunnel(plan["proxy_port"])
        if not tunnel_result.get("ok"):
            raise RuntimeError(tunnel_result.get("error"))
        result = server.start_prepared(plan, tunnel_result["public_url"])
        if not result.get("ok"):
            raise RuntimeError(result.get("error"))
        write_state(
            stage="ready",
            pid=None,
            local_url=result["local_url"],
            public_url=tunnel_result["public_url"],
            result=result,
            progress=progress[-20:],
        )
        while not STOP.exists():
            time.sleep(0.5)
        return 0
    except Exception as exc:  # noqa: BLE001
        write_state(stage="error", error=str(exc), progress=progress[-20:])
        return 1
    finally:
        tunnel.stop_tunnel()
        server.stop_server()


if __name__ == "__main__":
    raise SystemExit(main())
