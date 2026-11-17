"""Paired synthetic S292 sources with an independently authored direct oracle."""

import json
from zipfile import ZipFile

from tests.application.test_graph_workflow import graph_archive, identity
from tests.support.local_api import BRAIN, HOME, thought
from tests.support.local_api_graph import GraphApi, link
from tests.support.local_api_payloads import PNG, PayloadApi, attachment

IDS = {name: identity(i) for i, name in enumerate("ABCDEFGTU", 10)}
TITLES = {1: "Entry", **{i: name for i, name in enumerate("ABCDEFGTU", 10)}}
KINDS = {10: 2, 11: 2, 12: 2, 14: 2, 17: 4, 18: 4}
# a, b, relation, meaning, direction: independent reviewed source encodings.
EDGES = (
    (10, 11, 1, 3, -1),
    (11, 12, 1, 3, -1),
    (10, 14, 1, 3, -1),
    (12, 13, 1, 2, -1),
    (14, 15, 1, 2, -1),
    (10, 16, 1, 2, -1),
    (17, 11, 1, 5, -1),
    (18, 17, 1, 7, -1),
    (1, 11, 1, 1, -1),
    (11, 14, 3, 1, -1),
    (11, 13, 3, 1, -1),
    (11, 17, 3, 1, -1),
    (1, 10, 3, 1, -1),
)
TYPE_FIELDS = {11: 10, 12: 11, 14: 10, 13: 12, 15: 14, 16: 10}
DIRECT = {("A", "B"), ("B", "C"), ("A", "E"), ("C", "D"), ("E", "F"), ("A", "G")}
NAVIGATION = {
    ("hierarchy", "Entry", "B"),
    ("related", "B", "E"),
    ("related", "B", "D"),
    ("related", "B", "T"),
    ("related", "Entry", "A"),
}
ICON = identity(501)
DEEP_ICON = identity(502)


def scenario(edges, type_fields, deep):
    titles, kinds = dict(TITLES), dict(KINDS)
    fields = dict(TYPE_FIELDS if type_fields is None else type_fields)
    if deep:
        titles.update({30 + i: f"H{i}" for i in range(10)})
        titles.update({40: "N8", 41: "N9"})
        kinds.update({30 + i: 2 for i in range(10)})
        fields.update({31 + i: 30 + i for i in range(9)})
        fields.update({40: 37, 41: 38})
        edges = (
            *edges,
            *((30 + i, 31 + i, 1, 3, -1) for i in range(9)),
            (37, 40, 1, 2, -1),
            (38, 41, 1, 2, -1),
            (13, 15, 1, 1, -1),
            (15, 13, 1, 1, -1),
        )
    return titles, kinds, edges, fields


def brz_source(path, *, edges=EDGES, type_fields=None, deep=False):
    titles, kinds, edges, fields = scenario(edges, type_fields, deep)
    graph_archive(
        path, titles | {2: "Pinned"}, (*edges, (2, 1, 1, 6, -1)), kinds=kinds | {2: 5}
    )
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    records = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    for value in records:
        number = int(value["Id"].replace("-", ""), 16)
        if number in fields:
            value["TypeId"] = identity(fields[number])
    parts["thoughts.json"] = b"\n".join(json.dumps(v).encode() for v in records)
    owners = {ICON: IDS["A"]}
    if deep:
        owners[DEEP_ICON] = identity(30)
    parts["attachments.json"] = b"\n".join(
        json.dumps(
            {
                "Id": asset_id,
                "BrainId": BRAIN,
                "SourceId": owner,
                "SourceType": 2,
                "Type": 5,
                "IsIcon": True,
                "NoteType": 0,
                "Location": "Icon.png",
                "Name": "Icon.png",
                "DataLength": len(PNG),
            }
        ).encode()
        for asset_id, owner in owners.items()
    )
    meta = json.loads(parts["meta.json"])
    meta["AttachmentFileStates"] = {asset_id: 1 for asset_id in owners}
    parts["meta.json"] = json.dumps(meta).encode()
    for owner in owners.values():
        parts[owner + "/.data/Icon.png"] = PNG
    with ZipFile(path, "w") as archive:
        for name, raw in parts.items():
            archive.writestr(name, raw)
    return path


class TypeTagApi(PayloadApi, GraphApi):
    def __init__(self, *, edges=EDGES, type_fields=None, deep=False):
        super().__init__()
        titles, kinds, edges, fields = scenario(edges, type_fields, deep)
        self.thoughts = {HOME: thought(HOME, "Entry")}
        for number, name in titles.items():
            if number == 1:
                continue
            key = identity(number)
            self.thoughts[key] = thought(key, name) | {"kind": kinds.get(number, 1)}
        for member, provider in fields.items():
            self.thoughts[identity(member)]["typeId"] = identity(provider)
        self.types = [v for v in self.thoughts.values() if v["kind"] == 2]
        self.tags = [v for v in self.thoughts.values() if v["kind"] == 4]
        self.search = [
            {
                "brainId": BRAIN,
                "isFromOtherBrain": False,
                "sourceThought": {"id": k, "brainId": BRAIN, "kind": 0},
                "sourceLink": None,
            }
            for k in self.thoughts
        ]
        self.links = {
            identity(1000 + i): link(
                identity(1000 + i),
                HOME if a == 1 else identity(a),
                HOME if b == 1 else identity(b),
                relation=r,
                meaning=m,
                direction=d,
            )
            for i, (a, b, r, m, d) in enumerate(edges)
        }
        self.attachments = {
            ICON: attachment(ICON, IDS["A"], 5, "Icon.png", length=len(PNG))
        }
        self.payloads = {ICON: PNG}
        if deep:
            self.attachments[DEEP_ICON] = attachment(
                DEEP_ICON, identity(30), 5, "Icon.png", length=len(PNG)
            )
            self.payloads[DEEP_ICON] = PNG

    def response(self, path, query):
        status, value = super().response(path, query)
        if status == 200 and path.endswith("/graph") and path not in self.overrides:
            key = value["activeThought"]["id"]
            for edge in self.links.values():
                a, b = edge["thoughtIdA"], edge["thoughtIdB"]
                if edge["meaning"] == 3:
                    if key == a:
                        value["children"].append(self.thoughts[b])
                    if key == b:
                        value["type"] = self.thoughts[a]
                        value["parents"].append(self.thoughts[a])
                if edge["meaning"] == 7:
                    if key == a:
                        value["children"].append(self.thoughts[b])
                    if key == b:
                        value["tags"].append(self.thoughts[a])
                        value["parents"].append(self.thoughts[a])
        return status, value
