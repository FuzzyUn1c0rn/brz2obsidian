"""Independent reverse-hierarchy source and preservation controls for issue 214."""

import json

import pytest

from tests.local_acceptance.api_checker import audit_baseline, check_api_vault
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


def test_profile3_reverse_hierarchy_preserves_source_tuple_endpoints_and_navigation(
    tmp_path,
):
    baseline, vault = reverse_case(tmp_path)
    assert audit_baseline(baseline, profile_version="3")["relationships"] == 5
    assert check_api_vault(baseline, vault, profile_version="3") == {
        "thoughts": 4,
        "relationships": 5,
        "payloads": 3,
    }
    assert (
        (vault / "Home.md")
        .read_text(encoding="utf-8")
        .endswith("## Children\n\n- [[Child.md|Child]]\n")
    )
    assert (
        (vault / "Child.md")
        .read_text(encoding="utf-8")
        .endswith("## Parents\n\n- [[Home.md|Home]]\n")
    )


@pytest.mark.parametrize("profile", ["1", "2"])
def test_reverse_hierarchy_is_refused_by_both_old_profile_audits(tmp_path, profile):
    baseline, vault = reverse_case(tmp_path)
    with pytest.raises(AssertionError, match="unqualified raw relationship signature"):
        audit_baseline(baseline, profile_version=profile)
    with pytest.raises(AssertionError, match="unqualified raw relationship signature"):
        check_api_vault(baseline, vault, profile_version=profile)
    with pytest.raises(AssertionError, match="unqualified raw relationship signature"):
        audit_baseline(baseline)


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


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", True),
        ("kind", 1.0),
        ("kind", "1"),
        ("direction", 3.0),
        ("direction", "3"),
    ],
)
@pytest.mark.parametrize("conflicting_first", [False, True])
def test_reverse_hierarchy_repeated_scalars_must_agree_strictly_in_either_order(
    tmp_path, field, value, conflicting_first
):
    baseline, _ = reverse_case(tmp_path)

    def change(manifest, graphs):
        key = identity(2 if conflicting_first else 3)
        link = next(r for r in graphs[key]["links"] if r["id"] == identity(101))
        link[field] = value

    baseline = mutate_source(baseline, change)
    with pytest.raises(AssertionError, match="conflicting raw relationship"):
        audit_baseline(baseline, profile_version="3")


@pytest.mark.parametrize(
    "damage",
    [
        "a-inventory",
        "b-inventory",
        "nonincident-only",
        "a-children",
        "b-parents",
        "extra-child",
        "extra-parent",
        "stale-neighbor",
        "metadata-missing",
        "metadata-tuple",
        "metadata-bool",
        "metadata-float",
        "metadata-status",
        "content-outcome",
        "content-nonempty",
        "content-missing",
    ],
)
def test_reverse_hierarchy_requires_complete_authoritative_graph_and_content_joins(
    tmp_path, damage
):
    baseline, vault = reverse_case(tmp_path)
    root = baseline.manifest_path.parent

    def change(manifest, graphs):
        a, b, definition, tag = (identity(n) for n in (2, 3, 4, 5))
        if damage in {"a-inventory", "b-inventory", "nonincident-only"}:
            source = next(r for r in graphs[a]["links"] if r["id"] == identity(101))
            keys = (
                [a]
                if damage == "a-inventory"
                else [b]
                if damage == "b-inventory"
                else [a, b]
            )
            for key in keys:
                graphs[key]["links"] = [
                    r for r in graphs[key]["links"] if r["id"] != identity(101)
                ]
            if damage == "nonincident-only":
                graphs[definition]["links"].append(source)
        elif damage == "a-children":
            graphs[a]["children"] = []
        elif damage == "b-parents":
            graphs[b]["parents"] = []
        elif damage == "extra-child":
            graphs[a]["children"].append(graphs[definition]["activeThought"])
        elif damage == "extra-parent":
            graphs[b]["parents"].append(graphs[tag]["activeThought"])
        elif damage == "stale-neighbor":
            graphs[a]["children"][0]["name"] = "Stale child hint"
        elif damage == "metadata-missing":
            manifest["relationship_metadata"].clear()
        elif damage in {"metadata-tuple", "metadata-bool", "metadata-float"}:
            path = root / manifest["relationship_metadata"][identity(101)]["path"]
            row = json.loads(path.read_bytes())
            row["direction" if damage == "metadata-tuple" else "kind"] = (
                1
                if damage == "metadata-tuple"
                else True
                if damage == "metadata-bool"
                else 1.0
            )
            write_json(path, row)
        elif damage == "metadata-status":
            manifest["relationship_metadata"][identity(101)]["status"] = 404
        elif damage == "content-outcome":
            manifest["link_attachment_outcomes"][identity(101)] = 404
        elif damage == "content-nonempty":
            write_json(
                root / manifest["link_attachments"][identity(101)],
                [{"id": identity(999)}],
            )
        else:
            del manifest["link_attachments"][identity(101)]

    baseline = mutate_source(baseline, change)
    with pytest.raises(AssertionError):
        audit_baseline(baseline, profile_version="3")
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


def test_reverse_hierarchy_allows_qualified_type_provider_parent_overlap(tmp_path):
    baseline, vault = reverse_case(tmp_path)

    def change(manifest, graphs):
        graphs[identity(3)]["parents"].append(graphs[identity(4)]["activeThought"])

    baseline = mutate_source(baseline, change)
    assert audit_baseline(baseline, profile_version="3")["relationships"] == 5
    assert check_api_vault(baseline, vault, profile_version="3")["relationships"] == 5


@pytest.mark.parametrize(
    "damage",
    [
        "reverse-record",
        "omit-record",
        "alter-source-tuple",
        "omit-parent",
        "omit-child",
        "reverse-parent",
        "reverse-child",
        "duplicate-child",
        "missing-note",
    ],
)
def test_reverse_hierarchy_actual_navigation_and_source_evidence_cannot_be_replaced_by_record_claims(
    tmp_path, damage
):
    baseline, vault = reverse_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    if damage == "reverse-record":
        row = record["relationships"][0]
        row["item_a"], row["item_b"] = row["item_b"], row["item_a"]
    elif damage == "omit-record":
        record["relationships"].pop(0)
    elif damage == "alter-source-tuple":
        row = next(
            r
            for r in record["original_evidence"][0]["records"]
            if r["id"] == identity(101)
        )
        row["direction"] = 1
    elif damage == "omit-parent":
        (vault / "Child.md").write_text("# Child\n", encoding="utf-8")
    elif damage == "omit-child":
        (vault / "Home.md").write_text("# Home\n\nOriginal note.\n", encoding="utf-8")
    elif damage == "reverse-parent":
        (vault / "Child.md").write_text(
            "# Child\n\n## Children\n\n- [[Home.md|Home]]\n", encoding="utf-8"
        )
    elif damage == "reverse-child":
        (vault / "Home.md").write_text(
            "# Home\n\n## Parents\n\n- [[Child.md|Child]]\n", encoding="utf-8"
        )
    elif damage == "duplicate-child":
        with (vault / "Home.md").open("a", encoding="utf-8") as stream:
            stream.write("- [[Child.md|Child]]\n")
    else:
        (vault / "Child.md").unlink()
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", 2),
        ("relation", 2),
        ("meaning", 3),
        ("direction", 2),
        ("typeId", identity(999)),
    ],
)
def test_reverse_hierarchy_near_miss_tuple_refuses_after_fresh_requalification(
    tmp_path, field, value
):
    baseline, _ = reverse_case(tmp_path)

    def change(manifest, graphs):
        for graph in graphs.values():
            for row in graph["links"]:
                if row["id"] == identity(101):
                    row[field] = value

    with pytest.raises(AssertionError):
        audit_baseline(mutate_source(baseline, change), profile_version="3")


@pytest.mark.parametrize("kind", [2, 4, True, 1.0])
def test_reverse_hierarchy_requires_exact_ordinary_endpoint_roles(tmp_path, kind):
    baseline, _ = reverse_case(tmp_path)

    def change(manifest, graphs):
        graphs[identity(3)]["activeThought"]["kind"] = kind
        graphs[identity(2)]["children"][0]["kind"] = kind

    with pytest.raises(AssertionError):
        audit_baseline(mutate_source(baseline, change), profile_version="3")


def test_reverse_hierarchy_allows_additional_nonincident_raw_discovery_context(
    tmp_path,
):
    baseline, vault = reverse_case(tmp_path)

    def change(manifest, graphs):
        row = next(r for r in graphs[identity(2)]["links"] if r["id"] == identity(101))
        graphs[identity(4)]["links"].append(row)

    baseline = mutate_source(baseline, change)
    assert audit_baseline(baseline, profile_version="3")["relationships"] == 5
    assert check_api_vault(baseline, vault, profile_version="3")["relationships"] == 5


@pytest.mark.parametrize("profile", ["1", "2", "3"])
def test_inherited_hierarchy_keeps_nonordinary_endpoint_roles(tmp_path, profile):
    baseline, vault = source_case(tmp_path)
    root = baseline.manifest_path.parent
    row = {
        "id": identity(106),
        "brainId": identity(1),
        "thoughtIdA": identity(4),
        "thoughtIdB": identity(5),
        "kind": 1,
        "relation": 1,
        "meaning": 1,
        "direction": 1,
        "typeId": None,
    }

    def change(manifest, graphs):
        manifest["scope"]["relationship_ids"].append(identity(106))
        name = "additional-hierarchy-content.json"
        write_json(root / name, [])
        manifest["files"][name] = fingerprint(root / name)
        manifest["link_attachments"][identity(106)] = name
        graphs[identity(4)]["links"].append(row)
        graphs[identity(5)]["links"].append(row)
        graphs[identity(4)]["children"].append(graphs[identity(5)]["activeThought"])
        graphs[identity(5)]["parents"].append(graphs[identity(4)]["activeThought"])

    baseline = mutate_source(baseline, change)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["profile_version"] = profile
    record["original_evidence"][0]["records"].append(row)
    record["relationships"].append(
        {
            "key": identity(106),
            "kind": "hierarchy",
            "item_a": identity(4),
            "item_b": identity(5),
        }
    )
    write_json(record_path, record)
    assert audit_baseline(baseline, profile_version=profile)["relationships"] == 6
    assert (
        check_api_vault(baseline, vault, profile_version=profile)["relationships"] == 6
    )


def test_reverse_hierarchy_home_navigation_allows_existing_categories_footer(tmp_path):
    baseline, vault = reverse_case(tmp_path)
    with (vault / "Home.md").open("a", encoding="utf-8") as stream:
        stream.write("\n## Categories\n\n[[Categories.md|Browse categories]]\n")
    assert check_api_vault(baseline, vault, profile_version="3")["relationships"] == 5


@pytest.mark.parametrize("generated_present", [False, True])
def test_authored_children_heading_cannot_replace_generated_reverse_navigation(
    tmp_path, generated_present
):
    baseline, vault = reverse_case(tmp_path)
    raw = b"Authored example.\n\n## Children\n\n- [[Child.md|Child]]\n"
    note = (
        baseline.manifest_path.parent / baseline.data["payloads"][identity(201)]["path"]
    )
    note.write_bytes(raw)
    baseline = reseal(baseline)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    target = next(a for a in record["asset_targets"] if a["asset_id"] == identity(201))
    (vault / target["relative_path"]).write_bytes(raw)
    target.update(actual_length=len(raw), actual_sha256=fingerprint(note)["sha256"])
    write_json(record_path, record)
    body = "# Home\n\n" + raw.decode()
    if generated_present:
        body += "\n## Children\n\n- [[Child.md|Child]]\n"
    (vault / "Home.md").write_text(body, encoding="utf-8")
    if generated_present:
        assert (
            check_api_vault(baseline, vault, profile_version="3")["relationships"] == 5
        )
    else:
        with pytest.raises(AssertionError, match="generated navigation"):
            check_api_vault(baseline, vault, profile_version="3")


def test_authored_label_cannot_replace_generated_reverse_parent_navigation(tmp_path):
    baseline, vault = reverse_case(tmp_path)
    label = "## Parents\n\n- [[Home.md|Home]]\n"

    def change(manifest, graphs):
        for graph in graphs.values():
            if graph["activeThought"]["id"] == identity(3):
                graph["activeThought"]["label"] = label
            for field in ("parents", "children", "jumps", "tags"):
                for neighbor in graph[field] or []:
                    if neighbor["id"] == identity(3):
                        neighbor["label"] = label

    baseline = mutate_source(baseline, change)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    next(
        r for r in record["original_evidence"][0]["records"] if r["id"] == identity(3)
    )["label"] = label
    write_json(record_path, record)
    (vault / "Child.md").write_text("# Child\n\n" + label, encoding="utf-8")
    with pytest.raises(AssertionError, match="generated navigation"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("damage", [None, "order", "label"])
def test_reverse_navigation_uses_canonical_identity_order_and_visible_labels(
    tmp_path, damage
):
    baseline, vault = reverse_case(tmp_path)
    root = baseline.manifest_path.parent
    title = "A [type] | one\r\n two"
    extra = {
        "id": identity(106),
        "brainId": identity(1),
        "thoughtIdA": identity(2),
        "thoughtIdB": identity(4),
        "kind": 1,
        "relation": 1,
        "meaning": 1,
        "direction": 1,
        "typeId": None,
    }

    def change(manifest, graphs):
        for graph in graphs.values():
            rows = [
                graph["activeThought"],
                *(graph["parents"] or []),
                *(graph["children"] or []),
                *(graph["jumps"] or []),
                *(graph["tags"] or []),
            ]
            if graph["type"]:
                rows.append(graph["type"])
            for row in rows:
                if row["id"] == identity(4):
                    row["name"] = title
        types = json.loads((root / manifest["types"]).read_bytes())
        types[0]["name"] = title
        write_json(root / manifest["types"], types)
        graphs[identity(2)]["links"].append(extra)
        graphs[identity(4)]["links"].append(extra)
        graphs[identity(2)]["children"].append(graphs[identity(4)]["activeThought"])
        graphs[identity(4)]["parents"].append(graphs[identity(2)]["activeThought"])
        manifest["scope"]["relationship_ids"].append(identity(106))
        name = "additional-display-link-content.json"
        write_json(root / name, [])
        manifest["files"][name] = fingerprint(root / name)
        manifest["link_attachments"][identity(106)] = name

    baseline = mutate_source(baseline, change)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    next(
        r for r in record["original_evidence"][0]["records"] if r["id"] == identity(4)
    )["name"] = title
    record["original_evidence"][0]["records"].append(extra)
    next(t for t in record["item_targets"] if t["item_key"] == identity(4)).update(
        original_title=title, relative_path="Categories/A.md", created=True
    )
    record["relationships"].append(
        {
            "key": identity(106),
            "kind": "hierarchy",
            "item_a": identity(2),
            "item_b": identity(4),
        }
    )
    write_json(path, record)
    lines = ["- [[Child.md|Child]]\n", "- [[Categories/A.md|A type one two]]\n"]
    if damage == "order":
        lines.reverse()
    elif damage == "label":
        lines[1] = "- [[Categories/A.md|Wrong display label]]\n"
    (vault / "Home.md").write_text(
        "# Home\n\nOriginal note.\n\n## Children\n\n" + "".join(lines), encoding="utf-8"
    )
    if damage:
        with pytest.raises(AssertionError, match="Parents/Children navigation"):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert (
            check_api_vault(baseline, vault, profile_version="3")["relationships"] == 6
        )


@pytest.mark.parametrize("owner,heading", [("Home", "Children"), ("Child", "Parents")])
@pytest.mark.parametrize(
    "damage", ["incorrect", "duplicate", "prose-only", "empty", "noncanonical"]
)
def test_separated_extra_generated_navigation_cannot_hide_before_correct_tail(
    tmp_path, owner, heading, damage
):
    baseline, vault = reverse_case(tmp_path)
    expected = "- [[Child.md|Child]]\n" if owner == "Home" else "- [[Home.md|Home]]\n"
    if damage == "incorrect":
        extra = f"## {heading}\n\n- [[{owner}.md|{owner}]]\n"
    elif damage == "duplicate":
        extra = f"## {heading}\n\n" + expected
    elif damage == "prose-only":
        extra = f"## {heading}\n\nUnexplained generated relationship prose.\n"
    elif damage == "noncanonical":
        extra = f"### {heading.lower()}\n\n" + expected
    else:
        extra = f"## {heading}\n\n"
    prefix = "# Home\n\nOriginal note.\n\n" if owner == "Home" else "# Child\n\n"
    (vault / (owner + ".md")).write_text(
        prefix
        + extra
        + "\nUnexpected generated separator.\n\n"
        + f"## {heading}\n\n"
        + expected,
        encoding="utf-8",
    )
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


def test_reverse_navigation_keeps_resources_before_relationships_and_home_footer(
    tmp_path,
):
    baseline, vault = reverse_case(tmp_path)
    (vault / "Home.md").write_text(
        "# Home\n\nOriginal note.\n\n## Resources\n\n"
        "- [[00000000-0000-4000-8000-000000000203.bin|manual.pdf]]\n\n"
        "## Children\n\n- [[Child.md|Child]]\n\n"
        "## Categories\n\n[[Categories.md|Browse categories]]\n",
        encoding="utf-8",
    )
    assert check_api_vault(baseline, vault, profile_version="3")["relationships"] == 5


@pytest.mark.parametrize("owner", [2, 3])
@pytest.mark.parametrize("newline", ["\r\n", "\r"])
def test_reverse_endpoint_heading_preserves_newline_titles_without_false_refusal(
    tmp_path, owner, newline
):
    baseline, vault = reverse_case(tmp_path)
    titles = {identity(2): "Home", identity(3): "Child"}
    titles[identity(owner)] += newline + "Entry"

    def change(manifest, graphs):
        for graph in graphs.values():
            rows = [
                graph["activeThought"],
                *(graph["parents"] or []),
                *(graph["children"] or []),
                *(graph["jumps"] or []),
                *(graph["tags"] or []),
            ]
            for row in rows:
                if row["id"] == identity(owner):
                    row["name"] = titles[identity(owner)]

    baseline = mutate_source(baseline, change)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    next(
        r
        for r in record["original_evidence"][0]["records"]
        if r["id"] == identity(owner)
    )["name"] = titles[identity(owner)]
    next(t for t in record["item_targets"] if t["item_key"] == identity(owner))[
        "original_title"
    ] = titles[identity(owner)]
    write_json(record_path, record)
    parent_label = "Home Entry" if owner == 2 else "Home"
    child_label = "Child Entry" if owner == 3 else "Child"
    (vault / "Home.md").write_bytes(
        (
            "# "
            + titles[identity(2)]
            + "\n\nOriginal note.\n\n## Children\n\n"
            + "- [[Child.md|"
            + child_label
            + "]]\n"
        ).encode()
    )
    (vault / "Child.md").write_bytes(
        (
            "# "
            + titles[identity(3)]
            + "\n\n## Parents\n\n"
            + "- [[Home.md|"
            + parent_label
            + "]]\n"
        ).encode()
    )
    assert check_api_vault(baseline, vault, profile_version="3")["relationships"] == 5


@pytest.mark.parametrize(
    "owner,field",
    [(2, "parents"), (2, "tags"), (2, "siblings"), (3, "children"), (4, "links")],
)
@pytest.mark.parametrize("value", [None, False, 0, "", {}])
def test_required_reverse_graph_arrays_refuse_falsey_nonlists(
    tmp_path, owner, field, value
):
    baseline, _ = reverse_case(tmp_path)

    def change(manifest, graphs):
        graphs[identity(owner)][field] = value

    baseline = mutate_source(baseline, change)
    with pytest.raises(AssertionError):
        audit_baseline(baseline, profile_version="3")


def test_reverse_graph_nullable_attachments_keep_authoritative_list_fallback(tmp_path):
    baseline, vault = reverse_case(tmp_path)
    root = baseline.manifest_path.parent

    def change(manifest, graphs):
        name = "home-attachment-inventory.json"
        write_json(root / name, graphs[identity(2)]["attachments"])
        manifest["files"][name] = fingerprint(root / name)
        manifest["attachment_inventories"] = {identity(2): name}
        graphs[identity(2)]["attachments"] = None

    baseline = mutate_source(baseline, change)
    assert check_api_vault(baseline, vault, profile_version="3")["relationships"] == 5


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


def test_empty_unclassified_reverse_leaf_stays_uncreated_with_parent_link(tmp_path):
    baseline, vault = empty_reverse_leaf_case(tmp_path)
    assert check_api_vault(baseline, vault, profile_version="3")["relationships"] == 4
    assert not (vault / "Child.md").exists()
    assert "- [[Child.md|Child]]" in (vault / "Home.md").read_text()


@pytest.mark.parametrize(
    "damage",
    [
        "unexpected-note",
        "missing-parent-link",
        "unneeded-child-created",
        "nonboolean-created",
    ],
)
def test_empty_reverse_leaf_materialization_and_navigation_are_source_bound(
    tmp_path, damage
):
    baseline, vault = empty_reverse_leaf_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    child = next(t for t in record["item_targets"] if t["item_key"] == identity(3))
    if damage == "unexpected-note":
        (vault / "Child.md").write_text("# Child\n")
    elif damage == "missing-parent-link":
        (vault / "Home.md").write_text("# Home\n\nOriginal note.\n")
    elif damage == "nonboolean-created":
        child["created"] = 0
    else:
        child["created"] = True
        (vault / "Child.md").write_text("# Child\n\n## Parents\n\n- [[Home.md|Home]]\n")
    write_json(path, record)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="3")


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


@pytest.mark.parametrize("swap", [False, True])
def test_empty_reverse_edge_requires_deterministic_selected_parent(tmp_path, swap):
    baseline, vault = two_empty_reverse_endpoints_case(tmp_path)
    if swap:
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        for target in record["item_targets"]:
            if target["item_key"] in {identity(3), identity(6)}:
                target["created"] = target["item_key"] == identity(6)
        write_json(path, record)
        (vault / "Child.md").unlink()
        (vault / "Leaf.md").write_text("# Leaf\n\n## Parents\n\n- [[Child.md|Child]]\n")
        with pytest.raises(AssertionError):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert (
            check_api_vault(baseline, vault, profile_version="3")["relationships"] == 5
        )


@pytest.mark.parametrize("content", ["note", "url"])
def test_source_content_cannot_be_hidden_by_uncreated_reverse_target(tmp_path, content):
    baseline, vault = empty_reverse_leaf_case(tmp_path)
    root = baseline.manifest_path.parent
    attachment = {
        "id": identity(205),
        "brainId": identity(1),
        "sourceId": identity(3),
        "sourceType": 2,
        "type": 1 if content == "note" else 3,
        "isNotes": content == "note",
        "location": "Notes.md"
        if content == "note"
        else "https://example.invalid/source",
        "name": None,
        "dataLength": 20,
    }
    payload = b"Required child content.\n"

    def change(manifest, graphs):
        graphs[identity(3)]["attachments"].append(attachment)
        manifest["scope"]["attachment_ids"].append(identity(205))
        if content == "note":
            (root / "child-note.bin").write_bytes(payload)
            manifest["files"]["child-note.bin"] = fingerprint(root / "child-note.bin")
            manifest["payloads"][identity(205)] = {
                "status": 200,
                "path": "child-note.bin",
            }
            del manifest["no_notes"][identity(3)]

    baseline = mutate_source(baseline, change)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    record["original_evidence"][0]["records"].append(attachment)
    target = {
        "asset_id": identity(205),
        "owner": identity(3),
        "role": "note_original" if content == "note" else "url",
        "availability": "present" if content == "note" else "external",
        "original_name": attachment["location"],
        "display_name": None,
        "relative_path": "child-note.bin" if content == "note" else None,
        "actual_length": len(payload) if content == "note" else None,
        "actual_sha256": fingerprint(root / "child-note.bin")["sha256"]
        if content == "note"
        else None,
    }
    if content == "note":
        (vault / "child-note.bin").write_bytes(payload)
    else:
        target["external_uri"] = attachment["location"]
    record["asset_targets"].append(target)
    write_json(path, record)
    with pytest.raises(AssertionError, match="reverse hierarchy note materialization"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("owner", [2, 3])
def test_home_and_classified_reverse_endpoints_cannot_be_falsely_uncreated(
    tmp_path, owner
):
    baseline, vault = reverse_case(tmp_path)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    target = next(t for t in record["item_targets"] if t["item_key"] == identity(owner))
    target["created"] = False
    (vault / target["relative_path"]).unlink()
    write_json(path, record)
    with pytest.raises(AssertionError, match="reverse hierarchy note materialization"):
        check_api_vault(baseline, vault, profile_version="3")


@pytest.mark.parametrize("hide_parent", [False, True])
def test_old_tag_hierarchy_context_does_not_seed_a_contentless_tag(
    tmp_path, hide_parent
):
    baseline, vault = two_empty_reverse_endpoints_case(tmp_path)
    root = baseline.manifest_path.parent

    def change(manifest, graphs):
        for graph in graphs.values():
            for row in [
                graph["activeThought"],
                *graph["parents"],
                *graph["children"],
                *graph["jumps"],
                *graph["tags"],
            ]:
                if row["id"] == identity(6):
                    row["kind"] = 4
            for row in graph["links"]:
                if row["id"] == identity(106):
                    row["direction"] = -1
        tags_path = root / manifest["tags"]["path"]
        tags = json.loads(tags_path.read_bytes())
        tags.append(graphs[identity(6)]["activeThought"])
        write_json(tags_path, tags)
        metadata_path = root / manifest["relationship_metadata"][identity(106)]["path"]
        metadata = json.loads(metadata_path.read_bytes())
        metadata["direction"] = -1
        write_json(metadata_path, metadata)
        for name in manifest["statistics"]:
            stats = json.loads((root / name).read_bytes())
            stats.update(thoughts=2, tags=2)
            write_json(root / name, stats)

    baseline = mutate_source(baseline, change)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    for row in record["original_evidence"][0]["records"]:
        if row["id"] == identity(6):
            row["kind"] = 4
        elif row["id"] == identity(106):
            row["direction"] = -1
    if hide_parent:
        for target in record["item_targets"]:
            if target["item_key"] in {identity(3), identity(6)}:
                target["created"] = target["item_key"] == identity(6)
        (vault / "Child.md").unlink()
        (vault / "Leaf.md").write_text("# Leaf\n\n## Parents\n\n- [[Child.md|Child]]\n")
    write_json(path, record)
    assert audit_baseline(baseline, profile_version="3")["relationships"] == 5
    if hide_parent:
        with pytest.raises(
            AssertionError, match="reverse hierarchy note materialization"
        ):
            check_api_vault(baseline, vault, profile_version="3")
    else:
        assert (
            check_api_vault(baseline, vault, profile_version="3")["relationships"] == 5
        )
