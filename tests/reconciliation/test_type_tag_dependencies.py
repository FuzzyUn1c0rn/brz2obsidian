"""Independent provider/resource graphs through public review boundaries."""

import json
from copy import deepcopy

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


@pytest.fixture(scope="module")
def prepared_far_provider_review(opaque_provider):
    baseline, incoming, current = conflicted_graph()
    if opaque_provider:
        current["Categories/A.md"] = current["Categories/A.md"].replace(
            b"\n---\n", b"\ncustom_values: [one, two]\n---\n"
        )
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
    return baseline, incoming, current, plan, independent


@pytest.mark.parametrize("change", ["bytes", "missing", "competitor"])
@pytest.mark.parametrize("opaque_provider", (False, True), scope="module")
def test_far_provider_icon_bytes_retire_dependent_choice_and_keep_unrelated_decision(
    change,
    prepared_far_provider_review,
):
    # Only the unchanged public preparation is shared. Every changed observation
    # and its decisions receive independent dictionaries and contract graphs.
    baseline, incoming, current, plan, independent = deepcopy(
        prepared_far_provider_review
    )
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


@pytest.mark.parametrize("opaque_provider", (False, True))
def test_full_provider_chain_beyond_native_eight_links_remains_safe_until_cycle(
    tmp_path,
    opaque_provider,
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
    if opaque_provider:
        current["Categories/H0.md"] = current["Categories/H0.md"].replace(
            b"\n---\n", b"\ncustom_values: [one, two]\n---\n"
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
            if opaque_provider:
                selected["Categories/H0.md"] = selected["Categories/H0.md"].replace(
                    b"\n---\n", b"\ncustom_values: [one, two]\n---\n"
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


def test_unchanged_provider_cycle_does_not_hide_new_invalid_owned_icon():
    from brz2obsidian.core import select_review_effects

    baseline = graph_payload()
    record = json.loads(baseline["migration-record.json"])
    record["asset_targets"].append(
        {"asset_id": "ordinary:manual", "relative_path": "Attachments/Manual.bin"}
    )
    baseline["migration-record.json"] = json.dumps(record).encode()
    baseline["Attachments/Manual.bin"] = b"An ordinary non-image resource."
    current, incoming = dict(baseline), dict(baseline)
    # Only authored Current closes B->C->B. Both generated source versions
    # retain the acyclic A->B->C assignment family.
    current["Categories/B.md"] = note(
        "category:B", provider="[[Categories/C.md]]", icon="[[A.svg]]", body="Local B."
    )
    incoming["Categories/B.md"] = note(
        "category:B",
        provider="[[Categories/A.md]]",
        icon="[[A.svg]]",
        body="Incoming B.",
    )
    incoming["Notes/Independent.md"] = note(
        "entry:I", category=False, body="Incoming I. [[Attachments/Manual.bin]]"
    )
    facts = facts_for(baseline, incoming, current)
    for bad_icon in (False, True):
        selected = dict(current)
        selected["Notes/Independent.md"] = incoming["Notes/Independent.md"]
        if bad_icon:
            selected["Categories/B.md"] = note(
                "category:B",
                provider="[[Categories/C.md]]",
                icon="[[Attachments/Manual.bin]]",
                body="Explicitly edited B.",
            )
        prospective = facts_for(baseline, selected, current)
        plan = prepare_review(facts, preflight=preflight())
        independent = next(c for c in plan.proposal.changes if c.item_id == "entry:I")
        kept = resolve_review(
            plan,
            action(
                plan,
                independent,
                choice="incoming",
                decision_id="ordinary-resource-consumer",
                candidate=selected_candidate(facts, prospective, "entry:I"),
            ),
        )
        assert kept.status == "accepted", kept.code
        plan = kept.plan
        member = next(c for c in plan.proposal.changes if c.item_id == "category:B")
        result = resolve_review(
            plan,
            action(
                plan,
                member,
                choice="edited" if bad_icon else "current",
                decision_id="existing-cycle-member",
                candidate=selected_candidate(facts, prospective, "category:B"),
            ),
        )
        assert result.status == "accepted" and result.plan.requirements == ()
        assert result.plan.ready is not bad_icon, result.plan.blockers
        if bad_icon:
            assert "selected_provider_invalid" in result.plan.blockers
            assert select_review_effects(result.plan).status == "refused"
        else:
            effects = select_review_effects(result.plan)
            assert effects.status == "selected"
            expected = dict(current)
            expected["Notes/Independent.md"] = incoming["Notes/Independent.md"]
            assert {row.path: row.content.data for row in effects.files} == expected
            assert effects.remove_paths == ()


def test_existing_bad_icon_does_not_hide_new_noncategory_provider():
    from brz2obsidian.core import select_review_effects

    baseline = graph_payload()
    record = json.loads(baseline["migration-record.json"])
    record["asset_targets"].append(
        {"asset_id": "ordinary:manual", "relative_path": "Attachments/Manual.bin"}
    )
    baseline["migration-record.json"] = json.dumps(record).encode()
    baseline["Attachments/Manual.bin"] = b"An ordinary non-image resource."
    current, incoming = dict(baseline), dict(baseline)
    current["Categories/A.md"] = note("category:A", icon="[[Attachments/Manual.bin]]")
    current["Categories/C.md"] = current["Categories/C.md"].replace(
        b"tags:\n  - categories", b"tags: []"
    )
    incoming["Categories/A.md"] = note(
        "category:A", icon="[[A.svg]]", body="Incoming A."
    )
    incoming["Notes/Independent.md"] = note(
        "entry:I", category=False, body="Incoming I. [[Attachments/Manual.bin]]"
    )
    facts = facts_for(baseline, incoming, current)
    for new_provider in (False, True):
        selected = dict(current)
        selected["Notes/Independent.md"] = incoming["Notes/Independent.md"]
        if new_provider:
            selected["Categories/A.md"] = note(
                "category:A",
                provider="[[Categories/C.md]]",
                icon="[[Attachments/Manual.bin]]",
                body="Explicitly edited A.",
            )
        prospective = facts_for(baseline, selected, current)
        plan = prepare_review(facts, preflight=preflight())
        independent = next(c for c in plan.proposal.changes if c.item_id == "entry:I")
        result = resolve_review(
            plan,
            action(
                plan,
                independent,
                choice="incoming",
                decision_id="preserve-independent-I",
                candidate=selected_candidate(facts, prospective, "entry:I"),
            ),
        )
        assert result.status == "accepted", result.code
        plan = result.plan
        change = next(c for c in plan.proposal.changes if c.item_id == "category:A")
        result = resolve_review(
            plan,
            action(
                plan,
                change,
                choice="edited" if new_provider else "current",
                decision_id="selected-A",
                candidate=selected_candidate(facts, prospective, "category:A")
                if new_provider
                else None,
            ),
        )
        assert result.status == "accepted" and result.plan.requirements == ()
        assert result.plan.ready is not new_provider, result.plan.blockers
        if new_provider:
            assert "selected_provider_invalid" in result.plan.blockers
            assert select_review_effects(result.plan).status == "refused"
        else:
            effects = select_review_effects(result.plan)
            expected = dict(current)
            expected["Notes/Independent.md"] = incoming["Notes/Independent.md"]
            assert effects.status == "selected"
            assert {row.path: row.content.data for row in effects.files} == expected


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


@pytest.mark.parametrize(
    "fault", ["wrong_extension", "empty_image", "missing_image", "invalid_declaration"]
)
def test_selected_chain_checks_owned_icon_without_rejecting_ordinary_resource(fault):
    from brz2obsidian.core import select_review_effects

    baseline, incoming, current = invalid_provider_graph()
    for payload in (baseline, incoming, current):
        payload["Attachments/B.svg"] = BLUE
        record = json.loads(payload["migration-record.json"])
        record["asset_targets"].append(
            {"asset_id": "image:b", "relative_path": "Attachments/B.svg"}
        )
        payload["migration-record.json"] = json.dumps(record).encode()
        payload["Categories/B.md"] = note(
            "category:B", provider="[[Categories/A.md]]", icon="[[Attachments/B.svg]]"
        )
    if fault == "wrong_extension":
        path, content = "Attachments/Manual.txt", b"An ordinary local document."
        declared = "[[Attachments/Manual.txt]]"
    elif fault == "empty_image":
        path, content = "Attachments/Manual.png", b""
        declared = "[[Attachments/Manual.png]]"
    else:
        path, content = "Attachments/Manual.txt", b"An ordinary local document."
        declared = (
            "not a wiki link" if fault == "invalid_declaration" else "[[Missing.png]]"
        )
    current[path] = content
    current["Categories/A.md"] = note("category:A", icon=declared)
    current["Notes/Independent.md"] = note(
        "entry:I", category=False, body="Local reference [[" + path + "]]."
    )
    incoming["Notes/Independent.md"] = note(
        "entry:I", category=False, body="Incoming I."
    )
    facts = facts_for(baseline, incoming, current)
    for choice, safe in (("current", True), ("incoming", False)):
        selected = dict(current)
        if choice == "incoming":
            selected["Categories/C.md"] = incoming["Categories/C.md"]
        prospective = facts_for(baseline, selected, current)
        plan = prepare_review(facts, preflight=preflight())
        independent = next(c for c in plan.proposal.changes if c.item_id == "entry:I")
        kept = resolve_review(
            plan,
            action(
                plan, independent, choice="current", decision_id="ordinary-resource"
            ),
        )
        assert kept.status == "accepted", kept
        plan = kept.plan
        assert plan.approvals[0].result.data == current["Notes/Independent.md"]
        # An unsuitable icon target remains a legitimate ordinary resource.
        change = next(c for c in plan.proposal.changes if c.item_id == "category:C")
        chosen = resolve_review(
            plan,
            action(
                plan,
                change,
                choice=choice,
                decision_id="select-C",
                candidate=selected_candidate(facts, prospective, "category:C"),
            ),
        )
        assert chosen.status == "accepted", chosen
        assert chosen.plan.requirements == ()
        assert chosen.plan.ready is safe, (fault, chosen.plan.blockers)
        if not safe:
            assert select_review_effects(chosen.plan).status == "refused"


@pytest.mark.parametrize(
    "fault", ("missing_role", "wrong_folder", "excluded_subfolder")
)
def test_selected_provider_requires_native_category_role_despite_nearer_owned_icon(
    fault,
):
    baseline, incoming, current = invalid_provider_graph()
    for payload in (baseline, incoming, current):
        payload["Attachments/B.svg"] = BLUE
        record = json.loads(payload["migration-record.json"])
        record["asset_targets"].append(
            {"asset_id": "image:b", "relative_path": "Attachments/B.svg"}
        )
        payload["migration-record.json"] = json.dumps(record).encode()
        payload["Categories/B.md"] = note(
            "category:B", provider="[[Categories/A.md]]", icon="[[Attachments/B.svg]]"
        )
    path = {
        "missing_role": "Categories/A.md",
        "wrong_folder": "Notes/A.md",
        "excluded_subfolder": "Categories/Attachments/A.md",
    }[fault]
    current.pop("Categories/A.md")
    current[path] = note(
        "category:A", icon="[[Attachments/A.svg]]", category=fault != "missing_role"
    )
    current["Categories/B.md"] = note(
        "category:B", provider="[[" + path + "]]", icon="[[Attachments/B.svg]]"
    )
    facts = facts_for(baseline, incoming, current)
    blue = next(
        row
        for row in facts.link_context.current_target_facts
        if row.target_id == "subject:image:b:asset"
    )
    assert blue.content.data == BLUE and blue.file_roles.image_path
    for choice, safe in (("current", True), ("incoming", False)):
        selected = current | (
            {"Categories/C.md": incoming["Categories/C.md"]}
            if choice == "incoming"
            else {}
        )
        if path != "Categories/A.md":
            record = json.loads(selected["migration-record.json"])
            next(
                row
                for row in record["item_targets"]
                if row["original_identity"] == "category:A"
            )["relative_path"] = path
            selected["migration-record.json"] = json.dumps(record).encode()
        prospective = facts_for(baseline, selected, current)
        plan = prepare_review(facts, preflight=preflight())
        change = next(
            row for row in plan.proposal.changes if row.item_id == "category:C"
        )
        result = resolve_review(
            plan,
            action(
                plan,
                change,
                choice=choice,
                candidate=selected_candidate(facts, prospective, "category:C"),
            ),
        )
        assert result.status == "accepted", result.code
        assert result.plan.requirements == ()
        assert result.plan.ready is safe, result.plan.blockers
        if not safe:
            assert "selected_provider_invalid" in result.plan.blockers


@pytest.mark.parametrize("invalid_declaration", (False, True))
def test_native_appearance_checks_keep_valid_custom_yaml_and_refuse_invalid_opaque_provider(
    invalid_declaration,
):
    baseline, incoming, current = invalid_provider_graph()
    for payload in (baseline, incoming, current):
        payload["Categories/B.md"] = note(
            "category:B", provider="[[Categories/A.md]]", icon="[[A.svg]]"
        )
    current["Categories/A.md"] = note("category:A", icon="[[A.svg]]").replace(
        b"\n---\n", b"\ncustom_values: [one, two]\n---\n"
    )
    if invalid_declaration:
        current["Categories/A.md"] = current["Categories/A.md"].replace(
            b"appearance_category: null", b"appearance_category: [1]"
        )
    facts = facts_for(baseline, incoming, current)
    provider = next(
        row
        for row in facts.link_context.current_target_facts
        if row.target_id == "subject:category:A:content"
    )
    assert provider.file_roles.category and provider.structure.status == "unsupported"
    selected = current | {"Categories/C.md": incoming["Categories/C.md"]}
    prospective = facts_for(baseline, selected, current)
    plan = prepare_review(facts, preflight=preflight())
    change = next(row for row in plan.proposal.changes if row.item_id == "category:C")
    result = resolve_review(
        plan,
        action(
            plan,
            change,
            choice="incoming",
            candidate=selected_candidate(facts, prospective, "category:C"),
        ),
    )
    assert result.status == "accepted", result.code
    assert result.plan.requirements == ()
    assert result.plan.ready is not invalid_declaration, result.plan.blockers
    if invalid_declaration:
        assert "selected_provider_invalid" in result.plan.blockers


@pytest.mark.parametrize("identity", ("valid", "wrong_type", "incomplete", "foreign"))
def test_current8_identity_survives_native_custom_properties_outside_merge_grammar(
    identity,
):
    baseline, incoming, current = invalid_provider_graph()
    current["Categories/A.md"] = note("category:A", icon="[[A.svg]]").replace(
        b"\n---\n", b"\ncustom_values: [one, two]\n---\n"
    )
    if identity == "wrong_type":
        current["Categories/A.md"] = current["Categories/A.md"].replace(
            b'source_item_id: "category:A"', b"source_item_id: 42"
        )
    elif identity == "incomplete":
        current["Categories/A.md"] = current["Categories/A.md"].replace(
            b'source_item_id: "category:A"\n', b""
        )
    elif identity == "foreign":
        current["Categories/A.md"] = current["Categories/A.md"].replace(
            b'source_collection_id: "folio:chain"',
            b'source_collection_id: "folio:foreign"',
        )
    facts = facts_for(baseline, incoming, current)
    entry = next(
        row for row in facts.identity_inventory if row.current.path == "Categories/A.md"
    )
    if identity in ("wrong_type", "incomplete"):
        assert entry.identity_state == "malformed" and entry.identity is None
        proposal = prepare_review(facts, preflight=preflight()).proposal
        change = next(row for row in proposal.changes if row.item_id == "category:A")
        assert (
            change.identity_review.repair_required
            and change.identity_review.selected_entry_id is None
        )
        assert not proposal.ready
        return
    if identity == "foreign":
        assert (
            entry.identity_state == "valid"
            and entry.identity.collection_id == "folio:foreign"
        )
        proposal = prepare_review(facts, preflight=preflight()).proposal
        change = next(row for row in proposal.changes if row.item_id == "category:A")
        assert change.identity_review.status != "matched"
        assert not proposal.ready
        return
    assert entry.identity_state == "valid"
    assert entry.identity.item_id == "category:A"
    target = next(
        row
        for row in facts.link_context.current_targets
        if row.canonical_path == "Categories/A.md"
    )
    assert target.kind == "category" and target.identity.item_id == "category:A"
    state = next(
        row
        for row in facts.link_context.current_target_facts
        if row.target_id == target.target_id
    )
    assert state.file_roles.category
    assert state.structure.status == "unsupported"


@pytest.mark.parametrize("cycle", (False, True))
def test_native_user_category_without_imported_identity_keeps_qualified_chain_semantics(
    cycle,
):
    baseline, incoming, current = provider_cycle_graph()
    current["Categories/Local.md"] = (
        b'---\ncategories:\n  - "[[Categories/E.md]]"\nappearance_category: "[[Categories/E.md]]"\n'
        b"icon: null\ntags:\n  - categories\n---\nLocal category without source IDs.\n"
    )
    current["Categories/B.md"] = note(
        "category:B",
        provider="[[Categories/Local.md]]",
        icon="[[A.svg]]",
        body="Local B.",
    )
    facts = facts_for(baseline, incoming, current)
    local = next(
        row
        for row in facts.link_context.current_targets
        if row.canonical_path == "Categories/Local.md"
    )
    assert local.kind == "note" and local.identity is None
    state = next(
        row
        for row in facts.link_context.current_target_facts
        if row.target_id == local.target_id
    )
    assert state.file_roles.category
    selected = current | (
        {"Categories/E.md": incoming["Categories/E.md"]} if cycle else {}
    )
    prospective = facts_for(baseline, selected, current)
    plan = prepare_review(facts, preflight=preflight())
    record = next(
        row
        for row in plan.proposal.changes
        if row.item_id == "support:migration-record.json"
    )
    record_kept = resolve_review(
        plan, action(plan, record, choice="current", decision_id="keep:record")
    )
    assert record_kept.status == "accepted", record_kept.code
    plan = record_kept.plan
    b = next(row for row in plan.proposal.changes if row.item_id == "category:B")
    kept = resolve_review(plan, action(plan, b, choice="current", decision_id="keep:B"))
    assert kept.status == "accepted", kept.code
    e = next(row for row in kept.plan.proposal.changes if row.item_id == "category:E")
    result = resolve_review(
        kept.plan,
        action(
            kept.plan,
            e,
            choice="incoming" if cycle else "current",
            decision_id="select:E",
            candidate=selected_candidate(facts, prospective, "category:E")
            if cycle
            else None,
        ),
    )
    assert result.status == "accepted", result.code
    assert result.plan.requirements == ()
    assert result.plan.ready is not cycle, result.plan.blockers
    if cycle:
        assert "selected_provider_cycle" in result.plan.blockers, result.plan.blockers
