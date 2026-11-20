"""Owned source updates preserve Apply outcomes at Git write boundaries."""

import hashlib
import json
import os
import shutil
import sys
from threading import Event
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.cli_review import CliReviewResult
from brz2obsidian.contracts import OutputIdentity
from brz2obsidian.publication import vault_history
from brz2obsidian.publication.git_read import _GitTimeout, read_git
from tests.application.test_update_context import worker_context_call
from tests.application.test_vault_checkpoints import fixture_case, git, user_state
from tests.application.test_verified_coverage import (
    OWNER,
    PDF,
    add_attachment,
    change_record,
    source_parts,
    write_source,
)

_ASSET = "Attachments/22222222/sample.bin"
_ORIGINAL = bytes(range(256))
_INCOMING = _ORIGINAL[::-1]


@pytest.fixture
def ready_source_update():
    vault, baseline = fixture_case()
    vault.rmdir()
    original, incoming = vault.parent / "old", vault.parent / "new"
    original.mkdir()
    incoming.mkdir()
    parts = source_parts(original)
    add_attachment(parts, PDF, 1, "sample.bin", _ORIGINAL)
    original_archive = write_source(original, parts)
    note = b"A different source note.\r\n"
    parts[f"{OWNER}/Notes.md"] = note
    note_id = json.loads(parts["attachments.json"].splitlines()[0])["Id"]
    change_record(parts, note_id, DataLength=len(note))
    parts[f"{OWNER}/sample.bin"] = _INCOMING
    incoming_archive = write_source(incoming, parts)

    workflow = default_workflow()
    converted = workflow.convert(original_archive, vault)
    assert converted.receipt is not None and converted.receipt.verified
    shutil.copytree(vault, baseline, dirs_exist_ok=True)
    (vault / "Personal.md").write_bytes(b"Independent writing.\n")
    git(vault, "init", "-q")
    git(vault, "add", "--", "Personal.md")
    git(vault, "-c", "commit.gpgsign=false", "commit", "-qm", "Independent history")
    operations = Operations(workflow=workflow)
    observed = operations.inspect_history(vault)
    assert observed.admission is not None, observed.model_dump_json()
    seed = operations.capture_checkpoint(
        vault,
        baseline,
        vault_id="batch-interruption-vault",
        import_id="batch-interruption-import",
        identity=OutputIdentity(
            collection_id="11111111-1111-4111-8111-111111111111",
            module_id="thebrain-brz",
            module_version="11",
            profile_id="thebrain-format5-reviewed",
            profile_version="11",
            output_format=9,
            settings_digest=hashlib.sha256(b"{}").hexdigest(),
        ),
        admission=observed.admission,
    )
    assert seed.status == "captured", seed.model_dump_json()
    context = UpdateContext(operations=operations)
    try:
        opened = context.prepare(
            vault, selection_id=str(uuid4()), source=incoming_archive
        )
        assert opened.ready and opened.binding is not None, opened.model_dump_json()
        yield vault, context, opened.binding, seed.ref
    finally:
        context.close(choice="discard")


@pytest.fixture
def saved_source_update(ready_source_update):
    vault, context, binding, ref = ready_source_update
    saved = context.save(binding)
    assert saved.ready and saved.binding is not None, saved.model_dump_json()
    assert saved.capture is not None and saved.capture.commit is not None
    context.close(saved.binding, choice="discard")
    return vault, saved, ref


@pytest.mark.parametrize("entry_point", ("cli", "worker"))
def test_apply_retains_prepared_and_result_after_clean_tree_batch_timeout(
    saved_source_update, monkeypatch, capsys, entry_point
):
    vault, saved, _ = saved_source_update
    read_git = vault_history.read_git
    timed_out = set()

    def timeout_after_first_tree(argv, **kwargs):
        if argv[-3:] == ["mktree", "-z", "--batch"]:
            current = (vault / _ASSET).read_bytes()
            if current not in timed_out:
                # Let Git write a real tree before reporting a clean timeout.
                rows = kwargs["input"].split(b"\0\0", 1)[0] + b"\0"
                first = read_git(argv[:-1], **dict(kwargs, input=rows))
                assert first.returncode == 0 and not first.stderr
                timed_out.add(current)
                raise _GitTimeout("Injected tree batch timeout", stdout=first.stdout)
        return read_git(argv, **kwargs)

    monkeypatch.setattr(vault_history, "read_git", timeout_after_first_tree)
    if entry_point == "cli":
        exit_code = main(
            [
                "review",
                "apply",
                str(vault),
                "--proposal-id",
                saved.binding.proposal_id,
                "--generation",
                str(saved.binding.generation),
                "--checkpoint",
                saved.capture.commit,
                "--json",
            ]
        )
        applied = CliReviewResult.model_validate_json(capsys.readouterr().out)
        assert exit_code == 0, applied.model_dump_json()
    else:
        cold = UpdateContext()
        try:
            resumed = worker_context_call(
                cold,
                {
                    "command": "resume",
                    "vault": str(vault),
                    "selection_id": str(uuid4()),
                },
            )
            assert resumed.ready and resumed.binding is not None, (
                resumed.model_dump_json()
            )
            applied = worker_context_call(
                cold, {"command": "apply", "binding": resumed.binding}
            )
        finally:
            cold.close(choice="discard")

    assert applied.status == "applied", applied.model_dump_json()
    assert timed_out == {_ORIGINAL, _INCOMING}
    operation = applied.operation
    assert operation is not None and operation.phase == "terminal"
    assert not operation.recovery_required
    assert (vault / _ASSET).read_bytes() == _INCOMING
    for commit, boundary in (
        (operation.checkpoint_commit, "prepared"),
        (operation.result_commit, "result"),
    ):
        raw = git(vault, "cat-file", "blob", commit + ":manifest.json")
        assert json.loads(raw)["boundary"] == boundary
    receipt = git(vault, "cat-file", "blob", operation.receipt_commit + ":receipt.json")
    assert json.loads(receipt)["status"] == "applied"


def test_apply_refuses_reordered_result_checkpoint_tree_ids(
    saved_source_update, monkeypatch
):
    vault, saved, ref = saved_source_update
    read_git = vault_history.read_git
    swapped = False

    def reorder_result_trees(argv, **kwargs):
        nonlocal swapped
        result = read_git(argv, **kwargs)
        if (
            not swapped
            and argv[-3:] == ["mktree", "-z", "--batch"]
            and (vault / _ASSET).read_bytes() == _INCOMING
        ):
            assert result.returncode == 0 and not result.stderr
            oids = result.stdout.splitlines(keepends=True)
            if len(set(oids)) > 1:
                other = next(index for index, oid in enumerate(oids) if oid != oids[0])
                oids[0], oids[other] = oids[other], oids[0]
                result.stdout = b"".join(oids)
                swapped = True
        return result

    cold = UpdateContext()
    try:
        resumed = worker_context_call(
            cold,
            {"command": "resume", "vault": str(vault), "selection_id": str(uuid4())},
        )
        assert resumed.ready and resumed.binding is not None, resumed.model_dump_json()
        assert resumed.binding.checkpoint_commit == saved.capture.commit
        monkeypatch.setattr(vault_history, "read_git", reorder_result_trees)
        outcome = worker_context_call(
            cold, {"command": "apply", "binding": resumed.binding}
        )
    finally:
        cold.close(choice="discard")

    assert swapped
    assert outcome.status == "recovery_required", outcome.model_dump_json()
    operation = outcome.operation
    assert operation is not None and operation.publication == "complete"
    assert operation.published_files == operation.planned_files == 4
    assert operation.intent_commit and operation.checkpoint_commit
    assert operation.result_commit is None and operation.receipt_commit is None
    assert (vault / _ASSET).read_bytes() == _INCOMING
    assert git(vault, "rev-parse", ref).decode().strip() == operation.checkpoint_commit
    rediscovered = Operations().inspect_update_status(vault)
    assert rediscovered.status == "content_complete", rediscovered.model_dump_json()
    assert rediscovered.intent_commit == operation.intent_commit
    assert rediscovered.receipt_commit is None


def test_resumed_apply_acknowledges_cancellation_during_prepared_verification(
    saved_source_update,
):
    vault, saved, ref = saved_source_update
    before = user_state(vault, owned_ref=ref)
    locator = vault / ".brz2obsidian" / "locator.json"
    preparing = False
    saw_prepared = False

    def progress(row):
        nonlocal preparing
        if row.phase == "snapshot_preparation":
            preparing = True

    def cancel():
        nonlocal saw_prepared
        if (
            not preparing
            or json.loads(locator.read_bytes())["commit"] == saved.capture.commit
        ):
            return False
        # Request a stop after Apply's first poll at the retained checkpoint.
        if not saw_prepared:
            saw_prepared = True
            return False
        return True

    cold = UpdateContext()
    try:
        resumed = cold.resume(vault, selection_id=str(uuid4()))
        assert resumed.ready and resumed.binding is not None, resumed.model_dump_json()
        stopped = cold.apply(resumed.binding, cancel=cancel, progress=progress)
    finally:
        cold.close(choice="discard")

    assert saw_prepared
    assert stopped.status == "cancelled_before_publication", stopped.model_dump_json()
    assert stopped.code == "cancelled_before_intent"
    operation = stopped.operation
    assert operation is not None and operation.history == "prepared"
    assert operation.published_files == 0 and not operation.recovery_required
    assert operation.intent_commit is None and operation.stop_commit is None
    assert operation.result_commit is None and operation.receipt_commit is None
    assert stopped.history_retained and stopped.checkpoint_commit is not None
    assert stopped.checkpoint_commit != saved.capture.commit
    assert git(vault, "rev-parse", ref).decode().strip() == stopped.checkpoint_commit
    prepared = git(
        vault, "cat-file", "blob", stopped.checkpoint_commit + ":manifest.json"
    )
    assert json.loads(prepared)["boundary"] == "prepared"
    assert user_state(vault, owned_ref=ref) == before


def test_owned_apply_reports_cancellation_after_successful_review_blob_batch(
    ready_source_update, monkeypatch
):
    vault, context, binding, ref = ready_source_update
    before = user_state(vault, owned_ref=ref)
    cancel = Event()
    read_git = vault_history.read_git

    def cancel_after_review_write(argv, **kwargs):
        result = read_git(argv, **kwargs)
        if (
            argv[-4:] == ["hash-object", "-w", "--no-filters", "--stdin-paths"]
            and b"review-content-" in kwargs["input"]
        ):
            assert result.returncode == 0 and not result.stderr
            assert not cancel.is_set(), "The fixture must cancel after the last batch"
            # This fixture's review content fills one batch and part of the next.
            if len(result.stdout.splitlines()) < 32:
                cancel.set()
        return result

    monkeypatch.setattr(vault_history, "read_git", cancel_after_review_write)
    stopped = context.apply(binding, cancel=cancel.is_set)

    assert cancel.is_set()
    assert stopped.status == "cancelled_before_publication", stopped.model_dump_json()
    assert stopped.code == "cancelled_before_intent"
    assert stopped.operation is not None and stopped.operation.intent_commit is None
    assert stopped.operation.history == "prepared" and stopped.history_retained
    prepared = git(
        vault, "cat-file", "blob", stopped.checkpoint_commit + ":manifest.json"
    )
    assert json.loads(prepared)["boundary"] == "prepared"
    assert user_state(vault, owned_ref=ref) == before


@pytest.mark.parametrize("diagnostic", (False, True))
def test_git_timeout_with_pending_input_preserves_output_and_diagnostics(diagnostic):
    child = (
        "import sys, time\n"
        "print('completed tree', flush=True)\n"
        "if sys.argv[1] == 'True': print('write error', file=sys.stderr, flush=True)\n"
        "time.sleep(30)\n"
    )
    with pytest.raises(OSError) as error:
        read_git(
            [sys._base_executable, "-c", child, str(diagnostic)],
            env=os.environ.copy(),
            input=b"x" * (96 * 1024),
            timeout=2,
        )

    if diagnostic:
        assert type(error.value) is OSError
        assert "Git reported an error" in str(error.value)
    else:
        assert isinstance(error.value, _GitTimeout)
        assert error.value.stdout.splitlines() == [b"completed tree"]
