"""One real accepted legacy baseline, cold resume and subsequent update admission."""

import hashlib
import subprocess
import sys

from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.contracts import AttachmentCandidate, AttachmentSelection
from tests.application.test_onboarding import owned_case
from tests.application.test_onboarding_originals import (
    CURRENT,
    NOTE,
    ORIGINAL,
    legacy_brz_case,
)
from tests.application.test_update_lifecycle import _user_state, git
from tests.reconciliation.test_resolution import action


def authored_files(vault):
    return {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
        and p.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    }


def keep_current(operations, prepared):
    for number in range(3 * len(prepared.review.proposal.changes) + 1):
        if prepared.review.ready:
            return prepared
        requirement = prepared.review.requirements[0]
        change = next(
            c
            for c in prepared.review.proposal.changes
            if c.change_id == requirement.change_id
        )
        assert requirement.domain in ("format", "configuration"), requirement
        options = {}
        if change.attachment_review is not None:
            alternative = next(
                a
                for a in change.attachment_review.alternatives
                if a.choice == "current"
            )
            assert alternative.eligible and len(alternative.outputs) == 1
            context = prepared.review.producer_facts.link_context
            selection = AttachmentSelection(
                schema_id="brz2obsidian.attachment-selection",
                schema_version=1,
                proposal_id=prepared.review.proposal.proposal_id,
                generation=prepared.review.proposal.generation,
                item_id=change.item_id,
                facet=change.facet,
                reviewed_change_id=change.change_id,
                reviewed_assumptions=change.assumptions,
                choice="current",
                link_choices=(),
                provenance="explicit_user",
            )
            candidate = AttachmentCandidate(
                schema_id="brz2obsidian.attachment-candidate",
                schema_version=1,
                outputs=alternative.outputs,
                documents=context.current_documents,
                targets=context.current_targets,
                target_facts=context.current_target_facts,
            )
            options = {
                "attachment_selection": selection,
                "attachment_candidate": candidate,
            }
        chosen = operations.resolve_update(
            prepared,
            action(
                prepared.review,
                change,
                domain=requirement.domain,
                choice="current",
                decision_id=f"legacy-current-{number}",
                **options,
            ),
        )
        assert chosen.code == "accepted", chosen
        prepared = chosen.preparation
    raise AssertionError("The finite offered review did not complete")


def test_known_brz_onboarding_resumes_completes_and_admits_only_the_retained_reference():
    root = owned_case()
    operations, vault, archive = legacy_brz_case(root)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Manual.md").write_bytes(b"Independent user baseline.\r\n")
    (vault / "Attachments/manual.bin").write_bytes(b"\x00\xffIndependent binary.\r\n")
    git(vault, "add", "Manual.md", NOTE, "Attachments/manual.bin")
    git(vault, "commit", "-qm", "User authoring history")
    git(vault, "branch", "user-side")
    git(vault, "tag", "user-preserved")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    (vault / "Manual.md").write_bytes(b"Staged independent user writing.\r\n")
    git(vault, "add", "Manual.md")
    (vault / "Manual.md").write_bytes(b"Unstaged independent user writing.\r\n")
    before, user_before = authored_files(vault), _user_state(vault)
    offered = operations.prepare_onboarding(vault, archive, original_source=archive)
    assert offered.preparation is not None, offered
    prepared = keep_current(operations, offered.preparation)
    expected_decisions = [a.decision_id for a in prepared.review.approvals]
    assert all(not a.source_accepted for a in prepared.review.approvals)
    saved = operations.save_update(prepared)
    assert saved.code == "saved" and saved.checkpoint is not None, saved
    loaded = operations.load_update(vault)
    assert (
        loaded.kind == "onboarding" and loaded.loaded is not None and not loaded.ready
    )
    assert not loaded.loaded.ready
    pending = operations.prepare_update(vault, "unopened.brz")
    assert pending.code == "onboarding_review_required" and not pending.ready
    code = """
import sys
from pathlib import Path
from brz2obsidian.application.operations import Operations
result = Operations().resume_update(sys.argv[1])
Path(sys.argv[2]).write_text(result.model_dump_json())
"""
    resumed_path = root / "known-fresh-resume.json"
    process = subprocess.run(
        [sys.executable, "-c", code, str(vault), str(resumed_path)],
        capture_output=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    resumed = UpdateResult.model_validate_json(resumed_path.read_text())
    assert resumed.kind == "onboarding" and resumed.ready, resumed
    assert resumed.generation == 1
    assert [
        a.decision_id for a in resumed.preparation.review.approvals
    ] == expected_decisions
    note = next(
        s
        for s in resumed.preparation.review.facts.subjects
        if s.item_id == "22222222-2222-4222-8222-222222222222"
    )
    assert (
        note.baseline.content.data == ORIGINAL and note.current.content.data == CURRENT
    )
    assert authored_files(vault) == before and _user_state(vault) == user_before
    completed = operations.apply_update(resumed.preparation)
    (root / "completion-result.json").write_text(completed.model_dump_json())
    assert completed.kind == "onboarding" and completed.status == "no_content_change", (
        completed
    )
    assert completed.code != "already_current"
    assert (
        completed.application is not None
        and completed.application.history == "terminal"
    )
    assert (
        completed.application.planned_files
        == completed.application.published_files
        == 0
    )
    assert completed.application.receipt_commit is not None
    retained = operations.read_checkpoint(vault)
    assert retained.status == "valid" and retained.manifest.boundary == "result"
    assert retained.locator.commit == completed.application.result_commit
    operation_ref = (
        retained.locator.association.ref.rsplit("/", 1)[0]
        + "/operations/"
        + completed.operation_id
    )
    assert (
        git(vault, "rev-parse", operation_ref).strip().decode()
        == completed.application.receipt_commit
    )
    assert (
        retained.manifest.observed_source.source_sha256
        == hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    source_note = next(r for r in retained.manifest.source if r.path == NOTE)
    vault_note = next(r for r in retained.manifest.vault if r.path == NOTE)
    assert source_note.sha256 == hashlib.sha256(ORIGINAL).hexdigest()
    assert vault_note.sha256 == hashlib.sha256(CURRENT).hexdigest()
    assert authored_files(vault) == before and _user_state(vault) == user_before
    locator_before = (vault / ".brz2obsidian/locator.json").read_bytes()
    refs_before = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    future = operations.prepare_update(vault, archive)
    assert future.kind == "source_update" and future.preparation is not None, future
    future_note = next(
        s
        for s in future.preparation.review.facts.subjects
        if s.item_id == "22222222-2222-4222-8222-222222222222"
    )
    assert (
        future_note.baseline.status == "known"
        and future_note.baseline.content.data == ORIGINAL
    )
    assert (
        future_note.current.content.data == CURRENT
        and future_note.baseline.content.data != future_note.current.content.data
    )
    assert future.preparation.review.facts.baseline_identity.output_format == 7
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_before
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs_before
    )
    assert authored_files(vault) == before and _user_state(vault) == user_before
