"""Native category support observed through inspection and published vaults."""

import hashlib
import json

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_categories_workflow import typed_archive
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_properties_workflow import parts, set_thoughts
from tests.application.test_verified_coverage import add_attachment, write_source


def test_inspection_plans_and_conversion_accounts_for_native_category_support(tmp_path):
    source = typed_archive(tmp_path / "typed.brz")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    expected = {
        "MIGRATION REPORT.md": "report",
        "migration-record.json": "migration_record",
        ".obsidian/app.json": "configuration",
        ".obsidian/bookmarks.json": "configuration",
        ".obsidian/core-plugins.json": "configuration",
        "Uncreated targets.md": "listing",
        "Categories.md": "overview",
        "Templates/Bases/Members.base": "base",
        "Templates/Bases/Gallery.base": "base",
        "Templates/Bases/Categories.base": "base",
        ".obsidian/templates.json": "configuration",
        ".obsidian/types.json": "configuration",
        "Vault guide.md": "guide",
        "Templates/New note.md": "template",
        "Templates/Concept.md": "template",
        "Templates/Category starter.md": "starter",
        "Templates/Member template starter.md": "starter",
        "Templates/Bases/Starter.base": "starter",
    }
    assert inspected.outcome == "clean", inspected.issues
    assert {
        a.relative_path: a.purpose for a in inspected.inspection.support_artifacts
    } == expected
    assert inspected.counts.planned_support_files == 18
    assert inspected.counts.actual_support_files is None
    assert inspected.receipt is None
    assert "Categories.md" not in inspected.inspection.reserved_support_paths
    assert "Templates/New note.md" not in inspected.inspection.reserved_support_paths
    assert sorted(p.name for p in tmp_path.iterdir()) == ["typed.brz"]

    vault = tmp_path / "vault"
    converted = workflow.convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    assert converted.receipt.verified and converted.receipt.published
    assert converted.counts.actual_notes == 3
    assert converted.counts.actual_support_files == 18
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert {
        a["relative_path"]: a["purpose"] for a in record["support_artifacts"]
    } == expected
    assert {entry.relative_path for entry in converted.receipt.manifest} == {
        p.relative_to(vault).as_posix() for p in vault.rglob("*") if p.is_file()
    }
    assert (
        (vault / "Home — Entry.md")
        .read_text(encoding="utf-8")
        .endswith("## Categories\n\n[[Categories.md|Browse categories]]\n")
    )
    assert (vault / "Categories.md").read_text(encoding="utf-8") == (
        "# Categories\n\n![[Templates/Bases/Categories.base]]\n"
    )
    assert (
        (vault / "Categories/Concept.md")
        .read_text(encoding="utf-8")
        .endswith(
            "## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n"
            "## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n\n"
        )
    )
    configuration = json.loads((vault / ".obsidian/app.json").read_bytes())
    assert configuration["alwaysUpdateLinks"] is True
    assert configuration["openBehavior"] == "file:Home — Entry.md"
    assert (
        json.loads((vault / ".obsidian/core-plugins.json").read_bytes())["bases"]
        is True
    )
    assert (
        json.loads((vault / ".obsidian/bookmarks.json").read_bytes())["items"][0][
            "path"
        ]
        == "Home — Entry.md"
    )
    assert {a["kind"] for a in record["adaptations"]} >= {
        "category_dashboard",
        "categories_overview",
        "native_bases_configuration",
    }
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_native_views_express_membership_roles_icon_precedence_and_reviewed_columns(
    tmp_path,
):
    source = graph_archive(
        tmp_path / "views.brz",
        {
            1: "Entry",
            2: "Concept",
            3: "Template Method",
            4: "Override",
            5: "Prose only",
            6: "categories",
            7: "Hierarchy parent",
        },
        [(2, 3, 1, 2, -1), (2, 4, 1, 2, -1), (7, 5, 1, 1, -1)],
        kinds={2: 2, 6: 4},
        notes={
            1: (b"Original Home.\r\n", 4),
            5: (b"[[Concept]]\n", 4),
            6: (b"Tag-owned content.\n", 4),
        },
    )
    files = parts(source)
    set_thoughts(
        files,
        {identity(3): {"TypeId": identity(2)}, identity(4): {"TypeId": identity(2)}},
    )
    add_attachment(
        files, identity(3002), 5, "category.png", b"category bytes", owner=identity(2)
    )
    add_attachment(
        files, identity(3004), 5, "override.png", b"override bytes", owner=identity(4)
    )
    source = write_source(tmp_path, files)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    member = (vault / "Notes/Template Method.md").read_text(encoding="utf-8")
    assert 'categories:\n  - "[[Categories/Concept.md]]"' in member
    assert "icon:\n" in member
    assert "categories: []\n" in (vault / "Notes/Prose only.md").read_text(
        encoding="utf-8"
    )
    table = (vault / "Templates/Bases/Members.base").read_text(encoding="utf-8")
    assert table.startswith(
        'filters:\n  and:\n    - file.ext == "md"\n    - \'!file.inFolder("Templates")\'\n    - \'!file.inFolder("Attachments")\'\n    - list(categories).contains(this)\n'
    )
    assert 'link("Concept")' not in table and 'Template")' not in table
    assert "list(categories).contains(appearance_category)" in table
    assert 'appearance_category.asFile().inFolder("Categories")' in table
    assert (
        'list(appearance_category.asFile().properties.tags).contains("categories")'
        in table
    )
    assert "icon.asFile().ext.lower()" in table
    assert "formula.provider.properties.icon" in table
    assert (
        "formula.explicit_icon, formula.explicit_icon, formula.inherited_icon" in table
    )
    assert "image(formula.effective_icon.asFile())" in table
    assert '"No inheritance"' in table and '"Invalid provider"' in table
    assert "displayName: Icon" in table and "displayName: Note" in table
    assert "displayName: Inheritance" in table
    assert (
        "    order:\n      - formula.picture\n      - file.name\n      - formula.provider_status\n      - note.categories\n      - note.created\n      - note.updated\n"
    ) in table
    assert "sort:\n      - property: file.name\n        direction: ASC" in table
    gallery = (vault / "Templates/Bases/Gallery.base").read_text(encoding="utf-8")
    assert (
        "type: cards\n    name: Gallery\n    image: formula.effective_icon\n" in gallery
    )
    assert "imageFit: contain" in gallery
    overview = (vault / "Templates/Bases/Categories.base").read_text(encoding="utf-8")
    assert 'file.inFolder("Categories")' in overview
    assert 'list(tags).contains("categories")' in overview
    assert "displayName: Category" in overview
    assert "    order:\n      - formula.picture\n      - file.name\n" in overview
    assert all(
        "Appearance" not in base and "html(" not in base
        for base in (table, gallery, overview)
    )
    assert (
        vault / "Attachments/00000000000000000000000000000002/category.png"
    ).read_bytes() == b"category bytes"
    assert (
        vault / "Attachments/00000000000000000000000000000004/override.png"
    ).read_bytes() == b"override bytes"
    assert b"Original Home.\r\n" in (vault / "Home — Entry.md").read_bytes()
    assert (
        vault / "Attachments/00000000000000000000000000000001/Notes.md.original"
    ).read_bytes() == b"Original Home.\r\n"
