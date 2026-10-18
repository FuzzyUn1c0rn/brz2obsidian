"""Generated Markdown guards are raw-derived framing, not source adaptations."""

import json

from tests.application.test_forgotten_workflow import rewrite
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment

NAVIGATION = "## Categories\n\n[[Categories.md|Browse categories]]\n"
CHILDREN = "## Children\n\n- [[Notes/Live.md|Live]]\n"
RESOURCES = "## Resources\n\n- [resource.pdf](<file:///C:/absent/resource.pdf>)\n"


def source_with_tail(path, body, tail, *, label=None):
    owner = 1 if tail in {"home", "all"} else 2
    source = graph_archive(
        path,
        {1: "Home", 2: "Probe", 3: "Live"},
        [(owner, 3, 1, 1, -1)] if tail in {"children", "all"} else [],
        notes={owner: (body.encode(), 4)},
        labels={owner: label} if label else None,
    )
    if tail in {"resources", "all"}:

        def resource(parts):
            add_attachment(
                parts,
                identity(7001),
                2,
                r"C:\absent\resource.pdf",
                state=None,
                owner=identity(owner),
            )
            rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
            next(row for row in rows if row["Id"] == identity(7001))["Name"] = (
                "resource.pdf"
            )
            parts["attachments.json"] = b"\n".join(
                json.dumps(row).encode() for row in rows
            )

        rewrite(source, resource)
    return source, owner, "Home — Home.md" if owner == 1 else "Notes/Probe.md"


def authored_full_note(body, guard, tail, *, section_break="\n\n", prefix=None):
    """Assemble authored bytes with fixture-declared guard and literal section break.

    The caller works the break from its known ending; this helper neither
    normalizes source encodings nor infers padding from body/guard content.
    Resources always add two LF bytes; their final LF leaves one before Children,
    whose final LF in turn leaves one before Categories.
    """
    text = (
        prefix
        if prefix is not None
        else "# " + ("Home" if tail in {"home", "all"} else "Probe") + "\n\n"
    )
    text += body
    if tail != "none":
        text += guard
    text += {
        "none": "",
        "resources": "\n\n" + RESOURCES,
        "children": section_break + CHILDREN,
        "home": section_break + NAVIGATION,
        "all": "\n\n" + RESOURCES + "\n" + CHILDREN + "\n" + NAVIGATION,
    }[tail]
    return text.encode()
