"""Finite profile3 static SVGs through public HTTP source and capture seams."""

import hashlib
import json

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import IMAGE, NOTE, PayloadApi, attachment

SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="16" '
    b'viewBox="0 0 24 16"><rect x="1" y="2" width="8" height="6" '
    b'fill="#aBc"/><line x1="0" y1="0" x2="24" y2="16" '
    b'stroke="#010203" stroke-width=".5" stroke-linecap="round"/></svg>'
)
SVG_NOTE = (
    "# Drawing\r\n\r\n![Shape](.data/md-images/" + IMAGE + '.svg "Source")\r\n'
).encode()


class SvgApi(PayloadApi):
    def __init__(self, raw=SVG):
        super().__init__()
        self.payloads[NOTE] = SVG_NOTE
        self.attachments[NOTE]["dataLength"] = len(SVG_NOTE)
        self.attachments[IMAGE] = attachment(
            IMAGE, HOME, 12, IMAGE + ".svg", length=len(raw)
        )
        self.payloads[IMAGE] = raw


def test_svg_static_drawing_retains_original_bytes_role_and_authored_placement(
    tmp_path,
):
    with api_server(SvgApi()) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspection = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspection.outcome == "clean", inspection.issues
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    asset = next(row for row in record["asset_targets"] if row["asset_id"] == IMAGE)
    assert (asset["owner"], asset["role"], asset["original_name"]) == (
        HOME,
        "image",
        IMAGE + ".svg",
    )
    assert (asset["actual_length"], asset["actual_sha256"]) == (
        len(SVG),
        hashlib.sha256(SVG).hexdigest(),
    )
    assert (tmp_path / "vault" / asset["relative_path"]).read_bytes() == SVG
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == SVG_NOTE
    note = next((tmp_path / "vault").glob("Home*.md")).read_text(encoding="utf-8")
    assert "![Shape](Attachments/22222222/" + IMAGE + '.svg "Source")' in note


def drawing(child="", *, width="24", height="16", viewbox="0 0 24 16"):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="'
        + width
        + '" height="'
        + height
        + '" viewBox="'
        + viewbox
        + '">'
        + child
        + "</svg>"
    ).encode("utf-8")


VALID_DRAWINGS = [
    drawing(),
    b'<?xml version="1.0"?>' + SVG,
    b"<?xml version='1.0' encoding='utf-8' ?>\r\n" + SVG,
    drawing(
        '\n\t<rect width="1" height="2"/> \r\n<line x1="0" y1="0" x2="0" y2="0" stroke="none"/>\t'
    ),
    drawing(
        '<rect x="-0" y="-1000000" width="1000000" height=".1" fill="none" stroke="#AbC"/>'
    ),
    drawing(
        '<rect width="+1." height="2e+2" stroke-width="1e-9999999999999999999999999999999999999999999999999999999999999"/>'
    ),
    drawing(
        '<line x1="+.2" y1="-.2" x2="-0e9999999999999999999999999999999999999999999999999999999999999" y2="+0" stroke="#ABCdef" stroke-width=".0001" stroke-linecap="butt"/>'
    ),
    drawing(
        '<line x1="1e6" y1="-1E+6" x2="1.0" y2="-1." stroke="none" stroke-linecap="square"/>'
    ),
    drawing('<rect xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'),
    drawing(" \n<![CDATA[\t\r\n]]>\t"),
    drawing(width="32768", height="32768", viewbox="-1000000,+1000000,1000000,1000000"),
    drawing(
        width="1e-9999999999999999999999999999999999999999999999999999999999999",
        height=".1",
    ),
    drawing(width="0." + "0" * 61 + "1"),
    drawing(viewbox=" \t-1, +2\r\n3,4 "),
    drawing(viewbox="0 0, 24 16"),
]


@pytest.mark.parametrize("raw", VALID_DRAWINGS)
def test_svg_preserves_each_eligible_static_grammar_spelling(raw):
    with (
        api_server(SvgApi(raw)) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        session.verify_consistency()
        with session.open_payload(IMAGE) as payload:
            assert payload.read() == raw


INVALID_XML = [
    b"",
    SVG + SVG,
    b"\xef\xbb\xbf" + SVG,
    SVG.decode().encode("utf-16"),
    SVG.decode().encode("utf-32"),
    SVG.decode().encode("utf-16-le"),
    SVG.decode().encode("utf-32-le"),
    SVG + b"\xff",
    SVG[:-6],
    b'<?xml version="1.1"?>' + SVG,
    b'<?xml version="1.0" encoding="ASCII"?>' + SVG,
    b'<?xml version="1.0" encoding="UTF-16"?>' + SVG,
    b'<?xml version="1.0" standalone="yes"?>' + SVG,
    b'<?xml version="1.0" standalone="no"?>' + SVG,
    b"<?harmless ?>" + SVG,
    SVG.replace(b"<rect", b"<?harmless ?><rect"),
    SVG + b"<?harmless ?>",
    b"<!-- harmless -->" + SVG,
    SVG.replace(b"<rect", b"<!-- harmless --><rect"),
    SVG + b"<!-- harmless -->",
    b'<!DOCTYPE svg SYSTEM "http://127.0.0.1:9/DTD_CANARY">' + SVG,
    b'<!DOCTYPE svg [<!ENTITY data SYSTEM "file:///C:/ENTITY_CANARY">]>' + SVG,
    SVG.replace(b'viewBox="0 0', b'viewBox="0&#32;0'),
    SVG.replace(b'viewBox="0 0', b'viewBox="0&#x20;0'),
    drawing("&amp;"),
    drawing("&lt;"),
    SVG.replace(b'width="24"', b'width="24" xmlns:unused="urn:foreign"', 1),
    SVG.replace(b'width="24"', b'width="24" xmlns:s="http://www.w3.org/2000/svg"', 1),
    SVG.replace(b"http://www.w3.org/2000/svg", b"urn:foreign", 1),
    SVG.replace(b' xmlns="http://www.w3.org/2000/svg"', b"", 1),
    drawing('<rect xmlns="" width="1" height="1"/>'),
    drawing('<rect xmlns="urn:foreign" width="1" height="1"/>'),
    SVG.replace(b'width="24"', b'width="24" xml:space="preserve"', 1),
    SVG.replace(b'width="24"', b'width="24" extra=""', 1),
    SVG.replace(b'width="24"', b'width="24" width="24"', 1),
    SVG.replace(b' height="16"', b"", 1),
    SVG.replace(b' viewBox="0 0 24 16"', b"", 1),
    drawing('<svg width="1" height="1" viewBox="0 0 1 1"/>'),
    drawing(
        '<rect width="1" height="1"><line x1="0" y1="0" x2="1" y2="1" stroke="none"/></rect>'
    ),
    drawing("text"),
    drawing('<rect width="1" height="1">text</rect>'),
    drawing('<rect width="1" height="1"/>text'),
    drawing("\u00a0"),
]


@pytest.mark.parametrize("raw", INVALID_XML)
def test_svg_refuses_lexical_namespace_and_structural_near_misses(raw):
    with (
        api_server(SvgApi(raw)) as (_, address),
        pytest.raises(MigrationRefused),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)),
    ):
        pytest.fail("Unsupported SVG syntax must refuse before normalization")


@pytest.mark.parametrize(
    "value",
    [
        "NaN",
        "Infinity",
        "-inf",
        "1e1000000000000000000000000000000",
        "1000000.0001",
        "-1000000.0001",
        "1.000001e6",
        "1e+",
        ".",
        "+",
        "1px",
        "1%",
        "calc(1)",
        "1_0",
        " 1",
        "1 ",
        "1,0",
        "\u00a01",
        "\uff11",
        "0." + "0" * 62 + "1",
    ],
)
def test_svg_numeric_lexeme_and_magnitude_boundaries_refuse(value):
    raw = drawing('<rect width="1" height="1" x="' + value + '"/>')
    assert_svg_refused(raw)


def assert_svg_refused(raw):
    with (
        api_server(SvgApi(raw)) as (_, address),
        pytest.raises(MigrationRefused),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)),
    ):
        pytest.fail("A source outside the closed static SVG grammar must refuse")


@pytest.mark.parametrize("dimension", ["width", "height"])
@pytest.mark.parametrize("value", ["0", "-0", "-1", "32769", "32768.0001", "1e6"])
def test_svg_root_dimension_bounds_are_distinct_from_shape_bounds(dimension, value):
    assert_svg_refused(drawing(**{dimension: value}))


@pytest.mark.parametrize(
    "shape", ["rect_width", "rect_height", "rect_stroke", "line_stroke"]
)
@pytest.mark.parametrize(
    "value", ["0", "-0e9999999999999999999999999999999999999999", "-.1"]
)
def test_svg_shape_dimensions_and_both_stroke_widths_are_positive(shape, value):
    if shape.startswith("rect"):
        attrs = {"width": "1", "height": "1"}
        attrs[
            {
                "rect_width": "width",
                "rect_height": "height",
                "rect_stroke": "stroke-width",
            }[shape]
        ] = value
        child = (
            "<rect "
            + " ".join(key + '="' + item + '"' for key, item in attrs.items())
            + "/>"
        )
    else:
        child = (
            '<line x1="0" y1="0" x2="0" y2="0" stroke="none" stroke-width="'
            + value
            + '"/>'
        )
    assert_svg_refused(drawing(child))


@pytest.mark.parametrize(
    "value",
    [
        "",
        "0 0 1",
        "0 0 1 1 2",
        ",0 0 1 1",
        "0 0 1 1,",
        "0,,0 1 1",
        "0, ,0 1 1",
        "0 0 0 1",
        "0 0 1 0",
        "0 0 -1 1",
        "0 0 1 -1",
        "0;0;1;1",
        "0\u00a00 1 1",
        "0 0 1px 1",
        "0 0 1000001 1",
    ],
)
def test_svg_viewbox_requires_four_nonempty_exact_number_terms(value):
    assert_svg_refused(drawing(viewbox=value))


@pytest.mark.parametrize(
    "child",
    [
        '<rect height="1"/>',
        '<rect width="1"/>',
        '<line y1="0" x2="1" y2="1" stroke="none"/>',
        '<line x1="0" x2="1" y2="1" stroke="none"/>',
        '<line x1="0" y1="0" y2="1" stroke="none"/>',
        '<line x1="0" y1="0" x2="1" stroke="none"/>',
        '<line x1="0" y1="0" x2="1" y2="1"/>',
        '<rect width="1" height="1" rx="0"/>',
        '<rect width="1" height="1" stroke-linecap="butt"/>',
        '<line x1="0" y1="0" x2="1" y2="1" stroke="none" fill="none"/>',
        '<line x1="0" y1="0" x2="1" y2="1" stroke="none" stroke-linecap="Round"/>',
    ],
)
def test_svg_closed_shape_attribute_sets_refuse_near_misses(child):
    assert_svg_refused(drawing(child))


@pytest.mark.parametrize("attribute", ["fill", "stroke"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        "#1234",
        "#12345678",
        "#ggg",
        "red",
        "None",
        "transparent",
        "rgb(0,0,0)",
        "url(#paint)",
    ],
)
def test_svg_colour_literals_have_only_the_qualified_forms(attribute, value):
    assert_svg_refused(
        drawing('<rect width="1" height="1" ' + attribute + '="' + value + '"/>')
    )


@pytest.mark.parametrize(
    "tag",
    [
        "script",
        "foreignObject",
        "image",
        "use",
        "a",
        "style",
        "defs",
        "filter",
        "animate",
        "font",
        "text",
        "circle",
        "path",
        "g",
    ],
)
def test_svg_prohibited_element_families_refuse_without_interpretation(tag):
    assert_svg_refused(drawing("<" + tag + "/>"))


@pytest.mark.parametrize(
    "attribute",
    [
        "style",
        "onclick",
        "onload",
        "href",
        "src",
        "filter",
        "font-family",
        "transform",
        "opacity",
        "id",
        "class",
    ],
)
def test_svg_prohibited_attribute_families_refuse_even_when_empty(attribute):
    assert_svg_refused(drawing('<rect width="1" height="1" ' + attribute + '=""/>'))


@pytest.mark.parametrize("boundary", ["bytes", "elements"])
@pytest.mark.parametrize("excess", [0, 1])
def test_svg_exact_payload_and_element_limits_include_the_root(boundary, excess):
    if boundary == "bytes":
        blank = drawing()
        raw = drawing(" " * (1048576 - len(blank) + excess))
        assert len(raw) == 1048576 + excess
    else:
        raw = drawing('<rect width="1" height="1"/>' * (4095 + excess))
    if excess:
        assert_svg_refused(raw)
    else:
        with (
            api_server(SvgApi(raw)) as (_, address),
            LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="3",
            ).open(LocalApiSourceRef(BRAIN)) as session,
        ):
            session.verify_consistency()
            with session.open_payload(IMAGE) as payload:
                assert payload.read() == raw


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
        "name_text",
        "uppercase",
        "wrong_uuid",
        "noncanonical_uuid",
        "traversal",
        "foreign_brain",
        "foreign_owner",
        "cross_owner",
        "graph_mismatch",
        "metadata_mismatch",
        "private_owner",
        "custom_owner",
        "missing",
        "interrupted",
        "png_bytes",
        "unreferenced_corrupt",
        "duplicate_location",
    ],
)
def test_svg_requires_closed_declarations_full_joins_and_every_owned_payload(
    tmp_path, mutation
):
    from tests.support.local_api_payloads import PNG

    api = SvgApi()
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
    elif mutation in {"uppercase", "wrong_uuid", "noncanonical_uuid", "traversal"}:
        value["location"] = {
            "uppercase": IMAGE + ".SVG",
            "wrong_uuid": NOTE + ".svg",
            "noncanonical_uuid": IMAGE.replace("-", "") + ".svg",
            "traversal": "../" + IMAGE + ".svg",
        }[mutation]
    elif mutation == "foreign_brain":
        value["brainId"] = NOTE
    elif mutation == "foreign_owner":
        value["sourceId"] = BRAIN
        api.overrides[f"/api/thoughts/{BRAIN}/{HOME}/attachments"] = (
            200,
            [api.attachments[NOTE], value],
        )
    elif mutation == "cross_owner":
        value["sourceId"] = ALONE
    elif mutation == "graph_mismatch":
        path = f"/api/thoughts/{BRAIN}/{HOME}/graph"
        graph = api.response(path, {})[1]
        api.overrides[path] = 200, dict(graph, attachments=[api.attachments[NOTE]])
    elif mutation == "metadata_mismatch":
        api.overrides[f"/api/attachments/{BRAIN}/{IMAGE}/metadata"] = (
            200,
            value | {"position": 1},
        )
    elif mutation in {"private_owner", "custom_owner"}:
        api.thoughts[ALONE]["acType" if mutation == "private_owner" else "kind"] = (
            1 if mutation == "private_owner" else 3
        )
    elif mutation in {"missing", "interrupted"}:
        api.overrides[f"/api/attachments/{BRAIN}/{IMAGE}/file-content"] = (
            (404, b"PRIVATE_CANARY")
            if mutation == "missing"
            else (200, SVG[:20], {"Content-Length": str(len(SVG))})
        )
    elif mutation == "png_bytes":
        api.payloads[IMAGE] = PNG
    else:
        extra = "a3333333-3333-4333-8333-333333333334"
        api.attachments[extra] = attachment(
            extra,
            HOME if mutation == "duplicate_location" else ALONE,
            12,
            IMAGE + ".svg" if mutation == "duplicate_location" else extra + ".svg",
        )
        api.payloads[extra] = SVG if mutation == "duplicate_location" else SVG[:-6]
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome in {"refused", "failed"} and result.receipt is None
    assert not (tmp_path / "vault").exists()
    assert "CANARY" not in result.model_dump_json()


@pytest.mark.parametrize("version", ["1", "2", None])
def test_svg_keeps_explicit_old_profiles_and_direct_default_refusals(version):
    with api_server(SvgApi()) as (_, address):
        kwargs = {} if version is None else {"profile_version": version}
        with (
            pytest.raises(MigrationRefused),
            LocalApiSourceModule(
                LocalApiConfig(api_url=address), credentials=lambda: KEY, **kwargs
            ).open(LocalApiSourceRef(BRAIN)),
        ):
            pytest.fail("SVG is exclusive to explicit profile3")


SECOND = "a3333333-3333-4333-8333-333333333334"
REPEATED_NOTE = (
    "Before é\r\n![First](.data/md-images/"
    + IMAGE
    + '.svg "One")\r\nBetween\r\n![Again](.data/md-images/'
    + IMAGE
    + '.svg "Two")\r\n'
).encode("utf-8")


class DualSvgApi(SvgApi):
    def __init__(self):
        super().__init__()
        self.attachments[SECOND] = attachment(
            SECOND, ALONE, 12, SECOND + ".svg", length=len(SVG)
        )
        self.payloads[SECOND] = SVG
        self.payloads[NOTE] = REPEATED_NOTE
        self.attachments[NOTE]["dataLength"] = len(REPEATED_NOTE)


def test_equal_svg_bytes_keep_distinct_ids_owned_files_and_ordered_source_spans(
    tmp_path,
):
    with api_server(DualSvgApi()) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            images = [
                asset for asset in session.snapshot.assets if asset.role == "image"
            ]
            assert {(asset.asset_id, asset.owner) for asset in images} == {
                (IMAGE, HOME),
                (SECOND, ALONE),
            }
            assert {asset.actual_sha256 for asset in images} == {
                hashlib.sha256(SVG).hexdigest()
            }
            refs = session.snapshot.documents[0].references
            assert [ref.target for ref in refs] == [IMAGE, IMAGE]
            assert refs[0].start == 10
            assert refs[0].end < refs[1].start
            entries = {
                entry.identity: entry for entry in session.snapshot.accounting.entries
            }
            assert entries["attachment:" + SECOND].disposition == "normalized"
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    images = [asset for asset in record["asset_targets"] if asset["role"] == "image"]
    assert {asset["asset_id"] for asset in images} == {IMAGE, SECOND}
    assert len({asset["relative_path"] for asset in images}) == 2
    for asset in images:
        assert (tmp_path / "vault" / asset["relative_path"]).read_bytes() == SVG
    assert any(
        item["item_key"] == ALONE and item["relative_path"]
        for item in record["item_targets"]
    )
    note = next((tmp_path / "vault").glob("Home*.md")).read_text(encoding="utf-8")
    first = "![First](Attachments/22222222/" + IMAGE + '.svg "One")'
    second = "![Again](Attachments/22222222/" + IMAGE + '.svg "Two")'
    assert note.index(first) < note.index(second)
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == REPEATED_NOTE


def captured_svg_inputs(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with (
        api_server(DualSvgApi()) as (_, address),
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
                with session.open_payload(asset.asset_id) as payload:
                    payloads[asset.asset_id] = payload.read()
    return source, audit, snapshot, payloads


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "role",
        "name",
        "reference",
        "unreferenced_invalid",
        "unreferenced_omitted",
        "measurements",
        "profile1",
        "profile2",
        "excluded_system",
        "excluded_forgotten",
    ],
)
def test_fresh_svg_capture_rejects_invalid_bindings_even_with_regenerated_hashes(
    tmp_path, monkeypatch, mutation
):
    from brz2obsidian.contracts import SourceSnapshot
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession

    source, audit, snapshot, payloads = captured_svg_inputs(tmp_path, monkeypatch)
    clean = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        profile_version="3",
    )
    clean.verify_consistency()
    clean.close()
    asset = next(row for row in snapshot["assets"] if row["asset_id"] == SECOND)
    fact = next(row for row in source["payloads"] if row["asset_id"] == SECOND)
    version = "3"
    if mutation == "owner":
        asset["owner"] = HOME
    elif mutation == "role":
        asset["role"] = "file"
    elif mutation == "name":
        asset["original_name"] = "Other.svg"
    elif mutation == "reference":
        snapshot["documents"][0]["references"][0]["target"] = SECOND
    elif mutation == "unreferenced_invalid":
        payloads[SECOND] = SVG.replace(b"<rect ", b"<script ")
        asset["actual_sha256"] = fact["actual_sha256"] = hashlib.sha256(
            payloads[SECOND]
        ).hexdigest()
        asset["actual_length"] = fact["actual_length"] = len(payloads[SECOND])
    elif mutation == "unreferenced_omitted":
        snapshot["assets"].remove(asset)
        del payloads[SECOND]
    elif mutation == "measurements":
        asset["actual_length"] = fact["actual_length"] = len(SVG) - 1
    elif mutation.startswith("excluded_"):
        thought = next(
            row for row in source["records"] if row["key"] == "thought:" + ALONE
        )
        thought["value"]["kind"] = 5 if mutation == "excluded_system" else 1
        thought["value"]["forgottenDateTime"] = (
            "2026-01-01T00:00:00" if mutation == "excluded_forgotten" else None
        )
        next(
            row for row in snapshot["original_evidence"] if row["key"] == thought["key"]
        )["original_json"] = json.dumps(thought["value"])
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


@pytest.mark.parametrize("change", ["drawing", "identity"])
def test_valid_changed_svg_capture_has_different_content_identity(
    tmp_path, monkeypatch, change
):
    from brz2obsidian.contracts import SourceSnapshot
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession

    source, audit, snapshot, payloads = captured_svg_inputs(tmp_path, monkeypatch)
    original = snapshot["identity"].copy()
    if change == "drawing":
        replacement = SVG.replace(b'fill="#aBc"', b'fill="#dEf"')
        payloads[SECOND] = replacement
        asset = next(row for row in snapshot["assets"] if row["asset_id"] == SECOND)
        fact = next(row for row in source["payloads"] if row["asset_id"] == SECOND)
        asset["actual_sha256"] = fact["actual_sha256"] = hashlib.sha256(
            replacement
        ).hexdigest()
    else:
        # A fresh acquisition independently establishes the changed source ID;
        # no neutral identity or source accounting is hand-forged to permit it.
        api = DualSvgApi()
        replacement = "a3333333-3333-4333-8333-333333333335"
        old = api.attachments.pop(SECOND)
        api.attachments[replacement] = old | {
            "id": replacement,
            "location": replacement + ".svg",
        }
        api.payloads[replacement] = api.payloads.pop(SECOND)
        with (
            api_server(api) as (_, address),
            LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="3",
            ).open(LocalApiSourceRef(BRAIN)) as session,
        ):
            assert session.snapshot.identity.source_sha256 != original["source_sha256"]
            assert (
                session.snapshot.identity.snapshot_digest != original["snapshot_digest"]
            )
        return
    snapshot["identity"].update(source_sha256="", snapshot_digest="")
    fresh = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        profile_version="3",
    )
    try:
        fresh.verify_consistency()
        assert fresh.snapshot.identity.source_sha256 != original["source_sha256"]
        assert fresh.snapshot.identity.snapshot_digest != original["snapshot_digest"]
    finally:
        fresh.close()


@pytest.mark.parametrize("excluded", ["forgotten", "system"])
def test_known_excluded_svg_owner_is_skipped_before_authored_content_fetch(excluded):
    api = DualSvgApi()
    if excluded == "forgotten":
        api.thoughts[ALONE]["forgottenDateTime"] = "2026-01-01T00:00:00"
    else:
        api.thoughts[ALONE]["kind"] = 5
    api.payloads[SECOND] = b"PRIVATE_CANARY unsupported artwork"
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        assert {asset.asset_id for asset in session.snapshot.assets} == {NOTE, IMAGE}
        assert "CANARY" not in session.snapshot.model_dump_json()
        session.verify_consistency()
    assert not any(
        path == f"/api/attachments/{BRAIN}/{SECOND}/file-content"
        or path == f"/api/thoughts/{BRAIN}/{ALONE}/attachments"
        for path, _, _ in api.requests
    )


@pytest.mark.parametrize("recompute_manifest", [False, True])
def test_trusted_pin_detects_equal_length_unrequested_svg_mutation(
    tmp_path, monkeypatch, recompute_manifest
):
    import os
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with (
        api_server(DualSvgApi()) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        directory = next(tmp_path.glob("brz2obsidian-api-*"))
        manifest = json.loads((directory / "manifest.json").read_bytes())
        binding = next(
            row for row in manifest["payload_bindings"] if row["asset_id"] == SECOND
        )
        path = directory / binding["storage_key"]
        before = path.stat()
        replacement = SVG.replace(b'fill="#aBc"', b'fill="#dEf"')
        assert len(replacement) == len(SVG)
        path.write_bytes(replacement)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        if recompute_manifest:
            next(
                row
                for row in manifest["files"]
                if row["storage_key"] == binding["storage_key"]
            )["actual_sha256"] = hashlib.sha256(replacement).hexdigest()
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


@pytest.mark.parametrize("syntax", ["doctype", "entity", "href", "image"])
def test_svg_dependencies_refuse_without_any_dependency_io(monkeypatch, syntax):
    import builtins
    import socket
    from pathlib import Path

    actual_open = builtins.open
    actual_path_open = Path.open
    actual_dns = socket.getaddrinfo
    probes = []

    def guarded_open(file, *args, **kwargs):
        if "DEPENDENCY_CANARY" in str(file):
            probes.append(str(file))
            pytest.fail("SVG validation attempted an external source-file read")
        return actual_open(file, *args, **kwargs)

    def guarded_path_open(path, *args, **kwargs):
        if "DEPENDENCY_CANARY" in str(path):
            probes.append(str(path))
            pytest.fail("SVG validation attempted an external Path read")
        return actual_path_open(path, *args, **kwargs)

    def guarded_dns(host, *args, **kwargs):
        if host not in {"127.0.0.1", "localhost", b"127.0.0.1"}:
            probes.append(str(host))
            pytest.fail("SVG validation attempted external network resolution")
        return actual_dns(host, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_dns)
    raw = {
        "doctype": b'<!DOCTYPE svg SYSTEM "http://DEPENDENCY_CANARY.invalid/source.dtd">'
        + SVG,
        "entity": b'<!DOCTYPE svg [<!ENTITY art SYSTEM "file:///C:/DEPENDENCY_CANARY.svg">]>'
        + drawing("&art;"),
        "href": drawing(
            '<rect width="1" height="1" href="http://DEPENDENCY_CANARY.invalid/art"/>'
        ),
        "image": drawing('<image src="data:image/png;base64,DEPENDENCY_CANARY"/>'),
    }[syntax]
    assert_svg_refused(raw)
    assert probes == []


@pytest.mark.parametrize(
    "raw",
    [
        b'<?xml version="1.0" encoding="UTF-8"?>' + SVG,
        drawing(width="0." + "0" * 61 + "1"),
    ],
)
def test_svg_exact_64_character_positive_and_explicit_utf8_declaration(raw):
    with (
        api_server(SvgApi(raw)) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(LocalApiSourceRef(BRAIN)) as session,
    ):
        session.verify_consistency()


def test_svg_prefix_alias_does_not_expand_default_namespace_permission():
    assert_svg_refused(
        b'<s:svg xmlns:s="http://www.w3.org/2000/svg" width="1" height="1" viewBox="0 0 1 1"/>'
    )


def test_existing_url_reference_ending_svg_is_not_fetched_or_reinterpreted(tmp_path):
    from tests.support.local_api_payloads import WEBSITE

    api = SvgApi()
    uri = "https://example.invalid/source.svg?original=1"
    api.attachments[WEBSITE] = attachment(WEBSITE, HOME, 3, uri)
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    assert not any(
        path == f"/api/attachments/{BRAIN}/{WEBSITE}/file-content"
        for path, _, _ in api.requests
    )
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    target = next(row for row in record["asset_targets"] if row["asset_id"] == WEBSITE)
    assert target["role"] == "url" and target["external_uri"] == uri
    assert target["actual_length"] is target["actual_sha256"] is None


def test_svg_uses_existing_width_adaptation_and_keeps_original_note(tmp_path):
    api = SvgApi()
    note = (
        "Before é\r\n![図](.data/md-images/" + IMAGE + ".svg#$width=50p$)\r\n"
    ).encode("utf-8")
    api.payloads[NOTE] = note
    api.attachments[NOTE]["dataLength"] = len(note)
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "warnings"
    assert {issue.code for issue in result.issues} == {"image_presentation_normalized"}
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == note
    published = next((tmp_path / "vault").glob("Home*.md")).read_text(encoding="utf-8")
    assert "![図](Attachments/22222222/" + IMAGE + ".svg)" in published
    assert (tmp_path / f"vault/Attachments/22222222/{IMAGE}.svg").read_bytes() == SVG


def test_qualified_external_file_ending_svg_remains_reference_without_target_io(
    tmp_path, monkeypatch
):
    from pathlib import Path

    from tests.support.local_api_payloads import WEBSITE

    actual_stat = Path.stat
    actual_open = Path.open
    target_calls = []

    def guarded_call(operation, path, *args, **kwargs):
        if str(path).replace("/", "\\").lower().startswith("c:\\source\\"):
            target_calls.append(str(path))
            pytest.fail("An external .svg reference must never access its target")
        return operation(path, *args, **kwargs)

    monkeypatch.setattr(
        Path, "stat", lambda path, *a, **kw: guarded_call(actual_stat, path, *a, **kw)
    )
    monkeypatch.setattr(
        Path, "open", lambda path, *a, **kw: guarded_call(actual_open, path, *a, **kw)
    )
    api = SvgApi()
    api.attachments[WEBSITE] = attachment(WEBSITE, HOME, 2, "C:\\Source\\External.svg")
    with api_server(api) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "clean", result.issues
    assert target_calls == []
    assert not any(
        path == f"/api/attachments/{BRAIN}/{WEBSITE}/file-content"
        for path, _, _ in api.requests
    )
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    asset = next(row for row in record["asset_targets"] if row["asset_id"] == WEBSITE)
    assert asset["role"] == "file" and asset["availability"] == "external"
    assert asset["external_uri"] == "file:///C:/Source/External.svg"
    assert asset["actual_length"] is asset["actual_sha256"] is None
    assert asset["relative_path"] is None
    note = next((tmp_path / "vault").glob("Home*.md")).read_text(encoding="utf-8")
    assert "[External.svg](<file:///C:/Source/External.svg>)" in note
