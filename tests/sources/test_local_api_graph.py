"""Reviewed API graph facts through public frozen sessions and actual output."""

import pytest

from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import BRAIN, HOME, KEY, api_server


@pytest.mark.parametrize(
    "mutation",
    [
        "omit_relationship",
        "swap_orientation",
        "omit_assignment",
        "change_colour",
        "change_calendar",
        "duplicate_assignment",
        "unknown_link_reference",
        "unknown_sibling_reference",
    ],
)
@pytest.mark.parametrize("profile_version", ["1", "3"])
def test_frozen_capture_binds_graph_and_metadata_facts_to_scoped_originals(
    tmp_path, monkeypatch, mutation, profile_version
):
    import json
    import tempfile
    from datetime import date

    from brz2obsidian.contracts import CalendarDates, DeclaredAppearance
    from brz2obsidian.sources.thebrain.local_api import LocalApiSession
    from tests.support.local_api_graph import CompleteGraphApi

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with api_server(CompleteGraphApi()) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=profile_version,
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            # Retained filenames are the accepted public capture format. No
            # session internals or private normalization helpers are consulted.
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            snapshot = session.snapshot
            identity = snapshot.identity.model_copy(
                update={"source_sha256": "", "snapshot_digest": ""}
            )
            changed = {"identity": identity}
            if mutation == "omit_relationship":
                changed["relationships"] = snapshot.relationships[1:]
            elif mutation == "swap_orientation":
                first = snapshot.relationships[0]
                changed["relationships"] = (
                    first.model_copy(
                        update={"item_a": first.item_b, "item_b": first.item_a}
                    ),
                ) + snapshot.relationships[1:]
            elif mutation == "omit_assignment":
                changed["classification_assignments"] = ()
            elif mutation == "duplicate_assignment":
                changed["classification_assignments"] = (
                    snapshot.classification_assignments * 2
                )
            elif mutation in {"unknown_link_reference", "unknown_sibling_reference"}:
                field = (
                    "link_ids"
                    if mutation == "unknown_link_reference"
                    else "sibling_ids"
                )
                graph = next(
                    r for r in source["records"] if r["key"] == "graph:" + HOME
                )
                graph["value"][field].append("99999999-9999-4999-8999-999999999999")
                changed["original_evidence"] = tuple(
                    evidence.model_copy(
                        update={"original_json": json.dumps(graph["value"])}
                    )
                    if evidence.key == graph["key"]
                    else evidence
                    for evidence in snapshot.original_evidence
                )
            else:
                items = list(snapshot.items)
                index = next(i for i, item in enumerate(items) if item.key == HOME)
                field = (
                    {
                        "declared_appearance": DeclaredAppearance(
                            foreground_color="#abcdef"
                        )
                    }
                    if mutation == "change_colour"
                    else {
                        "calendar_dates": CalendarDates(
                            created=date(2000, 1, 1), updated=date(2000, 1, 1)
                        )
                    }
                )
                items[index] = items[index].model_copy(update=field)
                changed["items"] = tuple(items)
            with pytest.raises(MigrationRefused):
                LocalApiSession(
                    source=source,
                    snapshot=snapshot.model_copy(update=changed),
                    audit=audit,
                    profile_version=profile_version,
                )
