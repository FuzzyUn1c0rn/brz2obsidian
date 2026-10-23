"""Public exact-byte history outcomes with independently inspected Git graphs."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import Operations


def fixture_case():
    token = uuid4().hex
    container = Path(tempfile.mkdtemp(prefix="brz2obsidian-272-"))
    record = {
        "owner": token,
        "root": str(container.resolve()),
        "base": str(Path(tempfile.gettempdir()).resolve()),
    }
    (container / ".fixture-owner.json").write_text(json.dumps(record), encoding="utf-8")
    evidence = Path(__file__).resolve().parents[2] / "tmp/issue-272/fixtures"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (token + ".json")).write_text(json.dumps(record), encoding="utf-8")
    vault, source = container / "vault", container / "converted"
    vault.mkdir()
    source.mkdir()
    return vault, source


def git(vault, *args, input=None):
    start = time.perf_counter()
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Checkpoint fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-C",
            str(vault),
            *args,
        ],
        input=input,
        capture_output=True,
        check=False,
    )
    timing("fixture_git", time.perf_counter() - start)
    assert result.returncode == 0, result.stderr
    return result.stdout


def timing(kind, elapsed):
    evidence = Path(__file__).resolve().parents[2] / "tmp/issue-272/timings.jsonl"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    with evidence.open("a", encoding="utf-8") as output:
        output.write(
            json.dumps(
                {
                    "kind": kind,
                    "seconds": elapsed,
                    "test": os.environ.get("PYTEST_CURRENT_TEST"),
                }
            )
            + "\n"
        )


def capture(operations, *args, **kwargs):
    started = time.perf_counter()
    try:
        return operations.capture_checkpoint(*args, **kwargs)
    finally:
        timing("capture", time.perf_counter() - started)


def read_history(operations, *args, **kwargs):
    started = time.perf_counter()
    try:
        return operations.read_checkpoint(*args, **kwargs)
    finally:
        timing("read_history", time.perf_counter() - started)


def inspect(operations, *args, **kwargs):
    started = time.perf_counter()
    try:
        return operations.inspect_vault(*args, **kwargs)
    finally:
        timing("inspect", time.perf_counter() - started)


def user_state(vault, *, owned_ref=None):
    return {
        "index": (vault / ".git/index").read_bytes(),
        "head": (vault / ".git/HEAD").read_bytes(),
        "config": (vault / ".git/config").read_bytes(),
        "stages": git(vault, "ls-files", "--stage", "-z"),
        "refs": tuple(
            row
            for row in git(
                vault, "for-each-ref", "--format=%(refname) %(objectname)"
            ).splitlines()
            if row.split(b" ", 1)[0] != (owned_ref or "").encode()
        ),
        "authored": {
            p.relative_to(vault).as_posix(): p.read_bytes()
            for p in vault.rglob("*")
            if p.is_file()
            and ".git" not in p.relative_to(vault).parts
            and ".brz2obsidian" not in p.relative_to(vault).parts
        },
    }


def test_capture_distinct_source_vault_roots_and_raw_roundtrip_preserves_user_state():
    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "note.md").write_bytes(b"staged\r\n")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "user history")
    git(vault, "update-ref", "refs/notes/literal-user", "HEAD")
    git(vault, "update-ref", "refs/brz2obsidian/user-independent", "HEAD")
    (vault / "note.md").write_bytes(b"different staged\n")
    git(vault, "add", "note.md")
    (vault / "note.md").write_bytes(b"vault mixed\r\nending\n\xff")
    (vault / "user.bin").write_bytes(b"\x00\x80\xff")
    (source / "note.md").write_bytes(b"converted source\r\n")
    (source / "asset.bin").write_bytes(b"\xff\x00source")
    before = user_state(vault)
    operations = Operations()
    admission = inspect(operations, vault)
    result = capture(
        operations,
        vault,
        source,
        vault_id="vault-one",
        import_id="import-one",
        identity={
            "collection_id": "collection-one",
            "module_id": "fixture",
            "module_version": "1",
            "profile_id": "profile",
            "profile_version": "1",
            "output_format": 7,
            "settings_digest": "literal-settings",
        },
        admission=admission,
    )
    assert result.status == "captured"
    assert result.history_retained is True
    assert result.authored_files_changed is False
    assert user_state(vault, owned_ref=result.ref) == before
    checkpoint = read_history(operations, vault)
    assert checkpoint.status == "valid"
    assert [(f.path, f.mode, f.size) for f in checkpoint.manifest.source] == [
        ("asset.bin", "100644", 8),
        ("note.md", "100644", 18),
    ]
    assert [(f.path, f.mode, f.size) for f in checkpoint.manifest.vault] == [
        ("note.md", "100644", 21),
        ("user.bin", "100644", 3),
    ]
    assert (
        git(vault, "cat-file", "blob", result.commit + ":source/note.md")
        == b"converted source\r\n"
    )
    assert (
        git(vault, "cat-file", "blob", result.commit + ":vault/note.md")
        == b"vault mixed\r\nending\n\xff"
    )
    assert (
        git(vault, "cat-file", "blob", result.commit + ":vault/user.bin")
        == b"\x00\x80\xff"
    )
    assert git(vault, "rev-parse", result.ref).decode().strip() == result.commit
    assert (
        checkpoint.manifest.source[1].sha256
        == hashlib.sha256(b"converted source\r\n").hexdigest()
    )


def test_checkpoint_resource_preflight_refuses_before_any_owned_write(monkeypatch):
    import brz2obsidian.publication.vault_history as history

    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "note.md").write_bytes(b"authored\n")
    (source / "note.md").write_bytes(b"source\n")
    operations = Operations()
    admission = inspect(operations, vault)
    assert admission.status == "supported"
    before = ((vault / "note.md").read_bytes(), (source / "note.md").read_bytes())
    monkeypatch.setattr(history, "available_memory", lambda: 0)
    refused = capture(
        operations,
        vault,
        source,
        vault_id="resource-vault",
        import_id="resource-import",
        identity={
            "collection_id": "resource-collection",
            "module_id": "fixture",
            "module_version": "1",
            "profile_id": "profile",
            "profile_version": "1",
            "output_format": 7,
            "settings_digest": "literal-settings",
        },
        admission=admission,
    )
    assert (
        refused.status == "refused"
        and refused.code == "insufficient_checkpoint_resources"
    )
    assert refused.object_storage == "not_started" and not refused.objects_written
    assert before == (
        (vault / "note.md").read_bytes(),
        (source / "note.md").read_bytes(),
    )
    assert git(vault, "for-each-ref", "refs/brz2obsidian/imports") == b""
    assert not (vault / ".brz2obsidian").exists()


def test_historical_review_spool_counts_against_same_volume_peak_before_owned_write(
    monkeypatch,
):
    import brz2obsidian.publication.vault_history as history
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import (
        action,
        preflight,
        with_review_links,
    )

    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "Notes").mkdir()
    (source / "Notes").mkdir()
    current, incoming = b"authored", b"source-v2"
    baseline = b"B" * (512 * 1024)
    (vault / "Notes/Opening.md").write_bytes(current)
    (source / "Notes/Opening.md").write_bytes(incoming)
    git(vault, "add", "--", "Notes/Opening.md")
    facts = with_review_links(
        request(original=baseline, current=current, incoming=incoming)
    )
    initial = prepare_review(facts, preflight=preflight())
    reviewed = resolve_review(initial, action(initial, choice="current")).plan
    assert reviewed.ready
    operations = Operations()
    before = user_state(vault)
    admission = inspect(operations, vault)
    assert admission.status == "supported"
    assert os.stat(vault).st_dev == os.stat(tempfile.gettempdir()).st_dev
    actual_usage = shutil.disk_usage(vault)
    input_size = len(current) + len(incoming)
    # The 768 KiB allowance above input and margins can hold one copy of the
    # unmatched 512 KiB baseline, but not both its spool and Git object copy.
    free = 2 * input_size + 2 * 64 * 1024 * 1024 + 768 * 1024
    monkeypatch.setattr(
        history.shutil, "disk_usage", lambda _path: actual_usage._replace(free=free)
    )
    refused = capture(
        operations,
        vault,
        source,
        vault_id="review-resource-vault",
        import_id="review-resource-import",
        identity=facts.incoming_identity,
        admission=admission,
        review=reviewed,
    )
    assert refused.status == "refused"
    assert refused.code == "insufficient_checkpoint_resources"
    assert refused.object_storage == "not_started" and not refused.objects_written
    assert user_state(vault) == before
    assert git(vault, "for-each-ref", "refs/brz2obsidian/imports") == b""
    assert not (vault / ".brz2obsidian").exists()


def test_intact_owned_history_noop_and_independent_user_ancestry_rewrite():
    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "note.md").write_bytes(b"original user\n")
    (source / "note.md").write_bytes(b"source one\n")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "original user ancestry")
    operations = Operations()
    identity = {
        "collection_id": "collection-one",
        "module_id": "fixture",
        "module_version": "1",
        "profile_id": "profile",
        "profile_version": "1",
        "output_format": 7,
        "settings_digest": "literal-settings",
    }
    first = capture(
        operations,
        vault,
        source,
        vault_id="stable-vault",
        import_id="stable-import",
        identity=identity,
        admission=inspect(operations, vault),
    )
    assert first.status == "captured"
    observed = inspect(operations, vault)
    assert observed.status == "supported"
    assert observed.preflight.state_status == "supported"
    before = user_state(vault, owned_ref=first.ref)
    unchanged = capture(
        operations,
        vault,
        source,
        vault_id="stable-vault",
        import_id="stable-import",
        identity=identity,
        admission=observed,
    )
    assert unchanged.status == "unchanged"
    assert unchanged.commit == first.commit
    assert git(vault, "rev-list", "--count", first.ref) == b"1\n"
    assert user_state(vault, owned_ref=first.ref) == before

    # A real independent root commit replaces the user's ancestry, preserving
    # authored state. Its graph has no ancestry edge to converter history.
    tree = git(vault, "rev-parse", "HEAD^{tree}").decode().strip()
    new_user = (
        git(vault, "commit-tree", tree, input=b"independent user root\n")
        .decode()
        .strip()
    )
    git(vault, "update-ref", "HEAD", new_user)
    assert git(vault, "rev-list", "--count", "HEAD") == b"1\n"
    observed = inspect(operations, vault)
    assert observed.status == "supported"
    assert read_history(operations, vault).status == "valid"
    (source / "note.md").write_bytes(b"source two\n")
    before = user_state(vault, owned_ref=first.ref)
    second = capture(
        operations,
        vault,
        source,
        vault_id="stable-vault",
        import_id="stable-import",
        identity=identity,
        admission=observed,
    )
    assert second.status == "captured" and second.commit != first.commit
    assert git(vault, "rev-parse", second.commit + "^").decode().strip() == first.commit
    checkpoint = read_history(operations, vault)
    assert checkpoint.locator.association.import_id == "stable-import"
    assert checkpoint.manifest.generation == 2
    assert user_state(vault, owned_ref=first.ref) == before


def test_payload_larger_than_control_budget_is_raw_and_validated_from_owned_graph():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
        binary_context,
    )
    from tests.reconciliation.test_resolution import action, preflight

    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "Assets").mkdir()
    (source / "Assets").mkdir()
    current = ExactContent(data=b"\x00\xff\x80" * 6000000)
    incoming = ExactContent(data=b"\x00\xff\x80" * 5999999 + b"\x00\xff\x81")
    (vault / "Assets/data.bin").write_bytes(current.data)
    (source / "Assets/data.bin").write_bytes(incoming.data)
    facts = attachment_request()
    subject = facts.subjects[0].model_copy(
        update={
            "incoming": incoming,
            "current": facts.subjects[0].current.model_copy(
                update={"content": current}
            ),
        }
    )
    facts = facts.model_copy(
        update={
            "subjects": (subject,),
            "identity_inventory": (
                facts.identity_inventory[0].model_copy(
                    update={"current": subject.current}
                ),
            ),
            "link_context": None,
        }
    )
    facts = facts.model_copy(update={"link_context": binary_context(facts)})
    plan = prepare_review(facts, preflight=preflight())
    selection, candidate = attachment_candidate(facts, "current")
    accepted = resolve_review(
        plan,
        action(
            plan,
            domain="attachment",
            choice="current",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert accepted.status == "accepted" and accepted.plan.ready
    operations = Operations()
    result = capture(
        operations,
        vault,
        source,
        vault_id="binary-vault",
        import_id="binary-import",
        identity=facts.incoming_identity,
        admission=inspect(operations, vault),
        review=accepted.plan,
    )
    assert result.status == "captured"
    checkpoint = read_history(operations, vault)
    assert checkpoint.status == "valid"
    assert checkpoint.manifest.source[0].size == 18000000
    assert (
        checkpoint.manifest.vault[0].sha256
        == "b743ea3aa0502f706974c9129174e86dad5855c85ac3188bc09f3c89048976f7"
    )
    assert (
        checkpoint.manifest.source[0].object_id
        != checkpoint.manifest.vault[0].object_id
    )
    assert checkpoint.review.ready is False
    assert checkpoint.review.saved.plan == accepted.plan
    assert (
        checkpoint.review.saved.plan.approvals[0].source_memory.reviewed_incoming.data
        == incoming.data
    )
    assert int(git(vault, "cat-file", "-s", result.commit + ":review.json")) < 1_000_000


def test_saved_s1_keep_memory_is_real_reachable_history_and_load_is_unready():
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import prepare_review, resolve_review, resume_review
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import (
        action,
        preflight,
        with_review_links,
    )

    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "Notes").mkdir()
    (source / "Notes").mkdir()
    (vault / "Notes/Opening.md").write_bytes(b"authored")
    (source / "Notes/Opening.md").write_bytes(b"source-v2")
    facts = with_review_links(
        request(original=b"source-v1", current=b"authored", incoming=b"source-v2")
    )
    initial = prepare_review(facts, preflight=preflight())
    reviewed = resolve_review(initial, action(initial, choice="current")).plan
    assert reviewed.ready
    operations = Operations()
    result = capture(
        operations,
        vault,
        source,
        vault_id="memory-vault",
        import_id="memory-import",
        identity=facts.incoming_identity,
        admission=inspect(operations, vault),
        review=reviewed,
    )
    assert result.status == "captured"
    reopened = read_history(operations, vault)
    assert reopened.status == "valid"
    assert reopened.review.ready is False
    assert reopened.review.saved.plan == reviewed
    memory = reopened.review.saved.plan.approvals[0].source_memory
    assert memory.reviewed_incoming.data == b"source-v2"
    assert memory.choice == "keep_vault"
    shape = json.loads(git(vault, "cat-file", "blob", result.commit + ":review.json"))
    assert shape["schema_id"] == "brz2obsidian.saved-review-refs"
    baseline_sha = hashlib.sha256(b"source-v1").hexdigest()
    assert (
        git(
            vault, "cat-file", "blob", result.commit + ":review-content/" + baseline_sha
        )
        == b"source-v1"
    )
    assert [row.path for row in reopened.manifest.review_content] == [baseline_sha]
    changed = with_review_links(
        facts.model_copy(
            update={
                "generation": 2,
                "link_context": None,
                "source_version_memory": (memory,),
                "subjects": (
                    facts.subjects[0].model_copy(
                        update={"incoming": ExactContent(data=b"source-v3")}
                    ),
                ),
            }
        )
    )
    resumed = resume_review(
        reopened.review, changed, preflight=inspect(operations, vault).preflight
    )
    assert resumed.status == "resumed"
    assert not resumed.ready
    assert resumed.plan.approvals == ()
    # The current operation attestation observes the newly retained checkpoint.
    # Its proof token changes while status, scope, bytes and choice stay fixed.
    attested = facts.safety_facts[-1].model_copy(
        update={"fingerprint": "observed:" + result.commit}
    )
    equivalent_facts = facts.model_copy(
        update={
            "proposal_id": "different-run",
            "generation": 2,
            "safety_facts": facts.safety_facts[:-1] + (attested,),
        }
    )
    fresh = prepare_review(
        equivalent_facts,
        preflight=operations.inspect_history(vault).admission.preflight,
    )
    equivalent = resolve_review(
        fresh, action(fresh, decision_id="fresh-keep", choice="current")
    ).plan
    assert equivalent.ready
    repeated = capture(
        operations,
        vault,
        source,
        vault_id="memory-vault",
        import_id="memory-import",
        identity=facts.incoming_identity,
        admission=inspect(operations, vault),
        review=equivalent,
    )
    assert repeated.status == "unchanged" and repeated.commit == result.commit
    assert git(vault, "rev-list", "--count", result.ref) == b"1\n"
    from brz2obsidian.contracts import ImportedItemIdentity
    from brz2obsidian.obsidian import inspect_text_candidate

    candidate = inspect_text_candidate(
        facts.subjects[0].incoming,
        identity=ImportedItemIdentity(
            collection_id=facts.incoming_identity.collection_id,
            module_id=facts.incoming_identity.module_id,
            item_id=facts.subjects[0].item_id,
        ),
        target=facts.subjects[0].source_target,
        output_format=7,
        source_path="Notes/Opening.md",
        document_id="review:owner",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    selected_source = resolve_review(
        fresh,
        action(
            fresh,
            decision_id="accept-source-now",
            choice="incoming",
            candidate=candidate,
        ),
    )
    assert selected_source.status == "accepted", selected_source.code
    changed_memory = selected_source.plan
    assert changed_memory.approvals[0].source_memory is None
    distinct = capture(
        operations,
        vault,
        source,
        vault_id="memory-vault",
        import_id="memory-import",
        identity=facts.incoming_identity,
        admission=inspect(operations, vault),
        review=changed_memory,
    )
    assert distinct.status == "captured" and distinct.commit != result.commit
    assert read_history(operations, vault).review.saved.plan == changed_memory
    assert (vault / "Notes/Opening.md").read_bytes() == b"authored"


def test_capture_refuses_new_active_configured_hook_and_keeps_disabled_hook_inactive():
    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "note.md").write_bytes(b"vault\n")
    (source / "note.md").write_bytes(b"source\n")
    program, marker = vault.parent / "hook.py", vault.parent / "hook.marker"
    program.write_text(
        "from pathlib import Path\nPath("
        + repr(str(marker))
        + ").write_bytes(b'ran')\n",
        encoding="utf-8",
    )
    subprocess.run([sys.executable, str(program)], check=True)
    assert marker.read_bytes() == b"ran"
    marker.unlink()
    operations = Operations()
    observed = inspect(operations, vault)
    command = (
        '"'
        + sys.executable.replace("\\", "/")
        + '" "'
        + str(program).replace("\\", "/")
        + '"'
    )
    git(vault, "config", "hook.Capture.command", command)
    git(vault, "config", "hook.Capture.event", "reference-transaction")
    git(vault, "hook", "run", "reference-transaction", "--", "committed")
    assert marker.read_bytes() == b"ran"
    marker.unlink()
    identity = {
        "collection_id": "collection-one",
        "module_id": "fixture",
        "module_version": "1",
        "profile_id": "profile",
        "profile_version": "1",
        "output_format": 7,
        "settings_digest": "literal-settings",
    }
    before = (vault / ".git/config").read_bytes()
    refused = capture(
        operations,
        vault,
        source,
        vault_id="hook-vault",
        import_id="hook-import",
        identity=identity,
        admission=observed,
    )
    assert refused.status == "refused" and not refused.history_retained
    assert not marker.exists()
    assert (vault / ".git/config").read_bytes() == before
    assert git(vault, "for-each-ref", "refs/brz2obsidian") == b""
    git(vault, "config", "hook.Capture.enabled", "false")
    before = (vault / ".git/config").read_bytes()
    captured = capture(
        operations,
        vault,
        source,
        vault_id="hook-vault",
        import_id="hook-import",
        identity=identity,
        admission=inspect(operations, vault),
    )
    assert captured.status == "captured"
    assert not marker.exists()
    assert (vault / ".git/config").read_bytes() == before


def test_reviewed_initialization_rediscovery_cannot_capture_newly_applicable_policy(
    monkeypatch,
):
    vault, source = fixture_case()
    (vault / "note.md").write_bytes(b"user bytes\r\n")
    (source / "note.md").write_bytes(b"converted\n")
    global_config = vault.parent / "global-config"
    included = vault.parent / "conditional-config"
    included.write_text(
        '[core]\n autocrlf = true\n[filter "secret"]\n clean = missing-program\n',
        encoding="utf-8",
    )
    global_config.write_text(
        '[includeIf "gitdir/i:'
        + str(vault / ".git").replace("\\", "/")
        + '"]\n path = '
        + str(included).replace("\\", "/")
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    operations = Operations()
    before = inspect(operations, vault)
    assert (
        before.status == "supported" and before.policy_scope == "before_initialization"
    )
    decision = {
        "schema_id": "brz2obsidian.vault-initialization-decision",
        "schema_version": 1,
        "observation_fingerprint": before.observation_fingerprint,
        "choice": "initialize",
    }
    initialized = operations.initialize_vault(vault, decision=decision)
    assert initialized.status == "initialized_review_required"
    assert initialized.repository_created is True
    assert initialized.history_retained is False
    assert initialized.admission.policy_scope == "current_repository"
    assert initialized.admission.policy_fingerprint != before.policy_fingerprint
    assert initialized.admission.preflight.consents[0].kind == "storage"
    assert not (vault / ".brz2obsidian").exists()
    assert (vault / "note.md").read_bytes() == b"user bytes\r\n"
    assert git(vault, "for-each-ref") == b""


def test_invalid_initialization_decisions_cannot_claim_preexisting_repository_creation():
    vault, _ = fixture_case()
    git(vault, "init", "-q")
    (vault / "authored.md").write_bytes(b"existing authored bytes\r\n")
    git(vault, "add", "--", "authored.md")
    operations = Operations()
    observed = inspect(operations, vault)
    assert observed.repository.kind == "root"
    before = user_state(vault)
    for decision in (
        {"schema_id": "future-decision", "schema_version": 2},
        {"schema_id": "brz2obsidian.vault-initialization-decision"},
    ):
        result = operations.initialize_vault(vault, decision=decision)
        assert result.status == "failed"
        assert result.repository_created is False
        assert result.history_retained is False
        assert user_state(vault) == before
        assert not (vault / ".brz2obsidian").exists()


def test_failed_init_after_actual_repository_creation_reports_partial_change(
    monkeypatch,
):
    import brz2obsidian.publication.vault_history as history

    vault, _ = fixture_case()
    (vault / "authored.md").write_bytes(b"existing authored bytes\r\n")
    operations = Operations()
    before = inspect(operations, vault)
    assert before.status == "supported" and before.repository.kind == "none"
    original_call = history._Git.call

    def fail_after_init(git, *args, **kwargs):
        value = original_call(git, *args, **kwargs)
        if args[0] == "init":
            raise OSError("Init response was lost after the repository was created")
        return value

    monkeypatch.setattr(history._Git, "call", fail_after_init)
    result = operations.initialize_vault(
        vault,
        decision={
            "schema_id": "brz2obsidian.vault-initialization-decision",
            "schema_version": 1,
            "observation_fingerprint": before.observation_fingerprint,
            "choice": "initialize",
        },
    )
    assert result.status == "failed" and result.repository_created is True
    assert result.admission.repository.kind == "root"
    assert (vault / "authored.md").read_bytes() == b"existing authored bytes\r\n"
    assert git(vault, "for-each-ref") == b""
    assert not (vault / ".brz2obsidian").exists()


def test_actual_s1_storage_and_inclusion_choices_bind_raw_capture_and_decline_stops():
    from brz2obsidian.application.vault_contracts import VaultSubject
    from brz2obsidian.contracts import ContentVersion, reconciliation_subject_id
    from brz2obsidian.core import prepare_review, resolve_review
    from tests.reconciliation.test_formats import operation
    from tests.reconciliation.test_proposals import request
    from tests.reconciliation.test_resolution import action, with_review_links

    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Notes").mkdir()
    (source / "Notes").mkdir()
    (vault / "Notes/Opening.md").write_bytes(b"$Id$\r\nauthored\n")
    (source / "Notes/Opening.md").write_bytes(b"$Id$\r\nsource\n")
    (vault / ".gitattributes").write_bytes(b"*.md text eol=lf ident\n")
    (vault / ".gitignore").write_bytes(b"Notes/Opening.md\nunrelated.md\n")
    (vault / "unrelated.md").write_bytes(b"untracked recovery gap\n")
    facts = request(
        original=b"old", current=b"$Id$\r\nauthored\n", incoming=b"$Id$\r\nsource\n"
    )
    # Onboarding reviews the same supplied converted-source version on both
    # sides of its format choice; original historical bytes remain unknown.
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(
                        update={
                            "baseline": ContentVersion(
                                status="unknown", content=None, unavailable_digest=None
                            )
                        }
                    ),
                ),
                "format_operation": operation(
                    "onboarding",
                    recorded_generation="unavailable",
                    established_baseline=None,
                ),
            }
        )
    )
    identity = facts.incoming_identity
    subject_id = reconciliation_subject_id(
        identity.module_id,
        identity.collection_id,
        facts.subjects[0].item_id,
        facts.subjects[0].facet,
    )
    subjects = (VaultSubject(path="Notes/Opening.md", subject_id=subject_id),)
    operations = Operations()
    observed = operations.inspect_history(vault, subjects=subjects).admission
    assert observed.preflight.state_status == "absent"
    assert [requirement.kind for requirement in observed.preflight.consents] == [
        "storage",
        "tracking",
    ]
    plan = prepare_review(facts, preflight=observed.preflight)
    storage_requirement = next(r for r in plan.requirements if r.domain == "storage")
    declined = resolve_review(
        plan,
        action(
            plan,
            domain="storage",
            choice="decline",
            change_id=storage_requirement.change_id,
            reviewed_assumptions=storage_requirement.assumptions,
        ),
    ).plan
    refused = capture(
        operations,
        vault,
        source,
        vault_id="choices-vault",
        import_id="choices-import",
        identity=identity,
        admission=observed,
        subjects=subjects,
        review=declined,
    )
    assert refused.status == "refused" and not refused.objects_written
    assert git(vault, "for-each-ref", "refs/brz2obsidian/imports") == b""
    onboarding = resolve_review(
        plan,
        action(
            plan, decision_id="reviewed:onboarding", domain="format", choice="current"
        ),
    )
    assert onboarding.status == "accepted", (
        onboarding.code,
        plan.blockers,
        [(r.domain, r.choices) for r in plan.requirements],
    )
    plan = onboarding.plan
    for domain in ("storage", "tracking"):
        requirement = next(r for r in plan.requirements if r.domain == domain)
        transition = resolve_review(
            plan,
            action(
                plan,
                decision_id="accept:" + domain,
                domain=domain,
                choice="accept",
                change_id=requirement.change_id,
                reviewed_assumptions=requirement.assumptions,
            ),
        )
        assert transition.status == "accepted"
        plan = transition.plan
    before_config = (vault / ".git/config").read_bytes()
    proposed = vault.parent / "proposed"
    (proposed / "Notes").mkdir(parents=True)
    for path in (".gitattributes", ".gitignore"):
        (proposed / path).write_bytes((vault / path).read_bytes())
    (proposed / "Notes/Opening.md").write_bytes(b"$Id$\r\nsource\n")
    captured = capture(
        operations,
        vault,
        source,
        vault_id="choices-vault",
        import_id="choices-import",
        identity=identity,
        admission=observed,
        subjects=subjects,
        review=plan,
        boundary="prepared",
        proposed=proposed,
    )
    assert captured.status == "captured"
    reopened = read_history(operations, vault)
    assert reopened.status == "valid"
    assert reopened.manifest.recovery_gaps == ("unrelated.md",)
    assert (
        git(vault, "cat-file", "blob", captured.commit + ":vault/Notes/Opening.md")
        == b"$Id$\r\nauthored\n"
    )
    assert (
        git(vault, "cat-file", "blob", captured.commit + ":source/Notes/Opening.md")
        == b"$Id$\r\nsource\n"
    )
    assert (vault / ".git/config").read_bytes() == before_config
    assert not (vault / ".git/index").exists()
    repeated = capture(
        operations,
        vault,
        source,
        vault_id="choices-vault",
        import_id="choices-import",
        identity=identity,
        admission=operations.inspect_history(vault, subjects=subjects).admission,
        subjects=subjects,
        review=plan,
        boundary="prepared",
        proposed=proposed,
    )
    assert repeated.status == "unchanged" and repeated.commit == captured.commit
    current = operations.inspect_history(vault, subjects=subjects).admission
    refreshed_facts = facts.model_copy(
        update={"proposal_id": "another-observation", "generation": 2}
    )
    refreshed = prepare_review(refreshed_facts, preflight=current.preflight)
    for domain, choice in (
        ("format", "current"),
        ("storage", "accept"),
        ("tracking", "accept"),
    ):
        requirement = next(r for r in refreshed.requirements if r.domain == domain)
        transition = resolve_review(
            refreshed,
            action(
                refreshed,
                decision_id="fresh:" + domain,
                domain=domain,
                choice=choice,
                change_id=requirement.change_id,
                reviewed_assumptions=requirement.assumptions,
            ),
        )
        assert transition.status == "accepted", transition.code
        refreshed = transition.plan
    equivalent = capture(
        operations,
        vault,
        source,
        vault_id="choices-vault",
        import_id="choices-import",
        identity=identity,
        admission=current,
        subjects=subjects,
        review=refreshed,
        boundary="prepared",
        proposed=proposed,
    )
    assert equivalent.status == "unchanged" and equivalent.commit == captured.commit
    (vault / "Notes/Opening.md").write_bytes(b"$Id$\r\nsource\n")
    actual = capture(
        operations,
        vault,
        source,
        vault_id="choices-vault",
        import_id="choices-import",
        identity=identity,
        admission=operations.inspect_history(vault, subjects=subjects).admission,
        subjects=subjects,
        boundary="result",
        expected_prepared=captured.commit,
    )
    assert actual.status == "captured", actual.code
    completed = read_history(operations, vault)
    assert completed.manifest.boundary == "result"
    assert completed.review.ready is False
    assert completed.review.saved == reopened.review.saved
    assert (
        git(vault, "cat-file", "blob", actual.commit + ":preimage/Notes/Opening.md")
        == b"$Id$\r\nauthored\n"
    )
    assert (
        git(vault, "cat-file", "blob", actual.commit + ":vault/Notes/Opening.md")
        == b"$Id$\r\nsource\n"
    )
    assert (vault / ".git/config").read_bytes() == before_config


def test_prepared_roots_precede_intent_and_actual_result_requires_complete_matching_inventory():
    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "note.md").write_bytes(b"before\n")
    (vault / "unrelated.bin").write_bytes(b"\x00unrelated")
    (source / "note.md").write_bytes(b"incoming\n")
    proposed = vault.parent / "proposed"
    proposed.mkdir()
    (proposed / "note.md").write_bytes(b"after\n")
    (proposed / "unrelated.bin").write_bytes(b"\x00unrelated")
    operations = Operations()
    identity = {
        "collection_id": "collection-one",
        "module_id": "fixture",
        "module_version": "1",
        "profile_id": "profile",
        "profile_version": "1",
        "output_format": 7,
        "settings_digest": "literal-settings",
    }
    prepared = capture(
        operations,
        vault,
        source,
        vault_id="prepared-vault",
        import_id="prepared-import",
        identity=identity,
        admission=inspect(operations, vault),
        boundary="prepared",
        proposed=proposed,
    )
    assert prepared.status == "captured"
    assert not (vault / ".brz2obsidian/intent.json").exists()
    assert (
        git(vault, "cat-file", "blob", prepared.commit + ":source/note.md")
        == b"incoming\n"
    )
    assert (
        git(vault, "cat-file", "blob", prepared.commit + ":preimage/note.md")
        == b"before\n"
    )
    assert (
        git(vault, "cat-file", "blob", prepared.commit + ":proposed/note.md")
        == b"after\n"
    )
    refused = capture(
        operations,
        vault,
        source,
        vault_id="prepared-vault",
        import_id="prepared-import",
        identity=identity,
        admission=inspect(operations, vault),
        boundary="result",
        expected_prepared=prepared.commit,
    )
    assert refused.status == "refused" and refused.code == "result_inventory_mismatch"
    assert git(vault, "rev-parse", prepared.ref).decode().strip() == prepared.commit
    (vault / "note.md").write_bytes(b"after\n")
    actual = capture(
        operations,
        vault,
        source,
        vault_id="prepared-vault",
        import_id="prepared-import",
        identity=identity,
        admission=inspect(operations, vault),
        boundary="result",
        expected_prepared=prepared.commit,
    )
    assert actual.status == "captured"
    reopened = read_history(operations, vault)
    assert reopened.manifest.boundary == "result"
    assert [(f.path, f.mode, f.size) for f in reopened.manifest.vault] == [
        ("note.md", "100644", 6),
        ("unrelated.bin", "100644", 10),
    ]
    assert (
        git(vault, "cat-file", "blob", actual.commit + ":vault/note.md") == b"after\n"
    )
    assert (
        git(vault, "cat-file", "blob", actual.commit + ":preimage/note.md")
        == b"before\n"
    )


def test_selected_new_path_can_be_retained_after_unchanged_rules_and_complete_result():
    from brz2obsidian.application.vault_contracts import VaultSubject

    vault, source = fixture_case()
    git(vault, "init", "-q")
    (source / "new.md").write_bytes(b"incoming\n")
    proposed = vault.parent / "proposed"
    proposed.mkdir()
    (proposed / "new.md").write_bytes(b"incoming\n")
    selected = (VaultSubject(path="new.md", subject_id="literal:selected-new"),)
    operations = Operations()
    identity = {
        "collection_id": "collection-one",
        "module_id": "fixture",
        "module_version": "1",
        "profile_id": "profile",
        "profile_version": "1",
        "output_format": 7,
        "settings_digest": "literal-settings",
    }
    before = operations.inspect_history(vault, subjects=selected).admission
    prepared = capture(
        operations,
        vault,
        source,
        vault_id="new-vault",
        import_id="new-import",
        identity=identity,
        admission=before,
        subjects=selected,
        boundary="prepared",
        proposed=proposed,
    )
    assert prepared.status == "captured"
    assert read_history(operations, vault).manifest.vault == ()
    (vault / "new.md").write_bytes(b"incoming\n")
    current = operations.inspect_history(vault, subjects=selected).admission
    assert current.policy_fingerprint != before.policy_fingerprint
    result = capture(
        operations,
        vault,
        source,
        vault_id="new-vault",
        import_id="new-import",
        identity=identity,
        admission=current,
        subjects=selected,
        boundary="result",
        expected_prepared=prepared.commit,
    )
    assert result.status == "captured", result.code
    assert (
        git(vault, "cat-file", "blob", result.commit + ":vault/new.md") == b"incoming\n"
    )
    assert read_history(operations, vault).manifest.preimage == ()


def test_selected_missing_ignored_path_retains_reviewed_inclusion_after_result_creation():
    from brz2obsidian.application.vault_contracts import VaultSubject
    from brz2obsidian.contracts import (
        ContentVersion,
        ExactContent,
        ImportedItemIdentity,
        reconciliation_subject_id,
    )
    from brz2obsidian.core import prepare_review, resolve_review
    from brz2obsidian.obsidian import inspect_text_candidate
    from tests.reconciliation.test_absence import facts_for
    from tests.reconciliation.test_formats import operation
    from tests.reconciliation.test_resolution import action, with_review_links

    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / ".gitignore").write_bytes(b"Notes/Opening.md\n")
    (source / "Notes").mkdir()
    (source / "Notes/Opening.md").write_bytes(b"incoming\n")
    proposed = vault.parent / "proposed"
    (proposed / "Notes").mkdir(parents=True)
    (proposed / ".gitignore").write_bytes(b"Notes/Opening.md\n")
    (proposed / "Notes/Opening.md").write_bytes(b"incoming\n")
    facts = facts_for(existence="absent", original=b"old", incoming=b"incoming\n")
    subject = facts.subjects[0].model_copy(
        update={
            "baseline": ContentVersion(
                status="unknown", content=None, unavailable_digest=None
            )
        }
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (subject,),
                "identity_inventory": (
                    facts.identity_inventory[0].model_copy(
                        update={"current": subject.current}
                    ),
                ),
                "format_operation": operation(
                    "onboarding",
                    recorded_generation="unavailable",
                    established_baseline=None,
                ),
            }
        )
    )
    selected = (
        VaultSubject(
            path=subject.path,
            subject_id=reconciliation_subject_id(
                facts.incoming_identity.module_id,
                facts.incoming_identity.collection_id,
                subject.item_id,
                subject.facet,
            ),
        ),
    )
    operations = Operations()
    admission = operations.inspect_history(vault, subjects=selected).admission
    assert [r.kind for r in admission.preflight.consents] == ["tracking"]
    plan = prepare_review(facts, preflight=admission.preflight)
    candidate = inspect_text_candidate(
        ExactContent(data=b"incoming\n"),
        identity=ImportedItemIdentity(
            collection_id=facts.incoming_identity.collection_id,
            module_id=facts.incoming_identity.module_id,
            item_id=subject.item_id,
        ),
        target=subject.source_target,
        output_format=7,
        source_path=subject.path,
        document_id="review:owner",
        path_mode="vault",
        link_targets=(),
        link_target_facts=(),
        link_inventory="complete",
    )
    reviewed = resolve_review(
        plan, action(plan, domain="format", choice="incoming", candidate=candidate)
    ).plan
    requirement = next(r for r in reviewed.requirements if r.domain == "tracking")
    reviewed = resolve_review(
        reviewed,
        action(
            reviewed,
            domain="tracking",
            choice="accept",
            decision_id="tracking:accept",
            change_id=requirement.change_id,
            reviewed_assumptions=requirement.assumptions,
        ),
    ).plan
    assert reviewed.ready
    prepared = capture(
        operations,
        vault,
        source,
        vault_id="ignored-vault",
        import_id="ignored-import",
        identity=facts.incoming_identity,
        admission=admission,
        subjects=selected,
        review=reviewed,
        boundary="prepared",
        proposed=proposed,
    )
    assert prepared.status == "captured", prepared.code
    before = read_history(operations, vault)
    assert before.manifest.vault[0].path == ".gitignore"
    assert before.manifest.proposed[-1].path == "Notes/Opening.md"
    (vault / "Notes").mkdir()
    (vault / "Notes/Opening.md").write_bytes(b"incoming\n")
    current = operations.inspect_history(vault, subjects=selected).admission
    assert current.policy_fingerprint != admission.policy_fingerprint
    assert (
        current.policy_continuity_fingerprint == admission.policy_continuity_fingerprint
    )
    result = capture(
        operations,
        vault,
        source,
        vault_id="ignored-vault",
        import_id="ignored-import",
        identity=facts.incoming_identity,
        admission=current,
        subjects=selected,
        boundary="result",
        expected_prepared=prepared.commit,
    )
    assert result.status == "captured", result.code
    after = read_history(operations, vault)
    assert after.review.ready is False and after.review.saved.plan == reviewed
    assert (
        git(vault, "cat-file", "blob", result.commit + ":vault/Notes/Opening.md")
        == b"incoming\n"
    )
    assert [row.path for row in after.manifest.preimage] == [".gitignore"]


@pytest.mark.parametrize("fault", ("objects", "ref", "locator"))
def test_actual_partial_history_failures_report_retained_objects_and_roots_truthfully(
    fault,
):
    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "note.md").write_bytes(b"vault-before\n")
    (source / "note.md").write_bytes(b"converted-before\n")
    program = vault.parent / "locator-block.py"
    program.write_text(
        "from pathlib import Path\np=Path("
        + repr(str(vault / ".brz2obsidian"))
        + ")\np.mkdir(exist_ok=True)\n(p/'locator.pending').mkdir()\n",
        encoding="utf-8",
    )
    wrapper = vault.parent / "git-failure.cmd"
    actual_git = shutil.which("git")
    wrapper.write_text(
        '@echo off\nset localMode=\n:scan\nif "%~1"=="" goto run\nif "%~1"=="--stdin-paths" set localMode=objects\nif "%~1"=="update-ref" set localMode=ref\nshift\ngoto scan\n:run\n"'
        + actual_git
        + '" %*\nif errorlevel 1 exit /b %errorlevel%\nif "%localMode%"=="'
        + fault
        + '" exit /b 17\n'
        + (
            'if "%localMode%"=="ref" "' + sys.executable + '" "' + str(program) + '"\n'
            if fault == "locator"
            else ""
        )
        + "exit /b 0\n",
        encoding="utf-8",
    )
    operations = Operations()
    identity = {
        "collection_id": "collection-one",
        "module_id": "fixture",
        "module_version": "1",
        "profile_id": "profile",
        "profile_version": "1",
        "output_format": 7,
        "settings_digest": "literal-settings",
    }
    observed = inspect(operations, vault, git_executable=wrapper)
    assert observed.status == "supported"
    head = (vault / ".git/HEAD").read_bytes()
    config = (vault / ".git/config").read_bytes()
    result = capture(
        operations,
        vault,
        source,
        vault_id="failure-vault",
        import_id="failure-import",
        identity=identity,
        admission=observed,
        git_executable=wrapper,
    )
    assert result.status == "failed"
    assert result.objects_written is True
    assert result.authored_files_changed is False
    assert (vault / "note.md").read_bytes() == b"vault-before\n"
    assert (source / "note.md").read_bytes() == b"converted-before\n"
    assert (vault / ".git/HEAD").read_bytes() == head
    assert (vault / ".git/config").read_bytes() == config
    assert not (vault / ".git/index").exists()
    actual_blob = (
        git(
            vault, "hash-object", "--no-filters", "--stdin", input=b"converted-before\n"
        )
        .decode()
        .strip()
    )
    assert git(vault, "cat-file", "blob", actual_blob) == b"converted-before\n"
    if fault == "objects":
        assert result.object_storage == "verified"
        assert not result.history_retained
        assert git(vault, "for-each-ref", "refs/brz2obsidian/imports") == b""
    else:
        assert result.history_retained is True
        assert git(vault, "rev-parse", result.ref).decode().strip() == result.commit
        assert (
            git(vault, "cat-file", "blob", result.commit + ":source/note.md")
            == b"converted-before\n"
        )
        assert not (vault / ".brz2obsidian/locator.json").exists()
        assert operations.inspect_history(vault).status == "unavailable"


def test_locator_flush_failure_reports_published_ref_and_recovery_gap(monkeypatch):
    import brz2obsidian.publication.vault_history as history

    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "note.md").write_bytes(b"authored\n")
    (source / "note.md").write_bytes(b"converted\n")
    operations = Operations()
    admission = inspect(operations, vault)
    before = (
        (vault / "note.md").read_bytes(),
        (source / "note.md").read_bytes(),
        (vault / ".git/HEAD").read_bytes(),
        (vault / ".git/config").read_bytes(),
    )

    def refused_flush(_):
        raise OSError("controlled locator flush fault")

    monkeypatch.setattr(history.os, "fsync", refused_flush)
    result = capture(
        operations,
        vault,
        source,
        vault_id="flush-vault",
        import_id="flush-import",
        identity={
            "collection_id": "flush-collection",
            "module_id": "fixture",
            "module_version": "1",
            "profile_id": "profile",
            "profile_version": "1",
            "output_format": 7,
            "settings_digest": "literal-settings",
        },
        admission=admission,
    )
    assert result.status == "failed" and result.code == "capture_unavailable"
    assert result.objects_written and result.object_storage == "verified"
    assert result.history_retained is True and result.commit is not None
    assert git(vault, "rev-parse", result.ref).decode().strip() == result.commit
    assert (vault / ".brz2obsidian/locator.pending").exists()
    assert not (vault / ".brz2obsidian/locator.json").exists()
    assert before == (
        (vault / "note.md").read_bytes(),
        (source / "note.md").read_bytes(),
        (vault / ".git/HEAD").read_bytes(),
        (vault / ".git/config").read_bytes(),
    )
    assert read_history(operations, vault).status == "refused"


def test_public_checkpoint_refuses_malformed_raw_git_batch_after_real_object_write():
    vault, source = fixture_case()
    git(vault, "init", "-q")
    (vault / "note.md").write_bytes(b"authored\r\n")
    (source / "note.md").write_bytes(b"source\x00\xff\n")
    marker = vault.parent / "raw-written.marker"
    malformed = vault.parent / "malformed-batch.py"
    malformed.write_text(
        "import sys\nsys.stdin.buffer.read()\nsys.stdout.buffer.write(b'not-a-git-blob 0\\n')\nsys.stdout.buffer.flush()\n",
        encoding="utf-8",
    )
    wrapper = vault.parent / "malformed-git.cmd"
    wrapper.write_text(
        '@echo off\r\nset "mode="\r\n:scan\r\nif "%~1"=="" goto run\r\n'
        'if "%~1"=="--stdin-paths" set "mode=objects"\r\n'
        'if "%~1"=="cat-file" set "mode=cat"\r\nshift\r\ngoto scan\r\n'
        ':run\r\nif "%mode%"=="cat" if exist "' + str(marker) + '" goto corrupt\r\n'
        '"' + shutil.which("git") + '" %*\r\nif errorlevel 1 exit /b %errorlevel%\r\n'
        'if "%mode%"=="objects" type nul > "' + str(marker) + '"\r\nexit /b 0\r\n'
        ':corrupt\r\n"'
        + sys.executable
        + '" "'
        + str(malformed)
        + '"\r\nexit /b %errorlevel%\r\n',
        encoding="utf-8",
    )
    operations = Operations()
    observed = inspect(operations, vault, git_executable=wrapper)
    assert observed.status == "supported" and not marker.exists()
    before = (
        (vault / "note.md").read_bytes(),
        (source / "note.md").read_bytes(),
        (vault / ".git/HEAD").read_bytes(),
        (vault / ".git/config").read_bytes(),
    )
    result = capture(
        operations,
        vault,
        source,
        vault_id="protocol-vault",
        import_id="protocol-import",
        identity={
            "collection_id": "protocol-collection",
            "module_id": "fixture",
            "module_version": "1",
            "profile_id": "profile",
            "profile_version": "1",
            "output_format": 7,
            "settings_digest": "literal-settings",
        },
        admission=observed,
        git_executable=wrapper,
    )
    assert marker.exists()
    assert result.status == "failed" and result.code == "capture_unavailable"
    assert result.object_storage == "possible" and not result.objects_written
    oid = (
        git(vault, "hash-object", "--no-filters", "--stdin", input=b"source\x00\xff\n")
        .decode()
        .strip()
    )
    assert git(vault, "cat-file", "blob", oid) == b"source\x00\xff\n"
    assert git(vault, "for-each-ref", "refs/brz2obsidian/imports") == b""
    assert not (vault / ".brz2obsidian").exists()
    assert before == (
        (vault / "note.md").read_bytes(),
        (source / "note.md").read_bytes(),
        (vault / ".git/HEAD").read_bytes(),
        (vault / ".git/config").read_bytes(),
    )
