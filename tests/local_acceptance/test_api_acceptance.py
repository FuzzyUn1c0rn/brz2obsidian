"""Public controls for an oracle built from raw API evidence, never conversion."""

import ctypes
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.local_acceptance.api_manifest import load_baseline


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def fingerprint(path):
    data = path.read_bytes()
    return {"length": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_pinned_baseline_rejects_changed_source_evidence(tmp_path):
    source = write_json(tmp_path / "graph.json", {"activeThought": {"kind": 1}})
    manifest = write_json(
        tmp_path / "manifest.json",
        {
            "schema": "brz2obsidian.api-acceptance/1",
            "files": {"graph.json": fingerprint(source)},
        },
    )
    pin = fingerprint(manifest)["sha256"]
    assert load_baseline(manifest, pin).fingerprint == pin
    source.write_text('{"activeThought":{"kind":2}}', encoding="utf-8")
    with pytest.raises(AssertionError, match="baseline evidence changed"):
        load_baseline(manifest, pin)


def identity(number):
    return f"00000000-0000-4000-8000-{number:012d}"


def source_case(tmp_path):
    """Literal raw API controls and independently authored actual-output example."""
    root = tmp_path / "baseline"
    root.mkdir()
    brain, home, child, definition, tag = map(identity, (1, 2, 3, 4, 5))
    thoughts = [
        {
            "id": key,
            "brainId": brain,
            "kind": kind,
            "acType": 0,
            "forgottenDateTime": None,
            "name": name,
            "typeId": provider,
        }
        for key, kind, name, provider in (
            (home, 1, "Home", None),
            (child, 1, "Child", definition),
            (definition, 2, "Type", None),
            (tag, 4, "Tag", None),
        )
    ]
    links = [
        {
            "id": identity(key),
            "brainId": brain,
            "thoughtIdA": a,
            "thoughtIdB": b,
            "kind": 1,
            "relation": relation,
            "meaning": meaning,
            "direction": direction,
            "typeId": None,
        }
        for key, a, b, relation, meaning, direction in (
            (101, home, child, 1, 1, -1),
            (102, home, child, 3, 1, 5),
            (103, home, child, 3, 1, 7),
            (104, definition, child, 1, 2, -1),
            (105, tag, child, 1, 5, -1),
        )
    ]
    attachments = [
        {
            "id": identity(key),
            "brainId": brain,
            "sourceId": home,
            "sourceType": 2,
            "type": kind,
            "isNotes": note,
            "location": name,
            "name": None,
            "dataLength": 999999,
        }
        for key, kind, note, name in (
            (201, 1, True, "Notes.md"),
            (202, 12, False, identity(202) + ".webp"),
            (203, 1, False, "manual.pdf"),
            (204, 15, False, "manual.txt"),
        )
    ]
    files = {}

    def evidence(name, value):
        path = write_json(root / name, value)
        files[name] = fingerprint(path)
        return name

    graphs = {}
    for thought in thoughts:
        key = thought["id"]
        graphs[key] = evidence(
            key + ".json",
            {
                "activeThought": thought,
                "links": [
                    r for r in links if key in (r["thoughtIdA"], r["thoughtIdB"])
                ],
                "attachments": attachments if key == home else [],
                "children": [thoughts[1]] if key in (home, definition, tag) else [],
                "parents": [thoughts[0]] if key == child else [],
                "jumps": [thoughts[1]]
                if key == home
                else [thoughts[0]]
                if key == child
                else [],
                "tags": [thoughts[3]] if key == child else [],
                "type": thoughts[2] if key == child else None,
            },
        )
    payloads = {}
    data = {
        201: b"Original note.\n",
        202: b"RIFF\x04\x00\x00\x00WEBP",
        203: b"%PDF-1.7\nsource",
    }
    for key, value in data.items():
        name = str(key) + ".bin"
        (root / name).write_bytes(value)
        files[name] = fingerprint(root / name)
        payloads[identity(key)] = {"status": 200, "path": name}
    payloads[identity(204)] = {"status": 404}
    native = evidence(
        "native.json",
        {"synthetic": True, "review": "independent destination hides incoming source"},
    )
    stats = {
        "brainId": brain,
        "thoughts": 2,
        "thoughtTypes": 1,
        "tags": 1,
        "forgottenThoughts": 0,
        "links": 3,
    }
    manifest = {
        "schema": "brz2obsidian.api-acceptance/1",
        "files": files,
        "brain": evidence(
            "brain.json", {"id": brain, "homeThoughtId": home, "name": "Synthetic"}
        ),
        "scope": {
            "thought_ids": [t["id"] for t in thoughts],
            "relationship_ids": [r["id"] for r in links],
            "attachment_ids": [a["id"] for a in attachments],
        },
        "graphs": graphs,
        "types": evidence("types.json", [thoughts[2]]),
        "tags": {"status": 200, "path": evidence("tags.json", [thoughts[3]])},
        "statistics": [evidence("before.json", stats), evidence("after.json", stats)],
        "link_attachments": {
            r["id"]: evidence(r["id"] + "-attachments.json", []) for r in links
        },
        "no_notes": {
            t["id"]: evidence(
                t["id"] + "-note.json",
                {
                    "brainId": brain,
                    "sourceId": t["id"],
                    "sourceType": 2,
                    "markdown": "",
                    "html": None,
                    "text": None,
                    "modificationDateTime": "0001-01-01T00:00:00",
                },
            )
            for t in thoughts[1:]
        },
        "payloads": payloads,
        "qualification": [native],
        "archive_matches": [],
        "one_way_controls": [
            {
                "relationship_id": identity(102),
                "source_id": home,
                "destination_id": child,
                "direction": 5,
                "destination_hides_source": True,
                "evidence": [native],
                "graph": graphs[home],
            },
            {
                "relationship_id": identity(103),
                "source_id": child,
                "destination_id": home,
                "direction": 7,
                "destination_hides_source": True,
                "evidence": [native],
                "graph": graphs[home],
            },
        ],
    }
    manifest_path = write_json(root / "manifest.json", manifest)
    baseline = load_baseline(manifest_path, fingerprint(manifest_path)["sha256"])
    vault = tmp_path / "vault"
    vault.mkdir()
    targets = []
    for attachment in attachments:
        key = attachment["id"]
        payload = payloads[key]
        relative = key + ".bin" if payload["status"] == 200 else None
        if relative:
            (vault / relative).write_bytes((root / payload["path"]).read_bytes())
        targets.append(
            {
                "asset_id": key,
                "owner": home,
                "role": "note_original"
                if attachment["isNotes"]
                else "image"
                if attachment["type"] == 12
                else "file",
                "availability": "present" if relative else "absent",
                "relative_path": relative,
                "original_name": attachment["location"],
                "display_name": None,
                "actual_length": files[payload["path"]]["length"] if relative else None,
                "actual_sha256": files[payload["path"]]["sha256"] if relative else None,
            }
        )
    record = {
        "profile_id": "thebrain-local-api-reviewed",
        "profile_version": "1",
        "source_identity": {
            "source_id": brain,
            "module_id": "thebrain-local-api",
            "module_version": "1",
            "format_version": "1",
        },
        "item_targets": [
            {
                "item_key": t["id"],
                "original_identity": t["id"],
                "original_title": t["name"],
            }
            for t in thoughts
        ],
        "relationships": [
            {
                "key": r["id"],
                "kind": kind,
                "item_a": r["thoughtIdA"],
                "item_b": r["thoughtIdB"],
            }
            for r, kind in zip(
                links,
                ("hierarchy", "related", "related", "classification", "tag"),
                strict=True,
            )
        ],
        "classification_assignments": [
            {
                "relationship_key": identity(104),
                "definition_key": definition,
                "item_key": child,
            }
        ],
        "asset_targets": targets,
        "original_evidence": [{"records": thoughts + links + attachments}],
        "issues": [
            {
                "code": "approved_source_gap",
                "severity": "warning",
                "rule_id": "local-api.missing-txt-pdf.v1",
                "affected": [identity(204)],
            }
        ],
    }
    write_json(vault / "migration-record.json", record)
    return baseline, vault


def test_complete_raw_api_baseline_accepts_actual_payloads_and_rejects_omitted_relationship(
    tmp_path,
):
    from tests.local_acceptance.api_checker import check_api_vault

    baseline, vault = source_case(tmp_path)
    assert check_api_vault(baseline, vault)["relationships"] == 5
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["relationships"].pop()
    write_json(path, record)
    with pytest.raises(AssertionError, match="relationship identities"):
        check_api_vault(baseline, vault)


@pytest.mark.parametrize("damage", ["endpoint", "classification", "thought", "private"])
def test_source_bound_identities_and_assignments_reject_internally_consistent_omissions(
    tmp_path, damage
):
    from tests.local_acceptance.api_checker import check_api_vault

    baseline, vault = source_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    if damage == "endpoint":
        record["relationships"][0]["item_b"] = identity(4)
    elif damage == "classification":
        record["classification_assignments"].clear()
    elif damage == "thought":
        record["item_targets"].pop()
    else:
        record["item_targets"].append(
            {
                "item_key": identity(99),
                "original_identity": identity(99),
                "original_title": "Excluded",
            }
        )
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault)


@pytest.mark.parametrize(
    "damage", ["omitted", "missing", "corrupt", "owner", "availability", "digest"]
)
def test_every_required_api_payload_is_audited_not_sampled(tmp_path, damage):
    from tests.local_acceptance.api_checker import check_api_vault

    baseline, vault = source_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    target = record["asset_targets"][0]
    if damage == "omitted":
        record["asset_targets"].pop(0)
    elif damage == "missing":
        (vault / target["relative_path"]).unlink()
    elif damage == "corrupt":
        (vault / target["relative_path"]).write_bytes(b"not the original")
    elif damage == "owner":
        target["owner"] = identity(3)
    elif damage == "availability":
        target["availability"] = "absent"
    else:
        target["actual_sha256"] = "0" * 64
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault)


def reseal(baseline):
    """Synthetic independent requalification; never applied to private inputs."""
    data = json.loads(baseline.manifest_path.read_bytes())
    for name in data["files"]:
        data["files"][name] = fingerprint(baseline.manifest_path.parent / name)
    write_json(baseline.manifest_path, data)
    return load_baseline(
        baseline.manifest_path, fingerprint(baseline.manifest_path)["sha256"]
    )


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("-1", "-1"),
        ("-1.0", "-1"),
        ("1e0", "1"),
        ("1.2300", "1.23"),
        ("-0.0", "0"),
        ("0.000000000000000000000000001", "0.000000000000000000000000001"),
        ("9007199254740993.25", "9007199254740993.25"),
        ("12e3", "12000"),
    ],
)
def test_raw_attachment_position_uses_documented_exact_decimal_evidence(
    tmp_path, token, expected
):
    from tests.local_acceptance.api_checker import check_api_vault

    baseline, vault = source_case(tmp_path)
    graph_path = baseline.manifest_path.parent / baseline.data["graphs"][identity(2)]
    graph = json.loads(graph_path.read_bytes())
    graph["attachments"][0]["position"] = "RAW_POSITION_TOKEN"
    graph_path.write_text(
        json.dumps(graph).replace('"RAW_POSITION_TOKEN"', token), encoding="utf-8"
    )
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    attachment = next(
        row
        for row in record["original_evidence"][0]["records"]
        if row["id"] == identity(201)
    )
    attachment["position"] = {"decimal": expected}
    write_json(record_path, record)
    assert check_api_vault(reseal(baseline), vault)["payloads"] == 3


@pytest.mark.parametrize(
    ("source_token", "retained"),
    [
        ("-1.0", {"decimal": "-1.0"}),
        ("-1.0", {"decimal": "-01"}),
        ("-1.0", {"decimal": "-1e0"}),
        ("-1.0", {"decimal": "1"}),
        ("-1.0", {"decimal": "-1", "extra": True}),
        ("-1.0", {"decimal": -1}),
        ("-1.0", -1),
        ("-1.0", None),
        ("-1.0", "OMIT_POSITION"),
        (None, None),
        ("9007199254740993.25", {"decimal": "9007199254740993.2"}),
        ("true", {"decimal": "1"}),
        ('"-1"', {"decimal": "-1"}),
        ('{"decimal":"-1"}', {"decimal": "-1"}),
        ("null", None),
        ("NaN", {"decimal": "0"}),
        ("Infinity", {"decimal": "0"}),
        ("1e1000000000", {"decimal": "1"}),
    ],
)
def test_attachment_decimal_comparison_rejects_changed_or_invalid_facts(
    tmp_path, source_token, retained
):
    from tests.local_acceptance.api_checker import check_api_vault

    baseline, vault = source_case(tmp_path)
    graph_path = baseline.manifest_path.parent / baseline.data["graphs"][identity(2)]
    graph = json.loads(graph_path.read_bytes())
    if source_token is not None:
        graph["attachments"][0]["position"] = "RAW_POSITION_TOKEN"
    graph_path.write_text(
        json.dumps(graph).replace('"RAW_POSITION_TOKEN"', source_token or "null"),
        encoding="utf-8",
    )
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    attachment = next(
        row
        for row in record["original_evidence"][0]["records"]
        if row["id"] == identity(201)
    )
    if retained == "OMIT_POSITION":
        attachment.pop("position", None)
    else:
        attachment["position"] = retained
    write_json(record_path, record)
    with pytest.raises(AssertionError):
        check_api_vault(reseal(baseline), vault)


@pytest.mark.parametrize(
    "damage",
    [
        "visibility",
        "role",
        "no_note",
        "link_content",
        "type_join",
        "tag_join",
        "raw_signature",
    ],
)
def test_resealed_unqualified_source_facts_cannot_become_an_api_verdict(
    tmp_path, damage
):
    from tests.local_acceptance.api_checker import check_api_vault

    baseline, vault = source_case(tmp_path)
    data = json.loads(baseline.manifest_path.read_bytes())
    if damage == "visibility":
        data["one_way_controls"].pop()
        write_json(baseline.manifest_path, data)
    elif damage == "no_note":
        path = baseline.manifest_path.parent / data["no_notes"][identity(4)]
        wrapper = json.loads(path.read_bytes())
        wrapper["markdown"] = "Authored content cannot be silently omitted"
        write_json(path, wrapper)
    elif damage == "link_content":
        write_json(
            baseline.manifest_path.parent / data["link_attachments"][identity(101)],
            [{"id": identity(999)}],
        )
    elif damage == "raw_signature":
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        record["original_evidence"][0]["records"][5]["direction"] = -1
        write_json(path, record)
    else:
        path = baseline.manifest_path.parent / data["graphs"][identity(3)]
        graph = json.loads(path.read_bytes())
        if damage == "role":
            graph["activeThought"]["kind"] = 3
        elif damage == "type_join":
            graph["type"] = None
        else:
            graph["tags"] = []
        write_json(path, graph)
    baseline = reseal(baseline)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault)


def test_full_source_audit_is_available_before_conversion_and_requires_every_payload_outcome(
    tmp_path,
):
    from tests.local_acceptance.api_checker import audit_baseline

    baseline, _ = source_case(tmp_path)
    assert audit_baseline(baseline) == {
        "thoughts": 4,
        "relationships": 5,
        "classifications": 1,
        "attachments": 4,
        "payloads": 3,
        "reviewed_gaps": 1,
        "archive_matches": 0,
        "live_only_payloads": 3,
    }
    data = json.loads(baseline.manifest_path.read_bytes())
    del data["payloads"][identity(202)]
    write_json(baseline.manifest_path, data)
    with pytest.raises(AssertionError, match="payload coverage"):
        audit_baseline(reseal(baseline))


def test_loaded_baseline_cannot_be_rewritten_in_memory_to_bypass_its_external_pin(
    tmp_path,
):
    baseline, _ = source_case(tmp_path)
    baseline.data["scope"]["thought_ids"].pop()
    with pytest.raises(AssertionError, match="manifest"):
        baseline.verify()


def test_nullable_graph_inventory_requires_separate_successful_attachment_list(
    tmp_path,
):
    from tests.local_acceptance.api_checker import audit_baseline

    baseline, _ = source_case(tmp_path)
    data = json.loads(baseline.manifest_path.read_bytes())
    graph_path = baseline.manifest_path.parent / data["graphs"][identity(4)]
    graph = json.loads(graph_path.read_bytes())
    graph["attachments"] = None
    write_json(graph_path, graph)
    inventory = write_json(baseline.manifest_path.parent / "empty-attachments.json", [])
    data["attachment_inventories"] = {identity(4): inventory.name}
    data["files"][inventory.name] = fingerprint(inventory)
    write_json(baseline.manifest_path, data)
    assert audit_baseline(reseal(baseline))["relationships"] == 5
    data = json.loads(baseline.manifest_path.read_bytes())
    data["attachment_inventories"].clear()
    write_json(baseline.manifest_path, data)
    with pytest.raises(AssertionError, match="attachment inventory"):
        audit_baseline(reseal(baseline))


def test_archive_bytes_are_only_equivalent_after_complete_live_byte_comparison(
    tmp_path,
):
    from tests.local_acceptance.api_checker import audit_baseline

    baseline, _ = source_case(tmp_path)
    archive = baseline.manifest_path.parent / "source.brz"
    with ZipFile(archive, "w") as exported:
        exported.writestr("owner/Notes.md", b"Original note.\n")
    data = json.loads(baseline.manifest_path.read_bytes())
    data["files"][archive.name] = fingerprint(archive)
    data["archive_matches"] = [
        {
            "attachment_id": identity(201),
            "archive": archive.name,
            "member": "owner/Notes.md",
        }
    ]
    write_json(baseline.manifest_path, data)
    qualified = audit_baseline(reseal(baseline))
    assert (qualified["archive_matches"], qualified["live_only_payloads"]) == (1, 2)
    with ZipFile(archive, "w") as exported:
        exported.writestr("owner/Notes.md", b"Different archived note\n")
    with pytest.raises(AssertionError, match="archive/live byte equivalence"):
        audit_baseline(reseal(baseline))


def test_statistics_generation_time_does_not_invent_content_drift(tmp_path):
    from tests.local_acceptance.api_checker import audit_baseline

    baseline, _ = source_case(tmp_path)
    data = json.loads(baseline.manifest_path.read_bytes())
    path = baseline.manifest_path.parent / data["statistics"][1]
    stats = json.loads(path.read_bytes())
    stats["dateGenerated"] = "2026-10-14T23:00:01"
    write_json(path, stats)
    assert audit_baseline(reseal(baseline))["thoughts"] == 4
    stats["thoughts"] = 3
    write_json(path, stats)
    with pytest.raises(AssertionError, match="population drift"):
        audit_baseline(reseal(baseline))


@pytest.mark.parametrize(
    "damage", ["duplicate_scope", "foreign_attachment", "boolean_original"]
)
def test_independent_source_coverage_and_exact_json_types_are_not_weakened(
    tmp_path, damage
):
    from tests.local_acceptance.api_checker import check_api_vault

    baseline, vault = source_case(tmp_path)
    data = json.loads(baseline.manifest_path.read_bytes())
    if damage == "duplicate_scope":
        data["scope"]["thought_ids"].append(identity(2))
        write_json(baseline.manifest_path, data)
    elif damage == "foreign_attachment":
        path = baseline.manifest_path.parent / data["graphs"][identity(2)]
        graph = json.loads(path.read_bytes())
        graph["attachments"][0]["brainId"] = identity(999)
        write_json(path, graph)
        # The forged record repeats the same foreign metadata, so agreement
        # with converter output alone cannot establish source ownership.
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        record["original_evidence"][0]["records"][9]["brainId"] = identity(999)
        write_json(path, record)
    else:
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        record["original_evidence"][0]["records"][0]["kind"] = True
        write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(reseal(baseline), vault)


def test_reviewed_txt_absence_requires_its_exact_warning_not_silent_loss(tmp_path):
    from tests.local_acceptance.api_checker import check_api_vault

    baseline, vault = source_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["issues"].clear()
    write_json(path, record)
    with pytest.raises(AssertionError, match="reviewed gap warnings"):
        check_api_vault(baseline, vault)


PNG = (
    Path(__file__).parents[1] / "fixtures/local_api_acceptance/red-pixel.png"
).read_bytes()


def resource_case(tmp_path, shape):
    baseline, vault = source_case(tmp_path)
    data = json.loads(baseline.manifest_path.read_bytes())
    graph_path = baseline.manifest_path.parent / data["graphs"][identity(2)]
    graph = json.loads(graph_path.read_bytes())
    # Modify the present image resource only. Raw note/PDF/TXT controls survive.
    resource = graph["attachments"][1]
    resource.update(type=1, location="opaque.png")
    payload = PNG
    if shape == "file-zip":
        resource["location"] = "opaque.zip"
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("unimported-note.md", b"Opaque member bytes")
        payload = stream.getvalue()
    elif shape == "image-png":
        resource.update(type=12, location=resource["id"] + ".png")
    elif shape == "icon-jpeg":
        resource.update(type=5, location="Icon.png")
        payload = (
            Path(__file__).parents[1] / "fixtures/local_api_acceptance/red-pixel.jpg"
        ).read_bytes()
    write_json(graph_path, graph)
    payload_path = (
        baseline.manifest_path.parent / data["payloads"][resource["id"]]["path"]
    )
    payload_path.write_bytes(payload)
    baseline = reseal(baseline)
    return baseline, vault


@pytest.mark.parametrize("shape", ["file-png", "file-zip", "image-png", "icon-jpeg"])
def test_explicit_reviewed_profile2_adds_exact_four_decoded_resource_shapes(
    tmp_path, shape
):
    from tests.local_acceptance.api_checker import audit_baseline

    baseline, _ = resource_case(tmp_path, shape)
    assert audit_baseline(baseline, profile_version="2")["payloads"] == 3
    with pytest.raises(AssertionError):
        audit_baseline(baseline, profile_version="1")


def test_png_reference_requires_the_actual_note_and_image_owner_to_agree(tmp_path):
    from tests.local_acceptance.api_checker import audit_baseline

    baseline, _ = resource_case(tmp_path, "image-png")
    data = json.loads(baseline.manifest_path.read_bytes())
    root = baseline.manifest_path.parent
    home_path, child_path = (root / data["graphs"][identity(key)] for key in (2, 3))
    home, child = (json.loads(p.read_bytes()) for p in (home_path, child_path))
    image = home["attachments"].pop(1)
    image["sourceId"] = identity(3)
    child["attachments"] = [image]
    write_json(home_path, home)
    write_json(child_path, child)
    (root / data["payloads"][identity(201)]["path"]).write_bytes(
        ("![cross owner](.data/md-images/" + image["location"] + ")\n").encode()
    )
    with pytest.raises(AssertionError):
        audit_baseline(reseal(baseline), profile_version="2")


RESOURCE_CONTROLS = json.loads(
    (
        Path(__file__).parents[1] / "fixtures/local_api_profile/resource-v2.json"
    ).read_bytes()
)["independent_controls"]["controls"]


def apply_resource_control(baseline, vault, case):
    """Real source changes corresponding to independent declarative facts."""
    values = case["input"]
    data = json.loads(baseline.manifest_path.read_bytes())
    root = baseline.manifest_path.parent
    home_path = root / data["graphs"][identity(2)]
    graph = json.loads(home_path.read_bytes())
    attachment = graph["attachments"][1]
    key = attachment["id"]
    attachment.update(
        type=values["type"],
        isNotes=values["isNotes"],
        name=values["name"],
        sourceType=values["sourceType"],
        location=values["location"].replace(values["asset_id"], key),
        sourceId=identity(2)
        if values["sourceId"] == values["owner_id"]
        else identity(999),
        brainId=identity(1)
        if values["attachment_brain_id"] == values["brain_id"]
        else identity(999),
    )
    owner = graph["activeThought"]
    owner.update(
        acType=values["owner_acType"],
        forgottenDateTime=values["owner_forgottenDateTime"],
    )
    if type(values["owner_kind"]) is int and values["owner_kind"] in {2, 4}:
        owner_key = identity(4 if values["owner_kind"] == 2 else 5)
        other_path = root / data["graphs"][owner_key]
        other = json.loads(other_path.read_bytes())
        attachment["sourceId"] = owner_key
        graph["attachments"].remove(attachment)
        other["attachments"].append(attachment)
        write_json(other_path, other)
    else:
        owner["kind"] = values["owner_kind"]
    if values["owner_brain_id"] != values["brain_id"]:
        owner["brainId"] = identity(999)
    if not values["owner_in_included_inventory"]:
        del data["graphs"][identity(2)]
    if (
        not values["metadata_graph_inventory_agree"]
        or not values["unique_owned_resource"]
    ):
        graph["attachments"].append(dict(attachment))
    if "note_reference_owner" in values:
        other_path = root / data["graphs"][identity(3)]
        other = json.loads(other_path.read_bytes())
        graph["attachments"].remove(attachment)
        attachment["sourceId"] = identity(3)
        other["attachments"].append(attachment)
        write_json(other_path, other)
        (root / data["payloads"][identity(201)]["path"]).write_bytes(
            (
                "![cross owner](.data/md-images/" + attachment["location"] + ")\n"
            ).encode()
        )
    write_json(home_path, graph)
    payload_path = root / data["payloads"][key]["path"]
    if values["measured_format"] == "PNG":
        payload_path.write_bytes(PNG)
    elif values["measured_format"] == "JPEG":
        payload_path.write_bytes(
            (
                Path(__file__).parents[1]
                / "fixtures/local_api_acceptance/red-pixel.jpg"
            ).read_bytes()
        )
    if values["decode_eligible"] is False or not values["read_complete"]:
        payload_path.write_bytes(payload_path.read_bytes()[:12])
    if not values["measured_signature_matches_format"]:
        payload_path.write_bytes(b"not the claimed format")
    if values["ZIP_directory_valid"] is False:
        payload_path.write_bytes(b"PK\x03\x04invalid directory")
    data["payloads"][key]["status"] = values["content_status"]
    write_json(baseline.manifest_path, data)
    baseline = reseal(baseline)
    if not values["measured_length_hash_bound_to_bytes"]:
        data = json.loads(baseline.manifest_path.read_bytes())
        data["files"][data["payloads"][key]["path"]]["sha256"] = "0" * 64
        write_json(baseline.manifest_path, data)
        baseline = load_baseline(
            baseline.manifest_path, fingerprint(baseline.manifest_path)["sha256"]
        )
    if isinstance(case["expected"], dict) and case["expected"].get("accept"):
        record_path = vault / "migration-record.json"
        record = json.loads(record_path.read_bytes())
        record["profile_version"] = values["profile_version"]
        record["original_evidence"][0]["records"] = [
            attachment if r.get("id") == key else r
            for r in record["original_evidence"][0]["records"]
        ]
        target = next(t for t in record["asset_targets"] if t["asset_id"] == key)
        target.update(
            owner=attachment["sourceId"],
            role=case["expected"]["asset_role"],
            original_name=attachment["location"],
            actual_length=payload_path.stat().st_size,
            actual_sha256=fingerprint(payload_path)["sha256"],
        )
        (vault / target["relative_path"]).write_bytes(payload_path.read_bytes())
        write_json(record_path, record)
    return baseline


@pytest.mark.parametrize("case", RESOURCE_CONTROLS, ids=lambda case: case["id"])
def test_independent_profile2_controls_use_raw_fields_and_derived_byte_proofs(
    tmp_path, case
):
    from tests.local_acceptance.api_checker import audit_baseline, check_api_vault

    # Profile 3 is now qualified; preserve the unknown-profile negative with 4.
    if case["expected"] == "refuse_unknown_profile_version":
        from copy import deepcopy

        case = deepcopy(case)
        case["input"]["profile_version"] = "4"
    baseline, vault = resource_case(tmp_path, case["shape"])
    if case["id"] == "V2-J03":
        # API input contains no decoder-label assertion. A contradictory claim
        # cannot override the proof derived from the actual JPEG source bytes.
        result = audit_baseline(baseline, profile_version="2")
        proof = result["resource_eligibility"][identity(202)]
        assert proof["format"] == "JPEG" != case["input"]["decoder_classification"]
        return
    accepted = isinstance(case["expected"], dict) and case["expected"].get("accept")
    if accepted:
        baseline = apply_resource_control(baseline, vault, case)
        result = check_api_vault(
            baseline, vault, profile_version=case["input"]["profile_version"]
        )
        assert (result["payloads"], result["relationships"]) == (3, 5)
    else:
        with pytest.raises(AssertionError):
            baseline = apply_resource_control(baseline, vault, case)
            audit_baseline(baseline, profile_version=case["input"]["profile_version"])


def test_truncated_jpeg_is_refused_before_calling_the_native_decoder(
    tmp_path, monkeypatch
):
    from tests.local_acceptance.api_checker import audit_baseline

    baseline, _ = resource_case(tmp_path, "icon-jpeg")
    data = json.loads(baseline.manifest_path.read_bytes())
    path = baseline.manifest_path.parent / data["payloads"][identity(202)]["path"]
    path.write_bytes(path.read_bytes()[:12])

    def unavailable_native(*args):
        raise AssertionError("unexpected native decoder call for incomplete JPEG")

    monkeypatch.setattr(ctypes, "WinDLL", unavailable_native)
    with pytest.raises(AssertionError, match="JPEG completeness"):
        audit_baseline(reseal(baseline), profile_version="2")


def test_missing_native_decoder_leaves_format_eligibility_unavailable(
    tmp_path, monkeypatch
):
    from tests.local_acceptance.api_checker import audit_baseline
    from tests.local_acceptance.images import AuditUnavailable

    baseline, _ = resource_case(tmp_path, "file-png")

    def unavailable_native(*args):
        raise OSError("synthetic absent OS codec boundary")

    monkeypatch.setattr(ctypes, "WinDLL", unavailable_native)
    with pytest.raises(AuditUnavailable):
        audit_baseline(baseline, profile_version="2")


@pytest.mark.parametrize(
    "field,value",
    [("module_id", "thebrain-brz"), ("module_version", "2"), ("format_version", "2")],
)
def test_api_verdict_rejects_incompatible_source_contract_versions(
    tmp_path, field, value
):
    from tests.local_acceptance.api_checker import check_api_vault

    baseline, vault = source_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["source_identity"][field] = value
    write_json(path, record)
    with pytest.raises(AssertionError, match="API module/format"):
        check_api_vault(baseline, vault)


@pytest.mark.parametrize("shape", ["file-png", "file-zip"])
def test_txt404_cannot_use_a_profile2_generic_file_as_its_required_pdf(tmp_path, shape):
    from tests.local_acceptance.api_checker import audit_baseline

    baseline, _ = resource_case(tmp_path, shape)
    data = json.loads(baseline.manifest_path.read_bytes())
    path = baseline.manifest_path.parent / data["graphs"][identity(2)]
    graph = json.loads(path.read_bytes())
    graph["attachments"] = [a for a in graph["attachments"] if a["id"] != identity(203)]
    write_json(path, graph)
    data["scope"]["attachment_ids"].remove(identity(203))
    del data["payloads"][identity(203)]
    write_json(baseline.manifest_path, data)
    with pytest.raises(AssertionError, match="same-owner PDF"):
        audit_baseline(reseal(baseline), profile_version="2")


def test_raw_owned_png_note_joins_its_complete_api_image_inventory(tmp_path):
    from tests.local_acceptance.api_checker import audit_baseline

    baseline, _ = resource_case(tmp_path, "image-png")
    data = json.loads(baseline.manifest_path.read_bytes())
    note_path = baseline.manifest_path.parent / data["payloads"][identity(201)]["path"]
    note_path.write_bytes(
        ("![owned image](.data/md-images/" + identity(202) + ".png)\n").encode()
    )
    result = audit_baseline(reseal(baseline), profile_version="2")
    assert result["resource_eligibility"][identity(202)]["format"] == "PNG"


@pytest.mark.parametrize("profile", ["1", "2", "3"])
def test_public_api_oracle_entrypoints_preserve_inherited_facts(tmp_path, profile):
    from tests.local_acceptance.api_checker import (
        audit_baseline,
        check_api_vault,
        expected_asset,
    )

    baseline, vault = source_case(tmp_path)
    graph = baseline.json(baseline.data["graphs"][identity(2)])
    note = graph["attachments"][0]
    role, availability, payload = expected_asset(baseline, note, profile)
    assert (role, availability) == ("note_original", "present")
    assert payload == b"Original note.\n"
    assert audit_baseline(baseline, profile_version=profile)["relationships"] == 5
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["profile_version"] = profile
    write_json(path, record)
    assert check_api_vault(baseline, vault, profile_version=profile)["payloads"] == 3


@pytest.mark.parametrize("case", RESOURCE_CONTROLS, ids=lambda case: case["id"])
def test_profile3_inherits_independent_profile2_resource_controls(tmp_path, case):
    from copy import deepcopy

    from tests.local_acceptance.api_checker import audit_baseline, check_api_vault

    case = deepcopy(case)
    if case["input"]["profile_version"] == "2":
        case["input"]["profile_version"] = "3"
    # Profile 3 is now qualified; preserve the unknown-profile negative with 4.
    if case["expected"] == "refuse_unknown_profile_version":
        from copy import deepcopy

        case = deepcopy(case)
        case["input"]["profile_version"] = "4"
    baseline, vault = resource_case(tmp_path, case["shape"])
    if case["id"] == "V2-J03":
        proof = audit_baseline(baseline, profile_version="3")["resource_eligibility"][
            identity(202)
        ]
        assert proof["format"] == "JPEG" != case["input"]["decoder_classification"]
        return
    accepted = isinstance(case["expected"], dict) and case["expected"].get("accept")
    if accepted:
        baseline = apply_resource_control(baseline, vault, case)
        result = check_api_vault(baseline, vault, profile_version="3")
        assert (result["payloads"], result["relationships"]) == (3, 5)
    else:
        with pytest.raises(AssertionError):
            baseline = apply_resource_control(baseline, vault, case)
            audit_baseline(baseline, profile_version=case["input"]["profile_version"])


@pytest.mark.parametrize("profile", ["", "4", "unknown", None, 3, True])
def test_public_api_oracle_entrypoints_refuse_unknown_profiles(tmp_path, profile):
    from tests.local_acceptance.api_checker import (
        audit_baseline,
        check_api_vault,
        expected_asset,
    )

    baseline, vault = source_case(tmp_path)
    note = baseline.json(baseline.data["graphs"][identity(2)])["attachments"][0]
    for operation in (
        lambda: expected_asset(baseline, note, profile),
        lambda: audit_baseline(baseline, profile_version=profile),
        lambda: check_api_vault(baseline, vault, profile_version=profile),
    ):
        with pytest.raises(AssertionError, match="unsupported API profile version"):
            operation()


@pytest.mark.parametrize("record_profile", ["1", "2"])
def test_profile3_oracle_refuses_older_vault_profile(tmp_path, record_profile):
    from tests.local_acceptance.api_checker import check_api_vault

    baseline, vault = source_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["profile_version"] = record_profile
    write_json(path, record)
    with pytest.raises(AssertionError, match="API-bound profile"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("family", ["external-file", "external-folder", "jpeg", "svg"])
def test_profile3_shared_oracle_keeps_future_family_eligibility_held(tmp_path, family):
    from tests.local_acceptance.api_checker import audit_baseline, expected_asset

    baseline, _ = source_case(tmp_path)
    path = baseline.manifest_path.parent / baseline.data["graphs"][identity(2)]
    graph = json.loads(path.read_bytes())
    resource = graph["attachments"][1]
    if family in {"external-file", "external-folder"}:
        resource.update(
            type=2 if family == "external-file" else 8,
            location="C:\\External\\Reference",
        )
    else:
        resource.update(
            type=12,
            location=resource["id"] + (".jpg" if family == "jpeg" else ".svg"),
        )
    write_json(path, graph)
    with pytest.raises(AssertionError):
        expected_asset(reseal(baseline), resource, "3")
    with pytest.raises(AssertionError):
        audit_baseline(reseal(baseline), profile_version="3")


def test_profile3_oracle_retains_pin_and_complete_preservation_guards(tmp_path):
    from tests.local_acceptance.api_checker import audit_baseline, check_api_vault

    baseline, vault = source_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["profile_version"] = "3"
    record["relationships"][0]["item_a"], record["relationships"][0]["item_b"] = (
        record["relationships"][0]["item_b"],
        record["relationships"][0]["item_a"],
    )
    write_json(path, record)
    with pytest.raises(AssertionError, match="relationship endpoints/kind"):
        check_api_vault(baseline, vault, profile_version="3")
    note = (
        baseline.manifest_path.parent / baseline.data["payloads"][identity(201)]["path"]
    )
    original = note.read_bytes()
    timestamp = note.stat().st_mtime_ns
    note.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    import os

    os.utime(note, ns=(timestamp, timestamp))
    with pytest.raises(AssertionError, match="baseline evidence changed"):
        audit_baseline(baseline, profile_version="3")
