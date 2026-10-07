"""Read-only four-archive aggregate comparison; no extraction or conversion.

Run from the repository with .venv Python. Reuses the privacy-safe shape/Markdown
helpers from the v2 comparison and fingerprint-matched earlier CRC evidence.
All root records are rescanned; output has counts/shapes, no private strings/IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID, uuid5
from zipfile import ZipFile

REPO = Path(__file__).resolve().parents[4]
HELPER = REPO / "docs/history/brz-to-obsidian-v2/research/inspect_v2_archives.py"
spec = importlib.util.spec_from_file_location("prior_inventory", HELPER)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
from brz2obsidian.contracts import Document, MigrationRefused
from brz2obsidian.sources.thebrain.attachments import SPECIAL_FLAGS
from brz2obsidian.sources.thebrain.classifications import decode_classifications
from brz2obsidian.sources.thebrain.decoding import ROOT_FILES, decode_records
from brz2obsidian.sources.thebrain.metadata import calendar_dates, declared_appearance
from brz2obsidian.sources.thebrain.notes import (
    bind_note_references,
    trace_note_references,
)
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from brz2obsidian.sources.thebrain.relationships import decode_relationships
from brz2obsidian.sources.thebrain.semantics import validate_semantic_fields
from brz2obsidian.sources.thebrain.videos import reviewed_video


def fingerprint(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def refuse(code, message, affected=()):
    raise ValueError(code)


def guid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("invalid_source")
    return value


def member(record):
    prefix = (
        ".data/"
        if record["Type"] == 5
        else ".data/md-images/"
        if record["Type"] == 12
        else ""
    )
    return record["SourceId"] + "/" + prefix + record["Location"]


def inspect(path, label, evidence):
    digest = fingerprint(path)
    matched = evidence.get(digest)
    if matched is None:
        raise ValueError("No fingerprint-matched CRC evidence")
    failures = Counter()

    def check(name, fn):
        try:
            return fn()
        except ValueError, AssertionError, MigrationRefused:
            failures[name] += 1
            return None

    with ZipFile(path) as archive:
        infos = archive.infolist()
        names = set(archive.namelist())
        payloads = {i.filename for i in infos if not i.is_dir() and "/" in i.filename}
        roots = {i.filename for i in infos if not i.is_dir() and "/" not in i.filename}
        raw = {n: decode_records(n, archive.read(n))[0] for n in sorted(roots)}
        meta = raw["meta.json"][0]
        brain = meta["BrainId"]
        thoughts = {r["Id"]: r for r in raw["thoughts.json"]}
        links, attachments = raw["links.json"], raw["attachments.json"]
        states = meta["AttachmentFileStates"]
        live = [
            r
            for n in ("thoughts.json", "links.json", "attachments.json")
            for r in raw[n]
        ]
        live_ids = {r["Id"] for r in live}
        icons = [
            SimpleNamespace(owner=a["SourceId"], role="icon", asset_id=a["Id"])
            for a in attachments
            if a["Type"] == 5
        ]
        images = [
            SimpleNamespace(
                owner=a["SourceId"],
                role="image",
                asset_id=a["Id"],
                original_name=a["Location"],
                availability="present",
            )
            for a in attachments
            if a["Type"] == 12 and member(a) in payloads
        ]
        decoded = []
        for r in links:
            result = check(
                "relationship",
                lambda r=r: decode_relationships([r], thoughts, brain, refuse, guid),
            )
            if result:
                decoded.extend(result)
        classifications = check(
            "classification_join",
            lambda: decode_classifications(thoughts, decoded, refuse, guid),
        )
        for r in thoughts.values():
            check(
                "thought_role_access",
                lambda r=r: (
                    refuse("unsupported_feature", "role")
                    if type(r.get("Kind")) is not int
                    or r["Kind"] not in {1, 2, 4, 5}
                    or type(r.get("ACType", 0)) is not int
                    or r.get("ACType", 0) != 0
                    else None
                ),
            )
            check(
                "thought_semantics",
                lambda r=r: validate_semantic_fields(
                    r, refuse, known_type_fields=("TypeId",)
                ),
            )
            check("calendar_dates", lambda r=r: calendar_dates(r, refuse))
            check(
                "declared_appearance", lambda r=r: declared_appearance(r, icons, refuse)
            )
        local = [a for a in attachments if a["Type"] not in {3, 8}]
        present = [a for a in local if member(a) in payloads]
        absent = [a for a in local if member(a) not in payloads]
        external = [a for a in attachments if a["Type"] in {3, 8}]
        assigned = Counter(member(a) for a in present)
        docs, placeholders = [], []
        warnings = Counter()
        candidates = Counter(
            a["SourceId"]
            for a in attachments
            if a["Type"] == 1 and (a["NoteType"] == 4 or a["Location"] == "Notes.md")
        )
        videos = 0
        for a in attachments:
            check(
                "attachment_semantics",
                lambda a=a: validate_semantic_fields(
                    a, refuse, ("IsIcon",) + SPECIAL_FLAGS
                ),
            )
            video = check("video_metadata", lambda a=a: reviewed_video(a, refuse))
            videos += bool(video)

            def validate_attachment(a=a):
                if (
                    any(
                        type(a.get(k)) is not int
                        for k in ("SourceType", "Type", "NoteType", "DataLength")
                    )
                    or a["DataLength"] < 0
                ):
                    raise ValueError("scalar")
                if a["SourceType"] != 2 or (a["Type"], a["NoteType"]) not in {
                    (1, 4),
                    (1, 0),
                    (3, 0),
                    (5, 0),
                    (8, 0),
                    (12, 0),
                    (15, 0),
                }:
                    raise ValueError("role")
                if (
                    any(
                        k in a and type(a[k]) is not bool
                        for k in ("IsIcon",) + SPECIAL_FLAGS
                    )
                    or any(a.get(k) for k in SPECIAL_FLAGS)
                    or a.get("IsIcon", False) != (a["Type"] == 5)
                ):
                    raise ValueError("flag")
                if type(a["Location"]) is not str or not a["Location"]:
                    raise ValueError("location")
                if a["Type"] == 3:
                    uri = urlsplit(a["Location"])
                    if (
                        uri.scheme.casefold() not in {"http", "https"}
                        or not uri.netloc
                        or a["Id"] in states
                        or any(ord(c) < 32 or c in "<>" for c in a["Location"])
                    ):
                        raise ValueError("external")
                elif a["Type"] != 8:
                    location = a["Location"]
                    if (
                        PurePosixPath(location).is_absolute()
                        or any(p in {".", "..", ""} for p in location.split("/"))
                        or "\\" in location
                        or ":" in location
                    ):
                        raise ValueError("path")
                    if a["Type"] != 15 and (
                        states.get(a["Id"]) != 1 or member(a) not in payloads
                    ):
                        raise ValueError("missing_required_payload")

            check("attachment_role_path_state", validate_attachment)
            if a in present:
                size = archive.getinfo(member(a)).file_size
                if size != a["DataLength"]:
                    warnings[
                        "icon_length" if a["Type"] == 5 else "UNAPPROVED_length"
                    ] += 1
                if a["Type"] == 1 and (
                    a["NoteType"] == 4 or a["Location"] == "Notes.md"
                ):
                    data = archive.read(member(a))
                    text = data.decode("utf-8-sig")
                    refs = check(
                        "note_trace", lambda text=text: trace_note_references(text)
                    )
                    if refs is not None:
                        doc = Document(
                            key=a["Id"],
                            owner=a["SourceId"],
                            text=text,
                            text_digest=hashlib.sha256(data).hexdigest(),
                            original_asset_id=a["Id"],
                            references=refs,
                        )
                        check(
                            "note_reference_bind",
                            lambda doc=doc: bind_note_references(doc, images, thoughts),
                        )
                    if (
                        a["NoteType"] == 0
                        and text
                        and thoughts[a["SourceId"]]["Kind"] != 1
                    ):
                        failures["nonordinary_note0_active"] += 1
                    (docs if a["NoteType"] == 4 else placeholders).append(
                        (member(a), data)
                    )
            if a["Type"] == 15:
                intact = [
                    p
                    for p in present
                    if p["SourceId"] == a["SourceId"]
                    and (p["Type"], p["NoteType"]) == (1, 0)
                    and PurePosixPath(p["Location"]).suffix.casefold() == ".pdf"
                    and states.get(p["Id"]) == 1
                    and archive.getinfo(member(p)).file_size == p["DataLength"]
                ]
                okay = (
                    a in absent
                    and states.get(a["Id"]) == 2
                    and PurePosixPath(a["Location"]).suffix.casefold() == ".txt"
                    and (
                        bool(intact)
                        if a["DataLength"] > 0
                        else sum(
                            p["Id"] == PurePosixPath(a["Location"]).stem for p in intact
                        )
                        == 1
                    )
                )
                (warnings if okay else failures)[
                    (
                        "positive_absent_txt"
                        if a["DataLength"] > 0
                        else "zero_absent_txt"
                    )
                    if okay
                    else "Type15_outside_reviewed_rule"
                ] += 1
        for state in states.values():
            if type(state) is not int or state not in {1, 2}:
                failures["unsupported_global_file_state"] += 1
        categories = {
            "live_thought": set(thoughts),
            "live_link": {r["Id"] for r in links},
            "live_attachment": {a["Id"] for a in attachments},
            "brain": {brain},
            "brain_user_record": {r["Id"] for r in raw["brainusers.json"]},
            "user": {r.get("UserId") for r in raw["brainusers.json"]},
            "syncpoint": {r["Id"] for r in raw["syncpoints.json"]},
            "tombstone": {r["Id"] for r in raw["tombstones.json"]},
        }

        def reference_shape(v):
            if not v:
                return prior.shape(v)
            found = [k for k, values in categories.items() if v in values]
            return (
                "+".join(found)
                if found
                else "other_uuid"
                if type(v) is str and prior.UUID_PATTERN.fullmatch(v)
                else "non_uuid:" + prior.shape(v)
            )

        joins = {
            n: {
                k: prior.counts(reference_shape(r[k]) for r in rs if k in r)
                for k in sorted(
                    {
                        k
                        for r in rs
                        for k in r
                        if k.endswith("Id") and k not in {"Id", "BrainId"}
                    }
                )
            }
            for n, rs in raw.items()
        }
        hierarchy = [
            (r["ThoughtIdA"], r["ThoughtIdB"])
            for r in links
            if (r["Relation"], r["Meaning"]) == (1, 1)
        ]
        parents = Counter(b for a, b in hierarchy)
        assignments = Counter(
            (r["ThoughtIdA"], r["ThoughtIdB"]) for r in links if r["Meaning"] == 2
        )
        declared = Counter(
            (r["TypeId"], r["Id"]) for r in thoughts.values() if r.get("TypeId")
        )
        special = [
            r
            for r in links
            if (thoughts[r["ThoughtIdA"]]["Kind"], thoughts[r["ThoughtIdB"]]["Kind"])
            == (1, 2)
            and (r["Kind"], r["Relation"], r["Meaning"], r["Direction"])
            == (1, 1, 1, -1)
        ]
        home = [
            r for r in raw["settings.json"] if r["Id"] == str(uuid5(UUID(brain), "20"))
        ]
        slots = {str(uuid5(UUID(brain), str(i))): i for i in range(1000)}
        result = {
            "archive": label,
            "filename": path.name,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "exchange_format": meta["ExchangeFormatVersion"],
            "integrity_evidence_reused": matched,
            "zip": {
                "members": len(infos),
                "payload_files": len(payloads),
                "uncompressed_bytes": sum(i.file_size for i in infos),
                "known_roots_exact": roots == set(ROOT_FILES),
                "payload_extensions": prior.counts(
                    PurePosixPath(n).suffix.casefold() for n in payloads
                ),
                "root_encoding": {
                    n: {
                        "utf8_bom": archive.read(n).startswith(b"\xef\xbb\xbf"),
                        "crlf": b"\r\n" in archive.read(n),
                        "bare_cr": b"\r" in archive.read(n).replace(b"\r\n", b""),
                        "bare_lf": b"\n" in archive.read(n).replace(b"\r\n", b""),
                    }
                    for n in sorted(roots)
                },
            },
            "collections": {
                n: {
                    "records": len(rs),
                    "field_keys": sorted({k for r in rs for k in r}),
                    "record_key_schemas": prior.signatures(
                        tuple(sorted(r)) for r in rs
                    ),
                    "fields": prior.fields(rs),
                    "duplicate_ids": len([r for r in rs if "Id" in r])
                    - len({r["Id"] for r in rs if "Id" in r}),
                }
                for n, rs in raw.items()
            },
            "joins": joins,
            "identity": {
                "duplicate_live_ids": len(live) - len(live_ids),
                "noncanonical_ids": sum(
                    type(r["Id"]) is not str
                    or not prior.UUID_PATTERN.fullmatch(r["Id"])
                    for rs in raw.values()
                    for r in rs
                    if "Id" in r
                ),
                "live_deleted_overlap": len(
                    live_ids & {r["Id"] for r in raw["tombstones.json"]}
                ),
                "foreign_brain_owners": sum(
                    r.get("BrainId", brain) != brain for rs in raw.values() for r in rs
                ),
                "nonlive_endpoints": sum(
                    r[k] not in thoughts
                    for r in links
                    for k in ("ThoughtIdA", "ThoughtIdB")
                ),
                "nonlive_attachment_owners": sum(
                    a["SourceId"] not in thoughts for a in attachments
                ),
                "unmatched_state_ids": len(
                    set(states) - {a["Id"] for a in attachments}
                ),
                "unaccounted_payloads": len(payloads - set(assigned)),
                "ambiguous_payload_assignments": sum(v > 1 for v in assigned.values()),
                "home_valid": len(home) == 1
                and thoughts.get(home[0].get("Value"), {}).get("Kind") == 1,
            },
            "graph": {
                "thought_kinds": prior.counts(t["Kind"] for t in thoughts.values()),
                "relationship_signatures": prior.signatures(
                    (
                        r["Kind"],
                        r["Relation"],
                        r["Meaning"],
                        r["Direction"],
                        thoughts[r["ThoughtIdA"]]["Kind"],
                        thoughts[r["ThoughtIdB"]]["Kind"],
                    )
                    for r in links
                ),
                "classifications": len(classifications or []),
                "type_field_link_multiplicity_matches": assignments == declared,
                "type_hierarchy_meaning3": sum(r["Meaning"] == 3 for r in links),
                "tag_membership_arrays": sum(
                    len(t.get("TagIds", [])) for t in thoughts.values()
                ),
                "custom_link_types": sum(
                    bool(r.get("TypeId") or r.get("LinkTypeId")) for r in links
                ),
                "ordinary_type_hierarchy": {
                    "links": len(special),
                    "parents": len({r["ThoughtIdA"] for r in special}),
                    "type_children": len({r["ThoughtIdB"] for r in special}),
                    "typed_ordinary_parents": len(
                        {
                            r["ThoughtIdA"]
                            for r in special
                            if thoughts[r["ThoughtIdA"]].get("TypeId")
                        }
                    ),
                },
                "multi_parent_hierarchy_items": sum(v > 1 for v in parents.values()),
                "max_hierarchy_parents": max(parents.values(), default=0),
                "hierarchy_cyclic_nodes": prior.cyclic_nodes(thoughts, hierarchy),
                "self_links": sum(r["ThoughtIdA"] == r["ThoughtIdB"] for r in links),
                "exact_title_collisions": len(thoughts)
                - len({t["Name"] for t in thoughts.values()}),
            },
            "appearance": {
                "field_presence_by_role": prior.signatures(
                    (
                        t["Kind"],
                        bool(t.get("TypeId")),
                        "ForegroundColor" in t,
                        "BackgroundColor" in t,
                        "Label" in t,
                    )
                    for t in thoughts.values()
                ),
                "icon_declarations_by_owner_role": prior.counts(
                    thoughts[a["SourceId"]]["Kind"]
                    for a in attachments
                    if a["Type"] == 5
                ),
                "typed_ordinary_own_icons": sum(
                    a["Type"] == 5 and bool(thoughts[a["SourceId"]].get("TypeId"))
                    for a in attachments
                ),
                "opaque_icon_token_shapes": prior.signatures(
                    tuple(
                        prior.shape(v) for v in t.get("ThoughtIconInfo", "").split(":")
                    )
                    for t in thoughts.values()
                ),
            },
            "settings": {
                "matched_numeric_names": sorted(
                    slots[r["Id"]] for r in raw["settings.json"] if r["Id"] in slots
                ),
                "value_shapes_by_numeric_name": {
                    str(slots[r["Id"]]): prior.shape(r.get("Value"))
                    for r in raw["settings.json"]
                    if r["Id"] in slots
                },
                "unmatched_setting_ids": sum(
                    r["Id"] not in slots for r in raw["settings.json"]
                ),
                "names_other_than20_uninterpreted": True,
            },
            "history": {
                "nonlive_modification_source_refs": sum(
                    r["SourceId"] not in live_ids for r in raw["modificationlogs.json"]
                ),
                "retained_evidence_only": True,
            },
            "attachments": {
                "ownership_signatures": prior.signatures(
                    (
                        a["SourceType"],
                        a["Type"],
                        a["NoteType"],
                        thoughts[a["SourceId"]]["Kind"],
                    )
                    for a in attachments
                ),
                "state_role_presence": prior.signatures(
                    (
                        a["Type"],
                        a["NoteType"],
                        states.get(a["Id"]),
                        member(a) in payloads,
                    )
                    for a in local
                ),
                "states": prior.counts(states.values()),
                "present": len(present),
                "present_bytes": sum(
                    archive.getinfo(member(a)).file_size for a in present
                ),
                "absent": len(absent),
                "external": len(external),
                "external_schemes": prior.counts(
                    urlsplit(a["Location"]).scheme.casefold() for a in external
                ),
                "canonical_note_candidates_by_role_marker_presence": prior.signatures(
                    (thoughts[a["SourceId"]]["Kind"], a["NoteType"], a in present)
                    for a in attachments
                    if a["Type"] == 1
                    and (a["NoteType"] == 4 or a["Location"] == "Notes.md")
                ),
                "competing_note_owners": sum(v > 1 for v in candidates.values()),
                "reviewed_videos": videos,
            },
            "notes": {
                "marked_present": prior.note_inventory(docs, thoughts, names),
                "canonical_note0_present": prior.note_inventory(
                    placeholders, thoughts, names
                ),
            },
            "guard_failures": dict(sorted(failures.items())),
            "approved_warning_predicates": dict(sorted(warnings.items())),
            "unsupported_nonempty_collections": [
                n
                for n in (
                    "calendarevents.json",
                    "access.json",
                    "fielddefinitions.json",
                    "fieldinstances.json",
                )
                if raw[n]
            ],
        }
    result["fingerprint_unchanged_after_scan"] = fingerprint(path) == digest
    if not result["fingerprint_unchanged_after_scan"]:
        raise ValueError("source changed")
    return result


def differences(archives):
    old, new = archives[:-1], archives[-1]
    result = {"collections": {}}
    for name, c in new["collections"].items():
        previous = [a["collections"][name] for a in old]
        union = set().union(*(set(p["field_keys"]) for p in previous))
        changes = {}
        for k in sorted(set(c["field_keys"]) & union):
            current = c["fields"][k]
            earlier = [p["fields"].get(k, {}) for p in previous]
            shapes = set().union(*(set(e.get("shapes", {})) for e in earlier))
            numbers = set().union(
                *(set(e.get("numeric_boolean_values", {})) for e in earlier)
            )
            delta = {
                "new_shapes": sorted(set(current["shapes"]) - shapes),
                "new_numeric_boolean_values": sorted(
                    set(current.get("numeric_boolean_values", {})) - numbers
                ),
                "new_omission": bool(current["absent"])
                and not any(e.get("absent") for e in earlier),
                "new_null": bool(current["null"])
                and not any(e.get("null") for e in earlier),
            }
            if any(delta.values()):
                changes[k] = delta
        earlier_schemas = {
            tuple(s["signature"]) for p in previous for s in p["record_key_schemas"]
        }
        result["collections"][name] = {
            "new_fields": sorted(set(c["field_keys"]) - union),
            "earlier_fields_not_observed": sorted(union - set(c["field_keys"])),
            "field_shape_scalar_omission_null_delta": changes,
            "novel_record_key_schemas": [
                s
                for s in c["record_key_schemas"]
                if tuple(s["signature"]) not in earlier_schemas
            ],
        }
    for section, field in (
        ("graph", "relationship_signatures"),
        ("attachments", "ownership_signatures"),
        ("attachments", "state_role_presence"),
        ("appearance", "field_presence_by_role"),
    ):
        known = {tuple(s["signature"]) for a in old for s in a[section][field]}
        result[section + "_" + field] = [
            s for s in new[section][field] if tuple(s["signature"]) not in known
        ]
    result["novel_payload_extensions"] = sorted(
        set(new["zip"]["payload_extensions"])
        - set().union(*(set(a["zip"]["payload_extensions"]) for a in old))
    )
    result["novel_settings_numeric_names"] = sorted(
        set(new["settings"]["matched_numeric_names"])
        - set().union(*(set(a["settings"]["matched_numeric_names"]) for a in old))
    )
    result["settings_new_value_shapes"] = {
        k: v
        for k, v in new["settings"]["value_shapes_by_numeric_name"].items()
        if v not in {a["settings"]["value_shapes_by_numeric_name"].get(k) for a in old}
    }
    result["novel_icon_token_shapes"] = [
        s
        for s in new["appearance"]["opaque_icon_token_shapes"]
        if tuple(s["signature"])
        not in {
            tuple(e["signature"])
            for a in old
            for e in a["appearance"]["opaque_icon_token_shapes"]
        }
    ]
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    prior_path = (
        REPO / "docs/history/brz-to-obsidian-v2/research/aggregate-feature-inventory.json"
    )
    baseline = json.loads(prior_path.read_text(encoding="utf-8"))
    evidence = {
        a["sha256"]: {
            "report": "docs/history/brz-to-obsidian-v2/research/aggregate-feature-inventory.json",
            "crc_valid": a["zip"]["crc_valid"],
        }
        for a in baseline["archives"]
    }
    # Original exact-input inventory fingerprint/CRC are recorded in the durable
    # assessment; this does not rely on its deliberately incomplete subset.
    evidence["2b24c1d21b4090f3b0ed3ec0227f269b8c7a4e5b6832ada0e244a1dcfc941ced"] = {
        "report": "docs/history/management-leadership-wayfinding/research/archive-coverage.md",
        "crc_valid": True,
    }
    filenames = [
        "D&D_ The Rise of Anzoras 2026-10-03.brz",
        "Dungeons & Dragons 2026-10-03.brz",
        "Software Engineering 2026-10-04.brz",
        "Management & Leadership 2026-10-05.brz",
    ]
    archives = [
        inspect(REPO / "brz" / f, label, evidence)
        for f, label in zip(filenames, "ABCD", strict=True)
    ]
    result = {
        "schema_version": 1,
        "privacy": "Only aggregate field names, shape/count distributions, safe numeric scalars and source filenames/fingerprints; no private titles, note text, URLs or record IDs.",
        "method": "All thirteen complete root collections and present note bytes rescanned; prior whole-archive CRC evidence reused only after exact SHA-256 match; no conversions, extraction or mutations. Per-record guards are compatibility diagnostics, not an independent preservation oracle.",
        "profile": {"id": BRZ_POLICY.profile_id, "version": BRZ_POLICY.profile_version},
        "archives": archives,
        "differences": differences(archives),
        "tooling_sha256": {
            "prior_inspector": fingerprint(HELPER),
            "current_inspector": fingerprint(Path(__file__)),
        },
        "adapter_sha256": {
            f.name: fingerprint(f)
            for f in sorted((REPO / "src/brz2obsidian/sources/thebrain").glob("*.py"))
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "Four-archive aggregate written; "
        + "; ".join(
            a["archive"] + " failures=" + str(a["guard_failures"]) for a in archives
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 -- privacy boundary suppresses private values
        # Do not print exception arguments, which may include private values.
        print("Inspection failed: " + type(error).__name__)
        raise SystemExit(1)
