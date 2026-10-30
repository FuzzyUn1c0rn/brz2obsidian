"""Generated category and template restoration through the shared public producer."""

import json
from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import requirement_digest
from brz2obsidian.application.update_facts import (
    assemble_facts,
    output_identity,
    record,
)
from brz2obsidian.contracts import SourceIdentity
from brz2obsidian.core import (
    inspect_review_choices,
    load_review,
    save_review,
    select_review_effects,
)
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.application.test_update_context import worker_context_call
from tests.application.test_update_lifecycle_contracts import preparation

CATEGORY_PATH = "Categories/Native category.md"
TEMPLATE_PATH = "Templates/Native category.md"
CATEGORY_ID = "77777777-7777-4777-8777-777777777777"
CATEGORY = b"""---
categories: []
appearance_category:
icon:
created: 2026-10-03
updated:
tags:
  - "categories"
aliases: []
source_collection_id: "11111111-1111-4111-8111-111111111111"
source_item_id: "77777777-7777-4777-8777-777777777777"
---

# Native category

## Members

![[Templates/Bases/Members.base#Members]]

## Gallery

![[Templates/Bases/Gallery.base#Gallery]]

"""
TEMPLATE = b"""---
categories:
  - "[[Categories/Native category.md]]"
appearance_category: "[[Categories/Native category.md]]"
icon:
created: "{{date:YYYY-MM-DD}}"
updated: "{{date:YYYY-MM-DD}}"
tags: []
aliases: []
---

# {{title}}
"""
EDIT_PREFIX = b"""---
source_collection_id: "11111111-1111-4111-8111-111111111111"
source_item_id: "independent"
---
"""
EDITED = EDIT_PREFIX + b"Independently accepted writing.\r\n"


def support_restoration_payloads():
    # Category/template bytes are literal generated format-7 examples. The
    # category contains the same two named Base embeds as the native refusal.
    record = {
        "schema": "brz2obsidian.migration",
        "schema_version": 7,
        "profile_id": "thebrain-format5-reviewed",
        "profile_version": "10",
        "source_identity": {
            "source_id": "11111111-1111-4111-8111-111111111111",
            "module_id": "thebrain-brz",
            "module_version": "10",
            "format_version": "5",
            "source_sha256": "c" * 64,
            "snapshot_digest": "d" * 64,
        },
        "item_targets": [
            {
                "original_identity": CATEGORY_ID,
                "original_title": "Native category",
                "relative_path": CATEGORY_PATH,
                "created": True,
                "creation_reasons": ["definition"],
            },
            {
                "original_identity": "independent",
                "original_title": "Independent",
                "relative_path": "Notes/Independent.md",
                "created": True,
                "creation_reasons": ["content"],
            },
        ],
        "asset_targets": [],
        "source_gaps": [],
    }
    baseline = {
        "migration-record.json": json.dumps(record).encode(),
        CATEGORY_PATH: CATEGORY.replace(b"# Native category\n", b"# Old category\n"),
        TEMPLATE_PATH: TEMPLATE.replace(b"# {{title}}\n", b"# Old starter\n"),
        "Templates/Bases/Members.base": b"views:\n  - type: table\n    name: Members\n",
        "Templates/Bases/Gallery.base": b"views:\n  - type: cards\n    name: Gallery\n",
        "Notes/Independent.md": EDIT_PREFIX + b"Original writing.\n",
    }
    incoming = baseline | {
        CATEGORY_PATH: CATEGORY,
        TEMPLATE_PATH: TEMPLATE,
        "Notes/Independent.md": EDIT_PREFIX + b"Incoming writing.\n",
    }
    current = {
        path: raw
        for path, raw in baseline.items()
        if path not in (CATEGORY_PATH, TEMPLATE_PATH)
    } | {"Notes/Independent.md": EDIT_PREFIX + b"Local writing.\n"}
    return baseline, incoming, current


def support_restoration_preparation():
    baseline, incoming, current = support_restoration_payloads()
    facts = assemble_facts(
        baseline,
        incoming,
        current,
        proposal_id="review:support-restoration",
        generation=1,
    )
    return preparation(facts)


def choose_path(prepared, path, choice, *, edited=None):
    change = next(c for c in prepared.review.proposal.changes if c.target_path == path)
    offer = next(
        r
        for r in inspect_review_choices(prepared.review)
        if r.change_id == change.change_id
    )
    return Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice=choice,
        assumptions_digest=requirement_digest(offer),
        edited=edited,
    )


def test_public_category_and_template_restore_exact_incoming_and_retain_review_gate():
    prepared = support_restoration_preparation()
    assert len(prepared.review.requirements) == 3 and not prepared.review.ready
    edited = choose_path(prepared, "Notes/Independent.md", "edited", edited=EDITED)
    assert edited.code == "accepted", edited.code
    retained = edited.preparation.review.approvals[0]
    template = choose_path(edited.preparation, TEMPLATE_PATH, "restore_incoming")
    assert template.code == "accepted", template.code
    assert not template.ready and template.unresolved == 1
    approval = template.preparation.review.approvals[-1]
    assert approval.target_path == "Templates/Native category.md"
    assert approval.result.data == TEMPLATE and approval.source_accepted
    candidate = template.preparation.review.actions[-1].candidate
    assert candidate.identity.item_id == "support:Templates/Native category.md"
    assert all(p.identity_component is None for p in candidate.document.properties)
    membership = next(p for p in candidate.document.properties if p.key == "categories")
    assert membership.targets[0].identity.item_id == CATEGORY_ID
    assert membership.targets[0].canonical_path == "Categories/Native category.md"
    restored = choose_path(template.preparation, CATEGORY_PATH, "restore_incoming")
    assert restored.code == "accepted", restored.code
    assert restored.ready and restored.unresolved == 0
    assert restored.publication == "not_started" and restored.application is None
    plan = restored.preparation.review
    assert plan.approvals[0] == retained and retained.result.data == EDITED
    approval = plan.approvals[-1]
    assert approval.target_path == "Categories/Native category.md"
    assert approval.result.data == CATEGORY and approval.source_accepted
    candidate = plan.actions[-1].candidate
    assert candidate.identity.item_id == CATEGORY_ID
    assert [
        (o.meaning.status, o.meaning.path, o.meaning.fragment.value)
        for o in candidate.links.occurrences
    ] == [
        ("resolved", "Templates/Bases/Members.base", "Members"),
        ("resolved", "Templates/Bases/Gallery.base", "Gallery"),
    ]
    effects = select_review_effects(plan)
    assert effects.status == "selected", effects.code
    files = {row.path: row.content.data for row in effects.files}
    assert files[CATEGORY_PATH] == CATEGORY
    assert files[TEMPLATE_PATH] == TEMPLATE
    assert files["Notes/Independent.md"] == EDITED
    assert effects.remove_paths == ()


def test_saved_old_base_facts_resume_through_closed_worker_without_losing_edited_choice(
    tmp_path,
):
    from hashlib import sha256

    from brz2obsidian.application.checkpoint_contracts import CheckpointRead
    from brz2obsidian.application.source_payload_contracts import SourcePayloadFile
    from brz2obsidian.application.update_context import UpdateContext
    from brz2obsidian.application.vault_contracts import VaultFile
    from brz2obsidian.publication.vault_native import observe_file

    baseline, incoming, current = support_restoration_payloads()
    vault, source = tmp_path / "vault", tmp_path / "incoming"
    for root, payload in ((vault, current), (source, incoming)):
        for path, raw in payload.items():
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
    inventory = []
    for path in sorted(current):
        info, digest, _, physical = observe_file(vault, vault / path, prefix_limit=0)
        inventory.append(
            VaultFile(
                path=path,
                mode="100644",
                size=info.st_size,
                sha256=digest,
                identity=physical,
                tracked=True,
                excluded=False,
                exclusion=None,
            )
        )
    facts = assemble_facts(
        baseline,
        incoming,
        current,
        proposal_id="review:old-base-resume",
        generation=1,
        current_inventory=tuple(inventory),
    )
    context = facts.link_context

    def old_states(states, targets):
        base_ids = {
            t.target_id for t in targets if (t.canonical_path or "").endswith(".base")
        }
        return tuple(
            interpret_link_target(
                state.content,
                target_id=state.target_id,
                existence=state.existence,
                memberships=state.memberships,
                membership_targets=targets,
            )
            if state.target_id in base_ids
            else state
            for state in states
        )

    # The historical public interpreter had no media path. Its exact Base
    # observations have no anchors; save a canonical review of those facts.
    old_current = old_states(context.current_target_facts, context.current_targets)
    old_incoming = old_states(context.incoming_target_facts, context.incoming_targets)
    legacy_context = context.model_copy(
        update={
            "current_target_facts": old_current,
            "incoming_target_facts": old_incoming,
            "incoming_documents": tuple(
                interpret_links(
                    row.content,
                    document_id=row.document_id,
                    source_path=row.source_path,
                    path_mode=row.path_mode,
                    targets=context.incoming_targets,
                    target_facts=old_incoming,
                    inventory="complete",
                )
                for row in context.incoming_documents
            ),
        }
    )
    category = next(
        row
        for row in legacy_context.incoming_documents
        if row.source_path == CATEGORY_PATH
    )
    assert [o.meaning.status for o in category.occurrences] == [
        "fragment_missing",
        "fragment_missing",
    ]
    prepared = preparation(facts.model_copy(update={"link_context": legacy_context}))
    edited = choose_path(prepared, "Notes/Independent.md", "edited", edited=EDITED)
    assert edited.code == "accepted", edited.code
    prepared = edited.preparation
    retained = prepared.review.approvals[0]
    saved = save_review(prepared.review)
    assert saved.status == "saved", saved.code
    loaded = load_review(saved.record.model_dump_json())
    assert loaded.status == "loaded", loaded.code
    binding = Operations().observe_reviewed_source(source, prepared.review)
    baseline_rows = tuple(
        SourcePayloadFile(
            path=path, mode="100644", size=len(raw), sha256=sha256(raw).hexdigest()
        )
        for path, raw in sorted(baseline.items())
    )

    class SavedInputs(Operations):
        # Only observed history/checkpoint/input ports are controlled. Resume,
        # fresh assembly, canonical replay, Context and closed worker are real.
        def inspect_history(self, *args, **kwargs):
            return SimpleNamespace(
                status="intact",
                admission=SimpleNamespace(
                    vault=str(vault),
                    status="supported",
                    inventory=tuple(inventory),
                    inventory_complete=True,
                    preflight=prepared.review.preflight,
                    findings=(),
                    recovery_gaps=(),
                    repository=SimpleNamespace(kind="root"),
                ),
                checkpoint=SimpleNamespace(
                    status="valid",
                    locator=prepared.locator,
                    review=loaded.loaded,
                    manifest=SimpleNamespace(
                        boundary="local",
                        identity=output_identity(record(baseline)),
                        source=baseline_rows,
                        reviewed_source=binding,
                        observed_source=SourceIdentity.model_validate(
                            record(incoming)["source_identity"]
                        ),
                    ),
                ),
            )

        def inspect_update_inputs(self, path):
            assert path == str(vault)
            return nullcontext(
                SimpleNamespace(
                    history=self.inspect_history(),
                    read_payload=self.read_checkpoint_payload,
                    inspect=self.inspect_history,
                )
            )

        def read_checkpoint_payload(self, **kwargs):
            return SimpleNamespace(
                status="available",
                chunks=tuple(
                    SimpleNamespace(path=path, data=raw)
                    for path, raw in baseline.items()
                ),
            )

        def read_checkpoint(self, path, **kwargs):
            assert path == str(vault)
            return CheckpointRead(
                schema_id="brz2obsidian.checkpoint-read",
                schema_version=1,
                status="valid",
                code="controlled_current",
                locator=prepared.locator,
                manifest=None,
                review=None,
                message="Controlled saved checkpoint",
            )

        def capture_checkpoint(self, *args, **kwargs):
            raise AssertionError("Review restoration must not Save automatically")

        def apply_reviewed_update(self, *args, **kwargs):
            raise AssertionError("Review restoration must not publish automatically")

    producer = UpdateContext(operations=SavedInputs())
    resumed = worker_context_call(
        producer,
        {"command": "resume", "vault": str(vault), "selection_id": str(uuid4())},
    )
    assert resumed.binding is not None, resumed.code
    assert not resumed.ready and resumed.unresolved == 2 and resumed.stale == 0
    previous = resumed
    for index, (path, expected) in enumerate(
        ((CATEGORY_PATH, CATEGORY), (TEMPLATE_PATH, TEMPLATE))
    ):
        page = worker_context_call(
            producer, {"command": "page", "binding": previous.binding}
        )
        row = next(r for r in page.page.items if r.current_path == path)
        offer = next(r for r in page.offers if r.change_id == row.change_id)
        chosen = worker_context_call(
            producer,
            {
                "command": "choose",
                "binding": previous.binding,
                "requirement_id": offer.requirement_id,
                "choice": "restore_incoming",
                "assumptions_digest": offer.assumptions_digest,
            },
        )
        assert chosen.code == "accepted", chosen.code
        assert chosen.ready == (index == 1) and chosen.unresolved == 1 - index
        assert chosen.publication == "not_started"
        if index == 0:
            stale = worker_context_call(
                producer,
                {
                    "command": "choose",
                    "binding": previous.binding,
                    "requirement_id": offer.requirement_id,
                    "choice": "restore_incoming",
                    "assumptions_digest": offer.assumptions_digest,
                },
            )
            assert stale.code == "context_changed" and not stale.ready
        page = worker_context_call(
            producer, {"command": "page", "binding": chosen.binding}
        )
        assert (
            next(r for r in page.page.items if r.current_path == path).result
            == expected
        )
        assert (
            next(
                r for r in page.page.items if r.current_path == "Notes/Independent.md"
            ).result
            == retained.result.data
            == EDITED
        )
        previous = chosen
    assert {path: (vault / path).read_bytes() for path in current} == current
    assert not (vault / CATEGORY_PATH).exists() and not (vault / TEMPLATE_PATH).exists()
