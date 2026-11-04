"""A proved first local memo keeps its actual parent's review authority."""

import hashlib
import json
import tempfile
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from brz2obsidian.application.operations import Operations
from brz2obsidian.core import load_review, resume_review, save_review
from brz2obsidian.publication import vault_history
from brz2obsidian.publication.vault_native import verify_directory
from tests.application.test_attachment_cleanup_application import (
    cleanup_asset_action,
    literal_cleanup_case,
)
from tests.application.test_update_lifecycle_admission import NOTE, note
from tests.application.test_vault_admission import git


def test_first_local_memo_keeps_proved_result_parent_and_original_remove_decision(
    monkeypatch,
):
    # The native reader owns complete graph validation. This controlled return
    # supplies its validated scalar role chain at the real public admission port.
    owned = Path(tempfile.mkdtemp(prefix="brz2obsidian-285-memo-"))
    marker = {"owner": uuid4().hex, "root": str(owned.resolve())}
    (owned / ".fixture-owner.json").write_text(json.dumps(marker))
    case = literal_cleanup_case(owned, independent_keep=True)
    vault = case.vault
    git(vault, "init", "-q")
    git(vault, "add", "--all")
    git(vault, "commit", "-qm", "Independent authored fixture")
    association = case.history.checkpoint.locator.association.model_copy(
        update={
            "vault_anchor": verify_directory(vault),
            "git_anchor": verify_directory(vault / ".git"),
        }
    )
    parent = case.history.checkpoint.locator.model_copy(
        update={
            "association": association,
            "generation": 3,
            "commit": "b" * 40,
        }
    )
    # With a LOCAL review tip the validated reader computes memo fingerprints
    # for all ancestors, including this RESULT; None is not its actual shape.
    # The controlled native reader declares a common context over already
    # validated metadata. Runtime graph/manifest validation remains native-owned.
    fields = tuple(
        dict.fromkeys(
            vault_history._CheckpointRole._fields + ("review_context_fingerprint",)
        )
    )
    ContextRole = namedtuple("ContextRole", fields)
    source_inventory = tuple(
        {
            "path": path,
            "mode": "100644",
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "object_id": hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\x00" + raw
            ).hexdigest(),
        }
        for path, raw in sorted(case.retained.items())
    )
    context = {
        "association": association.model_dump(mode="json"),
        "identity": case.history.checkpoint.manifest.identity.model_dump(mode="json"),
        "source": source_inventory,
        "recovery_gaps": (),
        "policy_fingerprint": "1" * 64,
        "policy_continuity_fingerprint": "2" * 64,
    }

    def projected(role, *, proposed=(), **changes):
        declared = context | changes
        proof = hashlib.sha256(
            json.dumps(declared, sort_keys=True).encode()
        ).hexdigest()
        if (
            role.boundary not in ("result", "local")
            or role.boundary == "local"
            and proposed
        ):
            proof = None
        return ContextRole(**(role._asdict() | {"review_context_fingerprint": proof}))

    role = vault_history._CheckpointRole(
        parent.commit,
        None,
        parent.generation,
        "result",
        None,
        None,
        None,
        None,
        None,
        "e" * 64,
    )
    role = projected(role)
    active = {"locator": parent, "roles": (role,)}
    metadata = vault / ".brz2obsidian"
    metadata.mkdir()
    locator_file = metadata / "locator.json"
    locator_file.write_text(parent.model_dump_json())

    def read_validated(root, git_reader, **kwargs):
        assert Path(root) == vault
        kwargs["checkpoint_roles"].extend(active["roles"])
        return SimpleNamespace(status="valid", locator=active["locator"])

    monkeypatch.setattr(vault_history, "_read", read_validated)
    before = Operations().inspect_vault(vault)
    assert before.status == "supported" and before.preflight.operation_status == "idle"
    case.history.admission.preflight = before.preflight
    case.history.checkpoint.locator = parent
    prepared = case.operations.prepare_attachment_cleanup(vault).preparation
    for item, choice in (("keep-asset", "current"), ("remove-asset", "remove")):
        selected = case.operations.resolve_update(
            prepared,
            cleanup_asset_action(
                prepared.review,
                item,
                choice,
                document_edits={
                    NOTE: note("Authored ."),
                    "Manual.md": b"Manual . `[[Assets/remove.bin]]`\r\n",
                }
                if choice == "remove"
                else None,
            ),
        )
        assert selected.code == "accepted"
        prepared = selected.preparation
    assert selected.ready
    original_ids = tuple(row.decision_id for row in prepared.review.approvals)
    assert "cleanup:remove-asset" in original_ids
    saved = save_review(prepared.review)
    loaded = load_review(saved.record.model_dump_json())
    assert loaded.status == "loaded" and not loaded.loaded.ready
    local = parent.model_copy(update={"commit": "c" * 40, "generation": 4})
    memo = vault_history._CheckpointRole(
        local.commit,
        parent.commit,
        local.generation,
        "local",
        None,
        None,
        None,
        None,
        None,
        "f" * 64,
        before.preflight.state_fingerprint,
    )
    memo = projected(memo)
    active.update(locator=local, roles=(memo, role))
    locator_file.write_text(local.model_dump_json())
    after = Operations().inspect_vault(vault)
    assert after.status == "supported"
    assert after.preflight == before.preflight
    resumed = resume_review(
        loaded.loaded, prepared.review.facts, preflight=after.preflight
    )
    assert resumed.status == "resumed" and resumed.ready
    assert tuple(row.decision_id for row in resumed.plan.approvals) == original_ids
    removed = next(
        row
        for row in resumed.plan.approvals
        if row.decision_id == "cleanup:remove-asset"
    )
    assert removed.attachment_selection.choice == "remove"
    assert all(
        row.replacement == b"" for row in removed.attachment_selection.link_choices
    )

    # A local memo cannot alias an unproved parent or an operation boundary.
    for invalid in (
        memo._replace(previous="d" * 40),
        memo._replace(review_parent_fingerprint="foreign-history"),
        memo._replace(operation_intent_commit="d" * 40),
        memo._replace(generation=5),
        projected(memo, policy_fingerprint="3" * 64),
        projected(memo, policy_continuity_fingerprint="4" * 64),
        projected(memo, source=()),
        projected(memo, proposed=("new-output",)),
        memo._replace(review_context_fingerprint="invalid"),
    ):
        active["roles"] = (invalid, role)
        refused = Operations().inspect_vault(vault)
        assert refused.preflight.state_fingerprint != before.preflight.state_fingerprint
    active["roles"] = (memo, role)
    # Physical current/link changes still retire the relevant original decision.
    case.history.checkpoint.locator = local
    case.history.admission.preflight = after.preflight
    (vault / "Manual.md").write_bytes(
        b"New authored reference [[Assets/remove.bin]].\r\n"
    )
    changed = case.operations.refresh_update(
        prepared.model_copy(update={"locator": local})
    )
    assert not changed.ready
    assert "cleanup:remove-asset" not in {
        row.decision_id for row in changed.preparation.review.approvals
    }
