"""Qualified payload preservation through the public source/session seam."""

import hashlib
import json
import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.contracts import MigrationFailed, MigrationRefused, SourceSnapshot
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.sources.test_local_api import golden_inputs
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_graph import DEFINITION
from tests.support.local_api_payloads import (
    DIRECT_ICON,
    FILE,
    IMAGE,
    NOTE,
    PNG,
    RAW_NOTE,
    RICH_NOTE,
    TYPE_ICON,
    URI,
    FilePayloadApi,
    PayloadApi,
    RichPayloadApi,
    attachment,
)


def test_module_refuses_an_unreviewed_selected_profile():
    with pytest.raises(MigrationRefused):
        LocalApiSourceModule(profile_version="3")


def test_explicit_profile2_outer_pairing_preserves_generic_png_without_promoting_it(
    tmp_path,
):

    with api_server(FilePayloadApi()) as (_, address):
        config = LocalApiConfig(api_url=address)
        with (
            pytest.raises(MigrationRefused),
            LocalApiSourceModule(config, credentials=lambda: KEY).open(
                LocalApiSourceRef(BRAIN)
            ),
        ):
            pytest.fail("Profile1 cannot acquire profile2 shapes")
        workflow = local_api_workflow(config, credentials=lambda: KEY)
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        assert workflow.binding.policy.profile_version == "2"
        converted = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert converted.outcome == "clean", converted.issues
        assert (tmp_path / "vault/Attachments/22222222/generic.png").read_bytes() == PNG
        assert (
            tmp_path / "vault/Attachments/22222222/Notes.md.original"
        ).read_bytes() == RAW_NOTE
        assert "[[Attachments/22222222/generic.png" in (
            tmp_path / "vault/Home — Entry.md"
        ).read_text(encoding="utf-8")


def test_raw_markdown_is_captured_exactly_and_read_after_remote_bytes_change():
    with api_server(PayloadApi()) as (api, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert len(session.snapshot.documents) == 1
            document = session.snapshot.documents[0]
            assert document.owner == HOME
            assert document.original_asset_id == NOTE
            assert document.text == RAW_NOTE.decode("utf-8")
            accounting = {e.identity: e for e in session.snapshot.accounting.entries}
            assert (
                accounting["attachment:" + NOTE].disposition,
                accounting["attachment:" + NOTE].references,
            ) == ("normalized", (NOTE,))
            assert (
                accounting["note_text:" + HOME].disposition,
                accounting["note_text:" + HOME].references,
            ) == ("normalized", (document.key,))
            asset = session.snapshot.assets[0]
            assert (
                asset.asset_id,
                asset.role,
                asset.actual_length,
                asset.actual_sha256,
            ) == (
                NOTE,
                "note_original",
                len(RAW_NOTE),
                hashlib.sha256(RAW_NOTE).hexdigest(),
            )
            assert [
                r.actual_length
                for r in session.acquisition.audit.requests
                if r.operation == "attachment-content"
            ] == [len(RAW_NOTE)]
            api.payloads[NOTE] = b"Changed remote content"
            with session.open_payload(NOTE) as stream:
                assert stream.read() == RAW_NOTE
            session.verify_consistency()
        assert sum(path.endswith("/file-content") for path, _, _ in api.requests) == 1


@pytest.mark.parametrize("explicit", [False, True])
def test_complete_note_image_and_owned_or_inherited_icon_are_published(
    tmp_path, explicit
):

    with api_server(RichPayloadApi(explicit=explicit)) as (api, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        reference = LocalApiSourceRef(BRAIN)
        inspected = workflow.inspect(reference)
        assert inspected.outcome == "clean", inspected.issues
        result = workflow.convert(reference, tmp_path / "vault")
        assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    targets = {t["item_key"]: t for t in record["item_targets"]}
    assert targets[HOME]["icon_snapshot"]["effective_icon_asset_id"] == (
        DIRECT_ICON if explicit else TYPE_ICON
    )
    assert targets[DEFINITION]["declared_appearance"]["icon_asset_id"] == TYPE_ICON
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == RICH_NOTE
    assert (tmp_path / f"vault/Attachments/22222222/{IMAGE}.png").read_bytes() == PNG
    home = (tmp_path / "vault/Home — Entry.md").read_text(encoding="utf-8")
    assert f"![Red](Attachments/22222222/{IMAGE}.png)" in home
    assert "[[Notes/Alone.md|Alone]]" in home
    assert URI in home
    assert not any("example.invalid" in path for path, _, _ in api.requests)


@pytest.mark.parametrize("mutation", ["document_text", "asset_role", "item_documents"])
def test_public_capture_rejects_payload_meaning_changes_with_recomputed_identities(
    mutation,
):

    source, snapshot, audit, payloads = golden_inputs()
    snapshot["identity"]["source_sha256"] = snapshot["identity"]["snapshot_digest"] = ""
    if mutation == "document_text":
        snapshot["documents"][0]["text"] = "Invented content"
        snapshot["documents"][0]["text_digest"] = hashlib.sha256(
            b"Invented content"
        ).hexdigest()
    elif mutation == "asset_role":
        snapshot["assets"][0]["role"] = "file"
    else:
        snapshot["items"][0]["document_ids"] = []
    with pytest.raises(MigrationRefused):
        session = LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads=payloads,
        )
        session.close()


def test_forgotten_reference_is_scoped_before_adaptation_without_retaining_unsafe_original(
    tmp_path,
):

    api = PayloadApi()
    api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-14T10:00:00"
    api.payloads[NOTE] = (
        b"Visible\n[EXCLUDED_LABEL_CANARY](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone)\n"
    )
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert next(t for t in record["item_targets"] if t["item_key"] == HOME)[
        "documents"
    ][0]["original_copy_omitted"]
    assert (
        next(t for t in record["item_targets"] if t["item_key"] == HOME)["documents"][
            0
        ]["original_asset_id"]
        is None
    )
    assert not (tmp_path / "vault/Attachments/22222222/Notes.md.original").exists()
    for path in (tmp_path / "vault").rglob("*"):
        if path.is_file():
            assert b"EXCLUDED_LABEL_CANARY" not in path.read_bytes()


def test_note_formatting_uses_reviewed_api_finding_and_source_byte_report(tmp_path):

    api = PayloadApi()
    api.payloads[NOTE] = "> [!tip|icon:😂]\n> Authored body\n".encode()
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "warnings", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert (
        next(t for t in record["asset_targets"] if t["asset_id"] == NOTE)[
            "source_findings"
        ][0]["rule_id"]
        == "local-api.note-formatting.v1"
    )
    assert (
        next(t for t in record["asset_targets"] if t["asset_id"] == NOTE)[
            "source_findings"
        ][0]["kind"]
        == "formatting_loss"
    )
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == api.payloads[NOTE]
    report = (tmp_path / "vault/Migration report.md").read_text(encoding="utf-8")
    assert "Safe originals retain exact source bytes." in report


def test_large_payload_uses_payload_bound_and_owned_capture_is_cleaned(
    tmp_path, monkeypatch
):

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    survivor = tmp_path / "unrelated.txt"
    survivor.write_bytes(b"preserve me")
    api = FilePayloadApi()
    api.attachments[FILE]["location"] = "large.pdf"
    raw = b"%PDF-1.7\n" + b"opaque file bytes\n" * 8192
    api.payloads[FILE] = raw
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(
                api_url=address, max_response_bytes=4096, max_payload_bytes=256000
            ),
            credentials=lambda: KEY,
        )
        with (
            module.open(LocalApiSourceRef(BRAIN)) as session,
            session.open_payload(FILE) as stream,
        ):
            assert stream.read(9) == b"%PDF-1.7\n"
            assert stream.read() == raw[9:]
        assert sorted(p.name for p in tmp_path.iterdir()) == ["unrelated.txt"]
        assert survivor.read_bytes() == b"preserve me"


@pytest.mark.parametrize(
    "defect",
    [
        "note404",
        "icon404",
        "image404",
        "txt404",
        "truncated",
        "invalid_utf8",
        "unknown_signature",
        "foreign_owner",
        "wrong_metadata",
        "graph_mismatch",
        "private_token",
        "image_traversal",
        "image_other_owner",
        "unresolved_thought",
        "rendered_only",
        "payload_bound",
    ],
)
def test_incomplete_or_unqualified_payload_acquisition_never_yields_and_does_not_disclose(
    tmp_path, monkeypatch, defect
):

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    api = RichPayloadApi()
    config = {}
    if defect.endswith("404"):
        asset_id = {
            "note404": NOTE,
            "icon404": TYPE_ICON,
            "image404": IMAGE,
            "txt404": IMAGE,
        }[defect]
        if defect == "txt404":
            api.attachments[IMAGE].update(type=15, location="unavailable.txt")
        api.overrides[f"/api/attachments/{BRAIN}/{asset_id}/file-content"] = (
            404,
            b"HEADER_CANARY SERVICE_TOKEN_CANARY",
        )
    elif defect == "truncated":
        api.overrides[f"/api/attachments/{BRAIN}/{NOTE}/file-content"] = (
            200,
            b"partial",
            {"Content-Length": "100"},
        )
    elif defect == "invalid_utf8":
        api.payloads[NOTE] = b"\xffSERVICE_TOKEN_CANARY"
    elif defect == "unknown_signature":
        api.payloads[TYPE_ICON] = b"SERVICE_TOKEN_CANARY"
    elif defect == "foreign_owner":
        api.attachments[NOTE]["brainId"] = ALONE
    elif defect == "wrong_metadata":
        api.overrides[f"/api/attachments/{BRAIN}/{NOTE}/metadata"] = (
            200,
            dict(api.attachments[NOTE], location="Other.md"),
        )
    elif defect == "graph_mismatch":
        api.overrides[f"/api/thoughts/{BRAIN}/{HOME}/attachments"] = (200, [])
    elif defect == "private_token":
        api.payloads[NOTE] = KEY.encode()
    elif defect == "image_traversal":
        api.payloads[NOTE] = b"![hidden](.data/md-images/../bad.png)"
    elif defect == "image_other_owner":
        api.attachments[IMAGE]["sourceId"] = ALONE
    elif defect == "unresolved_thought":
        api.payloads[NOTE] = b"[missing](brain://qqqqqqqqqkqKqqqqqqqqqg/Missing)"
    elif defect == "rendered_only":
        api.attachments.pop(NOTE)
        api.overrides[f"/api/notes/{BRAIN}/{HOME}"] = (
            200,
            {"markdown": "https://example.invalid/?serviceToken=SERVICE_TOKEN_CANARY"},
        )
    else:
        config["max_payload_bytes"] = 16
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address, **config),
            credentials=lambda: KEY,
            profile_version="2",
        )
        with (
            pytest.raises((MigrationRefused, MigrationFailed)) as error,
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("An incomplete source must never yield")
        assert "CANARY" not in str(error.value) + repr(error.value.issues)
    assert list(tmp_path.iterdir()) == []


def test_acquired_payload_stream_revocation_corruption_and_unknown_access(
    tmp_path, monkeypatch
):

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with api_server(PayloadApi()) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            with pytest.raises(MigrationRefused), session.open_payload(HOME):
                pytest.fail("Unknown payload")
            with session.open_payload(NOTE) as outstanding:
                session.close()
                assert outstanding.closed
                with pytest.raises(MigrationRefused):
                    outstanding.read()
            with pytest.raises(MigrationRefused), session.open_payload(NOTE):
                pytest.fail("Closed payload")
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            directory = next(tmp_path.glob("brz2obsidian-api-*"))
            next((directory / "payload").iterdir()).write_bytes(b"CORRUPTION_CANARY")
            with pytest.raises(MigrationRefused):
                session.verify_consistency()
            with pytest.raises(MigrationRefused), session.open_payload(NOTE):
                pytest.fail("Corrupted payload")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "kind,location,format_name",
    [
        (1, "manual.pdf", "pdf"),
        (15, "source.TXT", "txt"),
        (1, "opaque.zip", "zip"),
        (12, "image.webp", "webp"),
        (5, "Icon.png", "jpeg"),
    ],
)
def test_each_qualified_payload_format_preserves_literal_role_and_bytes(
    kind, location, format_name
):

    if format_name == "pdf":
        raw = b"%PDF-1.7\nopaque binary\x00\xff"
    elif format_name == "txt":
        raw = "Literal café\r\n".encode()
    elif format_name == "jpeg":
        raw = (
            Path(__file__).parents[1] / "fixtures/local_api_acceptance/red-pixel.jpg"
        ).read_bytes()
    elif format_name == "zip":
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("never-extracted.txt", "Opaque archive")
        raw = stream.getvalue()
    else:
        stream = BytesIO()
        Image.new("RGB", (1, 1), "red").save(stream, format="WEBP")
        raw = stream.getvalue()
        location = FILE + ".webp"
    api = PayloadApi()
    api.attachments[FILE] = attachment(FILE, HOME, kind, location, length=12345)
    api.payloads[FILE] = raw
    version = "2" if format_name in {"zip", "jpeg"} else "1"
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=version,
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        asset = next(a for a in session.snapshot.assets if a.asset_id == FILE)
        assert (asset.role, asset.original_name, asset.owner) == (
            {5: "icon", 12: "image"}.get(kind, "file"),
            location,
            HOME,
        )
        assert asset.actual_length == len(raw)
        assert asset.actual_sha256 == hashlib.sha256(raw).hexdigest()
        with session.open_payload(FILE) as captured:
            assert captured.read() == raw


def test_independent_profile2_capture_literal_and_profile_match_remain_exact():

    vector = json.loads(
        (
            Path(__file__).parents[1]
            / "fixtures/local_api_capture/profile2-capture-vector.json"
        ).read_text(encoding="utf-8")
    )
    files = {f["storage_key"]: f["utf8"].encode() for f in vector["retained_files"]}
    source = json.loads(files["source.json"])
    snapshot = SourceSnapshot.model_validate_json(files["snapshot.json"])
    audit = json.loads(files["audit.json"])
    payloads = {
        b["asset_id"]: files[b["storage_key"]]
        for b in json.loads(files["manifest.json"])["payload_bindings"]
    }
    with pytest.raises(MigrationRefused):
        LocalApiSession(
            source=source, snapshot=snapshot, audit=audit, payloads=payloads
        )
    session = LocalApiSession(
        source=source,
        snapshot=snapshot,
        audit=audit,
        payloads=payloads,
        profile_version="2",
    )
    try:
        assert session.source_identity.source_sha256 == vector["expected_source_sha256"]
        assert (
            session.source_identity.snapshot_digest
            == vector["expected_snapshot_digest"]
        )
        assert (
            session.acquisition.integrity_sha256 == vector["expected_integrity_sha256"]
        )
    finally:
        session.close()


def test_replaced_acquisition_storage_preserves_unowned_directory_and_refuses(
    tmp_path, monkeypatch
):

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    api = PayloadApi()
    statistics_path = f"/api/brains/{BRAIN}/statistics"
    stats = api.response(statistics_path, {})
    calls, replacement = 0, None

    def replace_after_acquisition(query):
        nonlocal calls, replacement
        calls += 1
        if calls == 2:
            replacement = next(tmp_path.glob("brz2obsidian-api-acquire-*"))
            replacement.rename(tmp_path / "moved-owned-staging")
            replacement.mkdir()
            (replacement / "unowned.txt").write_bytes(b"UNOWNED_CANARY")
        return stats

    api.overrides[statistics_path] = replace_after_acquisition
    with (
        api_server(api) as (_, address),
        pytest.raises(MigrationFailed) as failure,
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)),
    ):
        pytest.fail("A replaced acquisition directory must refuse before yielding")
    assert "CANARY" not in str(failure.value)
    assert replacement is not None
    assert (replacement / "unowned.txt").read_bytes() == b"UNOWNED_CANARY"


def test_captured_authored_note_cannot_become_an_uninterpreted_asset():
    source, snapshot, audit, payloads = golden_inputs()
    note_keys = {r["key"] for r in source["records"] if r["domain"] == "note_text"}
    source["records"] = [r for r in source["records"] if r["key"] not in note_keys]
    snapshot["original_evidence"] = [
        e for e in snapshot["original_evidence"] if e["key"] not in note_keys
    ]
    snapshot["accounting"]["entries"] = [
        e for e in snapshot["accounting"]["entries"] if e["identity"] not in note_keys
    ]
    snapshot["documents"] = []
    snapshot["items"][0]["document_ids"] = []
    snapshot["identity"]["source_sha256"] = snapshot["identity"]["snapshot_digest"] = ""
    with pytest.raises(MigrationRefused):
        session = LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads=payloads,
        )
        session.close()


def test_source_attachment_decimal_zero_spellings_have_equal_content_identity():
    identities = []
    with api_server(PayloadApi()) as (api, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        original = dict(api.attachments[NOTE])
        for token in ("0", "-0", "0.000", "0e-1000000000"):
            raw = (
                json.dumps(original)
                .replace('"position": 0', '"position": ' + token)
                .encode()
            )
            api.overrides[f"/api/attachments/{BRAIN}/{NOTE}/metadata"] = (200, raw)
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                identities.append(session.source_identity)
        assert len({i.source_sha256 for i in identities}) == 1
        assert len({i.snapshot_digest for i in identities}) == 1


def test_unordered_payload_inventory_changes_keep_identity_but_bytes_and_position_change_it():
    api = RichPayloadApi(jpeg=True)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="2",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            initial = session.source_identity
        api.attachments = dict(reversed(list(api.attachments.items())))
        api.links = dict(reversed(list(api.links.items())))
        api.thoughts = dict(reversed(list(api.thoughts.items())))
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert session.source_identity == initial
        api.attachments[FILE]["position"] = 1.25
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            changed_position = session.source_identity
            assert changed_position.source_sha256 != initial.source_sha256
            assert changed_position.snapshot_digest != initial.snapshot_digest
        api.payloads[NOTE] += b"Changed authored note"
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert (
                session.source_identity.source_sha256 != changed_position.source_sha256
            )
            assert (
                session.source_identity.snapshot_digest
                != changed_position.snapshot_digest
            )


def test_external_resource_cannot_claim_measured_bytes_in_recomputed_capture():
    source, snapshot, audit, payloads = golden_inputs()
    external = next(a for a in snapshot["assets"] if a["availability"] == "external")
    fact = next(p for p in source["payloads"] if p["asset_id"] == external["asset_id"])
    for value in (external, fact):
        value["actual_length"] = 1
        value["actual_sha256"] = hashlib.sha256(b"x").hexdigest()
    snapshot["identity"]["source_sha256"] = snapshot["identity"]["snapshot_digest"] = ""
    with pytest.raises(MigrationRefused):
        session = LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads=payloads,
        )
        session.close()


@pytest.mark.parametrize(
    "field", ["creationDateTime", "modificationDateTime", "fileModificationDateTime"]
)
def test_optional_attachment_timestamp_still_requires_qualified_source_value(field):
    api = PayloadApi()
    api.attachments[NOTE][field] = 42
    with (
        api_server(api) as (_, address),
        pytest.raises(MigrationRefused),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)),
    ):
        pytest.fail("An optional attachment date cannot carry an arbitrary scalar")


def test_optional_attachment_date_omission_null_and_exact_authored_time_remain_distinct():
    api = PayloadApi()
    identities = []
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            identities.append(session.source_identity)
        for value in (None, "2026-12-31T23:59:00-12:00"):
            api.attachments[NOTE]["fileModificationDateTime"] = value
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                identities.append(session.source_identity)
                evidence = next(
                    e
                    for e in session.snapshot.original_evidence
                    if e.key == "attachment:" + NOTE
                )
                assert (
                    json.loads(evidence.original_json)["fileModificationDateTime"]
                    == value
                )
    assert len({i.source_sha256 for i in identities}) == 3


def test_excluded_original_never_reaches_disk_even_when_staging_cleanup_fails(
    tmp_path, monkeypatch
):
    import shutil

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    api = PayloadApi()
    api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-14T10:00:00"
    api.payloads[NOTE] = (
        b"Visible\n[EXCLUDED_LABEL_CANARY](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone)\n"
    )
    actual_open, actual_remove = Path.open, shutil.rmtree
    unsafe_written = False

    class ObservedWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, value):
            nonlocal unsafe_written
            unsafe_written |= b"EXCLUDED_LABEL_CANARY" in value
            return self.stream.write(value)

    def observe_writes(path, mode="r", *args, **kwargs):
        stream = actual_open(path, mode, *args, **kwargs)
        return (
            ObservedWriter(stream)
            if mode == "wb" and tmp_path in path.parents
            else stream
        )

    def fail_staging_cleanup(path, *args, **kwargs):
        if path.name.startswith("brz2obsidian-api-acquire-"):
            raise OSError("FILESYSTEM_CANARY")
        return actual_remove(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observe_writes)
    monkeypatch.setattr(shutil, "rmtree", fail_staging_cleanup)
    with (
        api_server(api) as (_, address),
        pytest.raises(MigrationFailed) as failure,
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)),
    ):
        pytest.fail("Staging teardown failure cannot yield a session")
    assert "CANARY" not in str(failure.value)
    assert not unsafe_written
    assert all(
        b"EXCLUDED_LABEL_CANARY" not in p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    )
