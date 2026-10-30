"""Literal per-occurrence rendering preserves display and exact link semantics."""

import pytest

from brz2obsidian.contracts import ExactContent
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.reconciliation.test_attachments import target_for_links


@pytest.mark.parametrize(
    ("old", "expected", "path", "mode"),
    (
        (
            "![[Assets/data.bin#Intro|Alias]]",
            "![[Assets/data (incoming-ba7816bf).bin#Intro|Alias]]",
            "Assets/data (incoming-ba7816bf).bin",
            "vault",
        ),
        (
            "[[Assets/data.bin]]",
            "[[Assets/data (incoming-ba7816bf).bin|Assets/data.bin]]",
            "Assets/data (incoming-ba7816bf).bin",
            "vault",
        ),
        (
            "![É label](<../Assets/data.bin#Intro>)",
            "![É label](<../Assets/%C3%89%20data%20%28incoming-ba7816bf%29.bin#Intro>)",
            "Assets/É data (incoming-ba7816bf).bin",
            "relative",
        ),
    ),
)
def test_link_replacement_preserves_alias_embed_fragment_and_byte_geometry(
    old, expected, path, mode
):
    from brz2obsidian.obsidian import render_link_replacement

    before = target_for_links("old", "Assets/data.bin", kind="resource")
    after = target_for_links("new", path, kind="resource")
    states = tuple(
        interpret_link_target(
            ExactContent(data=b"# Intro\n"),
            target_id=target.target_id,
            existence="present",
            memberships=(),
        )
        for target in (before, after)
    )
    prefix, suffix = "É exact before ".encode(), b" after `[[Assets/data.bin]]`\r\n"
    document = interpret_links(
        ExactContent(data=prefix + old.encode() + suffix),
        document_id="owner",
        source_path="Notes/Owner.md",
        path_mode=mode,
        targets=(before, after),
        target_facts=states,
        inventory="complete",
    )
    wanted = interpret_links(
        ExactContent(data=expected.encode()),
        document_id="wanted",
        source_path="Notes/Owner.md",
        path_mode=mode,
        targets=(before, after),
        target_facts=states,
        inventory="complete",
    )
    assert len(document.occurrences) == len(wanted.occurrences) == 1
    selected = wanted.occurrences[0].meaning
    assert selected.status == "resolved" and selected.target_id == "new"
    replacement = render_link_replacement(
        document,
        document.occurrences[0].occurrence_id,
        selected,
        targets=(before, after),
        target_facts=states,
    )
    assert replacement == expected.encode()
    occurrence = document.occurrences[0]
    changed = (
        document.content.data[: occurrence.span.start]
        + replacement
        + document.content.data[occurrence.span.end :]
    )
    assert changed == prefix + expected.encode() + suffix


def test_link_replacement_refuses_a_fragment_absent_from_the_selected_payload():
    from brz2obsidian.obsidian import render_link_replacement

    targets = (
        target_for_links("old", "Assets/data.bin", kind="resource"),
        target_for_links("new", "Assets/new.bin", kind="resource"),
    )
    states = tuple(
        interpret_link_target(
            ExactContent(data=raw),
            target_id=target.target_id,
            existence="present",
            memberships=(),
        )
        for target, raw in zip(targets, (b"# Intro\n", b"# Other\n"), strict=True)
    )
    document = interpret_links(
        ExactContent(data=b"[[Assets/data.bin#Intro|Kept]]"),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=targets,
        target_facts=states,
        inventory="complete",
    )
    unavailable = (
        interpret_links(
            ExactContent(data=b"[[Assets/new.bin#Intro|Kept]]"),
            document_id="new",
            source_path="Owner.md",
            path_mode="vault",
            targets=targets,
            target_facts=states,
            inventory="complete",
        )
        .occurrences[0]
        .meaning
    )
    assert unavailable.status == "fragment_missing"
    with pytest.raises(ValueError):
        render_link_replacement(
            document,
            document.occurrences[0].occurrence_id,
            unavailable.model_copy(update={"status": "resolved"}),
            targets=targets,
            target_facts=states,
        )


def test_base_named_view_fragments_bind_exact_yaml_names():
    raw = (
        "# É context\nviews:\n  - type: table\n    name: Members\n"
        "  - type: cards\n    name: 'Gallery'\n"
    ).encode()
    target = target_for_links("base", "Templates/Bases/Native.base")
    state = interpret_link_target(
        ExactContent(data=raw),
        target_id="base",
        existence="present",
        memberships=(),
        source_path="Templates/Bases/Native.base",
    )
    assert [
        (a.fragment.kind, a.fragment.value, a.raw_parts) for a in state.anchors
    ] == [
        ("heading", "Members", (b"Members",)),
        ("heading", "Gallery", (b"Gallery",)),
    ]
    assert [(a.spans[0].start, a.spans[0].end) for a in state.anchors] == [
        (46, 53),
        (81, 88),
    ]
    document = interpret_links(
        ExactContent(
            data=b"![[Templates/Bases/Native.base#Members]]\n"
            b"![[Templates/Bases/Native.base#Gallery]]\n"
        ),
        document_id="category",
        source_path="Categories/Native.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )
    assert [
        (o.meaning.status, o.meaning.path, o.meaning.fragment.value)
        for o in document.occurrences
    ] == [
        ("resolved", "Templates/Bases/Native.base", "Members"),
        ("resolved", "Templates/Bases/Native.base", "Gallery"),
    ]


@pytest.mark.parametrize(
    ("path", "raw", "expected"),
    (
        (
            "Native.base",
            b"views:\n  - type: table\n    name: Other\n",
            "fragment_missing",
        ),
        (
            "Native.base",
            b"views:\n  - name: Members\n  - name: Members\n",
            "fragment_ambiguous",
        ),
        ("Native.base", b"views: [\n", "unknown"),
        ("Native.base", b"views:\n  - name: 42\n", "unknown"),
        ("Native.base", b"views:\n  - name: Members\n    name: Other\n", "unknown"),
        ("Native.base", b'views:\n  - name: "Memb\\u0065rs"\n', "unknown"),
        ("Native.md", b"views:\n  - name: Members\n", "fragment_missing"),
    ),
)
def test_base_named_view_fragments_refuse_unestablished_destinations(
    path, raw, expected
):
    target = target_for_links("base", path)
    state = interpret_link_target(
        ExactContent(data=raw),
        target_id="base",
        existence="present",
        memberships=(),
        source_path=path,
    )
    document = interpret_links(
        ExactContent(data=("![[" + path + "#Members]]").encode()),
        document_id="category",
        source_path="Categories/Native.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )
    assert document.occurrences[0].meaning.status == expected
