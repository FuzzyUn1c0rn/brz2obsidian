"""Qualified owned payload facts; rendered note responses are never a fallback."""

import hashlib
import warnings
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from PIL import Image

from brz2obsidian.contracts import Asset, Document

from .declarations import source_date, uuid
from .errors import refuse, unsupported_shape
from .notes import scope_text
from .svg import validate_svg

ATTACHMENT_FIELDS = {
    "id",
    "brainId",
    "sourceId",
    "sourceType",
    "creationDateTime",
    "modificationDateTime",
    "name",
    "position",
    "fileModificationDateTime",
    "type",
    "isNotes",
    "dataLength",
    "location",
}


def declaration(value, brain, owner, budget):
    required = {
        "id",
        "brainId",
        "sourceId",
        "sourceType",
        "name",
        "position",
        "type",
        "isNotes",
        "dataLength",
        "location",
    }
    if (
        not isinstance(value, dict)
        or not required <= value.keys()
        or not value.keys() <= ATTACHMENT_FIELDS
    ):
        refuse("An attachment declaration is incomplete or unsupported")
    if (
        value["brainId"] != brain
        or value["sourceId"] != owner
        or type(value["sourceType"]) is not int
        or value["sourceType"] != 2
    ):
        refuse("An attachment declaration has foreign ownership")
    uuid(value["id"])
    if (
        type(value["type"]) is not int
        or type(value["isNotes"]) is not bool
        or value["dataLength"] is not None
        and (
            type(value["dataLength"]) is not int
            or not 0 <= value["dataLength"] <= 9223372036854775807
        )
    ):
        refuse("An attachment declaration has invalid scalar fields")
    position = value["position"]
    if not isinstance(position, (int, Decimal)) or isinstance(position, bool):
        refuse("An attachment position is not a source number")
    number = Decimal(position)
    if number.is_finite() and not number:
        return dict(value, position={"decimal": "0"})
    if (
        not number.is_finite()
        or abs(number.adjusted()) + len(number.as_tuple().digits) + 8 > budget
    ):
        refuse(
            "Attachment position expansion exceeds the metadata bound",
            "incomplete_source",
        )
    decimal = (
        format(number, "f").rstrip("0").rstrip(".")
        if number.as_tuple().exponent < 0
        else format(number, "f")
    )
    return dict(value, position={"decimal": decimal})


def role(value, profile_version):
    for field in (
        "creationDateTime",
        "modificationDateTime",
        "fileModificationDateTime",
    ):
        if field in value and value[field] is not None:
            source_date(value[field])
    kind, location, name = value["type"], value["location"], value["name"]
    if not isinstance(location, str) or not location:
        refuse("An attachment location is invalid")
    if value["isNotes"]:
        if kind == 1 and location == "Notes.md" and name is None:
            return "note_original"
        refuse("The authored note declaration is not qualified")
    if kind == 3:
        try:
            uri = urlsplit(location)
            if (
                uri.scheme.lower() not in {"http", "https"}
                or not uri.hostname
                or any(ord(c) <= 32 or ord(c) == 127 for c in location)
                or name is not None
                and not isinstance(name, str)
            ):
                raise ValueError
            return "url"
        except ValueError:
            refuse("The external resource declaration is not qualified")
    if kind == 5 and name is None and location == "Icon.png":
        return "icon"
    if (
        kind == 12
        and name is None
        and location
        in {value["id"] + ".webp"}
        | ({value["id"] + ".png"} if profile_version in {"2", "3"} else set())
        | ({value["id"] + ".svg"} if profile_version == "3" else set())
    ):
        return "image"
    if kind in {1, 15}:
        if (
            location.strip() != location
            or location in {".", ".."}
            or any(c in "/\\:%" or ord(c) < 32 or ord(c) == 127 for c in location)
            or name is not None
            and (not isinstance(name, str) or not name)
        ):
            refuse("The owned file basename or display name is not qualified")
        suffix = location.rsplit(".", 1)[-1].lower() if "." in location else ""
        if (
            (kind, suffix) in {(1, "pdf"), (15, "txt")}
            or profile_version in {"2", "3"}
            and name is None
            and (kind, suffix) in {(1, "png"), (1, "zip")}
        ):
            return "file"
    unsupported_shape(
        profile_version,
        "resource",
        "The attachment role/location is outside the reviewed profile",
    )


def validate_bytes(value, raw, profile_version):
    source = raw if isinstance(raw, Path) else BytesIO(raw)
    if isinstance(raw, Path):
        with raw.open("rb") as stream:
            prefix = stream.read(24)
    else:
        prefix = raw[:24]
    selected = role(value, profile_version)
    if selected in {"url"}:
        refuse("External destinations must not be fetched")
    if selected == "note_original" or value["type"] == 15:
        try:
            (raw.read_bytes() if isinstance(raw, Path) else raw).decode(
                "utf-8", errors="strict"
            )
        except UnicodeError:
            refuse("Required authored text is not strict UTF-8")
        return selected
    suffix = value["location"].rsplit(".", 1)[-1].lower()
    if selected == "file" and suffix == "pdf":
        if not prefix.startswith(b"%PDF-"):
            refuse("Required PDF bytes do not match the qualified signature")
        return selected
    if selected == "file" and suffix == "zip":
        try:
            if not prefix.startswith(b"PK\x03\x04"):
                raise ValueError
            with ZipFile(source) as archive:
                archive.infolist()
        except BadZipFile, ValueError, OSError:
            refuse("Required ZIP bytes have no valid central directory")
        return selected
    if selected == "image" and suffix == "svg" and profile_version == "3":
        validate_svg(raw)
        return selected
    expected = None
    if prefix.startswith(b"\x89PNG\r\n\x1a\n") and (
        selected == "icon" or suffix == "png"
    ):
        expected = "PNG"
    elif (
        selected == "icon"
        and profile_version in {"2", "3"}
        and prefix.startswith(b"\xff\xd8\xff")
    ):
        expected = "JPEG"
    elif (
        selected == "image"
        and suffix == "webp"
        and prefix[:4] == b"RIFF"
        and prefix[8:12] == b"WEBP"
    ):
        expected = "WEBP"
    if expected is None:
        refuse("Required image/icon bytes do not match the qualified signature")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(
                raw if isinstance(raw, Path) else BytesIO(raw), formats=(expected,)
            ) as image:
                image.verify()
            with Image.open(
                raw if isinstance(raw, Path) else BytesIO(raw), formats=(expected,)
            ) as image:
                if min(image.size) <= 0:
                    raise ValueError
                for index in range(getattr(image, "n_frames", 1)):
                    image.seek(index)
                    image.load()
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        refuse("Required image/icon bytes are not fully decodable")
    return selected


def capture_owner(
    client,
    config,
    brain,
    owner,
    owned,
    graph_attachments,
    record,
    profile_version,
    excluded,
    decisions,
    directory,
):
    declarations = [
        declaration(a, brain, owner, config.max_response_bytes) for a in owned
    ]
    if len({a["id"] for a in declarations}) != len(declarations):
        refuse("Owned attachment identities are duplicated")
    if graph_attachments is None and declarations:
        refuse("A populated attachment inventory needs actual graph agreement")
    if graph_attachments is not None:
        observed = [
            declaration(a, brain, owner, config.max_response_bytes)
            for a in graph_attachments
        ]
        if sorted(declarations, key=lambda a: a["id"]) != sorted(
            observed, key=lambda a: a["id"]
        ):
            refuse("Graph and owned attachment inventories disagree")
    assets, documents, payloads = [], [], {}
    for value in sorted(declarations, key=lambda a: a["id"]):
        asset_id = value["id"]
        selected = role(value, profile_version)
        metadata = declaration(
            client.json(
                "attachments", f"/attachments/{brain}/{asset_id}/metadata", asset_id
            ),
            brain,
            owner,
            config.max_response_bytes,
        )
        if metadata != value:
            refuse("Authoritative attachment declarations disagree")
        pointer = "attachment:" + asset_id
        record("attachment", pointer, owner, value)
        common = {
            "asset_id": asset_id,
            "owner": owner,
            "naming_seed": asset_id.replace("-", ""),
            "original_name": value["location"],
            "display_name": value["name"],
            "evidence": (pointer,),
        }
        if selected == "url":
            assets.append(
                Asset(
                    **dict(
                        common,
                        original_name=value["name"]
                        if value["name"] is not None
                        else value["location"],
                    ),
                    role="url",
                    availability="external",
                    external_uri=value["location"],
                )
            )
            continue
        raw = directory.path / f"{len(client.requests):016x}.bin"
        note_bytes = None
        if selected == "note_original":
            # Qualify scope before any original note bytes reach disk. The
            # transport applies the same payload/aggregate/deadline bounds.
            with BytesIO() as stream:
                client.request(
                    "attachment-content",
                    f"/attachments/{brain}/{asset_id}/file-content",
                    asset_id,
                    sink=stream,
                )
                note_bytes = stream.getvalue()
            validate_bytes(value, note_bytes, profile_version)
            measured_length, measured_hash = len(note_bytes), hashlib.sha256(note_bytes)
        else:
            with directory.open(raw.name, "xb") as stream:
                status, _ = client.request(
                    "attachment-content",
                    f"/attachments/{brain}/{asset_id}/file-content",
                    asset_id,
                    sink=stream,
                    allow_missing_txt=value["type"] == 15,
                )
            if status == 404:
                assets.append(Asset(**common, role="file", availability="absent"))
                continue
            directory.verify()
            validate_bytes(value, raw, profile_version)
            measured_length, measured_hash = 0, hashlib.sha256()
            with directory.open(raw.name, "rb") as stream:
                while chunk := stream.read(65536):
                    measured_length += len(chunk)
                    measured_hash.update(chunk)
        if selected == "note_original":
            text = note_bytes.decode("utf-8", errors="strict")
            client.ensure_safe(text)
            if documents:
                refuse("Multiple authored notes have ambiguous ownership")
            text, removed = scope_text(text, excluded)
            record("note_text", "note_text:" + owner, owner, {"text": text})
            if removed:
                decisions.append(
                    {
                        "key": "scope:note:" + asset_id,
                        "rule_id": "local-api.system.v1"
                        if any(excluded[k]["kind"] == 5 for k in removed)
                        else "local-api.forgotten.v1",
                        "outcome": "excluded_association",
                        "subjects": ["thought:" + owner]
                        + ["thought:" + k for k in sorted(removed)],
                        "evidence": ["note_text:" + owner]
                        + ["exclusion:" + k for k in sorted(removed)],
                    }
                )
            documents.append(
                Document(
                    key=asset_id,
                    owner=owner,
                    text=text,
                    text_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    original_asset_id=None if removed else asset_id,
                    original_copy_omitted=bool(removed),
                    evidence=(pointer,),
                )
            )
        if selected == "note_original" and documents[-1].original_copy_omitted:
            continue
        if selected == "note_original":
            with (
                BytesIO(note_bytes) as source_stream,
                directory.open(raw.name, "xb") as destination,
            ):
                while chunk := source_stream.read(65536):
                    destination.write(chunk)
        assets.append(
            Asset(
                **common,
                role=selected,
                availability="present",
                actual_length=measured_length,
                actual_sha256=measured_hash.hexdigest(),
            )
        )
        payloads[asset_id] = directory.payload(raw.name)
    if len([a for a in assets if a.role == "icon"]) > 1 or len(
        {a.original_name for a in assets if a.role == "image"}
    ) != len([a for a in assets if a.role == "image"]):
        refuse("Owned image/icon declarations are ambiguous")
    return assets, documents, payloads


def validate_payload_binding(source, snapshot, audit):
    """Bind normalized content to closed qualified source facts, not just hashes."""
    from .notes import bind_documents

    profile = source["identifiers"]["profile_version"]
    attachments = {
        r["value"]["id"]: r["value"]
        for r in source["records"]
        if r["domain"] == "attachment"
    }
    assets = {a.asset_id: a for a in snapshot.assets}
    texts = {
        r["owner_id"]: r["value"]["text"]
        for r in source["records"]
        if r["domain"] == "note_text"
    }
    empty = {r["owner_id"] for r in source["records"] if r["domain"] == "no_note"}
    note_owners = {
        value["sourceId"]
        for value in attachments.values()
        if role(value, profile) == "note_original"
    }
    omitted_owners = {d.owner for d in snapshot.documents if d.original_copy_omitted}
    omitted = {
        key
        for key, value in attachments.items()
        if value["sourceId"] in omitted_owners
        and role(value, profile) == "note_original"
    }
    if note_owners != set(texts) or set(texts) | empty != {
        i.key for i in snapshot.items
    }:
        refuse("Authored-note and successful no-note inventories do not reconcile")
    if set(attachments) != set(assets) | omitted or set(texts) & empty:
        refuse("Captured content declarations are missing or contradictory")
    for key, asset in assets.items():
        value = attachments[key]
        selected = role(value, profile)
        if (
            asset.owner != value["sourceId"]
            or asset.role != selected
            or asset.naming_seed != key.replace("-", "")
            or asset.original_name
            != (
                value["name"]
                if selected == "url" and value["name"] is not None
                else value["location"]
            )
            or asset.display_name != value["name"]
            or asset.availability
            not in ({"external"} if selected == "url" else {"present", "absent"})
            or asset.external_uri != (value["location"] if selected == "url" else None)
            or asset.video_presentation is not None
        ):
            refuse("Normalized payload roles or source declarations disagree")
    from .gaps import gap_projections, validate_gap_audit

    expected_findings, expected_decisions = gap_projections(
        snapshot.assets, attachments
    )
    if (
        sorted(
            (
                d
                for d in source["scope"]["decisions"]
                if d["outcome"] == "missing_txt404"
            ),
            key=lambda d: d["key"],
        )
        != expected_decisions
    ):
        refuse("Missing TXT scope decisions disagree with qualified payload facts")
    validate_gap_audit(snapshot.assets, audit, expected_decisions)
    owners = set()
    for document in snapshot.documents:
        if document.owner in owners or document.owner not in texts:
            refuse("Authored note ownership is ambiguous or unbound")
        owners.add(document.owner)
        raw = texts[document.owner]
        source_document = document.model_copy(
            update={
                "text": raw,
                "text_digest": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "references": (),
                "text_adaptations": (),
            }
        )
        expected_documents, document_findings = bind_documents(
            [source_document],
            snapshot.assets,
            {i.key for i in snapshot.items},
            with_findings=True,
        )
        expected = expected_documents[0]
        expected_findings.extend(document_findings)
        candidates = [
            key
            for key, value in attachments.items()
            if value["sourceId"] == document.owner
            and role(value, profile) == "note_original"
        ]
        if (
            len(candidates) != 1
            or document != expected
            or document.original_copy_omitted
            and (
                document.original_asset_id is not None
                or not any(
                    d["key"] == "scope:note:" + candidates[0]
                    and d["outcome"] == "excluded_association"
                    for d in source["scope"]["decisions"]
                )
            )
            or not document.original_copy_omitted
            and (
                document.original_asset_id != candidates[0]
                or assets[candidates[0]].actual_sha256
                != hashlib.sha256(raw.encode("utf-8")).hexdigest()
                or assets[candidates[0]].actual_length != len(raw.encode("utf-8"))
            )
        ):
            refuse("Normalized Markdown is not bound to qualified scoped source text")
    if sorted(snapshot.findings, key=lambda f: (f.affected, f.observed_json)) != sorted(
        expected_findings, key=lambda f: (f.affected, f.observed_json)
    ):
        refuse("Note findings are not bound to the qualified formatting adaptations")
    if owners != set(texts):
        refuse("An authored source note has no normalized document")
    for item in snapshot.items:
        icon = [
            a.asset_id
            for a in snapshot.assets
            if a.owner == item.key and a.role == "icon"
        ]
        if (
            len(icon) > 1
            or set(item.document_ids)
            != {d.key for d in snapshot.documents if d.owner == item.key}
            or set(item.resource_ids)
            != {
                a.asset_id
                for a in snapshot.assets
                if a.owner == item.key and a.role != "note_original"
            }
            or (
                item.declared_appearance.icon_asset_id
                if item.declared_appearance
                else None
            )
            != (icon[0] if icon else None)
        ):
            refuse("Item note/resource/icon ownership disagrees with captured facts")
        graph = next(
            r["value"] for r in source["records"] if r["key"] == "graph:" + item.key
        )
        if set(graph["attachment_ids"]) != {
            key for key, value in attachments.items() if value["sourceId"] == item.key
        }:
            refuse(
                "Scoped graph attachment inventory disagrees with owned declarations"
            )
