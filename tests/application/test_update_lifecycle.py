"""Real source and owned-history composition at the application seam."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.contracts import (
    AttachmentCandidate,
    AttachmentSelection,
    OutputIdentity,
)
from brz2obsidian.core import prepare_review
from brz2obsidian.obsidian import interpret_link_target
from tests.application.test_minimal_workflow import make_archive
from tests.reconciliation.test_resolution import action


@pytest.fixture
def case_path():
    path = Path(tempfile.mkdtemp(prefix="brz2obsidian-280-"))
    owner = {"owner": uuid4().hex, "root": str(path.resolve())}
    (path / ".fixture-owner.json").write_text(json.dumps(owner))
    evidence = Path(__file__).resolve().parents[2] / "tmp/issue-280/fixtures"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(json.dumps(owner))
    # Retain owned active-effort fixtures for exact failed-publication diagnosis.
    yield path


def git(vault, *args):
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Update fixture",
            "-c",
            "user.email=update@example.invalid",
            "-C",
            str(vault),
            *args,
        ],
        capture_output=True,
        check=True,
    )
    return result.stdout


def test_converter_vault_without_source_history_routes_to_preservation_onboarding(
    case_path,
):
    source = make_archive(case_path / "incoming.brz")
    vault = case_path / "vault"
    operations = Operations()
    from brz2obsidian.application.wiring import default_workflow

    assert default_workflow().convert(source, vault).receipt is not None
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    before = (vault / "Home — Entry thought.md").read_bytes()
    result = operations.prepare_update(vault, source)
    assert result.status == "refused"
    assert result.code == "onboarding_required"
    assert result.next_actions == ("review_onboarding",)
    assert not result.ready
    assert result.publication == "not_started"
    assert (vault / "Home — Entry thought.md").read_bytes() == before


def _seed(case_path, *, two_notes=False, capture_history=True):
    from brz2obsidian.application.wiring import default_workflow

    archive = make_archive(case_path / "initial.brz")
    if two_notes:
        second = case_path / "initial-two.brz"
        with ZipFile(archive) as old, ZipFile(second, "w") as new:
            for name in old.namelist():
                raw = old.read(name)
                if name == "thoughts.json":
                    thought = json.loads(raw)
                    thought.update(
                        Id="44444444-4444-4444-8444-444444444444", Name="Second thought"
                    )
                    raw += b"\n" + json.dumps(thought).encode()
                elif name == "attachments.json":
                    attachment = json.loads(raw)
                    attachment.update(
                        Id="55555555-5555-4555-8555-555555555555",
                        SourceId="44444444-4444-4444-8444-444444444444",
                    )
                    raw += b"\n" + json.dumps(attachment).encode()
                elif name == "meta.json":
                    meta = json.loads(raw)
                    meta["AttachmentFileStates"][
                        "55555555-5555-4555-8555-555555555555"
                    ] = 1
                    raw = json.dumps(meta).encode()
                new.writestr(name, raw)
            new.writestr(
                "44444444-4444-4444-8444-444444444444/Notes.md", b"Second source.\r\n"
            )
        archive = second
    vault, source = case_path / "vault", case_path / "source"
    workflow = default_workflow()
    metadata = workflow.metadata_factory()
    workflow.metadata_factory = lambda: metadata
    receipt = workflow.convert(archive, vault).receipt
    assert receipt is not None and receipt.verified
    source.mkdir()
    for row in receipt.manifest:
        original = vault / row.relative_path
        pristine = source / row.relative_path
        pristine.parent.mkdir(parents=True, exist_ok=True)
        original_bytes = original.read_bytes()
        assert len(original_bytes) == row.length
        assert hashlib.sha256(original_bytes).hexdigest() == row.sha256
        mode = original.stat().st_mode & 0o777
        shutil.copy2(original, pristine)
        assert pristine.stat().st_size == row.length
        assert hashlib.sha256(pristine.read_bytes()).hexdigest() == row.sha256
        assert pristine.stat().st_mode & 0o777 == mode
    # Distinct pristine source A is captured before authored changes or Git init.
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    if two_notes:
        (vault / "Manual.md").write_bytes(b"Initial independent writing.\r\n")
        (vault / "Attachments/manual.bin").write_bytes(
            b"\x00\xffmanual owned bytes\r\n"
        )
        git(
            vault,
            "add",
            "Manual.md",
            "Home — Entry thought.md",
            "Attachments/manual.bin",
        )
        git(vault, "commit", "-qm", "Independent user history")
        git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
        (vault / "Manual.md").write_bytes(b"Staged independent writing.\r\n")
        git(vault, "add", "Manual.md")
        (vault / "Manual.md").write_bytes(
            (
                "# My writing\n\nKeep [[Home — Entry thought.md|My reference]] and [[Second thought|Other]].\n\n![[Attachments/manual.bin]]\n"
            ).encode()
        )
    if not capture_history:
        return vault, archive
    identity = OutputIdentity(
        collection_id="11111111-1111-4111-8111-111111111111",
        module_id="thebrain-brz",
        module_version="10",
        profile_id="thebrain-format5-reviewed",
        profile_version="10",
        output_format=7,
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    result = Operations().capture_checkpoint(
        vault,
        source,
        vault_id="vault-280",
        import_id="import-280",
        identity=identity,
        admission=Operations().inspect_history(vault).admission,
    )
    assert result.status == "captured", result
    return vault, archive


def _changed_archive(source, path):
    with ZipFile(source) as old, ZipFile(path, "w") as new:
        for name in old.namelist():
            raw = old.read(name)
            if name.endswith("/Notes.md"):
                raw = b"Incoming body.\r\n"
            new.writestr(name, raw)
    return path


def test_actual_source_update_offers_current_incoming_and_edited_choices(case_path):
    vault, initial = _seed(case_path, two_notes=True)
    note = vault / "Home — Entry thought.md"
    note.write_bytes(note.read_bytes().replace(b"Authored body.", b"Local writing."))
    user_before = _user_state(vault)
    second_before = (vault / "Notes/Second thought.md").read_bytes()
    assert b"Second source.\r\n" in second_before
    incoming = _changed_archive(initial, case_path / "incoming.brz")
    result = Operations().prepare_update(vault, incoming)
    assert result.status == "prepared_review"
    assert not result.ready
    prepared = result.preparation
    change = next(
        c
        for c in prepared.review.proposal.changes
        if c.item_id == "22222222-2222-4222-8222-222222222222"
    )
    assert b"Local writing." in change.current.data
    assert b"Incoming body." in change.incoming.data
    chosen = Operations().resolve_update(
        prepared, action(prepared.review, change, choice="current")
    )
    assert chosen.status == "unresolved", chosen
    assert chosen.preparation.review.approvals[0].choice == "current"
    assert chosen.preparation.review.approvals[0].result.data == note.read_bytes()
    assert chosen.preparation.review.approvals[0].source_memory.choice == "keep_vault"
    # A caller can construct a canonical pure plan, but cannot introduce
    # trusted remembered decisions absent from the actual owned checkpoint.
    forged_facts = prepared.review.producer_facts.model_copy(
        update={
            "source_version_memory": (
                chosen.preparation.review.approvals[0].source_memory,
            )
        }
    )
    forged_plan = prepare_review(forged_facts, preflight=prepared.review.preflight)
    forged = prepared.model_copy(update={"review": forged_plan})
    refused_memory = Operations().refresh_update(forged)
    assert refused_memory.status == "stale_review" and not refused_memory.ready
    assert refused_memory.preparation.review.facts.source_version_memory == ()
    restored_choice = next(
        c
        for c in refused_memory.preparation.review.proposal.changes
        if c.item_id == change.item_id
    )
    assert any(
        r.change_id == restored_choice.change_id
        for r in refused_memory.preparation.review.requirements
    )
    prepared = chosen.preparation
    second = next(
        c
        for c in prepared.review.proposal.changes
        if c.item_id == "44444444-4444-4444-8444-444444444444"
    )
    chosen = Operations().resolve_update(
        prepared,
        action(
            prepared.review, second, choice="current", decision_id="independent-second"
        ),
    )
    assert chosen.code == "accepted", chosen
    expected = [a.decision_id for a in chosen.preparation.review.approvals]
    saved = Operations().save_update(chosen.preparation)
    assert saved.code == "saved", saved
    checkpoint = Operations().read_checkpoint(vault)
    assert saved.checkpoint == checkpoint.locator
    assert checkpoint.manifest.boundary == "local"
    assert (
        checkpoint.manifest.reviewed_source.files
        == chosen.preparation.source_binding.files
    )
    assert (
        checkpoint.manifest.observed_source.source_sha256
        == hashlib.sha256(incoming.read_bytes()).hexdigest()
    )
    # Unresolved Save retains A as SOURCE while complete incoming B remains in
    # the existing exact-byte review graph, including original assets/support.
    original_row = next(
        r
        for r in checkpoint.manifest.source
        if r.path == "Attachments/22222222/Notes.md.original"
    )
    assert (
        original_row.sha256
        == "5ffa7716ee53174debb9b0ddfec17efa574c4e494b4bd1a321a0378c29016229"
    )
    persisted = case_path / "resumed.json"
    script = (
        "import json, pathlib, sys\n"
        "from brz2obsidian.application.operations import Operations\n"
        "ops = Operations()\n"
        "loaded = ops.load_update(sys.argv[1]) if len(sys.argv) == 3 else None\n"
        "resumed = ops.resume_update(sys.argv[1])\n"
        "if resumed.preparation is not None:\n"
        " pathlib.Path(sys.argv[2]).write_text(resumed.preparation.model_dump_json())\n"
        "print(json.dumps({'loaded_ready':None if loaded is None else loaded.ready,'loaded_code':None if loaded is None else loaded.code,'status':resumed.status,'code':resumed.code,'decisions':[] if resumed.preparation is None else [a.decision_id for a in resumed.preparation.review.approvals]}))\n"
    )
    process = subprocess.run(
        [sys.executable, "-c", script, str(vault), str(persisted)],
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )
    reopened = json.loads(process.stdout)
    assert reopened["loaded_ready"] is False
    assert reopened["loaded_code"] == "revalidation_required"
    assert reopened["decisions"] == expected, reopened
    resumed = UpdatePreparation.model_validate_json(persisted.read_bytes())
    later = note.read_bytes() + b"\nLater independent writing.\r\n"
    note.write_bytes(later)
    refreshed = Operations().refresh_update(resumed)
    assert refreshed.preparation is not None, refreshed
    current = refreshed.preparation
    assert current.review.proposal.generation == resumed.review.proposal.generation + 1
    assert [a.decision_id for a in current.review.approvals] == ["independent-second"]
    event = current.review.history.events[-1]
    assert change.subject_id + ":current" in event.changed_keys
    assert "effect:" + change.subject_id in event.invalidated_keys
    assert "effect:" + second.subject_id not in event.invalidated_keys
    assert [(r.decision_id, r.subject_id) for r in event.retained] == [
        ("independent-second", second.subject_id)
    ]
    unresolved_items = {
        c.item_id
        for c in current.review.proposal.changes
        if any(r.change_id == c.change_id for r in current.review.requirements)
    }
    assert "22222222-2222-4222-8222-222222222222" in unresolved_items
    assert "44444444-4444-4444-8444-444444444444" not in unresolved_items
    current_change = next(
        c
        for c in current.review.proposal.changes
        if c.item_id == "22222222-2222-4222-8222-222222222222"
    )
    edited_bytes = later.replace(b"Local writing.", b"Reviewed writing.")
    edited = Operations().resolve_update(
        current,
        action(
            current.review,
            current_change,
            choice="edited",
            decision_id="edited-after-refresh",
        ),
        edited=edited_bytes,
    )
    assert edited.code == "accepted", edited
    saved_again = Operations().save_update(edited.preparation)
    assert saved_again.code == "saved", saved_again
    process = subprocess.run(
        [sys.executable, "-c", script, str(vault), str(persisted), "resume-only"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    reopened_again = json.loads(process.stdout)
    assert reopened_again["decisions"] == [
        "independent-second",
        "edited-after-refresh",
    ], reopened_again
    final = UpdatePreparation.model_validate_json(persisted.read_bytes())
    assert final.review.approvals[0].result.data == second.current.data
    assert (
        final.review.approvals[0].source_memory.reviewed_incoming.data
        == second.incoming.data
    )
    reopened_edit = next(
        a for a in final.review.approvals if a.decision_id == "edited-after-refresh"
    )
    assert reopened_edit.result.data == edited_bytes
    reopened_action = next(
        a for a in final.review.actions if a.decision_id == "edited-after-refresh"
    )
    assert reopened_action.candidate.content.data == edited_bytes
    assert (vault / "Home — Entry thought.md").read_bytes() == later
    assert final.source_binding.files == chosen.preparation.source_binding.files
    assert _user_state(vault) == user_before
    assert (vault / "Notes/Second thought.md").read_bytes() == second_before


def _user_state(vault):
    return {
        "head": (vault / ".git/HEAD").read_bytes(),
        "index": (vault / ".git/index").read_bytes(),
        "stages": git(vault, "ls-files", "--stage", "-z"),
        "staged_manual": git(vault, "show", ":Manual.md"),
        "refs": tuple(
            row
            for row in git(
                vault, "for-each-ref", "--format=%(refname) %(objectname)"
            ).splitlines()
            if not row.startswith(b"refs/brz2obsidian/")
        ),
        "manual": (vault / "Manual.md").read_bytes(),
        "binary": (vault / "Attachments/manual.bin").read_bytes(),
    }


def _finish_incoming(prepared):
    for number in range(20):
        plan = prepared.review
        if plan.ready:
            return prepared
        requirement = plan.requirements[0]
        change = next(
            c for c in plan.proposal.changes if c.change_id == requirement.change_id
        )
        selection = candidate = None
        choice = (
            "current"
            if requirement.domain == "configuration"
            else "approve"
            if "approve" in requirement.choices
            else "incoming"
        )
        if requirement.domain == "attachment":
            alternative = next(
                a
                for a in change.attachment_review.alternatives
                if a.choice == "incoming"
            )
            selection = AttachmentSelection(
                schema_id="brz2obsidian.attachment-selection",
                schema_version=1,
                proposal_id=plan.proposal.proposal_id,
                generation=plan.proposal.generation,
                item_id=change.item_id,
                facet=change.facet,
                reviewed_change_id=change.change_id,
                reviewed_assumptions=change.assumptions,
                choice="incoming",
                link_choices=(),
                provenance="explicit_user",
            )
            context = plan.producer_facts.link_context
            base = next(
                t
                for t in context.current_targets
                if t.target_id == alternative.outputs[0].target_id
            )
            states = tuple(
                s for s in context.current_target_facts if s.target_id != base.target_id
            ) + (
                interpret_link_target(
                    alternative.outputs[0].content,
                    target_id=base.target_id,
                    existence="present",
                    memberships=(),
                ),
            )
            candidate = AttachmentCandidate(
                schema_id="brz2obsidian.attachment-candidate",
                schema_version=1,
                outputs=alternative.outputs,
                documents=context.current_documents,
                targets=context.current_targets,
                target_facts=states,
            )
        chosen = Operations().resolve_update(
            prepared,
            action(
                plan,
                change,
                domain=requirement.domain,
                choice=choice,
                decision_id="finish:" + str(number),
                attachment_selection=selection,
                attachment_candidate=candidate,
            ),
        )
        assert chosen.code == "accepted", (
            requirement.domain,
            requirement.choices,
            chosen,
        )
        prepared = chosen.preparation
    raise AssertionError("Finite fixture review did not finish")


def _retained_bytes(value):
    if hasattr(type(value), "model_fields"):
        for name in type(value).model_fields:
            yield from _retained_bytes(getattr(value, name))
    elif isinstance(value, dict):
        for item in value.values():
            yield from _retained_bytes(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _retained_bytes(item)
    elif isinstance(value, bytes):
        yield value


def test_unreferenced_ignored_authored_bytes_never_enter_the_saved_review(case_path):
    vault, initial = _seed(case_path)
    ignored = vault / "Ignored"
    ignored.mkdir()
    marker = b"DO-NOT-RETAIN-280-private-content"
    (ignored / "Private.bin").write_bytes(b"\0\xff" + marker)
    (ignored / "Private.md").write_bytes(marker + b"\r\n")
    excludes = vault / ".git/info/exclude"
    excludes.write_bytes(excludes.read_bytes() + b"\nIgnored/\n")
    incoming = _changed_archive(initial, case_path / "incoming.brz")
    from brz2obsidian.application.wiring import default_workflow

    workflow = default_workflow()
    metadata = workflow.metadata_factory().model_copy(
        update={
            "run_id": "incoming-B-280",
            "run_time": "2026-10-24T10:00:00+00:00",
            "bookmark_time": 1792836000000,
        }
    )
    workflow.metadata_factory = lambda: metadata
    result = Operations(workflow=workflow).prepare_update(vault, incoming)
    assert result.preparation is not None, result
    source_record = json.loads(
        next(
            s.incoming.data
            for s in result.preparation.review.facts.subjects
            if s.item_id == "support:migration-record.json"
        )
    )
    assert source_record["run_metadata"]["run_id"] == "incoming-B-280"
    assert source_record["run_metadata"]["run_time"] == "2026-10-24T10:00:00+00:00"
    prior_record = json.loads((vault / "migration-record.json").read_bytes())
    assert (
        source_record["run_metadata"]["bookmark_time"]
        == prior_record["run_metadata"]["bookmark_time"]
    )
    complete = Operations().inspect_history(vault).admission
    assert {r.path for r in complete.inventory if r.excluded} >= {
        "Ignored/Private.bin",
        "Ignored/Private.md",
    }
    assert not any(marker in raw for raw in _retained_bytes(result.preparation.review))
    change = next(
        c
        for c in result.preparation.review.proposal.changes
        if c.item_id == "22222222-2222-4222-8222-222222222222"
    )
    current = Operations().resolve_update(
        result.preparation, action(result.preparation.review, change, choice="current")
    )
    assert current.code == "accepted", current
    saved = Operations().save_update(current.preparation)
    assert saved.code == "saved", saved
    retained = Operations().read_checkpoint(vault)
    assert not any(marker in raw for raw in _retained_bytes(retained.review))
    assert "Ignored/Private.bin" in retained.manifest.recovery_gaps
    assert "Ignored/Private.md" in retained.manifest.recovery_gaps
    assert not any(r.path.startswith("Ignored/") for r in retained.manifest.vault)
    assert (ignored / "Private.bin").read_bytes() == b"\0\xff" + marker
    assert (ignored / "Private.md").read_bytes() == marker + b"\r\n"
