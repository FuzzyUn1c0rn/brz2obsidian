"""Default Apply publishes owned binary content and keeps unchanged repeats idle."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import brz2obsidian.application.update_lifecycle as lifecycle
import brz2obsidian.publication.vault_history as history
import brz2obsidian.publication.vault_native as native
import brz2obsidian.publication.vault_recovery as recovery
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.contracts import OutputIdentity
from brz2obsidian.publication import checkpoint_payload
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git, user_state
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    source_parts,
    write_source,
)
from tests.support.recorded_format8 import format8_workflow


def test_default_context_applies_saved_binary_and_repeats_without_checkpoint_churn(
    monkeypatch,
):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-366-apply-"))
    owner = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2]
        / "tmp/r347-owned-publication-20261110/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(
        json.dumps(owner), encoding="utf-8"
    )
    initial_directory, incoming_directory = root / "initial", root / "incoming"
    initial_directory.mkdir()
    incoming_directory.mkdir()
    item_id = "66666666-6666-4666-8666-666666666666"
    asset_path = "Attachments/22222222/large.bin"
    original = b"\xffIndependent original binary.\r\n"
    current = b"\xfeIndependent authored binary.\r\n"
    parts = source_parts(initial_directory)
    add_attachment(parts, item_id, 1, "large.bin", original)
    initial_archive = write_source(initial_directory, parts)
    workflow = format8_workflow()
    metadata = workflow.metadata_factory()
    workflow.metadata_factory = lambda: metadata
    vault = root / "vault"
    converted = workflow.convert(initial_archive, vault)
    assert converted.receipt is not None and converted.receipt.verified, (
        converted.model_dump_json()
    )
    assert (vault / asset_path).read_bytes() == original
    baseline = root / "baseline"
    shutil.copytree(vault, baseline)
    (vault / asset_path).write_bytes(current)
    size = 16 * 1024 * 1024
    raw = b"\xfdIncoming binary\x00" + b"x" * (size - 17)
    assert len(raw) == size
    incoming_digest = hashlib.sha256(raw).hexdigest()
    parts["22222222-2222-4222-8222-222222222222/large.bin"] = raw
    change_record(parts, item_id, DataLength=size)
    incoming_archive = write_source(incoming_directory, parts)
    del parts, raw
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Personal.md").write_bytes(b"Committed independent writing.\r\n")
    git(vault, "add", "Personal.md")
    git(vault, "commit", "-qm", "Independent user history")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    (vault / "Personal.md").write_bytes(b"Staged independent writing.\r\n")
    git(vault, "add", "Personal.md")
    (vault / "Personal.md").write_bytes(b"Unstaged independent writing.\r\n")
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    operations = Operations(workflow=workflow)
    seed = operations.capture_checkpoint(
        vault,
        baseline,
        vault_id="owned-publication-vault",
        import_id="owned-publication-import",
        identity=OutputIdentity(
            collection_id="11111111-1111-4111-8111-111111111111",
            module_id="thebrain-brz",
            module_version="11",
            profile_id="thebrain-format5-reviewed",
            profile_version="11",
            output_format=8,
            settings_digest=hashlib.sha256(b"{}").hexdigest(),
        ),
        admission=operations.inspect_history(vault).admission,
    )
    assert seed.status == "captured" and seed.locator.generation == 1, (
        seed.model_dump_json()
    )
    seed_manifest_raw = git(vault, "cat-file", "blob", seed.commit + ":manifest.json")
    assert json.loads(seed_manifest_raw)["review_object"] is None
    before = user_state(vault, owned_ref=seed.ref)
    baseline_before, scratch_before = _tree(baseline), _tree(scratch)
    archives_before = _digest(initial_archive), _digest(incoming_archive)
    warm = UpdateContext(operations=operations)
    opened = worker_context_call(
        warm,
        {
            "command": "prepare",
            "vault": str(vault),
            "source": str(incoming_archive),
            "selection_id": "11111111-1111-4111-8111-111111111111",
            "kind": "source_update",
        },
    )
    assert opened.status == "prepared_review" and opened.binding is not None, (
        opened.model_dump_json()
    )
    assert not opened.ready and opened.unresolved > 0
    page = worker_context_call(
        warm, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available", page.model_dump_json()
    index, row = next(
        (index, row)
        for index, row in enumerate(page.page.items)
        if row.item_id == item_id and row.facet == "asset"
    )
    offer = next(
        offer
        for offer in page.offers
        if offer.change_id == row.change_id and offer.domain == "attachment"
    )
    details = worker_context_call(
        warm,
        {
            "command": "choice_details",
            "binding": opened.binding,
            "requirement_id": offer.requirement_id,
        },
    )
    assert details.status == "available" and details.next_choice_detail_offset is None
    incoming_outputs = [
        detail for detail in details.choice_details if detail.choice == "incoming"
    ]
    assert len(incoming_outputs) == 1
    assert incoming_outputs[0].path == asset_path
    assert incoming_outputs[0].size == size
    assert incoming_outputs[0].sha256 == incoming_digest
    references = worker_context_call(
        warm,
        {
            "command": "references",
            "binding": opened.binding,
            "requirement_id": offer.requirement_id,
        },
    )
    assert references.status == "available" and references.next_reference_offset is None
    assert references.total_references == len(references.references) > 0
    reference_choices = []
    for reference in references.references:
        destinations = [
            destination
            for destination in reference.destinations
            if destination.choice == "use_incoming"
            and destination.meaning.status == "resolved"
            and destination.meaning.target_id == incoming_outputs[0].target_id
            and destination.meaning.path == asset_path
            and destination.meaning.target_version == incoming_digest
        ]
        assert len(destinations) == 1 and "use_incoming" in reference.choices
        reference_choices.append(
            {"reference_id": reference.reference_id, "choice": destinations[0].choice}
        )
    chosen = worker_context_call(
        warm,
        {
            "command": "choose",
            "binding": opened.binding,
            "requirement_id": offer.requirement_id,
            "choice": "incoming",
            "assumptions_digest": offer.assumptions_digest,
            "references": tuple(reference_choices),
        },
    )
    assert chosen.code == "accepted" and chosen.binding is not None, (
        chosen.model_dump_json()
    )
    assert not chosen.ready
    choices = worker_context_call(
        warm, {"command": "choices", "binding": chosen.binding}
    )
    assert choices.status == "available", choices.model_dump_json()
    remaining = [offer for offer in choices.offers if offer.selected is None]
    assert len(remaining) == 1
    metadata_offer = remaining[0]
    record_row = next(
        row
        for row in page.page.items
        if row.item_id == "support:migration-record.json" and row.facet == "content"
    )
    assert metadata_offer.change_id == record_row.change_id
    assert metadata_offer.domain == "text" and "incoming" in metadata_offer.choices
    assert metadata_offer.disclosure == "Current file: migration-record.json"
    chosen = worker_context_call(
        warm,
        {
            "command": "choose",
            "binding": chosen.binding,
            "requirement_id": metadata_offer.requirement_id,
            "choice": "incoming",
            "assumptions_digest": metadata_offer.assumptions_digest,
        },
    )
    assert chosen.code == "accepted" and chosen.binding is not None, (
        chosen.model_dump_json()
    )
    assert chosen.ready and chosen.unresolved == 0
    saved = worker_context_call(warm, {"command": "save", "binding": chosen.binding})
    assert saved.code == "saved" and saved.capture is not None and saved.ready, (
        saved.model_dump_json()
    )
    assert saved.capture.status == "captured" and saved.history_retained
    assert saved.binding.checkpoint_generation == 2
    assert saved.binding.checkpoint_commit == saved.capture.commit != seed.commit
    closed = worker_context_call(
        warm, {"command": "close", "binding": saved.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None, (
        closed.model_dump_json()
    )
    assert _tree(scratch) == scratch_before
    assert user_state(vault, owned_ref=seed.ref) == before
    del warm, opened, chosen, page, converted

    capacity = 96 * 1024 * 1024
    assert 9 * size + 64 * 1024 * 1024 > capacity
    capacity_observed = []

    def available_memory():
        capacity_observed.append(capacity)
        return capacity

    for module in (native, history, lifecycle, checkpoint_payload, recovery):
        monkeypatch.setattr(module, "available_memory", available_memory)
    cold = UpdateContext(operations=Operations(workflow=workflow))
    loaded = worker_context_call(
        cold,
        {
            "command": "load",
            "vault": str(vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert loaded.status == "unresolved" and loaded.code == "revalidation_required", (
        loaded.model_dump_json()
    )
    assert not loaded.ready and loaded.binding is None and loaded.unresolved == 0
    assert loaded.checkpoint_commit == saved.capture.commit and loaded.history_retained
    assert capacity_observed and _tree(scratch) == scratch_before
    resumed = worker_context_call(
        cold,
        {
            "command": "resume",
            "vault": str(vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert resumed.status == "prepared_review" and resumed.code == "unchanged", (
        resumed.model_dump_json()
    )
    assert resumed.ready and resumed.unresolved == 0 and resumed.binding is not None
    assert resumed.binding.proposal_id == saved.binding.proposal_id
    assert resumed.binding.generation == saved.binding.generation
    assert resumed.binding.checkpoint_commit == saved.capture.commit
    assert resumed.binding.context_id != saved.binding.context_id
    assert cold.apply(saved.binding).code == "context_changed"
    shown = worker_context_call(
        cold,
        {
            "command": "page",
            "binding": resumed.binding,
            "offset": index,
            "limit": 1,
            "byte_limit": 256,
        },
    )
    assert shown.status == "available", shown.model_dump_json()
    displayed = shown.page.items[0]
    assert displayed.original == original and displayed.current == current
    assert displayed.incoming == b"\xfdIncoming binary\x00" + b"x" * (
        len(displayed.incoming) - 17
    )
    assert 17 < len(displayed.incoming) <= 256 and displayed.omitted
    selected = next(offer for offer in shown.offers if offer.domain == "attachment")
    assert selected.selected == "incoming" and selected.decision_id is not None
    assert (vault / asset_path).read_bytes() == current
    marker = vault / ".git/brz2obsidian"
    actual_unlink = Path.unlink
    witnessed = []

    def fail_actual_terminal_release(path, *arguments, **options):
        if path.absolute() == (marker / "owner.json").absolute():
            # _release closes its real held handle before this first unlink.
            # Witness the actual terminal journal and exact published bytes.
            owner_raw = path.read_bytes()
            owner_record = json.loads(owner_raw)
            operation_ref = (
                seed.ref.removesuffix("/checkpoints")
                + "/operations/"
                + owner_record["operation_id"]
            )
            receipt_commit = git(vault, "rev-parse", operation_ref).decode().strip()
            retained_receipt = json.loads(
                git(vault, "cat-file", "blob", receipt_commit + ":receipt.json")
            )
            assert retained_receipt["status"] == "applied"
            assert retained_receipt["operation_id"] == owner_record["operation_id"]
            assert (
                retained_receipt["result_commit"]
                == json.loads((vault / ".brz2obsidian/locator.json").read_bytes())[
                    "commit"
                ]
            )
            assert (vault / asset_path).stat().st_size == size and _digest(
                vault / asset_path
            ) == incoming_digest
            witnessed.append(
                (owner_raw, (marker / "held").read_bytes(), receipt_commit)
            )
            raise OSError("Actual terminal owner unlink failed after receipt and bytes")
        return actual_unlink(path, *arguments, **options)

    with monkeypatch.context() as boundary:
        boundary.setattr(Path, "unlink", fail_actual_terminal_release)
        applied = worker_context_call(
            cold, {"command": "apply", "binding": resumed.binding}
        )
    assert (
        witnessed
        and applied.status == "recovery_required"
        and applied.operation is not None
    ), applied.model_dump_json()
    stopped = applied.operation
    assert stopped.recovery_required and stopped.publication == "complete"
    assert (
        stopped.receipt_commit == witnessed[-1][2] and stopped.result_commit is not None
    )
    assert applied.binding is None and not applied.ready
    assert (marker / "owner.json").read_bytes() == witnessed[-1][0]
    assert (marker / "held").read_bytes() == witnessed[-1][1]
    assert _tree(scratch) == scratch_before
    refs_before_cleanup = git(
        vault, "for-each-ref", "--format=%(refname) %(objectname)"
    )
    locator_before_cleanup = (vault / ".brz2obsidian/locator.json").read_bytes()
    authored_before_cleanup = {
        value.relative_to(vault).as_posix(): _digest(value)
        for value in vault.rglob("*")
        if value.is_file()
        and value.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    }
    detail_intent = json.loads(
        git(vault, "cat-file", "blob", stopped.intent_commit + ":intent.json")
    )
    detail_paths = sorted(
        {row["path"] for row in detail_intent["before"] + detail_intent["proposed"]}
    )
    offset = detail_paths.index(asset_path)
    observed_terminal = Operations().inspect_update_status(vault)
    assert (
        observed_terminal.code == "terminal_cleanup_required"
        and observed_terminal.recovery_required
    )
    assert (
        observed_terminal.operation_id,
        observed_terminal.generation,
        observed_terminal.checkpoint_commit,
        observed_terminal.intent_commit,
        observed_terminal.result_commit,
        observed_terminal.receipt_commit,
    ) == (
        stopped.operation_id,
        stopped.generation,
        stopped.checkpoint_commit,
        stopped.intent_commit,
        stopped.result_commit,
        witnessed[-1][2],
    )
    assert observed_terminal.kind == "apply" and observed_terminal.direction == "finish"
    details = Operations().read_history_details(
        vault, expected=observed_terminal, offset=offset, limit=1
    )
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
        == refs_before_cleanup
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_before_cleanup
    assert (marker / "owner.json").read_bytes() == witnessed[-1][0]
    assert (marker / "held").read_bytes() == witnessed[-1][1]
    cleanup = UpdateContext(operations=Operations(workflow=workflow))
    inspected = worker_context_call(
        cleanup,
        {
            "command": "history",
            "vault": str(vault),
            "selection_id": "44444444-4444-4444-8444-444444444444",
        },
    )
    assert inspected.status == "recovery_required" and inspected.binding is not None, (
        inspected.model_dump_json()
    )
    assert inspected.history.operation.code == "terminal_cleanup_required"
    assert "review_recovery" in inspected.next_actions
    prepared_cleanup = worker_context_call(
        cleanup,
        {
            "command": "prepare_history",
            "binding": inspected.binding,
            "kind": "recovery",
        },
    )
    assert prepared_cleanup.status == "prepared_review" and prepared_cleanup.ready, (
        prepared_cleanup.model_dump_json()
    )
    assert (
        prepared_cleanup.binding is not None
        and prepared_cleanup.binding.direction is None
    )
    assert (
        prepared_cleanup.history_action.available_directions == ()
        and prepared_cleanup.unresolved == 0
    )
    cleaned = worker_context_call(
        cleanup, {"command": "execute_history", "binding": prepared_cleanup.binding}
    )
    assert (
        details.status == "available"
        and details.code == "validated"
        and cleaned.status == "applied"
        and cleaned.history_action.operation is not None
    ), json.dumps(
        {
            "details": details.model_dump(mode="json"),
            "cleanup": cleaned.model_dump(mode="json"),
        }
    )
    assert details.status == "available" and details.code == "validated", (
        details.model_dump_json()
    )
    assert (
        details.total == len(detail_paths)
        and details.offset == offset
        and details.limit == 1
    )
    (detail,) = details.items
    assert detail.path == asset_path
    assert (
        detail.before_size == len(current)
        and detail.before_sha256 == hashlib.sha256(current).hexdigest()
    )
    assert detail.after_size == size and detail.after_sha256 == incoming_digest
    assert len(details.model_dump_json()) < 8192
    assert (
        details.operation_id,
        details.intent_commit,
        details.generation,
        details.kind,
        details.direction,
    ) == (
        observed_terminal.operation_id,
        observed_terminal.intent_commit,
        observed_terminal.generation,
        observed_terminal.kind,
        observed_terminal.direction,
    )
    operation = cleaned.history_action.operation
    assert (
        operation.operation_id,
        operation.generation,
        operation.checkpoint_commit,
        operation.intent_commit,
        operation.result_commit,
        operation.receipt_commit,
    ) == (
        stopped.operation_id,
        stopped.generation,
        stopped.checkpoint_commit,
        stopped.intent_commit,
        stopped.result_commit,
        stopped.receipt_commit,
    )
    assert cleaned.publication == "complete" and operation.history == "terminal"
    assert cleaned.binding is None and not cleaned.ready and not marker.exists()
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
        == refs_before_cleanup
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_before_cleanup
    assert {
        value.relative_to(vault).as_posix(): _digest(value)
        for value in vault.rglob("*")
        if value.is_file()
        and value.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    } == authored_before_cleanup
    assert operation.phase == "terminal" and not operation.recovery_required
    assert operation.published_files == operation.planned_files > 0
    assert operation.checkpoint_commit != saved.capture.commit
    assert applied.checkpoint_commit == operation.result_commit
    assert (vault / asset_path).stat().st_size == size
    assert _digest(vault / asset_path) == incoming_digest
    with (vault / asset_path).open("rb") as stream:
        assert stream.read(32) == b"\xfdIncoming binary\x00" + b"x" * 15
    assert cold.page(resumed.binding).code == "context_changed"
    assert _tree(scratch) == scratch_before
    prepared = json.loads(
        git(vault, "cat-file", "blob", operation.checkpoint_commit + ":manifest.json")
    )
    intent = json.loads(
        git(vault, "cat-file", "blob", operation.intent_commit + ":intent.json")
    )
    result = json.loads(
        git(vault, "cat-file", "blob", operation.result_commit + ":manifest.json")
    )
    receipt = json.loads(
        git(vault, "cat-file", "blob", operation.receipt_commit + ":receipt.json")
    )
    assert prepared["boundary"] == "prepared"
    assert prepared["previous"] == saved.capture.commit
    assert intent["prepared_commit"] == operation.checkpoint_commit
    assert intent["operation_id"] == operation.operation_id
    assert intent["kind"] == "apply" and intent["direction"] == "finish"
    assert intent["generation"] == prepared["generation"] == operation.generation
    assert result["boundary"] == "result"
    assert result["previous"] == operation.checkpoint_commit
    assert result["operation_intent_commit"] == operation.intent_commit
    assert receipt["prepared_commit"] == operation.checkpoint_commit
    assert receipt["intent_commit"] == operation.intent_commit
    assert receipt["result_commit"] == operation.result_commit
    assert receipt["status"] == "applied" and asset_path in receipt["published_paths"]
    assert set(receipt["published_paths"]) == set(intent["affected_paths"])
    for role in ("source", "proposed"):
        row = next(row for row in prepared[role] if row["path"] == asset_path)
        assert row["size"] == size and row["sha256"] == incoming_digest
        retained = git(
            vault,
            "cat-file",
            "blob",
            operation.checkpoint_commit + ":" + role + "/" + asset_path,
        )
        assert len(retained) == size
        assert hashlib.sha256(retained).hexdigest() == incoming_digest
        del retained
    assert (
        git(
            vault,
            "cat-file",
            "blob",
            operation.checkpoint_commit + ":preimage/" + asset_path,
        )
        == current
    )
    result_asset = next(row for row in result["vault"] if row["path"] == asset_path)
    assert result_asset["size"] == size and result_asset["sha256"] == incoming_digest
    operation_ref = (
        seed.ref.removesuffix("/checkpoints") + "/operations/" + operation.operation_id
    )
    assert (
        git(vault, "rev-parse", operation_ref).decode().strip()
        == operation.receipt_commit
    )
    after = user_state(vault, owned_ref=seed.ref)
    for key in ("head", "index", "config", "stages"):
        assert after[key] == before[key]
    assert set(after["refs"]) == set(before["refs"]) | {
        (operation_ref + " " + operation.receipt_commit).encode()
    }
    assert after["authored"].keys() == before["authored"].keys()
    for path, raw in before["authored"].items():
        if path not in (asset_path, "migration-record.json", "MIGRATION REPORT.md"):
            assert after["authored"][path] == raw
    after_apply = after

    refs_before_repeat = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator_before_repeat = (vault / ".brz2obsidian/locator.json").read_bytes()
    repeated = UpdateContext(operations=Operations(workflow=workflow))
    opened_again = worker_context_call(
        repeated,
        {
            "command": "prepare",
            "vault": str(vault),
            "source": str(incoming_archive),
            "selection_id": "33333333-3333-4333-8333-333333333333",
            "kind": "source_update",
        },
    )
    assert opened_again.status == "prepared_review" and opened_again.ready, (
        opened_again.model_dump_json()
    )
    assert opened_again.unresolved == 0 and opened_again.binding is not None
    duplicate = worker_context_call(
        repeated, {"command": "apply", "binding": opened_again.binding}
    )
    assert (
        duplicate.status == "no_content_change" and duplicate.code == "already_current"
    ), duplicate.model_dump_json()
    assert duplicate.operation is None and duplicate.publication == "not_published"
    assert duplicate.checkpoint_commit == operation.result_commit
    assert _tree(scratch) == scratch_before
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
        == refs_before_repeat
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_before_repeat
    assert user_state(vault, owned_ref=seed.ref) == after_apply
    assert _digest(vault / asset_path) == incoming_digest
    assert (vault / "Personal.md").read_bytes() == b"Unstaged independent writing.\r\n"
    assert _tree(baseline) == baseline_before
    assert (_digest(initial_archive), _digest(incoming_archive)) == archives_before
    assert (
        git(vault, "cat-file", "blob", seed.commit + ":manifest.json")
        == seed_manifest_raw
    )
