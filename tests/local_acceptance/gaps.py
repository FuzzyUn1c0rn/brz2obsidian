"""Independent absence predicates, owner joins and generated display obligations."""

import hashlib

from .facts import member
from .images import decode_image


def derive_gaps(raw, archive):
    thoughts = {t["Id"]: t for t in raw["thoughts.json"]}
    states = raw["meta.json"][0]["AttachmentFileStates"]
    raw.gaps, raw.gap_warnings, raw.image_decodes = {}, {}, {}
    for index, a in enumerate(raw["attachments.json"]):
        key, owner, kind = a["Id"], a["SourceId"], a["Type"]
        if states.get(key) != 3:
            continue
        assert type(states[key]) is int and member(a) not in archive.namelist(), (
            "raw reviewed physical absence"
        )
        assert type(a["DataLength"]) is int and a["DataLength"] >= 0, (
            "raw absent declared length"
        )
        assert (
            type(a["SourceType"]) is int
            and a["SourceType"] == 2
            and type(kind) is int
            and type(a["NoteType"]) is int
        ), "raw absent role scalars"
        assert all(
            a.get(flag, False) is False
            for flag in (
                "IsBrainAttachment",
                "IsBrainIcon",
                "IsWallpaper",
                "IsAiScriptsFile",
                "IsKeyboardShortcutsFile",
                "IsToolbarConfigFile",
            )
        ), "raw absent special role"
        note = (
            kind == 1
            and a["NoteType"] == 4
            and a["Location"] == "Notes.md"
            and a.get("IsIcon", False) is False
        )
        icon = kind == 5 and a["NoteType"] == 0 and a.get("IsIcon") is True
        role = thoughts[owner]["Kind"]
        assert note and role in {1, 2} or icon and role == 2, "raw absent reviewed role"
        assert (
            len(
                [
                    p
                    for p in raw["attachments.json"]
                    if p["SourceId"] == owner
                    and (
                        p["Type"] == 5
                        if icon
                        else p["Type"] == 1
                        and (p["NoteType"] == 4 or p["Location"] == "Notes.md")
                    )
                ]
            )
            == 1
        ), "raw absent sole declaration"
        label = (
            "ordinary_note"
            if note and role == 1
            else "definition_note"
            if note
            else "definition_icon"
        )
        rule = (
            "thebrain-format5/"
            + {
                "ordinary_note": "absent-ordinary-note-images",
                "definition_note": "absent-type-note",
                "definition_icon": "absent-type-icon",
            }[label]
            + "/v1"
        )
        pointers = [f"attachments.json:{index}", "meta.json"]
        observed = {
            "owner": owner,
            "filename": a["Location"],
            "member": member(a),
            "source_type": 2,
            "type": kind,
            "note_type": a["NoteType"],
            "state": 3,
            "declared_length": a["DataLength"],
            "present": False,
        }
        images = []
        if label == "definition_icon":
            observed["is_icon"] = True
        if label == "ordinary_note":
            candidates = sorted(
                (
                    p
                    for p in raw["attachments.json"]
                    if p["SourceId"] == owner and p["Type"] == 12
                ),
                key=lambda p: p["Id"],
            )
            assert candidates, "raw absent ordinary image basis"
            observed["images"] = []
            for image in candidates:
                image_id, name = image["Id"], member(image)
                assert (
                    type(image["SourceType"]),
                    image["SourceType"],
                    type(image["NoteType"]),
                    image["NoteType"],
                    image.get("IsIcon", False),
                ) == (int, 2, int, 0, False), "raw fallback image role"
                assert all(
                    image.get(flag, False) is False
                    for flag in (
                        "IsBrainAttachment",
                        "IsBrainIcon",
                        "IsWallpaper",
                        "IsAiScriptsFile",
                        "IsKeyboardShortcutsFile",
                        "IsToolbarConfigFile",
                    )
                ), "raw fallback image special role"
                assert (
                    type(states.get(image_id)) is int
                    and states[image_id] == 1
                    and name in archive.namelist()
                ), "raw fallback present image state"
                data = archive.read(name)
                assert (
                    type(image["DataLength"]) is int
                    and image["DataLength"] == len(data)
                    and len(data) > 0
                ), "raw fallback image integrity"
                proof = decode_image(data, image["Location"])
                raw.image_decodes[image_id] = proof
                observed["images"].append(
                    {
                        "asset_id": image_id,
                        "owner": owner,
                        "member": name,
                        "state": 1,
                        "declared_length": len(data),
                        "actual_length": len(data),
                        "actual_sha256": hashlib.sha256(data).hexdigest(),
                        "crc_valid": True,
                        **{f: proof[f] for f in ("format", "width", "height")},
                    }
                )
                pointers += [
                    f"attachments.json:{raw['attachments.json'].index(image)}",
                    "payload:" + name,
                ]
                images.append(image_id)
        raw.gaps[key] = {
            "owner": owner,
            "asset_id": key,
            "role": label,
            "rule_id": rule,
            "evidence": pointers,
        }
        raw.gap_warnings[key] = (
            "known_absent_payload",
            rule,
            "approved_source_gap",
            observed,
        )
        raw.gaps[key]["images"] = images


def diagnostic_targets(raw, names, created, icons):
    assignments = {t["Id"]: t.get("TypeId") for t in raw["thoughts.json"]}
    result, presentations = [], []
    for key, fact in sorted(raw.gaps.items()):
        owner, images = fact["owner"], fact["images"]
        icon = fact["role"] == "definition_icon"
        result.append(
            {
                "gap": {k: v for k, v in fact.items() if k != "images"},
                "owner_target": names[owner],
                "owner_created": owner in created,
                "outcome": "image_fallback"
                if images
                else "neutral_icon"
                if icon
                else "unknown_note",
                "provider_key": owner if icon else None,
                "affected_member_keys": sorted(
                    k
                    for k in created
                    if icon and assignments.get(k) == owner and not icons[k]
                ),
                "image_asset_ids": images,
            }
        )
        if images:
            presentations.append(
                {
                    "presentation": {
                        "owner": owner,
                        "source_gap_asset_id": key,
                        "kind": "note_images",
                        "image_asset_ids": images,
                        "ordering": "canonical_asset_identity",
                    },
                    "note_path": names[owner],
                }
            )
    return result, presentations
