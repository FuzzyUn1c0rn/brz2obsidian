"""Inert source protocol controls, independently authored at HTTP/BRZ seams."""

import json
from zipfile import ZipFile

from tests.application.test_graph_workflow import graph_archive
from tests.support.local_api import HOME
from tests.support.local_api_payloads import attachment
from tests.support.type_tag_sources import IDS, TypeTagApi, brz_source

TAG_NOTE = "00000000-0000-4000-8000-000000000510"
TAG_BODY = b"Independent tag T source body.\r\n"
ABSENT_INTERMEDIATE_ICON = "00000000-0000-4000-8000-000000000511"
VIDEO_URLS = (
    "https://www.youtube.com/watch?v=SYNTHVID001&list=short",
    "https://www.youtube.com/watch?index=00&list=other%2Fcontext&v=SYNTHVID001",
    "https://www.youtube.com/playlist?list=only%2Bcontext",
)
VIDEO_HTML = "<iframe width='100%' height='100%' src='https://www.youtube.com/embed/SYNTHVID001?start=0' frameborder='0'></iframe>"

SCHEMA = {
    "openapi": "3.0.1",
    "info": {"title": "Synthetic current acquisition protocol", "version": "1.0"},
    "paths": {
        "/api/brains": {"get": {}},
        "/api/brains/{brainId}": {"get": {}},
        "/api/brains/{brainId}/statistics": {"get": {}},
        "/api/search/{brainId}": {"get": {}},
        "/api/thoughts/{brainId}/types": {"get": {}},
        "/api/thoughts/{brainId}/tags": {"get": {}},
        "/api/thoughts/{brainId}/{thoughtId}": {"get": {}},
        "/api/thoughts/{brainId}/{thoughtId}/graph": {"get": {}},
        "/api/thoughts/{brainId}/{thoughtId}/attachments": {"get": {}},
        "/api/links/{brainId}/{linkId}": {"get": {}},
        "/api/links/{brainId}/{linkId}/attachments": {"get": {}},
        "/api/attachments/{brainId}/{attachmentId}/metadata": {"get": {}},
        "/api/attachments/{brainId}/{attachmentId}/file-content": {"get": {}},
        "/api/notes/{brainId}/{thoughtId}": {"get": {}},
    },
}


def paired_audit_source(path):
    """Source-only paired base/deep graphs, present T/absent U and videos."""
    source = brz_source(path, deep=True)
    api = TypeTagApi(deep=True)
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    api.attachments[TAG_NOTE] = attachment(
        TAG_NOTE, IDS["T"], 1, "Notes.md", is_notes=True, length=len(TAG_BODY)
    )
    api.payloads[TAG_NOTE] = TAG_BODY
    for index, uri in enumerate(VIDEO_URLS, 520):
        key = f"00000000-0000-4000-8000-{index:012d}"
        api.attachments[key] = attachment(key, HOME, 3, uri) | {
            "name": f"Video {index}"
        }
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    # The retained paired helper uses a numeric BRZ Home and a fixed API Home;
    # give this independent audit fixture one matching logical Home identity.
    for name in ("thoughts.json", "links.json", "settings.json"):
        parts[name] = parts[name].replace(
            b"00000000-0000-0000-0000-000000000001", HOME.encode()
        )
    rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    for row in api.attachments.values():
        if row["id"] in {a["Id"] for a in rows}:
            continue
        raw = {
            "Id": row["id"],
            "BrainId": row["brainId"],
            "SourceId": row["sourceId"],
            "SourceType": 2,
            "Type": row["type"],
            "NoteType": 4 if row["isNotes"] else 0,
            "IsIcon": False,
            "Location": row["location"],
            "Name": row["name"] or row["location"],
            "DataLength": row["dataLength"],
        }
        if row["type"] == 3 and row["location"] in VIDEO_URLS[:2]:
            raw["VideoHtml"] = VIDEO_HTML
        rows.append(raw)
    # BRZ declares an absent H4 icon; the API fixture has no such attachment.
    # This source-specific absence must fall through to H0, not be fabricated
    # as an API declaration or copied into H4's owned icon property.
    rows.append(
        {
            "Id": ABSENT_INTERMEDIATE_ICON,
            "BrainId": "11111111-1111-4111-8111-111111111111",
            "SourceId": "00000000-0000-0000-0000-000000000022",
            "SourceType": 2,
            "Type": 5,
            "NoteType": 0,
            "IsIcon": True,
            "Location": "Absent.png",
            "Name": "Absent.png",
            "DataLength": 123,
        }
    )
    parts["attachments.json"] = b"\n".join(json.dumps(row).encode() for row in rows)
    parts[IDS["T"] + "/Notes.md"] = TAG_BODY
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"][TAG_NOTE] = 1
    meta["AttachmentFileStates"][ABSENT_INTERMEDIATE_ICON] = 3
    parts["meta.json"] = json.dumps(meta).encode()
    with ZipFile(source, "w") as archive:
        for name, raw in parts.items():
            archive.writestr(name, raw)
    return source, api


def uncreated_tag_source(path):
    """Only Home and U->T, with no content that could create either tag note."""
    source = graph_archive(
        path,
        {1: "Entry", 17: "T", 18: "U"},
        ((18, 17, 1, 7, -1),),
        kinds={17: 4, 18: 4},
    )
    api = TypeTagApi(edges=((18, 17, 1, 7, -1),), type_fields={})
    api.thoughts = {
        key: row for key, row in api.thoughts.items() if key == HOME or row["kind"] == 4
    }
    api.types = []
    api.tags = [row for row in api.thoughts.values() if row["kind"] == 4]
    api.search = [
        {
            "brainId": row["brainId"],
            "isFromOtherBrain": False,
            "sourceThought": {"id": key, "brainId": row["brainId"], "kind": 0},
            "sourceLink": None,
        }
        for key, row in api.thoughts.items()
    ]
    api.attachments = {}
    api.payloads = {}
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    return source, api
