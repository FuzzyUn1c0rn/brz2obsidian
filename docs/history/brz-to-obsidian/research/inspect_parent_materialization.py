"""Read real BRZs in place and emit parent-materialization aggregates only.

Python 3.14 standard library. No extraction, mutation, network activity,
source names, identifiers, note text, or attachment destinations in output.
Subset/permutation enumeration is for these small observed research cases;
this is not a production selection algorithm.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import combinations, permutations
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

from inspect_uncreated_targets import payload_path, records


def inspect(path: Path, label: str) -> dict:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    with zipfile.ZipFile(path, "r") as archive:
        thoughts = {thought["Id"]: thought for thought in records(archive, "thoughts.json")}
        links = records(archive, "links.json")
        attachments = records(archive, "attachments.json")
        members = {member.filename for member in archive.infolist() if not member.is_dir()}
        ordinary = {key for key, thought in thoughts.items() if thought["Kind"] == 1}
        note_payloads = defaultdict(set)
        substantive_other = set()
        for attachment in attachments:
            target = payload_path(attachment)
            is_note = attachment["Type"] == 1 and (attachment.get("NoteType", 0) != 0 or PurePosixPath(attachment["Location"].replace("\\", "/")).name.casefold() == "notes.md")
            if is_note:
                if target in members:
                    note_payloads[attachment["SourceId"]].add(target)
            elif attachment["Type"] in {2, 3, 8} or (attachment["Type"] != 5 and target in members):
                substantive_other.add(attachment["SourceId"])
        for member in members:
            if "/" in member and PurePosixPath(member).name.casefold() == "notes.md":
                note_payloads[member.split("/", 1)[0]].add(member)
        content_notes = substantive_other | {
            owner for owner, paths in note_payloads.items()
            if any(archive.read(target).decode("utf-8-sig").strip() for target in paths)
        }
        empty = ordinary - content_notes
        hierarchy = [
            (link["ThoughtIdA"], link["ThoughtIdB"]) if link["Relation"] == 1 else (link["ThoughtIdB"], link["ThoughtIdA"])
            for link in links
            if link["Kind"] == 1 and link["Meaning"] == 1 and link["Relation"] in {1, 2}
            and link["ThoughtIdA"] in ordinary and link["ThoughtIdB"] in ordinary
        ]
        uncovered = [(parent, child) for parent, child in hierarchy if parent in empty and child in empty]
        candidates = sorted({parent for parent, child in uncovered})
        candidate_set = set(candidates)
        children = {child for parent, child in uncovered}

        def covered(selected: set[str]) -> bool:
            return all(parent in selected or child in selected for parent, child in uncovered)

        minimum_size = None
        minimum_sets = 0
        for size in range(len(candidates) + 1):
            winners = sum(covered(set(selected)) for selected in combinations(candidates, size))
            if winners:
                minimum_size = size
                minimum_sets = winners
                break

        def sequential(order: tuple[tuple[str, str], ...] | list[tuple[str, str]]) -> int:
            selected = set()
            for parent, child in order:
                if parent not in selected and child not in selected:
                    selected.add(parent)
            assert covered(selected)
            return len(selected)

        # A has only seven initially uncovered edges; B four. Guard against
        # accidentally treating factorial enumeration as a scalable algorithm.
        if len(uncovered) > 9 or len(candidates) > 12:
            raise ValueError("Research enumeration bound exceeded")
        distribution = Counter(sequential(order) for order in permutations(uncovered))
        return {
            "archive": label,
            "sha256": digest,
            "ordinary_thoughts": len(ordinary),
            "initial_ordinary_content_notes": len(content_notes & ordinary),
            "ordinary_without_substantive_content": len(empty),
            "ordinary_hierarchy_edges": len(hierarchy),
            "initially_uncovered_hierarchy_edges": len(uncovered),
            "distinct_endpoints": len({endpoint for edge in uncovered for endpoint in edge}),
            "distinct_parent_candidates": len(candidates),
            "parent_candidates_also_children_of_uncovered_edge": len(candidate_set & children),
            "parent_candidates_with_child_outside_candidate_set": len({parent for parent, child in uncovered if child not in candidate_set}),
            "extra_notes_creating_every_parent_candidate": len(candidates),
            "minimum_parent_candidate_subset_cover_size": minimum_size,
            "minimum_parent_candidate_subset_cover_count": minimum_sets,
            "sequential_native_archive_order_extra_notes": sequential(uncovered),
            "sequential_reverse_archive_order_extra_notes": sequential(list(reversed(uncovered))),
            "sequential_minimum_over_all_edge_orders": min(distribution),
            "sequential_maximum_over_all_edge_orders": max(distribution),
            "sequential_edge_order_count": sum(distribution.values()),
            "sequential_order_count_by_extra_note_count": dict(sorted(distribution.items())),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs=2, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps({"python": sys.version.split()[0], "archives": [inspect(path, label) for path, label in zip(args.archives, ("A", "B"))]}, indent=2))
    except Exception as error:
        print(f"Inspection failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
