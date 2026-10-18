"""Reviewed category absences through real source ZIPs and public workflows."""

import json
from zipfile import ZipFile

from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import change_record


def type_parts(tmp_path):
    source = graph_archive(
        tmp_path / "base.brz",
        {1: "Entry", 2: "Concept", 3: "Member"},
        [(2, 3, 1, 2, -1)],
        kinds={2: 2},
        notes={2: (b"unknown", 4), 3: (b"Member prose.\r\n", 4)},
    )
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[2]["TypeId"] = identity(2)
    parts["thoughts.json"] = b"\n".join(json.dumps(t).encode() for t in thoughts)
    return parts


def remove_type_note(parts, declared=7):
    parts.pop(identity(2) + "/Notes.md")
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"][identity(2002)] = 3
    parts["meta.json"] = json.dumps(meta).encode()
    change_record(parts, identity(2002), DataLength=declared)


def inventory(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }
