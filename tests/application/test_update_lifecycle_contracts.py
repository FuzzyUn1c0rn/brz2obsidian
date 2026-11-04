"""Small public immutable reviews keep semantic variants off real BRZ/Git paths."""

import hashlib
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from brz2obsidian.application.checkpoint_contracts import (
    CheckpointLocator,
    VaultAssociation,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.source_payload_contracts import (
    ReviewedSourceBinding,
    SourcePayloadFile,
)
from brz2obsidian.application.update_contracts import UpdatePreparation, UpdateResult
from brz2obsidian.contracts import SourceIdentity
from brz2obsidian.core import prepare_review
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


@pytest.fixture(autouse=True)
def controlled_public_input_reader(monkeypatch):
    def inputs(operations, vault):
        return nullcontext(
            SimpleNamespace(
                history=operations.inspect_history(vault),
                read_payload=lambda **kwargs: operations.read_checkpoint_payload(
                    vault, **kwargs
                ),
                inspect=lambda **kwargs: operations.inspect_history(vault, **kwargs),
            )
        )

    monkeypatch.setattr(Operations, "inspect_update_inputs", inputs)


def preparation(facts=None):
    plan = prepare_review(
        with_review_links(request()) if facts is None else facts,
        preflight=preflight(),
    )
    row = SourcePayloadFile(
        path="Notes/Opening.md",
        mode="100644",
        size=9,
        sha256=hashlib.sha256(b"incoming\n").hexdigest(),
    )
    identity = plan.facts.incoming_identity
    association = VaultAssociation(
        schema_id="brz2obsidian.vault-association",
        schema_version=1,
        association_id="a" * 64,
        vault_id="vault",
        import_id="import",
        collection_id=identity.collection_id,
        module_id=identity.module_id,
        vault_anchor="observed-vault",
        git_anchor="observed-git",
        ref="refs/brz2obsidian/imports/" + "a" * 64 + "/checkpoints",
    )
    locator = CheckpointLocator(
        schema_id="brz2obsidian.checkpoint-locator",
        schema_version=1,
        association=association,
        generation=1,
        commit="b" * 40,
    )
    binding = ReviewedSourceBinding(
        schema_id="brz2obsidian.reviewed-source-binding",
        schema_version=1,
        proposal_id=plan.proposal.proposal_id,
        generation=1,
        incoming_identity=identity,
        target_source_version="source:b",
        source_anchor="observed-source",
        files=(row,),
        fingerprint=ReviewedSourceBinding.digest((row,)),
    )
    return UpdatePreparation(
        schema_id="brz2obsidian.update-preparation",
        schema_version=1,
        vault="unused",
        locator=locator,
        payload_directory="unused",
        source_binding=binding,
        observed_source=SourceIdentity(
            source_id=identity.collection_id,
            module_id=identity.module_id,
            module_version=identity.module_version,
            format_version="5",
            source_sha256="c" * 64,
            snapshot_digest="d" * 64,
        ),
        retained_source_provenance=False,
        review=plan,
    )


@pytest.mark.parametrize("preparation_kind", ("source_update", "onboarding"))
def test_matching_source_refresh_keeps_reader_and_fresh_observed_identity(
    tmp_path, monkeypatch, preparation_kind
):
    import json

    from brz2obsidian.application import SourceModuleBinding, Workflow
    from brz2obsidian.application.vault_contracts import VaultFile
    from brz2obsidian.contracts import OutputIdentity
    from brz2obsidian.obsidian import ObsidianRenderer
    from brz2obsidian.publication import FilesystemPublisher
    from brz2obsidian.publication.vault_native import observe_file
    from tests.application.test_module_seams import METADATA
    from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule

    source = tmp_path / "folio.json"
    data = {
        "collection": "refresh-collection",
        "start": "entry:opening",
        "entries": [
            {
                "key": "entry:opening",
                "seed": "00000001000040008000000000000000",
                "title": "Opening",
            }
        ],
        "connections": [],
        "assets": [],
        "documents": [],
    }
    source.write_text(json.dumps(data))
    workflow = Workflow(
        SourceModuleBinding(FolioSourceModule(), FOLIO_POLICY),
        ObsidianRenderer(),
        FilesystemPublisher(),
        metadata_factory=lambda: METADATA,
    )
    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.receipt is not None
    payload = {
        r.relative_path: (vault / r.relative_path).read_bytes()
        for r in converted.receipt.manifest
    }
    rows = tuple(
        SourcePayloadFile(
            path=p, mode="100644", size=len(raw), sha256=hashlib.sha256(raw).hexdigest()
        )
        for p, raw in sorted(payload.items())
    )
    inventory = []
    for row in rows:
        info, sha, _, physical = observe_file(vault, vault / row.path, prefix_limit=0)
        inventory.append(
            VaultFile(
                path=row.path,
                mode=row.mode,
                size=info.st_size,
                sha256=sha,
                identity=physical,
                tracked=True,
                excluded=False,
                exclusion=None,
            )
        )
    identity = OutputIdentity(
        collection_id="refresh-collection",
        module_id="synthetic-folio",
        module_version="3",
        profile_id="synthetic-folio-reviewed",
        profile_version="3",
        output_format=7,
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    association = VaultAssociation(
        schema_id="brz2obsidian.vault-association",
        schema_version=1,
        association_id="a" * 64,
        vault_id="vault",
        import_id="import",
        collection_id=identity.collection_id,
        module_id=identity.module_id,
        vault_anchor="observed-vault",
        git_anchor="observed-git",
        ref="refs/brz2obsidian/imports/" + "a" * 64 + "/checkpoints",
    )
    locator = CheckpointLocator(
        schema_id="brz2obsidian.checkpoint-locator",
        schema_version=1,
        association=association,
        generation=1,
        commit="b" * 40,
    )
    history = SimpleNamespace(
        status="intact",
        admission=SimpleNamespace(
            vault=str(vault),
            status="supported",
            inventory=tuple(inventory),
            preflight=preflight(),
            findings=(),
            recovery_gaps=(),
            repository=SimpleNamespace(kind="root"),
        ),
        checkpoint=SimpleNamespace(
            status="valid",
            locator=locator,
            review=None,
            manifest=SimpleNamespace(boundary="local", identity=identity, source=rows),
        ),
    )
    operations = Operations(workflow=workflow)
    scopes = []

    def inspection(*args, **kwargs):
        if "subjects" in kwargs:
            scopes.append(tuple(s.path for s in kwargs["subjects"]))
        return history

    monkeypatch.setattr(operations, "inspect_history", inspection)
    monkeypatch.setattr(
        operations,
        "read_checkpoint_payload",
        lambda *args, **kwargs: SimpleNamespace(
            status="available",
            chunks=tuple(
                SimpleNamespace(path=p, data=raw) for p, raw in payload.items()
            ),
        ),
    )
    prepared = operations.prepare_update(vault, source)
    assert prepared.preparation is not None, prepared
    prior = prepared.preparation
    if preparation_kind == "onboarding":
        facts = prior.review.facts.model_copy(
            update={
                "format_operation": prior.review.facts.format_operation.model_copy(
                    update={"kind": "onboarding"}
                ),
            }
        )
        prior = UpdatePreparation.model_validate(
            prior.model_dump()
            | {
                "kind": "onboarding",
                "review": prepare_review(facts, preflight=prior.review.preflight),
            }
        )
        history.checkpoint.manifest.boundary = "result"
    data["new_source_evidence"] = "literal changed observation"
    source.write_text(json.dumps(data))
    refreshed = operations.refresh_update(prior, source=source)
    assert refreshed.preparation is not None, refreshed
    assert refreshed.kind == refreshed.preparation.kind == "source_update"
    assert (
        refreshed.preparation.observed_source.source_sha256
        == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert refreshed.preparation.observed_source != prepared.preparation.observed_source
    assert (
        refreshed.preparation.review.facts.incoming_identity.collection_id
        == "refresh-collection"
    )
    assert len(scopes) == 2 and "Home \u2014 Opening.md" in scopes[-1]


@pytest.mark.parametrize(
    ("status", "has_locator"),
    (
        ("valid", True),
        ("refused", True),
        ("valid", False),
        ("absent", False),
        (None, False),
    ),
)
def test_recovery_gate_discloses_gaps_vault_and_only_valid_available_checkpoint(
    monkeypatch, status, has_locator
):
    locator = preparation().locator
    checkpoint = (
        SimpleNamespace(status=status, locator=locator if has_locator else None)
        if status is not None
        else None
    )
    history = SimpleNamespace(
        status="unavailable",
        checkpoint=checkpoint,
        admission=SimpleNamespace(
            status="recovery_first",
            vault="observed-vault",
            recovery_gaps=("Ignored/private.bin",),
            findings=(),
        ),
    )
    operations = Operations()
    monkeypatch.setattr(operations, "inspect_history", lambda vault: history)
    result = operations.prepare_update("observed-vault", "unused.brz")
    assert result.status == "recovery_required" and result.code == "recovery_first"
    assert result.next_actions == ("review_recovery",)
    assert result.vault == "observed-vault"
    assert result.recovery_gaps == ("Ignored/private.bin",)
    expected = locator if status == "valid" and has_locator else None
    assert result.checkpoint == expected
    assert result.checkpoint_commit == (
        expected.commit if expected is not None else None
    )


def test_current_incoming_and_edited_text_use_offered_identity_and_exact_bytes():
    original = preparation()
    operations = Operations()
    current = operations.resolve_update(
        original, action(original.review, choice="current")
    )
    incoming = operations.resolve_update(
        original, action(original.review, choice="incoming")
    )
    edited = operations.resolve_update(
        original,
        action(original.review, choice="edited"),
        edited=b"Authored chosen result.\r\n",
    )
    assert current.ready
    assert current.preparation.review.approvals[0].result.data == b"original\r\n"
    assert current.preparation.review.approvals[0].source_memory.choice == "keep_vault"
    assert incoming.ready
    assert incoming.preparation.review.approvals[0].result.data == b"incoming\n"
    assert edited.ready
    assert edited.preparation.review.approvals[0].result.data == (
        b"Authored chosen result.\r\n"
    )
    assert original.review.approvals == ()


def test_stale_action_and_unsafe_edited_text_never_gain_ready_authority():
    original = preparation()
    stale = Operations().resolve_update(
        original, action(original.review, expected_generation=2)
    )
    assert stale.status == "stale_review" and not stale.ready
    unsafe = Operations().resolve_update(
        original,
        action(original.review, choice="edited"),
        edited=b"---\na: 1\na: 2\n---\n",
    )
    assert unsafe.status == "refused" and not unsafe.ready
    assert unsafe.preparation.review.approvals == ()
    with pytest.raises(ValidationError):
        UpdateResult(status="prepared_review", code="invented", ready=True)
    with pytest.raises(ValidationError):
        UpdatePreparation.model_validate(
            original.model_dump() | {"arbitrary_patch_paths": ("escape",)}
        )


def test_edited_note_retains_real_manual_backlink_and_exact_resource_context():
    from tests.reconciliation.test_local_resources import manual_resource_facts

    original = preparation(manual_resource_facts())
    edited = Operations().resolve_update(
        original,
        action(original.review, choice="edited"),
        edited=b"Reviewed [[Guide]].",
    )
    assert edited.code == "accepted"
    assert edited.ready, edited.preparation.review.blockers
    assert edited.preparation.review.approvals[0].result.data == b"Reviewed [[Guide]]."


def test_independent_binary_choice_preserves_edited_note_backlink_context():
    from brz2obsidian.core import select_review_effects
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
    )
    from tests.reconciliation.test_identity import with_subjects
    from tests.reconciliation.test_local_resources import (
        manual_resource_facts,
        reobserve_documents,
    )

    note, binary = manual_resource_facts(), attachment_request()
    context = note.link_context.model_copy(
        update={
            name: getattr(note.link_context, name) + getattr(binary.link_context, name)
            for name in (
                "current_targets",
                "incoming_targets",
                "current_target_facts",
                "incoming_target_facts",
            )
        }
    )
    facts = with_subjects(
        note,
        note.subjects + binary.subjects,
        note.identity_inventory
        + (
            binary.identity_inventory[0].model_copy(
                update={"entry_id": "binary:payload"}
            ),
        ),
    ).model_copy(update={"link_context": context})
    facts = reobserve_documents(facts)
    original = preparation(facts)
    note_change = next(
        c for c in original.review.proposal.changes if c.facet == "content"
    )
    edited = Operations().resolve_update(
        original,
        action(original.review, note_change, choice="edited"),
        edited=b"Reviewed [[Guide]].",
    )
    assert edited.code == "accepted"
    plan = edited.preparation.review
    binary_change = next(c for c in plan.proposal.changes if c.attachment_review)
    selection, candidate = attachment_candidate(facts, "incoming")
    chosen = Operations().resolve_update(
        edited.preparation,
        action(
            plan,
            binary_change,
            domain="attachment",
            choice="incoming",
            decision_id="independent-binary",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert chosen.code == "accepted"
    assert chosen.ready, chosen.preparation.review.blockers
    effects = select_review_effects(chosen.preparation.review)
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Assets/data.bin", b"abc"),
        ("Notes/Opening.md", b"Reviewed [[Guide]]."),
    ]


def test_review_page_positive_budget_never_skips_unread_bytes(monkeypatch):
    from types import SimpleNamespace

    prepared = preparation(with_review_links(request(current=b"other exact\r\n")))
    operations = Operations()
    monkeypatch.setattr(
        operations,
        "read_checkpoint",
        lambda vault: SimpleNamespace(status="valid", locator=prepared.locator),
    )
    arguments = {
        "proposal_id": prepared.review.proposal.proposal_id,
        "generation": prepared.review.proposal.generation,
    }
    too_small = operations.inspect_update_review(prepared, byte_limit=2, **arguments)
    assert too_small.status == "refused"
    assert too_small.code == "insufficient_page_budget"
    page = operations.inspect_update_review(prepared, byte_limit=3, **arguments)
    assert page.status == "available" and len(page.items) == 1
    row = page.items[0]
    assert (row.original, row.current, row.incoming, row.result) == (
        b"o",
        b"o",
        b"i",
        None,
    )
    assert row.omitted and page.omitted
    assert row.offset == 0 and row.next_byte_offset == 1
    second = operations.inspect_update_review(
        prepared, byte_offset=1, byte_limit=3, **arguments
    )
    assert (
        second.items[0].original,
        second.items[0].current,
        second.items[0].incoming,
    ) == (
        b"r",
        b"t",
        b"n",
    )


def test_incoming_text_uses_explicitly_kept_binary_version():
    from brz2obsidian.core import select_review_effects
    from tests.reconciliation.test_attachments import attachment_candidate
    from tests.reconciliation.test_resolution import note_and_attachment_request

    facts = note_and_attachment_request()
    original = preparation(facts)
    binary = next(c for c in original.review.proposal.changes if c.attachment_review)
    selection, candidate = attachment_candidate(facts, "current")
    kept = Operations().resolve_update(
        original,
        action(
            original.review,
            binary,
            domain="attachment",
            choice="current",
            decision_id="keep-binary",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert kept.code == "accepted"
    note = next(
        c for c in kept.preparation.review.proposal.changes if c.facet == "content"
    )
    chosen = Operations().resolve_update(
        kept.preparation,
        action(
            kept.preparation.review, note, choice="incoming", decision_id="new-prose"
        ),
    )
    assert chosen.code == "accepted"
    assert chosen.ready, chosen.preparation.review.blockers
    effects = select_review_effects(chosen.preparation.review)
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Assets/data.bin", b"\x00authored"),
        ("Notes/Owner.md", b"New prose [[Assets/data.bin]]."),
    ]


@pytest.mark.parametrize("current", (b"abc", b"\x00authored"))
def test_explicit_current_binary_needs_memory_only_for_different_incoming_bytes(
    current,
):
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core import select_review_effects
    from tests.reconciliation.test_attachments import (
        attachment_candidate,
        attachment_request,
        binary_context,
    )
    from tests.reconciliation.test_identity import with_subjects

    facts = attachment_request()
    observed = facts.subjects[0].current.model_copy(
        update={"content": ExactContent(data=current)}
    )
    subject = facts.subjects[0].model_copy(update={"current": observed})
    entry = facts.identity_inventory[0].model_copy(update={"current": observed})
    facts = with_subjects(facts, (subject,), (entry,))
    facts = facts.model_copy(update={"link_context": binary_context(facts)})
    prepared = preparation(facts)
    selection, candidate = attachment_candidate(facts, "current")
    chosen = Operations().resolve_update(
        prepared,
        action(
            prepared.review,
            domain="attachment",
            choice="current",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    )
    assert chosen.code == "accepted" and chosen.ready
    approval = chosen.preparation.review.approvals[0]
    if current == b"abc":
        assert approval.source_memory is None
    else:
        assert approval.source_memory.reviewed_incoming.data == b"abc"
        assert approval.source_memory.choice == "keep_vault"
    effects = select_review_effects(chosen.preparation.review)
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Assets/data.bin", current)
    ]


@pytest.mark.parametrize("current", (b"incoming\n", b"Authored exact\r\n"))
def test_explicit_current_text_needs_memory_only_for_different_incoming_bytes(current):
    prepared = preparation(with_review_links(request(current=current)))
    chosen = Operations().resolve_update(
        prepared, action(prepared.review, choice="current")
    )
    assert chosen.code == "accepted" and chosen.ready
    approval = chosen.preparation.review.approvals[0]
    assert approval.result.data == current
    if current == b"incoming\n":
        assert approval.source_memory is None
    else:
        assert approval.source_memory.reviewed_incoming.data == b"incoming\n"
        assert approval.source_memory.choice == "keep_vault"


def test_review_page_exhaustion_leaves_the_unread_row_and_reports_eof(monkeypatch):
    from types import SimpleNamespace

    from tests.reconciliation.test_resolution import note_and_attachment_request

    prepared = preparation(note_and_attachment_request())
    operations = Operations()
    monkeypatch.setattr(
        operations,
        "read_checkpoint",
        lambda vault: SimpleNamespace(status="valid", locator=prepared.locator),
    )
    arguments = {
        "proposal_id": prepared.review.proposal.proposal_id,
        "generation": prepared.review.proposal.generation,
    }
    first = operations.inspect_update_review(prepared, byte_limit=4, **arguments)
    assert first.status == "available" and len(first.items) == 1
    assert first.items[0].incoming_path == "Notes/Owner.md"
    assert first.next_offset == 1 and first.items[0].next_byte_offset == 1
    second = operations.inspect_update_review(
        prepared, offset=1, byte_limit=3, **arguments
    )
    assert second.items[0].incoming_path == "Assets/data.bin"
    assert (
        second.items[0].original,
        second.items[0].current,
        second.items[0].incoming,
    ) == (b"\x00", b"\x00", b"a")
    assert second.next_offset is None
    end = operations.inspect_update_review(
        prepared, byte_offset=100, byte_limit=1, **arguments
    )
    assert len(end.items) == 2 and end.next_offset is None
    assert all(row.next_byte_offset is None for row in end.items)
    assert all(row.original == row.current == row.incoming == b"" for row in end.items)
    metadata = operations.inspect_update_review(prepared, byte_limit=0, **arguments)
    assert len(metadata.items) == 2 and metadata.omitted
    assert all(row.next_byte_offset == 0 for row in metadata.items)


def test_source_category_and_tag_memberships_keep_their_bound_identities():
    import json

    from brz2obsidian.application.update_facts import assemble_facts

    original = (
        b'---\ncategories: []\nappearance_category: ""\ntags: []\n'
        b'source_collection_id: "folio:collection"\n'
        b'source_item_id: "entry:opening"\n---\nOriginal.\n'
    )
    incoming = (
        b'---\ncategories:\n  - "[[Categories/Research.md]]"\n'
        b'appearance_category: "[[Categories/Research.md]]"\n'
        b"tags:\n  - source-tag\n"
        b'source_collection_id: "folio:collection"\n'
        b'source_item_id: "entry:opening"\n---\nIncoming.\n'
    )
    category = (
        b"---\ncategories: []\ntags:\n  - categories\n"
        b'source_collection_id: "folio:collection"\n'
        b'source_item_id: "category:research"\n---\nCategory description.\n'
    )
    source = {
        "schema": "brz2obsidian.migration",
        "schema_version": 7,
        "profile_id": "reviewed-folio",
        "profile_version": "1",
        "source_identity": {
            "source_id": "folio:collection",
            "module_id": "synthetic-folio",
            "module_version": "1",
            "format_version": "5",
            "source_sha256": "c" * 64,
            "snapshot_digest": "d" * 64,
        },
        "item_targets": [
            {
                "original_identity": "entry:opening",
                "original_title": "Opening",
                "relative_path": "Notes/Opening.md",
                "created": True,
                "creation_reasons": ["content"],
            },
            {
                "original_identity": "category:research",
                "original_title": "Research",
                "relative_path": "Categories/Research.md",
                "created": True,
                "creation_reasons": ["definition"],
            },
            {
                "original_identity": "tag:source",
                "original_title": "Source tag",
                "relative_path": "Notes/Source tag.md",
                "created": False,
                "creation_reasons": [],
                "vault_tag_token": "source-tag",
            },
        ],
        "asset_targets": [],
    }
    baseline = {
        "migration-record.json": json.dumps(source).encode(),
        "Notes/Opening.md": original,
        "Categories/Research.md": category,
    }
    source["source_identity"]["snapshot_digest"] = "e" * 64
    source["source_identity"]["source_sha256"] = "f" * 64
    received = baseline | {
        "Notes/Opening.md": incoming,
        "migration-record.json": json.dumps(source).encode(),
    }
    facts = assemble_facts(
        baseline,
        received,
        baseline,
        proposal_id="review:membership",
        generation=1,
    )
    prepared = preparation(facts)
    note = next(
        c for c in prepared.review.proposal.changes if c.item_id == "entry:opening"
    )
    chosen = Operations().resolve_update(
        prepared, action(prepared.review, note, choice="incoming")
    )
    assert chosen.code == "accepted", chosen.code
    assert chosen.preparation.review.approvals[0].result.data == incoming
    properties = chosen.preparation.review.actions[-1].candidate.document.properties
    category_target = next(p for p in properties if p.key == "categories").targets[0]
    tag_target = next(p for p in properties if p.key == "tags").targets[0]
    assert category_target.identity.item_id == "category:research"
    assert category_target.identity.collection_id == "folio:collection"
    assert category_target.canonical_path == "Categories/Research.md"
    assert tag_target.target_id == "tag:synthetic-folio:folio:collection:tag:source"
    assert tag_target.identity is None


@pytest.mark.parametrize(
    ("difference", "code", "next_action"),
    (
        (
            {"profile_version": "9"},
            "source_profile_unavailable",
            "review_format_transition",
        ),
        (
            {"output_format": 6},
            "format_transition_required",
            "review_format_transition",
        ),
        (
            {"settings_digest": "f" * 64},
            "configuration_transition_required",
            "review_configuration",
        ),
    ),
)
def test_unavailable_recorded_generation_routes_before_payload_access(
    monkeypatch, difference, code, next_action
):
    from types import SimpleNamespace

    from brz2obsidian.contracts import OutputIdentity

    identity = OutputIdentity(
        collection_id="collection:recorded",
        module_id="thebrain-brz",
        module_version="10",
        profile_id="thebrain-format5-reviewed",
        profile_version="10",
        output_format=7,
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    ).model_copy(update=difference)
    history = SimpleNamespace(
        status="intact",
        admission=SimpleNamespace(
            status="supported",
            repository=SimpleNamespace(kind="root"),
            findings=(),
        ),
        checkpoint=SimpleNamespace(
            manifest=SimpleNamespace(identity=identity, source=(), boundary="local"),
            review=None,
            locator=preparation().locator,
        ),
    )
    operations = Operations()
    monkeypatch.setattr(operations, "inspect_history", lambda vault: history)

    def unread(*args, **kwargs):
        raise AssertionError("Unavailable generation must not access source payload")

    monkeypatch.setattr(operations, "read_checkpoint_payload", unread)
    result = operations.prepare_update("unopened-vault", "unopened-source.brz")
    assert (result.status, result.code, result.next_actions) == (
        "refused",
        code,
        (next_action,),
    )
    assert not result.ready and result.preparation is None


def recorded_history(identity=None, locator=None):
    from types import SimpleNamespace

    from brz2obsidian.contracts import OutputIdentity

    identity = identity or OutputIdentity(
        collection_id="collection:recorded",
        module_id="thebrain-brz",
        module_version="10",
        profile_id="thebrain-format5-reviewed",
        profile_version="10",
        output_format=7,
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    return SimpleNamespace(
        status="intact",
        admission=SimpleNamespace(
            status="supported",
            repository=SimpleNamespace(kind="root"),
            findings=(),
        ),
        checkpoint=SimpleNamespace(
            manifest=SimpleNamespace(identity=identity, source=(), boundary="local"),
            review=None,
            locator=locator or preparation().locator,
        ),
    )


def test_module_release_change_preserves_supported_profile_route(monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace

    from brz2obsidian.application.wiring import default_workflow

    for release in ("10", "11"):
        workflow = default_workflow()
        workflow.binding = replace(
            workflow.binding,
            policy=workflow.binding.policy.model_copy(
                update={"module_version": release}
            ),
        )
        operations = Operations(workflow=workflow)
        monkeypatch.setattr(
            operations, "inspect_history", lambda vault: recorded_history()
        )
        monkeypatch.setattr(
            operations,
            "read_checkpoint_payload",
            lambda *args, **kwargs: SimpleNamespace(
                status="refused", code="retained_bytes_unavailable"
            ),
        )
        result = operations.prepare_update("unopened-vault", "unopened-source.brz")
        assert (result.status, result.code) == ("refused", "preparation_unavailable")
        assert result.preparation is None and not result.ready


@pytest.mark.parametrize("serialized", (False, True))
def test_source_refresh_refuses_another_intact_association_before_source_access(
    monkeypatch, serialized
):
    prepared = preparation()
    other = prepared.locator.association.model_copy(
        update={
            "association_id": "f" * 64,
            "ref": "refs/brz2obsidian/imports/" + "f" * 64 + "/checkpoints",
        }
    )
    locator = prepared.locator.model_copy(update={"association": other})
    operations = Operations()
    monkeypatch.setattr(
        operations, "inspect_history", lambda vault: recorded_history(locator=locator)
    )

    def unread(*args, **kwargs):
        raise AssertionError("Another association must not acquire incoming bytes")

    monkeypatch.setattr(operations, "read_checkpoint_payload", unread)
    value = prepared.model_dump(mode="python") if serialized else prepared
    result = operations.refresh_update(value, source="B.brz")
    assert (result.status, result.code) == ("refused", "association_mismatch")
    assert result.preparation is None and not result.ready


@pytest.mark.parametrize(
    "difference",
    (
        "collection",
        "module",
        "binding_proposal",
        "binding_generation",
        "binding_identity",
        "observed_release",
    ),
)
def test_review_page_refuses_a_foreign_review_or_incoming_binding(
    monkeypatch, difference
):
    from types import SimpleNamespace

    prepared = preparation()
    if difference in ("collection", "module"):
        key = "collection_id" if difference == "collection" else "module_id"
        association = prepared.locator.association.model_copy(update={key: "foreign"})
        prepared = prepared.model_copy(
            update={
                "locator": prepared.locator.model_copy(
                    update={"association": association}
                )
            }
        )
    elif difference == "observed_release":
        prepared = prepared.model_copy(
            update={
                "observed_source": prepared.observed_source.model_copy(
                    update={"module_version": "99"}
                )
            }
        )
    else:
        changes = {
            "binding_proposal": {"proposal_id": "foreign-proposal"},
            "binding_generation": {"generation": 2},
            "binding_identity": {
                "incoming_identity": prepared.source_binding.incoming_identity.model_copy(
                    update={"module_version": "99"}
                )
            },
        }
        prepared = prepared.model_copy(
            update={
                "source_binding": prepared.source_binding.model_copy(
                    update=changes[difference]
                )
            }
        )
    operations = Operations()
    monkeypatch.setattr(
        operations,
        "read_checkpoint",
        lambda vault: SimpleNamespace(status="valid", locator=prepared.locator),
    )
    page = operations.inspect_update_review(
        prepared,
        proposal_id=prepared.review.proposal.proposal_id,
        generation=prepared.review.proposal.generation,
    )
    assert (page.status, page.code) == ("refused", "invalid_review")
    assert not page.items and page.omitted


def configuration_preparation(facts):
    from tests.reconciliation.test_identity import with_subjects

    subject = facts.subjects[0].model_copy(
        update={
            "path": ".obsidian/app.json",
            "current": facts.subjects[0].current.model_copy(
                update={"path": ".obsidian/app.json"}
            ),
            "source_target": facts.subjects[0].source_target.model_copy(
                update={"normalized_path": ".obsidian/app.json"}
            ),
            "output_role": "configuration",
        }
    )
    entry = facts.identity_inventory[0].model_copy(
        update={"current": subject.current, "target": subject.source_target}
    )
    return preparation(with_review_links(with_subjects(facts, (subject,), (entry,))))


def test_configuration_restoration_routes_to_separate_operation():
    from tests.reconciliation.test_absence import facts_for

    prepared = configuration_preparation(
        facts_for(
            original=b'{"setting":1}\n',
            incoming=b'{"setting":2}\n',
            existence="absent",
        )
    )
    chosen = Operations().resolve_update(
        prepared,
        action(prepared.review, domain="restoration", choice="restore_incoming"),
    )
    assert chosen.code == "separate_configuration_operation_required"
    assert not chosen.ready and chosen.next_actions == ("review_configuration",)
    assert chosen.preparation.review.approvals[0].result.data == b'{"setting":2}\n'


def test_current_configuration_remains_eligible_when_selected_bytes_are_unchanged():
    prepared = configuration_preparation(
        request(
            original=b'{"generated":1}\n',
            current=b'{"authored":9}\n',
            incoming=b'{"generated":2}\n',
        )
    )
    chosen = Operations().resolve_update(
        prepared, action(prepared.review, domain="configuration", choice="current")
    )
    assert chosen.code == "accepted" and chosen.ready
    assert chosen.next_actions == ("apply_update",)
    assert chosen.preparation.review.approvals[0].result.data == b'{"authored":9}\n'


def test_saved_observation_module_version_binds_the_reviewed_incoming_identity():
    from brz2obsidian.application.checkpoint_contracts import CheckpointManifest

    prepared = preparation()
    binding = prepared.source_binding.model_copy(
        update={"target_source_version": prepared.observed_source.snapshot_digest}
    )
    manifest = CheckpointManifest(
        schema_id="brz2obsidian.checkpoint-manifest",
        schema_version=1,
        association_id=prepared.locator.association.association_id,
        generation=1,
        boundary="local",
        identity=binding.incoming_identity,
        source=(),
        vault=(),
        preimage=(),
        proposed=(),
        review_content=(),
        recovery_gaps=(),
        semantic_fingerprint="a" * 64,
        policy_fingerprint="b" * 64,
        policy_continuity_fingerprint="c" * 64,
        previous=None,
        review_object="d" * 40,
        review_size=1,
        review_sha256="e" * 64,
        observed_source=prepared.observed_source,
        reviewed_source=binding,
    )
    assert manifest.observed_source.format_version == "5"
    assert manifest.identity.output_format == 7
    legacy = manifest.model_copy(
        update={"observed_source": None, "reviewed_source": None}
    )
    old_json = legacy.model_dump_json()
    assert "observed_source" not in old_json and "reviewed_source" not in old_json
    assert (
        CheckpointManifest.model_validate_json(old_json).model_dump_json() == old_json
    )
    mismatched = manifest.model_dump(mode="python")
    mismatched["observed_source"]["module_version"] = "99"
    with pytest.raises(ValidationError):
        CheckpointManifest.model_validate(mismatched)


@pytest.mark.parametrize("missing", ("review", "reviewed_source"))
def test_saved_update_without_complete_retained_authority_cannot_load_or_resume(
    monkeypatch, missing
):
    from brz2obsidian.core import load_review, save_review

    prepared = preparation()
    loaded = load_review(save_review(prepared.review).record.model_dump_json()).loaded
    history = recorded_history(
        prepared.review.facts.incoming_identity, prepared.locator
    )
    history.admission.vault = prepared.vault
    history.checkpoint.review = loaded
    history.checkpoint.manifest.reviewed_source = prepared.source_binding
    operations = Operations()
    monkeypatch.setattr(operations, "inspect_history", lambda vault: history)
    positive = operations.load_update(prepared.vault)
    assert positive.code == "revalidation_required" and not positive.ready
    assert positive.loaded is not None and not positive.loaded.ready
    assert positive.loaded.readiness == "revalidation_required"
    assert (
        positive.loaded.saved.plan.proposal.proposal_id
        == prepared.review.proposal.proposal_id
    )
    assert positive.loaded.saved.plan.proposal.generation == 1
    assert positive.loaded.saved.plan.facts.subjects[0].incoming.data == b"incoming\n"
    assert positive.checkpoint == prepared.locator and positive.history_retained
    assert positive.next_actions == ("resume_update",)
    if missing == "review":
        history.checkpoint.review = None
    else:
        history.checkpoint.manifest.reviewed_source = None
    for refused in (
        operations.load_update(prepared.vault),
        operations.resume_update(prepared.vault),
    ):
        assert (refused.status, refused.code) == ("refused", "saved_update_unavailable")
        assert not refused.ready and refused.preparation is None
        assert refused.publication == "not_started"
    assert not loaded.ready and loaded.saved.plan == prepared.review


def test_resume_rejects_saved_payload_identity_before_reading_retained_source(
    monkeypatch,
):
    from brz2obsidian.core import load_review, save_review

    prepared = preparation()
    loaded = load_review(save_review(prepared.review).record.model_dump_json()).loaded
    history = recorded_history(
        prepared.review.facts.incoming_identity, prepared.locator
    )
    history.checkpoint.review = loaded
    changed = prepared.source_binding.files[0].model_copy(update={"sha256": "e" * 64})
    history.checkpoint.manifest.reviewed_source = prepared.source_binding.model_copy(
        update={
            "files": (changed,),
            "fingerprint": ReviewedSourceBinding.digest((changed,)),
        }
    )
    operations = Operations()
    monkeypatch.setattr(operations, "inspect_history", lambda vault: history)

    def no_payload(*args, **kwargs):
        raise AssertionError("Mismatched saved incoming bytes cannot read a baseline")

    monkeypatch.setattr(operations, "read_checkpoint_payload", no_payload)
    refused = operations.resume_update(prepared.vault)
    assert (refused.status, refused.code) == ("refused", "saved_payload_mismatch")
    assert refused.preparation is None and not refused.ready
    assert loaded.saved.plan.facts.subjects[0].incoming.data == b"incoming\n"


@pytest.mark.parametrize(
    "difference,expected_code",
    (
        ("unowned_incoming", "owned_payload_required"),
        ("changed_current_source", "source_payload_changed"),
        ("missing_saved_binding", "persisted_source_authority_required"),
        ("changed_saved_binding", "persisted_source_authority_required"),
    ),
)
def test_save_and_apply_reobserve_exact_incoming_authority_before_native_contact(
    tmp_path, monkeypatch, difference, expected_code
):
    import tempfile
    from pathlib import Path

    from brz2obsidian.application import SourceModuleBinding, Workflow
    from brz2obsidian.obsidian import ObsidianRenderer
    from brz2obsidian.publication import FilesystemPublisher
    from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule

    identity = request().incoming_identity.model_copy(
        update={"settings_digest": hashlib.sha256(b"{}").hexdigest()}
    )
    facts = request()
    established = facts.format_operation.established_baseline.model_copy(
        update={"identity": identity}
    )
    facts = facts.model_copy(
        update={
            "baseline_identity": identity,
            "incoming_identity": identity,
            "format_operation": facts.format_operation.model_copy(
                update={"established_baseline": established}
            ),
        }
    )
    policy = FOLIO_POLICY.model_copy(
        update={
            "module_version": "1",
            "profile_id": "reviewed-folio",
            "profile_version": "1",
        }
    )
    workflow = Workflow(
        SourceModuleBinding(FolioSourceModule(), policy),
        ObsidianRenderer(),
        FilesystemPublisher(),
    )
    operations = Operations(workflow=workflow)

    def forbidden_native(*args, **kwargs):
        raise AssertionError("Unbound incoming authority cannot capture or publish")

    monkeypatch.setattr(operations, "capture_checkpoint", forbidden_native)
    monkeypatch.setattr(operations, "apply_reviewed_update", forbidden_native)
    with tempfile.TemporaryDirectory(prefix="brz2obsidian-update-") as owned:
        incoming = Path(owned) / "incoming"
        (incoming / "Notes").mkdir(parents=True)
        note = incoming / "Notes/Opening.md"
        note.write_bytes(b"incoming\n")
        prepared = preparation(with_review_links(facts))
        binding = operations.observe_reviewed_source(incoming, prepared.review)
        prepared = prepared.model_copy(
            update={
                "vault": str(tmp_path),
                "payload_directory": str(incoming),
                "source_binding": binding,
            }
        )
        selected = operations.resolve_update(prepared, action(prepared.review))
        assert selected.code == "accepted" and selected.ready
        prepared = selected.preparation
        assert prepared.review.approvals[0].result.data == b"incoming\n"
        history = recorded_history(identity, prepared.locator)
        history.admission.preflight = preflight()
        history.checkpoint.manifest.reviewed_source = binding
        baseline = SourcePayloadFile(
            path="Notes/Opening.md",
            mode="100644",
            size=len(b"original\r\n"),
            sha256=hashlib.sha256(b"original\r\n").hexdigest(),
        )
        history.checkpoint.manifest.source = (baseline,)
        history.checkpoint.manifest.observed_source = prepared.observed_source
        monkeypatch.setattr(
            operations, "inspect_history", lambda *args, **kwargs: history
        )
        monkeypatch.setattr(
            operations,
            "read_checkpoint_payload",
            lambda *args, **kwargs: SimpleNamespace(
                status="available",
                chunks=(SimpleNamespace(path=baseline.path, data=b"original\r\n"),),
            ),
        )
        if difference == "unowned_incoming":
            foreign = tmp_path / "incoming"
            (foreign / "Notes").mkdir(parents=True)
            (foreign / "Notes/Opening.md").write_bytes(b"incoming\n")
            prepared = prepared.model_copy(update={"payload_directory": str(foreign)})
        elif difference == "changed_current_source":
            note.write_bytes(b"Changed after review.\n")
        elif difference == "missing_saved_binding":
            history.checkpoint.manifest.reviewed_source = None
        else:
            row = binding.files[0].model_copy(update={"sha256": "e" * 64})
            history.checkpoint.manifest.reviewed_source = binding.model_copy(
                update={
                    "files": (row,),
                    "fingerprint": ReviewedSourceBinding.digest((row,)),
                }
            )
        before = note.read_bytes()
        for refused in (
            operations.save_update(prepared),
            operations.apply_update(prepared),
        ):
            assert (refused.status, refused.code) == ("refused", expected_code)
            assert not refused.ready and refused.publication == "not_started"
        assert note.read_bytes() == before
        assert prepared.review.approvals[0].result.data == b"incoming\n"


@pytest.mark.parametrize("known_original", (True, False))
def test_saved_format_review_reopens_as_maintenance_and_blocks_ordinary_update(
    tmp_path, monkeypatch, known_original
):
    from pathlib import Path

    from brz2obsidian.application.checkpoint_contracts import CheckpointResult
    from brz2obsidian.core import load_review, save_review
    from tests.application.test_format_transition import transition_case
    from tests.support.recorded_format6 import CURRENT, FIXTURE, NOTE

    operations, vault, history = transition_case(
        tmp_path, monkeypatch, known_original=known_original
    )
    before = {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
    }
    offered = operations.prepare_format_transition(vault, FIXTURE / "source.brz")
    assert offered.preparation is not None and offered.kind == "format_transition"
    note = next(
        row for row in offered.preparation.review.proposal.changes if row.path == NOTE
    )
    kept = operations.resolve_update(
        offered.preparation,
        action(
            offered.preparation.review,
            note,
            domain="format",
            choice="current",
            decision_id="saved-format-current",
        ),
    )
    assert kept.code == "accepted"
    chosen = next(
        row
        for row in kept.preparation.review.approvals
        if row.decision_id == "saved-format-current"
    )
    assert chosen.result.data == CURRENT
    captured = []
    stored_source = {}

    def retain_description(vault_arg, source_arg, **values):
        # This declared native port retains descriptions for lifecycle routing;
        # no real checkpoint graph or file-publication claim follows.
        assert vault_arg == str(vault)
        source_root = Path(source_arg)
        stored_source.update(
            {
                path.relative_to(source_root).as_posix(): path.read_bytes()
                for path in source_root.rglob("*")
                if path.is_file()
            }
        )
        saved = save_review(values["review"])
        assert saved.status == "saved"
        loaded = load_review(saved.record.model_dump_json())
        assert loaded.status == "loaded" and not loaded.ready
        checkpoint = history.checkpoint
        checkpoint.review = loaded.loaded
        checkpoint.locator = checkpoint.locator.model_copy(
            update={"commit": "c" * 40, "generation": 2}
        )
        checkpoint.manifest.identity = values["identity"]
        checkpoint.manifest.boundary = "local"
        checkpoint.manifest.reviewed_source = values["source_binding"]
        checkpoint.manifest.observed_source = values["observed_source"]
        checkpoint.manifest.source = tuple(
            SourcePayloadFile(
                path=path,
                mode="100644",
                size=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
            for path, raw in sorted(stored_source.items())
        )
        captured.append(True)
        return CheckpointResult(
            schema_id="brz2obsidian.checkpoint-result",
            schema_version=1,
            status="captured",
            code="captured",
            commit="c" * 40,
            ref=checkpoint.locator.association.ref,
            history_retained=True,
            objects_written=True,
            object_storage="verified",
            authored_files_changed=False,
            message="Controlled saved-review port.",
            locator=checkpoint.locator,
        )

    monkeypatch.setattr(operations, "capture_checkpoint", retain_description)
    saved = operations.save_update(kept.preparation)
    assert saved.code == "saved" and captured == [True]
    assert saved.kind == "format_transition" and saved.checkpoint_commit == "c" * 40
    loaded = operations.load_update(vault)
    assert loaded.kind == "format_transition" and loaded.code == "revalidation_required"
    assert not loaded.ready and not loaded.loaded.ready

    def unopened_source(*args, **kwargs):
        raise AssertionError("Pending maintenance cannot start ordinary source access")

    with monkeypatch.context() as blocked_source:
        blocked_source.setattr(operations, "read_checkpoint_payload", unopened_source)
        blocked = operations.prepare_update(vault, "unopened-reference.brz")
    assert (blocked.status, blocked.code) == (
        "refused",
        "format_transition_review_required",
    )
    assert not blocked.ready and blocked.next_actions == ("resume_update",)
    monkeypatch.setattr(
        operations,
        "read_checkpoint_payload",
        lambda *args, **kwargs: SimpleNamespace(
            status="available",
            chunks=tuple(
                SimpleNamespace(path=path, data=raw)
                for path, raw in stored_source.items()
            ),
        ),
    )
    resumed = operations.resume_update(vault)
    assert resumed.kind == "format_transition" and resumed.preparation is not None
    assert resumed.code in ("unchanged", "refreshed")
    retained = next(
        row
        for row in resumed.preparation.review.approvals
        if row.decision_id == "saved-format-current"
    )
    assert retained.result.data == CURRENT
    assert resumed.preparation.review.facts.baseline_identity.output_format == 6
    assert resumed.preparation.review.facts.incoming_identity.output_format == 7
    assert not resumed.ready and captured == [True]
    assert {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
    } == before


@pytest.mark.parametrize(
    "changed",
    (
        "recovery_required",
        "incomplete_inventory",
        "unknown_history",
        "unowned_payload",
        "invalid_saved_actions",
        "changed_generated_payload",
        "changed_source_reference",
        "missing_persisted_authority",
    ),
)
def test_onboarding_save_rechecks_current_authority_before_any_checkpoint(
    tmp_path, monkeypatch, changed
):
    import json
    import shutil
    from pathlib import Path

    from tests.application.test_onboarding import legacy_inputs

    operations, vault, source, authored = legacy_inputs(tmp_path, monkeypatch)
    before = {path.name: path.read_bytes() for path in vault.iterdir()}
    original_source = source.read_bytes()

    def no_native_write(*args, **kwargs):
        raise AssertionError("Unqualified onboarding must not capture or publish")

    monkeypatch.setattr(operations, "capture_checkpoint", no_native_write)
    monkeypatch.setattr(operations, "apply_reviewed_update", no_native_write)
    offered = operations.prepare_onboarding(vault, source)
    assert offered.preparation is not None and offered.kind == "onboarding"
    prepared = offered.preparation
    assert prepared.locator is None and not prepared.review.ready
    assert all(
        row.baseline.status == "unknown" for row in prepared.review.facts.subjects
    )
    # Valid current source/vault facts reach the public before-snapshot boundary.
    cancelled = operations.save_update(prepared, cancel=lambda: True)
    assert (cancelled.status, cancelled.code) == (
        "cancelled_before_publication",
        "cancelled_before_snapshot",
    )
    assert cancelled.kind == "onboarding" and not cancelled.ready
    assert cancelled.publication == "not_published"
    assert source.read_bytes() == original_source
    assert {path.name: path.read_bytes() for path in vault.iterdir()} == before
    history = operations.inspect_history(vault)
    if changed == "recovery_required":
        history.admission.status = "recovery_first"
        history.admission.recovery_gaps = ("Personal.bin",)
    elif changed == "incomplete_inventory":
        history.admission.inventory_complete = False
    elif changed == "unknown_history":
        history.status = "unavailable"
    elif changed == "unowned_payload":
        foreign = tmp_path / "foreign" / "incoming"
        shutil.copytree(prepared.payload_directory, foreign)
        prepared = prepared.model_copy(update={"payload_directory": str(foreign)})
    elif changed == "invalid_saved_actions":
        stale = action(
            prepared.review,
            domain="format",
            choice="current",
            expected_generation=prepared.review.proposal.generation + 1,
        )
        review = prepared.review.model_copy(
            update={
                "history": prepared.review.history.model_copy(
                    update={"events": prepared.review.history.events + (stale,)}
                )
            }
        )
        prepared = prepared.model_copy(update={"review": review})
    elif changed == "changed_generated_payload":
        (Path(prepared.payload_directory) / "Home \u2014 Opening.md").write_bytes(
            b"Unreviewed generated replacement.\n"
        )
    elif changed == "changed_source_reference":
        data = json.loads(source.read_bytes())
        data["entries"][0]["title"] = "Changed after preparation"
        source.write_text(json.dumps(data))
    else:
        prepared = prepared.model_copy(update={"source_ref": None})
    expected_source = source.read_bytes()
    expected_incoming = {
        path.relative_to(prepared.payload_directory).as_posix(): path.read_bytes()
        for path in Path(prepared.payload_directory).rglob("*")
        if path.is_file()
    }
    result = operations.save_update(prepared)
    if changed == "recovery_required":
        assert (result.status, result.code) == ("recovery_required", "recovery_first")
        assert result.next_actions == ("review_recovery",)
        assert result.recovery_gaps == ("Personal.bin",)
    else:
        assert (result.status, result.code) == (
            "refused",
            "current_onboarding_unavailable",
        )
    assert result.kind == "onboarding" and not result.ready
    assert result.publication == "not_started"
    assert source.read_bytes() == expected_source
    assert (vault / "Home \u2014 Opening.md").read_bytes() == authored
    assert (vault / "Personal.bin").read_bytes() == b"\x00\xffprivate\r\n"
    assert {path.name: path.read_bytes() for path in vault.iterdir()} == before
    assert {
        path.relative_to(prepared.payload_directory).as_posix(): path.read_bytes()
        for path in Path(prepared.payload_directory).rglob("*")
        if path.is_file()
    } == expected_incoming
