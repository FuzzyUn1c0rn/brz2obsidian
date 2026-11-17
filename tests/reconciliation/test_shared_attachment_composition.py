"""Public review of independently selected attachments sharing a note."""

from hashlib import sha256

import pytest

from brz2obsidian.application.review_choices import (
    requirement_digest,
    review_plan_attachment_reference_page,
    review_plan_choice_action,
)
from brz2obsidian.contracts import (
    AttachmentDestination,
    ExactContent,
    IdentityTargetFacts,
    LinkContext,
)
from brz2obsidian.core import (
    inspect_review_choices,
    prepare_review,
    resolve_review,
    select_review_effects,
)
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.reconciliation.test_attachments import attachment_request, target_for_links
from tests.reconciliation.test_identity import inventory_item, with_subjects
from tests.reconciliation.test_resolution import preflight, request


@pytest.mark.parametrize("first", [b"", b"first incoming"])
@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
@pytest.mark.parametrize("keep_both", [False, True])
@pytest.mark.parametrize("output_format", [7, 8])
def test_shared_note_retains_both_explicit_incoming_meanings(
    first, order, keep_both, output_format
):
    base = attachment_request()
    payloads = (first, b"x" * 65537)
    subjects, inventory, targets, old, new = [], [], [], [], []
    incoming_path = f"Assets/0 (incoming-{sha256(first).hexdigest()[:8]}).bin"
    for index, payload in enumerate(payloads):
        path = f"Assets/{index}.bin"
        destination = AttachmentDestination(
            path=incoming_path,
            target=IdentityTargetFacts(
                normalized_path=incoming_path.lower(),
                containment="contained",
                status="safe",
            ),
        )
        entry = inventory_item(
            f"asset:{index}",
            "entry:opening",
            path,
            b"\x00current" + bytes([index]),
            facet=f"attachment:{index}",
        )
        subject = base.subjects[0].model_copy(
            update={
                "facet": entry.facet,
                "path": path,
                "current": entry.current,
                "source_target": entry.target,
                "incoming": ExactContent(data=payload),
                "attachment": base.subjects[0].attachment.model_copy(
                    update={
                        "current_target_id": f"resource:{index}",
                        "affected_documents": ("owner:0",),
                        "allocation_candidates": (destination,)
                        if index == 0 and keep_both
                        else (),
                    }
                ),
            }
        )
        subjects.append(subject)
        inventory.append(entry)
        targets.append(target_for_links(f"resource:{index}", path, kind="resource"))
        old.append(
            interpret_link_target(
                entry.current.content,
                target_id=f"resource:{index}",
                existence="present",
                memberships=(),
                source_path=path,
                output_format=output_format,
            )
        )
        new.append(
            interpret_link_target(
                subject.incoming,
                target_id=f"resource:{index}",
                existence="present",
                memberships=(),
                source_path=path,
                output_format=output_format,
            )
        )
    raw = b"[[Assets/0.bin|First]] [[Assets/1.bin|Second]]"
    entry = inventory_item("owner:0", "entry:opening", "Notes/Owner0.md", raw)
    inventory.append(entry)
    owner = (
        request(original=raw, current=raw, incoming=raw)
        .subjects[0]
        .model_copy(
            update={
                "item_id": "entry:opening",
                "path": entry.current.path,
                "current": entry.current,
                "source_target": entry.target,
            }
        )
    )
    subjects.append(owner)
    targets.append(
        target_for_links("owner:0", entry.current.path).model_copy(
            update={"identity": entry.identity}
        )
    )
    state = interpret_link_target(
        entry.current.content,
        target_id="owner:0",
        existence="present",
        memberships=(),
        source_path=entry.current.path,
        output_format=output_format,
    )
    old.append(state)
    new.append(state)
    args = {
        "document_id": "owner:0",
        "source_path": entry.current.path,
        "path_mode": "vault",
        "targets": tuple(targets),
        "inventory": "complete",
        "output_format": output_format,
        "record_format": output_format,
    }
    current = interpret_links(entry.current.content, target_facts=tuple(old), **args)
    incoming = interpret_links(entry.current.content, target_facts=tuple(new), **args)
    facts = with_subjects(base, tuple(subjects), tuple(inventory)).model_copy(
        update={
            "link_context": LinkContext(
                schema_id="brz2obsidian.link-context",
                schema_version=1,
                inventory="complete",
                current_targets=tuple(targets),
                incoming_targets=tuple(targets),
                current_target_facts=tuple(old),
                incoming_target_facts=tuple(new),
                current_documents=(current,),
                incoming_documents=(incoming,),
            )
        }
    )
    if output_format == 8:
        baseline = facts.baseline_identity.model_copy(update={"output_format": 8})
        facts = facts.model_copy(
            update={
                "baseline_identity": baseline,
                "incoming_identity": facts.incoming_identity.model_copy(
                    update={"output_format": 8}
                ),
                "format_operation": facts.format_operation.model_copy(
                    update={
                        "established_baseline": facts.format_operation.established_baseline.model_copy(
                            update={"identity": baseline}
                        )
                    }
                ),
            }
        )
    plan = prepare_review(facts, preflight=preflight())
    for index in order:
        offer = next(
            row
            for row in inspect_review_choices(plan)
            if row.domain == "attachment"
            and next(
                c for c in plan.proposal.changes if c.change_id == row.change_id
            ).facet
            == f"attachment:{index}"
        )
        references, total, following = review_plan_attachment_reference_page(
            plan, offer.requirement_id
        )
        assert following is None and total == len(references) == 1
        action = review_plan_choice_action(
            plan,
            requirement_id=offer.requirement_id,
            choice="both" if keep_both and index == 0 else "incoming",
            assumptions_digest=requirement_digest(offer),
            references=tuple(
                {
                    "reference_id": row.reference_id,
                    "choice": "use_secondary"
                    if keep_both and index == 0
                    else "use_incoming",
                }
                for row in references
            ),
        )
        result = resolve_review(plan, action)
        assert result.code == "accepted"
        plan = result.plan
    assert not plan.requirements and not plan.blockers and plan.ready
    effects = select_review_effects(plan)
    assert effects.status == "selected"
    files = {row.path: row.content.data for row in effects.files}
    assert files["Assets/0.bin"] == (b"\x00current\x00" if keep_both else payloads[0])
    if keep_both:
        assert files[incoming_path] == payloads[0]
    assert files["Assets/1.bin"] == payloads[1]
    expected_note = (
        f"[[{incoming_path}|First]] [[Assets/1.bin|Second]]".encode()
        if keep_both
        else raw
    )
    assert files.get("Notes/Owner0.md", raw) == expected_note
    selected = [
        choice.selected
        for approval in plan.approvals
        if approval.attachment_selection
        for choice in approval.attachment_selection.link_choices
    ]
    assert {(m.target_id, m.target_version) for m in selected} == {
        (
            f"resource:{i}"
            + (
                f":incoming:{sha256(payload).hexdigest()}"
                if keep_both and i == 0
                else ""
            ),
            sha256(payload).hexdigest(),
        )
        for i, payload in enumerate(payloads)
    }
