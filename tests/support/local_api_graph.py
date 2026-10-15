"""Independent source tuples from reviewed profile1, served only over HTTP."""

import json

from tests.support.local_api import ALONE, BRAIN, HOME, MetadataApi, thought

HIERARCHY = "60000000-0000-4000-8000-000000000001"
DEFINITION = "40000000-0000-4000-8000-000000000001"
TAG = "40000000-0000-4000-8000-000000000002"
CHILD = "40000000-0000-4000-8000-000000000003"
PEER = "40000000-0000-4000-8000-000000000004"
PLAIN = "40000000-0000-4000-8000-000000000005"
FORWARD = "40000000-0000-4000-8000-000000000006"
REVERSE = "40000000-0000-4000-8000-000000000007"
ARROW = "60000000-0000-4000-8000-000000000002"
JUMP = "60000000-0000-4000-8000-000000000003"
REVERSE_ARROW = "60000000-0000-4000-8000-000000000004"
ONE_WAY_FORWARD = "60000000-0000-4000-8000-000000000005"
ONE_WAY_REVERSE = "60000000-0000-4000-8000-000000000006"
TYPE_LINK = "60000000-0000-4000-8000-000000000007"
TAG_LINK = "60000000-0000-4000-8000-000000000008"

# Literal normative facts used across public interfaces, independently of output.
EXPECTED_RELATIONSHIPS = {
    (HIERARCHY, "hierarchy", HOME, ALONE),
    (ARROW, "hierarchy", HOME, CHILD),
    (JUMP, "related", HOME, PEER),
    (REVERSE_ARROW, "related", HOME, PLAIN),
    (ONE_WAY_FORWARD, "related", HOME, FORWARD),
    (ONE_WAY_REVERSE, "related", HOME, REVERSE),
    (TYPE_LINK, "classification", DEFINITION, HOME),
    (TAG_LINK, "tag", TAG, HOME),
}


def assert_published_graph(destination):
    """Literal #184 preservation checks shared by each public delivery seam."""
    record = json.loads((destination / "migration-record.json").read_bytes())
    assert {
        (r["key"], r["kind"], r["item_a"], r["item_b"]) for r in record["relationships"]
    } == EXPECTED_RELATIONSHIPS
    assert [
        (a["relationship_key"], a["definition_key"], a["item_key"])
        for a in record["classification_assignments"]
    ] == [(TYPE_LINK, DEFINITION, HOME)]
    targets = {t["item_key"]: t for t in record["item_targets"]}
    assert targets[HOME]["calendar_dates"] == {
        "created": "2026-01-01",
        "updated": "2026-12-31",
    }
    assert targets[HOME]["declared_appearance"] == {
        "foreground_color": "#123AbC",
        "background_color": None,
        "icon_asset_id": None,
    }
    assert targets[DEFINITION]["declared_appearance"] == {
        "foreground_color": "#6070ff",
        "background_color": "#ffe050",
        "icon_asset_id": None,
    }
    assert targets[HOME]["icon_snapshot"]["appearance_category_key"] == DEFINITION
    assert [
        (m["relationship_key"], m["tag_key"], m["item_key"], m["token"])
        for m in record["tag_memberships"]
    ] == [(TAG_LINK, TAG, HOME, "Source-tag")]
    note = (destination / "Home — Entry.md").read_text(encoding="utf-8")
    for expected in (
        "[[Categories/Definition.md]]",
        "created: 2026-01-01",
        "updated: 2026-12-31",
        "Source-tag",
        "Alone",
        "Arrow child",
        "Forward one way",
        "Reverse one way",
        "Plain reverse arrow",
        "Peer",
    ):
        assert expected in note
    assert (destination / "Categories/Definition.md").is_file()
    assert record["asset_targets"] == []
    assert "CANARY" not in json.dumps(record)
    return record


def link(key, a, b, *, relation=1, direction=-1, meaning=1):
    return {
        "id": key,
        "brainId": BRAIN,
        "thoughtIdA": a,
        "thoughtIdB": b,
        "kind": 1,
        "relation": relation,
        "direction": direction,
        "meaning": meaning,
        "typeId": None,
        "name": None,
        "color": None,
        "thickness": -1,
        "creationDateTime": "2026-10-14T10:00:00",
        "modificationDateTime": "2026-10-14T10:00:00",
    }


class GraphApi(MetadataApi):
    def __init__(self):
        super().__init__()
        self.links = {HIERARCHY: link(HIERARCHY, HOME, ALONE)}

    def response(self, path, query):
        if path in self.overrides:
            return super().response(path, query)
        for key, value in self.links.items():
            if path == f"/api/links/{BRAIN}/{key}":
                return 200, value
            if path == f"/api/links/{BRAIN}/{key}/attachments":
                return 200, []
        status, value = super().response(path, query)
        if path == f"/api/brains/{BRAIN}/statistics":
            # Reviewed counter family covers ordinary hierarchy/jumps only.
            return status, value | {
                "links": sum(l["meaning"] == 1 for l in self.links.values())
            }
        if path.endswith("/graph") and status == 200:
            key = value["activeThought"]["id"]
            for item in self.links.values():
                a, b = item["thoughtIdA"], item["thoughtIdB"]
                if key not in {a, b}:
                    continue
                value["links"].append(item)
                if item["meaning"] == 1:
                    if item["relation"] == 1:
                        value["children" if key == a else "parents"].append(
                            self.thoughts[b if key == a else a]
                        )
                    else:
                        value["jumps"].append(self.thoughts[b if key == a else a])
                elif item["meaning"] == 2:
                    if key == a:
                        value["children"].append(self.thoughts[b])
                    else:
                        value["type"] = self.thoughts[a]
                elif item["meaning"] == 5:
                    value["children" if key == a else "tags"].append(
                        self.thoughts[b if key == a else a]
                    )
            return status, value
        return status, value


class CompleteGraphApi(GraphApi):
    """All six ordinary tuples plus exact type/tag joins, without resources.

    Expected endpoints/roles are authored from LA-C05--08 and LA-C12, not
    calculated by any converter or checker. Every endpoint occurs in graphs.
    """

    def __init__(self):
        super().__init__()
        for key, name in (
            (DEFINITION, "Definition"),
            (TAG, "Source tag"),
            (CHILD, "Arrow child"),
            (PEER, "Peer"),
            (PLAIN, "Plain reverse arrow"),
            (FORWARD, "Forward one way"),
            (REVERSE, "Reverse one way"),
        ):
            self.thoughts[key] = thought(key, name)
        self.thoughts[DEFINITION].update(
            kind=2,
            foregroundColor="#6070ff",
            backgroundColor="#ffe050",
            label="Definition label",
        )
        self.thoughts[TAG]["kind"] = 4
        self.thoughts[HOME].update(
            typeId=DEFINITION,
            foregroundColor="#123AbC",
            label="Owned label",
            creationDateTime="2026-01-01T00:15:30+14:00",
            modificationDateTime="2026-12-31T23:59:00-12:00",
        )
        self.types = [self.thoughts[DEFINITION]]
        self.tags = [self.thoughts[TAG]]
        self.links.update(
            {
                ARROW: link(ARROW, HOME, CHILD, direction=1),
                JUMP: link(JUMP, HOME, PEER, relation=3),
                REVERSE_ARROW: link(
                    REVERSE_ARROW, HOME, PLAIN, relation=3, direction=3
                ),
                ONE_WAY_FORWARD: link(
                    ONE_WAY_FORWARD, HOME, FORWARD, relation=3, direction=5
                ),
                ONE_WAY_REVERSE: link(
                    ONE_WAY_REVERSE, HOME, REVERSE, relation=3, direction=7
                ),
                TYPE_LINK: link(TYPE_LINK, DEFINITION, HOME, meaning=2),
                TAG_LINK: link(TAG_LINK, TAG, HOME, meaning=5),
            }
        )
