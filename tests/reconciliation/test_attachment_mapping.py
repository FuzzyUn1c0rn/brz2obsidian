"""Qualified renderer mapping metadata; no native ownership is granted here."""

import hashlib
import json

import pytest

from brz2obsidian.contracts import ExactContent, OutputIdentity


@pytest.mark.parametrize(
    "case", ("valid", "settings", "case_alias", "unicode_alias", "prefix_alias")
)
def test_attachment_mapping_qualifies_full_meaning_and_refuses_phantom_aliases(case):
    from brz2obsidian.obsidian import interpret_attachment_mapping

    identity = OutputIdentity(
        collection_id="independent-collection",
        module_id="synthetic-source",
        module_version="1",
        profile_id="independent-profile",
        profile_version="1",
        output_format=7,
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    record = {
        "schema": "brz2obsidian.migration",
        "schema_version": 7,
        "source_identity": {
            "source_id": "independent-collection",
            "module_id": "synthetic-source",
            "module_version": "1",
            "format_version": "1",
            "source_sha256": "a" * 64,
            "snapshot_digest": "b" * 64,
        },
        "profile_id": "independent-profile",
        "profile_version": "1",
        "asset_targets": [
            {"asset_id": "asset-one", "relative_path": "Assets/Caf\u00e9.bin"}
        ],
    }
    if case == "settings":
        identity = identity.model_copy(update={"settings_digest": "foreign-settings"})
    aliases = {
        "case_alias": "assets/caf\u00e9.BIN",
        "unicode_alias": "Assets/Cafe\u0301.bin",
        "prefix_alias": "Assets/Caf\u00e9.bin/phantom.bin",
    }
    if case in aliases:
        record["asset_targets"].append(
            {"asset_id": "phantom-asset", "relative_path": aliases[case]}
        )
    raw = ExactContent(data=json.dumps(record, ensure_ascii=False).encode("utf-8"))
    if case != "valid":
        with pytest.raises(ValueError):
            interpret_attachment_mapping(raw, identity=identity)
        return
    source, assets = interpret_attachment_mapping(raw, identity=identity)
    assert (
        source.source_id == "independent-collection"
        and source.snapshot_digest == "b" * 64
    )
    assert tuple((a.asset_id, a.relative_path) for a in assets) == (
        ("asset-one", "Assets/Caf\u00e9.bin"),
    )
