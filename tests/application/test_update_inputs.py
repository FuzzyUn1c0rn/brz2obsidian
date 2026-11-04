"""One lexical public read retains complete physical history qualification."""

import pytest

from brz2obsidian.application.checkpoint_payload_contracts import (
    CheckpointPayloadRequest,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.vault_contracts import VaultSubject
from tests.application.test_checkpoint_payload import git, retained
from tests.application.test_vault_apply import _apply, _ready_case
from tests.application.test_vault_checkpoints import user_state

__all__ = ["retained"]


def test_idle_reader_keeps_exact_source_and_user_operation_named_ref(retained):
    vault, locator = retained
    git(vault, "update-ref", "refs/heads/feature/operations/local", "HEAD")
    before = git(vault, "show-ref")
    index = (vault / ".git/index").read_bytes()
    authored = (vault / "note.md").read_bytes()
    requests = (CheckpointPayloadRequest(path="note.md", limit=7),)
    reader = Operations().inspect_update_inputs(vault)
    with reader as observed:
        assert observed.history.status == "intact"
        assert observed.history.checkpoint.locator == locator
        answer = observed.read_payload(locator=locator, requests=requests, byte_limit=7)
        assert answer.status == "available", answer
        assert answer.chunks[0].data == b"A\r\nB\x00\xffZ"
        scoped = observed.inspect(subjects=())
        assert scoped.admission.inventory == observed.history.admission.inventory
        assert scoped.admission.status == "supported"
    assert git(vault, "show-ref") == before
    assert (vault / ".git/index").read_bytes() == index
    assert (vault / "note.md").read_bytes() == authored
    closed = reader.read_payload(locator=locator, requests=requests, byte_limit=7)
    assert closed.status == "refused" and not closed.chunks
    with pytest.raises(OSError), reader:
        pass


def test_reader_refuses_changed_refs_and_new_converter_lease(retained):
    vault, locator = retained
    operations = Operations()
    requests = (CheckpointPayloadRequest(path="note.md", limit=7),)
    ref = "refs/heads/ordered-reader-change"
    with operations.inspect_update_inputs(vault) as observed:
        git(vault, "update-ref", ref, "HEAD")
        try:
            answer = observed.read_payload(
                locator=locator, requests=requests, byte_limit=7
            )
            assert answer.status == "refused" and not answer.chunks
            with pytest.raises(OSError):
                observed.inspect(subjects=())
        finally:
            git(vault, "update-ref", "-d", ref)
    with operations.inspect_update_inputs(vault) as observed:
        lease = vault / ".git/brz2obsidian"
        assert not lease.exists()
        lease.mkdir()
        try:
            answer = observed.read_payload(
                locator=locator, requests=requests, byte_limit=7
            )
            assert answer.status == "refused" and not answer.chunks
        finally:
            lease.rmdir()


def test_scoped_reader_refuses_changed_current_rules_without_pending_consent(retained):
    vault, _ = retained
    attributes = vault / ".git/info/attributes"
    assert not attributes.exists()
    with Operations().inspect_update_inputs(vault) as observed:
        attributes.write_bytes(b"note.md -text\n")
        try:
            fresh = Operations().inspect_history(vault)
            assert fresh.admission.status == "supported"
            assert not fresh.admission.preflight.consents
            with pytest.raises(OSError):
                observed.inspect(subjects=())
        finally:
            attributes.unlink()


def test_fresh_selected_query_domain_exposes_distinct_storage_and_tracking(retained):
    vault, _ = retained
    attributes = vault / ".git/info/attributes"
    excludes = vault / ".git/info/exclude"
    assert not attributes.exists()
    previous = excludes.read_bytes()
    attributes.write_bytes(b"New.bin text\n")
    excludes.write_bytes(previous + b"\nIgnored/private.bin\n")
    try:
        with Operations().inspect_update_inputs(vault) as observed:
            scoped = observed.inspect(
                subjects=(
                    VaultSubject(path="New.bin", subject_id="selected-storage"),
                    VaultSubject(
                        path="Ignored/private.bin", subject_id="selected-tracking"
                    ),
                )
            )
            assert {r.kind for r in scoped.admission.preflight.consents} == {
                "storage",
                "tracking",
            }
            assert scoped.admission.inventory == observed.history.admission.inventory
    finally:
        attributes.unlink()
        excludes.write_bytes(previous)


def test_terminal_reader_keeps_real_operation_graph_and_exact_source():
    vault, source, operations, review, _ = _ready_case()
    applied = _apply(
        operations,
        vault,
        source,
        review=review,
        vault_id="vault-one",
        import_id="import-one",
    )
    assert applied.status == "applied", applied
    before = user_state(vault)
    with operations.inspect_update_inputs(vault) as observed:
        assert observed.history.status == "intact"
        assert observed.history.checkpoint.locator.commit == applied.result_commit
        answer = observed.read_payload(
            locator=observed.history.checkpoint.locator,
            requests=(CheckpointPayloadRequest(path="Notes/Opening.md", limit=17),),
            byte_limit=17,
        )
        assert answer.status == "available", answer
        assert answer.chunks[0].data == b"incoming opening\n"
        assert observed.inspect(subjects=()).admission.status == "supported"
    assert user_state(vault) == before
    assert (vault / "Notes/Opening.md").read_bytes() == b"incoming opening\n"
    assert (vault / "Notes/Local.md").read_bytes() == b"local \xff\r\n"
