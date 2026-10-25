"""Actual SOURCE/LOCAL roles for known and unknown recorded older generations."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import OutputIdentity
from tests.application.test_module_seams import METADATA
from tests.application.test_update_lifecycle import git
from tests.support.recorded_format6 import (
    CURRENT,
    FIXTURE,
    NOTE,
    ORIGINAL,
    historical_payload,
)


def owned_format_case():
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-282-"))
    owner = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    evidence = Path(__file__).resolve().parents[2] / "tmp/issue-282/fixtures"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(
        json.dumps(owner), encoding="utf-8"
    )
    return root


def user_git_state(vault):
    return (
        git(vault, "rev-parse", "HEAD"),
        (vault / ".git/index").read_bytes(),
        tuple(
            line
            for line in git(
                vault, "for-each-ref", "--format=%(refname) %(objectname)"
            ).splitlines()
            if not line.startswith(b"refs/brz2obsidian/imports/")
        ),
    )


def native_format_case(known_original):
    root = owned_format_case()
    payload, _proof = historical_payload()
    old_source, vault = root / "old-generated", root / "vault"
    for name, raw in payload.items():
        for directory in (old_source, vault):
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    source = root / "unchanged.brz"
    shutil.copyfile(FIXTURE / "source.brz", source)
    (vault / NOTE).write_bytes(CURRENT)
    (vault / "Manual.md").write_bytes(b"Independent tracked writing.\r\n")
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", "Manual.md", NOTE)
    git(vault, "commit", "-qm", "User legacy history")
    git(vault, "branch", "user-preserved")
    (vault / "Manual.md").write_bytes(b"Independent staged writing.\r\n")
    git(vault, "add", "Manual.md")
    (vault / "Manual.md").write_bytes(b"Independent unstaged writing.\r\n")
    user_before = user_git_state(vault)
    workflow = default_workflow()
    workflow.metadata_factory = lambda: METADATA
    operations = Operations(workflow=workflow)
    if known_original:
        identity = OutputIdentity(
            collection_id="7b170eec-a7e4-49f6-a0b4-bd553528a201",
            module_id="thebrain-brz",
            module_version="9",
            profile_id="thebrain-format5-reviewed",
            profile_version="9",
            output_format=6,
            settings_digest=hashlib.sha256(b"{}").hexdigest(),
        )
        seeded = operations.capture_checkpoint(
            vault,
            old_source,
            identity=identity,
            admission=operations.inspect_history(vault).admission,
            vault_id="legacy-known-vault",
            import_id="legacy-known-import",
        )
        assert seeded.status == "captured", seeded
    else:
        enrolled = operations.prepare_onboarding(vault, source)
        assert enrolled.preparation is not None, enrolled
        assert all(
            s.baseline.status == "unknown"
            for s in enrolled.preparation.review.facts.subjects
        )
        seeded = operations.save_update(enrolled.preparation)
        assert seeded.code == "saved", seeded
    assert user_git_state(vault) == user_before
    return root, operations, vault, source, user_before


@pytest.mark.parametrize("known_original", (True, False))
def test_native_local_checkpoint_keeps_old_identity_and_complete_target_without_promoting_originals(
    known_original,
):
    root, operations, vault, source, user_before = native_format_case(known_original)
    offered = operations.prepare_format_transition(vault, source)
    assert offered.preparation is not None, offered
    assert offered.kind == "format_transition" and not offered.ready
    saved = operations.save_update(offered.preparation)
    (root / "saved-transition.json").write_text(
        saved.model_dump_json(), encoding="utf-8"
    )
    assert saved.code == "saved" and saved.kind == "format_transition", saved
    actual = operations.read_checkpoint(vault)
    assert actual.status == "valid" and actual.manifest.boundary == "local", actual
    assert (
        actual.manifest.identity.output_format == 6
        and actual.manifest.identity.profile_version == "9"
    )
    assert actual.manifest.reviewed_source.incoming_identity.output_format == 7
    assert {
        (r.path, r.mode, r.size, r.sha256)
        for r in actual.manifest.reviewed_source.files
    } == {
        (r.path, r.mode, r.size, r.sha256)
        for r in offered.preparation.source_binding.files
    }
    assert actual.review.saved.plan.facts.format_operation.kind == "format_transition"
    note = next(
        s
        for s in actual.review.saved.plan.facts.subjects
        if s.item_id == "5f71e626-527e-47b4-abaa-e53d124619f8"
    )
    if known_original:
        assert (
            note.baseline.status == "known" and note.baseline.content.data == ORIGINAL
        )
        assert (
            next(r for r in actual.manifest.source if r.path == NOTE).sha256
            == hashlib.sha256(ORIGINAL).hexdigest()
        )
    else:
        assert note.baseline.status == "unknown" and note.baseline.content is None
    assert (
        note.current.content.data == CURRENT and (vault / NOTE).read_bytes() == CURRENT
    )
    assert user_git_state(vault) == user_before
