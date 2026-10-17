import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

pytestmark = pytest.mark.gui


def control(window, kind, name):
    return next(
        widget
        for widget in window.findChildren(kind)
        if widget.accessibleName() == name
    )
