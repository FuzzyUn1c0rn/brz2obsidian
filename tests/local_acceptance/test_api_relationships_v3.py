"""Independent reverse-hierarchy source and preservation controls for issue 214."""

import json

import pytest

from tests.local_acceptance.test_api_acceptance import (
    fingerprint,
    identity,
    reseal,
    source_case,
    write_json,
)


def reverse_case(tmp_path):
    """Literal source facts and expected navigation, never converter output."""
    baseline, vault = source_case(tmp_path)
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    for name in manifest["graphs"].values():
        path = root / name
        graph = json.loads(path.read_bytes())
        graph.setdefault("siblings", [])
        for link in graph["links"]:
            if link["id"] == identity(101):
                link["direction"] = 3
        write_json(path, graph)
    metadata = {
        "id": identity(101),
        "brainId": identity(1),
        "thoughtIdA": identity(2),
        "thoughtIdB": identity(3),
        "kind": 1,
        "relation": 1,
        "meaning": 1,
        "direction": 3,
        "typeId": None,
    }
    name = "reverse-link-metadata.json"
    write_json(root / name, metadata)
    manifest["files"][name] = fingerprint(root / name)
    manifest["relationship_metadata"] = {identity(101): {"status": 200, "path": name}}
    manifest["link_attachment_outcomes"] = {identity(101): 200}
    write_json(baseline.manifest_path, manifest)
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["profile_version"] = "3"
    record["original_evidence"][0]["records"] = [
        metadata if row["id"] == identity(101) else row
        for row in record["original_evidence"][0]["records"]
    ]
    for target in record["item_targets"]:
        if target["item_key"] == identity(2):
            target.update(relative_path="Home.md", created=True)
        elif target["item_key"] == identity(3):
            target.update(relative_path="Child.md", created=True)
    write_json(path, record)
    (vault / "Home.md").write_text(
        "# Home\n\nOriginal note.\n\n## Children\n\n- [[Child.md|Child]]\n",
        encoding="utf-8",
    )
    (vault / "Child.md").write_text(
        "# Child\n\n## Parents\n\n- [[Home.md|Home]]\n", encoding="utf-8"
    )
    return baseline, vault


def mutate_source(baseline, change):
    """Fresh synthetic construction with explicit independent requalification."""
    root = baseline.manifest_path.parent
    manifest = json.loads(baseline.manifest_path.read_bytes())
    graphs = {
        key: json.loads((root / name).read_bytes())
        for key, name in manifest["graphs"].items()
    }
    change(manifest, graphs)
    for key, graph in graphs.items():
        write_json(root / manifest["graphs"][key], graph)
    write_json(baseline.manifest_path, manifest)
    return reseal(baseline)


def empty_reverse_leaf_case(tmp_path):
    """Home covers an ordinary, unclassified, contentless child."""
    baseline, vault = reverse_case(tmp_path)

    def change(manifest, graphs):
        for graph in graphs.values():
            graph["links"] = [r for r in graph["links"] if r["id"] != identity(104)]
            for row in [
                graph["activeThought"],
                *graph["parents"],
                *graph["children"],
                *graph["jumps"],
                *graph["tags"],
            ]:
                if row["id"] == identity(3):
                    row["typeId"] = None
        graphs[identity(3)]["type"] = None
        graphs[identity(4)]["children"] = []
        manifest["scope"]["relationship_ids"].remove(identity(104))
        del manifest["link_attachments"][identity(104)]

    baseline = mutate_source(baseline, change)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["relationships"] = [
        r for r in record["relationships"] if r["key"] != identity(104)
    ]
    record["classification_assignments"] = []
    record["original_evidence"][0]["records"] = [
        r for r in record["original_evidence"][0]["records"] if r["id"] != identity(104)
    ]
    next(
        r for r in record["original_evidence"][0]["records"] if r["id"] == identity(3)
    )["typeId"] = None
    next(t for t in record["item_targets"] if t["item_key"] == identity(3)).update(
        created=False, creation_reasons=[]
    )
    write_json(path, record)
    (vault / "Child.md").unlink()
    return baseline, vault


def two_empty_reverse_endpoints_case(tmp_path):
    """An uncovered Child->Leaf edge deterministically selects Child, the parent."""
    baseline, vault = empty_reverse_leaf_case(tmp_path)
    root = baseline.manifest_path.parent
    leaf = {
        "id": identity(6),
        "brainId": identity(1),
        "kind": 1,
        "acType": 0,
        "forgottenDateTime": None,
        "name": "Leaf",
        "typeId": None,
    }
    link = {
        "id": identity(106),
        "brainId": identity(1),
        "thoughtIdA": identity(3),
        "thoughtIdB": identity(6),
        "kind": 1,
        "relation": 1,
        "meaning": 1,
        "direction": 3,
        "typeId": None,
    }

    def change(manifest, graphs):
        parent = graphs[identity(3)]["activeThought"]
        graphs[identity(3)]["links"].append(link)
        graphs[identity(3)]["children"].append(leaf)
        graphs[identity(6)] = {
            "activeThought": leaf,
            "links": [link],
            "parents": [parent],
            "children": [],
            "jumps": [],
            "tags": [],
            "siblings": [],
            "type": None,
            "attachments": [],
        }
        manifest["graphs"][identity(6)] = "leaf-graph.json"
        write_json(root / "leaf-graph.json", graphs[identity(6)])
        manifest["files"]["leaf-graph.json"] = fingerprint(root / "leaf-graph.json")
        manifest["scope"]["thought_ids"].append(identity(6))
        manifest["scope"]["relationship_ids"].append(identity(106))
        for name, value in (
            ("leaf-link.json", link),
            ("leaf-link-content.json", []),
            (
                "leaf-no-note.json",
                {
                    "brainId": identity(1),
                    "sourceId": identity(6),
                    "sourceType": 2,
                    "markdown": "",
                    "html": None,
                    "text": None,
                    "modificationDateTime": "0001-01-01T00:00:00",
                },
            ),
        ):
            write_json(root / name, value)
            manifest["files"][name] = fingerprint(root / name)
        manifest["relationship_metadata"][identity(106)] = {
            "status": 200,
            "path": "leaf-link.json",
        }
        manifest["link_attachment_outcomes"][identity(106)] = 200
        manifest["link_attachments"][identity(106)] = "leaf-link-content.json"
        manifest["no_notes"][identity(6)] = "leaf-no-note.json"
        for name in manifest["statistics"]:
            stats = json.loads((root / name).read_bytes())
            stats.update(thoughts=3, links=4)
            write_json(root / name, stats)

    baseline = mutate_source(baseline, change)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["original_evidence"][0]["records"].extend([leaf, link])
    record["relationships"].append(
        {
            "key": identity(106),
            "kind": "hierarchy",
            "item_a": identity(3),
            "item_b": identity(6),
        }
    )
    next(t for t in record["item_targets"] if t["item_key"] == identity(3)).update(
        created=True, creation_reasons=["hierarchy"]
    )
    record["item_targets"].append(
        {
            "item_key": identity(6),
            "original_identity": identity(6),
            "original_title": "Leaf",
            "relative_path": "Leaf.md",
            "created": False,
            "creation_reasons": [],
        }
    )
    write_json(path, record)
    (vault / "Child.md").write_text(
        "# Child\n\n## Parents\n\n- [[Home.md|Home]]\n\n## Children\n\n- [[Leaf.md|Leaf]]\n"
    )
    return baseline, vault


def formatting_reverse_case(tmp_path, raw, displayed):
    """Bind literal authored bytes independently of expected rendered body."""
    baseline, vault = reverse_case(tmp_path)
    root = baseline.manifest_path.parent
    (root / "201.bin").write_bytes(raw.encode("utf-8"))
    baseline = reseal(baseline)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    asset = next(
        row for row in record["asset_targets"] if row["asset_id"] == identity(201)
    )
    (vault / asset["relative_path"]).write_bytes(raw.encode("utf-8"))
    measured = fingerprint(root / "201.bin")
    asset.update(actual_length=measured["length"], actual_sha256=measured["sha256"])
    write_json(path, record)
    (vault / "Home.md").write_text(
        "# Home\n\n" + displayed + "\n## Children\n\n- [[Child.md|Child]]\n",
        encoding="utf-8",
    )
    return baseline, vault


NOTE_FORMAT_EXAMPLES = [
    pytest.param(
        "<Value> [Child](brain://AAAAAAAAAECAAAAAAAAAAw/title)\n\nAuthored body.\n",
        "\\<Value> [[Child.md|Child]]\n\nAuthored body.\n",
        id="literal-ref",
    ),
    pytest.param(
        "`<Value> [/toc/]`\n\n```md\n> [!tip|icon:😂]\n[/toc/]\n<Value>\n```\n<!-- <Value> [/toc/] -->\n\\<Value> <br>\n\nAuthored body.\n",
        "`<Value> [/toc/]`\n\n```md\n> [!tip|icon:😂]\n[/toc/]\n<Value>\n```\n<!-- <Value> [/toc/] -->\n\\<Value> <br>\n\nAuthored body.\n",
        id="protected",
    ),
    pytest.param(
        "> [!note]\n> One\n> [!tip|icon:😂]- Custom\n> Two\n\nAuthored body.\n",
        "> [!note]\n> One\n\n> [!tip]- 😂 Custom\n> Two\n\nAuthored body.\n",
        id="callout-siblings",
    ),
    pytest.param(
        "> [!note] Parent\n> > [!tip] Child\n> > One\n> > [!question] Sibling\n> > Two\n> Parent tail\n\nAuthored body.\n",
        "> [!note] Parent\n> > [!tip] Child\n> > One\n> \n> > [!question] Sibling\n> > Two\n> \n> Parent tail\n\nAuthored body.\n",
        id="callout-nested",
    ),
    pytest.param(
        "> [!tip] One\n> Body\n\nOutside\n\n> [!note] Two\n> Body\n\nAuthored body.\n",
        "> [!tip] One\n> Body\n\nOutside\n\n> [!note] Two\n> Body\n\nAuthored body.\n",
        id="callout-exit",
    ),
    pytest.param(
        "> [!tip|icon:unknown]- Title\n> Body\n> [!note|icon:😂|extra:x]\n> Next\n\nAuthored body.\n",
        "> [!tip]- Title — |icon:unknown\n> Body\n\n> [!note] Note — |icon:😂|extra:x\n> Next\n\nAuthored body.\n",
        id="callout-unsupported",
    ),
    pytest.param(
        '|One|Two|:(table="column-widths:-1,0,84;justification:default"):\n|`x|y`|2|\n\nAuthored body.\n',
        "|One|Two|\n|---|---|\n|<code>x&#124;y</code>|2|\n\nAuthored body.\n",
        id="table-code",
    ),
    pytest.param(
        '|One|Two|:(table="column-widths:-1,0,84;justification:default"):\n|:---|---:|\n|a\\|b|keep|\n\nAuthored body.\n',
        "|One|Two|\n|:---|---:|\n|a\\|b|keep|\n\nAuthored body.\n",
        id="table-separator",
    ),
    pytest.param(
        '|Code|Other|:(table="column-widths:-1,0,84;justification:default"):\n|`<a>|&</a>`|value|\n\nAuthored body.\n',
        "|Code|Other|\n|---|---|\n|<code>&lt;a&gt;&#124;&amp;&lt;/a&gt;</code>|value|\n\nAuthored body.\n",
        id="table-code-html",
    ),
    pytest.param(
        '|One|Two|:(table="column-widths:1,2;justification:default"):\n|1|2|\n\nAuthored body.\n',
        '|One|Two|:(table="column-widths:1,2;justification:default"):\n|1|2|\n\nAuthored body.\n',
        id="table-unsupported",
    ),
    pytest.param(
        '|One|Two|\\:(table="column-widths:-1,0,84;justification:default"):\n|1|2|\n\nAuthored body.\n',
        '|One|Two|\\:(table="column-widths:-1,0,84;justification:default"):\n|1|2|\n\nAuthored body.\n',
        id="table-protected",
    ),
    pytest.param(
        '|One|Two|:(table="column-widths:-1,0,84;justification:default"):\n|<!-- `x\\|y` -->|value|\n\nAuthored body.\n',
        "|One|Two|\n|---|---|\n|<!-- `x\\|y` -->|value|\n\nAuthored body.\n",
        id="table-comment",
    ),
    pytest.param(
        '|One|Two|:(table="column-widths:-1,0,84;justification:default"):\n|<!-- `x|y` -->|value|\n\nAuthored body.\n',
        '|One|Two|:(table="column-widths:-1,0,84;justification:default"):\n|<!-- `x|y` -->|value|\n\nAuthored body.\n',
        id="table-ambiguous-comment",
    ),
    pytest.param(
        '|Thought|Image|:(table="column-widths:-1,0,174;justification:default"):\n|[Child](brain://AAAAAAAAAECAAAAAAAAAAw/title)|![Alt](.data/md-images/00000000-0000-4000-8000-000000000202.webp#$width=50p$)|\n\nAuthored body.\n',
        "|Thought|Image|\n|---|---|\n|[[Child.md\\|Child]]|![Alt](00000000-0000-4000-8000-000000000202.bin)|\n\nAuthored body.\n",
        id="table-refs",
    ),
    pytest.param(
        "### Contents\n[/toc/]\n\n# Target\nBody\n\nAuthored body.\n",
        "### Contents\n- [Target](#^brz-toc-heading-1)\n\n# Target ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-simple",
    ),
    pytest.param(
        "### Contents\n[/toc/]\n\n# First ^keep\nBody\n\n## Second\nBody\n\nReserved ^brz-toc-heading-2\n\nAuthored body.\n",
        "### Contents\n- [First](#^keep)\n  - [Second](#^brz-toc-heading-2-generated)\n\n# First ^keep\nBody\n\n## Second ^brz-toc-heading-2-generated\nBody\n\nReserved ^brz-toc-heading-2\n\nAuthored body.\n",
        id="toc-id-collision",
    ),
    pytest.param(
        "[/toc/]\n\n# First ^same\nBody\n\n# Second ^same\nBody\n\nAuthored body.\n",
        "- [First](#^same)\n- [Second](#^brz-toc-heading-2)\n\n# First ^same\nBody\n\n# Second ^brz-toc-heading-2\nBody\n\nAuthored body.\n",
        id="toc-duplicate-id",
    ),
    pytest.param(
        "Contents\n--------\n[/toc/]\n\nMulti\nline heading\n============\nBody\n\nAuthored body.\n",
        "Contents\n--------\n- [Multi line heading](#^brz-toc-heading-1)\n\n# Multi line heading ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-setext",
    ),
    pytest.param(
        "> ### Contents\n> [/toc/]\n\n> ## Target\n> Body\n\nAuthored body.\n",
        "> ### Contents\n> - [Target](#^brz-toc-heading-1)\n\n> ## Target ^brz-toc-heading-1\n> Body\n\nAuthored body.\n",
        id="toc-quoted",
    ),
    pytest.param(
        "[/toc/]\nPlain body\n\nAuthored body.\n",
        "No authored headings.\nPlain body\n\nAuthored body.\n",
        id="toc-no-headings",
    ),
    pytest.param(
        "[/toc/]\n\n#\nEmpty heading\n\nAuthored body.\n",
        "- [Heading](#^brz-toc-heading-1)\n\n# ^brz-toc-heading-1\nEmpty heading\n\nAuthored body.\n",
        id="toc-empty-heading",
    ),
    pytest.param(
        "[/toc/]\n\n### Closed ^literal ###\nBody\n\nAuthored body.\n",
        "- [Closed \\^literal](#^brz-toc-heading-1)\n\n### Closed ^literal ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-closed",
    ),
    pytest.param(
        "[/toc/]\n\n# Power $x^2$ and literal \\^suffix\nBody\n\nAuthored body.\n",
        "- [Power $x^2$ and literal \\^suffix](#^brz-toc-heading-1)\n\n# Power $x^2$ and literal \\^suffix ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-math",
    ),
    pytest.param(
        "[/toc depth=2]\n\n# Kept\nBody\n\nAuthored body.\n",
        "[/toc depth=2]\n\n# Kept\nBody\n\nAuthored body.\n",
        id="toc-unsupported",
    ),
    pytest.param(
        "$$c = \\sqrt{a^2+b^2}$$\n\nAuthored body.\n",
        "$$c = \\sqrt{a^2+b^2}$$\n\nAuthored body.\n",
        id="math-unchanged",
    ),
    pytest.param(
        '### Contents\n[/toc/]\n\n### Table <Value>\n|Thought|Image|:(table="column-widths:-1,0,174;justification:default"):\n|[Child](brain://AAAAAAAAAECAAAAAAAAAAw/title)|![Alt](.data/md-images/00000000-0000-4000-8000-000000000202.webp#$width=50p$)|\n\n> [!note]\n> [Child](brain://AAAAAAAAAECAAAAAAAAAAw/title)\n> [!tip|icon:😂]\n> Press <Enter>.\n\nAuthored body.\n',
        "### Contents\n- [Table \\<Value\\>](#^brz-toc-heading-1)\n\n### Table \\<Value> ^brz-toc-heading-1\n|Thought|Image|\n|---|---|\n|[[Child.md\\|Child]]|![Alt](00000000-0000-4000-8000-000000000202.bin)|\n\n> [!note]\n> [[Child.md|Child]]\n\n> [!tip] 😂 Tip\n> Press \\<Enter>.\n\nAuthored body.\n",
        id="composition",
    ),
    pytest.param(
        "> [!TIP|icon:é]\n> Body\n\nAuthored body.\n",
        "> [!tip] é Tip\n> Body\n\nAuthored body.\n",
        id="icon-non-symbol",
    ),
    pytest.param(
        "> [!tip|icon:😂*]\n> Body\n\nAuthored body.\n",
        "> [!tip] Tip — |icon:😂\\*\n> Body\n\nAuthored body.\n",
        id="icon-forbidden-ascii",
    ),
    pytest.param(
        "> [!TIP|icon:😂:]\n> Body\n\nAuthored body.\n",
        "> [!tip] Tip — |icon:😂:\n> Body\n\nAuthored body.\n",
        id="icon-forbidden-colon",
    ),
    pytest.param(
        "`begin\n[/toc/]\nend`\n\n> [!tip|icon:😂]\n> Body\n\nProse <!-- begin\n[/toc/]\nend -->\n\nAuthored body.\n",
        "`begin\n[/toc/]\nend`\n\n> [!tip] 😂 Tip\n> Body\n\nProse <!-- begin\n[/toc/]\nend -->\n\nAuthored body.\n",
        id="multiline-protected",
    ),
    pytest.param(
        "[/toc/]\n\n# ![Café *emphasis* `code` [square] & ^literal](.data/md-images/00000000-0000-4000-8000-000000000202.webp)\nBody\n\nAuthored body.\n",
        "- [Café emphasis code \\[square\\] & \\^literal](#^brz-toc-heading-1)\n\n# ![Café *emphasis* `code` [square] & ^literal](00000000-0000-4000-8000-000000000202.bin) ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-image-label",
    ),
    pytest.param(
        "[/toc/]\n\n# [**Child**](brain://AAAAAAAAAECAAAAAAAAAAw/title)\nBody\n\nAuthored body.\n",
        "- [Child](#^brz-toc-heading-1)\n\n# [[Child.md|Child]] ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-link-label",
    ),
    pytest.param(
        '|Code|Other|:(table="column-widths:-1,0,84;justification:default"):\n|`[**Child**](brain://AAAAAAAAAECAAAAAAAAAAw/title)|x`|value|\n\nAuthored body.\n',
        "|Code|Other|\n|---|---|\n|<code>[**Child**](brain://AAAAAAAAAECAAAAAAAAAAw/title)&#124;x</code>|value|\n\nAuthored body.\n",
        id="table-code-reference",
    ),
    pytest.param(
        "|[**Child**](brain://AAAAAAAAAECAAAAAAAAAAw/title)|value|\n\nAuthored body.\n",
        "|[[Child.md|Child]]|value|\n\nAuthored body.\n",
        id="table-nonnative-reference",
    ),
    pytest.param(
        '|One|Two|:(table="column-widths:-1,0,-2;justification:default"):\n|1|2|\n\nAuthored body.\n',
        '|One|Two|:(table="column-widths:-1,0,-2;justification:default"):\n|1|2|\n\nAuthored body.\n',
        id="table-negative-width",
    ),
    pytest.param(
        '|One|Two|:(table="column-widths:-1,0,00;justification:default"):\n|1|2|\n\nAuthored body.\n',
        '|One|Two|:(table="column-widths:-1,0,00;justification:default"):\n|1|2|\n\nAuthored body.\n',
        id="table-leading-zero-width",
    ),
    pytest.param(
        '|One :(table="ambiguous"):|Two|:(table="column-widths:-1,0,84;justification:default"):\n|1|2|\n\nAuthored body.\n',
        '|One :(table="ambiguous"):|Two|:(table="column-widths:-1,0,84;justification:default"):\n|1|2|\n\nAuthored body.\n',
        id="table-multiple-declarations",
    ),
    pytest.param(
        '`literal beginning\n|literal`|Other|:(table="column-widths:-1,0,84;justification:default"):\n|1|2|\n\nAuthored body.\n',
        '`literal beginning\n|literal`|Other|:(table="column-widths:-1,0,84;justification:default"):\n|1|2|\n\nAuthored body.\n',
        id="table-protected-boundary",
    ),
    pytest.param(
        '|One|Two|:(table="column-widths:-1,0,84;justification:default"):\n|1|2|\n|incomplete\n\nAuthored body.\n',
        '|One|Two|:(table="column-widths:-1,0,84;justification:default"):\n|1|2|\n|incomplete\n\nAuthored body.\n',
        id="table-incomplete-row",
    ),
    pytest.param(
        "### Contents\n\n[/toc/]\n\n# Target\nBody\n\nAuthored body.\n",
        "### Contents\n\n- [Target](#^brz-toc-heading-1)\n\n# Target ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-label-blank",
    ),
    pytest.param(
        "Plain\u2028> [!tip|icon:😂]\u2028> Body\n\nAuthored body.\n",
        "Plain\u2028> [!tip|icon:😂]\u2028> Body\n\nAuthored body.\n",
        id="unicode-inline-separator",
    ),
    pytest.param(
        "[/toc/]\n\n# First\nBody\n\n### Nested\nBody\n\n## Second\nBody\n\nAuthored body.\n",
        "- [First](#^brz-toc-heading-1)\n  - [Nested](#^brz-toc-heading-2)\n  - [Second](#^brz-toc-heading-3)\n\n# First ^brz-toc-heading-1\nBody\n\n### Nested ^brz-toc-heading-2\nBody\n\n## Second ^brz-toc-heading-3\nBody\n\nAuthored body.\n",
        id="toc-skipped-level",
    ),
    pytest.param(
        "[/toc/]\n\n# Target\nBody\n\n`^brz-toc-heading-1`\n\nAuthored body.\n",
        "- [Target](#^brz-toc-heading-1-generated)\n\n# Target ^brz-toc-heading-1-generated\nBody\n\n`^brz-toc-heading-1`\n\nAuthored body.\n",
        id="toc-protected-id",
    ),
    pytest.param(
        "[/toc/]\n\n# `a*b`\nBody\n\nAuthored body.\n",
        "- [a\\*b](#^brz-toc-heading-1)\n\n# `a*b` ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-code-punctuation",
    ),
    pytest.param(
        '|One|Two|:(table="column-widths:-1,0,84;justification:default"): \n|1|2|\n\nAuthored body.\n',
        '|One|Two|:(table="column-widths:-1,0,84;justification:default"): \n|1|2|\n\nAuthored body.\n',
        id="table-trailing-space",
    ),
    pytest.param(
        "> [!note] Parent\n> > [!tip] Child\n> > Body\n> > `literal beginning\n> parent literal line\n> literal end`\n\nAuthored body.\n",
        "> [!note] Parent\n> > [!tip] Child\n> > Body\n> > `literal beginning\n> parent literal line\n> literal end`\n\nAuthored body.\n",
        id="callout-protected-return",
    ),
    pytest.param(
        "[/toc/]\n\n# Mixed ![Image ^literal](.data/md-images/00000000-0000-4000-8000-000000000202.webp) `Code ^literal` ^authored-mixed\nBody\n\nAuthored body.\n",
        "- [Mixed Image ^literal Code \\^literal](#^authored-mixed)\n\n# Mixed ![Image ^literal](00000000-0000-4000-8000-000000000202.bin) `Code ^literal` ^authored-mixed\nBody\n\nAuthored body.\n",
        id="toc-mixed-caret",
    ),
    pytest.param(
        "[/toc/]\n\n# Target\nBody\n\n`^brz-toc-heading-10`\n\nAuthored body.\n",
        "- [Target](#^brz-toc-heading-1)\n\n# Target ^brz-toc-heading-1\nBody\n\n`^brz-toc-heading-10`\n\nAuthored body.\n",
        id="toc-id-prefix-nearmiss",
    ),
    pytest.param(
        "[/toc/]\n\n# $a<b$\nBody\n\nAuthored body.\n",
        "- [\\$a\\<b\\$](#^brz-toc-heading-1)\n\n# $a<b$ ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-math-angle",
    ),
    pytest.param(
        "[/toc/]\n\n# $a[b]$\nBody\n\nAuthored body.\n",
        "- [\\$a\\[b\\]\\$](#^brz-toc-heading-1)\n\n# $a[b]$ ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-math-square",
    ),
    pytest.param(
        "[/toc/]\n\n# $a>b$\nBody\n\nAuthored body.\n",
        "- [\\$a\\>b\\$](#^brz-toc-heading-1)\n\n# $a>b$ ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-math-greater",
    ),
    pytest.param(
        "[/toc/]\n\n# $a\\$\nBody\n\nAuthored body.\n",
        "- [\\$a\\$](#^brz-toc-heading-1)\n\n# $a\\$ ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-escaped-dollar",
    ),
    pytest.param(
        "[/toc/]\n\n# $a `b`$\nBody\n\nAuthored body.\n",
        "- [\\$a b\\$](#^brz-toc-heading-1)\n\n# $a `b`$ ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-code-overlap",
    ),
    pytest.param(
        "[/toc/]\n\n# ![$x$](.data/md-images/00000000-0000-4000-8000-000000000202.webp)\nBody\n\nAuthored body.\n",
        "- [\\$x\\$](#^brz-toc-heading-1)\n\n# ![$x$](00000000-0000-4000-8000-000000000202.bin) ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-image-math",
    ),
    pytest.param(
        "[/toc/]\n\n# [$x$](https://example.invalid)\nBody\n\nAuthored body.\n",
        "- [\\$x\\$](#^brz-toc-heading-1)\n\n# [$x$](https://example.invalid) ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-link-math",
    ),
    pytest.param(
        "[/toc/]\n\n# A  B\nBody\n\nAuthored body.\n",
        "- [A  B](#^brz-toc-heading-1)\n\n# A  B ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-interior-spaces",
    ),
    pytest.param(
        "[/toc/]\n\n# `\\<`\nBody\n\nAuthored body.\n",
        "- [\\\\\\<](#^brz-toc-heading-1)\n\n# `\\<` ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-code-backslash",
    ),
    pytest.param(
        "[/toc/]\n\n# ` `\nBody\n\nAuthored body.\n",
        "- [Heading](#^brz-toc-heading-1)\n\n# ` ` ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-code-empty",
    ),
    pytest.param(
        "[/toc/]\n\n# ![` `](.data/md-images/00000000-0000-4000-8000-000000000202.webp)\nBody\n\nAuthored body.\n",
        "- [Image](#^brz-toc-heading-1)\n\n# ![` `](00000000-0000-4000-8000-000000000202.bin) ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-image-code-empty",
    ),
    pytest.param(
        "[/toc/]\n\n# \\\\<\nBody\n\nAuthored body.\n",
        "- [\\\\\\<](#^brz-toc-heading-1)\n\n# \\\\< ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-text-backslash",
    ),
    pytest.param(
        "[/toc/]\n\n# \\`literal` $x$ `tail\nBody\n\nAuthored body.\n",
        "- [\\`literal\\$x\\$tail](#^brz-toc-heading-1)\n\n# \\`literal` $x$ `tail ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-escaped-code-discovery",
    ),
    pytest.param(
        "[/toc/]\n\n# A <!-- `ignored` --> B\nBody\n\nAuthored body.\n",
        "- [A  B](#^brz-toc-heading-1)\n\n# A <!-- `ignored` --> B ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-comment-owned-code",
    ),
    pytest.param(
        "[/toc/]\n\n# \\``$x$`\nBody\n\nAuthored body.\n",
        "- [\\`\\$x\\$](#^brz-toc-heading-1)\n\n# \\``$x$` ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-escaped-run-suffix",
    ),
    pytest.param(
        "[/toc/]\n\n# \\```$x$``\nBody\n\nAuthored body.\n",
        "- [\\`\\$x\\$](#^brz-toc-heading-1)\n\n# \\```$x$`` ^brz-toc-heading-1\nBody\n\nAuthored body.\n",
        id="toc-escaped-run-suffix-three",
    ),
]
