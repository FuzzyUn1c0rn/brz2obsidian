"""Completion intent through the non-GUI runner and real outer adapter."""

import pytest

platform_actions = pytest.importorskip("brz2obsidian_ui.platform_actions")
CompletionActions, CompletionOutcome = (
    platform_actions.CompletionActions,
    platform_actions.CompletionOutcome,
)
