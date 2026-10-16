"""Independent complete mixed API wire packets and literal scope expectations.

Author: /root/baseline_owner. Inputs are source-only facts, never converter output.
Existing inert binary inputs retain contributor provenance beside their bytes.
"""

import base64
import hashlib
import json
from pathlib import Path
from uuid import UUID

FIXTURES = Path(__file__).parents[1] / "fixtures" / "local_api_scope_v3"


def identity(number):
    return f"00000000-0000-4000-8000-{number:012d}"


def compact(number):
    return (
        base64.urlsafe_b64encode(UUID(identity(number)).bytes_le).decode().rstrip("=")
    )


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


DRAWING = b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="12" viewBox="0 0 24 12"><rect width="24" height="12" fill="#aBc"/><line x1="0" y1="0" x2="24" y2="12" stroke="#123456"/></svg>\n'
EXCLUDED_PHRASE = (
    "[FORGOTTEN-CANARY ![enclosed](.data/md-images/"
    + identity(999)
    + ".svg)](brain://"
    + compact(91)
    + "/Forgotten)"
)
SYSTEM_PHRASE = "[SYSTEM-CANARY](brain://" + compact(90) + "/System)"
SCOPED_HOME = (
    "Préface Ω.\r\n<Enter>\r\n\r\n"
    "[/toc/]\r\n\r\n# Mixed ^mixed-source\r\n\r\n"
    '|Thought|Image|:(table="column-widths:-1,0,84;justification:default"):\r\n'
    "|[Child](brain://" + compact(3) + "/Child)|"
    "![Système](.data/md-images/"
    + identity(205)
    + '.svg#$width=50p$ "Stencil")|\r\n\r\n'
    "> [!tip|icon:😂]\r\n> Authored café.\r\n\r\n"
    "![JPEG](.data/md-images/" + identity(204) + ".jpg)\r\n"
    "![PNG](.data/md-images/" + identity(202) + ".png)\r\n"
    "![WebP](.data/md-images/" + identity(203) + ".webp)\r\n"
    "Visible  tail.\r\nSystem  done.\r\n"
)
RAW_HOME = SCOPED_HOME.replace(
    "Visible  tail.", "Visible " + EXCLUDED_PHRASE + " tail."
).replace("System  done.", "System " + SYSTEM_PHRASE + " done.")
ADAPTED_HOME = (
    "Préface Ω.\r\n\\<Enter>\r\n\r\n"
    "- [Mixed](#^mixed-source)\r\n\r\n# Mixed ^mixed-source\r\n\r\n"
    "|Thought|Image|\n|---|---|\r\n"
    "|[Child](brain://" + compact(3) + "/Child)|"
    "![Système](.data/md-images/"
    + identity(205)
    + '.svg#$width=50p$ "Stencil")|\r\n\r\n'
    "> [!tip] 😂 Tip\r\n> Authored café.\r\n\r\n"
    "![JPEG](.data/md-images/" + identity(204) + ".jpg)\r\n"
    "![PNG](.data/md-images/" + identity(202) + ".png)\r\n"
    "![WebP](.data/md-images/" + identity(203) + ".webp)\r\n"
    "Visible  tail.\r\nSystem  done.\r\n"
)


def mixed_source_packet(case="tags"):
    """Return exact bodies/route ledger and /2 input mappings, without a vault."""
    assert case in {"tags", "zero-tags", "changed-svg"}, "unknown mixed source packet"
    tagged = case != "zero-tags"
    brain = identity(1)
    created, modified = "2026-09-13T11:12:13Z", "2026-10-02T16:17:18+02:00"
    # All eleven required raw wire fields are authored explicitly, even exclusions.
    thoughts = []
    for key, title, kind, provider, forgotten, foreground, background in (
        (2, "Home", 1, None, None, None, None),
        (3, "Child", 1, identity(4), None, None, None),
        (4, "Type", 2, None, None, "#123456", "#abcdef"),
        (5, "Tag", 4, None, None, None, None),
        (6, "Empty after removal", 1, None, None, None, None),
        (7, "Coverage parent", 1, None, None, None, None),
        (8, "External only", 1, None, None, None, None),
        (9, "Safe empty", 1, None, None, None, None),
        (90, "SYSTEM-METADATA-CANARY", 5, None, None, None, None),
        (91, "FORGOTTEN-METADATA-CANARY", 1, None, "2026-09-20T01:02:03Z", None, None),
    ):
        if key == 5 and not tagged:
            continue
        thoughts.append(
            {
                "id": identity(key),
                "brainId": brain,
                "creationDateTime": created,
                "modificationDateTime": modified,
                "name": title,
                "typeId": provider,
                "forgottenDateTime": forgotten,
                "acType": 0,
                "kind": kind,
                "foregroundColor": foreground,
                "backgroundColor": background,
                "label": None,
                "aliases": [],
            }
        )
    by_id = {row["id"]: row for row in thoughts}
    excluded = {identity(90), identity(91)}
    included = {key: row for key, row in by_id.items() if key not in excluded}
    links = []
    for key, a, b, relation, meaning, direction in (
        (101, 2, 3, 1, 1, 3),
        (102, 2, 3, 3, 1, 5),
        (103, 2, 3, 3, 1, 7),
        (104, 4, 3, 1, 2, -1),
        (105, 5, 3, 1, 5, -1),
        (106, 2, 7, 1, 1, -1),
        (107, 7, 6, 1, 1, 3),
        (190, 2, 90, 9, 77, 44),
        (191, 2, 91, 9, 88, 55),
    ):
        if key == 105 and not tagged:
            continue
        links.append(
            {
                "id": identity(key),
                "brainId": brain,
                "thoughtIdA": identity(a),
                "thoughtIdB": identity(b),
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
        )
    active_links = [
        r for r in links if not excluded & {r["thoughtIdA"], r["thoughtIdB"]}
    ]
    image_svg = DRAWING if case != "changed-svg" else DRAWING.replace(b"#aBc", b"#aBd")
    payloads = {
        identity(201): RAW_HOME.encode("utf-8"),
        identity(202): (FIXTURES / "red-pixel.png").read_bytes(),
        identity(203): (FIXTURES / "red-green.webp").read_bytes(),
        identity(204): (FIXTURES / "inert-blue.jpg").read_bytes(),
        identity(205): image_svg,
        identity(206): DRAWING,
        identity(207): (FIXTURES / "blank.pdf").read_bytes(),
        identity(212): (FIXTURES / "inert-a.ico").read_bytes(),
        identity(301): (FIXTURES / "inert-b.ico").read_bytes(),
        identity(302): (FIXTURES / "red-pixel.png").read_bytes(),
        identity(401): b"Child authored body.\n",
        identity(601): EXCLUDED_PHRASE.encode("utf-8"),
        identity(901): b"",
    }
    attachments = []
    for key, owner, kind, is_note, location, name, declared_length, position in (
        (201, 2, 1, True, "Notes.md", None, None, 0),
        (202, 2, 12, False, identity(202) + ".png", None, None, 1),
        (203, 2, 12, False, identity(203) + ".webp", None, None, 2),
        (204, 2, 12, False, identity(204) + ".jpg", None, None, 3),
        (205, 2, 12, False, identity(205) + ".svg", None, None, 4),
        (206, 2, 12, False, identity(206) + ".svg", None, None, 5),
        (207, 2, 1, False, "manual.pdf", None, None, 6),
        (208, 2, 15, False, "manual.txt", None, 123, 7),
        (209, 8, 2, False, "C:\\Research\\R&D #1\\café [v2].pdf", None, 98765, 0),
        (210, 8, 8, False, "D:/Working Sets/Alpha", None, 0, 1),
        (
            211,
            8,
            3,
            False,
            "https://example.invalid/guide.svg?next=file:read",
            "file: guide",
            0,
            2,
        ),
        (212, 2, 5, False, "Icon.png", None, None, 8),
        (301, 4, 5, False, "Icon.png", None, None, 0),
        (302, 3, 5, False, "Icon.png", None, None, 0),
        (401, 3, 1, True, "Notes.md", None, None, 1),
        (601, 6, 1, True, "Notes.md", None, None, 0),
        (901, 9, 1, True, "Notes.md", None, None, 0),
    ):
        attachments.append(
            {
                "id": identity(key),
                "brainId": brain,
                "sourceId": identity(owner),
                "sourceType": 2,
                "type": kind,
                "isNotes": is_note,
                "location": location,
                "name": name,
                "position": position,
                "dataLength": len(payloads[identity(key)])
                if declared_length is None
                else declared_length,
            }
        )
    files, routes = {}, []

    def body(path, value):
        assert path not in files
        files[path] = value if isinstance(value, bytes) else json_bytes(value)
        return path

    def endpoint(route, path, value, status=200, optional=False):
        body(path, value)
        routes.append(
            {
                "method": "GET",
                "route": "/api" + route,
                "status": status,
                "body_path": path,
                "optional": optional,
            }
        )
        return path

    base = "/" + brain
    brain_row = {
        "id": brain,
        "name": "Independent mixed source",
        "homeThoughtId": identity(2),
    }
    stats = {
        "brainId": brain,
        "thoughts": 6,
        "thoughtTypes": 1,
        "tags": int(tagged),
        "forgottenThoughts": 1,
        "links": 9,
    }
    brain_path = endpoint("/brains" + base, "responses/brain.json", brain_row)
    endpoint("/brains", "responses/brains.json", [brain_row])
    before = endpoint(
        "/brains" + base + "/statistics", "responses/statistics-start.json", stats
    )
    after = body("responses/statistics-end.json", stats)
    types = endpoint(
        "/thoughts" + base + "/types", "responses/types.json", [by_id[identity(4)]]
    )
    tags = endpoint(
        "/thoughts" + base + "/tags",
        "responses/tags.json",
        [by_id[identity(5)]]
        if tagged
        else ("Could not retrieve list of Tags for brain " + brain).encode(),
        200 if tagged else 400,
    )
    endpoint("/thoughts" + base + "/pins", "responses/pins.json", [], optional=True)
    endpoint(
        "/search" + base,
        "responses/search.json",
        [
            {
                "brainId": "00000000-0000-0000-0000-000000000000",
                "isFromOtherBrain": False,
                "sourceThought": None,
                "sourceLink": {"id": identity(101), "brainId": brain},
                "searchResultType": 1,
                "entityType": 3,
                "sourceType": 0,
                "attachmentId": "00000000-0000-0000-0000-000000000000",
            },
            *(
                {
                    "brainId": brain,
                    "isFromOtherBrain": False,
                    "sourceThought": {"id": key, "brainId": brain, "kind": 0},
                    "sourceLink": None,
                }
                for key in by_id
            ),
        ],
    )
    graphs, inventories, no_notes, excluded_thoughts = {}, {}, {}, {}
    for key, row in by_id.items():
        metadata = endpoint(
            "/thoughts" + base + "/" + key, "responses/thoughts/" + key + ".json", row
        )
        if key in excluded:
            excluded_thoughts[key] = {"status": 200, "path": metadata}
            continue
        owned = [a for a in attachments if a["sourceId"] == key]
        adjacent = {
            field: [] for field in ("parents", "children", "jumps", "siblings", "tags")
        }
        for link in links:
            a, b = link["thoughtIdA"], link["thoughtIdB"]
            if link["relation"] == 1:
                if a == key:
                    adjacent["children"].append(by_id[b])
                if b == key and link["meaning"] == 1:
                    adjacent["parents"].append(by_id[a])
                if b == key and link["meaning"] == 5:
                    adjacent["tags"].append(by_id[a])
            elif link["meaning"] == 1 and key in {a, b}:
                neighbor = by_id[b if a == key else a]
                if neighbor not in adjacent["jumps"]:
                    adjacent["jumps"].append(neighbor)
            elif a == key and b in excluded:
                adjacent["children"].append(by_id[b])
        graph = {
            "activeThought": row,
            **adjacent,
            "type": by_id[row["typeId"]] if row["typeId"] else None,
            "links": [r for r in links if key in {r["thoughtIdA"], r["thoughtIdB"]}],
            "attachments": owned,
        }
        graphs[key] = endpoint(
            "/thoughts" + base + "/" + key + "/graph",
            "responses/graphs/" + key + ".json",
            graph,
        )
        inventories[key] = endpoint(
            "/thoughts" + base + "/" + key + "/attachments",
            "responses/owner-attachments/" + key + ".json",
            owned,
        )
        if not any(a["isNotes"] for a in owned):
            no_notes[key] = endpoint(
                "/notes" + base + "/" + key,
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
            )
    relationship_metadata, excluded_relationships, link_attachments = {}, {}, {}
    for link in links:
        key = link["id"]
        path = endpoint(
            "/links" + base + "/" + key, "responses/links/" + key + ".json", link
        )
        if link in active_links:
            relationship_metadata[key] = {"status": 200, "path": path}
            link_attachments[key] = endpoint(
                "/links" + base + "/" + key + "/attachments",
                "responses/link-attachments/" + key + ".json",
                [],
            )
        else:
            excluded_relationships[key] = {"status": 200, "path": path}
    metadata, outcomes = {}, {}
    for attachment in attachments:
        key = attachment["id"]
        path = endpoint(
            "/attachments" + base + "/" + key + "/metadata",
            "responses/attachment-metadata/" + key + ".json",
            attachment,
        )
        metadata[key] = {"status": 200, "path": path}
        if attachment["type"] in {2, 3, 8}:
            continue
        status = 404 if key == identity(208) else 200
        path = endpoint(
            "/attachments" + base + "/" + key + "/file-content",
            "payloads/" + key + ".bin",
            b"" if status == 404 else payloads[key],
            status,
        )
        outcomes[key] = {"status": status, "path": path}
    ledger = {
        "schema": "independent.inert-local-api-response-packet/1",
        "method": "GET",
        "routes": routes,
        "configuration": {"profile_version": "3", "include_pins": False},
        "query_policy": "Route identity excludes query; complete unsaturated search/graph response independent of query.",
        "consistency_pair": {
            "route": "/api/brains" + base + "/statistics",
            "starting_body": before,
            "ending_body": after,
        },
        "forbidden_routes": [
            *[
                "/api/thoughts" + base + "/" + key + suffix
                for key in sorted(excluded)
                for suffix in ("/graph", "/attachments")
            ],
            *["/api/notes" + base + "/" + key for key in sorted(excluded)],
            *[
                "/api/links" + base + "/" + key + "/attachments"
                for key in excluded_relationships
            ],
            *[
                "/api/attachments" + base + "/" + identity(key) + "/file-content"
                for key in (209, 210, 211)
            ],
        ],
        "unexpected_route_policy": "refuse and record; no default DTO/payload or external target I/O",
    }
    body("endpoints.json", ledger)
    # This non-wire qualification document was sealed with CRLF. Git text
    # checkout spelling must not change the qualified response-container pin.
    provenance = (FIXTURES / "input-provenance.json").read_bytes()
    body(
        "input-provenance.json",
        provenance.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"),
    )
    body(
        "one-way-source-control.json",
        {
            "synthetic": True,
            "qualified_source_rule": "retained independent145/209 direction5/7 source meaning; not a new native observation",
        },
    )
    mappings = {
        "brain": brain_path,
        "scope": {
            "thought_ids": sorted(included),
            "relationship_ids": [r["id"] for r in active_links],
            "attachment_ids": [a["id"] for a in attachments],
        },
        "graphs": graphs,
        "types": types,
        "tags": {"status": 200 if tagged else 400, "path": tags},
        "statistics": [before, after],
        "link_attachments": link_attachments,
        "link_attachment_outcomes": {key: 200 for key in link_attachments},
        "relationship_metadata": relationship_metadata,
        "no_notes": no_notes,
        "payloads": outcomes,
        "attachment_inventories": inventories,
        "attachment_metadata": metadata,
        "scope_inputs": {
            "excluded_thoughts": excluded_thoughts,
            "excluded_relationships": excluded_relationships,
        },
        "qualification": ["input-provenance.json", "one-way-source-control.json"],
        "archive_matches": [],
        "one_way_controls": [
            {
                "relationship_id": identity(key),
                "source_id": identity(a),
                "destination_id": identity(b),
                "direction": direction,
                "destination_hides_source": True,
                "evidence": ["one-way-source-control.json"],
                "graph": graphs[identity(2)],
            }
            for key, a, b, direction in ((102, 2, 3, 5), (103, 3, 2, 7))
        ],
        "source_packet_ledger": "endpoints.json",
    }
    return {"files": files, "ledger": ledger, "baseline_inputs": mappings, "case": case}


def mixed_expectations():
    """Literal independent safe/adapted facts; never reads generated output."""
    return {
        "safe_notes": {
            identity(201): SCOPED_HOME,
            identity(401): "Child authored body.\n",
            identity(601): "",
            identity(901): "",
        },
        "adapted_notes": {
            identity(201): ADAPTED_HOME,
            identity(401): "Child authored body.\n",
            identity(601): "",
            identity(901): "",
        },
        "removed_thought_ids": {
            identity(201): [identity(90), identity(91)],
            identity(601): [identity(91)],
        },
        "omitted_original_ids": [identity(201), identity(601)],
        "retained_asset_ids": [
            identity(k)
            for k in (
                202,
                203,
                204,
                205,
                206,
                207,
                208,
                209,
                210,
                211,
                212,
                301,
                302,
                401,
                901,
            )
        ],
        "openable_payload_ids": [
            identity(k) for k in (202, 203, 204, 205, 206, 207, 212, 301, 302, 401, 901)
        ],
        "created": {
            identity(2): True,
            identity(3): True,
            identity(4): True,
            identity(5): False,
            identity(6): False,
            identity(7): True,
            identity(8): True,
            identity(9): False,
        },
        "external": {
            identity(209): {
                "role": "file",
                "uri": "file:///C:/Research/R%26D%20%231/caf%C3%A9%20%5Bv2%5D.pdf",
                "display": "café [v2].pdf",
                "label": "café  v2 .pdf",
            },
            identity(210): {
                "role": "directory",
                "uri": "file:///D:/Working%20Sets/Alpha",
                "display": "Alpha",
                "label": "Alpha",
            },
            identity(211): {
                "role": "url",
                "uri": "https://example.invalid/guide.svg?next=file:read",
                "display": "file: guide",
                "label": "file: guide",
            },
        },
        "canaries": [
            "FORGOTTEN-CANARY",
            "SYSTEM-CANARY",
            "FORGOTTEN-METADATA-CANARY",
            "SYSTEM-METADATA-CANARY",
        ],
        "basis": "independently authored source strings and established rendering rules; no product/parser import",
    }


def mixed_literal_documents():
    """Worked literal transformations/spans, independent of all note parsers."""
    displayed = ADAPTED_HOME.replace("\r\n", "\n")
    item = "[Child](brain://" + compact(3) + "/Child)"
    displayed = displayed.replace(item, "[[Notes/Child.md\\|Child]]")
    references = []
    spellings = [("item", 3, item, "brain://" + compact(3) + "/Child", "Child", True)]
    for key, suffix, label, tail, table in (
        (205, "svg", "Système", '#$width=50p$ "Stencil"', True),
        (204, "jpg", "JPEG", "", False),
        (202, "png", "PNG", "", False),
        (203, "webp", "WebP", "", False),
    ):
        destination = ".data/md-images/" + identity(key) + "." + suffix
        phrase = "![" + label + "](" + destination + tail + ")"
        source_target = destination + ("#$width=50p$" if key == 205 else "")
        spellings.append(("image", key, phrase, source_target, label, table))
        displayed = displayed.replace(
            destination + ("#$width=50p$" if key == 205 else ""),
            "Attachments/" + identity(key) + "." + suffix,
        )
    for kind, key, phrase, source, label, table in spellings:
        start = ADAPTED_HOME.index(phrase)
        destination = ADAPTED_HOME.index(source, start)
        references.append(
            {
                "kind": kind,
                "target": identity(key),
                "display_text": label,
                "start": start,
                "end": start + len(phrase),
                "expected_original": phrase,
                "source_target": source,
                "destination_start": destination,
                "destination_end": destination + len(source),
                "table_cell": table,
            }
        )
    header = '|Thought|Image|:(table="column-widths:-1,0,84;justification:default"):'
    adaptations = []
    offset = 0
    for kind, before, after in (
        ("literal_text", "<Enter>", "\\<Enter>"),
        ("markdown_insert", "[/toc/]", "- [Mixed](#^mixed-source)"),
        ("markdown_insert", header, "|Thought|Image|\n|---|---|"),
        ("markdown_insert", "> [!tip|icon:😂]", "> [!tip] 😂 Tip"),
    ):
        start = SCOPED_HOME.index(before)
        adaptations.append(
            {
                "kind": kind,
                "start": start,
                "end": start + len(before),
                "before": before,
                "after": after,
                "adapted_start": start + offset,
                "adapted_end": start + offset + len(after),
                "source_digest": hashlib.sha256(SCOPED_HOME.encode()).hexdigest(),
                "source_basis": "scoped_source_text/unicode_codepoints",
                "adapted_basis": "document.text/unicode_codepoints",
            }
        )
        offset += len(after) - len(before)
    return {
        "key": identity(201),
        "owner": identity(2),
        "scoped_text": SCOPED_HOME,
        "adapted_text": ADAPTED_HOME,
        "display_text": displayed,
        "text_digest": hashlib.sha256(ADAPTED_HOME.encode()).hexdigest(),
        "source_digest": hashlib.sha256(SCOPED_HOME.encode()).hexdigest(),
        "references": references,
        "text_adaptations": adaptations,
    }
