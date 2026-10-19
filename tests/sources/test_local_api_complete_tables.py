"""Qualified complete tables through the public source and frozen-capture seams."""

import hashlib
import json
import tempfile
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

from brz2obsidian.contracts import MigrationRefused, SourceFinding, TextAdaptation
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.sources.test_local_api_table_colors import DECLARATION, note_api
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import IMAGE, PNG, attachment

FACTS = json.loads(
    (
        Path(__file__).parents[1] / "fixtures/local_api_profile/complete-tables.json"
    ).read_text(encoding="utf-8")
)


def test_plain_tables_keep_all_rows_cells_breaks_and_exact_evidence():
    cases = FACTS["cases"][:7]
    original = "\n".join(case["raw"] for case in cases)
    expected = "\n".join(case["expected"] for case in cases)
    with api_server(note_api(original)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            document = session.snapshot.documents[0]
            assert document.text == expected
            assert "<code>print a\\|b</code>" in MarkdownIt("commonmark").enable(
                "table"
            ).render(document.text)
            assert len(session.snapshot.findings) == 7
            edit = document.text_adaptations[0]
            assert (edit.start, edit.end, edit.before, edit.after) == (
                0,
                15,
                "|Field|Meaning|",
                "| | |\n|---|---|\n|Field|Meaning|",
            )
            assert {change.source_digest for change in document.text_adaptations} == {
                hashlib.sha256(original.encode()).hexdigest()
            }
            rebound = original
            for change in reversed(document.text_adaptations):
                assert original[change.start : change.end] == change.before
                assert (
                    document.text[change.adapted_start : change.adapted_end]
                    == change.after
                )
                rebound = rebound[: change.start] + change.after + rebound[change.end :]
            assert rebound == expected
            with session.open_payload(document.original_asset_id) as stream:
                assert stream.read() == original.encode()
            session.verify_consistency()


def test_frozen_tables_match_complete_current_or_prior_text_and_findings(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    original = "|Field|Meaning|\n|source|Select packets.|\n\n|One|Two|\n|1|2|3|\n"
    with api_server(note_api(original)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as live:
            current = live.snapshot
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
    prior_document = current.documents[0].model_copy(
        update={
            "text": original,
            "text_digest": hashlib.sha256(original.encode()).hexdigest(),
            "text_adaptations": (),
            "references": (),
        }
    )
    prior = current.model_copy(
        update={
            "identity": current.identity.model_copy(
                update={"source_sha256": "", "snapshot_digest": ""}
            ),
            "documents": (prior_document,),
            "findings": (),
        }
    )
    for expected in (current, prior):
        frozen = LocalApiSession(
            source=source,
            snapshot=expected,
            audit=audit,
            payloads={prior_document.original_asset_id: original.encode()},
        )
        try:
            assert frozen.snapshot.documents == expected.documents
            assert frozen.snapshot.findings == expected.findings
            frozen.verify_consistency()
        finally:
            frozen.close()
    current_document = current.documents[0]
    invented = current_document.text.replace("Select packets.", "Invented data.")
    for changed in (
        current.model_copy(update={"findings": ()}),
        prior.model_copy(update={"findings": current.findings}),
        current.model_copy(
            update={
                "documents": (
                    current_document.model_copy(
                        update={
                            "text": invented,
                            "text_digest": hashlib.sha256(
                                invented.encode()
                            ).hexdigest(),
                        }
                    ),
                )
            }
        ),
        prior.model_copy(
            update={
                "documents": (
                    prior_document.model_copy(
                        update={"text_adaptations": current_document.text_adaptations}
                    ),
                )
            }
        ),
    ):
        with pytest.raises(MigrationRefused):
            LocalApiSession(
                source=source,
                snapshot=changed,
                audit=audit,
                payloads={prior_document.original_asset_id: original.encode()},
            )
    with pytest.raises(MigrationRefused):
        LocalApiSession(
            source=source,
            snapshot=current,
            audit=audit,
            payloads={
                prior_document.original_asset_id: original.replace(
                    "Select packets.", "Invented data."
                ).encode()
            },
        )


def test_plain_table_boundaries_preserve_literals_prose_and_malformed_rows():
    source_table = "|A|B|\n|1|2|\n"
    marker_table = (
        "|Markers|Value|\n|Code|`{nl}`|\n|Comment|<!-- {nl} -->|\n|Escaped|\\{nl}|\n"
    )
    protected = r"""```text
|F|G|
|3|4|
```

    |I|J|
    |5|6|

`literal start
|K|L|
|7|8|
literal end`

<!--
|M|N|
|9|10|
-->

\|Escaped|example|
\|a|b|

Ordinary a | b pipeline.
[Docs | Reference](https://example.invalid/reference)

# Heading | Detail

> |Q|R|
> |1|2|

- |S|T|
  |1|2|

|Known|Markdown|
|:---|---:|
|x|y|
|only|

|Unequal|Columns|
|1|2|3|

|Broken|Tail|
|1|2\|

"""
    original = (
        "Intro sentence.\n"
        + source_table
        + "Following prose.\n\n"
        + protected
        + marker_table
    )
    expected = (
        "Intro sentence.\n\n| | |\n|---|---|\n|A|B|\n|1|2|\n\nFollowing prose.\n\n"
        + protected
        + "| | |\n|---|---|\n"
        + marker_table
    )
    with api_server(note_api(original)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert session.snapshot.documents[0].text == expected
            changes = [
                json.loads(f.observed_json)["change"] for f in session.snapshot.findings
            ]
            assert (
                sum("Malformed or ambiguous table" in change for change in changes) == 2
            )
            assert changes.count(FACTS["neutral_header_loss"]) == 2
            session.verify_consistency()


def test_image_adjacent_plain_table_keeps_reference_spans_and_cell_ownership():
    image = f".data/md-images/{IMAGE}.png"
    target = "brain://MzMzMzMzM0ODMzMzMzMzMw/Alone"
    original = f"![First]({image})![Second]({image})\n||\n|1{{nl}}2|`first|second`{{nl}}[Alone]({target})|\n"
    expected = f"![First]({image})![Second]({image})\n\n| | |\n|---|---|\n|1<br>2|<code>first&#124;second</code><br>[Alone]({target})|\n"
    api = note_api(original)
    api.attachments[IMAGE] = attachment(
        IMAGE, HOME, 12, IMAGE + ".png", length=len(PNG)
    )
    api.payloads[IMAGE] = PNG
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            document = session.snapshot.documents[0]
            assert document.text == expected
            assert [(r.kind, r.target, r.table_cell) for r in document.references] == [
                ("image", IMAGE, False),
                ("image", IMAGE, False),
                ("item", ALONE, True),
            ]
            reference = document.references[-1]
            assert (
                document.text[reference.start : reference.end] == f"[Alone]({target})"
            )
            assert reference.source_target == target
            for image_reference in document.references[:2]:
                assert (
                    document.text[
                        image_reference.destination_start : image_reference.destination_end
                    ]
                    == image
                )
            assert (
                reference.document_digest
                == hashlib.sha256(expected.encode()).hexdigest()
            )
            session.verify_consistency()


def test_styling_never_promotes_data_and_combined_styles_become_plain_tables():
    width = ':(table="column-widths:-1,0,0;justification:default"):'
    combined = (
        ':(table="column-widths:-1,0,0;justification:default;'
        + DECLARATION.removeprefix(':(table="')
    )
    original = (
        "|**Before**|Choose early.|"
        + width
        + "\n|**After**|Choose later.|\n\n"
        + "|Filter|Meaning|"
        + combined
        + "\n|`ip`|Packets.|\n\n"
        + "|||"
        + width
        + "\n|1{nl}2|first{nl}second|\n\n"
        + "|||\n|a|b|\n\n"
        + '|Record|Value|:(table="new-key:future-style;columns:unexpected;z:first"):\n|a|b|\n\n'
        + '||:(table="unfamiliar:ignored"):\n|1{nl}2|first{nl}second|\n\n'
        + '|A|B|:(table="opaque:value"):\n|---|---|\n|only|\n\n'
        + '|A|B|:(table="label:literal :(table=marker"):\n|1|2|\n'
    )
    expected = (
        "| | |\n|---|---|\n|**Before**|Choose early.|\n|**After**|Choose later.|\n\n"
        "| | |\n|---|---|\n|Filter|Meaning|\n|`ip`|Packets.|\n\n"
        "| | |\n|---|---|\n|1<br>2|first<br>second|\n\n"
        "| | |\n|---|---|\n|a|b|\n\n"
        "| | |\n|---|---|\n|Record|Value|\n|a|b|\n\n"
        "| | |\n|---|---|\n|1<br>2|first<br>second|\n\n"
        "|A|B|\n|---|---|\n|only|\n\n"
        "| | |\n|---|---|\n|A|B|\n|1|2|\n"
    )
    with api_server(note_api(original)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert session.snapshot.documents[0].text == expected
            assert len(session.snapshot.findings) == 8
            changes = [
                json.loads(f.observed_json)["change"] for f in session.snapshot.findings
            ]
            assert not any("Malformed" in change for change in changes)
            with session.open_payload(
                session.snapshot.documents[0].original_asset_id
            ) as stream:
                assert stream.read() == original.encode()
            session.verify_consistency()


def test_only_qualified_table_cell_code_links_gain_valid_plain_markdown():
    near_misses = (
        "|`curl -I [https://example.invalid`](https://other.invalid)|Different target|\n"
        "|`` `curl -I [https://example.invalid`](https://example.invalid) ``|Literal code|\n"
        "|[`curl -I https://example.invalid`](https://example.invalid)|Already valid|\n"
    )
    prose = "`curl -I [https://example.invalid`](https://example.invalid)\n\n"
    literal = "```text\n|Literal|Example|\n|`curl -I [https://example.invalid`](https://example.invalid)|Keep|\n```\n"
    original = (
        prose + "|Command|Meaning|\n"
        "|`curl -I [https://example.invalid`](https://example.invalid)|Headers only|\n"
        "|`curl -i [https://example.invalid/path`](https://example.invalid/path)|Include headers|\n"
        + near_misses
        + "\n"
        + literal
    )
    expected = (
        prose + "| | |\n|---|---|\n|Command|Meaning|\n"
        "|[`curl -I https://example.invalid`](https://example.invalid)|Headers only|\n"
        "|[`curl -i https://example.invalid/path`](https://example.invalid/path)|Include headers|\n"
        + near_misses
        + "\n"
        + literal
    )
    with api_server(note_api(original)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            document = session.snapshot.documents[0]
            assert document.text == expected
            rendered = MarkdownIt("commonmark").enable("table").render(document.text)
            assert (
                '<a href="https://example.invalid"><code>curl -I https://example.invalid</code></a>'
                in rendered
            )
            assert (
                document.text_adaptations[-1].source_digest
                == hashlib.sha256(original.encode()).hexdigest()
            )
            with session.open_payload(document.original_asset_id) as stream:
                assert stream.read() == original.encode()
            session.verify_consistency()


def test_exact_52ca_capture_keeps_its_whole_table_interpretation(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    width = ':(table="column-widths:-1,0,0;justification:default"):'
    plain = "|P|Q|\n|a|b|\n"
    styled = "|Capture|Description|" + width + "\n|Display|Later|\n"
    link = "`curl -I [https://example.invalid`](https://example.invalid)"
    linked = "[`curl -I https://example.invalid`](https://example.invalid)"
    code = "|Command|Use|\n|" + link + "|Headers|\n"
    combined = width.removesuffix('"):') + ';foreground-color:#ffffff"):'
    malformed = "|Legacy|Style|" + combined + "\n|Still|Literal|\n"
    original = plain + "\n" + styled + "\n" + code + "\n" + malformed
    prior_text = (
        "|||\n|---|---|\n|P|Q|\n|a|b|\n\n"
        "|Capture|Description|\n|---|---|\n|Display|Later|\n\n"
        "|||\n|---|---|\n|Command|Use|\n|" + link + "|Headers|\n"
    )
    prior_text += "\n" + malformed
    with api_server(note_api(original)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as live:
            current = live.snapshot
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
    source_digest = hashlib.sha256(original.encode()).hexdigest()
    replacements = [
        (0, "|P|Q|", "|||\n|---|---|\n|P|Q|"),
        (
            len(plain) + 1,
            "|Capture|Description|" + width,
            "|Capture|Description|\n|---|---|",
        ),
        (
            len(plain) + len(styled) + 2,
            "|Command|Use|",
            "|||\n|---|---|\n|Command|Use|",
        ),
    ]
    edits, delta = [], 0
    for start, before, after in replacements:
        assert original[start : start + len(before)] == before
        edits.append(
            TextAdaptation(
                kind="markdown_insert",
                start=start,
                end=start + len(before),
                before=before,
                after=after,
                adapted_start=start + delta,
                adapted_end=start + delta + len(after),
                source_digest=source_digest,
            )
        )
        delta += len(after) - len(before)
    document = current.documents[0]
    findings = tuple(
        SourceFinding(
            kind="formatting_loss",
            rule_id="local-api.note-formatting.v1",
            affected=tuple(sorted((document.owner, document.key))),
            evidence=document.evidence,
            observed_json=json.dumps(
                {"feature": "table", "declaration": declaration, "change": change},
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        for declaration, change in (
            ("|P|Q|", FACTS["neutral_header_loss"]),
            (
                width,
                "Column widths and justification become native responsive table layout; edit the table in Obsidian to adjust its presentation.",
            ),
            ("|Command|Use|", FACTS["neutral_header_loss"]),
            (
                combined,
                "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with a matching header separator.",
            ),
        )
    )
    previous_document = document.model_copy(
        update={
            "text": prior_text,
            "text_digest": hashlib.sha256(prior_text.encode()).hexdigest(),
            "text_adaptations": tuple(edits),
            "references": (),
        }
    )
    previous = current.model_copy(
        update={
            "identity": current.identity.model_copy(
                update={"source_sha256": "", "snapshot_digest": ""}
            ),
            "documents": (previous_document,),
            "findings": findings,
        }
    )
    frozen = LocalApiSession(
        source=source,
        snapshot=previous,
        audit=audit,
        payloads={document.original_asset_id: original.encode()},
    )
    try:
        assert frozen.snapshot.documents == (previous_document,)
        assert sorted(
            frozen.snapshot.findings, key=lambda f: f.observed_json
        ) == sorted(findings, key=lambda f: f.observed_json)
        frozen.verify_consistency()
    finally:
        frozen.close()
    start = original.index(link)
    mixed_edit = TextAdaptation(
        kind="markdown_insert",
        start=start,
        end=start + len(link),
        before=link,
        after=linked,
        adapted_start=start + delta,
        adapted_end=start + delta + len(linked),
        source_digest=source_digest,
    )
    mixed_text = prior_text.replace(link, linked)
    mixed_document = previous_document.model_copy(
        update={
            "text": mixed_text,
            "text_digest": hashlib.sha256(mixed_text.encode()).hexdigest(),
            "text_adaptations": (*edits, mixed_edit),
        }
    )
    with pytest.raises(MigrationRefused):
        LocalApiSession(
            source=source,
            snapshot=previous.model_copy(update={"documents": (mixed_document,)}),
            audit=audit,
            payloads={document.original_asset_id: original.encode()},
        )


def test_spaced_neutral_headers_keep_exact_compact_capture_compatibility(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    original = '|First|Meaning|\n|one|Keep.|\n\n||\n|2|Second|\n\n|||:(table="unfamiliar:value"):\n|3|Third|\n\n|||\n|---|---|\n|4|Fourth|\n\n| | |:(table="existing:spacing"):\n|5|Fifth|\n'
    expected = "| | |\n|---|---|\n|First|Meaning|\n|one|Keep.|\n\n| | |\n|---|---|\n|2|Second|\n\n| | |\n|---|---|\n|3|Third|\n\n| | |\n|---|---|\n|4|Fourth|\n\n| | |\n|---|---|\n|5|Fifth|\n"
    compact = "|||\n|---|---|\n|First|Meaning|\n|one|Keep.|\n\n|||\n|---|---|\n|2|Second|\n\n|||\n|---|---|\n|3|Third|\n\n|||\n|---|---|\n|4|Fourth|\n\n| | |\n|---|---|\n|5|Fifth|\n"
    with api_server(note_api(original)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as live:
            current = live.snapshot
            document = current.documents[0]
            assert document.text == expected
            assert MarkdownIt("commonmark").enable("table").render(
                expected
            ) == MarkdownIt("commonmark").enable("table").render(compact)
            with live.open_payload(document.original_asset_id) as stream:
                assert stream.read() == original.encode()
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
    prior_edits, delta = [], 0
    for change in document.text_adaptations:
        after = (
            change.after
            if change.before.startswith("| | |")
            else change.after.replace("| | |", "|||")
        )
        if after == change.before:
            continue
        prior_edits.append(
            change.model_copy(
                update={
                    "after": after,
                    "adapted_start": change.start + delta,
                    "adapted_end": change.start + delta + len(after),
                }
            )
        )
        delta += len(after) - len(change.before)
    prior_document = document.model_copy(
        update={
            "text": compact,
            "text_digest": hashlib.sha256(compact.encode()).hexdigest(),
            "text_adaptations": tuple(prior_edits),
        }
    )
    prior = current.model_copy(
        update={
            "identity": current.identity.model_copy(
                update={"source_sha256": "", "snapshot_digest": ""}
            ),
            "documents": (prior_document,),
        }
    )
    frozen = LocalApiSession(
        source=source,
        snapshot=prior,
        audit=audit,
        payloads={document.original_asset_id: original.encode()},
    )
    try:
        assert frozen.snapshot.documents == (prior_document,)
        assert frozen.snapshot.findings == current.findings
        frozen.verify_consistency()
    finally:
        frozen.close()
    mixed_text = compact.replace("|||", "| | |", 1)
    mixed_edits, delta = [], 0
    for index, change in enumerate(prior_edits):
        after = change.after.replace("|||", "| | |", 1) if index == 0 else change.after
        mixed_edits.append(
            change.model_copy(
                update={
                    "after": after,
                    "adapted_start": change.start + delta,
                    "adapted_end": change.start + delta + len(after),
                }
            )
        )
        delta += len(after) - len(change.before)
    mixed = prior_document.model_copy(
        update={
            "text": mixed_text,
            "text_digest": hashlib.sha256(mixed_text.encode()).hexdigest(),
            "text_adaptations": tuple(mixed_edits),
        }
    )
    with pytest.raises(MigrationRefused):
        LocalApiSession(
            source=source,
            snapshot=prior.model_copy(update={"documents": (mixed,)}),
            audit=audit,
            payloads={document.original_asset_id: original.encode()},
        )
