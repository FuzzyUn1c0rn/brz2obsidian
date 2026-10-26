"""Real consent-bearing Save and later user choices retain their exact authority."""

import hashlib
import json
import time

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_facts import assemble_facts, output_identity
from brz2obsidian.application.vault_contracts import VaultSubject
from brz2obsidian.contracts import SourceIdentity, reconciliation_subject_id
from brz2obsidian.core import prepare_review, resolve_review
from tests.application.test_attachment_cleanup_application import cleanup_asset_action
from tests.application.test_attachment_cleanup_history import owned_history_case
from tests.application.test_attachment_cleanup_lifecycle import user_git
from tests.application.test_vault_checkpoints import git
from tests.reconciliation.test_resolution import action


def _accept_storage(plan, decision_id):
    requirement = next(row for row in plan.requirements if row.domain == "storage")
    return action(
        plan,
        domain="storage",
        choice="accept",
        decision_id=decision_id,
        change_id=requirement.change_id,
        reviewed_assumptions=requirement.assumptions,
    )


def test_scoped_storage_save_retains_remove_then_a_new_current_choice(tmp_path):
    started = time.monotonic()
    vault, source, original = owned_history_case()
    owner = json.loads((vault.parent / ".fixture-owner.json").read_text())
    operations = Operations()
    identity = output_identity(json.loads(original["migration-record.json"]))
    first = operations.capture_checkpoint(
        vault,
        source,
        vault_id="consent-save-vault",
        import_id="consent-save-import",
        identity=identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert first.status == "captured", first.code
    manual = (
        b"Before [[Assets/remove.bin|old]] after.\r\n`[[Assets/remove.bin|code]]`\r\n"
    )
    attributes = b"Manual.md text\n"
    current = original | {"Manual.md": manual, ".gitattributes": attributes}
    (vault / "Manual.md").write_bytes(manual)
    (vault / ".gitattributes").write_bytes(attributes)
    git(vault, "add", "Manual.md", ".gitattributes")
    before_git = user_git(vault)
    evidence = {
        "completed": False,
        "owner": owner,
        "vault": str(vault),
        "source": str(source),
        "before_user_git": before_git,
        "current_literals": current,
        "source_sha256": {
            path: hashlib.sha256(raw).hexdigest() for path, raw in original.items()
        },
        "phases": [],
    }

    def record(phase, **facts):
        evidence["phases"].append(
            {"phase": phase, "elapsed": time.monotonic() - started, **facts}
        )
        raw = json.dumps(evidence, indent=2, default=lambda value: {"hex": value.hex()})
        (tmp_path / "consent-save-evidence.json").write_text(raw, encoding="utf-8")
        (vault.parent / "285-consent-save-evidence.json").write_text(
            raw, encoding="utf-8"
        )

    record("initial_checkpoint", result=first.model_dump(mode="json"))
    facts = assemble_facts(
        original, original, current, proposal_id="consented-native-seed", generation=1
    )
    subjects = tuple(
        VaultSubject(
            path=row.path,
            subject_id=reconciliation_subject_id(
                identity.module_id, identity.collection_id, row.item_id, row.facet
            ),
        )
        for row in sorted(facts.subjects, key=lambda row: row.path)
    )
    assert {row.path for row in subjects} == set(original)
    # Builtin storage applies to the whole current inventory. The ordinary
    # baseline already exists; accept this real policy before the terminal
    # operation whose unchanged policy domains the later Saves must prove.
    admission = operations.inspect_history(vault, subjects=subjects).admission
    assert [row.kind for row in admission.preflight.consents] == ["storage"]
    plan = prepare_review(facts, preflight=admission.preflight)
    accepted = resolve_review(plan, _accept_storage(plan, "apply:storage"))
    assert accepted.status == "accepted" and accepted.plan.ready, accepted.code
    terminal = operations.apply_reviewed_update(
        vault,
        source,
        review=accepted.plan,
        vault_id="consent-save-vault",
        import_id="consent-save-import",
        source_binding=operations.observe_reviewed_source(source, accepted.plan),
        observed_source=SourceIdentity.model_validate(
            json.loads(original["migration-record.json"])["source_identity"]
        ),
    )
    record("completed_result", result=terminal.model_dump(mode="json"))
    assert terminal.status == "no_content_change" and terminal.phase == "terminal", (
        terminal.code
    )
    parent = operations.read_checkpoint(vault)
    assert parent.status == "valid" and parent.manifest.boundary == "result"
    evidence["parent"] = {
        "locator": parent.locator.model_dump(mode="json"),
        "manifest": parent.manifest.model_dump(mode="json"),
    }

    offered = operations.prepare_attachment_cleanup(vault)
    assert offered.preparation is not None, offered.code
    selected = operations.resolve_update(
        offered.preparation,
        cleanup_asset_action(
            offered.preparation.review,
            "remove-asset",
            "remove",
            document_edits={
                "Manual.md": b"Before  after.\r\n`[[Assets/remove.bin|code]]`\r\n"
            },
        ),
    )
    assert selected.code == "accepted", selected.code
    prepared = selected.preparation

    for choice in ("remove", "current"):
        if choice == "current":
            selected = operations.resolve_update(
                prepared,
                cleanup_asset_action(
                    prepared.review, "remove-asset", "current"
                ).model_copy(update={"decision_id": "cleanup:keep-current"}),
            )
            assert selected.code == "accepted", selected.code
            prepared = selected.preparation
        refreshed = operations.refresh_update(prepared)
        record("current_scope", choice=choice, code=refreshed.code)
        assert refreshed.preparation is not None, refreshed.code
        prepared = refreshed.preparation
        selected_decision = next(
            row
            for row in prepared.review.approvals
            if row.attachment_selection is not None
            and row.attachment_selection.choice == choice
        )
        assert selected_decision.decision_id == (
            "cleanup:remove-asset" if choice == "remove" else "cleanup:keep-current"
        )
        if choice == "remove":
            assert len(selected_decision.attachment_selection.link_choices) == 1
            assert (
                selected_decision.attachment_selection.link_choices[0].replacement
                == b""
            )
        requirement = next(
            row for row in prepared.review.preflight.consents if row.kind == "storage"
        )
        if any(row.domain == "storage" for row in prepared.review.requirements):
            accepted = operations.resolve_update(
                prepared, _accept_storage(prepared.review, choice + ":storage")
            )
            assert accepted.code == "accepted", accepted.code
            prepared = accepted.preparation
        assert prepared.review.ready
        expected_decisions = tuple(prepared.review.approvals)
        expected_consents = tuple(prepared.review.consents)
        assert expected_consents and all(
            row.choice == "accept" for row in expected_consents
        )
        saved = operations.save_update(prepared)
        record(
            "saved",
            choice=choice,
            code=saved.code,
            original_decisions=[row.decision_id for row in expected_decisions],
            required_storage=requirement.model_dump(mode="json"),
            accepted_consents=[
                row.model_dump(mode="json") for row in expected_consents
            ],
            capture=saved.capture.model_dump(mode="json")
            if saved.capture is not None
            else None,
        )
        assert saved.code == "saved", saved.code
        retained = Operations().read_checkpoint(vault)
        assert retained.status == "valid" and retained.manifest.boundary == "local"
        assert retained.locator == saved.checkpoint
        evidence["final_saved_locator"] = retained.locator.model_dump(mode="json")
        record(
            "retained",
            choice=choice,
            manifest=retained.manifest.model_dump(mode="json"),
        )
        loaded = Operations().load_update(vault)
        assert loaded.code == "revalidation_required" and not loaded.ready
        resumed = Operations().resume_update(vault)
        record("resumed", choice=choice, code=resumed.code, ready=resumed.ready)
        assert resumed.preparation is not None and resumed.ready, resumed.code
        assert tuple(resumed.preparation.review.approvals) == expected_decisions
        assert tuple(resumed.preparation.review.consents) == expected_consents
        assert (
            resumed.preparation.review.preflight.consents
            == prepared.review.preflight.consents
        )
        prepared = resumed.preparation

    assert user_git(vault) == before_git
    assert all((vault / path).read_bytes() == raw for path, raw in current.items())
    assert all((source / path).read_bytes() == raw for path, raw in original.items())
    evidence["completed"] = True
    record("complete")
