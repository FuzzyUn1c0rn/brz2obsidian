"""The exact reviewed API TXT404/PDF exception at public source boundaries."""

import hashlib
import json

import pytest

from brz2obsidian.contracts import MigrationFailed, MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import PDF, PDF_BYTES, TXT, MissingTxtPdfApi

RULE = "local-api.missing-txt-pdf.v1"


def test_exact_txt404_retains_absence_and_preserved_measured_same_owner_pdf():
    with (
        api_server(MissingTxtPdfApi()) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        assets = {a.asset_id: a for a in session.snapshot.assets}
        assert (assets[TXT].owner, assets[TXT].role, assets[TXT].availability) == (
            HOME,
            "file",
            "absent",
        )
        assert assets[TXT].actual_length is assets[TXT].actual_sha256 is None
        assert assets[PDF].actual_length == len(PDF_BYTES)
        assert assets[PDF].actual_sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
        with session.open_payload(PDF) as stream:
            assert stream.read() == PDF_BYTES
        with pytest.raises(MigrationRefused), session.open_payload(TXT):
            pytest.fail("Unavailable TXT must never yield empty content")
        (finding,) = session.snapshot.findings
        assert (finding.rule_id, finding.kind, finding.affected) == (
            RULE,
            "known_absent_payload",
            (TXT,),
        )
        failed = [r for r in session.acquisition.audit.requests if r.status == 404]
        assert len(failed) == 1
        assert (failed[0].operation, failed[0].subject_id, failed[0].outcome) == (
            "attachment-content",
            TXT,
            "missing_txt_404",
        )
        assert failed[0].actual_length == 0
        original = {
            e.key: json.loads(e.original_json)
            for e in session.snapshot.original_evidence
        }
        decision = original["scope:missing-txt404:" + TXT]
        assert decision["rule_id"] == RULE and decision["outcome"] == "missing_txt404"
        assert set(decision["subjects"]) == {
            "attachment:" + TXT,
            "attachment:" + PDF,
        }
        assert set(decision["evidence"]) == {
            "attachment:" + TXT,
            "attachment:" + PDF,
            "payload:" + TXT,
            "payload:" + PDF,
        }
        assert (
            "CANARY"
            not in session.snapshot.model_dump_json()
            + session.acquisition.model_dump_json()
        )
        session.verify_consistency()


@pytest.mark.parametrize(
    "case",
    [
        "txt_type",
        "txt_note",
        "txt_no_name",
        "txt_basename",
        "txt_extension",
        "txt_foreign_brain",
        "txt_wrong_owner",
        "txt_metadata_mismatch",
        "txt_metadata404",
        "null_graph",
        "graph_mismatch",
        "sole_txt",
        "pdf_other_owner",
        "pdf404",
        "pdf_signature",
        "png_companion",
        "zip_companion",
        "image_companion",
        "icon_companion",
        "external_companion",
        "txt401",
        "txt403",
        "txt500",
        "txt_source_type",
        "txt_name_empty",
        "txt_name_scalar",
        "txt_length_scalar",
        "pdf_foreign_brain",
        "pdf_note",
        "pdf403",
        "txt_timeout",
        "pdf_timeout",
        "txt_interrupted",
        "pdf_interrupted",
        "txt_invalid_utf8",
        "pdf_private",
        "pdf_excluded",
    ],
)
def test_every_required_txt_pdf_predicate_and_operational_failure_refuses(case):
    from io import BytesIO
    from zipfile import ZipFile

    from tests.support.local_api_payloads import PNG, URI

    api = MissingTxtPdfApi()
    txt, pdf = api.attachments[TXT], api.attachments[PDF]
    if case == "txt_source_type":
        txt["sourceType"] = 1
    elif case == "txt_name_empty":
        txt["name"] = ""
    elif case == "txt_name_scalar":
        txt["name"] = 5
    elif case == "txt_length_scalar":
        txt["dataLength"] = True
    elif case == "pdf_foreign_brain":
        pdf["brainId"] = ALONE
    elif case in {"pdf_private", "pdf_excluded"}:
        pdf["sourceId"] = ALONE
        api.thoughts[ALONE].update(
            {"acType": 1}
            if case == "pdf_private"
            else {"forgottenDateTime": "2026-10-14T10:00:00"}
        )
    elif case == "pdf_note":
        pdf["isNotes"] = True
    elif case == "pdf403":
        api.overrides[f"/api/attachments/{BRAIN}/{PDF}/file-content"] = (
            403,
            b"ERROR_BODY_CANARY",
        )
    elif case in {"txt_timeout", "pdf_timeout"}:
        import time

        def delayed_payload(query):
            time.sleep(0.12)
            return 200, b"TIMEOUT_BODY_CANARY"

        identity = TXT if case.startswith("txt") else PDF
        api.overrides[f"/api/attachments/{BRAIN}/{identity}/file-content"] = (
            delayed_payload
        )
    elif case in {"txt_interrupted", "pdf_interrupted"}:
        identity = TXT if case.startswith("txt") else PDF
        api.overrides[f"/api/attachments/{BRAIN}/{identity}/file-content"] = (
            200,
            b"short",
            {"Content-Length": "9999"},
        )
    elif case == "txt_invalid_utf8":
        api.overrides[f"/api/attachments/{BRAIN}/{TXT}/file-content"] = 200, b"\xff"
    elif case == "txt_type":
        txt["type"] = 1
    elif case == "txt_note":
        txt["isNotes"] = True
    elif case == "txt_no_name":
        del txt["name"]
    elif case == "txt_basename":
        txt["location"] = "../authored.txt"
    elif case == "txt_extension":
        txt["location"] = "authored.pdf"
    elif case == "txt_foreign_brain":
        txt["brainId"] = ALONE
    elif case == "txt_wrong_owner":
        path = f"/api/thoughts/{BRAIN}/{HOME}/attachments"
        owned = api.response(path, {})[1]
        api.overrides[path] = (
            200,
            [dict(a, sourceId=ALONE) if a["id"] == TXT else a for a in owned],
        )
    elif case in {"txt_metadata_mismatch", "txt_metadata404"}:
        api.overrides[f"/api/attachments/{BRAIN}/{TXT}/metadata"] = (
            (404, b"ERROR_BODY_CANARY")
            if case.endswith("404")
            else (200, dict(txt, name="different"))
        )
    elif case in {"null_graph", "graph_mismatch"}:
        path = f"/api/thoughts/{BRAIN}/{HOME}/graph"
        graph = api.response(path, {})[1]
        api.overrides[path] = (
            200,
            dict(graph, attachments=None if case == "null_graph" else []),
        )
    elif case == "sole_txt":
        del api.attachments[PDF]
    elif case == "pdf_other_owner":
        pdf["sourceId"] = ALONE
    elif case == "pdf404":
        api.overrides[f"/api/attachments/{BRAIN}/{PDF}/file-content"] = (
            404,
            b"ERROR_BODY_CANARY",
        )
    elif case == "pdf_signature":
        api.payloads[PDF] = b"not a PDF"
    elif case in {"png_companion", "zip_companion"}:
        if case.startswith("png"):
            pdf["location"], api.payloads[PDF] = "opaque.png", PNG
        else:
            stream = BytesIO()
            with ZipFile(stream, "w") as archive:
                archive.writestr("opaque", b"ZIP resource")
            pdf["location"], api.payloads[PDF] = "opaque.zip", stream.getvalue()
    elif case in {"image_companion", "icon_companion", "external_companion"}:
        pdf.update(
            type={"image_companion": 12, "icon_companion": 5, "external_companion": 3}[
                case
            ]
        )
        pdf["location"] = {
            "image_companion": PDF + ".png",
            "icon_companion": "Icon.png",
            "external_companion": URI,
        }[case]
        api.payloads[PDF] = PNG
    elif case.startswith("txt"):
        api.overrides[f"/api/attachments/{BRAIN}/{TXT}/file-content"] = (
            int(case[3:]),
            b"ERROR_BODY_CANARY",
        )
    with (
        api_server(api) as (_, address),
        pytest.raises((MigrationRefused, MigrationFailed)) as failure,
        LocalApiSourceModule(
            LocalApiConfig(
                api_url=address,
                request_timeout=0.05 if case.endswith("timeout") else 30,
            ),
            credentials=lambda: KEY,
            profile_version="2",
        ).open(LocalApiSourceRef(BRAIN)),
    ):
        pytest.fail("Every TXT/PDF exception predicate must qualify")
    assert "CANARY" not in str(failure.value)


def test_successful_zero_length_txt_is_present_without_a_gap_or_substitution():
    api = MissingTxtPdfApi()
    api.overrides[f"/api/attachments/{BRAIN}/{TXT}/file-content"] = 200, b""
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        txt = next(a for a in session.snapshot.assets if a.asset_id == TXT)
        assert (txt.availability, txt.actual_length, txt.actual_sha256) == (
            "present",
            0,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        assert session.snapshot.findings == ()
        with session.open_payload(TXT) as stream:
            assert stream.read() == b""


def captured_gap_inputs(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with (
        api_server(MissingTxtPdfApi()) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        directory = next(tmp_path.glob("brz2obsidian-api-*"))
        source = json.loads((directory / "source.json").read_bytes())
        snapshot = json.loads(session.snapshot.model_dump_json())
        audit = json.loads((directory / "audit.json").read_bytes())
        payloads = {}
        for asset in session.snapshot.assets:
            if asset.availability == "present":
                with session.open_payload(asset.asset_id) as stream:
                    payloads[asset.asset_id] = stream.read()
        assert "CANARY" not in "".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in directory.rglob("*")
            if p.is_file()
        )
    return source, snapshot, audit, payloads
