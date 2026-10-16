"""Independent S7 literals; input-01 pin c153bac8, qualified separately.

These public controls construct raw API evidence and literal output. No runtime
normalizer, encoder or converter is an expectation source.
"""

import hashlib
import json

import pytest

from .api_checker import audit_baseline, check_api_vault, expected_asset
from .api_manifest import load_baseline
from .test_api_acceptance import (
    PNG,
    fingerprint,
    identity,
    reseal,
    source_case,
    write_json,
)

DRAWING = b'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" height="12" width="24" viewBox="-2 -3 24 12">\n  <rect width="3" height="4" x="-1.5" y="+2.0" fill="#aBc" stroke="none" stroke-width=".25"/>\n  <line x1="-2" y1="-3" x2="22" y2="9" stroke="#12ABcd" stroke-width="1e-2" stroke-linecap="round"/>\n</svg>\n'
NOTE = 'Préface Ω.\n![Système](.data/md-images/00000000-0000-4000-8000-000000000205.svg#$width=50p$ "Stencil")\n![Again](.data/md-images/00000000-0000-4000-8000-000000000205.svg)\n![PNG](.data/md-images/00000000-0000-4000-8000-000000000202.png)\n'


def svg_case(
    tmp_path, drawing=DRAWING, raw_note=NOTE, document_text=None, display_note=None
):
    document_text = raw_note if document_text is None else document_text
    baseline, vault = source_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    graph_path = root / manifest["graphs"][identity(2)]
    graph = json.loads(graph_path.read_bytes())
    attachments = graph["attachments"][:2]
    attachments[1].update(location=identity(202) + ".png")
    for key in (205, 206):
        attachments.append(
            {
                "id": identity(key),
                "brainId": identity(1),
                "sourceId": identity(2),
                "sourceType": 2,
                "type": 12,
                "isNotes": False,
                "location": identity(key) + ".svg",
                "name": None,
                "dataLength": len(drawing),
            }
        )
    payloads = {201: raw_note.encode(), 202: PNG, 205: drawing, 206: drawing}
    for attachment in attachments:
        key = int(attachment["id"][-12:])
        attachment["dataLength"] = len(payloads[key])
    graph["attachments"] = attachments
    write_json(graph_path, graph)
    manifest["scope"]["attachment_ids"] = [a["id"] for a in attachments]
    manifest["payloads"] = {}
    for key, payload in payloads.items():
        path = str(key) + ".bin"
        (root / path).write_bytes(payload)
        manifest["files"][path] = fingerprint(root / path)
        manifest["payloads"][identity(key)] = {"status": 200, "path": path}
    manifest["attachment_inventories"] = {identity(2): "home-attachments.json"}
    write_json(root / "home-attachments.json", attachments)
    manifest["files"]["home-attachments.json"] = fingerprint(
        root / "home-attachments.json"
    )
    manifest["attachment_metadata"] = {}
    for attachment in attachments:
        path = attachment["id"] + "-metadata.json"
        write_json(root / path, attachment)
        manifest["files"][path] = fingerprint(root / path)
        manifest["attachment_metadata"][attachment["id"]] = {
            "status": 200,
            "path": path,
        }
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["profile_version"] = "3"
    record["issues"] = []
    originals = record["original_evidence"][0]["records"]
    record["original_evidence"][0]["records"] = [
        row
        for row in originals
        if row["id"] not in {identity(k) for k in (201, 202, 203, 204)}
    ] + attachments
    record["asset_targets"] = []
    (vault / "Attachments").mkdir()
    for attachment in attachments:
        key = int(attachment["id"][-12:])
        relative = "Attachments/" + (
            "Notes.md" if key == 201 else attachment["location"]
        )
        (vault / relative).write_bytes(payloads[key])
        record["asset_targets"].append(
            {
                "asset_id": attachment["id"],
                "owner": identity(2),
                "role": "note_original" if key == 201 else "image",
                "availability": "present",
                "relative_path": relative,
                "original_name": attachment["location"],
                "display_name": None,
                "actual_length": len(payloads[key]),
                "actual_sha256": hashlib.sha256(payloads[key]).hexdigest(),
                "resource_link": relative if key == 206 else None,
                "retained_documents": [],
            }
        )
    names = {
        identity(2): "Home.md",
        identity(3): "Notes/Child.md",
        identity(4): "Categories/Type.md",
        identity(5): "Notes/Tag.md",
    }
    for target in record["item_targets"]:
        key = target["item_key"]
        provider = identity(4) if key == identity(3) else None
        target.update(
            relative_path=names[key],
            created=key != identity(5),
            documents=[],
            declared_appearance={
                "foreground_color": None,
                "background_color": None,
                "icon_asset_id": None,
            },
            icon_snapshot={
                "item_key": key,
                "explicit_icon_asset_id": None,
                "appearance_category_key": provider,
                "effective_icon_asset_id": None,
            }
            if key != identity(5)
            else None,
        )
        if key not in {identity(2), identity(5)}:
            note_path = vault / names[key]
            note_path.parent.mkdir(parents=True, exist_ok=True)
            category = ' "[[Categories/Type.md]]"' if provider else ""
            note_path.write_text(
                "---\nicon:\nappearance_category:"
                + category
                + "\n---\n\n# "
                + target["original_title"]
                + "\n\n",
                encoding="utf-8",
            )
    home = record["item_targets"][0]
    digest = hashlib.sha256(document_text.encode()).hexdigest()
    refs = []
    for key, phrase, label, source in (
        (
            205,
            "![Système](.data/md-images/"
            + identity(205)
            + '.svg#$width=50p$ "Stencil")',
            "Système",
            ".data/md-images/" + identity(205) + ".svg#$width=50p$",
        ),
        (
            205,
            "![Again](.data/md-images/" + identity(205) + ".svg)",
            "Again",
            ".data/md-images/" + identity(205) + ".svg",
        ),
        (
            202,
            "![PNG](.data/md-images/" + identity(202) + ".png)",
            "PNG",
            ".data/md-images/" + identity(202) + ".png",
        ),
    ):
        if phrase not in document_text:
            continue
        start = document_text.index(phrase)
        begin = document_text.index(source, start)
        end = begin + len(source)
        normalization = None
        if "#" in source:
            pos = begin + source.index("#")
            normalization = {
                "declaration": document_text[pos:end],
                "start": pos,
                "end": end,
                "document_digest": digest,
                "basis": "document.text/unicode_codepoints",
                "presentation": "responsive",
            }
        refs.append(
            {
                "start": start,
                "end": start + len(phrase),
                "kind": "image",
                "target": identity(key),
                "display_text": label,
                "expected_original": phrase,
                "document_digest": digest,
                "source_target": source,
                "destination_start": begin,
                "destination_end": end,
                "presentation_normalization": normalization,
                "table_cell": False,
            }
        )
    home["documents"] = [
        {
            "key": identity(201),
            "owner": identity(2),
            "original_asset_id": identity(201),
            "text_digest": digest,
            "owner_target": "Home.md",
            "original_copy_omitted": False,
            "references": refs,
            "text_adaptations": [],
            "evidence": ["attachment:" + identity(201)],
        }
    ]
    if raw_note != document_text:
        # A broad source-owned replay is a permitted alternative to atomic
        # segmentation. Exact before/after come from caller-owned literal pairs.
        home["documents"][0]["text_adaptations"] = [
            {
                "kind": "literal_text"
                if raw_note.startswith("<Value>")
                else "markdown_insert",
                "start": 0,
                "end": len(raw_note),
                "before": raw_note,
                "after": document_text,
                "adapted_start": 0,
                "adapted_end": len(document_text),
                "source_digest": hashlib.sha256(raw_note.encode()).hexdigest(),
                "source_basis": "scoped_source_text/unicode_codepoints",
                "adapted_basis": "document.text/unicode_codepoints",
            }
        ]
    if display_note is None:
        display_note = (
            "Préface Ω.\n"
            f'![Système](Attachments/{identity(205)}.svg "Stencil")\n'
            f"![Again](Attachments/{identity(205)}.svg)\n"
            f"![PNG](Attachments/{identity(202)}.png)\n"
        )
    (vault / "Home.md").write_text(
        "---\nicon:\nappearance_category:\n---\n\n# Home\n\n" + display_note + "\n"
        f"## Resources\n\n- [[Attachments/{identity(206)}.svg|{identity(206)}.svg]]\n",
        encoding="utf-8",
    )
    write_json(path, record)
    return baseline, vault


@pytest.mark.parametrize("key", [205, 206])
def test_qualified_independent_svg_has_image_role_and_exact_original(tmp_path, key):
    baseline, _ = svg_case(tmp_path)
    graph = baseline.json(baseline.data["graphs"][identity(2)])
    attachment = next(a for a in graph["attachments"] if a["id"] == identity(key))
    assert expected_asset(baseline, attachment, "3") == ("image", "present", DRAWING)


def test_every_svg_including_equal_byte_unreferenced_identity_is_preserved(tmp_path):
    baseline, vault = svg_case(tmp_path)
    audit = audit_baseline(baseline, profile_version="3")
    assert audit["attachments"] == 4
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4


def attachment(baseline, key=205):
    graph = baseline.json(baseline.data["graphs"][identity(2)])
    return next(a for a in graph["attachments"] if a["id"] == identity(key))


@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
@pytest.mark.parametrize(
    "damage",
    [
        "list",
        "metadata",
        "metadata-status",
        "owner-type",
        "owner-bool",
        "brain",
        "name",
        "filename",
    ],
)
def test_svg_authoritative_joins_and_declarations_refuse_independently(
    tmp_path, entry, damage
):
    baseline, vault = svg_case(tmp_path)
    root = baseline.manifest_path.parent
    row = attachment(baseline)
    if damage in {"list", "metadata"}:
        path = (
            baseline.data["attachment_inventories"][identity(2)]
            if damage == "list"
            else baseline.data["attachment_metadata"][identity(205)]["path"]
        )
        value = json.loads((root / path).read_bytes())
        selected = (
            next(a for a in value if a["id"] == identity(205))
            if damage == "list"
            else value
        )
        selected["dataLength"] += 1
        write_json(root / path, value)
    elif damage == "metadata-status":
        data = json.loads(baseline.manifest_path.read_bytes())
        data["attachment_metadata"][identity(205)]["status"] = 404
        write_json(baseline.manifest_path, data)
    else:
        field, value = {
            "owner-type": ("sourceType", 2.0),
            "owner-bool": ("sourceType", True),
            "brain": ("brainId", identity(9)),
            "name": ("name", ""),
            "filename": ("location", identity(205) + ".SVG"),
        }[damage]
        row[field] = value
        graph_path = root / baseline.data["graphs"][identity(2)]
        graph = json.loads(graph_path.read_bytes())
        graph["attachments"][2] = row
        write_json(graph_path, graph)
    baseline = reseal(baseline)
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(baseline, row, "3")
        elif entry == "baseline":
            audit_baseline(baseline, profile_version="3")
        else:
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "damage",
    [
        "body",
        "order",
        "alt",
        "title",
        "width",
        "target",
        "missing-resource",
        "fake-resource",
        "resource-in-code",
        "note-absent",
    ],
)
def test_svg_raw_note_placement_and_unreferenced_resource_are_actual_output_obligations(
    tmp_path, damage
):
    baseline, vault = svg_case(tmp_path)
    path = vault / "Home.md"
    text = path.read_text(encoding="utf-8")
    if damage == "body":
        text = text.replace("Préface Ω.", "Lost original text.")
    elif damage == "order":
        text = text.replace("![Système]", "![Again]", 1).replace(
            "![Again](Attachments/", "![Système](Attachments/", 1
        )
        # Swap the two complete SVG placements, retaining the same destinations.
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        first = next(i for i, line in enumerate(lines) if line.startswith("![Système]"))
        second = next(i for i, line in enumerate(lines) if line.startswith("![Again]"))
        lines[first], lines[second] = lines[second], lines[first]
        text = "".join(lines)
    elif damage == "alt":
        text = text.replace("Système", "System")
    elif damage == "title":
        text = text.replace(' "Stencil"', "")
    elif damage == "width":
        text = text.replace('.svg "Stencil"', '.svg#$width=50p$ "Stencil"')
    elif damage == "target":
        text = text.replace(identity(205), identity(206), 1)
    elif damage == "missing-resource":
        text = text[: text.index("## Resources")]
    elif damage == "fake-resource":
        text += "\n- [[Attachments/forged.svg|forged.svg]]\n"
    elif damage == "resource-in-code":
        text = text.replace("## Resources", "```\n## Resources") + "```\n"
    else:
        path.unlink()
    if damage != "note-absent":
        path.write_text(text, encoding="utf-8")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "damage",
    [
        "omitted",
        "digest",
        "owner",
        "original",
        "omitted-original",
        "span",
        "span-bytes",
        "source-target",
        "target",
        "label",
        "order",
        "drop",
        "width",
        "width-basis",
        "width-start",
        "destination",
    ],
)
def test_svg_record_documents_are_bound_to_original_unicode_coordinates(
    tmp_path, damage
):
    baseline, vault = svg_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    doc = record["item_targets"][0]["documents"][0]
    ref = doc["references"][0]
    if damage == "omitted":
        record["item_targets"][0]["documents"] = []
    elif damage == "digest":
        doc["text_digest"] = "0" * 64
    elif damage == "owner":
        doc["owner"] = identity(3)
    elif damage == "original":
        doc["original_asset_id"] = identity(202)
    elif damage == "omitted-original":
        doc["original_copy_omitted"] = True
    elif damage == "span":
        ref["start"] += 1
    elif damage == "span-bytes":
        ref["start"] = len(NOTE[: ref["start"]].encode())
    elif damage == "source-target":
        ref["source_target"] = ref["source_target"].split("#")[0]
    elif damage == "target":
        ref["target"] = identity(206)
    elif damage == "label":
        ref["display_text"] = "System"
    elif damage == "order":
        doc["references"].reverse()
    elif damage == "drop":
        doc["references"].pop()
    elif damage == "width":
        ref["presentation_normalization"] = None
    elif damage == "width-basis":
        ref["presentation_normalization"]["basis"] = "utf8-bytes"
    elif damage == "width-start":
        ref["presentation_normalization"]["start"] -= 1
    else:
        ref["destination_end"] -= 1
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


EMPTY = b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="12" viewBox="-2 -3 24 12"/>'

POSITIVE_DRAWINGS = [
    EMPTY,
    EMPTY.replace(b'width="24"', b'width="32768"'),
    EMPTY.replace(b'width="24"', b'width="+2.4e1"'),
    EMPTY.replace(b'width="24"', b'width=".00000000000000000000001"'),
    EMPTY.replace(
        b'width="24"',
        b'width="1e-999999999999999999999999999999999999999999999999999999999999"',
    ),
    EMPTY.replace(b'viewBox="-2 -3 24 12"', b'viewBox=" -1000000,+0.0, 1e6 , .1 "'),
    EMPTY.replace(b"/>", b"> <![CDATA[\t\r\n]]> </svg>"),
    EMPTY.replace(b"/>", b'><rect width="1000000" height=".1"/></svg>'),
    EMPTY.replace(
        b"/>",
        b'><rect width="1" height="1" x="-0e999999999999999999999999999999999999999999999999999999999999" fill="none" stroke="#aBc" stroke-width=".01"/></svg>',
    ),
    EMPTY.replace(b"/>", b'><line x1="0" y1="0" x2="0" y2="0" stroke="none"/></svg>'),
    EMPTY.replace(
        b"/>",
        b'><line x1="-1000000" y1="1E+6" x2="1" y2="2" stroke="#12AbCd" stroke-linecap="square"/></svg>',
    ),
    b"<?xml version='1.0' encoding='utf-8'?>\n" + EMPTY,
    b"<?xml version = '1.0' ?>\r\n" + EMPTY,
    EMPTY.replace(
        b"/>", b'><rect height="1" width="2" xmlns="http://www.w3.org/2000/svg"/></svg>'
    ),
    EMPTY.replace(b'width="24"', b'width="' + b"0" * 63 + b'1"'),
]

NEGATIVE_DRAWINGS = [
    b"",
    b"not XML",
    b"\xef\xbb\xbf" + EMPTY,
    EMPTY.decode().encode("utf-16"),
    EMPTY.decode().encode("utf-32"),
    b'<?xml version="1.1"?>' + EMPTY,
    b'<?xml version="1.0" standalone="no"?>' + EMPTY,
    b'<?xml version="1.0" standalone="yes"?>' + EMPTY,
    b'<?xml version="1.0" encoding="UTF-16"?>' + EMPTY,
    b"<?other inert?>" + EMPTY,
    EMPTY + b"<?other inert?>",
    b'<!DOCTYPE svg SYSTEM "https://example.invalid/no-fetch">' + EMPTY,
    b'<!DOCTYPE svg [<!ENTITY harmless " ">]>' + EMPTY,
    b"<!-- inert -->" + EMPTY,
    EMPTY.replace(b"/>", b"><!-- inert --></svg>"),
    EMPTY.replace(b"/>", b"> &#32; </svg>"),
    EMPTY.replace(b"/>", b"> &#x20; </svg>"),
    EMPTY.replace(b"/>", b"> &amp; </svg>"),
    EMPTY.replace(b"/>", b"> <![CDATA[x]]> </svg>"),
    EMPTY.replace(b"/>", b"> x </svg>"),
    EMPTY.replace(b"/>", b'><rect width="1" height="1">x</rect></svg>'),
    EMPTY.replace(b"/>", b'><rect width="1" height="1"/>x</svg>'),
    EMPTY.replace(b"http://www.w3.org/2000/svg", b"http://example.invalid/svg"),
    EMPTY.replace(b" width=", b' xmlns:unused="https://example.invalid/" width=', 1),
    EMPTY.replace(b"<svg xmlns=", b"<s:svg xmlns:s="),
    EMPTY.replace(b"/>", b'><rect xmlns="" width="1" height="1"/></svg>'),
    EMPTY.replace(b"/>", b'><svg width="1" height="1" viewBox="0 0 1 1"/></svg>'),
    EMPTY.replace(
        b"/>",
        b'><rect width="1" height="1"><line x1="0" y1="0" x2="1" y2="1" stroke="none"/></rect></svg>',
    ),
]
for _value in (
    "0",
    "-1",
    "32769",
    "1000001",
    "NaN",
    "Infinity",
    "1e999999999999999999999999999999999999999999999999999999999999",
    "24px",
    "1_0",
    "２",
    "1e",
    " 24",
    "24 ",
    "1" * 65,
):
    NEGATIVE_DRAWINGS.append(
        EMPTY.replace(b'width="24"', ('width="' + _value + '"').encode())
    )
for _value in (
    "0 0 0 1",
    "0 0 1 -1",
    ",0 0 1 1",
    "0 0 1 1,",
    "0,,0,1,1",
    "0, ,0,1,1",
    "0 0 1",
    "0 0 1 1 1",
    "0;0;1;1",
    "0\u00a00 1 1",
):
    NEGATIVE_DRAWINGS.append(
        EMPTY.replace(b'viewBox="-2 -3 24 12"', ('viewBox="' + _value + '"').encode())
    )
for _name in ("style", "href", "src", "onload", "filter", "font-family", "xml:space"):
    NEGATIVE_DRAWINGS.append(EMPTY.replace(b"/>", (" " + _name + '=""/>').encode()))
for _name in (
    "script",
    "foreignObject",
    "image",
    "style",
    "g",
    "animate",
    "filter",
    "text",
    "path",
):
    NEGATIVE_DRAWINGS.append(EMPTY.replace(b"/>", ("><" + _name + "/></svg>").encode()))
for _shape in (
    '<rect width="0" height="1"/>',
    '<rect width="1" height="-1"/>',
    '<rect width="1" height="1" stroke="none" stroke-width="0"/>',
    '<rect width="1" height="1" fill="None"/>',
    '<rect width="1" height="1" fill="red"/>',
    '<rect width="1" height="1" fill="url(#x)"/>',
    '<rect width="1" height="1" fill="#abcd"/>',
    '<rect width="1" height="1" x="calc(1)"/>',
    '<rect width="1" height="1" rx="0"/>',
    '<rect width="1"/>',
    '<rect width="1" width="1" height="1"/>',
    '<line x1="0" y1="0" x2="1" y2="1"/>',
    '<line x1="0" y1="0" x2="1" y2="1" stroke="none" stroke-linecap="Round"/>',
    '<line x1="0" y1="0" x2="1" y2="1" stroke="none" fill="none"/>',
):
    NEGATIVE_DRAWINGS.append(EMPTY.replace(b"/>", (">" + _shape + "</svg>").encode()))


@pytest.mark.parametrize("payload", POSITIVE_DRAWINGS)
def test_finite_svg_grammar_positive_spellings_are_not_narrowed(tmp_path, payload):
    baseline, _ = svg_case(tmp_path, payload)
    assert expected_asset(baseline, attachment(baseline), "3") == (
        "image",
        "present",
        payload,
    )


@pytest.mark.parametrize("payload", NEGATIVE_DRAWINGS)
def test_finite_svg_grammar_refuses_each_unsupported_lexical_or_structural_factor(
    tmp_path, payload
):
    baseline, _ = svg_case(tmp_path, payload)
    with pytest.raises(AssertionError):
        expected_asset(baseline, attachment(baseline), "3")


@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
@pytest.mark.parametrize("profile", ["1", "2", "unknown"])
def test_older_and_unknown_profiles_refuse_svg_at_every_public_entrypoint(
    tmp_path, entry, profile
):
    baseline, vault = svg_case(tmp_path)
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(baseline, attachment(baseline), profile)
        elif entry == "baseline":
            audit_baseline(baseline, profile_version=profile)
        else:
            check_api_vault(baseline, vault, profile_version=profile)


@pytest.mark.parametrize("kind", ["bytes", "elements"])
@pytest.mark.parametrize("outside", [False, True])
def test_svg_exact_size_and_root_inclusive_element_bounds(tmp_path, kind, outside):
    if kind == "bytes":
        payload = EMPTY.replace(
            b"/>", b">" + b" " * (1048576 - len(EMPTY) - 5 + outside) + b"</svg>"
        )
        assert len(payload) == 1048576 + outside
    else:
        payload = EMPTY.replace(
            b"/>", b">" + b'<rect width="1" height="1"/>' * (4095 + outside) + b"</svg>"
        )
    baseline, _ = svg_case(tmp_path, payload)
    if outside:
        with pytest.raises(AssertionError):
            expected_asset(baseline, attachment(baseline), "3")
    else:
        assert expected_asset(baseline, attachment(baseline), "3")[2] == payload


@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
@pytest.mark.parametrize("key", [205, 206])
def test_invalid_unreferenced_and_referenced_svg_are_never_sampled(
    tmp_path, entry, key
):
    baseline, vault = svg_case(tmp_path)
    payload = (
        baseline.manifest_path.parent / baseline.data["payloads"][identity(key)]["path"]
    )
    payload.write_bytes(b"<svg/>")
    baseline = reseal(baseline)
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(baseline, attachment(baseline, key), "3")
        elif entry == "baseline":
            audit_baseline(baseline, profile_version="3")
        else:
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("key", [205, 206])
@pytest.mark.parametrize(
    "damage", ["omission", "bytes", "filename", "owner", "role", "digest", "alias"]
)
def test_each_equal_byte_svg_identity_has_independent_output_obligations(
    tmp_path, key, damage
):
    baseline, vault = svg_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == identity(key))
    if damage == "omission":
        record["asset_targets"].remove(asset)
    elif damage == "bytes":
        (vault / asset["relative_path"]).write_bytes(b"PNG raster replacement")
    elif damage == "filename":
        old = vault / asset["relative_path"]
        asset["relative_path"] = "Attachments/renamed.svg"
        old.rename(vault / asset["relative_path"])
    elif damage == "owner":
        asset["owner"] = identity(3)
    elif damage == "role":
        asset["role"] = "file"
    elif damage == "digest":
        asset["actual_sha256"] = "0" * 64
    else:
        asset["relative_path"] = (
            "Attachments/" + identity(206 if key == 205 else 205) + ".svg"
        )
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


def test_nullable_graph_attachment_inventory_uses_bound_authoritative_owner_list(
    tmp_path,
):
    baseline, vault = svg_case(tmp_path)
    path = baseline.manifest_path.parent / baseline.data["graphs"][identity(2)]
    graph = json.loads(path.read_bytes())
    graph["attachments"] = None
    write_json(path, graph)
    assert (
        check_api_vault(reseal(baseline), vault, profile_version="3")["payloads"] == 4
    )


@pytest.mark.parametrize("damage", ["equal-length", "rehashed-untrusted-manifest"])
def test_pinned_svg_mutation_cannot_supply_its_own_new_trust(tmp_path, damage):
    baseline, _ = svg_case(tmp_path)
    root = baseline.manifest_path.parent
    path = root / baseline.data["payloads"][identity(206)]["path"]
    path.write_bytes(DRAWING.replace(b"#aBc", b"#dEf"))
    if damage == "rehashed-untrusted-manifest":
        data = json.loads(baseline.manifest_path.read_bytes())
        data["files"][path.name] = fingerprint(path)
        write_json(baseline.manifest_path, data)
    with pytest.raises(AssertionError, match="baseline .* changed"):
        audit_baseline(baseline, profile_version="3")


def test_fresh_valid_changed_svg_is_eligible_but_different_from_original_baseline(
    tmp_path,
):
    baseline, vault = svg_case(tmp_path)
    old_pin = baseline.fingerprint
    root = baseline.manifest_path.parent
    path = root / baseline.data["payloads"][identity(206)]["path"]
    changed = DRAWING.replace(b"#aBc", b"#dEf")
    path.write_bytes(changed)
    fresh = reseal(baseline)
    assert fresh.fingerprint != old_pin
    assert audit_baseline(fresh, profile_version="3")["payloads"] == 4
    assert expected_asset(fresh, attachment(fresh, 206), "3")[2] == changed
    with pytest.raises(AssertionError, match="required payload bytes"):
        check_api_vault(fresh, vault, profile_version="3")


# Independently literal admitted formatting/EOL contexts. The existing image
# phrases retain their raw declarations; adapted document coordinates precede
# final rendering and use Unicode codepoints, including preserved CR/CRLF.
FORMAT_PREFIXES = [
    (
        "raw-crlf",
        "Préface formatée.\r\n",
        "Préface formatée.\r\n",
        "Préface formatée.\n",
    ),
    ("raw-cr", "Préface formatée.\r", "Préface formatée.\r", "Préface formatée.\n"),
    ("literal", "<Value>\r\n", "\\<Value>\r\n", "\\<Value>\n"),
    (
        "callout",
        "> [!tip|icon:😂]\r\n> Authored body.\r\n\r\n",
        "> [!tip] 😂 Tip\r\n> Authored body.\r\n\r\n",
        "> [!tip] 😂 Tip\n> Authored body.\n\n",
    ),
    (
        "toc",
        "[/toc/]\r\n\r\n# Part\r\n",
        "- [Part](#^brz-toc-heading-1)\r\n\r\n# Part ^brz-toc-heading-1\r\n",
        "- [Part](#^brz-toc-heading-1)\n\n# Part ^brz-toc-heading-1\n",
    ),
    (
        "protected",
        "`<Value> [/toc/]`\r\n",
        "`<Value> [/toc/]`\r\n",
        "`<Value> [/toc/]`\n",
    ),
]


@pytest.mark.parametrize(
    "label,raw_prefix,document_prefix,display_prefix", FORMAT_PREFIXES
)
@pytest.mark.parametrize(
    "damage", [None, "metadata-eol", "image-offset", "authored-span"]
)
def test_svg_note_formatting_metadata_and_display_keep_distinct_eol_bases(
    tmp_path, label, raw_prefix, document_prefix, display_prefix, damage
):
    raw = raw_prefix + NOTE
    adapted = document_prefix + NOTE
    rendered = (
        display_prefix
        + "Préface Ω.\n"
        + f'![Système](Attachments/{identity(205)}.svg "Stencil")\n![Again](Attachments/{identity(205)}.svg)\n![PNG](Attachments/{identity(202)}.png)\n'
    )
    baseline, vault = svg_case(
        tmp_path, raw_note=raw, document_text=adapted, display_note=rendered
    )
    if damage == "metadata-eol":
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        doc = record["item_targets"][0]["documents"][0]
        doc["text_digest"] = hashlib.sha256(
            adapted.replace("\r\n", "\n").replace("\r", "\n").encode()
        ).hexdigest()
        write_json(path, record)
    elif damage == "image-offset":
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        record["item_targets"][0]["documents"][0]["references"][0]["start"] -= 1
        write_json(path, record)
    elif damage == "authored-span":
        path = vault / "Home.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                display_prefix, "Lost formatted span.\n", 1
            ),
            encoding="utf-8",
        )
    if damage:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4


@pytest.mark.parametrize(
    "damage",
    [
        "entire-note-fence",
        "entire-note-comment",
        "extra-embed",
        "extra-html-image",
        "resource-heading",
    ],
)
def test_svg_actual_generated_regions_cannot_be_hidden_or_forged(tmp_path, damage):
    baseline, vault = svg_case(tmp_path)
    path = vault / "Home.md"
    body = path.read_text(encoding="utf-8")
    if damage == "entire-note-fence":
        body = "```md\n" + body + "```\n"
    elif damage == "entire-note-comment":
        body = "<!--\n" + body + "-->\n"
    elif damage == "extra-embed":
        body += f"\n![Forged](Attachments/{identity(206)}.svg)\n"
    elif damage == "extra-html-image":
        body += f'\n<img src="Attachments/{identity(206)}.svg">\n'
    else:
        body = body.replace("## Resources", "## Forged")
    path.write_text(body, encoding="utf-8")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("field", ["width", "height", "viewBox"])
def test_svg_every_root_attribute_is_required(tmp_path, field):
    pair = {
        "width": b' width="24"',
        "height": b' height="12"',
        "viewBox": b' viewBox="-2 -3 24 12"',
    }[field]
    baseline, _ = svg_case(tmp_path, EMPTY.replace(pair, b""))
    with pytest.raises(AssertionError):
        expected_asset(baseline, attachment(baseline), "3")


@pytest.mark.parametrize("field", ["x1", "y1", "x2", "y2", "stroke"])
def test_svg_every_line_attribute_is_required(tmp_path, field):
    shape = '<line x1="0" y1="0" x2="1" y2="1" stroke="none"/>'
    value = "none" if field == "stroke" else "0" if field in {"x1", "y1"} else "1"
    payload = EMPTY.replace(
        b"/>",
        (">" + shape.replace(" " + field + '="' + value + '"', "") + "</svg>").encode(),
    )
    baseline, _ = svg_case(tmp_path, payload)
    with pytest.raises(AssertionError):
        expected_asset(baseline, attachment(baseline), "3")


@pytest.mark.parametrize("cap", ["butt", "round", "square"])
def test_svg_all_finite_caps_and_none_paint_keep_degenerate_line(tmp_path, cap):
    shape = f'<line x1="0" y1="0" x2="0" y2="0" stroke="none" stroke-linecap="{cap}"/>'
    payload = EMPTY.replace(b"/>", (">" + shape + "</svg>").encode())
    baseline, _ = svg_case(tmp_path, payload)
    assert expected_asset(baseline, attachment(baseline), "3")[2] == payload


@pytest.mark.parametrize(
    "metadata",
    [
        "list-missing",
        "list-null",
        "list-duplicate",
        "metadata-missing",
        "status-float",
        "metadata-scalar-conflict",
    ],
)
@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
def test_svg_required_independent_observation_shape_and_type_agreement(
    tmp_path, metadata, entry
):
    baseline, vault = svg_case(tmp_path)
    root = baseline.manifest_path.parent
    data = json.loads(baseline.manifest_path.read_bytes())
    if metadata == "list-missing":
        data["attachment_inventories"] = {}
    elif metadata in {"list-null", "list-duplicate"}:
        path = root / data["attachment_inventories"][identity(2)]
        rows = json.loads(path.read_bytes())
        write_json(path, None if metadata == "list-null" else rows + [rows[2]])
    elif metadata == "metadata-missing":
        data["attachment_metadata"].pop(identity(205))
    elif metadata == "status-float":
        data["attachment_metadata"][identity(205)]["status"] = 200.0
    else:
        path = root / data["attachment_metadata"][identity(205)]["path"]
        row = json.loads(path.read_bytes())
        row["sourceType"] = 2.0
        write_json(path, row)
    write_json(baseline.manifest_path, data)
    baseline = reseal(baseline)
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(baseline, attachment(baseline), "3")
        elif entry == "baseline":
            audit_baseline(baseline, profile_version="3")
        else:
            check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("entry", ["asset", "baseline", "vault"])
def test_public_checker_direct_defaults_do_not_silently_admit_svg(tmp_path, entry):
    baseline, vault = svg_case(tmp_path)
    with pytest.raises(AssertionError):
        if entry == "asset":
            expected_asset(baseline, attachment(baseline))
        elif entry == "baseline":
            audit_baseline(baseline)
        else:
            check_api_vault(baseline, vault)


def test_fresh_distinct_equal_byte_svg_identity_is_new_source_not_intrinsic_corruption(
    tmp_path,
):
    baseline, vault = svg_case(tmp_path)
    root = baseline.manifest_path.parent
    old_pin = baseline.fingerprint
    old, new = identity(206), identity(207)
    for path in list(root.glob("*.json")):
        # Synthetic new capture only. The original baseline pin is kept distinct;
        # this cannot be used to revise an accepted private-source expectation.
        text = path.read_text(encoding="utf-8").replace(old, new)
        destination = path.with_name(path.name.replace(old, new))
        destination.write_text(text, encoding="utf-8")
    fresh = reseal(baseline)
    assert fresh.fingerprint != old_pin
    assert audit_baseline(fresh, profile_version="3")["attachments"] == 4
    assert expected_asset(fresh, attachment(fresh, 207), "3")[2] == DRAWING
    with pytest.raises(AssertionError):
        check_api_vault(fresh, vault, profile_version="3")


@pytest.mark.parametrize(
    "bad",
    ["#$width=0p$", "#$width=101p$", "?download=1", "#unknown", "#$width=50p$extra"],
)
def test_svg_does_not_widen_inherited_owned_image_reference_grammar(tmp_path, bad):
    baseline, _ = svg_case(tmp_path)
    path = (
        baseline.manifest_path.parent / baseline.data["payloads"][identity(201)]["path"]
    )
    path.write_bytes(NOTE.replace("#$width=50p$", bad).encode())
    with pytest.raises(AssertionError):
        audit_baseline(reseal(baseline), profile_version="3")


def test_svg_source_image_reference_requires_its_actual_owner_even_for_equal_bytes(
    tmp_path,
):
    baseline, _ = svg_case(tmp_path)
    root = baseline.manifest_path.parent
    data = json.loads(baseline.manifest_path.read_bytes())
    home_path = root / data["graphs"][identity(2)]
    child_path = root / data["graphs"][identity(3)]
    home, child = (
        json.loads(home_path.read_bytes()),
        json.loads(child_path.read_bytes()),
    )
    row = home["attachments"].pop(2)
    row["sourceId"] = identity(3)
    child["attachments"] = [row]
    write_json(home_path, home)
    write_json(child_path, child)
    write_json(root / data["attachment_inventories"][identity(2)], home["attachments"])
    data["attachment_inventories"][identity(3)] = "child-attachments.json"
    write_json(root / "child-attachments.json", [row])
    data["files"]["child-attachments.json"] = fingerprint(
        root / "child-attachments.json"
    )
    write_json(root / data["attachment_metadata"][identity(205)]["path"], row)
    write_json(baseline.manifest_path, data)
    baseline = reseal(baseline)
    assert expected_asset(baseline, row, "3") == ("image", "present", DRAWING)
    with pytest.raises(AssertionError, match="inline image binding"):
        audit_baseline(baseline, profile_version="3")


@pytest.mark.parametrize("damage", [None, "table-cell", "cell-target", "code-pipe"])
def test_svg_native_table_image_spans_and_code_pipes_are_independently_source_bound(
    tmp_path, damage
):
    phrases = NOTE.splitlines()[1:]
    raw = (
        'Préface Ω.\n|First|Again|PNG|Code|:(table="column-widths:-1,0,84,84,84;justification:default"):\n|'
        + "|".join(phrases)
        + "|`x|y`|\n"
    )
    adapted = (
        "Préface Ω.\n|First|Again|PNG|Code|\n|---|---|---|---|\n|"
        + "|".join(phrases)
        + "|<code>x&#124;y</code>|\n"
    )
    displayed = (
        "Préface Ω.\n|First|Again|PNG|Code|\n|---|---|---|---|\n|"
        + f'![Système](Attachments/{identity(205)}.svg "Stencil")|![Again](Attachments/{identity(205)}.svg)|![PNG](Attachments/{identity(202)}.png)|<code>x&#124;y</code>|\n'
    )
    baseline, vault = svg_case(
        tmp_path, raw_note=raw, document_text=adapted, display_note=displayed
    )
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    for ref in record["item_targets"][0]["documents"][0]["references"]:
        ref["table_cell"] = True
    if damage == "table-cell":
        record["item_targets"][0]["documents"][0]["references"][0]["table_cell"] = False
    write_json(path, record)
    if damage in {"cell-target", "code-pipe"}:
        note = vault / "Home.md"
        text = note.read_text(encoding="utf-8")
        text = (
            text.replace(identity(205), identity(206), 1)
            if damage == "cell-target"
            else text.replace("x&#124;y", "xy")
        )
        note.write_text(text, encoding="utf-8")
    if damage:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4


@pytest.mark.parametrize("case", ["plain", "composed"])
def test_qualified_svg_source_factory_reproduces_every_body_and_route(case):
    packet = svg_source_packet(case)
    assert len(packet["files"]) == 41
    assert {
        name: {"length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for name, raw in packet["files"].items()
    } == QUALIFIED_SOURCE_BODIES[case]
    assert {
        "length": len(packet["ledger"]),
        "sha256": hashlib.sha256(packet["ledger"]).hexdigest(),
    } == QUALIFIED_SOURCE_ORIGINS[case]["endpoint_ledger"]
    assert len(json.loads(packet["ledger"])["routes"]) == 40
    assert packet["files"]["payloads/" + identity(205) + ".bin"] == DRAWING
    assert packet["files"]["payloads/" + identity(206) + ".bin"] == DRAWING


@pytest.mark.parametrize("case", ["plain", "composed"])
def test_qualified_svg_source_factory_has_separate_api_baseline_container(
    tmp_path, case
):
    baseline = svg_baseline(tmp_path / "baseline", case)
    assert baseline.data["schema"] == "brz2obsidian.api-acceptance/1"
    assert baseline.fingerprint != QUALIFIED_SOURCE_ORIGINS[case]["bundle_pin"]
    assert (
        baseline.fingerprint
        != QUALIFIED_SOURCE_ORIGINS[case]["bundle_manifest"]["sha256"]
    )
    assert audit_baseline(baseline, profile_version="3")["payloads"] == 4
    assert not (tmp_path / "vault").exists()


# Fixed source-only fingerprints from separately qualified raw packets; all
# literal DTO/body inputs below are independently authored, never output-derived.
COMPOSED_NOTE = b'Pr\xc3\xa9face \xce\xa9.\r\n<Enter>\r\n\r\n[/toc/]\r\n\r\n# Dessin ^drawing-source\r\n\r\n|Thought|Image|:(table="column-widths:-1,0,84;justification:default"):\r\n|[Child](brain://AAAAAAAAAECAAAAAAAAAAw/Child)|![Syst\xc3\xa8me](.data/md-images/00000000-0000-4000-8000-000000000205.svg#$width=50p$ "Stencil")|\r\n\r\n> [!tip|icon:\xf0\x9f\x98\x82]\r\n> Authored caf\xc3\xa9.\r\n\r\n![Again](.data/md-images/00000000-0000-4000-8000-000000000205.svg)\r\n![PNG](.data/md-images/00000000-0000-4000-8000-000000000202.png)\r\n'
QUALIFIED_SOURCE_BODIES = {
    "plain": {
        "payloads/00000000-0000-4000-8000-000000000201.bin": {
            "length": 237,
            "sha256": "f9205887c440ba1ed0e172672f0594a4854cb901ebef73a8e698bfad0022ed99",
        },
        "payloads/00000000-0000-4000-8000-000000000202.bin": {
            "length": 120,
            "sha256": "4ba8d4fd5ab42544feeff22d50e84412502433cc95952fd1df9a5293588ddbea",
        },
        "payloads/00000000-0000-4000-8000-000000000205.bin": {
            "length": 327,
            "sha256": "f3d00c956167018cd21ba848db5b5de304ac8356b16dbba15342cd8f67d235a2",
        },
        "payloads/00000000-0000-4000-8000-000000000206.bin": {
            "length": 327,
            "sha256": "f3d00c956167018cd21ba848db5b5de304ac8356b16dbba15342cd8f67d235a2",
        },
        "responses/attachment-metadata/00000000-0000-4000-8000-000000000201.json": {
            "length": 289,
            "sha256": "bbe3c921bd53651b593c450f3dcfc50d028caeed29e13279d64bbf8e2a56a941",
        },
        "responses/attachment-metadata/00000000-0000-4000-8000-000000000202.json": {
            "length": 323,
            "sha256": "8e29462ff722382a4f6aeea3bcf712fa6c1171cd61609ea22b7117805defd25c",
        },
        "responses/attachment-metadata/00000000-0000-4000-8000-000000000205.json": {
            "length": 323,
            "sha256": "eee1b358d964c781db5a701b2be186fa9b005f03edbf1c990a1adbb12794d210",
        },
        "responses/attachment-metadata/00000000-0000-4000-8000-000000000206.json": {
            "length": 323,
            "sha256": "62c2679ee803f30475d77b5cde79402e897381a798327e9e742b9ac1532f0198",
        },
        "responses/brain.json": {
            "length": 133,
            "sha256": "4b79aba3e8669b00d4946795bcd4ffa67064a2e102cd2b8dcbc7ff0f85c33047",
        },
        "responses/brains.json": {
            "length": 147,
            "sha256": "f83b3d51c7b2013766e989679c5f8299e5b2570362a8f34531ee70b4703c1f11",
        },
        "responses/graphs/00000000-0000-4000-8000-000000000002.json": {
            "length": 4546,
            "sha256": "e8b534062a8e443b5dd8bd63acf69a12f9d4ea3c42383ed40989740cd117d3ac",
        },
        "responses/graphs/00000000-0000-4000-8000-000000000003.json": {
            "length": 4946,
            "sha256": "3d9ac24810247bce455baf9252a854d2f12cc11eaa10c4f43b07029d9a44a025",
        },
        "responses/graphs/00000000-0000-4000-8000-000000000004.json": {
            "length": 1574,
            "sha256": "6bc2d19fed577c667dc7a7831c112689d4fb73310c2d0212497a891777fc2652",
        },
        "responses/graphs/00000000-0000-4000-8000-000000000005.json": {
            "length": 1573,
            "sha256": "6f8948b5b46e627cb238aafa5351a61117ab4742bd16f95db466d3563bac9b3c",
        },
        "responses/link-attachments/00000000-0000-4000-8000-000000000101.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/link-attachments/00000000-0000-4000-8000-000000000102.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/link-attachments/00000000-0000-4000-8000-000000000103.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/link-attachments/00000000-0000-4000-8000-000000000104.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/link-attachments/00000000-0000-4000-8000-000000000105.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/links/00000000-0000-4000-8000-000000000101.json": {
            "length": 452,
            "sha256": "2c168131a1279da89452ca76fa6fa6a6867a51c11a7762e2b238c9ca6ae85552",
        },
        "responses/links/00000000-0000-4000-8000-000000000102.json": {
            "length": 451,
            "sha256": "1f285951abab64321f90d8ddf43a7fdc520eca6aae7e37b0dda003b7c376da78",
        },
        "responses/links/00000000-0000-4000-8000-000000000103.json": {
            "length": 451,
            "sha256": "8c896c43fc044cdee478768cc96b67e546965596f1667e5c9fcadeb77103f968",
        },
        "responses/links/00000000-0000-4000-8000-000000000104.json": {
            "length": 452,
            "sha256": "46656c1db5f114a9f49bfb67f8dd1db7b52c11fec3b19d71437b3a0204828a42",
        },
        "responses/links/00000000-0000-4000-8000-000000000105.json": {
            "length": 452,
            "sha256": "ad41332d9b736405a9fd68b065048645a129fcfb46d7d611ce028716c04d774b",
        },
        "responses/no-notes/00000000-0000-4000-8000-000000000003.json": {
            "length": 228,
            "sha256": "c2cbbe85baa46276a2492402f97818e336f84ac39a1e710e91f1446666f578c3",
        },
        "responses/no-notes/00000000-0000-4000-8000-000000000004.json": {
            "length": 228,
            "sha256": "0fee6d7ff1efbcda5528144514a4e894a321c1f0be3ecd7988aec37760e2381b",
        },
        "responses/no-notes/00000000-0000-4000-8000-000000000005.json": {
            "length": 228,
            "sha256": "2dd3fc117a471195bc16d7eb4437765e16163ae32325c12131beb6d3c17b0e92",
        },
        "responses/owner-attachments/00000000-0000-4000-8000-000000000002.json": {
            "length": 1361,
            "sha256": "0a02ebd150d992ff516cdceba35acb97bd60c2662f25b4bf7aa1dddc67df7184",
        },
        "responses/owner-attachments/00000000-0000-4000-8000-000000000003.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/owner-attachments/00000000-0000-4000-8000-000000000004.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/owner-attachments/00000000-0000-4000-8000-000000000005.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/pins.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/search.json": {
            "length": 549,
            "sha256": "91e307b3814c5072bb99c2ca65af0553015cbbc6580d2ee99d1e7896a56af116",
        },
        "responses/statistics-end.json": {
            "length": 147,
            "sha256": "bc8bfd1e185f9462e71b1f07a6b0dd5e5e3e8f073953e40511ce71b54f77ff24",
        },
        "responses/statistics-start.json": {
            "length": 147,
            "sha256": "bc8bfd1e185f9462e71b1f07a6b0dd5e5e3e8f073953e40511ce71b54f77ff24",
        },
        "responses/tags.json": {
            "length": 419,
            "sha256": "195d4e25f99013ab6be8c0dddfd678b3437fe756c3fef9670530c6bdb2ccd9cb",
        },
        "responses/thoughts/00000000-0000-4000-8000-000000000002.json": {
            "length": 386,
            "sha256": "f3eb3e379abe1ce99c8f1c33f8e0937327d7d95a8bc4b6231b15b374d3e483c8",
        },
        "responses/thoughts/00000000-0000-4000-8000-000000000003.json": {
            "length": 421,
            "sha256": "4f85a128920fbfbab085e8bed79563773491115f03eea7750880afa2293df58e",
        },
        "responses/thoughts/00000000-0000-4000-8000-000000000004.json": {
            "length": 386,
            "sha256": "e57a8a8dbffa1e4178040e07cbba8c6fc67b368131d5d6329a44f861241f0feb",
        },
        "responses/thoughts/00000000-0000-4000-8000-000000000005.json": {
            "length": 385,
            "sha256": "06c62106e3a1e27eac822967115cff13f719fd48fcb398fcb0176838ebc50cbd",
        },
        "responses/types.json": {
            "length": 420,
            "sha256": "73efe5975daba4deec33139d2a8d123131b3a1edf50b25ae180a6fd0c2e36959",
        },
    },
    "composed": {
        "payloads/00000000-0000-4000-8000-000000000201.bin": {
            "length": 454,
            "sha256": "af64fee9aff4f4b753eabda0834afeb8bf281beacb0b208c94c3006f0c7ddd8d",
        },
        "payloads/00000000-0000-4000-8000-000000000202.bin": {
            "length": 120,
            "sha256": "4ba8d4fd5ab42544feeff22d50e84412502433cc95952fd1df9a5293588ddbea",
        },
        "payloads/00000000-0000-4000-8000-000000000205.bin": {
            "length": 327,
            "sha256": "f3d00c956167018cd21ba848db5b5de304ac8356b16dbba15342cd8f67d235a2",
        },
        "payloads/00000000-0000-4000-8000-000000000206.bin": {
            "length": 327,
            "sha256": "f3d00c956167018cd21ba848db5b5de304ac8356b16dbba15342cd8f67d235a2",
        },
        "responses/attachment-metadata/00000000-0000-4000-8000-000000000201.json": {
            "length": 289,
            "sha256": "a694d92a6f7ad498155a2ef9b0d49765f4e5c62409aa4332970799798bcb4fc1",
        },
        "responses/attachment-metadata/00000000-0000-4000-8000-000000000202.json": {
            "length": 323,
            "sha256": "8e29462ff722382a4f6aeea3bcf712fa6c1171cd61609ea22b7117805defd25c",
        },
        "responses/attachment-metadata/00000000-0000-4000-8000-000000000205.json": {
            "length": 323,
            "sha256": "eee1b358d964c781db5a701b2be186fa9b005f03edbf1c990a1adbb12794d210",
        },
        "responses/attachment-metadata/00000000-0000-4000-8000-000000000206.json": {
            "length": 323,
            "sha256": "62c2679ee803f30475d77b5cde79402e897381a798327e9e742b9ac1532f0198",
        },
        "responses/brain.json": {
            "length": 133,
            "sha256": "4b79aba3e8669b00d4946795bcd4ffa67064a2e102cd2b8dcbc7ff0f85c33047",
        },
        "responses/brains.json": {
            "length": 147,
            "sha256": "f83b3d51c7b2013766e989679c5f8299e5b2570362a8f34531ee70b4703c1f11",
        },
        "responses/graphs/00000000-0000-4000-8000-000000000002.json": {
            "length": 4546,
            "sha256": "b7d6403a49a5deaaa556ad2e1c83f7fbb091925f724594a338e55acbde34a8ee",
        },
        "responses/graphs/00000000-0000-4000-8000-000000000003.json": {
            "length": 4946,
            "sha256": "3d9ac24810247bce455baf9252a854d2f12cc11eaa10c4f43b07029d9a44a025",
        },
        "responses/graphs/00000000-0000-4000-8000-000000000004.json": {
            "length": 1574,
            "sha256": "6bc2d19fed577c667dc7a7831c112689d4fb73310c2d0212497a891777fc2652",
        },
        "responses/graphs/00000000-0000-4000-8000-000000000005.json": {
            "length": 1573,
            "sha256": "6f8948b5b46e627cb238aafa5351a61117ab4742bd16f95db466d3563bac9b3c",
        },
        "responses/link-attachments/00000000-0000-4000-8000-000000000101.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/link-attachments/00000000-0000-4000-8000-000000000102.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/link-attachments/00000000-0000-4000-8000-000000000103.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/link-attachments/00000000-0000-4000-8000-000000000104.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/link-attachments/00000000-0000-4000-8000-000000000105.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/links/00000000-0000-4000-8000-000000000101.json": {
            "length": 452,
            "sha256": "2c168131a1279da89452ca76fa6fa6a6867a51c11a7762e2b238c9ca6ae85552",
        },
        "responses/links/00000000-0000-4000-8000-000000000102.json": {
            "length": 451,
            "sha256": "1f285951abab64321f90d8ddf43a7fdc520eca6aae7e37b0dda003b7c376da78",
        },
        "responses/links/00000000-0000-4000-8000-000000000103.json": {
            "length": 451,
            "sha256": "8c896c43fc044cdee478768cc96b67e546965596f1667e5c9fcadeb77103f968",
        },
        "responses/links/00000000-0000-4000-8000-000000000104.json": {
            "length": 452,
            "sha256": "46656c1db5f114a9f49bfb67f8dd1db7b52c11fec3b19d71437b3a0204828a42",
        },
        "responses/links/00000000-0000-4000-8000-000000000105.json": {
            "length": 452,
            "sha256": "ad41332d9b736405a9fd68b065048645a129fcfb46d7d611ce028716c04d774b",
        },
        "responses/no-notes/00000000-0000-4000-8000-000000000003.json": {
            "length": 228,
            "sha256": "c2cbbe85baa46276a2492402f97818e336f84ac39a1e710e91f1446666f578c3",
        },
        "responses/no-notes/00000000-0000-4000-8000-000000000004.json": {
            "length": 228,
            "sha256": "0fee6d7ff1efbcda5528144514a4e894a321c1f0be3ecd7988aec37760e2381b",
        },
        "responses/no-notes/00000000-0000-4000-8000-000000000005.json": {
            "length": 228,
            "sha256": "2dd3fc117a471195bc16d7eb4437765e16163ae32325c12131beb6d3c17b0e92",
        },
        "responses/owner-attachments/00000000-0000-4000-8000-000000000002.json": {
            "length": 1361,
            "sha256": "303cf43db581bd39d1ce827d19b5c841ed8f35188aa37f5cd2cfe1ad5fc08e21",
        },
        "responses/owner-attachments/00000000-0000-4000-8000-000000000003.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/owner-attachments/00000000-0000-4000-8000-000000000004.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/owner-attachments/00000000-0000-4000-8000-000000000005.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/pins.json": {
            "length": 3,
            "sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        },
        "responses/search.json": {
            "length": 549,
            "sha256": "91e307b3814c5072bb99c2ca65af0553015cbbc6580d2ee99d1e7896a56af116",
        },
        "responses/statistics-end.json": {
            "length": 147,
            "sha256": "bc8bfd1e185f9462e71b1f07a6b0dd5e5e3e8f073953e40511ce71b54f77ff24",
        },
        "responses/statistics-start.json": {
            "length": 147,
            "sha256": "bc8bfd1e185f9462e71b1f07a6b0dd5e5e3e8f073953e40511ce71b54f77ff24",
        },
        "responses/tags.json": {
            "length": 419,
            "sha256": "195d4e25f99013ab6be8c0dddfd678b3437fe756c3fef9670530c6bdb2ccd9cb",
        },
        "responses/thoughts/00000000-0000-4000-8000-000000000002.json": {
            "length": 386,
            "sha256": "f3eb3e379abe1ce99c8f1c33f8e0937327d7d95a8bc4b6231b15b374d3e483c8",
        },
        "responses/thoughts/00000000-0000-4000-8000-000000000003.json": {
            "length": 421,
            "sha256": "4f85a128920fbfbab085e8bed79563773491115f03eea7750880afa2293df58e",
        },
        "responses/thoughts/00000000-0000-4000-8000-000000000004.json": {
            "length": 386,
            "sha256": "e57a8a8dbffa1e4178040e07cbba8c6fc67b368131d5d6329a44f861241f0feb",
        },
        "responses/thoughts/00000000-0000-4000-8000-000000000005.json": {
            "length": 385,
            "sha256": "06c62106e3a1e27eac822967115cff13f719fd48fcb398fcb0176838ebc50cbd",
        },
        "responses/types.json": {
            "length": 420,
            "sha256": "73efe5975daba4deec33139d2a8d123131b3a1edf50b25ae180a6fd0c2e36959",
        },
    },
}
QUALIFIED_SOURCE_ORIGINS = {
    "plain": {
        "bundle_pin": "6f28bf9893487996b2cbdd89310d977808c352209ba02e24095efc42ef10d0fd",
        "bundle_manifest": {
            "length": 8348,
            "sha256": "626fbaa942c8e22a1ccd2df58ef000a06600af8dc123b83cc645180c2b27fb30",
        },
        "endpoint_ledger": {
            "length": 19060,
            "sha256": "07713621ee340aea023773b8f34b01496424644cfaa2162322dc637e493ba643",
        },
        "original_svg_pin": "c153bac8f982d7db01f9c29a2579cc062f6026f06cb51accdbe09c3b100faed2",
    },
    "composed": {
        "bundle_pin": "94f0f033603e604102524790345b67894f6b82a037a00424f47c647c5786cc4e",
        "bundle_manifest": {
            "length": 8941,
            "sha256": "abfee5616633f8179d97f89a96bc5cf4601dfe3974e2f66ca9ec80a05ac0bdc8",
        },
        "endpoint_ledger": {
            "length": 19060,
            "sha256": "708f8f46bf2581b26267b6625eb1f9acf70da85f3a02ef98562a28669e6d1e2b",
        },
        "original_svg_pin": "c153bac8f982d7db01f9c29a2579cc062f6026f06cb51accdbe09c3b100faed2",
    },
}
SOURCE_PACKET_PROTOCOL = {
    "schema": "independent.inert-local-api-response-packet/1",
    "method": "GET",
    "routes": [],
    "query_policy": "One complete response array per fixture route; no authored values depend on query, order, host or port. This packet does not claim pagination behavior.",
    "consistency_pair": {
        "route": "/api/brains/00000000-0000-4000-8000-000000000001/statistics",
        "starting_body": "responses/statistics-start.json",
        "ending_body": "responses/statistics-end.json",
        "expected_relation": "identical independently authored counters",
    },
    "unexpected_route_policy": "No implicit defaults or fallback payloads; public-use adapter must record/refuse unexpected routes.",
    "operations_performed": 0,
}


def svg_source_packet(case="plain"):
    """Self-contained qualified raw wire inputs; never constructs expected output."""
    assert case in {"plain", "composed"}, "unknown qualified SVG source case"
    note = NOTE.encode("utf-8") if case == "plain" else COMPOSED_NOTE
    files = {}

    def write(name, value):
        assert name not in files, "duplicate raw source body path"
        raw = (
            value
            if isinstance(value, bytes)
            else (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(
                "utf-8"
            )
        )
        files[name] = raw
        return {"length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    brain, home, child, definition, tag = map(identity, (1, 2, 3, 4, 5))

    # Independently authored DTOs qualified in raw packets01/02; no defaults.
    created = "2026-09-12T14:05:06Z"
    modified = "2026-10-01T09:07:08+02:00"
    thoughts = [
        {
            "id": home,
            "brainId": brain,
            "name": "Home",
            "kind": 1,
            "acType": 0,
            "typeId": None,
            "forgottenDateTime": None,
            "label": None,
            "aliases": [],
            "foregroundColor": None,
            "backgroundColor": None,
            "creationDateTime": created,
            "modificationDateTime": modified,
        },
        {
            "id": child,
            "brainId": brain,
            "name": "Child",
            "kind": 1,
            "acType": 0,
            "typeId": definition,
            "forgottenDateTime": None,
            "label": None,
            "aliases": [],
            "foregroundColor": None,
            "backgroundColor": None,
            "creationDateTime": created,
            "modificationDateTime": modified,
        },
        {
            "id": definition,
            "brainId": brain,
            "name": "Type",
            "kind": 2,
            "acType": 0,
            "typeId": None,
            "forgottenDateTime": None,
            "label": None,
            "aliases": [],
            "foregroundColor": None,
            "backgroundColor": None,
            "creationDateTime": created,
            "modificationDateTime": modified,
        },
        {
            "id": tag,
            "brainId": brain,
            "name": "Tag",
            "kind": 4,
            "acType": 0,
            "typeId": None,
            "forgottenDateTime": None,
            "label": None,
            "aliases": [],
            "foregroundColor": None,
            "backgroundColor": None,
            "creationDateTime": created,
            "modificationDateTime": modified,
        },
    ]
    by_id = {row["id"]: row for row in thoughts}
    # Each tuple and endpoint was independently authored in source_case before SVG
    # normalization. Names/colour/default-width marker/dates are new explicit facts.
    links = [
        {
            "id": identity(key),
            "brainId": brain,
            "thoughtIdA": a,
            "thoughtIdB": b,
            "kind": 1,
            "relation": relation,
            "meaning": meaning,
            "direction": direction,
            "typeId": None,
            "name": None,
            "color": None,
            "thickness": -1,
            "creationDateTime": created,
            "modificationDateTime": modified,
        }
        for key, a, b, relation, meaning, direction in (
            (101, home, child, 1, 1, -1),
            (102, home, child, 3, 1, 5),
            (103, home, child, 3, 1, 7),
            (104, definition, child, 1, 2, -1),
            (105, tag, child, 1, 5, -1),
        )
    ]
    payload_bytes = {
        identity(201): note,
        identity(202): PNG,
        identity(205): DRAWING,
        identity(206): DRAWING,
    }
    attachments = [
        {
            "id": identity(201),
            "brainId": brain,
            "sourceId": home,
            "sourceType": 2,
            "type": 1,
            "isNotes": True,
            "location": "Notes.md",
            "name": None,
            "position": 0,
            "dataLength": len(note),
        },
        {
            "id": identity(202),
            "brainId": brain,
            "sourceId": home,
            "sourceType": 2,
            "type": 12,
            "isNotes": False,
            "location": identity(202) + ".png",
            "name": None,
            "position": 0,
            "dataLength": 120,
        },
        {
            "id": identity(205),
            "brainId": brain,
            "sourceId": home,
            "sourceType": 2,
            "type": 12,
            "isNotes": False,
            "location": identity(205) + ".svg",
            "name": None,
            "position": 0,
            "dataLength": 327,
        },
        {
            "id": identity(206),
            "brainId": brain,
            "sourceId": home,
            "sourceType": 2,
            "type": 12,
            "isNotes": False,
            "location": identity(206) + ".svg",
            "name": None,
            "position": 0,
            "dataLength": 327,
        },
    ]
    brain_value = {"id": brain, "name": "Synthetic", "homeThoughtId": home}
    statistics = {
        "brainId": brain,
        "thoughts": 2,
        "thoughtTypes": 1,
        "tags": 1,
        "forgottenThoughts": 0,
        "links": 3,
    }
    endpoints = []

    def endpoint(route, path, value, *, kind="json", subject=None):
        measurement = write(path, value)
        endpoints.append(
            {
                "method": "GET",
                "route": "/api" + route,
                "status": 200,
                "body_path": path,
                "body_encoding": kind,
                "subject": subject,
                "body": measurement,
            }
        )
        return path

    endpoint("/brains", "responses/brains.json", [brain_value], subject=brain)
    endpoint("/brains/" + brain, "responses/brain.json", brain_value, subject=brain)
    endpoint(
        "/brains/" + brain + "/statistics",
        "responses/statistics-start.json",
        statistics,
        subject=brain,
    )
    write("responses/statistics-end.json", statistics)
    endpoint(
        "/search/" + brain,
        "responses/search.json",
        [
            {
                "brainId": brain,
                "isFromOtherBrain": False,
                "sourceThought": {"id": home, "brainId": brain, "kind": 0},
                "sourceLink": None,
            },
            {
                "brainId": brain,
                "isFromOtherBrain": False,
                "sourceThought": {"id": child, "brainId": brain, "kind": 0},
                "sourceLink": None,
            },
        ],
        subject=brain,
    )
    endpoint(
        "/thoughts/" + brain + "/types",
        "responses/types.json",
        [by_id[definition]],
        subject=brain,
    )
    endpoint(
        "/thoughts/" + brain + "/tags",
        "responses/tags.json",
        [by_id[tag]],
        subject=brain,
    )
    endpoint("/thoughts/" + brain + "/pins", "responses/pins.json", [], subject=brain)
    for row in thoughts:
        key = row["id"]
        endpoint(
            "/thoughts/" + brain + "/" + key,
            "responses/thoughts/" + key + ".json",
            row,
            subject=key,
        )
        # Adjacencies are independently literal facts. Multiple one-way links share
        # one neighbor identity but retain both complete relationship inventories.
        graph = {
            "activeThought": row,
            "parents": [by_id[home]] if key == child else [],
            "children": [by_id[child]] if key in {home, definition, tag} else [],
            "jumps": [by_id[child]]
            if key == home
            else [by_id[home]]
            if key == child
            else [],
            "siblings": [],
            "tags": [by_id[tag]] if key == child else [],
            "type": by_id[definition] if key == child else None,
            "links": [
                link
                for link in links
                if key in {link["thoughtIdA"], link["thoughtIdB"]}
            ],
            "attachments": attachments if key == home else [],
        }
        endpoint(
            "/thoughts/" + brain + "/" + key + "/graph",
            "responses/graphs/" + key + ".json",
            graph,
            subject=key,
        )
        endpoint(
            "/thoughts/" + brain + "/" + key + "/attachments",
            "responses/owner-attachments/" + key + ".json",
            attachments if key == home else [],
            subject=key,
        )
        if key != home:
            endpoint(
                "/notes/" + brain + "/" + key,
                "responses/no-notes/" + key + ".json",
                {
                    "brainId": brain,
                    "sourceId": key,
                    "sourceType": 2,
                    "modificationDateTime": "0001-01-01T00:00:00",
                    "markdown": "",
                    "html": None,
                    "text": None,
                },
                subject=key,
            )
    for row in links:
        key = row["id"]
        endpoint(
            "/links/" + brain + "/" + key,
            "responses/links/" + key + ".json",
            row,
            subject=key,
        )
        endpoint(
            "/links/" + brain + "/" + key + "/attachments",
            "responses/link-attachments/" + key + ".json",
            [],
            subject=key,
        )
    for row in attachments:
        key = row["id"]
        assert len(payload_bytes[key]) == row["dataLength"]
        endpoint(
            "/attachments/" + brain + "/" + key + "/metadata",
            "responses/attachment-metadata/" + key + ".json",
            row,
            subject=key,
        )
        endpoint(
            "/attachments/" + brain + "/" + key + "/file-content",
            "payloads/" + key + ".bin",
            payload_bytes[key],
            kind="bytes",
            subject=key,
        )

    ledger = SOURCE_PACKET_PROTOCOL | {"routes": endpoints}
    ledger_bytes = (json.dumps(ledger, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    measured = {
        name: {"length": len(value), "sha256": hashlib.sha256(value).hexdigest()}
        for name, value in files.items()
    }
    assert measured == QUALIFIED_SOURCE_BODIES[case], "qualified source body changed"
    assert {
        "length": len(ledger_bytes),
        "sha256": hashlib.sha256(ledger_bytes).hexdigest(),
    } == QUALIFIED_SOURCE_ORIGINS[case]["endpoint_ledger"], (
        "qualified route table changed"
    )
    return {
        "files": files,
        "ledger": ledger_bytes,
        "origin": QUALIFIED_SOURCE_ORIGINS[case],
    }


def svg_baseline(directory, case="plain"):
    """API acceptance container over qualified source bytes, with its own pin."""
    directory.mkdir(parents=True)
    packet = svg_source_packet(case)
    files = {}
    for name, value in packet["files"].items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        files[name] = {
            "length": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
    (directory / "endpoints.json").write_bytes(packet["ledger"])
    files["endpoints.json"] = fingerprint(directory / "endpoints.json")
    write_json(
        directory / "qualified-origin.json",
        {
            "case": case,
            "origin": packet["origin"],
            "basis": "qualified raw bodies/routes; historical bundle hash is not this Baseline hash",
        },
    )
    files["qualified-origin.json"] = fingerprint(directory / "qualified-origin.json")
    write_json(
        directory / "native.json",
        {"synthetic": True, "review": "independent destination hides incoming source"},
    )
    files["native.json"] = fingerprint(directory / "native.json")
    home, child = identity(2), identity(3)

    def graph(key):
        return "responses/graphs/" + key + ".json"

    manifest = {
        "schema": "brz2obsidian.api-acceptance/1",
        "files": files,
        "brain": "responses/brain.json",
        "scope": {
            "thought_ids": [identity(k) for k in (2, 3, 4, 5)],
            "relationship_ids": [identity(k) for k in (101, 102, 103, 104, 105)],
            "attachment_ids": [identity(k) for k in (201, 202, 205, 206)],
        },
        "graphs": {identity(k): graph(identity(k)) for k in (2, 3, 4, 5)},
        "types": "responses/types.json",
        "tags": {"status": 200, "path": "responses/tags.json"},
        "statistics": [
            "responses/statistics-start.json",
            "responses/statistics-end.json",
        ],
        "link_attachments": {
            identity(k): "responses/link-attachments/" + identity(k) + ".json"
            for k in (101, 102, 103, 104, 105)
        },
        "link_attachment_outcomes": {
            identity(k): 200 for k in (101, 102, 103, 104, 105)
        },
        "relationship_metadata": {
            identity(k): {
                "status": 200,
                "path": "responses/links/" + identity(k) + ".json",
            }
            for k in (101, 102, 103, 104, 105)
        },
        "no_notes": {
            identity(k): "responses/no-notes/" + identity(k) + ".json"
            for k in (3, 4, 5)
        },
        "payloads": {
            identity(k): {"status": 200, "path": "payloads/" + identity(k) + ".bin"}
            for k in (201, 202, 205, 206)
        },
        "attachment_inventories": {
            identity(k): "responses/owner-attachments/" + identity(k) + ".json"
            for k in (2, 3, 4, 5)
        },
        "attachment_metadata": {
            identity(k): {
                "status": 200,
                "path": "responses/attachment-metadata/" + identity(k) + ".json",
            }
            for k in (201, 202, 205, 206)
        },
        "qualification": ["qualified-origin.json", "native.json"],
        "archive_matches": [],
        "one_way_controls": [
            {
                "relationship_id": identity(102),
                "source_id": home,
                "destination_id": child,
                "direction": 5,
                "destination_hides_source": True,
                "evidence": ["native.json"],
                "graph": graph(home),
            },
            {
                "relationship_id": identity(103),
                "source_id": child,
                "destination_id": home,
                "direction": 7,
                "destination_hides_source": True,
                "evidence": ["native.json"],
                "graph": graph(home),
            },
        ],
        "source_packet_ledger": "endpoints.json",
    }
    path = write_json(directory / "manifest.json", manifest)
    return load_baseline(path, fingerprint(path)["sha256"])


@pytest.mark.parametrize(
    "damage",
    [
        "top-level",
        "extra-document-field",
        "missing-document-field",
        "wrong-provenance",
        "copy-flag-zero",
        "duplicate-container",
        "wrong-container-owner",
        "unknown-reference-field",
        "typed-reference-span",
        "missing-adaptation",
        "empty-target",
        "empty-owner-target",
        "empty-source-target",
    ],
)
def test_svg_only_notes_require_complete_published_nested_document_contract(
    tmp_path, damage
):
    baseline, vault = svg_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    doc = record["item_targets"][0]["documents"][0]
    if damage == "top-level":
        record["documents"] = [doc]
    elif damage == "extra-document-field":
        doc["invented"] = "metadata"
    elif damage == "missing-document-field":
        doc.pop("evidence")
    elif damage == "wrong-provenance":
        doc["evidence"] = ["attachment:" + identity(202)]
    elif damage == "copy-flag-zero":
        doc["original_copy_omitted"] = 0
    elif damage == "duplicate-container":
        record["item_targets"][1]["documents"] = [doc]
    elif damage == "wrong-container-owner":
        doc["owner"] = identity(3)
    elif damage == "unknown-reference-field":
        doc["references"][0]["invented"] = True
    elif damage == "typed-reference-span":
        doc["references"][0]["end"] = float(doc["references"][0]["end"])
    elif damage == "empty-target":
        doc["references"][0]["target"] = ""
    elif damage == "empty-owner-target":
        doc["owner_target"] = ""
    elif damage == "empty-source-target":
        doc["references"][0]["source_target"] = ""
    else:
        doc.pop("text_adaptations")
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("segmentation", ["atomic", "container"])
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "item-target",
        "item-destination",
        "item-table",
        "image-table",
        "edit-digest",
        "edit-kind",
        "edit-gap",
        "edit-coordinate",
    ],
)
def test_composed_svg_document_has_raw_bound_items_tables_and_edit_ownership(
    tmp_path, segmentation, damage
):
    baseline, vault = composed_svg_case(tmp_path, segmentation)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    doc = record["item_targets"][0]["documents"][0]
    item = next(r for r in doc["references"] if r["kind"] == "item")
    image = next(r for r in doc["references"] if r["kind"] == "image")
    if damage == "item-target":
        item["target"] = identity(4)
    elif damage == "item-destination":
        item["destination_start"] = 0
    elif damage == "item-table":
        item["table_cell"] = False
    elif damage == "image-table":
        image["table_cell"] = False
    elif damage == "edit-digest":
        doc["text_adaptations"][0]["source_digest"] = "0" * 64
    elif damage == "edit-kind":
        doc["text_adaptations"][0]["kind"] = "markdown_insert"
    elif damage == "edit-gap":
        doc["text_adaptations"][0]["before"] = "Invented"
    elif damage == "edit-coordinate":
        doc["text_adaptations"][-1]["adapted_start"] += 1
    write_json(path, record)
    if damage:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4


def composed_svg_case(tmp_path, segmentation="atomic"):
    raw = COMPOSED_NOTE.decode("utf-8")
    item_phrase = "[Child](brain://AAAAAAAAAECAAAAAAAAAAw/Child)"
    table_header = (
        '|Thought|Image|:(table="column-widths:-1,0,84;justification:default"):'
    )
    callout_header = "> [!tip|icon:😂]"
    rules = [
        ("literal_text", "<Enter>", "\\<Enter>"),
        ("markdown_insert", "[/toc/]", "- [Dessin](#^drawing-source)"),
        ("markdown_insert", table_header, "|Thought|Image|\n|---|---|"),
        ("markdown_insert", callout_header, "> [!tip] 😂 Tip"),
    ]
    if segmentation == "container":
        table_row = raw.split(table_header + "\r\n", 1)[1].split("\r\n", 1)[0]
        rules[2] = (
            "markdown_insert",
            table_header + "\r\n" + table_row,
            "|Thought|Image|\n|---|---|\r\n" + table_row,
        )
        rules[3] = (
            "markdown_insert",
            callout_header + "\r\n> Authored café.",
            "> [!tip] 😂 Tip\r\n> Authored café.",
        )
    edits, adapted, cursor = [], [], 0
    source_digest = hashlib.sha256(COMPOSED_NOTE).hexdigest()
    for kind, before, after in rules:
        start = raw.index(before, cursor)
        gap = raw[cursor:start]
        adapted.append(gap)
        adapted_start = len("".join(adapted))
        adapted.append(after)
        edits.append(
            {
                "kind": kind,
                "start": start,
                "end": start + len(before),
                "before": before,
                "after": after,
                "adapted_start": adapted_start,
                "adapted_end": adapted_start + len(after),
                "source_digest": source_digest,
                "source_basis": "scoped_source_text/unicode_codepoints",
                "adapted_basis": "document.text/unicode_codepoints",
            }
        )
        cursor = start + len(before)
    adapted.append(raw[cursor:])
    document = "".join(adapted)
    displayed = document.replace("\r\n", "\n").replace("\r", "\n")
    displayed = displayed.replace(item_phrase, "[[Notes/Child.md\\|Child]]")
    for key in (205, 202):
        extension = ".svg" if key == 205 else ".png"
        displayed = displayed.replace(
            ".data/md-images/" + identity(key) + extension,
            "Attachments/" + identity(key) + extension,
        )
    displayed = displayed.replace("#$width=50p$", "")
    baseline, vault = svg_case(
        tmp_path, raw_note=raw, document_text=document, display_note=displayed
    )
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    doc = record["item_targets"][0]["documents"][0]
    doc["text_adaptations"] = edits
    doc["references"][0]["table_cell"] = True
    start = document.index(item_phrase)
    doc["references"].append(
        {
            "start": start,
            "end": start + len(item_phrase),
            "kind": "item",
            "target": identity(3),
            "display_text": "Child",
            "expected_original": item_phrase,
            "document_digest": hashlib.sha256(document.encode()).hexdigest(),
            "source_target": "brain://AAAAAAAAAECAAAAAAAAAAw/Child",
            "destination_start": None,
            "destination_end": None,
            "presentation_normalization": None,
            "table_cell": True,
        }
    )
    doc["references"].sort(key=lambda row: row["start"])
    write_json(path, record)
    return baseline, vault


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "omit-empty-document",
        "null-item-documents",
        "null-retained-documents",
        "hidden-image-owner",
        "missing-owner-note",
        "hidden-definition",
        "fabricated-tag",
        "uncreated-tag-snapshot",
        "retained-owner-conflict",
    ],
)
def test_empty_svg_document_retains_identity_and_source_derived_materialization(
    tmp_path, damage
):
    baseline, vault = svg_case(tmp_path, raw_note="", document_text="", display_note="")
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    for asset in record["asset_targets"]:
        if asset["asset_id"] == identity(205):
            asset["resource_link"] = asset["relative_path"]
    (vault / "Home.md").write_text(
        "---\nicon:\nappearance_category:\n---\n\n# Home\n\n## Resources\n\n"
        + "".join(
            f"- [[Attachments/{identity(key)}.svg|{identity(key)}.svg]]\n"
            for key in (205, 206)
        ),
        encoding="utf-8",
    )
    targets = {row["item_key"]: row for row in record["item_targets"]}
    home, category, tag = (targets[identity(key)] for key in (2, 4, 5))
    if damage == "omit-empty-document":
        home["documents"] = []
    elif damage == "null-item-documents":
        tag["documents"] = None
    elif damage == "null-retained-documents":
        record["asset_targets"][2]["retained_documents"] = None
    elif damage == "hidden-image-owner":
        home["created"] = False
        home["icon_snapshot"] = None
        (vault / "Home.md").unlink()
    elif damage == "missing-owner-note":
        (vault / "Home.md").unlink()
    elif damage == "hidden-definition":
        category["created"] = False
        category["icon_snapshot"] = None
        (vault / category["relative_path"]).unlink()
    elif damage == "fabricated-tag":
        tag["created"] = True
        (vault / tag["relative_path"]).write_text("# Tag\n", encoding="utf-8")
    elif damage == "uncreated-tag-snapshot":
        tag["icon_snapshot"] = {
            "item_key": identity(5),
            "explicit_icon_asset_id": None,
            "appearance_category_key": None,
            "effective_icon_asset_id": None,
        }
    elif damage == "retained-owner-conflict":
        record["asset_targets"][2]["retained_documents"] = home["documents"]
        home["documents"] = []
    write_json(path, record)
    if damage:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.invalid/guide.svg",
        "https://example.invalid/guide?label=.svg",
        "https://example.invalid/guide.svg?text=[[forged.svg]]",
    ],
)
@pytest.mark.parametrize("damage", [None, "missing-owned-svg"])
def test_svg_resources_keep_inherited_http_targets_outside_owned_svg_inventory(
    tmp_path, uri, damage
):
    baseline, vault = svg_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    graph_path = root / manifest["graphs"][identity(2)]
    graph = json.loads(graph_path.read_bytes())
    url = {
        "id": identity(207),
        "brainId": identity(1),
        "sourceId": identity(2),
        "sourceType": 2,
        "type": 3,
        "isNotes": False,
        "location": uri,
        "name": "SVG guide",
        "dataLength": 0,
    }
    graph["attachments"].append(url)
    write_json(graph_path, graph)
    write_json(
        root / manifest["attachment_inventories"][identity(2)], graph["attachments"]
    )
    metadata_path = identity(207) + "-metadata.json"
    write_json(root / metadata_path, url)
    manifest["files"][metadata_path] = fingerprint(root / metadata_path)
    manifest["attachment_metadata"][identity(207)] = {
        "status": 200,
        "path": metadata_path,
    }
    manifest["scope"]["attachment_ids"].append(identity(207))
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["original_evidence"][0]["records"].append(url)
    record["asset_targets"].append(
        {
            "asset_id": identity(207),
            "owner": identity(2),
            "role": "url",
            "availability": "external",
            "original_name": "SVG guide",
            "display_name": "SVG guide",
            "relative_path": None,
            "actual_length": None,
            "actual_sha256": None,
            "external_uri": uri,
            "resource_link": uri,
            "retained_documents": [],
        }
    )
    write_json(record_path, record)
    note = vault / "Home.md"
    note.write_text(
        note.read_text(encoding="utf-8") + "- [SVG guide](<" + uri + ">)\n",
        encoding="utf-8",
    )
    assert expected_asset(baseline, url, "3") == ("url", "external", None)
    assert audit_baseline(baseline, profile_version="3")["attachments"] == 5
    if damage:
        note.write_text(
            note.read_text(encoding="utf-8").replace(
                f"- [[Attachments/{identity(206)}.svg|{identity(206)}.svg]]\n", ""
            ),
            encoding="utf-8",
        )
        with pytest.raises(AssertionError, match="SVG generated Resources links"):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4


@pytest.mark.parametrize(
    "placement",
    [None, "before-section", "other-section", "duplicate-heading", "extra-markdown"],
)
def test_svg_owned_resources_bind_one_complete_generated_section(tmp_path, placement):
    baseline, vault = svg_case(tmp_path)
    note = vault / "Home.md"
    text = note.read_text(encoding="utf-8")
    boundary = text.index("## Resources\n")
    prefix = text[:boundary]
    row = f"- [[Attachments/{identity(206)}.svg|{identity(206)}.svg]]\n"
    if placement == "before-section":
        text = prefix + row + "\n## Resources\n\n"
    elif placement == "other-section":
        text = prefix + "## Elsewhere\n\n" + row + "\n## Resources\n\n"
    elif placement == "duplicate-heading":
        text += "\n## Resources\n\n"
    elif placement == "extra-markdown":
        text += f"- [Forged](Attachments/{identity(206)}.svg)\n"
    note.write_text(text, encoding="utf-8")
    if placement:
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4


@pytest.mark.parametrize("guard", ["inline-code", "fence", "comment"])
def test_svg_generated_destination_census_keeps_protected_examples_inactive(
    tmp_path, guard
):
    baseline, vault = svg_case(tmp_path)
    example = f"[Example](Attachments/{identity(206)}.svg)"
    protected = {
        "inline-code": "`" + example + "`",
        "fence": "```\n" + example + "\n```",
        "comment": "<!-- " + example + " -->",
    }[guard]
    note = vault / "Home.md"
    note.write_text(
        note.read_text(encoding="utf-8") + "\n" + protected + "\n", encoding="utf-8"
    )
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4


def test_svg_resources_classify_owned_destination_separately_from_child_label(tmp_path):
    baseline, vault = svg_case(tmp_path)
    root = baseline.manifest_path.parent

    def rename(value):
        if isinstance(value, dict):
            if value.get("id") == identity(3) and value.get("name") == "Child":
                value["name"] = "Child.svg"
            for child in value.values():
                rename(child)
        elif isinstance(value, list):
            for child in value:
                rename(child)

    for path in root.rglob("*.json"):
        value = json.loads(path.read_bytes())
        rename(value)
        write_json(path, value)
    baseline = reseal(baseline)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    rename(record)
    child = next(
        row for row in record["item_targets"] if row["item_key"] == identity(3)
    )
    child["original_title"] = "Child.svg"
    write_json(record_path, record)
    child_path = vault / child["relative_path"]
    child_path.write_text(
        child_path.read_text(encoding="utf-8").replace("# Child\n", "# Child.svg\n"),
        encoding="utf-8",
    )
    home = vault / "Home.md"
    home.write_text(
        home.read_text(encoding="utf-8")
        + "\n## Children\n\n- [[Notes/Child.md|Child.svg]]\n",
        encoding="utf-8",
    )
    assert check_api_vault(baseline, vault, profile_version="3")["payloads"] == 4
