"""External references through public HTTP acquisition, capture and output."""

import json

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import ALONE, BRAIN, KEY, api_server
from tests.support.local_api_payloads import PayloadApi, attachment

FILE = "b2222222-2222-4222-8222-222222222222"
DIRECTORY = "b8888888-8888-4888-8888-888888888888"
FILE_PATH = "C:\\Source\\caf\u00e9 %#.pdf"
FILE_URI = "file:///C:/Source/caf%C3%A9%20%25%23.pdf"
DIRECTORY_PATH = "D:/Projects/Folder Name"
DIRECTORY_URI = "file:///D:/Projects/Folder%20Name"


class ExternalReferenceApi(PayloadApi):
    def __init__(self, *, mixed=False):
        super().__init__()
        self.thoughts[ALONE]["name"] = "External owner"
        self.attachments = (self.attachments if mixed else {}) | {
            FILE: attachment(FILE, ALONE, 2, FILE_PATH, length=987654),
            DIRECTORY: attachment(DIRECTORY, ALONE, 8, DIRECTORY_PATH, length=123),
        }
        if not mixed:
            self.payloads = {}


def test_external_only_non_home_owner_materializes_both_reference_roles(tmp_path):
    api = ExternalReferenceApi()
    with api_server(api) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assets = {row["asset_id"]: row for row in record["asset_targets"]}
    for key, role, original, label, uri in (
        (FILE, "file", FILE_PATH, "caf\u00e9 %#.pdf", FILE_URI),
        (DIRECTORY, "directory", DIRECTORY_PATH, "Folder Name", DIRECTORY_URI),
    ):
        row = assets[key]
        assert (row["owner"], row["role"], row["availability"]) == (
            ALONE,
            role,
            "external",
        )
        assert row["original_name"] == original
        assert row["display_name"] == label
        assert row["external_uri"] == row["resource_link"] == uri
        assert (
            row["relative_path"] is row["actual_length"] is row["actual_sha256"] is None
        )
    note = (tmp_path / "vault/Notes/External owner.md").read_text(encoding="utf-8")
    assert "## Resources" in note
    assert "[caf\u00e9 %#.pdf](<file:///C:/Source/caf%C3%A9%20%25%23.pdf>)" in note
    assert "[Folder Name](<file:///D:/Projects/Folder%20Name>)" in note
    assert "![" not in note and "Absent source" not in note
    assert not any(path.endswith("/file-content") for path, _, _ in api.requests)
    assert record["source_gaps"] == []
    assert not (tmp_path / "vault/Attachments").exists()


@pytest.mark.parametrize("kind", [2, 8])
@pytest.mark.parametrize(
    "location,uri,display,rendered",
    [
        ("c:/Source/Mixed/Name", "file:///c:/Source/Mixed/Name", "Name", "Name"),
        ("C:\\Source/Mixed\\Name", "file:///C:/Source/Mixed/Name", "Name", "Name"),
        ("C:/Source/ Leading", "file:///C:/Source/%20Leading", " Leading", "Leading"),
        (
            "C:/Source/Percent%20Name",
            "file:///C:/Source/Percent%2520Name",
            "Percent%20Name",
            "Percent%20Name",
        ),
        ("C:/Source/[A]&", "file:///C:/Source/%5BA%5D%26", "[A]&", "A &"),
        ("C:/Source/[]", "file:///C:/Source/%5B%5D", "[]", "Resource"),
        ("C:/Source/_`{}", "file:///C:/Source/_%60%7B%7D", "_`{}", "\\_\\`\\{\\}"),
        ("C:/Source/COM0.txt", "file:///C:/Source/COM0.txt", "COM0.txt", "COM0.txt"),
        ("C:/Source/COM10", "file:///C:/Source/COM10", "COM10", "COM10"),
        ("C:/Source/CONIN$", "file:///C:/Source/CONIN%24", "CONIN$", "CONIN$"),
        ("C:/Source/CONOUT$", "file:///C:/Source/CONOUT%24", "CONOUT$", "CONOUT$"),
    ],
)
def test_external_path_literals_preserve_exact_metadata_and_safe_resources(
    tmp_path, kind, location, uri, display, rendered
):
    api = ExternalReferenceApi()
    api.attachments = {FILE: attachment(FILE, ALONE, kind, location)}
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    asset = record["asset_targets"][0]
    assert asset["original_name"] == location
    assert asset["display_name"] == display
    assert asset["resource_link"] == asset["external_uri"] == uri
    note = (tmp_path / "vault/Notes/External owner.md").read_text(encoding="utf-8")
    assert f"- [{rendered}](<{uri}>)" in note
    assert not any(path.endswith("/file-content") for path, _, _ in api.requests)


@pytest.mark.parametrize("kind", [2, 8])
@pytest.mark.parametrize(
    "location",
    [
        "relative.txt",
        "C:relative.txt",
        "C:/",
        "C:\\",
        "C:/Source/",
        "C:/Source//name",
        "C:/Source/./name",
        "C:/Source/../name",
        "C:/Source/name.",
        "C:/Source/name ",
        "C:/Source/name:stream",
        "C:/Source/a<b",
        "C:/Source/a>b",
        'C:/Source/a"b',
        "C:/Source/a|b",
        "C:/Source/a?b",
        "C:/Source/a*b",
        "C:/Source/a\x00b",
        "C:/Source/a\x1fb",
        "\\\\server\\share\\name",
        "\\\\?\\C:\\Source\\name",
        "\\\\.\\C:\\Source\\name",
        "C:/Source/cOn",
        "C:/Source/PRN.txt",
        "C:/AUX/name",
        "C:/Source/Nul.ext",
        "C:/Source/cOm1.log",
        "C:/lpt9/name",
        "C:/Source/COM9",
    ],
)
def test_external_path_rejects_each_disallowed_raw_class(tmp_path, kind, location):
    api = ExternalReferenceApi()
    api.attachments = {FILE: attachment(FILE, ALONE, kind, location)}
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.receipt is None
    assert not (tmp_path / "vault").exists()
    assert not any(path.endswith("/file-content") for path, _, _ in api.requests)


@pytest.mark.parametrize("kind", [2, 8])
@pytest.mark.parametrize(
    "change",
    [
        "name_absent",
        "name_empty",
        "name_authored",
        "type_bool",
        "type_float",
        "source_bool",
        "source_float",
        "source_string",
        "notes_integer",
        "notes_true",
        "foreign_brain",
        "foreign_owner",
        "bad_id",
        "graph_mismatch",
        "metadata_mismatch",
    ],
)
def test_external_declarations_require_exact_scalars_ownership_and_observation_joins(
    kind, change
):
    api = ExternalReferenceApi()
    value = attachment(FILE, ALONE, kind, FILE_PATH)
    api.attachments = {FILE: value}
    if change == "name_absent":
        del value["name"]
    elif change.startswith("name_"):
        value["name"] = "" if change == "name_empty" else "AUTHOR_CANARY"
    elif change.startswith("type_"):
        value["type"] = True if change == "type_bool" else float(kind)
    elif change.startswith("source_"):
        value["sourceType"] = {
            "source_bool": True,
            "source_float": 2.0,
            "source_string": "2",
        }[change]
    elif change.startswith("notes_"):
        value["isNotes"] = 0 if change == "notes_integer" else True
    elif change == "foreign_brain":
        value["brainId"] = FILE
    elif change == "foreign_owner":
        value["sourceId"] = BRAIN
        api.overrides[f"/api/thoughts/{BRAIN}/{ALONE}/attachments"] = (200, [value])
    elif change == "bad_id":
        value["id"] = FILE.replace("-", "")
    elif change == "graph_mismatch":
        graph = api.response(f"/api/thoughts/{BRAIN}/{ALONE}/graph", {})[1]
        graph["attachments"] = []
        api.overrides[f"/api/thoughts/{BRAIN}/{ALONE}/graph"] = (200, graph)
    else:
        api.overrides[f"/api/attachments/{BRAIN}/{FILE}/metadata"] = (
            200,
            value | {"location": "D:/Changed/name"},
        )
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail("Unqualified external declaration must refuse")
    assert not any(path.endswith("/file-content") for path, _, _ in api.requests)


@pytest.mark.parametrize("version", ["1", "2"])
@pytest.mark.parametrize("kind", [2, 8])
def test_older_profiles_refuse_external_reference_roles(version, kind):
    api = ExternalReferenceApi()
    api.attachments = {FILE: attachment(FILE, ALONE, kind, FILE_PATH)}
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=version,
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail("Old profile must not authorize the new external role")


def forbid_external_target_io(monkeypatch):
    import builtins
    import io
    import os
    import subprocess

    def guarded(original):
        def call(path, *args, **kwargs):
            candidates = path if isinstance(path, (list, tuple)) else [path]
            for candidate in candidates:
                if not isinstance(candidate, (str, bytes, os.PathLike)):
                    continue
                text = os.fsdecode(candidate).replace("\\", "/").lower()
                if text.startswith(
                    (
                        "c:/source",
                        "d:/projects",
                        "file:///c:/source",
                        "file:///d:/projects",
                    )
                ):
                    raise AssertionError("External target I/O was attempted")
            return original(path, *args, **kwargs)

        return call

    for module, names in (
        (builtins, ("open",)),
        (io, ("open",)),
        (os, ("open", "stat", "lstat", "listdir", "scandir", "startfile")),
        (subprocess, ("Popen",)),
    ):
        for name in names:
            if hasattr(module, name):
                monkeypatch.setattr(module, name, guarded(getattr(module, name)))


def test_external_target_boundaries_are_never_accessed_and_owned_bytes_still_work(
    tmp_path, monkeypatch
):
    from tests.support.local_api_payloads import NOTE, RAW_NOTE

    api = ExternalReferenceApi(mixed=True)
    forbid_external_target_io(monkeypatch)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert session.snapshot.source_gaps == ()
            assert session.snapshot.findings == ()
            session.verify_consistency()
            for external_id in (FILE, DIRECTORY):
                with pytest.raises(MigrationRefused), session.open_payload(external_id):
                    pytest.fail("An external reference has no captured payload")
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        assert workflow.inspect(LocalApiSourceRef(BRAIN)).outcome == "clean"
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == RAW_NOTE
    content_ids = {
        path.split("/")[-2]
        for path, _, _ in api.requests
        if path.endswith("/file-content")
    }
    assert content_ids == {NOTE}


@pytest.mark.parametrize("kind", [2, 8])
@pytest.mark.parametrize(
    "mutation",
    [
        "uri",
        "role",
        "display",
        "original",
        "source_name",
        "actual_length",
        "actual_hash",
        "payload",
        "availability",
        "omit",
        "profile1",
        "profile2",
    ],
)
def test_fresh_external_capture_rejects_recomputed_invalid_bindings(
    tmp_path, monkeypatch, kind, mutation
):
    import hashlib
    import tempfile

    from brz2obsidian.contracts import SourceSnapshot
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession

    api = ExternalReferenceApi()
    api.attachments = {FILE: attachment(FILE, ALONE, kind, FILE_PATH)}
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        capture = next(tmp_path.glob("brz2obsidian-api-*"))
        source = json.loads((capture / "source.json").read_bytes())
        audit = json.loads((capture / "audit.json").read_bytes())
        snapshot = json.loads(session.snapshot.model_dump_json())
    clean = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        profile_version="3",
    )
    clean.verify_consistency()
    clean.close()
    asset = snapshot["assets"][0]
    fact = source["payloads"][0]
    payloads = {}
    version = "3"
    if mutation == "uri":
        asset["external_uri"] = fact["external_uri"] = "file:///D:/Changed/name"
    elif mutation == "role":
        asset["role"] = "directory" if kind == 2 else "file"
    elif mutation == "display":
        asset["display_name"] = "Wrong basename"
    elif mutation == "original":
        asset["original_name"] = "D:/Changed/name"
    elif mutation == "source_name":
        row = next(r for r in source["records"] if r["key"] == "attachment:" + FILE)
        row["value"]["name"] = ""
        next(e for e in snapshot["original_evidence"] if e["key"] == row["key"])[
            "original_json"
        ] = json.dumps(row["value"])
    elif mutation == "actual_length":
        asset["actual_length"] = fact["actual_length"] = 1
    elif mutation == "actual_hash":
        asset["actual_sha256"] = fact["actual_sha256"] = "0" * 64
    elif mutation == "payload":
        payloads[FILE] = b"fabricated"
    elif mutation == "availability":
        asset["availability"] = fact["availability"] = "present"
        asset["external_uri"] = fact["external_uri"] = None
        payloads[FILE] = b"fabricated"
        asset["actual_length"] = fact["actual_length"] = len(payloads[FILE])
        asset["actual_sha256"] = fact["actual_sha256"] = hashlib.sha256(
            payloads[FILE]
        ).hexdigest()
    elif mutation == "omit":
        snapshot["assets"] = []
        source["payloads"] = []
    else:
        version = mutation[-1]
        source["identifiers"]["profile_version"] = version
    snapshot["identity"].update(source_sha256="", snapshot_digest="")
    with pytest.raises(MigrationRefused):
        fresh = LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads=payloads,
            profile_version=version,
        )
        fresh.close()


@pytest.mark.parametrize("kind", [2, 8])
def test_trusted_external_capture_detects_equal_length_source_path_mutation(
    tmp_path, monkeypatch, kind
):
    import os
    import tempfile

    api = ExternalReferenceApi()
    api.attachments = {FILE: attachment(FILE, ALONE, kind, FILE_PATH)}
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        source = next(tmp_path.glob("brz2obsidian-api-*")) / "source.json"
        before = source.stat()
        raw = source.read_bytes()
        changed = raw.replace(b"Source", b"Tamper")
        assert changed != raw and len(changed) == len(raw)
        source.write_bytes(changed)
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
        with pytest.raises(MigrationRefused):
            session.verify_consistency()


@pytest.mark.parametrize("kind", [2, 8])
def test_valid_raw_separator_only_change_keeps_uri_but_changes_both_content_identities(
    kind,
):
    identities = []
    uris = []
    for path in ("C:\\Source\\Document", "C:/Source/Document"):
        api = ExternalReferenceApi()
        api.attachments = {FILE: attachment(FILE, ALONE, kind, path)}
        with (
            api_server(api) as (_, address),
            LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="3",
            ).open(LocalApiSourceRef(BRAIN)) as session,
        ):
            identities.append(session.source_identity)
            uris.append(session.snapshot.assets[0].external_uri)
            session.verify_consistency()
    assert uris == ["file:///C:/Source/Document"] * 2
    assert identities[0].source_sha256 != identities[1].source_sha256
    assert identities[0].snapshot_digest != identities[1].snapshot_digest


@pytest.mark.parametrize("character,encoded", [("\x7f", "%7F"), ("\x85", "%C2%85")])
def test_existing_path_control_boundary_is_not_broadened(character, encoded):
    api = ExternalReferenceApi()
    path = "C:/Source/Name" + character
    api.attachments = {FILE: attachment(FILE, ALONE, 2, path)}
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        asset = session.snapshot.assets[0]
        assert asset.original_name == path
        assert asset.display_name == "Name" + character
        assert asset.external_uri == "file:///C:/Source/Name" + encoded
        session.verify_consistency()


def test_duplicate_basenames_keep_distinct_external_references(tmp_path):
    api = ExternalReferenceApi()
    api.attachments[FILE]["location"] = "C:/Source/Same"
    api.attachments[DIRECTORY]["location"] = "D:/Projects/Same"
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    note = (tmp_path / "vault/Notes/External owner.md").read_text(encoding="utf-8")
    assert "- [Same](<file:///C:/Source/Same>)" in note
    assert "- [Same](<file:///D:/Projects/Same>)" in note
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert len(record["asset_targets"]) == 2
    originals = {row["key"]: row["records"] for row in record["original_evidence"]}
    assert originals["attachment:" + FILE]["name"] is None
    assert originals["attachment:" + DIRECTORY]["name"] is None
