"""Raw relationship evidence defeats internally consistent navigation forgeries."""

from tests.application.test_graph_workflow import graph_archive


def relationship_archive(path, shape):
    return graph_archive(
        path,
        {1: "Entry", 2: "Other"},
        [(1, 2, 1, 1, 3)] if shape == "hierarchy" else [(1, 2, 3, 1, -1)],
        kinds={2: 1 if shape == "hierarchy" else 2},
        notes={2: (b"Other source.\r\n", 4)},
    )
