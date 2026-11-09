"""A lost locator after native capture does not erase durable history facts."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from tests.application.test_update_context import worker_context_call
from tests.application.test_update_lifecycle import (
    _changed_archive,
    _seed,
    _user_state,
    case_path,
    git,
)

__all__ = ["case_path"]


def _authored_files(vault):
    return {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
        and not {".git", ".brz2obsidian"}.intersection(path.relative_to(vault).parts)
    }


def test_lost_locator_after_capture_retains_history_and_retires_context(
    case_path, monkeypatch
):
    vault, initial = _seed(case_path, two_notes=True)
    incoming = _changed_archive(initial, case_path / "incoming.brz")
    source_hashes = tuple(
        hashlib.sha256(path.read_bytes()).hexdigest() for path in (initial, incoming)
    )
    authored_before = _authored_files(vault)
    user_before = _user_state(vault)
    config_before = (vault / ".git/config").read_bytes()
    locator = vault / ".brz2obsidian/locator.json"
    prior_locator = json.loads(locator.read_bytes())
    prior_manifest = git(
        vault, "cat-file", "blob", prior_locator["commit"] + ":manifest.json"
    )
    scratch = case_path / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    context = UpdateContext(operations=Operations())
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "vault": str(vault),
            "source": str(incoming),
            "selection_id": str(uuid4()),
            "kind": "source_update",
        },
    )
    assert opened.status == "prepared_review" and opened.binding is not None, opened
    assert opened.code == "prepared" and not opened.ready
    assert opened.binding.checkpoint_commit == prior_locator["commit"]
    # Fault the filesystem only after the actual writer atomically publishes
    # its locator. Git capture and its returned result remain entirely real.
    original_replace = os.replace
    retained_locator = case_path / "published-locator.json"
    witnessed = []

    def remove_just_published_locator(source, destination, **kwargs):
        original_replace(source, destination, **kwargs)
        if Path(destination).absolute() == locator.absolute() and not witnessed:
            raw = locator.read_bytes()
            witnessed.append(raw)
            original_replace(locator, retained_locator)

    monkeypatch.setattr(os, "replace", remove_just_published_locator)
    lost = worker_context_call(context, {"command": "save", "binding": opened.binding})
    assert len(witnessed) == 1 and retained_locator.read_bytes() == witnessed[0]
    assert (
        lost.status == "publication_unknown"
        and lost.code == "saved_context_unavailable"
    ), lost
    assert lost.binding is None and not lost.ready
    assert lost.history_retained and lost.next_actions == ("inspect_history",)
    assert lost.publication == "not_started"
    captured = lost.capture
    assert captured is not None and captured.status == "captured", lost
    assert captured.history_retained and captured.objects_written
    assert captured.object_storage == "verified" and not captured.authored_files_changed
    assert captured.locator is not None and captured.locator.generation == 2
    assert captured.commit == lost.checkpoint_commit == captured.locator.commit
    assert captured.commit != prior_locator["commit"]
    assert json.loads(witnessed[0]) == captured.locator.model_dump(mode="json")
    assert not locator.exists()
    assert git(vault, "rev-parse", captured.ref).decode().strip() == captured.commit
    assert (
        git(vault, "rev-parse", captured.commit + "^").decode().strip()
        == prior_locator["commit"]
    )
    manifest = json.loads(
        git(vault, "cat-file", "blob", captured.commit + ":manifest.json")
    )
    assert (
        manifest["previous"] == prior_locator["commit"]
        and manifest["boundary"] == "local"
    )
    assert manifest["review_object"] is not None
    assert context.page(opened.binding).code == "context_changed"
    assert not any(scratch.iterdir())
    assert _authored_files(vault) == authored_before
    assert _user_state(vault) == user_before
    assert (vault / ".git/config").read_bytes() == config_before
    assert (
        git(vault, "cat-file", "blob", prior_locator["commit"] + ":manifest.json")
        == prior_manifest
    )
    assert (
        tuple(
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (initial, incoming)
        )
        == source_hashes
    )
