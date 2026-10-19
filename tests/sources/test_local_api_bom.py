"""BOM-bearing thought notes through public workflow and capture interfaces."""

import hashlib
import json
import tempfile

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.contracts import MigrationRefused, SourceSnapshot
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.sources.test_local_api import golden_inputs
from tests.support.local_api import ALONE, BRAIN, KEY, api_server
from tests.support.local_api_payloads import NOTE, PayloadApi


def note_api(raw):
    api = PayloadApi()
    api.payloads[NOTE] = raw
    api.attachments[NOTE]["dataLength"] = len(raw)
    return api


@pytest.mark.parametrize(
    "body",
    [
        b"```sh\necho <Path with spaces>\n```\n",
        b"```html\n<script>alert('example')</script>\n```\n",
    ],
)
def test_leading_bom_fence_inspects_and_converts_with_exact_original(tmp_path, body):
    raw = b"\xef\xbb\xbf" + body
    with api_server(note_api(raw)) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        converted = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert converted.outcome == "clean", converted.issues
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == raw
    note = next((tmp_path / "vault").glob("Home*.md")).read_text(encoding="utf-8")
    assert body.decode("utf-8").rstrip() in note
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    original = next(a for a in record["asset_targets"] if a["asset_id"] == NOTE)
    assert original["actual_length"] == len(body) + 3
    assert original["actual_sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("profile", ["1", "2", "3"])
def test_previously_qualified_bom_capture_reopens_but_changed_binding_refuses(
    tmp_path, monkeypatch, profile
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    raw = b"\xef\xbb\xbfPreviously accepted plain note.\n"
    with api_server(note_api(raw)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=profile,
        )
        with module.open(LocalApiSourceRef(BRAIN)) as live:
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            snapshot = live.snapshot.model_dump(mode="json")
    # Exact pre-repair successful interpretation: signature and no adaptation.
    snapshot["identity"]["source_sha256"] = snapshot["identity"]["snapshot_digest"] = ""
    snapshot["documents"][0].update(
        text=raw.decode("utf-8"),
        text_digest=hashlib.sha256(raw).hexdigest(),
        text_adaptations=[],
    )
    frozen = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads={NOTE: raw},
        profile_version=profile,
    )
    try:
        frozen.verify_consistency()
        assert frozen.snapshot.documents[0].text == (
            "\ufeffPreviously accepted plain note.\n"
        )
        with frozen.open_payload(NOTE) as stream:
            assert stream.read() == raw
    finally:
        frozen.close()
    snapshot["documents"][0].update(
        text="Invented text", text_digest=hashlib.sha256(b"Invented text").hexdigest()
    )
    with pytest.raises(MigrationRefused):
        LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads={NOTE: raw},
            profile_version=profile,
        )


@pytest.mark.parametrize(
    ("profile", "raw", "expected"),
    [
        (
            "1",
            b"```sh\necho <Path with spaces>\n```\n",
            "```sh\necho <Path with spaces>\n```\n",
        ),
        (
            "2",
            b"\xef\xbb\xbf```html\n<script>literal</script>\n```\n",
            "```html\n<script>literal</script>\n```\n",
        ),
        ("3", b"\xef\xbb\xbf", ""),
        ("1", b"", ""),
        ("3", b"\xef\xbb\xbfStart\xef\xbb\xbfend.\n", "Start\ufeffend.\n"),
    ],
)
def test_note_encoding_controls_keep_exact_bytes(profile, raw, expected):
    with api_server(note_api(raw)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=profile,
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert session.snapshot.documents[0].text == expected
            original = session.snapshot.assets[0]
            assert (original.actual_length, original.actual_sha256) == (
                len(raw),
                hashlib.sha256(raw).hexdigest(),
            )
            with session.open_payload(NOTE) as stream:
                assert stream.read() == raw
            session.verify_consistency()


@pytest.mark.parametrize(
    "raw",
    [
        b"\xef\xbb\xbf\xff",
        b"\xef\xbb\xbf<script>active</script>\n",
        b"<script>active</script>\n",
    ],
)
def test_encoding_fix_does_not_admit_invalid_utf8_or_active_html(raw):
    with api_server(note_api(raw)) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        result = workflow.inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome == "refused"
    assert result.issues


def test_bom_capture_reopens_with_reference_spans_and_exact_edit_evidence(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    raw = b"\xef\xbb\xbf<placeholder> [Alone](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone)\n"
    with api_server(note_api(raw)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as live:
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            snapshot = live.snapshot
            document = snapshot.documents[0]
            assert document.text == (
                "\\<placeholder> [Alone](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone)\n"
            )
            assert [
                (
                    edit.start,
                    edit.end,
                    edit.before,
                    edit.after,
                    edit.adapted_start,
                    edit.adapted_end,
                )
                for edit in document.text_adaptations
            ] == [
                (0, 1, "\ufeff", "", 0, 0),
                (1, 14, "<placeholder>", "\\<placeholder>", 0, 14),
            ]
            assert {edit.source_digest for edit in document.text_adaptations} == {
                hashlib.sha256(raw).hexdigest()
            }
            reference = document.references[0]
            assert reference.target == ALONE
            assert (reference.start, reference.end) == (15, 60)
            assert document.text[reference.start : reference.end] == (
                "[Alone](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone)"
            )
            assert reference.document_digest == document.text_digest
    frozen = LocalApiSession(
        source=source, snapshot=snapshot, audit=audit, payloads={NOTE: raw}
    )
    try:
        assert frozen.snapshot == snapshot
        frozen.verify_consistency()
        with frozen.open_payload(NOTE) as stream:
            assert stream.read() == raw
    finally:
        frozen.close()
    with pytest.raises(MigrationRefused):
        LocalApiSession(
            source=source, snapshot=snapshot, audit=audit, payloads={NOTE: raw[3:]}
        )


def test_bom_scope_removal_maps_reference_back_to_retained_source_text():
    raw = b"\xef\xbb\xbf[Alone](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone) kept.\n"
    api = note_api(raw)
    api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-14T10:00:00"
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            document = session.snapshot.documents[0]
            assert document.text == " kept.\n"
            assert not document.references
            assert document.original_copy_omitted
            assert document.original_asset_id is None
            assert not session.snapshot.assets
            assert [
                (edit.start, edit.end, edit.before, edit.after)
                for edit in document.text_adaptations
            ] == [(0, 1, "\ufeff", "")]
            session.verify_consistency()


def test_prior_bom_capture_reopens_when_new_interpretation_would_refuse():
    source, snapshot, audit, payloads = golden_inputs("3")
    raw = (
        b"\xef\xbb\xbf```text\nExample\n```\n"
        b"[Missing](brain://MzMzMzMzM0ODMzMzMzMzMw/Missing)\n"
    )
    text = raw.decode("utf-8")
    measured = hashlib.sha256(raw).hexdigest()
    note_id = snapshot["documents"][0]["original_asset_id"]
    for record in source["records"]:
        if record["domain"] == "note_text":
            record["value"]["text"] = text
        elif record["domain"] == "attachment" and record["value"]["id"] == note_id:
            record["value"]["dataLength"] = len(raw)
    for evidence in snapshot["original_evidence"]:
        record = next(
            (r for r in source["records"] if r["key"] == evidence["key"]), None
        )
        if record is not None:
            evidence["original_json"] = json.dumps(record["value"])
    for asset in snapshot["assets"] + source["payloads"]:
        if asset["asset_id"] == note_id:
            asset.update(actual_length=len(raw), actual_sha256=measured)
    snapshot["documents"][0].update(text=text, text_digest=measured)
    snapshot["identity"]["source_sha256"] = snapshot["identity"]["snapshot_digest"] = ""
    payloads[note_id] = raw
    # The old parser owns the trailing reference as unclosed fenced code.
    # New live acquisition refuses it; exact prior captures remain valid under
    # their already sealed interpretation.
    frozen = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        profile_version="3",
    )
    try:
        assert not frozen.snapshot.documents[0].references
        frozen.verify_consistency()
    finally:
        frozen.close()
