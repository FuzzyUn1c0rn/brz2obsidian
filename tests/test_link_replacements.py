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
