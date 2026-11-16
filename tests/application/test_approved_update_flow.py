"""Approved setup and unresolved-only group decisions at supported public seams."""

from tests.application.test_onboarding_originals import (
    CURRENT,
    ORIGINAL,
    controlled_history,
    legacy_brz_case,
)


def test_known_original_setup_automatically_preserves_local_edits(
    tmp_path, monkeypatch
):
    operations, vault, archive = legacy_brz_case(tmp_path)
    controlled_history(operations, vault, monkeypatch)
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    offered = operations.prepare_onboarding(vault, archive, original_source=archive)
    assert offered.preparation is not None, offered
    review = offered.preparation.review
    note = next(
        s
        for s in review.facts.subjects
        if s.item_id == "22222222-2222-4222-8222-222222222222"
    )
    assert note.baseline.content.data == ORIGINAL
    assert note.current.content.data == CURRENT
    assert review.ready, review.requirements
    change = next(c for c in review.proposal.changes if c.item_id == note.item_id)
    assert change.result.data == CURRENT
    assert not review.requirements
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    } == before


def test_supported_review_automatically_selects_incoming_and_independent_merge():
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import preflight, with_review_links
    from tests.reconciliation.test_structure import structured_request

    for facts, expected in (
        (request(), b"incoming\n"),
        (
            structured_request(
                b"First old.\nMiddle.\nLast old.\n",
                b"First local.\nMiddle.\nLast old.\n",
                b"First old.\nMiddle.\nLast source.\n",
            ),
            b"First local.\nMiddle.\nLast source.\n",
        ),
    ):
        from brz2obsidian.application.update_facts import automatic_merge_facts

        review = prepare_review(
            automatic_merge_facts(with_review_links(facts)), preflight=preflight()
        )
        assert review.ready, review.requirements
        effects = select_review_effects(review)
        assert effects.status == "selected", effects
        assert [(f.path, f.content.data) for f in effects.files] == [
            ("Notes/Opening.md", expected)
        ]


def mixed_facts(*, conflict_count=None):
    from brz2obsidian.contracts import FormatBaselineOutput, ImportedItemIdentity
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import with_review_links

    base = request()
    subjects, inventory, outputs = [], [], []
    conflicts = (
        ("one", "two")
        if conflict_count is None
        else tuple(f"conflict-{number:03}" for number in range(conflict_count))
    )
    rows = (("clean", b"original\r\n"), ("prior", b"prior local\n")) + tuple(
        (name, f"{name} local\n".encode()) for name in conflicts
    )
    for name, current in rows:
        row = request(current=current)
        subject = row.subjects[0].model_copy(
            update={
                "item_id": name,
                "path": f"Notes/{name}.md",
                "current": row.subjects[0].current.model_copy(
                    update={"path": f"Notes/{name}.md"}
                ),
                "source_target": row.subjects[0].source_target.model_copy(
                    update={"normalized_path": f"notes/{name}.md"}
                ),
            }
        )
        subjects.append(subject)
        inventory.append(
            row.identity_inventory[0].model_copy(
                update={
                    "entry_id": name,
                    "current": subject.current,
                    "target": subject.source_target,
                    "identity": ImportedItemIdentity(
                        collection_id=base.incoming_identity.collection_id,
                        module_id=base.incoming_identity.module_id,
                        item_id=name,
                    ),
                }
            )
        )
        outputs.append(
            FormatBaselineOutput(
                item_id=name, facet="content", content=subject.baseline.content
            )
        )
    operation = base.format_operation.model_copy(
        update={
            "automatic_merge": True,
            "established_baseline": base.format_operation.established_baseline.model_copy(
                update={"outputs": tuple(outputs)}
            ),
        }
    )
    return with_review_links(
        base.model_copy(
            update={
                "subjects": tuple(subjects),
                "identity_inventory": tuple(inventory),
                "format_operation": operation,
            }
        )
    )


def test_worker_bulk_keeps_only_unresolved_preserving_incoming_and_clean(tmp_path):
    from types import SimpleNamespace

    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.update_context import UpdateContext
    from brz2obsidian.application.update_contracts import UpdateResult
    from tests.application.test_update_context import worker_context_call
    from tests.application.test_update_lifecycle_contracts import preparation

    prepared = preparation(mixed_facts()).model_copy(update={"vault": str(tmp_path)})

    class Inputs(Operations):
        def prepare_update(self, vault, source):
            return UpdateResult(
                status="unresolved",
                code="prepared",
                preparation=prepared,
                changes=4,
                unresolved=3,
            )

        def read_checkpoint(self, vault, **kwargs):
            return SimpleNamespace(status="valid", locator=prepared.locator)

    context = UpdateContext(operations=Inputs())

    def send(command, **values):
        return worker_context_call(context, {"command": command, **values})

    opened = send(
        "prepare",
        vault=str(tmp_path),
        source=str(tmp_path / "incoming.brz"),
        selection_id="11111111-1111-4111-8111-111111111111",
        kind="source_update",
    )
    assert opened.keep_current_count == 3
    offered = send("choices", binding=opened.binding, queue="unresolved")
    prior = next(
        o
        for o in offered.offers
        if o.change_id == prepared.review.proposal.changes[1].change_id
    )
    selected = send(
        "choose",
        binding=opened.binding,
        requirement_id=prior.requirement_id,
        choice="incoming",
        assumptions_digest=prior.assumptions_digest,
    )
    assert selected.keep_current_count == 2
    grouped = send(
        "keep_current_unresolved",
        binding=selected.binding,
        group_id=selected.keep_current_group_id,
    )
    assert grouped.affected_conflicts == 2 and grouped.ready and grouped.unresolved == 0
    page = send("page", binding=grouped.binding)
    assert {r.item_id: r.result for r in page.page.items} == {
        "clean": b"incoming\n",
        "prior": b"incoming\n",
        "one": b"one local\n",
        "two": b"two local\n",
    }
    assert send("page", binding=grouped.binding, queue="unresolved").page.total == 0


def test_group_history_cold_replay_and_selective_refresh(tmp_path):
    import json
    import subprocess
    import sys

    from brz2obsidian.application.review_choices import keep_current_group_action
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import (
        prepare_review,
        refresh_review,
        resolve_review,
        select_review_effects,
    )
    from brz2obsidian.core.resolution import unresolved_current_scope
    from tests.reconciliation.test_resolution import preflight, with_review_links

    facts = mixed_facts()
    plan = prepare_review(facts, preflight=preflight())
    digest, _ = unresolved_current_scope(plan)
    event = keep_current_group_action(plan, digest)
    accepted = resolve_review(plan, event)
    assert accepted.status == "accepted" and accepted.plan.ready
    assert len(accepted.plan.history.events) == 1
    assert len(accepted.plan.actions) == 3
    path = tmp_path / "group.json"
    path.write_text(accepted.plan.model_dump_json())
    assert '"automatic_merge":true' in path.read_text()
    code = """import json,sys
from pathlib import Path
from brz2obsidian.contracts import ReviewPlan
from brz2obsidian.core import validate_review, select_review_effects
plan=ReviewPlan.model_validate_json(Path(sys.argv[1]).read_text())
checked=validate_review(plan)
effects=select_review_effects(plan)
print(json.dumps({"valid":checked.status,"files":{f.path:f.content.data.decode() for f in effects.files}}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(path)], capture_output=True, check=False
    )
    assert completed.returncode == 0, completed.stderr.decode()
    assert json.loads(completed.stdout) == {
        "valid": "accepted",
        "files": {
            "Notes/clean.md": "incoming\n",
            "Notes/prior.md": "prior local\n",
            "Notes/one.md": "one local\n",
            "Notes/two.md": "two local\n",
        },
    }
    # Refresh one actual current version; the two independent prior choices survive.
    subject = facts.subjects[2]
    current = subject.current.model_copy(
        update={"content": ExactContent(data=b"one later edit\n")}
    )
    changed = facts.model_copy(
        update={
            "generation": 2,
            "link_context": None,
            "subjects": tuple(
                s.model_copy(update={"current": current}) if s.item_id == "one" else s
                for s in facts.subjects
            ),
            "identity_inventory": tuple(
                e.model_copy(update={"current": current}) if e.entry_id == "one" else e
                for e in facts.identity_inventory
            ),
        }
    )
    refreshed = refresh_review(
        accepted.plan, with_review_links(changed), preflight=preflight()
    )
    assert refreshed.status == "accepted", refreshed
    assert {a.change_id for a in refreshed.plan.approvals} == {
        a.change_id
        for a in accepted.plan.approvals
        if a.change_id != accepted.plan.proposal.changes[2].change_id
    }
    assert len(refreshed.plan.requirements) == 1
    assert select_review_effects(refreshed.plan).status == "refused"


def test_group_rejects_changed_scope_forgery_and_keeps_unsafe_choices_visible():
    from brz2obsidian.application.review_choices import keep_current_group_action
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.core.resolution import unresolved_current_scope
    from tests.reconciliation.test_resolution import preflight

    plan = prepare_review(mixed_facts(), preflight=preflight())
    digest, _ = unresolved_current_scope(plan)
    event = keep_current_group_action(plan, digest)
    for forged in (
        event.model_copy(update={"group_id": "0" * 64}),
        event.model_copy(update={"actions": event.actions[:-1]}),
        event.model_copy(
            update={
                "actions": (event.actions[0].model_copy(update={"choice": "incoming"}),)
                + event.actions[1:]
            }
        ),
        event.model_copy(
            update={
                "actions": (
                    event.actions[0].model_copy(update={"reviewed_assumptions": ()}),
                )
                + event.actions[1:]
            }
        ),
    ):
        refused = resolve_review(plan, forged)
        assert (
            refused.status != "accepted"
            and refused.plan.approvals == ()
            and refused.plan.history.events == ()
        )
    facts = mixed_facts()
    unsafe = facts.safety_facts[0].model_copy(
        update={"key": "unsafe-one", "subjects": ("one",), "status": "unsafe"}
    )
    blocked = prepare_review(
        facts.model_copy(update={"safety_facts": facts.safety_facts + (unsafe,)}),
        preflight=preflight(),
    )
    # Other safe conflicts remain eligible; one unsafe identity retains its blocker.
    digest, members = unresolved_current_scope(blocked)
    assert len(members) == 2
    grouped = resolve_review(blocked, keep_current_group_action(blocked, digest))
    assert grouped.status == "accepted" and not grouped.plan.ready
    assert len(grouped.plan.requirements) == 1 and grouped.plan.blockers


def test_setup_accepts_distinct_trusted_original_and_incoming(tmp_path, monkeypatch):
    import hashlib
    import json
    from zipfile import ZipFile

    operations, vault, original = legacy_brz_case(tmp_path)
    controlled_history(operations, vault, monkeypatch)
    incoming = tmp_path / "incoming.brz"
    with ZipFile(original) as old, ZipFile(incoming, "w") as new:
        for name in old.namelist():
            raw = old.read(name)
            if name.endswith("/Notes.md"):
                raw = b"Incoming prose.\r\n"
            if name == "attachments.json":
                record = json.loads(raw)
                record["DataLength"] = 17
                raw = json.dumps(record).encode()
            new.writestr(name, raw)
    original_sha = hashlib.sha256(original.read_bytes()).hexdigest()
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    offered = operations.prepare_onboarding(vault, incoming, original_source=original)
    assert offered.preparation is not None, offered
    note = next(
        s
        for s in offered.preparation.review.facts.subjects
        if s.item_id == "22222222-2222-4222-8222-222222222222"
    )
    assert note.baseline.content.data == ORIGINAL
    assert note.current.content.data == CURRENT
    assert b"Incoming prose." in note.incoming.data
    assert note.incoming.data != note.baseline.content.data
    assert not offered.preparation.review.blockers, offered.preparation.review.blockers
    assert all(r.domain != "format" for r in offered.preparation.review.requirements)
    assert hashlib.sha256(original.read_bytes()).hexdigest() == original_sha
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    } == before


def test_known_configuration_incoming_change_needs_no_routine_confirmation():
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import preflight, with_review_links

    facts = request(
        original=b"setting: old\n",
        current=b"setting: old\n",
        incoming=b"setting: new\n",
    )
    facts = facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(update={"output_role": "configuration"}),
            )
        }
    )
    review = prepare_review(
        automatic_merge_facts(with_review_links(facts)), preflight=preflight()
    )
    assert review.ready, review.requirements
    assert select_review_effects(review).files[0].content.data == b"setting: new\n"


def test_source_only_binary_automatically_preserves_authored_link_document():
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_attachments import linked_attachment_request
    from tests.reconciliation.test_resolution import preflight

    raw = b"Authored [[Assets/data.bin|Retained wording]].\r\n"
    facts = linked_attachment_request(payload_current=b"\x00original", raw=raw)
    facts = facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(update={"interpretation": "opaque"}),
            )
        }
    )
    plan = prepare_review(automatic_merge_facts(facts), preflight=preflight())
    assert plan.ready, plan.requirements
    selected = select_review_effects(plan)
    assert selected.status == "selected"
    files = {f.path: f.content.data for f in selected.files}
    assert files["Assets/data.bin"] == b"abc"
    assert files.get("Notes/Owner.md", raw) == raw


def test_owned_worker_group_cancel_save_partial_close_and_resume(monkeypatch):
    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_owned_update_controls import _native_controls_case
    from tests.application.test_update_context import worker_context_call

    case = _native_controls_case(monkeypatch)
    context = UpdateContext()

    def send(command, **values):
        return worker_context_call(context, {"command": command, **values})

    selection_id = "11111111-1111-4111-8111-111111111111"
    opened = send(
        "prepare",
        vault=str(case.vault),
        source=str(case.incoming_archive),
        selection_id=selection_id,
        kind="source_update",
    )
    assert opened.binding is not None, opened
    assert opened.keep_current_count >= 2
    cancellation_checks = []

    def cancel_after_entry():
        cancellation_checks.append(True)
        return len(cancellation_checks) > 1

    cancelled = context.keep_current_unresolved(
        opened.binding, group_id=opened.keep_current_group_id, cancel=cancel_after_entry
    )
    assert (
        cancelled.status == "cancelled_before_publication"
        and cancelled.affected_conflicts == 0
    )
    assert len(cancellation_checks) >= 2
    assert cancelled.binding == opened.binding
    page = send("page", binding=opened.binding, queue="unresolved", byte_limit=0)
    note = next(r for r in page.page.items if r.current_path == case.note_path)
    offer = next(o for o in page.offers if o.change_id == note.change_id)
    partial = send(
        "choose",
        binding=opened.binding,
        requirement_id=offer.requirement_id,
        choice="current",
        assumptions_digest=offer.assumptions_digest,
    )
    assert (
        partial.code == "accepted"
        and partial.keep_current_count < opened.keep_current_count
    )
    stale = send(
        "keep_current_unresolved",
        binding=opened.binding,
        group_id=opened.keep_current_group_id,
    )
    assert stale.code == "context_changed" and stale.affected_conflicts == 0
    saved = send("save", binding=partial.binding)
    assert saved.code == "saved" and saved.unresolved > 0, saved
    closed = send("close", binding=saved.binding, choice="discard")
    assert closed.code == "context_closed", closed
    reopened = UpdateContext()
    resumed = worker_context_call(
        reopened,
        {"command": "resume", "vault": str(case.vault), "selection_id": selection_id},
    )
    assert resumed.binding is not None and resumed.unresolved > 0, resumed
    assert resumed.keep_current_count == partial.keep_current_count
    # The full current inventory is rechecked once before admitting the group.
    path = case.vault / case.note_path
    path.write_bytes(case.current_note + b"Between-review edit.\r\n")
    changed = worker_context_call(
        reopened,
        {
            "command": "keep_current_unresolved",
            "binding": resumed.binding,
            "group_id": resumed.keep_current_group_id,
        },
    )
    assert changed.code == "current_inputs_changed" and changed.affected_conflicts == 0
    assert path.read_bytes() == case.current_note + b"Between-review edit.\r\n"
    refreshed = worker_context_call(
        reopened, {"command": "refresh", "binding": resumed.binding}
    )
    assert refreshed.binding is not None and refreshed.stale > 0, refreshed
    grouped = worker_context_call(
        reopened,
        {
            "command": "keep_current_unresolved",
            "binding": refreshed.binding,
            "group_id": refreshed.keep_current_group_id,
        },
    )
    assert grouped.code == "accepted" and grouped.ready and grouped.unresolved == 0, (
        grouped
    )
    assert grouped.affected_conflicts == refreshed.keep_current_count
    # Review actions and Save never publish either authored version.
    assert (
        case.vault / case.note_path
    ).read_bytes() == case.current_note + b"Between-review edit.\r\n"
    assert (case.vault / case.asset_path).read_bytes() == case.current


def test_new_output_uses_proven_absence_without_inventing_original():
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.contracts import ContentVersion, CurrentContent
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import preflight, with_review_links

    facts = request(incoming=b"New source note.\n")
    absent = CurrentContent(existence="absent", path="Notes/Opening.md", content=None)
    subject = facts.subjects[0].model_copy(
        update={
            "baseline": ContentVersion(
                status="unknown", content=None, unavailable_digest=None
            ),
            "current": absent,
        }
    )
    operation = facts.format_operation.model_copy(
        update={
            "established_baseline": facts.format_operation.established_baseline.model_copy(
                update={"outputs": ()}
            )
        }
    )
    facts = facts.model_copy(
        update={
            "subjects": (subject,),
            "identity_inventory": (
                facts.identity_inventory[0].model_copy(update={"current": absent}),
            ),
            "format_operation": operation,
        }
    )
    review = prepare_review(
        automatic_merge_facts(with_review_links(facts)), preflight=preflight()
    )
    assert review.ready, review.requirements
    assert review.facts.subjects[0].baseline.content is None
    effects = select_review_effects(review)
    assert (
        effects.status == "selected"
        and effects.files[0].content.data == b"New source note.\n"
    )


def test_group_scales_as_one_canonical_event_with_individual_traceability():
    from time import perf_counter

    from brz2obsidian.application.review_choices import keep_current_group_action
    from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
    from brz2obsidian.core.resolution import unresolved_current_scope
    from tests.reconciliation.test_resolution import preflight

    started = perf_counter()
    plan = prepare_review(mixed_facts(conflict_count=64), preflight=preflight())
    digest, members = unresolved_current_scope(plan)
    assert len(members) == 65
    grouped = resolve_review(plan, keep_current_group_action(plan, digest))
    assert grouped.status == "accepted" and grouped.plan.ready
    assert len(grouped.plan.history.events) == 1
    assert len(grouped.plan.approvals) == len(grouped.plan.actions) == 65
    files = {f.path: f.content.data for f in select_review_effects(grouped.plan).files}
    assert files["Notes/clean.md"] == b"incoming\n"
    assert files["Notes/conflict-000.md"] == b"conflict-000 local\n"
    assert files["Notes/conflict-063.md"] == b"conflict-063 local\n"
    print(
        f"65 unresolved conflicts: one canonical group event; elapsed {perf_counter() - started:.3f}s"
    )


def test_fresh_automatic_flow_retains_valid_legacy_decision():
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.core import prepare_review, refresh_review, resolve_review
    from tests.reconciliation.test_resolution import action, preflight

    facts = mixed_facts()
    facts = facts.model_copy(
        update={
            "format_operation": facts.format_operation.model_copy(
                update={"automatic_merge": False}
            )
        }
    )
    legacy = prepare_review(facts, preflight=preflight())
    assert '"automatic_merge"' not in legacy.model_dump_json()
    prior = legacy.proposal.changes[1]
    accepted = resolve_review(legacy, action(legacy, prior, choice="current"))
    assert accepted.status == "accepted"
    fresh = automatic_merge_facts(facts.model_copy(update={"generation": 2}))
    refreshed = refresh_review(accepted.plan, fresh, preflight=preflight())
    assert refreshed.status == "accepted"
    assert [a.decision_id for a in refreshed.plan.approvals] == ["review:decision:1"]
    assert refreshed.plan.approvals[0].result.data == b"prior local\n"
    assert all(
        r.change_id != refreshed.plan.proposal.changes[0].change_id
        for r in refreshed.plan.requirements
    )
    assert refreshed.plan.facts.format_operation.automatic_merge


def first_setup_operations():
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.wiring import default_workflow
    from tests.application.test_module_seams import METADATA
    from tests.application.test_onboarding import owned_case
    from tests.application.test_vault_checkpoints import git

    # Native Git fixtures use their retained short owned root on Windows.
    _, vault, archive = legacy_brz_case(owned_case())
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    manual = vault / "Manual.md"
    manual.write_bytes(b"Independent authoring.\r\n")
    (vault / "Attachments/manual.bin").write_bytes(b"\x00\xffIndependent binary.\r\n")
    git(vault, "add", "Manual.md", "Attachments/manual.bin")
    git(vault, "commit", "-qm", "Independent authoring")
    git(vault, "branch", "independent-user-branch")
    git(vault, "update-ref", "refs/notes/independent-user-proof", "HEAD")
    manual.write_bytes(b"Staged independent writing.\r\n")
    git(vault, "add", "Manual.md")
    manual.write_bytes(b"Unstaged independent writing.\r\n")
    workflow = default_workflow()
    workflow.metadata_factory = lambda: METADATA
    return Operations(workflow=workflow), vault, archive


def first_setup_context():
    from brz2obsidian.application.update_context import UpdateContext

    operations, vault, archive = first_setup_operations()
    context = UpdateContext(operations=operations)
    opened = context.prepare(
        str(vault),
        source=str(archive),
        original_source=str(archive),
        kind="onboarding",
        selection_id="11111111-1111-4111-8111-111111111111",
    )
    assert opened.ready and opened.binding is not None, opened
    return context, operations, opened, vault, archive


def all_refs(vault):
    from tests.application.test_vault_checkpoints import git

    return dict(
        line.split(b" ", 1)
        for line in git(
            vault, "for-each-ref", "--format=%(refname) %(objectname)"
        ).splitlines()
    )


def assert_only_owned_history_refs_added(vault, before, checkpoint):
    after = all_refs(vault)
    assert all(after.get(name) == value for name, value in before.items())
    checkpoint_ref = checkpoint.locator.association.ref.encode()
    operation_prefix = checkpoint_ref.rsplit(b"/", 1)[0] + b"/operations/"
    assert all(
        name == checkpoint_ref or name.startswith(operation_prefix)
        for name in after.keys() - before.keys()
    )


def test_first_apply_captures_separate_original_and_current_without_manual_save():
    import hashlib

    from tests.application.test_update_lifecycle import _user_state

    context, operations, opened, vault, archive = first_setup_context()
    assert "apply_update" in opened.next_actions
    assert not (vault / ".brz2obsidian/locator.json").exists()
    before, refs = _user_state(vault), all_refs(vault)
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    applied = context.apply(opened.binding)
    assert applied.status in ("no_content_change", "applied"), applied
    assert applied.history_retained and applied.capture is not None, applied
    checkpoint = operations.read_checkpoint(vault)
    assert checkpoint.status == "valid" and checkpoint.manifest.boundary == "result"
    source_note = next(
        r
        for r in checkpoint.manifest.source
        if r.path == "Home \u2014 Entry thought.md"
    )
    current_note = next(
        r for r in checkpoint.manifest.vault if r.path == "Home \u2014 Entry thought.md"
    )
    assert source_note.sha256 == hashlib.sha256(ORIGINAL).hexdigest()
    assert current_note.sha256 == hashlib.sha256(CURRENT).hexdigest()
    assert (vault / "Home \u2014 Entry thought.md").read_bytes() == CURRENT
    assert (vault / "Manual.md").read_bytes() == b"Unstaged independent writing.\r\n"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive_sha
    assert _user_state(vault) == before
    assert_only_owned_history_refs_added(vault, refs, checkpoint)


def test_first_apply_stop_after_checkpoint_retains_review_and_user_state(monkeypatch):
    from tests.application.test_onboarding_completion import authored_files
    from tests.application.test_update_lifecycle import _user_state

    operations, vault, archive = first_setup_operations()
    prepared = operations.prepare_onboarding(vault, archive, original_source=archive)
    assert prepared.ready and prepared.preparation.locator is None, prepared
    before, refs, files = _user_state(vault), all_refs(vault), authored_files(vault)
    captured = []
    native_capture = operations.capture_checkpoint

    def capture(*args, **kwargs):
        result = native_capture(*args, **kwargs)
        captured.append(result)
        return result

    # This is the native history port: cancel after its real durable reply.
    monkeypatch.setattr(operations, "capture_checkpoint", capture)
    stopped = operations.apply_update(
        prepared.preparation, cancel=lambda: bool(captured)
    )
    assert stopped.status == "cancelled_before_publication", stopped
    assert stopped.history_retained and stopped.capture == captured[0]
    assert stopped.preparation is not None and not stopped.ready
    checkpoint = operations.read_checkpoint(vault)
    assert checkpoint.status == "valid" and checkpoint.review is not None
    assert checkpoint.manifest.boundary == "local"
    loaded = operations.load_update(vault)
    assert loaded.loaded is not None and not loaded.ready
    assert authored_files(vault) == files
    assert _user_state(vault) == before
    assert_only_owned_history_refs_added(vault, refs, checkpoint)


def test_late_direct_group_cancel_reports_retained_history(monkeypatch):
    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_owned_update_controls import _native_controls_case

    case = _native_controls_case(monkeypatch)
    context = UpdateContext(operations=case.operations)
    opened = context.prepare(
        str(case.vault),
        source=str(case.incoming_archive),
        selection_id="11111111-1111-4111-8111-111111111111",
    )
    assert opened.binding is not None and opened.history_retained, opened
    checks = []

    def cancel():
        checks.append(True)
        return len(checks) > 1

    stopped = context.keep_current_unresolved(
        opened.binding, group_id=opened.keep_current_group_id, cancel=cancel
    )
    assert (
        stopped.status == "cancelled_before_publication"
        and stopped.affected_conflicts == 0
    )
    assert stopped.binding == opened.binding and stopped.history_retained
    assert stopped.checkpoint_commit == opened.checkpoint_commit
    assert stopped.unresolved == opened.unresolved and stopped.changes == opened.changes
    assert (case.vault / case.note_path).read_bytes() == case.current_note
    assert (case.vault / case.asset_path).read_bytes() == case.current


def test_unresolved_first_apply_does_not_capture_or_publish(monkeypatch):
    import json
    from zipfile import ZipFile

    from tests.application.test_onboarding_completion import authored_files

    operations, vault, archive = first_setup_operations()
    incoming = archive.with_name("incoming-conflict.brz")
    with ZipFile(archive) as old, ZipFile(incoming, "w") as new:
        for name in old.namelist():
            raw = old.read(name)
            if name.endswith("/Notes.md"):
                raw = b"Incoming prose.\r\n"
            if name == "attachments.json":
                record = json.loads(raw)
                record["DataLength"] = 17
                raw = json.dumps(record).encode()
            new.writestr(name, raw)
    offered = operations.prepare_onboarding(vault, incoming, original_source=archive)
    assert offered.preparation is not None and not offered.ready, offered
    files, refs = authored_files(vault), all_refs(vault)

    def capture(*args, **kwargs):
        raise AssertionError("Unresolved Apply cannot enter native checkpoint capture")

    monkeypatch.setattr(operations, "capture_checkpoint", capture)
    refused = operations.apply_update(offered.preparation)
    assert refused.code == "review_not_ready" and not refused.ready, refused
    assert (
        refused.capture is None and not (vault / ".brz2obsidian/locator.json").exists()
    )
    assert authored_files(vault) == files and all_refs(vault) == refs


def test_supported_independent_configuration_edits_merge_without_format_choice():
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_resolution import preflight, with_review_links
    from tests.reconciliation.test_structure import structured_request

    facts = structured_request(
        b"First old.\nMiddle.\nLast old.\n",
        b"First local.\nMiddle.\nLast old.\n",
        b"First old.\nMiddle.\nLast source.\n",
    )
    facts = facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(update={"output_role": "configuration"}),
            )
        }
    )
    plan = prepare_review(
        automatic_merge_facts(with_review_links(facts)), preflight=preflight()
    )
    assert plan.ready and not plan.requirements, plan.requirements
    effects = select_review_effects(plan)
    assert effects.status == "selected"
    assert effects.files[0].content.data == b"First local.\nMiddle.\nLast source.\n"


def test_configuration_conflict_keeps_explicit_safe_version_choices():
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.core import (
        inspect_review_choices,
        prepare_review,
        resolve_review,
        select_review_effects,
    )
    from tests.reconciliation.test_resolution import (
        action,
        literal_text_candidate,
        preflight,
        with_review_links,
    )
    from tests.reconciliation.test_structure import structured_request

    facts = structured_request(
        b"Setting old.\n", b"Setting local.\n", b"Setting source.\n"
    )
    facts = facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(update={"output_role": "configuration"}),
            )
        }
    )
    facts = automatic_merge_facts(with_review_links(facts))
    plan = prepare_review(facts, preflight=preflight())
    assert not plan.ready and len(plan.requirements) == 1
    offer = inspect_review_choices(plan)[0]
    assert offer.domain == "configuration" and {"current", "incoming", "edited"} <= set(
        offer.enabled_choices
    )
    for choice, expected in (
        ("current", b"Setting local.\n"),
        ("incoming", b"Setting source.\n"),
    ):
        candidate = (
            literal_text_candidate(facts, expected) if choice == "incoming" else None
        )
        selected = resolve_review(
            plan,
            action(plan, domain="configuration", choice=choice, candidate=candidate),
        )
        assert selected.status == "accepted" and selected.plan.ready, selected
        effects = select_review_effects(selected.plan)
        assert (
            effects.status == "selected" and effects.files[0].content.data == expected
        )


def test_distinct_original_onboarding_cold_resume_keeps_original_and_choice():
    import hashlib
    import json
    import subprocess
    import sys
    from zipfile import ZipFile

    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_onboarding_completion import authored_files
    from tests.application.test_update_context import worker_context_call
    from tests.application.test_update_lifecycle import _user_state

    operations, vault, archive = first_setup_operations()
    user_before, files_before = _user_state(vault), authored_files(vault)
    incoming = archive.with_name("distinct-incoming.brz")
    with ZipFile(archive) as old, ZipFile(incoming, "w") as new:
        for name in old.namelist():
            raw = old.read(name)
            if name.endswith("/Notes.md"):
                raw = b"Incoming prose.\r\n"
            if name == "attachments.json":
                record = json.loads(raw)
                record["DataLength"] = 17
                raw = json.dumps(record).encode()
            new.writestr(name, raw)
    source_hashes = tuple(
        hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, incoming)
    )
    context = UpdateContext(operations=operations)

    def send(command, **values):
        return worker_context_call(context, {"command": command, **values})

    opened = send(
        "prepare",
        kind="onboarding",
        vault=str(vault),
        source=str(incoming),
        original_source=str(archive),
        selection_id="11111111-1111-4111-8111-111111111111",
    )
    assert opened.binding is not None and opened.unresolved > 0, opened
    page = send("page", binding=opened.binding, queue="unresolved")
    note = next(
        r
        for r in page.page.items
        if r.item_id == "22222222-2222-4222-8222-222222222222"
    )
    assert note.original == ORIGINAL and note.current == CURRENT
    assert note.incoming == ORIGINAL.replace(
        b"Authored body.\r\n", b"Incoming prose.\r\n"
    )
    offer = next(r for r in page.offers if r.change_id == note.change_id)
    selected = send(
        "choose",
        binding=opened.binding,
        requirement_id=offer.requirement_id,
        choice="current",
        assumptions_digest=offer.assumptions_digest,
    )
    assert selected.code == "accepted" and selected.unresolved > 0, selected
    selected_offer = next(
        r
        for r in send("choices", binding=selected.binding).offers
        if r.change_id == note.change_id
    )
    decision_id = selected_offer.decision_id
    assert selected_offer.selected == "current" and decision_id is not None
    saved = send("save", binding=selected.binding)
    assert saved.code == "saved" and saved.unresolved > 0, saved
    assert (
        send("close", binding=saved.binding, choice="discard").code == "context_closed"
    )
    result_path = archive.with_name("cold-distinct-result.json")
    code = """import json,sys
from pathlib import Path
from brz2obsidian.application.update_context import UpdateContext
context=UpdateContext()
state=context.resume(sys.argv[1],selection_id="22222222-2222-4222-8222-222222222222")
assert state.binding is not None,state
page=context.page(state.binding)
note=next(r for r in page.page.items if r.item_id=="22222222-2222-4222-8222-222222222222")
offer=next(r for r in context.choice_page(state.binding).offers if r.change_id==note.change_id)
Path(sys.argv[2]).write_text(json.dumps({"original":None if note.original is None else note.original.hex(),"current":note.current.hex(),"incoming":note.incoming.hex(),"selected":offer.selected,"decision_id":offer.decision_id,"unresolved":state.unresolved,"stale":state.stale}),encoding="utf-8")
context.close(state.binding,choice="discard")
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(vault), str(result_path)],
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    cold = json.loads(result_path.read_text(encoding="utf-8"))
    assert cold["original"] == ORIGINAL.hex(), cold
    assert cold["current"] == CURRENT.hex()
    assert (
        cold["incoming"]
        == ORIGINAL.replace(b"Authored body.\r\n", b"Incoming prose.\r\n").hex()
    )
    assert cold["selected"] == "current" and cold["decision_id"] == decision_id
    assert cold["unresolved"] == saved.unresolved and cold["stale"] == 0
    assert authored_files(vault) == files_before and _user_state(vault) == user_before
    assert (
        tuple(hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, incoming))
        == source_hashes
    )


def supported_transition_facts(original, current, incoming):
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import align_structure, interpret_structure
    from tests.reconciliation.test_resolution import with_review_links
    from tests.reconciliation.test_structure import structured_request

    facts = structured_request(original, current, incoming)
    documents = tuple(
        interpret_structure(ExactContent(data=raw), output_format=version)
        for raw, version in ((original, 7), (current, 7), (incoming, 8))
    )
    facts = facts.model_copy(
        update={
            "incoming_identity": facts.incoming_identity.model_copy(
                update={"output_format": 8}
            ),
            "subjects": (
                facts.subjects[0].model_copy(
                    update={"structure": align_structure(*documents)}
                ),
            ),
            "format_operation": facts.format_operation.model_copy(
                update={
                    "kind": "format_transition",
                    "target_source_version": "source:a",
                }
            ),
        }
    )
    return automatic_merge_facts(with_review_links(facts))


def test_explicit_supported_transition_automatically_keeps_clean_and_combines_safe_files():
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_resolution import preflight

    for original, current, incoming, expected in (
        (b"Unchanged.\n", b"Unchanged.\n", b"Unchanged.\n", b"Unchanged.\n"),
        (
            b"Old presentation.\n",
            b"Old presentation.\n",
            b"Target presentation.\n",
            b"Target presentation.\n",
        ),
        (
            b"First old.\nMiddle.\nLast old.\n",
            b"First local.\nMiddle.\nLast old.\n",
            b"First old.\nMiddle.\nLast target.\n",
            b"First local.\nMiddle.\nLast target.\n",
        ),
    ):
        review = prepare_review(
            supported_transition_facts(original, current, incoming),
            preflight=preflight(),
        )
        assert review.proposal.operation == "format_transition"
        assert review.ready and not review.requirements, review.requirements
        assert review.proposal.changes[0].format_review is None
        effects = select_review_effects(review)
        assert effects.status == "selected", effects
        assert [(f.path, f.content.data) for f in effects.files] == [
            ("Notes/Opening.md", expected)
        ]


def test_transition_producer_interprets_automatic_combination_after_selecting_operation(
    tmp_path,
):
    import hashlib
    import json
    from types import SimpleNamespace

    from brz2obsidian.application.format_transition import transition_facts
    from brz2obsidian.application.update_facts import output_identity, record
    from brz2obsidian.core import prepare_review
    from tests.reconciliation.test_resolution import preflight
    from tests.support.recorded_format7 import historical_payload

    original, _ = historical_payload()
    # The controlled history port includes this independently specified support output.
    original["Compatible text.md"] = b"First old.\nMiddle.\nLast old.\n"
    incoming = dict(original)
    target_record = record(incoming)
    target_record["schema_version"] = 8
    incoming["migration-record.json"] = json.dumps(target_record).encode()
    guide_path = "Compatible text.md"
    incoming[guide_path] = b"First old.\nMiddle.\nLast target.\n"
    local = b"First local.\nMiddle.\nLast old.\n"
    rows = []
    for path, raw in original.items():
        raw = local if path == guide_path else raw
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        rows.append(
            SimpleNamespace(
                path=path,
                size=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                excluded=False,
            )
        )
    history = SimpleNamespace(
        checkpoint=SimpleNamespace(
            review=None,
            manifest=SimpleNamespace(
                boundary="result", identity=output_identity(record(original))
            ),
        ),
        admission=SimpleNamespace(vault=tmp_path, inventory=tuple(rows)),
    )
    facts = transition_facts(
        history, original, incoming, proposal_id="explicit-transition", generation=1
    )
    review = prepare_review(facts, preflight=preflight())
    note = next(
        change for change in review.proposal.changes if change.path == guide_path
    )
    subject = next(subject for subject in facts.subjects if subject.path == guide_path)
    assert subject.interpretation == "supported"
    assert subject.structure.alignment == "supported", subject.structure.alignment
    assert facts.format_operation.recorded_generation == "supported"
    assert facts.format_operation.established_baseline is not None
    assert (
        facts.format_operation.baseline_source_version
        == facts.format_operation.target_source_version
    )
    assert review.proposal.operation == "format_transition"
    assert note.disposition == "compatible" and not note.requires_decision, (
        note.provenance.rule,
        note.format_review,
        note.structure_result,
    )
    assert note.result.data == b"First local.\nMiddle.\nLast target.\n"
    assert not any(
        requirement.change_id == note.change_id for requirement in review.requirements
    )


def test_automatic_transition_keeps_conflicts_unsafe_unknown_and_legacy_reviews_blocked():
    from brz2obsidian.contracts import ContentVersion
    from brz2obsidian.core import (
        inspect_review_choices,
        prepare_review,
        select_review_effects,
    )
    from tests.reconciliation.test_resolution import preflight

    clean = supported_transition_facts(b"Old.\n", b"Old.\n", b"Target.\n")
    conflict = supported_transition_facts(b"Old.\n", b"Local.\n", b"Target.\n")
    unsafe = clean.model_copy(
        update={
            "safety_facts": tuple(
                fact.model_copy(update={"status": "unsafe"})
                if fact.kind == "target"
                else fact
                for fact in clean.safety_facts
            )
        }
    )
    unknown = clean.model_copy(
        update={
            "subjects": (
                clean.subjects[0].model_copy(
                    update={
                        "baseline": ContentVersion(
                            status="unknown",
                            content=None,
                            unavailable_digest="unknown-original",
                        )
                    }
                ),
            ),
            "format_operation": clean.format_operation.model_copy(
                update={"established_baseline": None}
            ),
        }
    )
    unsupported = supported_transition_facts(b"Old.\n", b"Old.\n", b"Target.\xff\n")
    unbound = clean.model_copy(
        update={
            "subjects": (
                clean.subjects[0].model_copy(
                    update={
                        "structure": clean.subjects[0].structure.model_copy(
                            update={
                                "incoming": clean.subjects[
                                    0
                                ].structure.incoming.model_copy(
                                    update={"output_format": 7}
                                )
                            }
                        )
                    }
                ),
            )
        }
    )
    for label, facts in (
        ("conflicting edits", conflict),
        ("unsafe target", unsafe),
        ("unknown original", unknown),
        ("unsupported target interpretation", unsupported),
        ("unbound target interpretation", unbound),
        (
            "unavailable generation",
            clean.model_copy(
                update={
                    "format_operation": clean.format_operation.model_copy(
                        update={"recorded_generation": "unavailable"}
                    )
                }
            ),
        ),
        (
            "unknown source",
            clean.model_copy(
                update={
                    "format_operation": clean.format_operation.model_copy(
                        update={"target_source_version": None}
                    )
                }
            ),
        ),
        (
            "changed source",
            clean.model_copy(
                update={
                    "format_operation": clean.format_operation.model_copy(
                        update={"target_source_version": "source:b"}
                    )
                }
            ),
        ),
        (
            "legacy explicit policy",
            clean.model_copy(
                update={
                    "format_operation": clean.format_operation.model_copy(
                        update={"automatic_merge": False}
                    )
                }
            ),
        ),
    ):
        review = prepare_review(facts, preflight=preflight())
        assert not review.ready, label
        assert review.requirements or review.blockers, label
        assert select_review_effects(review).status != "selected", label
        if label == "conflicting edits":
            assert review.proposal.changes[0].format_review is None
            offer = inspect_review_choices(review)[0]
            assert {"current", "incoming"} <= set(offer.enabled_choices)
        if label == "legacy explicit policy":
            assert review.proposal.changes[0].format_review is not None
            assert review.requirements[0].domain == "format"


def test_automatic_transition_keeps_opaque_assets_clean_and_validates_binary_effects():
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_attachments import linked_attachment_request
    from tests.reconciliation.test_resolution import preflight

    raw = b"Authored [[Assets/data.bin|Retained wording]].\r\n"
    for original in (b"\x00original", b"abc"):
        facts = linked_attachment_request(payload_current=original, raw=raw)
        subject = facts.subjects[0].model_copy(
            update={
                "interpretation": "opaque",
                "facet": "asset",
                "baseline": facts.subjects[0].baseline.model_copy(
                    update={"content": ExactContent(data=original)}
                ),
            }
        )
        baseline = facts.format_operation.established_baseline
        facts = facts.model_copy(
            update={
                "subjects": (subject,),
                "incoming_identity": facts.incoming_identity.model_copy(
                    update={"output_format": 8}
                ),
                "identity_inventory": tuple(
                    row.model_copy(update={"facet": "asset"})
                    if row.facet == "attachment:payload"
                    else row
                    for row in facts.identity_inventory
                ),
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "kind": "format_transition",
                        "target_source_version": "source:a",
                        "established_baseline": baseline.model_copy(
                            update={
                                "outputs": tuple(
                                    output.model_copy(
                                        update={
                                            "facet": "asset",
                                            "content": ExactContent(data=original),
                                        }
                                    )
                                    for output in baseline.outputs
                                )
                            }
                        ),
                    }
                ),
            }
        )
        normalized = automatic_merge_facts(facts)
        review = prepare_review(normalized, preflight=preflight())
        assert review.ready and not review.requirements, review.requirements
        assert review.proposal.changes[0].format_review is None
        selected = select_review_effects(review)
        assert selected.status == "selected", selected
        files = {row.path: row.content.data for row in selected.files}
        assert files["Assets/data.bin"] == b"abc"
        assert files.get("Notes/Owner.md", raw) == raw
        if original != b"abc":
            without_candidate = normalized.model_copy(
                update={
                    "subjects": (
                        normalized.subjects[0].model_copy(
                            update={
                                "automatic_attachment": None,
                                "automatic_attachment_links": (),
                            }
                        ),
                    )
                }
            )
            blocked = prepare_review(without_candidate, preflight=preflight())
            assert (
                not blocked.ready
                and select_review_effects(blocked).status != "selected"
            )


def test_group_revalidates_typed_and_mapping_envelopes_before_accepting_history():
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.application.review_choices import keep_current_group_action
    from brz2obsidian.core import (
        prepare_review,
        resolve_review,
        select_review_effects,
        validate_review,
    )
    from brz2obsidian.core.resolution import unresolved_current_scope
    from tests.reconciliation.test_resolution import preflight

    plan = prepare_review(mixed_facts(), preflight=preflight())
    before = plan.model_dump_json()
    group_id, _ = unresolved_current_scope(plan)
    event = keep_current_group_action(plan, group_id)
    for field, invalid in (
        ("schema_version", 2),
        ("schema_id", "brz2obsidian.foreign-group"),
    ):
        typed = event.model_copy(update={field: invalid})
        mapping = event.model_dump() | {field: invalid}
        for malformed in (typed, mapping):
            with pytest.raises(ValidationError) as rejected:
                resolve_review(plan, malformed)
            assert any(error["loc"] == (field,) for error in rejected.value.errors())
            assert plan.model_dump_json() == before
    accepted = resolve_review(plan, event)
    assert accepted.status == "accepted" and accepted.plan.ready
    assert len(accepted.plan.history.events) == 1
    assert validate_review(accepted.plan).status == "accepted"
    effects = select_review_effects(accepted.plan)
    assert effects.status == "selected"
    assert {row.path: row.content.data for row in effects.files} == {
        "Notes/clean.md": b"incoming\n",
        "Notes/prior.md": b"prior local\n",
        "Notes/one.md": b"one local\n",
        "Notes/two.md": b"two local\n",
    }
