"""History review choices compile from canonical offers and bounded private bytes."""

from hashlib import sha256
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
from tests.application.test_history_workflow import (
    absent_history,
    operation_state,
    ready_native_recovery,
)
from tests.application.test_update_context import worker_context_call
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import preflight, with_review_links


@pytest.mark.parametrize("choice", ("incoming", "edited"))
def test_worker_history_text_choice_uses_canonical_candidate(
    tmp_path, monkeypatch, choice
):
    vault = tmp_path / "vault"
    vault.mkdir()
    current = b"Later writing\r\n"
    incoming = b"Reviewed incoming\r\n"
    edited = b"Reviewed introduction.\r\n" + b"Later exact bytes.\r\n" * 2200
    expected = edited if choice == "edited" else incoming
    leases = []
    if choice == "edited":
        import tempfile

        allocate = tempfile.TemporaryFile

        def owned_file(*args, **kwargs):
            handle = allocate(*args, **kwargs)
            leases.append(handle)
            return handle

        monkeypatch.setattr(tempfile, "TemporaryFile", owned_file)
    (vault / "Personal.md").write_bytes(current)
    plan = prepare_review(
        with_review_links(
            request(
                original=b"Earlier writing\r\n",
                current=current,
                incoming=incoming,
                generation=3,
            )
        ),
        preflight=preflight(),
    )
    assert not plan.ready and plan.requirements[0].domain == "text"
    native = ready_native_recovery(direction="finish").native.model_copy(
        update={"review": plan}
    )
    actions = []

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            return absent_history()

        def inspect_update_status(self, path):
            return operation_state("incomplete")

        def prepare_recovery(self, path, *, direction=None):
            assert direction == "finish"
            return native

        def resolve_recovery(self, path, previous, action):
            transition = resolve_review(previous.review, action)
            assert transition.status == "accepted", transition.code
            effects = select_review_effects(transition.plan)
            assert effects.status == "selected"
            assert [(row.path, row.content.data) for row in effects.files] == [
                ("Notes/Opening.md", expected)
            ]
            actions.append(action)
            return previous.model_copy(update={"review": transition.plan})

    context = UpdateContext(operations=NativePorts())
    opened = worker_context_call(
        context,
        {"command": "history", "vault": str(vault), "selection_id": str(uuid4())},
    )
    prepared = worker_context_call(
        context,
        {
            "command": "prepare_history",
            "binding": opened.binding,
            "kind": "recovery",
            "direction": "finish",
        },
    )
    offers = worker_context_call(
        context, {"command": "history_choices", "binding": prepared.binding}
    )
    offer = offers.offers[0]
    assert choice in offer.choices
    binding, handle = prepared.binding, None
    if choice == "edited":
        started = worker_context_call(
            context,
            {
                "command": "begin_edit",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "size": len(edited),
                "sha256": sha256(edited).hexdigest(),
            },
        )
        binding, handle = started.binding, started.edit.handle
        assert (
            started.draft_pending
            and binding.operation_generation == 7
            and binding.review_generation == 3
        )
        before_seal = worker_context_call(
            context,
            {
                "command": "choose_history",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "choice": choice,
                "assumptions_digest": offer.assumptions_digest,
                "edit_handle": handle,
            },
        )
        assert before_seal.code == "edit_unsealed" and not actions
        continued = worker_context_call(
            context, {"command": "close", "binding": binding, "choice": "continue"}
        )
        assert (
            continued.draft_pending
            and continued.binding == binding
            and not leases[0].closed
        )
        for offset in range(0, len(edited), 32768):
            chunk = worker_context_call(
                context,
                {
                    "command": "write_edit",
                    "handle": handle,
                    "offset": offset,
                    "data": edited[offset : offset + 32768],
                },
            )
            assert chunk.code == "edit_chunk_accepted"
        sealed = worker_context_call(
            context, {"command": "seal_edit", "handle": handle}
        )
        assert sealed.edit.sealed and sealed.edit.received_bytes == len(edited)
    selected = worker_context_call(
        context,
        {
            "command": "choose_history",
            "binding": binding,
            "requirement_id": offer.requirement_id,
            "choice": choice,
            "assumptions_digest": offer.assumptions_digest,
            **({"edit_handle": handle} if handle else {}),
        },
    )
    assert (
        selected.ready and selected.binding.review_generation == 3 and len(actions) == 1
    )
    page = worker_context_call(
        context, {"command": "page", "binding": selected.binding}
    )
    if choice == "edited":
        assert page.page.items[0].result == edited[:16384]
        assert page.page.items[0].next_byte_offset == 16384
        rest = worker_context_call(
            context,
            {"command": "page", "binding": selected.binding, "byte_offset": 16384},
        )
        assert rest.page.items[0].result == edited[16384:]
        assert rest.page.items[0].next_byte_offset is None
    else:
        assert page.page.items[0].result == incoming
    assert page.page.items[0].current == current
    assert (vault / "Personal.md").read_bytes() == current
    if handle is not None:
        assert not selected.draft_pending and leases[0].closed
        stale = worker_context_call(context, {"command": "seal_edit", "handle": handle})
        assert stale.code == "edit_changed" and len(actions) == 1
        reoffers = worker_context_call(
            context, {"command": "history_choices", "binding": selected.binding}
        )
        offered_again = reoffers.offers[0]
        second = worker_context_call(
            context,
            {
                "command": "begin_edit",
                "binding": selected.binding,
                "requirement_id": offered_again.requirement_id,
                "size": 0,
                "sha256": sha256(b"").hexdigest(),
            },
        )
        assert not leases[1].closed
        discarded = worker_context_call(
            context,
            {"command": "close", "binding": second.binding, "choice": "discard"},
        )
        assert (
            discarded.code == "context_closed"
            and discarded.binding is None
            and not discarded.draft_pending
        )
        assert leases[1].closed and len(actions) == 1


def test_worker_history_reverse_restores_retained_name_and_removes_published_name(
    tmp_path,
):
    from brz2obsidian.contracts import (
        CurrentContent,
        OperationReversalOutput,
        OperationReversalTarget,
    )

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Personal.md").write_bytes(b"Untouched personal bytes\r\n")
    facts = request(
        original=b"base\r\n", current=b"new\r\n", incoming=b"base\r\n", generation=3
    )
    subject = facts.subjects[0].model_copy(
        update={
            "path": "Authored/Name.md",
            "source_target": facts.subjects[0].source_target.model_copy(
                update={"normalized_path": "authored/name.md"}
            ),
        }
    )
    facts = with_review_links(facts.model_copy(update={"subjects": (subject,)}))
    current_target = facts.link_context.current_targets[0]
    retained_target = facts.link_context.incoming_targets[0]
    proof = OperationReversalTarget(
        schema_id="brz2obsidian.operation-reversal-target",
        schema_version=1,
        operation_id="1" * 32,
        operation_kind="apply",
        direction="restore",
        operation_generation=7,
        history_fingerprint="validated:inverse-rename",
        origin_change_id="origin:rename",
        origin_decision_id="origin:rename-choice",
        owned_targets=(retained_target, current_target),
        outputs=(
            OperationReversalOutput(
                path="Authored/Name.md",
                target_id=retained_target.target_id,
                produced_existence="absent",
                produced=None,
                current=CurrentContent(
                    path="Authored/Name.md", existence="absent", content=None
                ),
                target_existence="present",
                target=subject.incoming,
            ),
            OperationReversalOutput(
                path="Notes/Opening.md",
                target_id=current_target.target_id,
                produced_existence="present",
                produced=subject.current.content,
                current=subject.current,
                target_existence="absent",
                target=None,
            ),
        ),
    )
    facts = facts.model_copy(
        update={"subjects": (subject.model_copy(update={"operation_reversal": proof}),)}
    )
    plan = prepare_review(facts, preflight=preflight())
    assert [(row.domain, row.choices) for row in plan.requirements] == [
        ("reversal", ("current", "reverse", "edited"))
    ]
    native = ready_native_recovery(direction="restore").native.model_copy(
        update={"review": plan}
    )
    actions = []

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            return absent_history()

        def inspect_update_status(self, path):
            return operation_state("incomplete").model_copy(
                update={"direction": "restore"}
            )

        def prepare_recovery(self, path, *, direction=None):
            assert direction == "restore"
            return native

        def resolve_recovery(self, path, previous, action):
            transition = resolve_review(previous.review, action)
            assert transition.status == "accepted", transition.code
            selected = select_review_effects(transition.plan)
            assert selected.status == "selected"
            assert [(row.path, row.content.data) for row in selected.files] == [
                ("Authored/Name.md", b"base\r\n")
            ]
            assert selected.remove_paths == ("Notes/Opening.md",)
            assert action.candidate.links.source_path == "Authored/Name.md"
            actions.append(action)
            return previous.model_copy(update={"review": transition.plan})

    context = UpdateContext(operations=NativePorts())
    opened = worker_context_call(
        context,
        {"command": "history", "vault": str(vault), "selection_id": str(uuid4())},
    )
    prepared = worker_context_call(
        context,
        {
            "command": "prepare_history",
            "binding": opened.binding,
            "kind": "recovery",
            "direction": "restore",
        },
    )
    offers = worker_context_call(
        context, {"command": "history_choices", "binding": prepared.binding}
    )
    offer = offers.offers[0]
    selected = worker_context_call(
        context,
        {
            "command": "choose_history",
            "binding": prepared.binding,
            "requirement_id": offer.requirement_id,
            "choice": "reverse",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert selected.ready and len(actions) == 1
    assert (vault / "Personal.md").read_bytes() == b"Untouched personal bytes\r\n"


def test_worker_history_binary_reverse_pages_and_stages_exact_reference_choices(
    tmp_path,
):
    from tests.reconciliation.test_attachments import linked_attachment_request
    from tests.reconciliation.test_reversal_absence import single_proof

    vault = tmp_path / "vault"
    vault.mkdir()
    literal = b"Before [[Assets/data.bin|Keep first]] and [[Assets/data.bin|Redirect second]] after.\r\n`[[Assets/data.bin|code]]`"
    (vault / "Manual.md").write_bytes(literal)
    facts = linked_attachment_request(raw=literal)
    subject = facts.subjects[0]
    proof = single_proof(facts, produced=None, target=subject.incoming).model_copy(
        update={
            "operation_id": "1" * 32,
            "operation_generation": 7,
        }
    )
    facts = facts.model_copy(
        update={
            "generation": 3,
            "subjects": (subject.model_copy(update={"operation_reversal": proof}),),
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    assert [(row.domain, row.choices) for row in plan.requirements] == [
        ("reversal", ("current", "reverse"))
    ]
    native = ready_native_recovery(direction="restore").native.model_copy(
        update={"review": plan}
    )
    actions = []

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            return absent_history()

        def inspect_update_status(self, path):
            return operation_state("incomplete").model_copy(
                update={"direction": "restore"}
            )

        def prepare_recovery(self, path, *, direction=None):
            assert direction == "restore"
            return native

        def resolve_recovery(self, path, previous, action):
            transition = resolve_review(previous.review, action)
            assert transition.status == "accepted", transition.code
            effects = select_review_effects(transition.plan)
            assert effects.status == "selected" and effects.remove_paths == ()
            files = {row.path: row.content.data for row in effects.files}
            assert files["Assets/data.bin"] == b"abc"
            assert files.get("Notes/Owner.md", literal) == literal
            assert (
                action.choice == "reverse"
                and action.attachment_selection.choice == "incoming"
            )
            assert len(action.attachment_selection.link_choices) == 2
            assert [
                (row.source_path, row.content.data)
                for row in action.attachment_candidate.documents
            ] == [("Notes/Owner.md", literal)]
            actions.append(action)
            return previous.model_copy(
                update={"review": transition.plan, "code": "recovery_choice_recorded"}
            )

    context = UpdateContext(operations=NativePorts())
    opened = worker_context_call(
        context,
        {"command": "history", "vault": str(vault), "selection_id": str(uuid4())},
    )
    prepared = worker_context_call(
        context,
        {
            "command": "prepare_history",
            "binding": opened.binding,
            "kind": "recovery",
            "direction": "restore",
        },
    )
    offer = worker_context_call(
        context, {"command": "history_choices", "binding": prepared.binding}
    ).offers[0]
    binding = prepared.binding
    for command in ("references", "choice_details"):
        refused = worker_context_call(
            context,
            {
                "command": command,
                "binding": binding,
                "requirement_id": "unoffered-requirement",
            },
        )
        assert refused.code == "offer_changed" and refused.publication == "partial"
        assert refused.history_retained == prepared.history_retained
        assert refused.history_action == prepared.history_action
    bad_token = worker_context_call(
        context,
        {
            "command": "stage_references",
            "binding": binding,
            "requirement_id": offer.requirement_id,
            "choices": ({"reference_id": "0" * 64, "choice": "use_incoming"},),
        },
    )
    assert bad_token.code == "offer_changed" and bad_token.publication == "partial"
    assert bad_token.history_retained == prepared.history_retained
    assert bad_token.history_action == prepared.history_action and not actions
    tokens = []
    for offset in (0, 1):
        refs = worker_context_call(
            context,
            {
                "command": "references",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "offset": offset,
                "limit": 1,
            },
        )
        assert refs.total_references == 2 and len(refs.references) == 1
        assert refs.next_reference_offset == (1 if offset == 0 else None)
        row = refs.references[0]
        assert (
            row.document_path == "Notes/Owner.md"
            and row.old.target_id == "resource:payload"
        )
        assert "use_incoming" in row.choices and len(row.snippet) <= 512
        tokens.append(row.reference_id)
        staged = worker_context_call(
            context,
            {
                "command": "stage_references",
                "binding": binding,
                "requirement_id": offer.requirement_id,
                "choices": (
                    {"reference_id": row.reference_id, "choice": "use_incoming"},
                ),
            },
        )
        assert staged.draft_pending and staged.binding.revision > binding.revision
        stale = worker_context_call(
            context,
            {
                "command": "references",
                "binding": binding,
                "requirement_id": offer.requirement_id,
            },
        )
        assert stale.code == "context_changed"
        assert (
            stale.publication == "partial"
            and stale.history_retained == prepared.history_retained
        )
        assert stale.history_action == prepared.history_action
        binding = staged.binding
    assert len(set(tokens)) == 2
    detail = worker_context_call(
        context,
        {
            "command": "choice_details",
            "binding": binding,
            "requirement_id": offer.requirement_id,
            "limit": 1,
        },
    )
    assert (
        detail.status == "available"
        and detail.total_choice_details == 0
        and detail.choice_details == ()
    )
    selected = worker_context_call(
        context,
        {
            "command": "choose_history",
            "binding": binding,
            "requirement_id": offer.requirement_id,
            "choice": "reverse",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert selected.ready and not selected.draft_pending and len(actions) == 1
    assert (vault / "Manual.md").read_bytes() == literal
