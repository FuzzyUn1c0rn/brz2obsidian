"""Inspect supplied BRZ archives read-only and emit aggregates only.

Python 3.14 standard library; no extraction or network activity. Archive
arguments are ordered A then B, matching brz-preservation.md. Payloads,
source names, identifiers, destinations and member paths are never printed.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import sys
import zipfile


def records(archive: zipfile.ZipFile, name: str) -> list[dict]:
    return [json.loads(line) for line in archive.read(name).decode("utf-8-sig").splitlines() if line.strip()]


def payload_path(attachment: dict) -> str | None:
    if attachment["Type"] in {2, 3, 8}:
        return None
    prefix = {5: ".data/", 12: ".data/md-images/", 6: "Notes/"}.get(attachment["Type"], "")
    return posixpath.normpath(attachment["SourceId"] + "/" + prefix + attachment["Location"].replace("\\", "/"))


def inspect(path: Path, label: str) -> dict:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    with zipfile.ZipFile(path, "r") as archive:
        thoughts = {thought["Id"]: thought for thought in records(archive, "thoughts.json")}
        links = records(archive, "links.json")
        attachments = records(archive, "attachments.json")
        members = {member.filename for member in archive.infolist() if not member.is_dir()}
        ordinary = {key for key, thought in thoughts.items() if thought["Kind"] == 1}
        tags = {key for key, thought in thoughts.items() if thought["Kind"] == 4}
        note_payloads: dict[str, set[str]] = defaultdict(set)
        other_attachments: dict[str, list[dict]] = defaultdict(list)
        for attachment in attachments:
            target = payload_path(attachment)
            is_note = attachment["Type"] == 1 and (attachment.get("NoteType", 0) != 0 or PurePosixPath(attachment["Location"].replace("\\", "/")).name.casefold() == "notes.md")
            if is_note:
                if target in members:
                    note_payloads[attachment["SourceId"]].add(target)
            else:
                other_attachments[attachment["SourceId"]].append(attachment)
        # Also inspect physical Notes.md placeholders independently of NoteType.
        for member in members:
            if "/" in member and PurePosixPath(member).name.casefold() == "notes.md":
                note_payloads[member.split("/", 1)[0]].add(member)
        nonblank_note = {owner for owner, paths in note_payloads.items() if any(archive.read(target).decode("utf-8-sig").strip() for target in paths)}
        labels = {key for key, thought in thoughts.items() if str(thought.get("Label", "")).strip()}
        empty_text = ordinary - nonblank_note
        # Decorative icon files and a Label are reported separately. Empty
        # Notes.md placeholders are note payloads but contribute no content.
        substantive = {
            owner for owner, owned in other_attachments.items()
            if any(attachment["Type"] in {2, 3, 8} or (attachment["Type"] != 5 and payload_path(attachment) in members) for attachment in owned)
        }
        no_substantive_content = empty_text - substantive
        contentless = {owner for owner in empty_text if not other_attachments[owner] and owner not in labels}
        incident = {endpoint for link in links for endpoint in (link["ThoughtIdA"], link["ThoughtIdB"])}
        normal_edges = [link for link in links if link["Kind"] == 1 and link["Meaning"] == 1 and link["ThoughtIdA"] in ordinary and link["ThoughtIdB"] in ordinary]

        def edge_counts(endpoints: set[str]) -> dict[str, int]:
            matching = [link for link in normal_edges if link["ThoughtIdA"] in endpoints and link["ThoughtIdB"] in endpoints]
            return {
                "hierarchy": sum(link["Relation"] in {1, 2} for link in matching),
                "jump": sum(link["Relation"] == 3 for link in matching),
                "other_relation": sum(link["Relation"] not in {1, 2, 3} for link in matching),
                "distinct_endpoints": len({endpoint for link in matching for endpoint in (link["ThoughtIdA"], link["ThoughtIdB"])}),
            }

        def attachment_counts(owners: set[str]) -> dict:
            selected = [attachment for owner in owners for attachment in other_attachments[owner]]
            return {
                "owners_with_any_other_attachment": sum(bool(other_attachments[owner]) for owner in owners),
                "other_attachment_records_by_type": dict(sorted(Counter(str(attachment["Type"]) for attachment in selected).items())),
                "owners_with_icon_file": sum(any(attachment["Type"] == 5 for attachment in other_attachments[owner]) for owner in owners),
                "owners_with_other_local_file": sum(any(attachment["Type"] not in {2, 3, 5, 8} and payload_path(attachment) in members for attachment in other_attachments[owner]) for owner in owners),
                "owners_with_external_reference": sum(any(attachment["Type"] in {2, 3, 8} for attachment in other_attachments[owner]) for owner in owners),
                "owners_with_missing_payload_record": sum(any(attachment["Type"] not in {2, 3, 8} and payload_path(attachment) not in members for attachment in other_attachments[owner]) for owner in owners),
                "owners_with_nonblank_label": len(owners & labels),
                "owners_with_foreground_color": sum("ForegroundColor" in thoughts[owner] for owner in owners),
            }

        return {
            "archive": label,
            "sha256": digest,
            "ordinary_thoughts": len(ordinary),
            "ordinary_with_nonblank_note_text": len(ordinary & nonblank_note),
            "ordinary_without_nonblank_note_text": len(empty_text),
            "ordinary_empty_text_with_physical_note_file": sum(bool(note_payloads[owner]) for owner in empty_text),
            "ordinary_empty_text_other_content": attachment_counts(empty_text),
            "ordinary_without_substantive_content": len(no_substantive_content),
            "ordinary_without_substantive_content_decoration": attachment_counts(no_substantive_content),
            "ordinary_strictly_contentless": len(contentless),
            "ordinary_normal_edges_both_empty_text": edge_counts(empty_text),
            "ordinary_normal_edges_both_without_substantive_content": edge_counts(no_substantive_content),
            "ordinary_normal_edges_both_strictly_contentless": edge_counts(contentless),
            "ordinary_isolated_empty_text_all_relationships": len(empty_text - incident),
            "ordinary_isolated_without_substantive_content_all_relationships": len(no_substantive_content - incident),
            "ordinary_isolated_strictly_contentless_all_relationships": len(contentless - incident),
            "all_isolated_without_substantive_content": len(set(thoughts) - nonblank_note - substantive - incident),
            "all_isolated_without_substantive_content_by_kind": dict(sorted(Counter(str(thoughts[owner]["Kind"]) for owner in set(thoughts) - nonblank_note - substantive - incident).items())),
            "tags": len(tags),
            "tags_with_nonblank_note_text": len(tags & nonblank_note),
            "tags_with_physical_note_file": sum(bool(note_payloads[owner]) for owner in tags),
            "tags_other_content": attachment_counts(tags),
            "note_records_missing_payload": sum(attachment["Type"] == 1 and attachment.get("NoteType", 0) != 0 and payload_path(attachment) not in members for attachment in attachments),
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
