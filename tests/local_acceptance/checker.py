"""Independent acceptance oracle. Imports no converter modules.

Direct archive records/bytes are authoritative. The migration record supplies
assignments to audit, never the expected source data, eligibility or graph.
"""

import base64
import hashlib
import html
import json
import posixpath
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import quote, unquote
from uuid import UUID, uuid5
from zipfile import ZipFile

from .facts import (
    classifications,
    identities,
    note_ids,
    relationships,
    video,
    zero_txt_observation,
)
from .facts import (
    member as raw_member,
)
from .gaps import derive_gaps, diagnostic_targets
from .scope import dump_json, scope
from .support import check_support_content

ROOTS = (
    "meta.json",
    "thoughts.json",
    "links.json",
    "attachments.json",
    "settings.json",
    "modificationlogs.json",
    "brainusers.json",
    "syncpoints.json",
    "tombstones.json",
    "calendarevents.json",
    "access.json",
    "fielddefinitions.json",
    "fieldinstances.json",
)


def load_json(raw):
    def unique(pairs):
        values = dict(pairs)
        assert len(values) == len(pairs), "duplicate JSON keys"
        return values

    return json.loads(
        raw,
        parse_float=Decimal,
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(
            AssertionError("nonfinite JSON")
        ),
    )


def semantic(value):
    if isinstance(value, dict):
        return ("object", tuple(sorted((k, semantic(v)) for k, v in value.items())))
    if isinstance(value, list):
        return ("array", tuple(map(semantic, value)))
    if type(value) in {int, Decimal}:
        return ("number", Decimal(value))
    return (type(value).__name__, value)


def read_source(archive):
    records = {}
    for name in ROOTS:
        text = archive.read(name).decode("utf-8-sig")
        records[name] = (
            [load_json(text)]
            if name == "meta.json"
            else [
                load_json(line)
                for line in re.split(r"\r\n|\r|\n", text)
                if line.strip()
            ]
        )
    return records


def check_vault(source, vault):
    vault = Path(vault)
    record = load_json((vault / "migration-record.json").read_bytes())
    assert set(record) == {
        "schema",
        "schema_version",
        "converter_version",
        "renderer_version",
        "source_identity",
        "profile_id",
        "profile_version",
        "run_metadata",
        "item_targets",
        "asset_targets",
        "relationships",
        "tag_memberships",
        "classification_assignments",
        "source_gaps",
        "generated_presentations",
        "support_artifacts",
        "reserved_support_paths",
        "adaptations",
        "source_accounting",
        "issues",
        "counts",
        "obsidian_configuration",
        "obsidian_core_plugins_configuration",
        "obsidian_templates_configuration",
        "obsidian_property_types_configuration",
        "original_evidence",
    }, "migration record schema fields"
    assert (record["schema"], record["schema_version"]) == (
        "brz2obsidian.migration",
        5,
    ), "record schema version"
    assert (
        record["converter_version"]
        == record["run_metadata"]["converter_version"]
        == "0.3.0"
    ), "converter version"
    assert (
        record["renderer_version"] == record["run_metadata"]["renderer_version"] == "5"
    ), "renderer version"
    with Path(source).open("rb") as stream:
        assert (
            record["source_identity"]["source_sha256"]
            == hashlib.file_digest(stream, "sha256").hexdigest()
        ), "source fingerprint"
    with ZipFile(source) as archive:
        assert archive.testzip() is None, "source CRC"
        archive_names = archive.namelist()
        assert len(
            {unicodedata.normalize("NFC", n).casefold() for n in archive_names}
        ) == len(archive_names), "raw unique physical ZIP identities"
        for info in archive.infolist():
            name = info.filename.rstrip("/")
            assert (
                name
                and str(PurePosixPath(name)) == name
                and not PurePosixPath(name).is_absolute()
                and not set(name.split("/")) & {"", ".", ".."}
                and "\\" not in name
                and ":" not in name
                and not info.flag_bits & 1
                and (info.external_attr >> 16) & 0o170000 != 0o120000
            ), "raw safe physical ZIP member"
        raw = scope(read_source(archive), archive)
        derive_gaps(raw, archive)
        bindings = {
            a["Id"]: {
                "asset_id": a["Id"],
                "owner": a["SourceId"],
                "role": "image" if a["Type"] == 12 else "other",
                "original_name": a["Location"],
            }
            for a in raw["attachments.json"]
        }
        for a in raw["attachments.json"]:
            if (
                a["Type"] == 1
                and (a["NoteType"] == 4 or a["Location"] == "Notes.md")
                and raw_member(a) in archive.namelist()
            ):
                body = archive.read(raw_member(a)).decode("utf-8-sig")
                removals = [
                    r
                    for r in source_references(
                        body, a["SourceId"], bindings, raw.excluded
                    )
                    if r["kind"] == "item" and r["target"] in raw.excluded
                ]
                if removals or any(token in body for token in raw.tokens):
                    raw.unsafe_originals.add(a["Id"])
                for r in reversed(removals):
                    body = body[: r["start"]] + body[r["end"] :]
                assert not raw.unsafe(body), (
                    "residual excluded identity in supplied body"
                )
                raw.documents[a["Id"]] = body
        assert (
            record["source_identity"]["source_id"] == raw["meta.json"][0]["BrainId"]
            and record["source_identity"]["format_version"] == "5"
        ), "collection source identity"
        assert (
            record["source_identity"]["module_id"] == "thebrain-brz"
            and record["source_identity"]["module_version"] == "5"
        ), "source module identity"
        assert (record["profile_id"], record["profile_version"]) == (
            "thebrain-format5-reviewed",
            "5",
        ), "reviewed source profile"
        originals = {e["key"]: e for e in record["original_evidence"]}
        for name in ROOTS:
            assert semantic(originals[name]["records"]) == semantic(raw[name]), (
                "original JSON"
            )
        targets = {a["asset_id"]: a for a in record["asset_targets"]}
        checked = set()
        digest_parts = []
        for name in ROOTS:
            text = archive.read(name).decode("utf-8-sig")
            digest_parts.append(
                dump_json(raw[name])
                if raw.excluded
                else "["
                + ",".join(
                    [text]
                    if name == "meta.json"
                    else [
                        line
                        for line in re.split(r"\r\n|\r|\n", text)
                        if line.strip(" \t")
                    ]
                )
                + "]"
            )
        for attachment in raw["attachments.json"]:
            kind = attachment["Type"]
            if (
                kind in {3, 8, 15}
                or attachment["Id"] in raw.unsafe_originals
                or attachment["Id"] in raw.gaps
            ):
                continue
            prefix = ".data/" if kind == 5 else ".data/md-images/" if kind == 12 else ""
            member = attachment["SourceId"] + "/" + prefix + attachment["Location"]
            assert attachment["Id"] in targets, "required safe payload identity"
            assigned = targets[attachment["Id"]]
            assert (
                assigned["relative_path"] is not None
                and (vault / assigned["relative_path"]).is_file()
            ), "required safe payload file"
            actual = (vault / assigned["relative_path"]).read_bytes()
            assert actual == archive.read(member), "payload bytes"
            assert assigned["actual_length"] == len(actual), "payload length"
            assert assigned["actual_sha256"] == hashlib.sha256(actual).hexdigest(), (
                "payload digest"
            )
            assert originals["payload:" + member]["records"] == {
                "member": member,
                "length": len(actual),
                "sha256": hashlib.sha256(actual).hexdigest(),
            }, "payload original evidence"
            digest_parts.append(
                json.dumps(
                    {
                        "member": member,
                        "length": len(actual),
                        "sha256": hashlib.sha256(actual).hexdigest(),
                    }
                )
            )
            checked.add(member)
        assert (
            record["source_identity"]["snapshot_digest"]
            == hashlib.sha256("".join(digest_parts).encode()).hexdigest()
        ), "raw-derived scoped digest"
        assert checked == {
            n
            for n in archive.namelist()
            if n not in ROOTS
            and not n.endswith("/")
            and n not in raw.dropped_members
            and n
            not in {
                raw_member(a)
                for a in raw["attachments.json"]
                if a["Id"] in raw.unsafe_originals
            }
        }, "payload accounting"
        asset_summary = check_assets(raw, record, archive, vault, targets)
        summary, documents, names = check_items(raw, record, archive, vault, targets)
        created = {t["item_key"] for t in record["item_targets"] if t["created"]}
        diagnostics, presentations = diagnostic_targets(
            raw,
            names,
            created,
            {k: expected_metadata(raw, k, targets)[2] for k in created},
        )
        for presentation in presentations:
            presentation["image_paths"] = [
                targets[k]["relative_path"]
                for k in presentation["presentation"]["image_asset_ids"]
            ]
        assert record["source_gaps"] == diagnostics, (
            "complete raw-derived source-gap diagnostics"
        )
        assert record["generated_presentations"] == presentations, (
            "complete raw-derived generated presentations"
        )
        summary["source_gaps"] = len(raw.gaps)
        summary["generated_embeds"] = sum(len(g["images"]) for g in raw.gaps.values())
        summary["decoded_image_frames"] = sum(
            len(p["frames"]) for p in raw.image_decodes.values()
        )
        summary["image_decoder_capabilities"] = sorted(
            {json.dumps(p["codec"], sort_keys=True) for p in raw.image_decodes.values()}
        )
        references = check_documents(raw, record, documents, names, targets)
        summary.update(asset_summary)
        check_accounting(raw, record, checked, references)
        files = check_actual_files(vault, record, targets, names, raw, summary)
        check_adaptations(raw, record, documents, names, targets)
        check_counts(raw, record, summary, references, targets, files)
        check_report(vault, raw, record, names, targets, summary, len(checked))
    return {
        "source_items": len(raw["thoughts.json"]),
        **{
            label + "_items": sum(t["Kind"] == kind for t in raw["thoughts.json"])
            for label, kind in (
                ("ordinary", 1),
                ("definition", 2),
                ("tag", 4),
                ("system", 5),
            )
        },
        "source_relationships": len(raw["links.json"]),
        "ordinary_category_hierarchy": sum(
            r["Meaning"] == 1
            and r["Relation"] == 1
            and next(
                t["Kind"] for t in raw["thoughts.json"] if t["Id"] == r["ThoughtIdA"]
            )
            == 1
            and next(
                t["Kind"] for t in raw["thoughts.json"] if t["Id"] == r["ThoughtIdB"]
            )
            == 2
            for r in raw["links.json"]
        ),
        "attachment_records": len(raw["attachments.json"]),
        "raw_local_payloads": sum(
            a["Type"] not in {3, 8, 15} and raw_member(a) in archive.namelist()
            for a in raw["attachments.json"]
        ),
        "url_attachments": sum(a["Type"] == 3 for a in raw["attachments.json"]),
        "present_note_images": sum(a["Type"] == 12 for a in raw["attachments.json"]),
        "present_icons": sum(
            a["Type"] == 5 and a["Id"] not in raw.gaps for a in raw["attachments.json"]
        ),
        "present_generic_files": sum(
            a["Type"] == 1 and a["Id"] not in raw.gaps and a["Id"] not in raw.documents
            for a in raw["attachments.json"]
        ),
        "marked_documents": sum(
            a["NoteType"] == 4 and a["Id"] in raw.documents
            for a in raw["attachments.json"]
        ),
        "canonical_documents": sum(
            a["NoteType"] == 0 and a["Id"] in raw.documents
            for a in raw["attachments.json"]
        ),
        **{
            "absent_" + label: sum(g["role"] == role for g in raw.gaps.values())
            for label, role in (
                ("ordinary_owners", "ordinary_note"),
                ("definition_notes", "definition_note"),
                ("icon_providers", "definition_icon"),
            )
        },
        "neutral_affected_members": len(
            {k for g in diagnostics for k in g["affected_member_keys"]}
        ),
        "txt_gaps": sum(a["Type"] == 15 for a in raw["attachments.json"]),
        "present_icon_discrepancies": sum(
            a["Type"] == 5
            and a["Id"] not in raw.gaps
            and a["DataLength"] != targets[a["Id"]]["actual_length"]
            for a in raw["attachments.json"]
        ),
        "payloads": len(checked),
        "files": files,
        "references": len(references),
        "image_references": sum(ref["kind"] == "image" for _, _, ref in references),
        "thought_references": sum(ref["kind"] == "item" for _, _, ref in references),
        "documents": len(documents),
        "json_records": sum(map(len, raw.values())),
        **summary,
    }


def visible_label(value):
    return " ".join(re.sub(r"[\[\]|\r\n]", " ", value).split())


def wiki(target, label):
    return "[[" + target + "|" + visible_label(label) + "]]"


def escaped(value):
    return re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", value)


def windows_uri(value):
    spelling = PureWindowsPath(value).as_posix()
    return (
        "file:" + quote(spelling, safe="/")
        if spelling.startswith("//")
        else "file:///" + quote(spelling, safe="/:")
    )


def readable(value, controls=True):
    value = (
        "".join(
            " " if unicodedata.category(c) == "Cc" else c
            for c in unicodedata.normalize("NFC", value)
        )
        if controls
        else unicodedata.normalize("NFC", value)
    )
    value = value.replace(":", " - ").replace("[", "(").replace("]", ")")
    value = (
        " ".join(re.sub(r'[<>"/\\|?*#^%\x00-\x1f]', " ", value).split()).strip(" .")
        or "Untitled"
    )
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value, re.IGNORECASE):
        value = "Note - " + value
    return value


def units(value):
    return len(value.encode("utf-16-le")) // 2


def bounded(value, prefix="", suffix="", limit=120):
    budget = limit - units(prefix + suffix)
    chars, used = [], 0
    for char in value:
        used += units(char)
        if used > budget:
            break
        chars.append(char)
    return prefix + "".join(chars).rstrip(" .") + suffix


def expected_names(thoughts, home):
    widths = dict.fromkeys(thoughts, 0)
    reserved = {
        "migration report",
        "migration-record",
        "tag memberships",
        "uncreated targets",
        "categories",
        "vault guide",
        "new note",
        "category starter",
        "member template starter",
        "members",
        "gallery",
        "starter",
        "app",
        "bookmarks",
        "core-plugins",
        "templates",
        "types",
    }
    while True:
        paths = {
            key: bounded(
                readable(t["Name"]),
                "Home — " if key == home else "",
                " — " + key.replace("-", "")[: widths[key]] if widths[key] else "",
            )
            for key, t in thoughts.items()
        }
        groups = defaultdict(list)
        for key, stem in paths.items():
            groups[stem.casefold()].append(key)
        clashes = contender_keys(
            groups, widths, {k: k.replace("-", "") for k in thoughts}, reserved
        )
        if not clashes:
            return {
                k: (
                    ""
                    if k == home
                    else "Categories/"
                    if thoughts[k]["Kind"] == 2
                    else "Notes/"
                )
                + v
                + ".md"
                for k, v in paths.items()
            }
        for key in clashes:
            assert widths[key] < len(key.replace("-", "")), (
                "independent distinct naming seeds"
            )
            widths[key] = widths[key] + 4 if widths[key] else 8


def contender_keys(groups, widths, seeds, reserved=()):
    selected = set()
    for stem, keys in groups.items():
        if stem in reserved:
            selected.update(keys)
        elif len(keys) > 1:
            selected.update(
                [k for k in keys if 0 < widths[k] < len(seeds[k])]
                or [k for k in keys if widths[k] == 0]
                or keys
            )
    return selected


def expected_tags(thoughts):
    names = {}
    for key, thought in thoughts.items():
        if thought["Kind"] != 4:
            continue
        name = (
            re.sub(r"[\W_]+", "-", unicodedata.normalize("NFC", thought["Name"])).strip(
                "-"
            )
            or "source-tag"
        )
        names[key] = "tag-" + name if name.isnumeric() else name
    widths = dict.fromkeys(names, 0)
    while True:
        tokens = {}
        for key, base in names.items():
            suffix = "-" + key.replace("-", "")[: widths[key]] if widths[key] else ""
            value = base[: 120 - len(suffix)].rstrip("-")
            if value.isnumeric():
                value = "tag-" + value[: 116 - len(suffix)]
            tokens[key] = value + suffix
        groups = defaultdict(list)
        for key, token in tokens.items():
            groups[token.casefold()].append(key)
        clashes = contender_keys(
            groups, widths, {k: k.replace("-", "") for k in tokens}
        )
        if not clashes:
            return tokens
        for key in clashes:
            assert widths[key] < len(key.replace("-", "")), (
                "independent distinct tag seeds"
            )
            widths[key] = widths[key] + 4 if widths[key] else 8


def check_items(raw, record, archive, vault, assets):
    all_thoughts = identities(raw["thoughts.json"], "item")
    thoughts = {k: t for k, t in all_thoughts.items() if t["Kind"] != 5}
    setting = str(uuid5(UUID(raw["meta.json"][0]["BrainId"]), "20"))
    home = next(s["Value"] for s in raw["settings.json"] if s["Id"] == setting)
    targets = {t["item_key"]: t for t in record["item_targets"]}
    assert (
        len(targets) == len(record["item_targets"])
        and targets.keys() == thoughts.keys()
    ), "item identities"
    names = expected_names(thoughts, home)
    tag_tokens = expected_tags(thoughts)
    assigned_types = classifications(raw)
    relation_kinds = relationships(raw)
    definitions = {k for k, t in thoughts.items() if t["Kind"] == 2}
    originals = note_ids(raw, archive)
    content, documents = set(), {}
    for a in raw["attachments.json"]:
        owner, kind = a["SourceId"], a["Type"]
        if a["Id"] in originals:
            text = raw.documents[a["Id"]]
            assert owner not in documents, "raw sole thought-note candidate"
            documents[owner] = (a["Id"], text)
            if text.strip():
                content.add(owner)
        elif a["Id"] not in raw.gaps and (
            kind in {3, 8} or (kind in {1, 12} and a["DataLength"] > 0)
        ):
            content.add(owner)
    created = (content & thoughts.keys()) | {home} | definitions | assigned_types.keys()
    initial = set(created)
    hierarchy = [
        (r["ThoughtIdA"], r["ThoughtIdB"])
        for r in raw["links.json"]
        if relation_kinds[r["Id"]] == "hierarchy"
    ]
    while uncovered := [
        (a, b) for a, b in hierarchy if a not in created and b not in created
    ]:
        candidates = {a for a, _ in uncovered}
        chosen = min(
            candidates, key=lambda k: (-sum(k in {a, b} for a, b in uncovered), k)
        )
        created.add(chosen)
    for key, target in targets.items():
        assert (
            target["original_identity"] == key
            and target["original_title"] == thoughts[key]["Name"]
        ), "item identity assignment"
        assert target["relative_path"] == names[key], "item filename assignment"
        assert target["created"] == (key in created), "greedy eligibility"
        reasons = (
            (["content"] if key in content else [])
            + (["home"] if key == home else [])
            + (["definition"] if key in definitions else [])
            + (["classification"] if key in assigned_types else [])
        )
        if key in created and key not in initial:
            reasons = ["hierarchy"]
        assert target["creation_reasons"] == reasons, "creation reasons"
        assert target["vault_tag_token"] == tag_tokens.get(key), "native tag token"
        declared, calendar, icon = expected_metadata(raw, key, assets)
        provider = assigned_types.get(key, {}).get("definition_key")
        effective = icon or (
            expected_metadata(raw, provider, assets)[2] if provider else None
        )
        assert target["declared_appearance"] == declared, "declared icon/colour facts"
        assert target["calendar_dates"] == calendar, "source calendar dates"
        assert target["metadata_evidence"] == [
            "thoughts.json:"
            + str(next(i for i, t in enumerate(raw["thoughts.json"]) if t["Id"] == key))
        ], "metadata source provenance"
        assert target["icon_snapshot"] == (
            {
                "item_key": key,
                "explicit_icon_asset_id": icon,
                "appearance_category_key": provider,
                "effective_icon_asset_id": effective,
            }
            if key in created
            else None
        ), "migration-time effective icon decision"
        assert (vault / names[key]).is_file() == (key in created), (
            "created/uncreated file"
        )
        assert (
            units(PurePosixPath(names[key]).stem) <= 120
            and units(str((vault / names[key]).resolve())) <= 240
        ), "target path limits"
    assert len({PurePosixPath(n).name.casefold() for n in names.values()}) == len(
        names
    ), "unique basenames"
    relations = {r["key"]: r for r in record["relationships"]}
    assert len(relations) == len(record["relationships"]) and relations.keys() == {
        r["Id"] for r in raw["links.json"]
    }, "all relationship identities"
    for source in raw["links.json"]:
        r = relations[source["Id"]]
        a, b = source["ThoughtIdA"], source["ThoughtIdB"]
        kind = relation_kinds[source["Id"]]
        assert r["evidence"] == [f"links.json:{raw['links.json'].index(source)}"], (
            "relationship source provenance"
        )
        assert (r["item_a"], r["item_b"], r["kind"]) == (a, b, kind), (
            "relationship interpretation"
        )
        assert (r["target_a"], r["target_b"]) == (names.get(a), names.get(b)), (
            "relationship targets"
        )
        assert (
            r["presentation"]
            == {
                "hierarchy": "Parents/Children",
                "related": "Related",
                "tag": "native tags",
                "system": "retained_only",
                "classification": "linked category membership",
            }[kind]
        ), "relationship presentation"
    memberships = {m["relationship_key"]: m for m in record["tag_memberships"]}
    assignments = [r for r in raw["links.json"] if r["Meaning"] == 5]
    assert len(memberships) == len(
        record["tag_memberships"]
    ) and memberships.keys() == {r["Id"] for r in assignments}, (
        "tag membership identities"
    )
    for r in assignments:
        a, b = r["ThoughtIdA"], r["ThoughtIdB"]
        m = memberships[r["Id"]]
        assert m["evidence"] == [f"links.json:{raw['links.json'].index(r)}"], (
            "tag source provenance"
        )
        assert (m["tag_key"], m["item_key"], m["native"], m["token"]) == (
            a,
            b,
            b in created,
            tag_tokens[a],
        ), "native tag membership"
        assert (
            m["tag_original_identity"],
            m["tag_name"],
            m["tag_target"],
            m["item_target"],
        ) == (a, thoughts[a]["Name"], names[a], names[b]), "tag identity targets"
    emitted_types = record["classification_assignments"]
    assert len({a["item_key"] for a in emitted_types}) == len(emitted_types), (
        "duplicate classification member"
    )
    assert len({a["relationship_key"] for a in emitted_types}) == len(emitted_types), (
        "duplicate classification relationship"
    )
    assert emitted_types == [
        dict(
            a,
            definition_target=names[a["definition_key"]],
            item_target=names[a["item_key"]],
        )
        for _, a in sorted(assigned_types.items())
    ], "classification identity/target/evidence correspondence"
    for key in sorted(created):
        tags = sorted(
            {
                tag_tokens[r["ThoughtIdA"]]
                for r in assignments
                if r["ThoughtIdB"] == key
            },
            key=str.casefold,
        )
        declared, calendar, icon = expected_metadata(raw, key, assets)
        if key in definitions:
            tags = sorted(set(tags) | {"categories"}, key=str.casefold)
        provider = assigned_types.get(key, {}).get("definition_key")
        category = "[[" + names[provider] + "]]" if provider else None
        effective = icon or (
            expected_metadata(raw, provider, assets)[2] if provider else None
        )
        expected = "---\ncategories:" + (
            "\n  - "
            + json.dumps(category, ensure_ascii=False)
            + "\nappearance_category: "
            + json.dumps(category, ensure_ascii=False)
            + "\n"
            if category
            else " []\nappearance_category:\n"
        )
        expected += (
            "icon:"
            + (
                " "
                + json.dumps(
                    "[[" + assets[icon]["relative_path"] + "]]", ensure_ascii=False
                )
                if icon
                else ""
            )
            + "\n"
        )
        for name in ("created", "updated"):
            expected += (
                name + ":" + (" " + calendar[name] if calendar[name] else "") + "\n"
            )
        expected += "tags:" + (
            "\n"
            + "".join("  - " + json.dumps(t, ensure_ascii=False) + "\n" for t in tags)
            if tags
            else " []\n"
        )
        expected += (
            "aliases: []\nsource_collection_id: "
            + json.dumps(raw["meta.json"][0]["BrainId"])
            + "\nsource_item_id: "
            + json.dumps(key)
            + "\n---\n\n"
        )
        expected += "# " + escaped(thoughts[key]["Name"]) + "\n\n"
        owned_gaps = [g for g in raw.gaps.values() if g["owner"] == key]
        presentation_images = next((g["images"] for g in owned_gaps if g["images"]), [])
        if presentation_images:
            expected += "> [!warning] Source note unavailable\n> Source note text is absent. Unknown prose, captions and layout were not recovered. See [[MIGRATION REPORT.md|Migration report]] for evidence and optional repair steps.\n\n"
        sections = {}
        for heading in ("Parents", "Children", "Related"):
            neighbors = set()
            for r in raw["links.json"]:
                a, b = r["ThoughtIdA"], r["ThoughtIdB"]
                if r["Meaning"] != 1:
                    continue
                if heading == "Parents" and r["Relation"] == 1 and b == key:
                    neighbors.add(a)
                elif heading == "Children" and r["Relation"] == 1 and a == key:
                    neighbors.add(b)
                elif heading == "Related" and r["Relation"] == 3 and key in {a, b}:
                    neighbors.add(b if a == key else a)
            if neighbors:
                sections[heading] = (
                    "## "
                    + heading
                    + "\n\n"
                    + "".join(
                        "- " + wiki(names[n], thoughts[n]["Name"]) + "\n"
                        for n in sorted(neighbors)
                    )
                )
        if key in definitions:
            for heading in ("Parents", "Children"):
                if heading in sections:
                    expected += sections.pop(heading) + "\n"
            if any(g["role"] == "definition_note" for g in owned_gaps):
                expected += "> [!warning] Source category note unavailable\n> Source category note text is absent and remains unknown. No prose, captions or layout were recovered. See [[MIGRATION REPORT.md|Migration report]] for evidence and optional repair steps.\n\n"
        elif effective:
            expected += "![[" + assets[effective]["relative_path"] + "]]\n\n"
        for _, gap in sorted(raw.gaps.items()):
            if gap["role"] != "definition_icon":
                continue
            if gap["owner"] == key:
                expected += "> [!warning] Source category icon unavailable\n> Source category icon is absent; appearance is neutral. See [[MIGRATION REPORT.md|Migration report]] for provider evidence and optional repair steps.\n\n"
            elif provider == gap["owner"] and not icon:
                expected += (
                    "> [!warning] Inherited icon unavailable\n> The inherited icon is unavailable from "
                    + wiki(names[provider], thoughts[provider]["Name"])
                    + "; appearance is neutral. See [[MIGRATION REPORT.md|Migration report]] for evidence and optional repair steps.\n\n"
                )
        if key in definitions:
            expected += "## Members\n\n![[Templates/Bases/Members.base#Members]]\n\n## Gallery\n\n![[Templates/Bases/Gallery.base#Gallery]]\n\n"
        if thoughts[key].get("Label"):
            expected += thoughts[key]["Label"] + "\n\n"
        body = documents.get(key, (None, ""))[1]
        expected += adapt_body(body, key, names[key], names, assets)
        if presentation_images:
            expected += (
                "\n\n".join(
                    "![[" + assets[i]["relative_path"] + "]]"
                    for i in presentation_images
                )
                + "\n\n"
            )
        resources = expected_resources(raw, key, body, assets)
        if resources:
            expected += "\n\n" + resources
        if sections:
            normalized_end = expected.replace("\r\n", "\n").replace("\r", "\n")
            expected += (
                ""
                if normalized_end.endswith("\n\n")
                else "\n"
                if normalized_end.endswith("\n")
                else "\n\n"
            )
            expected += "\n".join(sections.values())
        if key == home:
            normalized_end = expected.replace("\r\n", "\n").replace("\r", "\n")
            expected += (
                ""
                if normalized_end.endswith("\n\n")
                else "\n"
                if normalized_end.endswith("\n")
                else "\n\n"
            )
            expected += "## Categories\n\n[[Categories.md|Browse categories]]\n"
        actual_note = (vault / names[key]).read_bytes()
        assert actual_note == expected.encode(), (
            "complete note/body/graph/tag bytes: ordinal="
            + str(sorted(created).index(key))
            + " expected="
            + str(len(expected.encode()))
            + " actual="
            + str(len(actual_note))
            + " differing-offset="
            + str(
                next(
                    (
                        i
                        for i, (a, b) in enumerate(zip(actual_note, expected.encode()))
                        if a != b
                    ),
                    -1,
                )
            )
        )
    expected_config = {
        "showInlineTitle": False,
        "defaultViewMode": "preview",
        "newFileLocation": "folder",
        "newFileFolderPath": "Notes",
        "useMarkdownLinks": False,
        "newLinkFormat": "absolute",
        "openBehavior": "file:" + names[home],
        "alwaysUpdateLinks": True,
        "attachmentFolderPath": "Attachments",
    }
    assert load_json((vault / ".obsidian/app.json").read_bytes()) == expected_config, (
        "native Home configuration"
    )
    assert record["obsidian_configuration"] == expected_config, "record configuration"
    bookmarks = load_json((vault / ".obsidian/bookmarks.json").read_bytes())
    assert bookmarks == {
        "items": [
            {
                "type": "file",
                "ctime": record["run_metadata"]["bookmark_time"],
                "path": names[home],
                "title": "Home",
            }
        ]
    }, "native bookmark"
    check_listings(
        raw, vault, thoughts, names, created, tag_tokens, assignments, documents
    )
    return (
        {
            "notes": len(created),
            "hierarchy_only": len(created - initial),
            "ordinary_notes": sum(thoughts[k]["Kind"] == 1 for k in created),
            "tag_notes": sum(thoughts[k]["Kind"] == 4 for k in created),
            "category_notes": len(definitions),
            "typed_members": len(assigned_types),
            "membership_sizes": sorted(
                sum(a["definition_key"] == k for a in assigned_types.values())
                for k in definitions
            ),
            "typed_owned_overrides": sum(
                expected_metadata(raw, k, assets)[2] is not None for k in assigned_types
            ),
            "typed_inherited_icons": sum(
                expected_metadata(raw, k, assets)[2] is None
                and expected_metadata(raw, a["definition_key"], assets)[2] is not None
                for k, a in assigned_types.items()
            ),
            "uncreated": len(thoughts) - len(created),
        },
        documents,
        names,
    )


def expected_metadata(raw, key, assets):
    """Read reviewed declared facts directly from the original source records."""
    thought = next(t for t in raw["thoughts.json"] if t["Id"] == key)
    icons = [
        a["Id"]
        for a in raw["attachments.json"]
        if a["SourceId"] == key and a["Type"] == 5
    ]
    assert len(icons) <= 1, "unambiguous source icon"
    declared_icon = icons[0] if icons else None
    icon = declared_icon if declared_icon not in raw.gaps else None
    if icon:
        assert assets[icon]["relative_path"] and assets[icon]["actual_length"] > 0, (
            "present declared icon"
        )
    declared = {"icon_asset_id": declared_icon}
    for property_name, field in (
        ("foreground_color", "ForegroundColor"),
        ("background_color", "BackgroundColor"),
    ):
        number = thought.get(field)
        if number is not None:
            assert type(number) is int and -16777216 <= number <= -1, (
                "reviewed opaque ARGB"
            )
            declared[property_name] = "#" + hex(number + 2**32)[4:].upper().zfill(6)
        else:
            declared[property_name] = None
    calendar = {}
    for property_name, field in (
        ("created", "CreationDateTime"),
        ("updated", "ModificationDateTime"),
    ):
        value = thought.get(field)
        calendar[property_name] = (
            (
                datetime.fromisoformat(value).date().isoformat()
                if len(value or "") > 10
                else date.fromisoformat(value).isoformat()
            )
            if value
            else None
        )
    return declared, calendar, icon


def check_listings(
    raw, vault, thoughts, names, created, tokens, assignments, documents
):
    represented = set()
    pairs = set()
    for r in raw["links.json"]:
        if r["Meaning"] in {1, 5}:
            represented.update((r["ThoughtIdA"], r["ThoughtIdB"]))
        if (
            r["Meaning"] == 1
            and r["Relation"] == 3
            and not {r["ThoughtIdA"], r["ThoughtIdB"]} & created
        ):
            pairs.add(tuple(sorted((r["ThoughtIdA"], r["ThoughtIdB"]))))
    assets = {
        a["asset_id"]: a
        for a in load_json((vault / "migration-record.json").read_bytes())[
            "asset_targets"
        ]
    }
    for owner, (_, body) in documents.items():
        if owner in created:
            represented.update(
                r["target"]
                for r in source_references(body, owner, assets)
                if r["kind"] == "item"
            )
    isolated = sorted(
        k
        for k, t in thoughts.items()
        if t["Kind"] == 1 and k not in created and k not in represented
    )
    listing = ""
    if isolated or pairs:
        listing = "# Uncreated targets\n\n"
        if isolated:
            listing += (
                "## Isolated thoughts\n\n"
                + "".join(
                    "- " + wiki(names[k], thoughts[k]["Name"]) + "\n" for k in isolated
                )
                + "\n"
            )
        if pairs:
            listing += "## Related pairs\n\n" + "".join(
                "- "
                + wiki(names[a], thoughts[a]["Name"])
                + " — "
                + wiki(names[b], thoughts[b]["Name"])
                + "\n"
                for a, b in sorted(pairs)
            )
        listing = listing.rstrip("\n") + "\n"
    assert (vault / "Uncreated targets.md").is_file() == bool(listing), (
        "conditional uncreated listing"
    )
    if listing:
        assert (vault / "Uncreated targets.md").read_bytes() == listing.encode(), (
            "focused uncreated listing"
        )
    focused = [
        k
        for k in sorted(tokens)
        if not any(r["ThoughtIdA"] == k for r in assignments)
        or any(
            r["ThoughtIdA"] == k and r["ThoughtIdB"] not in created for r in assignments
        )
    ]
    assert (vault / "Tag memberships.md").is_file() == bool(focused), (
        "conditional tag listing"
    )
    if focused:
        listing = "# Tag memberships\n\nAssignments on uncreated targets and source tags without assignments. Use native tag search for created assigned notes.\n\n"
        for tag in focused:
            listing += (
                "## #"
                + tokens[tag]
                + "\n\nSource tag: "
                + wiki(names[tag], thoughts[tag]["Name"])
                + "\n\n"
            )
            hidden = sorted(
                {
                    r["ThoughtIdB"]
                    for r in assignments
                    if r["ThoughtIdA"] == tag and r["ThoughtIdB"] not in created
                }
            )
            listing += (
                "".join(
                    "- " + wiki(names[k], thoughts[k]["Name"]) + "\n" for k in hidden
                )
                + "\n"
                if hidden
                else "No source assignments.\n\n"
            )
        assert (vault / "Tag memberships.md").read_bytes() == (
            listing.rstrip("\n") + "\n"
        ).encode(), "focused tag listing"


def inline_display(value):
    """Independently interpret bounded inline label text, retaining literals."""
    assert "\x00" not in value, "unsupported null in raw reference label"
    protected = []

    def keep(text):
        protected.append(text)
        return "\x00" + str(len(protected) - 1) + "\x00"

    def code(match):
        text = re.sub(r"\r\n?|\n", " ", match[2])
        if text.startswith(" ") and text.endswith(" ") and text.strip():
            text = text[1:-1]
        return keep(text)

    value = re.sub(r"(?<!`)(`+)(?!`)(.*?)\1(?!`)", code, value, flags=re.DOTALL)
    value = re.sub(
        r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])',
        lambda match: keep(match[1]),
        value,
    )
    value = re.sub(
        r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);",
        lambda match: keep(html.unescape(match[0])),
        value,
    )
    for _ in range(3):
        value = re.sub(r"(\*{1,3})(?=\S)(.+?)(?<=\S)\1", r"\2", value)
        value = re.sub(r"(?<!\w)(_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", value)
    value = re.sub(r"</?[A-Za-z][^<>]*>", "", value)
    return re.sub(r"\x00([0-9]+)\x00", lambda match: protected[int(match[1])], value)


def inline_candidates(body):
    """Find balanced active phrases, distinguishing bracket text from links."""
    protected = []
    fence = None
    offset = 0
    paragraph = False
    for line in body.splitlines(keepends=True):
        marker = re.match(r" {0,3}(`{3,}|~{3,})", line)
        if fence or marker:
            protected.append((offset, offset + len(line)))
            if (
                fence
                and marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
            ):
                fence = None
            elif not fence:
                fence = marker[1]
        elif line.startswith(("    ", "\t")) and not paragraph:
            protected.append((offset, offset + len(line)))
        else:
            paragraph = bool(line.strip())
        offset += len(line)
    protected.extend(
        (m.start(), m.end())
        for m in re.finditer(r"<!--.*?-->|(`+)(?!`)(.*?)\1(?!`)", body, re.DOTALL)
    )
    mask = list(body)
    for start, end in protected:
        mask[start:end] = " " * (end - start)
    scan = "".join(mask)
    # Balanced brackets recognize whole outer phrases, including an image inside
    # a forgotten thought link. Escaped brackets never change nesting depth.
    candidates = []
    cursor = 0
    while cursor < len(scan):
        if scan[cursor : cursor + 9] == "<brain://":
            finish = scan.find(">", cursor + 1)
            if finish >= 0:
                candidates.append(
                    (
                        cursor,
                        finish + 1,
                        False,
                        scan[cursor + 1 : finish],
                        cursor + 1,
                        finish,
                    )
                )
                cursor = finish + 1
                continue
        if scan[cursor] == "\\":
            cursor += 2
            continue
        image = scan[cursor : cursor + 2] == "!["
        opening = cursor + int(image)
        if scan[opening : opening + 1] != "[":
            cursor += 1
            continue
        index, depth = opening + 1, 1
        while index < len(scan) and depth:
            if scan[index] == "\\":
                index += 2
                continue
            depth += (scan[index] == "[") - (scan[index] == "]")
            index += 1
        closing = index - 1
        if depth or scan[index : index + 1] != "(":
            cursor += 1
            continue
        start = index + 1
        if scan[start : start + 1] == "<":
            stop = scan.find(">", start + 1)
            destination_start, destination_end = start + 1, stop
            after = stop + 1
        else:
            after, nesting = start, 0
            while after < len(scan):
                if scan[after] == "\\":
                    after += 2
                    continue
                if scan[after] == ")" and nesting == 0 or scan[after].isspace():
                    break
                nesting += (scan[after] == "(") - (scan[after] == ")")
                after += 1
            destination_start, destination_end = start, after
        end = re.match(r'(?:\s+["\'][^"\']*["\'])?\)', scan[after:])
        if end is None or destination_end < destination_start:
            cursor += 1
            continue
        finish = after + end.end()
        candidates.append(
            (
                cursor,
                finish,
                image,
                body[opening + 1 : closing],
                destination_start,
                destination_end,
            )
        )
        cursor = finish
    return candidates, mask, scan


def source_references(body, owner, assets, excluded=()):
    """Separate syntax scan without converter spans or markdown-it-py.

    Protected regions retain source offsets. Unrecognized active local syntax
    fails the audit instead of silently passing its coverage claim.
    """
    candidates, mask, scan = inline_candidates(body)
    result = []
    for (
        begin,
        finish,
        image,
        label_text,
        destination_start,
        destination_end,
    ) in candidates:
        url = scan[destination_start:destination_end]
        kind, target = None, None
        if url.startswith("brain://"):
            compact = url[8:].split("/")[0]
            target = str(
                UUID(
                    bytes_le=base64.urlsafe_b64decode(
                        compact + "=" * (-len(compact) % 4)
                    )
                )
            )
            kind = "item"
            assert not image or target in excluded, "unexpected linked thought image"
            assert target in excluded or not inline_candidates(label_text)[0], (
                "unsupported included nested thought phrase"
            )
        elif image and url.startswith(".data/md-images/"):
            filename = unquote(url[len(".data/md-images/") :])
            targets = [
                a["asset_id"]
                for a in assets.values()
                if a["owner"] == owner
                and a["role"] == "image"
                and a["original_name"] == filename
            ]
            assert len(targets) == 1, "independent inline image binding"
            kind, target = "image", targets[0]
        if kind:
            label = inline_display(label_text)
            result.append(
                {
                    "start": begin,
                    "end": finish,
                    "kind": kind,
                    "target": target,
                    "label": label,
                    "destination_start": destination_start,
                    "destination_end": destination_end,
                }
            )
            mask[begin:finish] = " " * (finish - begin)
    remainder = "".join(mask)
    assert not re.search(
        r"(?:\]\(<?|<)brain://|!\[[^\]]*\]\(<?\.data/md-images/", remainder
    ), "independent scanner cannot establish all active local reference coverage"
    return result


def adapt_body(body, owner, note_path, names, assets):
    result = body
    for ref in reversed(source_references(body, owner, assets)):
        if ref["kind"] == "item":
            assert ref["target"] in names, "source local thought target"
            replacement = wiki(names[ref["target"]], ref["label"])
            start, end = ref["start"], ref["end"]
        else:
            start, end = ref["destination_start"], ref["destination_end"]
            replacement = quote(
                posixpath.relpath(
                    assets[ref["target"]]["relative_path"],
                    posixpath.dirname(note_path) or ".",
                ),
                safe="/",
            )
        result = result[:start] + replacement + result[end:]
    return result


def expected_resources(raw, owner, body, assets):
    inline = {
        r["target"]
        for r in source_references(body, owner, assets)
        if r["kind"] == "image"
    }
    lines = []
    for source in sorted(raw["attachments.json"], key=lambda a: a["Id"]):
        if source["SourceId"] != owner:
            continue
        if source["Id"] in raw.unsafe_originals:
            continue
        if any(source["Id"] in g["images"] for g in raw.gaps.values()):
            assert assets[source["Id"]]["resource_link"] is None, (
                "generated embed resource suppression"
            )
            continue
        kind = source["Type"]
        assigned = assets[source["Id"]]
        if kind == 15:
            filename = (
                escaped(PurePosixPath(source["Location"]).name)
                .replace("\r", " ")
                .replace("\n", " ")
            )
            lines.append(
                "- Absent source file: "
                + filename
                + " (metadata retained; bytes absent from the source)."
            )
        elif (
            kind in {3, 8}
            or kind == 12
            and source["Id"] not in inline
            or kind == 1
            and source["NoteType"] == 0
            and source["Location"] != "Notes.md"
        ):
            label = source.get("Name") or PurePosixPath(source["Location"]).name
            label = re.sub(r"[\[\]|\r\n]", " ", label).strip() or "Resource"
            if kind in {3, 8}:
                uri = (
                    source["Location"] if kind == 3 else windows_uri(source["Location"])
                )
                label = re.sub(r"([\\`*_{}<>])", r"\\\1", label)
                lines.append("- [" + label + "](<" + uri + ">)")
                assert (
                    assigned["external_uri"] == uri and assigned["resource_link"] == uri
                ), "external reference destination"
                presentation = video(source)
                if presentation:
                    lines.append(
                        '\n<iframe src="'
                        + html.escape(presentation["embed_uri"], quote=True)
                        + '" width="560" height="315" title="YouTube video player" frameborder="0" allowfullscreen></iframe>\n'
                    )
            else:
                lines.append("- [[" + assigned["relative_path"] + "|" + label + "]]")
                assert assigned["resource_link"] == assigned["relative_path"], (
                    "resource destination"
                )
        else:
            assert assigned["resource_link"] is None, (
                "decorative/inline resource suppression"
            )
    return "## Resources\n\n" + "\n".join(lines) + "\n" if lines else ""


def check_documents(raw, record, documents, names, assets):
    emitted = [d for t in record["item_targets"] for d in t["documents"]] + [
        d for a in record["asset_targets"] for d in a["retained_documents"]
    ]
    by_id = {d["key"]: d for d in emitted}
    assert len(by_id) == len(emitted) and set(by_id) == {
        d[0] for d in documents.values()
    }, "document identities"
    all_references = []
    for owner, (key, body) in documents.items():
        d = by_id[key]
        digest = hashlib.sha256(body.encode()).hexdigest()
        assert (
            d["owner"],
            d["original_asset_id"],
            d["text_digest"],
            d["owner_target"],
        ) == (
            owner,
            None if key in raw.unsafe_originals else key,
            digest,
            names.get(owner),
        ), "document identity/digest"
        assert d["original_copy_omitted"] == (key in raw.unsafe_originals), (
            "exact original eligibility"
        )
        assert d["evidence"] == [
            "attachments.json:"
            + str(
                next(i for i, a in enumerate(raw["attachments.json"]) if a["Id"] == key)
            )
        ], "document source provenance"
        independent = source_references(body, owner, assets)
        assert len(d["references"]) == len(independent), "all source references"
        for emitted_ref, actual in zip(d["references"], independent, strict=True):
            assert (
                emitted_ref["start"],
                emitted_ref["end"],
                emitted_ref["kind"],
                emitted_ref["target"],
                emitted_ref["display_text"],
            ) == (
                actual["start"],
                actual["end"],
                actual["kind"],
                actual["target"],
                actual["label"],
            ), "reference spans and targets"
            assert (
                emitted_ref["expected_original"]
                == body[actual["start"] : actual["end"]]
                and emitted_ref["document_digest"] == digest
            ), "reference binding"
            source_target = body[
                actual["destination_start"] : actual["destination_end"]
            ]
            assert emitted_ref["source_target"] == source_target, (
                "reference original destination"
            )
            if actual["kind"] == "image":
                assert (
                    emitted_ref["destination_start"],
                    emitted_ref["destination_end"],
                ) == (actual["destination_start"], actual["destination_end"]), (
                    "image destination span"
                )
            else:
                assert (
                    emitted_ref["destination_start"] is None
                    and emitted_ref["destination_end"] is None
                ), "thought reference whole-span adaptation"
        all_references.extend((key, i, ref) for i, ref in enumerate(independent))
    return all_references


def expected_asset_paths(raw):
    owners = {t["Id"]: t["Id"].replace("-", "") for t in raw["thoughts.json"]}
    owner_widths = dict.fromkeys(owners, 8)
    while True:
        tokens = {k: v[: owner_widths[k]] for k, v in owners.items()}
        clashes = {
            k for k, token in tokens.items() if list(tokens.values()).count(token) > 1
        }
        if not clashes:
            break
        grew = False
        for k in clashes:
            if owner_widths[k] < len(owners[k]):
                owner_widths[k] += 4
                grew = True
        assert grew, "independent distinct owner seeds"
    present = [
        a
        for a in raw["attachments.json"]
        if a["Type"] not in {3, 8, 15}
        and a["Id"] not in raw.unsafe_originals
        and a["Id"] not in raw.gaps
    ]
    widths = {a["Id"]: 0 for a in present}
    while True:
        result = {}
        for a in present:
            base = readable(PurePosixPath(a["Location"]).name, controls=False)
            extension = PurePosixPath(base).suffix
            stem = base[: -len(extension)] if extension else base
            suffix = (
                " — " + a["Id"].replace("-", "")[: widths[a["Id"]]]
                if widths[a["Id"]]
                else ""
            )
            ending = extension + (
                ".original"
                if a["Type"] == 1
                and (a["NoteType"] == 4 or a["Location"] == "Notes.md")
                else ""
            )
            result[a["Id"]] = (
                "Attachments/"
                + tokens[a["SourceId"]]
                + "/"
                + bounded(stem, suffix=suffix + ending)
            )
        clashes = {
            k
            for k, name in result.items()
            if sum(n.casefold() == name.casefold() for n in result.values()) > 1
        }
        if not clashes:
            return result
        grew = False
        for k in clashes:
            if widths[k] < len(k.replace("-", "")):
                widths[k] = widths[k] + 4 if widths[k] else 8
                grew = True
        assert grew, "independent distinct asset seeds"


def check_assets(raw, record, archive, vault, targets):
    identities(raw["attachments.json"], "attachment")
    assert len(targets) == len(record["asset_targets"]) and targets.keys() == {
        a["Id"] for a in raw["attachments.json"] if a["Id"] not in raw.unsafe_originals
    }, "all attachment identities"
    paths = expected_asset_paths(raw)
    originals = note_ids(raw, archive)
    raw_documents = {
        a["SourceId"]: raw.documents[a["Id"]]
        for a in raw["attachments.json"]
        if a["Id"] in originals
    }
    bindings = {
        a["Id"]: {
            "asset_id": a["Id"],
            "owner": a["SourceId"],
            "role": "image" if a["Type"] == 12 else "other",
            "original_name": a["Location"],
        }
        for a in raw["attachments.json"]
    }
    inline = {
        r["target"]
        for owner, body in raw_documents.items()
        for r in source_references(body, owner, bindings)
        if r["kind"] == "image"
    }
    expected_warnings = dict(raw.gap_warnings)
    backups = 0
    for a in raw["attachments.json"]:
        key, kind, owner = a["Id"], a["Type"], a["SourceId"]
        if key in raw.unsafe_originals:
            continue
        target = targets[key]
        role = (
            "url"
            if kind == 3
            else "directory"
            if kind == 8
            else "icon"
            if kind == 5
            else "image"
            if kind == 12
            else "note_original"
            if key in originals
            or key in raw.gaps
            and raw.gaps[key]["role"].endswith("note")
            else "file"
        )
        availability = (
            "external"
            if kind in {3, 8}
            else "absent"
            if kind == 15 or key in raw.gaps
            else "present"
        )
        assert (
            target["owner"],
            target["original_name"],
            target["display_name"],
            target["naming_seed"],
            target["role"],
            target["availability"],
            target["relative_path"],
        ) == (
            owner,
            a["Location"],
            a.get("Name"),
            key.replace("-", ""),
            role,
            availability,
            paths.get(key),
        ), "attachment identity/role/path"
        pointer = "attachments.json:" + str(raw["attachments.json"].index(a))
        assert target["evidence"] == [pointer], "asset source provenance"
        assert target["video_presentation"] == video(a), (
            "reviewed video normalized facts"
        )
        assert type(a["DataLength"]) is int and a["DataLength"] >= 0, (
            "raw attachment declared length"
        )
        assert (
            type(a["SourceType"]) is int
            and a["SourceType"] == 2
            and type(a["NoteType"]) is int
            and type(kind) is int
            and (kind, a["NoteType"])
            in {(1, 4), (1, 0), (3, 0), (5, 0), (8, 0), (12, 0), (15, 0)}
        ), "raw attachment role"
        flags = (
            "IsIcon",
            "IsBrainAttachment",
            "IsBrainIcon",
            "IsWallpaper",
            "IsAiScriptsFile",
            "IsKeyboardShortcutsFile",
            "IsToolbarConfigFile",
        )
        assert all(type(a[f]) is bool for f in flags if f in a), (
            "raw attachment role flags"
        )
        assert all(not a.get(f, False) for f in flags[1:]) and a.get(
            "IsIcon", False
        ) == (kind == 5), "raw reviewed attachment flags"
        assert a["SourceId"] in identities(raw["thoughts.json"], "item"), (
            "raw attachment owner"
        )
        if key in paths:
            assert raw["meta.json"][0]["AttachmentFileStates"][key] == 1, (
                "present asset ordinary state"
            )
            assert (
                units(PurePosixPath(paths[key]).name) <= 120
                and units(str((vault / paths[key]).resolve())) <= 240
            ), "resource path bounds"
            backups += role == "note_original"
        else:
            assert (
                target["actual_length"] is None and target["actual_sha256"] is None
            ), "no fabricated payload"
        if kind == 15:
            member = owner + "/" + a["Location"]
            assert (
                (a["SourceType"], a["NoteType"]) == (2, 0)
                and PurePosixPath(a["Location"]).suffix.lower() == ".txt"
                and type(a["DataLength"]) is int
                and a["DataLength"] >= 0
                and not PurePosixPath(a["Location"]).is_absolute()
                and str(PurePosixPath(a["Location"])) == a["Location"]
                and not any(p in {".", ".."} for p in a["Location"].split("/"))
                and "\\" not in a["Location"]
                and ":" not in a["Location"]
                and raw["meta.json"][0]["AttachmentFileStates"][key] == 2
                and member not in archive.namelist()
            ), "exact absent TXT predicate"
            pdfs = sorted(
                p["Id"]
                for p in raw["attachments.json"]
                if p["SourceId"] == owner
                and p["Type"] == 1
                and p["NoteType"] == 0
                and PurePosixPath(p["Location"]).suffix.lower() == ".pdf"
                and p["Id"] in paths
            )
            assert pdfs, "intact same-owner PDF"
            observed = (
                zero_txt_observation(raw, archive, a)
                if a["DataLength"] == 0
                else {
                    "owner": owner,
                    "filename": a["Location"],
                    "declared_length": a["DataLength"],
                    "state": 2,
                    "present": False,
                    "intact_same_owner_pdfs": pdfs,
                }
            )
            expected_warnings[key] = (
                "known_absent_payload",
                "thebrain-format5/zero-length-absent-txt/v1"
                if a["DataLength"] == 0
                else "thebrain-format5/absent-txt/v1",
                "approved_source_gap",
                observed,
            )
        elif key in paths and a["DataLength"] != target["actual_length"]:
            assert (
                kind == 5
                and a.get("IsIcon") is True
                and a["NoteType"] == 0
                and raw["meta.json"][0]["AttachmentFileStates"][key] == 1
            ), "exact icon discrepancy predicate"
            member = owner + "/.data/" + a["Location"]
            observed = {
                "member": member,
                "declared_length": a["DataLength"],
                "actual_length": len(archive.read(member)),
                "actual_sha256": hashlib.sha256(archive.read(member)).hexdigest(),
                "crc_valid": True,
            }
            expected_warnings[key] = (
                "approved_metadata_discrepancy",
                "thebrain-format5/icon-length/v1",
                "approved_metadata_discrepancy",
                observed,
            )
        if key in expected_warnings:
            kind_expected, rule, _, observed = expected_warnings[key]
            assert len(target["source_findings"]) == 1, "warning finding cardinality"
            finding = target["source_findings"][0]
            assert (finding["kind"], finding["rule_id"], finding["affected"]) == (
                kind_expected,
                rule,
                [key],
            ), "warning finding identity"
            assert load_json(finding["observed_json"]) == observed, (
                "warning predicate evidence"
            )
            pointer = "attachments.json:" + str(raw["attachments.json"].index(a))
            evidence = (
                [pointer, "meta.json"]
                + [
                    "attachments.json:" + str(index)
                    for index, source in enumerate(raw["attachments.json"])
                    if source["Id"] in observed.get("intact_same_owner_pdfs", [])
                ]
                if kind == 15
                else [pointer, "payload:" + observed["member"]]
            )
            if kind == 15 and a["DataLength"] == 0:
                pdf_pointer = "attachments.json:" + str(
                    next(
                        i
                        for i, p in enumerate(raw["attachments.json"])
                        if p["Id"] == observed["pdf_attachment_id"]
                    )
                )
                evidence = [
                    pointer,
                    "meta.json",
                    pdf_pointer,
                    "payload:" + observed["pdf"]["member"],
                ]
            if key in raw.gaps:
                evidence = raw.gaps[key]["evidence"]
            assert finding["evidence"] == evidence, "warning source evidence pointers"
        else:
            assert not target["source_findings"], "no unexplained source finding"
        if kind not in {3, 8}:
            assert target["external_uri"] is None, "local asset no external URI"
        elif kind == 3:
            assert target["external_uri"] == a["Location"], (
                "exact original external URL"
            )
        if kind in {3, 8}:
            assert key not in raw["meta.json"][0]["AttachmentFileStates"], (
                "external reference no file state"
            )
        resource = (
            a["Location"]
            if kind == 3
            else windows_uri(a["Location"])
            if kind == 8
            else paths[key]
            if role in {"file", "image"}
            and availability == "present"
            and key not in inline
            and not any(key in g["images"] for g in raw.gaps.values())
            else None
        )
        assert target["resource_link"] == resource, (
            "all raw-derived resource destinations/suppression"
        )
    issues = {i["affected"][0]: i for i in record["issues"]}
    assert (
        len(issues) == len(record["issues"])
        and issues.keys() == expected_warnings.keys()
    ), "exact warning items"
    report = (vault / "MIGRATION REPORT.md").read_bytes().decode()
    for key, (_, rule, code, _) in expected_warnings.items():
        issue = issues[key]
        assert (issue["code"], issue["rule_id"], issue["severity"]) == (
            code,
            rule,
            "warning",
        ), "warning disposition"
        assert (
            issue["phase"] == "analysis"
            and issue["evidence"] == targets[key]["source_findings"][0]["evidence"]
        ), "warning issue provenance"
        assert issue["guidance"] and issue["message"].endswith(
            "Observed: " + targets[key]["source_findings"][0]["observed_json"]
        ), "warning issue observation"
        assert (
            code in report
            and rule in report
            and escaped(PurePosixPath(targets[key]["original_name"]).name) in report
        ), "report source warning"
    raw.expected_warnings = expected_warnings
    return {
        "backups": backups,
        "warnings": len(expected_warnings),
        "warning_owners": len({targets[k]["owner"] for k in expected_warnings}),
        "videos": sum(video(a) is not None for a in raw["attachments.json"]),
        "zero_txt_gaps": sum(
            a["Type"] == 15 and type(a["DataLength"]) is int and a["DataLength"] == 0
            for a in raw["attachments.json"]
        ),
        "exceptional_notes": sum(
            a["Id"] in originals
            and a["NoteType"] == 0
            and archive.read(raw_member(a)).decode("utf-8-sig").strip() != ""
            for a in raw["attachments.json"]
        ),
        "bom_documents": sum(
            archive.read(raw_member(a)).startswith(b"\xef\xbb\xbf")
            for a in raw["attachments.json"]
            if a["Id"] in originals
        ),
        "crlf_documents": sum(
            b"\r\n" in archive.read(raw_member(a))
            for a in raw["attachments.json"]
            if a["Id"] in originals
        ),
    }


def check_accounting(raw, record, checked, references):
    expected = {}
    for name, records in raw.items():
        for index, _ in enumerate(records):
            pointer = name + ":" + str(index)
            disposition = (
                "normalized"
                if name
                in {
                    "meta.json",
                    "thoughts.json",
                    "links.json",
                    "attachments.json",
                    "settings.json",
                }
                else "retained_only"
            )
            expected[pointer] = (disposition, [pointer])
    for a in raw["attachments.json"]:
        if (
            a["Type"] in {3, 8, 15}
            or a["Id"] in raw.unsafe_originals
            or a["Id"] in raw.gaps
        ):
            continue
        prefix = (
            ".data/"
            if a["Type"] == 5
            else ".data/md-images/"
            if a["Type"] == 12
            else ""
        )
        expected["payload:" + a["SourceId"] + "/" + prefix + a["Location"]] = (
            "normalized",
            [a["Id"]],
        )
    for key, index, ref in references:
        expected["reference:" + key + ":" + str(index)] = (
            "normalized",
            [key, ref["target"]],
        )
    entries = record["source_accounting"]["entries"]
    actual = {e["identity"]: (e["disposition"], e["references"]) for e in entries}
    assert len(actual) == len(entries) and actual == expected, (
        "complete source accounting"
    )
    evidence = {e["key"]: e for e in record["original_evidence"]}
    assert len(evidence) == len(record["original_evidence"]) and evidence.keys() == set(
        ROOTS
    ) | {"payload:" + m for m in checked}, "complete original evidence identities"
    assert all(evidence[r]["kind"] == "records" for r in ROOTS), "original record roles"
    for member in checked:
        assert evidence["payload:" + member]["kind"] == "payload", (
            "original payload role"
        )


def check_actual_files(vault, record, targets, names, raw, summary):
    created = {t["relative_path"] for t in record["item_targets"] if t["created"]}
    expected = created | {
        t["relative_path"] for t in targets.values() if t["relative_path"] is not None
    }
    expected |= {
        ".obsidian/app.json",
        ".obsidian/bookmarks.json",
        ".obsidian/core-plugins.json",
        "Categories.md",
        "Templates/Bases/Members.base",
        "Templates/Bases/Gallery.base",
        "Templates/Bases/Categories.base",
        "Templates/Bases/Starter.base",
        "Templates/New note.md",
        "Templates/Category starter.md",
        "Templates/Member template starter.md",
        "Vault guide.md",
        ".obsidian/templates.json",
        ".obsidian/types.json",
        "MIGRATION REPORT.md",
        "migration-record.json",
    }
    for name in ("Uncreated targets.md", "Tag memberships.md"):
        if (vault / name).exists():
            expected.add(name)
    definitions = {t["Id"] for t in raw["thoughts.json"] if t["Kind"] == 2}
    expected |= {"Templates/" + PurePosixPath(names[k]).name for k in definitions}
    actual = {p.relative_to(vault).as_posix() for p in vault.rglob("*") if p.is_file()}
    assert actual == expected, "complete actual vault file accounting"
    support = {
        ".obsidian/app.json": "configuration",
        ".obsidian/bookmarks.json": "configuration",
        ".obsidian/core-plugins.json": "configuration",
        "Categories.md": "overview",
        "Templates/Bases/Members.base": "base",
        "Templates/Bases/Gallery.base": "base",
        "Templates/Bases/Categories.base": "base",
        "Templates/Bases/Starter.base": "starter",
        "Templates/New note.md": "template",
        "Templates/Category starter.md": "starter",
        "Templates/Member template starter.md": "starter",
        "Vault guide.md": "guide",
        ".obsidian/templates.json": "configuration",
        ".obsidian/types.json": "configuration",
        "MIGRATION REPORT.md": "report",
        "migration-record.json": "migration_record",
    }
    for name in ("Uncreated targets.md", "Tag memberships.md"):
        if name in actual:
            support[name] = "listing"
    support.update(
        {"Templates/" + PurePosixPath(names[k]).name: "template" for k in definitions}
    )
    assert {
        a["relative_path"]: a["purpose"] for a in record["support_artifacts"]
    } == support, "support artifact accounting"
    assert len(record["support_artifacts"]) == len(support), (
        "duplicate support artifact"
    )
    check_support_content(vault, names, definitions)
    inactive = {"Uncreated targets.md", "Tag memberships.md"} - actual
    assert (
        len(record["reserved_support_paths"]) == len(inactive)
        and set(record["reserved_support_paths"]) == inactive
    ), "inactive support reservations"
    all_paths = actual | set(names.values()) | inactive
    normalized = {unicodedata.normalize("NFC", p).casefold() for p in all_paths}
    assert len(normalized) == len(all_paths), "full path collisions"
    for name in all_paths:
        path = PurePosixPath(name)
        assert (
            not path.is_absolute()
            and str(path) == name
            and all(
                p not in {"", ".", ".."}
                and not re.search(r'[<>:"\\|?*\x00-\x1f]', p)
                and not p.endswith((".", " "))
                and not re.match(
                    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", p, re.IGNORECASE
                )
                for p in path.parts
            )
        ), "safe actual/reserved paths"
        assert units(str((vault / name).resolve())) <= 240, (
            "actual/reserved absolute path bounds"
        )
        assert all(
            unicodedata.normalize("NFC", str(parent)).casefold() not in normalized
            for parent in path.parents
            if str(parent) != "."
        ), "file/directory path prefix"
    assert (vault / "Categories.md").read_bytes() == (
        b"# Categories\n\n![[Templates/Bases/Categories.base]]\n"
    ), "native categories overview"
    assert load_json((vault / ".obsidian/core-plugins.json").read_bytes()) == {
        "file-explorer": True,
        "global-search": True,
        "switcher": True,
        "graph": True,
        "backlink": True,
        "tag-pane": True,
        "page-preview": True,
        "command-palette": True,
        "bookmarks": True,
        "properties": True,
        "bases": True,
        "templates": True,
    }, "native Bases configuration"
    assert record["obsidian_core_plugins_configuration"] == load_json(
        (vault / ".obsidian/core-plugins.json").read_bytes()
    ), "record core plugin configuration"
    template_config = {"folder": "Templates", "dateFormat": "YYYY-MM-DD"}
    assert (
        load_json((vault / ".obsidian/templates.json").read_bytes()) == template_config
    ), "native template configuration"
    assert record["obsidian_templates_configuration"] == template_config, (
        "record template configuration"
    )
    types_config = {
        "types": {
            "categories": "multitext",
            "appearance_category": "text",
            "icon": "text",
            "created": "date",
            "updated": "date",
            "tags": "tags",
            "aliases": "aliases",
            "source_collection_id": "text",
            "source_item_id": "text",
        }
    }
    assert load_json((vault / ".obsidian/types.json").read_bytes()) == types_config, (
        "native property type configuration"
    )
    assert record["obsidian_property_types_configuration"] == types_config, (
        "record property type configuration"
    )
    reserved = set(names.values()) | {
        ".obsidian/app.json",
        ".obsidian/bookmarks.json",
        "MIGRATION REPORT.md",
        "migration-record.json",
        "Uncreated targets.md",
        "Tag memberships.md",
    }
    for name in expected:
        if not name.endswith(".md"):
            continue
        text = (vault / name).read_bytes().decode()
        # Examples are documentation, not live navigation obligations. Bound
        # Markdown fences independently rather than importing converter parsing.
        active = []
        fence = None
        for line in text.splitlines(keepends=True):
            marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
            if fence:
                if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                    fence = None
            elif marker:
                fence = marker[1]
            else:
                active.append(line)
        text = "".join(active)
        for match in re.finditer(r"\[\[([^\]\n]+)\]\]", text):
            destination = match[1].split("|")[0].split("#")[0]
            assert destination in reserved | actual, "actual local wikilink destination"
        for match in re.finditer(r"!\[[^\]]*\]\((<[^>]+>|[^\s)]+)", text):
            destination = unquote(match[1].strip("<>"))
            if not re.match(r"[a-z]+://", destination, re.IGNORECASE):
                resolved = posixpath.normpath(
                    posixpath.join(posixpath.dirname(name), destination)
                )
                assert resolved in actual, "actual inline image destination"
    return len(actual)


def check_counts(raw, record, summary, references, targets, files):
    created = {t["item_key"] for t in record["item_targets"] if t["created"]}
    assigned = [r for r in raw["links.json"] if r["Meaning"] == 5]
    native = sum(r["ThoughtIdB"] in created for r in assigned)
    tags = {t["Id"] for t in raw["thoughts.json"] if t["Kind"] == 4}
    owners = {a["Id"]: a["SourceId"] for a in raw["attachments.json"]}
    live_references = sum(owners[key] in created for key, _, _ in references)
    expected = {
        "source_gaps": summary["source_gaps"],
        "generated_presentations": sum(bool(g["images"]) for g in raw.gaps.values()),
        "planned_generated_embeds": summary["generated_embeds"],
        "actual_generated_embeds": summary["generated_embeds"],
        "source_items": len(raw["thoughts.json"]),
        "source_relationships": len(raw["links.json"]),
        "source_references": len(references),
        "text_adaptations": 0,
        "present_assets": summary["payloads"]
        if "payloads" in summary
        else sum(a["availability"] == "present" for a in targets.values()),
        "planned_notes": summary["notes"],
        "planned_assets": sum(a["availability"] == "present" for a in targets.values()),
        "planned_references": live_references,
        "actual_notes": None,
        "actual_assets": None,
        "actual_files": None,
        "actual_references": live_references,
        "source_tags": len(tags),
        "tag_memberships": len(assigned),
        "native_tag_memberships": native,
        "uncreated_tag_memberships": len(assigned) - native,
        "created_tag_items": len(tags & created),
        "uncreated_tag_items": len(tags - created),
        "source_definitions": summary["category_notes"],
        "classification_assignments": summary["typed_members"],
        "typed_members": summary["typed_members"],
        "planned_category_notes": summary["category_notes"],
        "actual_category_notes": None,
        "planned_support_files": files
        - summary["notes"]
        - sum(a["availability"] == "present" for a in targets.values()),
        "actual_support_files": None,
    }
    assert record["counts"] == expected, "independent counts"


def check_adaptations(raw, record, documents, names, assets):
    created = {t["item_key"] for t in record["item_targets"] if t["created"]}
    definitions = {t["Id"] for t in raw["thoughts.json"] if t["Kind"] == 2}
    home = next(k for k, name in names.items() if name.startswith("Home — "))
    expected = {
        ("native_templates_configuration", ".obsidian/templates.json"),
        ("vault_maintenance_guide", "Vault guide.md"),
        ("categories_overview", home),
        ("native_bases_configuration", ".obsidian/core-plugins.json"),
    }
    expected |= {
        (kind, k)
        for kind in ("category_dashboard", "category_template")
        for k in definitions
    }
    expected |= {("canonical_properties", k) for k in created}
    expected |= {
        ("item_target", t["Id"])
        for t in raw["thoughts.json"]
        if t["Id"] in names and PurePosixPath(names[t["Id"]]).stem != t["Name"]
    }
    expected |= {
        ("relationship_presentation", k)
        for k, kind in relationships(raw).items()
        if kind in {"hierarchy", "related"}
    }
    for owner, (key, body) in documents.items():
        if owner in created:
            expected |= {
                (ref["kind"] + "_reference", f"reference:{key}:{i}")
                for i, ref in enumerate(source_references(body, owner, assets))
            }
    assignments = classifications(raw)
    for key in created:
        declared, calendar, icon = expected_metadata(raw, key, assets)
        if any(calendar.values()):
            expected.add(("source_calendar_dates", key))
        if any(declared.values()):
            expected.add(("declared_appearance", key))
        provider = assignments.get(key, {}).get("definition_key")
        effective = icon or (
            expected_metadata(raw, provider, assets)[2] if provider else None
        )
        if effective and key not in definitions:
            expected.add(("body_icon_snapshot", key))
    for a in raw["attachments.json"]:
        presentation = video(a)
        if presentation:
            expected.add(("video_embed", a["Id"]))
            if presentation["start_seconds"]:
                expected.add(("video_timing", a["Id"]))
    actual = {
        (a["kind"], a["affected"]): a["description"] for a in record["adaptations"]
    }
    assert len(actual) == len(record["adaptations"]) and set(actual) == expected, (
        "complete adaptation obligations"
    )
    assert all(type(d) is str and d for d in actual.values()), "adaptation descriptions"
    for kind, key in expected:
        if kind == "category_dashboard":
            assert all(
                fact in actual[kind, key]
                for fact in (
                    "Parents/Children navigation immediately follows the category title when present",
                    "Members and Gallery Bases follow that navigation",
                    "before retained source content",
                    "without a generated introductory icon image",
                    "link-preserving renames",
                )
            ), "category dashboard adaptation factual presentation"
        if kind == "item_target":
            assert names[key] in actual[kind, key], "naming adaptation factual target"
        if kind == "video_embed":
            a = next(a for a in raw["attachments.json"] if a["Id"] == key)
            assert video(a)["embed_uri"] in actual[kind, key], (
                "video adaptation factual URI"
            )
        if kind == "video_timing":
            a = next(a for a in raw["attachments.json"] if a["Id"] == key)
            assert str(video(a)["start_seconds"]) + " seconds" in actual[kind, key], (
                "video adaptation factual timing"
            )
        if kind == "body_icon_snapshot":
            provider = assignments.get(key, {}).get("definition_key")
            icon = expected_metadata(raw, key, assets)[2]
            effective = icon or expected_metadata(raw, provider, assets)[2]
            assert (
                effective in actual[kind, key]
                and ("owned icon" if icon else provider) in actual[kind, key]
            ), "icon adaptation factual asset/provider"
    for owner, (key, body) in documents.items():
        if owner in created:
            for i, ref in enumerate(source_references(body, owner, assets)):
                assert (
                    ref["target"]
                    in actual[ref["kind"] + "_reference", f"reference:{key}:{i}"]
                ), "reference adaptation factual identity"


def check_report(vault, raw, record, names, assets, summary, payloads):
    report = (vault / "MIGRATION REPORT.md").read_bytes().decode()
    assert (
        f"Created {summary['notes']} thought notes; preserved {payloads} present payloads."
        in report
    ), "independent report counts"
    obligations = (
        "Unsupported feature classes are refused",
        "[[Vault guide.md|Vault guide]]",
        "insertion-day ISO dates",
        "update dates are maintained explicitly",
        "embedding category",
        "Members table and Gallery after the title and any Parents/Children navigation",
        "without a generated introductory category image",
        "Retained source content and resources follow the Bases",
        "ordinary/member note-body image",
        "empty provider",
        "invalid provider",
        "migration-time snapshots",
        "Declared colours remain in migration-record.json only",
    )
    assert all(value in report for value in obligations), "required report obligations"
    absent = sorted(
        (
            (key, fact)
            for key, fact in raw.expected_warnings.items()
            if fact[0] == "known_absent_payload"
        ),
        key=lambda pair: (pair[1][1], pair[0]),
    )
    if absent:
        assert (
            report.count("## Source-gap evidence and optional repair checklist\n") == 1
        ), "required source-gap checklist"
        checklist = report.split(
            "## Source-gap evidence and optional repair checklist\n\n", 1
        )[1].split("\n## Source warnings\n", 1)[0]
        assert "Unknown prose, captions and layout were not recovered." in checklist, (
            "honest source-gap recovery limit"
        )
        meta = raw["meta.json"][0]
        collection = (
            escaped(meta.get("Name", "TheBrain collection"))
            .replace("\r", " ")
            .replace("\n", " ")
        )
        prefix = (
            "Source fingerprint: "
            + record["source_identity"]["source_sha256"]
            + "; scoped digest: "
            + record["source_identity"]["snapshot_digest"]
            + "; collection: "
            if raw.gaps
            else "Collection: "
        )
        suffix = (
            "."
            if raw.gaps
            else "; fingerprint and scoped digest are recorded in migration-record.json."
        )
        assert (
            prefix + collection + " (" + meta["BrainId"] + ")" + suffix in checklist
        ), "raw-bound checklist fingerprint/scope/collection"
        rows = re.split(r"(?m)^- \[ \] ", checklist)[1:]
        assert len(rows) == len(absent), "complete source-gap checklist cardinality"
        thoughts = {t["Id"]: t for t in raw["thoughts.json"]}
        created = {t["item_key"] for t in record["item_targets"] if t["created"]}
        diagnostics = {
            g["gap"]["asset_id"]: g
            for g in diagnostic_targets(
                raw,
                names,
                created,
                {k: expected_metadata(raw, k, assets)[2] for k in created},
            )[0]
        }
        for row, (key, (_, _, _, observed)) in zip(rows, absent, strict=True):
            owner = assets[key]["owner"]
            title = re.sub(r"[\[\]|\r\n]", " ", thoughts[owner]["Name"])
            destination = (
                wiki(names[owner], title)
                if owner in created
                else escaped(thoughts[owner]["Name"])
                + " (uncreated target: "
                + escaped(names[owner])
                + ")"
                if owner in names
                else escaped(thoughts[owner]["Name"]) + " (no vault-note target)"
            )
            diagnostic = diagnostics.get(key)
            role = diagnostic["gap"]["role"] if diagnostic else assets[key]["role"]
            outcome = (
                diagnostic["outcome"]
                if diagnostic
                else "metadata retained; bytes absent"
            )
            heading = (
                destination
                + "; thought ID "
                + owner
                + "; attachment "
                + key
                + "; role "
                + role
                + "; outcome "
                + outcome
                + ".\n"
            )
            assert row.startswith(heading), "raw owner/target/role/outcome diagnostic"
            lines = row[len(heading) :].rstrip("\n").splitlines()
            assert lines[0].startswith("  Declaration and physical absence: "), (
                "required raw diagnostic observation"
            )
            decoded = re.sub(r"\\([\\`*_{}\[\]<>#])", r"\1", lines[0].split(": ", 1)[1])
            assert semantic(load_json(decoded)) == semantic(observed), (
                "raw state/path/length/image diagnostic observation"
            )
            expected_lines = []
            if diagnostic:
                if diagnostic["provider_key"]:
                    members = diagnostic["affected_member_keys"]
                    expected_lines += [
                        "  Provider: " + destination + ".",
                        f"  Affected included members ({len(members)}):",
                    ]
                    expected_lines += [
                        "  - "
                        + wiki(names[k], thoughts[k]["Name"])
                        + "; thought ID "
                        + k
                        for k in members
                    ]
                expected_lines += [
                    "  - Image "
                    + image
                    + ": [["
                    + assets[image]["relative_path"]
                    + "]]"
                    for image in diagnostic["image_asset_ids"]
                ]
            assert lines[1:] == expected_lines, (
                "complete ordered provider/member/image diagnostic links"
            )
    else:
        assert "## Source-gap evidence and optional repair checklist" not in report, (
            "no fabricated source-gap checklist"
        )
    if any(
        a["Type"] == 1 and a["Location"].casefold().endswith(".pdf")
        for a in raw["attachments.json"]
    ):
        assert (
            "Vault Search does not search PDF body text" in report
            and "does not extract or index it" in report
        ), "PDF Search report limitation"
    if any(video(a) for a in raw["attachments.json"]):
        assert (
            "Offline playback and service availability are not guaranteed" in report
            and "original resource links remain available" in report
        ), "remote video report limitation"


def normalized_record(record):
    """Logical record after documented provenance and clock/order differences.

    Accounting and original evidence are separately checked against each ZIP;
    source-order pointers cannot be compared between reordered root streams.
    """

    set_fields = {
        "item_targets",
        "asset_targets",
        "relationships",
        "tag_memberships",
        "classification_assignments",
        "source_gaps",
        "generated_presentations",
        "support_artifacts",
        "reserved_support_paths",
        "adaptations",
        "issues",
    }

    def normalize(value, field=None):
        if isinstance(value, dict):
            return {
                k: normalize(v, k)
                for k, v in value.items()
                if k
                not in {
                    "evidence",
                    "metadata_evidence",
                    "original_evidence",
                    "source_accounting",
                }
            }
        if isinstance(value, list):
            result = [normalize(v) for v in value]
            return (
                sorted(result, key=lambda v: repr(semantic(v)))
                if field in set_fields
                else result
            )
        return value

    result = normalize(record)
    for field in ("source_sha256", "snapshot_digest"):
        result["source_identity"].pop(field)
    for field in ("run_id", "run_time", "bookmark_time"):
        result["run_metadata"].pop(field)
    return semantic(result)


def compare_vaults(first, second):
    first, second = Path(first), Path(second)

    def files(root):
        return {
            p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }

    a, b = files(first), files(second)
    assert a.keys() == b.keys(), "reproducible names/selections"
    for name in a:
        if name == "migration-record.json":
            assert normalized_record(load_json(a[name])) == normalized_record(
                load_json(b[name])
            ), "reproducible logical record"
        elif name == ".obsidian/bookmarks.json":
            aa, bb = load_json(a[name]), load_json(b[name])
            aa["items"][0].pop("ctime")
            bb["items"][0].pop("ctime")
            assert aa == bb, "reproducible bookmark"
        elif name == "MIGRATION REPORT.md":

            def normalized_report(data, record_data):
                identity = load_json(record_data)["source_identity"]
                return data.replace(
                    (
                        "Source fingerprint: "
                        + identity["source_sha256"]
                        + "; scoped digest: "
                        + identity["snapshot_digest"]
                        + ";"
                    ).encode(),
                    b"Source fingerprint: <source>; scoped digest: <scoped>;",
                )

            assert normalized_report(
                a[name], a["migration-record.json"]
            ) == normalized_report(b[name], b["migration-record.json"]), (
                "reproducible report facts"
            )
        else:
            assert a[name] == b[name], "reproducible content/resource bytes"


def check_run_result(result, vault, summary):
    vault = Path(vault)
    record = load_json((vault / "migration-record.json").read_bytes())
    expected = record["counts"] | {
        "actual_notes": summary["notes"],
        "actual_assets": summary["payloads"],
        "actual_files": summary["files"],
        "actual_category_notes": summary["category_notes"],
        "actual_support_files": record["counts"]["planned_support_files"],
    }
    assert result["counts"] == expected and result["receipt"]["counts"] == expected, (
        "actual result counts"
    )
    assert (
        result["issues"] == record["issues"]
        and len(result["issues"]) == summary["warnings"]
    ), "result warning evidence"
    receipt = result["receipt"]
    assert (
        result["source_identity"]
        == record["source_identity"]
        == receipt["source_identity"]
    ), "result source binding"
    assert (
        receipt["destination"] == str(vault.resolve())
        and receipt["published"] is True
        and receipt["verified"] is True
    ), "actual publication receipt"
    files = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    actual = {
        m["relative_path"]: (m["length"], m["sha256"]) for m in receipt["manifest"]
    }
    assert len(actual) == len(receipt["manifest"]) and actual == {
        name: (len(data), hashlib.sha256(data).hexdigest())
        for name, data in files.items()
    }, "receipt file evidence"
    assert (
        result["operation"] == "convert"
        and result["schema_version"] == 5
        and result["outcome"] == ("warnings" if summary["warnings"] else "clean")
    ), "result envelope"
