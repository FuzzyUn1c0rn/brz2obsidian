from brz2obsidian.application.operations import Operations
from tests.application.test_collection_import_transaction import _vault
from tests.support.type_tag_sources import IDS, brz_source


def test_source_import_offers_separate_choices_and_observed_reuse(tmp_path):
    vault = _vault(established=False)
    shared = vault / "Categories/A.md"
    shared.parent.mkdir()
    authored = b'---\r\ntags: ["categories"]\r\n---\r\n# A\r\n\r\nExisting dashboard prose.\r\n'
    shared.write_bytes(authored)
    (vault / "Manual.md").write_bytes(b'---\ntags: ["focus/now"]\n---\n# Manual\n')
    source = tmp_path / "categories.brz"
    brz_source(source)
    operations = Operations()
    offered = operations.prepare_collection_import_from_source(
        vault,
        source,
        staging=tmp_path / "preview",
        import_location="Imports/Atlas",
        preview_classifications=True,
    )
    assert offered.code == "import_classification_review_required"
    review = offered.classification_review
    assert "focus/now" in review.vault_tags
    shared_candidate = next(
        row
        for row in review.vault_categories
        if row.destination_path == "Categories/A.md"
    )
    assert (IDS["A"], "Categories/A.md") in review.category_suggestions
    choices = tuple(
        {"source_identity": source_id}
        | (
            shared_candidate.model_dump(
                include={
                    "destination_path",
                    "destination_identity",
                    "destination_sha256",
                }
            )
            if source_id == IDS["A"]
            else {}
        )
        for source_id, _ in review.source_categories
    )
    preview = operations.prepare_collection_import_from_source(
        vault,
        source,
        staging=tmp_path / "proposal",
        import_location="Imports/Atlas",
        category_choices=choices,
        tag_reuse=((review.source_tags[0][0], "focus/now"),),
    )
    assert preview.ready, (preview.code, preview.findings, preview.preparation)
    assert shared.read_bytes() == authored
    assert (
        tmp_path / "proposal/Imports/Atlas/References/A — source reference.md"
    ).is_file()
    assert not (tmp_path / "proposal/Imports/Atlas/Views").exists()
    assert not (vault / "Imports").exists()

    unreviewed = operations.prepare_collection_import(
        vault,
        tmp_path / "proposal",
        record_path="Imports/Atlas/migration-record.json",
    )
    assert unreviewed.code == "import_classification_approval_missing"
    shared.write_bytes(authored + b"More authored prose.\r\n")
    stale = operations.save_update(preview.preparation)
    assert stale.code == "import_category_target_changed"
    assert operations.inspect_history(vault).status == "absent"
    assert shared.read_bytes() == authored + b"More authored prose.\r\n"

    shared.write_bytes(authored)
    saved = operations.save_update(preview.preparation)
    assert saved.code == "saved", saved.code
    resumed = Operations().resume_update(vault)
    assert resumed.code == "resumed" and resumed.ready, resumed.code
    assert shared.read_bytes() == authored
    assert not (vault / "Imports").exists()


def _proposed_category_choices(review, source, path, *, view):
    shared = next(
        row for row in review.vault_categories if row.destination_path == path
    )
    return tuple(
        {"source_identity": source_id}
        | (
            shared.model_dump(exclude={"link_members_view"}) | {"compatible_view": view}
            if source_id == source
            else {}
        )
        for source_id, _ in review.source_categories
    )


def _rename_source_category(source, target, title):
    import json
    from zipfile import ZipFile

    with ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    rows = [json.loads(line) for line in files["thoughts.json"].splitlines()]
    definition = next(row for row in rows if row["Id"] == IDS["A"])
    definition["Name"] = title
    files["thoughts.json"] = b"\n".join(json.dumps(row).encode() for row in rows)
    with ZipFile(target, "w") as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(name, raw)


def test_native_category_import_update_and_reviewed_remap(tmp_path):
    from tests.application.test_collection_import_transaction import _user_git
    from tests.support.type_tag_sources import PNG

    vault = _vault(established=True)
    categories = vault / "Categories"
    categories.mkdir()
    initial_category = "Categories/Existing.md"
    note = (vault / "Opening.md").read_bytes()
    (vault / "Opening.md").unlink()
    original = note.replace(b"\n---\n", b'\ntags:\n  - "categories"\n---\n', 1)
    (vault / initial_category).write_bytes(original)
    alternative = "Categories/Alternative.md"
    alternative_bytes = b'---\ntags: ["categories"]\n---\n# Alternative\n'
    (vault / alternative).write_bytes(alternative_bytes)
    root_overview = b"# Independent existing overview\r\n"
    (vault / "Categories.md").write_bytes(root_overview)
    author = vault / "Existing.md"
    author.write_bytes(
        f'---\ncategories:\n  - "[[{initial_category}]]"\ntags: ["focus/now"]\n---\n# Already a member\n'.encode()
    )
    staged_git = _user_git(vault)
    source = tmp_path / "baseline.brz"
    brz_source(source)
    operations = Operations()
    location = "Imports/Atlas"
    record_path = location + "/migration-record.json"
    offered = operations.prepare_collection_import_from_source(
        vault,
        source,
        staging=tmp_path / "preview",
        import_location=location,
        preview_classifications=True,
    )
    chosen = _proposed_category_choices(
        offered.classification_review, IDS["A"], initial_category, view=True
    )
    ready = operations.prepare_collection_import_from_source(
        vault,
        source,
        staging=tmp_path / "initial",
        import_location=location,
        category_choices=chosen,
    )
    assert ready.ready, (ready.code, ready.findings)
    applied = operations.apply_update(ready.preparation)
    assert applied.status == "applied", applied.code
    assert (vault / initial_category).read_bytes() == original
    reference_file = next((vault / location / "References").glob("A*.md"))
    view_file = next((vault / location / "Views").glob("A*.base"))
    overview = next((vault / location).glob("Categories*.md"))
    imported_b = next((vault / location / "Categories").glob("B*.md"))
    assert initial_category.encode() in reference_file.read_bytes()
    assert initial_category.encode() in view_file.read_bytes()
    assert (vault / "Categories.md").read_bytes() == root_overview
    assert PNG in {
        path.read_bytes() for path in (vault / location / "Attachments").rglob("*.png")
    }

    moved_category = "Moved/Existing category.md"
    moved_path = vault / moved_category
    moved_path.parent.mkdir()
    (vault / initial_category).rename(moved_path)
    for file in (author, *tuple((vault / location).rglob("*.md"))):
        prior = file.read_bytes()
        updated = prior.replace(initial_category.encode(), moved_category.encode())
        if updated != prior:
            file.write_bytes(updated)
    renamed = tmp_path / "renamed.brz"
    _rename_source_category(source, renamed, "A revised")
    updated = Operations().prepare_collection_update_from_source(
        vault, renamed, staging=tmp_path / "update", record_path=record_path
    )
    assert updated.ready, (updated.code, updated.findings)
    applied = Operations().apply_update(updated.preparation)
    assert applied.status == "applied", applied.code
    assert moved_path.read_bytes() == original
    assert moved_category.encode() in view_file.read_bytes()
    assert b"A revised (shared)" in overview.read_bytes()
    assert reference_file.exists()

    manual = b"\r\nPersonal prose after Update.\r\n"
    imported_b.write_bytes(imported_b.read_bytes() + manual)
    candidate = next(
        row
        for row in updated.classification_review.vault_categories
        if row.destination_path == alternative
    )
    remap_choice = (
        {"source_identity": IDS["A"], "compatible_view": True}
        | candidate.model_dump(exclude={"link_members_view"}),
    )
    remap = Operations().prepare_collection_remap_from_source(
        vault,
        renamed,
        staging=tmp_path / "remap",
        record_path=record_path,
        category_choices=remap_choice,
    )
    assert remap.code == "classification_remap_prepared"
    assert remap.ready, remap.findings
    assert (
        Operations()
        .prepare_collection_update(vault, tmp_path / "remap", record_path=record_path)
        .code
        == "classification_remap_required"
    )
    before_conflict = imported_b.read_bytes()
    removed_membership = b'categories:\n  - "[[' + moved_category.encode() + b']]"\n'
    assert removed_membership in before_conflict
    edited = before_conflict.replace(removed_membership, b"categories: []\n", 1)
    imported_b.write_bytes(edited)
    stale = Operations().apply_update(remap.preparation)
    assert stale.status in ("refused", "unresolved", "stale_review"), stale.code
    assert imported_b.read_bytes() == edited
    assert moved_path.read_bytes() == original
    assert _user_git(vault) == staged_git
    imported_b.write_bytes(before_conflict)

    remapped = Operations().apply_update(remap.preparation)
    assert remapped.status == "applied", remapped.code
    assert imported_b.read_bytes().endswith(manual)
    assert alternative.encode() in imported_b.read_bytes()
    assert alternative.encode() in view_file.read_bytes()
    assert alternative.encode() in overview.read_bytes()
    assert alternative.encode() in reference_file.read_bytes()
    assert moved_path.read_bytes() == original
    assert (vault / alternative).read_bytes() == alternative_bytes
    assert (vault / "Categories.md").read_bytes() == root_overview
    assert _user_git(vault) == staged_git


def test_remembered_category_follows_a_unique_stable_id():
    import pytest

    from brz2obsidian.application.collection_classification import _update_placement
    from brz2obsidian.contracts import ImportCategoryCandidate, MigrationRefused
    from brz2obsidian.obsidian.import_classification import classification_review
    from tests.application.test_graph_modules import item, snapshot

    source = snapshot((item("category", "Renamed category", role="definition"),))
    claim = ("thebrain-brz", "earlier", "shared")
    original = {
        "source_identity": source.identity.model_dump(),
        "collection_location": "Imports/Atlas",
        "item_targets": [
            {
                "original_identity": "category",
                "relative_path": "Imports/Atlas/References/Old.md",
            }
        ],
        "category_mappings": [
            {
                "source_identity": "category",
                "destination": {
                    "source_identity": "category",
                    "destination_path": "Categories/Old.md",
                    "destination_sha256": "a" * 64,
                    "destination_identity": claim,
                    "compatible_view": True,
                },
            }
        ],
    }
    moved = ImportCategoryCandidate(
        destination_path="Archive/New path.md",
        destination_sha256="b" * 64,
        destination_identity=claim,
        link_members_view="compatible_view_available",
    )
    preview = classification_review(source, (moved,), ())
    arguments = _update_placement(source, original, preview, (), (), False)
    (choice,) = arguments["category_choices"]
    assert choice.destination_identity == claim
    assert choice.destination_path == "Archive/New path.md"
    assert choice.destination_sha256 == "b" * 64
    assert choice.compatible_view
    assert arguments["remembered_item_paths"] == (
        ("category", "Imports/Atlas/References/Old.md"),
    )

    duplicate = moved.model_copy(update={"destination_path": "Duplicate.md"})
    ambiguous = classification_review(source, (moved, duplicate), ())
    with pytest.raises(MigrationRefused) as error:
        _update_placement(source, original, ambiguous, (), (), False)
    assert error.value.issues[0].code == "import_category_target_ambiguous"
