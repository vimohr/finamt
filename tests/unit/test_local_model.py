from __future__ import annotations

import json
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from finamt.agents import llm_backend, local_llama, model_assets


def asset(file: Path, data: bytes | None = None) -> model_assets.Asset:
    content = file.read_bytes() if data is None else data
    return model_assets.Asset(file.name, file.as_uri(), len(content), sha256(content).hexdigest())


def test_optional_setup_only_activates_verified_files_and_can_retry(tmp_path, monkeypatch):
    directory = tmp_path / "installed"
    model = tmp_path / "model.gguf"
    expected = b"test-model"
    model.write_bytes(b"bad-model!")
    runtime = tmp_path / "runtime.zip"
    with ZipFile(runtime, "w") as bundle:
        bundle.writestr("runtime/llama-server.exe", b"synthetic executable")
        bundle.writestr("runtime/llama.dll", b"synthetic library")

    monkeypatch.setattr(model_assets, "MODEL", asset(model, expected))
    monkeypatch.setattr(model_assets, "WINDOWS_RUNTIME", asset(runtime))
    monkeypatch.setattr(model_assets, "_check_runtime", Mock())
    monkeypatch.delenv(model_assets.MODEL_DIRECTORY_ENV, raising=False)
    monkeypatch.delenv("FINAMT_EST_GUIDE_MODEL", raising=False)
    assert not model_assets.configure_installed_model(directory)

    with pytest.raises(ValueError, match="Integrity check failed"):
        model_assets.install_default_model(directory)
    assert model_assets.installed_paths(directory) is None
    assert not list(directory.iterdir())

    model.write_bytes(expected)
    model_assets.install_default_model(directory)
    server, installed_model = model_assets.installed_paths(directory)
    assert installed_model.read_bytes() == expected
    assert server.with_name("llama.dll").is_file()
    assert model_assets.configure_installed_model(directory)

    model.unlink()
    model_assets.install_default_model(directory)
    assert model_assets.installed_paths(directory) == (server, installed_model)

    monkeypatch.setenv("FINAMT_EST_GUIDE_MODEL", "custom-model")
    assert model_assets.configure_installed_model(directory)
    assert model_assets.os.environ["FINAMT_EST_GUIDE_MODEL"] == "custom-model"


def test_installed_alias_uses_local_auth_and_requests_json(monkeypatch, tmp_path):
    class Endpoint(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            exchanges.append((self.path, self.headers.get("Authorization"), payload))
            response = json.dumps(
                {"choices": [{"message": {"content": '{"betrag":"18.35"}'}}]}
            ).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(response)

    exchanges = []
    with ThreadingHTTPServer(("127.0.0.1", 0), Endpoint) as server:
        worker = Thread(target=server.serve_forever)
        worker.start()
        try:
            process = Mock()
            process.poll.return_value = None
            runtime = local_llama.LocalModel(
                process, server.server_port, "test-local-key", ready=True
            )
            monkeypatch.setattr(local_llama, "_runtime", runtime)
            monkeypatch.setattr(local_llama, "installed_paths", lambda _: (tmp_path, tmp_path))
            monkeypatch.setenv(model_assets.MODEL_DIRECTORY_ENV, str(tmp_path))
            raw = llm_backend.generate(
                "Fiktiver Beleg", "finamt-local", max_tokens=32, json_object=True
            )
            assert json.loads(raw) == {"betrag": "18.35"}
            [(path, authorization, payload)] = exchanges
            assert path == "/v1/chat/completions"
            assert authorization == "Bearer test-local-key"
            assert payload["response_format"] == {"type": "json_object"}
            assert payload["cache_prompt"] is False
            local_llama.close_local_model()
            process.terminate.assert_called_once()
        finally:
            server.shutdown()
            worker.join(timeout=3)
