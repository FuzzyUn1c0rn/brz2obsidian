"""Typed migration behavior observed through actual archives and vaults."""

import json
from zipfile import ZipFile

from tests.application.test_graph_workflow import graph_archive, identity
from tests.sources.test_reader import rewrite


def typed_archive(path):
    source = graph_archive(
        path,
        {1: "Entry", 2: "Concept", 3: "Empty member", 4: "Untyped empty"},
        [(2, 3, 1, 2, -1)],
        kinds={2: 2},
    )
    with ZipFile(source) as archive:
        thoughts = [
            json.loads(line) for line in archive.read("thoughts.json").splitlines()
        ]
    thoughts[2]["TypeId"] = identity(2)
    rewrite(
        source, "thoughts.json", "\n".join(json.dumps(t) for t in thoughts).encode()
    )
    return source
