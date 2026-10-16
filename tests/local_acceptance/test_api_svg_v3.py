"""Independent S7 literals; input-01 pin c153bac8, qualified separately.

These public controls construct raw API evidence and literal output. No runtime
normalizer, encoder or converter is an expectation source.
"""

import hashlib
import json

import pytest

from .api_checker import audit_baseline, check_api_vault, expected_asset
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
            }
        )
    home = record["item_targets"][0]
    home.update(created=True, relative_path="Home.md")
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
            "evidence": [],
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
        "# Home\n\n" + display_note + "\n"
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
        lines[3], lines[4] = lines[4], lines[3]
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
