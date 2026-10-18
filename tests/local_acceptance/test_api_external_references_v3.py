"""Independent literal external-file/directory source and output controls."""

import json

from tests.local_acceptance.api_checker import (
    audit_baseline,
    check_api_vault,
    expected_asset,
)
from tests.local_acceptance.test_api_acceptance import (
    fingerprint,
    identity,
    reseal,
    source_case,
    write_json,
)

FILE = (
    2,
    "C:\\Research\\R&D #1\\café [v2].pdf",
    "café [v2].pdf",
    "file:///C:/Research/R%26D%20%231/caf%C3%A9%20%5Bv2%5D.pdf",
    "café  v2 .pdf",
)
DIRECTORY = (
    8,
    "D:/Working Sets/Alpha",
    "Alpha",
    "file:///D:/Working%20Sets/Alpha",
    "Alpha",
)


def external_case(tmp_path, example=FILE, *, source_factory=source_case):
    """Literal graph/list/metadata join and external-only materialized owner."""
    kind, location, display, uri, label = example
    baseline, vault = source_factory(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    owner = {
        "id": identity(6),
        "brainId": identity(1),
        "kind": 1,
        "acType": 0,
        "forgottenDateTime": None,
        "name": "External only",
        "typeId": None,
    }
    attachment = {
        "id": identity(205),
        "brainId": identity(1),
        "sourceId": identity(6),
        "sourceType": 2,
        "type": kind,
        "isNotes": False,
        "location": location,
        "name": None,
        "dataLength": 98765,
    }
    graph = {
        "activeThought": owner,
        "links": [],
        "attachments": [attachment],
        "parents": [],
        "children": [],
        "jumps": [],
        "siblings": [],
        "tags": [],
        "type": None,
    }
    evidence = {
        "external-graph.json": graph,
        "external-list.json": [attachment],
        "external-metadata.json": attachment,
        "external-no-note.json": {
            "brainId": identity(1),
            "sourceId": identity(6),
            "sourceType": 2,
            "markdown": "",
            "html": None,
            "text": None,
            "modificationDateTime": "0001-01-01T00:00:00",
        },
    }

    for name, value in evidence.items():
        write_json(root / name, value)
        manifest["files"][name] = fingerprint(root / name)
    manifest["scope"]["thought_ids"].append(identity(6))
    manifest["scope"]["attachment_ids"].append(identity(205))
    manifest["graphs"][identity(6)] = "external-graph.json"
    manifest["attachment_inventories"] = {identity(6): "external-list.json"}
    manifest["attachment_metadata"] = {
        identity(205): {"status": 200, "path": "external-metadata.json"}
    }

    manifest["no_notes"][identity(6)] = "external-no-note.json"
    for name in manifest["statistics"]:
        statistics = json.loads((root / name).read_bytes())
        statistics["thoughts"] = 3
        write_json(root / name, statistics)
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["profile_version"] = "3"
    record["item_targets"].append(
        {
            "item_key": identity(6),
            "original_identity": identity(6),
            "original_title": "External only",
            "relative_path": "External.md",
            "created": True,
            "creation_reasons": ["content"],
        }
    )
    record["asset_targets"].append(
        {
            "asset_id": identity(205),
            "owner": identity(6),
            "role": "file" if kind == 2 else "directory",
            "availability": "external",
            "relative_path": None,
            "resource_link": uri,
            "original_name": location,
            "display_name": display,
            "actual_length": None,
            "actual_sha256": None,
            "external_uri": uri,
        }
    )
    record["original_evidence"][0]["records"].extend([owner, attachment])
    write_json(path, record)
    (vault / "External.md").write_text(
        "# External only\n\n## Resources\n\n- [" + label + "](<" + uri + ">)\n",
        encoding="utf-8",
    )
    return baseline, vault, attachment


ENTRYPOINTS = ("asset", "baseline", "vault")


def assert_public_accepts(entrypoint, baseline, vault, attachment):
    if entrypoint == "asset":
        assert expected_asset(baseline, attachment, "3")[1:] == ("external", None)
    elif entrypoint == "baseline":
        audit_baseline(baseline, profile_version="3")
    else:
        check_api_vault(baseline, vault, profile_version="3")


def replace_declaration(baseline, vault, changes, *, omitted=()):
    """Fresh independently constructed observation, never production resealing."""
    root = baseline.manifest_path.parent
    attachment = json.loads((root / "external-metadata.json").read_bytes())
    attachment.update(changes)
    for key in omitted:
        attachment.pop(key)
    graph = json.loads((root / "external-graph.json").read_bytes())
    graph["attachments"] = [attachment]
    write_json(root / "external-graph.json", graph)
    write_json(root / "external-list.json", [attachment])
    write_json(root / "external-metadata.json", attachment)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["original_evidence"][0]["records"][-1] = attachment
    write_json(record_path, record)
    return reseal(baseline), attachment


PATH_POSITIVES = [
    (2, "C:/COM0", "COM0", "file:///C:/COM0", "COM0"),
    (8, "C:/COM10", "COM10", "file:///C:/COM10", "COM10"),
    (2, "C:/CONIN$", "CONIN$", "file:///C:/CONIN%24", "CONIN$"),
    (8, "C:/CONOUT$", "CONOUT$", "file:///C:/CONOUT%24", "CONOUT$"),
    (2, "c:/A/100%20.pdf", "100%20.pdf", "file:///c:/A/100%2520.pdf", "100%20.pdf"),
    (8, "D:/ leading/Set", "Set", "file:///D:/%20leading/Set", "Set"),
    (2, "E:/A/a#b&c.pdf", "a#b&c.pdf", "file:///E:/A/a%23b%26c.pdf", "a#b&c.pdf"),
    (8, "F:/é/ca\u0301fe", "ca\u0301fe", "file:///F:/%C3%A9/ca%CC%81fe", "ca\u0301fe"),
    (2, "C:/A/[[]]", "[[]]", "file:///C:/A/%5B%5B%5D%5D", "Resource"),
    (
        2,
        "C:/A/`a_b{c}.pdf",
        "`a_b{c}.pdf",
        "file:///C:/A/%60a_b%7Bc%7D.pdf",
        "\\`a\\_b\\{c\\}.pdf",
    ),
    (8, "C:/A/has\x7fDEL", "has\x7fDEL", "file:///C:/A/has%7FDEL", "has\x7fDEL"),
    (2, "C:/A/has\x85C1", "has\x85C1", "file:///C:/A/has%C2%85C1", "has\x85C1"),
    (
        8,
        "C:/A/external.svg",
        "external.svg",
        "file:///C:/A/external.svg",
        "external.svg",
    ),
]

PATH_NEGATIVES = [
    "relative.pdf",
    "C:relative.pdf",
    "/root/file",
    "//host/share/a",
    "\\\\host\\share\\a",
    "C:/",
    "C:/a/",
    "C:/a//b",
    "C:/a/./b",
    "C:/a/../b",
    "C:/a/file ",
    "C:/a/file.",
    "C:/a/stream:ads",
    'C:/a/quo"te',
    "C:/a/a<b",
    "C:/a/a>b",
    "C:/a/a|b",
    "C:/a/a?b",
    "C:/a/a*b",
    "C:/a/line\nfeed",
    "C:/a/\x00null",
    "C:/NUL",
    "C:/con.pdf",
    "C:/Aux/a",
    "C:/a/COM1.txt",
    "C:/a/lPt9",
    "1:/a",
    "C://device/a",
    "\\\\?\\C:\\file",
]


def mixed_note_case(tmp_path, form="callout"):
    """Literal raw original and existing icon-callout adaptation, independently authored."""
    import hashlib

    baseline, vault, attachment = external_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    raw = "> [!tip|icon:😂]\n> Authored body.\n\n## Resources\n\nAuthored prose.\n"
    displayed = "> [!tip] 😂 Tip\n> Authored body.\n\n## Resources\n\nAuthored prose.\n"
    guard = ""
    if form == "fence":
        raw = displayed = "```\nAuthored body.\n"
        guard = "\n\n```\n"
    elif form == "comment":
        raw = displayed = "<!--\nAuthored body.\n"
        guard = "\n\n-->\n"
    note = dict(
        attachment,
        id=identity(206),
        type=1,
        isNotes=True,
        location="Notes.md",
        dataLength=len(raw.encode("utf-8")),
    )
    (root / "206.bin").write_bytes(raw.encode("utf-8"))
    manifest["files"]["206.bin"] = fingerprint(root / "206.bin")
    manifest["payloads"][identity(206)] = {"status": 200, "path": "206.bin"}
    manifest["scope"]["attachment_ids"].append(identity(206))
    manifest["no_notes"].pop(identity(6))
    graph = json.loads((root / "external-graph.json").read_bytes())
    graph["attachments"].append(note)
    write_json(root / "external-graph.json", graph)
    write_json(root / "external-list.json", [attachment, note])
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["asset_targets"].append(
        {
            "asset_id": identity(206),
            "owner": identity(6),
            "role": "note_original",
            "availability": "present",
            "relative_path": "206.bin",
            "original_name": "Notes.md",
            "display_name": None,
            "actual_length": len(raw.encode("utf-8")),
            "actual_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        }
    )
    record["original_evidence"][0]["records"].append(note)
    write_json(path, record)
    (vault / "206.bin").write_bytes(raw.encode("utf-8"))
    generated = "## Resources\n\n- [café  v2 .pdf](<" + FILE[3] + ">)\n"
    (vault / "External.md").write_text(
        "# External only\n\n" + displayed + "\n" + guard + generated, encoding="utf-8"
    )
    return baseline, vault, attachment, raw, displayed, generated
