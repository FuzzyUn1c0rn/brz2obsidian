"""Explicit profile5 admission from independently qualified #352 source inputs."""

import gzip
import hashlib
import json
import os
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from threading import Event
from time import perf_counter

import pytest

from brz2obsidian.contracts import MigrationFailed, MigrationRefused, SourceSnapshot
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from brz2obsidian.sources.thebrain.local_api.resources import validate_bytes
from tests.local_acceptance.api_icon_inputs import (
    DECLARATION,
    bmp,
    bmp_mutations,
    ico,
    ico_mutations,
    positive_cases,
)
from tests.sources.test_local_api_images_v3 import ICON, IcoIconApi
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server


def test_explicit5_bmp_source_seals_original_icon_bytes_and_facts():
    fixture = bmp()
    with (
        api_server(IcoIconApi(fixture["raw"])) as (_, origin),
        LocalApiSourceModule(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY, profile_version="5"
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        asset = next(a for a in session.snapshot.assets if a.asset_id == ICON)
        assert (asset.owner, asset.role, asset.original_name) == (
            HOME,
            "icon",
            "Icon.png",
        )
        assert (asset.actual_length, asset.actual_sha256) == (
            fixture["length"],
            fixture["sha256"],
        )
        with session.open_payload(ICON) as stream:
            assert stream.read() == fixture["raw"]
        session.verify_consistency()


def vector_inputs():
    vector = json.loads(
        (
            Path(__file__).parents[1]
            / "fixtures/local_api_capture/profile5-capture-vector.json"
        ).read_bytes()
    )
    files = {
        row["storage_key"]: bytes.fromhex(row["hex"])
        if "hex" in row
        else row["utf8"].encode()
        for row in vector["retained_files"]
    }
    manifest = json.loads(files["manifest.json"])
    return (
        vector,
        files,
        {
            "source": json.loads(files["source.json"]),
            "snapshot": SourceSnapshot.model_validate_json(files["snapshot.json"]),
            "audit": json.loads(files["audit.json"]),
            "payloads": {
                b["asset_id"]: files[b["storage_key"]]
                for b in manifest["payload_bindings"]
            },
            "storage_keys": {
                b["asset_id"]: b["storage_key"] for b in manifest["payload_bindings"]
            },
            "profile_version": "5",
        },
    )


def test_frozen5_session_matches_all_independent_canonical_digests(tmp_path):
    vector, _files, arguments = vector_inputs()
    with closing(LocalApiSession(**arguments, capture_parent=tmp_path)) as session:
        assert session.source_identity.source_sha256 == vector["expected_source_sha256"]
        assert (
            session.source_identity.snapshot_digest
            == vector["expected_snapshot_digest"]
        )
        assert (
            session.acquisition.integrity_sha256 == vector["expected_integrity_sha256"]
        )
        session.verify_consistency()
        for key, raw in arguments["payloads"].items():
            with session.open_payload(key) as stream:
                assert stream.read() == raw


def test_independent_new_icon_family_and_structural_refusals():
    for name, fixture in positive_cases():
        assert validate_bytes(DECLARATION, fixture["raw"], "5") == "icon", name
    for name, raw in (*ico_mutations(), *bmp_mutations()):
        with pytest.raises(MigrationRefused):
            validate_bytes(DECLARATION, raw, "5")


def test_real_event_after_decoded_frame_prevents_source_yield(tmp_path, monkeypatch):
    import tempfile

    from PIL import Image

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    cancelled = Event()
    original = Image.Image.convert

    def converted(image, *args, **kwargs):
        result = original(image, *args, **kwargs)
        if image.size == (2, 2) and result.mode == "RGBA":
            cancelled.set()  # A genuine completed Pillow conversion, not a check counter.
        return result

    monkeypatch.setattr(Image.Image, "convert", converted)
    with api_server(IcoIconApi(ico((2, 3))["raw"])) as (_, origin):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=origin),
            credentials=lambda: KEY,
            profile_version="5",
            cancel=cancelled.is_set,
        )
        with (
            pytest.raises(MigrationFailed) as error,
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("Cancelled source cannot yield an accepted capture")
    assert cancelled.is_set()
    assert error.value.issues[0].code == "api_acquisition_cancelled"
    assert not list(tmp_path.glob("brz2obsidian-api-*"))


@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("prefix,limit", [(b"BM", 4_194_358), (b"\0\0\1\0", 8_388_608)])
def test_live_family_ceiling_stops_plain_and_gzip_before_seal(
    prefix, limit, compressed
):
    raw = prefix + bytes(limit + 1 - len(prefix))
    api = IcoIconApi(raw)
    if compressed:
        api.overrides[f"/api/attachments/{BRAIN}/{ICON}/file-content"] = (
            200,
            gzip.compress(raw),
            {"Content-Encoding": "gzip"},
        )
    with api_server(api) as (_, origin):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY, profile_version="5"
        )
        with (
            pytest.raises(MigrationRefused) as error,
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("Oversized icon cannot yield a sealed session")
    assert error.value.issues[0].code == "incomplete_source"
    assert "icon" in error.value.issues[0].message


def test_historical_union_and_role_boundaries_remain_explicit():
    from tests.local_acceptance.api_icon_inputs import legacy_zero_alpha_control

    for version in ("1", "2", "3", "4"):
        for fixture in (bmp(), ico()):
            with pytest.raises(MigrationRefused):
                validate_bytes(DECLARATION, fixture["raw"], version)
    old = Path(__file__).parents[1] / "fixtures/local_api_images_v3"
    for name in ("inert-a.ico", "inert-b.ico"):
        assert validate_bytes(DECLARATION, old / name, "5") == "icon"
    assert (
        validate_bytes(DECLARATION, legacy_zero_alpha_control()["raw"], "5") == "icon"
    )
    for changed in (
        {"type": 12},
        {"location": "Other.png"},
        {"name": "Icon"},
        {"isNotes": True},
    ):
        with pytest.raises(MigrationRefused):
            validate_bytes({"id": ICON} | DECLARATION | changed, bmp()["raw"], "5")
    assert (
        validate_bytes(
            DECLARATION | {"type": 1, "location": "ordinary.bin"}, bmp()["raw"], "5"
        )
        == "file"
    )


@pytest.mark.parametrize(
    "damage",
    [
        {"brainId": "00000000-0000-4000-8000-000000000001"},
        {"sourceId": "00000000-0000-4000-8000-000000000002"},
        {"sourceType": 1},
        {"type": 12},
        {"name": "Icon"},
        {"location": "Other.png"},
        {"isNotes": True},
    ],
)
def test_icon_source_declaration_guards_precede_payload_admission(damage):
    api = IcoIconApi(bmp()["raw"])
    api.overrides[f"/api/attachments/{BRAIN}/{ICON}/metadata"] = (
        200,
        api.attachments[ICON] | damage,
    )
    with api_server(api) as (_, origin):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY, profile_version="5"
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail("Invalid source declaration cannot grant icon admission")


@pytest.mark.parametrize(
    "cancel",
    [
        False,
        lambda: 0,
        lambda: "CONTROL_CANARY",
        lambda: (_ for _ in ()).throw(ValueError("CONTROL_CANARY")),
    ],
)
def test_bad_controls_fail_safely_before_source_or_session_seal(cancel):
    for constructor, arguments in (
        (LocalApiSourceModule, {"profile_version": "5"}),
        (LocalApiSession, vector_inputs()[2]),
    ):
        with pytest.raises(MigrationFailed) as error:
            constructor(**arguments, cancel=cancel)
        assert error.value.issues[0].code == "api_acquisition_cancelled"
        assert "control" in error.value.issues[0].message
        assert "CONTROL_CANARY" not in str(error.value)


def test_profile5_inherits_graph_literal_links_opaque_files_and_both_gap_kinds(
    tmp_path, monkeypatch
):
    import tempfile

    from tests.support.local_api_payloads import (
        FILE,
        IMAGE,
        NOTE,
        PDF,
        PDF_BYTES,
        TXT,
        attachment,
    )
    from tests.support.type_tag_sources import DIRECT, IDS, NAVIGATION, TypeTagApi

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    api = TypeTagApi()
    link = "brain://api.thebrain.com/EREREREREUGBEREREREREQ/AAAAAAAAAAAAAAAAAAAACw"
    body = f"<X/>\n[Type]({link})\n![Lost](.data/md-images/{IMAGE}.png)\n".encode()
    api.attachments.update(
        {
            NOTE: attachment(
                NOTE, HOME, 1, "Notes.md", is_notes=True, length=len(body)
            ),
            FILE: attachment(FILE, HOME, 1, "raw.future", length=3),
            IMAGE: attachment(IMAGE, HOME, 12, IMAGE + ".png", length=123),
            TXT: attachment(TXT, HOME, 15, "lost.txt", length=123),
            PDF: attachment(PDF, HOME, 1, "other.pdf", length=len(PDF_BYTES)),
            ICON: attachment(ICON, HOME, 5, "Icon.png", length=bmp()["length"]),
        }
    )
    api.payloads.update(
        {NOTE: body, FILE: b"\0\xff\x80", PDF: PDF_BYTES, ICON: bmp()["raw"]}
    )
    for key in (TXT, IMAGE):
        api.overrides[f"/api/attachments/{BRAIN}/{key}/file-content"] = (
            404,
            b"not retained",
        )
    with (
        api_server(api) as (_, origin),
        LocalApiSourceModule(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY, profile_version="5"
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        snapshot = session.snapshot
        names = {item.key: item.title for item in snapshot.items}
        assert {
            (names[a.definition_key], names[a.item_key])
            for a in snapshot.classification_assignments
        } == DIRECT
        assert {
            (r.kind, names[r.item_a], names[r.item_b])
            for r in snapshot.relationships
            if r.kind in {"hierarchy", "related"}
        } == NAVIGATION
        document = next(d for d in snapshot.documents if d.owner == HOME)
        assert (
            document.text.startswith("\\<X/>\n")
            and "Image unavailable: Lost" in document.text
        )
        assert any(
            r.kind == "item" and r.target == IDS["B"] for r in document.references
        )
        assert {f.rule_id for f in snapshot.findings} >= {
            "local-api.missing-txt-pdf.v1",
            "thebrain.unavailable-declared-image.v1",
        }
        with session.open_payload(FILE) as stream:
            assert stream.read() == b"\0\xff\x80"
        capture = next(tmp_path.glob("brz2obsidian-api-*"))
        source = json.loads((capture / "source.json").read_bytes())
        audit = session.acquisition.audit.model_dump(mode="json")
        payloads = {}
        for asset in snapshot.assets:
            if asset.availability == "present":
                with session.open_payload(asset.asset_id) as stream:
                    payloads[asset.asset_id] = stream.read()
    with closing(
        LocalApiSession(
            source=source,
            snapshot=snapshot,
            audit=audit,
            payloads=payloads,
            profile_version="5",
            capture_parent=tmp_path,
        )
    ) as replay:
        assert replay.snapshot == snapshot
        replay.verify_consistency()


def test_explicit5_workflow_preserves_whole_container_and_refuses_bad_icon_without_output(
    tmp_path,
):
    from brz2obsidian.application.contracts import (
        DestinationValidation,
        LocalApiSourceSelection,
        ReviewedInspection,
    )
    from brz2obsidian.application.conversion import convert
    from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
    from brz2obsidian.obsidian import ObsidianRenderer
    from brz2obsidian.publication import FilesystemPublisher
    from brz2obsidian.sources.thebrain.local_api import LOCAL_API_POLICY_V5
    from tests.support.local_api_payloads import DIRECT_ICON, RichPayloadApi

    fixture = ico((2, 3), physical=(1, 0))
    api = RichPayloadApi(explicit=True, jpeg=True)
    api.payloads[DIRECT_ICON] = fixture["raw"]
    api.attachments[DIRECT_ICON]["dataLength"] = fixture["length"]
    with api_server(api) as (_, origin):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY, profile_version="5"
        )
        workflow = Workflow(
            SourceModuleBinding(module, LOCAL_API_POLICY_V5),
            ObsidianRenderer(),
            FilesystemPublisher(),
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean"
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean" and result.receipt.verified
        record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
        assert record["profile_version"] == "5"
        row = next(r for r in record["asset_targets"] if r["asset_id"] == DIRECT_ICON)
        assert (
            row["owner"],
            row["role"],
            row["original_name"],
            row["actual_sha256"],
            row["actual_length"],
        ) == (HOME, "icon", "Icon.png", fixture["sha256"], fixture["length"])
        assert (tmp_path / "vault" / row["relative_path"]).read_bytes() == fixture[
            "raw"
        ]
        selection = LocalApiSourceSelection(brain_id=BRAIN, config={"api_url": origin})
        reviewed = ReviewedInspection(
            source_selection=selection,
            source_identity=inspected.source_identity,
            converter_version=inspected.converter_version,
            profile_id=inspected.profile_id,
            profile_version=inspected.profile_version,
            outcome="clean",
        )
        changed = ico((2, 3), physical=(1, 0), opaque=True)
        api.payloads[DIRECT_ICON] = changed["raw"]
        api.attachments[DIRECT_ICON]["dataLength"] = changed["length"]
        stale = convert(
            workflow,
            LocalApiSourceRef(BRAIN),
            DestinationValidation(
                outcome="valid",
                status="destination_valid",
                destination=str(tmp_path / "stale"),
            ),
            reviewed,
            False,
            source_selection=selection,
        )
        assert stale.outcome == "refused" and stale.publication.state == "not_published"
        assert stale.review_required and {f.code for f in stale.findings} == {
            "review_changed"
        }
        assert not (tmp_path / "stale").exists()
        api.payloads[DIRECT_ICON] = fixture["raw"][:-1]
        refused = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "bad")
        assert refused.outcome == "refused" and refused.receipt is None
        assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("growth", [False, True])
def test_path_oversize_checks_bound_all_reads_before_decoding(
    tmp_path, monkeypatch, growth
):
    from io import BytesIO
    from types import SimpleNamespace

    target = tmp_path / "icon.bin"
    target.write_bytes(bmp()["raw"])
    original_open, original_stat = Path.open, Path.stat
    requests = []
    raw = b"BM" + bytes(4_194_357) if growth else bmp()["raw"]

    class Guard(BytesIO):
        def read(self, size=-1):
            assert size > 0, "Icon validation must never issue an unbounded file read"
            requests.append(size)
            return super().read(size)

    def opened(path, *args, **kwargs):
        return Guard(raw) if path == target else original_open(path, *args, **kwargs)

    def stated(path, *args, **kwargs):
        return (
            SimpleNamespace(st_size=78 if growth else 4_194_359)
            if path == target
            else original_stat(path, *args, **kwargs)
        )

    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(Path, "stat", stated)
    with pytest.raises(MigrationRefused):
        validate_bytes(DECLARATION, target, "5")
    assert sum(requests) <= 4_194_359
    if not growth:
        assert all(size <= 24 for size in requests)


@pytest.mark.parametrize("manifest_forgery", [False, True])
def test_pinned5_capture_checks_unrequested_same_stat_icon_and_untrusted_manifest(
    tmp_path, monkeypatch, manifest_forgery
):
    import tempfile

    from tests.local_acceptance.api_icon_inputs import capture_digest, capture_json
    from tests.support.local_api_payloads import NOTE

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with (
        api_server(IcoIconApi(bmp()["raw"])) as (_, origin),
        LocalApiSourceModule(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY, profile_version="5"
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        capture = next(tmp_path.glob("brz2obsidian-api-*"))
        manifest = json.loads((capture / "manifest.json").read_bytes())
        binding = next(b for b in manifest["payload_bindings"] if b["asset_id"] == ICON)
        path = capture / binding["storage_key"]
        stat = path.stat()
        changed = bytearray(path.read_bytes())
        changed[54] ^= 1  # A valid changed blue byte, not an intrinsic syntax error.
        path.write_bytes(changed)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        if manifest_forgery:
            row = next(
                r
                for r in manifest["files"]
                if r["storage_key"] == binding["storage_key"]
            )
            row["actual_sha256"] = hashlib.sha256(changed).hexdigest()
            manifest["integrity_sha256"] = capture_digest(
                "integrity",
                {k: v for k, v in manifest.items() if k != "integrity_sha256"},
            )
            (capture / "manifest.json").write_bytes(capture_json(manifest))
        with pytest.raises(MigrationRefused), session.open_payload(NOTE):
            pytest.fail(
                "Reading a different asset cannot evade complete capture checks"
            )


def test_frozen5_direct_session_rejects_profile_owner_and_role_mismatches(tmp_path):
    for damage in ("profile", "owner", "role"):
        _vector, _files, arguments = vector_inputs()
        if damage == "profile":
            arguments["profile_version"] = "4"
        else:
            snapshot = arguments["snapshot"].model_dump(mode="json")
            icon = next(a for a in snapshot["assets"] if a["role"] == "icon")
            icon["owner" if damage == "owner" else "role"] = (
                "different:owner" if damage == "owner" else "file"
            )
            snapshot["identity"].update(source_sha256="", snapshot_digest="")
            arguments["snapshot"] = SourceSnapshot.model_validate_json(
                json.dumps(snapshot)
            )
        with pytest.raises(MigrationRefused):
            LocalApiSession(**arguments, capture_parent=tmp_path)


def test_frozen5_fresh_valid_artwork_changes_identity_without_granting_old_authority(
    tmp_path,
):
    vector, _files, arguments = vector_inputs()
    source = deepcopy(arguments["source"])
    snapshot = arguments["snapshot"].model_dump(mode="json")
    asset = next(a for a in snapshot["assets"] if a["role"] == "icon")
    fixture = ico(opaque=True)
    asset["actual_length"], asset["actual_sha256"] = (
        fixture["length"],
        fixture["sha256"],
    )
    fact = next(p for p in source["payloads"] if p["asset_id"] == asset["asset_id"])
    fact["actual_length"], fact["actual_sha256"] = fixture["length"], fixture["sha256"]
    arguments["payloads"][asset["asset_id"]] = fixture["raw"]
    snapshot["identity"].update(source_sha256="", snapshot_digest="")
    arguments.update(
        source=source, snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot))
    )
    with closing(LocalApiSession(**arguments, capture_parent=tmp_path)) as fresh:
        assert fresh.source_identity.source_sha256 != vector["expected_source_sha256"]
        assert (
            fresh.source_identity.snapshot_digest != vector["expected_snapshot_digest"]
        )
        assert fresh.acquisition.integrity_sha256 != vector["expected_integrity_sha256"]
        with fresh.open_payload(asset["asset_id"]) as stream:
            assert stream.read() == fixture["raw"]


def test_frozen5_session_copy_observes_real_event_and_configured_limit(tmp_path):
    from io import BytesIO

    cancelled = Event()
    _vector, _files, arguments = vector_inputs()
    icon = next(a for a in arguments["snapshot"].assets if a.role == "icon")

    class CancelRead(BytesIO):
        def read(self, size=-1):
            result = super().read(size)
            cancelled.set()
            return result

    # Actual externally supplied Path IO is the direct-session copy boundary.
    path = tmp_path / "incoming.bin"
    raw = arguments["payloads"][icon.asset_id]
    path.write_bytes(raw)
    original = Path.open
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            Path,
            "open",
            lambda p, *a, **kw: CancelRead(raw) if p == path else original(p, *a, **kw),
        )
        arguments["payloads"][icon.asset_id] = path
        with pytest.raises(MigrationFailed) as error:
            LocalApiSession(
                **arguments, capture_parent=tmp_path, cancel=cancelled.is_set
            )
        assert error.value.issues[0].code == "api_acquisition_cancelled"
    _vector, _files, arguments = vector_inputs()
    arguments["audit"]["limits"]["max_payload_bytes"] = 64
    with pytest.raises(MigrationRefused) as error:
        LocalApiSession(**arguments, capture_parent=tmp_path)
    assert error.value.issues[0].code == "incomplete_source"


@pytest.mark.parametrize("kind", ["ico", "bmp"])
def test_genuine_maximum_through_source_and_seal_records_bounded_work(
    tmp_path, monkeypatch, kind
):
    from brz2obsidian.sources.thebrain.local_api import resources
    from tests.local_acceptance.api_image_proofs import icon_process_memory

    # Material ledger, deliberately no compression/dedup credit: one <=4.2MiB
    # source plus <=8.4MiB recipe/body working copies, <=8.4MiB sequential capture
    # copies and <=16.8MiB decoded/comparison work. <40MiB new simultaneous inert
    # material; old #35232MiB plus this child64MiB remain separate ceilings.
    baseline = icon_process_memory()
    started = perf_counter()
    fixture = (
        ico(
            tuple(range(241, 257)),
            physical=tuple(range(15, -1, -1)),
            retain_pixels=False,
        )
        if kind == "ico"
        else bmp(1024, 1024, retain_pixels=False)
    )
    generation_seconds = perf_counter() - started
    assert fixture["length"] == (4_081_638 if kind == "ico" else 4_194_358)
    assert sum(f["width"] * f["height"] for f in fixture["frames"]) == (
        988_376 if kind == "ico" else 1_048_576
    )
    observations = []
    original = resources.validate_bytes

    def measured(value, raw, profile, **kwargs):
        if value["type"] != 5:
            return original(value, raw, profile, **kwargs)
        before = icon_process_memory()
        started = perf_counter()
        result = original(value, raw, profile, **kwargs)
        elapsed = perf_counter() - started
        observations.append(
            {
                "validation_seconds": elapsed,
                "before": before,
                "after": icon_process_memory(),
                "path_input": isinstance(raw, Path),
            }
        )
        assert elapsed <= 30
        return result

    monkeypatch.setattr(resources, "validate_bytes", measured)
    started = perf_counter()
    with (
        api_server(IcoIconApi(fixture["raw"])) as (_, origin),
        LocalApiSourceModule(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY, profile_version="5"
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        asset = next(a for a in session.snapshot.assets if a.asset_id == ICON)
        assert (asset.actual_length, asset.actual_sha256) == (
            fixture["length"],
            fixture["sha256"],
        )
        measured_hash = hashlib.sha256()
        with session.open_payload(ICON) as stream:
            while chunk := stream.read(65536):
                measured_hash.update(chunk)
        assert measured_hash.hexdigest() == fixture["sha256"]
    operation_seconds = perf_counter() - started
    assert operation_seconds <= 30 and observations
    evidence = {
        "kind": kind,
        "encoded_bytes": fixture["length"],
        "source_sha256": fixture["sha256"],
        "generation_seconds": generation_seconds,
        "source_and_seal_seconds": operation_seconds,
        "baseline": baseline,
        "after": icon_process_memory(),
        "validations": observations,
        "memory_meaning": "Actual process current and lifetime peaks, not a peak delta or production memory guarantee",
    }
    (tmp_path / (kind + "-production-maximum.json")).write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )


def test_frozen5_oversized_caller_icon_is_rejected_before_buffer_conversion(tmp_path):
    class Oversized(bytearray):
        def __bytes__(self):
            raise AssertionError(
                "Oversized icon must be rejected before allocating a converted buffer"
            )

    _vector, _files, arguments = vector_inputs()
    icon = next(a for a in arguments["snapshot"].assets if a.role == "icon")
    arguments["payloads"][icon.asset_id] = Oversized(b"\0\0\1\0" + bytes(8_388_605))
    with pytest.raises(MigrationRefused) as error:
        LocalApiSession(**arguments, capture_parent=tmp_path)
    assert error.value.issues[0].code == "incomplete_source"


def test_decoder_failure_on_historical_overlap_does_not_retry_another_alternative(
    monkeypatch,
):
    from PIL import Image

    original = Image.open
    failed = False

    def opened(*args, **kwargs):
        nonlocal failed
        if kwargs.get("formats") == ("ICO",):
            assert not failed, (
                "A failed selected ICO decode must not retry another alternative"
            )
        image = original(*args, **kwargs)
        if kwargs.get("formats") == ("ICO",) and image.size == (16, 16):
            failed = True
            image.close()
            raise OSError("DECODER_DETAIL_CANARY")
        return image

    monkeypatch.setattr(Image, "open", opened)
    with pytest.raises(MigrationRefused) as error:
        validate_bytes(DECLARATION, ico((32, 16), opaque=True, masks=False)["raw"], "5")
    assert failed and "DECODER_DETAIL_CANARY" not in str(error.value)


@pytest.mark.parametrize("case", ["distinct", "ambiguous", "excluded"])
def test_equal_icon_bytes_keep_owner_identity_and_exclusions_precede_acquisition(case):
    from tests.support.local_api_payloads import attachment

    other = "b5555555-5555-4555-8555-555555555555"
    fixture = bmp()
    api = IcoIconApi(fixture["raw"])
    owner = HOME if case == "ambiguous" else ALONE
    api.attachments[other] = attachment(
        other, owner, 5, "Icon.png", length=fixture["length"]
    )
    api.payloads[other] = (
        b"UNQUALIFIED_EXCLUDED_CANARY" if case == "excluded" else fixture["raw"]
    )
    if case == "excluded":
        api.thoughts[ALONE]["forgottenDateTime"] = "2026-01-01T00:00:00Z"
    with api_server(api) as (_, origin):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY, profile_version="5"
        )
        if case == "ambiguous":
            with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
                pytest.fail("Two own icon declarations require refusal")
        else:
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                icons = [a for a in session.snapshot.assets if a.role == "icon"]
                assert {(a.asset_id, a.owner) for a in icons} == (
                    {(ICON, HOME)}
                    if case == "excluded"
                    else {(ICON, HOME), (other, ALONE)}
                )
                assert {a.actual_sha256 for a in icons} == {fixture["sha256"]}
                for asset in icons:
                    item = next(
                        i for i in session.snapshot.items if i.key == asset.owner
                    )
                    assert asset.asset_id in item.resource_ids
                    assert item.declared_appearance.icon_asset_id == asset.asset_id
    if case == "excluded":
        assert not any(
            path == f"/api/attachments/{BRAIN}/{other}/file-content"
            for path, _, _ in api.requests
        )


def test_frozen5_session_rejects_known_oversized_open_file_before_body_copy(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    _vector, _files, arguments = vector_inputs()
    icon = next(a for a in arguments["snapshot"].assets if a.role == "icon")
    path = tmp_path / "external-icon.bin"
    path.write_bytes(arguments["payloads"][icon.asset_id])
    arguments["payloads"][icon.asset_id] = path
    original_open, original_fstat = Path.open, os.fstat
    opened_descriptors = set()

    class Guard:
        def __init__(self, stream):
            self.stream = stream
            opened_descriptors.add(stream.fileno())

        def __enter__(self):
            return self

        def __exit__(self, *args):
            opened_descriptors.remove(self.stream.fileno())
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            assert 0 < size <= 4, "Known oversize must refuse before copying body bytes"
            return self.stream.read(size)

    monkeypatch.setattr(
        Path,
        "open",
        lambda p, *a, **kw: (
            Guard(original_open(p, *a, **kw))
            if p == path
            else original_open(p, *a, **kw)
        ),
    )
    monkeypatch.setattr(
        os,
        "fstat",
        lambda fd: (
            SimpleNamespace(st_size=8_388_609)
            if fd in opened_descriptors
            else original_fstat(fd)
        ),
    )
    with pytest.raises(MigrationRefused) as error:
        LocalApiSession(**arguments, capture_parent=tmp_path)
    assert error.value.issues[0].code == "incomplete_source"


def test_frozen5_verified_caller_buffer_does_not_invoke_custom_whole_bytes_conversion(
    tmp_path,
):
    class Buffer(bytearray):
        def __bytes__(self):
            raise AssertionError(
                "Use the bounded verified buffer, not custom whole-value conversion"
            )

    vector, _files, arguments = vector_inputs()
    icon = next(a for a in arguments["snapshot"].assets if a.role == "icon")
    arguments["payloads"][icon.asset_id] = Buffer(arguments["payloads"][icon.asset_id])
    with closing(LocalApiSession(**arguments, capture_parent=tmp_path)) as session:
        assert session.source_identity.source_sha256 == vector["expected_source_sha256"]
        assert (
            session.source_identity.snapshot_digest
            == vector["expected_snapshot_digest"]
        )
        assert (
            session.acquisition.integrity_sha256 == vector["expected_integrity_sha256"]
        )
