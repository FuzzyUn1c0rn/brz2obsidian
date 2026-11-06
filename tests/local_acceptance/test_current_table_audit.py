"""Current table source facts qualify complete outputs before forged claims."""

import json
import shutil
from copy import deepcopy
from hashlib import sha256

import pytest

from brz2obsidian.application.wiring import default_workflow, local_api_workflow
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef
from tests.application.test_forgotten_workflow import rewrite
from tests.application.test_literal_angles_workflow import literal_archive
from tests.local_acceptance.api_baseline import prepare_controls
from tests.local_acceptance.api_checker import check_api_vault
from tests.local_acceptance.api_note_text import expected_document_text
from tests.local_acceptance.api_recording import ApiRecording
from tests.local_acceptance.checker import check_vault
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.sources.test_local_api_bom import note_api
from tests.support.audit_sources import SCHEMA
from tests.support.local_api import BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import NOTE

DOCUMENT = "01111111-1111-4111-8111-111111111111"
LINK = "[Target](brain://IiIiIiIiIkKCIiIiIiIiIg/Home)"
PROTECTED = (
    '```text\n|||:(table="opaque:value"):\n|fence|kept|\n```\n\n'
    '<!--\n|||:(table="opaque:value"):\n|comment|kept|\n-->\n\n'
    '    |||:(table="opaque:value"):\n    |indent|kept|\n\n'
    "> |quote|kept|\n> |second|row|\n\n"
    "- List.\n  |list|kept|\n  |second|row|\n"
    '\n`|||:(table="opaque:value"):`\n\n'
    "# |heading|kept|\n|single|row|\n\n"
    "|setext|heading|\n---\n|single|row|\n"
)
ORDINARY_RAW = "\n|||\n|a|b|\n\n|A|B|\n|` x|y `|\\{nl}|\n\n|escaped\\|\n|next|\n"
ORDINARY_EXPECTED = (
    "\n| | |\n|---|---|\n|a|b|\n\n"
    "| | |\n|---|---|\n|A|B|\n|<code>x&#124;y</code>|\\{nl}|\n\n"
    "|escaped\\|\n|next|\n"
)
RAW = (
    'Before.\n|||:(table="column-widths:-1,0,0"):\n|one|two|\nAfter.\n\n'
    + "|First|"
    + LINK
    + '|`a|b`|:(table="new-key:opaque"):\n|x|y|z|\n\n'
    + '|A|B|:(table="opaque:value"):\n|---|---|\n|short|\n\n'
    + "|only|\n|next|\n\n"
    + '|A|B|:(table="opaque:value"):\n|one|\n\n'
    + PROTECTED
    + ORDINARY_RAW
    + '\n||:(table="opaque:imported"):\n|one{nl}two|value|\n'
    + '\n|A|B|:(table="opaque:ragged"):\n|---|---|\n|'
    + LINK
    + "|\n"
    + '\n|||:(table="opaque:origin"):\n'
    + "|![Lost](.data/md-images/lost.png)|`x|y`|\n\n"
    + "After compound. "
    + LINK
    + "\n"
    + "\n[/toc/unsupported]\n\n> [!unreviewed] Keep.\n"
).encode()
EXPECTED = (
    "Before.\n\n| | |\n|---|---|\n|one|two|\n\nAfter.\n\n"
    + "| | | |\n|---|---|---|\n|First|"
    + LINK
    + "|<code>a&#124;b</code>|\n|x|y|z|\n\n"
    + "|A|B|\n|---|---|\n|short|\n\n"
    + "|only|\n|next|\n\n"
    + '|A|B|:(table="opaque:value"):\n|one|\n\n'
    + PROTECTED
    + ORDINARY_EXPECTED
    + "\n| | |\n|---|---|\n|one<br>two|value|\n"
    + "\n|A|B|\n|---|---|\n|"
    + LINK
    + "|\n"
    + "\n| | |\n|---|---|\n"
    + "|Image unavailable: Lost|<code>x&#124;y</code>|\n\n"
    + "After compound. "
    + LINK
    + "\n"
    + "\n[/toc/unsupported]\n\n> [!unreviewed] Keep.\n"
)
FORMAT_FINDINGS = (
    {
        "feature": "callout",
        "declaration": "> [!unreviewed] Keep.",
        "change": "Unsupported callout type retained as source text; change it to a supported native type.",
    },
    {
        "feature": "table",
        "declaration": ':(table="opaque:value"):',
        "change": "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with a matching header separator.",
    },
    {
        "feature": "table",
        "declaration": "|only|",
        "change": "Malformed or ambiguous table retained as source text; supply an ordinary Markdown table with matching columns and a header separator.",
    },
    {
        "feature": "table_of_contents",
        "declaration": "[/toc/unsupported]",
        "change": "Unsupported ToC declaration retained; use a standalone [/toc/] marker and reconvert, or author links manually.",
    },
)


@pytest.fixture(scope="module")
def table_outputs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("table-audit")
    source = literal_archive(folder / "source.brz", RAW)

    def qualify(parts):
        row = json.loads(parts["attachments.json"])
        previous = row["Id"]
        row["Id"] = DOCUMENT
        parts["attachments.json"] = json.dumps(row).encode()
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][DOCUMENT] = meta["AttachmentFileStates"].pop(
            previous
        )
        parts["meta.json"] = json.dumps(meta).encode()
        item = json.loads(parts["thoughts.json"])
        item["Name"] = "Entry"
        parts["thoughts.json"] = json.dumps(item).encode()

    rewrite(source, qualify)
    brz = default_workflow()
    assert brz.inspect(source).outcome == "warnings"
    brz_vault = folder / "brz"
    brz_result = brz.convert(source, brz_vault)
    assert brz_result.outcome == "warnings"
    api_raw = b"\xef\xbb\xbf" + RAW
    api = note_api(api_raw)
    row = api.attachments.pop(NOTE)
    row["id"] = DOCUMENT
    api.attachments[DOCUMENT] = row
    api.payloads[DOCUMENT] = api.payloads.pop(NOTE)
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    controls = prepare_controls(folder / "controls")
    api_vault = folder / "api"
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            folder / "http", upstream, brain_id=BRAIN, credential=KEY, purpose="convert"
        )
        with recording:
            workflow = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
            )
            assert workflow.inspect(LocalApiSourceRef(BRAIN)).outcome == "warnings"
            api_result = workflow.convert(LocalApiSourceRef(BRAIN), api_vault)
            assert api_result.outcome == "warnings"
            recording.complete()
        baseline = recording.seal(qualification=controls)
    return source, brz_vault, baseline, api_vault, brz_result, api_result


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_current_table_complete_output_keeps_raw_rows_and_findings(
    table_outputs, adapter
):
    source, brz_vault, baseline, api_vault, _, _ = table_outputs
    vault = brz_vault if adapter == "brz" else api_vault
    record = json.loads((vault / "migration-record.json").read_bytes())
    item = next(t for t in record["item_targets"] if t["item_key"] == HOME)
    document = item["documents"][0]
    assert document["key"] == DOCUMENT
    assert document["text_digest"] == sha256(EXPECTED.encode()).hexdigest()
    assert next(vault.rglob("*.original")).read_bytes() == (
        RAW if adapter == "brz" else b"\xef\xbb\xbf" + RAW
    )
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == DOCUMENT)
    findings = [f for f in asset["source_findings"] if f["kind"] == "formatting_loss"]
    expected_findings = list(FORMAT_FINDINGS)
    if adapter == "api":
        expected_findings.sort(
            key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"))
        )
    assert [json.loads(f["observed_json"]) for f in findings] == expected_findings
    assert all(
        f["affected"] == ([HOME, DOCUMENT] if adapter == "brz" else [DOCUMENT, HOME])
        for f in findings
    )
    rendered = (
        EXPECTED.replace(LINK, "[[Home — Entry.md\\|Target]]", 1)
        .replace(LINK, "[[Home — Entry.md\\|Target]]", 1)
        .replace(LINK, "[[Home — Entry.md|Target]]")
    )
    assert rendered.rstrip() in (vault / item["relative_path"]).read_text(
        encoding="utf-8"
    )
    assert [
        (r["start"], r["end"], r["table_cell"]) for r in document["references"]
    ] == [
        (73, 118, True),
        (700, 745, True),
        (829, 874, False),
    ]
    warning = next(
        i for i in record["issues"] if i["rule_id"] == "thebrain.unavailable-image.v1"
    )
    proof = json.loads(warning["message"].split("Observed: ", 1)[1])
    shift = adapter == "api"
    assert (
        proof["source_reference"]["start"],
        proof["source_reference"]["end"],
        proof["source_reference"]["before"],
    ) == (
        805 + shift,
        838 + shift,
        "![Lost](.data/md-images/lost.png)",
    )
    assert (
        proof["intermediate_reference"]["start"],
        proof["intermediate_reference"]["end"],
    ) == (765, 798)
    assert (
        proof["notice"]["start"],
        proof["notice"]["end"],
        proof["notice"]["text"],
    ) == (765, 788, "Image unavailable: Lost")
    if adapter == "brz":
        check_vault(source, vault)
    else:
        check_api_vault(baseline, vault, profile_version="4")


@pytest.mark.parametrize("adapter", ("brz", "api"))
@pytest.mark.parametrize(
    "damage",
    ("body", "warning", "provenance", "identity-order", "row-context", "code-origin"),
)
def test_current_tables_refuse_rehashed_output_claims(
    table_outputs, tmp_path, adapter, damage
):
    source, brz_vault, baseline, api_vault, brz_result, api_result = table_outputs
    original = brz_vault if adapter == "brz" else api_vault
    result = brz_result if adapter == "brz" else api_result
    vault = tmp_path / "forged"
    shutil.copytree(original, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    identity = deepcopy(record["source_identity"])
    document = next(d for item in record["item_targets"] for d in item["documents"])
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == DOCUMENT)
    rule = (
        "thebrain.markdown-inserts.v1"
        if adapter == "brz"
        else "local-api.note-formatting.v1"
    )
    findings = [f for f in asset["source_findings"] if f["rule_id"] == rule]
    warnings = [i for i in record["issues"] if i["rule_id"] == rule]
    if damage == "warning":
        asset["source_findings"] = [
            f for f in asset["source_findings"] if f["rule_id"] != rule
        ]
        record["issues"] = [i for i in record["issues"] if i["rule_id"] != rule]
        path = vault / "MIGRATION REPORT.md"
        path.write_text(
            "".join(
                line
                for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
                if rule not in line
            ),
            encoding="utf-8",
        )
    elif damage in {"provenance", "identity-order"}:
        for claim in findings + warnings:
            if damage == "provenance":
                claim["evidence"] = [
                    "attachments.json:999"
                    if adapter == "brz"
                    else "attachment:invented"
                ]
            else:
                claim["affected"] = list(reversed(claim["affected"]))
    elif damage == "row-context":
        document["references"][0]["table_cell"] = False
        path = vault / document["owner_target"]
        path.write_bytes(
            path.read_bytes().replace(b"Entry.md\\|Target", b"Entry.md|Target", 1)
        )
    elif damage == "code-origin":
        warning = next(
            i
            for i in record["issues"]
            if i["rule_id"] == "thebrain.unavailable-image.v1"
        )
        proof = json.loads(warning["message"].split("Observed: ", 1)[1])
        proof["composition"]["base_edits"][0]["kind"] = "literal_text"
        warning["message"] = (
            warning["message"].split("Observed: ", 1)[0]
            + "Observed: "
            + json.dumps(proof, sort_keys=True, separators=(",", ":"))
        )
        for finding in asset["source_findings"]:
            if finding["rule_id"] == warning["rule_id"]:
                finding["observed_json"] = json.dumps(
                    proof, sort_keys=True, separators=(",", ":")
                )
    else:
        path = vault / document["owner_target"]
        path.write_bytes(path.read_bytes().replace(b"|First|", b"|False|", 1))
        before_digest = document["text_digest"]
        changed_digest = sha256(
            EXPECTED.replace("|First|", "|False|", 1).encode()
        ).hexdigest()
        document["text_digest"] = changed_digest
        for edit in document["text_adaptations"]:
            edit["after"] = edit["after"].replace("|First|", "|False|", 1)
        for adaptation in record["adaptations"]:
            if adaptation.get("text_edit"):
                adaptation["text_edit"]["after"] = adaptation["text_edit"][
                    "after"
                ].replace("|First|", "|False|", 1)
        # Rebind every final-stage digest, including serialized image proof;
        # raw digests, originals and source identities remain authoritative.
        record = json.loads(json.dumps(record).replace(before_digest, changed_digest))
        intermediate = EXPECTED.replace(
            "Image unavailable: Lost", "![Lost](.data/md-images/lost.png)"
        )
        record = json.loads(
            json.dumps(record).replace(
                sha256(intermediate.encode()).hexdigest(),
                sha256(
                    intermediate.replace("|First|", "|False|", 1).encode()
                ).hexdigest(),
            )
        )
    forged = result.model_dump(mode="json")
    forged["receipt"]["destination"] = str(vault.resolve())
    rewrite_record(vault, record, forged)
    assert record["source_identity"] == identity
    with pytest.raises(AssertionError) as rejection:
        if adapter == "brz":
            check_vault(source, vault)
        else:
            check_api_vault(baseline, vault, profile_version="4")
    if damage == "code-origin":
        assert str(rejection.value) == "independent compound kind/code ownership"
    baseline.verify()


@pytest.mark.parametrize("profile", ("1", "2", "3"))
def test_historical_table_grammar_keeps_current_generic_forms_unchanged(profile):
    source = '|||:(table="column-widths:-1,0,0"):\n|a|b|\n\n|x|\n|y|\n'
    assert expected_document_text(source, profile_version=profile) == source
