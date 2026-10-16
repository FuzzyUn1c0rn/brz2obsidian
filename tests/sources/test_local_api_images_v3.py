"""Profile3 JPEG/finite ICO preservation through public HTTP source workflows."""

import hashlib
import json
from pathlib import Path

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_graph import GraphApi
from tests.support.local_api_payloads import IMAGE, JPEG, NOTE, PayloadApi, attachment

JPEG_SHA256 = "88d4b59a63385475e658d1992901eea75c2bf887ebc7c3a7398965dd332850e8"
JPEG_NOTE = (
    "# Photo\n\n![Photo](.data/md-images/" + IMAGE + '.jpg "Portrait")\n'
).encode("utf-8")


class JpegImageApi(PayloadApi):
    def __init__(self):
        super().__init__()
        self.payloads[NOTE] = JPEG_NOTE
        self.attachments[NOTE]["dataLength"] = len(JPEG_NOTE)
        self.attachments[IMAGE] = attachment(
            IMAGE, HOME, 12, IMAGE + ".jpg", length=634
        )
        self.payloads[IMAGE] = JPEG


def test_jpeg_note_image_preserves_bytes_role_reference_and_output(tmp_path):
    assert len(JPEG) == 634 and hashlib.sha256(JPEG).hexdigest() == JPEG_SHA256
    api = JpegImageApi()
    with api_server(api) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    asset = next(row for row in record["asset_targets"] if row["asset_id"] == IMAGE)
    assert (asset["owner"], asset["role"], asset["original_name"]) == (
        HOME,
        "image",
        IMAGE + ".jpg",
    )
    assert (asset["actual_length"], asset["actual_sha256"]) == (634, JPEG_SHA256)
    assert (tmp_path / "vault" / asset["relative_path"]).read_bytes() == JPEG
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == JPEG_NOTE
    note = next((tmp_path / "vault").glob("Home*.md")).read_text(encoding="utf-8")
    assert "![Photo](Attachments/22222222/" + IMAGE + '.jpg "Portrait")' in note


@pytest.mark.parametrize(
    "mutation",
    [
        "type_file",
        "type_float",
        "type_bool",
        "source_float",
        "source_bool",
        "notes_zero",
        "notes_true",
        "notes_null",
        "name_absent",
        "name_empty",
        "name_authored",
        "uppercase",
        "jpeg_suffix",
        "wrong_uuid",
        "noncanonical_uuid",
        "traversal",
        "foreign_brain",
        "foreign_owner",
        "graph_mismatch",
        "metadata_mismatch",
        "private_owner",
        "custom_owner",
        "missing",
        "interrupted",
        "prefix_only",
        "truncated",
        "png_bytes",
        "unreferenced_corrupt",
    ],
)
def test_jpeg_image_requires_exact_declaration_joins_and_complete_owned_bytes(
    tmp_path, mutation
):
    from tests.support.local_api_payloads import PNG

    api = JpegImageApi()
    value = api.attachments[IMAGE]
    if mutation.startswith("type_"):
        value["type"] = {"type_file": 1, "type_float": 12.0, "type_bool": True}[
            mutation
        ]
    elif mutation.startswith("source_"):
        value["sourceType"] = 2.0 if mutation == "source_float" else True
    elif mutation.startswith("notes_"):
        value["isNotes"] = {"notes_zero": 0, "notes_true": True, "notes_null": None}[
            mutation
        ]
    elif mutation.startswith("name_"):
        if mutation == "name_absent":
            del value["name"]
        else:
            value["name"] = "" if mutation == "name_empty" else "AUTHOR_CANARY"
    elif mutation in {
        "uppercase",
        "jpeg_suffix",
        "wrong_uuid",
        "noncanonical_uuid",
        "traversal",
    }:
        value["location"] = {
            "uppercase": IMAGE + ".JPG",
            "jpeg_suffix": IMAGE + ".jpeg",
            "wrong_uuid": NOTE + ".jpg",
            "noncanonical_uuid": IMAGE.replace("-", "") + ".jpg",
            "traversal": "../" + IMAGE + ".jpg",
        }[mutation]
    elif mutation == "foreign_brain":
        value["brainId"] = NOTE
    elif mutation == "foreign_owner":
        value["sourceId"] = BRAIN
        api.overrides[f"/api/thoughts/{BRAIN}/{HOME}/attachments"] = (
            200,
            [api.attachments[NOTE], value],
        )
    elif mutation == "graph_mismatch":
        graph = api.response(f"/api/thoughts/{BRAIN}/{HOME}/graph", {})[1]
        graph["attachments"] = [api.attachments[NOTE]]
        api.overrides[f"/api/thoughts/{BRAIN}/{HOME}/graph"] = (200, graph)
    elif mutation == "metadata_mismatch":
        api.overrides[f"/api/attachments/{BRAIN}/{IMAGE}/metadata"] = (
            200,
            value | {"dataLength": 1},
        )
    elif mutation in {"private_owner", "custom_owner"}:
        api.thoughts[ALONE]["acType" if mutation == "private_owner" else "kind"] = (
            1 if mutation == "private_owner" else 3
        )
    elif mutation in {"missing", "interrupted"}:
        api.overrides[f"/api/attachments/{BRAIN}/{IMAGE}/file-content"] = (
            (404, b"PRIVATE_CANARY")
            if mutation == "missing"
            else (200, JPEG[:20], {"Content-Length": "634"})
        )
    else:
        if mutation == "unreferenced_corrupt":
            extra = "a3333333-3333-4333-8333-333333333334"
            api.attachments[extra] = attachment(extra, ALONE, 12, extra + ".jpg")
            api.payloads[extra] = JPEG[:20]
        else:
            api.payloads[IMAGE] = {
                "prefix_only": b"\xff\xd8\xff",
                "truncated": JPEG[:-12],
                "png_bytes": PNG,
            }[mutation]
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome in {"refused", "failed"}
    assert result.receipt is None
    assert not (tmp_path / "vault").exists()
    assert "CANARY" not in result.model_dump_json()


@pytest.mark.parametrize("version", ["1", "2"])
def test_explicit_older_profiles_refuse_jpeg_note_image_without_content_fetch(version):
    with api_server(JpegImageApi()) as (api, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=version,
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail("The older profile cannot grant the JPEG image role")
    assert not any(
        path == f"/api/attachments/{BRAIN}/{IMAGE}/file-content"
        for path, _, _ in api.requests
    )


@pytest.mark.parametrize("kind,forgotten", [(1, "2026-01-01T00:00:00"), (5, None)])
def test_known_excluded_image_owner_keeps_minimal_scope_without_payload_fetch(
    kind, forgotten
):
    api = JpegImageApi()
    api.payloads[NOTE] = b"Home body"
    api.attachments[NOTE]["dataLength"] = 9
    api.attachments[IMAGE]["sourceId"] = ALONE
    api.thoughts[ALONE].update(
        kind=kind,
        forgottenDateTime=forgotten,
        name="EXCLUDED_CANARY",
        label="EXCLUDED_CANARY",
    )
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        assert {item.key for item in session.snapshot.items} == {HOME}
        assert IMAGE not in {asset.asset_id for asset in session.snapshot.assets}
        assert "CANARY" not in session.snapshot.model_dump_json()
        session.verify_consistency()
    assert not any(
        path == f"/api/attachments/{BRAIN}/{IMAGE}/file-content"
        or path == f"/api/thoughts/{BRAIN}/{ALONE}/attachments"
        for path, _, _ in api.requests
    )


def test_jpeg_image_requires_decoder_jpeg_classification(tmp_path, monkeypatch):
    from PIL import Image

    actual_open = Image.open

    def misclassified(*args, **kwargs):
        image = actual_open(*args, **kwargs)
        if kwargs.get("formats") == ("JPEG",):
            image.format = "PNG"
        return image

    monkeypatch.setattr(Image, "open", misclassified)
    with api_server(JpegImageApi()) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.receipt is None
    assert not (tmp_path / "vault").exists()


def captured_inputs(api, tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        directory = next(tmp_path.glob("brz2obsidian-api-*"))
        source = json.loads((directory / "source.json").read_bytes())
        audit = json.loads((directory / "audit.json").read_bytes())
        snapshot = json.loads(session.snapshot.model_dump_json())
        payloads = {}
        for asset in session.snapshot.assets:
            if asset.availability == "present":
                with session.open_payload(asset.asset_id) as stream:
                    payloads[asset.asset_id] = stream.read()
    return source, audit, snapshot, payloads


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "role",
        "name",
        "reference",
        "bytes",
        "actual_length",
        "icon_assignment",
        "profile1",
        "profile2",
    ],
)
def test_fresh_jpeg_capture_revalidates_semantics_with_recomputed_hashes(
    tmp_path, monkeypatch, mutation
):
    from brz2obsidian.contracts import SourceSnapshot
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession
    from tests.support.local_api_payloads import PNG

    source, audit, snapshot, payloads = captured_inputs(
        JpegImageApi(), tmp_path, monkeypatch
    )
    clean = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        profile_version="3",
    )
    clean.verify_consistency()
    clean.close()
    asset = next(a for a in snapshot["assets"] if a["asset_id"] == IMAGE)
    version = "3"
    if mutation == "owner":
        asset["owner"] = ALONE
    elif mutation == "role":
        asset["role"] = "file"
    elif mutation == "name":
        asset["original_name"] = "Other.jpg"
    elif mutation == "reference":
        snapshot["documents"][0]["references"][0]["target"] = NOTE
    elif mutation == "bytes":
        payloads[IMAGE] = PNG
        asset["actual_length"] = len(PNG)
        asset["actual_sha256"] = hashlib.sha256(PNG).hexdigest()
        fact = next(f for f in source["payloads"] if f["asset_id"] == IMAGE)
        fact.update(actual_length=len(PNG), actual_sha256=asset["actual_sha256"])
    elif mutation == "actual_length":
        asset["actual_length"] = 635
        next(f for f in source["payloads"] if f["asset_id"] == IMAGE)[
            "actual_length"
        ] = 635
    elif mutation == "icon_assignment":
        next(item for item in snapshot["items"] if item["key"] == HOME)[
            "declared_appearance"
        ] = {"foreground_color": None, "background_color": None, "icon_asset_id": IMAGE}
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


def test_unrequested_jpeg_payload_mutation_cannot_replace_trusted_capture(
    tmp_path, monkeypatch
):
    import os
    import tempfile

    extra = "a3333333-3333-4333-8333-333333333334"
    api = JpegImageApi()
    api.attachments[extra] = attachment(extra, ALONE, 12, extra + ".jpg")
    api.payloads[extra] = JPEG
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        directory = next(tmp_path.glob("brz2obsidian-api-*"))
        manifest = json.loads((directory / "manifest.json").read_bytes())
        binding = next(
            row for row in manifest["payload_bindings"] if row["asset_id"] == extra
        )
        target = directory / binding["storage_key"]
        before = target.stat()
        raw = target.read_bytes()
        changed = raw[:20] + bytes([raw[20] ^ 1]) + raw[21:]
        target.write_bytes(changed)
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        file = next(
            row
            for row in manifest["files"]
            if row["storage_key"] == binding["storage_key"]
        )
        file["actual_sha256"] = hashlib.sha256(changed).hexdigest()
        manifest.pop("integrity_sha256")
        canonical = json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        manifest["integrity_sha256"] = hashlib.sha256(
            b"brz2obsidian.local-api.integrity.v1\n" + canonical
        ).hexdigest()
        (directory / "manifest.json").write_text(
            json.dumps(
                manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ),
            encoding="utf-8",
        )
        with pytest.raises(MigrationRefused):
            session.verify_consistency()


INPUTS = Path(__file__).parents[1] / "fixtures/local_api_images_v3"
ICO_FACTS = json.loads((INPUTS / "source-facts.json").read_bytes())
ICON = "a5555555-5555-4555-8555-555555555555"


class IcoIconApi(PayloadApi, GraphApi):
    def __init__(self, raw, *, owner=HOME):
        super().__init__()
        self.attachments[ICON] = attachment(ICON, owner, 5, "Icon.png", length=len(raw))
        self.payloads[ICON] = raw


@pytest.mark.parametrize("filename", ["inert-a.ico", "inert-b.ico"])
def test_exact_finite_ico_preserves_whole_container_icon_name_and_owner(
    tmp_path, filename
):
    fact = next(row for row in ICO_FACTS["payloads"] if row["file"] == filename)
    raw = (INPUTS / filename).read_bytes()
    assert len(raw) == fact["length"]
    assert hashlib.sha256(raw).hexdigest() == fact["sha256"]
    with api_server(IcoIconApi(raw)) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    asset = next(row for row in record["asset_targets"] if row["asset_id"] == ICON)
    assert (asset["owner"], asset["role"], asset["original_name"]) == (
        HOME,
        "icon",
        "Icon.png",
    )
    assert (asset["actual_length"], asset["actual_sha256"]) == (
        fact["length"],
        fact["sha256"],
    )
    assert (tmp_path / "vault" / asset["relative_path"]).read_bytes() == raw
    assert_published_ico_variants(
        (tmp_path / "vault" / asset["relative_path"]).read_bytes(), fact
    )
    target = next(row for row in record["item_targets"] if row["item_key"] == HOME)
    assert target["declared_appearance"]["icon_asset_id"] == ICON
    assert target["icon_snapshot"]["effective_icon_asset_id"] == ICON
    note = next((tmp_path / "vault").glob("Home*.md")).read_text(encoding="utf-8")
    assert "Icon.png" in note
    assert "## Resources" not in note


def assert_published_ico_variants(raw, fact):
    import struct
    from io import BytesIO

    from PIL import Image

    for variant in fact["directory_order"]:
        width = variant["width"]
        offset, size = variant["offset"], variant["body_length"]
        body = raw[offset : offset + size]
        assert hashlib.sha256(body).hexdigest() == variant["body_sha256"]
        wrapper = (
            struct.pack("<HHHBBBBHHII", 0, 1, 1, width, width, 0, 0, 1, 32, size, 22)
            + body
        )
        with Image.open(BytesIO(wrapper), formats=("ICO",)) as image:
            image.load()
            rgba = image.convert("RGBA")
            assert image.size == (variant["width"], variant["height"])
            assert hashlib.sha256(rgba.tobytes()).hexdigest() == variant["rgba_sha256"]
            for sample in variant["literal_samples"]:
                assert list(rgba.getpixel(tuple(sample["xy"]))) == sample["rgba"]


@pytest.mark.parametrize("filename", ["inert-a.ico", "inert-b.ico"])
@pytest.mark.parametrize(
    "mutation",
    [
        "dir_reserved",
        "dir_type",
        "dir_count",
        "entry_width",
        "entry_height",
        "entry_colour",
        "entry_reserved",
        "entry_planes",
        "entry_bits",
        "entry_size",
        "offset_gap",
        "offset_overlap",
        "offset_oob",
        "entry_order",
        "entry_duplicate",
        "header_size",
        "dib_width",
        "dib_height",
        "negative_height",
        "dib_planes",
        "dib_bits",
        "compression",
        "image_size",
        "x_density",
        "y_density",
        "colours_used",
        "colours_important",
        "trailer",
        "truncate",
        "png_body",
    ],
)
def test_ico_each_directory_dib_and_extent_near_miss_refuses_without_publication(
    tmp_path, filename, mutation
):
    import struct

    raw = bytearray((INPUTS / filename).read_bytes())
    fact = next(row for row in ICO_FACTS["payloads"] if row["file"] == filename)
    # Index1 is nondefault for both containers; the preferred largest body stays intact.
    variant = fact["directory_order"][1]
    entry = 6 + 16
    body = variant["offset"]
    directory_fields = {
        "dir_reserved": ("<H", 0, 1),
        "dir_type": ("<H", 2, 2),
        "dir_count": ("<H", 4, 1),
        "entry_width": ("<B", entry, 0),
        "entry_height": ("<B", entry + 1, 0),
        "entry_colour": ("<B", entry + 2, 1),
        "entry_reserved": ("<B", entry + 3, 1),
        "entry_planes": ("<H", entry + 4, 2),
        "entry_bits": ("<H", entry + 6, 24),
        "entry_size": ("<I", entry + 8, variant["body_length"] + 1),
        "offset_gap": ("<I", entry + 12, body + 1),
        "offset_overlap": ("<I", entry + 12, body - 1),
        "offset_oob": ("<I", entry + 12, len(raw) + 1),
    }
    dib_fields = {
        "header_size": ("<I", 0, 108),
        "dib_width": ("<i", 4, variant["width"] + 1),
        "dib_height": ("<i", 8, variant["height"]),
        "negative_height": ("<i", 8, -2 * variant["height"]),
        "dib_planes": ("<H", 12, 2),
        "dib_bits": ("<H", 14, 24),
        "compression": ("<I", 16, 3),
        "image_size": ("<I", 20, 4 * variant["width"] * variant["height"]),
        "x_density": ("<i", 24, 1),
        "y_density": ("<i", 28, 1),
        "colours_used": ("<I", 32, 1),
        "colours_important": ("<I", 36, 1),
    }
    if mutation in directory_fields:
        fmt, offset, value = directory_fields[mutation]
        struct.pack_into(fmt, raw, offset, value)
    elif mutation in dib_fields:
        fmt, offset, value = dib_fields[mutation]
        struct.pack_into(fmt, raw, body + offset, value)
    elif mutation == "entry_order":
        raw[6:22], raw[22:38] = raw[22:38], raw[6:22]
    elif mutation == "entry_duplicate":
        raw[22:38] = raw[6:22]
    elif mutation == "trailer":
        raw += b"\x00"
    elif mutation == "truncate":
        del raw[-1]
    else:
        raw[body : body + 8] = b"\x89PNG\r\n\x1a\n"
    with api_server(IcoIconApi(bytes(raw))) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.receipt is None
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize("variant_index", [1, 2])
@pytest.mark.parametrize("region", ["mask", "tail"])
def test_padded_ico_large_variants_require_zero_mask_and_zero_tail(
    tmp_path, variant_index, region
):
    fact = next(row for row in ICO_FACTS["payloads"] if row["file"] == "inert-b.ico")
    variant = fact["directory_order"][variant_index]
    raw = bytearray((INPUTS / "inert-b.ico").read_bytes())
    offset = variant["offset"] + 40 + 4 * variant["width"] * variant["height"]
    if region == "tail":
        offset += variant["mask_length"]
    raw[offset] = 1
    with api_server(IcoIconApi(bytes(raw))) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail("A nonzero padded mask/tail must refuse")


VARIANTS = [
    (fact["file"], index)
    for fact in ICO_FACTS["payloads"]
    for index in range(len(fact["directory_order"]))
]


@pytest.mark.parametrize("filename,index", VARIANTS)
@pytest.mark.parametrize("delta", [-1, 1])
def test_each_ico_body_has_exact_extent_even_when_container_length_is_unchanged(
    filename, index, delta
):
    import struct

    fact = next(row for row in ICO_FACTS["payloads"] if row["file"] == filename)
    raw = (INPUTS / filename).read_bytes()
    count = len(fact["directory_order"])
    bodies = [
        raw[row["offset"] : row["offset"] + row["body_length"]]
        for row in fact["directory_order"]
    ]
    other = (index + 1) % count
    bodies[index] = bodies[index] + b"\x00" if delta > 0 else bodies[index][:-1]
    bodies[other] = bodies[other][:-1] if delta > 0 else bodies[other] + b"\x00"
    directory = bytearray(raw[: 6 + 16 * count])
    offset = len(directory)
    for position, body in enumerate(bodies):
        struct.pack_into("<II", directory, 6 + 16 * position + 8, len(body), offset)
        offset += len(body)
    mutated = bytes(directory) + b"".join(bodies)
    assert len(mutated) == len(raw)
    with api_server(IcoIconApi(mutated)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail("Balanced size mutations cannot hide an illegal body extent")


@pytest.mark.parametrize("filename,index", VARIANTS)
@pytest.mark.parametrize("fault", ["format", "dimensions", "decode"])
def test_every_advertised_ico_variant_requires_matching_full_decoder_result(
    tmp_path, monkeypatch, filename, index, fault
):
    from PIL import Image

    fact = next(row for row in ICO_FACTS["payloads"] if row["file"] == filename)
    width = fact["directory_order"][index]["width"]
    original_open = Image.open
    reached = []

    class FaultedDecoder:
        def __init__(self, image):
            self.image = image
            self.format = "PNG" if fault == "format" else image.format
            self.size = (width + 1, width) if fault == "dimensions" else image.size

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.image.close()

        def verify(self):
            self.image.verify()

        def load(self):
            if fault == "decode":
                raise OSError("CODEC_CANARY")
            return self.image.load()

        def convert(self, mode):
            return self.image.convert(mode)

    def codec(*args, **kwargs):
        image = original_open(*args, **kwargs)
        if kwargs.get("formats") == ("ICO",) and image.size == (width, width):
            reached.append(width)
            return FaultedDecoder(image)
        return image

    monkeypatch.setattr(Image, "open", codec)
    with api_server(IcoIconApi((INPUTS / filename).read_bytes())) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert reached
    assert result.outcome == "refused"
    assert result.receipt is None and not (tmp_path / "vault").exists()
    assert "CANARY" not in result.model_dump_json()


@pytest.mark.parametrize("filename", ["inert-a.ico", "inert-b.ico"])
def test_nondefault_ico_corruption_refuses_while_default_variant_still_decodes(
    filename,
):
    import struct
    from io import BytesIO

    from PIL import Image

    fact = next(row for row in ICO_FACTS["payloads"] if row["file"] == filename)
    raw = bytearray((INPUTS / filename).read_bytes())
    variant = fact["directory_order"][1]
    struct.pack_into("<I", raw, variant["offset"] + 16, 3)
    with Image.open(BytesIO(raw), formats=("ICO",)) as default:
        default.load()
        expected = 32 if filename == "inert-a.ico" else 48
        assert default.size == (expected, expected)
    with api_server(IcoIconApi(bytes(raw))) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail(
                "A default decode does not authorize the nondefault corrupt body"
            )


BLUE_IMAGE = "a3333333-3333-4333-8333-333333333334"
UNREFERENCED_IMAGE = "a3333333-3333-4333-8333-333333333335"
BLUE_JPEG = (INPUTS / "inert-blue.jpg").read_bytes()
BLUE_FACTS = json.loads((INPUTS / "jpeg-source-facts.json").read_bytes())
ORDERED_JPEG_NOTE = (
    "Before \u00e9\r\n![red](.data/md-images/"
    + IMAGE
    + '.jpg "caption") next\r'
    + "![blue](.data/md-images/"
    + BLUE_IMAGE
    + ".jpg#$width=50p$)\nAfter\n"
).encode("utf-8")


class OrderedJpegApi(JpegImageApi):
    def __init__(self):
        super().__init__()
        self.payloads[NOTE] = ORDERED_JPEG_NOTE
        self.attachments[NOTE]["dataLength"] = len(ORDERED_JPEG_NOTE)
        self.attachments[BLUE_IMAGE] = attachment(
            BLUE_IMAGE, HOME, 12, BLUE_IMAGE + ".jpg", length=632
        )
        self.payloads[BLUE_IMAGE] = BLUE_JPEG
        self.attachments[UNREFERENCED_IMAGE] = attachment(
            UNREFERENCED_IMAGE, ALONE, 12, UNREFERENCED_IMAGE + ".jpg", length=634
        )
        self.payloads[UNREFERENCED_IMAGE] = JPEG


def test_jpeg_order_alt_title_unicode_width_and_unreferenced_owned_content(tmp_path):
    assert len(BLUE_JPEG) == BLUE_FACTS["length"] == 632
    assert hashlib.sha256(BLUE_JPEG).hexdigest() == BLUE_FACTS["sha256"]
    with (
        api_server(OrderedJpegApi()) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        references = session.snapshot.documents[0].references
        assert [r.target for r in references] == [IMAGE, BLUE_IMAGE]
        assert [r.display_text for r in references] == ["red", "blue"]
        assert references[0].start == 10
        assert (
            references[0].expected_original
            == "![red](.data/md-images/" + IMAGE + '.jpg "caption")'
        )
        assert references[1].presentation_normalization.declaration == "#$width=50p$"
        session.verify_consistency()
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert inspected.outcome == result.outcome == "warnings"
    assert {issue.code for issue in result.issues} == {"image_presentation_normalized"}
    note = next((tmp_path / "vault").glob("Home*.md")).read_bytes().decode("utf-8")
    expected = (
        "Before \u00e9\r\n![red](Attachments/22222222/"
        + IMAGE
        + '.jpg "caption") next\r'
        + "![blue](Attachments/22222222/"
        + BLUE_IMAGE
        + ".jpg)\nAfter\n"
    )
    assert expected in note
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == ORDERED_JPEG_NOTE
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    targets = {row["asset_id"]: row for row in record["asset_targets"]}
    for key, original in (
        (IMAGE, JPEG),
        (BLUE_IMAGE, BLUE_JPEG),
        (UNREFERENCED_IMAGE, JPEG),
    ):
        assert (
            tmp_path / "vault" / targets[key]["relative_path"]
        ).read_bytes() == original
    assert next(row for row in record["item_targets"] if row["item_key"] == ALONE)[
        "created"
    ]
    assert (tmp_path / "vault/Notes/Alone.md").is_file()


def test_icon_only_empty_item_is_not_promoted_to_content(tmp_path):
    raw = (INPUTS / "inert-a.ico").read_bytes()
    with api_server(IcoIconApi(raw, owner=ALONE)) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    target = next(row for row in record["item_targets"] if row["item_key"] == ALONE)
    assert not target["created"]
    assert not (tmp_path / "vault" / target["relative_path"]).exists()


@pytest.mark.parametrize("explicit", [False, True])
def test_ico_type_inheritance_and_explicit_precedence_preserve_both_containers(
    tmp_path, explicit
):
    from tests.support.local_api_graph import DEFINITION
    from tests.support.local_api_payloads import DIRECT_ICON, TYPE_ICON, RichPayloadApi

    api = RichPayloadApi(explicit=explicit)
    expected = {TYPE_ICON: (INPUTS / "inert-a.ico").read_bytes()}
    if explicit:
        expected[DIRECT_ICON] = (INPUTS / "inert-b.ico").read_bytes()
    for key, raw in expected.items():
        api.payloads[key] = raw
        api.attachments[key]["dataLength"] = len(raw)
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    items = {row["item_key"]: row for row in record["item_targets"]}
    assert items[DEFINITION]["declared_appearance"]["icon_asset_id"] == TYPE_ICON
    assert items[HOME]["icon_snapshot"]["effective_icon_asset_id"] == (
        DIRECT_ICON if explicit else TYPE_ICON
    )
    assets = {row["asset_id"]: row for row in record["asset_targets"]}
    for key, raw in expected.items():
        assert (
            assets[key]["role"] == "icon" and assets[key]["original_name"] == "Icon.png"
        )
        assert (tmp_path / "vault" / assets[key]["relative_path"]).read_bytes() == raw


@pytest.mark.parametrize("filename", ["inert-a.ico", "inert-b.ico"])
@pytest.mark.parametrize("kind,forgotten", [(1, "2026-01-01T00:00:00"), (5, None)])
def test_known_excluded_ico_owner_and_association_stay_excluded_before_artwork_fetch(
    filename, kind, forgotten
):
    from tests.support.local_api_graph import HIERARCHY

    api = IcoIconApi((INPUTS / filename).read_bytes(), owner=ALONE)
    api.thoughts[ALONE].update(
        kind=kind,
        forgottenDateTime=forgotten,
        name="EXCLUDED_CANARY",
        label="EXCLUDED_CANARY",
    )
    api.links[HIERARCHY].update(
        meaning=6, name="EXCLUDED_CANARY", color="EXCLUDED_CANARY"
    )
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        assert {item.key for item in session.snapshot.items} == {HOME}
        assert session.snapshot.relationships == ()
        assert ICON not in {asset.asset_id for asset in session.snapshot.assets}
        assert "CANARY" not in session.snapshot.model_dump_json()
        session.verify_consistency()
    assert not any(
        path
        in {
            f"/api/attachments/{BRAIN}/{ICON}/file-content",
            f"/api/thoughts/{BRAIN}/{ALONE}/attachments",
        }
        for path, _, _ in api.requests
    )


@pytest.mark.parametrize("version", ["1", "2"])
@pytest.mark.parametrize("filename", ["inert-a.ico", "inert-b.ico"])
def test_explicit_older_profiles_refuse_finite_ico(version, filename):
    with api_server(IcoIconApi((INPUTS / filename).read_bytes())) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=version,
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pytest.fail("The older profile must not accept ICO bytes")
