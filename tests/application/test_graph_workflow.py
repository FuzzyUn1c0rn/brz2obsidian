import json
from uuid import UUID, uuid5
from zipfile import ZipFile

from tests.application.test_minimal_workflow import FIXTURE

BRAIN = "11111111-1111-4111-8111-111111111111"


def identity(number):
    return str(UUID(int=number))


def graph_archive(
    path, titles, edges=(), *, kinds=None, labels=None, reverse=False, notes=None
):
    kinds, labels = kinds or {}, labels or {}
    records = {
        file.name: file.read_bytes() for file in FIXTURE.iterdir() if file.is_file()
    }
    records["meta.json"] = json.dumps(
        {"BrainId": BRAIN, "ExchangeFormatVersion": 5, "AttachmentFileStates": {}}
    ).encode()
    thoughts = [
        {
            "Id": identity(n),
            "BrainId": BRAIN,
            "Name": title,
            "Kind": kinds.get(n, 1),
            "ACType": 0,
            "Label": labels.get(n),
            "ForgottenDateTime": None,
        }
        for n, title in titles.items()
    ]
    links = [
        {
            "Id": identity(1000 + i),
            "BrainId": BRAIN,
            "ThoughtIdA": identity(a),
            "ThoughtIdB": identity(b),
            "Kind": 1,
            "Relation": relation,
            "Meaning": meaning,
            "Direction": direction,
        }
        for i, (a, b, relation, meaning, direction) in enumerate(edges)
    ]
    if reverse:
        thoughts.reverse()
        links.reverse()
    records["thoughts.json"] = "\n".join(json.dumps(r) for r in thoughts).encode()
    records["links.json"] = "\n".join(json.dumps(r) for r in links).encode()
    records["settings.json"] = json.dumps(
        {"Id": str(uuid5(UUID(BRAIN), "20")), "Value": identity(1)}
    ).encode()
    attachments, states = [], {}
    for owner, (body, note_type) in (notes or {}).items():
        attachment_id = identity(2000 + owner)
        attachments.append(
            {
                "Id": attachment_id,
                "BrainId": BRAIN,
                "SourceId": identity(owner),
                "SourceType": 2,
                "Type": 1,
                "NoteType": note_type,
                "Location": "Notes.md",
                "Name": "Notes.md",
                "DataLength": len(body),
            }
        )
        states[attachment_id] = 1
        records[identity(owner) + "/Notes.md"] = body
    records["attachments.json"] = "\n".join(json.dumps(r) for r in attachments).encode()
    records["meta.json"] = json.dumps(
        {"BrainId": BRAIN, "ExchangeFormatVersion": 5, "AttachmentFileStates": states}
    ).encode()
    with ZipFile(path, "w") as archive:
        for name in sorted(records, reverse=reverse):
            archive.writestr(name, records[name])
    return path
