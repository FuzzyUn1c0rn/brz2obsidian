"""A local Save preserves choices across separately qualified policy scopes."""

import hashlib
import json
import time
from pathlib import Path

from brz2obsidian.application.operations import Operations
from tests.application.test_attachment_cleanup_application import cleanup_asset_action
from tests.application.test_attachment_cleanup_history import (
    completed_native_ownership_case,
)
from tests.application.test_attachment_cleanup_lifecycle import user_git


def test_save_keeps_original_remove_decisions_under_verified_parent_policy_scope(
    tmp_path,
):
    started = time.monotonic()

    def phase(name, **facts):
        with (tmp_path / "save-scope-phases.jsonl").open("a", encoding="utf-8") as log:
            log.write(
                json.dumps(
                    {"phase": name, "elapsed": time.monotonic() - started, **facts}
                )
                + "\n"
            )

    manual = (
        b"Before [[Assets/remove.bin|old]] after.\r\n`[[Assets/remove.bin|code]]`\r\n"
    )
    phase("native_seed")
    vault, source, original, operations, _, before_git = (
        completed_native_ownership_case(manual=manual)
    )
    owner = json.loads((vault.parent / ".fixture-owner.json").read_text())
    assert owner["root"] == str(vault.parent.resolve()) and owner["owner"]

    def json_bytes(value):
        if isinstance(value, bytes):
            return {"hex": value.hex(), "sha256": hashlib.sha256(value).hexdigest()}
        if isinstance(value, dict):
            return {key: json_bytes(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [json_bytes(item) for item in value]
        return value

    checkout = Path(__file__).resolve().parents[2]
    evidence = {
        "completed": False,
        "owner": owner,
        "vault": str(vault),
        "source": str(source),
        "source_files": {
            path: {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            for path, raw in original.items()
        },
        "literal_manual": json_bytes(manual),
        "before_user_git": json_bytes(before_git),
        "assessed_files": {
            path: hashlib.sha256((checkout / path).read_bytes()).hexdigest()
            for path in (
                "src/brz2obsidian/application/update_lifecycle.py",
                "src/brz2obsidian/publication/vault_history.py",
                "src/brz2obsidian/publication/vault_admission.py",
                "tests/application/test_update_save_scope.py",
            )
        },
        "saves": [],
    }

    def record():
        raw = json.dumps(evidence, indent=2)
        (vault.parent / "285-save-scope-evidence.json").write_text(
            raw, encoding="utf-8"
        )
        (tmp_path / "save-scope-evidence.json").write_text(raw, encoding="utf-8")

    record()
    phase("completed_result", vault=str(vault), owner=owner["owner"])
    parent = operations.read_checkpoint(vault)
    assert parent.status == "valid" and parent.manifest.boundary == "result"
    evidence["parent"] = {
        "locator": parent.locator.model_dump(mode="json"),
        "manifest": parent.manifest.model_dump(mode="json"),
    }
    record()
    offered = operations.prepare_attachment_cleanup(vault)
    assert offered.preparation is not None, offered.code
    chosen = operations.resolve_update(
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
    assert chosen.ready, (chosen.code, chosen.preparation.review.requirements)
    original_decisions = tuple(chosen.preparation.review.approvals)
    removal = next(
        row for row in original_decisions if row.decision_id == "cleanup:remove-asset"
    )
    assert removal.attachment_selection.choice == "remove"
    assert len(removal.attachment_selection.link_choices) == 1
    assert removal.attachment_selection.link_choices[0].replacement == b""
    evidence["original_decisions"] = [
        {
            "decision_id": row.decision_id,
            "choice": row.choice,
            "attachment_selection": row.attachment_selection.model_dump(mode="json")
            if row.attachment_selection is not None
            else None,
        }
        for row in original_decisions
    ]
    record()
    phase("original_review_ready")

    prepared = chosen.preparation
    for number in (1, 2):
        saved = operations.save_update(prepared)
        evidence["saves"].append(
            {
                "number": number,
                "code": saved.code,
                "capture": saved.capture.model_dump(mode="json")
                if saved.capture is not None
                else None,
            }
        )
        record()
        phase("saved", number=number, code=saved.code)
        assert saved.code == "saved" and saved.capture.status in (
            "captured",
            "unchanged",
        ), saved.code
        retained = Operations().read_checkpoint(vault)
        assert retained.status == "valid" and retained.manifest.boundary == "local"
        assert retained.locator == saved.checkpoint
        evidence["saves"][-1]["manifest"] = retained.manifest.model_dump(mode="json")
        evidence["final_saved_locator"] = retained.locator.model_dump(mode="json")
        record()
        assert retained.manifest.source == parent.manifest.source
        assert retained.manifest.identity == parent.manifest.identity
        assert retained.manifest.recovery_gaps == parent.manifest.recovery_gaps
        assert retained.manifest.proposed == ()
        loaded = Operations().load_update(vault)
        assert loaded.code == "revalidation_required" and not loaded.ready
        resumed = Operations().resume_update(vault)
        evidence["saves"][-1].update(
            resumed_code=resumed.code,
            resumed_ready=resumed.ready,
            resumed_decision_ids=[
                row.decision_id for row in resumed.preparation.review.approvals
            ]
            if resumed.preparation is not None
            else [],
        )
        record()
        phase("resumed", number=number, code=resumed.code, ready=resumed.ready)
        assert resumed.preparation is not None and resumed.ready, resumed.code
        assert tuple(resumed.preparation.review.approvals) == original_decisions
        assert resumed.preparation.locator == saved.checkpoint
        prepared = resumed.preparation

    assert user_git(vault) == before_git
    assert (vault / "Manual.md").read_bytes() == manual
    assert all((vault / path).read_bytes() == raw for path, raw in original.items())
    assert all((source / path).read_bytes() == raw for path, raw in original.items())
    evidence["completed"] = True
    record()
    phase("complete")
