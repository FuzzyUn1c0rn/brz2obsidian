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


VARIANTS = [
    (fact["file"], index)
    for fact in ICO_FACTS["payloads"]
    for index in range(len(fact["directory_order"]))
]


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


def changed_valid_icon(filename):
    info = next(row for row in ICO_FACTS["payloads"] if row["file"] == filename)
    raw = bytearray((INPUTS / filename).read_bytes())
    raw[info["directory_order"][1]["offset"] + 44] ^= 1
    return bytes(raw)


JPEG_NEIGHBORS = Path(__file__).parents[1] / "fixtures/local_api_jpeg_neighbors_v3"
JPEG_NEIGHBOR_FACTS = json.loads((JPEG_NEIGHBORS / "source-facts.json").read_bytes())
JPEG_COLOUR_FACTS = json.loads(
    (JPEG_NEIGHBORS / "extended-source-facts.json").read_bytes()
)

JPEG_CLASSES = Path(__file__).parents[1] / "fixtures/local_api_jpeg_classes_v3"
JPEG_CLASS_FACTS = json.loads((JPEG_CLASSES / "class-source-facts.json").read_bytes())


class IndependentImageBaselineApi:
    """Serve only response bytes pinned by the independent source author."""

    def __init__(self, baseline):
        baseline.verify()
        self.baseline = baseline
        self.requests = []
        self.response_chunks = {}
        self.response_counts = {}
        self.unexpected_requests = []

    def response(self, path, query):
        responses = self.baseline.data["http_responses"]
        if path not in responses:
            self.unexpected_requests.append(path)
            return 404, b"Unbound source endpoint"
        response = responses[path]
        if isinstance(response, list):
            count = self.response_counts.get(path, 0)
            self.response_counts[path] = count + 1
            response = response[count % len(response)]
        return response["status"], self.baseline.bytes(response["path"])


def assert_independent_image_source_converts_and_audits(baseline, destination):
    from tests.local_acceptance.api_checker import check_api_vault

    brain = baseline.json(baseline.data["brain"])["id"]
    source_ref = LocalApiSourceRef(brain)
    api = IndependentImageBaselineApi(baseline)
    with api_server(api) as (_, address):
        config = LocalApiConfig(api_url=address)
        with LocalApiSourceModule(
            config, credentials=lambda: KEY, profile_version="3"
        ).open(source_ref) as session:
            session.verify_consistency()
            for key, payload in baseline.data["payloads"].items():
                if payload["status"] == 200:
                    with session.open_payload(key) as stream:
                        assert stream.read() == baseline.bytes(payload["path"])
        workflow = local_api_workflow(config, credentials=lambda: KEY)
        inspected = workflow.inspect(source_ref)
        assert not api.unexpected_requests
        assert inspected.outcome in {"clean", "warnings"}, inspected.issues
        converted = workflow.convert(source_ref, destination)
    assert not api.unexpected_requests
    assert converted.outcome in {"clean", "warnings"}, converted.issues
    assert converted.receipt.verified and converted.receipt.published
    baseline.verify()
    record = json.loads((destination / "migration-record.json").read_bytes())
    assert "documents" not in record
    assert any(row["documents"] for row in record["item_targets"])
    check_api_vault(baseline, destination, profile_version="3")
