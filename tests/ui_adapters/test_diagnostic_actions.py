"""Diagnostic file adapters at the real filesystem boundary."""

import pytest

DiagnosticActions = pytest.importorskip(
    "brz2obsidian_ui.platform_actions"
).DiagnosticActions
