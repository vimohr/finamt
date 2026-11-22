"""Run a private llama.cpp instance for the installed local model."""

from __future__ import annotations

import atexit
import json
import os
import secrets
import socket
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from threading import Lock
from time import monotonic, sleep

from .model_assets import MODEL_ALIAS, MODEL_DIRECTORY_ENV, installed_paths

_HOST = "127.0.0.1"
_MAX_RESPONSE = 1_048_576
_LOCK = Lock()


@dataclass
class LocalModel:
    process: subprocess.Popen
    port: int
    key: str
    ready: bool = False

    @classmethod
    def start(cls, server: Path, model: Path) -> LocalModel:
        with socket.socket() as listener:
            listener.bind((_HOST, 0))
            port = listener.getsockname()[1]
        key = secrets.token_urlsafe(32)
        env = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith(("LLAMA_", "GGML_"))
        }
        env["LLAMA_API_KEY"] = key
        process = subprocess.Popen(
            [
                str(server),
                "--model",
                str(model),
                "--alias",
                MODEL_ALIAS,
                "--host",
                _HOST,
                "--port",
                str(port),
                "--ctx-size",
                "8192",
                "--parallel",
                "1",
                "--gpu-layers",
                "0",
                "--threads",
                str(min(os.cpu_count() or 1, 8)),
                "--no-webui",
                "--no-slots",
                "--log-disable",
            ],
            cwd=server.parent,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return cls(process, port, key)

    def wait_ready(self) -> None:
        if self.ready:
            return
        deadline = monotonic() + 90
        while self.process.poll() is None and monotonic() < deadline:
            try:
                status, response = self.request("GET", "/health", timeout=2)
                if status == 200 and response.get("status") == "ok":
                    self.ready = True
                    return
            except (OSError, HTTPException, ValueError):
                pass
            sleep(0.15)
        raise RuntimeError("Das lokale KI-Modell konnte nicht gestartet werden.")

    def request(
        self, method: str, path: str, *, timeout: int, payload: dict | None = None
    ) -> tuple[int, dict]:
        connection = HTTPConnection(_HOST, self.port, timeout=timeout)
        try:
            headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
            body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read(_MAX_RESPONSE + 1)
            if len(data) > _MAX_RESPONSE:
                raise ValueError("Local model response exceeded its size limit")
            return response.status, json.loads(data)
        finally:
            connection.close()

    def close(self) -> None:
        if self.process.poll() is not None:
            return
        with suppress(ProcessLookupError):
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)


_runtime: LocalModel | None = None


@atexit.register
def close_local_model() -> None:
    global _runtime
    with _LOCK:
        runtime, _runtime = _runtime, None
    if runtime:
        runtime.close()


def generate(
    prompt: str, *, temperature: float, top_p: float, max_tokens: int, response_schema: dict | None
) -> str:
    global _runtime
    location = os.environ.get(MODEL_DIRECTORY_ENV)
    paths = installed_paths(Path(location)) if location else None
    if paths is None:
        raise RuntimeError("Das lokale KI-Modell ist nicht vollständig installiert.")

    with _LOCK:
        if _runtime is None or _runtime.process.poll() is not None:
            _runtime = LocalModel.start(*paths)
        runtime = _runtime
    try:
        runtime.wait_ready()
    except RuntimeError:
        close_local_model()
        raise

    payload = {
        "model": MODEL_ALIAS,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "cache_prompt": False,
    }
    if response_schema is not None:
        payload["response_format"] = {"type": "json_schema", "schema": response_schema}
    code, result = runtime.request("POST", "/v1/chat/completions", timeout=180, payload=payload)
    if code != 200:
        raise RuntimeError(f"Das lokale Modell hat die Anfrage abgelehnt (HTTP {code}).")
    reply = result["choices"][0]["message"]["content"]
    if not isinstance(reply, str):
        raise ValueError("The local model did not return a text reply")
    return reply
