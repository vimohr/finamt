"""Build the Windows x64 online installer with Python 3.11+, uv and NSIS."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import tomllib

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent


def verify_example(example: Path) -> None:
    cases = (example / "fall.json", example / "fall-vollstaendig.json")
    for file in cases:
        case = json.loads(file.read_text(encoding="utf-8"))
        for source in case["documents"].values():
            original = example / source["path"]
            if sha256(original.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError(f"The synthetic example's source hash changed: {original}")


def build(output: Path, compiler: str) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    installer = output / f"finamt-{version}-windows-x64-setup.exe"
    with TemporaryDirectory(prefix="finamt-build-", dir=output) as temp:
        staging = Path(temp)
        payload = staging / "payload"
        payload.mkdir()
        for name in (
            "pyproject.toml",
            "uv.lock",
            "README.md",
            "LICENSE",
            "MANIFEST.in",
            ".python-version",
        ):
            shutil.copy2(ROOT / name, payload / name)
        shutil.copytree(
            ROOT / "src",
            payload / "src",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
        )
        shutil.copy2(SCRIPTS / "launch.pyw", payload / "launch.pyw")
        shutil.copytree(ROOT / "examples" / "einkommensteuer-2025", payload / "beispielfall")
        verify_example(payload / "beispielfall")

        bootstrap = staging / "bootstrap"
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--no-deps",
                "--only-binary",
                ":all:",
                "--require-hashes",
                "--python",
                sys.executable,
                "--python-platform",
                "x86_64-pc-windows-msvc",
                "--target",
                str(bootstrap),
                "-r",
                str(SCRIPTS / "bootstrap-requirements.txt"),
            ],
            check=True,
        )
        shutil.copy2(next(bootstrap.rglob("uv.exe")), payload / "uv.exe")
        licenses = next(bootstrap.glob("uv-*.dist-info/licenses"))
        shutil.copytree(licenses, payload / "uv-licenses")

        digest = sha256()
        for file in sorted(path for path in payload.rglob("*") if path.is_file()):
            digest.update(file.relative_to(payload).as_posix().encode())
            digest.update(b"\0" + sha256(file.read_bytes()).digest())
        bundle = digest.hexdigest()[:16]
        switch = "/" if os.name == "nt" else "-"
        compiled = staging / installer.name
        subprocess.run(
            [
                compiler,
                f"{switch}INPUTCHARSET",
                "UTF8",
                *[
                    f"{switch}D{key}={value}"
                    for key, value in {
                        "PAYLOAD_PATTERN": payload / "*",
                        "LICENSE_FILE": payload / "LICENSE",
                        "OUTPUT": compiled,
                        "FINAMT_VERSION": version,
                        "BUNDLE_ID": bundle,
                    }.items()
                ],
                str(SCRIPTS / "finamt.nsi"),
            ],
            check=True,
        )
        compiled.replace(installer)
    checksum = sha256(installer.read_bytes()).hexdigest()
    installer.with_suffix(".exe.sha256").write_text(
        f"{checksum}  {installer.name}\n", encoding="ascii"
    )
    return installer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--makensis", default="makensis", help="Path to the NSIS compiler")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "windows")
    options = parser.parse_args()
    print(build(options.output_dir.resolve(), options.makensis))


if __name__ == "__main__":
    main()
