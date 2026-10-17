"""Independent source/scope component controls and separate complete-vault controls.

Older partial vault fixtures use the explicit component-check seam. Only complete
generated fixtures call check_api_vault and can establish full-vault coverage.
"""

import hashlib

from .api_manifest import load_baseline
from .api_scope_inputs import (
    identity,
    json_bytes,
    mixed_source_packet,
    raster_scope_packet,
)


def scope_baseline(directory, case="tags"):
    """Deliver self-contained raw source facts, without a manufactured safe view."""
    return packet_baseline(directory, mixed_source_packet(case))


def raster_scope_baseline(
    directory, *, excluded=True, profile_version="3", image_format="png"
):
    """Install qualified raster wire facts without constructing generated output."""
    return packet_baseline(
        directory,
        raster_scope_packet(
            excluded=excluded,
            profile_version=profile_version,
            image_format=image_format,
        ),
    )


def packet_baseline(directory, packet):
    """Install a source-only packet and bind its complete independent file map."""
    directory.mkdir(parents=True)
    files = {}
    for name, raw in packet["files"].items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        files[name] = {"length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    data = {
        "schema": "brz2obsidian.api-acceptance/2",
        "files": files,
        **packet["baseline_inputs"],
    }
    path = directory / "manifest.json"
    raw = json_bytes(data)
    path.write_bytes(raw)
    return load_baseline(path, hashlib.sha256(raw).hexdigest())


def repin(baseline):
    import json

    data = json.loads(baseline.manifest_path.read_bytes())
    for name in data["files"]:
        raw = (baseline.manifest_path.parent / name).read_bytes()
        data["files"][name] = {
            "length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    raw = json_bytes(data)
    baseline.manifest_path.write_bytes(raw)
    return load_baseline(baseline.manifest_path, hashlib.sha256(raw).hexdigest())


def mixed_vault(directory, baseline):
    """Independent literal output construction, never a converter expectation."""
    import json

    from .api_scope_inputs import mixed_expectations, mixed_literal_documents

    directory.mkdir(parents=True)
    facts = mixed_expectations()
    literal = mixed_literal_documents()
    names = {
        identity(2): "Home.md",
        identity(3): "Notes/Child.md",
        identity(4): "Categories/Type.md",
        identity(5): "Notes/Tag.md",
        identity(6): "Notes/Empty after removal.md",
        identity(7): "Notes/Coverage parent.md",
        identity(8): "Notes/External only.md",
        identity(9): "Notes/Safe empty.md",
    }
    rows = [
        baseline.json(path)["activeThought"]
        for path in baseline.data["graphs"].values()
    ]
    rows_by_id = {row["id"]: row for row in rows}
    attachments = [
        row
        for path in baseline.data["attachment_inventories"].values()
        for row in baseline.json(path)
    ]
    roles = {
        identity(key): role
        for key, role in (
            (202, "image"),
            (203, "image"),
            (204, "image"),
            (205, "image"),
            (206, "image"),
            (207, "file"),
            (208, "file"),
            (209, "file"),
            (210, "directory"),
            (211, "url"),
            (212, "icon"),
            (301, "icon"),
            (302, "icon"),
            (401, "note_original"),
            (901, "note_original"),
        )
    }
    assets = []
    by_asset = {}
    for row in attachments:
        key = row["id"]
        if key in facts["omitted_original_ids"]:
            continue
        role = roles[key]
        external = key in facts["external"]
        absent = key == identity(208)
        present = not external and not absent
        raw = (
            baseline.bytes(baseline.data["payloads"][key]["path"]) if present else None
        )
        filename = row["location"]
        if role == "icon":
            filename = key + "/Icon.png"
        elif role == "note_original":
            filename = key + "/Notes.md"
        relative = "Attachments/" + filename if present else None
        resource = relative if key in {identity(206), identity(207)} else None
        example = facts["external"].get(key)
        value = {
            "asset_id": key,
            "owner": row["sourceId"],
            "role": role,
            "availability": "external"
            if external
            else "absent"
            if absent
            else "present",
            "relative_path": relative,
            "resource_link": example["uri"] if external else resource,
            "original_name": row["name"] or row["location"]
            if role == "url"
            else row["location"],
            "display_name": example["display"] if external else row["name"],
            "actual_length": len(raw) if present else None,
            "actual_sha256": hashlib.sha256(raw).hexdigest() if present else None,
            "external_uri": example["uri"] if external else None,
            "retained_documents": [],
        }
        assets.append(value)
        by_asset[key] = value
        if present:
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    documents = {}
    for key, owner in ((201, 2), (401, 3), (601, 6), (901, 9)):
        body = facts["adapted_notes"][identity(key)]
        refs = []
        if key == 201:
            for row in literal["references"]:
                item = row["kind"] == "item"
                start, end = row["destination_start"], row["destination_end"]
                normalization = None
                if row["target"] == identity(205):
                    pos = start + row["source_target"].index("#")
                    normalization = {
                        "declaration": "#$width=50p$",
                        "start": pos,
                        "end": end,
                        "document_digest": literal["text_digest"],
                        "basis": "document.text/unicode_codepoints",
                        "presentation": "responsive",
                    }
                refs.append(
                    row
                    | {
                        "document_digest": literal["text_digest"],
                        "destination_start": None if item else start,
                        "destination_end": None if item else end,
                        "presentation_normalization": normalization,
                    }
                )
        documents[identity(owner)] = {
            "key": identity(key),
            "owner": identity(owner),
            "original_asset_id": None if key in {201, 601} else identity(key),
            "original_copy_omitted": key in {201, 601},
            "text_digest": hashlib.sha256(body.encode()).hexdigest(),
            "owner_target": names[identity(owner)],
            "references": refs,
            "text_adaptations": literal["text_adaptations"] if key == 201 else [],
            "evidence": ["attachment:" + identity(key)],
        }
    targets = []
    for row in rows:
        key = row["id"]
        provider = identity(4) if key == identity(3) else None
        explicit = {
            identity(2): identity(212),
            identity(3): identity(302),
            identity(4): identity(301),
        }.get(key)
        created = facts["created"][key]
        target = {
            "item_key": key,
            "original_identity": key,
            "original_title": row["name"],
            "relative_path": names[key],
            "created": created,
            "documents": [documents[key]] if key in documents else [],
            "declared_appearance": {
                "foreground_color": row["foregroundColor"],
                "background_color": row["backgroundColor"],
                "icon_asset_id": explicit,
            }
            if explicit or row["foregroundColor"] or row["backgroundColor"]
            else None,
            "icon_snapshot": {
                "item_key": key,
                "explicit_icon_asset_id": explicit,
                "appearance_category_key": provider,
                "effective_icon_asset_id": explicit,
            }
            if created
            else None,
        }
        targets.append(target)
        if not created:
            continue
        icon = (
            json.dumps("[[" + by_asset[explicit]["relative_path"] + "]]")
            if explicit
            else ""
        )
        category = json.dumps("[[Categories/Type.md]]") if provider else ""
        text = (
            "---\nicon:"
            + (" " + icon if icon else "")
            + "\nappearance_category:"
            + (" " + category if category else "")
            + "\n---\n\n# "
            + row["name"]
            + "\n\n"
        )
        tags = (
            ["categories"]
            if key == identity(4)
            else ["Tag"]
            if key == identity(3) and identity(5) in rows_by_id
            else []
        )
        categories = ["[[Categories/Type.md]]"] if provider else []
        properties = {
            "categories": categories,
            "tags": tags,
            "aliases": [],
            "created": "2026-09-13",
            "updated": "2026-10-02",
            "source_collection_id": identity(1),
            "source_item_id": key,
        }
        prefix = "".join(
            name + ": " + json.dumps(value, ensure_ascii=False) + "\n"
            for name, value in properties.items()
        )
        text = text.replace("---\n", "---\n" + prefix, 1)
        if explicit and row["kind"] != 2:
            text += "![[" + by_asset[explicit]["relative_path"] + "]]\n\n"
        if key == identity(2):
            text += (
                literal["display_text"]
                + "\n## Resources\n\n- [[Attachments/"
                + identity(206)
                + ".svg|"
                + identity(206)
                + ".svg]]\n- [[Attachments/manual.pdf|manual.pdf]]\n- Absent source file: manual.txt (metadata retained; bytes absent from the source).\n\n"
            )
            text += "## Children\n\n- [[Notes/Child.md|Child]]\n- [[Notes/Coverage parent.md|Coverage parent]]\n\n## Related\n\n- [[Notes/Child.md|Child]]\n"
        elif key == identity(3):
            text += "Child authored body.\n\n## Parents\n\n- [[Home.md|Home]]\n\n## Related\n\n- [[Home.md|Home]]\n"
        elif key == identity(7):
            text += "## Parents\n\n- [[Home.md|Home]]\n\n## Children\n\n- [[Notes/Empty after removal.md|Empty after removal]]\n"
        elif key == identity(8):
            text += (
                "## Resources\n\n"
                + "\n".join(
                    "- ["
                    + facts["external"][identity(k)]["label"]
                    + "](<"
                    + facts["external"][identity(k)]["uri"]
                    + ">)"
                    for k in (209, 210, 211)
                )
                + "\n"
            )
        path = directory / names[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf8")
    links = [
        baseline.json(value["path"])
        for value in baseline.data["relationship_metadata"].values()
    ]
    relationships = [
        {
            "key": row["id"],
            "item_a": row["thoughtIdA"],
            "item_b": row["thoughtIdB"],
            "kind": "classification"
            if row["meaning"] == 2
            else "tag"
            if row["meaning"] == 5
            else "hierarchy"
            if row["relation"] == 1
            else "related",
        }
        for row in links
    ]
    minimal = []
    for field, names_ in (
        ("excluded_thoughts", ("id", "brainId", "kind", "acType", "forgottenDateTime")),
        ("excluded_relationships", ("id", "brainId", "thoughtIdA", "thoughtIdB")),
    ):
        minimal.extend(
            {k: baseline.json(v["path"])[k] for k in names_}
            for v in baseline.data["scope_inputs"][field].values()
        )
    record = {
        "source_identity": {
            "module_id": "thebrain-local-api",
            "module_version": "1",
            "format_version": "1",
            "source_id": identity(1),
        },
        "profile_id": "thebrain-local-api-reviewed",
        "profile_version": "3",
        "item_targets": targets,
        "asset_targets": assets,
        "relationships": relationships,
        "classification_assignments": [
            {
                "relationship_key": identity(104),
                "definition_key": identity(4),
                "item_key": identity(3),
            }
        ],
        "tag_memberships": [
            {
                "relationship_key": identity(105),
                "tag_key": identity(5),
                "item_key": identity(3),
            }
        ]
        if identity(5) in rows_by_id
        else [],
        "issues": [
            {
                "rule_id": "local-api.missing-txt-pdf.v1",
                "code": "approved_source_gap",
                "severity": "warning",
                "affected": [identity(208)],
            }
        ],
        "original_evidence": [
            {
                "records": rows
                + links
                + [
                    dict(a, position={"decimal": str(a["position"])})
                    for a in attachments
                ]
                + minimal
            }
        ],
    }
    record["tag_memberships"] = (
        [
            {
                "relationship_key": identity(105),
                "tag_key": identity(5),
                "item_key": identity(3),
                "native": True,
                "tag_name": "Tag",
                "token": "Tag",
                "tag_original_identity": identity(5),
                "tag_target": names[identity(5)],
                "item_target": names[identity(3)],
                "evidence": ["link:" + identity(105)],
                "listing_path": None,
            }
        ]
        if identity(5) in rows_by_id
        else []
    )
    record["classification_assignments"][0].update(
        evidence=[
            "link:" + identity(104),
            "thought:" + identity(3),
            "thought:" + identity(4),
        ],
        definition_target=names[identity(4)],
        item_target=names[identity(3)],
    )
    record = complete_scope_record(baseline, record)
    (directory / "migration-record.json").write_bytes(json_bytes(record))
    return directory


def complete_scope_record(baseline, record):
    """Literal source-record/accounting expectations for this independently authored packet."""
    from .api_scope_inputs import mixed_expectations

    data = baseline.data
    literal = mixed_expectations()
    expected = {"brain:" + identity(1): baseline.json(data["brain"])}
    for key, path in data["graphs"].items():
        expected["thought:" + key] = baseline.json(path)["activeThought"]
    for key, value in data["relationship_metadata"].items():
        expected["link:" + key] = baseline.json(value["path"])
    for path in data["attachment_inventories"].values():
        for row in baseline.json(path):
            expected["attachment:" + row["id"]] = dict(
                row, position={"decimal": str(row["position"])}
            )
    for owner, path in data["no_notes"].items():
        expected["no_note:" + owner] = baseline.json(path)
    for when, path in zip(("start", "end"), data["statistics"], strict=True):
        expected["statistics:" + when] = {
            key: value for key, value in baseline.json(path).items() if key != "brainId"
        }
    for key, value in data["scope_inputs"]["excluded_thoughts"].items():
        raw = baseline.json(value["path"])
        expected["exclusion:" + key] = {
            field: raw[field]
            for field in ("id", "brainId", "kind", "acType", "forgottenDateTime")
        }
        decision = {
            "key": "scope:excluded:" + key,
            "rule_id": "local-api.system.v1"
            if key == identity(90)
            else "local-api.forgotten.v1",
            "outcome": "excluded_system"
            if key == identity(90)
            else "excluded_forgotten",
            "subjects": ["thought:" + key],
            "evidence": ["exclusion:" + key],
        }
        expected[decision["key"]] = decision
    for key, value in data["scope_inputs"]["excluded_relationships"].items():
        raw = baseline.json(value["path"])
        expected["link:" + key] = {
            field: raw[field] for field in ("id", "brainId", "thoughtIdA", "thoughtIdB")
        }
        excluded = identity(90) if key == identity(190) else identity(91)
        decision = {
            "key": "scope:association:" + key,
            "rule_id": "local-api.system.v1"
            if key == identity(190)
            else "local-api.forgotten.v1",
            "outcome": "excluded_association",
            "subjects": [
                "link:" + key,
                "thought:" + identity(2),
                "thought:" + excluded,
            ],
            "evidence": ["link:" + key, "exclusion:" + excluded],
        }
        expected[decision["key"]] = decision
    # Each adjacency/incident relation list is a separately worked literal join.
    adjacency = {
        2: (
            [],
            [3, 7],
            [3],
            [],
            [],
            [],
            [101, 102, 103, 106],
            [201, 202, 203, 204, 205, 206, 207, 208, 212],
        ),
        3: ([2], [], [2], [], [5], [4], [101, 102, 103, 104, 105], [302, 401]),
        4: ([], [3], [], [], [], [], [104], [301]),
        5: ([], [3], [], [], [], [], [105], []),
        6: ([7], [], [], [], [], [], [107], [601]),
        7: ([2], [6], [], [], [], [], [106, 107], []),
        8: ([], [], [], [], [], [], [], [209, 210, 211]),
        9: ([], [], [], [], [], [], [], [901]),
    }
    for owner, path in data["graphs"].items():
        values = adjacency[int(owner[-12:])]
        graph = {
            field: [
                identity(i)
                for i in numbers
                if identity(i) in data["scope"]["thought_ids"]
                or field in {"link_ids", "attachment_ids"}
            ]
            for field, numbers in zip(
                (
                    "parents_ids",
                    "children_ids",
                    "jump_ids",
                    "sibling_ids",
                    "tag_ids",
                    "type_ids",
                    "link_ids",
                    "attachment_ids",
                ),
                values,
                strict=True,
            )
        }
        graph["link_ids"] = [
            key for key in graph["link_ids"] if key in data["scope"]["relationship_ids"]
        ]
        expected["graph:" + owner] = graph
        decision = {
            "key": "scope:included:" + owner,
            "rule_id": "local-api.roles-access.v1",
            "outcome": "included",
            "subjects": ["thought:" + owner],
            "evidence": ["thought:" + owner],
        }
        expected[decision["key"]] = decision
    for note, owner in ((201, 2), (401, 3), (601, 6), (901, 9)):
        expected["note_text:" + identity(owner)] = {
            "text": literal["safe_notes"][identity(note)]
        }
        if note in {201, 601}:
            removed = [identity(90), identity(91)] if note == 201 else [identity(91)]
            decision = {
                "key": "scope:note:" + identity(note),
                "rule_id": "local-api.system.v1"
                if note == 201
                else "local-api.forgotten.v1",
                "outcome": "excluded_association",
                "subjects": ["thought:" + identity(owner)]
                + ["thought:" + key for key in removed],
                "evidence": ["note_text:" + identity(owner)]
                + ["exclusion:" + key for key in removed],
            }
            expected[decision["key"]] = decision
    key = "scope:missing-txt404:" + identity(208)
    expected[key] = {
        "key": key,
        "rule_id": "local-api.missing-txt-pdf.v1",
        "outcome": "missing_txt404",
        "subjects": ["attachment:" + identity(207), "attachment:" + identity(208)],
        "evidence": [
            "attachment:" + identity(207),
            "attachment:" + identity(208),
            "payload:" + identity(207),
            "payload:" + identity(208),
        ],
    }
    if data["tags"]["status"] == 400:
        key = "scope:tag400-zero:" + identity(1)
        expected[key] = {
            "key": key,
            "rule_id": "local-api.tag400.v1",
            "outcome": "tag400_zero",
            "subjects": ["brain:" + identity(1)],
            "evidence": ["inventory:tag_ids", "statistics:end", "statistics:start"],
        }
    # Source scope decisions use canonical unique logical-key sets; authored
    # arrays, Document references and edit sequences retain their own order.
    for key, value in expected.items():
        if key.startswith("scope:"):
            for field in ("subjects", "evidence"):
                value[field] = sorted(set(value[field]))
    record["original_evidence"] = [
        {"key": key, "kind": "records", "records": value}
        for key, value in sorted(expected.items())
    ]
    normalized = {
        **{"thought:" + key: [key] for key in data["graphs"]},
        **{"link:" + key: [key] for key in data["scope"]["relationship_ids"]},
        **{"attachment:" + key: [key] for key in literal["retained_asset_ids"]},
        **{
            "note_text:" + identity(owner): [identity(note)]
            for note, owner in ((201, 2), (401, 3), (601, 6), (901, 9))
        },
    }
    record["source_accounting"] = {
        "entries": [
            {
                "identity": key,
                "disposition": "normalized" if key in normalized else "retained_only",
                "references": normalized.get(key, [key]),
            }
            for key in sorted(expected)
        ]
    }
    return record


def raster_scope_case(
    directory,
    *,
    excluded=True,
    profile="3",
    image_format="png",
    source_prefix=None,
    display_prefix=None,
):
    """Independent literal inherited-PNG source and output, without runtime imports."""
    import json

    baseline = raster_scope_baseline(
        directory / "source",
        excluded=excluded,
        profile_version=profile,
        image_format=image_format,
    )
    if source_prefix is not None:
        note_id = identity(201)
        payload = baseline.data["payloads"][note_id]["path"]
        raw = baseline.bytes(payload).replace(
            "Kept Ω.".encode(), source_prefix.encode("utf8"), 1
        )
        (baseline.manifest_path.parent / payload).write_bytes(raw)

        def update(row):
            if isinstance(row, dict):
                if row.get("id") == note_id and "dataLength" in row:
                    row["dataLength"] = len(raw)
                for child in row.values():
                    update(child)
            elif isinstance(row, list):
                for child in row:
                    update(child)

        for relative in baseline.data["files"]:
            if (
                relative.startswith("responses/")
                and relative.endswith(".json")
                and relative != baseline.data["tags"]["path"]
            ):
                row = baseline.json(relative)
                update(row)
                (baseline.manifest_path.parent / relative).write_bytes(json_bytes(row))
        baseline = repin(baseline)
    data = baseline.data
    vault = directory / "vault"
    vault.mkdir()
    home, child, note, image = map(identity, (2, 3, 201, 202))
    prose = "Kept Ω." if source_prefix is None else source_prefix
    original_safe = (
        prose + "\r\n![Pixel](.data/md-images/" + image + "." + image_format + ")\r\n"
    )
    displayed = prose if display_prefix is None else display_prefix
    safe = (
        displayed
        + "\r\n![Pixel](.data/md-images/"
        + image
        + "."
        + image_format
        + ")\r\n"
    )
    phrase, destination = (
        "![Pixel](.data/md-images/" + image + "." + image_format + ")",
        ".data/md-images/" + image + "." + image_format,
    )
    begin, start = safe.index(phrase), safe.index(destination)
    digest = hashlib.sha256(safe.encode()).hexdigest()
    document = {
        "key": note,
        "owner": home,
        "text_digest": digest,
        "original_asset_id": None if excluded else note,
        "original_copy_omitted": excluded,
        "owner_target": "Home.md",
        "text_adaptations": [],
        "evidence": ["attachment:" + note],
        "references": [
            {
                "start": begin,
                "end": begin + len(phrase),
                "expected_original": phrase,
                "kind": "image",
                "target": image,
                "display_text": "Pixel",
                "table_cell": False,
                "document_digest": digest,
                "source_target": destination,
                "destination_start": start,
                "destination_end": start + len(destination),
                "presentation_normalization": None,
            }
        ],
    }
    if display_prefix is not None:
        document["text_adaptations"] = [
            {
                "kind": "markdown_insert",
                "start": 0,
                "end": len(prose),
                "before": prose,
                "after": display_prefix,
                "adapted_start": 0,
                "adapted_end": len(display_prefix),
                "source_digest": hashlib.sha256(original_safe.encode()).hexdigest(),
                "source_basis": "scoped_source_text/unicode_codepoints",
                "adapted_basis": "document.text/unicode_codepoints",
            }
        ]
    targets = [
        {
            "item_key": key,
            "original_identity": key,
            "original_title": title,
            "relative_path": name,
            "created": key == home,
            "documents": [document] if key == home else [],
            "declared_appearance": None,
            "icon_snapshot": {
                "item_key": home,
                "explicit_icon_asset_id": None,
                "appearance_category_key": None,
                "effective_icon_asset_id": None,
            }
            if key == home
            else None,
        }
        for key, title, name in (
            (home, "Home", "Home.md"),
            (child, "Child", "Notes/Child.md"),
        )
    ]
    assets = []
    for key, role, location in (
        (note, "note_original", "Notes.md"),
        (image, "image", image + "." + image_format),
    ):
        if excluded and key == note:
            continue
        raw = baseline.bytes(data["payloads"][key]["path"])
        path = "Attachments/" + (note + "/Notes.md" if key == note else location)
        target = vault / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        assets.append(
            {
                "asset_id": key,
                "owner": home,
                "role": role,
                "availability": "present",
                "relative_path": path,
                "resource_link": None,
                "original_name": location,
                "display_name": None,
                "actual_length": len(raw),
                "actual_sha256": hashlib.sha256(raw).hexdigest(),
                "external_uri": None,
                "retained_documents": [],
            }
        )
    evidence, accounting = [], []

    def retain(key, value, references=None):
        evidence.append({"key": key, "kind": "records", "records": value})
        accounting.append(
            {
                "identity": key,
                "disposition": "normalized" if references else "retained_only",
                "references": references or [key],
            }
        )

    def decision(key, rule, outcome, subjects, pointers):
        retain(
            key,
            {
                "key": key,
                "rule_id": rule,
                "outcome": outcome,
                "subjects": sorted(set(subjects)),
                "evidence": sorted(set(pointers)),
            },
        )

    retain("brain:" + identity(1), baseline.json(data["brain"]))
    for key, path in data["graphs"].items():
        retain("thought:" + key, baseline.json(path)["activeThought"], [key])
        retain(
            "graph:" + key,
            {
                "parents_ids": [home] if key == child else [],
                "children_ids": [child] if key == home else [],
                "jump_ids": [child if key == home else home],
                "sibling_ids": [],
                "tag_ids": [],
                "type_ids": [],
                "link_ids": [identity(i) for i in (101, 102, 103)],
                "attachment_ids": [note, image] if key == home else [],
            },
        )
        decision(
            "scope:included:" + key,
            "local-api.roles-access.v1",
            "included",
            ["thought:" + key],
            ["thought:" + key],
        )
    for key, value in data["relationship_metadata"].items():
        retain("link:" + key, baseline.json(value["path"]), [key])
    for key, value in data["attachment_metadata"].items():
        row = baseline.json(value["path"])
        retain(
            "attachment:" + key,
            dict(row, position={"decimal": str(row["position"])}),
            None if excluded and key == note else [key],
        )
    retain("note_text:" + home, {"text": original_safe}, [note])
    retain("no_note:" + child, baseline.json(data["no_notes"][child]))
    for when, path in zip(("start", "end"), data["statistics"], strict=True):
        retain(
            "statistics:" + when,
            {k: v for k, v in baseline.json(path).items() if k != "brainId"},
        )
    decision(
        "scope:tag400-zero:" + identity(1),
        "local-api.tag400.v1",
        "tag400_zero",
        ["brain:" + identity(1)],
        ["inventory:tag_ids", "statistics:end", "statistics:start"],
    )
    if excluded:
        key, link = identity(91), identity(191)
        row = baseline.json(data["scope_inputs"]["excluded_thoughts"][key]["path"])
        retain(
            "exclusion:" + key,
            {
                field: row[field]
                for field in ("id", "brainId", "kind", "acType", "forgottenDateTime")
            },
        )
        decision(
            "scope:excluded:" + key,
            "local-api.forgotten.v1",
            "excluded_forgotten",
            ["thought:" + key],
            ["exclusion:" + key],
        )
        retain(
            "link:" + link,
            {"id": link, "brainId": identity(1), "thoughtIdA": home, "thoughtIdB": key},
        )
        decision(
            "scope:association:" + link,
            "local-api.forgotten.v1",
            "excluded_association",
            ["link:" + link, "thought:" + home, "thought:" + key],
            ["link:" + link, "exclusion:" + key],
        )
        decision(
            "scope:note:" + note,
            "local-api.forgotten.v1",
            "excluded_association",
            ["thought:" + home, "thought:" + key],
            ["note_text:" + home, "exclusion:" + key],
        )
    record = {
        "source_identity": {
            "module_id": "thebrain-local-api",
            "module_version": "1",
            "format_version": "1",
            "source_id": identity(1),
        },
        "profile_id": "thebrain-local-api-reviewed",
        "profile_version": profile,
        "item_targets": targets,
        "asset_targets": assets,
        "relationships": [
            {"key": identity(i), "item_a": home, "item_b": child, "kind": kind}
            for i, kind in ((101, "hierarchy"), (102, "related"), (103, "related"))
        ],
        "classification_assignments": [],
        "tag_memberships": [],
        "issues": [],
        "original_evidence": evidence,
        "source_accounting": {"entries": accounting},
    }
    (vault / "migration-record.json").write_bytes(json_bytes(record))
    properties = {
        "categories": [],
        "icon": None,
        "appearance_category": None,
        "tags": [],
        "aliases": [],
        "created": "2026-09-13",
        "updated": "2026-10-02",
        "source_collection_id": identity(1),
        "source_item_id": home,
    }
    text = (
        "---\n"
        + "".join(
            k + ":" + (" " + json.dumps(v) if v is not None else "") + "\n"
            for k, v in properties.items()
        )
        + "---\n\n# Home\n\n"
    )
    text += (
        displayed.replace("\r\n", "\n").replace("\r", "\n")
        + "\n![Pixel](Attachments/"
        + image
        + "."
        + image_format
        + ")\n\n## Children\n\n- [[Notes/Child.md|Child]]\n\n## Related\n\n- [[Notes/Child.md|Child]]\n"
    )
    (vault / "Home.md").write_text(text, encoding="utf8")
    return baseline, vault


def complete_raster_support(baseline, vault):
    """Independent full support input: one Home, one image, no optional listing.

    Stock input prose is the separately qualified source-free GP05 reference.
    Source cardinalities below are worked literals for RAW02 scoped PNG.
    No checker/generated-proof function constructs this checked object.
    """
    import json

    from .api_generated import STATIC
    from .support import CATEGORY_VIEWS, image_formula, template

    files = {}
    for role in ("members", "gallery", "categories"):
        if role == "categories":
            formulas = {
                "local_icon": image_formula("icon"),
                "picture": "if(formula.local_icon, image(formula.local_icon.asFile()), null)",
            }
            head = 'filters:\n  and:\n    - file.ext == "md"\n    - file.inFolder("Categories")\n    - list(tags).contains("categories")\n'
            properties = "properties:\n  formula.picture:\n    displayName: Icon\n  file.name:\n    displayName: Category\n"
            view = "views:\n  - type: table\n    name: Categories\n    order:\n      - formula.picture\n      - file.name\n"
        else:
            formulas = {
                "provider": 'if(appearance_category.isEmpty(), null, if(appearance_category.isType("link") && list(categories).contains(appearance_category) && appearance_category.asFile() && appearance_category.asFile().ext == "md" && appearance_category.asFile().inFolder("Categories") && list(appearance_category.asFile().properties.tags).contains("categories"), appearance_category.asFile(), null))',
                "explicit_icon": image_formula("icon"),
                "provider_icon": "if(formula.provider, formula.provider.properties.icon, null)",
                "inherited_icon": image_formula("formula.provider_icon"),
                "effective_icon": "if(formula.explicit_icon, formula.explicit_icon, formula.inherited_icon)",
                "picture": "if(formula.effective_icon, image(formula.effective_icon.asFile()), null)",
                "provider_status": 'if(appearance_category.isEmpty(), "No inheritance", if(formula.provider, "Category defaults", "Invalid provider"))',
            }
            head = 'filters:\n  and:\n    - file.ext == "md"\n    - \'!file.inFolder("Templates")\'\n    - \'!file.inFolder("Attachments")\'\n    - list(categories).contains(this)\n'
            properties = "properties:\n  formula.picture:\n    displayName: Icon\n  file.name:\n    displayName: Note\n  formula.provider_status:\n    displayName: Inheritance\n"
            view = (
                "views:\n  - type: cards\n    name: Gallery\n    image: formula.effective_icon\n    imageFit: contain\n    imageAspectRatio: 0.4\n    cardSize: 230\n    order:\n      - file.name\n      - formula.provider_status\n"
                if role == "gallery"
                else "views:\n  - type: table\n    name: Members\n    order:\n      - formula.picture\n      - file.name\n      - formula.provider_status\n      - note.categories\n      - note.created\n      - note.updated\n"
            )
        content = (
            head
            + "formulas:\n"
            + "".join(
                "  " + key + ": '" + value + "'\n" for key, value in formulas.items()
            )
            + properties
            + view
            + "    sort:\n      - property: file.name\n        direction: ASC\n"
        )
        files["Templates/Bases/" + role.title() + ".base"] = content
    files["Templates/Bases/Starter.base"] = files["Templates/Bases/Members.base"]
    files["Templates/New note.md"] = template()
    files["Templates/Category starter.md"] = (
        template(role_tag=True) + "\n" + CATEGORY_VIEWS
    )
    files["Templates/Member template starter.md"] = (
        template()
        + "\n<!-- Duplicate this as a full template, then set categories and appearance_category to your existing category. Keep the date/title variables for insertion into a new note. See Vault guide. -->\n"
    )
    files["Categories.md"] = "# Categories\n\n![[Templates/Bases/Categories.base]]\n"
    files["Vault guide.md"] = (
        STATIC["GP05-GUIDE-00"] + STATIC["GP05-GUIDE-02"] + STATIC["GP05-GUIDE-03"]
    )
    files["MIGRATION REPORT.md"] = (
        STATIC["GP05-REPORT-00"]
        + "Created 1 thought notes; preserved 1 present payloads.\n\n"
        + STATIC["GP05-REPORT-01"]
        + STATIC["GP05-REPORT-02"]
        + STATIC["GP05-REPORT-03"]
        + STATIC["GP05-REPORT-12"]
    )
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record.update(
        schema="brz2obsidian.migration",
        schema_version=7,
        converter_version="0.1.0",
        renderer_version="7",
    )
    record["run_metadata"] = {
        "converter_version": "0.1.0",
        "renderer_version": "7",
        "run_id": "aaaaaaaa-0000-4000-8000-000000000001",
        "run_time": "2026-10-16T12:00:00+00:00",
        "obsidian_version": "1.13.7",
        "bookmark_time": 1792152000000,
    }
    record["run_metadata"]["source_acquisition"] = {
        "integrity_sha256": "a" * 64,
        "audit": {
            "atomic": False,
            "method": "bounded-read-only-local-api",
            "started_at": "2026-10-16T11:59:00.000000Z",
            "finished_at": "2026-10-16T11:59:01.000000Z",
            "limits": {
                "initial_search_results": 5000,
                "search_budget_ms": 300000,
                "search_max_response_bytes": 128000000,
                "max_search_results": None,
                "request_timeout_ms": 30000,
                "max_response_bytes": 16000000,
                "max_total_capture_bytes": 1000000000,
                "max_requests": 100000,
                "max_traversal_items": 100000,
                "max_payload_bytes": 256000000,
            },
            "requests": [
                {
                    "sequence": 1,
                    "operation": "brain",
                    "brain_id": identity(1),
                    "subject_id": identity(1),
                    "status": 200,
                    "outcome": "success",
                    "started_at": "2026-10-16T11:59:00.100000Z",
                    "finished_at": "2026-10-16T11:59:00.200000Z",
                    "actual_length": len(baseline.bytes(baseline.data["brain"])),
                }
            ],
            "consistency_limits": [
                "non-atomic-multi-request",
                "captured-copy-integrity-only",
                "empirical-discovery-no-completeness-guarantee",
            ],
        },
    }
    record["source_identity"].update(source_sha256="a" * 64, snapshot_digest="b" * 64)
    configs = {
        ".obsidian/app.json": (
            "obsidian_configuration",
            {
                "showInlineTitle": False,
                "defaultViewMode": "preview",
                "newFileLocation": "folder",
                "newFileFolderPath": "Notes",
                "useMarkdownLinks": False,
                "newLinkFormat": "absolute",
                "openBehavior": "file:Home.md",
                "alwaysUpdateLinks": True,
                "attachmentFolderPath": "Attachments",
            },
        ),
        ".obsidian/core-plugins.json": (
            "obsidian_core_plugins_configuration",
            dict.fromkeys(
                (
                    "file-explorer",
                    "global-search",
                    "switcher",
                    "graph",
                    "backlink",
                    "tag-pane",
                    "page-preview",
                    "command-palette",
                    "bookmarks",
                    "properties",
                    "bases",
                    "templates",
                ),
                True,
            ),
        ),
        ".obsidian/templates.json": (
            "obsidian_templates_configuration",
            {"folder": "Templates", "dateFormat": "YYYY-MM-DD"},
        ),
        ".obsidian/types.json": (
            "obsidian_property_types_configuration",
            {
                "types": {
                    "categories": "multitext",
                    "appearance_category": "text",
                    "icon": "text",
                    "created": "date",
                    "updated": "date",
                    "tags": "tags",
                    "aliases": "aliases",
                    "source_collection_id": "text",
                    "source_item_id": "text",
                }
            },
        ),
    }
    for name, (field, value) in configs.items():
        files[name] = json.dumps(value) + "\n"
        record[field] = value
    files[".obsidian/bookmarks.json"] = (
        json.dumps(
            {
                "items": [
                    {
                        "type": "file",
                        "ctime": 1792152000000,
                        "path": "Home.md",
                        "title": "Home",
                    }
                ]
            }
        )
        + "\n"
    )
    purposes = {
        name: "configuration"
        if name.startswith(".obsidian/")
        else "report"
        if name == "MIGRATION REPORT.md"
        else "overview"
        if name == "Categories.md"
        else "guide"
        if name == "Vault guide.md"
        else "starter"
        if "starter" in name.lower()
        else "base"
        if name.endswith(".base")
        else "template"
        for name in files
    }
    purposes["migration-record.json"] = "migration_record"
    record["support_artifacts"] = [
        {"relative_path": name, "purpose": purpose}
        for name, purpose in purposes.items()
    ]
    record["reserved_support_paths"] = ["Uncreated targets.md", "Tag memberships.md"]
    record["source_gaps"] = []
    record["generated_presentations"] = []
    for target in record["item_targets"]:
        key = target["item_key"]
        target.update(
            creation_reasons=["content", "home"] if key == identity(2) else [],
            calendar_dates={"created": "2026-09-13", "updated": "2026-10-02"},
            metadata_evidence=["thought:" + key],
            vault_tag_token=None,
        )
    for asset in record["asset_targets"]:
        asset.update(
            naming_seed=asset["asset_id"].replace("-", ""),
            evidence=["attachment:" + asset["asset_id"]],
            video_presentation=None,
            source_findings=[],
        )
    for relation in record["relationships"]:
        relation.update(
            target_a="Home.md",
            target_b="Notes/Child.md",
            evidence=["link:" + relation["key"]],
            presentation="Parents/Children"
            if relation["kind"] == "hierarchy"
            else "Related",
        )
    record["adaptations"] = []
    for kind, affected, description in (
        (
            "native_templates_configuration",
            ".obsidian/templates.json",
            STATIC["GP07-DESCRIPTION-19"],
        ),
        ("vault_maintenance_guide", "Vault guide.md", STATIC["GP07-DESCRIPTION-20"]),
        ("categories_overview", identity(2), STATIC["GP07-DESCRIPTION-21"]),
        (
            "native_bases_configuration",
            ".obsidian/core-plugins.json",
            STATIC["GP07-DESCRIPTION-22"],
        ),
        ("canonical_properties", identity(2), STATIC["GP07-DESCRIPTION-16"]),
        ("source_calendar_dates", identity(2), STATIC["GP07-DESCRIPTION-14"]),
        (
            "image_reference",
            "reference:" + identity(201) + ":0",
            "Inline source reference resolves to canonical "
            + identity(202)
            + "; original display and syntax remain in document evidence.",
        ),
        *(
            (
                "relationship_presentation",
                identity(key),
                "Simple "
                + label
                + " links; original source arrow and visibility details remain in evidence.",
            )
            for key, label in (
                (101, "Parents/Children"),
                (102, "Related"),
                (103, "Related"),
            )
        ),
    ):
        record["adaptations"].append(
            {
                "kind": kind,
                "affected": affected,
                "description": description,
                "document_key": None,
                "owner": None,
                "evidence": [],
                "text_edit": None,
            }
        )
    record["counts"] = {
        "image_presentation_normalizations": 0,
        "text_adaptations": 0,
        "source_gaps": 0,
        "generated_presentations": 0,
        "planned_generated_embeds": 0,
        "actual_generated_embeds": 0,
        "source_items": 2,
        "source_relationships": 3,
        "source_references": 1,
        "present_assets": 1,
        "planned_notes": 1,
        "planned_assets": 1,
        "planned_references": 1,
        "actual_notes": None,
        "actual_assets": None,
        "actual_files": None,
        "actual_references": 1,
        "source_tags": 0,
        "tag_memberships": 0,
        "native_tag_memberships": 0,
        "uncreated_tag_memberships": 0,
        "created_tag_items": 0,
        "uncreated_tag_items": 0,
        "source_definitions": 0,
        "classification_assignments": 0,
        "typed_members": 0,
        "planned_category_notes": 0,
        "actual_category_notes": None,
        "planned_support_files": 16,
        "actual_support_files": None,
    }
    for name, text in files.items():
        output = vault / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf8", newline="\n")
    path.write_bytes(json_bytes(record))
    return baseline, vault
