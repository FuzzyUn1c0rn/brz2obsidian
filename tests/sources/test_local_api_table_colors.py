"""Qualified color-only tables through public local API source and workflows."""

import hashlib
import json
import tempfile
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import BRAIN, KEY, api_server
from tests.support.local_api_payloads import NOTE, PayloadApi
from tests.support.notes import note_body

FACTS = json.loads(
    (
        Path(__file__).parents[1] / "fixtures/local_api_profile/table-colors.json"
    ).read_text()
)
DECLARATION = FACTS["declaration"]
TABLE = FACTS["header"] + DECLARATION + "\n" + "\n".join(FACTS["rows"]) + "\n"
EXPECTED = FACTS["expected_header"] + "\n" + "\n".join(FACTS["rows"]) + "\n"


def note_api(text):
    api = PayloadApi()
    raw = text.encode("utf-8")
    api.payloads[NOTE] = raw
    api.attachments[NOTE]["dataLength"] = len(raw)
    return api


@pytest.mark.parametrize("profile", ["1", "2", "3"])
def test_color_table_live_and_frozen_keep_editable_cells_and_exact_evidence(
    tmp_path, monkeypatch, profile
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with api_server(note_api(TABLE)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=profile,
        )
        with module.open(LocalApiSourceRef(BRAIN)) as live:
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            snapshot = live.snapshot
            document = snapshot.documents[0]
            assert document.text == EXPECTED
            assert len(document.text_adaptations) == 1
            edit = document.text_adaptations[0]
            assert (edit.start, edit.before, edit.after) == (
                0,
                FACTS["header"] + DECLARATION,
                FACTS["expected_header"],
            )
            assert (edit.end, edit.adapted_start, edit.adapted_end) == (356, 0, 30)
            assert edit.source_digest == hashlib.sha256(TABLE.encode()).hexdigest()
            finding = snapshot.findings[0]
            assert finding.kind == "formatting_loss"
            assert json.loads(finding.observed_json) == {
                "feature": "table",
                "declaration": DECLARATION,
                "change": FACTS["color_loss"],
            }
            with live.open_payload(NOTE) as stream:
                assert stream.read() == TABLE.encode()
            live.verify_consistency()
    frozen = LocalApiSession(
        source=source,
        snapshot=snapshot,
        audit=audit,
        payloads={NOTE: TABLE.encode()},
        profile_version=profile,
    )
    try:
        assert frozen.snapshot == snapshot
        frozen.verify_consistency()
    finally:
        frozen.close()


def test_prior_color_table_capture_keeps_its_complete_interpretation_and_rejects_tampering(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with api_server(note_api(TABLE)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as live:
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            current = live.snapshot
    previous_document = current.documents[0].model_copy(
        update={
            "text": TABLE,
            "text_digest": hashlib.sha256(TABLE.encode()).hexdigest(),
            "text_adaptations": (),
        }
    )
    previous_finding = current.findings[0].model_copy(
        update={
            "observed_json": json.dumps(
                {
                    "feature": "table",
                    "declaration": DECLARATION,
                    "change": "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with a matching header separator.",
                }
            )
        }
    )
    previous = current.model_copy(
        update={
            "identity": current.identity.model_copy(
                update={"source_sha256": "", "snapshot_digest": ""}
            ),
            "documents": (previous_document,),
            "findings": (previous_finding,),
        }
    )
    frozen = LocalApiSession(
        source=source,
        snapshot=previous,
        audit=audit,
        payloads={NOTE: TABLE.encode()},
    )
    try:
        assert frozen.snapshot.documents[0] == previous_document
        assert json.loads(frozen.snapshot.findings[0].observed_json) == json.loads(
            previous_finding.observed_json
        )
        frozen.verify_consistency()
    finally:
        frozen.close()
    invented = TABLE.replace("Show all IP packets.", "Invented cell.")
    invented_text = previous_document.model_copy(
        update={
            "text": invented,
            "text_digest": hashlib.sha256(invented.encode()).hexdigest(),
        }
    )
    mixed_adaptation = previous_document.model_copy(
        update={"text_adaptations": current.documents[0].text_adaptations}
    )
    for changed in (
        previous.model_copy(update={"documents": (invented_text,)}),
        previous.model_copy(update={"documents": (mixed_adaptation,)}),
        previous.model_copy(update={"findings": current.findings}),
    ):
        with pytest.raises(MigrationRefused):
            LocalApiSession(
                source=source,
                snapshot=changed,
                audit=audit,
                payloads={NOTE: TABLE.encode()},
            )


def test_color_table_closed_predicate_and_literal_ownership_keep_safe_fallbacks():
    plain = "|A|B|" + DECLARATION + "\n|1|2|\n"
    invalid_declarations = [
        DECLARATION.replace("foreground-color", "unknown-color", 1),
        DECLARATION.replace("foreground-color:#ff370c0b;", "", 1),
        DECLARATION.replace("background-color:", "foreground-color:", 1),
        DECLARATION.replace(
            "foreground-color:#ff370c0b;background-color:#fff9d3d2",
            "background-color:#fff9d3d2;foreground-color:#ff370c0b",
        ),
        DECLARATION.replace("#ff370c0b", "red"),
        DECLARATION.replace("#ff370c0b", "#ff370c0"),
        DECLARATION.replace('"):', ';"):'),
        DECLARATION.replace('table="', 'table="column-widths:-1,0,84;'),
        DECLARATION + DECLARATION,
    ]
    malformed = ["|A|B|" + d + "\n|1|2|\n" for d in invalid_declarations]
    malformed += ["|A|B|" + DECLARATION + "\n|1|2|3|\n", "|A|B|" + DECLARATION + "\n"]
    protected = [
        "```md\n" + plain + "```\n",
        "    " + plain.replace("\n|", "\n    |"),
        "`" + plain + "`\n",
        "<!--\n" + plain + "-->\n",
        "|A|B|\\" + DECLARATION + "\n|1|2|\n",
    ]
    existing = (
        "|**One**|Two|"
        + DECLARATION.replace("#ff", "#FF")
        + "\n|:---|---:|\n|a\\|b|`x|y`|\n"
    )
    text = "\n".join(malformed + protected + [existing])
    expected = "\n".join(
        malformed
        + protected
        + ["|**One**|Two|\n|:---|---:|\n|a\\|b|<code>x&#124;y</code>|\n"]
    )
    with api_server(note_api(text)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert session.snapshot.documents[0].text == expected
            changes = [
                json.loads(f.observed_json)["change"] for f in session.snapshot.findings
            ]
            assert len(changes) == len(malformed) + 1
            assert changes.count(FACTS["color_loss"]) == 1
            assert sum(
                "Malformed or ambiguous table retained" in c for c in changes
            ) == len(malformed)
            assert len(session.snapshot.documents[0].text_adaptations) == 2
            session.verify_consistency()


def test_workflow_publishes_editable_five_row_table_with_migration_evidence(tmp_path):
    destination = tmp_path / "vault"
    with api_server(note_api(TABLE)) as (_, address):
        result = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        ).convert(LocalApiSourceRef(BRAIN), destination)
    assert result.outcome == "warnings", result.issues
    assert len(result.issues) == 1 and result.issues[0].code == "formatting_loss"
    assert FACTS["color_loss"] in result.issues[0].message
    note = next(destination.glob("Home*.md")).read_text(encoding="utf-8")
    body = note_body(note)
    assert EXPECTED in body and DECLARATION not in body
    tokens = MarkdownIt("commonmark").enable("table").parse(body)
    assert sum(t.type == "table_open" for t in tokens) == 1
    assert sum(t.type == "tr_open" for t in tokens) == 6
    table = tokens[
        next(i for i, t in enumerate(tokens) if t.type == "table_open") : next(
            i for i, t in enumerate(tokens) if t.type == "table_close"
        )
    ]
    assert [t.content for t in table if t.type == "inline"] == [
        "Filter",
        "Description",
        "`ip`",
        "Show all IP packets.",
        "`ip.src == 192.0.2.1`",
        "Show packets from the example address.",
        "`tcp.port == 443`",
        "Show HTTPS port traffic.",
        "`ip.addr == 192.0.2.2`",
        "Show either endpoint.",
        "`udp.port == 53`",
        "DNS with an escaped | pipe.",
    ]
    assert (
        destination / "Attachments/22222222/Notes.md.original"
    ).read_bytes() == TABLE.encode()
    record = json.loads((destination / "migration-record.json").read_bytes())
    finding = next(t for t in record["asset_targets"] if t["source_findings"])[
        "source_findings"
    ][0]
    assert json.loads(finding["observed_json"])["declaration"] == DECLARATION
    adaptation = record["adaptations"][0]["text_edit"]
    assert adaptation["before"] == FACTS["header"] + DECLARATION
    assert adaptation["after"] == FACTS["expected_header"]
    assert adaptation["source_digest"] == hashlib.sha256(TABLE.encode()).hexdigest()
