"""One admitted current-family review through the public lexical facade."""

import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.vault_contracts import VaultSubject
from tests.application.test_checkpoint_payload import git

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/saved_reviews/memory-347"
OWNER = "ba1c4d1118161042cdba372561029f4e57204cdca8aa4a8645dc8d2e382b39cd"


@pytest.fixture(scope="module")
def review_vault():
    # Root's whole-phase256MiB reservation is not renewed by this fixture.
    assert shutil.disk_usage(tempfile.gettempdir()).free >= 256 * 1024 * 1024
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-357-review-"))
    owner = {"root": str(root), "owner": uuid4().hex, "per_run_reservation": 8 << 20}
    (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    records = Path(__file__).resolve().parents[2] / "tmp/current-content-family"
    records.mkdir(exist_ok=True, parents=True)
    (records / (owner["owner"] + ".json")).write_text(
        json.dumps(owner), encoding="utf-8"
    )
    vault, source, scratch = (root / name for name in ("vault", "source", "scratch"))
    for path in (vault, source, scratch):
        path.mkdir()
    for parent, content in ((vault, b"\x00authored"), (source, b"abc")):
        (parent / "Assets").mkdir()
        (parent / "Assets/data.bin").write_bytes(content)
    git(vault, "init", "-q")
    operations = Operations()
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="review-session-vault",
        import_id="review-session-import",
        identity={
            "collection_id": "review-session",
            "module_id": "fixture",
            "module_version": "1",
            "profile_id": "profile",
            "profile_version": "1",
            "output_format": 7,
            "settings_digest": "literal-settings",
        },
        admission=operations.inspect_vault(vault),
        review=None,
        boundary="local",
    )
    assert captured.status == "captured"
    return vault, scratch


def test_frozen_both_refresh_loads_descriptors_and_stages_exact_owned_effects(
    review_vault,
):
    from brz2obsidian.application.review_session import ReviewBudget, ReviewSession
    from brz2obsidian.contracts import OpaqueContent

    vault, scratch = review_vault
    raw = (FIXTURES / "attachment.inline.json").read_bytes()
    before = (vault / "Assets/data.bin").read_bytes(), git(vault, "for-each-ref")
    limits = ReviewBudget(
        metadata_limit=8 << 20,
        node_limit=262144,
        depth_limit=256,
        decoded_limit=64 << 20,
        raw_work_limit=128 << 20,
        encoded_limit=128 << 20,
        request_limit=4096,
        step_limit=100000,
        timeout=120,
        cancel=Event(),
    )
    with (
        Operations().inspect_update_inputs(vault) as observed,
        ReviewSession(observed, scratch_parent=scratch, budget=limits) as session,
    ):
        loaded = session.load_review(raw)
        assert loaded.status == "loaded" and loaded.code == "loaded"
        assert not loaded.ready and not loaded.loaded.ready
        assert loaded.loaded.readiness == "revalidation_required"
        plan = loaded.loaded.saved.plan
        change = plan.proposal.changes[0]
        assert all(
            type(content) is OpaqueContent
            for content in (change.original, change.current, change.incoming)
        )
        assert plan.proposal.generation == 2
        assert [
            (
                action.decision_id,
                action.domain,
                action.choice,
                action.expected_generation,
            )
            for action in plan.actions
        ] == [
            ("legacy:both", "attachment", "both", 1),
            ("legacy:consent", "storage", "accept", 1),
        ]
        approval = plan.approvals[0]
        assert approval.decision_id == "legacy:both"
        assert approval.provenance == "explicit_user"
        assert approval.attachment_selection.generation == 1
        assert approval.attachment_selection.provenance == "explicit_user"
        assert plan.consents[0].decision_id == "legacy:consent"
        assert plan.consents[0].provenance == "explicit_user"
        assert plan.history.initial_preflight.consents[0].subjects == (OWNER,)
        refresh = plan.history.events[-1]
        assert refresh.expected_generation == 1 and refresh.invalidated_keys == ()
        assert [
            (row.decision_id, row.subject_id, row.domain, row.origin_generation)
            for row in refresh.retained
        ] == [("legacy:both", OWNER, "attachment", 1)]
        # Real physical current/output scope is freshly checked outside the
        # bounded proof phase. Frozen logical source/risk facts remain separate.
        admission = observed.inspect(
            subjects=(
                VaultSubject(path="Assets/data.bin", subject_id=OWNER),
                VaultSubject(
                    path="Assets/data (incoming-ba7816bf).bin", subject_id=OWNER
                ),
            )
        )
        resumed = session.resume_review(
            loaded.loaded,
            plan.producer_facts,
            preflight=plan.preflight,
            admission=admission,
        )
        assert resumed.status == "resumed" and resumed.code == "unchanged"
        assert resumed.ready and not loaded.loaded.ready
        assert resumed.plan.actions == plan.actions
        assert resumed.plan.history.events == plan.history.events
        effects = session.select_review_effects(resumed.plan)
        assert effects.status == "selected" and effects.generation == 2
        assert effects.remove_paths == ()
        assert [(row.path, row.subject_id) for row in effects.files] == [
            ("Assets/data (incoming-ba7816bf).bin", OWNER),
            ("Assets/data.bin", OWNER),
        ]
        stages = [session.stage_effect(row) for row in effects.files]
        assert all(type(row.content) is OpaqueContent for row in effects.files)
        assert [stage.path.read_bytes() for stage in stages] == [
            b"abc",
            b"\x00authored",
        ]
    assert all(not stage.path.exists() for stage in stages)
    assert (
        (vault / "Assets/data.bin").read_bytes(),
        git(vault, "for-each-ref"),
    ) == before


def test_changed_candidate_byte_with_original_proofs_has_no_load_authority(
    review_vault,
):
    from brz2obsidian.application.review_session import ReviewBudget, ReviewSession

    vault, scratch = review_vault
    original = (FIXTURES / "attachment.inline.json").read_bytes()
    record = json.loads(original)
    output = record["plan"]["history"]["events"][0]["attachment_candidate"]["outputs"][
        1
    ]
    assert output["path"] == "Assets/data (incoming-ba7816bf).bin"
    assert output["content"] == {"data": "YWJj", "reference": None}
    output["content"]["data"] = "YWJk"  # Literal abc -> abd; preserve all old proofs.
    tampered = json.dumps(record, separators=(",", ":"), ensure_ascii=True).encode()
    assert len(tampered) == len(original)
    assert sum(a != b for a, b in zip(original, tampered, strict=True)) == 1
    before = (vault / "Assets/data.bin").read_bytes(), git(vault, "for-each-ref")
    limits = ReviewBudget(
        metadata_limit=8 << 20,
        node_limit=262144,
        depth_limit=256,
        decoded_limit=64 << 20,
        raw_work_limit=128 << 20,
        encoded_limit=128 << 20,
        request_limit=4096,
        step_limit=100000,
        timeout=120,
        cancel=Event(),
    )
    with (
        Operations().inspect_update_inputs(vault) as observed,
        ReviewSession(observed, scratch_parent=scratch, budget=limits) as session,
    ):
        refused = session.load_review(tampered)
        assert refused.status == "refused" and refused.code == "invalid_review"
        assert refused.loaded is None and not refused.ready
    assert (FIXTURES / "attachment.inline.json").read_bytes() == original
    assert (
        (vault / "Assets/data.bin").read_bytes(),
        git(vault, "for-each-ref"),
    ) == before


def test_typed_reconstruction_reserves_before_new_graph_ownership(review_vault):
    from brz2obsidian.application.review_session import ReviewBudget, ReviewSession
    from brz2obsidian.core import load_review

    vault, scratch = review_vault
    raw = (FIXTURES / "attachment.inline.json").read_bytes()
    # Caller-owned typed convenience input: this old inline parse/replay is an
    # explicit setup cost, never the bounded raw descriptor ingress.
    old = load_review(raw)
    assert old.status == "loaded"
    saved = old.loaded.saved
    original_wire = saved.model_dump_json()
    before = (vault / "Assets/data.bin").read_bytes(), git(vault, "for-each-ref")
    before_scratch = tuple(scratch.iterdir())
    for metadata, nodes, expected in (
        (8 << 20, 262144, "loaded"),
        # 64KiB admits fixed refusal/workspace escrow; the supplied SavedReview
        # graph exceeds it. One node admits the root reservation visit only.
        (65536, 262144, "refused"),
        (8 << 20, 1, "refused"),
    ):
        limits = ReviewBudget(
            metadata_limit=metadata,
            node_limit=nodes,
            depth_limit=256,
            decoded_limit=64 << 20,
            raw_work_limit=128 << 20,
            encoded_limit=128 << 20,
            request_limit=4096,
            step_limit=100000,
            timeout=120,
            cancel=Event(),
        )
        with (
            Operations().inspect_update_inputs(vault) as observed,
            ReviewSession(observed, scratch_parent=scratch, budget=limits) as session,
        ):
            result = session.load_review(saved)
            assert result.status == expected
            assert not result.ready
            if expected == "loaded":
                assert result.loaded.readiness == "revalidation_required"
                assert result.loaded.saved.plan.proposal.generation == 2
                assert tuple(
                    a.decision_id for a in result.loaded.saved.plan.actions
                ) == (
                    "legacy:both",
                    "legacy:consent",
                )
                assert (
                    result.loaded.saved.plan.approvals[0].provenance == "explicit_user"
                )
            else:
                assert result.code == "invalid_review" and result.loaded is None
        assert tuple(scratch.iterdir()) == before_scratch
    assert saved.model_dump_json() == original_wire
    assert (FIXTURES / "attachment.inline.json").read_bytes() == raw
    assert (
        (vault / "Assets/data.bin").read_bytes(),
        git(vault, "for-each-ref"),
    ) == before


@pytest.fixture(scope="module")
def composition_vault():
    # Share only immutable physical setup; each test opens its own observation.
    # Lazy creation keeps the inline composition control before Git setup.
    prepared = []

    def create():
        if prepared:
            return prepared[0]
        # A separate owner retains the real fixture and all failure evidence.
        # Neither candidate nor the composed output is written into current facts.
        assert shutil.disk_usage(tempfile.gettempdir()).free >= 256 * 1024 * 1024
        root = Path(tempfile.mkdtemp(prefix="brz2obsidian-357-review-"))
        owner = {
            "root": str(root),
            "owner": uuid4().hex,
            "per_run_reservation": 8 << 20,
        }
        (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
        records = Path(__file__).resolve().parents[2] / "tmp/current-content-family"
        records.mkdir(exist_ok=True, parents=True)
        (records / (owner["owner"] + ".json")).write_text(
            json.dumps(owner), encoding="utf-8"
        )
        vault, source, scratch = (
            root / name for name in ("vault", "source", "scratch")
        )
        for path in (vault, source, scratch):
            path.mkdir()
        for parent, binary_bytes, note_bytes in (
            (vault, b"\x00authored", b"Old prose [[Assets/data.bin]]."),
            (source, b"abc", b"New prose [[Assets/data.bin]]."),
        ):
            (parent / "Assets").mkdir()
            (parent / "Notes").mkdir()
            (parent / "Assets/data.bin").write_bytes(binary_bytes)
            (parent / "Notes/Owner.md").write_bytes(note_bytes)
        absent = vault / "Assets/data (incoming-ba7816bf).bin"
        assert not absent.exists()
        git(vault, "init", "-q")
        operations = Operations()
        captured = operations.capture_checkpoint(
            vault,
            source,
            vault_id="composition-vault",
            import_id="composition-import",
            identity={
                "collection_id": "review-session",
                "module_id": "fixture",
                "module_version": "1",
                "profile_id": "profile",
                "profile_version": "1",
                "output_format": 7,
                "settings_digest": "literal-settings",
            },
            admission=operations.inspect_vault(vault),
            review=None,
            boundary="local",
        )
        assert captured.status == "captured"

        prepared.append((vault, source, scratch))
        return prepared[0]

    return create


def test_edited_prose_and_reference_choice_create_owned_composed_content(
    composition_vault,
):
    from brz2obsidian.application.review_session import ReviewBudget, ReviewSession
    from brz2obsidian.contracts import ExactContent, InlineExactContent, OpaqueContent
    from brz2obsidian.core import (
        load_review,
        prepare_review,
        resolve_review,
        save_review,
        select_review_effects,
    )
    from brz2obsidian.obsidian import inspect_text_candidate, interpret_link_target
    from tests.reconciliation.test_resolution import (
        action,
        note_and_attachment_request,
        preflight,
        redirected_attachment_choice,
    )

    # Caller-owned inline setup establishes the existing semantic algorithm.
    # It is an explicit setup cost, not bounded descriptor-ingress evidence.
    facts = note_and_attachment_request()
    offered = prepare_review(facts, preflight=preflight())
    note = next(c for c in offered.proposal.changes if c.path == "Notes/Owner.md")
    edited_content = ExactContent(data=b"Edited prose [[Assets/data.bin]].")
    edited_state = interpret_link_target(
        edited_content,
        target_id="owner:note",
        existence="present",
        memberships=(),
        source_path="Notes/Owner.md",
        output_format=7,
    )
    # Interpret only the candidate's own document; external targets retain
    # their current facts, as in the existing public candidate construction.
    candidate_states = tuple(
        edited_state if state.target_id == "owner:note" else state
        for state in facts.link_context.current_target_facts
    )
    text = inspect_text_candidate(
        edited_content,
        identity=facts.identity_inventory[1].identity,
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Owner.md",
        document_id="owner:note",
        path_mode="vault",
        link_targets=facts.link_context.current_targets,
        link_target_facts=candidate_states,
        link_inventory="complete",
    )
    edited = resolve_review(
        offered,
        action(
            offered,
            note,
            choice="edited",
            decision_id="stage-b:text",
            candidate=text,
        ),
    )
    assert edited.status == "accepted"
    binary = next(
        c for c in edited.plan.proposal.changes if c.path == "Assets/data.bin"
    )
    selection, candidate = redirected_attachment_choice(facts)
    accepted = resolve_review(
        edited.plan,
        action(
            edited.plan,
            binary,
            domain="attachment",
            choice="both",
            decision_id="stage-b:both",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert accepted.status == "accepted" and accepted.plan.ready
    expected = {
        "Notes/Owner.md": b"Edited prose [[Assets/data (incoming-ba7816bf).bin]].",
        "Assets/data.bin": b"\x00authored",
        "Assets/data (incoming-ba7816bf).bin": b"abc",
    }
    inline_effects = select_review_effects(accepted.plan)
    assert inline_effects.status == "selected" and inline_effects.remove_paths == ()
    assert {row.path: row.content.data for row in inline_effects.files} == expected
    assert tuple(a.decision_id for a in accepted.plan.actions) == (
        "stage-b:text",
        "stage-b:both",
    )
    assert tuple(a.provenance for a in accepted.plan.approvals) == (
        "explicit_user",
        "explicit_user",
    )
    saved = save_review(accepted.plan)
    assert saved.status == "saved"
    original_wire = saved.record.model_dump_json()
    # Caller serialization uses the unchanged default v1 codec. Raw ingress
    # selects descriptors; the separate typed convenience test stays inline.
    wire_bytes = original_wire.encode("utf-8")
    inline_loaded = load_review(original_wire)
    assert inline_loaded.status == "loaded" and not inline_loaded.ready
    assert inline_loaded.loaded.readiness == "revalidation_required"

    vault, source, scratch = composition_vault()
    absent = vault / "Assets/data (incoming-ba7816bf).bin"
    operations = Operations()
    physical_paths = tuple(
        parent / path
        for parent in (vault, source)
        for path in ("Assets/data.bin", "Notes/Owner.md")
    )
    before = tuple(path.read_bytes() for path in physical_paths)
    before_refs = git(vault, "for-each-ref")
    limits = ReviewBudget(
        metadata_limit=64 << 20,
        node_limit=1048576,
        depth_limit=256,
        decoded_limit=64 << 20,
        raw_work_limit=128 << 20,
        encoded_limit=128 << 20,
        request_limit=4096,
        step_limit=2000000,
        timeout=120,
        cancel=Event(),
    )
    with (
        operations.inspect_update_inputs(vault) as observed,
        ReviewSession(observed, scratch_parent=scratch, budget=limits) as session,
    ):
        loaded = session.load_review(wire_bytes)
        assert loaded.status == "loaded" and not loaded.ready
        assert loaded.loaded.readiness == "revalidation_required"
        plan = loaded.loaded.saved.plan
        assert tuple(a.decision_id for a in plan.actions) == (
            "stage-b:text",
            "stage-b:both",
        )
        assert tuple(a.provenance for a in plan.approvals) == (
            "explicit_user",
            "explicit_user",
        )
        binary_change = next(
            c for c in plan.proposal.changes if c.path == "Assets/data.bin"
        )
        assert type(binary_change.current) is OpaqueContent
        binary_state = next(
            state
            for state in plan.producer_facts.link_context.current_target_facts
            if state.target_id == "resource:payload"
        )
        assert binary_state.structure.status == "opaque"
        assert type(binary_state.structure.content) is OpaqueContent
        assert type(binary_state.content) is OpaqueContent
        note_state = next(
            state
            for state in plan.producer_facts.link_context.current_target_facts
            if state.target_id == "owner:note"
        )
        assert note_state.structure.status == "supported"
        assert type(note_state.structure.content) is InlineExactContent
        assert type(note_state.content) is InlineExactContent
        # Four logical owner pairs cover the same three physical files: the
        # attachment decision also owns its explicit reference edit in the note.
        admission = observed.inspect(
            subjects=tuple(
                VaultSubject(path=row.path, subject_id=row.subject_id)
                for row in inline_effects.files
            )
            + (
                VaultSubject(
                    path="Notes/Owner.md", subject_id=binary_change.subject_id
                ),
            )
        )
        resumed = session.resume_review(
            loaded.loaded,
            plan.producer_facts,
            preflight=plan.preflight,
            admission=admission,
        )
        assert resumed.status == "resumed" and resumed.code == "unchanged"
        assert resumed.ready and not loaded.loaded.ready
        assert resumed.plan.actions == plan.actions
        assert resumed.plan.history.events == plan.history.events
        effects = session.select_review_effects(resumed.plan)
        assert effects.status == "selected" and effects.remove_paths == ()
        generated = next(row for row in effects.files if row.path == "Notes/Owner.md")
        assert generated.content.reference is None
        stages = [(row.path, session.stage_effect(row)) for row in effects.files]
        assert {path: stage.path.read_bytes() for path, stage in stages} == expected
    assert all(not stage.path.exists() for _, stage in stages)
    assert tuple(scratch.iterdir()) == ()
    assert tuple(path.read_bytes() for path in physical_paths) == before
    assert git(vault, "for-each-ref") == before_refs and not absent.exists()
    assert saved.record.model_dump_json() == original_wire


def test_raw_review_with_unknown_nested_extra_has_no_load_authority(composition_vault):
    from brz2obsidian.application.review_session import ReviewBudget, ReviewSession

    original = (FIXTURES / "attachment.inline.json").read_bytes()
    record = json.loads(original)
    event = record["plan"]["history"]["events"][0]
    assert "unexpected" not in event
    event["unexpected"] = {"nested": [{"literal": "must not acquire authority"}]}
    wire = json.dumps(record, separators=(",", ":"), ensure_ascii=True).encode()
    vault, source, scratch = composition_vault()
    paths = tuple(
        parent / path
        for parent in (vault, source)
        for path in ("Assets/data.bin", "Notes/Owner.md")
    )
    before = tuple(path.read_bytes() for path in paths), git(vault, "for-each-ref")
    before_scratch = tuple(scratch.iterdir())
    limits = ReviewBudget(
        metadata_limit=8 << 20,
        node_limit=262144,
        depth_limit=256,
        decoded_limit=64 << 20,
        raw_work_limit=128 << 20,
        encoded_limit=128 << 20,
        request_limit=4096,
        step_limit=100000,
        timeout=120,
        cancel=Event(),
    )
    with (
        Operations().inspect_update_inputs(vault) as observed,
        ReviewSession(observed, scratch_parent=scratch, budget=limits) as session,
    ):
        refused = session.load_review(wire)
        assert refused.status == "refused" and refused.code == "invalid_review"
        assert refused.loaded is None and not refused.ready
    assert tuple(scratch.iterdir()) == before_scratch
    assert (
        tuple(path.read_bytes() for path in paths),
        git(vault, "for-each-ref"),
    ) == before
    assert (FIXTURES / "attachment.inline.json").read_bytes() == original
    assert wire == json.dumps(record, separators=(",", ":"), ensure_ascii=True).encode()


def test_opaque_structure_keep_preserves_descriptor_alignment_obligations(review_vault):
    from brz2obsidian.application.review_session import ReviewBudget, ReviewSession
    from brz2obsidian.contracts import InlineExactContent, OpaqueContent
    from brz2obsidian.core import prepare_review, save_review
    from tests.reconciliation.test_resolution import preflight
    from tests.reconciliation.test_structure import structured_request

    original = b"Original.\n"
    current = b"\xff\x00---\r\nduplicate: true\nduplicate: false\n"
    facts = structured_request(original, current, original)
    plan = prepare_review(facts, preflight=preflight())
    change = plan.proposal.changes[0]
    assert plan.proposal.ready and change.disposition == "preserve_vault"
    assert change.result.data == current and change.structure_result is None
    comparison = facts.subjects[0].structure
    assert comparison.alignment == "supported"
    assert comparison.local_edits[0].expected == original
    assert comparison.local_edits[0].replacement == current
    assert comparison.source_edits == ()
    saved = save_review(plan)
    assert saved.status == "saved"
    wire = saved.record.model_dump_json()
    vault, scratch = review_vault
    before = (vault / "Assets/data.bin").read_bytes(), git(vault, "for-each-ref")
    before_scratch = tuple(scratch.iterdir())
    limits = ReviewBudget(
        metadata_limit=64 << 20,
        node_limit=1048576,
        depth_limit=256,
        decoded_limit=64 << 20,
        raw_work_limit=128 << 20,
        encoded_limit=128 << 20,
        request_limit=4096,
        step_limit=2000000,
        timeout=120,
        cancel=Event(),
    )
    with (
        Operations().inspect_update_inputs(vault) as observed,
        ReviewSession(observed, scratch_parent=scratch, budget=limits) as session,
    ):
        result = session.load_review(wire.encode())
        assert result.status == "loaded" and not result.ready
        loaded = result.loaded.saved.plan
        assert loaded.proposal.ready
        assert loaded.proposal.changes[0].disposition == "preserve_vault"
        assert type(loaded.proposal.changes[0].result) is OpaqueContent
        actual = loaded.facts.subjects[0].structure
        assert actual.alignment == "supported"
        assert actual.local_edits[0].expected == original
        assert actual.local_edits[0].replacement == current
        assert actual.source_edits == ()
        assert type(actual.current.content) is InlineExactContent
        assert actual.current.content.data == current
        assert loaded.proposal.changes[0].structure_result is None
    assert tuple(scratch.iterdir()) == before_scratch
    assert (
        (vault / "Assets/data.bin").read_bytes(),
        git(vault, "for-each-ref"),
    ) == before
    assert saved.record.model_dump_json() == wire


def test_descriptor_onboarding_retains_exact_opaque_current_preservation(review_vault):
    from brz2obsidian.application.review_session import ReviewBudget, ReviewSession
    from brz2obsidian.contracts import OpaqueContent
    from brz2obsidian.core import save_review, select_review_effects
    from tests.application.test_onboarding import legacy_inputs
    from tests.reconciliation.test_resolution import action

    vault, scratch = review_vault
    root = scratch.parent / "descriptor-onboarding"
    root.mkdir()
    operations, legacy_vault, source, authored = legacy_inputs(root, opaque=True)
    git(legacy_vault, "init", "-q")
    git(legacy_vault, "config", "core.autocrlf", "false")
    legacy_before = {
        path.name: path.read_bytes()
        for path in legacy_vault.iterdir()
        if path.is_file()
    }
    source_before = source.read_bytes()
    legacy_refs = git(legacy_vault, "for-each-ref")
    offered = operations.prepare_onboarding(legacy_vault, source)
    assert offered.preparation is not None, offered
    prepared = offered.preparation
    report = next(
        change
        for change in prepared.review.proposal.changes
        if change.item_id == "support:MIGRATION REPORT.md"
    )
    chosen = operations.resolve_update(
        prepared,
        action(
            prepared.review,
            report,
            domain="format",
            choice="current",
            decision_id="keep-opaque-report",
        ),
    )
    assert chosen.code == "accepted", chosen
    prepared = chosen.preparation
    while prepared.review.requirements:
        requirement = prepared.review.requirements[0]
        change = next(
            change
            for change in prepared.review.proposal.changes
            if change.change_id == requirement.change_id
        )
        chosen = operations.resolve_update(
            prepared,
            action(
                prepared.review,
                change,
                domain=requirement.domain,
                choice="current",
                decision_id="keep-" + change.item_id,
            ),
        )
        assert chosen.code == "accepted", chosen
        prepared = chosen.preparation
    plan = prepared.review
    assert plan.ready, plan.blockers
    effects = select_review_effects(plan)
    assert effects.status == "selected" and effects.remove_paths == ()
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Home \u2014 Opening.md", authored),
        ("MIGRATION REPORT.md", b"\xffUnsupported authored report.\r\n"),
    ]
    approvals = tuple(
        (row.decision_id, row.domain, row.choice, row.source_accepted, row.provenance)
        for row in plan.approvals
    )
    saved = save_review(plan)
    assert saved.status == "saved"
    wire = saved.record.model_dump_json()
    before = (vault / "Assets/data.bin").read_bytes(), git(vault, "for-each-ref")
    before_scratch = tuple(scratch.iterdir())
    limits = ReviewBudget(
        metadata_limit=64 << 20,
        node_limit=1048576,
        depth_limit=256,
        decoded_limit=64 << 20,
        raw_work_limit=128 << 20,
        encoded_limit=128 << 20,
        request_limit=4096,
        step_limit=2000000,
        timeout=120,
        cancel=Event(),
    )
    # Load a historical review into the real retained reader. Its independent
    # current physical scope cannot grant this onboarding plan resume authority.
    with (
        Operations().inspect_update_inputs(vault) as observed,
        ReviewSession(observed, scratch_parent=scratch, budget=limits) as session,
    ):
        result = session.load_review(wire.encode())
        assert result.status == "loaded" and not result.ready
        loaded = result.loaded.saved.plan
        assert loaded.ready and loaded.blockers == ()
        assert result.loaded.readiness == "revalidation_required"
        assert (
            tuple(
                (
                    row.decision_id,
                    row.domain,
                    row.choice,
                    row.source_accepted,
                    row.provenance,
                )
                for row in loaded.approvals
            )
            == approvals
        )
        report_approval = next(
            row for row in loaded.approvals if row.decision_id == "keep-opaque-report"
        )
        assert type(report_approval.result) is OpaqueContent
        assert not report_approval.source_accepted
    assert tuple(scratch.iterdir()) == before_scratch
    assert (
        (vault / "Assets/data.bin").read_bytes(),
        git(vault, "for-each-ref"),
    ) == before
    assert {
        path.name: path.read_bytes()
        for path in legacy_vault.iterdir()
        if path.is_file()
    } == legacy_before
    assert git(legacy_vault, "for-each-ref") == legacy_refs
    assert source.read_bytes() == source_before
    assert saved.record.model_dump_json() == wire


def _review_preservation_state(vault):
    paths = (
        "Assets/data.bin",
        ".brz2obsidian/locator.json",
        ".git/HEAD",
        ".git/index",
        ".git/config",
    )
    return (
        tuple(
            (vault / path).read_bytes() if (vault / path).exists() else None
            for path in paths
        ),
        git(vault, "for-each-ref"),
    )


def test_raw_review_rejects_malformed_and_ambiguous_envelopes(review_vault, tmp_path):
    from brz2obsidian.application.review_session import ReviewBudget, ReviewSession

    vault, _ = review_vault
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    sentinel = scratch / "user-file"
    sentinel.write_bytes(b"retain this file")
    raw = (FIXTURES / "attachment.inline.json").read_bytes()
    assert raw.startswith(b'{"schema_id":"brz2obsidian.saved-review",')
    assert b'"data":"YWJj"' in raw
    schema = b'"brz2obsidian.saved-review"'
    assert raw.count(schema) == 1
    escaped = raw.replace(schema, b'"\\u0062rz2obsidian.saved-review"', 1)
    malformed_strings = (
        b'"\\qrz2obsidian.saved-review"',
        b'"\\u06"',
        b'"\\ud800"',
        b'"\\udc00"',
        b'"brz2obsidian\x01.saved-review"',
    )
    expected_actions = [
        ("legacy:both", "attachment", "both"),
        ("legacy:consent", "storage", "accept"),
    ]
    cases = (
        raw[:-1],  # Truncated envelope.
        raw + b" true",  # A second value after a complete envelope.
        raw.replace(
            b'{"schema_id":',
            b'{"schema_id":"brz2obsidian.saved-review","schema_id":',
            1,
        ),  # Duplicate member occurrence, even with the same value.
        b"\xff" + raw,  # Invalid UTF-8.
        raw.replace(b'"data":"YWJj"', b'"data":"YW@j"', 1),  # Invalid base64.
        raw.replace(b'"data":"YWJj"', b'"data":"Y"', 1),  # Incomplete base64.
        *(raw.replace(schema, value, 1) for value in malformed_strings),
    )
    assert escaped != raw and all(invalid != raw for invalid in cases)
    before = _review_preservation_state(vault)
    budget = ReviewBudget(
        metadata_limit=64 << 20,
        node_limit=1048576,
        depth_limit=256,
        decoded_limit=64 << 20,
        raw_work_limit=128 << 20,
        encoded_limit=128 << 20,
        request_limit=4096,
        step_limit=2000000,
        timeout=120,
        cancel=Event(),
    )
    with Operations().inspect_update_inputs(vault) as observed:
        with ReviewSession(observed, scratch_parent=scratch, budget=budget) as session:
            valid = session.load_review(raw)
            assert valid.status == "loaded" and not valid.ready
            assert valid.loaded.readiness == "revalidation_required"
            plan = valid.loaded.saved.plan
            assert plan.proposal.generation == 2
            assert [
                (action.decision_id, action.domain, action.choice)
                for action in plan.actions
            ] == expected_actions
        with ReviewSession(observed, scratch_parent=scratch, budget=budget) as session:
            equivalent = session.load_review(escaped)
            assert equivalent.status == "loaded" and not equivalent.ready
            assert equivalent.loaded.readiness == "revalidation_required"
            equivalent_plan = equivalent.loaded.saved.plan
            assert equivalent.loaded.saved.schema_id == "brz2obsidian.saved-review"
            assert equivalent_plan.proposal.generation == 2
            assert [
                (action.decision_id, action.domain, action.choice)
                for action in equivalent_plan.actions
            ] == expected_actions
        for invalid in cases:
            with ReviewSession(
                observed, scratch_parent=scratch, budget=budget
            ) as session:
                refused = session.load_review(invalid)
                assert (
                    refused.status,
                    refused.code,
                    refused.loaded,
                    refused.ready,
                ) == (
                    "refused",
                    "invalid_review",
                    None,
                    False,
                )
            assert sorted(path.name for path in scratch.iterdir()) == ["user-file"]
    assert sentinel.read_bytes() == b"retain this file"
    assert _review_preservation_state(vault) == before
    assert (FIXTURES / "attachment.inline.json").read_bytes() == raw


def test_raw_review_respects_caller_limits_and_retires_failed_loads(
    review_vault, tmp_path
):
    from brz2obsidian.application.review_session import ReviewBudget, ReviewSession

    vault, _ = review_vault
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    sentinel = scratch / "user-file"
    sentinel.write_bytes(b"retain this file")
    raw = (FIXTURES / "attachment.inline.json").read_bytes()
    before = _review_preservation_state(vault)
    budget = ReviewBudget(
        metadata_limit=64 << 20,
        node_limit=1048576,
        depth_limit=256,
        decoded_limit=64 << 20,
        raw_work_limit=128 << 20,
        encoded_limit=128 << 20,
        request_limit=4096,
        step_limit=2000000,
        timeout=120,
        cancel=Event(),
    )
    with Operations().inspect_update_inputs(vault) as observed:
        with ReviewSession(observed, scratch_parent=scratch, budget=budget) as session:
            assert session.load_review(raw).status == "loaded"
        for field in ("decoded_limit", "raw_work_limit", "encoded_limit"):
            limited = replace(budget, **{field: 0})
            with ReviewSession(
                observed, scratch_parent=scratch, budget=limited
            ) as session:
                refused = session.load_review(raw)
                assert (
                    refused.status,
                    refused.code,
                    refused.loaded,
                    refused.ready,
                ) == (
                    "refused",
                    "invalid_review",
                    None,
                    False,
                ), field
            assert sorted(path.name for path in scratch.iterdir()) == ["user-file"]
    assert sentinel.read_bytes() == b"retain this file"
    assert _review_preservation_state(vault) == before


def test_cancel_and_deadline_close_live_session_without_touching_history(
    review_vault, tmp_path, monkeypatch
):
    from brz2obsidian.application import review_session
    from brz2obsidian.application.review_session import ReviewBudget, ReviewSession

    vault, _ = review_vault
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    sentinel = scratch / "user-file"
    sentinel.write_bytes(b"retain this file")
    raw = (FIXTURES / "attachment.inline.json").read_bytes()
    before = _review_preservation_state(vault)
    real_monotonic = review_session.time.monotonic
    clock = [real_monotonic()]
    monkeypatch.setattr(
        review_session, "time", SimpleNamespace(monotonic=lambda: clock[0])
    )
    budget = ReviewBudget(
        metadata_limit=64 << 20,
        node_limit=1048576,
        depth_limit=256,
        decoded_limit=64 << 20,
        raw_work_limit=128 << 20,
        encoded_limit=128 << 20,
        request_limit=4096,
        step_limit=2000000,
        timeout=120,
        cancel=Event(),
    )
    with Operations().inspect_update_inputs(vault) as observed:
        for reason in ("cancel", "deadline"):
            clock[0] = real_monotonic()
            cancel = Event()
            with ReviewSession(
                observed, scratch_parent=scratch, budget=replace(budget, cancel=cancel)
            ) as session:
                loaded = session.load_review(raw)
                assert loaded.status == "loaded" and not loaded.ready
                if reason == "cancel":
                    cancel.set()
                else:
                    clock[0] += 121.0
                with pytest.raises(OSError, match="cancelled or time budget exhausted"):
                    session.load_review(raw)
            with pytest.raises(OSError, match="closed"):
                session.load_review(raw)
            assert sorted(path.name for path in scratch.iterdir()) == ["user-file"]
    assert sentinel.read_bytes() == b"retain this file"
    assert _review_preservation_state(vault) == before
