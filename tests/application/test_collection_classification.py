from brz2obsidian.application.operations import Operations
from tests.application.test_collection_import_transaction import _vault
from tests.support.type_tag_sources import IDS, brz_source

CATEGORY_PROSE = (
    b"Exact source category instructions.\r\n\r\nIndependent second paragraph.\r\n"
)


def _classification_archive(tmp_path):
    from pathlib import Path
    from zipfile import ZipFile

    from tests.application.test_graph_workflow import identity
    from tests.application.test_verified_coverage import (
        add_attachment,
        change_record,
        write_source,
    )

    baseline = brz_source(tmp_path / "category-graph.brz")
    with ZipFile(baseline) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    pdf = (
        Path(__file__).parents[1] / "fixtures/local_api_scope_v3/blank.pdf"
    ).read_bytes()
    note = identity(701)
    add_attachment(parts, note, 1, "Notes.md", CATEGORY_PROSE, owner=IDS["A"])
    change_record(parts, note, NoteType=4)
    add_attachment(parts, identity(702), 1, "Category guide.pdf", pdf, owner=IDS["A"])
    return write_source(tmp_path, parts), pdf


def _assert_original_category_material(scope, note, expected_pdf):
    raw = note.read_bytes()
    assert CATEGORY_PROSE in raw
    assets = scope / "Attachments"
    pdf = next(assets.rglob("Category guide.pdf"))
    assert pdf.read_bytes() == expected_pdf
    assert next(assets.rglob("Notes.md.original")).read_bytes() == CATEGORY_PROSE
    destination = pdf.relative_to(scope.parent.parent).as_posix()
    assert f"[[{destination}|Category guide.pdf]]".encode() in raw


def test_source_import_offers_separate_choices_and_observed_reuse(tmp_path):
    vault = _vault(established=True)
    (vault / ".gitattributes").write_bytes(b"*.pdf -diff\n")
    shared = vault / "Categories/A.md"
    shared.parent.mkdir()
    opening = vault / "Opening.md"
    opening.rename(shared)
    authored = (
        shared.read_bytes().replace(b"\n---\n", b'\ntags:\n  - "categories"\n---\n', 1)
        + b"\r\nExisting dashboard prose.\r\n"
    )
    shared.write_bytes(authored)
    (vault / "Manual.md").write_bytes(b'---\ntags: ["focus/now"]\n---\n# Manual\n')
    source, pdf = _classification_archive(tmp_path)
    operations = Operations()
    before = operations.inspect_history(vault).checkpoint.locator
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
    assert shared_candidate.destination_identity == (
        "thebrain-brz",
        "brain-a",
        "opening",
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
    staged = tmp_path / "proposal/Imports/Atlas"
    _assert_original_category_material(
        staged, staged / "References/A — source reference.md", pdf
    )
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
    assert operations.inspect_history(vault).checkpoint.locator == before
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
    from brz2obsidian.application.update_lifecycle import text_choice_action
    from tests.application.test_collection_import_transaction import _user_git
    from tests.reconciliation.test_resolution import action
    from tests.support.type_tag_sources import PNG

    vault = _vault(established=True)
    (vault / ".gitattributes").write_bytes(b"*.pdf -diff\n")
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
    author = vault / "Projects/Attachments/Member.md"
    author.parent.mkdir(parents=True)
    author.write_bytes(
        f'---\ncategories:\n  - "[[{initial_category}]]"\ntags: ["focus/now"]\n---\n# Already a member\n'.encode()
    )
    staged_git = _user_git(vault)
    source, pdf = _classification_archive(tmp_path)
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
    _assert_original_category_material(vault / location, reference_file, pdf)
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
    preparation = updated.preparation
    assert preparation is not None, (updated.code, updated.findings)
    pending_paths = {
        path.relative_to(vault).as_posix()
        for path in (reference_file, overview, view_file.with_suffix(".md"))
    }
    assert not preparation.review.blockers
    while pending_paths:
        review = preparation.review
        assert set(review.blockers) <= {"selected_link_context_conflict"}
        assert len(review.requirements) == len(pending_paths)
        requirement = review.requirements[0]
        change = next(
            row
            for row in review.proposal.changes
            if row.change_id == requirement.change_id
        )
        assert change.path in pending_paths
        assert requirement.domain == "text"
        assert requirement.choices == ("current", "incoming", "edited")
        pending_paths.remove(change.path)
        choice = text_choice_action(
            review,
            action(
                review,
                change,
                domain="text",
                choice="incoming",
                decision_id="confirm-moved-category:" + change.change_id,
            ),
        )
        resolved = Operations().resolve_update(preparation, choice)
        assert resolved.code == "accepted", resolved.code
        preparation = resolved.preparation
        assert preparation is not None
    assert not preparation.review.blockers
    assert not preparation.review.requirements
    assert preparation.review.ready
    expected_author = author.read_bytes()
    applied = Operations().apply_update(preparation)
    assert applied.status == "applied", applied.code
    assert moved_path.read_bytes() == original
    assert moved_category.encode() in view_file.read_bytes()
    assert b"A revised (shared)" in overview.read_bytes()
    _assert_original_category_material(vault / location, reference_file, pdf)
    assert author.read_bytes() == expected_author
    assert (vault / "Categories.md").read_bytes() == root_overview
    assert _user_git(vault) == staged_git

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
    _assert_original_category_material(vault / location, reference_file, pdf)
    assert moved_path.read_bytes() == original
    assert (vault / alternative).read_bytes() == alternative_bytes
    assert (vault / "Categories.md").read_bytes() == root_overview
    assert _user_git(vault) == staged_git


def test_remembered_category_follows_a_unique_stable_id():
    import pytest

    from brz2obsidian.application.collection_classification import _update_placement
    from brz2obsidian.contracts import (
        ImportCategoryCandidate,
        ImportCategoryChoice,
        MigrationRefused,
    )
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

    alternate = ImportCategoryCandidate(
        destination_path="Categories/Alternative.md",
        destination_sha256="c" * 64,
        link_members_view="compatible_view_available",
    )
    replacement = ImportCategoryChoice(
        source_identity="category",
        destination_path=alternate.destination_path,
        destination_sha256=alternate.destination_sha256,
    )
    preview = classification_review(source, (alternate,), ())
    with pytest.raises(MigrationRefused) as error:
        _update_placement(source, original, preview, (), (), False)
    assert error.value.issues[0].code == "import_category_target_ambiguous"
    for explicit in (replacement, ImportCategoryChoice(source_identity="category")):
        remap = _update_placement(source, original, preview, (explicit,), (), True)
        assert remap["category_choices"] == (explicit,)


def test_held_undo_keeps_reversal_authority_instead_of_forward_mapping(monkeypatch):
    from types import SimpleNamespace

    from brz2obsidian.publication import vault_apply

    admission = SimpleNamespace(
        status="supported", inventory=(), policy_fingerprint="same policy"
    )
    checkpoint = SimpleNamespace(locator=SimpleNamespace(commit="retained checkpoint"))
    observed = SimpleNamespace(
        status="intact", admission=admission, checkpoint=checkpoint
    )
    monkeypatch.setattr(
        vault_apply,
        "_qualify_collection_apply",
        lambda *_: "import_classification_approval_missing",
    )
    args = (observed, observed, None, None, None)
    assert (
        vault_apply._held_apply_refusal(*args, undo_target=None)
        == "import_classification_approval_missing"
    )
    target = SimpleNamespace(observation=SimpleNamespace(checkpoint=checkpoint))
    assert vault_apply._held_apply_refusal(*args, undo_target=target) is None
    stale = SimpleNamespace(
        status="intact",
        admission=admission,
        checkpoint=SimpleNamespace(locator=SimpleNamespace(commit="new checkpoint")),
    )
    assert (
        vault_apply._held_apply_refusal(
            observed, stale, None, None, None, undo_target=target
        )
        == "current_admission_required"
    )


def test_paused_classified_update_finish_reobserves_selected_shared_target(
    tmp_path, monkeypatch
):
    import hashlib
    import json
    from types import SimpleNamespace

    import pytest

    from brz2obsidian.application.checkpoint_contracts import CheckpointFile
    from brz2obsidian.application.vault_update_contracts import (
        VaultOperationIntent,
        VaultPathMetadata,
    )
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.publication import collection_placement as placement

    record_path = "Imports/Atlas/migration-record.json"
    member_path = "Imports/Atlas/Notes/Member.md"
    category = "Categories/Shared.md"
    authored = b'---\ntags: ["categories"]\n---\n# Shared\n'
    target = tmp_path / category
    target.parent.mkdir()
    target.write_bytes(authored)
    choice = {
        "source_identity": "projects",
        "destination_path": category,
        "destination_sha256": hashlib.sha256(authored).hexdigest(),
    }
    incoming = {
        "schema": "brz2obsidian.migration",
        "source_identity": {"snapshot_digest": "same-snapshot"},
        "item_targets": [{"original_identity": "projects"}],
        "category_mappings": [{"source_identity": "projects", "destination": choice}],
        "vault_tag_mappings": [],
    }
    before = incoming | {
        "category_mappings": [
            {
                "source_identity": "projects",
                "destination": {"source_identity": "projects"},
            }
        ]
    }
    old_record = ExactContent(data=json.dumps(before).encode())
    new_record = ExactContent(data=json.dumps(incoming).encode())
    old_member = ExactContent(data=b"# Member\n")
    new_member = ExactContent(
        data=b'---\ncategories: ["[[Categories/Shared.md]]"]\n---\n# Member\n'
    )
    selected = {record_path: new_record, member_path: new_member}
    kind = SimpleNamespace(kind="source_update")
    approval = placement.classification_approval(incoming)
    review = SimpleNamespace(
        facts=SimpleNamespace(format_operation=kind),
        producer_facts=SimpleNamespace(
            link_context=SimpleNamespace(
                import_classification_approval=approval,
                import_classification_remap=True,
                current_documents=(),
            ),
            subjects=(
                SimpleNamespace(
                    path=record_path,
                    baseline=SimpleNamespace(content=old_record),
                    structure=None,
                ),
                SimpleNamespace(
                    path=member_path,
                    current=SimpleNamespace(path=member_path),
                    structure=SimpleNamespace(
                        prior_mappings=(),
                        incoming_mappings=(
                            SimpleNamespace(
                                kind="category", classification_id="category:projects"
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    def row(path, content):
        return CheckpointFile(
            path=path,
            size=content.identity.size,
            sha256=content.identity.sha256,
            object_id="a" * 40,
            mode="100644",
        )

    paths = tuple(sorted(selected))
    before_rows = (row(member_path, old_member), row(record_path, old_record))
    after_rows = tuple(row(path, selected[path]) for path in paths)
    metadata = tuple(
        VaultPathMetadata(path=path, mode=0, attributes=0, security="retained")
        for path in paths
    )
    origin = VaultOperationIntent(
        schema_id="brz2obsidian.vault-operation-intent",
        schema_version=1,
        operation_id="b" * 32,
        kind="apply",
        direction="finish",
        generation=1,
        association_id="a" * 64,
        prepared_commit="b" * 40,
        before=before_rows,
        proposed=after_rows,
        affected_paths=paths,
        protected_paths=(),
        before_metadata=metadata,
        result_metadata=metadata,
        created_directories=(),
    )
    observed = SimpleNamespace(
        vault=str(tmp_path), inventory=(after_rows[1], before_rows[0])
    )
    monkeypatch.setattr(
        placement, "existing_files", lambda _: {category: target.read_bytes()}
    )
    monkeypatch.setattr(
        placement,
        "observe_classification_inventory",
        lambda _, _checkpoint, *, existing=None: placement.vault_classifications(
            existing or {}
        ),
    )

    placement.require_collection_finish_links(
        observed, None, record_path, review, selected, origin=origin
    )
    target.write_bytes(authored + b"Later authored edit.\n")
    with pytest.raises(
        placement.ImportRecoveryLinkChange,
        match="recovery_import_classifications_changed",
    ):
        placement.require_collection_finish_links(
            observed, None, record_path, review, selected, origin=origin
        )
    inverse = origin.model_copy(update={"kind": "undo"})
    placement.require_collection_finish_links(
        observed, None, record_path, review, selected, origin=inverse
    )
    terminal = SimpleNamespace(vault=str(tmp_path), inventory=after_rows)
    placement.require_collection_finish_links(
        terminal, None, record_path, review, selected, origin=origin
    )


def test_paused_new_member_uses_its_retained_assignments_when_structure_is_absent():
    import hashlib
    import json
    from types import SimpleNamespace

    import pytest

    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.publication import collection_placement as placement

    record_path = "Imports/Atlas/migration-record.json"
    member_path = "Imports/Atlas/Notes/New member.md"
    category_path = "Categories/Shared.md"
    authored_category = b'---\ntags: ["categories"]\n---\n# Shared\n'
    tag_document = "Imports/Atlas/Notes/Existing tag.md"
    authored_tag = b'---\ntags: ["shared/tag"]\n---\n# Authored tag\n'
    live = {category_path: authored_category, tag_document: authored_tag}
    before = {
        "schema": "brz2obsidian.migration",
        "source_identity": {"snapshot_digest": "old"},
        "item_targets": [
            {"item_key": "type-key", "original_identity": "projects"},
            {"item_key": "tag-key", "original_identity": "source-tag"},
        ],
        "category_mappings": [
            {
                "source_identity": "projects",
                "destination": {
                    "source_identity": "projects",
                    "destination_path": category_path,
                    "destination_sha256": hashlib.sha256(authored_category).hexdigest(),
                },
            }
        ],
        "vault_tag_mappings": [],
    }
    incoming = before | {
        "source_identity": {"snapshot_digest": "next"},
        "item_targets": [
            *before["item_targets"],
            {
                "item_key": "new-key",
                "original_identity": "new-item",
                "relative_path": member_path,
                "created": True,
            },
        ],
        "classification_assignments": [
            {
                "definition_key": "type-key",
                "item_key": "new-key",
                "item_target": member_path,
                "definition_target": category_path,
            }
        ],
        "tag_memberships": [
            {
                "tag_key": "tag-key",
                "tag_original_identity": "source-tag",
                "item_key": "new-key",
                "item_target": member_path,
                "native": True,
                "token": "shared/tag",
            }
        ],
        "vault_tag_mappings": [
            {
                "source_identity": "source-tag",
                "vault_tag": "shared/tag",
                "mode": "reuse",
            }
        ],
    }
    old = ExactContent(data=json.dumps(before).encode())
    new = ExactContent(data=json.dumps(incoming).encode())
    member = ExactContent(
        data=b'---\ncategories: ["[[Categories/Shared.md]]"]\ntags: ["shared/tag"]\n---\n# New member\n'
    )

    def row(path, content):
        return SimpleNamespace(
            path=path, size=content.identity.size, sha256=content.identity.sha256
        )

    selected = {record_path: new, member_path: member}
    origin = SimpleNamespace(
        kind="apply",
        affected_paths=tuple(selected),
        before=(row(record_path, old),),
        proposed=(row(record_path, new), row(member_path, member)),
    )
    member_subject = SimpleNamespace(
        path=member_path,
        item_id="new-item",
        facet="content",
        output_role="note",
        baseline=SimpleNamespace(content=None),
        current=SimpleNamespace(path=member_path, existence="absent"),
        structure=None,
        incoming=member,
    )
    review = SimpleNamespace(
        facts=SimpleNamespace(format_operation=SimpleNamespace(kind="source_update")),
        producer_facts=SimpleNamespace(
            link_context=SimpleNamespace(
                import_classification_approval=placement.classification_approval(
                    incoming
                ),
                import_classification_remap=False,
                current_documents=(),
            ),
            subjects=(
                SimpleNamespace(
                    path=record_path,
                    baseline=SimpleNamespace(content=old),
                    structure=None,
                ),
                member_subject,
            ),
        ),
    )

    def finish(record_bytes, effects=selected, *, witness=None):
        inventory = (row(record_path, record_bytes),)
        if witness is not None:
            inventory += (row(tag_document, witness),)
        observed = SimpleNamespace(inventory=inventory)
        placement.require_collection_finish_links(
            observed,
            None,
            record_path,
            review,
            effects,
            origin=origin,
            produced=selected,
        )

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(placement, "existing_files", lambda _: dict(live))
        patch.setattr(
            placement,
            "observe_classification_inventory",
            lambda _, _checkpoint, *, existing=None: placement.vault_classifications(
                existing or {}
            ),
        )
        for record_bytes in (old, new):
            finish(record_bytes)
            live[category_path] = authored_category + b"Later offline edit.\n"
            with pytest.raises(
                placement.ImportRecoveryLinkChange,
                match="recovery_import_classifications_changed",
            ):
                finish(record_bytes)
            live[category_path] = authored_category
            live.pop(tag_document)
            with pytest.raises(
                placement.ImportRecoveryLinkChange,
                match="recovery_import_classifications_changed",
            ):
                finish(record_bytes)
            live[tag_document] = authored_tag
        live[category_path] = authored_category + b"Later offline edit.\n"
        finish(
            new,
            selected | {member_path: ExactContent(data=b"# Authored alternative\n")},
        )

        live[category_path] = authored_category
        before_witness = ExactContent(data=authored_tag)
        published = ExactContent(
            data=authored_tag.replace(b"# Authored tag", b"# Reviewed new body")
        )
        live[tag_document] = published.data
        selected[tag_document] = published
        origin.affected_paths += (tag_document,)
        origin.before += (row(tag_document, before_witness),)
        origin.proposed += (row(tag_document, published),)
        context = review.producer_facts.link_context
        context.current_documents = (
            SimpleNamespace(source_path=tag_document, content=before_witness),
        )
        finish(new, witness=published)

        independent_before = ExactContent(data=b"# Original note without the tag\n")
        original_rows = origin.before
        origin.before = (*original_rows[:-1], row(tag_document, independent_before))
        with pytest.raises(
            placement.ImportRecoveryLinkChange,
            match="recovery_import_classifications_changed",
        ):
            finish(new, witness=published)

        context.current_documents = (
            SimpleNamespace(source_path=tag_document, content=independent_before),
        )
        with pytest.raises(
            placement.ImportRecoveryLinkChange,
            match="recovery_import_classifications_changed",
        ):
            finish(new, witness=published)

        edited = ExactContent(
            data=published.data + b"Later author edited the published note.\n"
        )
        live[tag_document] = edited.data
        with pytest.raises(
            placement.ImportRecoveryLinkChange,
            match="recovery_import_classifications_changed",
        ):
            finish(new, witness=edited)

        origin.before = original_rows
        context.current_documents = (
            SimpleNamespace(source_path=tag_document, content=before_witness),
        )
        finish(new, witness=edited)
        missing_tag = ExactContent(data=b"# Later author removed the shared tag.\n")
        live[tag_document] = missing_tag.data
        with pytest.raises(
            placement.ImportRecoveryLinkChange,
            match="recovery_import_classifications_changed",
        ):
            finish(new, witness=missing_tag)


def test_classified_restore_before_rebinds_peer_memberships_to_current_lookup(
    monkeypatch,
):
    from types import SimpleNamespace

    from brz2obsidian.application.update_facts import link_state
    from brz2obsidian.application.update_facts import target as path_target
    from brz2obsidian.contracts import ExactContent
    from brz2obsidian.core.link_validation import validate_link_document
    from brz2obsidian.core.review_appearance import provider_chain_blockers
    from brz2obsidian.obsidian import interpret_links
    from brz2obsidian.publication import vault_recovery
    from tests.reconciliation.test_memberships import target

    def category(identifier, path, *extra):
        return target(identifier, "category", f"[[{path}]]", *extra).model_copy(
            update={"canonical_path": path, "target": path_target(path)}
        )

    peer = category("E", "Imports/Atlas/Categories/E.md")
    former = category("old", "Moved/Shared.md", "[[Shared]]")
    manual = category("manual", "Categories/Manual.md")
    competing = category("competing", "Elsewhere/Shared.md", "[[Shared]]")
    category_tag = target("category-tag", "tag", "categories")
    source_path = "Imports/Atlas/Categories/B.md"
    source = ExactContent(
        data=f"Restored reference to [[{peer.canonical_path}]].\n".encode()
    )
    operation = SimpleNamespace(
        facts=SimpleNamespace(
            baseline_identity=SimpleNamespace(output_format=9),
            incoming_identity=SimpleNamespace(output_format=9),
            link_context=SimpleNamespace(import_classification_approval="a" * 64),
        )
    )
    owned = object()
    journal = object()
    prior = (
        '---\ncategories:\n  - "{provider}"\n  - "[[Categories/Manual.md]]"\n'
        'appearance_category: "{provider}"\ntags:\n  - "categories"\n---\nExact authored tail.\r\n'
    )

    def restore(provider, *lookups):
        raw = ExactContent(data=prior.format(provider=provider).encode())

        def retained_content(git, row, *, _owner):
            assert git is owned and row is journal and _owner is None
            return raw

        monkeypatch.setattr(vault_recovery, "_owned_content", retained_content)
        registry = (peer, manual, *lookups, category_tag)
        stable = {
            row.target_id: link_state(
                ExactContent(
                    data=(
                        '---\ntags:\n  - "categories"\n'
                        f'source_collection_id: "{row.identity.collection_id}"\n'
                        f'source_item_id: "{row.identity.item_id}"\n'
                        "---\n# Existing category\n"
                    ).encode()
                ),
                target_id=row.target_id,
                existence="present",
                source_path=row.canonical_path,
                output_format=9,
                membership_targets=registry,
            )
            for row in (manual, *lookups)
        }
        states = tuple(
            vault_recovery._restore_target_states(
                operation,
                SimpleNamespace(current_targets=registry),
                stable,
                {peer.canonical_path: journal},
                {peer.canonical_path},
                owned,
                _owner=None,
            )
        )
        document = interpret_links(
            source,
            document_id="restored:B",
            source_path=source_path,
            path_mode="vault",
            targets=registry,
            target_facts=states,
            inventory="complete",
            output_format=9,
        )
        checked = validate_link_document(
            document,
            expected_content=source,
            expected_path=source_path,
            targets=registry,
            target_facts=states,
            inventory="complete",
        )
        blockers = provider_chain_blockers((), states, selected_targets=registry)
        return raw, states[0], checked, blockers

    raw, retained, checked, blockers = restore("[[Moved/Shared.md]]", former)
    assert retained.content == raw
    assert retained.memberships == ("old", "manual", "category-tag")
    assert retained.file_roles.category
    assert checked.valid and not blockers
    for provider, lookups in (
        ("[[Moved/Shared.md]]", ()),
        ("[[Shared]]", (former, competing)),
    ):
        _, unsupported, _, blockers = restore(provider, *lookups)
        assert unsupported.structure.issues == ("membership_target_unknown",)
        assert unsupported.memberships == ()
        assert blockers == ("selected_provider_invalid",)
