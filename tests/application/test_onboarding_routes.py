"""A trace record cannot silently upgrade format or manufacture source evidence."""

import json
from contextlib import nullcontext
from types import SimpleNamespace

from tests.application.test_onboarding_originals import (
    CURRENT,
    NOTE,
    controlled_history,
    legacy_brz_case,
)


def test_recorded_older_format_preserves_review_but_requires_separate_transition(
    tmp_path, monkeypatch
):
    operations, vault, archive = legacy_brz_case(tmp_path)
    path = vault / "migration-record.json"
    recorded = json.loads(path.read_bytes())
    recorded["schema_version"] = 6
    path.write_text(json.dumps(recorded))
    controlled_history(operations, vault, monkeypatch)
    offered = operations.prepare_onboarding(vault, archive)
    assert offered.preparation is not None, offered
    facts = offered.preparation.review.facts
    assert facts.baseline_identity.output_format == 6
    assert facts.incoming_identity.output_format == 8
    assert facts.format_operation.recorded_generation == "unavailable"
    assert all(s.baseline.status == "unknown" for s in facts.subjects)
    assert "review_format_transition" in offered.next_actions
    applied = operations.apply_update(offered.preparation)
    assert (
        applied.kind == "onboarding" and applied.code == "format_transition_required"
    ), applied
    assert not applied.ready and applied.publication == "not_started"
    assert (vault / NOTE).read_bytes() == CURRENT
    assert json.loads(path.read_bytes())["schema_version"] == 6


def test_record_without_source_preserves_unknown_history_and_blocks_ordinary_update(
    tmp_path, monkeypatch
):
    operations, vault, _ = legacy_brz_case(tmp_path)
    controlled_history(operations, vault, monkeypatch)
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    result = operations.prepare_onboarding(vault)
    assert result.kind == "onboarding" and result.code == "onboarding_evidence_required"
    assert result.preparation is None and not result.ready
    assert result.next_actions == ("choose_source_reference",)
    assert not result.history_retained and result.checkpoint is None
    monkeypatch.setattr(
        operations,
        "inspect_update_inputs",
        lambda path: nullcontext(
            SimpleNamespace(history=operations.inspect_history(path))
        ),
    )
    ordinary = operations.prepare_update(vault, "unopened-source.brz")
    assert ordinary.code == "onboarding_required" and not ordinary.ready
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    } == before


def test_prepared_onboarding_reference_is_not_a_completed_update_baseline(monkeypatch):
    import hashlib

    from brz2obsidian.application import SourceModuleBinding, Workflow
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.contracts import ContentVersion
    from brz2obsidian.core import (
        load_review,
        prepare_review,
        resolve_review,
        save_review,
    )
    from brz2obsidian.obsidian import (
        ObsidianRenderer,
        interpret_link_target,
        interpret_links,
    )
    from brz2obsidian.publication import FilesystemPublisher
    from tests.application.test_update_lifecycle_contracts import (
        preparation,
        recorded_history,
    )
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import action, with_review_links
    from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule

    facts = request()
    identity = facts.incoming_identity.model_copy(
        update={
            "output_format": 9,
            "module_version": "3",
            "profile_id": FOLIO_POLICY.profile_id,
            "profile_version": FOLIO_POLICY.profile_version,
            "settings_digest": hashlib.sha256(b"{}").hexdigest(),
        }
    )
    pending = facts.model_copy(
        update={
            "baseline_identity": identity,
            "incoming_identity": identity,
            "subjects": (
                facts.subjects[0].model_copy(
                    update={
                        "baseline": ContentVersion(
                            status="unknown", content=None, unavailable_digest=None
                        )
                    }
                ),
            ),
            "format_operation": facts.format_operation.model_copy(
                update={
                    "kind": "source_update",
                    "recorded_generation": "unknown",
                    "baseline_source_version": None,
                    "established_baseline": None,
                }
            ),
        }
    )
    pending = with_review_links(pending)
    context = pending.link_context
    subject = pending.subjects[0]
    current_target, incoming_target = (
        context.current_targets[0],
        context.incoming_targets[0],
    )
    current_state = interpret_link_target(
        subject.current.content,
        target_id=current_target.target_id,
        existence="present",
        memberships=(),
        source_path=subject.current.path,
        output_format=9,
    )
    incoming_state = interpret_link_target(
        subject.incoming,
        target_id=incoming_target.target_id,
        existence="present",
        memberships=(),
        source_path=subject.path,
        output_format=9,
    )
    # This controlled pure fixture represents a current-format pending review;
    # both byte-bound target interpretations and documents use that generation.
    pending = pending.model_copy(
        update={
            "link_context": context.model_copy(
                update={
                    "current_target_facts": (current_state,),
                    "incoming_target_facts": (incoming_state,),
                    "current_documents": (
                        interpret_links(
                            subject.current.content,
                            document_id=current_target.target_id,
                            source_path=subject.current.path,
                            path_mode="vault",
                            targets=context.current_targets,
                            target_facts=(current_state,),
                            inventory="complete",
                        ),
                    ),
                    "incoming_documents": (
                        interpret_links(
                            subject.incoming,
                            document_id=incoming_target.target_id,
                            source_path=subject.path,
                            path_mode="vault",
                            targets=context.incoming_targets,
                            target_facts=(incoming_state,),
                            inventory="complete",
                        ),
                    ),
                }
            )
        }
    )
    current = preparation(pending)
    history = recorded_history(identity=identity, locator=current.locator)
    pending = pending.model_copy(
        update={
            "format_operation": pending.format_operation.model_copy(
                update={"kind": "onboarding"}
            )
        }
    )
    plan = prepare_review(pending, preflight=current.review.preflight)
    kept = resolve_review(plan, action(plan, domain="format", choice="current"))
    assert kept.status == "accepted" and kept.plan.ready
    loaded = load_review(save_review(kept.plan).record)
    assert loaded.status == "loaded"
    history.checkpoint.manifest.boundary = "prepared"
    history.checkpoint.review = loaded.loaded
    operations = Operations(
        workflow=Workflow(
            SourceModuleBinding(FolioSourceModule(), FOLIO_POLICY),
            ObsidianRenderer(),
            FilesystemPublisher(),
        )
    )
    monkeypatch.setattr(
        operations,
        "inspect_update_inputs",
        lambda path: nullcontext(SimpleNamespace(history=history)),
    )
    result = operations.prepare_update("unopened-vault", "unopened-source.brz")
    assert result.code == "onboarding_review_required" and not result.ready
