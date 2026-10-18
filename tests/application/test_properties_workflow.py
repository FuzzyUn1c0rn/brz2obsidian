"""Canonical object metadata observed through real archives and vault files."""

import json
from zipfile import ZipFile

import pytest

from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.core import analyze
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment, write_source


def parts(source):
    with ZipFile(source) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def set_thoughts(files, changes):
    thoughts = [json.loads(line) for line in files["thoughts.json"].splitlines()]
    for thought in thoughts:
        thought.update(changes.get(thought["Id"], {}))
    files["thoughts.json"] = "\n".join(json.dumps(t) for t in thoughts).encode()


def property_block(note):
    assert note.startswith(b"---\n")
    return note.split(b"---\n", 2)[1].decode()


@pytest.mark.parametrize(
    "change", ["another_owner", "file_role", "zero_length", "unknown_asset"]
)
def test_public_core_refuses_inconsistent_declared_image_facts(tmp_path, change):
    files = parts(
        graph_archive(
            tmp_path / "icon.brz", {1: "Entry", 2: "Other"}, notes={1: (b"", 4)}
        )
    )
    add_attachment(files, identity(3001), 5, "icon.png", b"image", owner=identity(1))
    with BrzSourceModule().open(write_source(tmp_path, files)) as session:
        snapshot = session.snapshot
    icon = next(a for a in snapshot.assets if a.asset_id == identity(3001))
    if change == "unknown_asset":
        item = snapshot.items[0]
        item = item.model_copy(
            update={
                "declared_appearance": item.declared_appearance.model_copy(
                    update={"icon_asset_id": "unknown"}
                )
            }
        )
        snapshot = snapshot.model_copy(update={"items": (item, snapshot.items[1])})
    else:
        icon = icon.model_copy(
            update={"owner": identity(2)}
            if change == "another_owner"
            else {"role": "file"}
            if change == "file_role"
            else {"actual_length": 0}
        )
        snapshot = snapshot.model_copy(
            update={
                "assets": tuple(
                    icon if a.asset_id == icon.asset_id else a for a in snapshot.assets
                )
            }
        )
    with pytest.raises(MigrationRefused):
        analyze(snapshot, BRZ_POLICY)
