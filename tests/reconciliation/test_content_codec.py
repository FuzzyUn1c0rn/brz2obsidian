"""Current content declarations preserve the exact legacy inline wire boundary."""

import pytest
from pydantic import TypeAdapter


def test_reversal_declares_exact_opaque_versions_and_distinguishes_absence():
    from brz2obsidian.contracts import (
        ContentIdentity,
        CurrentContent,
        ExactContent,
        OpaqueContent,
        OperationReversalOutput,
    )

    empty = OpaqueContent(
        identity=ContentIdentity(
            content_id="sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855:0",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            size=0,
        )
    )
    abc = OpaqueContent(
        identity=ContentIdentity(
            content_id="sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad:3",
            sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            size=3,
        )
    )
    common = {
        "path": "Manual.md",
        "target_id": "file:Manual.md",
        "current": CurrentContent(existence="absent", path="Manual.md", content=None),
    }
    removed = OperationReversalOutput(
        **common,
        produced_existence="present",
        produced=empty,
        target_existence="absent",
        target=None,
    )
    assert removed.produced == empty and removed.target is None
    restored = OperationReversalOutput(
        **common,
        produced_existence="absent",
        produced=None,
        target_existence="present",
        target=empty,
    )
    assert restored.produced is None and restored.target == empty
    changed = OperationReversalOutput(
        **common,
        produced_existence="present",
        produced=empty,
        target_existence="present",
        target=abc,
    )
    assert changed.produced == empty and changed.target == abc
    with pytest.raises(ValueError, match="exact proven version change"):
        OperationReversalOutput(
            **common,
            produced_existence="present",
            produced=empty,
            target_existence="present",
            target=ExactContent(data=b""),
        )


def test_legacy_mapping_gate_is_distinct_from_typed_and_current_content():
    # New declarations are imported in the call so the initial RED executes.
    from brz2obsidian.contracts import (
        ContentIdentity,
        ContentValue,
        ExactContent,
        InlineExactContent,
        OpaqueContent,
    )

    identity = ContentIdentity(
        content_id="sha256:db8fed54159afe40ace5b49d702259fd88c9c4009307181824487baab5c6bdea:2",
        sha256="db8fed54159afe40ace5b49d702259fd88c9c4009307181824487baab5c6bdea",
        size=2,
    )
    inline = ExactContent(data=b"\xfb\xff", identity=identity)
    assert ExactContent is InlineExactContent
    assert inline.model_dump() == {"data": b"\xfb\xff", "reference": None}
    assert inline.model_dump_json() == '{"data":"-_8=","reference":null}'
    assert (
        ExactContent.model_validate_json('{"reference":null,"data":"\\u002d_8="}')
        == inline
    )
    nested = TypeAdapter(tuple[ContentValue, ...])
    assert nested.dump_json((inline,)) == b'[{"data":"-_8=","reference":null}]'

    class LegacyMapping(dict):
        pass

    assert nested.validate_python((LegacyMapping(data=b"\xfb\xff"),)) == (inline,)
    declared = LegacyMapping(data=b"\xfb\xff", identity=identity)
    with pytest.raises(ValueError):
        ExactContent.model_validate(declared)
    with pytest.raises(ValueError):
        TypeAdapter(ExactContent).validate_python(declared)
    with pytest.raises(ValueError):
        nested.validate_python((declared,))
    with pytest.raises(ValueError):
        ExactContent.model_validate_json('{"data":"-_8=","kind":"inline"}')

    opaque = OpaqueContent(identity=identity)
    with pytest.raises(ValueError):
        opaque.model_dump_json()
    current = nested.dump_json((inline, opaque), context={"current_content": True})
    with pytest.raises(ValueError):
        nested.validate_json(current)
    assert nested.validate_json(current, context={"current_content": True}) == (
        inline,
        opaque,
    )
    with pytest.raises(ValueError):
        nested.validate_json(
            b'[{"kind":"invented","data":"-_8="}]',
            context={"current_content": True},
        )


def test_content_copy_revalidates_bytes_identity_and_legacy_reference():
    from brz2obsidian.contracts import (
        ContentIdentity,
        ExactContent,
        ImmutableContentReference,
        OpaqueContent,
    )

    fbff = ContentIdentity(
        content_id="sha256:db8fed54159afe40ace5b49d702259fd88c9c4009307181824487baab5c6bdea:2",
        sha256="db8fed54159afe40ace5b49d702259fd88c9c4009307181824487baab5c6bdea",
        size=2,
    )
    abc = ContentIdentity(
        content_id="sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad:3",
        sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        size=3,
    )
    reference = ImmutableContentReference(
        content_id="literal:fbff",
        sha256="db8fed54159afe40ace5b49d702259fd88c9c4009307181824487baab5c6bdea",
        size=2,
    )
    original = ExactContent(data=b"\xfb\xff", occurrence=("record", "inline"))
    copied = original.model_copy(update={"data": b"abc"})
    assert copied.data == b"abc" and copied.identity == abc
    assert copied.reference is None and copied.occurrence is None
    assert copied.model_dump_json() == '{"data":"YWJj","reference":null}'
    assert original.data == b"\xfb\xff" and original.identity == fbff
    unchanged = original.model_copy(update={"data": b"\xfb\xff"}, deep=True)
    assert unchanged == original and unchanged.occurrence == original.occurrence
    with pytest.raises(ValueError):
        original.model_copy(update={"data": b"abc", "identity": fbff})
    with pytest.raises(ValueError):
        original.model_copy(update={"data": b"abc", "occurrence": original.occurrence})
    with pytest.raises(ValueError):
        original.model_copy(update={"occurrence": ("foreign", "inline")})

    referenced = ExactContent(data=b"\xfb\xff", reference=reference)
    assert referenced.model_copy().reference == reference
    with pytest.raises(ValueError):
        referenced.model_copy(update={"data": b"abc"})
    assert (
        referenced.model_copy(
            update={"data": b"abc", "identity": abc, "reference": None}
        ).identity
        == abc
    )

    opaque = OpaqueContent(
        identity=fbff, reference=reference, occurrence=("record", "opaque")
    )
    same = opaque.model_copy(update={"identity": fbff}, deep=True)
    assert same == opaque and same.reference == reference
    assert same.occurrence == opaque.occurrence
    with pytest.raises(ValueError):
        opaque.model_copy(update={"identity": abc})
    changed = opaque.model_copy(update={"identity": abc, "reference": None})
    assert changed.identity == abc and changed.reference is None
    assert changed.occurrence is None
    with pytest.raises(ValueError):
        opaque.model_copy(
            update={"identity": abc, "reference": None, "occurrence": opaque.occurrence}
        )
    with pytest.raises(ValueError):
        opaque.model_copy(update={"occurrence": ("foreign", "opaque")})
    assert opaque.identity == fbff and opaque.reference == reference


def test_opaque_declarations_do_not_authorize_public_reconciliation():
    from brz2obsidian.contracts import (
        ContentIdentity,
        OpaqueContent,
        ProposedChange,
        ReconciliationInput,
    )
    from brz2obsidian.core import reconcile
    from tests.reconciliation.test_proposals import request

    facts = request(original=b"abc", current=b"abc", incoming=b"abc")
    control = reconcile(facts)
    (change,) = control.changes
    assert change.disposition == "no_change"
    assert change.path == "Notes/Opening.md" and change.result.data == b"abc"

    class SupportedMapping(dict):
        pass

    inline_mapping = SupportedMapping(facts.model_dump())
    assert reconcile(inline_mapping) == control
    identity = ContentIdentity(
        content_id="sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad:3",
        sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        size=3,
    )
    opaque = OpaqueContent(identity=identity)
    # A consistent no-change declaration is a value, not permission to act.
    declared = ProposedChange.model_validate(
        change.model_dump()
        | {"original": opaque, "current": opaque, "incoming": opaque, "result": opaque}
    )
    assert declared.result == opaque and declared.result.reference is None
    assert declared.disposition == "no_change"

    subject = facts.subjects[0].model_dump() | {"incoming": opaque}
    offered = SupportedMapping(inline_mapping | {"subjects": (subject,)})
    typed = ReconciliationInput.model_validate(offered)
    assert typed.subjects[0].incoming == opaque
    with pytest.raises(ValueError):
        reconcile(typed)
    with pytest.raises(ValueError):
        reconcile(offered)
    assert facts.subjects[0].incoming.data == b"abc"
    assert inline_mapping["subjects"][0]["incoming"] == {
        "data": b"abc",
        "reference": None,
    }


def test_opaque_attachment_values_refuse_with_validation_findings():
    from brz2obsidian.contracts import (
        AttachmentCandidate,
        AttachmentOutput,
        ContentIdentity,
        OpaqueContent,
        ReconciliationInput,
    )
    from brz2obsidian.core import validate_attachment_candidate
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
    )

    facts = attachment_request()
    selection, candidate = attachment_candidate(facts, "incoming")
    assert tuple(output.content.data for output in candidate.outputs) == (b"abc",)
    assert validate_attachment_candidate(facts, selection, candidate).valid
    identity = ContentIdentity(
        content_id="sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad:3",
        sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        size=3,
    )
    opaque = OpaqueContent(identity=identity)
    output_fields = candidate.outputs[0].model_dump() | {"content": opaque}
    declared_output = AttachmentOutput.model_validate(output_fields)
    assert declared_output.content == opaque
    assert declared_output.content_version == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    with pytest.raises(ValueError):
        AttachmentOutput.model_validate(output_fields | {"content_version": "0" * 64})

    class SupportedMapping(dict):
        pass

    candidate_mapping = SupportedMapping(
        candidate.model_dump() | {"outputs": (declared_output,)}
    )
    declared_candidate = AttachmentCandidate.model_validate(candidate_mapping)
    facts_mapping = SupportedMapping(
        facts.model_dump()
        | {"subjects": (facts.subjects[0].model_dump() | {"incoming": opaque},)}
    )
    declared_facts = ReconciliationInput.model_validate(facts_mapping)
    # Each distinct public argument graph is checked in typed and supported
    # mapping form; all four must return findings rather than byte-access errors.
    for offered_facts, offered_candidate in (
        (declared_facts, candidate),
        (facts_mapping, candidate),
        (facts, declared_candidate),
        (facts, candidate_mapping),
    ):
        refused = validate_attachment_candidate(
            offered_facts, selection, offered_candidate
        )
        assert not refused.valid
        assert any(
            finding.blocking and finding.code == "attachment_facts_invalid"
            for finding in refused.findings
        )
    assert facts.subjects[0].incoming.data == b"abc"
    assert candidate.outputs[0].content.data == b"abc"


def test_opaque_review_values_preserve_public_refusal_conventions():
    from brz2obsidian import core
    from brz2obsidian.contracts import (
        ContentIdentity,
        OpaqueContent,
        ReconciliationInput,
        ReviewPlan,
        SavedReview,
    )
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import (
        action,
        preflight,
        with_review_links,
    )

    facts = with_review_links(request(original=b"abc", current=b"abc", incoming=b"abc"))
    gate = preflight()
    plan = core.prepare_review(facts, preflight=gate)
    assert core.validate_review(plan).status == "accepted"
    assert plan.proposal.changes[0].result.data == b"abc"
    saved = core.save_review(plan)
    assert saved.status == "saved"
    loaded = core.load_review(saved.record.model_dump_json())
    assert loaded.status == "loaded" and not loaded.ready
    assert core.resume_review(loaded.loaded, facts, preflight=gate).status == "resumed"

    opaque = OpaqueContent(
        identity=ContentIdentity(
            content_id="sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad:3",
            sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            size=3,
        )
    )

    class SupportedMapping(dict):
        pass

    subject = facts.subjects[0].model_dump()
    subject["baseline"]["content"] = opaque
    subject["current"]["content"] = opaque
    facts_mapping = SupportedMapping(facts.model_dump() | {"subjects": (subject,)})
    declared_facts = ReconciliationInput.model_validate(facts_mapping)
    assert declared_facts.subjects[0].baseline.content == opaque
    assert declared_facts.subjects[0].current.content == opaque
    plan_mapping = SupportedMapping(plan.model_dump() | {"facts": declared_facts})
    declared_plan = ReviewPlan.model_validate(plan_mapping)
    offered_action = action(plan)

    for offered in (declared_facts, facts_mapping):
        with pytest.raises(ValueError):
            core.prepare_review(offered, preflight=gate)
        with pytest.raises(ValueError):
            core.refresh_review(plan, offered, preflight=gate)
        refused = core.resume_review(loaded.loaded, offered, preflight=gate)
        assert (refused.status, refused.code, refused.plan, refused.ready) == (
            "refused",
            "invalid_current_facts",
            None,
            False,
        )

    for offered in (declared_plan, plan_mapping):
        for operation in (
            core.validate_review,
            core.inspect_review_choices,
            lambda value: core.resolve_review(value, offered_action),
            lambda value: core.refresh_review(value, facts, preflight=gate),
            lambda value: core.review_owned_outputs(value, ()),
            lambda value: core.review_owned_target_groups(value, ()),
            lambda value: core.review_owned_targets(value, "unused", "unused"),
        ):
            with pytest.raises(ValueError):
                operation(offered)
        refused_save = core.save_review(offered)
        assert (refused_save.status, refused_save.code, refused_save.record) == (
            "refused",
            "invalid_review",
            None,
        )
        refused_effects = core.select_review_effects(offered)
        assert (refused_effects.status, refused_effects.code) == (
            "refused",
            "invalid_plan",
        )
        assert refused_effects.files == () and refused_effects.remove_paths == ()

    declared_saved = SavedReview.model_validate(
        saved.record.model_dump() | {"plan": declared_plan}
    )
    refused_load = core.load_review(declared_saved)
    assert (refused_load.status, refused_load.code, refused_load.loaded) == (
        "refused",
        "invalid_record",
        None,
    )
    assert facts.subjects[0].baseline.content.data == b"abc"
    assert facts.subjects[0].current.content.data == b"abc"
    assert core.validate_review(plan).status == "accepted"


def test_opaque_link_target_declarations_return_invalid_facts():
    from brz2obsidian.contracts import (
        ContentIdentity,
        ExactContent,
        LinkTargetFacts,
        OpaqueContent,
    )
    from brz2obsidian.core import validate_link_document
    from brz2obsidian.obsidian import interpret_link_target, interpret_links
    from tests.reconciliation.test_attachments import target_for_links

    target = target_for_links()
    state = interpret_link_target(
        ExactContent(data=b"abc"),
        target_id="note:guide",
        existence="present",
        memberships=(),
    )
    document = interpret_links(
        ExactContent(data=b"[[Docs/Guide|Read]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )
    arguments = {
        "expected_content": document.content,
        "expected_path": "Owner.md",
        "targets": (target,),
        "target_facts": (state,),
        "inventory": "complete",
    }
    assert document.occurrences[0].meaning.status == "resolved"
    assert validate_link_document(document, **arguments).valid
    opaque = OpaqueContent(
        identity=ContentIdentity(
            content_id="sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad:3",
            sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            size=3,
        )
    )

    class SupportedMapping(dict):
        pass

    mapping = SupportedMapping(state.model_dump() | {"content": opaque})
    declared = LinkTargetFacts.model_validate(mapping)
    assert declared.content == opaque and declared.anchors == ()
    for offered in (declared, mapping):
        refused = validate_link_document(
            document, **(arguments | {"target_facts": (offered,)})
        )
        assert not refused.valid
        assert any(
            f.blocking and f.code == "link_facts_invalid" for f in refused.findings
        )
    refused = validate_link_document(
        document, **(arguments | {"expected_content": opaque})
    )
    assert not refused.valid
    assert any(f.blocking and f.code == "link_facts_invalid" for f in refused.findings)
    assert (
        state.content.data == b"abc" and document.content.data == b"[[Docs/Guide|Read]]"
    )
