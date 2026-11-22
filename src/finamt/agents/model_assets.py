"""Provision the optional, version-pinned Windows model."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

MODEL_ALIAS = "finamt-local"
MODEL_DIRECTORY_ENV = "FINAMT_LOCAL_MODEL_DIR"
MODEL_NAME = "Qwen3-4B-Instruct-2507"


@dataclass(frozen=True)
class Asset:
    filename: str
    url: str
    size: int
    digest: str


MODEL = Asset(
    "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
    "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/"
    "a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
    2_497_281_120,
    "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597",
)
WINDOWS_RUNTIME = Asset(
    "llama-b12240-bin-win-cpu-x64.zip",
    "https://github.com/ggml-org/llama.cpp/releases/download/b12240/llama-b12240-bin-win-cpu-x64.zip",
    24_931_979,
    "ecfd6e90619d44cdb417e073056e48a467086cdf756129e5d75fd50f14e424b6",
)
_RUNTIME_DIRECTORY = "llama-b12240-cpu-x64"
_SERVER_FILENAME = "llama-server.exe"
_VERIFICATION_FILE = "installierte-modellversion.txt"
_BLOCK_BYTES = 4 * 1024 * 1024


def _verification() -> str:
    return f"{MODEL.digest}\n{WINDOWS_RUNTIME.digest}\n"


def installed_paths(directory: Path) -> tuple[Path, Path] | None:
    model = directory / MODEL.filename
    server = directory / _RUNTIME_DIRECTORY / _SERVER_FILENAME
    try:
        if (
            model.is_file()
            and model.stat().st_size == MODEL.size
            and server.is_file()
            and (directory / _VERIFICATION_FILE).read_text(encoding="ascii") == _verification()
        ):
            return server, model
    except (OSError, ValueError):
        pass
    return None


def configure_installed_model(directory: Path) -> bool:
    """Enable the guide for a completed setup, preserving explicit user settings."""
    if installed_paths(directory) is None:
        return False
    os.environ.setdefault(MODEL_DIRECTORY_ENV, str(directory.resolve()))
    os.environ.setdefault("FINAMT_EST_GUIDE_MODEL", MODEL_ALIAS)
    return True


def _download(asset: Asset, destination: Path) -> None:
    """Check the byte count and SHA-256 before any downloaded asset is installed."""
    digest = sha256()
    size = 0
    last_step = 0
    request = Request(asset.url, headers={"User-Agent": "finamt-model-setup"})
    print(f"Download: {asset.filename}", flush=True)
    with urlopen(request, timeout=45) as response, destination.open("wb") as output:
        while block := response.read(_BLOCK_BYTES):
            size += len(block)
            if size > asset.size:
                raise ValueError(f"Unexpected file size for {asset.filename}")
            digest.update(block)
            output.write(block)
            step = 10 * size // asset.size
            if step > last_step:
                print(f"{asset.filename} · {step * 10} %", flush=True)
                last_step = step
    if size != asset.size or digest.hexdigest() != asset.digest:
        raise ValueError(f"Integrity check failed for {asset.filename}")


def _check_runtime(server: Path) -> None:
    result = subprocess.run(
        [str(server), "--version"],
        cwd=server.parent,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=20,
    )
    if result.returncode:
        raise RuntimeError("llama.cpp konnte auf diesem Rechner nicht gestartet werden.")


def install_default_model(directory: Path) -> None:
    directory = directory.resolve()
    if installed_paths(directory):
        print("Das lokale KI-Modell ist bereits installiert.", flush=True)
        return

    directory.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(directory).free < MODEL.size + WINDOWS_RUNTIME.size + 150_000_000:
        raise OSError("Für das Modell fehlen rund 3 GB freier Speicherplatz.")
    runtime = directory / _RUNTIME_DIRECTORY
    with TemporaryDirectory(prefix="modell-setup-", dir=directory) as temporary:
        staging = Path(temporary)
        package = staging / WINDOWS_RUNTIME.filename
        _download(WINDOWS_RUNTIME, package)
        unpacked = staging / "unpacked"
        with ZipFile(package) as archive:
            archive.extractall(unpacked)
        servers = list(unpacked.rglob(_SERVER_FILENAME))
        if len(servers) != 1:
            raise ValueError("Die Modelllaufzeit fehlt im Archiv.")
        _check_runtime(servers[0])

        model = staging / MODEL.filename
        _download(MODEL, model)
        # Only activate complete, verified installations. A concurrent setup may have finished first.
        try:
            servers[0].parent.replace(runtime)
        except OSError:
            if not (runtime / _SERVER_FILENAME).is_file():
                raise
        try:
            model.replace(directory / MODEL.filename)
        except OSError:
            if installed_paths(directory) is None:
                raise
        verified = staging / _VERIFICATION_FILE
        verified.write_text(_verification(), encoding="ascii")
        verified.replace(directory / _VERIFICATION_FILE)
    if installed_paths(directory) is None:
        raise RuntimeError("Die Modellinstallation ist unvollständig.")
    print(f"{MODEL_NAME} ist lokal installiert.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    options = parser.parse_args()
    try:
        install_default_model(options.directory)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, BadZipFile) as exc:
        print(f"KI-Modell konnte nicht eingerichtet werden. {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
