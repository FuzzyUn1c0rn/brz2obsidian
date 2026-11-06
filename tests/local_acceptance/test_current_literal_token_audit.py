"""Independent stdlib acceptance and coherent forgery controls for #334."""

import json
import shutil
from copy import deepcopy
from hashlib import sha256

import pytest

from brz2obsidian.application.wiring import default_workflow, local_api_workflow
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef
from tests.application.test_literal_angles_workflow import literal_archive
from tests.local_acceptance.api_baseline import prepare_controls
from tests.local_acceptance.api_checker import audit_baseline, check_api_vault
from tests.local_acceptance.api_note_text import (
    expected_document_text,
    literal_note_edits,
)
from tests.local_acceptance.api_recording import ApiRecording
from tests.local_acceptance.api_scope import scope_note
from tests.local_acceptance.checker import check_vault
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.local_acceptance.text import literal_edits
from tests.sources.test_local_api_bom import note_api
from tests.support.audit_sources import SCHEMA
from tests.support.local_api import BRAIN, KEY, api_server

QUOTED_RAW = b"> <Example\n> /> tail\n"
BRZ_RAW = (
    b"</X>\n*kept* [Home](brain://IiIiIiIiIkKCIiIiIiIiIg/Home)\n<Y/>\n\n" + QUOTED_RAW
)
API_RAW = (
    b"\xef\xbb\xbf</X>\n*kept* [Alone](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone)\n<Y/>\n\n"
    + QUOTED_RAW
)


def test_quoted_multiline_literal_keeps_full_public_source_and_oracle_span(tmp_path):
    raw = QUOTED_RAW.decode()
    expected = "> \\<Example\n> /> tail\n"
    source = literal_archive(tmp_path / "quoted.brz", QUOTED_RAW)
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == expected
        assert [
            (e.start, e.end, e.before, e.after, e.adapted_start, e.adapted_end)
            for e in document.text_adaptations
        ] == [
            (2, 15, "<Example\n> />", "\\<Example\n> />", 2, 16),
        ]
        with session.open_payload(document.original_asset_id) as stream:
            assert stream.read() == QUOTED_RAW
    adapted, edits = literal_edits(raw, allow_literal_tokens=True)
    assert adapted == expected
    assert [
        (
            e["start"],
            e["end"],
            e["before"],
            e["after"],
            e["adapted_start"],
            e["adapted_end"],
        )
        for e in edits
    ] == [
        (2, 15, "<Example\n> />", "\\<Example\n> />", 2, 16),
    ]
    with pytest.raises(AssertionError, match="unestablished active HTML"):
        literal_edits(raw)


@pytest.mark.parametrize(
    "raw,start,end,before",
    [
        ("> - <Example\n>   /> tail\n", 4, 19, "<Example\n>   />"),
        ("- > <Example\n  > /> tail\n", 4, 19, "<Example\n  > />"),
        (">\t<Example\n>\t/> tail\n", 2, 15, "<Example\n>\t/>"),
        ("> `<Example\n> />` and <Visible\n> /> tail\n", 22, 35, "<Visible\n> />"),
    ],
    ids=("quote-list", "list-quote", "tab-prefix", "protected-code-first"),
)
def test_container_literal_origins_preserve_raw_prefixes_and_code(
    tmp_path, raw, start, end, before
):
    expected = raw[:start] + "\\" + raw[start:]
    expected_span = (start, end, before, "\\" + before, start, end + 1)
    source = literal_archive(tmp_path / "containers.brz", raw.encode())
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == expected
        assert [
            (e.start, e.end, e.before, e.after, e.adapted_start, e.adapted_end)
            for e in document.text_adaptations
        ] == [expected_span]
    adapted, edits = literal_edits(raw, allow_literal_tokens=True)
    assert adapted == expected
    assert [
        (
            e["start"],
            e["end"],
            e["before"],
            e["after"],
            e["adapted_start"],
            e["adapted_end"],
        )
        for e in edits
    ] == [expected_span]


def test_literal_oracle_keeps_distinct_inline_blocks_separate(tmp_path):
    raw = "<Example\n> /> tail\n\n> <Example\n\n> /> tail\n\n<Example\n- /> tail\n"
    source = literal_archive(tmp_path / "separate.brz", raw.encode())
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == raw
        assert document.text_adaptations == ()
    assert literal_edits(raw, allow_literal_tokens=True) == (raw, [])


@pytest.fixture(scope="module")
def literal_outputs(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("literal-audits")
    source = literal_archive(tmp_path / "source.brz", BRZ_RAW)
    brz_vault = tmp_path / "brz-vault"
    brz_result = default_workflow().convert(source, brz_vault)
    assert brz_result.outcome == "clean", brz_result.issues
    api = note_api(API_RAW)
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    controls = prepare_controls(tmp_path / "controls")
    api_vault = tmp_path / "api-vault"
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "http",
            upstream,
            brain_id=BRAIN,
            credential=KEY,
            purpose="convert",
        )
        with recording:
            workflow = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
            )
            api_result = workflow.convert(LocalApiSourceRef(BRAIN), api_vault)
            assert api_result.outcome == "clean", api_result.issues
            recording.complete()
        baseline = recording.seal(qualification=controls)
    return source, brz_vault, brz_result, baseline, api_vault, api_result


def test_current_brz_workflow_and_independent_audit_preserve_literal_runs(
    literal_outputs,
):
    source, vault, _, _, _, _ = literal_outputs
    assert check_vault(source, vault)["thought_references"] == 1
    note = (vault / "Home — Entry thought.md").read_text(encoding="utf-8")
    assert "\\</X>\n*kept* [[Home — Entry thought.md|Home]]\n\\<Y/>\n" in note
    assert "> \\<Example\n> /> tail\n" in note
    assert next(vault.rglob("*.original")).read_bytes() == BRZ_RAW


def test_api4_workflow_and_complete_independent_audit_preserve_literal_runs(
    literal_outputs,
):
    _, _, _, baseline, vault, _ = literal_outputs
    assert check_api_vault(baseline, vault, profile_version="4") == {
        "thoughts": 2,
        "relationships": 0,
        "payloads": 1,
    }
    assert next(vault.rglob("*.original")).read_bytes() == API_RAW
    normalized = "\\</X>\n*kept* [Alone](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone)\n\\<Y/>\n\n> \\<Example\n> /> tail\n"
    assert expected_document_text(API_RAW.decode(), profile_version="4") == normalized
    edits = literal_note_edits(API_RAW.decode(), profile_version="4")
    assert [
        (e["before"], e["start"], e["end"], e["adapted_start"], e["adapted_end"])
        for e in edits[:2]
    ] == [
        ("\ufeff", 0, 1, 0, 0),
        ("</X>", 1, 5, 0, 5),
    ]
    assert {e["source_digest"] for e in edits} == {sha256(API_RAW).hexdigest()}
    quoted = next(e for e in edits if e["before"].startswith("<Example"))
    start = API_RAW.decode().index("<Example")
    assert (quoted["start"], quoted["end"], quoted["before"], quoted["after"]) == (
        start,
        start + 13,
        "<Example\n> />",
        "\\<Example\n> />",
    )
    escaped = "\ufeff\\</X>\n"
    for profile in ("1", "2", "3"):
        assert expected_document_text(escaped, profile_version=profile) == escaped
    assert expected_document_text(escaped) == escaped
    code = '\ufeff```html\n<img src="https://example.invalid/no-fetch">\n'
    assert scope_note(code, {}, profile_version="4") == (code, frozenset())
    assert expected_document_text(code, profile_version="4") == code[1:]


@pytest.mark.parametrize("adapter", ("brz", "api"))
@pytest.mark.parametrize("damage", ("body", "adaptation", "original", "mapped-span"))
def test_independent_current_literal_audit_refuses_rehashed_forgery(
    literal_outputs, tmp_path, adapter, damage
):
    source, brz_vault, brz_result, baseline, api_vault, api_result = literal_outputs
    original, result = (
        (brz_vault, brz_result) if adapter == "brz" else (api_vault, api_result)
    )
    vault = tmp_path / "forged"
    shutil.copytree(original, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    trusted_identity = deepcopy(record["source_identity"])
    source_hash = sha256(source.read_bytes()).hexdigest()
    document = next(d for target in record["item_targets"] for d in target["documents"])
    if damage == "body":
        path = vault / document["owner_target"]
        path.write_bytes(path.read_bytes().replace(b"\\</X>", b"</X>", 1))
    elif damage == "adaptation":
        edit = next(
            e
            for e in document["text_adaptations"]
            if e["kind"] == "literal_text" and e["before"] == "</X>"
        )
        assert (edit["start"], edit["end"]) == ((0, 4) if adapter == "brz" else (1, 5))
        edit["start"] += 1
        next(
            a
            for a in record["adaptations"]
            if a["kind"] == "literal_text" and a["text_edit"]["before"] == "</X>"
        )["text_edit"] = deepcopy(edit)
    elif damage == "mapped-span":
        edit = next(
            e
            for e in document["text_adaptations"]
            if e["kind"] == "literal_text" and e["before"] == "<Example\n> />"
        )
        # The old oracle stopped at the continuation marker. This forged
        # prefix has valid raw/replacement geometry and the same net delta,
        # so complete replay still yields the exact escaped document body.
        prefix = "<Example\n>"
        edit.update(
            end=edit["start"] + len(prefix),
            before=prefix,
            after="\\" + prefix,
            adapted_end=edit["adapted_start"] + len(prefix) + 1,
        )
        next(
            a
            for a in record["adaptations"]
            if a["kind"] == "literal_text"
            and a["text_edit"]["before"] == "<Example\n> />"
        )["text_edit"] = deepcopy(edit)
    else:
        asset = next(
            a
            for a in record["asset_targets"]
            if a["asset_id"] == document["original_asset_id"]
        )
        path = vault / asset["relative_path"]
        body = path.read_bytes()[:-1] + b"!"
        path.write_bytes(body)
        asset["actual_sha256"] = sha256(body).hexdigest()
        if adapter == "brz":
            # Forge the emitted payload claim too, while the actual source ZIP
            # stays fixed as independent authority for the original bytes.
            payload_evidence = next(
                e for e in record["original_evidence"] if e["kind"] == "payload"
            )
            payload_evidence["records"].update(
                length=len(body), sha256=sha256(body).hexdigest()
            )
    forged_result = result.model_dump(mode="json")
    forged_result["receipt"]["destination"] = str(vault.resolve())
    rewrite_record(vault, record, forged_result)
    (tmp_path / "forged-result.json").write_text(
        json.dumps(forged_result), encoding="utf-8"
    )
    assert record["source_identity"] == trusted_identity
    expected_guard = {
        ("brz", "body"): "complete note/body/graph/tag bytes:",
        ("api", "body"): "complete active generated image prose/order/alt/title/sizing",
        ("brz", "adaptation"): "raw-derived exact literal spans and bases",
        ("api", "adaptation"): "document adaptation source before",
        ("brz", "original"): "payload bytes",
        ("api", "original"): "required payload bytes",
        ("brz", "mapped-span"): "raw-derived exact literal spans and bases",
        ("api", "mapped-span"): "document adaptation exact literal token extent",
    }[adapter, damage]
    with pytest.raises(AssertionError) as error:
        if adapter == "brz":
            check_vault(source, vault)
        else:
            check_api_vault(baseline, vault, profile_version="4")
    assert str(error.value).startswith(expected_guard)
    assert sha256(source.read_bytes()).hexdigest() == source_hash
    baseline.verify()


def test_independent_literal_scope_cache_keeps_old_and_current_policy_distinct(
    literal_outputs,
):
    _, _, _, baseline, vault, _ = literal_outputs
    assert check_api_vault(baseline, vault, profile_version="4")["payloads"] == 1
    with pytest.raises(AssertionError, match="unestablished active HTML"):
        audit_baseline(baseline, profile_version="3")
    assert check_api_vault(baseline, vault, profile_version="4")["payloads"] == 1


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("é </x \r    >tail", "é \\</x \r    >tail"),
        ("<X\t\r\n /><y>", "\\<X\t\r\n />\\<y>"),
        ("<X/>\n`<img src='no-fetch'>`\n", "\\<X/>\n`<img src='no-fetch'>`\n"),
    ],
)
def test_independent_literal_grammar_has_literal_known_answers(raw, expected):
    adapted, edits = literal_edits(raw, allow_literal_tokens=True)
    assert adapted == expected
    for edit in edits:
        assert raw[edit["start"] : edit["end"]] == edit["before"]
        assert expected[edit["adapted_start"] : edit["adapted_end"]] == edit["after"]
    with pytest.raises(AssertionError, match="unestablished active HTML"):
        literal_edits(raw)


def test_current_oracle_refuses_active_unicode_separator_but_keeps_code_ownership():
    with pytest.raises(AssertionError, match="unestablished active HTML"):
        literal_edits("<word\u00a0>\n", allow_literal_tokens=True)
    protected = "`<word\u00a0>`\n"
    assert literal_edits(protected, allow_literal_tokens=True) == (protected, [])
