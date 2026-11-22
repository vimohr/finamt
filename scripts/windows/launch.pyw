"""Start finamt from its Windows Start menu shortcut."""

import ctypes
import os
import sys
from pathlib import Path


def main():
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")

        from finamt.agents.model_assets import configure_installed_model
        from finamt.ui.desktop import launch

        configure_installed_model(Path(__file__).resolve().parents[2] / "modell")
        launch()
    except (OSError, RuntimeError) as exc:
        ctypes.windll.user32.MessageBoxW(None, str(exc), "finamt", 0x10)
        raise SystemExit(1) from exc
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(
            None,
            f"finamt konnte nicht gestartet werden. Fehler: {type(exc).__name__}",
            "finamt",
            0x10,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
