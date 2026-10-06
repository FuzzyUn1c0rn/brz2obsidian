"""Public raw-source oracle controls for the reviewed scoped conversion."""

import base64
import copy
import ctypes
import hashlib
import json
import struct
import zlib
from uuid import UUID
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_absent_note_images_workflow import (
    IMAGE,
    fallback_parts,
    png_bytes,
)
from tests.application.test_forgotten_workflow import forget, rewrite
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_type_source_gaps_workflow import (
    remove_type_note,
    type_parts,
)
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    write_source,
)
from tests.local_acceptance.checker import ROOTS, check_vault, load_json
from tests.local_acceptance.test_checker_v2 import rewrite_record


def test_oracle_derives_scope_and_original_ordinals_before_scoped_provenance(tmp_path):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Excluded first", 3: "Included last"},
        [(1, 2, 1, 1, -1), (1, 3, 1, 1, -1)],
        notes={2: (b"owned excluded bytes", 4), 3: (b"safe included body", 4)},
    )
    rewrite(source, lambda parts: forget(parts, 2))
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean"
    summary = check_vault(source, vault)
    assert summary["source_items"] == 2
    assert summary["source_relationships"] == 1
    assert summary["payloads"] == summary["documents"] == 1
    record = load_json((vault / "migration-record.json").read_bytes())
    included = next(t for t in record["item_targets"] if t["item_key"] == identity(3))
    assert included["metadata_evidence"] == ["thoughts.json:1"]
    with ZipFile(source) as original:
        assert json.loads(original.read("thoughts.json").splitlines()[2])[
            "Id"
        ] == identity(3)


@pytest.mark.parametrize(
    "phrase",
    ["[private **label**]", "![private]", "[![private](https://example.invalid/card)]"],
)
def test_oracle_independently_removes_whole_excluded_phrases_and_omits_unsafe_original(
    tmp_path, phrase
):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    body = f"α before\r\n{phrase}(brain://{compact}/private) after\rTail\n`literal brain://included`"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={1: (body.encode(), 4)},
    )
    rewrite(source, lambda parts: forget(parts, 2))
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    summary = check_vault(source, vault)
    assert (
        summary["documents"] == 1 and summary["payloads"] == summary["references"] == 0
    )


@pytest.mark.parametrize(
    "damage",
    [
        "unsafe_evidence",
        "safe_evidence_omitted",
        "safe_precision",
        "excluded_bytes",
        "body",
    ],
)
def test_scoped_semantics_reject_forged_consistent_receipts(tmp_path, damage):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={1: (b"safe body\r\n", 4)},
    )

    def edit(parts):
        forget(parts, 2)
        parts["brainusers.json"] = (
            '{"Id":"'
            + identity(8200)
            + '","Precise":0.12345678901234567890123456789,"Null":null}\n'
            '{"Id":"'
            + identity(8201)
            + '","Nested":{"SourceId":"'
            + identity(2)
            + '"},"Value":"private sibling"}'
        ).encode()

    rewrite(source, edit)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_vault(source, vault)
    record = load_json((vault / "migration-record.json").read_bytes())
    users = next(
        e["records"]
        for e in record["original_evidence"]
        if e["key"] == "brainusers.json"
    )
    if damage == "unsafe_evidence":
        users.append(
            {
                "Id": identity(8201),
                "Nested": {"SourceId": identity(2)},
                "Value": "private sibling",
            }
        )
    elif damage == "safe_evidence_omitted":
        users.clear()
    elif damage == "safe_precision":
        users[0]["Precise"] = 0.12
    elif damage == "excluded_bytes":
        (vault / "excluded.bin").write_bytes(b"private owned bytes")
    else:
        note = vault / "Home — Home.md"
        note.write_bytes(note.read_bytes().replace(b"safe body", b"false text"))
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError):
        check_vault(source, vault)


def test_oracle_derives_absent_body_images_and_generated_credit_from_raw(tmp_path):
    source = write_source(tmp_path, fallback_parts(tmp_path))
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "warnings"
    summary = check_vault(source, vault)
    assert summary["documents"] == summary["references"] == summary["backups"] == 0
    assert (
        summary["generated_embeds"]
        == summary["source_gaps"]
        == summary["payloads"]
        == 1
    )


def test_oracle_derives_neutral_category_provider_and_owned_override(tmp_path):
    parts = type_parts(tmp_path)
    remove_type_note(parts, declared=0)
    add_attachment(
        parts, identity(3001), 5, "type.png", state=3, declared=7, owner=identity(2)
    )
    source = write_source(tmp_path, parts)
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "warnings"
    summary = check_vault(source, vault)
    assert summary["source_gaps"] == 2 and summary["typed_members"] == 1
    assert summary["typed_inherited_icons"] == summary["generated_embeds"] == 0


def mixed_v3_archive(path):
    """Independent synthetic raw joins covering interacting v3 behavior."""
    compact = base64.urlsafe_b64encode(UUID(identity(8)).bytes_le).decode().rstrip("=")
    live = base64.urlsafe_b64encode(UUID(identity(9)).bytes_le).decode().rstrip("=")
    body = f"Home prose\r\n[![private](https://example.invalid/card)](brain://{compact}/private)\rafter [reserved](brain://{live}/same-title)\n![authored](.data/md-images/home.png)\n`literal brain://{live}`"
    graph_archive(
        path,
        {
            1: "Home",
            2: "Concept",
            3: "Member",
            4: "Override",
            5: "Image owner",
            6: "TXT owner",
            7: "Excluded provider",
            8: "Same title",
            9: "Same title",
            10: "Excluded member",
        },
        [
            (1, 2, 1, 1, -1),
            (2, 3, 1, 2, -1),
            (2, 4, 1, 2, -1),
            (7, 9, 1, 2, -1),
            (2, 10, 1, 2, -1),
            (1, 8, 1, 1, -1),
        ],
        kinds={2: 2, 7: 2},
        labels={2: "Retained category label", 8: "Private label"},
        notes={
            1: (body.encode(), 4),
            2: (b"absent definition", 4),
            3: (b"\xef\xbb\xbf", 4),
            5: (b"unknown", 4),
            8: (b"private payload", 4),
        },
    )
    with ZipFile(path) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    forget(parts, 7, 8, 10)
    rows = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    for row in rows:
        if row["Id"] in {identity(3), identity(4), identity(10)}:
            row["TypeId"] = identity(2)
        if row["Id"] == identity(9):
            row["TypeId"] = identity(7)
    parts["thoughts.json"] = b"\n".join(json.dumps(r).encode() for r in rows)
    meta = json.loads(parts["meta.json"])
    for n in (2, 5):
        parts.pop(identity(n) + "/Notes.md")
        meta["AttachmentFileStates"][identity(2000 + n)] = 3
    parts["meta.json"] = json.dumps(meta).encode()
    add_attachment(
        parts, identity(3001), 5, "type.png", declared=9, state=3, owner=identity(2)
    )
    add_attachment(
        parts, identity(3002), 5, "override.png", png_bytes(), owner=identity(4)
    )
    add_attachment(
        parts,
        identity(3003),
        12,
        "z-first.webp",
        base64.b64decode("UklGRhwAAABXRUJQVlA4TA8AAAAvAQAAAAfQ/4j+ByKi/wEA"),
        owner=identity(5),
    )
    add_attachment(
        parts, identity(3004), 12, "a-last.png", png_bytes(), owner=identity(5)
    )
    add_attachment(
        parts, identity(3005), 12, "home.png", png_bytes(), owner=identity(1)
    )
    add_attachment(
        parts, identity(3008), 12, "private.png", png_bytes(), owner=identity(8)
    )
    add_attachment(parts, identity(3006), 1, "empty.pdf", b"", owner=identity(6))
    add_attachment(
        parts,
        identity(3007),
        15,
        identity(3006) + ".txt",
        declared=0,
        state=2,
        owner=identity(6),
    )
    parts["brainusers.json"] = (
        '{"Id":"'
        + identity(8201)
        + '","Nested":"{\\"SourceId\\":\\"'
        + identity(8)
        + '\\"}","Value":"private sibling"}\n'
        '{"Id":"'
        + identity(8202)
        + '","Nested":{"AttachmentId":"'
        + identity(8201)
        + '"},"Value":"private transitive"}\n'
        '{"Id":"'
        + identity(8203)
        + '","Precise":0.12345678901234567890123456789,"Null":null}'
    ).encode()
    with ZipFile(path, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return path


def test_oracle_conserves_mixed_scoped_source_and_repeat_reorder(tmp_path):
    from tests.local_acceptance.checker import check_run_result, compare_vaults
    from tests.local_acceptance.run import reordered_archive

    source = mixed_v3_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert result["outcome"] == "warnings", result["issues"]
    summary = check_vault(source, vault)
    check_run_result(result, vault, summary)
    assert (
        summary["source_items"],
        summary["source_relationships"],
        summary["notes"],
        summary["source_gaps"],
        summary["generated_embeds"],
        summary["documents"],
        summary["references"],
        summary["backups"],
        summary["typed_members"],
        summary["typed_owned_overrides"],
        summary["typed_inherited_icons"],
    ) == (7, 3, 5, 3, 2, 2, 2, 1, 2, 1, 0)
    assert summary["decoded_image_frames"] == 2
    assert len(summary["image_decoder_capabilities"]) == 2
    with ZipFile(source) as original:
        assert original.read(
            identity(8) + "/.data/md-images/private.png"
        ) == original.read(identity(5) + "/.data/md-images/a-last.png")
    assert (
        vault / "Attachments/00000000000000000000000000000005/a-last.png"
    ).read_bytes() == png_bytes()
    reordered = tmp_path / "reordered.brz"
    reordered_archive(source, reordered)
    for name, archive in (("repeat", source), ("reordered", reordered)):
        other = tmp_path / name
        default_workflow().convert(archive, other)
        assert check_vault(archive, other) == summary
        compare_vaults(vault, other)


@pytest.mark.parametrize(
    "damage",
    [
        "excluded_identity",
        "excluded_asset",
        "excluded_label",
        "unsafe_evidence",
        "safe_evidence_omitted",
        "safe_precision",
        "safe_original_omitted",
        "unsafe_original_fabricated",
        "absent_original_fabricated",
        "missing_embed",
        "duplicate_embed",
        "misowned_embed",
        "ordered_embeds",
        "resources_only",
        "extra_heading",
        "recovered_prose",
        "generated_obligation_order",
        "generated_obligation_missing",
        "fake_document",
        "fake_reference_credit",
        "gap_outcome",
        "gap_owner",
        "gap_observation",
        "neutral_icon",
        "provider",
        "affected_member",
        "override",
        "membership",
        "hierarchy_omitted",
        "hierarchy_reversed",
        "hierarchy_membership",
        "category_views_first",
        "diagnostic_owner",
        "diagnostic_state",
        "diagnostic_image",
        "diagnostic_member",
        "diagnostic_fingerprint",
        "txt_materialized",
        "scoped_digest",
    ],
)
def test_mixed_v3_semantic_corruption_cannot_hide_behind_consistent_receipts(
    tmp_path, damage
):
    source = mixed_v3_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_vault(source, vault)
    record = load_json((vault / "migration-record.json").read_bytes())
    items = {t["item_key"]: t for t in record["item_targets"]}
    assets = {a["asset_id"]: a for a in record["asset_targets"]}
    presentation = record["generated_presentations"][0]
    image_note = vault / "Notes/Image owner.md"
    first = b"![[Attachments/00000000000000000000000000000005/z-first.webp]]"
    last = b"![[Attachments/00000000000000000000000000000005/a-last.png]]"
    before = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    original_record = copy.deepcopy(record)
    if damage == "excluded_identity":
        target = copy.deepcopy(items[identity(9)])
        target.update(
            item_key=identity(8),
            original_identity=identity(8),
            original_title="Same title",
            relative_path="Notes/Excluded.md",
        )
        record["item_targets"].append(target)
    elif damage == "excluded_asset":
        asset = copy.deepcopy(assets[identity(3005)])
        asset.update(
            asset_id=identity(2008),
            owner=identity(8),
            relative_path="Attachments/excluded.png",
        )
        record["asset_targets"].append(asset)
        (vault / asset["relative_path"]).write_bytes(b"private payload")
        asset["actual_length"] = len(b"private payload")
        asset["actual_sha256"] = hashlib.sha256(b"private payload").hexdigest()
        record["counts"]["planned_assets"] += 1
        record["counts"]["present_assets"] += 1
    elif damage == "excluded_label":
        image_note.write_bytes(image_note.read_bytes() + b"Private label\n")
    elif damage in {"unsafe_evidence", "safe_evidence_omitted", "safe_precision"}:
        users = next(
            e["records"]
            for e in record["original_evidence"]
            if e["key"] == "brainusers.json"
        )
        if damage == "unsafe_evidence":
            users.append(
                {
                    "Id": identity(8201),
                    "Nested": {"SourceId": identity(8)},
                    "Value": "private sibling",
                }
            )
        elif damage == "safe_evidence_omitted":
            users.clear()
        else:
            users[0]["Precise"] = 0.12
    elif damage == "safe_original_omitted":
        (vault / assets[identity(2003)]["relative_path"]).unlink()
        assets[identity(2003)].update(
            availability="absent",
            relative_path=None,
            actual_length=None,
            actual_sha256=None,
        )
        record["counts"]["planned_assets"] -= 1
        record["counts"]["present_assets"] -= 1
    elif damage in {"unsafe_original_fabricated", "absent_original_fabricated"}:
        key = (
            identity(2001) if damage == "unsafe_original_fabricated" else identity(2005)
        )
        asset = (
            copy.deepcopy(assets[identity(2003)])
            if key == identity(2001)
            else assets[key]
        )
        asset.update(
            asset_id=key,
            owner=identity(1) if key == identity(2001) else identity(5),
            availability="present",
            relative_path="Attachments/fabricated.original",
            actual_length=0,
            actual_sha256=hashlib.sha256(b"").hexdigest(),
        )
        if key == identity(2001):
            record["asset_targets"].append(asset)
        (vault / asset["relative_path"]).write_bytes(b"")
        record["counts"]["planned_assets"] += 1
        record["counts"]["present_assets"] += 1
    elif damage in {
        "missing_embed",
        "duplicate_embed",
        "ordered_embeds",
        "resources_only",
        "extra_heading",
        "recovered_prose",
    }:
        text = image_note.read_bytes()
        if damage == "missing_embed":
            text = text.replace(first + b"\n\n", b"")
            presentation["presentation"]["image_asset_ids"].pop(0)
            presentation["image_paths"].pop(0)
            record["counts"]["planned_generated_embeds"] -= 1
            record["counts"]["actual_generated_embeds"] -= 1
        elif damage == "duplicate_embed":
            text += first + b"\n"
            presentation["presentation"]["image_asset_ids"].append(identity(3003))
            presentation["image_paths"].append(presentation["image_paths"][0])
            record["counts"]["planned_generated_embeds"] += 1
            record["counts"]["actual_generated_embeds"] += 1
        elif damage == "ordered_embeds":
            text = text.replace(first + b"\n\n" + last, last + b"\n\n" + first)
            presentation["presentation"]["image_asset_ids"].reverse()
            presentation["image_paths"].reverse()
        elif damage == "resources_only":
            text = text.replace(first, b"## Resources\n\n- " + first[1:]).replace(
                last, b"- " + last[1:]
            )
            record["counts"]["planned_generated_embeds"] = record["counts"][
                "actual_generated_embeds"
            ] = 0
        elif damage == "extra_heading":
            text = text.replace(first, b"## Available note images\n\n" + first)
        else:
            text = text.replace(
                first, b"Recovered prose and guessed captions.\n\n" + first
            )
        image_note.write_bytes(text)
    elif damage == "misowned_embed":
        image_note.write_bytes(image_note.read_bytes().replace(first + b"\n\n", b""))
        member = vault / "Notes/Member.md"
        member.write_bytes(member.read_bytes() + first + b"\n")
        presentation["note_path"] = "Notes/Member.md"
        presentation["presentation"]["owner"] = identity(3)
    elif damage.startswith("generated_obligation"):
        if damage.endswith("order"):
            presentation["presentation"]["image_asset_ids"].reverse()
            presentation["image_paths"].reverse()
        else:
            record["generated_presentations"].clear()
            record["counts"]["generated_presentations"] = record["counts"][
                "planned_generated_embeds"
            ] = record["counts"]["actual_generated_embeds"] = 0
    elif damage == "fake_document":
        document = copy.deepcopy(items[identity(3)]["documents"][0])
        document.update(
            key=identity(2005),
            owner=identity(5),
            original_asset_id=identity(2005),
            owner_target="Notes/Image owner.md",
        )
        items[identity(5)]["documents"].append(document)
    elif damage == "fake_reference_credit":
        for field in ("source_references", "planned_references", "actual_references"):
            record["counts"][field] += 2
    elif damage.startswith("gap_"):
        gap = next(
            g for g in record["source_gaps"] if g["gap"]["role"] == "ordinary_note"
        )
        if damage == "gap_outcome":
            gap["outcome"] = "unknown_note"
        elif damage == "gap_owner":
            gap["gap"]["owner"] = identity(3)
        else:
            finding = assets[identity(2005)]["source_findings"][0]
            observation = json.loads(finding["observed_json"])
            observation["state"] = 2
            finding["observed_json"] = json.dumps(observation)
            next(i for i in record["issues"] if i["affected"] == [identity(2005)])[
                "message"
            ] = "Forged source observation. Observed: " + finding["observed_json"]
    elif damage == "neutral_icon":
        items[identity(3)]["icon_snapshot"]["effective_icon_asset_id"] = identity(3002)
    elif damage == "provider":
        items[identity(3)]["icon_snapshot"]["appearance_category_key"] = identity(7)
    elif damage == "affected_member":
        next(g for g in record["source_gaps"] if g["gap"]["role"] == "definition_icon")[
            "affected_member_keys"
        ].append(identity(4))
    elif damage == "override":
        override = vault / "Notes/Override.md"
        text = override.read_bytes()
        override.write_bytes(text.replace(b"override.png", b"home.png"))
    elif damage == "membership":
        record["classification_assignments"][0]["definition_key"] = identity(7)
    elif damage.startswith("hierarchy_"):
        relationship = next(
            r for r in record["relationships"] if r["kind"] == "hierarchy"
        )
        if damage == "hierarchy_omitted":
            record["relationships"].remove(relationship)
            record["counts"]["source_relationships"] -= 1
        elif damage == "hierarchy_reversed":
            relationship["item_a"], relationship["item_b"] = (
                relationship["item_b"],
                relationship["item_a"],
            )
            relationship["target_a"], relationship["target_b"] = (
                relationship["target_b"],
                relationship["target_a"],
            )
        else:
            record["classification_assignments"].append(
                {
                    "relationship_key": relationship["key"],
                    "definition_key": identity(2),
                    "item_key": identity(1),
                    "definition_target": "Categories/Concept.md",
                    "item_target": "Home — Home.md",
                    "evidence": relationship["evidence"],
                }
            )
            record["counts"]["classification_assignments"] += 1
            record["counts"]["typed_members"] += 1
    elif damage == "category_views_first":
        category = vault / "Categories/Concept.md"
        navigation = b"## Parents\n\n- [[Home \xe2\x80\x94 Home.md|Home]]\n\n"
        text = category.read_bytes()
        assert navigation in text
        category.write_bytes(
            text.replace(navigation, b"").replace(
                b"Retained category label", navigation + b"Retained category label"
            )
        )
    elif damage.startswith("diagnostic_"):
        report = vault / "MIGRATION REPORT.md"
        text = report.read_text(encoding="utf-8")
        replacements = {
            "diagnostic_owner": (
                "- [ ] [[Notes/Image owner.md|Image owner]]",
                "- [ ] [[Notes/Member.md|Image owner]]",
            ),
            "diagnostic_state": ('"state": 3', '"state": 2'),
            "diagnostic_image": (
                "Image "
                + identity(3003)
                + ": [[Attachments/00000000000000000000000000000005/z-first.webp]]",
                "Image "
                + identity(3003)
                + ": [[Attachments/00000000000000000000000000000005/a-last.png]]",
            ),
            "diagnostic_member": (
                "  - [[Notes/Member.md|Member]]; thought ID " + identity(3),
                "  - [[Notes/Override.md|Override]]; thought ID " + identity(4),
            ),
            "diagnostic_fingerprint": (
                record["source_identity"]["source_sha256"],
                "0" * 64,
            ),
        }
        old, new = replacements[damage]
        assert old in text
        report.write_text(text.replace(old, new, 1), encoding="utf-8")
    elif damage == "txt_materialized":
        items[identity(6)].update(created=True, creation_reasons=["content"])
        (vault / "Notes/TXT owner.md").write_bytes(b"# TXT owner\n")
        record["counts"]["planned_notes"] += 1
    else:
        record["source_identity"]["snapshot_digest"] = "0" * 64
    after = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    assert record != original_record or after != before, "corruption hook must fire"
    rewrite_record(vault, record, result)
    assert (
        result["receipt"]["verified"]
        and result["receipt"]["counts"] == result["counts"]
    )
    with pytest.raises(AssertionError):
        check_vault(source, vault)


@pytest.mark.parametrize(
    "literal",
    [
        "`brain://{compact}`",
        "```md\nbrain://{compact}\n```",
        "<!-- brain://{compact} -->",
        "bare brain://{compact}",
        "bare {identity}",
        "`bare {upper_identity}`",
        "<!-- brain://{percent_compact} -->",
        "```text\n{percent_identity}\n```",
        "bare {unicode_identity}",
    ],
)
def test_oracle_refuses_residual_excluded_identity_even_without_an_original_copy(
    tmp_path, literal
):
    source = mixed_v3_archive(tmp_path / "source.brz")
    omitted = "abcdef01-2345-6789-abcd-ef0123456789"
    old_compact = (
        base64.urlsafe_b64encode(UUID(identity(8)).bytes_le).decode().rstrip("=")
    )
    compact = base64.urlsafe_b64encode(UUID(omitted).bytes_le).decode().rstrip("=")

    def identify(parts):
        for name in list(parts):
            data = parts.pop(name)
            parts[name.replace(identity(8), omitted)] = data.replace(
                identity(8).encode(), omitted.encode()
            ).replace(old_compact.encode(), compact.encode())

    rewrite(source, identify)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_vault(source, vault)
    tail = literal.format(
        compact=compact,
        identity=omitted,
        upper_identity=omitted.upper(),
        percent_compact="".join(f"%{ord(c):02x}" for c in compact),
        percent_identity="".join(f"%{ord(c):02x}" for c in omitted),
        unicode_identity="".join(f"\\u{ord(c):04x}" for c in omitted),
    ).encode()

    def edit(parts):
        parts[identity(1) + "/Notes.md"] += b"\n" + tail
        change_record(
            parts, identity(2001), DataLength=len(parts[identity(1) + "/Notes.md"])
        )

    rewrite(source, edit)
    record = load_json((vault / "migration-record.json").read_bytes())
    record["source_identity"]["source_sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    home = vault / "Home — Home.md"
    home.write_bytes(home.read_bytes() + b"\n" + tail)
    document = next(t for t in record["item_targets"] if t["item_key"] == identity(1))[
        "documents"
    ][0]
    assert document["original_copy_omitted"] and document["original_asset_id"] is None
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError, match="residual excluded identity"):
        check_vault(source, vault)


def image_candidate(tmp_path):
    source = write_source(tmp_path, fallback_parts(tmp_path))
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_vault(source, vault)
    return (
        source,
        vault,
        result,
        load_json((vault / "migration-record.json").read_bytes()),
    )


def test_compact_identity_case_is_preserved_as_distinct_safe_literal(tmp_path):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    assert compact.swapcase() != compact
    body = ("Literal `brain://" + compact.swapcase() + "` is separate.\r\n").encode()
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Private"}, notes={1: (body, 4)}
    )
    rewrite(source, lambda parts: forget(parts, 2))
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    assert check_vault(source, vault)["backups"] == 1


@pytest.mark.parametrize(
    "damage",
    ["excluded_provider", "setting_duplicate", "setting_foreign", "live_tombstone"],
)
def test_oracle_establishes_trusted_raw_identities_before_exclusion(tmp_path, damage):
    source = mixed_v3_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_vault(source, vault)
    record = load_json((vault / "migration-record.json").read_bytes())

    def edit(parts):
        if damage == "excluded_provider":
            rows = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
            next(r for r in rows if r["Id"] == identity(7))["TypeId"] = identity(99001)
            parts["thoughts.json"] = b"\n".join(json.dumps(r).encode() for r in rows)
        elif damage.startswith("setting"):
            rows = [json.loads(line) for line in parts["settings.json"].splitlines()]
            if damage == "setting_duplicate":
                rows.append(rows[0])
            else:
                rows[0]["BrainId"] = identity(99001)
            parts["settings.json"] = b"\n".join(json.dumps(r).encode() for r in rows)
        else:
            parts["tombstones.json"] = json.dumps({"Id": identity(8)}).encode()

    rewrite(source, edit)
    record["source_identity"]["source_sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    rewrite_record(vault, record, result)
    with pytest.raises(
        AssertionError, match="raw (live provider|setting|live/deleted)"
    ):
        check_vault(source, vault)


@pytest.mark.parametrize(
    "label",
    [
        "**bold**",
        "*emphasis*",
        "_emphasis_",
        "plain ` code `",
        "A &amp; B",
        r"literal \*star\*",
    ],
)
def test_complete_body_includes_independently_interpreted_authored_reference_labels(
    tmp_path, label
):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    body = (
        "Untouched α\r\n[" + label + "](brain://" + compact + "/reserved)\rTail\n"
    ).encode()
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Reserved"}, notes={1: (body, 4)}
    )
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    assert check_vault(source, vault)["references"] == 1


@pytest.mark.parametrize(
    "label,display,alias",
    [
        (r"opening \[literal", "opening [literal", "opening literal"),
        (r"closing literal\]", "closing literal]", "closing literal"),
        (r"escaped \[literal\]", "escaped [literal]", "escaped literal"),
        ("outer [nested]", "outer [nested]", "outer nested"),
    ],
)
def test_valid_bracket_labels_preserve_record_display_text_and_sanitized_alias(
    tmp_path, label, display, alias
):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    body = (
        "Untouched α\r\n[" + label + "](brain://" + compact + "/reserved)\rTail\n"
    ).encode()
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Reserved"}, notes={1: (body, 4)}
    )
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    record = load_json((vault / "migration-record.json").read_bytes())
    home = next(t for t in record["item_targets"] if t["item_key"] == identity(1))
    assert home["documents"][0]["references"][0]["display_text"] == display
    assert ("[[Notes/Reserved.md|" + alias + "]]").encode() in (
        vault / "Home — Home.md"
    ).read_bytes()
    assert check_vault(source, vault)["references"] == 1


def test_sanitized_alias_cannot_replace_richer_recorded_bracket_display_text(tmp_path):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    body = (r"[escaped \[literal\]](brain://" + compact + "/reserved)").encode()
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Reserved"}, notes={1: (body, 4)}
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert check_vault(source, vault)["references"] == 1
    record = load_json((vault / "migration-record.json").read_bytes())
    home = next(t for t in record["item_targets"] if t["item_key"] == identity(1))
    home["documents"][0]["references"][0]["display_text"] = "escaped literal"
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError, match="reference spans and targets"):
        check_vault(source, vault)


@pytest.mark.parametrize(
    "label",
    [
        "outer [nested](https://example.invalid)",
        "outer ![image](https://example.invalid/card)",
        "unclosed destination",
    ],
)
def test_bracket_label_compatibility_keeps_nested_active_and_malformed_phrases_closed(
    tmp_path, label
):
    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Reserved"},
        notes={1: (b"plain supplied body", 4)},
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    assert check_vault(source, vault)["references"] == 0

    def edit(parts):
        parts[identity(1) + "/Notes.md"] = (
            "[" + label + "](brain://" + compact + "/reserved)"
        ).encode()
        if label == "unclosed destination":
            parts[identity(1) + "/Notes.md"] = parts[identity(1) + "/Notes.md"][:-1]
        change_record(
            parts, identity(2001), DataLength=len(parts[identity(1) + "/Notes.md"])
        )

    rewrite(source, edit)
    record = load_json((vault / "migration-record.json").read_bytes())
    record["source_identity"]["source_sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    rewrite_record(vault, record, result)
    with pytest.raises(
        AssertionError,
        match="unsupported included nested thought phrase|active local reference coverage",
    ):
        check_vault(source, vault)


def forge_image_source(source, vault, record, result, image_bytes, name="card.png"):
    """Forge raw declarations, exact output bytes, observations and honest receipts."""
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    rows = [
        json.loads(line)
        for line in parts["attachments.json"].decode("utf-8-sig").splitlines()
        if line.strip()
    ]
    candidate = next(r for r in rows if r["Id"] == IMAGE)
    old_member = candidate["SourceId"] + "/.data/md-images/" + candidate["Location"]
    candidate.update(DataLength=len(image_bytes), Location=name, Name=name)
    new_member = candidate["SourceId"] + "/.data/md-images/" + name
    parts.pop(old_member)
    parts[new_member] = image_bytes
    parts["attachments.json"] = b"\n".join(json.dumps(r).encode() for r in rows)
    with ZipFile(source, "w") as archive:
        for filename, data in parts.items():
            archive.writestr(filename, data)
    digest = hashlib.sha256(image_bytes).hexdigest()
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == IMAGE)
    (vault / asset["relative_path"]).write_bytes(image_bytes)
    asset.update(
        actual_length=len(image_bytes),
        actual_sha256=digest,
        original_name=name,
        display_name=name,
    )
    for evidence in record["original_evidence"]:
        if evidence["key"] == "attachments.json":
            evidence["records"] = rows
        elif evidence["key"] == "payload:" + old_member:
            evidence["key"] = "payload:" + new_member
            evidence["records"] = {
                "member": new_member,
                "length": len(image_bytes),
                "sha256": digest,
            }
    observed = next(a for a in record["asset_targets"] if a["source_findings"])[
        "source_findings"
    ][0]
    fact = json.loads(observed["observed_json"])
    fact["images"][0].update(
        member=new_member,
        declared_length=len(image_bytes),
        actual_length=len(image_bytes),
        actual_sha256=digest,
    )
    observed["observed_json"] = json.dumps(fact)
    record["issues"][0]["message"] = (
        "Forged structurally valid receipt. Observed: " + observed["observed_json"]
    )
    record["source_identity"]["source_sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    root_parts = [
        "["
        + ",".join(
            [data.decode("utf-8-sig")]
            if n == "meta.json"
            else [
                line for line in data.decode("utf-8-sig").splitlines() if line.strip()
            ]
        )
        + "]"
        for n in ROOTS
        for data in [parts[n]]
    ]
    record["source_identity"]["snapshot_digest"] = hashlib.sha256(
        (
            "".join(root_parts)
            + json.dumps(
                {"member": new_member, "length": len(image_bytes), "sha256": digest}
            )
        ).encode()
    ).hexdigest()
    rewrite_record(vault, record, result)


def png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )


@pytest.mark.parametrize(
    "kind",
    [
        "adam7",
        "palette_sub",
        "palette_up",
        "palette_average",
        "palette_paeth",
        "two_frame_gif",
    ],
)
def test_independent_image_oracle_forces_complete_supported_frames_and_png_modes(
    tmp_path, kind
):
    from tests.application.test_absent_note_images_workflow import OWNER

    if kind == "two_frame_gif":
        descriptor = b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00"
        data = (
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\x00\x00\x00\xff\x00"
            + descriptor
            + b"\x02\x02\x44\x01\x00"
            + descriptor
            + b"\x02\x02\x4c\x01\x00\x3b"
        )
        name, frames = "card.gif", 2
    else:
        indexed = kind != "adam7"
        filter_kind = {
            "palette_sub": 1,
            "palette_up": 2,
            "palette_average": 3,
            "palette_paeth": 4,
        }.get(kind)
        header = struct.pack(
            ">IIBBBBB",
            2 if indexed else 1,
            2 if indexed else 1,
            8,
            3 if indexed else 2,
            0,
            0,
            0 if indexed else 1,
        )
        scanlines = (
            b"\x00\x00\x01" + bytes([filter_kind, 1, 255])
            if indexed
            else b"\x00\xff\x00\x00"
        )
        data = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", header)
            + (png_chunk(b"PLTE", b"\xff\x00\x00\x00\xff\x00") if indexed else b"")
            + png_chunk(b"IDAT", zlib.compress(scanlines))
            + png_chunk(b"IEND", b"")
        )
        name, frames = "card.png", 1
    parts = fallback_parts(tmp_path)
    parts.pop(OWNER + "/.data/md-images/card.png")
    parts[OWNER + "/.data/md-images/" + name] = data
    change_record(parts, IMAGE, Location=name, Name=name, DataLength=len(data))
    source = write_source(tmp_path, parts)
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "warnings"
    summary = check_vault(source, vault)
    assert summary["decoded_image_frames"] == frames
    assert summary["generated_embeds"] == 1
    assert (vault / "Attachments/22222222" / name).read_bytes() == data


@pytest.mark.parametrize(
    "damage",
    [
        "compressed",
        "scanline",
        "filter",
        "palette",
        "zero_dimensions",
        "extension",
        "webp_compressed",
    ],
)
def test_raw_image_invalid_content_rejected_after_crc_hash_length_and_receipt_repair(
    tmp_path, damage
):
    source, vault, result, record = image_candidate(tmp_path)
    if damage == "webp_compressed":
        data = bytearray(
            base64.b64decode("UklGRhwAAABXRUJQVlA4TA8AAAAvAQAAAAfQ/4j+ByKi/wEA")
        )
        data[25:35] = b"\xff" * 10  # Retain RIFF/chunk sizes and VP8L dimensions.
        forge_image_source(source, vault, record, result, bytes(data), "card.webp")
        expected = "invalid full WEBP pixel decode"
    else:
        header = struct.pack(
            ">IIBBBBB",
            0 if damage == "zero_dimensions" else 1,
            1,
            8,
            3 if damage == "palette" else 2,
            0,
            0,
            0,
        )
        scanline = (
            b"\x05\xff\x00\x00"
            if damage == "filter"
            else b"\x00\x02"
            if damage == "palette"
            else b"\x00\xff\x00"
            if damage == "scanline"
            else b"\x00\xff\x00\x00"
        )
        compressed = (
            b"\xff" * len(zlib.compress(scanline))
            if damage == "compressed"
            else zlib.compress(scanline)
        )
        data = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", header)
            + (png_chunk(b"PLTE", b"\xff\x00\x00") if damage == "palette" else b"")
            + png_chunk(b"IDAT", compressed)
            + png_chunk(b"IEND", b"")
        )
        forge_image_source(
            source,
            vault,
            record,
            result,
            data,
            "card.webp" if damage == "extension" else "card.png",
        )
        expected = (
            "invalid raw fallback image format"
            if damage == "extension"
            else "invalid PNG"
        )
    with ZipFile(source) as archive:
        assert archive.testzip() is None
    with pytest.raises(AssertionError, match=expected):
        check_vault(source, vault)


def test_missing_native_decoder_is_an_unavailable_audit_not_invalid_or_accepted(
    tmp_path, monkeypatch
):
    from tests.local_acceptance.images import AuditUnavailable

    source, vault, _, _ = image_candidate(tmp_path)

    def unavailable(*args, **kwargs):
        raise OSError("native WIC library unavailable at OS boundary")

    monkeypatch.setattr(ctypes, "WinDLL", unavailable)
    with pytest.raises(AuditUnavailable, match="unavailable"):
        check_vault(source, vault)


def test_native_decoder_allocation_failure_is_an_unavailable_audit(
    tmp_path, monkeypatch
):
    from tests.local_acceptance.images import AuditUnavailable

    source, vault, _, _ = image_candidate(tmp_path)

    def unavailable(*args, **kwargs):
        raise MemoryError("native codec metadata allocation unavailable")

    monkeypatch.setattr(ctypes, "create_unicode_buffer", unavailable)
    with pytest.raises(AuditUnavailable, match="memory"):
        check_vault(source, vault)


@pytest.mark.parametrize(
    "encoding",
    [
        "nested",
        "serialized",
        "unicode_escaped",
        "duplicate_keys",
        "twice_serialized",
        "serialized_association_value",
        "case_association_value",
    ],
)
def test_oracle_derives_nested_owned_siblings_and_transitive_exclusion_independently(
    tmp_path, encoding
):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={1: (b"safe source prose", 4)},
    )

    def edit(parts):
        forget(parts, 2)
        value = {"SourceId": identity(2), "Value": "private nested"}
        if encoding == "serialized_association_value":
            value["SourceId"] = json.dumps(identity(2))
        elif encoding == "case_association_value":
            # Replace the source identity too, so uppercase genuinely differs.
            omitted = "abcdef01-2345-6789-abcd-ef0123456789"
            for name in list(parts):
                parts[name] = parts[name].replace(
                    identity(2).encode(), omitted.encode()
                )
            value["SourceId"] = omitted.upper()
        if encoding in {"serialized", "twice_serialized"}:
            value = json.dumps(value)
            if encoding == "twice_serialized":
                value = json.dumps(value)
        elif encoding == "unicode_escaped":
            value = (
                '{"SourceId":"'
                + "".join(f"\\u{ord(c):04x}" for c in identity(2))
                + '","Value":"private nested"}'
            )
        elif encoding == "duplicate_keys":
            value = (
                '{"SourceId":"'
                + identity(2)
                + '","SourceId":"'
                + identity(1)
                + '","Value":"private nested"}'
            )
        parts["brainusers.json"] = b"\n".join(
            json.dumps(row).encode()
            for row in [
                {"Id": identity(8301), "Envelope": value, "Sibling": "private sibling"},
                {
                    "Id": identity(8302),
                    "Nested": {"AttachmentId": identity(8301)},
                    "Value": "private dependent",
                },
                {
                    "Id": identity(8303),
                    "Value": "safe independent record",
                    "Null": None,
                },
            ]
        )

    rewrite(source, edit)
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    assert check_vault(source, vault)["source_items"] == 1
    users = next(
        e["records"]
        for e in load_json((vault / "migration-record.json").read_bytes())[
            "original_evidence"
        ]
        if e["key"] == "brainusers.json"
    )
    assert users == [
        {"Id": identity(8303), "Value": "safe independent record", "Null": None}
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("SourceType", 1),
        ("SourceType", True),
        ("NoteType", 0),
        ("Type", 12),
        ("Location", "Other.md"),
        ("IsIcon", True),
        ("IsWallpaper", True),
        ("DataLength", -1),
    ],
)
def test_oracle_does_not_accept_near_miss_absent_declarations_with_forged_receipts(
    tmp_path, field, value
):
    source, vault, result, record = image_candidate(tmp_path)

    def edit(parts):
        from tests.application.test_absent_note_images_workflow import NOTE

        change_record(parts, NOTE, **{field: value})

    rewrite(source, edit)
    record["source_identity"]["source_sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError):
        check_vault(source, vault)


@pytest.mark.parametrize(
    "body",
    [b"", b"\xef\xbb\xbf", b" \r\n\t", b"![supplied](.data/md-images/card.png)\r\n"],
)
def test_supplied_empty_or_bom_body_never_gains_fallback_or_generated_credit(
    tmp_path, body
):
    parts = fallback_parts(tmp_path)
    from tests.application.test_absent_note_images_workflow import NOTE, OWNER

    parts[OWNER + "/Notes.md"] = body
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"][NOTE] = 1
    parts["meta.json"] = json.dumps(meta).encode()
    change_record(parts, NOTE, DataLength=len(body))
    source = write_source(tmp_path, parts)
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    summary = check_vault(source, vault)
    assert summary["source_gaps"] == summary["generated_embeds"] == 0
    assert summary["documents"] == summary["backups"] == 1


@pytest.mark.parametrize("damage", ["body", "embed_order", "diagnostic"])
def test_clean_source_free_conventions_do_not_certify_raw_source_preservation(
    tmp_path, damage
):
    from brz2obsidian.vault_check import check_vault as check_conventions

    source = mixed_v3_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault).model_dump(mode="json")
    check_vault(source, vault)
    record = load_json((vault / "migration-record.json").read_bytes())
    if damage == "body":
        home = vault / "Home — Home.md"
        home.write_bytes(home.read_bytes().replace(b"Home prose", b"False text"))
    elif damage == "embed_order":
        path = vault / "Notes/Image owner.md"
        first = b"![[Attachments/00000000000000000000000000000005/z-first.webp]]"
        last = b"![[Attachments/00000000000000000000000000000005/a-last.png]]"
        original = path.read_bytes()
        assert first + b"\n\n" + last in original
        path.write_bytes(
            original.replace(first + b"\n\n" + last, last + b"\n\n" + first)
        )
        for field in (
            record["generated_presentations"][0]["presentation"]["image_asset_ids"],
            record["generated_presentations"][0]["image_paths"],
        ):
            field.reverse()
    else:
        report = vault / "MIGRATION REPORT.md"
        original = report.read_bytes()
        assert b'"state": 3' in original
        report.write_bytes(original.replace(b'"state": 3', b'"state": 2', 1))
    rewrite_record(vault, record, result)
    assert check_conventions(vault).outcome == "clean"
    with pytest.raises(AssertionError):
        check_vault(source, vault)
