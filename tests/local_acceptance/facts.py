"""Independent raw-source predicates. Only the standard library is imported."""

import hashlib
import re
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlsplit


def identities(records, label):
    result = {r["Id"]: r for r in records}
    assert len(result) == len(records), "duplicate raw " + label + " identity"
    return result


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
        if (
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
        elif signature == (1, 1, 2, -1) and roles == (2, 1):
            kind = "classification"
        elif signature == (1, 1, 5, -1) and roles == (4, 1):
            kind = "tag"
        else:
            raise AssertionError("raw relationship signature/roles")
        result[key] = kind
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
                thought["Kind"] == 1
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
    assert set(query) in ({"v"}, {"v", "t"}) and query["v"] == [match[1]], (
        "raw video identity/query"
    )
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
