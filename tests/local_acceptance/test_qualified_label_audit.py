"""Public source and independent-audit controls for visible inline labels."""

from contextlib import nullcontext
from uuid import UUID

import pytest

from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.application.test_forgotten_workflow import forget, rewrite
from tests.application.test_graph_workflow import graph_archive
from tests.local_acceptance.api_scope import scope_note
from tests.local_acceptance.checker import source_references
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import NOTE, PayloadApi

TOKEN = "MzMzMzMzM0ODMzMzMzMzMw"
BRAIN_TOKEN = "EREREREREUGBEREREREREQ"
CURRENT = f"brain://api.thebrain.com/{BRAIN_TOKEN}/{TOKEN}"
FOREIGN = f"brain://api.thebrain.com/AAAAAAAAAAAAAAAAAAAAAg/{BRAIN_TOKEN}"


@pytest.mark.parametrize(
    "opener,refused",
    [
        ("&#77;", True),
        ("&#x4D;", True),
        ("&#X4D;", True),
        (r"\&#X4D;", False),
        ("&#000000077;", False),
    ],
)
def test_public_current_sources_and_independent_scope_agree_on_label_privacy(
    tmp_path, opener, refused
):
    label = opener + TOKEN[1:]
    phrase = f"[{label}]({FOREIGN})"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", int(UUID(ALONE)): "Private"},
        notes={1: (phrase.encode(), 4)},
    )
    rewrite(source, lambda parts: forget(parts, int(UUID(ALONE))))
    with (
        pytest.raises(MigrationRefused) if refused else nullcontext(),
        BrzSourceModule().open(source) as session,
    ):
        document = session.snapshot.documents[0]
        assert document.text == phrase and document.references == ()
        with session.open_payload(document.original_asset_id) as stream:
            assert stream.read() == phrase.encode()
    api = PayloadApi()
    api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-15T10:00:00"
    api.payloads[NOTE] = phrase.encode()
    api.attachments[NOTE]["dataLength"] = len(phrase.encode())
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with (
            pytest.raises(MigrationRefused) if refused else nullcontext(),
            module.open(LocalApiSourceRef(BRAIN)) as session,
        ):
            document = session.snapshot.documents[0]
            assert document.text == phrase and document.references == ()
            with session.open_payload(document.original_asset_id) as stream:
                assert stream.read() == phrase.encode()
            session.verify_consistency()
    with pytest.raises(AssertionError, match="excluded") if refused else nullcontext():
        assert source_references(phrase, HOME, {}, {ALONE}, qualified_brain=BRAIN) == []
    with pytest.raises(AssertionError, match="excluded") if refused else nullcontext():
        assert scope_note(phrase, {ALONE}, qualified_brain=BRAIN) == (
            phrase,
            frozenset(),
        )


@pytest.mark.parametrize(
    "authored,visible",
    [
        ("&#X4D;", "M"),
        ("&#0000077;", "M"),
        ("&#00000077;", "&#00000077;"),
        ("&#000000077;", "&#000000077;"),
        ("&#x00004D;", "M"),
        ("&#x000004D;", "&#x000004D;"),
        ("&#0;", "\ufffd"),
        ("&#128;", "\ufffd"),
        ("&#xD800;", "\ufffd"),
        ("&#xFDD0;", "\ufffd"),
        ("&#1114112;", "\ufffd"),
        ("&#x10FFFF;", "\ufffd"),
        ("&#10;", "\n"),
        ("&#x1F;", "\ufffd"),
        ("&#x10FFFD;", "\U0010fffd"),
        ("&copycat;", "&copycat;"),
        ("&copy", "&copy"),
        ("&copy;", "©"),
        (r"\&copy;", "&copy;"),
        ("&amp;copy;", "&copy;"),
        ("&amp;#X4D;", "&#X4D;"),
        ("`&#X4D;`", "&#X4D;"),
        (r"\\&#X4D;", "\\M"),
        (r"\&#X4D;", "&#X4D;"),
        ("&ast;bold&ast;", "*bold*"),
        ("&lt;em&gt;x&lt;/em&gt;", "<em>x</em>"),
        ("&NotEqualTilde;", "≂̸"),
        ("\u0080", "\u0080"),
        ("\ufdd0", "\ufdd0"),
    ],
)
def test_public_reference_and_independent_render_label_match_pinned_inline_known_answers(
    tmp_path, authored, visible
):
    phrase = f"[{authored}]({CURRENT})"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", int(UUID(ALONE)): "Target"},
        notes={1: (phrase.encode(), 4)},
    )
    with BrzSourceModule().open(source) as session:
        reference = session.snapshot.documents[0].references[0]
        assert reference.display_text == visible
        assert reference.expected_original == phrase
    references = source_references(phrase, HOME, {}, qualified_brain=BRAIN)
    assert len(references) == 1 and references[0]["label"] == visible


@pytest.mark.parametrize(
    "damage", ["uppercase-entity", "escaped-code", "longer-closer"]
)
def test_independent_vault_audit_rejects_matching_unsafe_label_source_and_output(
    tmp_path,
    damage,
):
    import hashlib
    import json
    import shutil

    from brz2obsidian.application.wiring import default_workflow
    from tests.local_acceptance.checker import check_vault

    encoded = "&#X4D;" + TOKEN[1:]
    if damage == "uppercase-entity":
        safe = f"[\\{encoded}]({FOREIGN})"
        unsafe = f"[{encoded}]({FOREIGN})"
    else:
        safe = f"[`{encoded}`]({FOREIGN})"
        unsafe = (
            f"[\\`{encoded}`]({FOREIGN})"
            if damage == "escaped-code"
            else f"[`{encoded}``]({FOREIGN})"
        )
    source = graph_archive(
        tmp_path / "safe.brz",
        {1: "Home", int(UUID(ALONE)): "Private"},
        notes={1: (safe.encode(), 4)},
    )
    rewrite(source, lambda parts: forget(parts, int(UUID(ALONE))))
    original = tmp_path / "safe-vault"
    result = default_workflow().convert(source, original)
    assert result.outcome == "clean", result.issues
    check_vault(source, original)
    forged_source, forged = tmp_path / "unsafe.brz", tmp_path / "unsafe-vault"
    shutil.copyfile(source, forged_source)
    shutil.copytree(original, forged)

    def edit(parts):
        row = json.loads(parts["attachments.json"])
        parts[row["SourceId"] + "/Notes.md"] = unsafe.encode()
        row["DataLength"] = len(unsafe.encode())
        parts["attachments.json"] = json.dumps(row).encode()

    rewrite(forged_source, edit)
    record_path = forged / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    record["source_identity"]["source_sha256"] = hashlib.sha256(
        forged_source.read_bytes()
    ).hexdigest()
    target = next(t for t in record["item_targets"] if t["documents"])
    target["documents"][0]["text_digest"] = hashlib.sha256(unsafe.encode()).hexdigest()
    asset = record["asset_targets"][0]
    asset["actual_length"], asset["actual_sha256"] = (
        len(unsafe.encode()),
        hashlib.sha256(unsafe.encode()).hexdigest(),
    )
    (forged / asset["relative_path"]).write_bytes(unsafe.encode())
    note = forged / target["relative_path"]
    assert safe.encode() in note.read_bytes()
    note.write_bytes(note.read_bytes().replace(safe.encode(), unsafe.encode()))
    for evidence in record["original_evidence"]:
        if evidence["key"] == "attachments.json":
            evidence["records"][0]["DataLength"] = len(unsafe.encode())
        elif evidence["kind"] == "payload":
            evidence["records"]["length"] = len(unsafe.encode())
            evidence["records"]["sha256"] = hashlib.sha256(unsafe.encode()).hexdigest()
    from tests.local_acceptance.checker import ROOTS
    from tests.local_acceptance.scope import dump_json

    evidence = {entry["key"]: entry for entry in record["original_evidence"]}
    parts = [dump_json(evidence[name]["records"]) for name in ROOTS]
    parts += [
        json.dumps(entry["records"])
        for entry in record["original_evidence"]
        if entry["kind"] == "payload"
    ]
    record["source_identity"]["snapshot_digest"] = hashlib.sha256(
        "".join(parts).encode()
    ).hexdigest()
    record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    assert default_workflow().inspect(forged_source).outcome == "refused"
    with pytest.raises(AssertionError, match="excluded"):
        check_vault(forged_source, forged)


@pytest.fixture(scope="module")
def label_outputs(tmp_path_factory):
    from brz2obsidian.application.wiring import default_workflow, local_api_workflow
    from brz2obsidian.sources.thebrain.local_api import (
        LocalApiConfig,
        LocalApiSourceRef,
    )
    from tests.local_acceptance.api_baseline import prepare_controls
    from tests.local_acceptance.api_recording import ApiRecording
    from tests.support.audit_sources import SCHEMA

    directory = tmp_path_factory.mktemp("qualified-labels")
    foreign = f"[&#000000077;{TOKEN[1:]}]({FOREIGN})\n[\\&#X4D;{TOKEN[1:]}]({FOREIGN})\n[`&#X4D;{TOKEN[1:]}`]({FOREIGN})\n"

    def authored(home):
        uri = f"brain://api.thebrain.com/{BRAIN_TOKEN}/{home}"
        return foreign + "\n\n".join(
            f"[{label}]({uri})"
            for label in [
                "&#X4D;",
                "&#000000077;",
                "&copycat;",
                "&#128;",
                "&amp;copy;",
                r"\`A&copy;`",
                "`A&copy;``",
                r"`A&copy;\`",
            ]
        )

    brz_body = authored("AAAAAAAAAAAAAAAAAAAAAQ")
    source = graph_archive(
        directory / "source.brz",
        {1: "Home", int(UUID(ALONE)): "Private"},
        notes={1: (brz_body.encode(), 4)},
    )
    rewrite(source, lambda parts: forget(parts, int(UUID(ALONE))))
    vault = directory / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    api_body = authored("IiIiIiIiIkKCIiIiIiIiIg")
    api = PayloadApi()
    api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-15T10:00:00"
    api.payloads[NOTE] = api_body.encode()
    api.attachments[NOTE]["dataLength"] = len(api_body.encode())
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    controls = prepare_controls(directory / "controls")
    api_vault = directory / "api-vault"
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            directory / "http",
            upstream,
            brain_id=BRAIN,
            credential=KEY,
            purpose="convert",
        )
        with recording:
            result = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
            ).convert(LocalApiSourceRef(BRAIN), api_vault)
            assert result.outcome == "clean", result.issues
            recording.complete()
        baseline = recording.seal(qualification=controls)
    return source, vault, brz_body, baseline, api_vault, api_body


@pytest.mark.parametrize("adapter", ["brz", "api"])
def test_independent_full_audit_accepts_literal_and_decoded_labels_from_public_outputs(
    label_outputs, adapter
):
    import json

    from tests.local_acceptance.api_checker import check_api_vault
    from tests.local_acceptance.checker import check_vault

    source, vault, brz_body, baseline, api_vault, api_body = label_outputs
    if adapter == "brz":
        check_vault(source, vault)
        body = brz_body
    else:
        check_api_vault(baseline, api_vault, profile_version="4")
        vault, body = api_vault, api_body
    assert next(vault.rglob("*.original")).read_bytes() == body.encode()
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert (
        sum(
            len(d["references"])
            for target in record["item_targets"]
            for d in target["documents"]
        )
        == 8
    )


@pytest.mark.parametrize(
    "authored, visible",
    [
        ("A &amp;copy;", "A &copy;"),
        ("A `&copy;`", "A &copy;"),
        (r"A \&copy;", "A &copy;"),
        ("A &ast;word&ast;", r"A \*word\*"),
    ],
)
def test_public_adapted_heading_label_and_independent_api_document_are_single_pass(
    tmp_path, authored, visible
):
    from tests.local_acceptance.api_note_text import expected_document_text

    body = f"[/toc/]\n\n# [{authored}](https://example.invalid/item)\n"
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home"}, notes={1: (body.encode(), 4)}
    )
    with BrzSourceModule().open(source) as session:
        normalized = session.snapshot.documents[0].text
    assert f"- [{visible}](#^brz-toc-heading-1)" in normalized
    assert expected_document_text(body) == normalized
