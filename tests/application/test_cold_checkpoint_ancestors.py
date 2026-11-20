"""Cold ancestor admission through the public owned-history operations."""

import hashlib
import json
import tempfile

import brz2obsidian.publication.vault_history as history
from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ExactContent
from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
from tests.application.test_vault_checkpoints import fixture_case, git, user_state
from tests.reconciliation.legacy_content_builder import retarget_checkpoint
from tests.reconciliation.test_attachments import (
    attachment_candidate,
    attachment_request,
    binary_context,
)
from tests.reconciliation.test_identity import with_subjects
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def test_nonreturned_binary_ancestor_loads_with_capacity_for_tip_and_metadata(
    monkeypatch,
):
    operations = Operations()
    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    for parent in (vault, source):
        (parent / "Assets").mkdir()
    current = b"\x00authored"
    incoming = b"abc"
    tip_source = b"\x00tiny-tip\xff\n"
    (vault / "Assets/data.bin").write_bytes(current)
    (source / "Assets/data.bin").write_bytes(incoming)
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "Independent authored baseline")

    def capture_ancestor():
        original = b"\x00" * (16 * 1024 * 1024)
        original_sha = hashlib.sha256(original).hexdigest()
        facts = attachment_request()
        subject = facts.subjects[0].model_copy(
            update={
                "baseline": facts.subjects[0].baseline.model_copy(
                    update={"content": ExactContent(data=original)}
                ),
            }
        )
        # Attachment semantics, not a note containing binary bytes: the owned
        # decoder must leave this baseline opaque rather than promoting it to T.
        assert subject.attachment is not None
        assert subject.facet == "attachment:payload"
        assert subject.path == "Assets/data.bin"
        assert subject.current.content.data == current
        assert subject.incoming.data == incoming
        facts = with_subjects(facts, (subject,), facts.identity_inventory)
        facts = facts.model_copy(update={"link_context": binary_context(facts)})
        assert facts.link_context.current_targets[0].kind == "resource"
        initial = prepare_review(facts, preflight=preflight())
        assert initial.proposal.changes[0].disposition == "unresolved"
        assert initial.proposal.changes[0].format_review is None
        assert initial.proposal.changes[0].attachment_review is not None
        selection, candidate = attachment_candidate(facts, "current")
        chosen = resolve_review(
            initial,
            action(
                initial,
                domain="attachment",
                choice="current",
                decision_id="ancestor:keep-current",
                attachment_selection=selection,
                attachment_candidate=candidate,
            ),
        )
        assert chosen.status == "accepted" and chosen.plan.ready, (
            chosen.status,
            chosen.code,
            chosen.plan.blockers if chosen.plan is not None else None,
        )
        assert chosen.plan.approvals[0].decision_id == "ancestor:keep-current"
        assert not chosen.plan.approvals[0].source_accepted
        effects = select_review_effects(chosen.plan)
        assert effects.status == "selected" and effects.remove_paths == ()
        assert [(row.path, row.content.data) for row in effects.files] == [
            ("Assets/data.bin", current)
        ]
        captured = operations.capture_checkpoint(
            vault,
            source,
            vault_id="cold-ancestor-vault",
            import_id="cold-ancestor-import",
            identity=facts.incoming_identity,
            admission=operations.inspect_vault(vault),
            review=chosen.plan,
        )
        assert captured.status == "captured", captured.code
        return captured, facts.incoming_identity, original_sha

    # The helper's large caller graph does not remain live during cold admission.
    ancestor, identity, original_sha = capture_ancestor()
    ancestor_manifest = json.loads(
        git(vault, "cat-file", "blob", ancestor.commit + ":manifest.json")
    )
    ancestor_wire = git(vault, "cat-file", "blob", ancestor.commit + ":review.json")
    envelope = json.loads(ancestor_wire)
    assert envelope["schema_id"] == "brz2obsidian.saved-review-refs"
    assert envelope["schema_version"] == 1
    original_row = next(
        row
        for row in ancestor_manifest["review_content"]
        if row["sha256"] == original_sha
    )
    assert original_row["size"] == 16 * 1024 * 1024
    assert (
        int(git(vault, "cat-file", "-s", original_row["object_id"])) == 16 * 1024 * 1024
    )
    original_slot = envelope["record"]["plan"]["facts"]["subjects"][0]["baseline"][
        "content"
    ]
    assert original_slot["data"] == {"__brz2obsidian_review_blob__": original_sha}
    assert (
        envelope["record"]["plan"]["actions"][0]["decision_id"]
        == "ancestor:keep-current"
    )

    (source / "Assets/data.bin").write_bytes(tip_source)
    tip = operations.capture_checkpoint(
        vault,
        source,
        vault_id="cold-ancestor-vault",
        import_id="cold-ancestor-import",
        identity=identity,
        admission=operations.inspect_vault(vault),
    )
    assert tip.status == "captured" and tip.locator.generation == 2, tip.code
    tip_manifest = json.loads(
        git(vault, "cat-file", "blob", tip.commit + ":manifest.json")
    )
    assert tip_manifest["previous"] == ancestor.commit
    assert tip_manifest["review_object"] is None
    assert tip_manifest["review_content"] == []
    assert git(vault, "rev-list", "--count", tip.ref) == b"2\n"
    before = user_state(vault)
    before_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    before_locator = (vault / ".brz2obsidian/locator.json").read_bytes()

    capacity = 96 * 1024 * 1024
    assert 4 * ancestor_manifest["review_size"] + 64 * 1024 * 1024 < capacity
    assert capacity < 9 * original_row["size"] + 64 * 1024 * 1024
    capacity_observed = []

    def available_memory():
        capacity_observed.append(capacity)
        return capacity

    monkeypatch.setattr(history, "available_memory", available_memory)
    with operations.inspect_update_inputs(vault) as observed:
        assert capacity_observed
        assert observed.history.status == "intact", observed.history
        assert observed.history.admission.status == "supported"
        assert observed.history.checkpoint.locator.commit == tip.commit
        assert observed.history.checkpoint.review is None
    loaded = operations.load_update(vault)
    assert loaded.status == "refused" and loaded.code == "saved_update_unavailable", (
        loaded
    )
    assert loaded.history_retained and not loaded.ready
    assert loaded.loaded is None
    assert user_state(vault) == before
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == before_refs
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == before_locator
    assert (vault / "Assets/data.bin").read_bytes() == current
    assert (source / "Assets/data.bin").read_bytes() == tip_source
    assert (
        git(vault, "cat-file", "blob", ancestor.commit + ":review.json")
        == ancestor_wire
    )


def test_repeated_semantic_ancestor_shares_verified_bytes_within_capacity(monkeypatch):
    operations = Operations()
    vault, source = fixture_case()
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    for parent in (vault, source):
        (parent / "Notes").mkdir()
    current = b"authored current\r\n"
    incoming = b"incoming next\n"
    tip_source = b"tiny next source\n"
    (vault / "Notes/Opening.md").write_bytes(current)
    (source / "Notes/Opening.md").write_bytes(incoming)
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "Independent authored text baseline")

    def capture_ancestor():
        original = b"A" * (16 * 1024 * 1024)
        original_sha = hashlib.sha256(original).hexdigest()
        facts = with_review_links(
            request(original=original, current=current, incoming=incoming)
        )
        subject = facts.subjects[0]
        assert subject.attachment is None
        assert subject.interpretation == "supported" and subject.output_role == "note"
        initial = prepare_review(facts, preflight=preflight())
        assert initial.proposal.changes[0].disposition == "unresolved"
        assert initial.proposal.changes[0].format_review is None
        chosen = resolve_review(
            initial,
            action(initial, choice="current", decision_id="semantic:keep-current"),
        )
        assert chosen.status == "accepted" and chosen.plan.ready, chosen.code
        assert not chosen.plan.approvals[0].source_accepted
        effects = select_review_effects(chosen.plan)
        assert effects.status == "selected" and effects.remove_paths == ()
        assert [(row.path, row.content.data) for row in effects.files] == [
            ("Notes/Opening.md", current)
        ]
        captured = operations.capture_checkpoint(
            vault,
            source,
            vault_id="semantic-ancestor-vault",
            import_id="semantic-ancestor-import",
            identity=facts.incoming_identity,
            admission=operations.inspect_vault(vault),
            review=chosen.plan,
        )
        assert captured.status == "captured", captured.code
        return captured, facts.incoming_identity, original_sha

    ancestor, identity, original_sha = capture_ancestor()
    manifest = json.loads(
        git(vault, "cat-file", "blob", ancestor.commit + ":manifest.json")
    )
    ancestor_wire = git(vault, "cat-file", "blob", ancestor.commit + ":review.json")
    envelope = json.loads(ancestor_wire)
    assert envelope["schema_id"] == "brz2obsidian.saved-review-refs"
    plan = envelope["record"]["plan"]
    marker = {"__brz2obsidian_review_blob__": original_sha}
    # These are two independently authenticated semantic occurrences of the
    # same retained original, not two distinct payloads or invented aliases.
    assert plan["facts"]["subjects"][0]["baseline"]["content"]["data"] == marker
    assert (
        plan["history"]["initial_facts"]["subjects"][0]["baseline"]["content"]["data"]
        == marker
    )
    assert plan["actions"][0]["decision_id"] == "semantic:keep-current"
    sizes = {
        row["sha256"]: row["size"]
        for role in ("source", "vault", "preimage", "proposed", "review_content")
        for row in manifest[role]
    }
    assert sizes[original_sha] == 16 * 1024 * 1024

    (source / "Notes/Opening.md").write_bytes(tip_source)
    tip = operations.capture_checkpoint(
        vault,
        source,
        vault_id="semantic-ancestor-vault",
        import_id="semantic-ancestor-import",
        identity=identity,
        admission=operations.inspect_vault(vault),
    )
    assert tip.status == "captured" and tip.locator.generation == 2, tip.code
    tip_manifest = json.loads(
        git(vault, "cat-file", "blob", tip.commit + ":manifest.json")
    )
    assert tip_manifest["previous"] == ancestor.commit
    assert tip_manifest["review_object"] is None
    before = user_state(vault)
    before_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    before_locator = (vault / ".brz2obsidian/locator.json").read_bytes()

    capacity = 256 * 1024 * 1024
    assert (
        4 * manifest["review_size"] + 9 * sum(sizes.values()) + 64 * 1024 * 1024
        < capacity
    )
    assert (
        capacity
        < 4 * manifest["review_size"] + 9 * 2 * sizes[original_sha] + 64 * 1024 * 1024
    )
    capacity_observed = []

    def available_memory():
        capacity_observed.append(capacity)
        return capacity

    monkeypatch.setattr(history, "available_memory", available_memory)
    with operations.inspect_update_inputs(vault) as observed:
        assert capacity_observed
        assert observed.history.status == "intact", observed.history
        assert observed.history.admission.status == "supported"
        assert observed.history.checkpoint.locator.commit == tip.commit
    loaded = operations.load_update(vault)
    assert loaded.status == "refused" and loaded.code == "saved_update_unavailable", (
        loaded
    )
    assert loaded.history_retained and not loaded.ready and loaded.loaded is None
    assert user_state(vault) == before
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == before_refs
    )
    assert (vault / ".brz2obsidian/locator.json").read_bytes() == before_locator
    assert (vault / "Notes/Opening.md").read_bytes() == current
    assert (source / "Notes/Opening.md").read_bytes() == tip_source
    assert (
        git(vault, "cat-file", "blob", ancestor.commit + ":review.json")
        == ancestor_wire
    )


def test_coherent_ancestor_reference_tamper_refuses_and_retires_owned_files(
    monkeypatch,
):
    operations = Operations()
    vault, source = fixture_case()
    owned = vault.parent
    # Keep native repositories outside the checkout; all subsequent temporary
    # spools are still inside this fixture's owned OS-temp root.
    monkeypatch.setattr(tempfile, "tempdir", str(owned))
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    for parent in (vault, source):
        (parent / "Assets").mkdir()
    current, incoming, original = b"\x00authored", b"abc", b"\x00original"
    (vault / "Assets/data.bin").write_bytes(current)
    (source / "Assets/data.bin").write_bytes(incoming)
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "Independent authored corruption fixture")
    facts = attachment_request()
    initial = prepare_review(facts, preflight=preflight())
    selection, candidate = attachment_candidate(facts, "current")
    chosen = resolve_review(
        initial,
        action(
            initial,
            domain="attachment",
            choice="current",
            decision_id="ancestor:reference-control",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert chosen.status == "accepted" and chosen.plan.ready, chosen.code
    ancestor = operations.capture_checkpoint(
        vault,
        source,
        vault_id="corrupt-ancestor-vault",
        import_id="corrupt-ancestor-import",
        identity=facts.incoming_identity,
        admission=operations.inspect_vault(vault),
        review=chosen.plan,
    )
    assert ancestor.status == "captured", ancestor.code
    ancestor_wire = git(vault, "cat-file", "blob", ancestor.commit + ":review.json")
    ancestor_manifest = json.loads(
        git(vault, "cat-file", "blob", ancestor.commit + ":manifest.json")
    )
    (source / "Assets/data.bin").write_bytes(b"tiny next source\n")
    tip = operations.capture_checkpoint(
        vault,
        source,
        vault_id="corrupt-ancestor-vault",
        import_id="corrupt-ancestor-import",
        identity=facts.incoming_identity,
        admission=operations.inspect_vault(vault),
    )
    assert tip.status == "captured" and tip.locator.generation == 2, tip.code
    tip_manifest = json.loads(
        git(vault, "cat-file", "blob", tip.commit + ":manifest.json")
    )
    assert tip_manifest["previous"] == ancestor.commit
    assert tip_manifest["review_object"] is None
    with operations.inspect_update_inputs(vault) as observed:
        assert observed.history.status == "intact"
        assert observed.history.checkpoint.locator.commit == tip.commit

    locator_path = vault / ".brz2obsidian/locator.json"
    valid_locator = locator_path.read_bytes()
    valid_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    oracles = owned / "valid-chain-oracles"
    oracles.mkdir()
    (oracles / "locator.json").write_bytes(valid_locator)
    (oracles / "refs.txt").write_bytes(valid_refs)
    (oracles / "ancestor-review.json").write_bytes(ancestor_wire)

    poisoned = json.loads(ancestor_wire)
    slot = poisoned["record"]["plan"]["facts"]["subjects"][0]["baseline"]["content"]
    assert slot["reference"] is None
    original_sha = hashlib.sha256(original).hexdigest()
    assert slot["data"] == {"__brz2obsidian_review_blob__": original_sha}
    slot["reference"] = {
        "content_id": "historical:changed-ancestor-reference",
        "sha256": original_sha,
        "size": len(original),
    }
    poisoned_wire = json.dumps(poisoned, separators=(",", ":")).encode()
    retarget_checkpoint(vault, ancestor, review=poisoned_wire)
    bad_ancestor = json.loads(locator_path.read_bytes())["commit"]
    bad_manifest = json.loads(
        git(vault, "cat-file", "blob", bad_ancestor + ":manifest.json")
    )
    assert bad_manifest["previous"] is None and bad_manifest["generation"] == 1
    assert (
        bad_manifest["semantic_fingerprint"]
        == ancestor_manifest["semantic_fingerprint"]
    )
    assert bad_manifest["review_content"] == ancestor_manifest["review_content"]
    assert bad_manifest["review_size"] == len(poisoned_wire)
    assert bad_manifest["review_sha256"] == hashlib.sha256(poisoned_wire).hexdigest()

    rows = {
        row.split(b"\t", 1)[1]: row
        for row in git(vault, "ls-tree", "-z", tip.commit).split(b"\0")
        if row
    }
    old_tip_meaning = tip_manifest["semantic_fingerprint"]
    tip_manifest["previous"] = bad_ancestor
    manifest_oid = git(
        vault, "hash-object", "-w", "--stdin", input=json.dumps(tip_manifest).encode()
    ).strip()
    rows[b"manifest.json"] = b"100644 blob " + manifest_oid + b"\tmanifest.json"
    tree = (
        git(vault, "mktree", "-z", input=b"\0".join(rows.values()) + b"\0")
        .strip()
        .decode()
    )
    bad_tip = (
        git(
            vault,
            "commit-tree",
            tree,
            "-p",
            bad_ancestor,
            input=b"Coherent tip over changed ancestor reference\n",
        )
        .strip()
        .decode()
    )
    git(vault, "update-ref", tip.ref, bad_tip, bad_ancestor)
    locator = json.loads(valid_locator)
    locator["commit"] = bad_tip
    locator_path.write_text(json.dumps(locator), encoding="utf-8")
    assert git(vault, "rev-parse", bad_tip + "^").decode().strip() == bad_ancestor
    assert tip_manifest["semantic_fingerprint"] == old_tip_meaning
    assert (
        git(vault, "cat-file", "blob", bad_ancestor + ":review.json") == poisoned_wire
    )

    def owned_tree():
        return (
            {
                str(path.relative_to(owned)): path.read_bytes()
                for path in owned.rglob("*")
                if path.is_file()
            },
            {
                str(path.relative_to(owned))
                for path in owned.rglob("*")
                if path.is_dir()
            },
        )

    before_tree = owned_tree()
    before_state = user_state(vault)
    poisoned_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    assert poisoned_refs != valid_refs
    with operations.inspect_update_inputs(vault) as observed:
        assert observed.history.status == "unavailable"
        assert observed.history.checkpoint is None
    refused = operations.load_update(vault)
    assert refused.status == "recovery_required" and refused.code == "recovery_first", (
        refused
    )
    assert refused.history_retained and not refused.ready and refused.loaded is None
    assert owned_tree() == before_tree
    assert user_state(vault) == before_state
    assert (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == poisoned_refs
    )
    assert (vault / "Assets/data.bin").read_bytes() == current
    assert (source / "Assets/data.bin").read_bytes() == b"tiny next source\n"
    assert (oracles / "locator.json").read_bytes() == valid_locator
    assert (oracles / "refs.txt").read_bytes() == valid_refs
    assert (
        git(vault, "cat-file", "blob", ancestor.commit + ":review.json")
        == ancestor_wire
    )
