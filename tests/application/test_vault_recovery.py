"""Public recovery choices over actual retained operation history and vault bytes."""

import json

from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ExactContent
from brz2obsidian.obsidian import inspect_text_candidate
from tests.application.test_vault_apply import (
    _apply,
    _binary_link_case,
    _ready_case,
    _renamed_case,
    _restored_note_case,
)
from tests.application.test_vault_checkpoints import user_state
from tests.reconciliation.test_resolution import action


def test_stopped_apply_offers_both_first_recovery_directions_without_mutation():
    vault, source, operations, reviewed, _ = _ready_case()
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    retained_user_state = user_state(vault)
    retained_owner = (vault / ".git/brz2obsidian/owner.json").read_bytes()

    offered = Operations().prepare_recovery(vault)

    assert offered.status == "offered" and offered.code == "initial_recovery_choice"
    assert offered.operation_id == stopped.operation_id
    assert offered.kind == "apply" and offered.generation == stopped.generation
    assert offered.intent_commit == stopped.intent_commit
    assert offered.available_directions == ("finish", "restore")
    assert offered.review is None
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault) == retained_user_state
    assert (vault / ".git/brz2obsidian/owner.json").read_bytes() == retained_owner

    # A copied owner marker is only a hint; the retained Git intent is the
    # authority after the original process has stopped.
    marker = vault / ".git/brz2obsidian"
    (marker / "owner.json").unlink()
    (marker / "held").unlink()
    marker.rmdir()
    missing_marker = Operations().prepare_recovery(vault)
    assert missing_marker.status == "offered"
    assert missing_marker.intent_commit == stopped.intent_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault) == retained_user_state

    # The edit happens after the stopped operation, so recovery must still be
    # discoverable while the new bytes await an explicit current review.
    (vault / "Notes/Opening.md").write_bytes(b"authored opening\r\nlater note\n")
    later = Operations().prepare_recovery(vault)
    assert later.status == "offered" and later.intent_commit == stopped.intent_commit
    assert later.available_directions == ("finish", "restore")
    assert (
        vault / "Notes/Opening.md"
    ).read_bytes() == b"authored opening\r\nlater note\n"

    reviewed_later = Operations().prepare_recovery(vault, direction="finish")
    assert reviewed_later.status == "offered"
    assert reviewed_later.direction == "finish"
    assert reviewed_later.review is not None
    assert reviewed_later.review.readiness == "review_required", (
        reviewed_later.review.blockers
    )
    assert reviewed_later.review.facts.subjects[0].current.content.data == (
        b"authored opening\r\nlater note\n"
    )
    assert reviewed_later.review.facts.generation > reviewed.proposal.generation
    assert (
        vault / "Notes/Opening.md"
    ).read_bytes() == b"authored opening\r\nlater note\n"

    restored_later = Operations().prepare_recovery(vault, direction="restore")
    assert restored_later.status == "offered" and restored_later.direction == "restore"
    assert restored_later.review is not None
    assert restored_later.review.readiness == "review_required", (
        restored_later.review.blockers
    )
    (reversal,) = restored_later.review.facts.subjects
    assert reversal.baseline.content.data == b"incoming opening\n"
    assert reversal.current.content.data == b"authored opening\r\nlater note\n"
    assert reversal.incoming.data == b"authored opening\r\n"
    assert (
        vault / "Notes/Opening.md"
    ).read_bytes() == b"authored opening\r\nlater note\n"

    assert [(r.domain, r.choices) for r in reviewed_later.review.requirements] == [
        ("text", ("current", "incoming", "edited"))
    ]
    kept = Operations().resolve_recovery(
        vault,
        reviewed_later,
        action(
            reviewed_later.review,
            domain="text",
            choice="current",
            decision_id="recovery:current:1",
        ),
    )
    assert kept.status == "offered" and kept.review.ready, kept.code
    assert kept.review.approvals[0].result.data == b"authored opening\r\nlater note\n"
    (vault / "Notes/Opening.md").write_bytes(
        b"authored opening\r\nlater note\nsecond later note\n"
    )
    after_later_edit = user_state(vault)
    stale = Operations().resolve_recovery(
        vault,
        kept,
        action(
            kept.review,
            domain="text",
            choice="incoming",
            decision_id="recovery:incoming:2",
        ),
    )
    assert stale.status == "refused" and stale.code == "recovery_review_stale"
    stale_execution = Operations().execute_recovery(vault, kept)
    assert stale_execution.status == "refused"
    assert stale_execution.code == "recovery_review_stale"
    assert stale_execution.recovery_required
    assert stale_execution.operation_id == stopped.operation_id
    assert stale_execution.intent_commit == stopped.intent_commit
    assert user_state(vault) == after_later_edit
    refreshed = Operations().refresh_recovery(vault, kept)
    assert refreshed.status == "offered" and refreshed.direction == "finish"
    assert refreshed.review.proposal.generation == kept.review.proposal.generation + 1
    assert refreshed.review.facts.subjects[0].current.content.data.endswith(
        b"second later note\n"
    )
    assert not refreshed.review.ready and refreshed.review.approvals == ()
    assert user_state(vault) == after_later_edit

    restored_current = Operations().refresh_recovery(vault, restored_later)
    assert restored_current.status == "offered" and not restored_current.review.ready
    assert [(r.domain, r.choices) for r in restored_current.review.requirements] == [
        ("text", ("current", "incoming", "edited"))
    ]
    restore_facts = restored_current.review.facts
    restore_subject = restore_facts.subjects[0]
    restore_links = restore_facts.link_context
    restore_candidate = inspect_text_candidate(
        ExactContent(data=b"authored opening\r\n"),
        identity=restore_facts.identity_inventory[0].identity,
        target=restore_subject.source_target,
        output_format=7,
        source_path=restore_subject.path,
        document_id=restore_links.incoming_documents[0].document_id,
        path_mode="vault",
        link_targets=restore_links.incoming_targets,
        link_target_facts=restore_links.incoming_target_facts,
        link_inventory="complete",
    )
    chosen_restore = Operations().resolve_recovery(
        vault,
        restored_current,
        action(
            restored_current.review,
            domain="text",
            choice="incoming",
            decision_id="recovery:restore:1",
            candidate=restore_candidate,
        ),
    )
    assert chosen_restore.status == "offered" and chosen_restore.review.ready
    completed = Operations().execute_recovery(vault, chosen_restore)
    assert completed.status == "restored" and completed.publication == "complete", (
        completed.code
    )
    assert completed.direction == "restore" and completed.receipt_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert Operations().inspect_update_status(vault).status == "restored"
    assert user_state(vault)["index"] == after_later_edit["index"]


def test_torn_owner_marker_refuses_recovery_preparation_without_touching_vault():
    vault, source, operations, reviewed, _ = _ready_case()
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    owner = vault / ".git/brz2obsidian/owner.json"
    owner.write_bytes(b'{"schema_id":"torn"')
    retained_user_state = user_state(vault)

    offered = Operations().prepare_recovery(vault)

    assert (
        offered.status == "unavailable" and offered.code == "operation_marker_invalid"
    )
    assert offered.available_directions == () and offered.review is None
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert owner.read_bytes() == b'{"schema_id":"torn"'
    assert user_state(vault) == retained_user_state


def test_missing_checkpoint_locator_reports_unknown_history_without_authored_mutation():
    vault, source, operations, reviewed, _ = _ready_case()
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    locator = vault / ".brz2obsidian/locator.json"
    locator.unlink()
    damaged_state = user_state(vault)

    observed = Operations().inspect_update_status(vault)
    offered = Operations().prepare_recovery(vault, direction="finish")
    gated = Operations().inspect_history(vault)

    assert observed.status == "unknown" and observed.recovery_required
    assert observed.publication == "unknown" and observed.history == "unknown"
    assert offered.status == "unavailable" and offered.review is None
    assert gated.status == "unavailable"
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert not locator.exists()
    assert user_state(vault) == damaged_state


def test_partial_binary_both_restore_retains_result_after_terminal_receipt_fault(
    monkeypatch,
):
    from brz2obsidian.publication import vault_recovery
    from brz2obsidian.publication.vault_replace import move_file
    from tests.application.test_vault_checkpoints import git

    retained_primary = b"\x00authored"
    vault, source, _, reviewed, before, changed_document = _binary_link_case()
    original_document = (vault / "Notes/Owner.md").read_bytes()
    created = vault / "Assets/data (incoming-ba7816bf).bin"

    class StopAfterActualFirstMove:
        calls = 0

        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            self.calls += 1
            if self.calls == 1:
                raise OSError("Stopped after actual new asset publication")

        def remove(self, target, destination):
            raise AssertionError("Original selected effect has no removal")

    stopped = _apply(
        Operations(vault_executor=StopAfterActualFirstMove()),
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert stopped.status == "incomplete" and stopped.recovery_required
    assert created.read_bytes() == b"abc"
    assert (vault / "Assets/data.bin").read_bytes() == retained_primary
    assert (vault / "Notes/Owner.md").read_bytes() == original_document
    assert (vault / "Notes/Owner.md").read_bytes() != changed_document
    retained = user_state(vault)

    offered = Operations().prepare_recovery(vault, direction="restore")
    assert offered.status == "offered" and offered.review is not None, offered.code
    assert any(
        requirement.domain == "reversal" for requirement in offered.review.requirements
    )
    proof = offered.review.facts.subjects[0].operation_reversal
    assert proof is not None
    assert [
        (row.path, row.produced.data, row.current.content.data, row.target)
        for row in proof.outputs
    ] == [("Assets/data (incoming-ba7816bf).bin", b"abc", b"abc", None)]
    assert created.read_bytes() == b"abc"
    assert (vault / "Notes/Owner.md").read_bytes() == original_document
    assert user_state(vault) == retained
    assert retained["index"] == before["index"]

    chosen = Operations().resolve_recovery(
        vault,
        offered,
        action(
            offered.review,
            domain="reversal",
            choice="reverse",
            decision_id="recovery:remove-generated-version",
        ),
    )
    assert chosen.status == "offered" and chosen.review.ready, (
        chosen.code,
        chosen.review.blockers if chosen.review else (),
        tuple(r.domain for r in chosen.review.requirements) if chosen.review else (),
    )
    from brz2obsidian.core import select_review_effects

    effects = select_review_effects(chosen.review)
    assert effects.status == "selected", effects.code
    assert effects.remove_paths == ("Assets/data (incoming-ba7816bf).bin",)
    assert (vault / "Assets/data.bin").read_bytes() == retained_primary
    real_journal = vault_recovery._journal

    def fail_terminal_receipt(git, name, record, **kwargs):
        if name == "receipt.json":
            raise OSError("Fixture stopped terminal receipt publication")
        return real_journal(git, name, record, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(vault_recovery, "_journal", fail_terminal_receipt)
        completed = Operations().execute_recovery(vault, chosen)
    assert completed.status == "content_complete" and completed.recovery_required
    assert completed.result_commit and completed.receipt_commit is None
    assert completed.publication == "complete" and completed.history == "result"
    assert git(vault, "cat-file", "-t", completed.result_commit).strip() == b"commit"
    assert not created.exists()
    assert (vault / "Assets/data.bin").read_bytes() == retained_primary
    assert (vault / "Notes/Owner.md").read_bytes() == original_document
    fresh = Operations().inspect_update_status(vault)
    assert fresh.status == "content_complete" and fresh.recovery_required
    assert fresh.history == "result" and fresh.result_commit == completed.result_commit
    assert fresh.receipt_commit is None
    assert user_state(vault)["index"] == before["index"]


def test_restore_retains_unaffected_automatic_source_subject_without_approval():
    vault, source, operations, reviewed, before = _ready_case(unaffected_auto=True)
    assert len(reviewed.approvals) == 1
    assert (vault / "Notes/Unchanged.md").read_bytes() == b"unchanged note\n"
    calls = 0

    def cancel_original():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel_original,
    )
    assert stopped.status == "cancelled" and stopped.recovery_required
    assert stopped.intent_commit and stopped.planned_files == 1
    assert (vault / "Notes/Unchanged.md").read_bytes() == b"unchanged note\n"
    offered = Operations().prepare_recovery(vault, direction="restore")
    assert offered.status == "offered" and offered.review is not None, offered.code
    assert [s.path for s in offered.review.facts.subjects] == ["Notes/Opening.md"]
    assert offered.review.facts.subjects[0].incoming.data == b"authored opening\r\n"
    assert (vault / "Notes/Unchanged.md").read_bytes() == b"unchanged note\n"
    assert user_state(vault)["index"] == before["index"]


def test_partial_approved_rename_selects_inverse_for_real_source_identity():
    from brz2obsidian.publication.vault_replace import move_file

    vault, source, _, reviewed, before = _renamed_case(local_name="Local.bin")

    class StopAfterActualPublication:
        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            raise OSError("Stopped after actual new-path publication")

        def remove(self, target, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            move_file(target, destination, replace=False)

    stopped = _apply(
        Operations(vault_executor=StopAfterActualPublication()),
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert stopped.status == "content_complete" and stopped.recovery_required
    assert not (vault / "Authored/Name.md").exists()
    assert (vault / "Notes/Opening.md").read_bytes() == b"new\r\n"
    assert (vault / "Local.bin").read_bytes() == b"user \xff\n"
    retained = user_state(vault)

    offered = Operations().prepare_recovery(vault, direction="restore")
    assert offered.status == "offered" and offered.review is not None, offered.code
    assert offered.operation_id == stopped.operation_id
    assert offered.review.facts.subjects[0].item_id == "entry:opening"
    assert (vault / "Local.bin").read_bytes() == b"user \xff\n"
    assert user_state(vault) == retained
    assert retained["index"] == before["index"]

    from brz2obsidian.core import select_review_effects

    facts = offered.review.facts
    subject = facts.subjects[0]
    proof = subject.operation_reversal
    assert proof is not None
    assert [
        (row.path, row.current.existence, row.target.data if row.target else None)
        for row in proof.outputs
    ] == [
        ("Authored/Name.md", "absent", b"base\r\n"),
        ("Notes/Opening.md", "present", None),
    ]
    old_target = next(
        target
        for target in proof.owned_targets
        if target.canonical_path == "Authored/Name.md"
    )
    incoming_doc = next(
        doc
        for doc in facts.link_context.incoming_documents
        if doc.source_path == "Authored/Name.md"
    )
    candidate = inspect_text_candidate(
        ExactContent(data=b"base\r\n"),
        identity=next(
            row.identity
            for row in facts.identity_inventory
            if row.identity is not None and row.identity.item_id == subject.item_id
        ),
        target=old_target.target,
        output_format=facts.incoming_identity.output_format,
        source_path="Authored/Name.md",
        document_id=incoming_doc.document_id,
        path_mode=incoming_doc.path_mode,
        link_targets=facts.link_context.incoming_targets,
        link_target_facts=facts.link_context.incoming_target_facts,
        link_inventory="complete",
    )
    chosen = Operations().resolve_recovery(
        vault,
        offered,
        action(
            offered.review,
            domain="reversal",
            choice="reverse",
            decision_id="recovery:inverse-rename",
            candidate=candidate,
        ),
    )
    assert chosen.status == "offered" and chosen.review.ready, chosen.code
    effects = select_review_effects(chosen.review)
    assert effects.status == "selected"
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Authored/Name.md", b"base\r\n")
    ]
    assert effects.remove_paths == ("Notes/Opening.md",)
    assert user_state(vault) == retained


def test_partial_approved_rename_finishes_with_reviewed_later_new_path_bytes():
    from brz2obsidian.core import select_review_effects
    from brz2obsidian.publication.vault_replace import move_file

    vault, source, _, reviewed, before = _renamed_case(local_name="Local.bin")

    class StopAfterActualPublication:
        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            raise OSError("Stopped after actual new-path publication")

        def remove(self, target, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            move_file(target, destination, replace=False)

    stopped = _apply(
        Operations(vault_executor=StopAfterActualPublication()),
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert stopped.status == "content_complete" and stopped.recovery_required
    assert not (vault / "Authored/Name.md").exists()
    assert (vault / "Notes/Opening.md").read_bytes() == b"new\r\n"

    (vault / "Authored/Name.md").write_bytes(b"independent third version\n")
    ambiguous = Operations().prepare_recovery(vault, direction="finish")
    assert ambiguous.status == "unavailable" and ambiguous.review is None
    assert (vault / "Authored/Name.md").read_bytes() == b"independent third version\n"
    assert (vault / "Notes/Opening.md").read_bytes() == b"new\r\n"
    (vault / "Authored/Name.md").unlink()

    later = b"new\r\nlater authored note\n"
    (vault / "Notes/Opening.md").write_bytes(later)
    retained = user_state(vault)
    offered = Operations().prepare_recovery(vault, direction="finish")
    assert offered.status == "offered" and offered.review is not None, offered.code
    assert offered.review.facts.subjects[0].current.path == "Notes/Opening.md"
    assert offered.review.facts.subjects[0].current.content.data == later
    assert offered.review.readiness == "review_required"
    assert [(r.domain, r.choices) for r in offered.review.requirements] == [
        ("text", ("current", "incoming", "edited"))
    ]
    assert user_state(vault) == retained

    chosen = Operations().resolve_recovery(
        vault,
        offered,
        action(
            offered.review,
            domain="text",
            choice="current",
            decision_id="recovery:finish-renamed-current",
        ),
    )
    assert chosen.status == "offered" and chosen.review.ready, chosen.code
    effects = select_review_effects(chosen.review)
    assert effects.status == "selected" and effects.remove_paths == ()
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Notes/Opening.md", later)
    ]
    assert user_state(vault) == retained

    completed = Operations().execute_recovery(vault, chosen)
    assert completed.status == "applied" and completed.receipt_commit, completed.code
    assert not (vault / "Authored/Name.md").exists()
    assert (vault / "Notes/Opening.md").read_bytes() == later
    assert (vault / "Local.bin").read_bytes() == b"user \xff\n"
    assert Operations().inspect_update_status(vault).status == "applied"
    after = user_state(vault)
    for key in ("index", "head", "config", "stages"):
        assert after[key] == before[key]


def test_stopped_rename_before_first_move_observes_real_old_path_identity():
    vault, source, operations, reviewed, before = _renamed_case(local_name="Local.bin")
    calls = 0

    def cancel_before_first_move():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel_before_first_move,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    assert stopped.published_files == 0 and stopped.recovery_required
    assert (vault / "Authored/Name.md").read_bytes() == b"base\r\n"
    assert not (vault / "Notes/Opening.md").exists()
    retained = user_state(vault)

    offered = Operations().prepare_recovery(vault, direction="finish")
    assert offered.status == "offered" and offered.review is not None, offered.code
    assert offered.review.facts.subjects[0].current.path == "Authored/Name.md"
    assert offered.review.facts.subjects[0].current.content.data == b"base\r\n"
    assert offered.review.ready, offered.review.blockers
    assert user_state(vault) == retained
    assert retained["index"] == before["index"]

    completed = Operations().execute_recovery(vault, offered)
    assert completed.status == "applied" and completed.receipt_commit, completed.code
    assert not (vault / "Authored/Name.md").exists()
    assert (vault / "Notes/Opening.md").read_bytes() == b"new\r\n"
    assert (vault / "Local.bin").read_bytes() == b"user \xff\n"
    assert Operations().inspect_update_status(vault).status == "applied"
    after = user_state(vault)
    for key in ("index", "head", "config", "stages"):
        assert after[key] == before[key]


def test_created_note_stop_retains_same_identity_for_finish_and_restore():
    from brz2obsidian.publication.vault_replace import move_file

    vault, source, _, reviewed, before = _restored_note_case()

    class StopAfterCreatedNote:
        def directory(self, stage, target):
            move_file(stage, target, replace=False)

        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            raise OSError("Stopped after the reviewed note became visible")

        def remove(self, target, destination):
            raise AssertionError("The reviewed creation has no removal")

    stopped = _apply(
        Operations(vault_executor=StopAfterCreatedNote()),
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert stopped.status == "content_complete" and stopped.recovery_required
    assert (vault / "Notes/Opening.md").read_bytes() == b"new note\n"
    retained = user_state(vault)

    finish = Operations().prepare_recovery(vault, direction="finish")
    restore = Operations().prepare_recovery(vault, direction="restore")
    for offered in (finish, restore):
        assert offered.status == "offered" and offered.review is not None, offered.code
        assert offered.operation_id == stopped.operation_id
        assert offered.review.facts.subjects[0].current.path == "Notes/Opening.md"
        assert offered.review.facts.subjects[0].current.content.data == b"new note\n"
    assert finish.review.ready, finish.review.blockers
    assert restore.review.facts.subjects[0].operation_reversal is not None
    assert user_state(vault) == retained

    completed = Operations().execute_recovery(vault, finish)
    assert completed.status == "applied" and completed.receipt_commit, completed.code
    assert (vault / "Notes/Opening.md").read_bytes() == b"new note\n"
    assert (vault / "Unrelated.md").read_bytes() == b"user remains\n"
    assert Operations().inspect_update_status(vault).status == "applied"
    after = user_state(vault)
    for key in ("index", "head", "config", "stages"):
        assert after[key] == before[key]


def test_large_retained_binary_is_read_for_a_public_restore_review():
    from hashlib import sha256

    from brz2obsidian.core import prepare_review, resolve_review
    from tests.application.test_vault_checkpoints import fixture_case, git
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
        binary_context,
    )

    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "Assets").mkdir()
    (source / "Assets").mkdir()
    retained = ExactContent(data=b"\x00" * (16 * 1024 * 1024 + 1))
    (vault / "Assets/data.bin").write_bytes(retained.data)
    (source / "Assets/data.bin").write_bytes(b"\x00original")
    facts = attachment_request()
    subject = facts.subjects[0].model_copy(
        update={
            "current": facts.subjects[0].current.model_copy(
                update={"content": retained}
            )
        }
    )
    facts = facts.model_copy(
        update={
            "subjects": (subject,),
            "identity_inventory": (
                facts.identity_inventory[0].model_copy(
                    update={"current": subject.current}
                ),
            ),
            "link_context": None,
        }
    )
    facts = facts.model_copy(update={"link_context": binary_context(facts)})
    operations = Operations()
    seeded = operations.capture_checkpoint(
        vault,
        source,
        vault_id="binary-vault",
        import_id="binary-import",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert seeded.status == "captured", seeded.code
    (source / "Assets/data.bin").write_bytes(b"abc")
    offered = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    selection, candidate = attachment_candidate(facts, "incoming")
    reviewed = resolve_review(
        offered,
        action(
            offered,
            domain="attachment",
            choice="incoming",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    assert reviewed.ready
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="binary-vault",
        import_id="binary-import",
        cancel=cancel,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    assert stopped.published_files == 0
    assert (
        sha256((vault / "Assets/data.bin").read_bytes()).digest()
        == sha256(retained.data).digest()
    )
    restored = Operations().prepare_recovery(vault, direction="restore")
    assert restored.status == "offered" and restored.review is not None, restored.code
    assert restored.review.facts.subjects[0].incoming == retained
    assert (
        sha256((vault / "Assets/data.bin").read_bytes()).digest()
        == sha256(retained.data).digest()
    )


def test_ready_stopped_apply_finishes_through_retained_direction_and_actual_result():
    vault, source, operations, reviewed, before = _ready_case()
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    (source / "Notes/Opening.md").unlink()
    assert not (source / "Notes/Opening.md").exists()
    offer = Operations().prepare_recovery(vault, direction="finish")
    assert offer.status == "offered" and offer.review.ready, (
        offer.code,
        len(offer.review.approvals) if offer.review else None,
        offer.review.history.events[-1].changed_keys if offer.review else None,
    )
    old_owner = (vault / ".git/brz2obsidian/owner.json").read_bytes()
    old_held = (vault / ".git/brz2obsidian/held").read_bytes()

    completed = Operations().execute_recovery(vault, offer)
    assert completed.status == "applied" and completed.publication == "complete", (
        completed.code,
        completed.phase,
        completed.history,
    )
    assert completed.intent_commit and completed.receipt_commit
    assert completed.direction == "finish" and completed.kind == "apply"
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    fresh = Operations().inspect_update_status(vault)
    assert (
        fresh.status == "applied" and fresh.receipt_commit == completed.receipt_commit
    )
    assert user_state(vault)["index"] == before["index"]

    # Reintroduce only the exact old fixture-owned marker to model a failed
    # final directory cleanup after the real result and receipt were retained.
    marker = vault / ".git/brz2obsidian"
    marker.mkdir()
    (marker / "owner.json").write_bytes(old_owner)
    (marker / "held").write_bytes(old_held)
    pending = Operations().inspect_update_status(vault)
    assert (
        pending.status == "content_complete"
        and pending.code == "terminal_cleanup_required"
    )
    cleanup = Operations().prepare_recovery(vault)
    assert cleanup.status == "cleanup" and cleanup.review is None
    assert Operations().prepare_recovery(vault, direction="restore").status == "refused"
    after_cleanup = Operations().execute_recovery(vault, cleanup)
    assert (
        after_cleanup.status == "applied"
        and after_cleanup.receipt_commit == completed.receipt_commit
    )
    assert not marker.exists()


def test_fully_published_apply_without_receipt_finishes_as_applied_with_zero_new_moves():
    from brz2obsidian.publication.vault_replace import move_file

    vault, source, _, reviewed, before = _ready_case()

    class StopAfterActualMove:
        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)
            raise OSError("Stopped after exact authored replacement")

        def remove(self, target, destination):
            raise AssertionError("This selected update has no removal")

    stopped = _apply(
        Operations(vault_executor=StopAfterActualMove()),
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert stopped.status == "content_complete" and stopped.recovery_required
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    retained_user_state = user_state(vault)

    offered = Operations().prepare_recovery(vault, direction="finish")
    assert offered.status == "offered" and offered.review.ready, offered.code
    completed = Operations().execute_recovery(vault, offered)

    assert completed.status == "applied" and completed.publication == "complete", (
        completed.code
    )
    assert completed.planned_files == completed.published_files == 0
    assert completed.authored_files_changed is False
    assert completed.receipt_commit and completed.result_commit
    assert Operations().inspect_update_status(vault).status == "applied"
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    after = user_state(vault)
    for key in ("index", "head", "config", "stages", "authored"):
        assert after[key] == retained_user_state[key]
    checkpoint_ref = json.loads((vault / ".brz2obsidian/locator.json").read_bytes())[
        "association"
    ]["ref"]
    assert checkpoint_ref.endswith("/checkpoints")
    operation_ref = (
        checkpoint_ref.removesuffix("/checkpoints")
        + "/operations/"
        + stopped.operation_id
    )
    owned_refs = {checkpoint_ref.encode(), operation_ref.encode()}
    assert tuple(
        row for row in after["refs"] if row.split(b" ", 1)[0] not in owned_refs
    ) == tuple(
        row
        for row in retained_user_state["refs"]
        if row.split(b" ", 1)[0] not in owned_refs
    )
    assert retained_user_state["index"] == before["index"]


def test_pre_intent_recovery_cleanup_fault_returns_typed_recovery_required(monkeypatch):
    from pathlib import Path

    vault, source, operations, reviewed, before = _ready_case()
    calls = 0

    def cancel_original():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel_original,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    offered = Operations().prepare_recovery(vault, direction="finish")
    assert offered.status == "offered" and offered.review.ready
    owner = vault / ".git/brz2obsidian/owner.json"
    original_unlink = Path.unlink

    def fail_owned_cleanup(path, *args, **kwargs):
        if path == owner:
            raise OSError("Fixture owner cleanup fault")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_owned_cleanup)
        failed = Operations().execute_recovery(vault, offered, cancel=lambda: True)

    assert failed.code == "recovery_cleanup_failed"
    assert failed.recovery_required and failed.operation_id == stopped.operation_id
    assert failed.intent_commit == stopped.intent_commit
    assert failed.publication == "unknown" and failed.published_files == 0
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    assert user_state(vault)["index"] == before["index"]
    assert Operations().inspect_history(vault).admission.status == "recovery_first"
    marker = owner.parent
    owner.unlink()
    (marker / "held").unlink()
    marker.rmdir()


def test_cancel_after_recovery_preparation_retains_stopped_authority_for_retry():
    vault, source, operations, reviewed, before = _ready_case()
    calls = 0

    def cancel_original():
        nonlocal calls
        calls += 1
        return calls == 2

    stopped = _apply(
        operations,
        vault,
        source,
        review=reviewed,
        vault_id="vault-one",
        import_id="import-one",
        cancel=cancel_original,
    )
    assert stopped.status == "cancelled" and stopped.intent_commit
    offered = Operations().prepare_recovery(vault, direction="finish")
    assert offered.status == "offered" and offered.review.ready
    owned = user_state(vault)

    cancelled = Operations().execute_recovery(vault, offered, cancel=lambda: True)
    assert (
        cancelled.status == "cancelled"
        and cancelled.code == "cancelled_before_recovery_intent"
    )
    assert cancelled.phase == "prepared" and cancelled.recovery_required
    assert cancelled.operation_id == stopped.operation_id
    assert cancelled.intent_commit == stopped.intent_commit
    assert cancelled.checkpoint_commit != stopped.checkpoint_commit
    assert cancelled.publication == stopped.publication
    assert cancelled.published_files == stopped.published_files
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored opening\r\n"
    after_cancel = user_state(vault)
    for key in ("index", "head", "config", "stages", "authored"):
        assert after_cancel[key] == owned[key]
    assert after_cancel["index"] == before["index"]

    fresh = Operations().inspect_update_status(vault)
    assert fresh.operation_id == stopped.operation_id
    assert fresh.intent_commit == stopped.intent_commit and fresh.recovery_required
    assert fresh.status in {"cancelled", "incomplete", "content_complete"}, fresh.code
    retry = Operations().prepare_recovery(vault, direction="finish")
    assert retry.status == "offered" and retry.review.ready, retry.code
    finished = Operations().execute_recovery(vault, retry)
    assert finished.status == "applied" and finished.receipt_commit, finished.code
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    assert Operations().inspect_update_status(vault).status == "applied"
