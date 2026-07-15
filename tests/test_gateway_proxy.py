from __future__ import annotations

import asyncio
import socket
import threading
import unittest

import requests
from aiohttp import ClientSession, WSMsgType, web

from network_launcher.gateway_proxy import GatewayProxy, _is_backend_path


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ThreadedUpstream:
    def __init__(self, name: str):
        self.name = name
        self.port = free_port()
        self.loop = None
        self.thread = None
        self.ready = threading.Event()
        self.runner = None
        self.last_ws_headers = {}

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError("upstream did not start")

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start())
        self.ready.set()
        try:
            self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self.runner.cleanup())
            self.loop.close()

    async def _start(self):
        app = web.Application(client_max_size=16 * 1024**2)

        async def handler(request: web.Request):
            if request.path == "/redirect":
                response = web.Response(status=302)
                response.headers["Location"] = f"http://localhost:{self.port}/final"
                response.headers.add("Set-Cookie", "session=ok; Domain=localhost; Path=/; HttpOnly")
                return response
            if request.path == "/stream":
                response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
                await response.prepare(request)
                await response.write(b"data: one\n\n")
                await response.write(b"data: two\n\n")
                await response.write_eof()
                return response
            body = await request.read()
            return web.json_response(
                {
                    "upstream": self.name,
                    "method": request.method,
                    "body_length": len(body),
                    "host": request.headers.get("Host"),
                    "forwarded_host": request.headers.get("X-Forwarded-Host"),
                    "forwarded_proto": request.headers.get("X-Forwarded-Proto"),
                    "origin": request.headers.get("Origin"),
                }
            )

        async def websocket_handler(request: web.Request):
            self.last_ws_headers = dict(request.headers)
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    await ws.send_str(f"{self.name}:{message.data}")
                elif message.type == WSMsgType.BINARY:
                    await ws.send_bytes(message.data[::-1])
            return ws

        app.router.add_get("/ws", websocket_handler)
        app.router.add_get("/_next/webpack-hmr", websocket_handler)
        app.router.add_route("*", "/{tail:.*}", handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, "127.0.0.1", self.port).start()

    def stop(self):
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread:
            self.thread.join(5)


class GatewayProxyIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frontend = ThreadedUpstream("frontend")
        cls.backend = ThreadedUpstream("backend")
        cls.frontend.start()
        cls.backend.start()

    @classmethod
    def tearDownClass(cls):
        cls.frontend.stop()
        cls.backend.stop()

    def setUp(self):
        self.proxy = GatewayProxy(
            self.frontend.port,
            self.backend.port,
            free_port(),
            ["/api", "/ws"],
            dev_compatibility=True,
        )
        self.proxy.start()

    def tearDown(self):
        self.proxy.stop()

    def test_route_and_forwarded_headers(self):
        frontend = requests.get(f"{self.proxy.url}/page", timeout=5).json()
        backend = requests.get(
            f"{self.proxy.url}/api/check",
            headers={
                "Host": "example.ngrok-free.dev",
                "Origin": "https://example.ngrok-free.dev",
                "X-Forwarded-Proto": "https",
            },
            timeout=5,
        ).json()
        self.assertEqual(frontend["upstream"], "frontend")
        self.assertEqual(backend["upstream"], "backend")
        self.assertEqual(backend["host"], f"localhost:{self.backend.port}")
        self.assertEqual(backend["forwarded_host"], "example.ngrok-free.dev")
        self.assertEqual(backend["forwarded_proto"], "https")
        self.assertEqual(backend["origin"], "https://example.ngrok-free.dev")

    def test_large_multipart_and_http_methods(self):
        payload = b"x" * (2 * 1024 * 1024)
        response = requests.post(
            f"{self.proxy.url}/api/upload",
            files={"file": ("large.bin", payload)},
            timeout=15,
        ).json()
        self.assertEqual(response["upstream"], "backend")
        self.assertGreater(response["body_length"], len(payload))
        for method in ("put", "patch", "delete"):
            response = getattr(requests, method)(f"{self.proxy.url}/api/item", data=b"ok", timeout=5)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["method"], method.upper())

    def test_stream_redirect_and_cookie_rewrite(self):
        streamed = requests.get(f"{self.proxy.url}/stream", stream=True, timeout=5)
        self.assertEqual(streamed.headers["Content-Type"], "text/event-stream")
        self.assertEqual(b"".join(streamed.iter_content()), b"data: one\n\ndata: two\n\n")
        redirected = requests.get(
            f"{self.proxy.url}/redirect",
            headers={"Host": "public.example", "X-Forwarded-Proto": "https"},
            allow_redirects=False,
            timeout=5,
        )
        self.assertEqual(redirected.headers["Location"], "https://public.example/final")
        self.assertNotIn("Domain=localhost", redirected.headers["Set-Cookie"])

    def test_websocket_text_and_binary(self):
        async def scenario():
            async with ClientSession() as session:
                async with session.ws_connect(f"{self.proxy.url.replace('http', 'ws', 1)}/ws") as ws:
                    await ws.send_str("hello")
                    text = await ws.receive(timeout=5)
                    self.assertEqual(text.data, "backend:hello")
                    await ws.send_bytes(b"abc")
                    binary = await ws.receive(timeout=5)
                    self.assertEqual(binary.data, b"cba")

                async with session.ws_connect(
                    f"{self.proxy.url.replace('http', 'ws', 1)}/_next/webpack-hmr",
                    origin="https://example.ngrok-free.dev",
                ) as ws:
                    await ws.send_str("hmr")
                    echoed = await ws.receive(timeout=5)
                    self.assertEqual(echoed.data, "frontend:hmr")

        asyncio.run(scenario())
        self.assertEqual(
            self.frontend.last_ws_headers.get("Origin"),
            f"http://localhost:{self.frontend.port}",
        )
        self.assertEqual(
            self.frontend.last_ws_headers.get("Host"),
            f"localhost:{self.frontend.port}",
        )

    def test_custom_backend_prefix(self):
        self.assertTrue(_is_backend_path("/custom/a", ["/custom"]))
        self.assertFalse(_is_backend_path("/api/a", ["/custom"]))
