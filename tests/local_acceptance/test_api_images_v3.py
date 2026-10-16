"""Independent source-bound JPEG and finite ICO controls for issue 216."""

import hashlib
import json
import struct
from pathlib import Path

import pytest

from tests.local_acceptance.api_checker import (
    audit_baseline,
    check_api_vault,
    expected_asset,
)
from tests.local_acceptance.api_manifest import load_baseline
from tests.local_acceptance.test_api_acceptance import (
    fingerprint,
    identity,
    reseal,
    source_case,
    write_json,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "local_api_images_v3"


def image_case(tmp_path):
    baseline, vault = source_case(tmp_path)
    root = baseline.manifest_path.parent
    graph_path = root / baseline.data["graphs"][identity(2)]
    graph = baseline.json(baseline.data["graphs"][identity(2)])
    image = graph["attachments"][1]
    image["location"] = image["id"] + ".jpg"
    write_json(graph_path, graph)
    (root / "202.bin").write_bytes((FIXTURES / "inert-blue.jpg").read_bytes())
    return reseal(baseline), vault, image


def test_profile3_jpeg_owned_image_is_measured_without_rewriting_bytes(tmp_path):
    baseline, _, image = image_case(tmp_path)
    proofs = {}
    role, availability, raw = expected_asset(baseline, image, "3", proofs)
    assert (role, availability) == ("image", "present")
    assert raw == (FIXTURES / "inert-blue.jpg").read_bytes()
    assert proofs[image["id"]]["format"] == "JPEG"
    assert (proofs[image["id"]]["width"], proofs[image["id"]]["height"]) == (2, 1)


def test_profile3_ico_preserves_all_advertised_variants_as_icon(tmp_path):
    baseline, _, image = image_case(tmp_path)
    root = baseline.manifest_path.parent
    image.update(type=5, location="Icon.png")
    raw = (FIXTURES / "inert-b.ico").read_bytes()
    (root / "202.bin").write_bytes(raw)
    proofs = {}
    assert expected_asset(baseline, image, "3", proofs) == ("icon", "present", raw)
    assert proofs[image["id"]]["format"] == "ICO"
    assert [(f["width"], f["height"]) for f in proofs[image["id"]]["frames"]] == [
        (16, 16),
        (32, 32),
        (48, 48),
    ]


def put_payload(baseline, raw):
    (baseline.manifest_path.parent / "202.bin").write_bytes(raw)
    return reseal(baseline)


@pytest.mark.parametrize("filename", ["inert-a.ico", "inert-b.ico"])
def test_all_ico_variants_match_independent_preencoding_pixels_and_original_bytes(
    tmp_path, filename
):
    baseline, _, image = image_case(tmp_path)
    image.update(type=5, location="Icon.png")
    raw = (FIXTURES / filename).read_bytes()
    baseline = put_payload(baseline, raw)
    facts = next(
        p
        for p in json.loads((FIXTURES / "source-facts.json").read_bytes())["payloads"]
        if p["file"] == filename
    )
    proofs = {}
    assert expected_asset(baseline, image, "3", proofs) == ("icon", "present", raw)
    proof = proofs[image["id"]]
    assert proof["source_sha256"] == facts["sha256"]
    assert len(raw) == facts["length"]
    for measured, literal in zip(
        proof["frames"], facts["directory_order"], strict=True
    ):
        assert {
            k: measured[k]
            for k in (
                "width",
                "height",
                "body_length",
                "body_sha256",
                "offset",
                "mask_length",
                "extra_zero_tail_length",
                "rgba_sha256",
            )
        } == {
            k: literal[k]
            for k in (
                "width",
                "height",
                "body_length",
                "body_sha256",
                "offset",
                "mask_length",
                "extra_zero_tail_length",
                "rgba_sha256",
            )
        }


@pytest.mark.parametrize("profile", ["1", "2"])
@pytest.mark.parametrize(
    "filename,kind,location",
    [
        ("inert-a.ico", 5, "Icon.png"),
        ("inert-b.ico", 5, "Icon.png"),
        ("inert-blue.jpg", 12, identity(202) + ".jpg"),
    ],
)
def test_new_image_forms_refuse_both_older_profiles(
    tmp_path, profile, filename, kind, location
):
    baseline, _, image = image_case(tmp_path)
    image.update(type=kind, location=location)
    baseline = put_payload(baseline, (FIXTURES / filename).read_bytes())
    with pytest.raises(AssertionError):
        expected_asset(baseline, image, profile)


@pytest.mark.parametrize(
    "filename,index",
    [
        ("inert-a.ico", 0),
        ("inert-a.ico", 1),
        ("inert-b.ico", 0),
        ("inert-b.ico", 1),
        ("inert-b.ico", 2),
    ],
)
@pytest.mark.parametrize(
    "field",
    [
        "width",
        "height",
        "colours",
        "reserved",
        "planes",
        "bits",
        "size",
        "offset",
        "dib_size",
        "dib_width",
        "dib_height",
        "top_down",
        "dib_planes",
        "dib_bits",
        "compression",
        "image_size",
        "x_density",
        "y_density",
        "colours_used",
        "colours_important",
        "short_colour",
        "short_mask",
        "extra_byte",
        "tail_minus",
        "tail_plus",
    ],
)
def test_each_advertised_ico_entry_and_dib_field_is_finite(
    tmp_path, filename, index, field
):
    baseline, _, image = image_case(tmp_path)
    image.update(type=5, location="Icon.png")
    raw = bytearray((FIXTURES / filename).read_bytes())
    entry = 6 + 16 * index
    length, offset = struct.unpack_from("<II", raw, entry + 8)
    entry_fields = {
        "width": (0, "B", 0),
        "height": (1, "B", 0),
        "colours": (2, "B", 1),
        "reserved": (3, "B", 1),
        "planes": (4, "H", 2),
        "bits": (6, "H", 24),
        "size": (8, "I", length - 1),
        "offset": (12, "I", offset + 1),
    }
    dib_fields = {
        "dib_size": (0, "I", 41),
        "dib_width": (4, "i", 1),
        "dib_height": (8, "i", 1),
        "top_down": (8, "i", -2 * raw[entry]),
        "dib_planes": (12, "H", 2),
        "dib_bits": (14, "H", 24),
        "compression": (16, "I", 1),
        "image_size": (20, "I", 1),
        "x_density": (24, "i", 1),
        "y_density": (28, "i", 1),
        "colours_used": (32, "I", 1),
        "colours_important": (36, "I", 1),
    }
    if field in entry_fields or field in dib_fields:
        delta, fmt, value = (entry_fields if field in entry_fields else dib_fields)[
            field
        ]
        struct.pack_into(
            "<" + fmt, raw, (entry if field in entry_fields else offset) + delta, value
        )
    elif field in {"short_colour", "short_mask", "tail_minus"}:
        position = offset + 40 if field == "short_colour" else offset + length - 1
        del raw[position]
    else:
        raw.insert(offset + length, 0)
    baseline = put_payload(baseline, raw)
    with pytest.raises(AssertionError):
        expected_asset(baseline, image, "3")


@pytest.mark.parametrize(
    "damage",
    [
        "reserved",
        "cur",
        "count",
        "order",
        "duplicate",
        "gap",
        "overlap",
        "body_permutation",
        "trailer",
        "png_body",
        "nonzero_mask32",
        "nonzero_mask48",
        "nonzero_tail32",
        "nonzero_tail48",
    ],
)
def test_rehashed_fresh_ico_container_near_misses_refuse(tmp_path, damage):
    baseline, _, image = image_case(tmp_path)
    image.update(type=5, location="Icon.png")
    raw = bytearray((FIXTURES / "inert-b.ico").read_bytes())
    if damage in {"reserved", "cur", "count"}:
        struct.pack_into(
            "<H",
            raw,
            {"reserved": 0, "cur": 2, "count": 4}[damage],
            {"reserved": 1, "cur": 2, "count": 1}[damage],
        )
    elif damage == "order":
        raw[6:22], raw[22:38] = raw[22:38], raw[6:22]
    elif damage == "duplicate":
        raw[22:38] = raw[6:22]
    elif damage in {"gap", "overlap"}:
        struct.pack_into("<I", raw, 34, 1183 if damage == "gap" else 1181)
    elif damage == "body_permutation":
        raw[54:1182], raw[1182:5574] = raw[1182:5574], raw[54:1182]
    elif damage == "trailer":
        raw += b"\x00"
    elif damage == "png_body":
        raw[54:62] = b"\x89PNG\r\n\x1a\n"
    else:
        raw[
            {
                "nonzero_mask32": 5318,
                "nonzero_tail32": 5446,
                "nonzero_mask48": 14830,
                "nonzero_tail48": 15214,
            }[damage]
        ] = 1
    baseline = put_payload(baseline, raw)
    with pytest.raises(AssertionError):
        expected_asset(baseline, image, "3")


@pytest.mark.parametrize(
    "damage", ["signature", "truncated", "no_eoi", "header_only", "png"]
)
def test_jpeg_requires_complete_actual_jpeg_decode(tmp_path, damage):
    baseline, _, image = image_case(tmp_path)
    raw = (FIXTURES / "inert-blue.jpg").read_bytes()
    damaged = {
        "signature": b"bad" + raw[3:],
        "truncated": raw[:320],
        "no_eoi": raw[:-2],
        "header_only": raw[:20] + b"\xff\xd9",
        "png": b"\x89PNG\r\n\x1a\n",
    }[damage]
    baseline = put_payload(baseline, damaged)
    with pytest.raises(AssertionError):
        expected_asset(baseline, image, "3")


@pytest.mark.parametrize(
    "field,value",
    [
        ("sourceType", True),
        ("sourceType", 1),
        ("sourceType", 2.0),
        ("brainId", identity(99)),
        ("sourceId", identity(99)),
        ("sourceId", identity(1).upper()),
        ("isNotes", 0),
        ("isNotes", None),
        ("isNotes", True),
        ("name", ""),
        ("name", "Blue"),
        ("location", identity(202) + ".jpeg"),
        ("location", identity(202) + ".JPG"),
        ("location", identity(203) + ".jpg"),
        ("type", 1),
        ("type", 5),
    ],
)
def test_jpeg_declaration_factors_refuse_independently(tmp_path, field, value):
    baseline, _, image = image_case(tmp_path)
    image[field] = value
    with pytest.raises(AssertionError):
        expected_asset(baseline, image, "3")


def bound_case(tmp_path):
    """Raw API facts and an independently authored vault, with no converter call."""
    baseline, vault, image = image_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    graphs = {key: baseline.json(path) for key, path in manifest["graphs"].items()}
    new = []
    for key, owner, kind, location, file in [
        (205, 3, 12, identity(205) + ".jpg", "inert-blue.jpg"),
        (206, 2, 5, "Icon.png", "inert-a.ico"),
        (207, 4, 5, "Icon.png", "inert-b.ico"),
    ]:
        row = image | {
            "id": identity(key),
            "sourceId": identity(owner),
            "type": kind,
            "location": location,
        }
        graphs[identity(owner)]["attachments"].append(row)
        new.append(row)
        name = str(key) + ".bin"
        (root / name).write_bytes((FIXTURES / file).read_bytes())
        manifest["files"][name] = fingerprint(root / name)
        manifest["payloads"][identity(key)] = {"status": 200, "path": name}
        manifest["scope"]["attachment_ids"].append(identity(key))
    authored = (
        "Préface 🐈\n\n![bleu](.data/md-images/"
        + identity(202)
        + '.jpg "Titre")\n\n![deux](.data/md-images/'
        + identity(202)
        + ".jpg#$width=75p$)\n"
    )
    (root / "201.bin").write_bytes(authored.encode())
    manifest["attachment_metadata"] = {}
    manifest["attachment_inventories"] = {}
    for owner, graph in graphs.items():
        write_json(root / manifest["graphs"][owner], graph)
        path = owner + "-attachments.json"
        write_json(root / path, graph["attachments"])
        manifest["files"][path] = fingerprint(root / path)
        manifest["attachment_inventories"][owner] = path
        for row in graph["attachments"]:
            path = row["id"] + "-metadata.json"
            write_json(root / path, row)
            manifest["files"][path] = fingerprint(root / path)
            manifest["attachment_metadata"][row["id"]] = {"status": 200, "path": path}
    # Child now owns an unreferenced image, so its no-note wrapper stays required.
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["profile_version"] = "3"
    all_rows = [row for graph in graphs.values() for row in graph["attachments"]]
    record["original_evidence"][0]["records"] = (
        [
            row
            for row in record["original_evidence"][0]["records"]
            if row["id"] != identity(202)
        ]
        + [image]
        + new
    )
    for row in all_rows:
        key = row["id"]
        outcome = manifest["payloads"][key]
        if outcome["status"] != 200:
            continue
        raw = baseline.bytes(outcome["path"])
        relative = (
            "Assets/" + row["sourceId"] + "/" + row["location"]
            if row["type"] in {5, 12}
            else key + ".bin"
        )
        (vault / relative).parent.mkdir(parents=True, exist_ok=True)
        (vault / relative).write_bytes(raw)
        target = next(
            (a for a in record["asset_targets"] if a["asset_id"] == key), None
        )
        if target is None:
            target = {"asset_id": key}
            record["asset_targets"].append(target)
        target.update(
            owner=row["sourceId"],
            role="note_original"
            if row["isNotes"]
            else "image"
            if row["type"] == 12
            else "icon"
            if row["type"] == 5
            else "file",
            availability="present",
            relative_path=relative,
            original_name=row["location"],
            display_name=None,
            actual_length=len(raw),
            actual_sha256=hashlib.sha256(raw).hexdigest(),
        )
    for target in record["item_targets"]:
        key = target["item_key"]
        created = key != identity(5)
        icon = (
            identity(206)
            if key == identity(2)
            else identity(207)
            if key == identity(4)
            else None
        )
        provider = identity(4) if key == identity(3) else None
        target.update(
            relative_path={
                identity(2): "Home.md",
                identity(3): "Child.md",
                identity(4): "Type.md",
                identity(5): "Tag.md",
            }[key],
            created=created,
            declared_appearance={
                "icon_asset_id": icon,
                "foreground_color": None,
                "background_color": None,
            }
            if icon
            else None,
            icon_snapshot={
                "item_key": key,
                "explicit_icon_asset_id": icon,
                "appearance_category_key": provider,
                "effective_icon_asset_id": icon
                or (identity(207) if provider else None),
            }
            if created
            else None,
        )
    digest = hashlib.sha256(authored.encode()).hexdigest()
    references = []
    for label, url in [
        ("bleu", ".data/md-images/" + identity(202) + ".jpg"),
        ("deux", ".data/md-images/" + identity(202) + ".jpg#$width=75p$"),
    ]:
        start = authored.index("![" + label + "]")
        end = authored.index(")", start) + 1
        dest = authored.index(url, start)
        norm = None
        if "#" in url:
            begin = dest + url.index("#")
            norm = {
                "declaration": "#$width=75p$",
                "start": begin,
                "end": dest + len(url),
                "document_digest": digest,
                "basis": "document.text/unicode_codepoints",
                "presentation": "responsive",
            }
        references.append(
            {
                "start": start,
                "end": end,
                "expected_original": authored[start:end],
                "kind": "image",
                "target": identity(202),
                "display_text": label,
                "document_digest": digest,
                "source_target": url,
                "destination_start": dest,
                "destination_end": dest + len(url),
                "presentation_normalization": norm,
            }
        )
    record["documents"] = [
        {
            "key": identity(201),
            "owner": identity(2),
            "original_asset_id": identity(201),
            "text_digest": digest,
            "owner_target": "Home.md",
            "references": references,
        }
    ]
    (vault / "Home.md").write_text(
        "# Home\n\nPréface 🐈\n\n![bleu]("
        + "Assets/"
        + identity(2)
        + "/"
        + identity(202)
        + '.jpg "Titre")\n\n![deux]('
        + "Assets/"
        + identity(2)
        + "/"
        + identity(202)
        + ".jpg)\n",
        encoding="utf-8",
    )
    (vault / "Child.md").write_text("# Child\n", encoding="utf-8")
    (vault / "Type.md").write_text("# Type\n", encoding="utf-8")
    write_json(record_path, record)
    return baseline, vault


def test_bound_image_baseline_and_every_payload_pass_full_audit(tmp_path):
    baseline, vault = bound_case(tmp_path)
    assert audit_baseline(baseline, profile_version="3")["payloads"] == 6
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6


@pytest.mark.parametrize(
    "damage",
    [
        "metadata_missing",
        "metadata_404",
        "metadata_owner",
        "list_missing",
        "list_conflict",
        "duplicate_icon",
        "private_owner",
        "forgotten_owner",
        "system_owner",
    ],
)
def test_fresh_image_baseline_requires_owner_and_all_authoritative_joins(
    tmp_path, damage
):
    baseline, vault = bound_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    if damage == "metadata_missing":
        del manifest["attachment_metadata"][identity(202)]
    elif damage == "metadata_404":
        manifest["attachment_metadata"][identity(202)]["status"] = 404
    elif damage == "metadata_owner":
        path = root / manifest["attachment_metadata"][identity(202)]["path"]
        row = json.loads(path.read_bytes())
        row["sourceId"] = identity(3)
        write_json(path, row)
    elif damage == "list_missing":
        del manifest["attachment_inventories"][identity(2)]
    elif damage == "list_conflict":
        path = root / manifest["attachment_inventories"][identity(2)]
        rows = json.loads(path.read_bytes())
        rows.pop()
        write_json(path, rows)
    else:
        path = root / manifest["graphs"][identity(2)]
        graph = json.loads(path.read_bytes())
        if damage == "duplicate_icon":
            graph["attachments"].append(
                graph["attachments"][-1] | {"id": identity(999)}
            )
            manifest["scope"]["attachment_ids"].append(identity(999))
            manifest["payloads"][identity(999)] = manifest["payloads"][identity(206)]
        elif damage == "private_owner":
            graph["activeThought"]["acType"] = 1
        elif damage == "forgotten_owner":
            graph["activeThought"]["forgottenDateTime"] = "2026-01-01T00:00:00"
        else:
            graph["activeThought"]["kind"] = 5
        write_json(path, graph)
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    with pytest.raises(AssertionError):
        audit_baseline(baseline, profile_version="3")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "damage",
    [
        "omitted_asset",
        "bytes",
        "role",
        "owner",
        "name",
        "length",
        "sha",
        "omitted_document",
        "reference_target",
        "reference_order",
        "span",
        "alt",
        "sizing",
        "generated_alt",
        "generated_title",
        "generated_order",
        "declared_icon",
        "inherited_icon",
        "unreferenced_owner",
    ],
)
def test_source_bound_image_vault_rejects_independent_loss_controls(tmp_path, damage):
    baseline, vault = bound_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == identity(205))
    if damage == "omitted_asset":
        record["asset_targets"].remove(asset)
    elif damage == "bytes":
        (vault / asset["relative_path"]).write_bytes(b"corrupt")
    elif damage in {"role", "owner", "name", "length", "sha"}:
        asset[
            {
                "role": "role",
                "owner": "owner",
                "name": "original_name",
                "length": "actual_length",
                "sha": "actual_sha256",
            }[damage]
        ] = {
            "role": "icon",
            "owner": identity(2),
            "name": "x.jpg",
            "length": 0,
            "sha": "0" * 64,
        }[damage]
    elif damage == "omitted_document":
        record["documents"] = []
    elif damage.startswith("generated_"):
        note = (vault / "Home.md").read_text(encoding="utf-8")
        if damage == "generated_alt":
            note = note.replace("bleu", "wrong")
        elif damage == "generated_title":
            note = note.replace("Titre", "wrong")
        else:
            note = note.replace("![bleu]", "![deux]", 1)
        (vault / "Home.md").write_text(note, encoding="utf-8")
    elif damage in {"declared_icon", "inherited_icon", "unreferenced_owner"}:
        target = next(
            t
            for t in record["item_targets"]
            if t["item_key"] == identity(2 if damage == "declared_icon" else 3)
        )
        if damage == "declared_icon":
            target["declared_appearance"]["icon_asset_id"] = identity(207)
        elif damage == "inherited_icon":
            target["icon_snapshot"]["effective_icon_asset_id"] = identity(206)
        else:
            target["created"] = False
    else:
        references = record["documents"][0]["references"]
        if damage == "reference_order":
            references.reverse()
        else:
            references[0][
                {
                    "reference_target": "target",
                    "span": "start",
                    "alt": "display_text",
                    "sizing": "presentation_normalization",
                }[damage]
            ] = {
                "reference_target": identity(205),
                "span": 0,
                "alt": "wrong",
                "sizing": references[1]["presentation_normalization"],
            }[damage]
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("damage", ["failure", "dimensions", "classification"])
def test_nondefault_variant_cannot_hide_failed_or_mismatched_native_decode(
    tmp_path, monkeypatch, damage
):
    from tests.local_acceptance import api_image_proofs

    baseline, _, image = image_case(tmp_path)
    image.update(type=5, location="Icon.png")
    baseline = put_payload(baseline, (FIXTURES / "inert-b.ico").read_bytes())
    actual = api_image_proofs.decode_ico_variant

    def decoder(raw):
        proof = actual(raw)
        if proof["width"] == 16:
            if damage == "failure":
                raise AssertionError("synthetic codec failed")
            proof["width" if damage == "dimensions" else "format"] = (
                48 if damage == "dimensions" else "PNG"
            )
        return proof

    monkeypatch.setattr(api_image_proofs, "decode_ico_variant", decoder)
    with pytest.raises(AssertionError):
        expected_asset(baseline, image, "3")


@pytest.mark.parametrize("key", [202, 205, 206, 207])
def test_trusted_source_pin_rejects_even_equal_length_nondefault_or_unreferenced_changes(
    tmp_path, key
):
    baseline, vault = bound_case(tmp_path)
    path = (
        baseline.manifest_path.parent / baseline.data["payloads"][identity(key)]["path"]
    )
    raw = bytearray(path.read_bytes())
    raw[4400 if key == 206 else 1200 if key == 207 else 300] ^= 1
    path.write_bytes(raw)
    with pytest.raises(AssertionError, match="baseline evidence changed"):
        audit_baseline(baseline, profile_version="3")
    with pytest.raises(AssertionError, match="baseline evidence changed"):
        check_api_vault(baseline, vault, profile_version="3")


def test_valid_changed_nondefault_pixels_have_a_new_pin_and_cannot_pass_original_vault(
    tmp_path,
):
    baseline, vault = bound_case(tmp_path)
    original_pin = baseline.fingerprint
    path = baseline.manifest_path.parent / "206.bin"
    raw = bytearray(path.read_bytes())
    raw[4350] ^= 1
    path.write_bytes(raw)
    changed = reseal(baseline)
    assert changed.fingerprint != original_pin
    with pytest.raises(AssertionError, match="baseline manifest changed"):
        load_baseline(changed.manifest_path, original_pin)
    assert (
        audit_baseline(changed, profile_version="3")["resource_eligibility"][
            identity(206)
        ]["source_sha256"]
        != "b44733332d8c307dabc7b11be5164d567f11f962a7b18c6b94df57be28378613"
    )
    with pytest.raises(AssertionError, match="required payload bytes"):
        check_api_vault(changed, vault, profile_version="3")


@pytest.mark.parametrize("filename", ["inert-a.ico", "inert-b.ico"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("sourceType", 1),
        ("sourceType", True),
        ("type", 1),
        ("type", 12),
        ("isNotes", True),
        ("isNotes", 0),
        ("name", "Icon.png"),
        ("name", ""),
        ("location", "icon.png"),
        ("location", "Icon.ico"),
        ("sourceId", identity(99)),
        ("brainId", identity(99)),
    ],
)
def test_ico_declaration_is_exact_and_never_a_generic_file_or_note_image(
    tmp_path, filename, field, value
):
    baseline, _, image = image_case(tmp_path)
    image.update(type=5, location="Icon.png")
    image[field] = value
    baseline = put_payload(baseline, (FIXTURES / filename).read_bytes())
    with pytest.raises(AssertionError):
        expected_asset(baseline, image, "3")


@pytest.mark.parametrize("profile", ["2", "3"])
def test_existing_jpeg_under_png_icon_name_keeps_icon_role(tmp_path, profile):
    baseline, _, image = image_case(tmp_path)
    image.update(type=5, location="Icon.png")
    role, availability, raw = expected_asset(baseline, image, profile)
    assert (role, availability) == ("icon", "present")
    assert (
        hashlib.sha256(raw).hexdigest()
        == "e3a2954fee014acf9f0b399791f49458604d6592ab22844bcebecc0e666be5ed"
    )


@pytest.mark.parametrize(
    "key,mutation",
    [
        (202, "jpeg"),
        (205, "jpeg"),
        (206, "scalar"),
        (206, "nondefault"),
        (207, "mask"),
        (207, "tail"),
    ],
)
def test_fresh_rehashed_invalid_payloads_refuse_all_full_audit_boundaries(
    tmp_path, key, mutation
):
    baseline, vault = bound_case(tmp_path)
    path = baseline.manifest_path.parent / f"{key}.bin"
    raw = bytearray(path.read_bytes())
    if mutation == "jpeg":
        raw = raw[:320]
    elif mutation == "scalar":
        struct.pack_into("<I", raw, 38, 41)
    elif mutation == "nondefault":
        struct.pack_into("<i", raw, 4302 + 8, -32)
    elif mutation == "mask":
        raw[14830] = 1
    else:
        raw[15214] = 1
    path.write_bytes(raw)
    baseline = reseal(baseline)
    with pytest.raises(AssertionError):
        audit_baseline(baseline, profile_version="3")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


def test_valid_changed_pixels_and_fresh_output_accept_with_the_new_source_identity(
    tmp_path,
):
    baseline, vault = bound_case(tmp_path)
    path = baseline.manifest_path.parent / "206.bin"
    raw = bytearray(path.read_bytes())
    raw[4350] ^= 1
    path.write_bytes(raw)
    changed = reseal(baseline)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == identity(206))
    (vault / asset["relative_path"]).write_bytes(raw)
    asset["actual_sha256"] = hashlib.sha256(raw).hexdigest()
    write_json(record_path, record)
    assert check_api_vault(changed, vault, profile_version="3")["payloads"] == 6


@pytest.mark.parametrize("filename", ["inert-a.ico", "inert-b.ico"])
def test_allowed_16px_mask_is_preserved_without_a_zero_mask_rule(tmp_path, filename):
    baseline, _, image = image_case(tmp_path)
    image.update(type=5, location="Icon.png")
    raw = bytearray((FIXTURES / filename).read_bytes())
    offset = 4302 if filename == "inert-a.ico" else 54
    raw[offset + 40 + 4 * 16 * 16 + 3] = 255
    baseline = put_payload(baseline, raw)
    assert expected_asset(baseline, image, "3")[2] == raw


def add_empty_owner(baseline, vault, role):
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    owner, key = identity(6), identity(208)
    thought = {
        "id": owner,
        "brainId": identity(1),
        "kind": 1,
        "acType": 0,
        "forgottenDateTime": None,
        "name": "Empty",
        "typeId": None,
    }
    attachment = {
        "id": key,
        "brainId": identity(1),
        "sourceId": owner,
        "sourceType": 2,
        "type": 5 if role == "icon" else 12,
        "isNotes": False,
        "name": None,
        "location": "Icon.png" if role == "icon" else key + ".jpg",
    }
    graph = {
        "activeThought": thought,
        "attachments": [attachment],
        "links": [],
        "children": [],
        "parents": [],
        "jumps": [],
        "tags": [],
        "type": None,
    }

    def evidence(name, value):
        write_json(root / name, value)
        manifest["files"][name] = fingerprint(root / name)
        return name

    manifest["graphs"][owner] = evidence("empty-graph.json", graph)
    manifest["attachment_inventories"][owner] = evidence(
        "empty-inventory.json", [attachment]
    )
    manifest["attachment_metadata"][key] = {
        "status": 200,
        "path": evidence("empty-metadata.json", attachment),
    }
    manifest["no_notes"][owner] = evidence(
        "empty-note.json",
        {
            "brainId": identity(1),
            "sourceId": owner,
            "sourceType": 2,
            "markdown": "",
            "html": None,
            "text": None,
            "modificationDateTime": "0001-01-01T00:00:00",
        },
    )
    manifest["scope"]["thought_ids"].append(owner)
    manifest["scope"]["attachment_ids"].append(key)
    for path in manifest["statistics"]:
        stats = json.loads((root / path).read_bytes())
        stats["thoughts"] += 1
        write_json(root / path, stats)
    raw = (
        FIXTURES / ("inert-a.ico" if role == "icon" else "inert-blue.jpg")
    ).read_bytes()
    (root / "208.bin").write_bytes(raw)
    manifest["files"]["208.bin"] = fingerprint(root / "208.bin")
    manifest["payloads"][key] = {"status": 200, "path": "208.bin"}
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["original_evidence"][0]["records"] += [thought, attachment]
    record["asset_targets"].append(
        {
            "asset_id": key,
            "owner": owner,
            "role": role,
            "availability": "present",
            "relative_path": "Assets/" + owner + "/" + attachment["location"],
            "original_name": attachment["location"],
            "display_name": None,
            "actual_length": len(raw),
            "actual_sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
    relative = "Assets/" + owner + "/" + attachment["location"]
    (vault / relative).parent.mkdir(parents=True, exist_ok=True)
    (vault / relative).write_bytes(raw)
    record["item_targets"].append(
        {
            "item_key": owner,
            "original_identity": owner,
            "original_title": "Empty",
            "relative_path": "Empty.md",
            "created": role == "image",
            "declared_appearance": {
                "icon_asset_id": key,
                "foreground_color": None,
                "background_color": None,
            }
            if role == "icon"
            else None,
            "icon_snapshot": {
                "item_key": owner,
                "explicit_icon_asset_id": None,
                "appearance_category_key": None,
                "effective_icon_asset_id": None,
            }
            if role == "image"
            else None,
        }
    )
    if role == "image":
        (vault / "Empty.md").write_text("# Empty\n", encoding="utf-8")
    write_json(path, record)
    return baseline


@pytest.mark.parametrize("role", ["icon", "image"])
def test_icon_only_owner_stays_uncreated_and_unreferenced_jpeg_materializes_owner(
    tmp_path, role
):
    baseline, vault = bound_case(tmp_path)
    baseline = add_empty_owner(baseline, vault, role)
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 7
    assert (vault / "Empty.md").exists() == (role == "image")
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["item_targets"][-1]["created"] = role != "image"
    if role == "icon":
        record["item_targets"][-1]["icon_snapshot"] = {
            "item_key": identity(6),
            "explicit_icon_asset_id": identity(208),
            "appearance_category_key": None,
            "effective_icon_asset_id": identity(208),
        }
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("key", [202, 205, 206, 207])
@pytest.mark.parametrize("damage", ["omitted", "bytes"])
def test_every_new_owned_image_and_icon_is_audited_even_when_unreferenced(
    tmp_path, key, damage
):
    baseline, vault = bound_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == identity(key))
    if damage == "omitted":
        record["asset_targets"].remove(asset)
        write_json(path, record)
    else:
        (vault / asset["relative_path"]).write_bytes(b"corrupt")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


def test_direct_ico_takes_precedence_over_distinct_type_ico(tmp_path):
    baseline, vault = bound_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    path = root / manifest["graphs"][identity(3)]
    graph = json.loads(path.read_bytes())
    row = {
        "id": identity(209),
        "brainId": identity(1),
        "sourceId": identity(3),
        "sourceType": 2,
        "type": 5,
        "isNotes": False,
        "location": "Icon.png",
        "name": None,
    }
    graph["attachments"].append(row)
    write_json(path, graph)
    write_json(
        root / manifest["attachment_inventories"][identity(3)], graph["attachments"]
    )
    write_json(root / "209-metadata.json", row)
    manifest["files"]["209-metadata.json"] = fingerprint(root / "209-metadata.json")
    manifest["attachment_metadata"][identity(209)] = {
        "status": 200,
        "path": "209-metadata.json",
    }
    manifest["scope"]["attachment_ids"].append(identity(209))
    manifest["payloads"][identity(209)] = manifest["payloads"][identity(206)]
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["original_evidence"][0]["records"].append(row)
    direct = next(a for a in record["asset_targets"] if a["asset_id"] == identity(206))
    record["asset_targets"].append(
        direct
        | {
            "asset_id": identity(209),
            "owner": identity(3),
            "relative_path": "Assets/" + identity(3) + "/Icon.png",
        }
    )
    copied = vault / ("Assets/" + identity(3) + "/Icon.png")
    copied.parent.mkdir(parents=True, exist_ok=True)
    copied.write_bytes((FIXTURES / "inert-a.ico").read_bytes())
    child = next(t for t in record["item_targets"] if t["item_key"] == identity(3))
    child["declared_appearance"] = {
        "icon_asset_id": identity(209),
        "foreground_color": None,
        "background_color": None,
    }
    child["icon_snapshot"].update(
        explicit_icon_asset_id=identity(209), effective_icon_asset_id=identity(209)
    )
    write_json(path, record)
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 7
    child["icon_snapshot"]["effective_icon_asset_id"] = identity(207)
    write_json(path, record)
    with pytest.raises(AssertionError, match="effective explicit/inherited icon"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("key", [202, 205, 206, 207])
def test_new_family_actual_payload_name_cannot_be_relabelled(tmp_path, key):
    baseline, vault = bound_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == identity(key))
    old = vault / asset["relative_path"]
    renamed = old.with_suffix(".bin")
    old.rename(renamed)
    asset["relative_path"] = renamed.relative_to(vault).as_posix()
    if key == 202:
        note = (vault / "Home.md").read_text(encoding="utf-8")
        (vault / "Home.md").write_text(
            note.replace(identity(202) + ".jpg", identity(202) + ".bin"),
            encoding="utf-8",
        )
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


def test_jpeg_missing_required_segments_is_invalid_even_without_native_codec(
    tmp_path, monkeypatch
):
    from tests.local_acceptance import api_checker
    from tests.local_acceptance.images import AuditUnavailable

    baseline, _, image = image_case(tmp_path)
    raw = (FIXTURES / "inert-blue.jpg").read_bytes()[:20] + b"\xff\xd9"
    baseline = put_payload(baseline, raw)

    def unavailable(*args):
        raise AuditUnavailable("synthetic native codec unavailable")

    monkeypatch.setattr(api_checker, "decode_image", unavailable)
    with pytest.raises(AssertionError, match="JPEG required image/scan segments"):
        expected_asset(baseline, image, "3")


@pytest.mark.parametrize("container", ["comment", "fence"])
def test_expected_image_prose_hidden_in_inactive_text_cannot_prove_display(
    tmp_path, container
):
    baseline, vault = bound_case(tmp_path)
    path = vault / "Home.md"
    note = path.read_text(encoding="utf-8")
    hidden = (
        ("<!--\n" + note + "\n-->\n")
        if container == "comment"
        else ("```\n" + note + "\n```\n")
    )
    path.write_text(note.replace("bleu", "wrong") + hidden, encoding="utf-8")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


def test_image_metadata_joins_keep_exact_fractional_source_positions(tmp_path):
    baseline, vault = bound_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = baseline.data
    paths = [
        manifest["graphs"][identity(2)],
        manifest["attachment_inventories"][identity(2)],
        manifest["attachment_metadata"][identity(202)]["path"],
    ]
    for index, name in enumerate(paths):
        path = root / name
        value = json.loads(path.read_bytes())
        rows = value["attachments"] if index == 0 else value if index == 1 else [value]
        next(row for row in rows if row["id"] == identity(202))["position"] = 1.25
        write_json(path, value)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    next(
        row
        for row in record["original_evidence"][0]["records"]
        if row["id"] == identity(202)
    )["position"] = {"decimal": "1.25"}
    write_json(path, record)
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6
