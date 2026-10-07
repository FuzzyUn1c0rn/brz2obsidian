"""Read-only verification of the two local, synthetic relationship fixtures.

Run from the repository root with Python 3.11+. This is an evidence aid,
not a validator or converter for arbitrary BRZ files.
"""

import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path


def read_archive(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None, f"CRC failure: {path.name}"

        def records(member):
            return [
                json.loads(line)
                for line in archive.read(member).decode("utf-8-sig").splitlines()
                if line.strip()
            ]

        meta = json.loads(archive.read("meta.json").decode("utf-8-sig"))
        assert meta["ExchangeFormatVersion"] == 5
        return meta, records("thoughts.json"), records("links.json")


def verify():
    baseline = Path("tmp/legacy/brz/relationship-fixture.brz")
    extended = Path("tmp/legacy/brz/relationship-fixture-extended.brz")
    _, baseline_thoughts, baseline_links = read_archive(baseline)
    _, thoughts, links = read_archive(extended)
    assert len(baseline_thoughts) == 5 and len(baseline_links) == 4
    assert len(thoughts) == 8 and len(links) == 7
    assert len({thought["Id"] for thought in thoughts}) == len(thoughts)
    assert len({link["Id"] for link in links}) == len(links)

    expected_names = {
        "PARENT",
        "CHILD",
        "PEER",
        "ARROW",
        "REVERSE_ARROW",
        "ONE_WAY_FORWARD",
        "ONE_WAY_REVERSE",
    }
    assert Counter(t["Name"] for t in thoughts if t["Kind"] == 1) == Counter(
        expected_names
    )
    names = {t["Id"]: t["Name"] if t["Kind"] == 1 else "SYSTEM" for t in thoughts}
    assert len([t for t in thoughts if t["Kind"] == 5]) == 1

    # Sync bookkeeping changed after the original export. All other fields
    # in each original relationship record must remain identical.
    by_link_id = {link["Id"]: link for link in links}
    for original in baseline_links:
        current = by_link_id[original["Id"]]
        assert {k: v for k, v in original.items() if k != "SyncSentId"} == {
            k: v for k, v in current.items() if k != "SyncSentId"
        }

    by_thought_id = {thought["Id"]: thought for thought in thoughts}
    permitted_thought_changes = {
        "SyncSentId",
        "ActivationDateTime",
        "DisplayModificationDateTime",
    }
    for original in baseline_thoughts:
        current = by_thought_id[original["Id"]]
        assert {
            k: v for k, v in original.items() if k not in permitted_thought_changes
        } == {k: v for k, v in current.items() if k not in permitted_thought_changes}

    expected = {
        ("SYSTEM", "PARENT"): (1, 1, 6, -1),
        ("PARENT", "CHILD"): (1, 1, 1, -1),
        ("CHILD", "PEER"): (1, 3, 1, -1),
        ("CHILD", "ARROW"): (1, 1, 1, 1),
        ("CHILD", "REVERSE_ARROW"): (1, 3, 1, 3),
        ("CHILD", "ONE_WAY_FORWARD"): (1, 3, 1, 5),
        ("CHILD", "ONE_WAY_REVERSE"): (1, 3, 1, 7),
    }
    observed = {}
    for link in links:
        pair = names[link["ThoughtIdA"]], names[link["ThoughtIdB"]]
        assert pair not in observed
        observed[pair] = tuple(
            link[k] for k in ("Kind", "Relation", "Meaning", "Direction")
        )
    assert observed == expected

    baseline_hash = hashlib.sha256(baseline.read_bytes()).hexdigest()
    assert (
        baseline_hash
        == "53fd9fd22249a59875d3525774e1bb27c8b66830b3d84430b4ababdf0675ae6a"
    )
    return {
        "exchange_format": 5,
        "baseline_sha256": baseline_hash,
        "extended_bytes": extended.stat().st_size,
        "extended_sha256": hashlib.sha256(extended.read_bytes()).hexdigest(),
        "original_relationships_preserved_except_sync_bookkeeping": True,
        "relationships": [
            {
                "A": a,
                "B": b,
                "Kind": kind,
                "Relation": relation,
                "Meaning": meaning,
                "Direction": direction,
            }
            for (a, b), (kind, relation, meaning, direction) in sorted(observed.items())
        ],
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
