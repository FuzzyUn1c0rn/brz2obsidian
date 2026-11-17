"""Ordinary internal files through public acquisition and frozen replay."""

import json
import tempfile
from contextlib import closing
from copy import deepcopy

import pytest

from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
from brz2obsidian.contracts import MigrationFailed, MigrationRefused, SourceSnapshot
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain.local_api import (
    LOCAL_API_POLICY,
    LOCAL_API_POLICY_V2,
    LOCAL_API_POLICY_V3,
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import (
    FILE,
    NOTE,
    PDF_BYTES,
    RAW_NOTE,
    PayloadApi,
    attachment,
)

OPAQUE_BYTES = b"\x00\xff\x80opaque\r\n"
OPAQUE_SHA256 = "5279aa9eec014d31258ce8e269703446524731e417120c83eb4699c94d734ee8"


def test_current_profile_preserves_opaque_internal_file_and_replays_exact_bytes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    api = PayloadApi()
    api.attachments[FILE] = attachment(
        FILE, HOME, 1, "clip.mp4", length=len(OPAQUE_BYTES)
    )
    api.attachments[FILE]["name"] = "Raw media label"
    api.payloads[FILE] = OPAQUE_BYTES
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            snapshot = session.snapshot
            asset = next(a for a in snapshot.assets if a.asset_id == FILE)
            assert (
                asset.owner,
                asset.role,
                asset.availability,
                asset.original_name,
                asset.display_name,
                asset.actual_length,
                asset.actual_sha256,
                asset.video_presentation,
            ) == (
                HOME,
                "file",
                "present",
                "clip.mp4",
                "Raw media label",
                11,
                OPAQUE_SHA256,
                None,
            )
            assert snapshot.documents[0].text.encode() == RAW_NOTE
            with session.open_payload(FILE) as stream:
                assert stream.read() == OPAQUE_BYTES
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            assert source["identifiers"]["profile_version"] == "4"
            session.verify_consistency()
    with closing(
        LocalApiSession(
            source=source,
            snapshot=snapshot,
            audit=audit,
            payloads={NOTE: RAW_NOTE, FILE: OPAQUE_BYTES},
            profile_version="4",
            capture_parent=tmp_path,
        )
    ) as replay:
        assert replay.snapshot == snapshot
        with replay.open_payload(FILE) as stream:
            assert stream.read() == OPAQUE_BYTES
        replay.verify_consistency()


@pytest.mark.parametrize(
    ("filename", "raw"),
    [
        ("document.docx", b"PK\x03\x04opaque Office attachment"),
        ("page.html", b'<img src="https://example.invalid/never-fetch">'),
        ("page.mhtml", b"MIME-Version: 1.0\r\nContent-Type: multipart/related\r\n"),
        ("ordinary.md", b"# File heading\n[File link](https://example.invalid)\n"),
        ("ordinary.txt", OPAQUE_BYTES),
        ("future.unreviewed", OPAQUE_BYTES),
        ("without-extension", OPAQUE_BYTES),
        ("pdf", OPAQUE_BYTES),
        ("png", OPAQUE_BYTES),
        ("zip", OPAQUE_BYTES),
        ("empty.future", b""),
    ],
)
def test_current_ordinary_files_are_opaque_without_note_or_media_interpretation(
    filename, raw
):
    api = PayloadApi()
    api.attachments[FILE] = attachment(FILE, HOME, 1, filename, length=len(raw))
    api.payloads[FILE] = raw
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        asset = next(a for a in session.snapshot.assets if a.asset_id == FILE)
        assert (asset.role, asset.availability, asset.actual_length) == (
            "file",
            "present",
            len(raw),
        )
        assert asset.original_name == filename
        assert asset.video_presentation is None
        assert [document.key for document in session.snapshot.documents] == [NOTE]
        assert session.snapshot.documents[0].text.encode() == RAW_NOTE
        with session.open_payload(FILE) as stream:
            assert stream.read() == raw


@pytest.mark.parametrize(
    ("filename", "raw", "diagnostic"),
    [
        ("broken.PDF", OPAQUE_BYTES, "PDF"),
        ("broken.PNG", OPAQUE_BYTES, "image/icon"),
        ("broken.ZIP", b"PK\x03\x04incomplete", "ZIP"),
        ("empty.PDF", b"", "PDF"),
        ("empty.PNG", b"", "image/icon"),
        ("empty.ZIP", b"", "ZIP"),
    ],
)
def test_known_file_formats_cannot_fall_back_to_opaque_admission(
    filename, raw, diagnostic
):
    api = PayloadApi()
    api.attachments[FILE] = attachment(FILE, HOME, 1, filename, length=len(raw))
    api.attachments[FILE]["name"] = "Ordinary file label"
    api.payloads[FILE] = raw
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with (
            pytest.raises(MigrationRefused) as error,
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("A generic file must not bypass its known format validator")
    assert error.value.issues[0].code == "invalid_source"
    assert diagnostic in error.value.issues[0].message


@pytest.mark.parametrize("profile", ["1", "2", "3"])
def test_historical_profiles_do_not_acquire_current_ordinary_file_admission(
    tmp_path, monkeypatch, profile
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    api = PayloadApi()
    api.attachments[FILE] = attachment(
        FILE, HOME, 1, "manual.pdf", length=len(PDF_BYTES)
    )
    api.payloads[FILE] = PDF_BYTES
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=profile,
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            snapshot = session.snapshot
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
        with closing(
            LocalApiSession(
                source=source,
                snapshot=snapshot,
                audit=audit,
                payloads={NOTE: RAW_NOTE, FILE: PDF_BYTES},
                profile_version=profile,
                capture_parent=tmp_path,
            )
        ) as replay:
            assert replay.snapshot == snapshot
            with replay.open_payload(FILE) as stream:
                assert stream.read() == PDF_BYTES
            replay.verify_consistency()
        policy = {
            "1": LOCAL_API_POLICY,
            "2": LOCAL_API_POLICY_V2,
            "3": LOCAL_API_POLICY_V3,
        }[profile]
        workflow = Workflow(
            SourceModuleBinding(module, policy),
            ObsidianRenderer(),
            FilesystemPublisher(),
        )
        metadata = workflow.metadata_factory
        workflow.metadata_factory = lambda: module.run_metadata(metadata())
        vault = tmp_path / "vault"
        result = workflow.convert(LocalApiSourceRef(BRAIN), vault)
        assert result.outcome == "clean", result.issues
        record = json.loads((vault / "migration-record.json").read_bytes())
        assert (
            record["profile_version"] == profile and record["renderer_version"] == "9"
        )
        assert (vault / "Attachments/22222222/manual.pdf").read_bytes() == PDF_BYTES
        api.attachments[FILE]["location"] = "clip.mp4"
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail(
                "Current renderer generation must not widen an old source profile"
            )

    # Start with the actually admitted old-profile capture, not a retagged4.
    declaration = next(r for r in source["records"] if r["key"] == "attachment:" + FILE)
    declaration["value"]["location"] = "clip.mp4"
    changed = snapshot.model_dump(mode="json")
    changed["identity"]["source_sha256"] = changed["identity"]["snapshot_digest"] = ""
    next(a for a in changed["assets"] if a["asset_id"] == FILE)["original_name"] = (
        "clip.mp4"
    )
    evidence = next(
        e for e in changed["original_evidence"] if e["key"] == declaration["key"]
    )
    evidence["original_json"] = json.dumps(declaration["value"])
    with pytest.raises(MigrationRefused) as error:
        replay = LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(changed)),
            audit=audit,
            payloads={NOTE: RAW_NOTE, FILE: PDF_BYTES},
            profile_version=profile,
            capture_parent=tmp_path,
        )
        replay.close()
        pytest.fail("Old-profile constructor must reject the new ordinary-file class")
    assert error.value.issues[0].code == (
        "api_resource_shape_unsupported" if profile == "3" else "invalid_source"
    )


@pytest.fixture
def current_internal_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    api = PayloadApi()
    api.attachments[FILE] = attachment(
        FILE, HOME, 1, "clip.mp4", length=len(OPAQUE_BYTES)
    )
    api.payloads[FILE] = OPAQUE_BYTES
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        snapshot = session.snapshot.model_dump(mode="json")
        directory = next(tmp_path.glob("brz2obsidian-api-*"))
        source = json.loads((directory / "source.json").read_bytes())
        audit = json.loads((directory / "audit.json").read_bytes())
    return source, snapshot, audit, {NOTE: RAW_NOTE, FILE: OPAQUE_BYTES}


@pytest.mark.parametrize(
    "damage",
    ["role", "owner", "availability", "payload", "missing-payload", "known-format"],
)
def test_current_capture_rejects_invalid_file_binding_before_snapshot_exposure(
    tmp_path, current_internal_capture, damage
):
    source, original, audit, payloads = current_internal_capture
    snapshot = deepcopy(original)
    snapshot["identity"]["source_sha256"] = ""
    snapshot["identity"]["snapshot_digest"] = ""
    asset = next(a for a in snapshot["assets"] if a["asset_id"] == FILE)
    if damage == "role":
        asset["role"] = "icon"
    elif damage == "owner":
        asset["owner"] = ALONE
    elif damage == "availability":
        asset.update(availability="absent", actual_length=None, actual_sha256=None)
        payloads.pop(FILE)
    elif damage == "payload":
        # Same length: source-bound digest equality, not size alone, must fail.
        payloads[FILE] = b"\x01" + OPAQUE_BYTES[1:]
    elif damage == "known-format":
        asset["original_name"] = "broken.PNG"
        declaration = next(
            r for r in source["records"] if r["key"] == "attachment:" + FILE
        )
        declaration["value"]["location"] = "broken.PNG"
        evidence = next(
            e for e in snapshot["original_evidence"] if e["key"] == declaration["key"]
        )
        evidence["original_json"] = json.dumps(declaration["value"])
    else:
        payloads.pop(FILE)
    with pytest.raises(MigrationRefused) as error:
        replay = LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads=payloads,
            profile_version="4",
            capture_parent=tmp_path,
        )
        try:
            _ = replay.snapshot
            pytest.fail("Invalid binding must refuse during constructor admission")
        finally:
            replay.close()
    assert error.value.issues[0].code == "invalid_source"
    if damage == "known-format":
        assert "image/icon bytes" in error.value.issues[0].message


@pytest.mark.parametrize(
    ("fault", "expected_type", "expected_code"),
    [
        ("404", MigrationFailed, "api_request_failed"),
        ("403", MigrationFailed, "api_authentication_failed"),
        ("truncated", MigrationRefused, "invalid_source"),
        ("payload-limit", MigrationRefused, "incomplete_source"),
    ],
)
def test_ordinary_file_failures_never_become_an_absent_txt_gap(
    fault, expected_type, expected_code
):
    api = PayloadApi()
    raw = OPAQUE_BYTES * 8
    api.attachments[FILE] = attachment(FILE, HOME, 1, "clip.mp4", length=len(raw))
    api.payloads[FILE] = raw
    endpoint = f"/api/attachments/{BRAIN}/{FILE}/file-content"
    options = {}
    if fault in {"404", "403"}:
        api.overrides[endpoint] = (int(fault), b"REMOTE_ERROR_BODY_CANARY")
    elif fault == "truncated":
        api.overrides[endpoint] = (200, b"partial", {"Content-Length": "1000"})
    else:
        options["max_payload_bytes"] = 64
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address, **options),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with (
            pytest.raises(expected_type) as error,
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("An incomplete ordinary file must not yield an absent asset")
    assert error.value.issues[0].code == expected_code
    assert error.value.issues[0].guidance
    assert "CANARY" not in str(error.value) + repr(error.value.issues)


@pytest.mark.parametrize(
    "damage",
    [
        "note",
        "image",
        "icon",
        "unsafe-name",
        "empty-label",
        "foreign",
        "private",
        "duplicate",
    ],
)
def test_generic_file_admission_keeps_declaration_and_scope_guards(damage):
    api = PayloadApi()
    value = attachment(FILE, HOME, 1, "clip.mp4", length=len(OPAQUE_BYTES))
    api.attachments[FILE] = value
    api.payloads[FILE] = OPAQUE_BYTES
    if damage == "note":
        value["isNotes"] = True
    elif damage in {"image", "icon"}:
        value["type"] = {"image": 12, "icon": 5}[damage]
    elif damage == "unsafe-name":
        value["location"] = "../clip.mp4"
    elif damage == "empty-label":
        value["name"] = ""
    elif damage == "foreign":
        value["brainId"] = ALONE
    elif damage == "private":
        api.thoughts[HOME]["acType"] = 1
    else:
        owned = [api.attachments[NOTE], value, value]
        api.overrides[f"/api/thoughts/{BRAIN}/{HOME}/attachments"] = (200, owned)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail("Generic byte preservation cannot grant source admission")
    assert not any(
        path == f"/api/attachments/{BRAIN}/{FILE}/file-content"
        for path, _, _ in api.requests
    )


def test_excluded_owner_does_not_fetch_or_preserve_its_generic_file():
    api = PayloadApi()
    api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-15T10:00:00"
    api.attachments[FILE] = attachment(
        FILE, ALONE, 1, "clip.mp4", length=len(OPAQUE_BYTES)
    )
    api.payloads[FILE] = OPAQUE_BYTES
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        assert FILE not in {a.asset_id for a in session.snapshot.assets}
        assert ALONE not in {item.key for item in session.snapshot.items}
    assert not any(
        path == f"/api/attachments/{BRAIN}/{FILE}/file-content"
        for path, _, _ in api.requests
    )
