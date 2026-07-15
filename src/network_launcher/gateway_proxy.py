"""Единый локальный reverse proxy для frontend, backend и публичного ngrok."""

from __future__ import annotations

import asyncio
import re
import threading
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
from multidict import CIMultiDict

from .publish_profile import DEFAULT_BACKEND_PREFIXES, normalize_prefix


_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_DEV_WS_PATHS = (
    "/_next/webpack-hmr",
    "/_next/turbopack",
    "/__webpack_hmr",
    "/sockjs-node",
)
_LOOPBACK_COOKIE_DOMAIN = re.compile(
    r";\s*domain\s*=\s*(?:localhost|127\.0\.0\.1)(?=;|$)", re.IGNORECASE
)


def _is_backend_path(path: str, prefixes: Optional[list[str]] = None) -> bool:
    path_only = path.split("?", 1)[0]
    for prefix in prefixes or DEFAULT_BACKEND_PREFIXES:
        normalized = normalize_prefix(prefix)
        if not normalized:
            continue
        if path_only == normalized or path_only.startswith(normalized + "/"):
            return True
    return False


def _connection_tokens(headers) -> set[str]:
    value = headers.get("Connection", "")
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _external_scheme(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip()
    if forwarded in {"http", "https"}:
        return forwarded
    host = request.headers.get("Host", "").lower()
    if host.endswith(".ngrok-free.dev") or host.endswith(".ngrok.app"):
        return "https"
    return request.scheme


def _rewrite_location(value: str, request: web.Request) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return value
    external_host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host")
    if not external_host:
        return value
    return urlunsplit(
        (_external_scheme(request), external_host.split(",", 1)[0].strip(), parsed.path, parsed.query, parsed.fragment)
    )


def _rewrite_set_cookie(value: str) -> str:
    return _LOOPBACK_COOKIE_DOMAIN.sub("", value)


class GatewayProxy:
    """Потоковый HTTP/WebSocket proxy, слушающий только loopback-интерфейс."""

    def __init__(
        self,
        frontend_port: int,
        backend_port: Optional[int],
        listen_port: int,
        backend_prefixes: Optional[list[str]] = None,
        *,
        dev_compatibility: bool = False,
        preserve_host: bool = False,
    ):
        self.frontend_port = int(frontend_port)
        self.backend_port = int(backend_port) if backend_port else None
        self.listen_port = int(listen_port)
        self.backend_prefixes = list(backend_prefixes or DEFAULT_BACKEND_PREFIXES)
        self.dev_compatibility = bool(dev_compatibility)
        self.preserve_host = bool(preserve_host)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._runner: Optional[web.AppRunner] = None
        self._session: Optional[ClientSession] = None
        self._ready = threading.Event()
        self._start_error: Optional[BaseException] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._start_error = None
        self._thread = threading.Thread(target=self._run, name="network-launcher-proxy", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise OSError("Proxy не запустился за 10 секунд")
        if self._start_error:
            raise OSError(str(self._start_error)) from self._start_error

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._async_start())
        except BaseException as exc:  # noqa: BLE001 - передаём ошибку вызывающему потоку
            self._start_error = exc
            self._ready.set()
            loop.close()
            self._loop = None
            return
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(self._async_stop())
            loop.close()
            self._loop = None

    async def _async_start(self) -> None:
        self._session = ClientSession(
            timeout=ClientTimeout(total=None, sock_connect=60, sock_read=None),
            auto_decompress=False,
        )
        app = web.Application(client_max_size=1024**3)
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.listen_port)
        await site.start()

    async def _async_stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        if self._session is not None:
            await self._session.close()
            self._session = None

    def stop(self) -> None:
        loop = self._loop
        thread = self._thread
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=10)
        self._thread = None

    def _target_port(self, path: str) -> int:
        if self.backend_port and _is_backend_path(path, self.backend_prefixes):
            return self.backend_port
        return self.frontend_port

    def _request_headers(self, request: web.Request, port: int, *, websocket: bool) -> CIMultiDict:
        skip = _HOP_HEADERS | _connection_tokens(request.headers) | {"host"}
        if websocket:
            skip |= {
                "sec-websocket-accept",
                "sec-websocket-extensions",
                "sec-websocket-key",
                "sec-websocket-protocol",
                "sec-websocket-version",
            }
        headers = CIMultiDict(
            (key, value) for key, value in request.headers.items() if key.lower() not in skip
        )
        original_host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host", "")
        upstream_name = "localhost" if self.dev_compatibility else "127.0.0.1"
        upstream_host = f"{upstream_name}:{port}"
        headers["Host"] = original_host if self.preserve_host and original_host else upstream_host
        if original_host:
            headers["X-Forwarded-Host"] = original_host.split(",", 1)[0].strip()
        headers["X-Forwarded-Proto"] = _external_scheme(request)
        headers["X-Forwarded-Port"] = "443" if headers["X-Forwarded-Proto"] == "https" else "80"
        remote = request.remote or "127.0.0.1"
        previous = request.headers.get("X-Forwarded-For", "").strip()
        headers["X-Forwarded-For"] = f"{previous}, {remote}" if previous else remote
        if original_host:
            headers["Forwarded"] = (
                f'for="{remote}";proto={headers["X-Forwarded-Proto"]};host="{original_host}"'
            )
        return headers

    def _is_dev_websocket(self, request: web.Request, protocols: list[str]) -> bool:
        if not self.dev_compatibility:
            return False
        path = request.path
        return (
            any(path == prefix or path.startswith(prefix + "/") for prefix in _DEV_WS_PATHS)
            or "vite-hmr" in protocols
            or request.query.get("transport") == "websocket" and path.startswith("/_next")
        )

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._handle_websocket(request)
        return await self._handle_http(request)

    async def _handle_http(self, request: web.Request) -> web.StreamResponse:
        assert self._session is not None
        port = self._target_port(request.path)
        target = f"http://127.0.0.1:{port}{request.rel_url}"
        headers = self._request_headers(request, port, websocket=False)
        body = request.content.iter_chunked(64 * 1024) if request.can_read_body else None
        try:
            async with self._session.request(
                request.method,
                target,
                headers=headers,
                data=body,
                allow_redirects=False,
            ) as upstream:
                out_headers = CIMultiDict()
                skip = _HOP_HEADERS | _connection_tokens(upstream.headers)
                for key, value in upstream.headers.items():
                    low = key.lower()
                    if low in skip or low == "set-cookie":
                        continue
                    if low == "location":
                        value = _rewrite_location(value, request)
                    out_headers.add(key, value)
                for value in upstream.headers.getall("Set-Cookie", []):
                    out_headers.add("Set-Cookie", _rewrite_set_cookie(value))
                response = web.StreamResponse(
                    status=upstream.status,
                    reason=upstream.reason,
                    headers=out_headers,
                )
                await response.prepare(request)
                if request.method != "HEAD":
                    async for chunk in upstream.content.iter_chunked(64 * 1024):
                        await response.write(chunk)
                await response.write_eof()
                return response
        except (OSError, asyncio.TimeoutError) as exc:
            return web.Response(
                status=502,
                text=f"Gateway proxy error -> 127.0.0.1:{port}: {exc}",
                content_type="text/plain",
                charset="utf-8",
            )

    async def _handle_websocket(self, request: web.Request) -> web.StreamResponse:
        assert self._session is not None
        port = self._target_port(request.path)
        target = f"ws://127.0.0.1:{port}{request.rel_url}"
        protocols = [
            item.strip()
            for item in request.headers.get("Sec-WebSocket-Protocol", "").split(",")
            if item.strip()
        ]
        headers = self._request_headers(request, port, websocket=True)
        origin = headers.pop("Origin", None)
        if self._is_dev_websocket(request, protocols):
            origin = f"http://localhost:{port}"
            headers["X-Network-Launcher-Original-Origin"] = request.headers.get("Origin", "")
        try:
            upstream = await self._session.ws_connect(
                target,
                headers=headers,
                protocols=protocols,
                origin=origin,
                autoping=True,
                autoclose=True,
                max_msg_size=0,
            )
        except Exception as exc:  # noqa: BLE001 - превращаем handshake в понятный 502
            return web.Response(
                status=502,
                text=f"WebSocket proxy error -> 127.0.0.1:{port}: {exc}",
                content_type="text/plain",
                charset="utf-8",
            )

        downstream = web.WebSocketResponse(
            protocols=[upstream.protocol] if upstream.protocol else [],
            autoping=True,
            autoclose=True,
            max_msg_size=0,
        )
        await downstream.prepare(request)

        async def relay(source, destination) -> None:
            async for message in source:
                if message.type == WSMsgType.TEXT:
                    await destination.send_str(message.data)
                elif message.type == WSMsgType.BINARY:
                    await destination.send_bytes(message.data)
                elif message.type == WSMsgType.PING:
                    await destination.ping(message.data)
                elif message.type == WSMsgType.PONG:
                    await destination.pong(message.data)
                elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                    break

        tasks = {
            asyncio.create_task(relay(downstream, upstream)),
            asyncio.create_task(relay(upstream, downstream)),
        }
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)
        await upstream.close()
        await downstream.close()
        return downstream

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.listen_port}"


def detect_existing_gateway_port(services: dict) -> Optional[int]:
    for name, info in services.items():
        role = info.get("role") or ""
        low = name.lower()
        if role == "gateway" or any(hint in low for hint in ("gateway", "traefik", "caddy", "edge")):
            ports = info.get("ports") or []
            if ports:
                return ports[0]
    return None
