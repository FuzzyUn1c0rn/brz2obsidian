"""Independent raw-source predicates. Only the standard library is imported."""

import hashlib
import re
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlsplit


def identities(records, label):
    result = {r["Id"]: r for r in records}
    assert len(result) == len(records), "duplicate raw " + label + " identity"
    return result


def navigation_selection(initial, relationships, output_version):
    """Derive materialized identities from independently admitted source edges."""
    if output_version == 9:
        neighbors = {
            endpoint
            for kind, left, right in relationships
            if kind in {"hierarchy", "related"}
            for endpoint in (left, right)
        }
        return initial | neighbors

    selected = set(initial)
    hierarchy = [(a, b) for kind, a, b in relationships if kind == "hierarchy"]
    while pending := [
        (a, b) for a, b in hierarchy if a not in selected and b not in selected
    ]:
        counts = {
            parent: sum(parent in pair for pair in pending)
            for parent in {a for a, _ in pending}
        }
        selected.add(min(counts, key=lambda key: (-counts[key], key)))
    return selected


def assert_acyclic(edges, message):
    """Iterative source-edge check, including branching and self-assignment."""
    adjacent = {}
    for left, right in edges:
        adjacent.setdefault(left, set()).add(right)
    done = set()
    for start in adjacent:
        active, stack = set(), [(start, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                active.remove(node)
                done.add(node)
            elif node not in done:
                assert node not in active, message
                active.add(node)
                stack.append((node, True))
                stack.extend((child, False) for child in adjacent.get(node, ()))


def relationships(raw):
    thoughts = identities(raw["thoughts.json"], "item")
    sources = identities(raw["links.json"], "relationship")
    result = {}
    for key, r in sources.items():
        a, b = r["ThoughtIdA"], r["ThoughtIdB"]
        assert a in thoughts and b in thoughts, "raw live relationship endpoints"
        signature = tuple(r[f] for f in ("Kind", "Relation", "Meaning", "Direction"))
        assert all(type(v) is int for v in signature), "raw relationship integers"
        roles = thoughts[a]["Kind"], thoughts[b]["Kind"]
        assert all(type(role) is int for role in roles), "raw endpoint role integers"
        assert all(
            r.get(field) is None or type(r[field]) is str and not r[field]
            for field in ("ThoughtTypeId", "LinkTypeId", "TypeId")
        ), "raw default relationship type"
        assert all(
            value is False for field, value in r.items() if field.startswith("Is")
        ), "raw reviewed relationship flags"
        if signature == (1, 1, 1, 3) and roles == (1, 1):
            kind = "hierarchy"
        elif signature == (1, 3, 1, -1) and roles in {
            (1, 2),
            (2, 1),
            (2, 2),
            (2, 4),
            (4, 2),
        }:
            kind = "related"
        elif (
            signature in {(1, 1, 1, -1), (1, 1, 1, 1), (1, 1, 1, 7)}
            and roles == (1, 1)
            or signature == (1, 1, 1, -1)
            and roles in {(1, 2), (1, 4)}
        ):
            kind = "hierarchy"
        elif signature in {
            (1, 3, 1, -1),
            (1, 3, 1, 3),
            (1, 3, 1, 5),
            (1, 3, 1, 7),
        } and roles == (1, 1):
            kind = "related"
        elif signature == (1, 1, 6, -1) and roles[0] == 5 and roles[1] in {1, 2, 4}:
            kind = "system"
        elif (signature == (1, 1, 2, -1) and roles == (2, 1)) or (
            signature == (1, 1, 3, -1) and roles == (2, 2)
        ):
            kind = "classification"
        elif (signature == (1, 1, 5, -1) and roles in {(4, 1), (4, 2)}) or (
            signature == (1, 1, 7, -1) and roles == (4, 4)
        ):
            kind = "tag"
        else:
            raise AssertionError("raw relationship signature/roles")
        result[key] = kind
    assert_acyclic(
        (
            (r["ThoughtIdA"], r["ThoughtIdB"])
            for r in sources.values()
            if result[r["Id"]] == "tag"
        ),
        "unqualified source tag cycle",
    )
    return result


def classifications(raw):
    thoughts = identities(raw["thoughts.json"], "item")
    kinds = relationships(raw)
    result = {}
    for index, thought in enumerate(raw["thoughts.json"]):
        key = thought["Id"]
        instances = [
            r
            for r in raw["links.json"]
            if kinds[r["Id"]] == "classification" and r["ThoughtIdB"] == key
        ]
        provider = thought.get("TypeId")
        if provider:
            assert (
                thought["Kind"] in {1, 2}
                and provider in thoughts
                and thoughts[provider]["Kind"] == 2
            ), "raw classification roles"
            assert len(instances) == 1 and instances[0]["ThoughtIdA"] == provider, (
                "raw field/link correspondence"
            )
            link = instances[0]
            result[key] = {
                "relationship_key": link["Id"],
                "definition_key": provider,
                "item_key": key,
                "evidence": [
                    f"thoughts.json:{index}",
                    f"links.json:{raw['links.json'].index(link)}",
                ],
            }
        else:
            assert not instances, "raw instance lacks TypeId"
    for origin in result:
        chain, node = [], origin
        while node in result:
            assert node not in chain, "raw source type-assignment cycle"
            chain.append(node)
            node = result[node]["definition_key"]
    return result


def member(a):
    prefix = (
        ".data/" if a["Type"] == 5 else ".data/md-images/" if a["Type"] == 12 else ""
    )
    return a["SourceId"] + "/" + prefix + a["Location"]


def note_ids(raw, archive):
    """Marked notes, empty placeholders and the fully eligible sole exception."""
    thoughts = identities(raw["thoughts.json"], "item")
    identities(raw["attachments.json"], "attachment")
    result = set()
    for a in raw["attachments.json"]:
        if a["Type"] != 1:
            continue
        canonical = a["Location"] == "Notes.md" and a["NoteType"] == 0
        if a["NoteType"] != 4 and not canonical:
            continue
        assert (a["SourceType"], a["Type"], a["NoteType"]) in {(2, 1, 4), (2, 1, 0)}, (
            "raw note role"
        )
        assert a["SourceId"] in thoughts, "raw note owner"
        assert type(a["DataLength"]) is int and a["DataLength"] >= 0, "raw note length"
        if a["Id"] in raw.gaps:
            continue
        assert raw["meta.json"][0]["AttachmentFileStates"][a["Id"]] == 1, (
            "raw note state"
        )
        data = archive.read(member(a))
        assert len(data) == a["DataLength"], "raw note integrity"
        text = data.decode("utf-8-sig")
        if canonical and text.strip():
            assert thoughts[a["SourceId"]]["Kind"] == 1, "exceptional ordinary owner"
            candidates = [
                p
                for p in raw["attachments.json"]
                if p["SourceId"] == a["SourceId"]
                and p["Type"] == 1
                and (p["NoteType"] == 4 or p["Location"] == "Notes.md")
            ]
            assert len(candidates) == 1, "exceptional sole note candidate"
        result.add(a["Id"])
    return result


def video(a):
    html = a.get("VideoHtml")
    if html in (None, ""):
        return None
    assert type(html) is str and (
        a["SourceType"],
        a["Type"],
        a["NoteType"],
        a["DataLength"],
    ) == (2, 3, 0, 0), "raw reviewed video role"
    match = re.fullmatch(
        r"<iframe width='100%' height='100%' src='https://www\.youtube\.com/embed/([A-Za-z0-9_-]{11})\?start=0' frameborder='0'></iframe>",
        html,
    )
    url = urlsplit(a["Location"])
    query = parse_qs(url.query, keep_blank_values=True)
    assert match and (url.scheme, url.netloc, url.path, url.fragment) == (
        "https",
        "www.youtube.com",
        "/watch",
        "",
    ), "raw reviewed video provider"
    assert set(query) in (
        {"v"},
        {"v", "t"},
        {"v", "list"},
        {"v", "list", "index"},
    ) and query["v"] == [match[1]], "raw video identity/query"
    for context in ("list", "index"):
        if context in query:
            assert len(query[context]) == 1 and query[context][0], "raw video context"
    seconds = 0
    if "t" in query:
        assert len(query["t"]) == 1 and re.fullmatch(r"[0-9]+s", query["t"][0]), (
            "raw video timing"
        )
        seconds = int(query["t"][0][:-1])
    return {
        "provider": "youtube",
        "embed_uri": f"https://www.youtube.com/embed/{match[1]}?start={seconds}",
        "start_seconds": seconds,
    }


def zero_txt_observation(raw, archive, a):
    stem = PurePosixPath(a["Location"]).stem
    pdfs = [
        p
        for p in raw["attachments.json"]
        if p["Id"] == stem
        and p["SourceId"] == a["SourceId"]
        and (p["SourceType"], p["Type"], p["NoteType"]) == (2, 1, 0)
        and PurePosixPath(p["Location"]).suffix.casefold() == ".pdf"
    ]
    assert len(pdfs) == 1, "zero TXT exact same-owner PDF identity"
    p = pdfs[0]
    assert raw["meta.json"][0]["AttachmentFileStates"][p["Id"]] == 1, (
        "zero TXT intact PDF state"
    )
    data = archive.read(member(p))
    assert type(p["DataLength"]) is int and len(data) == p["DataLength"], (
        "zero TXT intact PDF length"
    )
    return {
        "owner": a["SourceId"],
        "filename": a["Location"],
        "declared_length": 0,
        "state": 2,
        "present": False,
        "filename_stem": stem,
        "pdf_attachment_id": p["Id"],
        "pdf": {
            "owner": p["SourceId"],
            "filename": p["Location"],
            "source_type": 2,
            "type": 1,
            "note_type": 0,
            "state": 1,
            "member": member(p),
            "declared_length": p["DataLength"],
            "actual_length": len(data),
            "actual_sha256": hashlib.sha256(data).hexdigest(),
            "crc_valid": True,
        },
    }
