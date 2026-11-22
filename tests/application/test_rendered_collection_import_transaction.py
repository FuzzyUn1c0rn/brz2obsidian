"""Native source-to-vault evidence for scoped placement and authored link review."""

import json
from zipfile import ZipFile

from brz2obsidian.application.operations import Operations
from brz2obsidian.core import select_review_effects
from tests.application.test_collection_import_transaction import _user_git, _vault
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_sized_images_workflow import images
from tests.application.test_verified_coverage import add_attachment

LOCATION = "Library/Independent Brain"
DRAFT_LINKS = (
    b"[[Twin#Old heading|Existing target]]\r\n"
    b"[[../Old/Twin#^old-block|Existing wiki relative]]\r\n"
    b"[Existing Markdown relative](../Old/Twin.md#%5Eold-block)\r\n"
    b"[Current qualified asset](Old/Existing.png)\r\n"
    b"[[Prospective|Leave this unresolved]]\r\n"
    b"[[Library/Independent Brain/Notes/Future#Landing|Reviewed connection]]\r\n"
    b"[[Old/Unrelated|Existing unrelated warning]]\r\n"
)


def _incoming_archive(path):
    graph_archive(
        path,
        {1: "Independent entry", 2: "Twin", 3: "Prospective", 4: "Future", 5: "Clear"},
        tuple((1, n, 1, 1, -1) for n in range(2, 6)),
        notes={4: (b"## Landing\n\n![Picture](.data/md-images/picture.png)\n", 4)},
    )
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    art = images()[0]
    add_attachment(files, identity(6001), 12, "picture.png", art, owner=identity(4))
    meta = json.loads(files["meta.json"])
    meta["Name"] = "Independent Brain"
    files["meta.json"] = json.dumps(meta).encode()
    with ZipFile(path, "w") as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(name, raw)
    return path, art


def _write(vault, path, data):
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _observation(result, display):
    return next(
        row
        for row in result.import_link_impact.observations
        if row.before.display_text == display
    )


def test_rendered_collection_fixture_offers_a_publishable_review(tmp_path):
    archive, _ = _incoming_archive(tmp_path / "independent.brz")
    operations = Operations()
    inspected = operations.inspect(archive)
    assert inspected.outcome in ("clean", "warnings"), inspected.findings
    vault = _vault(established=False)
    _write(vault, "Journal/Author.md", DRAFT_LINKS)
    _write(vault, "Old/Twin.md", b"# Old heading\n\nExisting body ^old-block\n")
    _write(vault, "Old/Existing.png", images()[1])
    preview = operations.prepare_collection_import_from_source(
        vault,
        archive,
        staging=tmp_path / "preview",
        import_location=LOCATION,
        preview_connections=True,
    )
    choice = _observation(preview, "Reviewed connection").connection
    offered = operations.prepare_collection_import_from_source(
        vault,
        archive,
        staging=tmp_path / "review",
        import_location=LOCATION,
        connections=(choice,),
    )
    assert _observation(offered, "Reviewed connection").kind == "approved_connection"
    assert offered.ready, offered.findings
    selected = select_review_effects(offered.preparation.review)
    stage = tmp_path / "review"
    assert {row.path: row.content.data for row in selected.files} == {
        file.relative_to(stage).as_posix(): file.read_bytes()
        for file in stage.rglob("*")
        if file.is_file()
    }
    assert not selected.remove_paths
    assert not (vault / LOCATION).exists()


def test_rendered_collection_import_keeps_authored_links_and_revalidates_connection(
    tmp_path,
):
    vault = _vault(established=True)
    authored = {
        "Journal/Author.md": DRAFT_LINKS,
        "Old/Twin.md": b"# Old heading\n\nExisting body ^old-block\n",
        "Old/Existing.png": images()[1],
        "Categories.md": b"# Authored vault overview\r\n",
        ".obsidian/app.json": (vault / ".obsidian/app.json").read_bytes(),
        "Opening.md": (vault / "Opening.md").read_bytes(),
        "migration-record.json": (vault / "migration-record.json").read_bytes(),
        "Manual.md": (vault / "Manual.md").read_bytes(),
    }
    for path, raw in authored.items():
        _write(vault, path, raw)
    source, asset = _incoming_archive(tmp_path / "independent.brz")
    before_git = _user_git(vault)
    before = Operations()
    default = before.prepare_collection_import_from_source(
        vault,
        source,
        staging=tmp_path / "default",
    )
    assert (
        default.preparation is not None and not default.preparation.review.blockers
    ), default
    assert default.preparation.collection_record_path == (
        "Imports/Independent Brain/migration-record.json"
    )
    default_record = json.loads(
        (tmp_path / "default" / default.preparation.collection_record_path).read_bytes()
    )
    assert (
        next(
            row
            for row in default_record["item_targets"]
            if row["original_title"] == "Future"
        )["relative_path"]
        == "Imports/Independent Brain/Notes/Future.md"
    )

    preview = before.prepare_collection_import_from_source(
        vault,
        source,
        staging=tmp_path / "preview",
        import_location=LOCATION,
        preview_connections=True,
    )
    assert preview.code == "import_connection_preview", preview
    selected = _observation(preview, "Reviewed connection")
    assert selected.kind == "connection_required"
    assert selected.after.path == LOCATION + "/Notes/Future.md"
    assert selected.after.fragment.value == "Landing"
    assert _observation(preview, "Leave this unresolved").kind == "connection_required"

    staged = tmp_path / "review"
    offer = before.prepare_collection_import_from_source(
        vault,
        source,
        staging=staged,
        import_location=LOCATION,
        connections=(selected.connection,),
    )
    assert offer.preparation is not None and not offer.preparation.review.blockers, (
        offer
    )
    selected = _observation(offer, "Reviewed connection")
    assert selected.kind == "approved_connection"
    assert _observation(offer, "Leave this unresolved").after.status == "missing"
    for display, path in (
        ("Existing target", "Old/Twin.md"),
        ("Existing wiki relative", "Old/Twin.md"),
        ("Existing Markdown relative", "Old/Twin.md"),
        ("Current qualified asset", "Old/Existing.png"),
    ):
        observed = _observation(offer, display)
        assert observed.before.path == path
        assert observed.after == observed.before
    assert (
        _observation(offer, "Existing unrelated warning").kind == "preexisting_warning"
    )

    unapproved = before.prepare_collection_import(
        vault,
        staged,
        record_path=offer.preparation.collection_record_path,
    )
    assert unapproved.import_link_impact.blockers == (
        "import_connection_approval_missing",
    )
    assert offer.ready, offer.findings
    saved = before.save_update(offer.preparation)
    assert saved.code == "saved", saved
    resumed = Operations().resume_update(vault)
    assert resumed.code == "resumed", resumed
    rogue_base = vault / "New view.base"
    rogue_target = LOCATION + "/Notes/Clear.md"
    base_bytes = f"formulas:\n  open: 'link(\"{rogue_target}\")'\n".encode()
    rogue_base.write_bytes(base_bytes)
    prepared = resumed.preparation
    association = prepared.locator.association
    refused = Operations().apply_reviewed_update(
        vault,
        prepared.payload_directory,
        review=prepared.review,
        vault_id=association.vault_id,
        import_id=association.import_id,
        source_binding=prepared.source_binding,
        observed_source=prepared.observed_source,
    )
    assert refused.status == "refused" and not (vault / LOCATION).exists(), refused
    assert rogue_base.read_bytes() == base_bytes
    rogue_base.unlink()
    path = "Journal/Author.md"
    edited = authored[path] + b"New user writing.\r\n"
    _write(vault, path, edited)
    for result in (
        Operations().resume_update(vault),
        Operations().refresh_update(resumed.preparation),
        Operations().apply_update(resumed.preparation),
    ):
        assert result.code == "import_link_meanings_changed", result
        assert "import_connection_stale" in result.import_link_impact.blockers
        assert (vault / path).read_bytes() == edited
        assert not (vault / LOCATION).exists()
    _write(vault, path, authored[path])

    operations = Operations()
    resumed = operations.resume_update(vault)
    result = operations.apply_update(resumed.preparation)
    assert result.status == "applied", result
    assert {path: (vault / path).read_bytes() for path in authored} == authored
    assert _user_git(vault) == before_git
    record_path = LOCATION + "/migration-record.json"
    record = json.loads((vault / record_path).read_bytes())
    notes = {
        row["original_title"]: row["relative_path"] for row in record["item_targets"]
    }
    assert notes["Future"] == LOCATION + "/Notes/Future.md"
    assert notes["Clear"] == LOCATION + "/Notes/Clear.md"
    assert notes["Twin"].startswith(LOCATION + "/Notes/Twin — ")
    assert notes["Prospective"].startswith(LOCATION + "/Notes/Prospective — ")
    assert record["import_support_paths"]["Categories.md"].startswith(
        LOCATION + "/Categories — "
    )
    picture = next(
        row["relative_path"]
        for row in record["asset_targets"]
        if row["relative_path"].endswith("/picture.png")
    )
    assert (vault / picture).read_bytes() == asset
    assert picture in (vault / notes["Future"]).read_text(encoding="utf-8")
    assert notes["Future"] in (vault / notes["Independent entry"]).read_text(
        encoding="utf-8"
    )


def test_established_default_import_binds_unrelated_authored_asset(tmp_path):
    source, _ = _incoming_archive(tmp_path / "independent.brz")
    vault = _vault(established=True)
    _write(vault, "Journal/Author.md", DRAFT_LINKS)
    _write(vault, "Old/Twin.md", b"# Old heading\n\nExisting body ^old-block\n")
    _write(vault, "Old/Existing.png", images()[1])
    result = Operations().prepare_collection_import_from_source(
        vault, source, staging=tmp_path / "default"
    )
    assert result.ready, result.findings
    observed = _observation(result, "Current qualified asset")
    assert observed.before == observed.after
    assert observed.after.path == "Old/Existing.png"
