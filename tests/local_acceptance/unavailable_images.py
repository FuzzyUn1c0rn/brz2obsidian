"""Raw-source image absence and staged proof audit, without producer imports."""

import hashlib
import json
import re
from urllib.parse import quote, unquote, urlsplit
from uuid import UUID

from .note_links import markdown_destination
from .text import inline_candidates

IMAGE_KINDS = {"image_unavailable", "markdown_insert_image_unavailable"}
RULES = {"thebrain.unavailable-image.v1", "thebrain.unavailable-declared-image.v1"}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def image_location(uri, *, authored=None):
    raw = uri if authored is None else authored
    assert uri.startswith(".data/md-images/"), "raw exact local image prefix"
    path, separator, fragment = uri.partition("#")
    assert (
        "?" not in uri
        and "?" not in raw
        and (
            not separator
            or re.fullmatch(r"\$width=([1-9]|[1-9][0-9]|100)p\$", fragment)
            and raw.rsplit("#", 1)[-1] == fragment
        )
    ), "raw unavailable image destination grammar"
    value = path.removeprefix(".data/md-images/")
    assert not any(
        re.search(r"%(?![0-9a-fA-F]{2})|%(?:2[fF]|5[cC])", path)
        for path in (raw.split("#", 1)[0], value)
    ), "raw unavailable image encoding"
    value = unquote(value, errors="strict")
    assert (
        not re.search(r"%[0-9a-fA-F]{2}", value)
        and not any(c in value for c in "\\:")
        and not any(ord(c) < 32 or ord(c) == 127 for c in value)
        and not any(segment in {"", ".", ".."} for segment in value.split("/"))
    ), "raw unavailable image safe relative path"
    return value


def api_images(baseline):
    """Only independently bound owned metadata and content outcomes decide absence."""
    rows = {}
    for path in baseline.data["attachment_inventories"].values():
        for row in baseline.json(path):
            assert row["id"] not in rows, "raw image inventory unique identity"
            rows[row["id"]] = row
    bindings, absent = {}, {}
    for key, row in rows.items():
        outcome = baseline.data["payloads"].get(key)
        bindings[key] = {
            "asset_id": key,
            "owner": row["sourceId"],
            "role": "image" if row["type"] == 12 and not row["isNotes"] else "other",
            "original_name": row["location"],
            "availability": "absent"
            if outcome and outcome["status"] == 404
            else "present",
        }
        if row["type"] != 12 or not outcome or outcome["status"] != 404:
            continue
        metadata = baseline.data["attachment_metadata"][key]
        assert metadata["status"] == 200 and baseline.json(metadata["path"]) == row, (
            "raw declared image metadata200"
        )
        assert (
            row["sourceType"] == 2
            and row["isNotes"] is False
            and row["location"]
            in {key + suffix for suffix in (".webp", ".png", ".jpg", ".svg")}
        ), "raw absent image role"
        assert "http_responses" in baseline.data, (
            "image404 requires independently recorded request closure"
        )
        ledger = baseline.json(baseline.data["http_responses"])
        captured = [
            r for r in ledger["occurrences"] if r["phase"] == "source-acquisition"
        ]
        # Converter acquisition requests are exactly the recorder's source phase;
        # completion/qualification traffic has no acquisition sequence authority.
        prefix = "/api/attachments/" + row["brainId"] + "/" + key
        metadata_rows = [
            (i, r)
            for i, r in enumerate(captured, 1)
            if urlsplit(r["target"]).path == prefix + "/metadata"
        ]
        content_rows = [
            (i, r)
            for i, r in enumerate(captured, 1)
            if urlsplit(r["target"]).path == prefix + "/file-content"
        ]
        assert (
            len(metadata_rows) == len(content_rows) == 1
            and metadata_rows[0][1]["status"] == 200
            and content_rows[0][1]["status"] == 404
        ), "raw exact image metadata/content outcome join"
        absent[key] = {
            "basis": "api_declared_content404",
            "metadata_sequence": metadata_rows[0][0],
            "request_sequence": content_rows[0][0],
            "status": 404,
            "asset_id": key,
        }
    return bindings, absent


def expectation(raw, owner, bindings, absent, *, basis, profile_version="4"):
    """Rebuild copied origins at independent insert builders, then notice events."""
    from .api_note_text import callouts, contents, literal_note_edits, tables
    from .checker import inline_display

    literal = literal_note_edits(raw, profile_version=profile_version)
    text, origins = raw, list(range(len(raw)))
    for edit in reversed(literal):
        start, end = edit["start"], edit["end"]
        replacement = edit["after"]
        assert replacement in {"", "\\" + edit["before"]}, (
            "independent literal origin operation"
        )
        copied = ([None] + origins[start:end]) if replacement else []
        text = text[:start] + replacement + text[end:]
        origins[start:end] = copied
    source = {}
    for start, end, image, label, left, right in inline_candidates(text)[0]:
        uri = quote(
            markdown_destination(text[left:right]), safe="/:?#@!$&'()*+,;=-._~%"
        )
        if image and uri.startswith(".data/md-images/"):
            a, b = origins[start], origins[end - 1] + 1
            angle = text[left - 1 : left] == "<" and text[right : right + 1] == ">"
            destination_left, destination_right = (
                (left - 1, right + 1) if angle else (left, right)
            )
            source[a, b] = {
                "start": a,
                "end": b,
                "before": raw[a:b],
                "source_digest": digest(raw),
                "uri": uri,
                "label": inline_display(label),
                "destination_start": origins[destination_left],
                "destination_end": origins[destination_right - 1] + 1,
            }
    for transform in (tables, callouts, contents):
        options = (
            {"current_tables": profile_version in {"4", "5"}}
            if transform is tables
            else {}
        )
        text = transform(text, origins=origins, **options)
        assert len(origins) == len(text), "independent insert copied-origin length"
    intermediate = text
    # Active HTML was independently refused before insert builders. These code
    # elements can therefore only be products of the reviewed table code builder.
    masked = re.sub(r"<code>[^<]*</code>", lambda m: " " * len(m[0]), text)
    events = []
    for start, end, image, _label, left, right in inline_candidates(masked)[0]:
        authored_uri = text[left:right]
        uri = quote(markdown_destination(authored_uri), safe="/:?#@!$&'()*+,;=-._~%")
        if not image or not uri.startswith(".data/md-images/"):
            continue
        filename = image_location(uri, authored=authored_uri)
        owned = [
            a
            for a in bindings.values()
            if a["owner"] == owner and a["original_name"] == filename
        ]
        if (
            len(owned) == 1
            and owned[0]["role"] == "image"
            and owned[0].get("availability", "present") == "present"
        ):
            continue
        declared = (
            owned[0]
            if len(owned) == 1
            and owned[0]["role"] == "image"
            and owned[0]["asset_id"] in absent
            else None
        )
        assert not owned or declared is not None, (
            "raw missing image conflicts with owned declaration"
        )
        suffixes = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "avif", "svg"}
        assert filename.rsplit(".", 1)[-1].lower() in suffixes, (
            "raw unavailable image supported filename"
        )
        try:
            identity = str(UUID(filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]))
        except ValueError:
            identity = None
        assert identity not in {
            a["asset_id"] for a in bindings.values() if a["owner"] != owner
        }, "raw unavailable image foreign identity"
        pair = origins[start], origins[end - 1] + 1
        assert pair in source and all(
            value is None or pair[0] <= value < pair[1] for value in origins[start:end]
        ), "independent missing image copied source occurrence"
        reference = source[pair]
        label = (
            reference["label"].replace("\\<", "<").strip()
            or filename.rsplit("/", 1)[-1]
        )
        label = " ".join(label.split())
        notice = "Image unavailable: " + "".join(
            f"&#{ord(c)};" if c.isascii() and not c.isalnum() and not c.isspace() else c
            for c in label
        )
        absence = absent[declared["asset_id"]] if declared else {"basis": basis}
        events.append(
            {
                "owner": owner,
                "source_reference": reference,
                "intermediate_reference": {
                    "start": start,
                    "end": end,
                    "before": text[start:end],
                    "document_digest": digest(text),
                },
                "absence": absence | {"location": filename},
                "notice": {"text": notice},
            }
        )
    for event in reversed(events):
        span = event["intermediate_reference"]
        text = text[: span["start"]] + event["notice"]["text"] + text[span["end"] :]
    delta = 0
    for event in events:
        span, notice = event["intermediate_reference"], event["notice"]
        begin = span["start"] + delta
        notice.update(
            start=begin,
            end=begin + len(notice["text"]),
            document_digest=digest(text),
        )
        delta += len(notice["text"]) - len(span["before"])
    owned_absent = set(absent).intersection(
        a["asset_id"] for a in bindings.values() if a["owner"] == owner
    )
    assert owned_absent <= {
        e["absence"]["asset_id"] for e in events if "asset_id" in e["absence"]
    }, "unreferenced absent image"
    return text, intermediate, events


def validate(raw, final, intermediate, edits, events, observed):
    """Check occurrence proof and independently qualified base edit ownership."""
    from .api_note_text import validate_document_adaptations

    assert len(observed) == len(events), (
        "complete unavailable image occurrence evidence"
    )
    actual = sorted(observed, key=lambda o: o["source_reference"]["start"])
    expected = sorted(events, key=lambda o: o["source_reference"]["start"])
    base = [e for e in edits if e["kind"] not in IMAGE_KINDS]
    proof_by_flat = {}
    for claimed, event in zip(actual, expected, strict=True):
        assert {
            k: v for k, v in claimed.items() if k not in {"composition", "document"}
        } == event, (
            "raw-derived unavailable image source/intermediate/final/absence evidence"
        )
        proof = claimed["composition"]
        assert (
            set(proof) == {"base_edits", "flat_edit"}
            and type(proof["flat_edit"]) is int
        ), "unavailable image composition fields"
        index = proof["flat_edit"]
        assert 0 <= index < len(edits), "unavailable image containing edit"
        edit = edits[index]
        assert (
            edit["kind"] in IMAGE_KINDS
            and edit["start"]
            <= event["source_reference"]["start"]
            < event["source_reference"]["end"]
            <= edit["end"]
        ), "unavailable image exact flat ownership"
        if index in proof_by_flat:
            assert proof_by_flat[index] == proof["base_edits"], (
                "shared unavailable image composition proof"
            )
        else:
            proof_by_flat[index] = proof["base_edits"]
            base.extend(proof["base_edits"])
        compound = any(e["kind"] == "markdown_insert" for e in proof["base_edits"])
        assert edit["kind"] == (
            "markdown_insert_image_unavailable" if compound else "image_unavailable"
        ), "independent compound kind/code ownership"
    assert {i for i, e in enumerate(edits) if e["kind"] in IMAGE_KINDS} == set(
        proof_by_flat
    ), "unexplained unavailable image edit"
    base.sort(key=lambda e: e["start"])
    rebuilt_base, base_delta = [], 0
    proven = [candidate for proof in proof_by_flat.values() for candidate in proof]
    for edit in base:
        if edit in proven:
            rebuilt_base.append(edit)
        else:
            rebuilt_base.append(
                edit
                | {
                    "adapted_start": edit["start"] + base_delta,
                    "adapted_end": edit["start"] + base_delta + len(edit["after"]),
                }
            )
        base_delta += len(edit["after"]) - len(edit["before"])
    base = rebuilt_base
    validate_document_adaptations(raw, intermediate, base, profile_version="4")
    # Independently rebuild each composed edit from exact source and base output.
    for index, proof in proof_by_flat.items():
        edit = edits[index]
        occurrences = [
            e
            for e, o in zip(expected, actual, strict=True)
            if o["composition"]["flat_edit"] == index
        ]
        intervals = sorted(
            [
                (e["source_reference"]["start"], e["source_reference"]["end"])
                for e in occurrences
            ]
            + [(e["start"], e["end"]) for e in proof]
        )
        frontier = intervals[0][1]
        for begin, end in intervals[1:]:
            assert begin < frontier, "unavailable image connected source union"
            frontier = max(frontier, end)
        left = min(
            [e["source_reference"]["start"] for e in occurrences]
            + [e["start"] for e in proof]
        )
        right = max(
            [e["source_reference"]["end"] for e in occurrences]
            + [e["end"] for e in proof]
        )
        assert (edit["start"], edit["end"], edit["before"], edit["source_digest"]) == (
            left,
            right,
            raw[left:right],
            digest(raw),
        ), "unavailable image exact source union"
        before_start = left + sum(
            len(e["after"]) - len(e["before"]) for e in base if e["end"] <= left
        )
        before_end = right + sum(
            len(e["after"]) - len(e["before"]) for e in base if e["end"] <= right
        )
        after = intermediate[before_start:before_end]
        for event in reversed(occurrences):
            span = event["intermediate_reference"]
            after = (
                after[: span["start"] - before_start]
                + event["notice"]["text"]
                + after[span["end"] - before_start :]
            )
        assert edit["after"] == after, (
            "unavailable image exact composed replacement/code ownership"
        )
    replay, cursor, delta = [], 0, 0
    for edit in edits:
        assert set(edit) == {
            "kind",
            "start",
            "end",
            "before",
            "after",
            "adapted_start",
            "adapted_end",
            "source_digest",
            "source_basis",
            "adapted_basis",
        }, "unavailable image flattened edit fields"
        assert all(
            type(edit[k]) is int
            for k in ("start", "end", "adapted_start", "adapted_end")
        ), "unavailable image flattened coordinate scalars"
        start, end = edit["start"], edit["end"]
        assert cursor <= start < end <= len(raw) and edit["before"] == raw[start:end], (
            "unavailable image flattened source spans"
        )
        assert (edit["adapted_start"], edit["adapted_end"]) == (
            start + delta,
            start + delta + len(edit["after"]),
        ), "unavailable image flattened final spans"
        assert (
            edit["source_basis"] == "scoped_source_text/unicode_codepoints"
            and edit["adapted_basis"] == "document.text/unicode_codepoints"
            and edit["source_digest"] == digest(raw)
        ), "unavailable image flattened source bases"
        replay.extend((raw[cursor:start], edit["after"]))
        cursor = end
        delta += len(edit["after"]) - len(edit["before"])
    replay.append(raw[cursor:])
    assert "".join(replay) == final, "unavailable image complete flattened replay"


def warning_text(api, declared):
    messages = {
        (True, True): (
            (
                "A referenced declared image returned HTTP404; its declaration is retained "
                "and no pixels were recovered."
            ),
            (
                "Review the exact source reference and classified acquisition evidence "
                "in the Migration report."
            ),
        ),
        (False, True): (
            (
                "A referenced declared image has recorded state3 and no archive payload; "
                "no image bytes were recovered."
            ),
            (
                "Review the exact reference, image declaration and state evidence "
                "in the Migration report."
            ),
        ),
        (True, False): (
            (
                "An inline image is unavailable in the captured source; "
                "no image bytes were recovered."
            ),
            (
                "Review the retained source reference and captured inventory evidence "
                "in the Migration report."
            ),
        ),
        (False, False): (
            (
                "An inline image is unavailable; its source reference is retained "
                "and no image bytes were recovered."
            ),
            "Review the original reference and absence evidence in the Migration report.",
        ),
    }
    return messages[api, declared]


def findings(record, key, events, *, api, evidence):
    found = []
    for issue in record["issues"]:
        if issue.get("rule_id") not in RULES:
            continue
        observed = json.loads(issue["message"].split("Observed: ", 1)[1])
        if observed.get("document") != key:
            continue
        declared = "asset_id" in observed["absence"]
        message, guidance = warning_text(api, declared)
        affected = (
            [observed["absence"]["asset_id"]]
            if declared
            else sorted([observed["owner"], key])
        )
        rule = (
            "thebrain.unavailable-declared-image.v1"
            if declared
            else "thebrain.unavailable-image.v1"
        )
        assert issue == {
            "code": "approved_source_gap",
            "severity": "warning",
            "phase": "analysis",
            "message": message + " Observed: " + observation_json(observed, api=api),
            "guidance": guidance,
            "affected": affected,
            "evidence": evidence,
            "rule_id": rule,
            "leftover_path": None,
        }, "unavailable image complete warning evidence"
        found.append(observed)
    assert len(found) == len(events), "unavailable image warning census"
    return found


def api_preparation(baseline, key, raw, profile_version):
    from .api_note_text import expected_document_text

    if profile_version not in {"4", "5"}:
        return expected_document_text(raw, profile_version=profile_version), None, []
    bindings, absent = api_images(baseline)
    return expectation(
        raw,
        bindings[key]["owner"],
        bindings,
        absent,
        basis="api_undeclared_inventory",
        profile_version=profile_version,
    )


def api_document_text(baseline, key, raw, profile_version):
    return api_preparation(baseline, key, raw, profile_version)[0]


def observation_json(value, *, api=False):
    if not api:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    if isinstance(value, str):
        return (
            '"'
            + "".join(
                f"\\u{ord(c):04x}"
                if ord(c) < 32
                else json.dumps(c, ensure_ascii=False)[1:-1]
                for c in value
            )
            + '"'
        )
    if isinstance(value, list):
        return "[" + ",".join(observation_json(v, api=True) for v in value) + "]"
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                observation_json(k, api=True)
                + ":"
                + observation_json(value[k], api=True)
                for k in sorted(value)
            )
            + "}"
        )
    return json.dumps(value, separators=(",", ":"))


def check_api_acquisition(record, baseline):
    _bindings, absent = api_images(baseline)
    requests = record["run_metadata"]["source_acquisition"]["audit"]["requests"]
    assert {
        r["subject_id"] for r in requests if r["outcome"] == "missing_image_404"
    } == set(absent), "raw image acquisition absence census"
    for key, fact in absent.items():
        for field, operation, status, outcome in (
            ("metadata_sequence", "attachments", 200, "success"),
            ("request_sequence", "attachment-content", 404, "missing_image_404"),
        ):
            matches = [r for r in requests if r["sequence"] == fact[field]]
            assert len(matches) == 1, "raw image acquisition request sequence"
            row = matches[0]
            assert (
                row["operation"],
                row["subject_id"],
                row["brain_id"],
                row["status"],
                row["outcome"],
            ) == (
                operation,
                key,
                baseline.json(baseline.data["brain"])["id"],
                status,
                outcome,
            ), "raw image acquisition metadata/content binding"
            if status == 404:
                assert row["actual_length"] == 0, (
                    "raw image acquisition no recovered bytes"
                )
    return absent


def api_findings(record, baseline, scoped, profile_version):
    result = []
    absent = (
        check_api_acquisition(record, baseline) if profile_version in {"4", "5"} else {}
    )
    documents = {d["key"]: d for t in record["item_targets"] for d in t["documents"]}
    documents.update(
        {d["key"]: d for a in record["asset_targets"] for d in a["retained_documents"]}
    )
    seen_absent = set()
    for key, note in scoped.safe_notes.items():
        final, intermediate, events = api_preparation(
            baseline, key, note.scoped_text, profile_version
        )
        observed = findings(
            record, key, events, api=True, evidence=["attachment:" + key]
        )
        if events:
            validate(
                note.scoped_text,
                final,
                intermediate,
                documents[key]["text_adaptations"],
                events,
                observed,
            )
        for value in observed:
            declared = "asset_id" in value["absence"]
            if declared:
                seen_absent.add(value["absence"]["asset_id"])
            result.append(
                {
                    "kind": "unavailable_image_reference",
                    "rule_id": (
                        "thebrain.unavailable-declared-image.v1"
                        if declared
                        else "thebrain.unavailable-image.v1"
                    ),
                    "affected": (
                        [value["absence"]["asset_id"]]
                        if declared
                        else sorted([value["owner"], key])
                    ),
                    "evidence": ["attachment:" + key],
                    "observed_json": value,
                }
            )
    assert set(absent) == seen_absent, "raw image complete referenced absence closure"
    return result
