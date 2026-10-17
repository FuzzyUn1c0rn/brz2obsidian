"""Public controls for an oracle built from raw API evidence, never conversion."""

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


@pytest.mark.parametrize("damage", ["classification"])
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


def reseal(baseline):
    """Synthetic independent requalification; never applied to private inputs."""
    data = json.loads(baseline.manifest_path.read_bytes())
    for name in data["files"]:
        data["files"][name] = fingerprint(baseline.manifest_path.parent / name)
    write_json(baseline.manifest_path, data)
    return load_baseline(
        baseline.manifest_path, fingerprint(baseline.manifest_path)["sha256"]
    )


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
