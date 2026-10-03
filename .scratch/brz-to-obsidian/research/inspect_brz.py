"""Read BRZ archives in place and print structural aggregates only.

Python 3.11+ standard library. No extraction, mutation, network access, or
private names/identifiers/note text in output. Regex note scans are evidence
probes, not a Markdown parser or a converter. Unexpected errors are reported
without payloads or source paths.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import sys
from urllib.parse import unquote, urlsplit
import uuid
import zipfile


UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
URL_RE = re.compile(r"(?:brain|https?|file)://[^\s<>\)\]\"']+", re.I)
LINK_RE = re.compile(r"(!?)\[[^\]\n]*\]\(([^)\n]+)\)")
ENUM_KEYS = {
    "thoughts.json": ("Kind", "ACType"),
    "links.json": ("Kind", "Relation", "Meaning", "Direction", "Thickness"),
    "attachments.json": ("Type", "SourceType", "NoteType", "IsIcon"),
    "tombstones.json": ("Type",),
}


def counts(values):
    return dict(sorted(Counter(str(v) for v in values).items()))


def guid(value):
    try:
        if UUID_RE.fullmatch(value):
            return str(uuid.UUID(value))
        if re.fullmatch(r"[A-Za-z0-9_-]{22}", value):
            return str(uuid.UUID(bytes_le=base64.urlsafe_b64decode(value + "==")))
    except (ValueError, TypeError):
        pass
    return None


def components(nodes, edges):
    adjacency = defaultdict(set)
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    remaining = set(nodes)
    sizes = []
    while remaining:
        stack = [remaining.pop()]
        size = 0
        while stack:
            current = stack.pop()
            size += 1
            found = adjacency[current] & remaining
            remaining.difference_update(found)
            stack.extend(found)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def cyclic_nodes(nodes, edges):
    adjacency = defaultdict(set)
    for a, b in edges:
        adjacency[a].add(b)
    indices, low, stack, active, cyclic = {}, {}, [], set(), set()
    def visit(node):
        indices[node] = low[node] = len(indices)
        stack.append(node)
        active.add(node)
        for child in adjacency[node]:
            if child not in indices:
                visit(child)
                low[node] = min(low[node], low[child])
            elif child in active:
                low[node] = min(low[node], indices[child])
        if low[node] == indices[node]:
            group = []
            while True:
                member = stack.pop()
                active.remove(member)
                group.append(member)
                if member == node:
                    break
            if len(group) > 1 or node in adjacency[node]:
                cyclic.update(group)
    for node in nodes:
        if node not in indices:
            visit(node)
    return len(cyclic)


def normalized_member(source_id, location):
    location = location.replace("\\", "/")
    if location.startswith("/") or re.match(r"^[A-Za-z]:", location):
        return None
    candidate = posixpath.normpath(source_id + "/" + location)
    return candidate if candidate.startswith(source_id + "/") else None


def inspect(path, label):
    output = {"archive": label, "bytes": path.stat().st_size}
    with path.open("rb") as stream:
        output["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    with zipfile.ZipFile(path) as z:
        members = z.infolist()
        names = [m.filename for m in members]
        name_set = set(names)
        resources = {m.filename: m for m in members if "/" in m.filename and not m.is_dir()}
        root_json = [n for n in names if "/" not in n and n.endswith(".json")]
        records = {}
        bom_count = 0
        for name in root_json:
            raw = z.read(name)
            bom_count += raw.startswith(b"\xef\xbb\xbf")
            records[name] = [json.loads(s) for s in raw.decode("utf-8-sig").splitlines() if s.strip()]
        output["zip"] = {
            "members": len(members), "root_json_files": len(root_json),
            "resource_files": len(resources), "uncompressed_bytes": sum(m.file_size for m in members),
            "duplicate_names": len(names) - len(name_set),
            "unsafe_paths": sum(n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/") or bool(re.match(r"^[A-Za-z]:", n)) for n in names),
            "symlinks": sum(stat.S_ISLNK(m.external_attr >> 16) for m in members),
            "encrypted_members": sum(bool(m.flag_bits & 1) for m in members),
            "compression_methods": counts(m.compress_type for m in members),
            "crc_errors": 0 if z.testzip() is None else 1,
            "utf8_bom_root_files": bom_count,
            "resource_extensions": counts(PurePosixPath(n).suffix.lower() for n in resources),
            "resource_owner_directories": len({n.split("/")[0] for n in resources}),
        }
        meta = records["meta.json"][0]
        brain_id = meta["BrainId"]
        states = meta["AttachmentFileStates"]
        output["exchange_format_version"] = meta["ExchangeFormatVersion"]
        output["collections"] = {
            n: {"records": len(rs), "field_keys": sorted({k for r in rs for k in r}),
                "duplicate_ids": len(rs) - len({r.get("Id") for r in rs}),
                "foreign_brain_ids": sum(r.get("BrainId") != brain_id for r in rs),
                "enums": {k: counts(r.get(k) for r in rs) for k in ENUM_KEYS.get(n, ())}}
            for n, rs in records.items() if n != "meta.json"
        }
        output["identity"] = {
            "invalid_uuid_ids": sum(not bool(UUID_RE.fullmatch(r.get("Id", ""))) for n, rs in records.items() if n not in {"meta.json", "settings.json"} for r in rs),
            "settings_id_shapes": counts("uuid" if UUID_RE.fullmatch(r.get("Id", "")) else "other" for r in records["settings.json"]),
            "datetime_timezone_suffixes": counts("UTC_Z" if v.endswith("Z") else "offset" if re.search(r"[+-]\d{2}:\d{2}$", v) else "unspecified" for rs in records.values() for r in rs for k, v in r.items() if k.endswith("DateTime") and isinstance(v, str)),
        }
        thoughts = {r["Id"]: r for r in records["thoughts.json"]}
        links = records["links.json"]
        attachments = records["attachments.json"]
        link_ids = {r["Id"] for r in links}
        attachment_ids = {r["Id"] for r in attachments}
        live_ids = set(thoughts) | link_ids | attachment_ids
        tombstones = records["tombstones.json"]
        tombstone_ids = {r["Id"] for r in tombstones}
        edges = [(r["ThoughtIdA"], r["ThoughtIdB"]) for r in links]
        ordinary_edges = [(r["ThoughtIdA"], r["ThoughtIdB"]) for r in links if r["Meaning"] == 1]
        hierarchy = [(r["ThoughtIdA"], r["ThoughtIdB"]) for r in links if r["Meaning"] == 1 and r["Relation"] == 1]
        parent_counts = Counter(b for a, b in hierarchy)
        incident = {v for edge in edges for v in edge}
        tag_pairs = set()
        tag_refs = []
        for thought in thoughts.values():
            raw_tags = thought["TagIds"]
            tags = raw_tags if isinstance(raw_tags, list) else re.findall(r"[0-9a-fA-F-]{36}", raw_tags or "")
            tag_refs.extend(tags)
            tag_pairs.update((tag_id, thought["Id"]) for tag_id in tags)
        has_tag_pairs = {(r["ThoughtIdA"], r["ThoughtIdB"]) for r in links if r["Meaning"] == 5}
        output["graph"] = {
            "dangling_endpoints": sum(v not in thoughts for edge in edges for v in edge),
            "self_links": sum(a == b for a, b in edges),
            "duplicate_ordered_pairs": len(edges) - len(set(edges)),
            "isolated_thoughts": len(set(thoughts) - incident),
            "all_relationship_component_sizes": components(thoughts, edges),
            "ordinary_relationship_component_sizes": components(thoughts, ordinary_edges),
            "ordinary_hierarchy_multi_parent_thoughts": sum(c > 1 for c in parent_counts.values()),
            "ordinary_hierarchy_max_parents": max(parent_counts.values(), default=0),
            "ordinary_hierarchy_cyclic_nodes": cyclic_nodes(thoughts, hierarchy),
            "relationship_signatures": counts((r["Kind"], r["Relation"], r["Meaning"], r["Direction"]) for r in links),
            "endpoint_kind_signatures": counts((r["Meaning"], thoughts[r["ThoughtIdA"]]["Kind"], thoughts[r["ThoughtIdB"]]["Kind"]) for r in links if r["ThoughtIdA"] in thoughts and r["ThoughtIdB"] in thoughts),
            "tag_id_value_types": counts(type(r["TagIds"]).__name__ for r in thoughts.values()),
            "tag_id_references": len(tag_refs), "tag_id_missing_targets": sum(v not in thoughts for v in tag_refs),
            "tag_id_non_tag_targets": sum(thoughts[v]["Kind"] != 4 for v in tag_refs if v in thoughts),
            "tag_pairs_without_has_tag_relationship": len(tag_pairs - has_tag_pairs),
            "has_tag_relationships_without_tag_id": len(has_tag_pairs - tag_pairs),
            "type_id_references": sum("TypeId" in r for r in thoughts.values()),
            "forgotten_thoughts": sum("ForgottenDateTime" in r for r in thoughts.values()),
            "thought_labels": sum("Label" in r for r in thoughts.values()),
            "named_relationships": sum("Name" in r for r in links),
            "thought_alias_fields": sum("Aliases" in r for r in thoughts.values()),
            "repeated_exact_titles": len(thoughts) - len({r["Name"] for r in thoughts.values()}),
            "casefold_title_collisions": len(thoughts) - len({r["Name"].casefold() for r in thoughts.values()}),
            "windows_invalid_title_characters": sum(bool(re.search(r'[<>:"/\\|?*]', r["Name"])) for r in thoughts.values()),
        }
        owner_kinds = Counter()
        resolved, failures, mismatches = [], [], Counter()
        metadata_paths = set()
        attachment_signature = Counter()
        for attachment in attachments:
            source_id = attachment["SourceId"]
            owner_kinds["thought" if source_id in thoughts else "link" if source_id in link_ids else "brain" if source_id == brain_id else "unresolved"] += 1
            attachment_signature[(attachment["Type"], attachment["NoteType"], PurePosixPath(attachment["Location"].replace("\\", "/")).suffix.lower())] += 1
            if attachment["Type"] in {2, 3, 8}:
                continue
            subdirectory = {5: ".data/", 12: ".data/md-images/", 6: "Notes/"}.get(attachment["Type"], "")
            candidate = normalized_member(source_id, subdirectory + attachment["Location"])
            if candidate in resources:
                metadata_paths.add(candidate)
                resolved.append(attachment)
                if resources[candidate].file_size != attachment["DataLength"]:
                    mismatches[str(attachment["Type"])] += 1
            else:
                failures.append(attachment)
        orphan_paths = set(resources) - metadata_paths
        note_paths = {n for n in resources if PurePosixPath(n).name.casefold() == "notes.md"}
        output["attachments"] = {
            "owner_kinds": dict(owner_kinds), "type_note_extension_signatures": counts(attachment_signature.elements()),
            "local_payload_records": len(resolved), "missing_local_payload_records": len(failures),
            "missing_local_payload_types": counts(r["Type"] for r in failures),
            "length_mismatch_types": dict(mismatches),
            "length_mismatch_zero_metadata": sum(not r["DataLength"] for r in resolved if resources[normalized_member(r["SourceId"], {5: ".data/", 12: ".data/md-images/", 6: "Notes/"}.get(r["Type"], "") + r["Location"])].file_size != r["DataLength"]),
            "external_url_records": sum(r["Type"] == 3 for r in attachments),
            "external_file_records": sum(r["Type"] == 2 for r in attachments),
            "external_directory_records": sum(r["Type"] == 8 for r in attachments),
            "physical_note_files": len(note_paths),
            "declared_markdown_note_records": sum(r["Type"] == 1 and r["NoteType"] == 4 for r in attachments),
            "orphan_resource_files": len(orphan_paths),
            "orphan_resource_extensions": counts(PurePosixPath(n).suffix.lower() for n in orphan_paths),
            "orphan_resources_live_thought_owners": sum(n.split("/")[0] in thoughts for n in orphan_paths),
            "orphan_resources_tombstoned_owners": sum(n.split("/")[0] in tombstone_ids for n in orphan_paths),
            "resources_with_nonlive_owner": sum(n.split("/")[0] not in thoughts and n.split("/")[0] not in link_ids for n in resources),
            "file_state_entries": len(states), "file_state_values": counts(states.values()),
            "file_state_ids_without_attachment_record": len(set(states) - attachment_ids),
            "file_state_missing_local_payload_records": sum(r["Id"] not in states for r in resolved),
            "missing_payload_file_state_values": counts(states.get(r["Id"]) for r in failures),
            "missing_payload_data_length_zero": sum(not r["DataLength"] for r in failures),
            "type15_with_pdf_on_same_owner": sum(any(x["SourceId"] == r["SourceId"] and x["Type"] == 1 and x["Location"].lower().endswith(".pdf") for x in attachments) for r in attachments if r["Type"] == 15),
        }
        syntax = Counter()
        refs = Counter()
        resolved_urls = Counter()
        note_nonempty = 0
        note_bom = 0
        for name in sorted(note_paths):
            raw = z.read(name)
            note_bom += raw.startswith(b"\xef\xbb\xbf")
            text = raw.decode("utf-8-sig")
            note_nonempty += bool(text.strip())
            probes = {
                "percent_style_marker": r"%%[^\n]*?%%", "footnote_definition": r"(?m)^\[\^[^\]]+\]:",
                "plus_fence": r"(?m)^\+\+\+", "double_equals_marker": r"==[^\n]*==",
                "checkbox_at_marker": r"@@", "headings": r"(?m)^#{1,6} ",
                "fenced_code": r"(?m)^```", "pipe_table": r"(?m)^\|.*\|$",
                "checkbox": r"(?m)^\s*[-*+] \[[xX ]\]", "html_tags": r"<[A-Za-z][^>]*>",
                "tb_comment": r"<!--tb:", "yaml_frontmatter": r"\A---\s*\n",
                "wiki_links": r"\[\[", "markdown_images": r"!\[[^\]\n]*\]\(",
                "html_entities": r"&(?:[A-Za-z]+|#\d+|#x[0-9a-fA-F]+);",
            }
            for key, pattern in probes.items():
                syntax[key] += bool(re.search(pattern, text))
            for match in LINK_RE.finditer(text):
                target = html.unescape(match[2].strip().strip("<>"))
                target = re.sub(r'\s+"[^\"]*"$', '', target)
                split = urlsplit(target)
                if split.scheme:
                    refs["image_" + split.scheme.lower() if match[1] else "link_" + split.scheme.lower()] += 1
                elif target.startswith("#"):
                    refs["local_fragment"] += 1
                else:
                    refs["relative_image" if match[1] else "relative_link"] += 1
                    local_target = unquote(split.path).replace("\\", "/")
                    candidate = posixpath.normpath(posixpath.dirname(name) + "/" + local_target)
                    refs["relative_resolved" if candidate in resources else "relative_missing"] += 1
            for match in URL_RE.finditer(text):
                target = html.unescape(match[0])
                split = urlsplit(target)
                refs["all_url_scheme_" + split.scheme.lower()] += 1
                if split.scheme.lower() != "brain":
                    continue
                parts = split.path.strip("/").split("/")
                if split.netloc.lower() in {"api.thebrain.com", "api.bra.in"} and len(parts) >= 2:
                    url_brain, url_thought = guid(parts[0]), guid(parts[1])
                    resolved_urls["same_brain" if url_brain == brain_id else "other_or_unresolved_brain"] += 1
                    resolved_urls["thought_found" if url_thought in thoughts else "thought_missing"] += 1
                    resolved_urls["short_guid_pair" if len(parts[0]) == len(parts[1]) == 22 else "other_id_form"] += 1
                elif guid(split.netloc):
                    # First-party docs permit omitted server and Brain IDs for
                    # links within the same Brain. All supplied notes use this.
                    url_thought = guid(split.netloc)
                    resolved_urls["same_brain_compact_thought_url"] += 1
                    resolved_urls["thought_found" if url_thought in thoughts else "thought_missing"] += 1
                else:
                    resolved_urls["other_url_shape"] += 1
        output["notes"] = {"physical_files": len(note_paths), "nonempty_files": note_nonempty,
                           "utf8_bom_files": note_bom, "files_with_syntax_probe": dict(syntax),
                           "references": dict(refs), "brain_url_resolution": dict(resolved_urls)}
        output["history"] = {"tombstones_overlapping_live_ids": len(tombstone_ids & live_ids),
                             "log_source_type_counts": counts(r.get("SourceType") for r in records["modificationlogs.json"]),
                             "log_sources_not_live": sum(r.get("SourceId") not in live_ids for r in records["modificationlogs.json"])}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps([inspect(p, f"archive_{i}") for i, p in enumerate(args.archives, 1)], indent=2))
    except Exception as error:
        # Never leak record contents, private paths, names, or JSON fragments.
        print(f"Inspection failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
