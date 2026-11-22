"""Open the employee tax workspace in a private Windows desktop window."""

from __future__ import annotations

import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Thread
from time import monotonic, sleep

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from finamt.ui.est import router

_LOOPBACK = "127.0.0.1"
_WORKSPACE = "/einkommensteuer"
_WEBVIEW2_CLIENT = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def _workspace_app(origin: str) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[_LOOPBACK])
    app.include_router(router)

    @app.middleware("http")
    async def reject_foreign_posts(request: Request, call_next):
        if request.method == "POST" and request.headers.get("origin") != origin:
            return JSONResponse({"detail": "Die Anfrage muss aus dem finamt-Fenster kommen."}, 403)
        return await call_next(request)

    @app.get("/")
    def home():
        return RedirectResponse(_WORKSPACE)

    return app


@contextmanager
def _local_workspace() -> Iterator[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((_LOOPBACK, 0))
        port = listener.getsockname()[1]
        origin = f"http://{_LOOPBACK}:{port}"
        server = uvicorn.Server(
            uvicorn.Config(
                _workspace_app(origin),
                host=_LOOPBACK,
                port=port,
                access_log=False,
                log_level="warning",
                proxy_headers=False,
                timeout_graceful_shutdown=2,
            )
        )
        worker = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            deadline = monotonic() + 10
            while not server.started:
                if not worker.is_alive() or monotonic() >= deadline:
                    raise RuntimeError("Die lokale Fallansicht konnte nicht gestartet werden.")
                sleep(0.02)
            yield origin + _WORKSPACE
        finally:
            server.should_exit = True
            worker.join(timeout=3)


def _has_webview2() -> bool:
    import winreg

    for hive, access in (
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_READ | winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_CURRENT_USER, winreg.KEY_READ),
    ):
        try:
            with winreg.OpenKey(hive, _WEBVIEW2_CLIENT, 0, access) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return True
    return False


def launch() -> None:
    if sys.platform != "win32":
        raise RuntimeError(
            "Das Desktopfenster benötigt Windows. Die Browseransicht startet mit finamt serve."
        )
    try:
        import webview
        from webview.errors import WebViewException
    except ImportError as exc:
        raise RuntimeError(
            "Installiere die Desktop-Abhängigkeiten mit uv sync --extra windows-desktop."
        ) from exc
    if not _has_webview2():
        raise RuntimeError("Installiere die Microsoft Edge WebView2 Runtime, um finamt zu öffnen.")

    with _local_workspace() as url:
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["ALLOW_FILE_URLS"] = False
        webview.create_window(
            "finamt – Einkommensteuer",
            url,
            width=1220,
            height=875,
            min_size=(660, 540),
            text_select=True,
            zoomable=True,
        )
        try:
            webview.start(gui="edgechromium", private_mode=True)
        except WebViewException as exc:
            raise RuntimeError(
                "Das Fenster konnte nicht geöffnet werden. Prüfe die Microsoft Edge WebView2 Runtime."
            ) from exc
