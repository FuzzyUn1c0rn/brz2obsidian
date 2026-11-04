"""Public recovery rebinds unchanged authored links to actual current targets."""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ReferenceTarget
from brz2obsidian.core import prepare_review, resolve_review
from brz2obsidian.obsidian import (
    align_structure,
    inspect_text_candidate,
    interpret_structure,
)
from brz2obsidian.publication.vault_replace import move_file
from tests.reconciliation.test_local_resources import manual_resource_facts
from tests.reconciliation.test_resolution import action


def git(vault, *args):
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Recovery context fixture",
            "-c",
            "user.email=recovery@example.invalid",
            "-C",
            str(vault),
            *args,
        ],
        capture_output=True,
        check=True,
    )
    return result.stdout


def inventory(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def make_stopped_case(*, include_tag=False):
    container = Path(tempfile.mkdtemp(prefix="brz2obsidian-280-recovery-links-"))
    record = {
        "owner": uuid4().hex,
        "root": str(container.resolve()),
        "base": str(Path(tempfile.gettempdir()).resolve()),
    }
    (container / ".fixture-owner.json").write_text(json.dumps(record), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2]
        / "tmp/issue-280-recovery-links/fixtures"
        / record["owner"]
    )
    evidence.mkdir(parents=True)
    (evidence / "owner.json").write_text(json.dumps(record), encoding="utf-8")
    vault, source = container / "vault", container / "source"
    vault.mkdir(mode=0o700)
    source.mkdir()
    facts = manual_resource_facts()
    subject = facts.subjects[0]
    structure = align_structure(
        *(
            interpret_structure(content, output_format=7)
            for content in (
                subject.baseline.content,
                subject.current.content,
                subject.incoming,
            )
        )
    )
    facts = facts.model_copy(
        update={"subjects": (subject.model_copy(update={"structure": structure}),)}
    )
    if include_tag:
        tag = ReferenceTarget(
            schema_id="brz2obsidian.reference-target",
            schema_version=1,
            target_id="tag:topic",
            kind="tag",
            canonical_path=None,
            identity=None,
            target=None,
            representations=("topic",),
            validation_fingerprint="known-topic-tag",
            status="safe",
        )
        context = facts.link_context
        facts = facts.model_copy(
            update={
                "link_context": context.model_copy(
                    update={
                        "current_targets": (tag,) + context.current_targets,
                        "incoming_targets": (tag,) + context.incoming_targets,
                    }
                )
            }
        )
    literal_current = {
        "Notes/Opening.md": b"Old [[Guide]].",
        "Docs/Guide.md": b"Guide body.",
        "Docs/Backlink.md": b"Keep [[Notes/Opening]]. ![[Assets/manual.bin]]",
        "Assets/manual.bin": b"\x00\xffmanual",
    }
    for path, data in literal_current.items():
        target = vault / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    converted = source / "Notes/Opening.md"
    converted.parent.mkdir()
    converted.write_bytes(b"Old [[Guide]].")
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "independent literal current files")
    operations = Operations()
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="recovery-context-vault",
        import_id="recovery-context-import",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert captured.status == "captured", captured.code
    converted.write_bytes(b"New [[Guide]].")
    offered = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    context = facts.link_context
    candidate = inspect_text_candidate(
        subject.incoming,
        identity=facts.identity_inventory[0].identity,
        target=subject.source_target,
        output_format=7,
        source_path=subject.path,
        document_id="opening",
        path_mode="vault",
        link_targets=context.incoming_targets,
        link_target_facts=context.incoming_target_facts,
        link_inventory=context.inventory,
    )
    transition = resolve_review(
        offered, action(offered, choice="incoming", candidate=candidate)
    )
    assert transition.status == "accepted", transition.code
    reviewed = transition.plan
    assert reviewed.ready, (reviewed.requirements, reviewed.blockers)

    class StopAfterActualMove:
        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            raise OSError("Fixture stopped after actual single-file publication")

        def directory(self, stage, target):
            raise AssertionError("This fixture has existing ordinary parents")

        def remove(self, target, destination):
            raise AssertionError("This fixture selects no removal")

    calls = 0

    def cancel_after_intent():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = Operations(vault_executor=StopAfterActualMove()).apply_reviewed_update(
        vault,
        source,
        review=reviewed,
        source_binding=operations.observe_reviewed_source(source, reviewed),
        vault_id="recovery-context-vault",
        import_id="recovery-context-import",
        cancel=cancel_after_intent if include_tag else None,
    )
    assert stopped.recovery_required and stopped.intent_commit, stopped
    if include_tag:
        assert stopped.status == "cancelled" and stopped.publication == "not_published"
        assert (vault / "Notes/Opening.md").read_bytes() == b"Old [[Guide]]."
    else:
        assert (
            stopped.status == "content_complete" and stopped.publication == "complete"
        )
        assert (vault / "Notes/Opening.md").read_bytes() == b"New [[Guide]]."
    assert (vault / "Docs/Backlink.md").read_bytes() == (
        b"Keep [[Notes/Opening]]. ![[Assets/manual.bin]]"
    )
    assert (vault / "Assets/manual.bin").read_bytes() == b"\x00\xffmanual"
    return vault, evidence


@pytest.fixture(scope="module")
def content_complete_case():
    return make_stopped_case()


@pytest.fixture(scope="module")
def tagged_cancelled_case():
    return make_stopped_case(include_tag=True)


def test_recovery_reinterprets_unchanged_backlink_after_target_version_changed(
    content_complete_case,
):
    vault, evidence = content_complete_case
    later = b"New [[Guide]].\nLater tracked writing."
    (vault / "Notes/Opening.md").write_bytes(later)
    before = inventory(vault)
    offered = Operations().prepare_recovery(vault, direction="finish")
    assert inventory(vault) == before
    (evidence / "recovery-result.json").write_text(
        offered.model_dump_json(), encoding="utf-8"
    )
    assert offered.status == "offered" and offered.review is not None, offered.code
    assert "current_link_context_unbound" not in offered.review.blockers
    context = offered.review.producer_facts.link_context
    backlink = next(
        document
        for document in context.current_documents
        if document.source_path == "Docs/Backlink.md"
    )
    assert backlink.content.data == b"Keep [[Notes/Opening]]. ![[Assets/manual.bin]]"
    opening, resource = backlink.occurrences
    assert (
        opening.meaning.status,
        opening.meaning.path,
        opening.meaning.target_version,
    ) == (
        "resolved",
        "Notes/Opening.md",
        hashlib.sha256(later).hexdigest(),
    )
    resource_digest = hashlib.sha256(b"\x00\xffmanual").hexdigest()
    assert resource.meaning.target_version == resource_digest
    kept = Operations().resolve_recovery(
        vault,
        offered,
        action(offered.review, choice="current", decision_id="recovery-current"),
    )
    assert inventory(vault) == before
    assert kept.status == "offered" and kept.review.ready, kept.code
    assert kept.review.approvals[0].result.data == later


def test_recovery_accepts_known_tag_without_file_state_in_both_directions(
    tagged_cancelled_case,
):
    vault, evidence = tagged_cancelled_case
    before = inventory(vault)
    for direction in ("finish", "restore"):
        offered = Operations().prepare_recovery(vault, direction=direction)
        assert inventory(vault) == before
        (evidence / (direction + "-result.json")).write_text(
            offered.model_dump_json(), encoding="utf-8"
        )
        assert offered.status == "offered" and offered.review is not None, offered.code
        assert "current_link_context_unbound" not in offered.review.blockers
        context = offered.review.producer_facts.link_context
        tags = tuple(
            target for target in context.current_targets if target.kind == "tag"
        )
        assert len(tags) == 1
        assert (
            tags[0].target_id,
            tags[0].canonical_path,
            tags[0].identity,
            tags[0].target,
        ) == ("tag:topic", None, None, None)
        assert "tag:topic" not in {
            state.target_id for state in context.current_target_facts
        }
        assert "tag:topic" not in {
            state.target_id for state in context.incoming_target_facts
        }
        backlink = next(
            document
            for document in context.current_documents
            if document.source_path == "Docs/Backlink.md"
        )
        assert backlink.content.data == (
            b"Keep [[Notes/Opening]]. ![[Assets/manual.bin]]"
        )
        assert (
            backlink.occurrences[0].meaning.target_version
            == hashlib.sha256(b"Old [[Guide]].").hexdigest()
        )
