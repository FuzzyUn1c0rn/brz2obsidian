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
