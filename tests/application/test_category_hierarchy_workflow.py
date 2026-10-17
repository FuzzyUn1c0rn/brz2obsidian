"""Category hierarchy observed through archive inspection and published vaults."""

import json
from zipfile import ZipFile

from tests.application.test_graph_workflow import graph_archive, identity
from tests.sources.test_reader import rewrite


def complete_hierarchy_archive(path, *, excluded_parent=True):
    source = graph_archive(
        path,
        {
            1: "Entry",
            2: "Concept",
            3: "Assigned parent",
            4: "Unassigned parent",
            5: "Empty parent",
            6: "Cycle A",
            7: "Cycle B",
            8: "Empty leaf",
            9: "Excluded parent",
            10: "Related",
            11: "Other category",
        },
        [
            (2, 3, 1, 2, -1),
            (3, 2, 1, 1, -1),
            (4, 2, 1, 1, -1),
            (5, 2, 1, 1, -1),
            (6, 7, 1, 1, -1),
            (7, 6, 1, 1, -1),
            (6, 8, 1, 1, -1),
            (9, 2, 1, 1, -1),
            (4, 10, 3, 1, -1),
            (4, 2, 1, 1, -1),
        ],
        kinds={2: 2, 11: 2},
        labels={2: "Category label"},
        notes={2: (b"Category source.\r\n", 4), 4: (b"Parent source.\r\n", 4)},
    )
    with ZipFile(source) as archive:
        thoughts = [
            json.loads(line) for line in archive.read("thoughts.json").splitlines()
        ]
    thoughts[2]["TypeId"] = identity(2)
    thoughts[8]["ForgottenDateTime"] = "2020-01-01"
    if not excluded_parent:
        thoughts.pop(8)
        with ZipFile(source) as archive:
            links = [
                json.loads(line) for line in archive.read("links.json").splitlines()
            ]
        links.pop(7)
        rewrite(source, "links.json", "\n".join(map(json.dumps, links)).encode())
    rewrite(source, "thoughts.json", "\n".join(map(json.dumps, thoughts)).encode())
    return source
