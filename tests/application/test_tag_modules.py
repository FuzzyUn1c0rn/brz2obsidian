import pytest

from brz2obsidian.contracts import Item, MigrationRefused
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from tests.application.test_graph_modules import POLICY, edge, generated, snapshot
from tests.application.test_module_seams import METADATA
from tests.support.notes import note_body


def tag(key, title, seed=None, **values):
    return Item(
        key=key,
        original_identity=key,
        naming_seed=seed or key.encode().hex(),
        title=title,
        role="tag",
        **values,
    )


def test_flat_tag_tokens_preserve_exact_source_names_and_handle_empty_numeric_unicode():
    facts = snapshot(
        (
            tag("a", "alpha / beta!?_ gamma"),
            tag("b", "123"),
            tag("c", "... / "),
            tag("d", "e\u0301 / 中文"),
            tag("e", "²"),
        )
    )
    migration = plan(analyze(facts, POLICY))
    assert {t.tag_key: t.token for t in migration.tag_targets} == {
        "a": "alpha-beta-gamma",
        "b": "tag-123",
        "c": "source-tag",
        "d": "é-中文",
        "e": "tag-²",
    }
    assert migration.tag_targets[3].original_name == "e\u0301 / 中文"


@pytest.mark.parametrize("a,b", [("entry", "a"), ("a", "a")])
def test_invalid_classification_source_or_self_membership_is_refused(a, b):
    facts = snapshot((tag("a", "Tag"),), (edge("membership", a, b, "tag"),))
    with pytest.raises(MigrationRefused) as error:
        analyze(facts, POLICY)
    assert error.value.issues[0].code == "invalid_reference"


def test_native_frontmatter_keeps_yaml_boolean_and_null_names_as_string_tags():
    facts = snapshot(
        (tag("a", "true"), tag("b", "null")),
        (edge("a-entry", "a", "entry", "tag"), edge("b-entry", "b", "entry", "tag")),
    )
    artifacts = render(plan(analyze(facts, POLICY)), METADATA)
    assert 'tags:\n  - "null"\n  - "true"\n' in generated(artifacts, "Home — Entry.md")
    assert note_body(generated(artifacts, "Home — Entry.md")) == (
        "# Entry\n\n## Categories\n\n[[Categories.md|Browse categories]]\n"
    )


def test_numeric_token_created_by_truncation_still_has_a_nonnumeric_prefix():
    facts = snapshot((tag("a", "1" * 125 + "A"),))
    migration = plan(analyze(facts, POLICY))
    assert migration.tag_targets[0].token == "tag-" + "1" * 116


def test_tag_tokens_extend_seeds_for_casefold_natural_and_truncation_collisions():
    facts = snapshot(
        (
            tag("a", "Twin", "abcdef010001"),
            tag("b", "twin", "abcdef010002"),
            tag("c", "Twin-abcdef01", "feed"),
            tag("d", "Z" * 121, "aa"),
            tag("e", "Z" * 120 + "X", "bb"),
        )
    )
    migration = plan(analyze(facts, POLICY))
    assert {t.tag_key: t.token for t in migration.tag_targets} == {
        "a": "Twin-abcdef010001",
        "b": "twin-abcdef010002",
        "c": "Twin-abcdef01",
        "d": "Z" * 117 + "-aa",
        "e": "Z" * 117 + "-bb",
    }
    reordered = facts.model_copy(update={"items": tuple(reversed(facts.items))})
    assert plan(analyze(reordered, POLICY)).tag_targets == migration.tag_targets


def test_exhausted_seeds_suffix_natural_tag_contender_and_refuse_indistinguishable_seeds():
    facts = snapshot(
        (tag("a", "Foo", "ab"), tag("b", "foo", "cd"), tag("c", "Foo-ab", "ef"))
    )
    assert {t.tag_key: t.token for t in plan(analyze(facts, POLICY)).tag_targets} == {
        "a": "Foo-ab",
        "b": "foo-cd",
        "c": "Foo-ab-ef",
    }
    ambiguous = snapshot((tag("a", "Foo", "ab"), tag("b", "foo", "ab")))
    with pytest.raises(MigrationRefused) as error:
        plan(analyze(ambiguous, POLICY))
    assert "distinct stable naming seeds" in error.value.issues[0].guidance


def test_scoped_tags_keep_a_distinct_brain_prefix_and_explicit_existing_reuse():
    import json

    facts = snapshot(
        (tag("urgent", "Urgent"), tag("later", "Later")),
        (
            edge("urgent-entry", "urgent", "entry", "tag"),
            edge("later-entry", "later", "entry", "tag"),
        ),
    ).model_copy(update={"collection_title": "Atlas Brain"})
    migration = plan(
        analyze(facts, POLICY),
        output_format=9,
        import_location="Imports/Atlas",
        existing_vault_tags=("focus/urgent",),
        tag_reuse=(("urgent", "focus/urgent"),),
    )
    meta = METADATA.model_copy(update={"renderer_version": "9"})
    rendered = render(migration, meta)
    home = generated(rendered, "Imports/Atlas/Home — Entry.md")
    assert 'tags:\n  - "Atlas-Brain/Later"\n  - "focus/urgent"\n' in home
    record = json.loads(generated(rendered, "Imports/Atlas/migration-record.json"))
    assert {
        row["source_identity"]: row["vault_tag"] for row in record["vault_tag_mappings"]
    } == {
        "later": "Atlas-Brain/Later",
        "urgent": "focus/urgent",
    }
    collision = plan(
        analyze(facts, POLICY),
        output_format=9,
        import_location="Imports/Atlas",
        existing_vault_tags=("atlas-brain/Other", "focus/urgent"),
        tag_reuse=(("urgent", "focus/urgent"),),
    )
    tokens = {row.original_identity: row.token for row in collision.tag_targets}
    assert tokens["later"].startswith("Atlas-Brain-") and tokens["later"].endswith(
        "/Later"
    )
    assert tokens["urgent"] == "focus/urgent"
    with pytest.raises(MigrationRefused) as error:
        plan(
            analyze(facts, POLICY),
            import_location="Imports/Atlas",
            tag_reuse=(("urgent", "missing"),),
        )
    assert error.value.issues[0].code == "import_tag_reuse_unavailable"


def test_scoped_tag_mappings_keep_source_identity_when_labels_change():
    facts = snapshot((tag("a", "Renamed"), tag("b", "New topic"))).model_copy(
        update={"collection_title": "Renamed Brain"}
    )
    scoped = plan(
        analyze(facts, POLICY),
        output_format=9,
        import_location="Imports/Atlas",
        existing_vault_tags=("Atlas/Original",),
        remembered_tags=(("a", "Atlas/Original", "new"),),
    )
    assert {row.original_identity: row.token for row in scoped.tag_targets} == {
        "a": "Atlas/Original",
        "b": "Atlas/New-topic",
    }


def test_new_default_tag_stays_distinct_through_scoped_update_qualification():
    from types import SimpleNamespace

    from brz2obsidian.publication import collection_placement as placement

    original_token = "Atlas/Original"
    late_token = "atlas/new-topic"
    existing = (original_token, "Atlas/Another-note")
    facts = snapshot((tag("a", "Renamed"), tag("b", "New topic")))
    analysis = analyze(facts, POLICY)
    remembered = (("a", original_token, "new"),)

    def planned(tags):
        return plan(
            analysis,
            output_format=9,
            import_location="Imports/Atlas",
            existing_vault_tags=tags,
            remembered_tags=remembered,
        ).tag_targets

    _, proposed = planned(existing)
    _, allocated = planned(existing + (late_token,))
    assert proposed.token == "Atlas/New-topic"
    assert allocated.token.startswith("Atlas/New-topic-")
    assert allocated.token.casefold() != late_token
    original = {
        "item_targets": [{"original_identity": "a"}],
        "vault_tag_mappings": [
            {"source_identity": "a", "vault_tag": original_token, "mode": "new"}
        ],
    }
    incoming = {
        "item_targets": [{"original_identity": "a"}, {"original_identity": "b"}],
        "vault_tag_mappings": [
            *original["vault_tag_mappings"],
            {"source_identity": "b", "vault_tag": proposed.token, "mode": "new"},
        ],
    }
    approval = placement.classification_approval(incoming)

    def qualify(tokens, *, sources=None):
        text = (
            "---\ntags: ["
            + ", ".join(f'"{token}"' for token in tokens)
            + "]\n---\n# Authored\n"
        ).encode()
        inventory = SimpleNamespace(
            inventory=(SimpleNamespace(path="Author.md", excluded=False),)
        )
        return placement.classification_transition_refusal(
            inventory,
            None,
            original,
            incoming,
            approval,
            remap=False,
            sources=sources,
            existing={"Author.md": text},
        )

    assert qualify(existing) is None
    assert qualify(existing + (late_token,)) == "import_tag_namespace_changed"
    assert qualify(existing + (late_token,), sources={("tag", "a")}) is None


def test_reviewed_remap_preserves_second_source_reason_and_manual_membership():
    from brz2obsidian.application.update_facts import assemble_facts
    from brz2obsidian.core import prepare_review, select_review_effects
    from tests.application.test_graph_modules import item
    from tests.reconciliation.test_resolution import preflight

    facts = snapshot(
        (tag("a", "First"), tag("b", "Second"), item("solo", "Solo")),
        (
            edge("nav", "entry", "solo"),
            edge("entry-a", "a", "entry", "tag"),
            edge("entry-b", "b", "entry", "tag"),
            edge("solo-a", "a", "solo", "tag"),
        ),
    )
    analysis = analyze(facts, POLICY)
    options = {
        "output_format": 9,
        "import_location": "Imports/Atlas",
        "existing_vault_tags": ("focus/old", "focus/new"),
    }
    meta = METADATA.model_copy(update={"renderer_version": "9"})

    def payload(a_tag):
        migration = plan(
            analysis, **options, tag_reuse=(("a", a_tag), ("b", "focus/old"))
        )
        return {
            row.relative_path: row.content
            for row in render(migration, meta).generated_files
        }

    original = payload("focus/old")
    incoming = payload("focus/new")
    home = "Imports/Atlas/Home — Entry.md"
    solo = "Imports/Atlas/Notes/Solo.md"
    manual = b'  - "personal/keep"\n'
    current = original | {
        home: original[home].replace(
            b'  - "focus/old"\n', b'  - "focus/old"\n' + manual
        ),
        solo: original[solo].replace(b"# Solo\n", b"# Solo\n\nAuthored prose.\n"),
    }
    plan_inputs = assemble_facts(
        original,
        incoming,
        current,
        proposal_id="classified-remap",
        generation=1,
        record_path="Imports/Atlas/migration-record.json",
        classification_remap=True,
    )
    review = prepare_review(plan_inputs, preflight=preflight())
    selected = select_review_effects(review)
    assert selected.status == "selected", (review.blockers, review.requirements)
    files = {row.path: row.content.data for row in selected.files}
    assert b'tags:\n  - "focus/old"\n' + manual + b'  - "focus/new"\n' in files[home]
    assert b'tags:\n  - "focus/new"\n' in files[solo]
    assert b"Authored prose.\n" in files[solo]

    current[solo] = current[solo].replace(b'tags:\n  - "focus/old"\n', b"tags: []\n")
    conflict = prepare_review(
        assemble_facts(
            original,
            incoming,
            current,
            proposal_id="classified-remap",
            generation=2,
            record_path="Imports/Atlas/migration-record.json",
            classification_remap=True,
        ),
        preflight=preflight(),
    )
    disputed = next(row for row in conflict.proposal.changes if row.path == solo)
    assert disputed.requires_decision
    assert not conflict.ready
