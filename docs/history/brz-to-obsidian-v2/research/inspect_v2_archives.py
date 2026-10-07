"""Read complete BRZ archives and emit a deterministic, privacy-safe inventory.

No extraction, source mutation, conversion, network access, or private record
values. Uses the checked-out source reader for compatibility probes, not as a
semantic oracle. The last input is compared with the union of preceding inputs.
Run with the project's .venv Python; see source-differences.md.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import unicodedata
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid5
from zipfile import ZipFile


REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))
from markdown_it import MarkdownIt
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.attachments import normalize_attachments
from brz2obsidian.sources.thebrain.decoding import ROOT_FILES, decode_records
from brz2obsidian.sources.thebrain.notes import trace_note_references
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from brz2obsidian.sources.thebrain.reader import BrzSourceModule, _refuse, _uuid


UUID_PATTERN = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
DATE_PATTERN = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?\Z")
PROBES = {
    "percent_style_marker": r"%%[^\n]*?%%",
    "footnote_definition": r"(?m)^\[\^[^\]]+\]:",
    "plus_fence": r"(?m)^\+\+\+",
    "double_equals_marker": r"==[^\n]*==",
    "checkbox_at_marker": r"@@",
    "headings": r"(?m)^#{1,6} ",
    "fenced_code": r"(?m)^```",
    "tilde_fence": r"(?m)^~~~",
    "pipe_table": r"(?m)^\|.*\|$",
    "checkbox": r"(?m)^\s*[-*+] \[[xX ]\]",
    "html_tags": r"<[A-Za-z][^>]*>",
    "tb_comment": r"<!--tb:",
    "yaml_frontmatter": r"\A---\s*\n",
    "wiki_links": r"\[\[",
    "markdown_images": r"!\[[^\]\n]*\]\(",
    "html_entities": r"&(?:[A-Za-z]+|#\d+|#x[0-9a-fA-F]+);",
}
# Numeric signatures reviewed in docs/source-coverage.md. Endpoint roles matter.
REVIEWED_LINKS = {
    (1, 1, 1, -1, 1, 1), (1, 1, 1, 1, 1, 1),
    (1, 1, 1, 7, 1, 1), (1, 1, 1, -1, 1, 4),
    (1, 3, 1, -1, 1, 1), (1, 3, 1, 3, 1, 1),
    (1, 3, 1, 5, 1, 1), (1, 3, 1, 7, 1, 1),
    (1, 1, 5, -1, 4, 1), (1, 1, 6, -1, 5, 1),
    (1, 1, 6, -1, 5, 4),
}


def counts(values):
    return dict(sorted(Counter(str(v) for v in values).items()))


def signatures(values):
    return [dict(signature=list(k), count=v) for k, v in sorted(Counter(values).items(), key=lambda x: str(x[0]))]


def shape(value):
    """Retain data types and string categories, never string contents or IDs."""
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) in {int, float}:
        return type(value).__name__
    if isinstance(value, list):
        return "array[" + ",".join(sorted({shape(v) for v in value})) + "]"
    if isinstance(value, dict):
        # Dynamic keys may be private identities, titles or property names.
        return "object[" + ",".join(sorted({shape(v) for v in value.values()})) + "]"
    if not value:
        return "string:empty"
    if UUID_PATTERN.fullmatch(value):
        return "string:uuid"
    if DATE_PATTERN.fullmatch(value):
        suffix = "Z" if value.endswith("Z") else "offset" if re.search(r"[+-]\d\d:\d\d$", value) else "unspecified-zone"
        return "string:datetime:" + suffix
    if value.startswith(("http://", "https://", "brain://", "file://")):
        return "string:uri:" + value.split(":", 1)[0]
    if value in {"True", "False", "true", "false"}:
        return "string:boolean"
    if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return "string:numeric"
    return "string:other"


def fields(records):
    result = {}
    for field in sorted({key for r in records for key in r}):
        values = [r[field] for r in records if field in r]
        result[field] = {
            "present": len(values), "absent": len(records) - len(values),
            "null": sum(v is None for v in values), "shapes": counts(shape(v) for v in values),
            "distinct_values": len({json.dumps(v, sort_keys=True) for v in values}),
        }
        scalars = [v for v in values if type(v) in {bool, int, float}]
        if scalars:
            result[field]["numeric_boolean_values"] = counts(json.dumps(v) for v in scalars)
        arrays = [v for v in values if isinstance(v, list)]
        if arrays:
            result[field]["array_lengths"] = counts(len(v) for v in arrays)
        objects = [v for v in values if isinstance(v, dict)]
        if objects:
            result[field]["object_key_counts"] = counts(len(v) for v in objects)
    return result


def components(nodes, edges):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    remaining, sizes = set(nodes), []
    while remaining:
        stack, size = [remaining.pop()], 0
        while stack:
            current = stack.pop()
            size += 1
            found = adj[current] & remaining
            remaining.difference_update(found)
            stack.extend(found)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def cyclic_nodes(nodes, edges):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
    indices, low, stack, active, cyclic = {}, {}, [], set(), set()
    def visit(node):
        indices[node] = low[node] = len(indices)
        stack.append(node)
        active.add(node)
        for child in adj[node]:
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
            if len(group) > 1 or node in adj[node]:
                cyclic.update(group)
    for node in nodes:
        if node not in indices:
            visit(node)
    return len(cyclic)


class HtmlShape(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.attrs, self.url_schemes = Counter(), Counter(), Counter()
    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        self.attrs.update(key for key, value in attrs)
        for key, value in attrs:
            if key in {"src", "href"} and value:
                self.url_schemes[urlsplit(value).scheme.lower() or "relative"] += 1
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def note_inventory(payloads, thought_ids, names):
    parser = MarkdownIt("commonmark")
    metrics, tokens, probes, targets, local, html_tags, trace = (Counter() for _ in range(7))
    token_files = Counter()
    for member, raw in payloads:
        text = raw.decode("utf-8-sig")
        metrics["files"] += 1
        metrics["nonempty_decoded_files"] += bool(text)
        metrics["nonblank_files"] += bool(text.strip())
        metrics["utf8_bom_files"] += raw.startswith(b"\xef\xbb\xbf")
        metrics["files_with_crlf"] += "\r\n" in text
        metrics["files_with_bare_lf"] += "\n" in text.replace("\r\n", "")
        metrics["files_with_bare_cr"] += "\r" in text.replace("\r\n", "")
        metrics["files_with_nul"] += "\0" in text
        for name, pattern in PROBES.items():
            probes[name] += bool(re.search(pattern, text))
        file_tokens = set()
        for block in parser.parse(text):
            for token in [block] + (block.children or []):
                tokens[token.type] += 1
                file_tokens.add(token.type)
                if token.type.startswith("html_"):
                    hp = HtmlShape()
                    hp.feed(token.content)
                    html_tags.update(hp.tags)
                if token.type not in {"image", "link_open"}:
                    continue
                target = token.attrGet("src" if token.type == "image" else "href")
                parts = urlsplit(target)
                targets[(token.type, parts.scheme.lower() or "relative", "reference" if "label" in token.meta else "inline_or_autolink")] += 1
        token_files.update(file_tokens)
        try:
            spans = trace_note_references(text)
            trace["accepted_files"] += 1
            for span in spans:
                local[span.kind + "_references"] += 1
                parts = urlsplit(span.target)
                if span.kind == "item":
                    try:
                        compact = parts.netloc
                        uid = str(UUID(bytes_le=base64.urlsafe_b64decode(compact + "==")))
                        valid = len(compact) == 22 and base64.urlsafe_b64encode(UUID(uid).bytes_le).decode().rstrip("=") == compact
                        local["item_valid_compact_live_targets"] += valid and uid in thought_ids
                        local["item_invalid_or_nonlive_targets"] += not valid or uid not in thought_ids
                        if valid and uid in thought_ids:
                            local["item_target_kind_" + str(thought_ids[uid]["Kind"])] += 1
                    except (ValueError, TypeError):
                        local["item_invalid_or_nonlive_targets"] += 1
                else:
                    loc = unquote(parts.path)
                    candidate = str(PurePosixPath(member).parent / loc)
                    local["image_present_targets"] += candidate in names
                    local["image_absent_targets"] += candidate not in names
        except MigrationRefused as error:
            trace["refused_files"] += 1
            trace.update(issue.code for issue in error.issues)
    return {
        "metrics": dict(sorted(metrics.items())), "token_types": dict(sorted(tokens.items())),
        "files_with_token_types": dict(sorted(token_files.items())),
        "syntax_probe_file_counts": dict(sorted(probes.items())),
        "parsed_target_shapes": signatures(targets.elements()),
        "parsed_html_tag_counts": dict(sorted(html_tags.items())),
        "current_note_tracer": dict(sorted(trace.items())),
        "active_local_references": dict(sorted(local.items())),
    }


def inspect(path, label):
    output = {"archive": label, "bytes": path.stat().st_size}
    with path.open("rb") as stream:
        output["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    with ZipFile(path) as archive:
        infos = archive.infolist()
        names = set(archive.namelist())
        folded = [unicodedata.normalize("NFC", i.filename).casefold() for i in infos]
        resources = {i.filename for i in infos if "/" in i.filename and not i.is_dir()}
        roots = {i.filename for i in infos if "/" not in i.filename and not i.is_dir()}
        records, root_encoding = {}, {}
        for name in sorted(roots):
            raw = archive.read(name)
            if name.endswith(".json"):
                records[name] = decode_records(name, raw)[0]
                root_encoding[name] = {
                    "utf8_bom": raw.startswith(b"\xef\xbb\xbf"),
                    "has_crlf": b"\r\n" in raw,
                    "has_bare_cr": b"\r" in raw.replace(b"\r\n", b""),
                    "has_bare_lf": b"\n" in raw.replace(b"\r\n", b""),
                }
        meta = records["meta.json"][0]
        brain = meta["BrainId"]
        thoughts = {r["Id"]: r for r in records["thoughts.json"]}
        links, attachments = records["links.json"], records["attachments.json"]
        live_records = [r for n in ("thoughts.json", "links.json", "attachments.json") for r in records[n]]
        live_ids = {r["Id"] for r in live_records}
        state = meta["AttachmentFileStates"]
        output["exchange_format_version"] = meta["ExchangeFormatVersion"]
        output["zip"] = {
            "members": len(infos), "directories": sum(i.is_dir() for i in infos),
            "root_files": sorted(roots), "payload_files": len(resources),
            "root_files_match_v1_known_collections": roots == set(ROOT_FILES),
            "uncompressed_bytes": sum(i.file_size for i in infos),
            "crc_valid": archive.testzip() is None,
            "duplicate_or_case_ambiguous_names": len(folded) - len(set(folded)),
            "unsafe_members": sum(PurePosixPath(i.filename).is_absolute() or ".." in PurePosixPath(i.filename).parts or "\\" in i.filename or ":" in i.filename or str(PurePosixPath(i.filename)) != i.filename.removesuffix("/") for i in infos),
            "encrypted_members": sum(bool(i.flag_bits & 1) for i in infos),
            "symlink_members": sum(stat.S_ISLNK(i.external_attr >> 16) for i in infos),
            "compression_methods": counts(i.compress_type for i in infos),
            "payload_extensions": counts(PurePosixPath(n).suffix.lower() for n in resources),
            "payload_owner_directories": len({n.split("/")[0] for n in resources}),
            "root_encoding": root_encoding,
        }
        output["collections"] = {
            name: {
                "records": len(rs), "field_keys": sorted({k for r in rs for k in r}),
                "record_key_schemas": signatures(tuple(sorted(r)) for r in rs),
                "fields": fields(rs),
                "duplicate_ids": len([r for r in rs if "Id" in r]) - len({r["Id"] for r in rs if "Id" in r}),
                "foreign_brain_ids": sum("BrainId" in r and r["BrainId"] != brain for r in rs),
            } for name, rs in sorted(records.items())
        }
        output["identity"] = {
            "invalid_canonical_record_ids": sum(not UUID_PATTERN.fullmatch(r["Id"]) for rs in records.values() for r in rs if "Id" in r),
            "duplicate_live_ids_across_collections": len(live_records) - len(live_ids),
            "live_tombstone_overlap": len(live_ids & {r["Id"] for r in records["tombstones.json"]}),
            "nonlive_link_endpoints": sum(r[k] not in thoughts for r in links for k in ("ThoughtIdA", "ThoughtIdB")),
            "nonlive_attachment_owners": sum(r["SourceId"] not in thoughts for r in attachments),
            "state_ids_without_attachment": len(set(state) - {r["Id"] for r in attachments}),
            "nonlive_history_source_references": sum(r["SourceId"] not in live_ids for r in records["modificationlogs.json"]),
            "history_source_references_are_not_live_constraints": True,
        }
        categories = {
            "live_thought": set(thoughts),
            "live_link": {r["Id"] for r in links},
            "live_attachment": {r["Id"] for r in attachments},
            "brain_user_record": {r["Id"] for r in records["brainusers.json"]},
            "user": {r.get("UserId") for r in records["brainusers.json"]},
            "syncpoint": {r["Id"] for r in records["syncpoints.json"]},
            "tombstone": {r["Id"] for r in records["tombstones.json"]},
            "brain": {brain},
        }
        def reference_shape(value):
            if value is None or value == "":
                return shape(value)
            found = [kind for kind, values in categories.items() if value in values]
            return "+".join(found) if found else "other_uuid" if type(value) is str and UUID_PATTERN.fullmatch(value) else "non_uuid:" + shape(value)
        output["top_level_identifier_reference_joins"] = {
            name: {field: counts(reference_shape(r[field]) for r in rs if field in r)
                   for field in sorted({k for r in rs for k in r if k.endswith("Id") and k not in {"Id", "BrainId"}})}
            for name, rs in sorted(records.items())
        }
        edge_shapes = [(r["Kind"], r["Relation"], r["Meaning"], r["Direction"], thoughts.get(r["ThoughtIdA"], {}).get("Kind"), thoughts.get(r["ThoughtIdB"], {}).get("Kind")) for r in links]
        edges = [(r["ThoughtIdA"], r["ThoughtIdB"]) for r in links]
        hierarchy = [(r["ThoughtIdA"], r["ThoughtIdB"]) for r in links if (r["Meaning"], r["Relation"]) == (1, 1)]
        normal = [(r["ThoughtIdA"], r["ThoughtIdB"]) for r in links if r["Meaning"] == 1]
        parents = Counter(b for a, b in hierarchy)
        typed = [r for r in thoughts.values() if r.get("TypeId")]
        assignments = {(r["ThoughtIdA"], r["ThoughtIdB"]) for r in links if r["Meaning"] == 2}
        declared_assignments = {(r["TypeId"], r["Id"]) for r in typed}
        tag_arrays = [(tag, r["Id"]) for r in thoughts.values() for tag in r.get("TagIds", [])]
        tag_links = {(r["ThoughtIdA"], r["ThoughtIdB"]) for r in links if r["Meaning"] == 5}
        output["graph"] = {
            "thought_kinds": counts(r["Kind"] for r in thoughts.values()),
            "relationship_signatures_with_endpoint_kinds": signatures(edge_shapes),
            "self_links": sum(a == b for a, b in edges),
            "duplicate_ordered_endpoint_pairs": len(edges) - len(set(edges)),
            "isolated_thoughts": len(set(thoughts) - {v for edge in edges for v in edge}),
            "all_component_sizes": components(thoughts, edges),
            "normal_meaning_component_sizes": components(thoughts, normal),
            "normal_hierarchy_multi_parent_thoughts": sum(v > 1 for v in parents.values()),
            "normal_hierarchy_max_parents": max(parents.values(), default=0),
            "normal_hierarchy_cyclic_nodes": cyclic_nodes(thoughts, hierarchy),
            "populated_thought_type_id_count": len(typed),
            "type_id_missing_targets": sum(r["TypeId"] not in thoughts for r in typed),
            "type_id_endpoint_kinds": signatures((thoughts.get(r["TypeId"], {}).get("Kind"), r["Kind"]) for r in typed),
            "assignment_pairs_without_matching_type_id": len(assignments - declared_assignments),
            "type_id_pairs_without_matching_assignment": len(declared_assignments - assignments),
            "type_membership_sizes": sorted(Counter(r["TypeId"] for r in typed).values(), reverse=True),
            "kind2_populated_type_id_count": sum(r["Kind"] == 2 for r in typed),
            "meaning3_links": sum(r["Meaning"] == 3 for r in links),
            "link_type_identifier_fields_populated": sum(bool(r.get(k)) for r in links for k in ("TypeId", "LinkTypeId")),
            "tag_id_array_references": len(tag_arrays),
            "tag_id_missing_targets": sum(tag not in thoughts for tag, owner in tag_arrays),
            "tag_array_pairs_without_assignment": len(set(tag_arrays) - tag_links),
            "tag_assignment_pairs_without_array": len(tag_links - set(tag_arrays)),
            "forgotten_thoughts": sum("ForgottenDateTime" in r for r in thoughts.values()),
            "thought_label_field_count": sum("Label" in r for r in thoughts.values()),
            "named_link_count": sum("Name" in r for r in links),
            "thought_aliases_populated": sum(bool(r.get("Aliases")) for r in thoughts.values()),
            "exact_title_collisions": len(thoughts) - len({r["Name"] for r in thoughts.values()}),
            "casefold_title_collisions": len(thoughts) - len({r["Name"].casefold() for r in thoughts.values()}),
            "windows_invalid_title_characters": sum(bool(re.search(r'[<>:"/\\|?*]', r["Name"])) for r in thoughts.values()),
        }
        output["appearance"] = {
            "field_presence_by_kind": signatures((r["Kind"], "ForegroundColor" in r, "BackgroundColor" in r, "Label" in r) for r in thoughts.values()),
            "typed_ordinary_direct_foreground": sum("ForegroundColor" in r for r in typed if r["Kind"] == 1),
            "typed_ordinary_direct_background": sum("BackgroundColor" in r for r in typed if r["Kind"] == 1),
            "typed_ordinary_direct_label": sum("Label" in r for r in typed if r["Kind"] == 1),
            "typed_ordinary_own_icon_attachments": sum(a["Type"] == 5 and thoughts[a["SourceId"]].get("TypeId") is not None for a in attachments),
            "thought_icon_info_colon_token_shapes": signatures(tuple(shape(v) for v in r["ThoughtIconInfo"].split(":")) for r in thoughts.values()),
            "thought_icon_info_safe_token_values": {
                str(i): counts(v if re.fullmatch(r"-?\d+(?:\.\d+)?|True|False", v) else "empty" if not v else "redacted-string" for r in thoughts.values() for v in [r["ThoughtIconInfo"].split(":")[i]])
                for i in range(min(len(r["ThoughtIconInfo"].split(":")) for r in thoughts.values()))
            },
            "thought_icon_info_semantics": "opaque; no token meanings inferred",
        }
        setting_slots = {str(uuid5(UUID(brain), str(i))): i for i in range(1000)}
        settings = records["settings.json"]
        home = [r for r in settings if r["Id"] == str(uuid5(UUID(brain), "20"))]
        output["settings"] = {
            "matched_uuid5_numeric_names_0_to_999": sorted(setting_slots[r["Id"]] for r in settings if r["Id"] in setting_slots),
            "unmatched_id_count": sum(r["Id"] not in setting_slots for r in settings),
            "value_shapes_by_numeric_name": {str(setting_slots[r["Id"]]): shape(r.get("Value")) for r in settings if r["Id"] in setting_slots},
            "home_setting_count": len(home),
            "home_references_live_ordinary_thought": len(home) == 1 and home[0].get("Value") in thoughts and thoughts[home[0]["Value"]]["Kind"] == 1,
            "home_thought_has_type_id": len(home) == 1 and bool(thoughts.get(home[0].get("Value"), {}).get("TypeId")),
            "numeric_names_other_than_20_are_uninterpreted": True,
        }
        assigned, missing, length_mismatch, physical_multi = set(), [], Counter(), Counter()
        active_notes, generic_md = [], []
        owner_icons = Counter()
        video_tags, video_attrs, video_schemes = Counter(), Counter(), Counter()
        extrefs = []
        for r in attachments:
            if "VideoHtml" in r:
                hp = HtmlShape()
                hp.feed(r["VideoHtml"])
                video_tags.update(hp.tags)
                video_attrs.update(hp.attrs)
                video_schemes.update(hp.url_schemes)
            if r["Type"] in {3, 8}:
                extrefs.append(r)
                continue
            sub = ".data/md-images/" if r["Type"] == 12 else ".data/" if r["Type"] == 5 else ""
            member = r["SourceId"] + "/" + sub + r["Location"]
            if member not in resources:
                missing.append(r)
                continue
            assigned.add(member)
            physical_multi[member] += 1
            info = archive.getinfo(member)
            if info.file_size != r["DataLength"]:
                length_mismatch[r["Type"]] += 1
            if (r["Type"], r["NoteType"]) == (1, 4):
                active_notes.append((member, archive.read(member)))
            elif member.endswith(".md"):
                generic_md.append((member, archive.read(member)))
            if r["Type"] == 5:
                owner_icons[thoughts[r["SourceId"]]["Kind"]] += 1
        output["attachments"] = {
            "source_type_type_note_type_owner_kind_signatures": signatures((r["SourceType"], r["Type"], r["NoteType"], thoughts.get(r["SourceId"], {}).get("Kind")) for r in attachments),
            "type_note_extension_signatures": signatures((r["Type"], r["NoteType"], PurePosixPath(r["Location"]).suffix.lower() if r["Type"] not in {3, 8} else "external-reference") for r in attachments),
            "file_state_counts": counts(state.values()),
            "present_payload_records": len(attachments) - len(extrefs) - len(missing),
            "absent_payload_records": len(missing),
            "absent_type_note_state_extension_signatures": signatures((r["Type"], r["NoteType"], state.get(r["Id"]), PurePosixPath(r["Location"]).suffix.lower()) for r in missing),
            "absent_positive_length": sum(r["DataLength"] > 0 for r in missing),
            "absent_zero_length": sum(r["DataLength"] == 0 for r in missing),
            "absent_with_present_same_owner_pdf": sum(any(p["SourceId"] == r["SourceId"] and p["Type"] == 1 and p["Location"].lower().endswith(".pdf") and p["SourceId"] + "/" + p["Location"] in assigned for p in attachments) for r in missing),
            "present_payload_state_not_1": sum(state.get(r["Id"]) != 1 for r in attachments if r not in extrefs and r not in missing),
            "external_reference_count": len(extrefs),
            "external_reference_with_local_state": sum(r["Id"] in state for r in extrefs),
            "external_reference_uri_schemes": counts(urlsplit(r["Location"]).scheme.lower() for r in extrefs if r["Type"] == 3),
            "external_reference_without_http_https_host": sum(urlsplit(r["Location"]).scheme.lower() not in {"http", "https"} or not urlsplit(r["Location"]).netloc for r in extrefs if r["Type"] == 3),
            "unaccounted_payload_files": len(resources - assigned),
            "physical_members_assigned_more_than_once": sum(v > 1 for v in physical_multi.values()),
            "declared_length_mismatch_by_type": counts(length_mismatch.elements()),
            "icon_owner_kinds": counts(owner_icons.elements()),
            "active_note_owner_kinds": counts(thoughts[r["SourceId"]]["Kind"] for r in attachments if (r["Type"], r["NoteType"]) == (1, 4)),
            "nonempty_type1_note0_exact_Notes_md": sum(bool(archive.read(r["SourceId"] + "/Notes.md").decode("utf-8-sig")) for r in attachments if (r["Type"], r["NoteType"], r["Location"]) == (1, 0, "Notes.md")),
            "owners_with_multiple_note_or_Notes_md_records": sum(v > 1 for v in Counter(r["SourceId"] for r in attachments if r["Type"] == 1 and (r["NoteType"] == 4 or r["Location"] == "Notes.md")).values()),
            "VideoHtml_present_records": sum("VideoHtml" in r for r in attachments),
            "VideoHtml_nonempty_records": sum(bool(r.get("VideoHtml")) for r in attachments),
            "VideoHtml_attachment_signatures": signatures((r["SourceType"], r["Type"], r["NoteType"]) for r in attachments if "VideoHtml" in r),
            "VideoHtml_tag_counts": dict(sorted(video_tags.items())),
            "VideoHtml_attribute_counts": dict(sorted(video_attrs.items())),
            "VideoHtml_url_scheme_counts": dict(sorted(video_schemes.items())),
        }
        output["notes"] = {
            "active_thought_markdown": note_inventory(active_notes, thoughts, names),
            "generic_or_placeholder_markdown_files": note_inventory(generic_md, thoughts, names),
        }
        output["v1_compatibility"] = {
            "unreviewed_thought_role_records": sum(r["Kind"] not in {1, 4, 5} for r in thoughts.values()),
            "populated_custom_thought_type_records": len(typed),
            "unreviewed_link_signature_records": sum(sig not in REVIEWED_LINKS for sig in edge_shapes),
            "unreviewed_link_signatures": signatures(sig for sig in edge_shapes if sig not in REVIEWED_LINKS),
            "nonempty_unimplemented_collections": [n for n in ("calendarevents.json", "access.json", "fielddefinitions.json", "fieldinstances.json") if records[n]],
        }
        try:
            assets, documents, members, evidence, accounting, findings = normalize_attachments(archive, attachments, meta, thoughts, _refuse, _uuid)
            output["v1_compatibility"]["low_level_attachment_probe"] = {
                "status": "accepted", "assets": len(assets), "documents": len(documents),
                "findings": counts(f.kind for f in findings),
                "finding_rules": counts(f.rule_id for f in findings),
                "note_reference_kinds": counts(r.kind for d in documents for r in d.references),
                "VideoHtml_is_only_retained_original_metadata": True,
                "probe_does_not_validate_thought_roles_or_inheritance": True,
            }
        except MigrationRefused as error:
            output["v1_compatibility"]["low_level_attachment_probe"] = {"status": "refused", "codes": counts(i.code for i in error.issues)}
        # Diagnose every explicitly guarded new role/state and the remaining
        # subset. This is a probe only: exclusions do not authorize conversion.
        blockers = Counter()
        blocked_ids = set()
        for r in attachments:
            if r["Type"] == 15 and (r["DataLength"] <= 0 or state.get(r["Id"]) != 2 or not r["Location"].lower().endswith(".txt") or r["SourceId"] + "/" + r["Location"] in names):
                blockers["Type15_outside_reviewed_absent_TXT_predicate"] += 1
                blocked_ids.add(r["Id"])
            if (r["Type"], r["NoteType"], r["Location"]) == (1, 0, "Notes.md") and r["SourceId"] + "/Notes.md" in names and archive.read(r["SourceId"] + "/Notes.md").decode("utf-8-sig"):
                blockers["nonempty_Type1_NoteType0_Notes_md"] += 1
                blocked_ids.add(r["Id"])
        output["v1_compatibility"]["all_observed_guarded_attachment_blockers"] = dict(sorted(blockers.items()))
        if blocked_ids:
            subset = [r for r in attachments if r["Id"] not in blocked_ids]
            subset_meta = dict(meta, AttachmentFileStates={k: v for k, v in state.items() if k not in blocked_ids})
            try:
                assets, documents, members, evidence, accounting, findings = normalize_attachments(archive, subset, subset_meta, thoughts, _refuse, _uuid)
                output["v1_compatibility"]["attachment_subset_diagnostic"] = {
                    "excluded_records": len(blocked_ids), "status": "accepted",
                    "assets": len(assets), "documents": len(documents),
                    "findings": counts(f.kind for f in findings),
                    "note_reference_kinds": counts(r.kind for d in documents for r in d.references),
                    "unaccounted_payloads_in_excluded_subset": len(resources - set(members.values())),
                    "not_a_valid_complete_source_or_conversion": True,
                    "VideoHtml_only_retained_as_original_metadata": True,
                }
            except MigrationRefused as error:
                output["v1_compatibility"]["attachment_subset_diagnostic"] = {"excluded_records": len(blocked_ids), "status": "refused", "codes": counts(i.code for i in error.issues)}
    try:
        with BrzSourceModule().open(path) as session:
            output["v1_compatibility"]["source_reader_probe"] = {"status": "accepted", "items": len(session.snapshot.items)}
    except MigrationRefused as error:
        output["v1_compatibility"]["source_reader_probe"] = {"status": "refused", "codes": counts(i.code for i in error.issues)}
    with path.open("rb") as stream:
        output["source_fingerprint_unchanged_after_inspection"] = output["sha256"] == hashlib.file_digest(stream, "sha256").hexdigest()
    return output


def differences(archives):
    old, new = archives[:-1], archives[-1]
    result = {"baseline": [a["archive"] for a in old], "compared": new["archive"], "collections": {}}
    for name, collection in new["collections"].items():
        previous = [a["collections"].get(name, {"field_keys": [], "fields": {}}) for a in old]
        union = set().union(*(set(c["field_keys"]) for c in previous))
        current = set(collection["field_keys"])
        changed = {}
        for field in sorted(current & union):
            oldshapes = set().union(*(set(c["fields"].get(field, {}).get("shapes", {})) for c in previous))
            now = set(collection["fields"][field]["shapes"])
            oldvalues = set().union(*(set(c["fields"].get(field, {}).get("numeric_boolean_values", {})) for c in previous))
            newvalues = set(collection["fields"][field].get("numeric_boolean_values", {}))
            if now - oldshapes or newvalues - oldvalues:
                changed[field] = {"new_shapes": sorted(now - oldshapes), "new_numeric_boolean_values": sorted(newvalues - oldvalues)}
        result["collections"][name] = {
            "new_fields": sorted(current - union), "v1_fields_not_observed": sorted(union - current),
            "new_shapes_or_scalar_values": changed,
        }
    def new_signatures(section, field):
        baseline = {tuple(s["signature"]) for a in old for s in a[section][field]}
        return [s for s in new[section][field] if tuple(s["signature"]) not in baseline]
    result["new_link_signatures"] = new_signatures("graph", "relationship_signatures_with_endpoint_kinds")
    result["new_attachment_signatures"] = new_signatures("attachments", "source_type_type_note_type_owner_kind_signatures")
    result["new_resource_extensions"] = sorted(set(new["zip"]["payload_extensions"]) - set().union(*(set(a["zip"]["payload_extensions"]) for a in old)))
    result["new_setting_numeric_names"] = sorted(set(new["settings"]["matched_uuid5_numeric_names_0_to_999"]) - set().union(*(set(a["settings"]["matched_uuid5_numeric_names_0_to_999"]) for a in old)))
    result["new_active_note_token_types"] = sorted(set(new["notes"]["active_thought_markdown"]["token_types"]) - set().union(*(set(a["notes"]["active_thought_markdown"]["token_types"]) for a in old)))
    return result


def original_comparison(archives, path):
    """Compare only directly comparable fields; old regex probes were not parsers."""
    old = json.loads(path.read_text(encoding="utf-8-sig"))
    result = []
    for current in archives[:-1]:
        matches = [a for a in old if a["sha256"] == current["sha256"]]
        checks = {}
        if len(matches) == 1:
            previous = matches[0]
            checks["bytes"] = current["bytes"] == previous["bytes"]
            checks["zip_members"] = current["zip"]["members"] == previous["zip"]["members"]
            checks["uncompressed_bytes"] = current["zip"]["uncompressed_bytes"] == previous["zip"]["uncompressed_bytes"]
            checks["payload_extensions"] = current["zip"]["payload_extensions"] == previous["zip"]["resource_extensions"]
            checks["collection_counts"] = all(current["collections"][n]["records"] == c["records"] for n, c in previous["collections"].items())
            checks["collection_field_keys"] = all(current["collections"][n]["field_keys"] == c["field_keys"] for n, c in previous["collections"].items())
        result.append({"archive": current["archive"], "sha256_matches": len(matches), "checks": checks})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--original-inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if len(args.archives) < 2:
            raise ValueError("Need baseline and comparison archives")
        archives = [inspect(p, "v1_A" if i == 0 else "v1_B" if i == 1 else "v2_C") for i, p in enumerate(args.archives)]
        result = {
            "schema_version": 1,
            "privacy": "Counts, field names and value shapes only; source strings/URLs/IDs omitted.",
            "method": "Complete member CRC pass, strict CR/LF JSON decoding, live/payload/reference checks, current-reader probes; no conversion.",
            "archives": archives, "differences": differences(archives),
            "original_inventory_comparison": original_comparison(archives, args.original_inventory),
            "source_profile": {"id": BRZ_POLICY.profile_id, "version": BRZ_POLICY.profile_version},
            "reader_source_sha256": {
                name: hashlib.sha256((REPO / "src/brz2obsidian/sources/thebrain" / name).read_bytes()).hexdigest()
                for name in ("reader.py", "attachments.py", "decoding.py", "notes.py", "relationships.py", "semantics.py", "profile.py", "findings.py")
            },
        }
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print("Inventory written; " + ", ".join(a["archive"] + ": " + str(a["zip"]["members"]) + " members, CRC valid=" + str(a["zip"]["crc_valid"]) for a in archives))
    except Exception as error:
        # Exception values can contain private JSON, paths, URLs or identifiers.
        print("Inspection failed: " + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
