"""Qualified complete tables through the public source and frozen-capture seams."""

import hashlib
import json
import tempfile
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.sources.test_local_api_table_colors import note_api
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
                "|||\n|---|---|\n|Field|Meaning|",
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
        "Intro sentence.\n\n|||\n|---|---|\n|A|B|\n|1|2|\n\nFollowing prose.\n\n"
        + protected
        + "|||\n|---|---|\n"
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
    expected = f"![First]({image})![Second]({image})\n\n|||\n|---|---|\n|1<br>2|<code>first&#124;second</code><br>[Alone]({target})|\n"
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
