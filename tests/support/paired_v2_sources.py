"""Two independently authored encodings of compatible category/date/icon facts."""

import json
from zipfile import ZipFile

from tests.support.paired_sources import BRAIN, KEYS, identity, paired_sources, seed

TYPE_IMAGE = b"folio category image\x00\xff"
MEMBER_IMAGE = b"folio owned override\x00\xff"
DEFINITION_BODY = b"Definition-owned prose.\r\n"
URL = "https://www.youtube.com/watch?v=SYNTHVID001&t=18s"
EMBED = "https://www.youtube.com/embed/SYNTHVID001?start=18"


def paired_v2_sources(path):
    brz, folio = paired_sources(path)
    # Folio's own named concepts and calendar triplets, never decoded from BRZ.
    data = json.loads(folio.read_bytes())
    data["entries"].append(
        {
            "key": "category:concept",
            "seed": seed(11),
            "title": "Concept",
            "role": "definition",
            "label": "Definition label",
            "appearance": {
                "icon_asset_id": "asset:107:category-image",
                "foreground_color": "#FF0000",
            },
            "calendar": {"created": [2024, 2, 29], "updated": [2025, 1, 1]},
        }
    )
    data["entries"][3].update(
        appearance={"icon_asset_id": "asset:108:owned-image"},
        calendar={"created": [2024, 2, 29], "updated": [2025, 1, 1]},
    )
    data["connections"].extend(
        [
            {
                "key": "classification:empty",
                "kind": "classification",
                "item_a": "category:concept",
                "item_b": KEYS[1],
            },
            {
                "key": "classification:middle",
                "kind": "classification",
                "item_a": "category:concept",
                "item_b": KEYS[3],
            },
        ]
    )
    data["assignments"] = [
        {
            "relationship_key": "classification:empty",
            "definition_key": "category:concept",
            "item_key": KEYS[1],
        },
        {
            "relationship_key": "classification:middle",
            "definition_key": "category:concept",
            "item_key": KEYS[3],
        },
    ]
    for number, key, owner, name, role, body in (
        (
            107,
            "asset:107:category-image",
            "category:concept",
            "type.png",
            "icon",
            TYPE_IMAGE,
        ),
        (108, "asset:108:owned-image", KEYS[3], "override.png", "icon", MEMBER_IMAGE),
        (
            109,
            "asset:109:category-original",
            "category:concept",
            "Notes.md",
            "note_original",
            DEFINITION_BODY,
        ),
    ):
        data["assets"].append(
            {
                "key": key,
                "seed": seed(number),
                "owner": owner,
                "name": name,
                "role": role,
                "file": f"payload-{number}",
            }
        )
        (folio.parent / f"payload-{number}").write_bytes(body)
    data["assets"].append(
        {
            "key": "asset:110:video",
            "seed": seed(110),
            "owner": KEYS[0],
            "name": "Video",
            "label": "Video",
            "role": "url",
            "uri": URL,
            "video": {"provider": "youtube", "embed_uri": EMBED, "start_seconds": 18},
        }
    )
    data["documents"].append(
        {
            "key": "document:category",
            "owner": "category:concept",
            "original": "asset:109:category-original",
        }
    )
    folio.write_text(json.dumps(data), encoding="utf-8")

    # Independently encode those meanings in TheBrain's fields/enums/records.
    with ZipFile(brz) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts.append(
        {
            "Id": identity(11),
            "BrainId": BRAIN,
            "Name": "Concept",
            "Kind": 2,
            "ACType": 0,
            "Label": "Definition label",
            "ForegroundColor": -65536,
            "CreationDateTime": "2024-02-29T23:59:58-11:00",
            "ModificationDateTime": "2025-01-01T00:00:00+14:00",
        }
    )
    for number in (2, 4):
        thoughts[number - 1]["TypeId"] = identity(11)
    thoughts[3].update(
        CreationDateTime="2024-02-29T23:59:58-11:00",
        ModificationDateTime="2025-01-01T00:00:00+14:00",
    )
    parts["thoughts.json"] = "\n".join(json.dumps(t) for t in thoughts).encode()
    links = [json.loads(line) for line in parts["links.json"].splitlines()]
    links.extend(
        {
            "Id": identity(200 + n),
            "BrainId": BRAIN,
            "ThoughtIdA": identity(11),
            "ThoughtIdB": identity(member),
            "Kind": 1,
            "Relation": 1,
            "Meaning": 2,
            "Direction": -1,
        }
        for n, member in ((6, 2), (7, 4))
    )
    parts["links.json"] = "\n".join(json.dumps(t) for t in links).encode()
    attachments = [json.loads(line) for line in parts["attachments.json"].splitlines()]
    meta = json.loads(parts["meta.json"])
    for number, owner, name, kind, note_type, body in (
        (107, 11, "type.png", 5, 0, TYPE_IMAGE),
        (108, 4, "override.png", 5, 0, MEMBER_IMAGE),
        (109, 11, "Notes.md", 1, 4, DEFINITION_BODY),
    ):
        attachments.append(
            {
                "Id": identity(number),
                "BrainId": BRAIN,
                "SourceId": identity(owner),
                "SourceType": 2,
                "Type": kind,
                "NoteType": note_type,
                "Location": name,
                "Name": name,
                "DataLength": len(body),
                "IsIcon": kind == 5,
            }
        )
        meta["AttachmentFileStates"][identity(number)] = 1
        parts[f"{identity(owner)}/" + (".data/" if kind == 5 else "") + name] = body
    attachments.append(
        {
            "Id": identity(110),
            "BrainId": BRAIN,
            "SourceId": identity(1),
            "SourceType": 2,
            "Type": 3,
            "NoteType": 0,
            "Location": URL,
            "Name": "Video",
            "DataLength": 0,
            "VideoHtml": "<iframe width='100%' height='100%' src='https://www.youtube.com/embed/SYNTHVID001?start=0' frameborder='0'></iframe>",
        }
    )
    parts["attachments.json"] = "\n".join(json.dumps(a) for a in attachments).encode()
    parts["meta.json"] = json.dumps(meta).encode()
    with ZipFile(brz, "w") as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return brz, folio
