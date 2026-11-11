"""An actual recorded format7 review retains a large authored attachment."""

import hashlib
import json
import tempfile
from pathlib import Path
from uuid import uuid4

import brz2obsidian.application.update_lifecycle as lifecycle
import brz2obsidian.publication.vault_history as history
import brz2obsidian.publication.vault_native as native
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.publication import checkpoint_payload
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_type_tag_compatibility import seed_format7
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git, user_state
from tests.support.recorded_format7 import FIXTURE, historical_payload


def test_default_context_saves_and_cold_resumes_source_stable_format7(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-366-format-"))
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
    # This checks every actual producer file against immutable provenance;
    # no historical renderer or rewritten migration record creates the seed.
    payload, proof = historical_payload()
    operations, vault, source, _ = seed_format7(root)
    asset_path = "Attachments/5f71e626/Notes.md.original"
    item_id = "5ba9bf70-39d1-4bf1-a125-ad64541a491a"
    original = b"Independent legacy source body.\r\n"
    assert payload[asset_path] == original and len(original) == 33
    assert proof["files"][asset_path]["sha256"] == hashlib.sha256(original).hexdigest()
    recorded = json.loads(payload["migration-record.json"])
    (asset,) = [row for row in recorded["asset_targets"] if row["asset_id"] == item_id]
    assert asset["relative_path"] == asset_path and asset["actual_length"] == 33
    source_version = "180a0b1e3d04d39a3cd324987b7043a33db240c37546feff5961ba4d3ff083ea"
    assert recorded["source_identity"]["snapshot_digest"] == source_version
    seed_locator = json.loads((vault / ".brz2obsidian/locator.json").read_bytes())
    seed_commit = seed_locator["commit"]
    seed_manifest = json.loads(
        git(vault, "cat-file", "blob", seed_commit + ":manifest.json")
    )
    assert seed_manifest["identity"]["output_format"] == 7
    assert seed_manifest["generation"] == 1
    seed_bytes = git(vault, "cat-file", "blob", seed_commit + ":manifest.json")
    size = 16 * 1024 * 1024
    prefix = b"\xffIndependent authored format attachment\x00"
    raw = prefix + b"z" * (size - len(prefix))
    expected_digest = hashlib.sha256(raw).hexdigest()
    (vault / asset_path).write_bytes(raw)
    del raw
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    (vault / "Manual.md").write_bytes(b"Staged independent format writing.\r\n")
    git(vault, "add", "Manual.md")
    (vault / "Manual.md").write_bytes(b"Unstaged independent format writing.\r\n")
    before = user_state(vault, owned_ref=seed_locator["association"]["ref"])
    original_tree = _tree(root / "original7")
    fixture_tree = _tree(FIXTURE)
    archive_hash = _digest(source)
    authored = {
        path.relative_to(vault).as_posix(): _digest(path)
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    }
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    scratch_before = _tree(scratch)
    capacity = 96 * 1024 * 1024
    assert 9 * size + 64 * 1024 * 1024 > capacity
    observations = []

    def available_memory():
        observations.append(capacity)
        return capacity

    for module in (native, history, lifecycle, checkpoint_payload):
        monkeypatch.setattr(module, "available_memory", available_memory)
    warm = UpdateContext(operations=operations)
    opened = worker_context_call(
        warm,
        {
            "command": "prepare",
            "vault": str(vault),
            "source": str(source),
            "selection_id": "11111111-1111-4111-8111-111111111111",
            "kind": "format_transition",
        },
    )
    assert opened.status == "prepared_review" and opened.kind == "format_transition", (
        opened.model_dump_json()
    )
    assert (
        opened.binding is not None and opened.binding.checkpoint_commit == seed_commit
    )
    assert observations
    page = worker_context_call(
        warm, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available" and page.page.next_offset is None, (
        page.model_dump_json()
    )
    index, row = next(
        (index, row)
        for index, row in enumerate(page.page.items)
        if row.item_id == item_id and row.facet == "asset"
    )
    shown = worker_context_call(
        warm,
        {
            "command": "page",
            "binding": opened.binding,
            "offset": index,
            "limit": 1,
            "byte_limit": 256,
        },
    )
    assert shown.status == "available", shown.model_dump_json()
    (displayed,) = shown.page.items
    assert displayed.original == displayed.incoming == original
    assert displayed.current_path == displayed.incoming_path == asset_path
    assert displayed.current == prefix + b"z" * (len(displayed.current) - len(prefix))
    assert len(prefix) <= len(displayed.current) <= 256 and displayed.omitted
    assert (
        sum(
            len(value)
            for value in (
                displayed.original,
                displayed.current,
                displayed.incoming,
                displayed.result,
            )
            if value is not None
        )
        <= 256
    )
    (offer,) = [
        offer
        for offer in shown.offers
        if offer.change_id == row.change_id and offer.domain == "format"
    ]
    assert "current" in offer.choices
    chosen = worker_context_call(
        warm,
        {
            "command": "choose",
            "binding": opened.binding,
            "requirement_id": offer.requirement_id,
            "choice": "current",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert chosen.code == "accepted" and chosen.binding is not None, (
        chosen.model_dump_json()
    )
    page = worker_context_call(
        warm, {"command": "page", "binding": chosen.binding, "byte_limit": 0}
    )
    assert page.status == "available" and page.configuration is not None, (
        page.model_dump_json()
    )
    assert (
        page.configuration.member_count > 0 and "current" in page.configuration.choices
    )
    configured = worker_context_call(
        warm,
        {
            "command": "choose_configuration",
            "binding": chosen.binding,
            "group_id": page.configuration.group_id,
            "choice": "current",
        },
    )
    assert configured.code == "accepted" and configured.binding is not None, (
        configured.model_dump_json()
    )
    assert not configured.ready
    saved = worker_context_call(
        warm, {"command": "save", "binding": configured.binding}
    )
    assert saved.code == "saved" and saved.capture is not None, saved.model_dump_json()
    assert saved.capture.status == "captured" and saved.history_retained
    assert not saved.ready
    assert (
        saved.binding.checkpoint_generation == 2
        and saved.binding.checkpoint_commit == saved.capture.commit
    )
    manifest = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":manifest.json")
    )
    assert manifest["boundary"] == "local" and manifest["previous"] == seed_commit
    assert manifest["source"] == seed_manifest["source"]
    assert manifest["reviewed_source"]["target_source_version"] == source_version
    for relative, expected in payload.items():
        assert (
            git(vault, "cat-file", "blob", seed_commit + ":source/" + relative)
            == expected
        )
    assert manifest["identity"]["output_format"] == 7
    assert manifest["reviewed_source"]["incoming_identity"]["output_format"] == 8
    incoming = next(
        row for row in manifest["reviewed_source"]["files"] if row["path"] == asset_path
    )
    assert (
        incoming["size"] == len(original)
        and incoming["sha256"] == hashlib.sha256(original).hexdigest()
    )
    plan = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":review.json")
    )["record"]["plan"]
    assert not plan["ready"]
    facts = plan["facts"]
    assert (
        facts["baseline_identity"]["output_format"] == 7
        and facts["incoming_identity"]["output_format"] == 8
    )
    assert facts["format_operation"]["kind"] == "format_transition"
    assert facts["format_operation"]["recorded_generation"] == "supported"
    assert (
        facts["format_operation"]["baseline_source_version"]
        == facts["format_operation"]["target_source_version"]
        == source_version
    )
    subject = next(
        row
        for row in facts["subjects"]
        if row["item_id"] == item_id and row["facet"] == "asset"
    )
    assert (
        subject["baseline"]["status"] == "known"
        and subject["baseline"]["content"] is not None
    )
    approval = next(
        row
        for row in plan["approvals"]
        if row["change_id"] == displayed.change_id and row["domain"] == "format"
    )
    assert approval["choice"] == "current" and approval["provenance"] == "explicit_user"
    configurations = [
        row for row in plan["approvals"] if row["domain"] == "configuration"
    ]
    assert len(configurations) == page.configuration.member_count
    assert all(
        row["choice"] == "current" and row["provenance"] == "explicit_user"
        for row in configurations
    )
    assert (
        git(vault, "cat-file", "blob", saved.capture.commit + ":source/" + asset_path)
        == original
    )
    retained = git(
        vault, "cat-file", "blob", saved.capture.commit + ":vault/" + asset_path
    )
    assert (
        len(retained) == size
        and hashlib.sha256(retained).hexdigest() == expected_digest
    )
    assert retained[: len(prefix)] == prefix
    del retained
    closed = worker_context_call(
        warm, {"command": "close", "binding": saved.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None, (
        closed.model_dump_json()
    )
    assert _tree(scratch) == scratch_before
    del warm, page, shown
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator = (vault / ".brz2obsidian/locator.json").read_bytes()
    cold = UpdateContext()
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
    assert (
        loaded.kind == "format_transition"
        and not loaded.ready
        and loaded.binding is None
    )
    assert loaded.checkpoint_commit == saved.capture.commit and loaded.next_actions == (
        "resume_update",
    )
    assert _tree(scratch) == scratch_before
    resumed = worker_context_call(
        cold,
        {
            "command": "resume",
            "vault": str(vault),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert resumed.status == "prepared_review" and resumed.binding is not None, (
        resumed.model_dump_json()
    )
    assert resumed.kind == "format_transition" and resumed.code == "unchanged"
    assert not resumed.ready
    assert resumed.binding.context_id != saved.binding.context_id
    assert resumed.binding.proposal_id == saved.binding.proposal_id
    # Unchanged canonical facts and actual format-purpose scoped preflight retain
    # the saved review generation; checkpoint generation is a separate counter.
    assert resumed.binding.generation == saved.binding.generation
    assert (
        resumed.binding.checkpoint_generation == 2
        and resumed.binding.checkpoint_commit == saved.capture.commit
    )
    assert cold.page(saved.binding).code == "context_changed"
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
    (displayed,) = shown.page.items
    assert displayed.item_id == item_id and displayed.facet == "asset"
    assert displayed.original == displayed.incoming == original
    assert displayed.current == prefix + b"z" * (len(displayed.current) - len(prefix))
    assert len(prefix) <= len(displayed.current) <= 256 and displayed.omitted
    selected = next(
        offer
        for offer in shown.offers
        if offer.change_id == displayed.change_id and offer.domain == "format"
    )
    assert (
        selected.selected == "current"
        and selected.decision_id == approval["decision_id"]
    )
    assert shown.configuration is not None and shown.configuration.selected == "current"
    choices = worker_context_call(
        cold, {"command": "choices", "binding": resumed.binding}
    )
    assert choices.status == "available" and choices.next_choice_offset is None, (
        choices.model_dump_json()
    )
    assert {
        offer.decision_id for offer in choices.offers if offer.domain == "configuration"
    } == {row["decision_id"] for row in configurations}
    closed = worker_context_call(
        cold, {"command": "close", "binding": resumed.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None, (
        closed.model_dump_json()
    )
    assert _tree(scratch) == scratch_before
    assert user_state(vault, owned_ref=saved.capture.ref) == before
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    assert git(vault, "cat-file", "blob", seed_commit + ":manifest.json") == seed_bytes
    assert _tree(root / "original7") == original_tree and _tree(FIXTURE) == fixture_tree
    assert _digest(source) == archive_hash
    assert {
        path.relative_to(vault).as_posix(): _digest(path)
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    } == authored
    assert (vault / asset_path).stat().st_size == size and _digest(
        vault / asset_path
    ) == expected_digest
