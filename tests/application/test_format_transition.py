"""Separate format and configuration maintenance at the public Operations seam."""

from types import SimpleNamespace

import pytest

from brz2obsidian.application.operations import Operations


def test_interrupted_history_blocks_format_transition_before_source_access(monkeypatch):
    def unopened(*args, **kwargs):
        raise AssertionError(
            "Interrupted history must be reported before opening a reference"
        )

    operations = Operations(workflow=SimpleNamespace(convert=unopened))
    history = SimpleNamespace(
        status="incomplete",
        checkpoint=None,
        admission=SimpleNamespace(
            status="recovery_first",
            vault="unopened-vault",
            recovery_gaps=("preimage_unavailable",),
        ),
    )
    monkeypatch.setattr(operations, "inspect_history", lambda vault: history)
    result = operations.prepare_format_transition(
        "unopened-vault", "unopened-reference.brz"
    )
    assert result.kind == "format_transition" and result.status == "recovery_required"
    assert result.code == "recovery_first" and not result.ready
    assert result.preparation is None and result.publication == "not_started"
    assert result.history_retained and result.recovery_gaps == ("preimage_unavailable",)
    assert result.vault == "unopened-vault" and result.next_actions == (
        "review_recovery",
    )


def transition_case(tmp_path, monkeypatch, known_original=True):
    import hashlib
    from pathlib import Path

    from brz2obsidian.application.checkpoint_contracts import (
        CheckpointLocator,
        VaultAssociation,
    )
    from brz2obsidian.application.source_payload_contracts import SourcePayloadFile
    from brz2obsidian.application.vault_contracts import VaultFile
    from brz2obsidian.application.wiring import default_workflow
    from brz2obsidian.contracts import OutputIdentity
    from brz2obsidian.publication.vault_native import observe_file
    from tests.application.test_module_seams import METADATA
    from tests.reconciliation.test_resolution import preflight
    from tests.support.recorded_format6 import (
        CURRENT,
        FIXTURE,
        NOTE,
        historical_payload,
    )

    payload, _proof = historical_payload()
    vault = tmp_path / "vault"
    for name, raw in payload.items():
        path = vault / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (vault / NOTE).write_bytes(CURRENT)
    identity = OutputIdentity(
        collection_id="7b170eec-a7e4-49f6-a0b4-bd553528a201",
        module_id="thebrain-brz",
        module_version="9",
        profile_id="thebrain-format5-reviewed",
        profile_version="9",
        output_format=6,
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    association = VaultAssociation(
        schema_id="brz2obsidian.vault-association",
        schema_version=1,
        association_id="a" * 64,
        vault_id="legacy-vault",
        import_id="legacy-import",
        collection_id=identity.collection_id,
        module_id=identity.module_id,
        vault_anchor="observed-vault",
        git_anchor="observed-git",
        ref="refs/brz2obsidian/imports/" + "a" * 64 + "/checkpoints",
    )
    locator = CheckpointLocator(
        schema_id="brz2obsidian.checkpoint-locator",
        schema_version=1,
        association=association,
        generation=1,
        commit="b" * 40,
    )
    rows = tuple(
        SourcePayloadFile(
            path=name,
            mode="100644",
            size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
        for name, raw in sorted(payload.items())
    )
    inventory = []
    for path in sorted(p for p in vault.rglob("*") if p.is_file()):
        info, sha, _, physical = observe_file(vault, path, prefix_limit=0)
        inventory.append(
            VaultFile(
                path=path.relative_to(vault).as_posix(),
                mode="100644",
                size=info.st_size,
                sha256=sha,
                identity=physical,
                tracked=True,
                excluded=False,
                exclusion=None,
            )
        )
    history = SimpleNamespace(
        status="intact",
        checkpoint=SimpleNamespace(
            status="valid",
            locator=locator,
            manifest=SimpleNamespace(
                identity=identity, source=rows, boundary="local", reviewed_source=None
            ),
            review=None,
        ),
        admission=SimpleNamespace(
            vault=str(vault),
            status="supported",
            inventory=tuple(inventory),
            inventory_complete=True,
            preflight=preflight(),
            repository=SimpleNamespace(kind="root"),
            findings=(),
            recovery_gaps=(),
        ),
    )
    workflow = default_workflow()
    workflow.metadata_factory = lambda: METADATA
    operations = Operations(workflow=workflow)
    monkeypatch.setattr(operations, "inspect_history", lambda *args, **kwargs: history)
    monkeypatch.setattr(
        operations,
        "read_checkpoint_payload",
        lambda *args, **kwargs: SimpleNamespace(
            status="available",
            chunks=tuple(
                SimpleNamespace(path=name, data=raw) for name, raw in payload.items()
            ),
        ),
    )
    if not known_original:
        from brz2obsidian.core import load_review, save_review

        history.status, history.checkpoint = "absent", None
        enrolled = operations.prepare_onboarding(vault, FIXTURE / "source.brz")
        assert enrolled.preparation is not None, enrolled
        assert enrolled.preparation.review.facts.baseline_identity.output_format == 6
        assert all(
            s.baseline.status == "unknown"
            for s in enrolled.preparation.review.facts.subjects
        )
        loaded = load_review(save_review(enrolled.preparation.review).record)
        assert loaded.status == "loaded" and not loaded.loaded.ready
        binding = enrolled.preparation.source_binding
        payload = {
            row.path: (
                Path(enrolled.preparation.payload_directory) / row.path
            ).read_bytes()
            for row in binding.files
        }
        history.status = "intact"
        history.checkpoint = SimpleNamespace(
            status="valid",
            locator=locator,
            manifest=SimpleNamespace(
                identity=identity,
                source=binding.files,
                boundary="local",
                reviewed_source=binding,
                observed_source=enrolled.preparation.observed_source,
            ),
            review=loaded.loaded,
        )
    return operations, vault, history


@pytest.mark.parametrize("known_original", (True, False))
def test_transition_compares_actual_stored_format6_original_current_and_format7_target(
    tmp_path, monkeypatch, known_original
):
    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_update_context import worker_context_call
    from tests.support.recorded_format6 import CURRENT, FIXTURE, NOTE, ORIGINAL

    operations, vault, _history = transition_case(tmp_path, monkeypatch, known_original)
    offered = operations.prepare_format_transition(vault, FIXTURE / "source.brz")
    assert offered.preparation is not None, offered
    facts = offered.preparation.review.facts
    assert offered.kind == facts.format_operation.kind == "format_transition"
    assert (
        facts.baseline_identity.output_format == 6
        and facts.baseline_identity.profile_version == "9"
    )
    assert (
        facts.incoming_identity.output_format == 7
        and facts.incoming_identity.profile_version == "10"
    )
    assert facts.format_operation.recorded_generation == "unavailable"
    assert (
        facts.format_operation.baseline_source_version
        == facts.format_operation.target_source_version
    )
    note = next(
        s for s in facts.subjects if s.item_id == "5f71e626-527e-47b4-abaa-e53d124619f8"
    )
    if known_original:
        assert (
            note.baseline.status == "known" and note.baseline.content.data == ORIGINAL
        )
    else:
        assert note.baseline.status == "unknown" and note.baseline.content is None
    assert note.current.content.data == CURRENT
    assert b"Independent legacy source body." in note.incoming.data
    assert not offered.ready and (vault / NOTE).read_bytes() == CURRENT
    roles = {s.output_role for s in facts.subjects}
    assert {"configuration", "guide", "note", "dashboard", "template"} <= roles

    class PreparedSourcePort(Operations):
        # Reuse the exact real preparation above, without rendering it twice.
        # Offer production and worker framing remain real.
        def prepare_format_transition(self, path, source):
            assert str(path) == str(vault) and str(source) == str(
                FIXTURE / "source.brz"
            )
            return offered

    context = UpdateContext(operations=PreparedSourcePort())
    prepared = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "format_transition",
            "vault": str(vault),
            "source": str(FIXTURE / "source.brz"),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert prepared.binding is not None and not prepared.ready
    choices = worker_context_call(
        context, {"command": "choices", "binding": prepared.binding}
    )
    note = next(
        offer
        for offer in choices.offers
        if offer.domain == "format" and "Home — Format six seed.md" in offer.disclosure
    )
    assert "Recorded output format: 6" in note.disclosure
    assert "Incoming output format: 7" in note.disclosure
    assert "Keep vault version preserves the current vault content" in note.disclosure
    assert (
        "Use incoming version replaces it with the reviewed generated content"
        in note.disclosure
    )
    if known_original:
        assert (
            "Original generated content is available for comparison" in note.disclosure
        )
    else:
        assert "Original generated content is unknown" in note.disclosure
        assert "current vault content is not assumed unchanged" in note.disclosure
    assert not note.detail_omitted and (vault / NOTE).read_bytes() == CURRENT


def test_format_transition_refuses_a_distinct_source_before_review(
    tmp_path, monkeypatch
):
    from tests.support.recorded_format6 import CURRENT, NOTE, changed_source

    operations, vault, _history = transition_case(tmp_path, monkeypatch)
    changed = changed_source(tmp_path / "source-b.brz")
    result = operations.prepare_format_transition(vault, changed)
    assert result.kind == "format_transition" and result.status == "refused", result
    assert result.code == "format_source_changed" and not result.ready
    assert result.preparation is None and result.next_actions == (
        "choose_source_reference",
    )
    assert (
        result.publication == "not_started" and (vault / NOTE).read_bytes() == CURRENT
    )
