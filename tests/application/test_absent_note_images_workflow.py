import hashlib
import json
import struct
import zlib
from base64 import b64decode
from contextlib import contextmanager

import pytest

from brz2obsidian.application import SourceModuleBinding, Workflow
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from brz2obsidian.contracts import MigrationRefused, RunMetadata
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from brz2obsidian.vault_check import check_vault
from tests.application.test_verified_coverage import (
    OWNER,
    PDF,
    TXT,
    add_attachment,
    change_record,
    source_parts,
    write_source,
)

IMAGE = "77777777-7777-4777-8777-777777777777"
NOTE = "33333333-3333-4333-8333-333333333333"


def png_bytes():
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


def fallback_parts(tmp_path):
    parts = source_parts(tmp_path)
    records = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    assert len(records) == 1
    note = records[0]
    assert note["Id"] == NOTE
    parts.pop(OWNER + "/" + note["Location"])
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"][NOTE] = 3
    parts["meta.json"] = json.dumps(meta).encode()
    add_attachment(parts, IMAGE, 12, "card.png", png_bytes())
    return parts


def test_absent_note_displays_owned_image_with_truthful_obligations(tmp_path):
    source = write_source(tmp_path, fallback_parts(tmp_path))
    before = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    assert inspected.inspection.documents == ()
    assert (
        inspected.receipt is None and inspected.counts.actual_generated_embeds is None
    )
    assert inspected.counts.source_references == 0
    assert inspected.counts.source_gaps == 1
    assert inspected.counts.planned_generated_embeds == 1
    assert inspected.inspection.source_gaps[0].image_asset_ids == (IMAGE,)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.issues
    assert result.counts.actual_generated_embeds == 1
    assert result.counts.actual_references == 0 and result.counts.actual_assets == 1
    note = (tmp_path / "vault/Home — Entry thought.md").read_text()
    assert "> [!warning] Source note unavailable\n> Source note text is absent" in note
    assert "Source note text is absent" in note
    assert "prose, captions and layout were not recovered" in note
    assert "[[MIGRATION REPORT.md|Migration report]]" in note
    assert note.index("Source note text") < note.index(
        "![[Attachments/22222222/card.png]]"
    )
    assert note.count("![[Attachments/22222222/card.png]]") == 1
    assert "Available note images" not in note and "## Resources" not in note
    image = tmp_path / "vault/Attachments/22222222/card.png"
    assert image.read_bytes() == png_bytes()
    assert not list((tmp_path / "vault").rglob("*.original"))
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert record["source_gaps"][0]["outcome"] == "image_fallback"
    absent = next(a for a in record["asset_targets"] if a["asset_id"] == NOTE)
    assert absent["actual_sha256"] is None and absent["actual_length"] is None
    assert absent["relative_path"] is None
    assert record["generated_presentations"][0]["image_paths"] == [
        "Attachments/22222222/card.png"
    ]
    assert (
        hashlib.sha256(image.read_bytes()).hexdigest()
        == next(a for a in record["asset_targets"] if a["asset_id"] == IMAGE)[
            "actual_sha256"
        ]
    )
    assert source.read_bytes() == before


OTHER_IMAGE = "66666666-6666-4666-8666-666666666666"


@pytest.mark.parametrize("declared", [0, 9876])
@pytest.mark.parametrize("reverse", [False, True])
def test_multiple_owned_images_follow_identity_order_with_cli_and_checker(
    tmp_path, capsys, declared, reverse
):
    parts = fallback_parts(tmp_path)
    change_record(parts, NOTE, DataLength=declared)
    add_attachment(parts, OTHER_IMAGE, 12, "z-first.png", png_bytes())
    if reverse:
        parts["attachments.json"] = b"\n".join(
            reversed(parts["attachments.json"].splitlines())
        )
        parts = dict(reversed(list(parts.items())))
    source = write_source(tmp_path, parts)
    assert main(["inspect", str(source), "--json"]) == 2
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["counts"]["planned_generated_embeds"] == 2
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["counts"]["actual_generated_embeds"] == 2
    text = (vault / "Home — Entry thought.md").read_text()
    assert text.index("z-first.png]]") < text.index("card.png]]")
    assert check_vault(vault).outcome == "clean"
    (vault / "Attachments/22222222/card.png").unlink()
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    checked = check_vault(vault)
    assert any(i.code == "missing_image" for i in checked.issues)
    assert {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    } == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("Type", 5),
        ("NoteType", 0),
        ("SourceType", 1),
        ("IsIcon", True),
        ("IsBrainAttachment", True),
        ("IsBrainIcon", True),
        ("IsWallpaper", True),
        ("IsAiScriptsFile", True),
        ("IsKeyboardShortcutsFile", True),
        ("IsToolbarConfigFile", True),
        ("Location", "other.md"),
        ("Location", "../Notes.md"),
        ("Location", "folder/Notes.md"),
        ("DataLength", -1),
        ("DataLength", True),
        ("DataLength", "0"),
        ("SourceId", "99999999-9999-4999-8999-999999999999"),
        ("BrainId", "99999999-9999-4999-8999-999999999999"),
        ("Id", "invalid"),
        ("Id", IMAGE),
    ],
)
def test_absent_declaration_near_miss_refuses_without_publishing(
    tmp_path, field, value
):
    parts = fallback_parts(tmp_path)
    change_record(parts, NOTE, **{field: value})
    source = write_source(tmp_path, parts)
    before = source.read_bytes()
    marker = tmp_path / "caller.bin"
    marker.write_bytes(b"caller\r\n")
    workflow = default_workflow()
    assert workflow.inspect(source).outcome == "refused"
    assert workflow.convert(source, tmp_path / "vault").outcome == "refused"
    assert not (tmp_path / "vault").exists()
    assert source.read_bytes() == before and marker.read_bytes() == b"caller\r\n"


@pytest.mark.parametrize(
    "state,payload",
    [(9, None), (True, None), (1, None), (2, None), (3, b""), (3, b"present")],
)
def test_note_state_contradiction_refuses(tmp_path, state, payload):
    parts = fallback_parts(tmp_path)
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"][NOTE] = state
    parts["meta.json"] = json.dumps(meta).encode()
    if payload is not None:
        parts[OWNER + "/Notes.md"] = payload
    assert (
        default_workflow().inspect(write_source(tmp_path, parts)).outcome == "refused"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("Type", 1),
        ("NoteType", 4),
        ("SourceType", 1),
        ("IsIcon", True),
        ("DataLength", 999),
        ("DataLength", -1),
        ("DataLength", True),
        ("Location", "../card.png"),
        ("Id", NOTE),
    ],
)
def test_owned_image_basis_near_miss_refuses(tmp_path, field, value):
    parts = fallback_parts(tmp_path)
    change_record(parts, IMAGE, **{field: value})
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "refused" and not (tmp_path / "vault").exists()


@pytest.mark.parametrize("pixels", [b"not pixels", png_bytes()[:33], png_bytes()[:-15]])
def test_complete_image_decode_is_required_even_with_valid_header_and_length(
    tmp_path, pixels
):
    parts = fallback_parts(tmp_path)
    parts[OWNER + "/.data/md-images/card.png"] = pixels
    change_record(parts, IMAGE, DataLength=len(pixels))
    inspected = default_workflow().inspect(write_source(tmp_path, parts))
    assert (
        inspected.outcome == "refused" and inspected.issues[0].code == "invalid_source"
    )


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b" \r\n\t",
        b"\xef\xbb\xbf",
        b"Caption\r\n",
        b'![x](.data/md-images/card.png "title")\r',
        b"| ![x](.data/md-images/card.png) |\n",
        "Unicode Ω [nested [label]](https://example.com)\r\n`![literal](.data/md-images/no.png)`\r".encode(),
    ],
)
@pytest.mark.parametrize("note_type", [0, 4])
def test_present_recognized_note_wins_without_new_pixel_processing(
    tmp_path, body, note_type
):
    parts = fallback_parts(tmp_path)
    parts[OWNER + "/Notes.md"] = body
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"][NOTE] = 1
    parts["meta.json"] = json.dumps(meta).encode()
    change_record(parts, NOTE, NoteType=note_type, DataLength=len(body))
    parts[OWNER + "/.data/md-images/card.png"] = (
        b"accepted present-note synthetic image"
    )
    change_record(
        parts, IMAGE, DataLength=len(b"accepted present-note synthetic image")
    )
    source = write_source(tmp_path, parts)
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "clean", inspected.issues
    assert (
        inspected.counts.source_gaps == 0
        and inspected.counts.planned_generated_embeds == 0
    )
    assert len(inspected.inspection.documents) == 1
    converted = default_workflow().convert(source, tmp_path / "vault")
    assert converted.outcome == "clean", converted.issues
    note = (tmp_path / "vault/Home — Entry thought.md").read_bytes().decode()
    expected = body.decode("utf-8-sig").replace(
        ".data/md-images/card.png", "Attachments/22222222/card.png"
    )
    assert "# Entry thought\n\n" + expected in note
    assert "Source note text is absent" not in note
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == body


@pytest.mark.parametrize("align_obligations", [False, True])
def test_renderer_rejects_forged_generated_image_destination(
    tmp_path, align_obligations
):
    source = write_source(tmp_path, fallback_parts(tmp_path))
    with BrzSourceModule().open(source) as session:
        planned = plan(analyze(session.snapshot, BRZ_POLICY))
    targets = tuple(
        t.model_copy(update={"relative_path": "Attachments/forged.png"})
        if t.asset_id == IMAGE
        else t
        for t in planned.asset_targets
    )
    generated = tuple(
        p.model_copy(update={"image_paths": ("Attachments/forged.png",)})
        for p in planned.generated_presentations
    )
    forged = planned.model_copy(
        update={
            "asset_targets": targets,
            "generated_presentations": generated
            if align_obligations
            else planned.generated_presentations,
        }
    )
    metadata = RunMetadata(
        converter_version="0.3.0",
        renderer_version="3",
        run_id="test",
        run_time="2026-10-06T00:00:00Z",
        obsidian_version="1.12.4",
        bookmark_time=1,
    )
    with pytest.raises(MigrationRefused):
        ObsidianRenderer().render(forged, metadata)


@pytest.mark.parametrize("field", ["source_gaps", "generated_presentations"])
def test_renderer_refuses_forged_source_gap_counts(tmp_path, field):
    source = write_source(tmp_path, fallback_parts(tmp_path))
    with BrzSourceModule().open(source) as session:
        planned = plan(analyze(session.snapshot, BRZ_POLICY))
    forged = planned.model_copy(
        update={"counts": planned.counts.model_copy(update={field: 999})}
    )
    metadata = RunMetadata(
        converter_version="0.3.0",
        renderer_version="3",
        run_id="test",
        run_time="2026-10-06T00:00:00Z",
        obsidian_version="1.12.4",
        bookmark_time=1,
    )
    with pytest.raises(MigrationRefused):
        ObsidianRenderer().render(forged, metadata)


@pytest.mark.parametrize("materialized", [False, True])
def test_existing_txt_diagnostics_distinguish_created_and_uncreated_owners(
    tmp_path, materialized
):
    parts = source_parts(tmp_path)
    owner = OWNER if materialized else "88888888-8888-4888-8888-888888888888"
    if not materialized:
        thought = json.loads(parts["thoughts.json"])
        thought.update(Id=owner, Name="Empty owner")
        parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
    add_attachment(parts, PDF, 1, "empty.pdf", b"", owner=owner)
    add_attachment(parts, TXT, 15, PDF + ".txt", declared=0, state=2, owner=owner)
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings"
    report = (tmp_path / "vault/MIGRATION REPORT.md").read_text(encoding="utf-8")
    if materialized:
        assert "[[Home — Entry thought.md|Entry thought]]" in report
    else:
        assert "uncreated target: Notes/Empty owner.md" in report
        assert "[[Notes/Empty owner.md" not in report
        assert not (tmp_path / "vault/Notes/Empty owner.md").exists()


def test_text_cli_names_generated_embeds_separately_from_authored_references(
    tmp_path, capsys
):
    source = write_source(tmp_path, fallback_parts(tmp_path))
    assert main(["inspect", str(source)]) == 2
    text = capsys.readouterr().out
    assert "Planned generated image embeds: 1" in text
    assert "Local references: 0; planned conversions: 0" in text


@pytest.mark.parametrize(
    "mutation",
    [
        "no_image",
        "missing_image",
        "state2",
        "state3",
        "wrong_owner",
        "mixed_invalid",
        "duplicate_path",
        "zero_dimensions",
        "crc",
    ],
)
def test_required_image_basis_is_complete_owned_and_intact(tmp_path, mutation):
    parts = fallback_parts(tmp_path)
    member = OWNER + "/.data/md-images/card.png"
    if mutation == "no_image":
        parts.pop(member)
        parts["attachments.json"] = parts["attachments.json"].splitlines()[0]
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"].pop(IMAGE)
        parts["meta.json"] = json.dumps(meta).encode()
    elif mutation == "missing_image":
        parts.pop(member)
    elif mutation in {"state2", "state3"}:
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][IMAGE] = int(mutation[-1])
        parts["meta.json"] = json.dumps(meta).encode()
    elif mutation == "wrong_owner":
        owner = "88888888-8888-4888-8888-888888888888"
        thought = json.loads(parts["thoughts.json"])
        thought.update(Id=owner, Name="Entry thought")
        parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
        change_record(parts, IMAGE, SourceId=owner)
        parts[owner + "/.data/md-images/card.png"] = parts.pop(member)
    elif mutation == "mixed_invalid":
        add_attachment(parts, OTHER_IMAGE, 12, "invalid.png", b"not pixels")
    elif mutation == "duplicate_path":
        add_attachment(parts, OTHER_IMAGE, 12, "card.png", png_bytes())
    elif mutation == "zero_dimensions":
        raw = bytearray(png_bytes())
        raw[16:20] = b"\x00" * 4
        raw[29:33] = struct.pack(">I", zlib.crc32(raw[12:29]))
        parts[member] = bytes(raw)
    source = write_source(tmp_path, parts)
    if mutation == "crc":
        source.write_bytes(
            source.read_bytes().replace(png_bytes(), b"x" + png_bytes()[1:])
        )
    before = source.read_bytes()
    workflow = default_workflow()
    assert workflow.inspect(source).outcome == "refused"
    assert workflow.convert(source, tmp_path / "vault").outcome == "refused"
    assert not (tmp_path / "vault").exists() and source.read_bytes() == before


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("body", [b"", b"\xef\xbb\xbf"])
def test_competing_present_note_never_rescues_an_absent_declaration(
    tmp_path, reverse, body
):
    parts = fallback_parts(tmp_path)
    add_attachment(parts, OTHER_IMAGE, 1, "Competing.md", body)
    change_record(parts, OTHER_IMAGE, NoteType=4)
    if reverse:
        parts["attachments.json"] = b"\n".join(
            reversed(parts["attachments.json"].splitlines())
        )
    result = default_workflow().convert(
        write_source(tmp_path, parts), tmp_path / "vault"
    )
    assert result.outcome == "refused" and result.issues[0].code == "invalid_source"
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_gap",
        "gap_owner",
        "gap_asset",
        "gap_rule",
        "gap_evidence",
        "duplicate_gap",
        "missing_presentation",
        "presentation_owner",
        "duplicate_presentation",
        "empty_images",
        "duplicate_images",
        "wrong_image",
        "false_inventory",
        "false_hash",
        "absent_inventory",
    ],
)
def test_public_analysis_refuses_inconsistent_source_gap_joins(tmp_path, mutation):
    source = write_source(tmp_path, fallback_parts(tmp_path))
    with BrzSourceModule().open(source) as session:
        snapshot = session.snapshot
    gap = snapshot.source_gaps[0]
    presentation = snapshot.generated_presentations[0]
    updates = {
        "missing_gap": {"source_gaps": ()},
        "gap_owner": {"source_gaps": (gap.model_copy(update={"owner": "unknown"}),)},
        "gap_asset": {"source_gaps": (gap.model_copy(update={"asset_id": IMAGE}),)},
        "gap_rule": {"source_gaps": (gap.model_copy(update={"rule_id": "unknown"}),)},
        "gap_evidence": {"source_gaps": (gap.model_copy(update={"evidence": ()}),)},
        "duplicate_gap": {"source_gaps": (gap, gap)},
        "missing_presentation": {"generated_presentations": ()},
        "presentation_owner": {
            "generated_presentations": (
                presentation.model_copy(update={"owner": "unknown"}),
            )
        },
        "duplicate_presentation": {
            "generated_presentations": (presentation, presentation)
        },
        "empty_images": {
            "generated_presentations": (
                presentation.model_copy(update={"image_asset_ids": ()}),
            )
        },
        "duplicate_images": {
            "generated_presentations": (
                presentation.model_copy(update={"image_asset_ids": (IMAGE, IMAGE)}),
            )
        },
        "wrong_image": {
            "generated_presentations": (
                presentation.model_copy(update={"image_asset_ids": (NOTE,)}),
            )
        },
    }
    if mutation in updates:
        snapshot = snapshot.model_copy(update=updates[mutation])
    else:
        key = NOTE if mutation == "absent_inventory" else IMAGE
        fields = (
            {"actual_length": 1}
            if mutation == "absent_inventory"
            else {"actual_length": 0}
            if mutation == "false_inventory"
            else {"actual_sha256": "invented"}
        )
        snapshot = snapshot.model_copy(
            update={
                "assets": tuple(
                    a.model_copy(update=fields) if a.asset_id == key else a
                    for a in snapshot.assets
                )
            }
        )
    with pytest.raises(MigrationRefused):
        analyze(snapshot, BRZ_POLICY)


def test_owned_png_and_webp_are_both_displayed_without_recompression(tmp_path):
    webp = b64decode("UklGRhwAAABXRUJQVlA4TA8AAAAvAQAAAAfQ/4j+ByKi/wEA")
    parts = fallback_parts(tmp_path)
    add_attachment(parts, OTHER_IMAGE, 12, "green.webp", webp)
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings", result.issues
    note = (tmp_path / "vault/Home \u2014 Entry thought.md").read_bytes().decode()
    assert note.index("green.webp]]") < note.index("card.png]]")
    assert (tmp_path / "vault/Attachments/22222222/green.webp").read_bytes() == webp
    assert result.counts.actual_generated_embeds == 2
    assert check_vault(tmp_path / "vault").outcome == "clean"


@pytest.mark.parametrize("fields", [{"actual_sha256": "0" * 64}, {"actual_length": 1}])
def test_publication_refuses_forged_generated_image_measurements(tmp_path, fields):
    source = write_source(tmp_path, fallback_parts(tmp_path))

    class ChangedInventory:
        @contextmanager
        def open(self, source_ref):
            with BrzSourceModule().open(source_ref) as session:
                session.snapshot = session.snapshot.model_copy(
                    update={
                        "assets": tuple(
                            a.model_copy(update=fields) if a.asset_id == IMAGE else a
                            for a in session.snapshot.assets
                        )
                    }
                )
                yield session

    workflow = Workflow(
        SourceModuleBinding(ChangedInventory(), BRZ_POLICY),
        ObsidianRenderer(),
        FilesystemPublisher(),
    )
    result = workflow.convert(source, tmp_path / "vault")
    assert result.outcome == "failed" and not (tmp_path / "vault").exists()
    assert result.receipt is None


def test_crc_valid_image_structure_with_invalid_compressed_pixels_refuses(tmp_path):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    pixels = (
        png_bytes()[:33]
        + chunk(b"IDAT", b"invalid compressed pixels")
        + chunk(b"IEND", b"")
    )
    parts = fallback_parts(tmp_path)
    parts[OWNER + "/.data/md-images/card.png"] = pixels
    change_record(parts, IMAGE, DataLength=len(pixels))
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused" and result.issues[0].code == "invalid_source"
    assert not (tmp_path / "vault").exists()


def test_renderer_refuses_aligned_but_noncanonical_fallback_owner_target(tmp_path):
    source = write_source(tmp_path, fallback_parts(tmp_path))
    with BrzSourceModule().open(source) as session:
        planned = plan(analyze(session.snapshot, BRZ_POLICY))
    forged = planned.model_copy(
        update={
            "item_targets": tuple(
                t.model_copy(update={"relative_path": "Notes/forged.md"})
                if t.item_key == OWNER
                else t
                for t in planned.item_targets
            ),
            "source_gaps": tuple(
                g.model_copy(update={"owner_target": "Notes/forged.md"})
                for g in planned.source_gaps
            ),
            "generated_presentations": tuple(
                p.model_copy(update={"note_path": "Notes/forged.md"})
                for p in planned.generated_presentations
            ),
        }
    )
    metadata = RunMetadata(
        converter_version="0.3.0",
        renderer_version="3",
        run_id="test",
        run_time="2026-10-06T00:00:00Z",
        obsidian_version="1.12.4",
        bookmark_time=1,
    )
    with pytest.raises(MigrationRefused):
        ObsidianRenderer().render(forged, metadata)


@pytest.mark.parametrize("kind", [4, 5])
def test_absent_note_refuses_unsupported_owner_roles(tmp_path, kind):
    owner = "88888888-8888-4888-8888-888888888888"
    parts = fallback_parts(tmp_path)
    thought = json.loads(parts["thoughts.json"])
    thought.update(Id=owner, Name="Wrong role owner", Kind=kind)
    parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
    change_record(parts, NOTE, SourceId=owner)
    change_record(parts, IMAGE, SourceId=owner)
    parts[owner + "/.data/md-images/card.png"] = parts.pop(
        OWNER + "/.data/md-images/card.png"
    )
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused" and not (tmp_path / "vault").exists()


def test_foreign_identical_image_is_preserved_without_supplying_fallback_embeds(
    tmp_path,
):
    owner = "88888888-8888-4888-8888-888888888888"
    parts = fallback_parts(tmp_path)
    thought = json.loads(parts["thoughts.json"])
    thought.update(Id=owner, Name="Entry thought")
    parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
    add_attachment(parts, OTHER_IMAGE, 12, "card.png", png_bytes(), owner=owner)
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings" and result.counts.actual_generated_embeds == 1
    note = (tmp_path / "vault/Home \u2014 Entry thought.md").read_bytes().decode()
    assert "![[Attachments/22222222/card.png]]" in note
    assert "Attachments/88888888/card.png" not in note
    assert (
        tmp_path / "vault/Attachments/88888888/card.png"
    ).read_bytes() == png_bytes()


def test_forgotten_absent_note_and_unusable_images_do_not_enter_gap_obligations(
    tmp_path,
):
    owner = "88888888-8888-4888-8888-888888888888"
    absent = "99999999-9999-4999-8999-999999999999"
    parts = fallback_parts(tmp_path)
    thought = json.loads(parts["thoughts.json"])
    thought.update(
        Id=owner, Name="Private excluded owner", ForgottenDateTime="2026-10-05T00:00:00"
    )
    parts["thoughts.json"] += b"\n" + json.dumps(thought).encode()
    add_attachment(parts, absent, 1, "Notes.md", declared=33, state=3, owner=owner)
    change_record(parts, absent, NoteType=4)
    add_attachment(
        parts, OTHER_IMAGE, 12, "private.png", b"invalid excluded pixels", owner=owner
    )
    source = write_source(tmp_path, parts)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "warnings" and result.counts.source_gaps == 1
    assert result.counts.actual_assets == result.counts.actual_generated_embeds == 1
    public = result.model_dump_json()
    for private in [
        owner,
        absent,
        OTHER_IMAGE,
        "Private excluded owner",
        "invalid excluded pixels",
        "private.png",
    ]:
        assert private not in public
        assert all(
            private.encode() not in p.read_bytes()
            for p in (tmp_path / "vault").rglob("*")
            if p.is_file()
        )
