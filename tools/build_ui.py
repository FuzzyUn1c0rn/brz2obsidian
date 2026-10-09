"""Build the checkout-bound local Windows launcher; never install at runtime."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def build(root: Path, interpreter: Path) -> Path:
    root, interpreter = root.resolve(), interpreter.resolve()
    pythonw = interpreter.with_name("pythonw.exe")
    if not interpreter.is_file() or not pythonw.is_file():
        raise ValueError(
            "The project .venv is missing or moved. Follow README.md to create it and install the GUI dependencies, then rebuild."
        )
    if not (root / "src/brz2obsidian_ui/__main__.py").is_file():
        raise ValueError("The GUI source is missing from this checkout.")
    checked = subprocess.run(
        [
            str(interpreter),
            "-c",
            "import json,sys,struct,PySide6; from PySide6.QtCore import qVersion; print(json.dumps({'python':sys.version.split()[0],'bits':struct.calcsize('P')*8,'pyside':PySide6.__version__,'qt':qVersion()}))",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if checked.returncode:
        raise ValueError(
            "GUI dependencies are unavailable. Install requirements.txt and requirements-gui.txt in the project .venv, then rebuild."
        )
    versions = json.loads(checked.stdout)
    if (
        versions["pyside"] != "6.12.0"
        or versions["bits"] != 64
        or tuple(map(int, versions["python"].split(".")[:2])) < (3, 14)
    ):
        raise ValueError(
            "This local build requires 64-bit CPython 3.14+ and PySide6 6.12.0."
        )
    output = root / "build/ui"
    output.mkdir(parents=True, exist_ok=True)

    def batch_path(path):
        return str(path).replace("%", "%%")

    launcher = output / "Start brz2obsidian.cmd"
    launcher.write_text(
        "\n".join(
            (
                "@echo off",
                "chcp 65001 >nul",
                "setlocal",
                f'if not exist "{batch_path(pythonw)}" goto missing',
                f'if not exist "{batch_path(root / "src/brz2obsidian_ui/__main__.py")}" goto missing',
                f'set "PYTHONPATH={batch_path(root / "src")}"',
                f'start "" "{batch_path(pythonw)}" -m brz2obsidian_ui --python "{batch_path(interpreter)}" --source-root "{batch_path(root / "src")}"',
                "exit /b 0",
                ":missing",
                "echo brz2obsidian could not start: this checkout or its Python environment is missing or moved.",
                "echo Follow README.md setup instructions, then run tools\\build_ui.py again.",
                "pause",
                "exit /b 1",
                "",
            )
        ),
        encoding="utf-8",
        newline="\r\n",
    )
    (output / "runtime.json").write_text(
        json.dumps(
            {
                **versions,
                "source_root": str(root / "src"),
                "interpreter": str(interpreter),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return launcher


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python",
        type=Path,
        help="Explicit project .venv interpreter for an isolated worktree",
    )
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        launcher = build(root, options.python or root / ".venv/Scripts/python.exe")
    except (OSError, ValueError) as error:
        print(f"brz2obsidian: {error}", file=sys.stderr)
        return 1
    print(launcher)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
