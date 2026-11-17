"""Literal per-occurrence rendering preserves display and exact link semantics."""

import pytest

from brz2obsidian.contracts import ExactContent
from brz2obsidian.obsidian import interpret_link_target, interpret_links
from tests.reconciliation.test_attachments import target_for_links


@pytest.mark.parametrize(
    "raw",
    (
        b"![](C:\\Imported\\image.webp#$width=65p$)",
        b"![](<d:/Imported images/100%literal.webp#^opaque[fragment]>)",
    ),
)
def test_format8_preserves_literal_external_windows_destination(raw):
    document = interpret_links(
        ExactContent(data=raw),
        document_id="owner",
        source_path="Notes/note.md",
        path_mode="vault",
        targets=(),
        target_facts=(),
        inventory="complete",
        output_format=8,
    )
    assert document.status == "supported" and not document.issues
    (occurrence,) = document.occurrences
    assert occurrence.raw == document.content.data == raw
    assert occurrence.query is None
    assert occurrence.meaning.status == "external"
    assert occurrence.meaning.target_id is None
    assert occurrence.meaning.path is None and occurrence.meaning.fragment is None


@pytest.mark.parametrize(
    "raw, output_format",
    (
        (b"![](C:\\Imported\\image.webp)", 7),
        (b"![](C:relative.webp)", 8),
        (b"[[C:\\Imported\\image.webp]]", 8),
        (b"![](C%3A%5CImported%5Cimage.webp)", 8),
        (b"![](C:\\Imported images\\image.webp)", 8),
        (b"![](<C:\\Imported\\bad\x00image.webp>)", 8),
    ),
)
def test_external_windows_support_preserves_existing_path_refusals(raw, output_format):
    document = interpret_links(
        ExactContent(data=raw),
        document_id="owner",
        source_path="Notes/note.md",
        path_mode="vault",
        targets=(),
        target_facts=(),
        inventory="complete",
        output_format=output_format,
    )
    assert document.status == "unsupported"
    assert all(o.meaning.status != "external" for o in document.occurrences)


def test_format8_interprets_rendered_relative_image_and_vault_wiki_together():
    image = target_for_links("image", "Attachments/id/É image.webp", kind="resource")
    note = target_for_links("note", "Notes/Other.md")
    states = tuple(
        interpret_link_target(
            ExactContent(data=b"content\n"),
            target_id=target.target_id,
            existence="present",
            memberships=(),
        )
        for target in (image, note)
    )
    raw = "É ![](../Attachments/id/%C3%89%20image.webp) [[Notes/Other.md]]\n".encode()
    parsed = interpret_links(
        ExactContent(data=raw),
        document_id="owner",
        source_path="Notes/note.md",
        path_mode="vault",
        targets=(image, note),
        target_facts=states,
        inventory="complete",
        output_format=8,
    )
    assert parsed.status == "supported" and parsed.content.data == raw
    image_link, wiki_link = parsed.occurrences
    assert (
        image_link.query.value,
        image_link.meaning.status,
        image_link.meaning.target_id,
    ) == (
        "Attachments/id/É image.webp",
        "resolved",
        "image",
    )
    assert (
        raw[image_link.span.start : image_link.span.end]
        == b"![](../Attachments/id/%C3%89%20image.webp)"
    )
    assert (
        raw[image_link.destination_span.start : image_link.destination_span.end]
        == b"../Attachments/id/%C3%89%20image.webp"
    )
    assert (wiki_link.query.value, wiki_link.meaning.target_id) == (
        "Notes/Other.md",
        "note",
    )


def test_unchanged_format8_relative_image_keeps_its_exact_destination():
    from brz2obsidian.obsidian import render_link_replacement

    target = target_for_links("image", "Attachments/id/image.webp", kind="resource")
    state = interpret_link_target(
        ExactContent(data=b"image"),
        target_id="image",
        existence="present",
        memberships=(),
    )
    raw = b"![](../Attachments/id/image.webp)"
    document = interpret_links(
        ExactContent(data=raw),
        document_id="owner",
        source_path="Notes/note.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
        output_format=8,
    )
    occurrence = document.occurrences[0]
    assert occurrence.meaning.status == "resolved"
    assert (
        render_link_replacement(
            document,
            occurrence.occurrence_id,
            occurrence.meaning,
            targets=(target,),
            target_facts=(state,),
        )
        == raw
    )


def test_format8_relative_image_keeps_uri_when_target_bytes_change():
    from brz2obsidian.obsidian import render_link_replacement

    target = target_for_links("image", "Attachments/id/image.webp", kind="resource")
    old, new = (
        interpret_link_target(
            ExactContent(data=content),
            target_id="image",
            existence="present",
            memberships=(),
        )
        for content in (b"old image", b"new image")
    )
    raw = b"![](../Attachments/id/image.webp)"
    options = {
        "document_id": "owner",
        "source_path": "Notes/note.md",
        "path_mode": "vault",
        "targets": (target,),
        "inventory": "complete",
        "output_format": 8,
    }
    document = interpret_links(ExactContent(data=raw), target_facts=(old,), **options)
    selected = (
        interpret_links(ExactContent(data=raw), target_facts=(new,), **options)
        .occurrences[0]
        .meaning
    )
    occurrence = document.occurrences[0]
    assert occurrence.meaning.status == selected.status == "resolved"
    assert occurrence.meaning.target_version != selected.target_version
    assert (
        render_link_replacement(
            document,
            occurrence.occurrence_id,
            selected,
            targets=(target,),
            target_facts=(new,),
        )
        == raw
    )
    with pytest.raises(ValueError):
        render_link_replacement(
            document,
            occurrence.occurrence_id,
            occurrence.meaning,
            targets=(target,),
            target_facts=(new,),
        )


def test_changed_format8_relative_image_keeps_relative_uri_and_other_bytes():
    from brz2obsidian.obsidian import render_link_replacement

    targets = (
        target_for_links("old", "Attachments/id/image.webp", kind="resource"),
        target_for_links("new", "Attachments/id/new asset.webp", kind="resource"),
        target_for_links("note", "Notes/Other.md"),
        target_for_links("local", "Notes/local.webp", kind="resource"),
    )
    states = tuple(
        interpret_link_target(
            ExactContent(data=b"content"),
            target_id=target.target_id,
            existence="present",
            memberships=(),
        )
        for target in targets
    )
    options = {
        "document_id": "owner",
        "source_path": "Notes/note.md",
        "path_mode": "vault",
        "targets": targets,
        "target_facts": states,
        "inventory": "complete",
        "output_format": 8,
    }
    raw = "É ![](../Attachments/id/image.webp) [[Notes/Other.md]]\n".encode()
    document = interpret_links(ExactContent(data=raw), **options)
    occurrence = document.occurrences[0]
    selected = (
        interpret_links(
            ExactContent(data=b"![](../Attachments/id/new%20asset.webp)"), **options
        )
        .occurrences[0]
        .meaning
    )
    assert selected.status == "resolved" and selected.target_id == "new"
    replacement = render_link_replacement(
        document,
        occurrence.occurrence_id,
        selected,
        targets=targets,
        target_facts=states,
    )
    assert replacement == b"![](../Attachments/id/new%20asset.webp)"
    changed = raw[: occurrence.span.start] + replacement + raw[occurrence.span.end :]
    assert (
        changed
        == "É ![](../Attachments/id/new%20asset.webp) [[Notes/Other.md]]\n".encode()
    )
    parsed = interpret_links(ExactContent(data=changed), **options)
    image, wiki = parsed.occurrences
    assert image.meaning == selected
    assert changed[image.destination_span.start : image.destination_span.end] == (
        b"../Attachments/id/new%20asset.webp"
    )
    assert wiki.meaning.target_id == "note" and wiki.query.value == "Notes/Other.md"
    local = (
        interpret_links(ExactContent(data=b"![](./local.webp)"), **options)
        .occurrences[0]
        .meaning
    )
    assert local.status == "resolved" and local.target_id == "local"
    assert (
        render_link_replacement(
            document,
            occurrence.occurrence_id,
            local,
            targets=targets,
            target_facts=states,
        )
        == b"![](./local.webp)"
    )


def test_format8_relative_image_retains_path_and_target_guards():
    def parse(raw, output_format=8):
        return interpret_links(
            ExactContent(data=raw),
            document_id="owner",
            source_path="Notes/note.md",
            path_mode="vault",
            targets=(),
            target_facts=(),
            inventory="complete",
            output_format=output_format,
        )

    assert parse(b"![](../Attachments/id/image.webp)", 7).issues == (
        "path_unsupported",
    )
    assert parse(b"![](../../outside.webp)").issues == ("path_unsupported",)
    assert parse(b"![](../Attachments/%FF.webp)").issues == ("path_unsupported",)
    unknown = parse(b"![](../Attachments/id/missing.webp)")
    assert unknown.status == "supported"
    assert unknown.occurrences[0].meaning.status != "resolved"
    wiki = parse(b"[[../Attachments/id/image.webp]]")
    assert wiki.issues == ("path_unsupported",)


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


def test_link_replacement_requires_the_bound_resolved_occurrence():
    from brz2obsidian.obsidian import render_link_replacement

    target = target_for_links("asset", "Assets/data.bin", kind="resource")
    state = interpret_link_target(
        ExactContent(data=b"# Intro\n"),
        target_id="asset",
        existence="present",
        memberships=(),
    )
    raw = b"[[Assets/data.bin#Intro|Exact alias]]"
    document = interpret_links(
        ExactContent(data=raw),
        document_id="owner",
        source_path="Owner.md",
        path_mode="vault",
        targets=(target,),
        target_facts=(state,),
        inventory="complete",
    )
    occurrence = document.occurrences[0]
    assert occurrence.meaning.status == "resolved"
    assert (
        render_link_replacement(
            document,
            occurrence.occurrence_id,
            occurrence.meaning,
            targets=(target,),
            target_facts=(state,),
        )
        == raw
    )
    with pytest.raises(ValueError, match="bound resolved"):
        render_link_replacement(
            document,
            "unknown-occurrence",
            occurrence.meaning,
            targets=(target,),
            target_facts=(state,),
        )
    with pytest.raises(ValueError, match="bound resolved"):
        render_link_replacement(
            document,
            occurrence.occurrence_id,
            occurrence.meaning.model_copy(update={"status": "unknown"}),
            targets=(target,),
            target_facts=(state,),
        )
