"""Independent acceptance oracle. Imports no converter modules.

Direct archive records/bytes are authoritative. The migration record supplies
assignments to audit, never the expected source data, eligibility or graph.
"""

import base64
import hashlib
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
        "support_artifacts",
        "reserved_support_paths",
        "adaptations",
        "source_accounting",
        "issues",
        "counts",
        "obsidian_configuration",
        "original_evidence",
    }, "migration record schema fields"
    assert (record["schema"], record["schema_version"]) == (
        "brz2obsidian.migration",
        2,
    ), "record schema version"
    with Path(source).open("rb") as stream:
        assert (
            record["source_identity"]["source_sha256"]
            == hashlib.file_digest(stream, "sha256").hexdigest()
        ), "source fingerprint"
    with ZipFile(source) as archive:
        assert archive.testzip() is None, "source CRC"
        raw = read_source(archive)
        assert (
            record["source_identity"]["source_id"] == raw["meta.json"][0]["BrainId"]
            and record["source_identity"]["format_version"] == "5"
        ), "collection source identity"
        assert (record["profile_id"], record["profile_version"]) == (
            "thebrain-format5-reviewed",
            "2",
        ), "reviewed source profile"
        originals = {e["key"]: e for e in record["original_evidence"]}
        for name in ROOTS:
            assert semantic(originals[name]["records"]) == semantic(raw[name]), (
                "original JSON"
            )
        targets = {a["asset_id"]: a for a in record["asset_targets"]}
        checked = set()
        for attachment in raw["attachments.json"]:
            kind = attachment["Type"]
            if kind in {3, 8, 15}:
                continue
            prefix = ".data/" if kind == 5 else ".data/md-images/" if kind == 12 else ""
            member = attachment["SourceId"] + "/" + prefix + attachment["Location"]
            assigned = targets[attachment["Id"]]
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
            checked.add(member)
        assert checked == {
            n for n in archive.namelist() if n not in ROOTS and not n.endswith("/")
        }, "payload accounting"
        summary, documents, names = check_items(raw, record, archive, vault, targets)
        references = check_documents(record, documents, names, targets)
        summary.update(check_assets(raw, record, archive, vault, targets))
        check_accounting(raw, record, checked, references)
        files = check_actual_files(vault, record, targets, names)
        check_counts(raw, record, summary, references, targets, files)
    return {
        "payloads": len(checked),
        "files": files,
        "references": len(references),
        "json_records": sum(map(len, raw.values())),
        **summary,
    }


def visible_label(value):
    return " ".join(re.sub(r"[\[\]|\r\n]", " ", value).split())


def wiki(target, label):
    return "[[" + target + "|" + visible_label(label) + "]]"


def escaped(value):
    return re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", value)


def readable(value):
    value = "".join(
        " " if unicodedata.category(c) == "Cc" else c
        for c in unicodedata.normalize("NFC", value)
    )
    value = value.replace(":", " - ").replace("[", "(").replace("]", ")")
    value = (
        " ".join(re.sub(r'[<>"/\\|?*#^%]', " ", value).split()).strip(" .")
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
    for _ in range(10):
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
        clashes = {
            k
            for stem, keys in groups.items()
            if len(keys) > 1 or stem in reserved
            for k in keys
        }
        if not clashes:
            return {
                k: ("" if k == home else "Notes/") + v + ".md" for k, v in paths.items()
            }
        for key in clashes:
            widths[key] = widths[key] + 4 if widths[key] else 8
    raise AssertionError("independent filename allocation failed")


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
    for _ in range(10):
        tokens = {}
        for key, base in names.items():
            suffix = "-" + key.replace("-", "")[: widths[key]] if widths[key] else ""
            value = base[: 120 - len(suffix)].rstrip("-")
            if value.isnumeric():
                value = "tag-" + value[: 116 - len(suffix)]
            tokens[key] = value + suffix
        clashes = {
            k
            for k, v in tokens.items()
            if sum(x.casefold() == v.casefold() for x in tokens.values()) > 1
        }
        if not clashes:
            return tokens
        for key in clashes:
            widths[key] = widths[key] + 4 if widths[key] else 8
    raise AssertionError("independent tag allocation failed")


def check_items(raw, record, archive, vault, assets):
    all_thoughts = {t["Id"]: t for t in raw["thoughts.json"]}
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
    content, documents = set(), {}
    for a in raw["attachments.json"]:
        owner, kind = a["SourceId"], a["Type"]
        if kind == 1 and (a["NoteType"] == 4 or a["Location"] == "Notes.md"):
            text = archive.read(owner + "/" + a["Location"]).decode("utf-8-sig")
            documents[owner] = (a["Id"], text)
            if text.strip():
                content.add(owner)
        elif kind in {3, 8} or (kind in {1, 12} and a["DataLength"] > 0):
            content.add(owner)
    created = (content & thoughts.keys()) | {home}
    initial = set(created)
    hierarchy = [
        (r["ThoughtIdA"], r["ThoughtIdB"])
        for r in raw["links.json"]
        if r["Meaning"] == 1 and r["Relation"] == 1
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
        reasons = (["content"] if key in content else []) + (
            ["home"] if key == home else []
        )
        if key in created and key not in initial:
            reasons = ["hierarchy"]
        assert target["creation_reasons"] == reasons, "creation reasons"
        assert target["vault_tag_token"] == tag_tokens.get(key), "native tag token"
        declared, calendar, icon = expected_metadata(raw, key, assets)
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
                "appearance_category_key": None,
                "effective_icon_asset_id": icon,
            }
            if key in created
            else None
        ), "migration-time owned icon decision"
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
    assert relations.keys() == {r["Id"] for r in raw["links.json"]}, (
        "all relationship identities"
    )
    for source in raw["links.json"]:
        r = relations[source["Id"]]
        a, b = source["ThoughtIdA"], source["ThoughtIdB"]
        kind = (
            "system"
            if source["Meaning"] == 6
            else "tag"
            if source["Meaning"] == 5
            else "hierarchy"
            if source["Relation"] == 1
            else "related"
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
            }[kind]
        ), "relationship presentation"
    memberships = {m["relationship_key"]: m for m in record["tag_memberships"]}
    assignments = [r for r in raw["links.json"] if r["Meaning"] == 5]
    assert memberships.keys() == {r["Id"] for r in assignments}, (
        "tag membership identities"
    )
    for r in assignments:
        a, b = r["ThoughtIdA"], r["ThoughtIdB"]
        m = memberships[r["Id"]]
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
        expected = "---\ncategories: []\nappearance_category:\n"
        expected += (
            "icon:"
            + (
                " " + json.dumps("[[" + assets[icon]["relative_path"] + "]]")
                if icon
                else ""
            )
            + "\n"
        )
        for name in ("foreground_color", "background_color"):
            expected += (
                name
                + ":"
                + (" " + json.dumps(declared[name]) if declared[name] else "")
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
        if icon:
            expected += "![[" + assets[icon]["relative_path"] + "]]\n\n"
        if thoughts[key].get("Label"):
            expected += thoughts[key]["Label"] + "\n\n"
        body = documents.get(key, (None, ""))[1]
        expected += adapt_body(body, key, names[key], names, assets)
        resources = expected_resources(raw, key, body, assets)
        if resources:
            expected += "\n\n" + resources
        sections = []
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
                sections.append(
                    "## "
                    + heading
                    + "\n\n"
                    + "".join(
                        "- " + wiki(names[n], thoughts[n]["Name"]) + "\n"
                        for n in sorted(neighbors)
                    )
                )
        if sections:
            normalized_end = expected.replace("\r\n", "\n").replace("\r", "\n")
            expected += (
                ""
                if normalized_end.endswith("\n\n")
                else "\n"
                if normalized_end.endswith("\n")
                else "\n\n"
            )
            expected += "\n".join(sections)
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
    icon = icons[0] if icons else None
    if icon:
        assert assets[icon]["relative_path"] and assets[icon]["actual_length"] > 0, (
            "present declared icon"
        )
    declared = {"icon_asset_id": icon}
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


def source_references(body, owner, assets):
    """Separate syntax scan for accepted inline forms in these acceptance inputs.

    It does not consume converter spans or use markdown-it-py. Protected source
    regions are masked without changing offsets. Unrecognized active local
    syntax fails this oracle instead of silently passing its coverage claim.
    """
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
    pattern = re.compile(
        r'(?P<image>!)?\[(?P<label>(?:\\.|[^\\\]])*)\]\((?P<destination><[^>]+>|(?:\\.|[^\s)])+)(?:\s+["\'][^"\']*["\'])?\)'
    )
    result = []
    for match in pattern.finditer(scan):
        destination = match["destination"]
        url = destination.removeprefix("<").removesuffix(">")
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
            assert not match["image"], "unexpected linked thought image"
        elif match["image"] and url.startswith(".data/md-images/"):
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
            label = re.sub(
                r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])', r"\1", match["label"]
            )
            result.append(
                {
                    "start": match.start(),
                    "end": match.end(),
                    "kind": kind,
                    "target": target,
                    "label": label,
                    "destination_start": match.start("destination")
                    + (1 if destination.startswith("<") else 0),
                    "destination_end": match.end("destination")
                    - (1 if destination.endswith(">") else 0),
                }
            )
            mask[match.start() : match.end()] = " " * (match.end() - match.start())
    remainder = "".join(mask)
    assert "brain://" not in remainder and ".data/md-images/" not in remainder, (
        "independent scanner cannot establish all active local reference coverage"
    )
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
                    source["Location"]
                    if kind == 3
                    else PureWindowsPath(source["Location"]).as_uri()
                )
                label = re.sub(r"([\\`*_{}<>])", r"\\\1", label)
                lines.append("- [" + label + "](<" + uri + ">)")
                assert (
                    assigned["external_uri"] == uri and assigned["resource_link"] == uri
                ), "external reference destination"
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


def check_documents(record, documents, names, assets):
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
        ) == (owner, key, digest, names.get(owner)), "document identity/digest"
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
            if actual["kind"] == "image":
                assert (
                    emitted_ref["destination_start"],
                    emitted_ref["destination_end"],
                ) == (actual["destination_start"], actual["destination_end"]), (
                    "image destination span"
                )
        all_references.extend((key, i, ref) for i, ref in enumerate(independent))
    return all_references


def expected_asset_paths(raw):
    owners = {t["Id"]: t["Id"].replace("-", "") for t in raw["thoughts.json"]}
    owner_widths = dict.fromkeys(owners, 8)
    for _ in range(8):
        tokens = {k: v[: owner_widths[k]] for k, v in owners.items()}
        clashes = {
            k for k, token in tokens.items() if list(tokens.values()).count(token) > 1
        }
        if not clashes:
            break
        for k in clashes:
            owner_widths[k] += 4
    present = [a for a in raw["attachments.json"] if a["Type"] not in {3, 8, 15}]
    widths = {a["Id"]: 0 for a in present}
    for _ in range(8):
        result = {}
        for a in present:
            base = readable(PurePosixPath(a["Location"]).name)
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
        for k in clashes:
            widths[k] = widths[k] + 4 if widths[k] else 8
    raise AssertionError("independent attachment filename allocation")


def check_assets(raw, record, archive, vault, targets):
    assert len(targets) == len(record["asset_targets"]) and targets.keys() == {
        a["Id"] for a in raw["attachments.json"]
    }, "all attachment identities"
    paths = expected_asset_paths(raw)
    expected_warnings = {}
    backups = 0
    for a in raw["attachments.json"]:
        key, kind, owner = a["Id"], a["Type"], a["SourceId"]
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
            if kind == 1 and (a["NoteType"] == 4 or a["Location"] == "Notes.md")
            else "file"
        )
        availability = (
            "external" if kind in {3, 8} else "absent" if kind == 15 else "present"
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
        if key in paths:
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
                and a["DataLength"] > 0
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
            observed = {
                "owner": owner,
                "filename": a["Location"],
                "declared_length": a["DataLength"],
                "state": 2,
                "present": False,
                "intact_same_owner_pdfs": pdfs,
            }
            expected_warnings[key] = (
                "known_absent_payload",
                "thebrain-format5/absent-txt/v1",
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
            assert finding["evidence"] == evidence, "warning source evidence pointers"
        else:
            assert not target["source_findings"], "no unexplained source finding"
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
    return {
        "backups": backups,
        "warnings": len(expected_warnings),
        "warning_owners": len({targets[k]["owner"] for k in expected_warnings}),
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
        if a["Type"] in {3, 8, 15}:
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


def check_actual_files(vault, record, targets, names):
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
        "MIGRATION REPORT.md",
        "migration-record.json",
    }
    for name in ("Uncreated targets.md", "Tag memberships.md"):
        if (vault / name).exists():
            expected.add(name)
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
        "MIGRATION REPORT.md": "report",
        "migration-record.json": "migration_record",
    }
    for name in ("Uncreated targets.md", "Tag memberships.md"):
        if name in actual:
            support[name] = "listing"
    assert {
        a["relative_path"]: a["purpose"] for a in record["support_artifacts"]
    } == support, "support artifact accounting"
    assert len(record["support_artifacts"]) == len(support), (
        "duplicate support artifact"
    )
    assert record["classification_assignments"] == [], "baseline classifications"
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
    }, "native Bases configuration"
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
        for match in re.finditer(r"\[\[([^\]\n]+)\]\]", text):
            destination = match[1].split("|")[0]
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
    live_references = sum(targets[key]["owner"] in created for key, _, _ in references)
    expected = {
        "source_items": len(raw["thoughts.json"]),
        "source_relationships": len(raw["links.json"]),
        "source_references": len(references),
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
        "source_definitions": 0,
        "classification_assignments": 0,
        "typed_members": 0,
        "planned_category_notes": 0,
        "actual_category_notes": None,
        "planned_support_files": files
        - summary["notes"]
        - sum(a["availability"] == "present" for a in targets.values()),
        "actual_support_files": None,
    }
    assert record["counts"] == expected, "independent counts"


def normalized_record(record):
    """Logical record after documented provenance and clock/order differences.

    Accounting and original evidence are separately checked against each ZIP;
    source-order pointers cannot be compared between reordered root streams.
    """

    def normalize(value):
        if isinstance(value, dict):
            return {
                k: normalize(v)
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
            return sorted(
                (normalize(v) for v in value), key=lambda v: repr(semantic(v))
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
        else:
            assert a[name] == b[name], "reproducible content/resource bytes"


def check_run_result(result, vault, summary):
    vault = Path(vault)
    record = load_json((vault / "migration-record.json").read_bytes())
    expected = record["counts"] | {
        "actual_notes": summary["notes"],
        "actual_assets": summary["payloads"],
        "actual_files": summary["files"],
        "actual_category_notes": 0,
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
        and result["schema_version"] == 2
        and result["outcome"] == ("warnings" if summary["warnings"] else "clean")
    ), "result envelope"
