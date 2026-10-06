"""Native object creation support through published workflow output."""

import hashlib
import json

import yaml

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_categories_workflow import typed_archive
from tests.application.test_graph_workflow import graph_archive, identity
from tests.local_acceptance.checker import compare_vaults
from tests.local_acceptance.run import reordered_archive


def test_native_template_date_tokens_survive_safe_yaml_rewriting_and_insertion(
    tmp_path,
):
    source = typed_archive(tmp_path / "typed.brz")
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    templates = sorted((vault / "Templates").glob("*.md"))
    assert {p.name for p in templates} == {
        "New note.md",
        "Concept.md",
        "Category starter.md",
        "Member template starter.md",
    }
    for path in templates:
        frontmatter = path.read_text(encoding="utf-8").split("---", 2)[1]
        properties = yaml.safe_load(frontmatter)
        assert properties["created"] == "{{date:YYYY-MM-DD}}"
        assert properties["updated"] == "{{date:YYYY-MM-DD}}"
        if path.name == "Concept.md":
            properties["categories"] = ["[[Categories/Concept Renamed]]"]
            properties["appearance_category"] = "[[Categories/Concept Renamed]]"
        rewritten = yaml.safe_dump(properties, allow_unicode=True, sort_keys=False)
        reread = yaml.safe_load(rewritten)
        assert reread["created"] == "{{date:YYYY-MM-DD}}"
        assert reread["updated"] == "{{date:YYYY-MM-DD}}"
        inserted = yaml.safe_load(
            rewritten.replace("{{date:YYYY-MM-DD}}", "2030-04-05")
        )
        assert inserted["created"] == "2030-04-05"
        assert inserted["updated"] == "2030-04-05"


def test_full_templates_initialize_new_objects_without_imported_identity(tmp_path):
    source = typed_archive(tmp_path / "typed.brz")
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    template = (vault / "Templates/Concept.md").read_text(encoding="utf-8")
    assert template == (
        '---\ncategories:\n  - "[[Categories/Concept.md]]"\n'
        'appearance_category: "[[Categories/Concept.md]]"\n'
        "icon:\n"
        'created: "{{date:YYYY-MM-DD}}"\nupdated: "{{date:YYYY-MM-DD}}"\n'
        "tags: []\naliases: []\n---\n\n# {{title}}\n"
    )
    generic = (vault / "Templates/New note.md").read_text(encoding="utf-8")
    assert generic == (
        "---\ncategories: []\nappearance_category:\n"
        "icon:\n"
        'created: "{{date:YYYY-MM-DD}}"\nupdated: "{{date:YYYY-MM-DD}}"\n'
        "tags: []\naliases: []\n---\n\n# {{title}}\n"
    )
    assert "source_collection_id" not in template + generic
    assert "source_item_id" not in template + generic
    assert json.loads((vault / ".obsidian/core-plugins.json").read_bytes())["templates"]
    assert json.loads((vault / ".obsidian/templates.json").read_bytes()) == {
        "folder": "Templates",
        "dateFormat": "YYYY-MM-DD",
    }
    assert json.loads((vault / ".obsidian/types.json").read_bytes()) == {
        "types": {
            "categories": "multitext",
            "appearance_category": "text",
            "icon": "text",
            "created": "date",
            "updated": "date",
            "tags": "tags",
            "aliases": "aliases",
            "source_collection_id": "text",
            "source_item_id": "text",
        }
    }


def test_starters_and_guide_support_manual_extension_without_a_registry(tmp_path):
    source = typed_archive(tmp_path / "typed.brz")
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    starter = (vault / "Templates/Category starter.md").read_text(encoding="utf-8")
    assert 'tags:\n  - "categories"' in starter
    assert "# {{title}}" in starter
    assert "![[Templates/Bases/Members.base#Members]]" in starter
    assert "![[Templates/Bases/Gallery.base#Gallery]]" in starter
    member = (vault / "Templates/Member template starter.md").read_text(
        encoding="utf-8"
    )
    assert "categories: []" in member and "appearance_category:\n" in member
    assert "{{date:YYYY-MM-DD}}" in member and "source_item_id" not in member + starter
    base = (vault / "Templates/Bases/Starter.base").read_text(encoding="utf-8")
    assert "list(categories).contains(this)" in base
    assert '!file.inFolder("Templates")' in base
    assert '!file.inFolder("Attachments")' in base
    assert "      - formula.picture\n      - file.name" in base
    guide = (vault / "Vault guide.md").read_text(encoding="utf-8")
    for instruction in (
        "Templates: Insert template",
        "Editing view",
        "names and aliases",
        "edit categories directly",
        "scalar properties",
        "updated explicitly",
        "source_collection_id",
        "source_item_id",
        "meaningful entity",
        "membership order",
        "body-icon snapshots",
        "standalone contextual Base",
        "[[Templates/Concept.md]]",
        "[[Templates/Category starter.md]]",
        "[[Templates/Member template starter.md]]",
        "[[Templates/Bases/Starter.base]]",
        "kepano",
    ):
        assert instruction in guide
    assert 'categories:\n  - "[[Categories/Experiments]]"' in guide
    assert "template:" not in member + starter
    assert "vault_role:" not in member + starter
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert "[[Vault guide.md|Vault guide]]" in report
    assert "Declared colours remain in migration-record.json only" in report


def test_inspection_manifest_record_and_configuration_account_for_every_support_file(
    tmp_path,
):
    source = typed_archive(tmp_path / "typed.brz")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert sorted(p.name for p in tmp_path.iterdir()) == ["typed.brz"]
    expected = {
        "MIGRATION REPORT.md": "report",
        "migration-record.json": "migration_record",
        ".obsidian/app.json": "configuration",
        ".obsidian/bookmarks.json": "configuration",
        ".obsidian/core-plugins.json": "configuration",
        ".obsidian/templates.json": "configuration",
        ".obsidian/types.json": "configuration",
        "Uncreated targets.md": "listing",
        "Categories.md": "overview",
        "Vault guide.md": "guide",
        "Templates/New note.md": "template",
        "Templates/Concept.md": "template",
        "Templates/Category starter.md": "starter",
        "Templates/Member template starter.md": "starter",
        "Templates/Bases/Members.base": "base",
        "Templates/Bases/Gallery.base": "base",
        "Templates/Bases/Categories.base": "base",
        "Templates/Bases/Starter.base": "starter",
    }
    assert {
        a.relative_path: a.purpose for a in inspected.inspection.support_artifacts
    } == expected
    assert inspected.counts.planned_support_files == 18
    assert inspected.counts.actual_support_files is None and inspected.receipt is None
    assert set(inspected.inspection.reserved_support_paths) == {"Tag memberships.md"}
    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    assert converted.counts.actual_support_files == 18
    assert converted.counts.actual_notes == 3
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert {
        a["relative_path"]: a["purpose"] for a in record["support_artifacts"]
    } == expected
    assert {entry.relative_path for entry in converted.receipt.manifest} == set(
        expected
    ) | {"Home — Entry.md", "Categories/Concept.md", "Notes/Empty member.md"}
    for field, filename in (
        ("obsidian_configuration", "app.json"),
        ("obsidian_core_plugins_configuration", "core-plugins.json"),
        ("obsidian_templates_configuration", "templates.json"),
        ("obsidian_property_types_configuration", "types.json"),
    ):
        assert record[field] == json.loads(
            (vault / ".obsidian" / filename).read_bytes()
        )
    assert record["obsidian_configuration"]["openBehavior"] == "file:Home — Entry.md"
    assert record["obsidian_configuration"]["alwaysUpdateLinks"]
    assert {a["kind"] for a in record["adaptations"]} >= {
        "native_templates_configuration",
        "category_template",
        "vault_maintenance_guide",
    }
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash


def test_category_templates_reuse_safe_targets_through_collisions_and_reordering(
    tmp_path,
):
    # Leave room for the intentionally maximal names in a managed worktree.
    tmp_path = tmp_path.parent / "tc"
    tmp_path.mkdir()
    source = graph_archive(
        tmp_path / "collisions.brz",
        {
            1: "Entry",
            2: "New note",
            3: "Books",
            4: "Books",
            5: "Long " + "a" * 150,
            6: "Café",
            7: "Cafe\u0301",
            8: 'Concept: "quoted" [type]',
        },
        kinds={n: 2 for n in range(2, 9)},
    )
    workflow = default_workflow()
    inspection = workflow.inspect(source)
    assert inspection.outcome == "clean", inspection.issues
    targets = {t.item_key: t.relative_path for t in inspection.inspection.item_targets}
    assert targets[identity(2)] == "Categories/New note — 00000000.md"
    assert (
        targets[identity(3)] == "Categories/Books — 00000000000000000000000000000003.md"
    )
    assert (
        targets[identity(4)] == "Categories/Books — 00000000000000000000000000000004.md"
    )
    assert targets[identity(5)] == "Categories/Long " + "a" * 115 + ".md"
    assert (
        targets[identity(6)] == "Categories/Café — 00000000000000000000000000000006.md"
    )
    assert (
        targets[identity(7)] == "Categories/Café — 00000000000000000000000000000007.md"
    )
    assert targets[identity(8)] == "Categories/Concept - quoted (type).md"
    first, second, third = (tmp_path / name for name in ("first", "second", "third"))
    reordered = tmp_path / "reordered.brz"
    reordered_archive(source, reordered)
    for archive, destination in (
        (source, first),
        (source, second),
        (reordered, third),
    ):
        result = workflow.convert(archive, destination)
        assert result.outcome == "clean", result.issues
        assert result.counts.actual_category_notes == 7
        assert result.counts.actual_support_files == 23
        templates = list((destination / "Templates").glob("*.md"))
        assert len(templates) == 10
        assert len({p.name.casefold() for p in templates}) == 10
        for number in range(2, 9):
            target = targets[identity(number)]
            template = destination / "Templates" / target.removeprefix("Categories/")
            text = template.read_text(encoding="utf-8")
            expected_link = json.dumps("[[" + target + "]]", ensure_ascii=False)
            assert "categories:\n  - " + expected_link in text
            assert "appearance_category: " + expected_link in text
            assert "source_item_id" not in text
            assert "icon:\n" in text and "{{date:YYYY-MM-DD}}" in text
    compare_vaults(first, second)
    compare_vaults(first, third)
