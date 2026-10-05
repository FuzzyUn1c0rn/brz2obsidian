import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from brz2obsidian.cli import main
from brz2obsidian.vault_check import check_vault


def write(vault, name, text):
    path = vault / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path


def inventory(vault):
    if not vault.is_dir():
        return None
    result = {}
    for root, directories, files in os.walk(vault, followlinks=False):
        for name in sorted(directories + files):
            path = Path(root) / name
            relative = path.relative_to(vault).as_posix()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(
                info, "st_file_attributes", 0
            ) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                result[relative] = ("reparse", os.readlink(path))
                if name in directories:
                    directories.remove(name)
            elif stat.S_ISDIR(info.st_mode):
                result[relative] = None
            else:
                with open(path, "rb") as file:
                    result[relative] = hashlib.sha256(file.read()).hexdigest()
    return result


def checked(vault):
    before = inventory(vault)
    result = check_vault(vault)
    assert inventory(vault) == before
    assert check_vault(vault) == result
    assert inventory(vault) == before
    return result


def test_check_current_source_free_vault_returns_distinct_durable_result(tmp_path):
    vault = tmp_path / "editable"
    write(vault, "Notes/Manual.md", "# A manual note\n[[Not created yet]]\n")
    write(vault, "migration-record.json", '{"invented": "not authoritative"}')
    write(vault, "caller.bin", "arbitrary caller bytes\r\n")
    (vault / "empty folder").mkdir()

    result = checked(vault)

    assert result.outcome == "clean"
    assert result.vault.location == str(vault.absolute())
    assert result.vault.name == "editable"
    assert result.counts.inventory_files == 3
    assert result.counts.markdown_files == result.counts.read_markdown_files == 1
    assert result.counts.base_files == result.counts.read_base_files == 0
    envelope = json.loads(result.model_dump_json(by_alias=True))
    assert envelope["schema"] == "brz2obsidian.vault-check"
    assert envelope["schema_version"] == 1
    assert (
        result.__class__.model_validate_json(result.model_dump_json(by_alias=True))
        == result
    )
    with pytest.raises(ValidationError):
        result.outcome = "issues"
    with pytest.raises(ValidationError):
        result.counts.read_markdown_files = 0
    with pytest.raises(ValidationError):
        result.__class__.model_validate(
            {**result.model_dump(by_alias=True), "extra": 1}
        )
    with pytest.raises(ValidationError):
        result.counts.__class__(read_markdown_files="1")


def test_custom_fields_blank_overrides_opaque_ids_and_template_dates_are_valid(
    tmp_path,
):
    write(
        tmp_path,
        "Notes/Template topic.md",
        """\ufeff---\r
categories: []\r
appearance_category:\r
icon: ''\r
foreground_color: '#aB12fF'\r
background_color:\r
created: 2000-02-29\r
updated: '2025-01-31'\r
tags: [topic]\r
aliases: [Another name]\r
source_collection_id: 'opaque collection: 1'\r
source_item_id: opaque/item\r
custom: {nested: [1, true, null]}\r
---\r
# Manual\r
""",
    )
    write(
        tmp_path,
        "Templates/Starter.md",
        """---
categories: []
appearance_category: ''
created: "{{date:YYYY-MM-DD}}"
updated: "{{date}}"
tags: [categories]
aliases: []
---
# {{title}}
""",
    )
    result = checked(tmp_path)
    assert result.outcome == "clean"
    assert result.counts.imported_notes == 1
    assert result.counts.category_notes == 0


def test_removed_colour_names_are_custom_fields_in_read_only_library_and_cli(
    tmp_path, capsys
):
    write(
        tmp_path,
        "Notes/Manual.md",
        "---\nforeground_color: {custom: [1, true, null]}\n"
        "background_color: false\n---\n# Manual\n",
    )
    result = checked(tmp_path)
    assert result.outcome == "clean"
    before = inventory(tmp_path)
    assert main(["check-vault", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == result.model_dump(
        mode="json", by_alias=True
    )
    assert inventory(tmp_path) == before


@pytest.mark.parametrize(
    "property,value",
    [
        ("categories", "null"),
        ("categories", "'[[Books]]'"),
        ("appearance_category", "['[[Books]]']"),
        ("icon", "42"),
        ("tags", "topic"),
        ("aliases", "[true]"),
        ("created", "'2025-02-29'"),
        ("updated", "true"),
        ("created", "'{{date:YYYY-MM-DD}}'"),
        ("source_collection_id", "null"),
        ("source_item_id", "[opaque]"),
    ],
)
def test_known_property_cardinality_and_values_are_checked(tmp_path, property, value):
    write(tmp_path, "Notes/Manual.md", f"---\n{property}: {value}\n---\n")
    result = checked(tmp_path)
    assert result.outcome == "issues"
    assert any(
        issue.code == "invalid_property" and issue.property == property
        for issue in result.issues
    )


@pytest.mark.parametrize(
    "frontmatter",
    [
        "categories: [",
        "tags: []\ntags: []",
        "custom: {x: 1, x: 2}",
        "custom: &shared {x: 1}\ncopy: {<<: *shared, x: 2}",
        "custom: !!python/object/apply:os.system ['echo forbidden']",
        "- not a mapping",
        "null",
        "42: invalid key",
        "tags: []\n",
    ],
)
def test_malformed_duplicate_and_executable_yaml_is_diagnostic_data(
    tmp_path, frontmatter
):
    closing = "" if frontmatter == "tags: []\n" else "\n---\n"
    write(tmp_path, "Notes/Bad.md", "---\n" + frontmatter + closing)
    write(tmp_path, "Notes/Other.md", "---\ncreated: 'not a date'\n---\n")
    result = checked(tmp_path)
    assert result.outcome == "issues"
    assert [(issue.artifact, issue.code) for issue in result.issues] == [
        ("Notes/Bad.md", "invalid_frontmatter"),
        ("Notes/Other.md", "invalid_property"),
    ]
    assert result.counts.category_notes is result.counts.imported_notes is None


def category_fixture(vault):
    write(
        vault,
        "Categories/Books.md",
        "---\ntags: [categories]\nicon: '[[Attachments/book.png]]'\n---\n",
    )
    write(vault, "Categories/Topic.v2.md", "---\ntags: [categories]\n---\n")
    write(vault, "Attachments/book.png", "synthetic image bytes")


def test_membership_and_provider_resolve_file_identity_and_dotted_short_links(tmp_path):
    category_fixture(tmp_path)
    write(
        tmp_path,
        "Notes/Member.md",
        """---
categories: ['[[Categories/Books.md|Books]]', '[[Topic.v2#Heading]]']
appearance_category: '[[Books#Heading|Provider]]'
icon: '[[book.png|Own icon]]'
---
[[Intentional uncreated ordinary target]]
""",
    )
    result = checked(tmp_path)
    assert result.outcome == "clean"
    assert result.counts.category_notes == 2


def test_ambiguous_category_is_reported_before_convenient_role_filtering(tmp_path):
    category_fixture(tmp_path)
    write(tmp_path, "Notes/Books.md", "---\ntags: [source/books]\n---\n")
    write(tmp_path, "Templates/Books.md", "---\ntags: [categories]\n---\n")
    write(
        tmp_path,
        "Notes/Member.md",
        "---\ncategories: ['[[Books]]']\nappearance_category: '[[Books]]'\n---\n",
    )
    result = checked(tmp_path)
    ambiguous = [
        issue for issue in result.issues if issue.code == "ambiguous_reference"
    ]
    assert [(issue.property, issue.candidates) for issue in ambiguous] == [
        (
            "appearance_category",
            ("Categories/Books.md", "Notes/Books.md", "Templates/Books.md"),
        ),
        ("categories", ("Categories/Books.md", "Notes/Books.md", "Templates/Books.md")),
    ]
    with pytest.raises(ValidationError):
        ambiguous[0].candidates = ()


@pytest.mark.parametrize(
    "target",
    [
        "Notes/Tag.md",
        "Categories/Untagged.md",
        "Templates/Category.md",
        "Attachments/Category.md",
    ],
)
def test_category_membership_requires_folder_and_native_tag_role(tmp_path, target):
    write(
        tmp_path,
        target,
        "---\ntags: [categories]\n---\n"
        if "Untagged" not in target
        else "# Not a category\n",
    )
    write(tmp_path, "Notes/Member.md", f"---\ncategories: ['[[{target}]]']\n---\n")
    result = checked(tmp_path)
    assert [(issue.code, issue.property) for issue in result.issues] == [
        ("invalid_category", "categories")
    ]


@pytest.mark.parametrize(
    "provider",
    ["[[Categories/Missing]]", "[[Categories/Topic.v2.md]]", "[[Notes/Ordinary.md]]"],
)
def test_invalid_provider_remains_visible_with_an_explicit_icon(tmp_path, provider):
    category_fixture(tmp_path)
    write(tmp_path, "Notes/Ordinary.md", "# Ordinary\n")
    write(
        tmp_path,
        "Notes/Member.md",
        f"---\ncategories: ['[[Categories/Books]]']\nappearance_category: '{provider}'\nicon: '[[Attachments/book.png]]'\n---\n",
    )
    result = checked(tmp_path)
    assert [(issue.code, issue.property) for issue in result.issues] == [
        ("invalid_provider", "appearance_category")
    ]


def test_imported_identity_duplicates_follow_current_properties_through_renames(
    tmp_path,
):
    properties = "---\nsource_collection_id: opaque collection\nsource_item_id: opaque item\n---\n"
    write(tmp_path, "Notes/Renamed.md", properties)
    write(tmp_path, "Categories/Other.md", properties + "# Other\n")
    write(tmp_path, "migration-record.json", '{"identity": "unrelated"}')
    result = checked(tmp_path)
    assert result.counts.imported_notes == 2
    assert [
        (issue.artifact, issue.code, issue.candidates) for issue in result.issues
    ] == [
        (
            "Categories/Other.md",
            "duplicate_source_identity",
            ("Categories/Other.md", "Notes/Renamed.md"),
        ),
        (
            "Notes/Renamed.md",
            "duplicate_source_identity",
            ("Categories/Other.md", "Notes/Renamed.md"),
        ),
    ]


def test_active_base_and_local_images_are_checked_without_code_or_comment_examples(
    tmp_path,
):
    write(
        tmp_path,
        "Templates/Bases/Members.base",
        "views:\n  - type: table\n    name: Members\nformulas:\n  constant: 'do_not_execute()'\n",
    )
    write(tmp_path, "Attachments/with space.png", "synthetic image")
    write(
        tmp_path,
        "Notes/Manual.md",
        """# Manual
![[Templates/Bases/Members.base#Members|View]]
![[with space.png|Snapshot]]
![relative](../Attachments/with%20space.png "Caption")
![remote](https://example.invalid/image.png)
![[Future ordinary note]]
`![[Missing-inline.base]]` and `![code](missing-code.png)`
<!-- ![[Missing-comment.base]] ![comment](missing-comment.png) -->
<!--
![[Missing-multiline.base]]
-->
```yaml
icon: '[[Missing.png]]'
![[Missing-fence.base]]
```
    ![[Missing-indented.base]]
""",
    )
    assert checked(tmp_path).outcome == "clean"
    (tmp_path / "Attachments/with space.png").unlink()
    (tmp_path / "Templates/Bases/Members.base").unlink()
    result = checked(tmp_path)
    assert [(issue.code, issue.reference) for issue in result.issues] == [
        ("missing_base", "[[Templates/Bases/Members.base#Members|View]]"),
        ("missing_image", "../Attachments/with%20space.png"),
        ("missing_image", "[[with space.png|Snapshot]]"),
    ]


@pytest.mark.parametrize(
    "target",
    ["Attachments/empty.png", "Attachments/wrong.pdf", "Attachments/directory.png"],
)
def test_icons_require_nonempty_supported_regular_image_files(tmp_path, target):
    if "directory" in target:
        (tmp_path / target).mkdir(parents=True)
    else:
        write(tmp_path, target, "" if "empty" in target else "PDF bytes")
    write(tmp_path, "Notes/Manual.md", f"---\nicon: '[[{target}]]'\n---\n")
    assert [issue.code for issue in checked(tmp_path).issues] == ["missing_image"]


def test_ambiguous_images_and_bases_use_sorted_inventory_candidates(tmp_path):
    write(tmp_path, "Attachments/a/icon.png", "a")
    write(tmp_path, "Attachments/z/icon.png", "z")
    write(tmp_path, "Templates/Bases/a/Members.base", "views: []\n")
    write(tmp_path, "Templates/Bases/z/Members.base", "views: []\n")
    write(
        tmp_path,
        "Notes/Manual.md",
        "---\nicon: '[[icon.png]]'\n---\n![[Members.base#Members]]\n",
    )
    result = checked(tmp_path)
    assert [(issue.reference, issue.candidates) for issue in result.issues] == [
        (
            "[[Members.base#Members]]",
            ("Templates/Bases/a/Members.base", "Templates/Bases/z/Members.base"),
        ),
        ("[[icon.png]]", ("Attachments/a/icon.png", "Attachments/z/icon.png")),
    ]


@pytest.mark.parametrize(
    "data",
    [
        "views: [",
        "views: []\nviews: []",
        "!!python/object/apply:os.system ['echo forbidden']",
        "- not a mapping",
    ],
)
def test_base_yaml_is_structural_data_and_never_executes_formulas(tmp_path, data):
    write(tmp_path, "Templates/Bases/Broken.base", data)
    result = checked(tmp_path)
    assert result.counts.read_base_files == 1
    assert [(issue.artifact, issue.code) for issue in result.issues] == [
        ("Templates/Bases/Broken.base", "invalid_base")
    ]


@pytest.mark.parametrize("relative", ["missing", "file"])
def test_unavailable_vault_returns_failed_with_unavailable_totals(tmp_path, relative):
    vault = tmp_path / relative
    if relative == "file":
        vault.write_bytes(b"caller file")
    result = checked(vault)
    assert result.outcome == "failed"
    assert [issue.code for issue in result.issues] == ["read_failure"]
    assert result.counts.inventory_files is None
    assert result.counts.markdown_files is None
    assert result.counts.read_markdown_files == 0
    assert result.counts.category_notes is None


def test_note_io_failure_keeps_other_diagnostics_and_honest_processed_counts(
    tmp_path, monkeypatch
):
    broken = write(tmp_path, "Notes/A unreadable.md", "---\ntags: []\n---\n")
    write(tmp_path, "Notes/Z readable.md", "---\ncreated: wrong\n---\n")
    write(tmp_path, "Templates/Bases/Readable.base", "views: []\n")
    before = inventory(tmp_path)
    original = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path == broken:
            raise PermissionError("synthetic unreadable note")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as boundary:
        boundary.setattr(Path, "read_text", unreadable)
        result = check_vault(tmp_path)
        assert check_vault(tmp_path) == result
    assert inventory(tmp_path) == before
    assert result.outcome == "failed"
    assert [(issue.artifact, issue.code) for issue in result.issues] == [
        ("Notes/A unreadable.md", "read_failure"),
        ("Notes/Z readable.md", "invalid_property"),
    ]
    assert result.counts.inventory_files == 3
    assert result.counts.markdown_files == 2
    assert result.counts.read_markdown_files == 1
    assert result.counts.read_base_files == 1
    assert result.counts.category_notes is result.counts.imported_notes is None


@pytest.mark.parametrize(
    "reference",
    [
        "../outside.png",
        "/outside.png",
        "C:/outside.png",
        "//server/share/outside.png",
        r"\\server\share\outside.png",
        r"\\?\C:\outside.png",
        "file:///C:/outside.png",
        "Attachments/evil\x7f.png",
        "Attachments/NUL.png",
        "Attachments/CON.md",
        "Attachments/evil?.png",
    ],
)
def test_unsafe_required_wikilinks_are_reported_without_external_reads(
    tmp_path, reference
):
    # JSON strings are also valid YAML scalars and preserve control characters.
    write(
        tmp_path,
        "Notes/Manual.md",
        "---\nicon: " + json.dumps("[[" + reference + "]]") + "\n---\n",
    )
    result = checked(tmp_path)
    assert [issue.code for issue in result.issues] == ["unsafe_reference"]


def test_markdown_image_traversal_and_encoded_external_paths_are_unsafe(tmp_path):
    write(
        tmp_path,
        "Notes/Manual.md",
        "![outside](../../outside.png)\n![encoded](%2e%2e/%2e%2e/outside.png)\n![file](file:///C:/outside.png)\n",
    )
    result = checked(tmp_path)
    assert [issue.code for issue in result.issues] == ["unsafe_reference"] * 3


def test_linked_file_is_not_opened_or_selected_as_a_safe_reference(
    tmp_path, monkeypatch
):
    outside = tmp_path / "outside"
    outside.mkdir()
    external = write(outside, "Secret.md", "---\ncreated: wrong\n---\n")
    vault = tmp_path / "vault"
    vault.mkdir()
    linked = vault / "Categories" / "Secret.md"
    linked.parent.mkdir()
    try:
        linked.symlink_to(external)
    except OSError:
        pytest.skip("Creating symbolic links requires OS support or privilege")
    write(
        vault, "Notes/Manual.md", "---\ncategories: ['[[Categories/Secret.md]]']\n---\n"
    )
    original = Path.read_text

    def forbid_external(path, *args, **kwargs):
        assert path not in {external, linked}, "Checker opened a linked external note"
        return original(path, *args, **kwargs)

    with monkeypatch.context() as boundary:
        boundary.setattr(Path, "read_text", forbid_external)
        result = checked(vault)
    assert "invalid_property" not in [issue.code for issue in result.issues]
    assert any(
        issue.code == "unsafe_reference" and issue.reference for issue in result.issues
    )
    assert external.read_text(encoding="utf-8") == "---\ncreated: wrong\n---\n"


def test_enumeration_failure_retains_observed_diagnostics_and_null_totals(
    tmp_path, monkeypatch
):
    blocked = tmp_path / "Blocked"
    write(tmp_path, "Blocked/Hidden.md", "# Hidden\n")
    write(tmp_path, "Notes/Readable.md", "---\ntags: scalar\n---\n")
    before = inventory(tmp_path)
    original = os.scandir

    def unreadable(path):
        if Path(path) == blocked:
            raise PermissionError("synthetic enumeration failure")
        return original(path)

    with monkeypatch.context() as boundary:
        boundary.setattr(os, "scandir", unreadable)
        result = check_vault(tmp_path)
        assert check_vault(tmp_path) == result
    assert inventory(tmp_path) == before
    assert result.outcome == "failed"
    assert [(issue.artifact, issue.code) for issue in result.issues] == [
        ("Blocked", "read_failure"),
        ("Notes/Readable.md", "invalid_property"),
    ]
    assert result.counts.inventory_files is result.counts.markdown_files is None
    assert result.counts.read_markdown_files == 1
    assert result.counts.category_notes is result.counts.imported_notes is None


def test_unreadable_base_keeps_available_note_measurements(tmp_path, monkeypatch):
    broken = write(tmp_path, "Templates/Bases/Broken.base", "views: []\n")
    write(tmp_path, "Notes/Manual.md", "![[Templates/Bases/Broken.base]]\n")
    before = inventory(tmp_path)
    original = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path == broken:
            raise PermissionError("synthetic unreadable Base")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as boundary:
        boundary.setattr(Path, "read_text", unreadable)
        result = check_vault(tmp_path)
    assert inventory(tmp_path) == before
    assert result.outcome == "failed"
    assert result.counts.base_files == 1
    assert result.counts.read_base_files == 0
    assert result.counts.read_markdown_files == 1
    assert result.counts.category_notes == result.counts.imported_notes == 0


def junction(link, target):
    if os.name != "nt":
        pytest.skip("Windows junction control")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        pytest.skip("Creating junctions is unavailable")


def test_windows_junction_child_and_vault_root_are_never_followed(
    tmp_path, monkeypatch
):
    outside = tmp_path / "outside"
    write(outside, "Secret.md", "---\ncreated: wrong\n---\n")
    write(outside, "outside.png", "outside sentinel")
    vault = tmp_path / "vault"
    write(
        vault,
        "Notes/Manual.md",
        "---\ncategories: ['[[Categories/Secret.md]]']\n---\n![[Categories/outside.png]]\n",
    )
    linked = vault / "Categories"
    junction(linked, outside)
    before = inventory(vault), inventory(outside)
    original = Path.read_text

    def forbid_external(path, *args, **kwargs):
        assert not path.resolve().is_relative_to(outside), (
            "Checker opened a junction target"
        )
        return original(path, *args, **kwargs)

    try:
        with monkeypatch.context() as boundary:
            boundary.setattr(Path, "read_text", forbid_external)
            result = checked(vault)
            root_result = check_vault(linked)
        assert result.outcome == "issues"
        assert [issue.code for issue in result.issues] == ["unsafe_reference"] * 3
        assert result.counts.read_markdown_files == 1
        assert result.counts.inventory_files is None
        assert root_result.outcome == "failed"
        assert root_result.counts.read_markdown_files == 0
        assert [issue.code for issue in root_result.issues] == ["unsafe_reference"]
        assert (inventory(vault), inventory(outside)) == before
    finally:
        # Remove only the junction entry; never traverse or recursively delete its target.
        linked.rmdir()


def test_unicode_normalized_candidate_collisions_are_retained_not_overwritten(tmp_path):
    write(tmp_path, "Categories/Café.md", "---\ntags: [categories]\n---\n")
    write(tmp_path, "Notes/Cafe\u0301.md", "# Ordinary\n")
    write(tmp_path, "Notes/Member.md", "---\ncategories: ['[[CAFÉ]]']\n---\n")
    result = checked(tmp_path)
    assert [(issue.code, issue.candidates) for issue in result.issues] == [
        ("ambiguous_reference", ("Categories/Café.md", "Notes/Cafe\u0301.md")),
    ]


def test_malformed_remote_url_is_not_opened_or_a_local_image_requirement(tmp_path):
    write(tmp_path, "Notes/Manual.md", "![remote](https://[)\n")
    assert checked(tmp_path).outcome == "clean"


def test_native_embeds_preserve_markdown_punctuation_in_targets_and_aliases(tmp_path):
    write(
        tmp_path,
        "Notes/Manual.md",
        """![[Attachments/_icon_.png|**Icon**]]
![[Templates/Bases/_Members_.base#_View_]]
`![[Attachments/_code_.png]]`
<!-- ![[Templates/Bases/_comment_.base]] -->
""",
    )
    result = checked(tmp_path)
    assert [(issue.code, issue.reference) for issue in result.issues] == [
        ("missing_base", "[[Templates/Bases/_Members_.base#_View_]]"),
        ("missing_image", "[[Attachments/_icon_.png|**Icon**]]"),
    ]


def test_unreadable_category_does_not_fabricate_invalid_membership_or_provider(
    tmp_path, monkeypatch
):
    category_fixture(tmp_path)
    write(
        tmp_path,
        "Notes/Member.md",
        "---\ncategories: ['[[Categories/Books]]']\nappearance_category: '[[Books]]'\n---\n",
    )
    broken = tmp_path / "Categories/Books.md"
    before = inventory(tmp_path)
    original = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path == broken:
            raise PermissionError("synthetic unreadable category")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as boundary:
        boundary.setattr(Path, "read_text", unreadable)
        result = check_vault(tmp_path)
        assert check_vault(tmp_path) == result
    assert inventory(tmp_path) == before
    assert result.outcome == "failed"
    assert [(issue.artifact, issue.code) for issue in result.issues] == [
        ("Categories/Books.md", "read_failure")
    ]
    assert result.counts.category_notes is None
