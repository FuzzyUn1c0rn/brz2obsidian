import json
from zipfile import ZipFile

from tests.application.test_resources_workflow import HOME, resource_archive, thought

TARGET = "01234567-89ab-4cde-8f01-23456789abcd"
COMPACT = "Z0UjAauJ3kyPASNFZ4mrzQ"


def links_archive(path, body, *, resources=(), others=(), other_notes=()):
    resource_archive(path, resources, thoughts=(thought(TARGET, "Topic.v2"), *others))
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files[HOME + "/Notes.md"] = body.encode("utf-8")
    records = [json.loads(line) for line in files["attachments.json"].splitlines()]
    records[0]["DataLength"] = len(files[HOME + "/Notes.md"])
    meta = json.loads(files["meta.json"])
    for owner, text in other_notes:
        key = "bbbbbbbb-0000-4000-8000-000000000001"
        data = text.encode("utf-8")
        records.append(
            {
                "Id": key,
                "BrainId": meta["BrainId"],
                "SourceId": owner,
                "SourceType": 2,
                "Type": 1,
                "NoteType": 4,
                "Location": "Notes.md",
                "DataLength": len(data),
            }
        )
        meta["AttachmentFileStates"][key] = 1
        files[owner + "/Notes.md"] = data
    files["meta.json"] = json.dumps(meta).encode()
    files["attachments.json"] = "\n".join(json.dumps(r) for r in records).encode()
    with ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path
