"""Cross-document prose versions and authentic saved-review compatibility."""

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_offers import choice_offers
from brz2obsidian.contracts import ExactContent, LinkContext
from brz2obsidian.core import save_review, select_review_effects
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.application.test_update_attachment_memberships import (
    EDIT_PATH,
    EDIT_PREFIX,
    membership_preparation,
)
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_attachments import target_for_links
from tests.reconciliation.test_identity import with_subjects
from tests.reconciliation.test_refresh import two_items

OLD_RECORD = (
    Path(__file__).parents[1] / "fixtures/saved_reviews/note-proof-ccc807a.json"
)

HOME_OLD = EDIT_PREFIX + b"# Shared\r\nOld home prose.\r\n^native\r\n"
HOME_EDITED = EDIT_PREFIX + b"# Shared\r\nEdited home prose.\r\n^native\r\n"
HOME_INCOMING = EDIT_PREFIX + b"# Shared\r\nIncoming home prose.\r\n^native\r\n"
MANUAL = (
    b"Map [[Assets/data.bin|Current]] ![[Assets/data.bin|Incoming]].\r\n"
    b"Home [[Notes/Independent.md|Home]] [[Notes/Independent.md#Shared]] "
    b"[[Notes/Independent.md#^native]] [Home](Independent.md#Shared).\r\n"
    b"Existing [[Missing.md]] [[Absent.md]].\r\n"
)
FINAL_MANUAL = (
    b"Map [[Assets/data.bin|Current]] ![[Assets/data (incoming-ba7816bf).bin|Incoming]].\r\n"
    b"Home [[Notes/Independent.md|Home]] [[Notes/Independent.md#Shared]] "
    b"[[Notes/Independent.md#^native]] [Home](Independent.md#Shared).\r\n"
    b"Existing [[Missing.md]] [[Absent.md]].\r\n"
)


def cross_document_preparation(*, home_current=HOME_OLD):
    facts = membership_preparation("both")[0].review.facts
    context = facts.link_context
    home = facts.subjects[1].model_copy(
        update={
            "current": facts.subjects[1].current.model_copy(
                update={"content": ExactContent(data=home_current)}
            ),
            "incoming": ExactContent(data=HOME_INCOMING),
            "title": "Home",
        }
    )
    second_facts = two_items()
    second, entry = second_facts.subjects[1], second_facts.identity_inventory[1]
    subjects = (facts.subjects[0], home, second)
    inventory = tuple(
        row.model_copy(
            update={
                "current": row.current.model_copy(
                    update={
                        "content": ExactContent(
                            data=MANUAL
                            if row.current.path == "Notes/Owner.md"
                            else home_current
                        )
                    }
                )
            }
        )
        if row.current.path in ("Notes/Owner.md", EDIT_PATH)
        else row
        for row in facts.identity_inventory
    ) + (entry,)
    facts = with_subjects(facts, subjects, inventory)
    extra = target_for_links("review:second", second.current.path).model_copy(
        update={"identity": entry.identity}
    )
    targets = context.current_targets + (extra,)

    def states(rows, home_raw, second_content):
        return tuple(
            interpret_link_target(
                ExactContent(data=home_raw),
                target_id=row.target_id,
                existence="present",
                memberships=(),
                membership_targets=targets,
            )
            if row.target_id == "independent-note"
            else interpret_link_target(
                ExactContent(data=MANUAL),
                target_id=row.target_id,
                existence="present",
                memberships=(),
                membership_targets=targets,
            )
            if row.target_id == "owner:note"
            else row
            for row in rows
        ) + (
            interpret_link_target(
                second_content,
                target_id=extra.target_id,
                existence="present",
                memberships=(),
            ),
        )

    old = states(context.current_target_facts, home_current, second.current.content)
    new = states(context.incoming_target_facts, HOME_INCOMING, second.incoming)

    def documents(rows, home_raw, target_states, second_content):
        values = tuple(
            (
                row.document_id,
                row.source_path,
                HOME_OLD
                if row.source_path == EDIT_PATH and home_raw == HOME_OLD
                else home_raw
                if row.source_path == EDIT_PATH
                else MANUAL
                if row.source_path == "Notes/Owner.md"
                else row.content.data,
            )
            for row in rows
        )
        values += ((extra.target_id, second.current.path, second_content.data),)
        return tuple(
            interpret_links(
                ExactContent(data=raw),
                document_id=key,
                source_path=path,
                path_mode="vault",
                targets=targets,
                target_facts=target_states,
                inventory="complete",
            )
            for key, path, raw in values
        )

    facts = facts.model_copy(
        update={
            "link_context": LinkContext(
                schema_id="brz2obsidian.link-context",
                schema_version=1,
                inventory="complete",
                current_targets=targets,
                incoming_targets=targets,
                current_target_facts=old,
                incoming_target_facts=new,
                current_documents=documents(
                    context.current_documents, home_current, old, second.current.content
                ),
                incoming_documents=documents(
                    context.incoming_documents, HOME_INCOMING, new, second.incoming
                ),
            )
        }
    )
    return preparation(type(facts).model_validate(facts.model_dump()))


def choose(prepared, domain, choice, *, item_id=None, edited=None, references=()):
    offer = next(
        row
        for row in choice_offers(prepared)
        if row.domain == domain
        and (
            item_id is None
            or next(
                c
                for c in prepared.review.proposal.changes
                if c.change_id == row.change_id
            ).item_id
            == item_id
        )
    )
    result = Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        assumptions_digest=offer.assumptions_digest,
        choice=choice,
        edited=edited,
        references=references,
    )
    assert result.code == "accepted", result.code
    return result.preparation


def cross_document_review(*, edited=HOME_EDITED, prepared=None):
    from brz2obsidian.application.review_choices import attachment_reference_page

    prepared = choose(
        cross_document_preparation() if prepared is None else prepared,
        "text",
        "current",
        item_id="entry:second",
    )
    prepared = choose(
        prepared, "text", "edited", item_id="entry:independent", edited=edited
    )
    offer = next(row for row in choice_offers(prepared) if row.domain == "attachment")
    refs, total, following = attachment_reference_page(prepared, offer.requirement_id)
    assert total == 2 and following is None
    return choose(
        prepared,
        "attachment",
        "both",
        references=tuple(
            {
                "reference_id": row.reference_id,
                "choice": "use_secondary"
                if row.old.display_text == "Incoming"
                else "keep_current",
            }
            for row in refs
        ),
    ).review


def test_cross_document_edited_home_preserves_unrelated_note_references(tmp_path):
    plan = cross_document_review()
    saved = save_review(plan)
    assert saved.status == "saved", saved.code
    artifact = tmp_path / "authentic-saved-review.json"
    artifact.write_bytes(saved.record.model_dump_json().encode("utf-8"))
    print("AUTHENTIC_OLD_REVIEW:", artifact)
    assert plan.ready, plan.blockers
    selected = select_review_effects(plan)
    assert selected.status == "selected", selected.code
    assert {row.path: row.content.data for row in selected.files} == {
        "Assets/data.bin": b"\x00authored",
        "Assets/data (incoming-ba7816bf).bin": b"abc",
        EDIT_PATH: HOME_EDITED,
        "Notes/Owner.md": FINAL_MANUAL,
        "Notes/Second.md": b"original\r\n",
    }
    assert selected.remove_paths == ()
    manual = next(
        d
        for d in plan.facts.link_context.current_documents
        if d.source_path == "Notes/Owner.md"
    )
    assert [o.meaning.status for o in manual.occurrences[-2:]] == ["missing", "missing"]


def saved_payload_port(tmp_path, saved, *, boundary="local", proposed=False):
    """Declared external cat-file bytes; the real blob verifier and reader run."""
    from brz2obsidian.application.checkpoint_contracts import (
        CheckpointFile,
        CheckpointManifest,
    )
    from brz2obsidian.publication.vault_history import _review_shape

    envelope, payloads = _review_shape(saved)

    def oid(raw):
        return hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
        ).hexdigest()

    rows = tuple(
        CheckpointFile(
            path=sha, mode="100644", size=len(raw), sha256=sha, object_id=oid(raw)
        )
        for sha, raw in sorted(payloads.items())
    )
    blobs = {row.object_id: payloads[row.sha256].hex() for row in rows}
    blobs[oid(envelope)] = envelope.hex()
    declaration = tmp_path / "declared-blobs.json"
    declaration.write_text(json.dumps(blobs), encoding="utf-8")
    server = (
        "import json,sys;from pathlib import Path;"
        "objects=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));"
        "out=sys.stdout.buffer\n"
        "for line in sys.stdin.buffer:\n"
        " key=line.strip().decode('ascii');raw=bytes.fromhex(objects[key]);"
        "out.write((key+' blob '+str(len(raw))+'\\n').encode()+raw+b'\\n');out.flush()\n"
    )
    git = SimpleNamespace(
        prefix=[sys.executable, "-c", server, str(declaration)],
        env=dict(os.environ),
        inspection=SimpleNamespace(temporary_base=lambda: tmp_path),
    )
    proposal = (
        (rows[0].model_copy(update={"path": "proposed.bin"}),) if proposed else ()
    )
    remaining = rows[1:] if proposed else rows
    manifest = CheckpointManifest(
        schema_id="brz2obsidian.checkpoint-manifest",
        schema_version=1,
        association_id="a" * 64,
        generation=1,
        boundary=boundary,
        identity=saved.plan.facts.incoming_identity,
        source=(),
        vault=(),
        preimage=(),
        proposed=proposal,
        review_content=remaining,
        recovery_gaps=(),
        semantic_fingerprint="payload-test-only",
        policy_fingerprint="b" * 64,
        policy_continuity_fingerprint="c" * 64,
        previous=None,
        review_object=oid(envelope),
        review_size=len(envelope),
        review_sha256=hashlib.sha256(envelope).hexdigest(),
    )
    return git, manifest, envelope, declaration


def test_verified_old_local_review_reconstructs_then_requires_current_recheck(tmp_path):
    from brz2obsidian.contracts import SavedReview
    from brz2obsidian.core import load_review, resume_review
    from brz2obsidian.publication.vault_history import read_checkpoint_review

    raw = OLD_RECORD.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "5b2fc083d56166871c188a104547f2c33396399377467020079cfc40969cee20"
    )
    old = SavedReview.model_validate_json(raw)
    assert (
        old.plan.blockers == ("selected_link_context_conflict",) and not old.plan.ready
    )
    assert load_review(raw).status == "refused"
    git, manifest, _envelope, declaration = saved_payload_port(tmp_path, old)
    before = declaration.read_bytes()
    verified = set()
    loaded, references = read_checkpoint_review(git, manifest, verified)
    assert not loaded.ready and loaded.readiness == "revalidation_required"
    assert loaded.saved.plan.history == old.plan.history
    assert loaded.saved.plan.actions == old.plan.actions
    assert loaded.saved.plan.approvals == old.plan.approvals
    assert loaded.saved.plan.model_dump(
        exclude={"ready", "readiness", "blockers"}
    ) == old.plan.model_dump(exclude={"ready", "readiness", "blockers"})
    assert references == {row.sha256 for row in manifest.review_content}
    assert verified == {row.object_id for row in manifest.review_content}
    resumed = resume_review(loaded, old.plan.facts, preflight=old.plan.preflight)
    assert resumed.status == "resumed" and resumed.ready
    selected = select_review_effects(resumed.plan)
    assert selected.status == "selected", selected.code
    assert {row.path: row.content.data for row in selected.files} == {
        "Assets/data.bin": b"\x00authored",
        "Assets/data (incoming-ba7816bf).bin": b"abc",
        EDIT_PATH: HOME_EDITED,
        "Notes/Owner.md": FINAL_MANUAL,
        "Notes/Second.md": b"original\r\n",
    }
    assert selected.remove_paths == ()
    assert OLD_RECORD.read_bytes() == raw and declaration.read_bytes() == before
    changed = cross_document_preparation(
        home_current=EDIT_PREFIX + b"Externally changed, without anchors.\r\n"
    ).review
    rechecked = resume_review(
        loaded,
        changed.facts.model_copy(update={"generation": 2}),
        preflight=changed.preflight,
    )
    assert rechecked.status == "resumed" and not rechecked.ready
    assert old.plan.approvals[0] in rechecked.plan.approvals
    assert old.plan.approvals[1] not in rechecked.plan.approvals
    assert select_review_effects(rechecked.plan).status == "refused"


@pytest.mark.parametrize(
    "edited",
    (
        EDIT_PREFIX + b"# Renamed\r\nEdited home prose.\r\n^native\r\n",
        EDIT_PREFIX + b"# Shared\r\nEdited home prose without block.\r\n",
    ),
)
def test_note_prose_renewal_does_not_waive_missing_heading_or_block(edited):
    plan = cross_document_review(edited=edited)
    assert not plan.ready and "selected_link_context_conflict" in plan.blockers
    assert select_review_effects(plan).status == "refused"


@pytest.mark.parametrize(
    "kind", ("approval", "history", "facts", "requirements", "other-cache")
)
def test_verified_note_cache_refuses_other_field_or_history_changes(tmp_path, kind):
    from brz2obsidian.contracts import SavedReview
    from brz2obsidian.publication.vault_history import read_checkpoint_review

    saved = SavedReview.model_validate_json(OLD_RECORD.read_bytes())
    plan = saved.plan
    if kind == "approval":
        plan = plan.model_copy(
            update={
                "approvals": (
                    plan.approvals[0].model_copy(
                        update={"target_path": "Unreviewed.md"}
                    ),
                )
                + plan.approvals[1:]
            }
        )
    elif kind == "history":
        event = plan.history.events[-1].model_copy(update={"expected_generation": 99})
        plan = plan.model_copy(
            update={
                "history": plan.history.model_copy(
                    update={"events": plan.history.events + (event,)}
                )
            }
        )
    elif kind == "facts":
        plan = plan.model_copy(
            update={"facts": plan.facts.model_copy(update={"proposal_id": "forged"})}
        )
    elif kind == "requirements":
        plan = plan.model_copy(
            update={
                "requirements": cross_document_preparation().review.requirements[:1]
            }
        )
    else:
        plan = plan.model_copy(update={"blockers": ("unrelated-cache",)})
    git, manifest, _, _ = saved_payload_port(
        tmp_path, saved.model_copy(update={"plan": plan})
    )
    with pytest.raises(OSError, match="Saved S1 review"):
        read_checkpoint_review(git, manifest, set())


@pytest.mark.parametrize(
    "boundary,proposed", (("prepared", False), ("result", False), ("local", True))
)
def test_note_cache_compatibility_is_limited_to_empty_local_memos(
    tmp_path, boundary, proposed
):
    from brz2obsidian.contracts import SavedReview
    from brz2obsidian.publication.vault_history import read_checkpoint_review

    old = SavedReview.model_validate_json(OLD_RECORD.read_bytes())
    git, manifest, _, _ = saved_payload_port(
        tmp_path, old, boundary=boundary, proposed=proposed
    )
    with pytest.raises(OSError, match="Saved S1 review"):
        read_checkpoint_review(git, manifest, set())


def test_current_nonready_local_record_loads_exactly_without_readiness_authority(
    tmp_path,
):
    from brz2obsidian.core import resume_review
    from brz2obsidian.publication.vault_history import read_checkpoint_review

    plan = cross_document_preparation().review
    saved = save_review(plan)
    assert saved.status == "saved" and not plan.ready and plan.requirements
    git, manifest, _, _ = saved_payload_port(tmp_path, saved.record)
    loaded, _ = read_checkpoint_review(git, manifest, set())
    assert loaded.saved.plan == plan and not loaded.ready
    assert loaded.historical_effects.status == "refused"
    rechecked = resume_review(loaded, plan.facts, preflight=plan.preflight)
    assert rechecked.status == "resumed" and not rechecked.ready


def test_note_prose_renewal_does_not_redirect_an_old_manual_lookup():
    prepared = cross_document_preparation()
    facts = prepared.review.facts
    home = facts.subjects[1].model_copy(
        update={
            "path": "Moved/Home.md",
            "source_target": facts.subjects[1].source_target.model_copy(
                update={"normalized_path": "moved/home.md"}
            ),
        }
    )
    context = facts.link_context
    targets = tuple(
        row.model_copy(
            update={
                "canonical_path": home.path,
                "representations": (home.path,),
                "target": home.source_target,
            }
        )
        if row.target_id == "independent-note"
        else row
        for row in context.incoming_targets
    )
    incoming = tuple(
        interpret_links(
            row.content,
            document_id=row.document_id,
            source_path=home.path
            if row.document_id == "independent-note"
            else row.source_path,
            path_mode=row.path_mode,
            targets=targets,
            target_facts=context.incoming_target_facts,
            inventory=context.inventory,
        )
        for row in context.incoming_documents
    )
    facts = facts.model_copy(
        update={
            "subjects": (facts.subjects[0], home, facts.subjects[2]),
            "link_context": context.model_copy(
                update={"incoming_targets": targets, "incoming_documents": incoming}
            ),
        }
    )
    prepared = choose(
        preparation(facts), "rename", "source_path", item_id="entry:independent"
    )
    plan = cross_document_review(prepared=prepared)
    assert not plan.ready and "selected_link_context_conflict" in plan.blockers
    assert select_review_effects(plan).status == "refused"
