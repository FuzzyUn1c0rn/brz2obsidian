"""External images retain authored bytes without owned vault obligations."""

import builtins
import io
import json
import os
import shutil
import socket
from copy import deepcopy
from hashlib import sha256

import pytest

from brz2obsidian.application.wiring import default_workflow, local_api_workflow
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.application.test_literal_angles_workflow import literal_archive
from tests.local_acceptance.api_baseline import prepare_controls
from tests.local_acceptance.api_checker import check_api_vault
from tests.local_acceptance.api_recording import ApiRecording
from tests.local_acceptance.checker import check_vault
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.sources.test_local_api_bom import note_api
from tests.support.audit_sources import SCHEMA
from tests.support.local_api import BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import IMAGE, PNG, attachment
from tests.support.reviewed_api_workflow import reviewed_api_workflow

CANARY = "__BRZ_NO_FETCH_CANARY__"
OWNED = "![Owned](.data/md-images/" + IMAGE + ".png)"
RAW = (
    "Before.\n"
    "![Drive](C:\\__BRZ_NO_FETCH_CANARY__\\missing.png#$width=65p$)\n"
    "![Forward](d:/__BRZ_NO_FETCH_CANARY__/missing.png)\n"
    "![HTTPS](https://example.invalid/__BRZ_NO_FETCH_CANARY__.png)\n"
    + OWNED
    + "\nAfter.\n"
).encode()
IMAGE_PATH = "Attachments/22222222/" + IMAGE + ".png"
EXPECTED_RENDERED_BODY = RAW.decode().replace(
    ".data/md-images/" + IMAGE + ".png", IMAGE_PATH
)


@pytest.fixture(scope="module")
def external_outputs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("external-image-audit")
    attempts = []

    def guarded_file(call):
        def guarded(path, *args, **kwargs):
            if CANARY in str(path):
                attempts.append(("file", str(path)))
                raise AssertionError("External canary path must remain a reference")
            return call(path, *args, **kwargs)

        return guarded

    connect, resolve = socket.socket.connect, socket.getaddrinfo

    def guarded_connect(sock, address):
        if address[0] not in {"127.0.0.1", "::1", "localhost"}:
            attempts.append(("connect", str(address)))
            raise AssertionError("Only the synthetic loopback API may be accessed")
        return connect(sock, address)

    def guarded_resolve(host, *args, **kwargs):
        if host not in {"127.0.0.1", "::1", "localhost"}:
            attempts.append(("resolve", str(host)))
            raise AssertionError("External image names must not be resolved")
        return resolve(host, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        for module, name in (
            (builtins, "open"),
            (io, "open"),
            (os, "open"),
            (os, "stat"),
            (os, "lstat"),
        ):
            patch.setattr(module, name, guarded_file(getattr(module, name)))
        patch.setattr(socket.socket, "connect", guarded_connect)
        patch.setattr(socket, "getaddrinfo", guarded_resolve)
        source = literal_archive(
            folder / "source.brz",
            RAW,
            resources=(({"Type": 12, "Location": IMAGE + ".png"}, PNG),),
        )
        with BrzSourceModule().open(source) as session:
            brz_snapshot = session.snapshot
        brz_vault = folder / "brz"
        brz_result = default_workflow().convert(source, brz_vault)
        api = note_api(RAW)
        api.attachments[IMAGE] = attachment(
            IMAGE, HOME, 12, IMAGE + ".png", length=len(PNG)
        )
        api.payloads[IMAGE] = PNG
        api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
        controls = prepare_controls(folder / "controls")
        api_vault = folder / "api"
        with api_server(api) as (_, address):
            recording = ApiRecording(
                folder / "http",
                address,
                brain_id=BRAIN,
                credential=KEY,
                purpose="convert",
            )
            with recording:
                config = LocalApiConfig(api_url=recording.api_url)
                with LocalApiSourceModule(
                    config, credentials=lambda: KEY, profile_version="4"
                ).open(LocalApiSourceRef(BRAIN)) as session:
                    api_snapshot = session.snapshot
                api_result = reviewed_api_workflow(
                    config, credentials=lambda: KEY, profile_version="4"
                ).convert(LocalApiSourceRef(BRAIN), api_vault)
                recording.complete()
            baseline = recording.seal(qualification=controls)
            record = json.loads((api_vault / "migration-record.json").read_bytes())
            assert (record["profile_id"], record["profile_version"]) == (
                "thebrain-local-api-reviewed",
                "4",
            )
        assert not attempts
        yield {
            "brz": (source, brz_vault, brz_result, brz_snapshot),
            "api": (baseline, api_vault, api_result, api_snapshot),
            "attempts": attempts,
        }
        baseline.verify()
        assert not attempts


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_complete_external_images_keep_authored_and_owned_authority(
    external_outputs, adapter
):
    source, vault, result, snapshot = external_outputs[adapter]
    assert result.outcome == "clean", result.issues
    document = next(d for d in snapshot.documents if d.owner == HOME)
    assert document.text == RAW.decode()
    digest = sha256(RAW).hexdigest()
    assert document.text_digest == digest
    assert not document.text_adaptations
    start = RAW.decode().index(OWNED)
    destination = ".data/md-images/" + IMAGE + ".png"
    destination_start = RAW.decode().index(destination)
    image_id = "aaaaaaaa-0000-4000-8000-000000000001" if adapter == "brz" else IMAGE
    expected_references = [
        {
            "start": start,
            "end": start + len(OWNED),
            "expected_original": OWNED,
            "kind": "image",
            "target": image_id,
            "display_text": "Owned",
            "table_cell": False,
            "document_digest": digest,
            "source_target": destination,
            "destination_start": destination_start,
            "destination_end": destination_start + len(destination),
            "presentation_normalization": None,
        }
    ]
    assert [
        r.model_dump(mode="json") for r in document.references
    ] == expected_references
    record = json.loads((vault / "migration-record.json").read_bytes())
    actual = next(d for t in record["item_targets"] for d in t["documents"])
    assert actual["text_digest"] == digest and actual["text_adaptations"] == []
    assert actual["references"] == expected_references
    assert next(vault.rglob("*.original")).read_bytes() == RAW
    assert EXPECTED_RENDERED_BODY.rstrip() in (
        vault / actual["owner_target"]
    ).read_text(encoding="utf-8")
    images = [a for a in record["asset_targets"] if a["role"] == "image"]
    assert len(images) == 1
    image = images[0]
    assert (
        image["asset_id"],
        image["owner"],
        image["availability"],
        image["relative_path"],
        image["actual_length"],
        image["actual_sha256"],
    ) == (image_id, HOME, "present", IMAGE_PATH, len(PNG), sha256(PNG).hexdigest())
    assert (vault / IMAGE_PATH).read_bytes() == PNG
    assert not external_outputs["attempts"]
    if adapter == "brz":
        check_vault(source, vault)
    else:
        check_api_vault(source, vault, profile_version="4")


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_encoded_relative_drive_does_not_acquire_external_authority(
    external_outputs, tmp_path, adapter
):
    raw = b"![Encoded](%43:%5C__BRZ_NO_FETCH_CANARY__%5Cmissing.png)\n"
    vault = tmp_path / "encoded-vault"
    if adapter == "brz":
        source = literal_archive(tmp_path / "encoded.brz", raw)
        result = default_workflow().convert(source, vault)
    else:
        api = note_api(raw)
        api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
        with api_server(api) as (_, address):
            result = local_api_workflow(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            ).convert(LocalApiSourceRef(BRAIN), vault)
    # This unsupported source-local form is refused before the final scanner;
    # a passing emitted producer output must not be invented for this control.
    assert result.outcome == "refused"
    assert [(issue.code, issue.phase) for issue in result.issues] == [
        ("unsupported_feature", "source")
    ]
    assert not vault.exists()
    assert not external_outputs["attempts"]


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_external_exemptions_keep_owned_payload_and_target_source_bound(
    external_outputs, tmp_path, adapter
):
    source, original, result, _ = external_outputs[adapter]
    # Establish the complete source-bound positive before either controlled
    # artifact forgery. Both share the same two original conversions.
    if adapter == "brz":
        check_vault(source, original)
    else:
        check_api_vault(source, original, profile_version="4")
    for damage in ("owned-bytes", "owned-target"):
        vault = tmp_path / damage
        shutil.copytree(original, vault)
        record = json.loads((vault / "migration-record.json").read_bytes())
        image = next(a for a in record["asset_targets"] if a["role"] == "image")
        if damage == "owned-bytes":
            changed = PNG + b"coherent false payload"
            (vault / IMAGE_PATH).write_bytes(changed)
            image["actual_length"] = len(changed)
            image["actual_sha256"] = sha256(changed).hexdigest()
        else:
            changed_path = "Attachments/22222222/coherent-false-target.png"
            image["relative_path"] = changed_path
            (vault / changed_path).write_bytes(PNG)
            (vault / IMAGE_PATH).unlink()
            document = next(d for t in record["item_targets"] for d in t["documents"])
            path = vault / document["owner_target"]
            path.write_text(
                path.read_text(encoding="utf-8").replace(IMAGE_PATH, changed_path),
                encoding="utf-8",
            )
        forged = deepcopy(result.model_dump(mode="json"))
        forged["receipt"]["destination"] = str(vault.resolve())
        rewrite_record(vault, record, forged)
        # Mutable artifact bytes, measured facts, links and manifest agree;
        # immutable raw source ownership/payload/naming authority still wins.
        expected_rejection = {
            ("brz", "owned-bytes"): "payload bytes",
            ("api", "owned-bytes"): "required payload bytes",
            ("brz", "owned-target"): "attachment identity/role/path",
            ("api", "owned-target"): "SVG original filename",
        }[adapter, damage]
        with pytest.raises(AssertionError, match="^" + expected_rejection + "$"):
            if adapter == "brz":
                check_vault(source, vault)
            else:
                check_api_vault(source, vault, profile_version="4")
    assert not external_outputs["attempts"]
