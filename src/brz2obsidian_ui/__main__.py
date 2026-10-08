"""Window entrypoint; build launcher supplies absolute code/interpreter paths."""

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from brz2obsidian_ui.window import MainWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--python", type=Path, default=Path(sys.executable).with_name("python.exe")
    )
    parser.add_argument("--source-root", type=Path, default=Path(__file__).parents[1])
    options = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("brz2obsidian")
    window = MainWindow(interpreter=options.python, source_root=options.source_root)
    window.show()
    status = app.exec()
    window.shutdown()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
