"""One real source-absence, explicit cleanup and interrupted native graph."""

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from brz2obsidian.application.checkpoint_payload_contracts import (
    CheckpointPayloadRequest,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_contracts import UpdateResult
from brz2obsidian.contracts import AttachmentCandidate, AttachmentSelection
from brz2obsidian.obsidian import interpret_link_target
from tests.application.test_attachment_cleanup_application import cleanup_asset_action
from tests.application.test_onboarding_completion import keep_current
from tests.application.test_update_lifecycle import _seed
from tests.application.test_vault_checkpoints import git, user_state
from tests.reconciliation.test_resolution import action

OLD_ASSET = "33333333-3333-4333-8333-333333333333"
NEW_ASSET = "55555555-5555-4555-8555-555555555555"
OLD_PATH = "Attachments/22222222/Notes.md.original"
NEW_PATH = "Attachments/22222222/Fresh.md.original"
NOTE_PATH = "Home — Entry thought.md"
ORIGINAL = b"Authored body.\r\n"
LEGACY_CURRENT = b"\x00authored legacy asset\xff"


def all_bytes(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def user_git(vault):
    state = user_state(vault)
    state.pop("authored")
    state["refs"] = tuple(
        row for row in state["refs"] if not row.startswith(b"refs/brz2obsidian/")
    )
    return state


def incoming_attachment(plan, change):
    alternative = next(
        a for a in change.attachment_review.alternatives if a.choice == "incoming"
    )
    assert alternative.eligible
    context = plan.producer_facts.link_context
    output = alternative.outputs[0]
    states = tuple(
        s for s in context.current_target_facts if s.target_id != output.target_id
    ) + (
        interpret_link_target(
            output.content,
            target_id=output.target_id,
            existence="present",
            memberships=(),
        ),
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
    candidate = AttachmentCandidate(
        schema_id="brz2obsidian.attachment-candidate",
        schema_version=1,
        outputs=alternative.outputs,
        documents=context.current_documents,
        targets=context.current_targets,
        target_facts=states,
    )
    return selection, candidate


def test_actual_absence_cleanup_save_restart_interruption_and_finish_preserve_current_source():
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-283-"))
    owner = uuid4().hex
    marker = {"owner": owner, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(marker), encoding="utf-8")
    records = Path(__file__).resolve().parents[2] / "tmp/issue-283-application/fixtures"
    records.mkdir(parents=True, exist_ok=True)
    (records / (owner + ".json")).write_text(json.dumps(marker), encoding="utf-8")
    started = time.monotonic()

    def remember(name, value):
        (root / (name + ".json")).write_text(value.model_dump_json(), encoding="utf-8")
        with (root / "milestones.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "stage": name,
                        "seconds": time.monotonic() - started,
                        "status": value.status,
                        "code": value.code,
                    }
                )
                + "\n"
            )
        return value

    vault, archive_a = _seed(root, capture_history=False)
    assert (vault / OLD_PATH).read_bytes() == ORIGINAL
    assert not (vault / ".brz2obsidian").exists()
    assert git(vault, "for-each-ref", "--format=%(refname)", "refs/brz2obsidian") == b""
    source_a = all_bytes(root / "source")
    source_a_version = json.loads(source_a["migration-record.json"])["source_identity"][
        "snapshot_digest"
    ]
    manual = b"Manual [[Attachments/22222222/Notes.md.original|Original]]. `[[Attachments/22222222/Notes.md.original]]`\r\n"
    (vault / "Manual.md").write_bytes(manual)
    (vault / "Unrelated.bin").write_bytes(b"\xffindependent user bytes\x00")
    git(vault, "add", "Manual.md", "Unrelated.bin", NOTE_PATH)
    git(vault, "commit", "-qm", "Independent user history before source absence")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    (vault / "Manual.md").write_bytes(b"Staged separate user writing.\r\n")
    git(vault, "add", "Manual.md")
    (vault / "Manual.md").write_bytes(manual)
    original_user_git = user_git(vault)
    (vault / OLD_PATH).write_bytes(LEGACY_CURRENT)
    legacy_before = {
        path: raw
        for path, raw in all_bytes(vault).items()
        if not path.startswith((".git/", ".brz2obsidian/"))
    }
    operations = Operations()
    onboarding = remember(
        "first-onboarding", operations.prepare_onboarding(vault, archive_a)
    )
    assert onboarding.preparation is not None, onboarding.code
    initial = keep_current(operations, onboarding.preparation)
    initial_saved = remember("first-onboarding-saved", operations.save_update(initial))
    assert initial_saved.code == "saved", initial_saved.code
    established = remember(
        "first-onboarding-completed", operations.apply_update(initial_saved.preparation)
    )
    assert established.status == "no_content_change", established.code
    assert (
        established.application.planned_files
        == established.application.published_files
        == 0
    )
    assert all(
        (vault / path).read_bytes() == raw for path, raw in legacy_before.items()
    )
    assert user_git(vault) == original_user_git

    archive_b = root / "source-B.brz"
    with ZipFile(archive_a) as old, ZipFile(archive_b, "w") as new:
        for name in old.namelist():
            raw = old.read(name)
            if name == "attachments.json":
                record = json.loads(raw)
                record.update(Id=NEW_ASSET, Location="Fresh.md")
                raw = json.dumps(record).encode()
            elif name == "meta.json":
                record = json.loads(raw)
                record["AttachmentFileStates"] = {NEW_ASSET: 1}
                raw = json.dumps(record).encode()
            if name == "22222222-2222-4222-8222-222222222222/Notes.md":
                name = "22222222-2222-4222-8222-222222222222/Fresh.md"
            new.writestr(name, raw)
    ordinary = remember(
        "ordinary-preparation", operations.prepare_update(vault, archive_b)
    )
    assert ordinary.preparation is not None, ordinary.code
    ordinary_plan = ordinary.preparation.review
    disappeared = next(
        c for c in ordinary_plan.proposal.changes if c.item_id == OLD_ASSET
    )
    assert (
        disappeared.disposition == "source_absent"
        and disappeared.result.data == LEGACY_CURRENT
    )
    assert all(a.choice != "remove" for a in disappeared.attachment_review.alternatives)
    assert (vault / OLD_PATH).read_bytes() == LEGACY_CURRENT
    resolution_limit = len(ordinary.preparation.review.requirements) + 2
    resolutions = 0
    while not ordinary.ready:
        assert resolutions < resolution_limit, ordinary.preparation.review.blockers
        resolutions += 1
        prepared = ordinary.preparation
        plan = prepared.review
        assert plan.requirements, plan.blockers
        requirement = plan.requirements[0]
        change = next(
            c for c in plan.proposal.changes if c.change_id == requirement.change_id
        )
        choice = (
            "approve"
            if "approve" in requirement.choices
            else "restore_incoming"
            if "restore_incoming" in requirement.choices
            else "incoming"
        )
        selection = candidate = None
        if change.attachment_review is not None:
            selection, candidate = incoming_attachment(plan, change)
        ordinary = remember(
            "ordinary-resolution-" + str(len(plan.actions)),
            operations.resolve_update(
                prepared,
                action(
                    plan,
                    change,
                    domain=requirement.domain,
                    choice=choice,
                    decision_id="explicit-source-B:" + change.subject_id,
                    attachment_selection=selection,
                    attachment_candidate=candidate,
                ),
            ),
        )
        assert ordinary.code == "accepted", (
            requirement.domain,
            requirement.choices,
            ordinary.code,
        )
    expected_source_b = all_bytes(Path(ordinary.preparation.payload_directory))
    source_b_version = ordinary.preparation.observed_source.snapshot_digest
    assert source_b_version != source_a_version and OLD_PATH not in expected_source_b
    assert expected_source_b[NEW_PATH] == ORIGINAL
    updated = remember(
        "ordinary-applied", operations.apply_update(ordinary.preparation)
    )
    assert updated.status == "applied", updated.code
    assert (vault / OLD_PATH).read_bytes() == LEGACY_CURRENT and (
        vault / NEW_PATH
    ).read_bytes() == ORIGINAL
    assert user_git(vault) == original_user_git

    note_before = (
        vault / NOTE_PATH
    ).read_bytes() + b"\nMy reference ![[Attachments/22222222/Notes.md.original]].\n"
    (vault / NOTE_PATH).write_bytes(note_before)
    untouched = {
        p: raw
        for p, raw in all_bytes(vault).items()
        if not p.startswith((".git/", ".brz2obsidian/"))
        and p not in (OLD_PATH, NOTE_PATH, "Manual.md")
    }
    cleanup = remember(
        "cleanup-preparation", operations.prepare_attachment_cleanup(vault)
    )
    assert cleanup.preparation is not None and not cleanup.ready, cleanup.code
    historical = next(
        s
        for s in cleanup.preparation.review.producer_facts.subjects
        if s.item_id == OLD_ASSET
    )
    assert (
        historical.baseline.status == "unknown"
        and historical.baseline.content is None
        and historical.incoming is None
    )
    assert historical.attachment.retained_ownership.source_version == source_a_version
    assert (
        cleanup.preparation.review.facts.format_operation.target_source_version
        == source_b_version
    )
    saved = remember(
        "cleanup-saved-unready", operations.save_update(cleanup.preparation)
    )
    assert saved.code == "saved" and not saved.ready, saved.code

    copy = root / "complete-owned-copy"
    shutil.copytree(vault, copy)
    copy_before, vault_before = all_bytes(copy), all_bytes(vault)
    matching = remember(
        "completed-claim-copy", operations.validate_history_copy(vault, copy)
    )
    assert matching.status == "matching", matching.code
    assert all_bytes(copy) == copy_before and all_bytes(vault) == vault_before
    resumed_path = root / "fresh-resume.json"
    script = (
        "from pathlib import Path\nimport sys\n"
        "from brz2obsidian.application.operations import Operations\n"
        "result = Operations().resume_update(sys.argv[1])\n"
        "Path(sys.argv[2]).write_text(result.model_dump_json(), encoding='utf-8')\n"
    )
    subprocess.run(
        [sys.executable, "-c", script, str(vault), str(resumed_path)],
        check=True,
        capture_output=True,
        timeout=150,
    )
    resumed = remember(
        "cleanup-fresh-resumed",
        UpdateResult.model_validate_json(resumed_path.read_bytes()),
    )
    assert (
        resumed.kind == "attachment_cleanup"
        and resumed.preparation is not None
        and not resumed.ready
    ), resumed.code
    prepared = resumed.preparation
    kept = operations.resolve_update(
        prepared, cleanup_asset_action(prepared.review, NEW_ASSET, "current")
    )
    assert kept.code == "accepted", kept.code
    prepared = kept.preparation
    expected_note = note_before.replace(
        b"![[Attachments/22222222/Notes.md.original]]", b""
    )
    expected_manual = b"Manual . `[[Attachments/22222222/Notes.md.original]]`\r\n"
    removed = remember(
        "cleanup-explicit-removal",
        operations.resolve_update(
            prepared,
            cleanup_asset_action(
                prepared.review,
                OLD_ASSET,
                "remove",
                document_edits={NOTE_PATH: expected_note, "Manual.md": expected_manual},
            ),
        ),
    )
    assert removed.code == "accepted" and removed.ready, (
        removed.code,
        removed.preparation.review.blockers,
    )
    stopped = remember(
        "cleanup-partially-stopped",
        operations.apply_update(
            removed.preparation,
            cancel=lambda: not (vault / OLD_PATH).exists(),
        ),
    )
    assert (
        stopped.status == "recovery_required"
        and stopped.application.published_files == 1
    ), stopped.code
    assert (
        not (vault / OLD_PATH).exists()
        and (vault / NOTE_PATH).read_bytes() == note_before
    )
    later = b"Later independent writing.\r\n"
    (vault / "Manual.md").write_bytes(manual + later)
    restarted = remember(
        "cleanup-restart", Operations().inspect_history_workflow(vault)
    )
    assert (
        restarted.status == "recovery_required"
        and restarted.operation.origin_role == "attachment_cleanup"
    )
    assert restarted.operation.kind == "apply" and restarted.next_actions == (
        "review_recovery",
    )
    finish = remember(
        "cleanup-finish-preparation",
        Operations().prepare_history_workflow(
            vault, kind="recovery", direction="finish"
        ),
    )
    assert finish.preparation is not None, finish.code
    finish = remember(
        "cleanup-finish-refreshed",
        Operations().refresh_history_workflow(finish.preparation),
    )
    assert finish.preparation is not None, finish.code
    resolution_limit = len(finish.preparation.native.review.requirements) + 2
    resolutions = 0
    while not finish.preparation.ready:
        assert resolutions < resolution_limit, finish.preparation.native.review.blockers
        resolutions += 1
        native = finish.preparation.native
        plan = native.review
        assert not plan.blockers, plan.blockers
        assert plan.requirements, plan.blockers
        requirement = plan.requirements[0]
        change = next(
            c for c in plan.proposal.changes if c.change_id == requirement.change_id
        )
        assert requirement.domain == "attachment" and "remove" in requirement.choices, (
            requirement.domain,
            requirement.choices,
        )
        finish = remember(
            "cleanup-finish-choice-" + str(len(plan.actions)),
            Operations().resolve_history_workflow(
                finish.preparation,
                cleanup_asset_action(
                    plan,
                    change.item_id,
                    "remove",
                    document_edits={
                        NOTE_PATH: expected_note,
                        "Manual.md": expected_manual + later,
                    },
                ),
            ),
        )
        assert finish.preparation is not None, finish.code
    completed = remember(
        "cleanup-finished", Operations().execute_history_workflow(finish.preparation)
    )
    assert (
        completed.status == "applied"
        and completed.operation.origin_role == "attachment_cleanup"
    ), completed.code
    assert not (vault / OLD_PATH).exists()
    assert (vault / NOTE_PATH).read_bytes() == expected_note
    assert (vault / "Manual.md").read_bytes() == expected_manual + later
    assert all((vault / path).read_bytes() == raw for path, raw in untouched.items())
    assert user_git(vault) == original_user_git
    checkpoint = operations.read_checkpoint(vault)
    assert checkpoint.status == "valid", checkpoint.code
    retained = operations.read_checkpoint_payload(
        vault,
        locator=checkpoint.locator,
        requests=tuple(
            CheckpointPayloadRequest(path=p, offset=0, limit=len(raw))
            for p, raw in sorted(expected_source_b.items())
        ),
        byte_limit=sum(map(len, expected_source_b.values())),
    )
    assert (
        retained.status == "available"
        and {chunk.path: chunk.data for chunk in retained.chunks} == expected_source_b
    )
    undo = remember("cleanup-no-older-undo", operations.prepare_undo(vault))
    assert undo.status == "none" and undo.code == "latest_operation_is_maintenance"
    assert undo.target_receipt_commit is None
    (vault / OLD_PATH).write_bytes(b"New manual file at the old name\x00")
    with operations.inspect_update_inputs(vault) as observed:
        assert (
            observed.read_attachment_ownership(
                locator=observed.history.checkpoint.locator, paths=(OLD_PATH,)
            )
            == ()
        )
    assert all_bytes(copy) == copy_before
    assert (vault / OLD_PATH).read_bytes() == b"New manual file at the old name\x00"
