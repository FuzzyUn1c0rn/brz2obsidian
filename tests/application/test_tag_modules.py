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
    assert note_body(generated(artifacts, "Home — Entry.md")) == "# Entry\n\n"


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
