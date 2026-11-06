"""Existing canonical video output is editable without approving arbitrary HTML."""

import json

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import (
    attachment_references,
    requirement_digest,
)
from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.contracts import ExactContent
from brz2obsidian.core import inspect_review_choices, select_review_effects
from brz2obsidian.obsidian import interpret_links
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_resolution import action
from tests.reconciliation.test_type_tag_dependencies import graph_payload, note

PLAYER = (
    '<iframe src="https://www.youtube.com/embed/SYNTHVID001?start=0" '
    'width="560" height="315" title="YouTube video player" '
    'frameborder="0" allowfullscreen></iframe>'
)


def test_player_dialect_keeps_default7_exact_and_output8_external_meaning():
    uri = "https://www.youtube.com/watch?list=original%2Fcontext&v=SYNTHVID001&index=00"
    raw = f"[Original resource](<{uri}>)\n{PLAYER}\n".encode()
    options = {
        "content": ExactContent(data=raw),
        "document_id": "authored",
        "source_path": "Local.md",
        "path_mode": "vault",
        "targets": (),
        "target_facts": (),
        "inventory": "complete",
    }
    default = interpret_links(**options)
    explicit7 = interpret_links(**options, output_format=7)
    current8 = interpret_links(**options, output_format=8)
    assert default.model_dump_json() == explicit7.model_dump_json()
    assert (
        default.issues == ("link_syntax_unsupported",)
        and default.status == "unsupported"
    )
    assert current8.status == "supported" and current8.issues == ()
    assert current8.content.data == raw
    assert current8.occurrences == default.occurrences
    assert len(current8.occurrences) == 1
    occurrence = current8.occurrences[0]
    assert occurrence.raw == f"[Original resource](<{uri}>)".encode()
    assert occurrence.meaning.status == "external" and occurrence.query is None


@pytest.mark.parametrize(
    "output_format,player,accepted",
    (
        (7, PLAYER, False),
        (8, PLAYER, True),
        (
            8,
            PLAYER.replace(
                "https://www.youtube.com/embed/SYNTHVID001?start=0", "../private.md"
            ),
            False,
        ),
        (
            8,
            PLAYER.replace(
                " allowfullscreen", ' onload="unreviewed()" allowfullscreen'
            ),
            False,
        ),
    ),
    ids=("legacy7", "canonical8", "local-target", "extra-attribute"),
)
def test_restoration_accepts_canonical_output8_player_without_html_or_source_grants(
    output_format, player, accepted
):
    baseline = graph_payload()
    baseline["Categories/A.md"] = note("category:A", icon="[[Attachments/A.svg]]")
    record = json.loads(baseline["migration-record.json"])
    record["schema_version"] = output_format
    baseline["migration-record.json"] = json.dumps(record).encode()
    current, incoming = dict(baseline), dict(baseline)
    del current["Notes/Independent.md"]
    incoming["Notes/Independent.md"] = note(
        "entry:I",
        category=False,
        body="Incoming prose.\n[Original resource](<https://www.youtube.com/watch?v=SYNTHVID001>)\n"
        + player,
    )
    incoming_record = json.loads(incoming["migration-record.json"])
    incoming_record["source_identity"].update(
        source_sha256="e" * 64, snapshot_digest="f" * 64
    )
    incoming["migration-record.json"] = json.dumps(incoming_record).encode()
    facts = assemble_facts(
        baseline, incoming, current, proposal_id="restore-player", generation=1
    )
    prepared = preparation(facts)
    operations = Operations()
    change = next(
        c
        for c in prepared.review.proposal.changes
        if c.item_id == "support:migration-record.json"
    )
    kept = operations.resolve_update(
        prepared,
        action(prepared.review, change, choice="current", decision_id="keep-record"),
    )
    assert kept.code == "accepted", kept.code
    offer = next(
        row
        for row in inspect_review_choices(kept.preparation.review)
        if row.domain == "restoration"
    )
    selected = operations.resolve_update_choice(
        kept.preparation,
        requirement_id=offer.requirement_id,
        choice="restore_incoming",
        assumptions_digest=requirement_digest(offer),
    )
    if not accepted:
        assert selected.code == "invalid_candidate" and not selected.ready
        return
    assert selected.code == "accepted" and selected.ready, selected.code
    chosen = next(
        a for a in selected.preparation.review.approvals if a.domain == "restoration"
    )
    assert chosen.result.data == incoming["Notes/Independent.md"]
    assert chosen.provenance == "explicit_user"
    original = next(
        subject.baseline
        for subject in selected.preparation.review.facts.subjects
        if subject.item_id == "entry:I"
    )
    assert original.status == "known"
    assert original.content.data == baseline["Notes/Independent.md"]
    effects = select_review_effects(selected.preparation.review)
    assert effects.status == "selected"
    assert (
        next(f.content.data for f in effects.files if f.path == "Notes/Independent.md")
        == incoming["Notes/Independent.md"]
    )


def test_output8_attachment_reference_choice_preserves_player_and_external_uri():
    from tests.reconciliation.test_type_tag_dependencies import BLUE, RED

    baseline = graph_payload()
    baseline["Categories/A.md"] = note("category:A", icon="[[Attachments/A.svg]]")
    uri = "https://www.youtube.com/watch?list=original%2Fcontext&v=SYNTHVID001&index=00"
    baseline["Notes/Independent.md"] = note(
        "entry:I",
        category=False,
        body=f"[Original resource](<{uri}>)\n{PLAYER}\n![[Attachments/A.svg]]",
    )
    current, incoming = dict(baseline), dict(baseline)
    current["Attachments/A.svg"] = (
        b'<svg xmlns="http://www.w3.org/2000/svg">local</svg>'
    )
    incoming["Attachments/A.svg"] = BLUE
    record = json.loads(incoming["migration-record.json"])
    record["source_identity"].update(source_sha256="e" * 64, snapshot_digest="f" * 64)
    incoming["migration-record.json"] = json.dumps(record).encode()
    prepared = preparation(
        assemble_facts(
            baseline,
            incoming,
            current,
            proposal_id="player-resource",
            generation=1,
        )
    )
    operations = Operations()
    record_change = next(
        c
        for c in prepared.review.proposal.changes
        if c.item_id == "support:migration-record.json"
    )
    prepared = operations.resolve_update(
        prepared,
        action(
            prepared.review, record_change, choice="current", decision_id="keep-record"
        ),
    ).preparation
    offer = next(
        row
        for row in inspect_review_choices(prepared.review)
        if row.domain == "attachment"
    )
    references = attachment_references(prepared, offer.requirement_id)
    assert len(references) == 2
    selected = operations.resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice="incoming",
        assumptions_digest=requirement_digest(offer),
        references=tuple(
            {"reference_id": token, "choice": "use_incoming"}
            for token, _, _ in references
        ),
    )
    assert selected.code == "accepted" and selected.ready, selected.code
    effects = select_review_effects(selected.preparation.review)
    assert effects.status == "selected"
    files = {row.path: row.content.data for row in effects.files}
    assert files["Attachments/A.svg"] == BLUE != RED
    assert (
        files.get("Notes/Independent.md", baseline["Notes/Independent.md"])
        == baseline["Notes/Independent.md"]
    )
    document = next(
        doc
        for doc in selected.preparation.review.facts.link_context.current_documents
        if doc.source_path == "Notes/Independent.md"
    )
    assert document.status == "supported"
    assert [(occ.raw, occ.meaning.status) for occ in document.occurrences] == [
        (f"[Original resource](<{uri}>)".encode(), "external"),
        (b"![[Attachments/A.svg]]", "resolved"),
    ]


@pytest.mark.parametrize("output_format", (7, 8))
def test_migration_record_choice_keeps_source_markup_as_data(output_format):
    baseline = graph_payload()
    baseline["Categories/A.md"] = note("category:A", icon="[[Attachments/A.svg]]")
    record = json.loads(baseline["migration-record.json"])
    record["schema_version"] = output_format
    baseline["migration-record.json"] = json.dumps(record).encode()
    incoming = dict(baseline)
    record["source_identity"].update(source_sha256="e" * 64, snapshot_digest="f" * 64)
    record["original_evidence"] = [
        {
            "records": [
                {
                    "Note": "[Original reference](brain://api.thebrain.com/EREREREREUGBEREREREREQ/AAAAAAAAAAAAAAAAAAAAEw/version-1)",
                    "VideoHtml": "<iframe width='100%' height='100%' src='https://www.youtube.com/embed/SYNTHVID001?start=0' frameborder='0'></iframe>",
                }
            ]
        }
    ]
    raw = json.dumps(record).encode()
    incoming["migration-record.json"] = raw
    prepared = preparation(
        assemble_facts(
            baseline,
            incoming,
            baseline,
            proposal_id="raw-evidence-record",
            generation=1,
        )
    )
    offer = next(
        row for row in inspect_review_choices(prepared.review) if row.domain == "text"
    )
    selected = Operations().resolve_update_choice(
        prepared,
        requirement_id=offer.requirement_id,
        choice="incoming",
        assumptions_digest=requirement_digest(offer),
    )
    if output_format == 7:
        assert selected.code == "invalid_candidate" and not selected.ready
        return
    assert selected.code == "accepted" and selected.ready, selected.code
    effects = select_review_effects(selected.preparation.review)
    assert effects.status == "selected"
    assert (
        next(
            row.content.data
            for row in effects.files
            if row.path == "migration-record.json"
        )
        == raw
    )
    choice = next(
        a for a in selected.preparation.review.approvals if a.domain == "text"
    )
    assert choice.provenance == "explicit_user" and choice.result.data == raw


def test_migration_record_data_dialect_keeps_note_and_legacy_guards():
    record = json.loads(graph_payload()["migration-record.json"])
    record["original_evidence"] = [
        {
            "records": [
                {
                    "VideoHtml": "<iframe src='https://unreviewed.invalid/player'></iframe>",
                    "Note": "[raw](brain://source/original)",
                }
            ]
        }
    ]
    raw = json.dumps(record).encode()
    options = {
        "document_id": "record",
        "path_mode": "vault",
        "targets": (),
        "target_facts": (),
        "inventory": "complete",
    }
    parsed = interpret_links(
        ExactContent(data=raw),
        source_path="migration-record.json",
        output_format=8,
        **options,
    )
    assert parsed.status == "supported" and not parsed.occurrences
    assert parsed.content.data == raw
    legacy = interpret_links(
        ExactContent(data=raw), source_path="migration-record.json", **options
    )
    assert legacy == interpret_links(
        ExactContent(data=raw),
        source_path="migration-record.json",
        output_format=7,
        **options,
    )
    assert legacy.status == "unsupported"
    for path, data in (
        ("Notes/Record.md", raw),
        ("Nested/migration-record.json", raw),
        ("migration-record.json", raw[:-1]),
        ("migration-record.json", b"{"),
        ("migration-record.json", b"{}"),
        ("migration-record.json", b"[]"),
        ("migration-record.json", raw.replace(b'"brz2obsidian.migration"', b'"other"')),
        (
            "migration-record.json",
            raw.replace(b'"schema_version": 8', b'"schema_version": 7'),
        ),
        (
            "migration-record.json",
            raw.replace(b'"schema_version": 8', b'"schema_version": 8.0'),
        ),
        (
            "migration-record.json",
            raw.replace(b'"schema_version": 8', b'"schema_version": true'),
        ),
        (
            "migration-record.json",
            json.dumps({**record, "asset_targets": ["not a mapping"]}).encode(),
        ),
        ("migration-record.json", json.dumps({**record, "profile_id": None}).encode()),
        ("migration-record.json", raw.replace(b'"source_id":', b'"unknown_id":')),
        (
            "migration-record.json",
            json.dumps(
                {
                    "schema": "brz2obsidian.migration",
                    "schema_version": 8,
                    "original_evidence": record["original_evidence"],
                }
            ).encode(),
        ),
    ):
        rejected = interpret_links(
            ExactContent(data=data), source_path=path, output_format=8, **options
        )
        assert rejected.status == "unsupported", (path, data)


@pytest.mark.parametrize(
    "recorded,current_version,renamed_player",
    ((6, 6, False), (7, 7, False), (7, 6, False), (7, 7, True)),
    ids=(
        "six-to-eight",
        "seven-to-eight",
        "wrong-current-version",
        "renamed-seven-player",
    ),
)
def test_transition_qualifies_current_record_from_recorded_identity(
    recorded, current_version, renamed_player
):
    from brz2obsidian.application.review_choices import review_plan_choice_action
    from brz2obsidian.application.update_lifecycle import text_choice_action
    from brz2obsidian.core import (
        load_review,
        prepare_review,
        resolve_review,
        resume_review,
        save_review,
    )
    from tests.reconciliation.test_resolution import preflight

    baseline = graph_payload()
    baseline["Categories/A.md"] = note("category:A")
    del baseline["Attachments/A.svg"]
    if renamed_player:
        baseline["Notes/Independent.md"] = note(
            "entry:I",
            category=False,
            body="Original prose.\n[Video](<https://www.youtube.com/watch?v=SYNTHVID001>)\n"
            + PLAYER,
        )
    record = json.loads(baseline["migration-record.json"])
    record.update(schema_version=recorded, asset_targets=[])
    record["original_evidence"] = [
        {
            "records": [
                {
                    "VideoHtml": "<iframe src='https://source.invalid/player'></iframe>",
                    "Note": "[raw](brain://source/original)",
                }
            ]
        }
    ]
    baseline["migration-record.json"] = json.dumps(record).encode()
    current, incoming = dict(baseline), dict(baseline)
    if renamed_player:
        current["Notes/Personal media.md"] = current.pop(
            "Notes/Independent.md"
        ).replace(b"Original prose.", b"Local media prose.")
    current["migration-record.json"] = json.dumps(
        {**record, "schema_version": current_version}
    ).encode()
    incoming["migration-record.json"] = json.dumps(
        {**record, "schema_version": 8}
    ).encode()
    facts = assemble_facts(
        baseline, incoming, current, proposal_id="record-transition", generation=1
    )
    facts = facts.model_copy(
        update={
            "format_operation": facts.format_operation.model_copy(
                update={
                    "kind": "format_transition",
                    "recorded_generation": "supported"
                    if recorded == 7
                    else "unavailable",
                }
            )
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    for step in range(8):
        if plan.ready:
            break
        requirement = plan.requirements[0]
        offer = next(
            row
            for row in inspect_review_choices(plan)
            if row.requirement_id == requirement.requirement_id
        )
        item = next(
            c.item_id
            for c in plan.proposal.changes
            if c.change_id == requirement.change_id
        )
        selection = (
            "keep_path"
            if requirement.domain == "rename"
            else "current"
            if renamed_player and item == "entry:I"
            else "incoming"
        )
        choice = review_plan_choice_action(
            plan,
            requirement_id=offer.requirement_id,
            choice=selection,
            assumptions_digest=requirement_digest(offer),
        )
        compiled = text_choice_action(plan, choice)
        changed = resolve_review(plan, compiled)
        item = next(
            c.item_id
            for c in plan.proposal.changes
            if c.change_id == requirement.change_id
        )
        if item == "support:migration-record.json" and current_version != recorded:
            assert changed.code == "invalid_candidate" and not changed.plan.ready
            return
        assert changed.code == "accepted", (item, changed.code)
        plan = changed.plan
    assert plan.ready
    effects = select_review_effects(plan)
    assert effects.status == "selected"
    if renamed_player:
        files = {row.path: row.content.data for row in effects.files}
        assert files["Notes/Personal media.md"] == current["Notes/Personal media.md"]
        assert "Notes/Independent.md" not in files
        subject = next(row for row in facts.subjects if row.item_id == "entry:I")
        assert subject.baseline.content.data == baseline["Notes/Independent.md"]
        assert subject.structure.current.output_format == 7
    assert (
        next(
            row.content.data
            for row in effects.files
            if row.path == "migration-record.json"
        )
        == incoming["migration-record.json"]
    )
    old = next(
        doc
        for doc in facts.link_context.current_documents
        if doc.source_path == "migration-record.json"
    )
    assert old.status == "supported" and not old.occurrences
    assert old.content.data == current["migration-record.json"]
    saved = save_review(plan)
    assert saved.code == "saved"
    loaded = load_review(saved.record.model_dump_json())
    assert loaded.code == "loaded" and not loaded.ready
    resumed = resume_review(loaded.loaded, facts, preflight=plan.preflight)
    assert resumed.code == "unchanged" and resumed.plan == plan
