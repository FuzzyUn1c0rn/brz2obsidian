"""Qualified payload preservation through the public source/session seam."""

import hashlib
import json
import tempfile

import pytest

from brz2obsidian.contracts import MigrationFailed, MigrationRefused, SourceSnapshot
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.sources.test_local_api import golden_inputs
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import IMAGE, NOTE, TYPE_ICON, RichPayloadApi


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
