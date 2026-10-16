"""Independent source/scope component controls and separate complete-vault controls.

Older partial vault fixtures use the explicit component-check seam. Only complete
generated fixtures call check_api_vault and can establish full-vault coverage.
"""

import hashlib

import pytest

from .api_checker import audit_baseline, expected_asset
from .api_manifest import load_baseline
from .api_scope_inputs import (
    identity,
    json_bytes,
    mixed_expectations,
    mixed_source_packet,
    negative_mixed_source_packet,
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


@pytest.mark.parametrize(
    "case",
    [
        "forgotten-invalid-calendar",
        "relationship-contradictory-repeat",
        "resource-unsupported-type",
        "external-traversal",
        "note-unresolved-thought",
        "jpeg-premature-entropy",
    ],
)
def test_qualified_negative_mixed_source_refuses_at_public_audit(tmp_path, case):
    baseline = packet_baseline(tmp_path / "source", negative_mixed_source_packet(case))
    with pytest.raises(AssertionError):
        audit_baseline(baseline, profile_version="3")


@pytest.mark.parametrize("key", [201, 601])
def test_raw_successful_scoped_note_is_not_a_retained_asset(tmp_path, key):
    baseline = scope_baseline(tmp_path / "source")
    row = baseline.json(baseline.data["attachment_metadata"][identity(key)]["path"])
    assert baseline.data["payloads"][identity(key)]["status"] == 200
    with pytest.raises(AssertionError, match="scoped original has no retained Asset"):
        expected_asset(baseline, row, "3")


@pytest.mark.parametrize("case", ["tags", "zero-tags", "changed-svg"])
def test_mixed_scope_audit_derives_retention_from_raw_reads(tmp_path, case):
    baseline = scope_baseline(tmp_path / "source", case)
    result = audit_baseline(baseline, profile_version="3")
    literal = mixed_expectations()
    assert result["thoughts"] == (7 if case == "zero-tags" else 8)
    assert result["relationships"] == (6 if case == "zero-tags" else 7)
    assert (result["attachments"], result["payloads"], result["reviewed_gaps"]) == (
        17,
        11,
        1,
    )
    assert result["retention"] == {
        field: literal[field]
        for field in (
            "omitted_original_ids",
            "retained_asset_ids",
            "openable_payload_ids",
        )
    }


@pytest.mark.parametrize("key", [203, 302])
@pytest.mark.parametrize("entry", ["asset", "baseline"])
def test_mixed_legacy_images_require_complete_pixels_in_profile3(tmp_path, key, entry):
    baseline = scope_baseline(tmp_path / "source")
    raw_path = (
        baseline.manifest_path.parent / baseline.data["payloads"][identity(key)]["path"]
    )
    raw_path.write_bytes(raw_path.read_bytes()[:-4])
    baseline = repin(baseline)
    row = baseline.json(baseline.data["attachment_metadata"][identity(key)]["path"])
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(baseline, row, "3")
        else:
            audit_baseline(baseline, profile_version="3")


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


def test_scoped_mixed_vault_preserves_safe_nested_documents_and_empty_policy(tmp_path):
    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    assert check_api_vault(baseline, vault, profile_version="3") == {
        "thoughts": 8,
        "relationships": 7,
        "payloads": 11,
    }


@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
@pytest.mark.parametrize(
    "damage",
    [
        "missing-wire-field",
        "extra-wire-field",
        "false-status",
        "private",
        "bool-kind",
        "unknown-role",
        "unlisted-exclusion",
        "included-overlap",
        "unknown-scope-field",
        "unknown-endpoint",
        "no-excluded-endpoint",
        "contradictory-repeat",
    ],
)
def test_scope_authority_is_explicit_complete_and_type_sensitive(
    tmp_path, entry, damage
):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    root = baseline.manifest_path.parent
    data = json.loads(baseline.manifest_path.read_bytes())
    path = root / data["scope_inputs"]["excluded_thoughts"][identity(91)]["path"]
    row = json.loads(path.read_bytes())
    if damage == "missing-wire-field":
        row.pop("backgroundColor")
    elif damage == "extra-wire-field":
        row["custom"] = None
    elif damage == "false-status":
        data["scope_inputs"]["excluded_thoughts"][identity(91)]["status"] = True
    elif damage == "private":
        row["acType"] = 1
    elif damage == "bool-kind":
        row["kind"] = True
    elif damage == "unknown-role":
        row["kind"] = 99
    elif damage == "unlisted-exclusion":
        data["scope_inputs"]["excluded_thoughts"].pop(identity(91))
    elif damage == "included-overlap":
        data["scope_inputs"]["excluded_thoughts"][identity(2)] = dict(
            data["scope_inputs"]["excluded_thoughts"][identity(91)]
        )
    elif damage == "unknown-scope-field":
        data["scope_inputs"]["safe_text"] = "asserted safe"
    elif damage in {"unknown-endpoint", "no-excluded-endpoint"}:
        target = (
            root / data["scope_inputs"]["excluded_relationships"][identity(191)]["path"]
        )
        link = json.loads(target.read_bytes())
        link["thoughtIdB"] = identity(999 if damage == "unknown-endpoint" else 3)
        target.write_bytes(json_bytes(link))
    else:
        target = root / data["graphs"][identity(2)]
        graph = json.loads(target.read_bytes())
        graph["children"][-1]["kind"] = True
        target.write_bytes(json_bytes(graph))
    path.write_bytes(json_bytes(row))
    baseline.manifest_path.write_bytes(json_bytes(data))
    baseline = repin(baseline)
    with pytest.raises(AssertionError):
        if entry == "asset":
            image = baseline.json(data["attachment_metadata"][identity(204)]["path"])
            expected_asset(baseline, image, "3")
        elif entry == "baseline":
            audit_baseline(baseline, profile_version="3")
        else:
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "damage", ["copied-unsafe-original", "minimal-thought-leak", "minimal-link-leak"]
)
def test_scoped_output_cannot_retain_original_or_excluded_authored_metadata(
    tmp_path, damage
):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    if damage == "copied-unsafe-original":
        (vault / "copied-unsafe.md").write_bytes(
            baseline.bytes(baseline.data["payloads"][identity(201)]["path"])
        )
    else:
        key = (
            ("exclusion:" + identity(91))
            if damage == "minimal-thought-leak"
            else ("link:" + identity(191))
        )
        next(
            row["records"] for row in record["original_evidence"] if row["key"] == key
        )["name"] = "AUTHORED-EXCLUSION-LEAK"
        path.write_bytes(json_bytes(record))
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "damage",
    [
        "omit-uncreated-document",
        "created-empty-child",
        "hide-coverage-parent",
        "swap-empty-selection",
        "omit-safe-empty-asset",
        "omit-safe-empty-payload",
        "restore-unsafe-asset",
        "raw-document-digest",
        "raw-coordinate-offset",
        "wrong-original-flag",
        "forged-scope-edit",
        "wrong-item-table-flag",
        "omit-svg-identity",
        "reverse-endpoints",
        "external-uri",
        "external-role",
    ],
)
def test_mixed_scope_output_requires_source_bound_documents_selection_and_resources(
    tmp_path, damage
):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    targets = {row["item_key"]: row for row in record["item_targets"]}
    assets = {row["asset_id"]: row for row in record["asset_targets"]}
    document = targets[identity(2)]["documents"][0]
    if damage == "omit-uncreated-document":
        targets[identity(6)]["documents"].clear()
    elif damage == "created-empty-child":
        targets[identity(6)]["created"] = True
    elif damage == "hide-coverage-parent":
        targets[identity(7)]["created"] = False
        (vault / targets[identity(7)]["relative_path"]).unlink()
    elif damage == "swap-empty-selection":
        targets[identity(7)]["created"] = False
        (vault / targets[identity(7)]["relative_path"]).unlink()
        targets[identity(6)]["created"] = True
        (vault / targets[identity(6)]["relative_path"]).write_text(
            "# Empty after removal\n", encoding="utf8"
        )
    elif damage == "omit-safe-empty-asset":
        record["asset_targets"].remove(assets[identity(901)])
    elif damage == "omit-safe-empty-payload":
        (vault / assets[identity(901)]["relative_path"]).unlink()
    elif damage == "restore-unsafe-asset":
        record["asset_targets"].append(
            dict(assets[identity(401)], asset_id=identity(201), owner=identity(2))
        )
    elif damage == "raw-document-digest":
        document["text_digest"] = hashlib.sha256(
            baseline.bytes(baseline.data["payloads"][identity(201)]["path"])
        ).hexdigest()
    elif damage == "raw-coordinate-offset":
        document["references"][-1]["start"] += len("FORGOTTEN-CANARY")
    elif damage == "wrong-original-flag":
        document["original_asset_id"] = identity(201)
        document["original_copy_omitted"] = False
    elif damage == "forged-scope-edit":
        document["text_adaptations"][0]["source_digest"] = hashlib.sha256(
            baseline.bytes(baseline.data["payloads"][identity(201)]["path"])
        ).hexdigest()
    elif damage == "wrong-item-table-flag":
        document["references"][0]["table_cell"] = False
    elif damage == "omit-svg-identity":
        record["asset_targets"].remove(assets[identity(206)])
    elif damage == "reverse-endpoints":
        record["relationships"][0]["item_a"], record["relationships"][0]["item_b"] = (
            record["relationships"][0]["item_b"],
            record["relationships"][0]["item_a"],
        )
    elif damage == "external-uri":
        assets[identity(209)]["external_uri"] = "file:///C:/forged.pdf"
    else:
        assets[identity(210)]["role"] = "file"
    path.write_bytes(json_bytes(record))
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("entry", ["asset", "baseline"])
@pytest.mark.parametrize(
    "damage",
    [
        "notes-bool-int",
        "notes-type-float",
        "notes-source-bool",
        "notes-metadata",
        "notes-list",
        "notes-extra-field",
    ],
)
def test_original_omission_cannot_bypass_attachment_declaration_qualification(
    tmp_path, entry, damage
):
    import json

    baseline = scope_baseline(tmp_path / "source")
    root = baseline.manifest_path.parent
    graph_path = root / baseline.data["graphs"][identity(2)]
    graph = json.loads(graph_path.read_bytes())
    note = graph["attachments"][0]
    if damage == "notes-bool-int":
        note["isNotes"] = 1
    elif damage == "notes-type-float":
        note["type"] = 1.0
    elif damage == "notes-source-bool":
        note["sourceType"] = True
    elif damage == "notes-extra-field":
        note["future_role"] = False
    if damage not in {"notes-metadata", "notes-list"}:
        graph_path.write_bytes(json_bytes(graph))
        rows = baseline.json(baseline.data["attachment_inventories"][identity(2)])
        rows[0] = note
        (root / baseline.data["attachment_inventories"][identity(2)]).write_bytes(
            json_bytes(rows)
        )
        (
            root / baseline.data["attachment_metadata"][identity(201)]["path"]
        ).write_bytes(json_bytes(note))
    elif damage == "notes-metadata":
        note["name"] = "forged"
        (
            root / baseline.data["attachment_metadata"][identity(201)]["path"]
        ).write_bytes(json_bytes(note))
    else:
        rows = baseline.json(baseline.data["attachment_inventories"][identity(2)])
        rows[0]["name"] = "forged"
        (root / baseline.data["attachment_inventories"][identity(2)]).write_bytes(
            json_bytes(rows)
        )
    baseline = repin(baseline)
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(
                baseline,
                baseline.json(
                    baseline.data["attachment_metadata"][identity(204)]["path"]
                ),
                "3",
            )
        else:
            audit_baseline(baseline, profile_version="3")


def test_excluded_both_endpoint_association_needs_no_excluded_graph_fetch(tmp_path):
    import json

    baseline = scope_baseline(tmp_path / "source")
    root = baseline.manifest_path.parent
    metadata_path = (
        root
        / baseline.data["scope_inputs"]["excluded_relationships"][identity(190)]["path"]
    )
    link = json.loads(metadata_path.read_bytes())
    link.update(
        thoughtIdA=identity(90),
        thoughtIdB=identity(91),
        meaning={"ignored": "authored unknown"},
    )
    metadata_path.write_bytes(json_bytes(link))
    graph_path = root / baseline.data["graphs"][identity(2)]
    graph = json.loads(graph_path.read_bytes())
    graph["links"] = [r for r in graph["links"] if r["id"] != identity(190)]
    graph["children"] = [r for r in graph["children"] if r["id"] != identity(90)]
    graph_path.write_bytes(json_bytes(graph))
    baseline = repin(baseline)
    assert audit_baseline(baseline, profile_version="3")["retention"][
        "omitted_original_ids"
    ] == [identity(201), identity(601)]


@pytest.mark.parametrize(
    "asset,variant", [(212, 0), (212, 1), (301, 0), (301, 1), (301, 2)]
)
@pytest.mark.parametrize(
    "entry,damage",
    [
        ("asset", "fresh-invalid"),
        ("asset", "trusted-pin"),
        ("baseline", "fresh-invalid"),
        ("baseline", "trusted-pin"),
        ("vault", "fresh-invalid"),
        ("vault", "trusted-pin"),
        ("vault", "output-bytes"),
    ],
)
def test_every_mixed_ico_variant_has_semantic_integrity_and_output_obligations(
    tmp_path, asset, variant, entry, damage
):
    import json
    import os
    import struct

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    source = (
        baseline.manifest_path.parent
        / baseline.data["payloads"][identity(asset)]["path"]
    )
    raw = bytearray(source.read_bytes())
    offset = struct.unpack_from("<I", raw, 6 + 16 * variant + 12)[0]
    if damage == "output-bytes":
        record = json.loads((vault / "migration-record.json").read_bytes())
        target = next(
            row for row in record["asset_targets"] if row["asset_id"] == identity(asset)
        )
        path = vault / target["relative_path"]
        raw[offset + 40] ^= 1
        path.write_bytes(raw)
    else:
        stamp = source.stat()
        raw[offset + (16 if damage == "fresh-invalid" else 40)] ^= 1
        source.write_bytes(raw)
        os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        if damage == "fresh-invalid":
            baseline = repin(baseline)
    row = baseline.json(baseline.data["attachment_metadata"][identity(asset)]["path"])
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(baseline, row, "3")
        elif entry == "baseline":
            audit_baseline(baseline, profile_version="3")
        else:
            check_api_vault(baseline, vault, profile_version="3")


def test_mixed_ico_and_legacy_pixel_proofs_match_independent_source_literals(tmp_path):
    import json

    from .api_scope_inputs import FIXTURES

    baseline = scope_baseline(tmp_path / "source")
    proof = audit_baseline(baseline, profile_version="3")["resource_eligibility"]
    original = json.loads((FIXTURES / "qualified-image-input-facts.json").read_bytes())
    for key, name in ((212, "inert-a.ico"), (301, "inert-b.ico")):
        source = next(row for row in original["payloads"] if row["file"] == name)
        actual = proof[identity(key)]
        assert actual["format"] == "ICO" and actual["source_sha256"] == source["sha256"]
        assert len(actual["frames"]) == len(source["directory_order"])
        for frame, expect in zip(
            actual["frames"], source["directory_order"], strict=True
        ):
            assert {
                field: frame[field]
                for field in (
                    "width",
                    "height",
                    "offset",
                    "body_length",
                    "body_sha256",
                    "mask_length",
                    "extra_zero_tail_length",
                    "rgba_sha256",
                )
            } == {
                field: expect[field]
                for field in (
                    "width",
                    "height",
                    "offset",
                    "body_length",
                    "body_sha256",
                    "mask_length",
                    "extra_zero_tail_length",
                    "rgba_sha256",
                )
            }
    for key, format_name, width, height in (
        (202, "PNG", 1, 1),
        (203, "WEBP", 2, 1),
        (302, "PNG", 1, 1),
    ):
        assert (
            proof[identity(key)]["format"],
            proof[identity(key)]["width"],
            proof[identity(key)]["height"],
        ) == (format_name, width, height)


@pytest.mark.parametrize("entry", ["asset", "baseline"])
@pytest.mark.parametrize("damage", ["malformed-id", "invalid-calendar"])
def test_scope_identity_and_calendar_fail_as_public_qualification(
    tmp_path, entry, damage
):
    import json

    baseline = scope_baseline(tmp_path / "source")
    path = (
        baseline.manifest_path.parent
        / baseline.data["scope_inputs"]["excluded_thoughts"][identity(91)]["path"]
    )
    row = json.loads(path.read_bytes())
    row["id" if damage == "malformed-id" else "forgottenDateTime"] = (
        "not-a-uuid" if damage == "malformed-id" else "2026-02-30T12:00:00Z"
    )
    path.write_bytes(json_bytes(row))
    baseline = repin(baseline)
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(
                baseline,
                baseline.json(
                    baseline.data["attachment_metadata"][identity(204)]["path"]
                ),
                "3",
            )
        else:
            audit_baseline(baseline, profile_version="3")


@pytest.mark.parametrize(
    "asset,variant", [(212, 0), (212, 1), (301, 0), (301, 1), (301, 2)]
)
@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
@pytest.mark.parametrize("damage", ["failure", "dimensions"])
def test_each_mixed_ico_variant_requires_its_own_complete_native_result(
    tmp_path, monkeypatch, asset, variant, entry, damage
):
    import struct

    from . import api_image_proofs
    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    raw = baseline.bytes(baseline.data["payloads"][identity(asset)]["path"])
    length, offset = struct.unpack_from("<II", raw, 6 + 16 * variant + 8)
    source_body = raw[offset : offset + length]
    actual = api_image_proofs.decode_ico_variant

    def native_result(wrapper):
        proof = actual(wrapper)
        if wrapper[22:] == source_body:
            if damage == "failure":
                raise AssertionError("independent synthetic native decode failure")
            proof = dict(proof, width=proof["width"] + 1)
        return proof

    # The external WIC seam is controlled, not an internal source classifier.
    monkeypatch.setattr(api_image_proofs, "decode_ico_variant", native_result)
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(
                baseline,
                baseline.json(
                    baseline.data["attachment_metadata"][identity(asset)]["path"]
                ),
                "3",
            )
        elif entry == "baseline":
            audit_baseline(baseline, profile_version="3")
        else:
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("entry", ["asset", "baseline"])
def test_observed_forgotten_authority_cannot_disappear_from_summary(tmp_path, entry):
    import json

    baseline = scope_baseline(tmp_path / "source")
    for name in baseline.data["statistics"]:
        path = baseline.manifest_path.parent / name
        row = json.loads(path.read_bytes())
        row["forgottenThoughts"] = 0
        path.write_bytes(json_bytes(row))
    baseline = repin(baseline)
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(
                baseline,
                baseline.json(
                    baseline.data["attachment_metadata"][identity(204)]["path"]
                ),
                "3",
            )
        else:
            audit_baseline(baseline, profile_version="3")


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


@pytest.mark.parametrize(
    "damage",
    [
        "safe-note",
        "scope-decision",
        "graph-exclusion",
        "graph-omitted-id",
        "accounting-drop",
        "accounting-omitted-normalized",
    ],
)
def test_mixed_scope_evidence_and_accounting_are_independently_source_bound(
    tmp_path, damage
):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    evidence = {row["key"]: row["records"] for row in record["original_evidence"]}
    if damage == "safe-note":
        evidence["note_text:" + identity(2)]["text"] += "FORGED SOURCE"
    elif damage == "scope-decision":
        evidence["scope:note:" + identity(201)]["subjects"].pop()
    elif damage == "graph-exclusion":
        evidence["graph:" + identity(2)]["children_ids"].append(identity(91))
    elif damage == "graph-omitted-id":
        evidence["graph:" + identity(2)]["attachment_ids"].remove(identity(201))
    elif damage == "accounting-drop":
        record["source_accounting"]["entries"].pop()
    else:
        next(
            row
            for row in record["source_accounting"]["entries"]
            if row["identity"] == "attachment:" + identity(201)
        )["disposition"] = "normalized"
    path.write_bytes(json_bytes(record))
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


def test_qualified_toc_fallback_materializes_owner_from_final_safe_text(tmp_path):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    root = baseline.manifest_path.parent
    (root / baseline.data["payloads"][identity(901)]["path"]).write_bytes(b"[/toc/]")
    graph_path = root / baseline.data["graphs"][identity(9)]
    graph = json.loads(graph_path.read_bytes())
    graph["attachments"][0]["dataLength"] = 7
    graph_path.write_bytes(json_bytes(graph))
    (root / baseline.data["attachment_inventories"][identity(9)]).write_bytes(
        json_bytes(graph["attachments"])
    )
    (root / baseline.data["attachment_metadata"][identity(901)]["path"]).write_bytes(
        json_bytes(graph["attachments"][0])
    )
    baseline = repin(baseline)
    vault = mixed_vault(tmp_path / "vault", baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    document = next(
        row for row in record["item_targets"] if row["item_key"] == identity(9)
    )["documents"][0]
    document["text_digest"] = hashlib.sha256(b"No authored headings.").hexdigest()
    owner = next(
        row for row in record["item_targets"] if row["item_key"] == identity(9)
    )
    owner["created"] = True
    owner["icon_snapshot"] = {
        "item_key": identity(9),
        "explicit_icon_asset_id": None,
        "appearance_category_key": None,
        "effective_icon_asset_id": None,
    }
    properties = {
        "categories": [],
        "tags": [],
        "aliases": [],
        "created": "2026-09-13",
        "updated": "2026-10-02",
        "source_collection_id": identity(1),
        "source_item_id": identity(9),
    }
    prefix = "".join(
        key + ": " + json.dumps(value) + "\n" for key, value in properties.items()
    )
    (vault / owner["relative_path"]).write_text(
        "---\n"
        + prefix
        + "icon:\nappearance_category:\n---\n\n# Safe empty\n\nNo authored headings.\n\n",
        encoding="utf8",
    )
    document["text_adaptations"] = [
        {
            "kind": "markdown_insert",
            "start": 0,
            "end": 7,
            "before": "[/toc/]",
            "after": "No authored headings.",
            "adapted_start": 0,
            "adapted_end": 21,
            "source_digest": hashlib.sha256(b"[/toc/]").hexdigest(),
            "source_basis": "scoped_source_text/unicode_codepoints",
            "adapted_basis": "document.text/unicode_codepoints",
        }
    ]
    next(
        row
        for row in record["original_evidence"]
        if row["key"] == "note_text:" + identity(9)
    )["records"] = {"text": "[/toc/]"}
    path.write_bytes(json_bytes(record))
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 11


@pytest.mark.parametrize(
    "damage",
    ["drop-tag", "token", "native", "category-target", "yaml-tag", "yaml-category"],
)
def test_mixed_classification_and_native_tag_metadata_are_source_bound(
    tmp_path, damage
):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    if damage == "drop-tag":
        record["tag_memberships"].clear()
    elif damage == "token":
        record["tag_memberships"][0]["token"] = "forged"
    elif damage == "native":
        record["tag_memberships"][0]["native"] = False
    elif damage == "category-target":
        record["classification_assignments"][0]["definition_target"] = "Home.md"
    else:
        note = vault / "Notes/Child.md"
        text = note.read_text(encoding="utf8")
        text = (
            text.replace('tags: ["Tag"]', "tags: []")
            if damage == "yaml-tag"
            else text.replace(
                'categories: ["[[Categories/Type.md]]"]', "categories: []"
            )
        )
        note.write_text(text, encoding="utf8")
    path.write_bytes(json_bytes(record))
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("name", None),
        ("label", False),
        ("aliases", [1]),
        ("creationDateTime", "2026-02-30T00:00:00Z"),
        ("typeId", False),
        ("foregroundColor", "red"),
    ],
)
def test_included_wire_scalars_cannot_be_hidden_by_consistent_repeats(
    tmp_path, entry, field, value
):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)

    def replace(value_):
        if isinstance(value_, dict):
            if value_.get("id") == identity(3) and "forgottenDateTime" in value_:
                value_[field] = value
            for nested in value_.values():
                replace(nested)
        elif isinstance(value_, list):
            for nested in value_:
                replace(nested)

    for name in baseline.data["files"]:
        if not name.endswith(".json"):
            continue
        path = baseline.manifest_path.parent / name
        data = json.loads(path.read_bytes())
        replace(data)
        path.write_bytes(json_bytes(data))
    baseline = repin(baseline)
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(
                baseline,
                baseline.json(
                    baseline.data["attachment_metadata"][identity(204)]["path"]
                ),
                "3",
            )
        elif entry == "baseline":
            audit_baseline(baseline, profile_version="3")
        else:
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("case", ["zero-tags", "changed-svg"])
def test_independent_mixed_variants_preserve_their_own_source_identity(tmp_path, case):
    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source", case)
    vault = mixed_vault(tmp_path / "vault", baseline)
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 11


@pytest.mark.parametrize(
    "damage", ["omitted", "inactive", "outside-resources", "gap-description"]
)
def test_mixed_pdf_resource_requires_active_generated_section(tmp_path, damage):
    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    note = vault / "Home.md"
    text = note.read_text(encoding="utf8")
    row = "- [[Attachments/manual.pdf|manual.pdf]]"
    if damage == "gap-description":
        text = text.replace(
            "- Absent source file: manual.txt (metadata retained; bytes absent from the source).",
            "",
        )
    elif damage == "omitted":
        text = text.replace(row, "")
    elif damage == "inactive":
        text = text.replace(row, "<!--" + row + "-->")
    else:
        text = text.replace(row, "").replace(
            "## Resources", row + "\n\n## Resources", 1
        )
    note.write_text(text, encoding="utf8")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("damage", [False, True])
def test_mixed_scoped_document_allows_source_owned_composite_edits(tmp_path, damage):
    import json

    from .api_checker import check_api_component_vault as check_api_vault
    from .api_scope_inputs import mixed_literal_documents

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    literal = mixed_literal_documents()
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    edits = record["item_targets"][0]["documents"][0]["text_adaptations"]
    assert edits[1]["kind"] == edits[-1]["kind"] == "markdown_insert"
    first, last = edits[1], edits[-1]
    grouped = first | {
        "end": last["end"],
        "adapted_end": last["adapted_end"],
        "before": literal["scoped_text"][first["start"] : last["end"]],
        "after": literal["adapted_text"][first["adapted_start"] : last["adapted_end"]],
    }
    if damage:
        grouped["kind"] = "literal_text"
    edits[1:] = [grouped]
    path.write_bytes(json_bytes(record))
    if damage:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 11


def test_mixed_imported_calendar_properties_accept_yaml_date_scalars(tmp_path):
    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    import json

    record = json.loads((vault / "migration-record.json").read_bytes())
    for target in record["item_targets"]:
        if not target["created"]:
            continue
        note = vault / target["relative_path"]
        text = note.read_text(encoding="utf8")
        text = text.replace('created: "2026-09-13"', "created: 2026-09-13").replace(
            'updated: "2026-10-02"', "updated: 2026-10-02"
        )
        note.write_text(text, encoding="utf8")
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 11


@pytest.mark.parametrize(
    "field,value", [("foreground_color", "#000000"), ("background_color", None)]
)
def test_mixed_definition_declared_colors_are_source_bound(tmp_path, field, value):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    next(row for row in record["item_targets"] if row["item_key"] == identity(4))[
        "declared_appearance"
    ][field] = value
    path.write_bytes(json_bytes(record))
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
@pytest.mark.parametrize("profile", [None, "1", "2", "unknown"])
def test_mixed_scope_container_does_not_grant_a_profile(entry, profile, tmp_path):
    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    options = {} if profile is None else {"profile_version": profile}
    with pytest.raises(AssertionError):
        if entry == "asset":
            row = baseline.json(
                baseline.data["attachment_metadata"][identity(212)]["path"]
            )
            if profile is None:
                expected_asset(baseline, row)
            else:
                expected_asset(baseline, row, profile)
        elif entry == "baseline":
            audit_baseline(baseline, **options)
        else:
            check_api_vault(baseline, tmp_path / "unused-vault", **options)


@pytest.mark.parametrize("schema", ["brz2obsidian.api-acceptance/1", "unknown"])
def test_scope_authority_is_not_an_implicit_legacy_container_grant(tmp_path, schema):
    import json

    baseline = scope_baseline(tmp_path / "source")
    data = json.loads(baseline.manifest_path.read_bytes())
    data["schema"] = schema
    raw = json_bytes(data)
    baseline.manifest_path.write_bytes(raw)
    with pytest.raises(AssertionError):
        load_baseline(baseline.manifest_path, hashlib.sha256(raw).hexdigest())


def test_valid_changed_mixed_source_needs_new_pin_and_new_output_bytes(tmp_path):
    from .api_checker import check_api_component_vault as check_api_vault

    old = scope_baseline(tmp_path / "old")
    vault = mixed_vault(tmp_path / "old-vault", old)
    changed = scope_baseline(tmp_path / "changed", "changed-svg")
    assert changed.fingerprint != old.fingerprint
    with pytest.raises(AssertionError, match="manifest changed"):
        load_baseline(changed.manifest_path, old.fingerprint)
    assert (
        audit_baseline(changed, profile_version="3")["retention"]
        == audit_baseline(old, profile_version="3")["retention"]
    )
    with pytest.raises(AssertionError, match="required payload bytes"):
        check_api_vault(changed, vault, profile_version="3")


@pytest.mark.parametrize(
    "source",
    [
        "`FORGOTTEN-CANARY " + identity(91) + "`",
        "<!--" + identity(91) + "-->",
        "%30%30%30%30%30%30%30%30-0000-4000-8000-000000000091",
    ],
)
@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
def test_unremoved_scope_associations_refuse_even_in_protected_text(
    tmp_path, entry, source
):
    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    path = (
        baseline.manifest_path.parent / baseline.data["payloads"][identity(601)]["path"]
    )
    path.write_bytes(source.encode())
    baseline = repin(baseline)
    with pytest.raises(AssertionError, match="unremoved excluded note association"):
        if entry == "asset":
            expected_asset(
                baseline,
                baseline.json(
                    baseline.data["attachment_metadata"][identity(204)]["path"]
                ),
                "3",
            )
        elif entry == "baseline":
            audit_baseline(baseline, profile_version="3")
        else:
            check_api_vault(baseline, tmp_path / "unused-vault", profile_version="3")


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_qualified_source_factory_preserves_provenance_across_checkout_eols(
    tmp_path, monkeypatch, newline
):
    import shutil

    from . import api_scope_inputs

    fixtures = tmp_path / "fixtures"
    shutil.copytree(api_scope_inputs.FIXTURES, fixtures)
    path = fixtures / "input-provenance.json"
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", newline))
    monkeypatch.setattr(api_scope_inputs, "FIXTURES", fixtures)
    baseline = scope_baseline(tmp_path / "source")
    assert (
        hashlib.sha256(baseline.bytes("input-provenance.json")).hexdigest()
        == "d8e39f65b31e244ca2c078aa05a9207a2ddd31f94e4f3cc8c5aa1256dbc9ed29"
    )
    assert (
        baseline.fingerprint
        == "3535182dccc9a298c27d163afc12a006b8aa6aeac553168981374c851ba4ed81"
    )
    assert audit_baseline(baseline, profile_version="3")["payloads"] == 11


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


@pytest.mark.parametrize("excluded", [False, True])
@pytest.mark.parametrize(
    "profile,image_format", [("1", "webp"), ("2", "png"), ("3", "png")]
)
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "digest",
        "original",
        "reference",
        "omit-document",
        "original-id",
        "created-child",
        "hide-home",
    ],
)
def test_inherited_raster_only_scope_still_requires_complete_documents(
    tmp_path, excluded, damage, profile, image_format
):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline, vault = raster_scope_case(
        tmp_path, excluded=excluded, profile=profile, image_format=image_format
    )
    audit = audit_baseline(baseline, profile_version=profile)
    assert audit["retention"] == {
        "omitted_original_ids": [identity(201)] if excluded else [],
        "retained_asset_ids": [identity(202)]
        if excluded
        else [identity(201), identity(202)],
        "openable_payload_ids": [identity(202)]
        if excluded
        else [identity(201), identity(202)],
    }
    note = baseline.json(baseline.data["attachment_metadata"][identity(201)]["path"])
    if excluded:
        with pytest.raises(AssertionError, match="no retained Asset"):
            expected_asset(baseline, note, profile)
    else:
        assert expected_asset(baseline, note, profile)[0:2] == (
            "note_original",
            "present",
        )
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    document = record["item_targets"][0]["documents"][0]
    if damage == "digest":
        document["text_digest"] = "0" * 64
    elif damage == "original":
        document["original_copy_omitted"] = not excluded
    elif damage == "reference":
        document["references"][0]["start"] += 1
    elif damage == "omit-document":
        record["item_targets"][0]["documents"] = []
    elif damage == "original-id":
        document["original_asset_id"] = identity(202)
    elif damage == "created-child":
        record["item_targets"][1]["created"] = True
    elif damage == "hide-home":
        record["item_targets"][0]["created"] = False
    path.write_bytes(json_bytes(record))
    if damage is not None:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version=profile)
    else:
        assert check_api_vault(baseline, vault, profile_version=profile) == {
            "thoughts": 2,
            "relationships": 3,
            "payloads": 1 if excluded else 2,
        }


@pytest.mark.parametrize(
    "leak",
    [
        "original-newline",
        "canary-only",
        "record-original",
        "record-canary",
        "metadata-only",
    ],
)
def test_scope_output_refuses_source_owned_excluded_text_in_larger_containers(
    tmp_path, leak
):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    original = baseline.bytes(baseline.data["payloads"][identity(201)]["path"])
    if leak == "original-newline":
        (vault / "extra.md").write_bytes(original + b"\n")
    elif leak in {"canary-only", "metadata-only"}:
        (vault / "extra.md").write_text(
            "FORGOTTEN-CANARY"
            if leak == "canary-only"
            else "FORGOTTEN-METADATA-CANARY",
            encoding="utf8",
        )
    else:
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        record["extra_string"] = (
            "Prefix "
            + (original.decode() if leak == "record-original" else "FORGOTTEN-CANARY")
            + " suffix"
        )
        path.write_bytes(json_bytes(record))
    with pytest.raises(
        AssertionError, match="excluded authored content|unsafe original"
    ):
        check_api_vault(baseline, vault, profile_version="3")


def test_excluded_metadata_text_can_also_be_legitimate_included_source_text(tmp_path):
    from .api_checker import check_api_component_vault as check_api_vault

    baseline, vault = raster_scope_case(tmp_path)
    for name in baseline.data["files"]:
        if not name.startswith("responses/") or not name.endswith(".json"):
            continue
        try:
            value = baseline.json(name)
        except ValueError:
            continue

        def rename(row):
            if isinstance(row, dict):
                if row.get("id") == identity(91):
                    row["name"] = "Home"
                for child in row.values():
                    rename(child)
            elif isinstance(row, list):
                for child in row:
                    rename(child)

        rename(value)
        (baseline.manifest_path.parent / name).write_bytes(json_bytes(value))
    baseline = repin(baseline)
    assert check_api_vault(baseline, vault, profile_version="3") == {
        "thoughts": 2,
        "relationships": 3,
        "payloads": 1,
    }


@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
def test_scope_representation_does_not_grant_profile1_png(tmp_path, entry):
    from .api_checker import check_api_component_vault as check_api_vault

    baseline, vault = raster_scope_case(tmp_path, profile="1")
    image = baseline.json(baseline.data["attachment_metadata"][identity(202)]["path"])
    with pytest.raises(AssertionError, match="raw image role"):
        if entry == "asset":
            expected_asset(baseline, image, "1")
        elif entry == "baseline":
            audit_baseline(baseline, profile_version="1")
        else:
            check_api_vault(baseline, vault, profile_version="1")


@pytest.mark.parametrize(
    "damage", [None, "order", "duplicate", "subject-order", "subject-duplicate"]
)
def test_scope_decision_evidence_is_a_canonical_unique_logical_key_set(
    tmp_path, damage
):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline, vault = raster_scope_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    for row in record["original_evidence"]:
        if row["key"].startswith("scope:"):
            for field in ("subjects", "evidence"):
                row["records"][field] = sorted(set(row["records"][field]))
    association = next(
        row["records"]
        for row in record["original_evidence"]
        if row["key"] == "scope:association:" + identity(191)
    )
    if damage == "order":
        association["evidence"].reverse()
    elif damage == "duplicate":
        association["evidence"].append(association["evidence"][0])
    elif damage == "subject-order":
        association["subjects"].reverse()
    elif damage == "subject-duplicate":
        association["subjects"].append(association["subjects"][0])
    path.write_bytes(json_bytes(record))
    if damage is None:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 1
    else:
        with pytest.raises(
            AssertionError, match="scoped original source record/decision"
        ):
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("damage", [None, "order", "duplicate"])
def test_mixed_classification_evidence_is_canonical(tmp_path, damage):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    assignment = record["classification_assignments"][0]
    assignment["evidence"] = [
        "link:" + identity(104),
        "thought:" + identity(3),
        "thought:" + identity(4),
    ]
    if damage == "order":
        assignment["evidence"].reverse()
    elif damage == "duplicate":
        assignment["evidence"].append("thought:" + identity(4))
    path.write_bytes(json_bytes(record))
    if damage is None:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 11
    else:
        with pytest.raises(
            AssertionError, match="source-bound classification metadata"
        ):
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "overlap", ["minimal-uuid", "link-name", "attachment-name", "schema-word"]
)
@pytest.mark.parametrize("extra", [None, "file", "record", "note"])
def test_excluded_scalar_provenance_is_specific_to_its_output_location(
    tmp_path, overlap, extra
):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    value = {
        "minimal-uuid": identity(91),
        "link-name": "Included relationship label",
        "attachment-name": "file: guide",
        "schema-word": "source",
    }[overlap]

    def change(row):
        if isinstance(row, dict):
            if row.get("id") == identity(91):
                row["name"] = value
            if overlap == "link-name" and row.get("id") == identity(101):
                row["name"] = value
            for child in row.values():
                change(child)
        elif isinstance(row, list):
            for child in row:
                change(child)

    for name in baseline.data["files"]:
        if name.startswith("responses/") and name.endswith(".json"):
            row = baseline.json(name)
            change(row)
            (baseline.manifest_path.parent / name).write_bytes(json_bytes(row))
    baseline = repin(baseline)
    vault = mixed_vault(tmp_path / "vault", baseline)
    if extra == "file":
        (vault / "extra.txt").write_text(value, encoding="utf8")
    elif extra == "note":
        with (vault / "Home.md").open("a", encoding="utf8") as stream:
            stream.write("\n" + value + "\n")
    elif extra == "record":
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        record["extra_string"] = value
        path.write_bytes(json_bytes(record))
    if extra is None:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 11
    else:
        with pytest.raises(
            AssertionError,
            match="excluded authored content|reverse hierarchy",
        ):
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "damage", [None, "extra", "bad-uuid", "bad-digest", "bad-date", "unknown"]
)
def test_generated_protocol_provenance_has_closed_typed_locations(tmp_path, damage):
    import json

    from .api_checker import check_api_component_vault as check_api_vault

    baseline = scope_baseline(tmp_path / "source")

    def change(row):
        if isinstance(row, dict):
            if row.get("id") == identity(91):
                row["name"] = "aaaa"
            for child in row.values():
                change(child)
        elif isinstance(row, list):
            for child in row:
                change(child)

    for name in baseline.data["files"]:
        if name.startswith("responses/") and name.endswith(".json"):
            row = baseline.json(name)
            change(row)
            (baseline.manifest_path.parent / name).write_bytes(json_bytes(row))
    baseline = repin(baseline)
    vault = mixed_vault(tmp_path / "vault", baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record.update(
        schema="brz2obsidian.migration",
        schema_version=7,
        converter_version="0.1.0",
        renderer_version="7",
    )
    record["source_identity"].update(source_sha256="a" * 64, snapshot_digest="b" * 64)
    record["run_metadata"] = {
        "converter_version": "0.1.0",
        "renderer_version": "7",
        "run_id": "aaaaaaaa-0000-4000-8000-000000000001",
        "run_time": "2026-10-16T12:00:00+00:00",
        "obsidian_version": "1.9.12",
        "bookmark_time": 1792152000000,
    }
    if damage == "extra":
        record["extra"] = "aaaa"
    elif damage == "bad-uuid":
        record["run_metadata"]["run_id"] = "aaaa"
    elif damage == "bad-digest":
        record["source_identity"]["source_sha256"] = "aaaa"
    elif damage == "bad-date":
        record["run_metadata"]["run_time"] = "2026-99-16T12:00:00+00:00"
    elif damage == "unknown":
        record["run_metadata"]["extra"] = "aaaa"
    path.write_bytes(json_bytes(record))
    if damage is None:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 11
    else:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")


def test_generated_support_requires_source_derived_complete_census(tmp_path):
    import json

    from .api_checker import check_api_vault

    baseline = scope_baseline(tmp_path / "source")
    vault = mixed_vault(tmp_path / "vault", baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["support_artifacts"] = []
    record["reserved_support_paths"] = []
    path.write_bytes(json_bytes(record))
    with pytest.raises(AssertionError, match="support"):
        check_api_vault(baseline, vault, profile_version="3")


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


@pytest.mark.parametrize("name", ["a", "source"])
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "guide-append",
        "report-append",
        "both-envelopes",
        "protocol",
        "whole-support",
        "unknown-file",
        "unknown-field",
        "note",
        "wrong-count",
        "missing-count",
        "duplicate-support",
        "wrong-config",
        "wrong-base",
        "wrong-template",
        "wrong-adaptation",
        "unknown-acquisition",
        "bad-acquisition-time",
        "missing-item",
        "missing-asset",
        "missing-relationship",
        "benign-record",
        "benign-child",
    ],
)
def test_complete_generated_raster_provenance_is_location_specific(
    tmp_path, name, damage
):
    import json

    from .api_checker import check_api_vault

    baseline, vault = raster_scope_case(tmp_path)
    for relative in baseline.data["files"]:
        if relative.startswith("responses/") and relative.endswith(".json"):
            if (
                baseline.data["tags"]["status"] == 400
                and relative == baseline.data["tags"]["path"]
            ):
                continue
            value = baseline.json(relative)

            def change(row):
                if isinstance(row, dict):
                    if row.get("id") == identity(91):
                        row["name"] = name
                    for child in row.values():
                        change(child)
                elif isinstance(row, list):
                    for child in row:
                        change(child)

            change(value)
            (baseline.manifest_path.parent / relative).write_bytes(json_bytes(value))
    baseline = repin(baseline)
    complete_raster_support(baseline, vault)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    if damage in {"guide-append", "report-append", "note"}:
        output = (
            vault
            / {
                "guide-append": "Vault guide.md",
                "report-append": "MIGRATION REPORT.md",
                "note": "Home.md",
            }[damage]
        )
        output.write_bytes(output.read_bytes() + ("\n" + name).encode())
    elif damage == "both-envelopes":
        del record["support_artifacts"], record["reserved_support_paths"]
    elif damage == "protocol":
        for field in (
            "schema",
            "schema_version",
            "converter_version",
            "renderer_version",
            "run_metadata",
        ):
            del record[field]
    elif damage == "whole-support":
        for row in record["support_artifacts"]:
            if row["relative_path"] != "migration-record.json":
                (vault / row["relative_path"]).unlink()
        for output in sorted(
            vault.rglob("*"), key=lambda path: len(path.parts), reverse=True
        ):
            if output.is_dir() and not any(output.iterdir()):
                output.rmdir()
        for field in (
            "support_artifacts",
            "reserved_support_paths",
            "schema",
            "schema_version",
            "converter_version",
            "renderer_version",
            "run_metadata",
        ):
            del record[field]
    elif damage == "unknown-file":
        (vault / "unknown.txt").write_text("unrelated extra", encoding="utf8")
    elif damage == "unknown-field":
        record["unknown"] = name
    elif damage == "wrong-count":
        record["counts"]["planned_notes"] = 2
    elif damage == "missing-count":
        del record["counts"]["source_items"]
    elif damage == "duplicate-support":
        record["support_artifacts"].append(record["support_artifacts"][0])
    elif damage == "wrong-config":
        output = vault / ".obsidian/app.json"
        value = json.loads(output.read_bytes())
        value["alwaysUpdateLinks"] = False
        output.write_bytes(json_bytes(value))
    elif damage == "wrong-base":
        (vault / "Templates/Bases/Members.base").write_text("wrong", encoding="utf8")
    elif damage == "wrong-template":
        (vault / "Templates/New note.md").write_text("wrong", encoding="utf8")
    elif damage == "wrong-adaptation":
        record["adaptations"][0]["description"] += " " + name
    elif damage == "unknown-acquisition":
        record["run_metadata"]["source_acquisition"]["extra"] = name
    elif damage == "bad-acquisition-time":
        record["run_metadata"]["source_acquisition"]["audit"]["requests"][0][
            "finished_at"
        ] = "2026-10-16T11:58:00.200000Z"
    elif damage == "missing-item":
        del record["item_targets"][0]["creation_reasons"]
    elif damage == "missing-asset":
        del record["asset_targets"][0]["evidence"]
    elif damage == "missing-relationship":
        del record["relationships"][0]["presentation"]
    elif damage == "benign-record":
        record["unexpected"] = "benign"
    elif damage == "benign-child":
        record["item_targets"][0]["unexpected"] = "benign"
    record_path.write_bytes(json_bytes(record))
    if damage is None:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 1
    else:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")


def test_partial_component_refuses_undeclared_file_without_excluded_text(tmp_path):
    from .api_checker import check_api_component_vault

    baseline, vault = raster_scope_case(tmp_path)
    (vault / "extra.txt").write_text("unrelated", encoding="utf8")
    with pytest.raises(AssertionError, match="component source file census"):
        check_api_component_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "prefix,warning",
    [
        ('Text :(table="column-widths:-1,0;justification:default"):', "table"),
        ('`Text :(table="column-widths:-1,0;justification:default"):`', None),
        ('<!-- Text :(table="column-widths:-1,0;justification:default"): -->', None),
        (
            '| `:(table=x)` |:(table="column-widths:-1,0;justification:default"):\r\n| cell |',
            "responsive-table",
        ),
        ("[/toc/bad]", "table_of_contents"),
        ("[/tocBroken", None),
        ("[/toc/bad] trailing", None),
        ("> [/toc/bad]", None),
        ("`[/toc/bad]`", None),
        ("<!-- [/toc/bad] -->", None),
    ],
)
def test_complete_warning_grammar_retains_plain_and_protected_neighbors(
    tmp_path, prefix, warning
):
    import json

    from .api_checker import check_api_vault
    from .api_generated import STATIC
    from .checker import escaped

    display = (
        "| `:(table=x)` |\n|---|\r\n| cell |" if warning == "responsive-table" else None
    )
    baseline, vault = raster_scope_case(
        tmp_path, source_prefix=prefix, display_prefix=display
    )
    complete_raster_support(baseline, vault)
    if warning:
        table = warning in {"table", "responsive-table"}
        declaration = (
            prefix[prefix.index(':(table="') :].split("\r\n")[0] if table else prefix
        )
        change = (
            STATIC["GP07-LOSS-01"]
            if warning == "responsive-table"
            else STATIC["GP07-LOSS-08"]
            if table
            else STATIC["GP07-LOSS-10"]
        )
        observed = json.dumps(
            {
                "feature": "table" if table else warning,
                "declaration": declaration,
                "change": change,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        issue = {
            "code": "formatting_loss",
            "severity": "warning",
            "phase": "analysis",
            "message": STATIC["GP05-WARNING-02"] + " Observed: " + observed,
            "guidance": STATIC["GP05-WARNING-03"],
            "affected": [identity(2), identity(201)],
            "evidence": ["attachment:" + identity(201)],
            "rule_id": "local-api.note-formatting.v1",
            "leftover_path": None,
        }
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        record["issues"] = [issue]
        if display is not None:
            edit = record["item_targets"][0]["documents"][0]["text_adaptations"][0]
            record["adaptations"].append(
                {
                    "kind": "markdown_insert",
                    "affected": "text:" + identity(201) + ":0",
                    "description": STATIC["GP07-DESCRIPTION-27"],
                    "document_key": identity(201),
                    "owner": identity(2),
                    "evidence": ["attachment:" + identity(201)],
                    "text_edit": edit,
                }
            )
            record["counts"]["text_adaptations"] = 1
        path.write_bytes(json_bytes(record))
        report = vault / "MIGRATION REPORT.md"
        text = report.read_text(encoding="utf8")
        if display is not None:
            intro = "Created 1 thought notes; preserved 1 present payloads.\n\n"
            text = text.replace(
                intro,
                intro
                + STATIC["GP05-REPORT-15"]
                + "1"
                + STATIC["GP05-REPORT-16"]
                + "- [[Home.md|Home]]\n\n",
                1,
            )
        row = (
            "- [[Home.md|Home]] — formatting_loss (local-api.note-formatting.v1): "
            + escaped(issue["message"])
            + " "
            + issue["guidance"]
            + "\n"
        )
        text = text.replace(
            STATIC["GP05-REPORT-12"],
            STATIC["GP05-REPORT-11"] + row + STATIC["GP05-REPORT-12"],
            1,
        )
        report.write_text(text, encoding="utf8", newline="\n")
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 1
