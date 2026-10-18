"""Independent raw-source controls for repeated absent positive TXT declarations."""

from zipfile import ZipFile

from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment


def duplicate_txt_parts(tmp_path):
    source = graph_archive(
        tmp_path / "base.brz", {1: "Home", 2: "Owner"}, notes={1: (b"Home body", 4)}
    )
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    add_attachment(
        parts, identity(3000), 1, "intact.pdf", b"%PDF-synthetic", owner=identity(2)
    )
    for n, length in ((3001, 17), (3002, 29), (3003, 41)):
        add_attachment(
            parts,
            identity(n),
            15,
            "shared.txt",
            declared=length,
            state=2,
            owner=identity(2),
        )
    return parts


def thirteen_txt_parts(tmp_path):
    source = graph_archive(
        tmp_path / "base.brz",
        {1: "Home", **{n: f"Owner {n}" for n in range(2, 7)}},
        notes={1: (b"Home body", 4)},
    )
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    for owner in range(2, 7):
        add_attachment(
            parts,
            identity(4000 + owner),
            1,
            "intact.pdf",
            b"%PDF-synthetic",
            owner=identity(owner),
        )
        for offset, length in ((0, 17), (1, 29)):
            add_attachment(
                parts,
                identity(5000 + 2 * owner + offset),
                15,
                "shared.TXT",
                declared=length,
                state=2,
                owner=identity(owner),
            )
    for offset in range(3):
        add_attachment(
            parts,
            identity(6000 + offset),
            15,
            f"single-{offset}.txt",
            declared=53 + offset,
            state=2,
            owner=identity(2),
        )
    return parts
