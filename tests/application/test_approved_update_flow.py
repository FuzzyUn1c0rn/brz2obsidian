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
    backup_path = "Attachments/22222222/Notes.md.original"
    assert (vault / backup_path).read_bytes() == b"Authored body.\r\n"
    # Leave a genuine overlapping binary edit after choosing the note version.
    # A source-only backup change needs no routine confirmation.
    backup_current = b"Current backup edit.\r\n"
    (vault / backup_path).write_bytes(backup_current)
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
        and r.current_path == "Home \u2014 Entry thought.md"
    )
    assert note.original == ORIGINAL and note.current == CURRENT
    assert note.incoming == ORIGINAL.replace(
        b"Authored body.\r\n", b"Incoming prose.\r\n"
    )
    backup = next(r for r in page.page.items if r.current_path == backup_path)
    assert backup.original == b"Authored body.\r\n"
    assert backup.current == backup_current
    assert backup.incoming == b"Incoming prose.\r\n"
    assert backup.result is None
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
note=next(r for r in page.page.items if r.item_id=="22222222-2222-4222-8222-222222222222" and r.current_path=="Home \u2014 Entry thought.md")
backup=next(r for r in page.page.items if r.current_path=="Attachments/22222222/Notes.md.original")
offer=next(r for r in context.choice_page(state.binding).offers if r.change_id==note.change_id)
Path(sys.argv[2]).write_text(json.dumps({"original":None if note.original is None else note.original.hex(),"current":note.current.hex(),"incoming":note.incoming.hex(),"result":None if note.result is None else note.result.hex(),"selected":offer.selected,"decision_id":offer.decision_id,"unresolved":state.unresolved,"stale":state.stale,"backup_original":None if backup.original is None else backup.original.hex(),"backup_current":backup.current.hex(),"backup_incoming":backup.incoming.hex(),"backup_result":None if backup.result is None else backup.result.hex()}),encoding="utf-8")
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
    assert cold["result"] == CURRENT.hex()
    assert cold["backup_original"] == b"Authored body.\r\n".hex()
    assert cold["backup_current"] == backup_current.hex()
    assert cold["backup_incoming"] == b"Incoming prose.\r\n".hex()
    assert cold["backup_result"] is None
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


def test_default_worker_automatically_accepts_incoming_runtime_metadata():
    import hashlib
    import json

    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_onboarding_completion import authored_files
    from tests.application.test_update_context import worker_context_call
    from tests.application.test_update_lifecycle import _user_state

    _, vault, archive = first_setup_operations()
    before = authored_files(vault)
    user_before = _user_state(vault)
    original_record = (vault / "migration-record.json").read_bytes()
    source_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    # Incoming uses the public default runtime metadata, distinct from the
    # independently retained fixture's original generation metadata.
    context = UpdateContext()
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "onboarding",
            "vault": str(vault),
            "source": str(archive),
            "original_source": str(archive),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert opened.binding is not None, opened
    try:
        shallow = worker_context_call(
            context, {"command": "page", "binding": opened.binding, "byte_limit": 0}
        )
        offset = next(
            index
            for index, row in enumerate(shallow.page.items)
            if row.current_path == "migration-record.json"
        )
        page = worker_context_call(
            context,
            {
                "command": "page",
                "binding": opened.binding,
                "offset": offset,
                "limit": 1,
            },
        )
        record = page.page.items[0]
        assert not record.omitted
        assert record.original == record.current == original_record
        assert record.incoming is not None and record.incoming != original_record
        assert (
            json.loads(record.incoming)["source_identity"]
            == json.loads(original_record)["source_identity"]
        )
        assert record.result == record.incoming
        assert record.disposition == "compatible"
        assert (
            opened.ready
            and opened.unresolved == 0
            and "apply_update" in opened.next_actions
        )
    finally:
        worker_context_call(
            context,
            {"command": "close", "binding": opened.binding, "choice": "discard"},
        )
    assert authored_files(vault) == before and _user_state(vault) == user_before
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == source_sha


def test_incoming_only_repeated_text_uses_exact_supported_target_across_operations():
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_resolution import preflight, with_review_links
    from tests.reconciliation.test_structure import structured_request

    original = b"Repeated.\nOld.\nRepeated.\n"
    incoming = b"Repeated.\nTarget.\nRepeated.\n"
    for kind in ("source_update", "onboarding", "format_transition"):
        if kind == "format_transition":
            facts = supported_transition_facts(original, original, incoming)
        else:
            facts = structured_request(original, original, incoming)
            facts = facts.model_copy(
                update={
                    "format_operation": facts.format_operation.model_copy(
                        update={"kind": kind}
                    )
                }
            )
            facts = automatic_merge_facts(with_review_links(facts))
        assert facts.subjects[0].structure.alignment == "ambiguous"
        plan = prepare_review(facts, preflight=preflight())
        assert plan.ready and not plan.requirements, (kind, plan.requirements)
        assert plan.proposal.operation == kind
        change = plan.proposal.changes[0]
        assert change.original.data == change.current.data == original
        assert change.result.data == b"Repeated.\nTarget.\nRepeated.\n"
        assert change.format_review is None and not change.requires_decision
        effects = select_review_effects(plan)
        assert effects.status == "selected"
        assert [(row.path, row.content.data) for row in effects.files] == [
            ("Notes/Opening.md", b"Repeated.\nTarget.\nRepeated.\n")
        ]


def test_incoming_only_shortcut_keeps_ambiguous_local_and_untrusted_results_blocked():
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.contracts import ContentVersion
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.reconciliation.test_resolution import preflight, with_review_links
    from tests.reconciliation.test_structure import structured_request

    original = b"Repeated.\nOld.\nRepeated.\n"
    incoming = b"Repeated.\nTarget.\nRepeated.\n"
    local = b"Repeated.\nLocal.\nRepeated.\n"
    clean = automatic_merge_facts(
        with_review_links(structured_request(original, original, incoming))
    )
    conflict = automatic_merge_facts(
        with_review_links(structured_request(original, local, incoming))
    )
    onboarding = conflict.model_copy(
        update={
            "format_operation": conflict.format_operation.model_copy(
                update={"kind": "onboarding"}
            )
        }
    )
    unknown = clean.model_copy(
        update={
            "subjects": (
                clean.subjects[0].model_copy(
                    update={
                        "baseline": ContentVersion(
                            status="unknown", content=None, unavailable_digest="unknown"
                        )
                    }
                ),
            ),
            "format_operation": clean.format_operation.model_copy(
                update={"established_baseline": None}
            ),
        }
    )
    unsupported = automatic_merge_facts(
        with_review_links(
            structured_request(
                original, original, b"---\npriority: 1\npriority: 2\n---\nTarget.\n"
            )
        )
    )
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
                                    update={"output_format": 8}
                                )
                            }
                        )
                    }
                ),
            )
        }
    )
    unsafe = clean.model_copy(
        update={
            "safety_facts": tuple(
                fact.model_copy(update={"status": "unsafe"})
                if fact.kind == "candidate"
                else fact
                for fact in clean.safety_facts
            )
        }
    )
    legacy = clean.model_copy(
        update={
            "format_operation": clean.format_operation.model_copy(
                update={"automatic_merge": False}
            )
        }
    )
    for label, facts in (
        ("ambiguous source update with authored edits", conflict),
        ("ambiguous onboarding with authored edits", onboarding),
        (
            "ambiguous format transition with authored edits",
            supported_transition_facts(original, local, incoming),
        ),
        ("unknown original", unknown),
        ("unsupported target", unsupported),
        ("unbound target", unbound),
        ("unsafe candidate", unsafe),
        ("legacy False", legacy),
    ):
        plan = prepare_review(facts, preflight=preflight())
        assert not plan.ready and (plan.requirements or plan.blockers), label
        assert select_review_effects(plan).status != "selected", label


def test_ready_owned_group_advertises_apply_and_retains_it_after_refresh():
    import json
    from zipfile import ZipFile

    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_onboarding_completion import authored_files
    from tests.application.test_update_context import worker_context_call
    from tests.application.test_update_lifecycle import _user_state

    operations, vault, archive = first_setup_operations()
    before, user_before = authored_files(vault), _user_state(vault)
    incoming = archive.with_name("ready-group-incoming.brz")
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
    assert (
        opened.binding is not None
        and not opened.ready
        and opened.keep_current_count > 0
    ), opened
    active = opened
    try:
        grouped = send(
            "keep_current_unresolved",
            binding=opened.binding,
            group_id=opened.keep_current_group_id,
        )
        active = grouped
        assert (
            grouped.code == "accepted" and grouped.ready and grouped.unresolved == 0
        ), grouped
        assert "apply_update" in grouped.next_actions, grouped.next_actions
        refreshed = send("refresh", binding=grouped.binding)
        active = refreshed
        assert refreshed.ready and "apply_update" in refreshed.next_actions, refreshed
        assert refreshed.unresolved == 0
        page = send("page", binding=refreshed.binding)
        note = next(
            row
            for row in page.page.items
            if row.item_id == "22222222-2222-4222-8222-222222222222"
        )
        assert note.result == CURRENT
    finally:
        send("close", binding=active.binding, choice="discard")
    assert authored_files(vault) == before and _user_state(vault) == user_before


def test_bulk_current_recertifies_prior_incoming_reference_without_new_choice(tmp_path):
    import json
    import subprocess
    import sys

    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.review_choices import requirement_digest
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import (
        inspect_review_choices,
        refresh_review,
        select_review_effects,
    )
    from brz2obsidian.core.resolution import unresolved_current_scope
    from tests.application.test_update_lifecycle_contracts import preparation
    from tests.reconciliation.test_identity import with_subjects
    from tests.reconciliation.test_resolution import (
        note_and_attachment_request,
        preflight,
    )

    facts = note_and_attachment_request()
    note = facts.subjects[0].model_copy(
        update={
            "baseline": facts.subjects[0].baseline.model_copy(
                update={
                    "content": ExactContent(data=b"Baseline prose [[Assets/data.bin]].")
                }
            )
        }
    )
    facts = automatic_merge_facts(
        with_subjects(facts, (note, facts.subjects[1]), facts.identity_inventory)
    )
    prepared = preparation(facts)
    offered = next(
        row for row in inspect_review_choices(prepared.review) if row.domain == "text"
    )
    operations = Operations()
    selected = operations.resolve_update_choice(
        prepared,
        requirement_id=offered.requirement_id,
        choice="incoming",
        assumptions_digest=requirement_digest(offered),
    )
    assert selected.code == "accepted" and not selected.ready
    prior = selected.preparation.review
    digest, members = unresolved_current_scope(prior)
    assert len(members) == 1
    grouped = operations.keep_current_unresolved(selected.preparation, group_id=digest)
    assert grouped.code == "accepted" and grouped.ready, (
        grouped.preparation.review.blockers
    )
    plan = grouped.preparation.review
    assert plan.requirements == () and not plan.blockers
    assert plan.actions[: len(prior.actions)] == prior.actions
    assert all(approval in plan.approvals for approval in prior.approvals)
    assert len(plan.history.events) == 2 and len(plan.actions) == 2
    effects = select_review_effects(plan)
    expected = {
        "Assets/data.bin": b"\x00authored",
        "Notes/Owner.md": b"New prose [[Assets/data.bin]].",
    }
    assert (
        effects.status == "selected"
        and {row.path: row.content.data for row in effects.files} == expected
    )
    refreshed = refresh_review(
        plan, facts.model_copy(update={"generation": 2}), preflight=preflight()
    )
    assert refreshed.status == "accepted" and refreshed.plan.ready
    cold = tmp_path / "recertified-group.json"
    cold.write_text(plan.model_dump_json(), encoding="utf-8")
    code = """import json,sys
from pathlib import Path
from brz2obsidian.contracts import ReviewPlan
from brz2obsidian.core import validate_review,select_review_effects
plan=ReviewPlan.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
result=validate_review(plan)
effects=select_review_effects(plan)
print(json.dumps({"valid":result.status,"ready":result.plan.ready,"files":{row.path:row.content.data.hex() for row in effects.files}}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(cold)], capture_output=True, check=False
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert json.loads(completed.stdout) == {
        "valid": "accepted",
        "ready": True,
        "files": {path: raw.hex() for path, raw in expected.items()},
    }


def test_bulk_current_recertifies_automatic_incoming_note_without_reapproval():
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.core import select_review_effects
    from brz2obsidian.core.resolution import unresolved_current_scope
    from brz2obsidian.obsidian import align_structure, interpret_structure
    from tests.application.test_update_lifecycle_contracts import preparation
    from tests.reconciliation.test_resolution import note_and_attachment_request

    facts = note_and_attachment_request()
    note = facts.subjects[0]
    comparison = align_structure(
        *(
            interpret_structure(content, output_format=7)
            for content in (note.baseline.content, note.current.content, note.incoming)
        )
    )
    facts = facts.model_copy(
        update={
            "subjects": (
                note.model_copy(update={"structure": comparison}),
                facts.subjects[1],
            )
        }
    )
    prepared = preparation(automatic_merge_facts(facts))
    clean = prepared.review.proposal.changes[0]
    assert clean.disposition == "compatible" and not clean.requires_decision
    assert not prepared.review.actions
    digest, members = unresolved_current_scope(prepared.review)
    assert len(members) == 1
    result = Operations().keep_current_unresolved(prepared, group_id=digest)
    assert result.ready and not result.preparation.review.requirements, (
        result.preparation.review.blockers
    )
    assert (
        len(result.preparation.review.actions)
        == len(result.preparation.review.history.events)
        == 1
    )
    from brz2obsidian.contracts import ReviewPlan
    from brz2obsidian.core import validate_review

    restored = ReviewPlan.model_validate_json(
        result.preparation.review.model_dump_json()
    )
    assert validate_review(restored).status == "accepted" and restored.ready
    effects = select_review_effects(result.preparation.review)
    assert effects.status == "selected"
    assert {row.path: row.content.data for row in effects.files} == {
        "Assets/data.bin": b"\x00authored",
        "Notes/Owner.md": b"New prose [[Assets/data.bin]].",
    }


def test_owned_format_transition_normalization_uses_admitted_session():
    import hashlib

    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_format_transition_native import user_git_state
    from tests.application.test_onboarding import owned_case
    from tests.application.test_onboarding_completion import authored_files
    from tests.application.test_type_tag_compatibility import seed_format7
    from tests.application.test_update_context import worker_context_call
    from tests.application.test_vault_checkpoints import git
    from tests.support.recorded_format7 import NOTE, ORIGINAL

    operations, vault, source, current = seed_format7(owned_case())
    before, user = authored_files(vault), user_git_state(vault)
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    context = UpdateContext(operations=operations)
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "format_transition",
            "vault": str(vault),
            "source": str(source),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    try:
        assert opened.status == "prepared_review" and opened.binding is not None, opened
        page = worker_context_call(
            context, {"command": "page", "binding": opened.binding}
        )
        note = next(row for row in page.page.items if row.current_path == NOTE)
        assert note.original == ORIGINAL and note.current == current
        assert opened.kind == "format_transition" and note.incoming is not None
    finally:
        if opened.binding is not None:
            context.close(opened.binding, choice="discard")
    assert authored_files(vault) == before and user_git_state(vault) == user
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha


def reference_recertification_facts(
    *,
    current_payload=b"\x00authored",
    incoming_payload=b"abc",
    reference=b"[[Assets/data.bin]]",
    divergent=True,
    incoming_target=None,
):
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.obsidian import (
        align_structure,
        interpret_link_target,
        interpret_links,
        interpret_structure,
    )
    from tests.reconciliation.test_identity import with_subjects
    from tests.reconciliation.test_resolution import note_and_attachment_request

    facts = note_and_attachment_request()
    note, binary = facts.subjects
    original = (
        ExactContent(data=b"Baseline prose [[Assets/data.bin]].")
        if divergent
        else note.baseline.content
    )
    received = ExactContent(data=b"New prose " + reference + b".")
    note = note.model_copy(
        update={
            "baseline": note.baseline.model_copy(update={"content": original}),
            "incoming": received,
            "structure": align_structure(
                *(
                    interpret_structure(raw, output_format=7)
                    for raw in (original, note.current.content, received)
                )
            ),
        }
    )
    binary = binary.model_copy(
        update={
            "current": binary.current.model_copy(
                update={"content": ExactContent(data=current_payload)}
            ),
            "incoming": ExactContent(data=incoming_payload),
        }
    )
    inventory = tuple(
        row.model_copy(update={"current": binary.current})
        if row.current.path == "Assets/data.bin"
        else row
        for row in facts.identity_inventory
    )
    context = facts.link_context
    current_targets = context.current_targets
    incoming_targets = tuple(
        incoming_target
        if incoming_target is not None and target.target_id == "resource:payload"
        else target
        for target in context.incoming_targets
    )

    def states(rows, targets, resource, owner):
        return tuple(
            interpret_link_target(
                resource if row.target_id == "resource:payload" else owner,
                target_id=row.target_id,
                existence="present",
                memberships=(),
                membership_targets=targets,
                source_path=next(
                    target.canonical_path
                    for target in targets
                    if target.target_id == row.target_id
                ),
                output_format=7,
            )
            for row in rows
        )

    old_states = states(
        context.current_target_facts,
        current_targets,
        binary.current.content,
        note.current.content,
    )
    new_states = states(
        context.incoming_target_facts, incoming_targets, binary.incoming, note.incoming
    )

    def document(raw, targets, target_states):
        return interpret_links(
            raw,
            document_id="owner:note",
            source_path="Notes/Owner.md",
            path_mode="vault",
            targets=targets,
            target_facts=target_states,
            inventory="complete",
        )

    facts = with_subjects(facts, (note, binary), inventory)
    return automatic_merge_facts(
        facts.model_copy(
            update={
                "link_context": context.model_copy(
                    update={
                        "current_targets": current_targets,
                        "incoming_targets": incoming_targets,
                        "current_target_facts": old_states,
                        "incoming_target_facts": new_states,
                        "current_documents": (
                            document(note.current.content, current_targets, old_states),
                        ),
                        "incoming_documents": (
                            document(note.incoming, incoming_targets, new_states),
                        ),
                    }
                )
            }
        )
    )


def test_resource_recertification_preserves_real_semantic_and_authority_blockers():
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.review_choices import requirement_digest
    from brz2obsidian.contracts import ExactContent, ImportedItemIdentity
    from brz2obsidian.core import inspect_review_choices, select_review_effects
    from brz2obsidian.core.resolution import unresolved_current_scope
    from tests.application.test_update_lifecycle_contracts import preparation

    base = reference_recertification_facts()
    automatic = reference_recertification_facts(divergent=False)
    target = next(
        row
        for row in base.link_context.incoming_targets
        if row.target_id == "resource:payload"
    )
    moved = target.model_copy(
        update={
            "canonical_path": "Elsewhere/data.bin",
            "target": target.target.model_copy(
                update={"normalized_path": "elsewhere/data.bin"}
            ),
            "representations": ("Elsewhere/data.bin",),
        }
    )
    foreign = target.model_copy(
        update={
            "identity": ImportedItemIdentity(
                collection_id="other:collection",
                module_id="other-module",
                item_id="other:asset",
            )
        }
    )
    absent = automatic.model_copy(
        update={
            "subjects": (
                automatic.subjects[0].model_copy(update={"automatic_result": None}),
                automatic.subjects[1],
            )
        }
    )
    mismatch = automatic.model_copy(
        update={
            "subjects": (
                automatic.subjects[0].model_copy(
                    update={
                        "automatic_result": automatic.subjects[
                            0
                        ].automatic_result.model_copy(
                            update={"content": ExactContent(data=b"Mismatched proof.")}
                        )
                    }
                ),
                automatic.subjects[1],
            )
        }
    )
    unsafe = automatic.model_copy(
        update={
            "subjects": (
                automatic.subjects[0].model_copy(
                    update={
                        "automatic_result": automatic.subjects[
                            0
                        ].automatic_result.model_copy(
                            update={
                                "document": automatic.subjects[
                                    0
                                ].automatic_result.document.model_copy(
                                    update={"status": "unsafe"}
                                )
                            }
                        )
                    }
                ),
                automatic.subjects[1],
            )
        }
    )
    cases = (
        (
            "legacy False",
            base.model_copy(
                update={
                    "format_operation": base.format_operation.model_copy(
                        update={"automatic_merge": False}
                    )
                }
            ),
        ),
        (
            "missing current fragment",
            reference_recertification_facts(
                current_payload=b"No heading.\n",
                incoming_payload=b"# Needed\n",
                reference=b"[[Assets/data.bin#Needed]]",
            ),
        ),
        (
            "unavailable current fragment",
            reference_recertification_facts(
                incoming_payload=b"# Needed\n", reference=b"[[Assets/data.bin#Needed]]"
            ),
        ),
        (
            "ambiguous current fragment",
            reference_recertification_facts(
                current_payload=b"# Needed\n# Needed\n",
                incoming_payload=b"# Needed\n",
                reference=b"[[Assets/data.bin#Needed]]",
            ),
        ),
        (
            "changed reference path",
            reference_recertification_facts(
                reference=b"[[Elsewhere/data.bin]]", incoming_target=moved
            ),
        ),
        (
            "changed reference identity",
            reference_recertification_facts(incoming_target=foreign),
        ),
        ("missing automatic authority", absent),
        ("mismatched automatic authority", mismatch),
        ("unsafe automatic authority", unsafe),
    )
    operations = Operations()
    for label, facts in cases:
        prepared = preparation(facts)
        offers = inspect_review_choices(prepared.review)
        if label not in (
            "missing automatic authority",
            "mismatched automatic authority",
            "unsafe automatic authority",
        ):
            offered = next(row for row in offers if row.domain == "text")
            selected = operations.resolve_update_choice(
                prepared,
                requirement_id=offered.requirement_id,
                choice="incoming",
                assumptions_digest=requirement_digest(offered),
            )
            if label == "changed reference identity":
                assert selected.code == "invalid_candidate" and not selected.ready
                assert (
                    select_review_effects(selected.preparation.review).status
                    != "selected"
                )
                continue
            assert selected.code == "accepted", (label, selected.code)
            prepared = selected.preparation
        digest, members = unresolved_current_scope(prepared.review)
        assert len(members) == 1, label
        result = operations.keep_current_unresolved(prepared, group_id=digest)
        assert result.code == "accepted" and not result.ready, label
        assert not result.preparation.review.requirements, label
        assert "selected_link_context_conflict" in result.preparation.review.blockers, (
            label
        )
        assert select_review_effects(result.preparation.review).status != "selected", (
            label
        )
        if label == "missing current fragment":
            assert "selected_link_context_conflict" in result.findings
            assert "reference evidence" in result.summary
            assert "All changes" in result.guidance
            assert "apply_update" not in result.next_actions

    # A later Incoming proof is explicit new authority; an older Current choice
    # must not silently reinterpret that newer reference meaning.
    from tests.reconciliation.test_resolution import action

    initial = preparation(base)
    offers = inspect_review_choices(initial.review)
    text = next(row for row in offers if row.domain == "text")
    attachment = next(row for row in offers if row.domain == "attachment")
    old_proof = (
        operations.resolve_update_choice(
            initial,
            requirement_id=text.requirement_id,
            choice="incoming",
            assumptions_digest=requirement_digest(text),
        )
        .preparation.review.actions[-1]
        .candidate
    )
    binary_first = operations.resolve_update_choice(
        initial,
        requirement_id=attachment.requirement_id,
        choice="current",
        assumptions_digest=requirement_digest(attachment),
    )
    plan = binary_first.preparation.review
    note = next(change for change in plan.proposal.changes if change.facet == "content")
    newer = operations.resolve_update(
        binary_first.preparation,
        action(
            plan,
            note,
            choice="incoming",
            candidate=old_proof,
            decision_id="newer-explicit-reference",
        ),
    )
    assert newer.code == "accepted" and not newer.ready
    assert "selected_link_context_conflict" in newer.preparation.review.blockers
    assert newer.preparation.review.actions[-1].candidate == old_proof

    # Authored local text is never promoted to an automatic Incoming authority.
    local = preparation(base)
    asset = next(
        row
        for row in inspect_review_choices(local.review)
        if row.domain == "attachment"
    )
    chosen = operations.resolve_update_choice(
        local,
        requirement_id=asset.requirement_id,
        choice="current",
        assumptions_digest=requirement_digest(asset),
    )
    assert not chosen.ready and len(chosen.preparation.review.requirements) == 1
    assert chosen.preparation.review.approvals[0].domain == "attachment"
    unknown_current = automatic.subjects[0].current.model_copy(
        update={"existence": "unknown", "content": None}
    )
    unknown = automatic.model_copy(
        update={
            "subjects": (
                automatic.subjects[0].model_copy(update={"current": unknown_current}),
                automatic.subjects[1],
            ),
            "identity_inventory": tuple(
                row.model_copy(update={"current": unknown_current})
                if row.current.path == "Notes/Owner.md"
                else row
                for row in automatic.identity_inventory
            ),
        }
    )
    unready = preparation(unknown).review
    assert not unready.ready and (unready.blockers or unready.requirements)
    assert select_review_effects(unready).status != "selected"


def test_unknown_review_choice_raises_a_domain_error_before_action_construction():
    import pytest

    from brz2obsidian.application.operations import Operations
    from tests.application.test_update_lifecycle_contracts import preparation

    prepared = preparation(reference_recertification_facts())
    before = prepared.model_dump_json()
    with pytest.raises(ValueError):
        Operations().resolve_update_choice(
            prepared,
            requirement_id="0" * 64,
            choice="incoming",
            assumptions_digest="0" * 64,
        )
    assert prepared.model_dump_json() == before


def test_owned_mixed_group_and_reselect_keep_automatic_note_and_worker_usable(
    monkeypatch,
):
    import hashlib

    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_onboarding_completion import authored_files
    from tests.application.test_owned_update_controls import _native_controls_case
    from tests.application.test_update_context import worker_context_call
    from tests.application.test_vault_checkpoints import git, user_state

    case = _native_controls_case(monkeypatch, automatic_linked_note=True)
    before, user = (
        authored_files(case.vault),
        user_state(case.vault, owned_ref=case.seed.ref),
    )
    refs = git(case.vault, "for-each-ref", "--format=%(refname) %(objectname)")
    context = UpdateContext(operations=case.operations)

    def send(command, **values):
        result = worker_context_call(context, {"command": command, **values})
        assert result is not None, (
            command,
            "Worker must return a typed terminal result",
        )
        return result

    active = send(
        "prepare",
        kind="source_update",
        vault=str(case.vault),
        source=str(case.incoming_archive),
        selection_id="11111111-1111-4111-8111-111111111111",
    )
    assert active.binding is not None and active.keep_current_count == 2, active
    stale_binding = active.binding
    try:
        rows = send("page", binding=active.binding).page.items
        note = next(row for row in rows if row.current_path == case.note_path)
        clean = next(
            row
            for row in rows
            if row.item_id == case.automatic_note_id and row.facet == "content"
        )
        assert clean.original == clean.current and clean.result == clean.incoming
        assert b"Incoming clean [[Attachments/22222222/payload.bin]]." in clean.result
        incoming_note, incoming_clean = note.incoming, clean.incoming
        offer = next(
            row
            for row in send("choices", binding=active.binding).offers
            if row.change_id == note.change_id and row.domain == "text"
        )
        active = send(
            "choose",
            binding=active.binding,
            requirement_id=offer.requirement_id,
            choice="incoming",
            assumptions_digest=offer.assumptions_digest,
        )
        prior = next(
            row
            for row in send("choices", binding=active.binding).offers
            if row.change_id == note.change_id and row.domain == "text"
        )
        assert active.keep_current_count == 1 and prior.selected == "incoming"
        active = send(
            "keep_current_unresolved",
            binding=active.binding,
            group_id=active.keep_current_group_id,
        )
        assert (
            active.ready
            and "apply_update" in active.next_actions
            and active.affected_conflicts == 1
        ), active
        active = send("refresh", binding=active.binding)
        assert active.ready and "apply_update" in active.next_actions, active
        rows = send("page", binding=active.binding).page.items
        assert (
            next(row for row in rows if row.current_path == case.note_path).result
            == incoming_note
        )
        assert (
            next(
                row
                for row in rows
                if row.item_id == case.automatic_note_id and row.facet == "content"
            ).result
            == incoming_clean
        )
        binary = next(
            row for row in rows if row.item_id == case.asset_id and row.facet == "asset"
        )
        assert binary.current == case.current
        offers = send("choices", binding=active.binding).offers
        asset = next(row for row in offers if row.change_id == binary.change_id)
        assert asset.selected == "current"
        details = send(
            "choice_details",
            binding=active.binding,
            requirement_id=asset.requirement_id,
        )
        current = next(row for row in details.choice_details if row.choice == "current")
        assert current.path == case.asset_path and current.size == len(case.current)
        assert current.sha256 == hashlib.sha256(case.current).hexdigest()
        references = send(
            "references", binding=active.binding, requirement_id=asset.requirement_id
        )
        assert references.references and not references.draft_pending
        offers = send("choices", binding=active.binding).offers
        again = next(
            row
            for row in offers
            if row.change_id == note.change_id and row.domain == "text"
        )
        assert again.selected == "incoming" and again.decision_id == prior.decision_id
        active = send(
            "choose",
            binding=active.binding,
            requirement_id=again.requirement_id,
            choice="incoming",
            assumptions_digest=again.assumptions_digest,
        )
        assert active.ready and "apply_update" in active.next_actions, active
        current_binding = active.binding
        stale = send(
            "choose",
            binding=stale_binding,
            requirement_id=again.requirement_id,
            choice="incoming",
            assumptions_digest=again.assumptions_digest,
        )
        assert stale.status == "refused" and stale.code == "context_changed"
        invalid = send(
            "choose",
            binding=current_binding,
            requirement_id=again.requirement_id,
            choice="incoming",
            assumptions_digest="0" * 64,
        )
        assert invalid.status == "refused" and invalid.code == "invalid_review_action"
        active = invalid
        assert send("choices", binding=active.binding).status == "available"
        unknown = send(
            "choose",
            binding=active.binding,
            requirement_id="0" * 64,
            choice="incoming",
            assumptions_digest="0" * 64,
        )
        assert unknown.status == "refused" and unknown.code == "invalid_review_action"
        active = unknown
        active = send("refresh", binding=active.binding)
        assert active.ready and "apply_update" in active.next_actions, active
    finally:
        if active.binding is not None:
            context.close(active.binding, choice="discard")
        assert (
            authored_files(case.vault) == before
            and user_state(case.vault, owned_ref=case.seed.ref) == user
        )
        assert (
            git(case.vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
        )


def test_automatic_selected_content_retains_an_inverse_without_fabricated_approval():
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.application.test_vault_apply import _apply
    from tests.application.test_vault_checkpoints import fixture_case, git, user_state
    from tests.reconciliation.test_resolution import with_review_links
    from tests.reconciliation.test_structure import structured_request

    original = b"Original automatic prose.\n"
    incoming = b"Incoming automatic prose.\n"
    vault, source = fixture_case()
    for root in (vault, source):
        (root / "Notes").mkdir()
        (root / "Notes/Opening.md").write_bytes(original)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Personal.md").write_bytes(b"Independent personal writing.\n")
    git(vault, "add", "Personal.md")
    git(vault, "commit", "-qm", "Independent automatic Undo fixture")
    operations = Operations()
    facts = automatic_merge_facts(
        with_review_links(structured_request(original, original, incoming))
    )
    seeded = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert seeded.status == "captured", seeded.code
    (source / "Notes/Opening.md").write_bytes(incoming)
    plan = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    assert plan.ready and plan.actions == plan.approvals == ()
    assert {
        row.path: row.content.data for row in select_review_effects(plan).files
    } == {"Notes/Opening.md": incoming}
    applied = _apply(
        operations,
        vault,
        source,
        review=plan,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert (
        applied.status == "applied"
        and (vault / "Notes/Opening.md").read_bytes() == incoming
    ), applied.code
    before = user_state(vault)
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    undo = operations.prepare_undo(vault)
    assert undo.status == "offered", undo.code
    assert undo.target_receipt_commit == applied.receipt_commit
    (change,) = undo.review.proposal.changes
    assert change.current.data == incoming and change.incoming.data == original
    assert user_state(vault) == before
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs


def automatic_mixed_inverse_facts():
    from brz2obsidian.application.update_facts import automatic_merge_facts
    from brz2obsidian.contracts import ContentVersion, CurrentContent
    from tests.reconciliation.test_identity import with_subjects
    from tests.reconciliation.test_resolution import with_review_links
    from tests.reconciliation.test_structure import structured_request

    facts = reference_recertification_facts(
        divergent=False, current_payload=b"\x00original"
    )
    subjects, inventory = list(facts.subjects), list(facts.identity_inventory)
    context = facts.link_context
    for item, path, original, incoming, role in (
        (
            "support:metadata",
            "metadata.json",
            b'{"version":1}\n',
            b'{"version":2}\n',
            "guide",
        ),
        (
            "support:config",
            ".obsidian/options.json",
            b'{"setting":1}\n',
            b'{"setting":2}\n',
            "configuration",
        ),
        ("entry:new", "Notes/New.md", None, b"New source note.\n", "note"),
    ):
        extra = structured_request(original or b"", original or b"", incoming)
        old = extra.subjects[0]
        current = CurrentContent(
            existence="absent" if original is None else "present",
            path=path,
            content=None if original is None else old.current.content,
        )
        target = old.source_target.model_copy(
            update={"normalized_path": path.casefold()}
        )
        subject = old.model_copy(
            update={
                "item_id": item,
                "path": path,
                "current": current,
                "source_target": target,
                "output_role": role,
                "baseline": ContentVersion(
                    status="unknown", content=None, unavailable_digest=None
                )
                if original is None
                else old.baseline,
                "structure": None if original is None else old.structure,
            }
        )
        entry = extra.identity_inventory[0].model_copy(
            update={
                "entry_id": item,
                "identity": extra.identity_inventory[0].identity.model_copy(
                    update={"item_id": item}
                ),
                "current": current,
                "target": target,
            }
        )
        extra = with_review_links(with_subjects(extra, (subject,), (entry,)))
        subjects.append(subject)
        inventory.append(entry)
        context = context.model_copy(
            update={
                field: getattr(context, field) + getattr(extra.link_context, field)
                for field in (
                    "current_targets",
                    "incoming_targets",
                    "current_target_facts",
                    "incoming_target_facts",
                    "current_documents",
                    "incoming_documents",
                )
            }
        )
    return automatic_merge_facts(
        with_subjects(facts, tuple(subjects), tuple(inventory)).model_copy(
            update={"link_context": context}
        )
    )


def test_automatic_inverse_targets_include_proven_absence_without_a_decision():
    from brz2obsidian.core import (
        prepare_review,
        review_owned_targets,
        select_review_effects,
    )
    from tests.reconciliation.test_resolution import preflight

    plan = prepare_review(automatic_mixed_inverse_facts(), preflight=preflight())
    assert plan.ready, (plan.requirements, plan.blockers)
    assert (
        len(plan.approvals) == 1 and plan.approvals[0].provenance == "automatic_merge"
    )
    expected = {
        "Notes/Owner.md": b"New prose [[Assets/data.bin]].",
        "Assets/data.bin": b"abc",
        "metadata.json": b'{"version":2}\n',
        ".obsidian/options.json": b'{"setting":2}\n',
        "Notes/New.md": b"New source note.\n",
    }
    assert {
        row.path: row.content.data for row in select_review_effects(plan).files
    } == expected
    for change in plan.proposal.changes:
        approval = next(
            (a for a in plan.approvals if a.change_id == change.change_id), None
        )
        owned = review_owned_targets(
            plan, change.change_id, None if approval is None else approval.decision_id
        )
        assert [(row.canonical_path, row.status) for row in owned] == [
            (change.target_path, "safe")
        ]


def test_automatic_inverse_authority_cannot_replace_explicit_or_unavailable_history():
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.core import (
        prepare_review,
        resolve_review,
        review_owned_targets,
        select_review_effects,
    )
    from tests.reconciliation.test_resolution import action, preflight
    from tests.reconciliation.test_reversal_absence import reversal_facts

    facts = automatic_mixed_inverse_facts()
    plan = prepare_review(facts, preflight=preflight())
    note = next(row for row in plan.proposal.changes if row.path == "Notes/Owner.md")
    subject = next(row for row in facts.subjects if row.path == note.path)
    explicit = resolve_review(
        plan,
        action(
            plan,
            note,
            choice="incoming",
            candidate=subject.automatic_result,
            decision_id="explicit:note",
        ),
    ).plan
    assert explicit.ready
    assert (
        review_owned_targets(explicit, note.change_id, "explicit:note")[
            0
        ].canonical_path
        == note.path
    )
    for origin, change_id, decision in (
        (plan, note.change_id, ""),
        (plan, note.change_id, "missing:decision"),
        (plan, "missing:change", None),
        (explicit, note.change_id, None),
        (explicit.model_copy(update={"approvals": ()}), note.change_id, None),
        (explicit.model_copy(update={"actions": ()}), note.change_id, None),
    ):
        with pytest.raises(ValueError):
            review_owned_targets(origin, change_id, decision)
    restored = type(explicit).model_validate_json(explicit.model_dump_json())
    assert restored == explicit
    assert (
        review_owned_targets(restored, note.change_id, "explicit:note")[
            0
        ].canonical_path
        == note.path
    )

    legacy = reversal_facts().subjects[0].operation_reversal
    raw = legacy.model_dump_json()
    assert '"origin_decision_id":"origin:decision"' in raw
    assert type(legacy).model_validate_json(raw).model_dump_json() == raw
    automatic = type(legacy).model_validate(
        legacy.model_copy(update={"origin_decision_id": None})
    )
    assert "origin_decision_id" not in automatic.model_dump()
    assert type(automatic).model_validate_json(automatic.model_dump_json()) == automatic
    with pytest.raises(ValidationError):
        type(legacy).model_validate(
            legacy.model_copy(update={"origin_decision_id": ""})
        )

    absent = subject.model_copy(update={"automatic_result": None})
    no_incoming = facts.link_context.model_copy(
        update={
            "incoming_documents": tuple(
                d
                for d in facts.link_context.incoming_documents
                if d.source_path != note.path
            )
        }
    )
    cases = (
        facts.model_copy(
            update={
                "format_operation": facts.format_operation.model_copy(
                    update={"automatic_merge": False}
                )
            }
        ),
        facts.model_copy(
            update={
                "subjects": tuple(
                    absent if s.path == note.path else s for s in facts.subjects
                ),
                "link_context": no_incoming,
            }
        ),
        facts.model_copy(
            update={
                "subjects": tuple(
                    s.model_copy(
                        update={
                            "incoming": None,
                            "automatic_result": None,
                            "structure": None,
                        }
                    )
                    if s.path == note.path
                    else s
                    for s in facts.subjects
                )
            }
        ),
    )
    for changed in cases:
        refused = prepare_review(changed, preflight=preflight())
        assert not refused.ready
        assert select_review_effects(refused).status == "refused"
        with pytest.raises(ValueError):
            review_owned_targets(
                refused,
                next(
                    c.change_id for c in refused.proposal.changes if c.path == note.path
                ),
                None,
            )


def test_mixed_automatic_apply_has_owned_reviewed_undo_with_exact_preimage():
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.update_context import UpdateContext
    from brz2obsidian.core import prepare_review
    from tests.application.test_onboarding_completion import authored_files
    from tests.application.test_update_context import worker_context_call
    from tests.application.test_vault_apply import _apply
    from tests.application.test_vault_checkpoints import fixture_case, git, user_state
    from tests.application.test_vault_recovery_process import _assert_user_state
    from tests.application.test_vault_undo import _operation_ref

    facts = automatic_mixed_inverse_facts()
    vault, source = fixture_case()
    for subject in facts.subjects:
        for root, value in (
            (vault, subject.current.content),
            (source, subject.baseline.content),
        ):
            if value is not None:
                target = root / subject.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(value.data)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Personal.md").write_bytes(b"Committed personal writing.\n")
    git(vault, "add", "Personal.md")
    git(vault, "commit", "-qm", "Independent mixed automatic Undo fixture")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    git(vault, "update-ref", "refs/brz2obsidian/unrelated-user-proof", "HEAD")
    (vault / "Personal.md").write_bytes(b"Staged personal writing.\n")
    git(vault, "add", "Personal.md")
    (vault / "Personal.md").write_bytes(b"Unstaged personal writing.\n")
    operations = Operations()
    seed = operations.capture_checkpoint(
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity=facts.incoming_identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert seed.status == "captured", seed.code
    original = authored_files(vault)
    user = user_state(vault)
    for subject in facts.subjects:
        target = source / subject.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subject.incoming.data)
    source_before = authored_files(source)
    review = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    assert review.ready and len(review.approvals) == 1
    applied = _apply(
        operations,
        vault,
        source,
        review=review,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert applied.status == "applied", applied.code
    expected = {
        "Notes/Owner.md": b"New prose [[Assets/data.bin]].",
        "Assets/data.bin": b"abc",
        "metadata.json": b'{"version":2}\n',
        ".obsidian/options.json": b'{"setting":2}\n',
        "Notes/New.md": b"New source note.\n",
        "Personal.md": b"Unstaged personal writing.\n",
    }
    assert authored_files(vault) == expected
    before_review = user_state(vault)
    undo = operations.prepare_undo(vault)
    assert undo.status == "offered", undo.code
    created = next(s for s in undo.review.facts.subjects if s.path == "Notes/New.md")
    proof = created.operation_reversal
    assert proof.origin_decision_id is None
    assert "origin_decision_id" not in proof.model_dump()
    assert proof.outputs[0].produced.data == b"New source note.\n"
    assert (
        proof.outputs[0].target is None
        and proof.outputs[0].target_existence == "absent"
    )
    assert type(undo).model_validate_json(undo.model_dump_json()) == undo
    wrong = created.model_copy(
        update={
            "operation_reversal": proof.model_copy(
                update={"origin_change_id": "missing:origin"}
            )
        }
    )
    forged = undo.model_copy(
        update={
            "review": undo.review.model_copy(
                update={
                    "facts": undo.review.facts.model_copy(
                        update={
                            "subjects": tuple(
                                wrong if s.path == created.path else s
                                for s in undo.review.facts.subjects
                            )
                        }
                    )
                }
            )
        }
    )
    refused = operations.execute_undo(vault, forged)
    assert refused.status == "refused" and not refused.authored_files_changed
    assert user_state(vault) == before_review

    context = UpdateContext(operations=operations)
    active = None

    def send(command, **values):
        result = worker_context_call(context, {"command": command, **values})
        assert result is not None, (command, "Expected typed worker terminal result")
        return result

    try:
        active = send(
            "history",
            vault=str(vault),
            selection_id="11111111-1111-4111-8111-111111111111",
        )
        assert "review_undo" in active.next_actions
        active = send("prepare_history", binding=active.binding, kind="undo")
        assert (
            active.status == "prepared_review"
            and active.binding.target_receipt_commit == applied.receipt_commit
        ), active
        page = send("page", binding=active.binding)
        assert {row.current_path: row.current for row in page.page.items} == {
            path: value for path, value in expected.items() if path != "Personal.md"
        }
        required = {(r.change_id, r.domain) for r in undo.review.requirements}
        for change_id, domain in sorted(required):
            offers = send("history_choices", binding=active.binding).offers
            offer = next(
                row
                for row in offers
                if row.change_id == change_id and row.domain == domain
            )
            choice = "reverse" if domain == "reversal" else "incoming"
            assert choice in offer.choices, (domain, offer.choices)
            if offer.reference_review and domain == "attachment":
                missing = send(
                    "choose_history",
                    binding=active.binding,
                    requirement_id=offer.requirement_id,
                    choice=choice,
                    assumptions_digest=offer.assumptions_digest,
                )
                assert missing.code == "reference_choices_required"
                assert missing.binding == active.binding
                assert user_state(vault) == before_review
                references = send(
                    "references",
                    binding=active.binding,
                    requirement_id=offer.requirement_id,
                )
                assert references.references
                assert all(
                    "use_incoming" in row.choices for row in references.references
                )
                active = send(
                    "stage_references",
                    binding=active.binding,
                    requirement_id=offer.requirement_id,
                    choices=tuple(
                        {"reference_id": row.reference_id, "choice": "use_incoming"}
                        for row in references.references
                    ),
                )
                assert active.code == "reference_choices_staged"
            active = send(
                "choose_history",
                binding=active.binding,
                requirement_id=offer.requirement_id,
                choice=choice,
                assumptions_digest=offer.assumptions_digest,
            )
            assert active.status == "prepared_review", active
        assert active.ready, active
        assert user_state(vault) == before_review
        active = send("execute_history", binding=active.binding)
        assert active.status == "undone", active
        completed = active.history_action.operation
        assert completed.publication == "complete" and completed.kind == "undo"
    finally:
        if active is not None and active.binding is not None:
            context.close(active.binding, choice="discard")
        else:
            context.close(choice="discard")
    assert authored_files(vault) == original
    assert authored_files(source) == source_before
    allowed = {
        seed.ref.encode(),
        _operation_ref(seed.ref, applied.operation_id),
        _operation_ref(seed.ref, completed.operation_id),
    }
    _assert_user_state(user, user_state(vault), allowed_refs=allowed)
    assert operations.prepare_undo(vault).status == "already_undone"
