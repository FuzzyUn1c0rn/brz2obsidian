import json

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain.local_api import (
    LOCAL_API_POLICY,
    LOCAL_API_POLICY_V2,
    LOCAL_API_POLICY_V3,
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import BRAIN, KEY, api_server
from tests.support.local_api_payloads import (
    SHAPE_MESSAGES,
    RichPayloadApi,
    assert_published_payloads,
    unsupported_shape_api,
)


def test_standard_profile3_preserves_inherited_resources_and_direct_default(tmp_path):
    assert LocalApiSourceModule().profile_version == "1"
    with api_server(RichPayloadApi(jpeg=True)) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        assert workflow.binding.policy.profile_version == "3"
        assert workflow.binding.source.profile_version == "3"
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
        assert result.receipt.verified
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert record["profile_version"] == "3"
    assert_published_payloads(tmp_path / "vault", jpeg=True)


@pytest.mark.parametrize("version", ["1", "2", "3"])
@pytest.mark.parametrize("stage", ["search", "relationship", "resource"])
def test_unsupported_source_stage_is_safe_and_profile_gated(tmp_path, version, stage):
    with api_server(unsupported_shape_api(stage)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=version,
        )
        policy = {
            "1": LOCAL_API_POLICY,
            "2": LOCAL_API_POLICY_V2,
            "3": LOCAL_API_POLICY_V3,
        }[version]
        workflow = Workflow(
            SourceModuleBinding(module, policy),
            ObsidianRenderer(),
            FilesystemPublisher(),
        )
        for result in (
            workflow.inspect(LocalApiSourceRef(BRAIN)),
            workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "refused"),
        ):
            assert result.outcome == "refused", result.issues
            assert result.receipt is None
            assert result.issues[0].code == (
                f"api_{stage}_shape_unsupported" if version == "3" else "invalid_source"
            )
            if version == "3":
                assert result.issues[0].message == SHAPE_MESSAGES[stage]
            assert "CANARY" not in result.model_dump_json()
        assert not (tmp_path / "refused").exists()


@pytest.mark.parametrize("version", ["1", "2", "unknown"])
def test_profile3_capture_refuses_other_selected_profiles(version):
    from brz2obsidian.contracts import MigrationRefused, SourceSnapshot
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession
    from tests.sources.test_local_api import golden_inputs

    source, snapshot, audit, payloads = golden_inputs("3")
    with pytest.raises(MigrationRefused):
        LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads=payloads,
            profile_version=version,
        )


@pytest.mark.parametrize(
    "fault",
    [
        "ownership",
        "bytes",
        "credentials",
        "transport",
        "relationship_kind",
        "relationship_type",
    ],
)
def test_profile3_stage_messages_do_not_reclassify_other_source_failures(fault):
    from tests.support.local_api import MetadataApi
    from tests.support.local_api_graph import HIERARCHY, GraphApi
    from tests.support.local_api_payloads import IMAGE

    api = RichPayloadApi()
    if fault.startswith("relationship_"):
        api = GraphApi()
        api.links[HIERARCHY]["kind" if fault == "relationship_kind" else "typeId"] = (
            False
        )
    elif fault == "ownership":
        api.search = MetadataApi().search
        api.search[0]["brainId"] = "99999999-9999-4999-8999-999999999999"
    elif fault == "bytes":
        api.payloads[IMAGE] = b"INVALID_BYTES_CANARY"
    elif fault == "transport":
        api.overrides[f"/api/brains/{BRAIN}"] = 401, b"PRIVATE_REMOTE_CANARY"
    with api_server(api) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address),
            credentials=lambda: None if fault == "credentials" else KEY,
        )
        result = workflow.inspect(LocalApiSourceRef(BRAIN))
    expected = {
        "ownership": "invalid_source",
        "bytes": "invalid_source",
        "credentials": "api_credentials_missing",
        "transport": "api_authentication_failed",
        "relationship_kind": "invalid_source",
        "relationship_type": "invalid_source",
    }
    assert result.issues[0].code == expected[fault]
    assert "CANARY" not in result.model_dump_json()


@pytest.mark.parametrize(
    "family",
    [
        "link_search",
        "reverse_hierarchy",
        "external_file",
        "external_directory",
        "jpeg_image",
        "svg_image",
    ],
)
def test_profile3_does_not_enable_later_source_families_before_their_slice(family):
    from tests.support.local_api import HOME
    from tests.support.local_api_graph import HIERARCHY, GraphApi
    from tests.support.local_api_payloads import FILE, PayloadApi, attachment

    if family in {"link_search", "reverse_hierarchy"}:
        api = GraphApi()
        if family == "reverse_hierarchy":
            api.links[HIERARCHY]["direction"] = 3
        else:
            api.search = [
                {
                    "brainId": "00000000-0000-0000-0000-000000000000",
                    "isFromOtherBrain": False,
                    "sourceThought": None,
                    "sourceLink": {"id": HIERARCHY, "brainId": BRAIN},
                    "searchResultType": 1,
                    "entityType": 3,
                    "sourceType": 0,
                    "attachmentId": "00000000-0000-0000-0000-000000000000",
                }
            ]
    else:
        api = PayloadApi()
        kind, location = {
            "external_file": (2, "C:\\Source\\document.pdf"),
            "external_directory": (8, "D:\\Source\\Folder"),
            "jpeg_image": (12, FILE + ".jpg"),
            "svg_image": (12, FILE + ".svg"),
        }[family]
        api.attachments[FILE] = attachment(FILE, HOME, kind, location)
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome == "refused"
    assert result.receipt is None
    if family not in {"link_search", "reverse_hierarchy"}:
        assert not any(
            FILE in path and path.endswith("/file-content")
            for path, _, _ in api.requests
        )


@pytest.mark.parametrize("version", ["2", "3"])
def test_recomputed_untrusted_manifest_cannot_replace_pinned_capture(tmp_path, version):
    import hashlib
    from contextlib import closing

    from brz2obsidian.contracts import MigrationRefused, SourceSnapshot
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession
    from tests.sources.test_local_api import golden_inputs

    source, snapshot, audit, payloads = golden_inputs(version)
    with closing(
        LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads=payloads,
            capture_parent=tmp_path,
            profile_version=version,
        )
    ) as session:
        original_identity = session.source_identity
        capture = next(tmp_path.iterdir())
        manifest_path = capture / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        payload_file = next(
            row for row in manifest["files"] if row["role"] == "payload"
        )
        target = capture / payload_file["storage_key"]
        raw = target.read_bytes()
        changed = bytes([raw[0] ^ 1]) + raw[1:]
        target.write_bytes(changed)
        payload_file["actual_sha256"] = hashlib.sha256(changed).hexdigest()
        manifest.pop("integrity_sha256")
        preimage = json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        manifest["integrity_sha256"] = hashlib.sha256(
            b"brz2obsidian.local-api.integrity.v1\n" + preimage
        ).hexdigest()
        manifest_path.write_text(
            json.dumps(
                manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ),
            encoding="utf-8",
            newline="",
        )
        with pytest.raises(MigrationRefused):
            session.verify_consistency()
        assert session.source_identity == original_identity


@pytest.mark.parametrize(
    "mutation", ["owner", "role", "uri", "reference_target", "image_bytes"]
)
def test_profile3_fresh_capture_rejects_semantic_resource_corruption(
    tmp_path, monkeypatch, mutation
):
    import hashlib
    import tempfile

    from brz2obsidian.contracts import MigrationRefused, SourceSnapshot
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession
    from tests.support.local_api import ALONE
    from tests.support.local_api_payloads import FILE, IMAGE, WEBSITE

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with api_server(RichPayloadApi(jpeg=True)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            snapshot = json.loads(session.snapshot.model_dump_json())
            payloads = {}
            for asset in session.snapshot.assets:
                if asset.availability == "present":
                    with session.open_payload(asset.asset_id) as stream:
                        payloads[asset.asset_id] = stream.read()
    image = next(a for a in snapshot["assets"] if a["asset_id"] == IMAGE)
    if mutation == "owner":
        image["owner"] = ALONE
    elif mutation == "role":
        image["role"] = "file"
    elif mutation == "uri":
        next(a for a in snapshot["assets"] if a["asset_id"] == WEBSITE)[
            "external_uri"
        ] = "https://example.invalid/altered"
    elif mutation == "reference_target":
        document = next(d for d in snapshot["documents"] if d["references"])
        next(r for r in document["references"] if r["kind"] == "image")["target"] = FILE
    else:
        payloads[IMAGE] = b"X" * len(payloads[IMAGE])
        actual_hash = hashlib.sha256(payloads[IMAGE]).hexdigest()
        image["actual_sha256"] = actual_hash
        next(p for p in source["payloads"] if p["asset_id"] == IMAGE)[
            "actual_sha256"
        ] = actual_hash
    snapshot["identity"].update(source_sha256="", snapshot_digest="")
    with pytest.raises(MigrationRefused):
        fresh = LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads=payloads,
            profile_version="3",
        )
        fresh.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile_version", "4"),
        ("profile_id", "unknown-profile"),
        ("module_id", "unknown-module"),
        ("module_version", "2"),
        ("format_id", "unknown-format"),
        ("format_version", "2"),
        ("contract_version", 8),
    ],
)
def test_fresh_profile3_capture_refuses_unknown_identifier_bindings(field, value):
    from brz2obsidian.contracts import MigrationRefused, SourceSnapshot
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession
    from tests.sources.test_local_api import golden_inputs

    source, snapshot, audit, payloads = golden_inputs("3")
    source["identifiers"][field] = value
    snapshot["identity"].update(source_sha256="", snapshot_digest="")
    with pytest.raises(MigrationRefused):
        session = LocalApiSession(
            source=source,
            snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
            audit=audit,
            payloads=payloads,
            profile_version="3",
        )
        session.close()


@pytest.mark.parametrize("nested", ["thought", "link", "malformed_owner"])
@pytest.mark.parametrize("version", ["1", "2", "3"])
def test_search_nested_ownership_keeps_invalid_source_classification(nested, version):
    from tests.support.local_api import HOME, MetadataApi
    from tests.support.local_api_graph import HIERARCHY

    api = MetadataApi()
    hit = {
        "brainId": "00000000-0000-0000-0000-000000000000",
        "isFromOtherBrain": False,
        "sourceThought": {"id": HOME, "brainId": BRAIN},
        "sourceLink": None,
        "searchResultType": 1,
        "entityType": 2,
        "sourceType": 0,
        "attachmentId": "00000000-0000-0000-0000-000000000000",
        "name": "PRIVATE_HINT_CANARY",
    }
    if nested == "thought":
        hit["sourceThought"]["brainId"] = "99999999-9999-4999-8999-999999999999"
    elif nested == "link":
        hit.update(
            sourceThought=None,
            entityType=3,
            sourceLink={
                "id": HIERARCHY,
                "brainId": "99999999-9999-4999-8999-999999999999",
            },
        )
    else:
        hit["sourceThought"] = "PRIVATE_OWNER_CANARY"
    api.search = [hit]
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=version,
        )
        policy = {
            "1": LOCAL_API_POLICY,
            "2": LOCAL_API_POLICY_V2,
            "3": LOCAL_API_POLICY_V3,
        }[version]
        result = Workflow(
            SourceModuleBinding(module, policy),
            ObsidianRenderer(),
            FilesystemPublisher(),
        ).inspect(LocalApiSourceRef(BRAIN))
    assert result.outcome == "refused"
    assert result.issues[0].code == "invalid_source"
    assert "CANARY" not in result.model_dump_json()
