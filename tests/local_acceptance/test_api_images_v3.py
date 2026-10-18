"""Independent source-bound JPEG and finite ICO controls for issue 216."""

import hashlib
import json
from difflib import SequenceMatcher
from pathlib import Path

import pytest

from tests.local_acceptance.test_api_acceptance import (
    fingerprint,
    identity,
    reseal,
    source_case,
    write_json,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "local_api_images_v3"


def image_case(tmp_path):
    baseline, vault = source_case(tmp_path)
    root = baseline.manifest_path.parent
    graph_path = root / baseline.data["graphs"][identity(2)]
    graph = baseline.json(baseline.data["graphs"][identity(2)])
    image = graph["attachments"][1]
    image["location"] = image["id"] + ".jpg"
    write_json(graph_path, graph)
    (root / "202.bin").write_bytes((FIXTURES / "inert-blue.jpg").read_bytes())
    return reseal(baseline), vault, image


def put_payload(baseline, raw):
    (baseline.manifest_path.parent / "202.bin").write_bytes(raw)
    return reseal(baseline)


def image_note_prefix(name, explicit_owner=None, provider=None, effective_owner=None):
    """Literal presentation contract, independent of the checker predicate."""
    icon = (
        'icon: "[[Assets/' + identity(explicit_owner) + '/Icon.png]]"'
        if explicit_owner
        else "icon:"
    )
    category = (
        'appearance_category: "[[Type.md]]"' if provider else "appearance_category:"
    )
    result = "---\n" + icon + "\n" + category + "\n---\n\n# " + name + "\n\n"
    if effective_owner is not None:
        result += "![[Assets/" + identity(effective_owner) + "/Icon.png]]\n\n"
    return result


def first_document(record):
    return next(t for t in record["item_targets"] if t["item_key"] == identity(2))[
        "documents"
    ][0]


def image_source_case(tmp_path, scenario="basic"):
    """Return raw independently authored API observations, never output expectations."""
    baseline, _, image = image_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    graphs = {key: baseline.json(path) for key, path in manifest["graphs"].items()}
    new = []
    for key, owner, kind, location, file in [
        (205, 3, 12, identity(205) + ".jpg", "inert-blue.jpg"),
        (206, 2, 5, "Icon.png", "inert-a.ico"),
        (207, 4, 5, "Icon.png", "inert-b.ico"),
    ]:
        row = image | {
            "id": identity(key),
            "sourceId": identity(owner),
            "type": kind,
            "location": location,
        }
        graphs[identity(owner)]["attachments"].append(row)
        new.append(row)
        name = str(key) + ".bin"
        (root / name).write_bytes((FIXTURES / file).read_bytes())
        manifest["files"][name] = fingerprint(root / name)
        manifest["payloads"][identity(key)] = {"status": 200, "path": name}
        manifest["scope"]["attachment_ids"].append(identity(key))
    authored = (
        "Préface 🐈\n\n![bleu](.data/md-images/"
        + identity(202)
        + '.jpg "Titre")\n\n![deux](.data/md-images/'
        + identity(202)
        + ".jpg#$width=75p$)\n"
    )
    assert scenario in {"basic", "adapted"}, "literal source scenario"
    if scenario == "adapted":
        authored = (
            "Préface 🐈 <Enter>.\r\n\r\n"
            '|Item|Image|:(table="column-widths:-1,0,84;justification:default"):\r\n'
            "|[Child](brain://AAAAAAAAAECAAAAAAAAAAw/title)|![bleu](.data/md-images/"
            + identity(202)
            + '.jpg#$width=75p$ "Titre")|\r\n\r\n'
            + "> [!tip|icon:🐈]\r\n> ![deux](.data/md-images/"
            + identity(202)
            + ".jpg)\r\n"
        )
    (root / "201.bin").write_bytes(authored.encode())
    # Explicit inert wire observations; no provider or normalizer supplies defaults.
    thought_rows = {
        key: graph["activeThought"]
        | {
            "creationDateTime": "2024-01-02T03:04:05Z",
            "modificationDateTime": "2024-02-03T04:05:06Z",
            "foregroundColor": None,
            "backgroundColor": None,
        }
        for key, graph in graphs.items()
    }
    link_rows = {
        row["id"]: row
        | {
            "name": None,
            "color": None,
            "thickness": 1,
            "creationDateTime": "2024-01-02T03:04:05Z",
            "modificationDateTime": "2024-02-03T04:05:06Z",
        }
        for graph in graphs.values()
        for row in graph["links"]
    }
    attachment_rows = {
        row["id"]: row | {"position": 0}
        for graph in graphs.values()
        for row in graph["attachments"]
    }

    def canonical(value):
        if isinstance(value, list):
            return [canonical(v) for v in value]
        if isinstance(value, dict):
            key = value.get("id")
            if key in thought_rows:
                return thought_rows[key]
            if key in link_rows:
                return link_rows[key]
            if key in attachment_rows:
                return attachment_rows[key]
            return {k: canonical(v) for k, v in value.items()}
        return value

    graphs = {key: canonical(graph) | {"siblings": []} for key, graph in graphs.items()}
    write_json(root / manifest["types"], canonical(baseline.json(manifest["types"])))
    write_json(
        root / manifest["tags"]["path"],
        canonical(baseline.json(manifest["tags"]["path"])),
    )
    manifest["attachment_metadata"] = {}
    manifest["attachment_inventories"] = {}
    for owner, graph in graphs.items():
        write_json(root / manifest["graphs"][owner], graph)
        path = owner + "-attachments.json"
        write_json(root / path, graph["attachments"])
        manifest["files"][path] = fingerprint(root / path)
        manifest["attachment_inventories"][owner] = path
        for row in graph["attachments"]:
            path = row["id"] + "-metadata.json"
            write_json(root / path, row)
            manifest["files"][path] = fingerprint(root / path)
            manifest["attachment_metadata"][row["id"]] = {"status": 200, "path": path}

    def source_file(name, value):
        write_json(root / name, value)
        manifest["files"][name] = fingerprint(root / name)
        return name

    manifest["accessible_brains"] = source_file(
        "accessible-brains.json", [baseline.json(manifest["brain"])]
    )
    manifest["search"] = source_file(
        "search.json",
        [
            {
                "brainId": identity(1),
                "isFromOtherBrain": False,
                "sourceThought": {"id": key, "brainId": identity(1), "kind": 0},
                "sourceLink": None,
            }
            for key in sorted(thought_rows)
        ],
    )
    manifest["search_query"] = {
        "queryText": "*",
        "maxResults": "5000",
        "onlySearchThoughtNames": "false",
    }
    manifest["graph_query"] = {"includeSiblings": "true"}
    manifest["authoritative_thoughts"] = {
        key: source_file(key + "-thought.json", row)
        for key, row in thought_rows.items()
    }
    manifest["authoritative_links"] = {
        key: source_file(key + "-link.json", row) for key, row in link_rows.items()
    }
    brain = identity(1)
    http = {
        "/api/brains": {"status": 200, "path": manifest["accessible_brains"]},
        "/api/brains/" + brain: {"status": 200, "path": manifest["brain"]},
        "/api/brains/" + brain + "/statistics": [
            {"status": 200, "path": path} for path in manifest["statistics"]
        ],
        "/api/search/" + brain: {"status": 200, "path": manifest["search"]},
        "/api/thoughts/" + brain + "/types": {"status": 200, "path": manifest["types"]},
        "/api/thoughts/" + brain + "/tags": manifest["tags"],
    }
    for key in thought_rows:
        http["/api/thoughts/" + brain + "/" + key] = {
            "status": 200,
            "path": manifest["authoritative_thoughts"][key],
        }
        http["/api/thoughts/" + brain + "/" + key + "/graph"] = {
            "status": 200,
            "path": manifest["graphs"][key],
        }
        http["/api/thoughts/" + brain + "/" + key + "/attachments"] = {
            "status": 200,
            "path": manifest["attachment_inventories"][key],
        }
        if key in manifest["no_notes"]:
            http["/api/notes/" + brain + "/" + key] = {
                "status": 200,
                "path": manifest["no_notes"][key],
            }
    for key in link_rows:
        http["/api/links/" + brain + "/" + key] = {
            "status": 200,
            "path": manifest["authoritative_links"][key],
        }
        http["/api/links/" + brain + "/" + key + "/attachments"] = {
            "status": 200,
            "path": manifest["link_attachments"][key],
        }
    (root / "missing-404.bin").write_bytes(b"not found")
    manifest["files"]["missing-404.bin"] = fingerprint(root / "missing-404.bin")
    for key, outcome in manifest["payloads"].items():
        http["/api/attachments/" + brain + "/" + key + "/metadata"] = manifest[
            "attachment_metadata"
        ][key]
        http["/api/attachments/" + brain + "/" + key + "/file-content"] = (
            outcome
            if outcome["status"] == 200
            else {"status": 404, "path": "missing-404.bin"}
        )
    manifest["http_responses"] = http
    # Child now owns an unreferenced image, so its no-note wrapper stays required.
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    return baseline


def bound_case(tmp_path):
    """Independently authored expected vault for the source-only observation set."""
    baseline = image_source_case(tmp_path)
    vault = tmp_path / "vault"
    manifest = baseline.data
    graphs = {key: baseline.json(path) for key, path in manifest["graphs"].items()}
    authored = baseline.bytes(manifest["payloads"][identity(201)]["path"]).decode(
        "utf-8"
    )
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["profile_version"] = "3"
    all_rows = [row for graph in graphs.values() for row in graph["attachments"]]
    record["original_evidence"][0]["records"] = (
        [graph["activeThought"] for graph in graphs.values()]
        + list(
            {
                row["id"]: row for graph in graphs.values() for row in graph["links"]
            }.values()
        )
        + [row | {"position": {"decimal": "0"}} for row in all_rows]
    )
    for row in all_rows:
        key = row["id"]
        outcome = manifest["payloads"][key]
        if outcome["status"] != 200:
            continue
        raw = baseline.bytes(outcome["path"])
        relative = (
            "Assets/" + row["sourceId"] + "/" + row["location"]
            if row["type"] in {5, 12}
            else key + ".bin"
        )
        (vault / relative).parent.mkdir(parents=True, exist_ok=True)
        (vault / relative).write_bytes(raw)
        target = next(
            (a for a in record["asset_targets"] if a["asset_id"] == key), None
        )
        if target is None:
            target = {"asset_id": key}
            record["asset_targets"].append(target)
        target.update(
            owner=row["sourceId"],
            role="note_original"
            if row["isNotes"]
            else "image"
            if row["type"] == 12
            else "icon"
            if row["type"] == 5
            else "file",
            availability="present",
            relative_path=relative,
            original_name=row["location"],
            display_name=None,
            actual_length=len(raw),
            actual_sha256=hashlib.sha256(raw).hexdigest(),
        )
    for target in record["item_targets"]:
        key = target["item_key"]
        created = key != identity(5)
        icon = (
            identity(206)
            if key == identity(2)
            else identity(207)
            if key == identity(4)
            else None
        )
        provider = identity(4) if key == identity(3) else None
        target.update(
            documents=[],
            relative_path={
                identity(2): "Home.md",
                identity(3): "Child.md",
                identity(4): "Type.md",
                identity(5): "Tag.md",
            }[key],
            created=created,
            declared_appearance={
                "icon_asset_id": icon,
                "foreground_color": None,
                "background_color": None,
            }
            if icon
            else None,
            icon_snapshot={
                "item_key": key,
                "explicit_icon_asset_id": icon,
                "appearance_category_key": provider,
                "effective_icon_asset_id": icon
                or (identity(207) if provider else None),
            }
            if created
            else None,
        )
    digest = hashlib.sha256(authored.encode()).hexdigest()
    references = []
    for label, url in [
        ("bleu", ".data/md-images/" + identity(202) + ".jpg"),
        ("deux", ".data/md-images/" + identity(202) + ".jpg#$width=75p$"),
    ]:
        start = authored.index("![" + label + "]")
        end = authored.index(")", start) + 1
        dest = authored.index(url, start)
        norm = None
        if "#" in url:
            begin = dest + url.index("#")
            norm = {
                "declaration": "#$width=75p$",
                "start": begin,
                "end": dest + len(url),
                "document_digest": digest,
                "basis": "document.text/unicode_codepoints",
                "presentation": "responsive",
            }
        references.append(
            {
                "start": start,
                "end": end,
                "expected_original": authored[start:end],
                "kind": "image",
                "table_cell": False,
                "target": identity(202),
                "display_text": label,
                "document_digest": digest,
                "source_target": url,
                "destination_start": dest,
                "destination_end": dest + len(url),
                "presentation_normalization": norm,
            }
        )
    next(t for t in record["item_targets"] if t["item_key"] == identity(2))[
        "documents"
    ] = [
        {
            "key": identity(201),
            "owner": identity(2),
            "original_asset_id": identity(201),
            "original_copy_omitted": False,
            "text_adaptations": [],
            "evidence": ["attachment:" + identity(201)],
            "text_digest": digest,
            "owner_target": "Home.md",
            "references": references,
        }
    ]
    (vault / "Home.md").write_text(
        image_note_prefix("Home", 2, effective_owner=2)
        + "Préface 🐈\n\n![bleu]("
        + "Assets/"
        + identity(2)
        + "/"
        + identity(202)
        + '.jpg "Titre")\n\n![deux]('
        + "Assets/"
        + identity(2)
        + "/"
        + identity(202)
        + ".jpg)\n",
        encoding="utf-8",
    )
    (vault / "Child.md").write_text(
        image_note_prefix("Child", provider=4, effective_owner=4), encoding="utf-8"
    )
    (vault / "Type.md").write_text(image_note_prefix("Type", 4), encoding="utf-8")
    for asset in record["asset_targets"]:
        asset["retained_documents"] = []
    write_json(record_path, record)
    return baseline, vault


def add_empty_owner(baseline, vault, role):
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    owner, key = identity(6), identity(208)
    thought = {
        "id": owner,
        "brainId": identity(1),
        "kind": 1,
        "acType": 0,
        "forgottenDateTime": None,
        "name": "Empty",
        "typeId": None,
    }
    attachment = {
        "id": key,
        "brainId": identity(1),
        "sourceId": owner,
        "sourceType": 2,
        "type": 5 if role == "icon" else 12,
        "isNotes": False,
        "name": None,
        "location": "Icon.png" if role == "icon" else key + ".jpg",
    }
    graph = {
        "activeThought": thought,
        "attachments": [attachment],
        "links": [],
        "children": [],
        "parents": [],
        "jumps": [],
        "tags": [],
        "type": None,
    }

    def evidence(name, value):
        write_json(root / name, value)
        manifest["files"][name] = fingerprint(root / name)
        return name

    manifest["graphs"][owner] = evidence("empty-graph.json", graph)
    manifest["attachment_inventories"][owner] = evidence(
        "empty-inventory.json", [attachment]
    )
    manifest["attachment_metadata"][key] = {
        "status": 200,
        "path": evidence("empty-metadata.json", attachment),
    }
    manifest["no_notes"][owner] = evidence(
        "empty-note.json",
        {
            "brainId": identity(1),
            "sourceId": owner,
            "sourceType": 2,
            "markdown": "",
            "html": None,
            "text": None,
            "modificationDateTime": "0001-01-01T00:00:00",
        },
    )
    manifest["scope"]["thought_ids"].append(owner)
    manifest["scope"]["attachment_ids"].append(key)
    for path in manifest["statistics"]:
        stats = json.loads((root / path).read_bytes())
        stats["thoughts"] += 1
        write_json(root / path, stats)
    raw = (
        FIXTURES / ("inert-a.ico" if role == "icon" else "inert-blue.jpg")
    ).read_bytes()
    (root / "208.bin").write_bytes(raw)
    manifest["files"]["208.bin"] = fingerprint(root / "208.bin")
    manifest["payloads"][key] = {"status": 200, "path": "208.bin"}
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["original_evidence"][0]["records"] += [thought, attachment]
    record["asset_targets"].append(
        {
            "asset_id": key,
            "owner": owner,
            "retained_documents": [],
            "role": role,
            "availability": "present",
            "relative_path": "Assets/" + owner + "/" + attachment["location"],
            "original_name": attachment["location"],
            "display_name": None,
            "actual_length": len(raw),
            "actual_sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
    relative = "Assets/" + owner + "/" + attachment["location"]
    (vault / relative).parent.mkdir(parents=True, exist_ok=True)
    (vault / relative).write_bytes(raw)
    record["item_targets"].append(
        {
            "item_key": owner,
            "documents": [],
            "original_identity": owner,
            "original_title": "Empty",
            "relative_path": "Empty.md",
            "created": role == "image",
            "declared_appearance": {
                "icon_asset_id": key,
                "foreground_color": None,
                "background_color": None,
            }
            if role == "icon"
            else None,
            "icon_snapshot": {
                "item_key": owner,
                "explicit_icon_asset_id": None,
                "appearance_category_key": None,
                "effective_icon_asset_id": None,
            }
            if role == "image"
            else None,
        }
    )
    if role == "image":
        (vault / "Empty.md").write_text(image_note_prefix("Empty"), encoding="utf-8")
    write_json(path, record)
    return baseline


def add_ico_to_owner(baseline, vault, owner, name, provider=None):
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    path = root / manifest["graphs"][identity(owner)]
    graph = json.loads(path.read_bytes())
    row = {
        "id": identity(209),
        "brainId": identity(1),
        "sourceId": identity(owner),
        "sourceType": 2,
        "type": 5,
        "isNotes": False,
        "location": "Icon.png",
        "name": None,
    }
    graph["attachments"].append(row)
    write_json(path, graph)
    write_json(
        root / manifest["attachment_inventories"][identity(owner)], graph["attachments"]
    )
    write_json(root / "209-metadata.json", row)
    manifest["files"]["209-metadata.json"] = fingerprint(root / "209-metadata.json")
    manifest["attachment_metadata"][identity(209)] = {
        "status": 200,
        "path": "209-metadata.json",
    }
    manifest["scope"]["attachment_ids"].append(identity(209))
    manifest["payloads"][identity(209)] = manifest["payloads"][identity(206)]
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["original_evidence"][0]["records"].append(row)
    direct = next(a for a in record["asset_targets"] if a["asset_id"] == identity(206))
    record["asset_targets"].append(
        direct
        | {
            "asset_id": identity(209),
            "owner": identity(owner),
            "relative_path": "Assets/" + identity(owner) + "/Icon.png",
        }
    )
    copied = vault / ("Assets/" + identity(owner) + "/Icon.png")
    copied.parent.mkdir(parents=True, exist_ok=True)
    copied.write_bytes((FIXTURES / "inert-a.ico").read_bytes())
    child = next(t for t in record["item_targets"] if t["item_key"] == identity(owner))
    child["declared_appearance"] = {
        "icon_asset_id": identity(209),
        "foreground_color": None,
        "background_color": None,
    }
    child["icon_snapshot"].update(
        explicit_icon_asset_id=identity(209), effective_icon_asset_id=identity(209)
    )
    write_json(path, record)
    (vault / (name + ".md")).write_text(
        image_note_prefix(name, owner, provider=provider, effective_owner=owner),
        encoding="utf-8",
    )
    return baseline


ADAPTED_IMAGE_NOTES = [
    pytest.param(
        'Préface 🐈 <Enter>.\n\n> [!tip|icon:🐈]\n> ![bleu]({image}#$width=75p$ "Titre")\n',
        'Préface 🐈 \\<Enter>.{eol}{eol}> [!tip] 🐈 Tip{eol}> ![bleu]({image}#$width=75p$ "Titre"){eol}',
        id="callout-literal",
    ),
    pytest.param(
        '|Image|Other|:(table="column-widths:-1,0,84;justification:default"):\n|![bleu]({image})|value|\n',
        "|Image|Other|\n|---|---|{eol}|![bleu]({image})|value|{eol}",
        id="table",
    ),
    pytest.param(
        "[/toc/]\n\n# Heading\n![bleu]({image})\n",
        "- [Heading](#^brz-toc-heading-1){eol}{eol}# Heading ^brz-toc-heading-1{eol}![bleu]({image}){eol}",
        id="toc",
    ),
    pytest.param(
        "`![false]({image})`\n\n<!-- ![false]({image}) -->\n\n> [!info|icon:🐈]\n> ![bleu]({image}#$width=50p$)\n",
        "`![false]({image})`{eol}{eol}<!-- ![false]({image}) -->{eol}{eol}> [!info] 🐈 Info{eol}> ![bleu]({image}#$width=50p$){eol}",
        id="protected",
    ),
    pytest.param(
        'Préface <Enter>.\n\n[/toc/]\n\n# Images\n|Image|Other|:(table="column-widths:-1,0,84;justification:default"):\n|![bleu]({image}#$width=50p$)|value|\n\n> [!tip|icon:🐈]\n> ![deux]({image} "Titre")\n',
        'Préface \\<Enter>.{eol}{eol}- [Images](#^brz-toc-heading-1){eol}{eol}# Images ^brz-toc-heading-1{eol}|Image|Other|\n|---|---|{eol}|![bleu]({image}#$width=50p$)|value|{eol}{eol}> [!tip] 🐈 Tip{eol}> ![deux]({image} "Titre"){eol}',
        id="combined",
    ),
]

ADAPTED_IMAGE_NOTES += [
    pytest.param(
        "Préface 🐈 <Enter>.\n\n![bleu]({image})\n",
        "Préface 🐈 \\<Enter>.{eol}{eol}![bleu]({image}){eol}",
        id="literal-only",
    ),
    pytest.param(
        "Préface 🐈\n\n![bleu]({image})\n",
        "Préface 🐈{eol}{eol}![bleu]({image}){eol}",
        id="unchanged",
    ),
    pytest.param(
        "[/toc/]\n\n# First\nText\n\n## Second\n![bleu]({image})\n",
        "- [First](#^brz-toc-heading-1)\n  - [Second](#^brz-toc-heading-2){eol}{eol}# First ^brz-toc-heading-1{eol}Text{eol}{eol}## Second ^brz-toc-heading-2{eol}![bleu]({image}){eol}",
        id="toc-multiple",
    ),
    pytest.param(
        "[/toc/]\n\nMulti\nline\n====\n![bleu]({image})\n",
        "- [Multi line](#^brz-toc-heading-1){eol}{eol}# Multi line ^brz-toc-heading-1{eol}![bleu]({image}){eol}",
        id="toc-setext",
    ),
    pytest.param(
        "> `begin\nlazy ![false]({image})\n> end`\n\n> [!info|icon:🐈]\n> ![bleu]({image}#$width=50p$)\n",
        "> `begin{eol}lazy ![false]({image}){eol}> end`{eol}{eol}> [!info] 🐈 Info{eol}> ![bleu]({image}#$width=50p$){eol}",
        id="protected-lazy",
    ),
]

ADAPTED_IMAGE_NOTES += [
    pytest.param(
        '|Code|Image|:(table="column-widths:-1,0,84;justification:default"):\n|`![false](.data/md-images/missing.jpg)|x`|![bleu]({image})|\n',
        "|Code|Image|\n|---|---|{eol}|<code>![false](.data/md-images/missing.jpg)&#124;x</code>|![bleu]({image})|{eol}",
        id="table-code-false-target",
    ),
    pytest.param(
        "> `begin\nlazy ![false](.data/md-images/missing.jpg)\n> end`\n\n> [!info|icon:🐈]\n> ![bleu]({image}#$width=50p$)\n",
        "> `begin{eol}lazy ![false](.data/md-images/missing.jpg){eol}> end`{eol}{eol}> [!info] 🐈 Info{eol}> ![bleu]({image}#$width=50p$){eol}",
        id="lazy-false-target",
    ),
]


def fixture_adaptations(raw, adapted):
    """Literal template pairs supply valid noncanonical line edit segmentation."""
    before, after = raw.splitlines(keepends=True), adapted.splitlines(keepends=True)
    regions = []
    for tag, a, b, c, d in SequenceMatcher(
        None, before, after, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        if a == b:
            if b < len(before):
                b += 1
                d += 1
            else:
                a -= 1
                c -= 1
        if regions and a <= regions[-1][1] and c <= regions[-1][3]:
            old = regions.pop()
            a, c = old[0], old[2]
        regions.append((a, b, c, d))
    edits = []
    for a, b, c, d in regions:
        original, replacement = "".join(before[a:b]), "".join(after[c:d])
        insert = (
            any(token in original for token in (":(table=", "[/toc/]", "> [!"))
            or (
                "[/toc/]" in raw
                and any(
                    line.lstrip().startswith(("#", "=", "-")) for line in before[a:b]
                )
            )
            or (":(table=" in raw and "`" in original)
            or ("> [!" in raw and original.lstrip().startswith(">"))
        )
        edits.append(
            {
                "kind": "markdown_insert" if insert else "literal_text",
                "start": len("".join(before[:a])),
                "end": len("".join(before[:b])),
                "before": original,
                "after": replacement,
                "adapted_start": len("".join(after[:c])),
                "adapted_end": len("".join(after[:d])),
                "source_digest": hashlib.sha256(raw.encode()).hexdigest(),
                "source_basis": "scoped_source_text/unicode_codepoints",
                "adapted_basis": "document.text/unicode_codepoints",
            }
        )
    return edits


def adapted_note_case(tmp_path, raw_template, adapted_template, ending="\n"):
    baseline, vault = bound_case(tmp_path)
    url = ".data/md-images/" + identity(202) + ".jpg"
    raw = raw_template.format(image=url).replace("\n", ending)
    adapted = adapted_template.format(image=url, eol=ending)
    root = baseline.manifest_path.parent
    (root / "201.bin").write_bytes(raw.encode())
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    original = next(
        a for a in record["asset_targets"] if a["asset_id"] == identity(201)
    )
    (vault / original["relative_path"]).write_bytes(raw.encode())
    original.update(
        actual_length=len(raw.encode()),
        actual_sha256=hashlib.sha256(raw.encode()).hexdigest(),
    )
    digest = hashlib.sha256(adapted.encode()).hexdigest()
    references = []
    for label in ("bleu", "deux"):
        phrase = "![" + label + "]"
        if phrase not in adapted:
            continue
        start = adapted.index(phrase)
        end = adapted.index(")", start) + 1
        dest_start = adapted.index(url, start)
        dest_end = min(
            end - 1,
            adapted.find(" ", dest_start)
            if " " in adapted[dest_start : end - 1]
            else end - 1,
        )
        source_target = adapted[dest_start:dest_end]
        normalization = None
        if "#" in source_target:
            begin = dest_start + source_target.index("#")
            normalization = {
                "declaration": adapted[begin:dest_end],
                "start": begin,
                "end": dest_end,
                "document_digest": digest,
                "basis": "document.text/unicode_codepoints",
                "presentation": "responsive",
            }
        references.append(
            {
                "start": start,
                "end": end,
                "expected_original": adapted[start:end],
                "kind": "image",
                "table_cell": adapted[
                    max(adapted.rfind("\n", 0, start), adapted.rfind("\r", 0, start))
                    + 1 : start
                ]
                .lstrip()
                .startswith("|"),
                "target": identity(202),
                "display_text": label,
                "document_digest": digest,
                "source_target": source_target,
                "destination_start": dest_start,
                "destination_end": dest_end,
                "presentation_normalization": normalization,
            }
        )
    first_document(record).update(
        text_digest=digest,
        references=references,
        text_adaptations=fixture_adaptations(raw, adapted),
    )
    displayed = adapted
    actual = next(a for a in record["asset_targets"] if a["asset_id"] == identity(202))[
        "relative_path"
    ]
    for ref in sorted(references, key=lambda r: r["destination_start"], reverse=True):
        displayed = (
            displayed[: ref["destination_start"]]
            + actual
            + displayed[ref["destination_end"] :]
        )
    displayed = displayed.replace("\r\n", "\n").replace("\r", "\n")
    (vault / "Home.md").write_text(
        image_note_prefix("Home", 2, effective_owner=2) + displayed, encoding="utf-8"
    )
    write_json(path, record)
    return baseline, vault, adapted


def mixed_reference_case(tmp_path):
    uri = "brain://AAAAAAAAAECAAAAAAAAAAw/title"
    raw = (
        "[Child]("
        + uri
        + ")\r\n\r\n|Item|Image|\r\n|---|---|\r\n|[Child]("
        + uri
        + ")|![bleu]({image})|\r\n"
    )
    baseline, vault, text = adapted_note_case(tmp_path, raw, raw)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    doc = first_document(record)
    doc["references"][0]["table_cell"] = True
    phrase = "[Child](" + uri + ")"
    for start in [text.index(phrase), text.index(phrase, text.index(phrase) + 1)]:
        doc["references"].append(
            {
                "start": start,
                "end": start + len(phrase),
                "expected_original": phrase,
                "kind": "item",
                "target": identity(3),
                "display_text": "Child",
                "table_cell": start > text.index("|---|---|"),
                "document_digest": hashlib.sha256(text.encode()).hexdigest(),
                "source_target": uri,
                "destination_start": None,
                "destination_end": None,
                "presentation_normalization": None,
            }
        )
    doc["references"].sort(key=lambda row: row["start"])
    write_json(path, record)
    image_path = "Assets/" + identity(2) + "/" + identity(202) + ".jpg"
    display = text.replace(
        "![bleu](.data/md-images/" + identity(202) + ".jpg)",
        "![bleu](" + image_path + ")",
    )
    display = display.replace(phrase, "[[Child.md|Child]]", 1).replace(
        phrase, "[[Child.md\\|Child]]"
    )
    (vault / "Home.md").write_text(
        image_note_prefix("Home", 2, effective_owner=2) + display.replace("\r\n", "\n"),
        encoding="utf-8",
    )
    return baseline, vault
