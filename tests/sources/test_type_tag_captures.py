"""Profile provenance and frozen interpretation through the public SourceSession."""

import json
import tempfile
from contextlib import closing

import pytest

from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import BRAIN, KEY, api_server
from tests.support.local_api_graph import CompleteGraphApi
from tests.support.type_tag_sources import ICON, PNG, TypeTagApi


@pytest.mark.parametrize("profile", ["1", "2", "3", "4"])
def test_frozen_profile_retains_interpretation_and_qualification_baseline(
    tmp_path, monkeypatch, profile
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    api = TypeTagApi() if profile == "4" else CompleteGraphApi()
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=profile,
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            metadata = json.loads((capture / "metadata.json").read_bytes())
            snapshot = session.snapshot
            session.verify_consistency()
    assert source["identifiers"]["profile_version"] == profile
    assert metadata["desktop_build"] == (
        "15.0.647.0" if profile == "4" else "15.0.640.0"
    )
    assert metadata["schema_sha256"] == (
        "02fd25ff4f6a393f85aa0eab1597fb728f9a752a517497229715d834f5b49c5f"
        if profile == "4"
        else "7eba4646236dbecf2dd4c265d5cd52f782245a9b17f2ab92e90aa2e167a3b318"
    )
    with closing(
        LocalApiSession(
            source=source,
            snapshot=snapshot,
            audit=audit,
            profile_version=profile,
            payloads={ICON: PNG} if profile == "4" else {},
        )
    ) as frozen:
        assert (
            frozen.snapshot.classification_assignments
            == snapshot.classification_assignments
        )
        frozen.verify_consistency()
    with pytest.raises(MigrationRefused):
        LocalApiSession(
            source=source,
            snapshot=snapshot.model_copy(update={"classification_assignments": ()}),
            audit=audit,
            profile_version=profile,
            payloads={ICON: PNG} if profile == "4" else {},
        )
    if profile != "4":
        with pytest.raises(MigrationRefused):
            LocalApiSession(
                source=source, snapshot=snapshot, audit=audit, profile_version="4"
            )
