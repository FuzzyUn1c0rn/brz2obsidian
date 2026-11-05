"""Independent provider/resource graphs through public review boundaries."""

import json

import pytest

from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.contracts import ImportedItemIdentity
from brz2obsidian.core import prepare_review, refresh_review, resolve_review
from brz2obsidian.obsidian import inspect_text_candidate, interpret_links
from tests.reconciliation.test_resolution import action, preflight

RED = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1" fill="red"/></svg>'
BLUE = RED.replace(b'fill="red"', b'fill="blue"')


def note(item, *, provider=None, icon=None, body="Original.", category=True):
    memberships = (
        "categories:\n  - " + json.dumps(provider) + "\n"
        if provider
        else "categories: []\n"
    )
    text = (
        "---\n"
        + memberships
        + "appearance_category: "
        + json.dumps(provider)
        + "\n"
        + "icon: "
        + json.dumps(icon)
        + "\n"
        + ("tags:\n  - categories\n" if category else "tags: []\n")
        + 'source_collection_id: "folio:chain"\n'
        + "source_item_id: "
        + json.dumps(item)
        + "\n---\n\n"
        + "# "
        + item
        + "\n\n"
        + body
        + "\n"
    )
    return text.encode("utf-8")


def graph_payload():
    rows = [
        {
            "original_identity": item,
            "original_title": title,
            "relative_path": path,
            "created": True,
            "creation_reasons": ["definition" if category else "content"],
        }
        for item, title, path, category in (
            ("category:A", "A", "Categories/A.md", True),
            ("category:B", "B", "Categories/B.md", True),
            ("category:C", "C", "Categories/C.md", True),
            ("entry:I", "Independent", "Notes/Independent.md", False),
        )
    ]
    record = {
        "schema": "brz2obsidian.migration",
        "schema_version": 8,
        "profile_id": "reviewed-folio",
        "profile_version": "1",
        "source_identity": {
            "source_id": "folio:chain",
            "module_id": "synthetic-folio",
            "module_version": "1",
            "format_version": "1",
            "source_sha256": "c" * 64,
            "snapshot_digest": "d" * 64,
        },
        "item_targets": rows,
        "asset_targets": [
            {"asset_id": "image:a", "relative_path": "Attachments/A.svg"}
        ],
    }
    return {
        "migration-record.json": json.dumps(record).encode(),
        "Categories/A.md": note("category:A", icon="[[A.svg]]"),
        "Categories/B.md": note("category:B", provider="[[Categories/A.md]]"),
        "Categories/C.md": note("category:C", provider="[[Categories/B.md]]"),
        "Notes/Independent.md": note("entry:I", category=False),
        "Attachments/A.svg": RED,
    }


def conflicted_graph():
    baseline = graph_payload()
    current, incoming = dict(baseline), dict(baseline)
    for path in ("Categories/C.md", "Notes/Independent.md"):
        current[path] = current[path].replace(b"Original.", b"Local writing.")
        incoming[path] = incoming[path].replace(b"Original.", b"Incoming writing.")
    record = json.loads(incoming["migration-record.json"])
    record["source_identity"].update(source_sha256="e" * 64, snapshot_digest="f" * 64)
    incoming["migration-record.json"] = json.dumps(record).encode()
    return baseline, incoming, current


def facts_for(baseline, incoming, current, *, generation=1):
    facts = assemble_facts(
        baseline,
        incoming,
        current,
        proposal_id="provider-resource-review",
        generation=generation,
    )
    # This public graph variant uses the supported shortened-link interpretation.
    # The physical default-vault journey separately uses generated qualified links.
    context = facts.link_context
    documents = {}
    for stage in ("current", "incoming"):
        documents[stage + "_documents"] = tuple(
            interpret_links(
                doc.content,
                document_id=doc.document_id,
                source_path=doc.source_path,
                path_mode="shortened",
                targets=getattr(context, stage + "_targets"),
                target_facts=getattr(context, stage + "_target_facts"),
                inventory="complete",
            )
            for doc in getattr(context, stage + "_documents")
        )
    return facts.model_copy(
        update={"link_context": context.model_copy(update=documents)}
    )


@pytest.mark.parametrize("change", ["bytes", "missing", "competitor"])
def test_far_provider_icon_bytes_retire_dependent_choice_and_keep_unrelated_decision(
    change,
):
    baseline, incoming, current = conflicted_graph()
    initial = facts_for(baseline, incoming, current)
    owner = next(
        d
        for d in initial.link_context.current_documents
        if d.source_path == "Categories/A.md"
    )
    assert owner.occurrences[0].meaning.target_id == "subject:image:a:asset"
    assert owner.occurrences[0].meaning.path == "Attachments/A.svg"
    plan = prepare_review(initial, preflight=preflight())
    for item, decision in (
        ("category:C", "keep-dependent"),
        ("entry:I", "keep-independent"),
    ):
        selected = next(c for c in plan.proposal.changes if c.item_id == item)
        chosen = resolve_review(
            plan, action(plan, selected, choice="current", decision_id=decision)
        )
        assert chosen.status == "accepted", chosen
        plan = chosen.plan
    independent = next(a for a in plan.approvals if a.decision_id == "keep-independent")
    assert independent.provenance == "explicit_user"
    assert independent.source_memory.choice == "keep_vault"
    edited = dict(current)
    if change == "bytes":
        edited["Attachments/A.svg"] = BLUE
    elif change == "missing":
        del edited["Attachments/A.svg"]
    else:
        edited["Other/A.svg"] = BLUE
    # C declares no owned icon and contains no direct A.svg reference.
    assert b"A.svg" not in current["Categories/C.md"]
    observed = facts_for(baseline, incoming, edited, generation=2)
    fresh = prepare_review(observed, preflight=preflight())
    dependent_change = next(
        c for c in plan.proposal.changes if c.item_id == "category:C"
    )
    # A caller updating the generation alone has not reviewed the changed image context.
    old_consent = action(
        plan,
        dependent_change,
        choice="current",
        decision_id="stale-dependent-context",
        expected_generation=2,
    )
    stale = resolve_review(fresh, old_consent)
    assert (stale.status, stale.code) in {
        ("refused", "unknown_change"),
        ("stale", "assumptions_changed"),
    }
    assert stale.plan == fresh
    independent_change = next(
        c for c in plan.proposal.changes if c.item_id == "entry:I"
    )
    valid = resolve_review(
        fresh,
        action(
            plan,
            independent_change,
            choice="current",
            decision_id="same-independent-context",
            expected_generation=2,
        ),
    )
    assert valid.status == "accepted"
    refreshed = refresh_review(plan, observed, preflight=preflight())
    assert refreshed.status == "accepted", refreshed
    assert [a.decision_id for a in refreshed.plan.approvals] == ["keep-independent"]
    assert refreshed.plan.approvals[0] == independent
    assert not refreshed.plan.ready


def selected_candidate(facts, selected_facts, item):
    """Interpret exact selected bytes against the complete prospective file graph."""
    subject = next(s for s in facts.subjects if s.item_id == item)
    context = selected_facts.link_context
    doc = next(d for d in context.incoming_documents if d.source_path == subject.path)
    return inspect_text_candidate(
        doc.content,
        identity=ImportedItemIdentity(
            collection_id="folio:chain", module_id="synthetic-folio", item_id=item
        ),
        target=subject.source_target,
        output_format=8,
        source_path=subject.path,
        document_id=doc.document_id,
        path_mode="shortened",
        link_targets=context.incoming_targets,
        link_target_facts=context.incoming_target_facts,
        link_inventory="complete",
        membership_targets=context.incoming_targets,
    )


def provider_cycle_graph(own_icon=False):
    baseline = graph_payload()
    record = json.loads(baseline["migration-record.json"])
    record["item_targets"].append(
        {
            "original_identity": "category:E",
            "original_title": "E",
            "relative_path": "Categories/E.md",
            "created": True,
            "creation_reasons": ["definition"],
        }
    )
    baseline["migration-record.json"] = json.dumps(record).encode()
    baseline["Categories/E.md"] = note("category:E", provider="[[Categories/A.md]]")
    current, incoming = dict(baseline), dict(baseline)
    current["Categories/B.md"] = note(
        "category:B",
        provider="[[Categories/E.md]]",
        icon="[[A.svg]]" if own_icon else None,
        body="Local B.",
    )
    current["Categories/E.md"] = note(
        "category:E", provider="[[Categories/A.md]]", body="Local E."
    )
    incoming["Categories/B.md"] = note(
        "category:B", provider="[[Categories/A.md]]", body="Incoming B."
    )
    incoming["Categories/E.md"] = note(
        "category:E", provider="[[Categories/B.md]]", body="Incoming E."
    )
    record["source_identity"].update(source_sha256="e" * 64, snapshot_digest="f" * 64)
    incoming["migration-record.json"] = json.dumps(record).encode()
    return baseline, incoming, current


@pytest.mark.parametrize("own_icon", [False, True])
def test_combined_selected_providers_cannot_create_cycle(own_icon):
    baseline, incoming, current = provider_cycle_graph(own_icon)
    facts = facts_for(baseline, incoming, current)
    # Entire current and incoming graphs are acyclic. Only the mixed selection
    # B(current)->E and E(incoming)->B closes a cycle; an owned B icon does not
    # exempt independent full-chain safety checks.
    for choices, safe in (
        (("current", "current"), True),
        (("incoming", "incoming"), True),
        (("current", "incoming"), False),
    ):
        selected = dict(current)
        for item, choice in zip(("B", "E"), choices, strict=True):
            path = f"Categories/{item}.md"
            selected[path] = (current if choice == "current" else incoming)[path]
        selected_facts = facts_for(baseline, selected, current)
        plan = prepare_review(facts, preflight=preflight())
        support = next(
            c
            for c in plan.proposal.changes
            if c.item_id == "support:migration-record.json"
        )
        kept = resolve_review(
            plan, action(plan, support, choice="current", decision_id="keep-record")
        )
        assert kept.status == "accepted", kept
        plan = kept.plan
        for item, choice in zip(("category:B", "category:E"), choices, strict=True):
            change = next(c for c in plan.proposal.changes if c.item_id == item)
            candidate = selected_candidate(facts, selected_facts, item)
            assert candidate.status == "safe", candidate.document.issues
            resolved = resolve_review(
                plan,
                action(
                    plan,
                    change,
                    choice=choice,
                    candidate=candidate,
                    decision_id=item + ":" + choice,
                ),
            )
            assert resolved.status == "accepted", resolved
            plan = resolved.plan
        assert plan.ready is safe, (choices, plan.blockers, plan.requirements)
        if not safe:
            assert "selected_provider_cycle" in plan.blockers


def test_full_provider_chain_beyond_native_eight_links_remains_safe_until_cycle(
    tmp_path,
):
    from brz2obsidian.vault_check import check_vault

    baseline = graph_payload()
    record = json.loads(baseline["migration-record.json"])
    definitions = [f"H{i}" for i in range(10)] + ["F", "G"]
    for name in definitions + ["N9"]:
        category = name != "N9"
        path = ("Categories/" if category else "Notes/") + name + ".md"
        record["item_targets"].append(
            {
                "original_identity": "entry:" + name,
                "original_title": name,
                "relative_path": path,
                "created": True,
                "creation_reasons": ["definition" if category else "content"],
            }
        )
        provider = {"F": "G", "G": "F", "N9": "H8"}.get(name)
        if name.startswith("H") and name != "H0":
            provider = f"H{int(name[1:]) - 1}"
        baseline[path] = note(
            "entry:" + name,
            provider=f"[[Categories/{provider}.md]]" if provider else None,
            icon="[[A.svg]]" if name == "H0" else None,
            category=category,
        )
    baseline["migration-record.json"] = json.dumps(record).encode()
    current, incoming = dict(baseline), dict(baseline)
    current["Categories/H0.md"] = current["Categories/H0.md"].replace(
        b"Original.", b"Local H0."
    )
    incoming["Categories/H0.md"] = incoming["Categories/H0.md"].replace(
        b"Original.", b"Incoming H0."
    )
    for path, raw in current.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    checked = check_vault(tmp_path)
    assert {(i.code, i.artifact) for i in checked.issues} == {
        ("provider_cycle", "Categories/F.md"),
        ("provider_cycle", "Categories/G.md"),
        ("icon_lookup_depth", "Categories/H9.md"),
        ("icon_lookup_depth", "Notes/N9.md"),
    }
    facts = facts_for(baseline, incoming, current)
    for cycle in (False, True):
        selected = dict(current)
        if cycle:
            selected["Categories/H0.md"] = note(
                "entry:H0",
                provider="[[Categories/H9.md]]",
                icon="[[A.svg]]",
                body="Reviewed H0.",
            )
        selected_facts = facts_for(baseline, selected, current)
        plan = prepare_review(facts, preflight=preflight())
        change = next(c for c in plan.proposal.changes if c.item_id == "entry:H0")
        resolved = resolve_review(
            plan,
            action(
                plan,
                change,
                choice="edited" if cycle else "current",
                candidate=selected_candidate(facts, selected_facts, "entry:H0"),
            ),
        )
        assert resolved.status == "accepted", resolved
        assert resolved.plan.requirements == ()
        if cycle:
            assert not resolved.plan.ready
            assert resolved.plan.blockers == ("selected_provider_cycle",)
        else:
            assert resolved.plan.ready, resolved.plan.blockers


def invalid_provider_graph():
    baseline, _, _ = provider_cycle_graph()
    baseline["Categories/E.md"] = note("category:E")
    baseline["Categories/C.md"] = note("category:C", provider="[[Categories/E.md]]")
    baseline["Categories/B.md"] = note(
        "category:B", provider="[[Categories/A.md]]", icon="[[A.svg]]"
    )
    current, incoming = dict(baseline), dict(baseline)
    # The existing A declaration is already invalid; C currently chooses E and
    # is independent of A. B's valid owned image must not hide A's declaration
    # when C is explicitly switched into that chain.
    current["Categories/A.md"] = note("category:A", icon="[[A.svg]]").replace(
        b"appearance_category: null", b'appearance_category: "[[Missing]]"'
    )
    current["Categories/C.md"] = note(
        "category:C", provider="[[Categories/E.md]]", body="Local C."
    )
    incoming["Categories/C.md"] = note(
        "category:C", provider="[[Categories/B.md]]", body="Incoming C."
    )
    return baseline, incoming, current


def test_new_chain_cannot_reach_invalid_declaration_behind_nearer_owned_icon():
    baseline, incoming, current = invalid_provider_graph()
    facts = facts_for(baseline, incoming, current)
    for choice, safe in (("current", True), ("incoming", False)):
        selected = dict(current)
        if choice == "incoming":
            selected["Categories/C.md"] = incoming["Categories/C.md"]
        selected_facts = facts_for(baseline, selected, current)
        plan = prepare_review(facts, preflight=preflight())
        change = next(c for c in plan.proposal.changes if c.item_id == "category:C")
        result = resolve_review(
            plan,
            action(
                plan,
                change,
                choice=choice,
                candidate=selected_candidate(facts, selected_facts, "category:C"),
            ),
        )
        assert result.status == "accepted", result
        assert result.plan.requirements == ()
        assert result.plan.ready is safe, result.plan.blockers
        if not safe:
            assert "selected_provider_invalid" in result.plan.blockers
