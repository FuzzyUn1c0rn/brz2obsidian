"""Unknown first originals establish a terminal baseline before cold CLI publication."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli_review import CliReviewResult
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_owned_update_undo import _choose_incoming_attachment
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git, user_state
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    source_parts,
    write_source,
)


def _user_git(vault):
    state = user_state(vault)
    state.pop("authored")
    state["refs"] = tuple(
        row for row in state["refs"] if not row.startswith(b"refs/brz2obsidian/")
    )
    return state


def _authored(vault):
    return {
        path.relative_to(vault).as_posix(): (path.stat().st_size, _digest(path))
        for path in vault.rglob("*")
        if path.is_file()
        and path.relative_to(vault).parts[0] not in (".git", ".brz2obsidian")
    }


def _graph(vault, operation, *, previous, status):
    assert operation.history == "terminal" and operation.phase == "terminal"
    assert operation.publication == "complete" and not operation.recovery_required
    assert operation.status == status and operation.kind == "apply"
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
    assert prepared["boundary"] == "prepared" and prepared["previous"] == previous
    assert intent["prepared_commit"] == operation.checkpoint_commit
    assert intent["operation_id"] == operation.operation_id
    assert intent["kind"] == "apply" and intent["direction"] == "finish"
    assert intent["generation"] == prepared["generation"] == operation.generation
    assert (
        result["boundary"] == "result"
        and result["previous"] == operation.checkpoint_commit
    )
    assert result["operation_intent_commit"] == operation.intent_commit
    assert result["source"] == prepared["source"]
    assert result["vault"] == prepared["proposed"]
    assert receipt["prepared_commit"] == operation.checkpoint_commit
    assert receipt["intent_commit"] == operation.intent_commit
    assert receipt["result_commit"] == operation.result_commit
    assert receipt["status"] == status
    assert set(receipt["published_paths"]) == set(intent["affected_paths"])
    assert (
        operation.published_files
        == operation.planned_files
        == len(receipt["published_paths"])
    )
    return prepared, result, receipt


def _fresh_cli(root, scratch, label, arguments):
    marker = root / (label + "-capacity.json")
    script = """
import json, os, sys, tempfile
from pathlib import Path
import brz2obsidian.application.update_lifecycle as lifecycle
import brz2obsidian.publication.vault_history as history
import brz2obsidian.publication.vault_native as native
from brz2obsidian.publication import checkpoint_payload
from brz2obsidian.cli import main
observations = []
def available_memory():
    observations.append(96 * 1024 * 1024)
    return 96 * 1024 * 1024
for module in (native, history, lifecycle, checkpoint_payload):
    module.available_memory = available_memory
tempfile.tempdir = sys.argv[2]
try:
    code = main(sys.argv[3:])
finally:
    Path(sys.argv[1]).write_text(json.dumps({'pid': os.getpid(), 'observations': observations}), encoding='utf-8')
raise SystemExit(code)
"""
    process = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            script,
            str(marker),
            str(scratch),
            *arguments,
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=1200,
    )
    (root / (label + "-stdout.json")).write_text(process.stdout, encoding="utf-8")
    (root / (label + "-stderr.txt")).write_text(process.stderr, encoding="utf-8")
    assert process.returncode == 0, (process.stdout, process.stderr)
    assert process.stderr == "" and len(process.stdout.encode("utf-8")) <= 65536
    observation = json.loads(marker.read_bytes())
    assert observation["pid"] != os.getpid()
    assert observation["observations"] and set(observation["observations"]) == {
        96 * 1024 * 1024
    }
    assert (
        str(scratch) not in process.stdout
        and "brz2obsidian-update-" not in process.stdout
    )
    return CliReviewResult.model_validate_json(process.stdout), observation["pid"]


def test_unknown_onboarding_establishes_baseline_before_fresh_cli_applies_binary(
    monkeypatch,
):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-366-cli-"))
    marker = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(marker), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2]
        / "tmp/r347-owned-publication-20261110/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (marker["owner"] + ".json")).write_text(
        json.dumps(marker), encoding="utf-8"
    )
    source_a, source_b = root / "source-A", root / "source-B"
    source_a.mkdir()
    source_b.mkdir()
    asset_id = "66666666-6666-4666-8666-666666666666"
    asset_path = "Attachments/22222222/large.bin"
    original = b"\xffIndependent generated A.\r\n"
    current = b"\xfeIndependent authored binary.\r\n"
    parts = source_parts(source_a)
    add_attachment(parts, asset_id, 1, "large.bin", original)
    archive_a = write_source(source_a, parts)
    rendered = root / "rendered-A"
    converted = default_workflow().convert(archive_a, rendered)
    assert converted.receipt is not None and converted.receipt.verified, (
        converted.model_dump_json()
    )
    assert (rendered / asset_path).read_bytes() == original
    vault = root / "vault"
    vault.mkdir()
    for path in rendered.iterdir():
        if path.name == "migration-record.json":
            continue
        if path.is_dir():
            shutil.copytree(path, vault / path.name)
        else:
            shutil.copy2(path, vault / path.name)
    (vault / asset_path).write_bytes(current)
    assert not (vault / "migration-record.json").exists()
    assert not (vault / ".brz2obsidian").exists()
    manual = b"Independent ![[Attachments/22222222/large.bin]].\r\n"
    (vault / "Personal.md").write_bytes(b"Committed independent writing.\r\n")
    (vault / "Manual.md").write_bytes(manual)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", "Personal.md", "Manual.md")
    git(vault, "commit", "-qm", "Independent legacy writing")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    git(vault, "branch", "user-side")
    (vault / "Personal.md").write_bytes(b"Staged independent writing.\r\n")
    git(vault, "add", "Personal.md")
    personal = b"Later unstaged independent writing.\r\n"
    (vault / "Personal.md").write_bytes(personal)
    user_before = _user_git(vault)
    before = _authored(vault)
    original_rendered = _tree(rendered)
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    scratch_before = _tree(scratch)

    # Available source evidence supplies incoming bytes, never historical originals.
    onboarding = UpdateContext()
    state = worker_context_call(
        onboarding,
        {
            "command": "prepare",
            "kind": "onboarding",
            "vault": str(vault),
            "source": str(archive_a),
            "selection_id": "11111111-1111-4111-8111-111111111111",
        },
    )
    assert state.status == "prepared_review" and state.binding is not None, (
        state.model_dump_json()
    )
    assert state.kind == "onboarding" and not state.ready and not state.history_retained
    initial_page = worker_context_call(
        onboarding, {"command": "page", "binding": state.binding, "byte_limit": 0}
    )
    assert initial_page.status == "available" and initial_page.page.next_offset is None
    assert all(row.original is None for row in initial_page.page.items)
    for _ in range(3 * len(initial_page.page.items) + 1):
        if state.ready:
            break
        choices = worker_context_call(
            onboarding, {"command": "choices", "binding": state.binding}
        )
        assert choices.status == "available" and choices.next_choice_offset is None
        remaining = [offer for offer in choices.offers if offer.selected is None]
        assert remaining, choices.model_dump_json()
        offer = remaining[0]
        assert offer.domain in ("format", "configuration", "tracking", "storage")
        choice = "accept" if offer.domain in ("tracking", "storage") else "current"
        assert choice in offer.choices, choices.model_dump_json()
        state = worker_context_call(
            onboarding,
            {
                "command": "choose",
                "binding": state.binding,
                "requirement_id": offer.requirement_id,
                "choice": choice,
                "assumptions_digest": offer.assumptions_digest,
            },
        )
        assert state.code == "accepted" and state.binding is not None, (
            state.model_dump_json()
        )
    assert state.ready and state.unresolved == 0
    unsaved_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    refused = worker_context_call(
        onboarding, {"command": "apply", "binding": state.binding}
    )
    assert (
        refused.status == "unresolved" and refused.code == "first_checkpoint_required"
    ), refused.model_dump_json()
    assert (
        refused.binding is not None
        and refused.operation is None
        and not refused.history_retained
    )
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == unsaved_refs
    )
    assert _authored(vault) == before and _user_git(vault) == user_before
    first = worker_context_call(
        onboarding, {"command": "save", "binding": refused.binding}
    )
    assert first.code == "saved" and first.ready and first.capture is not None, (
        first.model_dump_json()
    )
    assert (
        first.binding.checkpoint_generation == 1 and first.capture.status == "captured"
    )
    first_manifest_raw = git(
        vault, "cat-file", "blob", first.capture.commit + ":manifest.json"
    )
    first_manifest = json.loads(first_manifest_raw)
    first_review_raw = git(
        vault, "cat-file", "blob", first.capture.commit + ":review.json"
    )
    first_plan = json.loads(first_review_raw)["record"]["plan"]
    assert first_manifest["boundary"] == "local" and first_manifest["previous"] is None
    assert first_plan["facts"]["format_operation"]["established_baseline"] is None
    assert first_plan["facts"]["format_operation"]["baseline_source_version"] is None
    assert first_plan["facts"]["format_operation"]["target_source_version"] is not None
    assert all(
        subject["baseline"]["status"] == "unknown"
        and subject["baseline"]["content"] is None
        for subject in first_plan["facts"]["subjects"]
    )
    assert first_plan["approvals"] and all(
        approval["choice"] == "current"
        and not approval["source_accepted"]
        and approval["provenance"] == "explicit_user"
        for approval in first_plan["approvals"]
    )
    established = worker_context_call(
        onboarding, {"command": "apply", "binding": first.binding}
    )
    assert (
        established.status == "no_content_change"
        and established.code != "already_current"
    ), established.model_dump_json()
    assert established.binding is None and established.operation is not None
    _, baseline_result, baseline_receipt = _graph(
        vault,
        established.operation,
        previous=first.capture.commit,
        status="no_content_change",
    )
    assert (
        established.operation.planned_files
        == established.operation.published_files
        == 0
    )
    assert baseline_receipt["published_paths"] == []
    assert all(
        row["path"] != "migration-record.json" for row in baseline_result["vault"]
    )
    assert (
        git(
            vault,
            "cat-file",
            "blob",
            established.operation.result_commit + ":source/" + asset_path,
        )
        == original
    )
    assert (
        git(
            vault,
            "cat-file",
            "blob",
            established.operation.result_commit + ":vault/" + asset_path,
        )
        == current
    )
    assert not (vault / "migration-record.json").exists()
    assert _authored(vault) == before and _user_git(vault) == user_before
    assert _tree(scratch) == scratch_before
    del onboarding, state, initial_page

    size = 16 * 1024 * 1024
    prefix = b"\xfdIndependent incoming CLI binary\x00"
    raw = prefix + b"x" * (size - len(prefix))
    incoming_digest = hashlib.sha256(raw).hexdigest()
    parts["22222222-2222-4222-8222-222222222222/large.bin"] = raw
    change_record(parts, asset_id, DataLength=size)
    archive_b = write_source(source_b, parts)
    del parts, raw
    archives_before = _digest(archive_a), _digest(archive_b)
    warm = UpdateContext()
    opened = worker_context_call(
        warm,
        {
            "command": "prepare",
            "kind": "source_update",
            "vault": str(vault),
            "source": str(archive_b),
            "selection_id": "22222222-2222-4222-8222-222222222222",
        },
    )
    assert opened.status == "prepared_review" and opened.binding is not None, (
        opened.model_dump_json()
    )
    page = worker_context_call(
        warm, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available" and page.page.next_offset is None
    index, row = next(
        (index, row)
        for index, row in enumerate(page.page.items)
        if row.item_id == asset_id and row.facet == "asset"
    )
    (offer,) = [
        offer
        for offer in page.offers
        if offer.change_id == row.change_id and offer.domain == "attachment"
    ]
    chosen = _choose_incoming_attachment(
        warm, opened, offer, path=asset_path, size=size, digest=incoming_digest
    )
    for _ in range(len(page.page.items) + 1):
        if chosen.ready:
            break
        choices = worker_context_call(
            warm, {"command": "choices", "binding": chosen.binding}
        )
        assert choices.status == "available" and choices.next_choice_offset is None
        remaining = [offer for offer in choices.offers if offer.selected is None]
        assert remaining and all(
            offer.domain in ("text", "restoration", "compatible_group")
            for offer in remaining
        ), choices.model_dump_json()
        offer = remaining[0]
        choice = (
            "incoming"
            if "incoming" in offer.choices
            else "restore_incoming"
            if "restore_incoming" in offer.choices
            else "approve"
        )
        assert choice in offer.choices
        chosen = worker_context_call(
            warm,
            {
                "command": "choose",
                "binding": chosen.binding,
                "requirement_id": offer.requirement_id,
                "choice": choice,
                "assumptions_digest": offer.assumptions_digest,
            },
        )
        assert chosen.code == "accepted" and chosen.binding is not None, (
            chosen.model_dump_json()
        )
    assert chosen.ready and chosen.unresolved == 0
    saved = worker_context_call(warm, {"command": "save", "binding": chosen.binding})
    assert saved.code == "saved" and saved.ready and saved.capture is not None, (
        saved.model_dump_json()
    )
    assert saved.binding.checkpoint_commit == saved.capture.commit
    closed = worker_context_call(
        warm, {"command": "close", "binding": saved.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None
    assert _tree(scratch) == scratch_before and _authored(vault) == before
    del warm, opened, chosen, page

    capacity = 96 * 1024 * 1024
    assert 9 * size + 64 * 1024 * 1024 > capacity
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator = (vault / ".brz2obsidian/locator.json").read_bytes()
    identity = [
        "--proposal-id",
        saved.binding.proposal_id,
        "--generation",
        str(saved.binding.generation),
        "--checkpoint",
        saved.capture.commit,
    ]
    shown, inspect_pid = _fresh_cli(
        root,
        scratch,
        "inspect",
        [
            "review",
            "inspect",
            str(vault),
            *identity,
            "--offset",
            str(index),
            "--limit",
            "1",
            "--byte-limit",
            "256",
            "--json",
        ],
    )
    assert (
        shown.command == "inspect"
        and shown.kind == "source_update"
        and shown.status == "prepared_review"
        and shown.ready
    )
    assert (shown.proposal_id, shown.generation, shown.checkpoint_commit) == (
        saved.binding.proposal_id,
        saved.binding.generation,
        saved.capture.commit,
    )
    assert shown.page.status == "available" and len(shown.page.items) == 1
    (displayed,) = shown.page.items
    assert (
        displayed.item_id == asset_id
        and displayed.original == original
        and displayed.current == current
    )
    assert len(prefix) <= len(displayed.incoming) <= 256 and displayed.omitted
    assert displayed.incoming == prefix + b"x" * (len(displayed.incoming) - len(prefix))
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
    assert _tree(scratch) == scratch_before and _authored(vault) == before
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator
    applied, apply_pid = _fresh_cli(
        root, scratch, "apply", ["review", "apply", str(vault), *identity, "--json"]
    )
    assert inspect_pid > 0 and apply_pid > 0
    assert (
        applied.command == "apply"
        and applied.kind == "source_update"
        and applied.status == "applied"
    ), applied.model_dump_json()
    assert (
        applied.operation is not None
        and applied.publication == "complete"
        and not applied.ready
    )
    assert (
        applied.proposal_id == saved.binding.proposal_id
        and applied.generation == saved.binding.generation
    )
    assert applied.source.source_sha256 == archives_before[1]
    prepared, result, receipt = _graph(
        vault, applied.operation, previous=saved.capture.commit, status="applied"
    )
    assert asset_path in receipt["published_paths"]
    assert applied.checkpoint_commit == applied.operation.result_commit
    assert (vault / asset_path).stat().st_size == size and _digest(
        vault / asset_path
    ) == incoming_digest
    with (vault / asset_path).open("rb") as stream:
        assert stream.read(len(prefix) + 32) == prefix + b"x" * 32
    for rows in (
        prepared["source"],
        prepared["proposed"],
        result["source"],
        result["vault"],
    ):
        (asset,) = [row for row in rows if row["path"] == asset_path]
        assert asset["size"] == size and asset["sha256"] == incoming_digest
    for commit, role in (
        (applied.operation.checkpoint_commit, "source"),
        (applied.operation.checkpoint_commit, "proposed"),
        (applied.operation.result_commit, "source"),
        (applied.operation.result_commit, "vault"),
    ):
        retained = git(
            vault, "cat-file", "blob", commit + ":" + role + "/" + asset_path
        )
        assert (
            len(retained) == size
            and hashlib.sha256(retained).hexdigest() == incoming_digest
        )
        assert retained[: len(prefix)] == prefix
        del retained
    assert (
        git(vault, "cat-file", "blob", first.capture.commit + ":manifest.json")
        == first_manifest_raw
    )
    assert (
        git(vault, "cat-file", "blob", first.capture.commit + ":review.json")
        == first_review_raw
    )
    assert _user_git(vault) == user_before
    assert (vault / "Manual.md").read_bytes() == manual and (
        vault / "Personal.md"
    ).read_bytes() == personal
    assert {
        path: value
        for path, value in _authored(vault).items()
        if path not in (asset_path, "migration-record.json", "MIGRATION REPORT.md")
    } == {
        path: value
        for path, value in before.items()
        if path not in (asset_path, "migration-record.json", "MIGRATION REPORT.md")
    }
    assert _tree(scratch) == scratch_before and _tree(rendered) == original_rendered
    assert (_digest(archive_a), _digest(archive_b)) == archives_before

    status_authored = _authored(vault)
    status_user_git = _user_git(vault)
    status_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    status_locator = (vault / ".brz2obsidian/locator.json").read_bytes()
    status, status_pid = _fresh_cli(
        root, scratch, "status", ["review", "status", str(vault), "--json"]
    )
    assert status_pid > 0
    assert (status.command, status.status, status.code) == (
        "status",
        "available",
        "history_available",
    )
    assert status.history_retained and status.checkpoint is not None
    assert status.checkpoint.commit == applied.operation.result_commit
    assert status.operation is not None
    assert (
        status.operation.operation_id,
        status.operation.generation,
        status.operation.status,
        status.operation.result_commit,
        status.operation.receipt_commit,
    ) == (
        applied.operation.operation_id,
        applied.operation.generation,
        "applied",
        applied.operation.result_commit,
        applied.operation.receipt_commit,
    )
    assert status.next_actions == ("review_update", "review_undo")
    assert _authored(vault) == status_authored
    assert _user_git(vault) == status_user_git
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == status_refs
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == status_locator
    assert _tree(scratch) == scratch_before
