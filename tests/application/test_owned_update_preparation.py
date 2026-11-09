"""Default native review commands retain verified binary bytes across Save."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import brz2obsidian.application.update_lifecycle as lifecycle
import brz2obsidian.publication.vault_history as history
import brz2obsidian.publication.vault_native as native
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import OutputIdentity
from brz2obsidian.publication import checkpoint_payload
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import git, user_state
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    source_parts,
    write_source,
)


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(65536):
            digest.update(block)
    return digest.hexdigest()


def _tree(root):
    return tuple(
        (
            path.relative_to(root).as_posix(),
            "directory" if path.is_dir() else "file",
            None if path.is_dir() else (path.stat().st_size, _digest(path)),
        )
        for path in sorted(root.rglob("*"))
    )


def test_default_context_prepares_saves_and_pages_binary_attachment(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-362-"))
    owner = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2]
        / "tmp/r347-owned-preparation-20261109/fixtures"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(
        json.dumps(owner), encoding="utf-8"
    )
    initial_directory, incoming_directory = root / "initial", root / "incoming"
    initial_directory.mkdir()
    incoming_directory.mkdir()
    parts = source_parts(initial_directory)
    first_id = "66666666-6666-4666-8666-666666666666"
    second_id = "77777777-7777-4777-8777-777777777777"
    first_path = "Attachments/22222222/first.bin"
    second_path = "Attachments/22222222/second.bin"
    size = 16 * 1024 * 1024
    original_hashes = {}
    for identity, name, prefix in (
        (first_id, "first.bin", b"\xffA"),
        (second_id, "second.bin", b"\xfeB"),
    ):
        raw = prefix + b"x" * (size - len(prefix))
        original_hashes[name] = hashlib.sha256(raw).hexdigest()
        add_attachment(parts, identity, 1, name, raw)
    del raw
    initial_archive = write_source(initial_directory, parts)
    workflow = default_workflow()
    metadata = workflow.metadata_factory()
    workflow.metadata_factory = lambda: metadata
    vault = root / "vault"
    converted = workflow.convert(initial_archive, vault)
    assert converted.receipt is not None and converted.receipt.verified, converted
    assert (vault / first_path).stat().st_size == size
    assert (vault / second_path).stat().st_size == size
    assert _digest(vault / first_path) == original_hashes["first.bin"]
    assert _digest(vault / second_path) == original_hashes["second.bin"]
    baseline = root / "baseline"
    shutil.copytree(vault, baseline)
    current_first, current_second = (
        b"\xffAuthored first.\r\n",
        b"\xfeAuthored second.\r\n",
    )
    incoming_first, incoming_second = (
        b"\xffIncoming first.\r\n",
        b"\xfeIncoming second.\r\n",
    )
    (vault / first_path).write_bytes(current_first)
    (vault / second_path).write_bytes(current_second)
    for identity, name, raw in (
        (first_id, "first.bin", incoming_first),
        (second_id, "second.bin", incoming_second),
    ):
        parts["22222222-2222-4222-8222-222222222222/" + name] = raw
        change_record(parts, identity, DataLength=len(raw))
    incoming_archive = write_source(incoming_directory, parts)
    del parts, raw
    with ZipFile(incoming_archive) as archive:
        assert (
            archive.read("22222222-2222-4222-8222-222222222222/first.bin")
            == incoming_first
        )
        assert (
            archive.read("22222222-2222-4222-8222-222222222222/second.bin")
            == incoming_second
        )
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
        vault_id="owned-preparation-vault",
        import_id="owned-preparation-import",
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
    assert seed.status == "captured" and seed.locator.generation == 1, seed
    seed_manifest_raw = git(vault, "cat-file", "blob", seed.commit + ":manifest.json")
    seed_manifest = json.loads(seed_manifest_raw)
    assert seed_manifest["review_object"] is None
    source_rows = {row["path"]: row for row in seed_manifest["source"]}
    assert source_rows[first_path]["size"] == source_rows[second_path]["size"] == size
    capacity = 96 * 1024 * 1024
    assert (
        32 * 1024 * 1024
        <= sum(row["size"] for row in source_rows.values())
        < 33 * 1024 * 1024
    )
    assert 4 * sum(row["size"] for row in source_rows.values()) > capacity
    before = user_state(vault, owned_ref=seed.ref)
    baseline_before, scratch_before = _tree(baseline), _tree(scratch)
    archive_before = _digest(initial_archive), _digest(incoming_archive)
    capacity_observed = []

    def available_memory():
        capacity_observed.append(capacity)
        return capacity

    # All aliases of the existing external OS-capacity adapter see one value;
    # the genuine seed capture and every native content/storage port remain real.
    for module in (native, history, lifecycle, checkpoint_payload):
        monkeypatch.setattr(module, "available_memory", available_memory)
    context = UpdateContext(operations=operations)
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "vault": str(vault),
            "source": str(incoming_archive),
            "selection_id": "11111111-1111-4111-8111-111111111111",
            "kind": "source_update",
        },
    )
    assert capacity_observed
    assert opened.status == "prepared_review" and opened.binding is not None, opened
    assert opened.code == "prepared" and opened.history_retained and not opened.ready
    page = worker_context_call(
        context, {"command": "page", "binding": opened.binding, "byte_limit": 0}
    )
    assert page.status == "available", page
    index, row = next(
        (index, row)
        for index, row in enumerate(page.page.items)
        if row.item_id == first_id and row.facet == "asset"
    )
    assert row.current_path == row.incoming_path == first_path
    offer = next(
        offer
        for offer in page.offers
        if offer.change_id == row.change_id and offer.domain == "attachment"
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
    assert (
        accepted.code == "accepted"
        and accepted.binding.revision > opened.binding.revision
    ), accepted
    assert context.page(opened.binding).code == "context_changed"
    saved = worker_context_call(
        context, {"command": "save", "binding": accepted.binding}
    )
    assert saved.code == "saved" and saved.capture is not None, saved
    assert saved.capture.status == "captured" and saved.history_retained
    assert saved.checkpoint_commit == saved.capture.commit != seed.commit
    assert saved.binding.checkpoint_commit == saved.capture.commit
    assert saved.binding.checkpoint_generation == 2
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
    assert displayed.item_id == first_id and displayed.current_path == first_path
    assert 64 <= len(displayed.original) <= 256
    assert displayed.original[:2] == b"\xffA"
    assert displayed.original[2:] == b"x" * (len(displayed.original) - 2)
    assert displayed.current == current_first and displayed.incoming == incoming_first
    assert displayed.offset == 0 and displayed.omitted
    assert displayed.next_byte_offset == len(displayed.original)
    selected = next(offer for offer in shown.offers if offer.domain == "attachment")
    assert selected.selected == "current" and selected.decision_id is not None
    assert len(shown.model_dump_json().encode()) < 16384
    assert context.page(accepted.binding).code == "context_changed"
    foreign = saved.binding.model_copy(
        update={"context_id": "22222222-2222-4222-8222-222222222222"}
    )
    assert context.page(foreign).code == "context_changed"
    retained_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    retained_locator = (vault / ".brz2obsidian/locator.json").read_bytes()
    again = worker_context_call(context, {"command": "save", "binding": saved.binding})
    assert again.code == "saved" and again.capture is not None, again
    assert again.capture.status == "unchanged" and again.history_retained
    assert again.capture.commit == again.checkpoint_commit == saved.capture.commit
    assert again.binding.checkpoint_commit == saved.binding.checkpoint_commit
    assert again.binding.checkpoint_generation == 2
    assert again.binding.revision > saved.binding.revision
    assert context.page(saved.binding).code == "context_changed"
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == retained_refs
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == retained_locator
    manifest = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":manifest.json")
    )
    envelope = json.loads(
        git(vault, "cat-file", "blob", saved.capture.commit + ":review.json")
    )
    assert (
        envelope["schema_id"] == "brz2obsidian.saved-review-refs"
        and envelope["schema_version"] == 1
    )
    assert manifest["previous"] == seed.commit and manifest["boundary"] == "local"
    assert (
        git(vault, "rev-parse", saved.capture.commit + "^").decode().strip()
        == seed.commit
    )
    assert manifest["source"] == seed_manifest["source"]
    plan = envelope["record"]["plan"]
    subject = next(
        subject
        for subject in plan["facts"]["subjects"]
        if subject["item_id"] == first_id and subject["facet"] == "asset"
    )
    assert subject["attachment"] is not None and subject["interpretation"] == "opaque"
    assert subject["baseline"]["content"]["data"] == {
        "__brz2obsidian_review_blob__": original_hashes["first.bin"]
    }
    approval = next(
        approval
        for approval in plan["approvals"]
        if approval["decision_id"] == selected.decision_id
    )
    assert approval["choice"] == "current" and approval["provenance"] == "explicit_user"
    assert approval["source_accepted"] is False
    assert approval["attachment_selection"]["provenance"] == "explicit_user"
    output = approval["attachment_candidate"]["outputs"][0]
    assert output["path"] == first_path
    assert output["content"]["data"] == {
        "__brz2obsidian_review_blob__": hashlib.sha256(current_first).hexdigest()
    }
    assert (
        git(vault, "cat-file", "blob", saved.capture.commit + ":vault/" + first_path)
        == current_first
    )
    assert (
        git(vault, "cat-file", "blob", saved.capture.commit + ":vault/" + second_path)
        == current_second
    )
    assert json.loads(retained_locator)["commit"] == saved.capture.commit
    assert (
        not saved.capture.authored_files_changed
        and not again.capture.authored_files_changed
    )
    closed = worker_context_call(
        context, {"command": "close", "binding": again.binding, "choice": "discard"}
    )
    assert (
        closed.code == "context_closed"
        and closed.binding is None
        and closed.history_retained
    )
    assert context.page(again.binding).code == "context_changed"
    assert _tree(scratch) == scratch_before
    assert user_state(vault, owned_ref=seed.ref) == before
    assert _tree(baseline) == baseline_before
    assert (_digest(initial_archive), _digest(incoming_archive)) == archive_before
    assert (
        git(vault, "cat-file", "blob", seed.commit + ":manifest.json")
        == seed_manifest_raw
    )
    assert git(vault, "rev-parse", seed.ref).decode().strip() == saved.capture.commit
