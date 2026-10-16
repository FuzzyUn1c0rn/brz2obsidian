"""Independent source-bound JPEG and finite ICO controls for issue 216."""

import hashlib
import json
import os
import struct
from difflib import SequenceMatcher
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
        struct.pack_into("<I", raw, entry + 8, length - 1)
        for following in range(index + 1, struct.unpack_from("<H", raw, 4)[0]):
            start = 6 + 16 * following + 12
            struct.pack_into(
                "<I", raw, start, struct.unpack_from("<I", raw, start)[0] - 1
            )
    else:
        raw.insert(offset + length, 0)
        struct.pack_into("<I", raw, entry + 8, length + 1)
        for following in range(index + 1, struct.unpack_from("<H", raw, 4)[0]):
            start = 6 + 16 * following + 12
            struct.pack_into(
                "<I", raw, start, struct.unpack_from("<I", raw, start)[0] + 1
            )
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


def image_note_prefix(name, explicit_owner=None, provider=None, effective_owner=None):
    """Literal presentation contract, independent of the checker predicate."""
    icon = (
        'icon: "[[Assets/' + identity(explicit_owner) + '/Icon.png]]"'
        if explicit_owner
        else "icon:"
    )
    category = (
        'appearance_category: "[[Type.md]]"' if provider else "appearance_category:"
    )
    result = "---\n" + icon + "\n" + category + "\n---\n\n# " + name + "\n\n"
    if effective_owner is not None:
        result += "![[Assets/" + identity(effective_owner) + "/Icon.png]]\n\n"
    return result


def first_document(record):
    return next(t for t in record["item_targets"] if t["item_key"] == identity(2))[
        "documents"
    ][0]


def image_source_case(tmp_path, scenario="basic"):
    """Return raw independently authored API observations, never output expectations."""
    baseline, _, image = image_case(tmp_path)
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
    assert scenario in {"basic", "adapted"}, "literal source scenario"
    if scenario == "adapted":
        authored = (
            "Préface 🐈 <Enter>.\r\n\r\n"
            '|Item|Image|:(table="column-widths:-1,0,84;justification:default"):\r\n'
            "|[Child](brain://AAAAAAAAAECAAAAAAAAAAw/title)|![bleu](.data/md-images/"
            + identity(202)
            + '.jpg#$width=75p$ "Titre")|\r\n\r\n'
            + "> [!tip|icon:🐈]\r\n> ![deux](.data/md-images/"
            + identity(202)
            + ".jpg)\r\n"
        )
    (root / "201.bin").write_bytes(authored.encode())
    # Explicit inert wire observations; no provider or normalizer supplies defaults.
    thought_rows = {
        key: graph["activeThought"]
        | {
            "creationDateTime": "2024-01-02T03:04:05Z",
            "modificationDateTime": "2024-02-03T04:05:06Z",
            "foregroundColor": None,
            "backgroundColor": None,
        }
        for key, graph in graphs.items()
    }
    link_rows = {
        row["id"]: row
        | {
            "name": None,
            "color": None,
            "thickness": 1,
            "creationDateTime": "2024-01-02T03:04:05Z",
            "modificationDateTime": "2024-02-03T04:05:06Z",
        }
        for graph in graphs.values()
        for row in graph["links"]
    }
    attachment_rows = {
        row["id"]: row | {"position": 0}
        for graph in graphs.values()
        for row in graph["attachments"]
    }

    def canonical(value):
        if isinstance(value, list):
            return [canonical(v) for v in value]
        if isinstance(value, dict):
            key = value.get("id")
            if key in thought_rows:
                return thought_rows[key]
            if key in link_rows:
                return link_rows[key]
            if key in attachment_rows:
                return attachment_rows[key]
            return {k: canonical(v) for k, v in value.items()}
        return value

    graphs = {key: canonical(graph) | {"siblings": []} for key, graph in graphs.items()}
    write_json(root / manifest["types"], canonical(baseline.json(manifest["types"])))
    write_json(
        root / manifest["tags"]["path"],
        canonical(baseline.json(manifest["tags"]["path"])),
    )
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

    def source_file(name, value):
        write_json(root / name, value)
        manifest["files"][name] = fingerprint(root / name)
        return name

    manifest["accessible_brains"] = source_file(
        "accessible-brains.json", [baseline.json(manifest["brain"])]
    )
    manifest["search"] = source_file(
        "search.json",
        [
            {
                "brainId": identity(1),
                "isFromOtherBrain": False,
                "sourceThought": {"id": key, "brainId": identity(1), "kind": 0},
                "sourceLink": None,
            }
            for key in sorted(thought_rows)
        ],
    )
    manifest["search_query"] = {
        "queryText": "*",
        "maxResults": "5000",
        "onlySearchThoughtNames": "false",
    }
    manifest["graph_query"] = {"includeSiblings": "true"}
    manifest["authoritative_thoughts"] = {
        key: source_file(key + "-thought.json", row)
        for key, row in thought_rows.items()
    }
    manifest["authoritative_links"] = {
        key: source_file(key + "-link.json", row) for key, row in link_rows.items()
    }
    brain = identity(1)
    http = {
        "/api/brains": {"status": 200, "path": manifest["accessible_brains"]},
        "/api/brains/" + brain: {"status": 200, "path": manifest["brain"]},
        "/api/brains/" + brain + "/statistics": [
            {"status": 200, "path": path} for path in manifest["statistics"]
        ],
        "/api/search/" + brain: {"status": 200, "path": manifest["search"]},
        "/api/thoughts/" + brain + "/types": {"status": 200, "path": manifest["types"]},
        "/api/thoughts/" + brain + "/tags": manifest["tags"],
    }
    for key in thought_rows:
        http["/api/thoughts/" + brain + "/" + key] = {
            "status": 200,
            "path": manifest["authoritative_thoughts"][key],
        }
        http["/api/thoughts/" + brain + "/" + key + "/graph"] = {
            "status": 200,
            "path": manifest["graphs"][key],
        }
        http["/api/thoughts/" + brain + "/" + key + "/attachments"] = {
            "status": 200,
            "path": manifest["attachment_inventories"][key],
        }
        if key in manifest["no_notes"]:
            http["/api/notes/" + brain + "/" + key] = {
                "status": 200,
                "path": manifest["no_notes"][key],
            }
    for key in link_rows:
        http["/api/links/" + brain + "/" + key] = {
            "status": 200,
            "path": manifest["authoritative_links"][key],
        }
        http["/api/links/" + brain + "/" + key + "/attachments"] = {
            "status": 200,
            "path": manifest["link_attachments"][key],
        }
    (root / "missing-404.bin").write_bytes(b"not found")
    manifest["files"]["missing-404.bin"] = fingerprint(root / "missing-404.bin")
    for key, outcome in manifest["payloads"].items():
        http["/api/attachments/" + brain + "/" + key + "/metadata"] = manifest[
            "attachment_metadata"
        ][key]
        http["/api/attachments/" + brain + "/" + key + "/file-content"] = (
            outcome
            if outcome["status"] == 200
            else {"status": 404, "path": "missing-404.bin"}
        )
    manifest["http_responses"] = http
    # Child now owns an unreferenced image, so its no-note wrapper stays required.
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    return baseline


def bound_case(tmp_path):
    """Independently authored expected vault for the source-only observation set."""
    baseline = image_source_case(tmp_path)
    vault = tmp_path / "vault"
    manifest = baseline.data
    graphs = {key: baseline.json(path) for key, path in manifest["graphs"].items()}
    authored = baseline.bytes(manifest["payloads"][identity(201)]["path"]).decode(
        "utf-8"
    )
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["profile_version"] = "3"
    all_rows = [row for graph in graphs.values() for row in graph["attachments"]]
    record["original_evidence"][0]["records"] = (
        [graph["activeThought"] for graph in graphs.values()]
        + list(
            {
                row["id"]: row for graph in graphs.values() for row in graph["links"]
            }.values()
        )
        + [row | {"position": {"decimal": "0"}} for row in all_rows]
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
            documents=[],
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
                "table_cell": False,
                "target": identity(202),
                "display_text": label,
                "document_digest": digest,
                "source_target": url,
                "destination_start": dest,
                "destination_end": dest + len(url),
                "presentation_normalization": norm,
            }
        )
    next(t for t in record["item_targets"] if t["item_key"] == identity(2))[
        "documents"
    ] = [
        {
            "key": identity(201),
            "owner": identity(2),
            "original_asset_id": identity(201),
            "original_copy_omitted": False,
            "text_adaptations": [],
            "evidence": ["attachment:" + identity(201)],
            "text_digest": digest,
            "owner_target": "Home.md",
            "references": references,
        }
    ]
    (vault / "Home.md").write_text(
        image_note_prefix("Home", 2, effective_owner=2)
        + "Préface 🐈\n\n![bleu]("
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
    (vault / "Child.md").write_text(
        image_note_prefix("Child", provider=4, effective_owner=4), encoding="utf-8"
    )
    (vault / "Type.md").write_text(image_note_prefix("Type", 4), encoding="utf-8")
    for asset in record["asset_targets"]:
        asset["retained_documents"] = []
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
        next(t for t in record["item_targets"] if t["item_key"] == identity(2))[
            "documents"
        ] = []
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
        references = first_document(record)["references"]
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
    stamp = path.stat()
    raw = bytearray(path.read_bytes())
    raw[4400 if key == 206 else 1200 if key == 207 else 300] ^= 1
    path.write_bytes(raw)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert path.stat().st_mtime_ns == stamp.st_mtime_ns
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
            "retained_documents": [],
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
            "documents": [],
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
        (vault / "Empty.md").write_text(image_note_prefix("Empty"), encoding="utf-8")
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


def add_ico_to_owner(baseline, vault, owner, name, provider=None):
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    path = root / manifest["graphs"][identity(owner)]
    graph = json.loads(path.read_bytes())
    row = {
        "id": identity(209),
        "brainId": identity(1),
        "sourceId": identity(owner),
        "sourceType": 2,
        "type": 5,
        "isNotes": False,
        "location": "Icon.png",
        "name": None,
    }
    graph["attachments"].append(row)
    write_json(path, graph)
    write_json(
        root / manifest["attachment_inventories"][identity(owner)], graph["attachments"]
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
            "owner": identity(owner),
            "relative_path": "Assets/" + identity(owner) + "/Icon.png",
        }
    )
    copied = vault / ("Assets/" + identity(owner) + "/Icon.png")
    copied.parent.mkdir(parents=True, exist_ok=True)
    copied.write_bytes((FIXTURES / "inert-a.ico").read_bytes())
    child = next(t for t in record["item_targets"] if t["item_key"] == identity(owner))
    child["declared_appearance"] = {
        "icon_asset_id": identity(209),
        "foreground_color": None,
        "background_color": None,
    }
    child["icon_snapshot"].update(
        explicit_icon_asset_id=identity(209), effective_icon_asset_id=identity(209)
    )
    write_json(path, record)
    (vault / (name + ".md")).write_text(
        image_note_prefix(name, owner, provider=provider, effective_owner=owner),
        encoding="utf-8",
    )
    return baseline


def test_direct_ico_takes_precedence_over_distinct_type_ico(tmp_path):
    baseline, vault = bound_case(tmp_path)
    baseline = add_ico_to_owner(baseline, vault, 3, "Child", provider=4)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    child = next(t for t in record["item_targets"] if t["item_key"] == identity(3))
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


@pytest.mark.parametrize("key", [202, 205, 206, 207])
@pytest.mark.parametrize("status", [404, 408, 503, 200.0, True])
def test_every_new_image_requires_an_actual_complete_200_response(
    tmp_path, key, status
):
    baseline, vault = bound_case(tmp_path)
    manifest = json.loads(baseline.manifest_path.read_bytes())
    manifest["payloads"][identity(key)]["status"] = status
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    with pytest.raises(AssertionError):
        audit_baseline(baseline, profile_version="3")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


ADAPTED_IMAGE_NOTES = [
    pytest.param(
        'Préface 🐈 <Enter>.\n\n> [!tip|icon:🐈]\n> ![bleu]({image}#$width=75p$ "Titre")\n',
        'Préface 🐈 \\<Enter>.{eol}{eol}> [!tip] 🐈 Tip{eol}> ![bleu]({image}#$width=75p$ "Titre"){eol}',
        id="callout-literal",
    ),
    pytest.param(
        '|Image|Other|:(table="column-widths:-1,0,84;justification:default"):\n|![bleu]({image})|value|\n',
        "|Image|Other|\n|---|---|{eol}|![bleu]({image})|value|{eol}",
        id="table",
    ),
    pytest.param(
        "[/toc/]\n\n# Heading\n![bleu]({image})\n",
        "- [Heading](#^brz-toc-heading-1){eol}{eol}# Heading ^brz-toc-heading-1{eol}![bleu]({image}){eol}",
        id="toc",
    ),
    pytest.param(
        "`![false]({image})`\n\n<!-- ![false]({image}) -->\n\n> [!info|icon:🐈]\n> ![bleu]({image}#$width=50p$)\n",
        "`![false]({image})`{eol}{eol}<!-- ![false]({image}) -->{eol}{eol}> [!info] 🐈 Info{eol}> ![bleu]({image}#$width=50p$){eol}",
        id="protected",
    ),
    pytest.param(
        'Préface <Enter>.\n\n[/toc/]\n\n# Images\n|Image|Other|:(table="column-widths:-1,0,84;justification:default"):\n|![bleu]({image}#$width=50p$)|value|\n\n> [!tip|icon:🐈]\n> ![deux]({image} "Titre")\n',
        'Préface \\<Enter>.{eol}{eol}- [Images](#^brz-toc-heading-1){eol}{eol}# Images ^brz-toc-heading-1{eol}|Image|Other|\n|---|---|{eol}|![bleu]({image}#$width=50p$)|value|{eol}{eol}> [!tip] 🐈 Tip{eol}> ![deux]({image} "Titre"){eol}',
        id="combined",
    ),
]

ADAPTED_IMAGE_NOTES += [
    pytest.param(
        "Préface 🐈 <Enter>.\n\n![bleu]({image})\n",
        "Préface 🐈 \\<Enter>.{eol}{eol}![bleu]({image}){eol}",
        id="literal-only",
    ),
    pytest.param(
        "Préface 🐈\n\n![bleu]({image})\n",
        "Préface 🐈{eol}{eol}![bleu]({image}){eol}",
        id="unchanged",
    ),
    pytest.param(
        "[/toc/]\n\n# First\nText\n\n## Second\n![bleu]({image})\n",
        "- [First](#^brz-toc-heading-1)\n  - [Second](#^brz-toc-heading-2){eol}{eol}# First ^brz-toc-heading-1{eol}Text{eol}{eol}## Second ^brz-toc-heading-2{eol}![bleu]({image}){eol}",
        id="toc-multiple",
    ),
    pytest.param(
        "[/toc/]\n\nMulti\nline\n====\n![bleu]({image})\n",
        "- [Multi line](#^brz-toc-heading-1){eol}{eol}# Multi line ^brz-toc-heading-1{eol}![bleu]({image}){eol}",
        id="toc-setext",
    ),
    pytest.param(
        "> `begin\nlazy ![false]({image})\n> end`\n\n> [!info|icon:🐈]\n> ![bleu]({image}#$width=50p$)\n",
        "> `begin{eol}lazy ![false]({image}){eol}> end`{eol}{eol}> [!info] 🐈 Info{eol}> ![bleu]({image}#$width=50p$){eol}",
        id="protected-lazy",
    ),
]


ADAPTED_IMAGE_NOTES += [
    pytest.param(
        '|Code|Image|:(table="column-widths:-1,0,84;justification:default"):\n|`![false](.data/md-images/missing.jpg)|x`|![bleu]({image})|\n',
        "|Code|Image|\n|---|---|{eol}|<code>![false](.data/md-images/missing.jpg)&#124;x</code>|![bleu]({image})|{eol}",
        id="table-code-false-target",
    ),
    pytest.param(
        "> `begin\nlazy ![false](.data/md-images/missing.jpg)\n> end`\n\n> [!info|icon:🐈]\n> ![bleu]({image}#$width=50p$)\n",
        "> `begin{eol}lazy ![false](.data/md-images/missing.jpg){eol}> end`{eol}{eol}> [!info] 🐈 Info{eol}> ![bleu]({image}#$width=50p$){eol}",
        id="lazy-false-target",
    ),
]


def fixture_adaptations(raw, adapted):
    """Literal template pairs supply valid noncanonical line edit segmentation."""
    before, after = raw.splitlines(keepends=True), adapted.splitlines(keepends=True)
    regions = []
    for tag, a, b, c, d in SequenceMatcher(
        None, before, after, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        if a == b:
            if b < len(before):
                b += 1
                d += 1
            else:
                a -= 1
                c -= 1
        if regions and a <= regions[-1][1] and c <= regions[-1][3]:
            old = regions.pop()
            a, c = old[0], old[2]
        regions.append((a, b, c, d))
    edits = []
    for a, b, c, d in regions:
        original, replacement = "".join(before[a:b]), "".join(after[c:d])
        insert = (
            any(token in original for token in (":(table=", "[/toc/]", "> [!"))
            or (
                "[/toc/]" in raw
                and any(
                    line.lstrip().startswith(("#", "=", "-")) for line in before[a:b]
                )
            )
            or (":(table=" in raw and "`" in original)
            or ("> [!" in raw and original.lstrip().startswith(">"))
        )
        edits.append(
            {
                "kind": "markdown_insert" if insert else "literal_text",
                "start": len("".join(before[:a])),
                "end": len("".join(before[:b])),
                "before": original,
                "after": replacement,
                "adapted_start": len("".join(after[:c])),
                "adapted_end": len("".join(after[:d])),
                "source_digest": hashlib.sha256(raw.encode()).hexdigest(),
                "source_basis": "scoped_source_text/unicode_codepoints",
                "adapted_basis": "document.text/unicode_codepoints",
            }
        )
    return edits


def adapted_note_case(tmp_path, raw_template, adapted_template, ending="\n"):
    baseline, vault = bound_case(tmp_path)
    url = ".data/md-images/" + identity(202) + ".jpg"
    raw = raw_template.format(image=url).replace("\n", ending)
    adapted = adapted_template.format(image=url, eol=ending)
    root = baseline.manifest_path.parent
    (root / "201.bin").write_bytes(raw.encode())
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    original = next(
        a for a in record["asset_targets"] if a["asset_id"] == identity(201)
    )
    (vault / original["relative_path"]).write_bytes(raw.encode())
    original.update(
        actual_length=len(raw.encode()),
        actual_sha256=hashlib.sha256(raw.encode()).hexdigest(),
    )
    digest = hashlib.sha256(adapted.encode()).hexdigest()
    references = []
    for label in ("bleu", "deux"):
        phrase = "![" + label + "]"
        if phrase not in adapted:
            continue
        start = adapted.index(phrase)
        end = adapted.index(")", start) + 1
        dest_start = adapted.index(url, start)
        dest_end = min(
            end - 1,
            adapted.find(" ", dest_start)
            if " " in adapted[dest_start : end - 1]
            else end - 1,
        )
        source_target = adapted[dest_start:dest_end]
        normalization = None
        if "#" in source_target:
            begin = dest_start + source_target.index("#")
            normalization = {
                "declaration": adapted[begin:dest_end],
                "start": begin,
                "end": dest_end,
                "document_digest": digest,
                "basis": "document.text/unicode_codepoints",
                "presentation": "responsive",
            }
        references.append(
            {
                "start": start,
                "end": end,
                "expected_original": adapted[start:end],
                "kind": "image",
                "table_cell": adapted[
                    max(adapted.rfind("\n", 0, start), adapted.rfind("\r", 0, start))
                    + 1 : start
                ]
                .lstrip()
                .startswith("|"),
                "target": identity(202),
                "display_text": label,
                "document_digest": digest,
                "source_target": source_target,
                "destination_start": dest_start,
                "destination_end": dest_end,
                "presentation_normalization": normalization,
            }
        )
    first_document(record).update(
        text_digest=digest,
        references=references,
        text_adaptations=fixture_adaptations(raw, adapted),
    )
    displayed = adapted
    actual = next(a for a in record["asset_targets"] if a["asset_id"] == identity(202))[
        "relative_path"
    ]
    for ref in sorted(references, key=lambda r: r["destination_start"], reverse=True):
        displayed = (
            displayed[: ref["destination_start"]]
            + actual
            + displayed[ref["destination_end"] :]
        )
    displayed = displayed.replace("\r\n", "\n").replace("\r", "\n")
    (vault / "Home.md").write_text(
        image_note_prefix("Home", 2, effective_owner=2) + displayed, encoding="utf-8"
    )
    write_json(path, record)
    return baseline, vault, adapted


@pytest.mark.parametrize("raw,adapted", ADAPTED_IMAGE_NOTES)
@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_image_documents_bind_to_independently_expected_adapted_text(
    tmp_path, raw, adapted, ending
):
    baseline, vault, text = adapted_note_case(tmp_path, raw, adapted, ending)
    assert audit_baseline(baseline, profile_version="3")["payloads"] == 6
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert (
        first_document(record)["text_digest"]
        == hashlib.sha256(text.encode()).hexdigest()
    )
    assert (baseline.manifest_path.parent / "201.bin").read_bytes() == raw.format(
        image=".data/md-images/" + identity(202) + ".jpg"
    ).replace("\n", ending).encode()


@pytest.mark.parametrize(
    "raw,adapted", [ADAPTED_IMAGE_NOTES[0], ADAPTED_IMAGE_NOTES[4]]
)
@pytest.mark.parametrize("ending", ["\r\n", "\r"])
@pytest.mark.parametrize(
    "damage",
    [
        "document_digest",
        "reference_digest",
        "start",
        "destination",
        "source_target",
        "expected_original",
        "presentation",
    ],
)
def test_adapted_image_document_metadata_cannot_be_forged(
    tmp_path, raw, adapted, ending, damage
):
    baseline, vault, _ = adapted_note_case(tmp_path, raw, adapted, ending)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    document = first_document(record)
    reference = document["references"][0]
    if damage == "document_digest":
        document["text_digest"] = "0" * 64
    elif damage == "reference_digest":
        reference["document_digest"] = "0" * 64
    elif damage == "start":
        reference["start"] += 1
    elif damage == "destination":
        reference["destination_start"] += 1
    elif damage == "source_target":
        reference["source_target"] = ".data/md-images/" + identity(205) + ".jpg"
    elif damage == "expected_original":
        reference["expected_original"] = reference["expected_original"].replace(
            "bleu", "wrong"
        )
    else:
        reference["presentation_normalization"] = {
            "declaration": "#$width=12p$",
            "start": 0,
            "end": 1,
            "document_digest": document["text_digest"],
            "basis": "document.text/unicode_codepoints",
            "presentation": "responsive",
        }
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_raw_note_digest_cannot_replace_the_final_adapted_document_digest(
    tmp_path, ending
):
    raw, adapted = ADAPTED_IMAGE_NOTES[0].values
    baseline, vault, _ = adapted_note_case(tmp_path, raw, adapted, ending)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    first_document(record)["text_digest"] = hashlib.sha256(
        (baseline.manifest_path.parent / "201.bin").read_bytes()
    ).hexdigest()
    write_json(path, record)
    with pytest.raises(AssertionError, match="image document source binding"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("family", ["protected", "protected-lazy"])
def test_protected_image_examples_cannot_be_promoted_to_document_references(
    tmp_path, family
):
    case = next(case for case in ADAPTED_IMAGE_NOTES if case.id == family)
    baseline, vault, adapted = adapted_note_case(tmp_path, *case.values, "\r\n")
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    reference = dict(first_document(record)["references"][0])
    start = adapted.index("![false]")
    end = adapted.index(")", start) + 1
    destination = adapted.index(".data/md-images/", start)
    reference.update(
        start=start,
        end=end,
        expected_original=adapted[start:end],
        display_text="false",
        destination_start=destination,
        destination_end=end - 1,
        source_target=adapted[destination : end - 1],
        presentation_normalization=None,
    )
    first_document(record)["references"].insert(0, reference)
    write_json(path, record)
    with pytest.raises(AssertionError, match="all source image references"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_raw_active_code_does_not_gain_generated_table_code_protection(
    tmp_path, ending
):
    baseline, _ = bound_case(tmp_path)
    raw = (
        "<code>![false](.data/md-images/missing.jpg)</code>\n\n"
        + "![bleu](.data/md-images/"
        + identity(202)
        + ".jpg)\n"
    ).replace("\n", ending)
    (baseline.manifest_path.parent / "201.bin").write_bytes(raw.encode())
    baseline = reseal(baseline)
    with pytest.raises(AssertionError, match="active HTML"):
        audit_baseline(baseline, profile_version="3")


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_literal_source_code_html_and_generated_table_code_keep_distinct_eligibility(
    tmp_path, ending
):
    raw = "`<code>![false](.data/md-images/missing.jpg)</code>`\n\n![bleu]({image})\n"
    adapted = "`<code>![false](.data/md-images/missing.jpg)</code>`{eol}{eol}![bleu]({image}){eol}"
    baseline, vault, _ = adapted_note_case(tmp_path, raw, adapted, ending)
    assert audit_baseline(baseline, profile_version="3")["payloads"] == 6
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6


@pytest.mark.parametrize("name,owner", [("Home", 2), ("Child", 4)])
@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "wrong",
        "duplicate",
        "comment",
        "fence",
        "escaped",
        "inline-code",
        "late",
    ],
)
def test_actual_selected_icon_introduction_cannot_be_omitted_or_forged(
    tmp_path, name, owner, damage
):
    baseline, vault = bound_case(tmp_path)
    path = vault / (name + ".md")
    text = path.read_text(encoding="utf-8")
    embed = "![[Assets/" + identity(owner) + "/Icon.png]]"
    wrong = "![[Assets/" + identity(4 if owner == 2 else 2) + "/Icon.png]]"
    replacement = {
        "missing": "",
        "wrong": wrong,
        "duplicate": embed + "\n\n" + embed,
        "comment": "<!-- " + embed + " -->",
        "fence": "```\n" + embed + "\n```",
        "escaped": "\\" + embed,
        "inline-code": "`" + embed + "`",
        "late": "Prose first.\n\n" + embed,
    }[damage]
    path.write_text(text.replace(embed, replacement, 1), encoding="utf-8")
    with pytest.raises(AssertionError, match="icon"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("name,explicit", [("Home", 2), ("Child", None), ("Type", 4)])
@pytest.mark.parametrize("damage", ["missing", "wrong", "null", "duplicate"])
def test_actual_icon_property_binds_explicit_ownership_only(
    tmp_path, name, explicit, damage
):
    baseline, vault = bound_case(tmp_path)
    path = vault / (name + ".md")
    text = path.read_text(encoding="utf-8")
    original = (
        ('icon: "[[Assets/' + identity(explicit) + '/Icon.png]]"')
        if explicit
        else "icon:"
    )
    wrong = 'icon: "[[Assets/' + identity(4 if explicit != 4 else 2) + '/Icon.png]]"'
    replacement = {
        "missing": "",
        "wrong": wrong,
        "null": "icon: null",
        "duplicate": original + "\n" + original,
    }[damage]
    path.write_text(text.replace(original, replacement, 1), encoding="utf-8")
    with pytest.raises(AssertionError, match="icon"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("name", ["Home", "Child", "Type"])
@pytest.mark.parametrize("damage", ["missing", "wrong", "duplicate"])
def test_actual_icon_provider_property_binds_source_type(tmp_path, name, damage):
    baseline, vault = bound_case(tmp_path)
    path = vault / (name + ".md")
    text = path.read_text(encoding="utf-8")
    original = (
        'appearance_category: "[[Type.md]]"'
        if name == "Child"
        else "appearance_category:"
    )
    replacement = {
        "missing": "",
        "wrong": 'appearance_category: "[[Home.md]]"',
        "duplicate": original + "\n" + original,
    }[damage]
    path.write_text(text.replace(original, replacement, 1), encoding="utf-8")
    with pytest.raises(AssertionError, match="icon"):
        check_api_vault(baseline, vault, profile_version="3")


def test_definition_uses_property_without_generated_body_icon(tmp_path):
    baseline, vault = bound_case(tmp_path)
    path = vault / "Type.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "![[Assets/" + identity(4) + "/Icon.png]]\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="icon"):
        check_api_vault(baseline, vault, profile_version="3")


def test_source_definition_cannot_be_hidden_by_record_selection(tmp_path):
    baseline, vault = bound_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    target = next(t for t in record["item_targets"] if t["item_key"] == identity(4))
    target.update(created=False, icon_snapshot=None)
    write_json(path, record)
    (vault / "Type.md").unlink()
    with pytest.raises(AssertionError, match="materialization"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("damage", ["forged", "omitted"])
def test_uncreated_decorative_owner_cannot_fabricate_icon_snapshot(tmp_path, damage):
    baseline, vault = bound_case(tmp_path)
    baseline = add_empty_owner(baseline, vault, "icon")
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["item_targets"][-1]["icon_snapshot"] = {
        "item_key": identity(6),
        "explicit_icon_asset_id": identity(208),
        "appearance_category_key": None,
        "effective_icon_asset_id": identity(208),
    }
    if damage == "omitted":
        del record["item_targets"][-1]["icon_snapshot"]
    write_json(path, record)
    with pytest.raises(AssertionError, match="icon"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("entropy_bytes", [0, 1, 3, 6])
@pytest.mark.parametrize("entrypoint", ["asset", "audit", "vault"])
def test_jpeg_premature_entropy_recovery_is_not_complete_validity(
    tmp_path, entropy_bytes, entrypoint
):
    baseline, vault = bound_case(tmp_path)
    raw = (FIXTURES / "inert-blue.jpg").read_bytes()
    assert raw[609:611] == b"\xff\xda" and raw[630:] == b"\xff\xd9"
    damaged = raw[: 623 + entropy_bytes] + b"\xff\xd9"
    baseline = put_payload(baseline, damaged)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    target = next(a for a in record["asset_targets"] if a["asset_id"] == identity(202))
    (vault / target["relative_path"]).write_bytes(damaged)
    target.update(
        actual_length=len(damaged), actual_sha256=hashlib.sha256(damaged).hexdigest()
    )
    write_json(path, record)
    image = next(
        a
        for a in record["original_evidence"][0]["records"]
        if a.get("id") == identity(202)
    )
    with pytest.raises(AssertionError, match="JPEG.*premature"):
        if entrypoint == "asset":
            expected_asset(baseline, image, "3")
        elif entrypoint == "audit":
            audit_baseline(baseline, profile_version="3")
        else:
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("name", ["inert-progressive.jpg", "inert-trailer.jpg"])
def test_complete_jpeg_progressive_multiscan_and_inert_trailer_remain_admitted(
    tmp_path, name
):
    fixtures = FIXTURES.parent / "local_api_jpeg_neighbors_v3"
    facts = json.loads((fixtures / "source-facts.json").read_bytes())
    raw = (fixtures / name).read_bytes()
    literal = facts["inputs"][name]
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == (
        literal["length"],
        literal["sha256"],
    )
    assert raw.count(b"\xff\xda") == literal["sos_markers"]
    assert raw.count(b"\xff\xc2") == literal["sof2_markers"]
    baseline, vault = bound_case(tmp_path)
    baseline = put_payload(baseline, raw)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    target = next(a for a in record["asset_targets"] if a["asset_id"] == identity(202))
    (vault / target["relative_path"]).write_bytes(raw)
    target.update(actual_length=len(raw), actual_sha256=hashlib.sha256(raw).hexdigest())
    write_json(path, record)
    proof = audit_baseline(baseline, profile_version="3")["resource_eligibility"][
        identity(202)
    ]
    assert proof["format"] == "JPEG" and proof["source_sha256"] == literal["sha256"]
    assert (proof["width"], proof["height"], proof["frames"][0]["decoded_bytes"]) == (
        2,
        1,
        8,
    )
    rgba = facts["expected_decoded"]["pixels"]
    bgra = bytes(v for r, g, b, a in rgba for v in (b, g, r, a))
    assert proof["frames"][0]["pixel_sha256"] == hashlib.sha256(bgra).hexdigest()
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6


@pytest.mark.parametrize(
    "damage",
    [None, "provider-body", "provider-property", "both-body", "blank-property"],
)
def test_actual_direct_icon_precedence_is_source_bound(tmp_path, damage):
    baseline, vault = bound_case(tmp_path)
    baseline = add_ico_to_owner(baseline, vault, 3, "Child", provider=4)
    path = vault / "Child.md"
    text = path.read_text(encoding="utf-8")
    direct = "Assets/" + identity(3) + "/Icon.png"
    inherited = "Assets/" + identity(4) + "/Icon.png"
    if damage == "provider-body":
        text = text.replace("![[" + direct + "]]", "![[" + inherited + "]]")
    elif damage == "provider-property":
        text = text.replace(
            'icon: "[[' + direct + ']]"', 'icon: "[[' + inherited + ']]"'
        )
    elif damage == "both-body":
        text += "![[" + inherited + "]]\n"
    elif damage == "blank-property":
        text = text.replace('icon: "[[' + direct + ']]"', "icon:")
    path.write_text(text, encoding="utf-8")
    if damage:
        with pytest.raises(AssertionError, match="icon"):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 7


@pytest.mark.parametrize("damage", [None, "missing-body", "missing-property"])
def test_materialized_tag_has_source_owned_explicit_icon_presentation(tmp_path, damage):
    baseline, vault = bound_case(tmp_path)
    baseline = add_empty_owner(baseline, vault, "image")
    root = baseline.manifest_path.parent
    graph_path = root / baseline.data["graphs"][identity(6)]
    graph = json.loads(graph_path.read_bytes())
    graph["activeThought"]["kind"] = 4
    write_json(graph_path, graph)
    tags_path = root / baseline.data["tags"]["path"]
    write_json(tags_path, json.loads(tags_path.read_bytes()) + [graph["activeThought"]])
    for path in baseline.data["statistics"]:
        statistics = json.loads((root / path).read_bytes())
        statistics["thoughts"] -= 1
        statistics["tags"] += 1
        write_json(root / path, statistics)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    next(
        row
        for row in record["original_evidence"][0]["records"]
        if row.get("id") == identity(6)
    )["kind"] = 4
    write_json(path, record)
    baseline = add_ico_to_owner(baseline, vault, 6, "Empty")
    path = vault / "Empty.md"
    text = path.read_text(encoding="utf-8")
    if damage == "missing-body":
        text = text.replace("![[Assets/" + identity(6) + "/Icon.png]]", "")
    elif damage == "missing-property":
        text = text.replace('icon: "[[Assets/' + identity(6) + '/Icon.png]]"', "icon:")
    path.write_text(text, encoding="utf-8")
    if damage:
        with pytest.raises(AssertionError, match="icon"):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 8


@pytest.mark.parametrize("source", ["label", "body"])
@pytest.mark.parametrize("damage", [None, "missing-generated"])
def test_authored_icon_syntax_cannot_substitute_for_generated_introduction(
    tmp_path, source, damage
):
    embed = "![[Assets/" + identity(2) + "/Icon.png]]"
    if source == "body":
        raw = "```\n" + embed + "\n```\n\n![bleu]({image})\n"
        baseline, vault, _ = adapted_note_case(
            tmp_path, raw, raw.replace("\n", "{eol}")
        )
    else:
        baseline, vault = bound_case(tmp_path)
        root = baseline.manifest_path.parent
        graph_path = root / baseline.data["graphs"][identity(2)]
        graph = json.loads(graph_path.read_bytes())
        label = embed + "\n\nAuthored label."
        graph["activeThought"]["label"] = label
        write_json(graph_path, graph)
        baseline = reseal(baseline)
        record_path = vault / "migration-record.json"
        record = json.loads(record_path.read_bytes())
        next(
            row
            for row in record["original_evidence"][0]["records"]
            if row.get("id") == identity(2)
        )["label"] = label
        write_json(record_path, record)
        path = vault / "Home.md"
        text = path.read_text(encoding="utf-8")
        prefix = image_note_prefix("Home", 2, effective_owner=2)
        path.write_text(prefix + label + "\n\n" + text[len(prefix) :], encoding="utf-8")
    path = vault / "Home.md"
    if damage:
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(embed + "\n\n", "", 1), encoding="utf-8")
        with pytest.raises(AssertionError, match="icon"):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6


@pytest.mark.parametrize("diagnostic", [b"", b"Warning: harmless codec note\n"])
def test_silent_jpeg_recovery_backend_remains_unverified(
    tmp_path, monkeypatch, diagnostic
):
    from tests.local_acceptance import api_image_proofs
    from tests.local_acceptance.images import AuditUnavailable

    baseline, _, image = image_case(tmp_path)
    api_image_proofs.jpeg_diagnostic_capability.cache_clear()
    real = api_image_proofs.isolated_jpeg_decode

    def suppress(raw):
        proof, _ = real(raw)
        return proof, diagnostic

    monkeypatch.setattr(api_image_proofs, "isolated_jpeg_decode", suppress)
    try:
        with pytest.raises(
            AuditUnavailable, match="corrupt-data diagnostic unavailable"
        ):
            expected_asset(baseline, image, "3")
    finally:
        api_image_proofs.jpeg_diagnostic_capability.cache_clear()


def test_unclassified_native_jpeg_diagnostic_is_unverified_not_invalid(
    tmp_path, monkeypatch
):
    from tests.local_acceptance import api_image_proofs
    from tests.local_acceptance.images import AuditUnavailable

    baseline, _, image = image_case(tmp_path)
    api_image_proofs.jpeg_diagnostic_capability()
    real = api_image_proofs.isolated_jpeg_decode

    def warning(raw):
        proof, diagnostics = real(raw)
        return proof, diagnostics + b"Warning: unclassified codec diagnostic\n"

    monkeypatch.setattr(api_image_proofs, "isolated_jpeg_decode", warning)
    with pytest.raises(AuditUnavailable, match="unclassified.*diagnostic"):
        expected_asset(baseline, image, "3")


@pytest.mark.parametrize("syntax", ["wiki", "markdown"])
@pytest.mark.parametrize("name,owner", [("Home", 2), ("Child", 4), ("Type", 4)])
def test_unexpected_additional_active_icon_cannot_escape_intro_ownership(
    tmp_path, syntax, name, owner
):
    baseline, vault = bound_case(tmp_path)
    path = vault / (name + ".md")
    target = "Assets/" + identity(owner) + "/Icon.png"
    extra = "![[" + target + "]]" if syntax == "wiki" else "![extra](" + target + ")"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n\n" + extra + "\n", encoding="utf-8"
    )
    with pytest.raises(AssertionError, match="icon"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("name", ["Home", "Child", "Type"])
@pytest.mark.parametrize("property", ["icon", "appearance_category"])
@pytest.mark.parametrize("syntax", ["quoted", "explicit-key"])
def test_yaml_semantic_duplicate_icon_properties_cannot_override_literal_line(
    tmp_path, name, property, syntax
):
    baseline, vault = bound_case(tmp_path)
    path = vault / (name + ".md")
    text = path.read_text(encoding="utf-8")
    extra = (
        '"' + property + '": null'
        if syntax == "quoted"
        else "? " + property + "\n: null"
    )
    path.write_text(
        text.replace("\n---\n", "\n" + extra + "\n---\n", 1), encoding="utf-8"
    )
    with pytest.raises(AssertionError, match="icon"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("offset", [20, 158, 177, 609])
@pytest.mark.parametrize("entrypoint", ["asset", "audit", "vault"])
def test_jpeg_definite_extraneous_data_recovery_cannot_be_accepted(
    tmp_path, offset, entrypoint
):
    baseline, vault = bound_case(tmp_path)
    raw = (FIXTURES / "inert-blue.jpg").read_bytes()
    assert raw[offset] == 255
    damaged = raw[:offset] + b"junk" + raw[offset:]
    baseline = put_payload(baseline, damaged)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    target = next(a for a in record["asset_targets"] if a["asset_id"] == identity(202))
    (vault / target["relative_path"]).write_bytes(damaged)
    target.update(
        actual_length=len(damaged), actual_sha256=hashlib.sha256(damaged).hexdigest()
    )
    write_json(path, record)
    image = next(
        a
        for a in record["original_evidence"][0]["records"]
        if a.get("id") == identity(202)
    )
    with pytest.raises(AssertionError, match="JPEG.*corrupt"):
        if entrypoint == "asset":
            expected_asset(baseline, image, "3")
        elif entrypoint == "audit":
            audit_baseline(baseline, profile_version="3")
        else:
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("name", ["inert-gray.jpg", "inert-cmyk.jpg"])
def test_existing_jpeg_color_classes_keep_full_bytes_and_codec_bound_pixel_proofs(
    tmp_path, name
):
    fixtures = FIXTURES.parent / "local_api_jpeg_neighbors_v3"
    facts = json.loads((fixtures / "extended-source-facts.json").read_bytes())[
        "inputs"
    ][name]
    raw = (fixtures / name).read_bytes()
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == (
        facts["length"],
        facts["sha256"],
    )
    baseline, vault = bound_case(tmp_path)
    baseline = put_payload(baseline, raw)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    target = next(a for a in record["asset_targets"] if a["asset_id"] == identity(202))
    (vault / target["relative_path"]).write_bytes(raw)
    target.update(actual_length=len(raw), actual_sha256=hashlib.sha256(raw).hexdigest())
    write_json(path, record)
    proof = audit_baseline(baseline, profile_version="3")["resource_eligibility"][
        identity(202)
    ]
    assert (
        proof["format"],
        proof["width"],
        proof["height"],
        proof["frames"][0]["decoded_bytes"],
    ) == ("JPEG", 2, 1, 8)
    measurement = facts["independent_wic_measurement"]
    assert proof["codec"]["name"] == measurement["codec"]
    # This assertion binds the separately qualified current WIC measurement;
    # CMYK-to-RGBA color is not asserted as universal source artwork truth.
    rgba = measurement["rgba_pixels"]
    bgra = bytes(
        v
        for i in range(0, len(rgba), 4)
        for v in (rgba[i + 2], rgba[i + 1], rgba[i], rgba[i + 3])
    )
    assert proof["frames"][0]["pixel_sha256"] == hashlib.sha256(bgra).hexdigest()
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6


@pytest.mark.parametrize(
    "name",
    [
        "literal-lossless-gray.jpg",
        "literal-lossless-rgb.jpg",
        "literal-lossless-cmyk.jpg",
        "literal-441.jpg",
        "literal-ycck.jpg",
    ],
)
def test_qualified_lossless_sampling_ycck_classes_keep_source_and_full_pixels(
    tmp_path, name
):
    fixtures = FIXTURES.parent / "local_api_jpeg_classes_v3"
    facts = json.loads((fixtures / "class-source-facts.json").read_bytes())["inputs"][
        name
    ]
    raw = (fixtures / name).read_bytes()
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == (
        facts["length"],
        facts["sha256"],
    )
    assert (
        b"\xff\xc3" if facts["literal_source_facts"]["frame"] == "SOF3" else b"\xff\xc0"
    ) in raw
    baseline, vault = bound_case(tmp_path)
    baseline = put_payload(baseline, raw)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    target = next(a for a in record["asset_targets"] if a["asset_id"] == identity(202))
    (vault / target["relative_path"]).write_bytes(raw)
    target.update(actual_length=len(raw), actual_sha256=hashlib.sha256(raw).hexdigest())
    write_json(path, record)
    image = next(
        a
        for a in record["original_evidence"][0]["records"]
        if a.get("id") == identity(202)
    )
    proofs = {}
    assert expected_asset(baseline, image, "3", proofs) == ("image", "present", raw)
    # These are independently qualified WIC measurements for this codec, not
    # universal CMYK/YCCK conversion truth or converter-output expectations.
    measured = facts["native_wic_measurement"]
    proof = proofs[identity(202)]
    assert proof["source_sha256"] == facts["sha256"] and proof["format"] == "JPEG"
    assert proof["codec"] == measured["codec"]
    assert proof["frames"] == measured["frames"]
    assert proof["native_diagnostics"] == ""
    audit = audit_baseline(baseline, profile_version="3")
    assert audit["resource_eligibility"][identity(202)]["frames"] == measured["frames"]
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6
    assert (vault / target["relative_path"]).read_bytes() == raw


@pytest.mark.parametrize("shadow", [False, True])
def test_published_nested_document_record_has_no_top_level_collection(tmp_path, shadow):
    baseline, vault = bound_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    if shadow:
        record["documents"] = [json.loads(json.dumps(first_document(record)))]
        write_json(path, record)
        with pytest.raises(AssertionError, match="document"):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6


@pytest.mark.parametrize(
    "damage",
    [
        "omitted",
        "wrong-owner-container",
        "asset-container",
        "duplicate",
        "digest",
        "copy-flag",
        "evidence",
        "table-flag",
    ],
)
def test_top_level_shadow_cannot_supply_nested_document_proof(tmp_path, damage):
    baseline, vault = bound_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    document = first_document(record)
    record["documents"] = [json.loads(json.dumps(document))]
    home = next(t for t in record["item_targets"] if t["item_key"] == identity(2))
    child = next(t for t in record["item_targets"] if t["item_key"] == identity(3))
    if damage == "omitted":
        home["documents"] = []
    elif damage == "wrong-owner-container":
        home["documents"] = []
        child["documents"] = [document]
    elif damage == "asset-container":
        home["documents"] = []
        record["asset_targets"][0]["retained_documents"] = [document]
    elif damage == "duplicate":
        child["documents"] = [document]
    elif damage == "digest":
        document["text_digest"] = "0" * 64
    elif damage == "copy-flag":
        document["original_copy_omitted"] = True
    elif damage == "evidence":
        document["evidence"] = ["attachment:forged"]
    else:
        document["references"][0]["table_cell"] = True
    write_json(path, record)
    with pytest.raises(AssertionError, match="document"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "damage",
    [
        "copy-true",
        "copy-number",
        "copy-missing",
        "evidence",
        "evidence-missing",
        "adaptations-bogus",
        "adaptations-missing",
        "table-true",
        "table-number",
        "source-target",
        "owner-target",
        "key",
        "unexpected-field",
    ],
)
def test_nested_document_complete_metadata_cannot_be_forged(tmp_path, damage):
    baseline, vault = bound_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    document = first_document(record)
    if damage == "copy-true":
        document["original_copy_omitted"] = True
    elif damage == "copy-number":
        document["original_copy_omitted"] = 0
    elif damage == "copy-missing":
        del document["original_copy_omitted"]
    elif damage == "evidence":
        document["evidence"] = ["attachment:forged"]
    elif damage == "evidence-missing":
        del document["evidence"]
    elif damage == "adaptations-bogus":
        document["text_adaptations"] = [{"kind": "markdown_insert"}]
    elif damage == "adaptations-missing":
        del document["text_adaptations"]
    elif damage == "table-true":
        document["references"][0]["table_cell"] = True
    elif damage == "table-number":
        document["references"][0]["table_cell"] = 0
    elif damage == "source-target":
        document["references"][0]["source_target"] = "forged.jpg"
    elif damage == "owner-target":
        document["owner_target"] = "Child.md"
    elif damage == "key":
        document["key"] = identity(205)
    else:
        document["text"] = "invented text"
    write_json(path, record)
    with pytest.raises(AssertionError, match="document|reference|adaptation"):
        check_api_vault(baseline, vault, profile_version="3")


def mixed_reference_case(tmp_path):
    uri = "brain://AAAAAAAAAECAAAAAAAAAAw/title"
    raw = (
        "[Child]("
        + uri
        + ")\r\n\r\n|Item|Image|\r\n|---|---|\r\n|[Child]("
        + uri
        + ")|![bleu]({image})|\r\n"
    )
    baseline, vault, text = adapted_note_case(tmp_path, raw, raw)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    doc = first_document(record)
    doc["references"][0]["table_cell"] = True
    phrase = "[Child](" + uri + ")"
    for start in [text.index(phrase), text.index(phrase, text.index(phrase) + 1)]:
        doc["references"].append(
            {
                "start": start,
                "end": start + len(phrase),
                "expected_original": phrase,
                "kind": "item",
                "target": identity(3),
                "display_text": "Child",
                "table_cell": start > text.index("|---|---|"),
                "document_digest": hashlib.sha256(text.encode()).hexdigest(),
                "source_target": uri,
                "destination_start": None,
                "destination_end": None,
                "presentation_normalization": None,
            }
        )
    doc["references"].sort(key=lambda row: row["start"])
    write_json(path, record)
    image_path = "Assets/" + identity(2) + "/" + identity(202) + ".jpg"
    display = text.replace(
        "![bleu](.data/md-images/" + identity(202) + ".jpg)",
        "![bleu](" + image_path + ")",
    )
    display = display.replace(phrase, "[[Child.md|Child]]", 1).replace(
        phrase, "[[Child.md\\|Child]]"
    )
    (vault / "Home.md").write_text(
        image_note_prefix("Home", 2, effective_owner=2) + display.replace("\r\n", "\n"),
        encoding="utf-8",
    )
    return baseline, vault


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "item-destination",
        "item-source",
        "item-table",
        "image-table",
        "ref-extra",
        "ref-start-bool",
    ],
)
def test_nested_mixed_item_image_and_table_reference_contract(tmp_path, damage):
    baseline, vault = mixed_reference_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    refs = first_document(record)["references"]
    if damage == "item-destination":
        refs[0]["destination_start"] = 8
        refs[0]["destination_end"] = 48
    elif damage == "item-source":
        refs[0]["source_target"] = "brain://forged"
    elif damage == "item-table":
        refs[1]["table_cell"] = False
    elif damage == "image-table":
        refs[2]["table_cell"] = False
    elif damage == "ref-extra":
        refs[0]["extra"] = True
    elif damage == "ref-start-bool":
        refs[0]["start"] = False
    write_json(path, record)
    if damage:
        with pytest.raises(AssertionError, match="reference|document"):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6


@pytest.mark.parametrize("damage", [None, "omitted", "created", "owner-target"])
def test_empty_original_document_is_owned_even_when_note_is_uncreated(tmp_path, damage):
    baseline, vault = bound_case(tmp_path)
    baseline = add_empty_owner(baseline, vault, "icon")
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    row = {
        "id": identity(209),
        "brainId": identity(1),
        "sourceId": identity(6),
        "sourceType": 2,
        "type": 1,
        "isNotes": True,
        "name": None,
        "location": "Notes.md",
    }
    graph = baseline.json(manifest["graphs"][identity(6)])
    graph["attachments"].append(row)
    write_json(root / manifest["graphs"][identity(6)], graph)
    write_json(
        root / manifest["attachment_inventories"][identity(6)], graph["attachments"]
    )
    write_json(root / "209-metadata.json", row)
    (root / "209.bin").write_bytes(b"")
    for name in ("209-metadata.json", "209.bin"):
        manifest["files"][name] = fingerprint(root / name)
    manifest["scope"]["attachment_ids"].append(identity(209))
    manifest["payloads"][identity(209)] = {"status": 200, "path": "209.bin"}
    manifest["attachment_metadata"][identity(209)] = {
        "status": 200,
        "path": "209-metadata.json",
    }
    del manifest["no_notes"][identity(6)]
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["original_evidence"][0]["records"].append(row)
    asset = next(
        a for a in record["asset_targets"] if a["asset_id"] == identity(201)
    ) | {
        "asset_id": identity(209),
        "owner": identity(6),
        "relative_path": "209.bin",
        "actual_length": 0,
        "actual_sha256": hashlib.sha256(b"").hexdigest(),
    }
    record["asset_targets"].append(asset)
    (vault / "209.bin").write_bytes(b"")
    target = next(t for t in record["item_targets"] if t["item_key"] == identity(6))
    target["documents"] = [
        {
            "key": identity(209),
            "owner": identity(6),
            "text_digest": hashlib.sha256(b"").hexdigest(),
            "original_asset_id": identity(209),
            "original_copy_omitted": False,
            "references": [],
            "text_adaptations": [],
            "evidence": ["attachment:" + identity(209)],
            "owner_target": "Empty.md",
        }
    ]
    if damage == "omitted":
        target["documents"] = []
    elif damage == "created":
        target["created"] = True
    elif damage == "owner-target":
        target["documents"][0]["owner_target"] = "Home.md"
    write_json(path, record)
    if damage:
        with pytest.raises(AssertionError, match="document|materialization"):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 8
        assert not (vault / "Empty.md").exists()


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "omitted",
        "digest",
        "source-basis",
        "adapted-basis",
        "before",
        "after",
        "start",
        "end",
        "adapted-start",
        "adapted-end",
        "order",
        "overlap",
        "kind",
        "kind-launder",
        "literal-launder",
        "bool-coordinate",
        "extra",
        "zero-span",
        "no-op",
    ],
)
def test_document_edit_provenance_is_source_owned_and_replayable(tmp_path, damage):
    raw_template, adapted_template = ADAPTED_IMAGE_NOTES[0].values
    baseline, vault, text = adapted_note_case(
        tmp_path, raw_template, adapted_template, "\r\n"
    )
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    doc = first_document(record)
    edits = doc["text_adaptations"]
    raw = baseline.bytes(baseline.data["payloads"][identity(201)]["path"]).decode()
    if damage == "omitted":
        doc["text_adaptations"] = []
    elif damage == "digest":
        edits[0]["source_digest"] = "0" * 64
    elif damage == "source-basis":
        edits[0]["source_basis"] = "document.text/unicode_codepoints"
    elif damage == "adapted-basis":
        edits[0]["adapted_basis"] = "scoped_source_text/unicode_codepoints"
    elif damage == "before":
        edits[0]["before"] = "forged"
    elif damage == "after":
        edits[0]["after"] = "forged"
    elif damage == "start":
        edits[0]["start"] += 1
    elif damage == "end":
        edits[0]["end"] -= 1
    elif damage == "adapted-start":
        edits[0]["adapted_start"] += 1
    elif damage == "adapted-end":
        edits[0]["adapted_end"] -= 1
    elif damage == "order":
        edits.reverse()
    elif damage == "overlap":
        edits.insert(1, edits[0].copy())
    elif damage == "kind":
        edits[0]["kind"] = "unknown"
    elif damage in {"kind-launder", "literal-launder"}:
        doc["text_adaptations"] = [
            edits[0]
            | {
                "kind": "markdown_insert"
                if damage == "kind-launder"
                else "literal_text",
                "start": 0,
                "end": len(raw),
                "before": raw,
                "after": text,
                "adapted_start": 0,
                "adapted_end": len(text),
            }
        ]
    elif damage == "bool-coordinate":
        edits[0]["start"] = False
    elif damage == "extra":
        edits[0]["extra"] = False
    elif damage == "zero-span":
        edits[0].update(end=edits[0]["start"], before="")
    elif damage == "no-op":
        edits[0].update(after=edits[0]["before"])
    write_json(path, record)
    if damage:
        with pytest.raises(AssertionError, match="adaptation"):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6


def test_literal_edit_provenance_accepts_alternate_valid_source_segmentation(tmp_path):
    raw = "Prefix <Enter>.\n\n![bleu]({image})\n"
    adapted = "Prefix \\<Enter>.{eol}{eol}![bleu]({image}){eol}"
    baseline, vault, text = adapted_note_case(tmp_path, raw, adapted)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    doc = first_document(record)
    original = baseline.bytes(baseline.data["payloads"][identity(201)]["path"]).decode()
    # The original line edit and this whole-source edit both replay exactly;
    # only the genuine literal token changes, so no atomic span is prescribed.
    doc["text_adaptations"] = [
        doc["text_adaptations"][0]
        | {
            "start": 0,
            "end": len(original),
            "before": original,
            "after": text,
            "adapted_start": 0,
            "adapted_end": len(text),
        }
    ]
    write_json(path, record)
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6


@pytest.mark.parametrize(
    "damage",
    [
        "missing-collection",
        "wrong-collection-type",
        "omitted",
        "wrong-owner",
        "asset-container",
        "duplicate",
        "extra",
        "original-id",
        "missing-owner",
        "missing-key",
        "missing-retained",
        "wrong-retained-type",
    ],
)
def test_nested_document_census_and_container_ownership_are_source_bound(
    tmp_path, damage
):
    baseline, vault = bound_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    home = next(t for t in record["item_targets"] if t["item_key"] == identity(2))
    child = next(t for t in record["item_targets"] if t["item_key"] == identity(3))
    document = home["documents"][0]
    if damage == "missing-collection":
        del home["documents"]
    elif damage == "wrong-collection-type":
        home["documents"] = {}
    elif damage == "omitted":
        home["documents"] = []
    elif damage == "wrong-owner":
        home["documents"] = []
        child["documents"] = [document]
    elif damage == "asset-container":
        home["documents"] = []
        record["asset_targets"][0]["retained_documents"] = [document]
    elif damage == "duplicate":
        home["documents"].append(document.copy())
    elif damage == "extra":
        child["documents"] = [document | {"key": identity(999), "owner": identity(3)}]
    elif damage == "original-id":
        document["original_asset_id"] = identity(202)
    elif damage == "missing-owner":
        del document["owner"]
    elif damage == "missing-key":
        del document["key"]
    elif damage == "missing-retained":
        del record["asset_targets"][0]["retained_documents"]
    else:
        record["asset_targets"][0]["retained_documents"] = {}
    write_json(path, record)
    with pytest.raises(AssertionError, match="document"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "scenario,pin",
    [
        ("basic", "fee3b92c5825ad3c0226e01e147279141078304e114c80463f7686ff816e78c2"),
        ("adapted", "92f959f1a9ae7fbca935fbac0de0593aadf519a88e213fc39097c9c13941a511"),
    ],
)
def test_public_bridge_source_scenarios_are_exactly_sealed(tmp_path, scenario, pin):
    baseline = image_source_case(tmp_path, scenario=scenario)
    assert baseline.fingerprint == pin
    assert len(baseline.data["http_responses"]) == 45
    assert audit_baseline(baseline, profile_version="3")["payloads"] == 6


def test_markdown_edit_provenance_accepts_alternate_toc_segmentation(tmp_path):
    raw, adapted = ADAPTED_IMAGE_NOTES[8].values
    baseline, vault, text = adapted_note_case(tmp_path, raw, adapted, "\r\n")
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    doc = first_document(record)
    original = baseline.bytes(baseline.data["payloads"][identity(201)]["path"]).decode()
    doc["text_adaptations"] = [
        doc["text_adaptations"][0]
        | {
            "start": 0,
            "end": len(original),
            "before": original,
            "after": text,
            "adapted_start": 0,
            "adapted_end": len(text),
        }
    ]
    write_json(path, record)
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 6
