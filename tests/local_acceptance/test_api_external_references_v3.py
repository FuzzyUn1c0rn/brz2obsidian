"""Independent literal external-file/directory source and output controls."""

import json

import pytest

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


@pytest.mark.parametrize("example", [FILE, DIRECTORY])
def test_expected_asset_qualifies_literal_external_role_without_payload(
    tmp_path, example
):
    baseline, _, attachment = external_case(tmp_path, example)
    assert expected_asset(baseline, attachment, "3") == (
        "file" if example[0] == 2 else "directory",
        "external",
        None,
    )


@pytest.mark.parametrize("example", [FILE, DIRECTORY])
def test_external_census_and_actual_resources_are_preserved(tmp_path, example):
    baseline, vault, _ = external_case(tmp_path, example)
    assert audit_baseline(baseline, profile_version="3")["payloads"] == 3
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 3


@pytest.mark.parametrize("example", [FILE, DIRECTORY])
@pytest.mark.parametrize(
    "damage",
    [
        "omit",
        "wrong-label",
        "wrong-uri",
        "duplicate",
        "embed",
        "uncreated",
        "missing-note",
        "swap-owner",
    ],
)
def test_external_actual_resource_corruption_refuses(tmp_path, example, damage):
    baseline, vault, _ = external_case(tmp_path, example)
    path = vault / "External.md"
    text = path.read_text(encoding="utf-8")
    if damage == "omit":
        text = "# External only\n"
    elif damage == "wrong-label":
        text = text.replace(example[4], "Wrong label")
    elif damage == "wrong-uri":
        text = text.replace(example[3], "file:///C:/wrong")
    elif damage == "duplicate":
        text += text[text.index("- [") :]
    elif damage == "embed":
        text = text.replace("- [", "- ![")
    elif damage == "uncreated":
        record_path = vault / "migration-record.json"
        record = json.loads(record_path.read_bytes())
        record["item_targets"][-1]["created"] = False
        write_json(record_path, record)
    elif damage == "missing-note":
        path.unlink()
    else:
        (vault / "Home.md").write_text(text, encoding="utf-8")
        text = "# External only\n"
    if damage != "missing-note":
        path.write_text(text, encoding="utf-8")
    with pytest.raises((AssertionError, FileNotFoundError)):
        check_api_vault(baseline, vault, profile_version="3")


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


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
@pytest.mark.parametrize("example", PATH_POSITIVES)
def test_established_windows_path_near_misses_remain_eligible(
    tmp_path, entrypoint, example
):
    baseline, vault, attachment = external_case(tmp_path, example)
    assert_public_accepts(entrypoint, baseline, vault, attachment)


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


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
@pytest.mark.parametrize("location", PATH_NEGATIVES)
def test_invalid_windows_path_fresh_construction_refuses(
    tmp_path, entrypoint, location
):
    baseline, vault, _ = external_case(tmp_path)
    baseline, attachment = replace_declaration(baseline, vault, {"location": location})
    with pytest.raises(AssertionError):
        assert_public_accepts(entrypoint, baseline, vault, attachment)


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
@pytest.mark.parametrize(
    "field,value",
    [
        ("type", True),
        ("type", 2.0),
        ("type", "2"),
        ("sourceType", True),
        ("sourceType", 2.0),
        ("sourceType", "2"),
        ("isNotes", 0),
        ("isNotes", True),
        ("name", ""),
        ("name", "authored"),
        ("sourceId", identity(101)),
        ("brainId", identity(99)),
    ],
)
def test_external_authoritative_scalar_predicates_refuse(
    tmp_path, entrypoint, field, value
):
    baseline, vault, _ = external_case(tmp_path)
    baseline, attachment = replace_declaration(baseline, vault, {field: value})
    with pytest.raises(AssertionError):
        assert_public_accepts(entrypoint, baseline, vault, attachment)


@pytest.mark.parametrize("example", [FILE, DIRECTORY])
@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_external_name_must_be_explicitly_null(tmp_path, entrypoint, example):
    baseline, vault, _ = external_case(tmp_path, example)
    baseline, attachment = replace_declaration(baseline, vault, {}, omitted=("name",))
    with pytest.raises(AssertionError):
        assert_public_accepts(entrypoint, baseline, vault, attachment)


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
@pytest.mark.parametrize(
    "damage",
    [
        "metadata-missing",
        "metadata-failure",
        "metadata-status-float",
        "metadata-location",
        "metadata-source-type-float",
        "list-missing",
        "list-null",
        "list-duplicate",
        "list-empty",
        "list-extra",
        "list-length-float",
        "graph-null",
        "payload",
    ],
)
def test_external_joins_and_no_payload_are_independently_qualified(
    tmp_path, entrypoint, damage
):
    baseline, vault, attachment = external_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    if damage == "metadata-missing":
        manifest["attachment_metadata"] = {}
    elif damage == "metadata-failure":
        manifest["attachment_metadata"][identity(205)]["status"] = 404
    elif damage == "metadata-status-float":
        manifest["attachment_metadata"][identity(205)]["status"] = 200.0
    elif damage.startswith("metadata-"):
        row = dict(attachment)
        row.update(
            {"location": "C:/different.pdf"}
            if damage == "metadata-location"
            else {"sourceType": 2.0}
        )
        write_json(root / "external-metadata.json", row)
    elif damage == "list-missing":
        manifest["attachment_inventories"] = {}
    elif damage.startswith("list-"):
        rows = [attachment]
        if damage == "list-null":
            rows = None
        elif damage == "list-duplicate":
            rows *= 2
        elif damage == "list-empty":
            rows = []
        elif damage == "list-extra":
            rows.append(dict(attachment, id=identity(206)))
        else:
            rows = [dict(attachment, dataLength=98765.0)]
        write_json(root / "external-list.json", rows)
    elif damage == "graph-null":
        graph = json.loads((root / "external-graph.json").read_bytes())
        graph["attachments"] = None
        write_json(root / "external-graph.json", graph)
    else:
        manifest["payloads"][identity(205)] = {"status": 200, "path": "201.bin"}
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    if damage == "graph-null":
        assert_public_accepts(entrypoint, baseline, vault, attachment)
    else:
        with pytest.raises(AssertionError):
            assert_public_accepts(entrypoint, baseline, vault, attachment)


@pytest.mark.parametrize("example", [FILE, DIRECTORY])
@pytest.mark.parametrize("profile_version", ["1", "2", "unknown"])
@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_external_families_remain_profile3_only(
    tmp_path, example, profile_version, entrypoint
):
    baseline, vault, attachment = external_case(tmp_path, example)
    with pytest.raises(AssertionError):
        if entrypoint == "asset":
            expected_asset(baseline, attachment, profile_version)
        elif entrypoint == "baseline":
            audit_baseline(baseline, profile_version=profile_version)
        else:
            check_api_vault(baseline, vault, profile_version=profile_version)


@pytest.mark.parametrize("example", [FILE, DIRECTORY])
@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "image"),
        ("availability", "absent"),
        ("original_name", "café [v2].pdf"),
        ("display_name", None),
        ("relative_path", "205.bin"),
        ("actual_length", 0),
        ("actual_sha256", "0" * 64),
        ("external_uri", "file:///C:/wrong"),
        ("resource_link", None),
        ("owner", identity(2)),
    ],
)
def test_external_record_bindings_refuse_forged_measurements_and_paths(
    tmp_path, example, field, value
):
    baseline, vault, _ = external_case(tmp_path, example)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["asset_targets"][-1][field] = value
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "damage",
    [
        "extra-after-section",
        "duplicate-heading",
        "authored-prose-only",
        "empty-heading",
        "launch-html",
    ],
)
def test_external_generated_resources_cannot_be_forged_by_other_prose(tmp_path, damage):
    baseline, vault, _ = external_case(tmp_path)
    path = vault / "External.md"
    body = path.read_text(encoding="utf-8")
    if damage == "extra-after-section":
        body += "\n## Children\n\n- [Wrong](<file:///C:/forged>)\n"
    elif damage == "duplicate-heading":
        body += "\n## Resources\n\nUnrelated prose.\n"
    elif damage == "authored-prose-only":
        body = body.replace("## Resources\n\n", "Prose mentions ## Resources.\n\n")
    elif damage == "empty-heading":
        body = body.replace("## Resources", "### Resources")
    else:
        body += '<a href="file:///C:/forged">Launch</a>\n'
    path.write_text(body, encoding="utf-8")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_external_checker_never_reads_or_opens_target_but_audits_owned_payloads(
    tmp_path, monkeypatch, entrypoint
):
    import os
    import socket
    import urllib.request
    import webbrowser
    from pathlib import Path

    example = (
        2,
        "C:/__oracle_never_read__/missing.pdf",
        "missing.pdf",
        "file:///C:/__oracle_never_read__/missing.pdf",
        "missing.pdf",
    )
    baseline, vault, attachment = external_case(tmp_path, example)
    stat, opened = Path.stat, Path.open

    def forbid_target(operation):
        def guarded(path, *args, **kwargs):
            spelling = str(path).replace("\\", "/").casefold()
            assert "__oracle_never_read__" not in spelling, "forbidden target access"
            return operation(path, *args, **kwargs)

        return guarded

    def forbid(*args, **kwargs):
        raise AssertionError("forbidden external action")

    monkeypatch.setattr(Path, "stat", forbid_target(stat))
    monkeypatch.setattr(Path, "open", forbid_target(opened))
    monkeypatch.setattr(urllib.request, "urlopen", forbid)
    monkeypatch.setattr(socket.socket, "connect", forbid)
    monkeypatch.setattr(webbrowser, "open", forbid)
    monkeypatch.setattr(os, "startfile", forbid, raising=False)
    assert_public_accepts(entrypoint, baseline, vault, attachment)
    if entrypoint != "asset":
        assert (vault / (identity(201) + ".bin")).read_bytes() == b"Original note.\n"


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_changed_raw_path_rejects_old_pin_but_valid_new_review_accepts(
    tmp_path, entrypoint
):
    baseline, vault, attachment = external_case(tmp_path)
    old = baseline
    baseline, changed = replace_declaration(
        baseline, vault, {"location": "C:/New/next.pdf"}
    )
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["asset_targets"][-1].update(
        original_name="C:/New/next.pdf",
        display_name="next.pdf",
        external_uri="file:///C:/New/next.pdf",
        resource_link="file:///C:/New/next.pdf",
    )
    write_json(record_path, record)
    (vault / "External.md").write_text(
        "# External only\n\n## Resources\n\n- [next.pdf](<file:///C:/New/next.pdf>)\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError):
        assert_public_accepts(entrypoint, old, vault, attachment)
    assert old.fingerprint != baseline.fingerprint
    assert_public_accepts(entrypoint, baseline, vault, changed)


def test_raw_slash_spelling_changes_identity_even_with_equal_derived_uri(tmp_path):
    (tmp_path / "backslash").mkdir()
    (tmp_path / "slash").mkdir()
    first, first_vault, _ = external_case(tmp_path / "backslash")
    alternate = (2, "C:/Research/R&D #1/café [v2].pdf", FILE[2], FILE[3], FILE[4])
    second, second_vault, _ = external_case(tmp_path / "slash", alternate)
    assert first.fingerprint != second.fingerprint
    for baseline, vault in ((first, first_vault), (second, second_vault)):
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 3


@pytest.mark.parametrize("profile_version", ["1", "2", "3"])
def test_inherited_type3_url_authored_name_and_uri_remain_distinct(
    tmp_path, profile_version
):
    baseline, vault, _ = external_case(tmp_path)
    baseline, attachment = replace_declaration(
        baseline,
        vault,
        {
            "type": 3,
            "name": "Sample [site]",
            "location": "https://example.invalid/a%20b?x=1#frag",
        },
    )
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["profile_version"] = profile_version
    record["asset_targets"][-1].update(
        role="url",
        original_name="Sample [site]",
        display_name="Sample [site]",
        external_uri="https://example.invalid/a%20b?x=1#frag",
        resource_link="https://example.invalid/a%20b?x=1#frag",
    )
    write_json(record_path, record)
    (vault / "External.md").write_text(
        "# External only\n\n## Resources\n\n- [Sample  site ](<https://example.invalid/a%20b?x=1#frag>)\n",
        encoding="utf-8",
    )
    assert expected_asset(baseline, attachment, profile_version) == (
        "url",
        "external",
        None,
    )
    assert audit_baseline(baseline, profile_version=profile_version)["payloads"] == 3
    assert (
        check_api_vault(baseline, vault, profile_version=profile_version)["payloads"]
        == 3
    )


@pytest.mark.parametrize("damage", [None, "missing-generated"])
def test_authored_resource_heading_does_not_supply_generated_reference(
    tmp_path, damage
):
    baseline, vault, _ = external_case(tmp_path)
    root = baseline.manifest_path.parent
    graph = json.loads((root / "external-graph.json").read_bytes())
    label = "Authored label.\n\n## Resources\n\n- [café  v2 .pdf](<" + FILE[3] + ">)\n"
    graph["activeThought"]["label"] = label
    write_json(root / "external-graph.json", graph)
    baseline = reseal(baseline)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["original_evidence"][0]["records"][-2] = graph["activeThought"]
    write_json(record_path, record)
    generated = "## Resources\n\n- [café  v2 .pdf](<" + FILE[3] + ">)\n"
    (vault / "External.md").write_text(
        "# External only\n\n" + label + ("\n" + generated if damage is None else ""),
        encoding="utf-8",
    )
    if damage is None:
        check_api_vault(baseline, vault, profile_version="3")
    else:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("same_uri", [False, True])
@pytest.mark.parametrize("damage", [None, "omit", "swap-order"])
def test_multiple_reference_identities_preserve_basename_and_raw_spelling(
    tmp_path, same_uri, damage
):
    baseline, vault, first = external_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    location = (
        "C:/Research/R&D #1/café [v2].pdf" if same_uri else "D:/Archive/café [v2].pdf"
    )
    uri = FILE[3] if same_uri else "file:///D:/Archive/caf%C3%A9%20%5Bv2%5D.pdf"
    second = dict(first, id=identity(206), location=location)
    graph = json.loads((root / "external-graph.json").read_bytes())
    graph["attachments"].append(second)
    write_json(root / "external-graph.json", graph)
    write_json(root / "external-list.json", [first, second])
    write_json(root / "second-metadata.json", second)
    manifest["files"]["second-metadata.json"] = fingerprint(
        root / "second-metadata.json"
    )
    manifest["attachment_metadata"][identity(206)] = {
        "status": 200,
        "path": "second-metadata.json",
    }
    manifest["scope"]["attachment_ids"].append(identity(206))
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["asset_targets"].append(
        dict(
            record["asset_targets"][-1],
            asset_id=identity(206),
            original_name=location,
            external_uri=uri,
            resource_link=uri,
        )
    )
    record["original_evidence"][0]["records"].append(second)
    write_json(path, record)
    lines = [
        "- [café  v2 .pdf](<" + FILE[3] + ">)\n",
        "- [café  v2 .pdf](<" + uri + ">)\n",
    ]
    if damage == "omit":
        lines.pop()
    elif damage == "swap-order":
        lines.reverse()
    (vault / "External.md").write_text(
        "# External only\n\n## Resources\n\n" + "".join(lines), encoding="utf-8"
    )
    if damage is None or same_uri and damage == "swap-order":
        assert expected_asset(baseline, second, "3") == ("file", "external", None)
        assert audit_baseline(baseline, profile_version="3")["attachments"] == 6
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 3
    else:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
@pytest.mark.parametrize(
    "field,value",
    [
        ("location", "D:relative"),
        ("location", "D:/NUL.ext"),
        ("name", "Directory"),
        ("isNotes", True),
        ("sourceType", 2.0),
        ("type", 8.0),
        ("type", "8"),
        ("isNotes", 0),
    ],
)
def test_directory_near_misses_cannot_bypass_either_census(
    tmp_path, entrypoint, field, value
):
    baseline, vault, _ = external_case(tmp_path, DIRECTORY)
    baseline, attachment = replace_declaration(baseline, vault, {field: value})
    with pytest.raises(AssertionError):
        assert_public_accepts(entrypoint, baseline, vault, attachment)


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


@pytest.mark.parametrize(
    "damage",
    [None, "omitted-body", "mutated-body", "omitted-generated", "mutated-original"],
)
def test_external_resources_follow_transformed_source_owned_body(tmp_path, damage):
    baseline, vault, attachment, raw, displayed, generated = mixed_note_case(tmp_path)
    assert expected_asset(baseline, attachment, "3") == ("file", "external", None)
    assert audit_baseline(baseline, profile_version="3")["payloads"] == 4
    path = vault / "External.md"
    body = path.read_text(encoding="utf-8")
    if damage == "omitted-body":
        body = body.replace(displayed, "")
    elif damage == "mutated-body":
        body = body.replace("Authored body.", "Forged body.")
    elif damage == "omitted-generated":
        body = body.replace(generated, "")
    elif damage == "mutated-original":
        (vault / "206.bin").write_bytes(
            raw.replace("Authored body.", "Forged body.").encode("utf-8")
        )
    path.write_text(body, encoding="utf-8")
    if damage is None:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4
    else:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_external_source_join_retains_accepted_reverse_hierarchy_profile(
    tmp_path, entrypoint
):
    from tests.local_acceptance.test_api_relationships_v3 import reverse_case

    baseline, vault, attachment = external_case(tmp_path, source_factory=reverse_case)
    assert_public_accepts(entrypoint, baseline, vault, attachment)


@pytest.mark.parametrize(
    "name,uri",
    [
        ("file: guide", "https://example.invalid/guide.svg"),
        ("Guide", "https://example.invalid/guide.svg?next=file:read"),
        ("Guide", "https://example.invalid/guide.svg?text=](file:guide)"),
        ("Guide", "https://example.invalid/guide.svg#](file:guide)"),
    ],
)
@pytest.mark.parametrize("damage", [None, "extra-file-link"])
def test_mixed_type3_url_metadata_cannot_be_misclassified_as_file_reference(
    tmp_path, name, uri, damage
):
    baseline, vault, external = external_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    url = dict(external, id=identity(206), type=3, name=name, location=uri)
    graph = json.loads((root / "external-graph.json").read_bytes())
    graph["attachments"].append(url)
    write_json(root / "external-graph.json", graph)
    write_json(root / "external-list.json", [external, url])
    manifest["scope"]["attachment_ids"].append(identity(206))
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["asset_targets"].append(
        dict(
            record["asset_targets"][-1],
            asset_id=identity(206),
            role="url",
            original_name=name,
            display_name=name,
            external_uri=uri,
            resource_link=uri,
        )
    )
    record["original_evidence"][0]["records"].append(url)
    write_json(path, record)
    body = (
        "# External only\n\n## Resources\n\n- [café  v2 .pdf](<"
        + FILE[3]
        + ">)\n- ["
        + name
        + "](<"
        + uri
        + ">)\n"
    )
    if damage:
        body += "- [Wrong](<file:///C:/forged>)\n"
    (vault / "External.md").write_text(body, encoding="utf-8")
    assert expected_asset(baseline, url, "3") == ("url", "external", None)
    assert audit_baseline(baseline, profile_version="3")["attachments"] == 6
    if damage:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 3


@pytest.mark.parametrize(
    "container", ["whole-fence", "link-fence", "link-comment", "inline-code"]
)
def test_inactive_required_resources_line_cannot_supply_clickable_reference(
    tmp_path, container
):
    baseline, vault, _ = external_case(tmp_path)
    path = vault / "External.md"
    body = path.read_text(encoding="utf-8")
    line = "- [café  v2 .pdf](<" + FILE[3] + ">)\n"
    if container == "whole-fence":
        body = body.replace("## Resources", "```\n## Resources") + "```\n"
    elif container == "link-fence":
        body = body.replace(line, "```\n" + line + "```\n")
    elif container == "link-comment":
        body = body.replace(line, "<!--\n" + line + "-->\n")
    else:
        body = body.replace(line, "`" + line.rstrip("\n") + "`\n")
    path.write_text(body, encoding="utf-8")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("form", ["fence", "comment"])
@pytest.mark.parametrize("missing_guard", [False, True])
def test_generated_resource_boundary_exits_open_authored_construct(
    tmp_path, form, missing_guard
):
    baseline, vault, _, _, _, _ = mixed_note_case(tmp_path, form)
    path = vault / "External.md"
    if missing_guard:
        body = path.read_text(encoding="utf-8")
        boundary = "\n\n```\n" if form == "fence" else "\n\n-->\n"
        path.write_text(body.replace(boundary, "", 1), encoding="utf-8")
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4


@pytest.mark.parametrize(
    "extra",
    [
        "More <file:///C:/forged>\n",
        'More <a href="file:///C:/forged">Wrong</a>\n',
        '<a\nhref="file:///C:/forged">Wrong</a>\n',
        "More [[file:///C:/forged]]\n",
        "More [Wrong](<file:///C:/forged>)\n",
        '<img\nsrc="file:///C:/forged">\n',
        "[Wrong]: <file:///C:/forged>\n",
    ],
)
def test_extra_active_file_targets_in_any_generated_position_refuse(tmp_path, extra):
    baseline, vault, _ = external_case(tmp_path)
    path = vault / "External.md"
    path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "label,guard",
    [
        ("<!A>", ""),
        ("<!A\nopaque>", ""),
        ("<!-- Keep <!A> -->\n<!B>", ""),
        ("```\n<!A>\n```", ""),
        ("```\n<!A>\n", "\n\n```\n"),
        ("<!--\n<!A>\n", "\n\n-->\n"),
    ],
)
@pytest.mark.parametrize("omitted", [False, True])
def test_metadata_label_is_preserved_outside_owned_note_grammar(
    tmp_path, label, guard, omitted
):
    baseline, vault, _ = external_case(tmp_path)
    root = baseline.manifest_path.parent
    graph = json.loads((root / "external-graph.json").read_bytes())
    graph["activeThought"]["label"] = label
    write_json(root / "external-graph.json", graph)
    baseline = reseal(baseline)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["original_evidence"][0]["records"][-2] = graph["activeThought"]
    write_json(record_path, record)
    generated = "## Resources\n\n- [café  v2 .pdf](<" + FILE[3] + ">)\n"
    body = (
        "# External only\n\n" + ("" if omitted else label + "\n\n") + guard + generated
    )
    (vault / "External.md").write_text(body, encoding="utf-8")
    if omitted:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 3
