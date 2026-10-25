"""Interpret supported generated asset mapping metadata without granting ownership."""

import hashlib
import json
import unicodedata
from itertools import pairwise

from brz2obsidian.contracts import (
    AssetTarget,
    ExactContent,
    OutputIdentity,
    ReconciliationContract,
    SourceIdentity,
)


def interpret_attachment_mapping(content: ExactContent, *, identity: OutputIdentity):
    record = json.loads(content.data)
    source = SourceIdentity.model_validate(record["source_identity"])
    actual = OutputIdentity(
        collection_id=source.source_id,
        module_id=source.module_id,
        module_version=source.module_version,
        profile_id=record["profile_id"],
        profile_version=record["profile_version"],
        output_format=record["schema_version"],
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    if (
        record["schema"] != "brz2obsidian.migration"
        or actual.output_format != 7
        or actual != identity
    ):
        raise ValueError("Attachment mapping generation is unqualified")
    assets = tuple(AssetTarget.model_validate(row) for row in record["asset_targets"])
    if len({row.asset_id for row in assets}) != len(assets):
        raise ValueError("Attachment mapping identity is ambiguous")
    paths = []
    for row in assets:
        if row.relative_path is None:
            continue
        ReconciliationContract.relative_vault_path(row.relative_path)
        paths.append(
            unicodedata.normalize(
                "NFC", unicodedata.normalize("NFC", row.relative_path).casefold()
            )
        )
    paths.sort()
    if any(
        current == previous or current.startswith(previous + "/")
        for previous, current in pairwise(paths)
    ):
        raise ValueError("Attachment mapping path is ambiguous")
    return source, assets
