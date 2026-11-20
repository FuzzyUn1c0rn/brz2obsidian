"""Default onboarding preserves unknown originals without copying binary bodies."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import brz2obsidian.application.update_lifecycle as lifecycle
import brz2obsidian.publication.vault_history as history
import brz2obsidian.publication.vault_native as native
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.publication import checkpoint_payload
from tests.application.test_owned_update_preparation import _digest, _tree
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git, user_state
from tests.application.test_verified_coverage import (
    add_attachment,
    source_parts,
    write_source,
)
from tests.support.recorded_format8 import format8_workflow


def test_absent_history_onboarding_saves_unknown_binary_originals(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-363-"))
    marker = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(marker), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2]
        / "tmp/r347-owned-onboarding-20261109/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (marker["owner"] + ".json")).write_text(
        json.dumps(marker), encoding="utf-8"
    )
    source_directory = root / "source"
    source_directory.mkdir()
    parts = source_parts(source_directory)
    first_id = "66666666-6666-4666-8666-666666666666"
    second_id = "77777777-7777-4777-8777-777777777777"
    first_path = "Attachments/22222222/first.bin"
    second_path = "Attachments/22222222/second.bin"
    size = 16 * 1024 * 1024
    incoming_hashes = {}
    for identity, name, prefix in (
        (first_id, "first.bin", b"\xffA"),
        (second_id, "second.bin", b"\xfeB"),
    ):
        raw = prefix + b"x" * (size - len(prefix))
        incoming_hashes[name] = hashlib.sha256(raw).hexdigest()
        add_attachment(parts, identity, 1, name, raw)
    archive = write_source(source_directory, parts)
    del parts, raw
    workflow = format8_workflow()
    metadata = workflow.metadata_factory()
    workflow.metadata_factory = lambda: metadata
    rendered = root / "rendered"
    converted = workflow.convert(archive, rendered)
    assert converted.receipt is not None and converted.receipt.verified, converted
    assert (rendered / first_path).stat().st_size == size
    assert (rendered / second_path).stat().st_size == size
    assert _digest(rendered / first_path) == incoming_hashes["first.bin"]
    assert _digest(rendered / second_path) == incoming_hashes["second.bin"]
    rendered_size = sum(p.stat().st_size for p in rendered.rglob("*") if p.is_file())
    capacity = 96 * 1024 * 1024
    assert 32 * 1024 * 1024 <= rendered_size < 33 * 1024 * 1024
    assert 4 * rendered_size > capacity

    # This is an authored legacy vault, with neither a migration record nor
    # converter history. The available source archive proves no original bytes.
    vault = root / "vault"
    vault.mkdir()
    for path in rendered.iterdir():
        if path.name == "migration-record.json":
            continue
        if path.is_dir():
            shutil.copytree(path, vault / path.name)
        else:
            shutil.copy2(path, vault / path.name)
    current_first = b"\xffIndependent authored first.\r\n"
    current_second = b"\xfeIndependent authored second.\r\n"
    (vault / first_path).write_bytes(current_first)
    (vault / second_path).write_bytes(current_second)
    assert not (vault / "migration-record.json").exists()
    assert not (vault / ".brz2obsidian").exists()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Personal.md").write_bytes(b"Committed independent writing.\r\n")
    git(vault, "add", "Personal.md")
    git(vault, "commit", "-qm", "Independent legacy history")
    git(vault, "update-ref", "refs/notes/user-proof", "HEAD")
    (vault / "Personal.md").write_bytes(b"Staged independent writing.\r\n")
    git(vault, "add", "Personal.md")
    (vault / "Personal.md").write_bytes(b"Unstaged independent writing.\r\n")
    scratch = root / "owned-temporary"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    operations = Operations(workflow=workflow)
    absent = operations.inspect_history(vault)
    assert absent.status == "absent", absent
    assert (
        absent.admission.status == "supported" and absent.admission.inventory_complete
    )
    assert absent.admission.repository.kind == "root"
    assert absent.checkpoint.locator is None
    before = user_state(vault)
    scratch_before, rendered_before = _tree(scratch), _tree(rendered)
    archive_before = _digest(archive)
    capacity_observed = []

    def available_memory():
        capacity_observed.append(capacity)
        return capacity

    for module in (native, history, lifecycle, checkpoint_payload):
        monkeypatch.setattr(module, "available_memory", available_memory)
    context = UpdateContext(operations=operations)
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "vault": str(vault),
            "source": str(archive),
            "selection_id": "11111111-1111-4111-8111-111111111111",
            "kind": "onboarding",
        },
    )
    assert capacity_observed
    assert opened.status == "prepared_review" and opened.binding is not None, opened
    assert opened.kind == "onboarding" and not opened.ready
    assert not opened.history_retained and opened.checkpoint_commit is None
    assert opened.binding.checkpoint_commit is None
    assert opened.binding.checkpoint_generation is None
    assert "older_checkpoints_unavailable" in opened.findings
    page = worker_context_call(
        context, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available", page
    index, row = next(
        (index, row)
        for index, row in enumerate(page.page.items)
        if row.item_id == first_id and row.facet == "asset"
    )
    assert row.original is None and row.current_path == row.incoming_path == first_path
    offer = next(
        offer
        for offer in page.offers
        if offer.change_id == row.change_id and offer.domain == "format"
    )
    assert "current" in offer.choices
    accepted = worker_context_call(
        context,
        {
            "command": "choose",
            "binding": opened.binding,
            "requirement_id": offer.requirement_id,
            "choice": "current",
            "assumptions_digest": offer.assumptions_digest,
        },
    )
    assert accepted.code == "accepted" and accepted.binding is not None, accepted
    assert accepted.binding.revision > opened.binding.revision
    assert context.page(opened.binding).code == "context_changed"
    saved = worker_context_call(
        context, {"command": "save", "binding": accepted.binding}
    )
    assert saved.code == "saved" and saved.capture is not None, saved
    assert saved.capture.status == "captured" and saved.history_retained
    assert saved.checkpoint_commit == saved.capture.commit
    assert saved.binding.checkpoint_commit == saved.capture.commit
    assert saved.binding.checkpoint_generation == 1
    assert saved.binding.revision > accepted.binding.revision
    shown = worker_context_call(
        context,
        {
            "command": "page",
            "binding": saved.binding,
            "offset": index,
            "limit": 1,
            "byte_offset": 0,
            "byte_limit": 256,
        },
    )
    assert shown.status == "available" and shown.page.status == "available", shown
    displayed = shown.page.items[0]
    assert displayed.item_id == first_id and displayed.original is None
    assert displayed.current == current_first
    assert 64 <= len(displayed.incoming) <= 256
    assert displayed.incoming[:2] == b"\xffA"
    assert displayed.incoming[2:] == b"x" * (len(displayed.incoming) - 2)
    assert displayed.omitted and displayed.next_byte_offset == len(displayed.incoming)
    selected = next(offer for offer in shown.offers if offer.domain == "format")
    assert selected.selected == "current" and selected.decision_id is not None
    assert len(shown.model_dump_json().encode()) < 16384
    assert context.page(accepted.binding).code == "context_changed"
    foreign = saved.binding.model_copy(
        update={"context_id": "22222222-2222-4222-8222-222222222222"}
    )
    assert context.page(foreign).code == "context_changed"
    manifest = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":manifest.json")
    )
    envelope = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":review.json")
    )
    assert manifest["previous"] is None and manifest["boundary"] == "local"
    assert git(vault, "rev-list", "--count", saved.capture.ref) == b"1\n"
    assert git(
        vault, "rev-list", "--parents", "-n", "1", saved.capture.commit
    ).split() == [saved.capture.commit.encode()]
    assert envelope["schema_id"] == "brz2obsidian.saved-review-refs"
    assert envelope["schema_version"] == 1
    plan = envelope["record"]["plan"]
    facts = plan["facts"]
    assert facts["format_operation"]["kind"] == "onboarding"
    assert facts["format_operation"]["recorded_generation"] == "unknown"
    assert facts["format_operation"]["baseline_source_version"] is None
    assert facts["format_operation"]["established_baseline"] is None
    assert all(
        subject["baseline"]["status"] == "unknown"
        and subject["baseline"]["content"] is None
        for subject in facts["subjects"]
    )
    subject = next(s for s in facts["subjects"] if s["item_id"] == first_id)
    assert subject["attachment"] is not None and subject["interpretation"] == "opaque"
    approval = next(
        approval
        for approval in plan["approvals"]
        if approval["decision_id"] == selected.decision_id
    )
    assert approval["choice"] == "current" and approval["domain"] == "format"
    assert approval["provenance"] == "explicit_user" and not approval["source_accepted"]
    assert approval["attachment_selection"]["provenance"] == "explicit_user"
    assert approval["attachment_candidate"]["outputs"][0]["content"]["data"] == {
        "__brz2obsidian_review_blob__": hashlib.sha256(current_first).hexdigest()
    }
    source_rows = {row["path"]: row for row in manifest["source"]}
    for name, path, current in (
        ("first.bin", first_path, current_first),
        ("second.bin", second_path, current_second),
    ):
        assert source_rows[path]["size"] == size
        raw = git(vault, "cat-file", "blob", saved.capture.commit + ":source/" + path)
        assert (
            len(raw) == size
            and hashlib.sha256(raw).hexdigest() == incoming_hashes[name]
        )
        assert (
            git(vault, "cat-file", "blob", saved.capture.commit + ":vault/" + path)
            == current
        )
    del raw
    assert not saved.capture.authored_files_changed
    assert user_state(vault, owned_ref=saved.capture.ref) == before
    assert not (vault / "migration-record.json").exists()
    refs_before_repeat = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    locator_before_repeat = (vault / ".brz2obsidian/locator.json").read_bytes()

    # A real new authored fact makes repeat Save stale; it cannot silently
    # publish another checkpoint or turn unknown originals into known bytes.
    revised_second = b"\xfeWriting after the first saved checkpoint.\r\n"
    (vault / second_path).write_bytes(revised_second)
    repeat = worker_context_call(context, {"command": "save", "binding": saved.binding})
    assert repeat.status == "stale_review" and repeat.code == "current_facts_changed", (
        repeat
    )
    assert not repeat.ready and repeat.binding is not None and repeat.history_retained
    assert repeat.binding.revision > saved.binding.revision
    assert repeat.binding.checkpoint_commit == saved.capture.commit
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
        == refs_before_repeat
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == locator_before_repeat
    assert context.page(saved.binding).code == "context_changed"
    closed = worker_context_call(
        context, {"command": "close", "binding": repeat.binding, "choice": "discard"}
    )
    assert closed.code == "context_closed" and closed.binding is None, closed
    assert (
        closed.history_retained
        and context.page(repeat.binding).code == "context_changed"
    )
    expected = dict(
        before, authored=dict(before["authored"], **{second_path: revised_second})
    )
    assert user_state(vault, owned_ref=saved.capture.ref) == expected
    assert _tree(scratch) == scratch_before
    assert _tree(rendered) == rendered_before and _digest(archive) == archive_before
    assert (
        git(vault, "rev-parse", saved.capture.ref).decode().strip()
        == saved.capture.commit
    )
