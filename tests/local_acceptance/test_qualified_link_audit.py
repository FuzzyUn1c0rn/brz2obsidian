"""Independent raw-source audit of current qualified thought-link meanings."""

import json
import shutil
from uuid import UUID

import pytest

from brz2obsidian.application.wiring import default_workflow, local_api_workflow
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef
from tests.application.test_forgotten_workflow import forget, rewrite
from tests.application.test_graph_workflow import graph_archive
from tests.local_acceptance.api_baseline import prepare_controls
from tests.local_acceptance.api_checker import audit_baseline, check_api_vault
from tests.local_acceptance.api_recording import ApiRecording
from tests.local_acceptance.api_scope import scope_note
from tests.local_acceptance.checker import check_vault, source_references
from tests.sources.test_local_api_svg_v3 import SVG
from tests.support.audit_sources import SCHEMA
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import (
    NOTE,
    PayloadApi,
    RichPayloadApi,
    attachment,
)

BRAIN_TOKEN = "EREREREREUGBEREREREREQ"
TARGET_TOKEN = "MzMzMzMzM0ODMzMzMzMzMw"
CURRENT_URI = f"brain://api.thebrain.com/{BRAIN_TOKEN}/{TARGET_TOKEN}"
FOREIGN_URI = f"brain://api.thebrain.com/{TARGET_TOKEN}/{TARGET_TOKEN}"
AUTHORED = (
    f"α\r\n[Current **label**](<{CURRENT_URI}/café name>)\r\n"
    f"[Foreign **label**]({FOREIGN_URI}/foreign\\(name\\)%2F)\r\n"
    f"[Absent foreign](brain://api.thebrain.com/{TARGET_TOKEN}/{BRAIN_TOKEN}/opaque%252F)\r\n"
    f"`[Code]({CURRENT_URI}/bad%)`\r\n"
    f"<!-- {CURRENT_URI}/bad% -->\r\n"
    f"\\[Escaped]({CURRENT_URI}/bad%)\r\n"
    f"\r\n[unused]: {CURRENT_URI}/bad%\r\n"
).encode()


@pytest.fixture(scope="module")
def qualified_outputs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("qualified-independent")
    source = graph_archive(
        directory / "source.brz",
        {1: "Home", int(UUID(ALONE)): "Target"},
        notes={1: (AUTHORED, 4)},
    )
    brz_vault, api_vault = directory / "brz-vault", directory / "api-vault"
    result = default_workflow().convert(source, brz_vault)
    assert result.outcome == "clean", result.issues
    api = PayloadApi()
    api.payloads[NOTE] = AUTHORED
    api.attachments[NOTE]["dataLength"] = len(AUTHORED)
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    controls = prepare_controls(directory / "separate-controls")
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            directory / "http",
            upstream,
            brain_id=BRAIN,
            credential=KEY,
            purpose="convert",
        )
        with recording:
            workflow = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
            )
            result = workflow.convert(LocalApiSourceRef(BRAIN), api_vault)
            assert result.outcome == "clean", result.issues
            recording.complete()
        baseline = recording.seal(qualification=controls)
    return source, brz_vault, baseline, api_vault


@pytest.mark.parametrize("adapter", ["brz", "api"])
def test_independent_audit_qualifies_namespaces_spans_and_normalized_source_target(
    qualified_outputs, adapter
):
    source, brz_vault, baseline, api_vault = qualified_outputs
    if adapter == "brz":
        assert check_vault(source, brz_vault)["thought_references"] == 1
    else:
        assert check_api_vault(baseline, api_vault, profile_version="4") == {
            "thoughts": 2,
            "relationships": 0,
            "payloads": 1,
        }
    vault = brz_vault if adapter == "brz" else api_vault
    record = json.loads((vault / "migration-record.json").read_bytes())
    reference = next(
        d["references"][0] for t in record["item_targets"] for d in t["documents"]
    )
    assert reference["source_target"] == CURRENT_URI + "/caf%C3%A9%20name"
    assert (
        reference["expected_original"]
        == f"[Current **label**](<{CURRENT_URI}/café name>)"
    )
    assert reference["destination_start"] is reference["destination_end"] is None
    assert next(vault.rglob("*.original")).read_bytes() == AUTHORED


@pytest.mark.parametrize(
    "adapter,damage",
    [
        ("brz", "foreign-binding"),
        ("api", "foreign-binding"),
        ("brz", "source-target"),
        ("api", "source-target"),
    ],
)
def test_independent_audit_rejects_namespace_or_original_uri_forgery(
    tmp_path, qualified_outputs, adapter, damage
):
    source, brz_vault, baseline, api_vault = qualified_outputs
    vault = tmp_path / "forged"
    shutil.copytree(brz_vault if adapter == "brz" else api_vault, vault)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    target = next(row for row in record["item_targets"] if row["documents"])
    document = target["documents"][0]
    if damage == "source-target":
        document["references"][0]["source_target"] = CURRENT_URI + "/wrong-original"
    else:
        # Keep the output's interpretation internally consistent: this invented
        # second local reference points to an included ID and has a matching
        # wiki rendering, counts and adaptation. Raw source namespace disproves it.
        phrase = f"[Foreign **label**]({FOREIGN_URI}/foreign\\(name\\)%2F)"
        raw = document["text"] if "text" in document else AUTHORED.decode()
        start = raw.index(phrase)
        reference = dict(document["references"][0]) | {
            "start": start,
            "end": start + len(phrase),
            "expected_original": phrase,
            "source_target": FOREIGN_URI + "/foreign(name)%2F",
            "display_text": "Foreign label",
        }
        document["references"].append(reference)
        for label in ("source_references", "planned_references"):
            record["counts"][label] += 1
        adaptation = next(
            a for a in record["adaptations"] if a["kind"] == "item_reference"
        )
        record["adaptations"].append(
            dict(adaptation) | {"affected": "reference:" + document["key"] + ":1"}
        )
        if adapter == "brz":
            accounting = next(
                e
                for e in record["source_accounting"]["entries"]
                if e["identity"] == "reference:" + document["key"] + ":0"
            )
            record["source_accounting"]["entries"].append(
                dict(accounting) | {"identity": "reference:" + document["key"] + ":1"}
            )
        note = vault / target["relative_path"]
        rendered = note.read_bytes()
        local = next(
            t["relative_path"] for t in record["item_targets"] if t["item_key"] == ALONE
        )
        note.write_bytes(
            rendered.replace(phrase.encode(), f"[[{local}|Foreign label]]".encode())
        )
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(AssertionError):
        if adapter == "brz":
            check_vault(source, vault)
        else:
            check_api_vault(baseline, vault, profile_version="4")


@pytest.mark.parametrize("profile", ["1", "2", "3"])
def test_independent_historical_profile_audit_does_not_admit_current_qualified_form(
    qualified_outputs, profile
):
    with pytest.raises(AssertionError, match="retained source profile"):
        audit_baseline(qualified_outputs[2], profile_version=profile)


def test_independent_scope_removes_only_current_namespace_and_keeps_foreign_exact():
    raw = f"Before [Private]({CURRENT_URI}/unrelated-name) after"
    assert scope_note(raw, {ALONE}, qualified_brain=BRAIN) == (
        "Before  after",
        frozenset({ALONE}),
    )
    foreign = f"[External](brain://api.thebrain.com/AAAAAAAAAAAAAAAAAAAAAg/{TARGET_TOKEN}/name)"
    assert scope_note(foreign, {}, qualified_brain=BRAIN) == (foreign, frozenset())


@pytest.mark.parametrize("where", ["target", "label", "suffix", "literal"])
def test_independent_foreign_scope_never_exempts_omitted_tokens(where):
    uri = f"brain://api.thebrain.com/AAAAAAAAAAAAAAAAAAAAAg/{BRAIN_TOKEN}"
    raw = {
        "target": f"[External]({uri.replace(BRAIN_TOKEN, TARGET_TOKEN)})",
        "label": f"[{TARGET_TOKEN}]({uri})",
        "suffix": f"[External]({uri}/{TARGET_TOKEN})",
        "literal": f"[External]({uri}) `{TARGET_TOKEN}`",
    }[where]
    with pytest.raises(AssertionError, match="unremoved excluded"):
        scope_note(raw, {ALONE}, qualified_brain=BRAIN)


@pytest.mark.parametrize(
    "destination",
    [
        CURRENT_URI + "?",
        CURRENT_URI + "/%",
        CURRENT_URI + "/%5c",
        CURRENT_URI + "/%1F",
        CURRENT_URI + "/one/two",
        CURRENT_URI.replace(TARGET_TOKEN, TARGET_TOKEN[:-1] + "x"),
        CURRENT_URI.replace("api.thebrain.com", "api.bra.in"),
        CURRENT_URI.replace("brain:", "BRAIN:"),
        CURRENT_URI.replace("api.thebrain.com", "API.THEBRAIN.COM"),
        CURRENT_URI.replace("api.thebrain.com", "api.thebrain.com:1234"),
    ],
)
def test_independent_scope_refuses_unqualified_grammar(destination):
    with pytest.raises(AssertionError):
        scope_note(f"[Label]({destination})", {}, qualified_brain=BRAIN)


@pytest.mark.parametrize("adapter", ["brz", "api"])
def test_independent_audit_qualifies_current_exclusion_and_unsafe_original_omission(
    tmp_path, adapter
):
    body = f"Before [Private]({CURRENT_URI}/private-name) after\r\n".encode()
    vault = tmp_path / "vault"
    if adapter == "brz":
        source = graph_archive(
            tmp_path / "source.brz",
            {1: "Home", int(UUID(ALONE)): "Private"},
            notes={1: (body, 4)},
        )
        rewrite(source, lambda parts: forget(parts, int(UUID(ALONE))))
        result = default_workflow().convert(source, vault)
        assert result.outcome == "clean", result.issues
        assert check_vault(source, vault)["thought_references"] == 0
    else:
        api = PayloadApi()
        api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-15T10:00:00"
        api.payloads[NOTE] = body
        api.attachments[NOTE]["dataLength"] = len(body)
        api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
        controls = prepare_controls(tmp_path / "controls")
        with api_server(api) as (_, upstream):
            recording = ApiRecording(
                tmp_path / "http",
                upstream,
                brain_id=BRAIN,
                credential=KEY,
                purpose="convert",
            )
            with recording:
                result = local_api_workflow(
                    LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
                ).convert(LocalApiSourceRef(BRAIN), vault)
                assert result.outcome == "clean", result.issues
                recording.complete()
            baseline = recording.seal(qualification=controls)
        assert check_api_vault(baseline, vault, profile_version="4")["payloads"] == 0
    assert not list(vault.rglob("*.original"))
    record = json.loads((vault / "migration-record.json").read_bytes())
    document = next(d for t in record["item_targets"] for d in t["documents"])
    assert document["original_copy_omitted"] is True
    assert document["original_asset_id"] is None
    assert document["references"] == []


def test_qualified_note_context_reaches_reverse_resource_and_svg_audits(tmp_path):
    api = RichPayloadApi()
    svg_id = "77777777-1234-4234-8234-123456789abc"
    file_id = "88888888-1234-4234-8234-123456789abc"
    body = AUTHORED + f"![Shape](.data/md-images/{svg_id}.svg)\r\n".encode()
    api.payloads[NOTE] = body
    api.attachments[NOTE]["dataLength"] = len(body)
    api.attachments[svg_id] = attachment(
        svg_id, HOME, 12, svg_id + ".svg", length=len(SVG)
    )
    api.payloads[svg_id] = SVG
    api.attachments[file_id] = attachment(
        file_id, HOME, 2, "C:/Source/manual.pdf", length=999
    )
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    controls = prepare_controls(tmp_path / "controls")
    vault = tmp_path / "vault"
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "http",
            upstream,
            brain_id=BRAIN,
            credential=KEY,
            purpose="convert",
        )
        with recording:
            result = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
            ).convert(LocalApiSourceRef(BRAIN), vault)
            assert result.outcome == "clean", result.issues
            recording.complete()
        baseline = recording.seal(qualification=controls)
    summary = check_api_vault(baseline, vault, profile_version="4")
    assert summary["relationships"] == 8
    assert summary["payloads"] == 5


@pytest.mark.parametrize(
    "text",
    [
        f"[Label][ref]\n\n[ref]: {FOREIGN_URI}",
        f"<{FOREIGN_URI}>",
        f'<a href="{FOREIGN_URI}">Label</a>',
        f"[![image](.data/md-images/p.png)]({FOREIGN_URI})",
    ],
)
def test_independent_foreign_interpretation_never_skips_rich_syntax_guards(text):
    with pytest.raises(AssertionError):
        source_references(text, HOME, {}, qualified_brain=BRAIN)


def test_independent_qualified_destination_uses_markdown_escaping_before_identity():
    text = (
        f"[Label]( \t<{CURRENT_URI.replace('brain:', r'brain\:')}/caf&#233;\\(name\\)>)"
    )
    references = source_references(text, HOME, {}, qualified_brain=BRAIN)
    assert len(references) == 1
    assert references[0]["target"] == ALONE
    assert references[0]["source_target"] == CURRENT_URI + "/caf%C3%A9(name)"


def test_independent_namespace_oracle_checks_non_symmetric_guid_known_answers():
    uri = "brain://api.thebrain.com/1MOyofbleEqavN7wEjRWeA/RDMiEWZViHeZqrvM3e7_AA/name"
    phrase = f"[Label]({uri})"
    local = source_references(
        phrase, HOME, {}, qualified_brain="a1b2c3d4-e5f6-4a78-9abc-def012345678"
    )
    assert len(local) == 1
    assert local[0]["target"] == "11223344-5566-7788-99aa-bbccddeeff00"
    assert local[0]["source_target"] == uri
    assert source_references(phrase, HOME, {}, qualified_brain=BRAIN) == []


ENTITY_SUFFIXES = ("/a&copy", "/a&copy;", r"/a\&copy;", "/a&amp;copy;")
ENTITY_TARGETS = ("/a&copy", "/a%C2%A9", "/a&copy;", "/a&copy;")


@pytest.fixture(scope="module")
def entity_outputs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("qualified-entities")
    authored = (
        "\r\n".join(
            f"[Label {i}]({CURRENT_URI}{suffix})"
            for i, suffix in enumerate(ENTITY_SUFFIXES)
        )
        + "\r\n"
    )
    source = graph_archive(
        directory / "source.brz",
        {1: "Home", int(UUID(ALONE)): "Target"},
        notes={1: (authored.encode(), 4)},
    )
    vault = directory / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    api = PayloadApi()
    api.payloads[NOTE] = authored.encode()
    api.attachments[NOTE]["dataLength"] = len(authored.encode())
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
    return source, vault, authored, baseline, api_vault


@pytest.mark.parametrize("adapter", ["brz", "api"])
def test_public_entity_destinations_and_independent_audit_keep_exact_original_meaning(
    entity_outputs, adapter
):
    source, brz_vault, authored, baseline, api_vault = entity_outputs
    with BrzSourceModule().open(source) as session:
        references = session.snapshot.documents[0].references
        assert [r.source_target for r in references] == [
            CURRENT_URI + s for s in ENTITY_TARGETS
        ]
        assert [r.expected_original for r in references] == [
            f"[Label {i}]({CURRENT_URI}{s})" for i, s in enumerate(ENTITY_SUFFIXES)
        ]
    vault = brz_vault if adapter == "brz" else api_vault
    assert next(vault.rglob("*.original")).read_bytes() == authored.encode()
    if adapter == "brz":
        assert check_vault(source, vault)["thought_references"] == 4
    else:
        assert check_api_vault(baseline, vault, profile_version="4")["payloads"] == 1
    record = json.loads((vault / "migration-record.json").read_bytes())
    document = next(d for t in record["item_targets"] for d in t["documents"])
    assert [r["source_target"] for r in document["references"]] == [
        CURRENT_URI + s for s in ENTITY_TARGETS
    ]


@pytest.mark.parametrize("index", [0, 2])
def test_independent_audit_rejects_entity_reinterpretation_in_original_destination_only(
    tmp_path, index
):
    authored = f"[Label]({CURRENT_URI}{ENTITY_SUFFIXES[index]})\r\n"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", int(UUID(ALONE)): "Target"},
        notes={1: (authored.encode(), 4)},
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "clean", result.issues
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    document = next(d for t in record["item_targets"] for d in t["documents"])
    assert len(document["references"]) == 1
    document["references"][0]["source_target"] = CURRENT_URI + "/a%C2%A9"
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(AssertionError, match="reference original destination"):
        check_vault(source, vault)


@pytest.mark.parametrize(
    "suffix,normalized",
    [
        ("/a&copy", "/a&copy"),
        ("/a&copy;", "/a%C2%A9"),
        (r"/a\&copy;", "/a&copy;"),
        ("/a&amp;copy;", "/a&copy;"),
        ("/a&copycat;", "/a&copycat;"),
        ("/a&AMP;copy;", "/a&copy;"),
        ("/a&Copy;", "/a&Copy;"),
        (r"/a\&amp;copy;", "/a&amp;copy;"),
        (r"/a&copy\;", "/a&copy;"),
        ("/a&copy&semi;", "/a&copy;"),
        ("/a&amp;amp;copy;", "/a&amp;copy;"),
        ("/a&#169;", "/a%C2%A9"),
        ("/a&#xA9;", "/a%C2%A9"),
        ("/a&#X0000A9;", "/a%C2%A9"),
        ("/a&#0000169;", "/a%C2%A9"),
        ("/a&#38;copy;", "/a&copy;"),
        ("/a&#x26;copy;", "/a&copy;"),
        ("/a&#00000169;", "/a%C2%A9"),
        ("/a&#x000000A9;", "/a%C2%A9"),
        ("/a&#x10FFFD;", "/a%F4%8F%BF%BD"),
        ("/a&#xD7FF;", "/a%ED%9F%BF"),
        ("/a&#xE000;", "/a%EE%80%80"),
        ("/a&NotEqualTilde;", "/a%E2%89%82%CC%B8"),
        ("/a\u0080", "/a%C2%80"),
        ("/a\ufdd0", "/a%EF%B7%90"),
    ],
)
def test_public_source_and_independent_scanner_agree_on_single_pass_entity_known_answers(
    tmp_path, suffix, normalized
):
    phrase = f"[Label]({CURRENT_URI}{suffix})"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", int(UUID(ALONE)): "Target"},
        notes={1: (phrase.encode(), 4)},
    )
    with BrzSourceModule().open(source) as session:
        reference = session.snapshot.documents[0].references[0]
        assert reference.source_target == CURRENT_URI + normalized
        assert reference.expected_original == phrase
    independent = source_references(phrase, HOME, {}, qualified_brain=BRAIN)
    assert len(independent) == 1
    assert independent[0]["source_target"] == CURRENT_URI + normalized


@pytest.mark.parametrize(
    "suffix",
    [
        r"/a\\&copy;",
        r"/a\\\&copy;",
        "/a&#1;",
        "/a&#x1f;",
        "/a&#127;",
        "/a&#000000169;",
        "/a&#x0000000A9;",
        "/a&#169",
        "/a&#xA9",
        "/a&#-1;",
        "/a&#x;",
        "/a&#;",
        "/a&bsol;",
        "/a&#92;copy;",
        "/a&#0;",
        "/a&#xD800;",
        "/a&#1114112;",
        "/a&#x110000;",
        "/a&#128;",
        "/a&#x10FFFF;",
        "/a&#xFDD0;",
        "/a&#xFFFE;",
        "/a&Tab;",
        "/a&NewLine;",
    ],
)
def test_public_source_and_independent_scanner_keep_numeric_and_backslash_refusals(
    tmp_path, suffix
):
    phrase = f"[Label]({CURRENT_URI}{suffix})"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", int(UUID(ALONE)): "Target"},
        notes={1: (phrase.encode(), 4)},
    )
    with pytest.raises(MigrationRefused), BrzSourceModule().open(source):
        pass
    with pytest.raises(AssertionError):
        source_references(phrase, HOME, {}, qualified_brain=BRAIN)


@pytest.mark.parametrize("adapter", ["brz", "api"])
def test_entity_spelling_cannot_exempt_a_foreign_omitted_identity(tmp_path, adapter):
    encoded = "&#77;" + TARGET_TOKEN[1:]
    uri = f"brain://api.thebrain.com/AAAAAAAAAAAAAAAAAAAAAg/{encoded}"
    if adapter == "brz":
        source = graph_archive(
            tmp_path / "source.brz",
            {1: "Home", int(UUID(ALONE)): "Private"},
            notes={1: (f"[Foreign]({uri})".encode(), 4)},
        )
        rewrite(source, lambda parts: forget(parts, int(UUID(ALONE))))
        result = default_workflow().convert(source, tmp_path / "vault")
    else:
        api = PayloadApi()
        api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-15T10:00:00"
        api.payloads[NOTE] = f"[Foreign]({uri})".encode()
        api.attachments[NOTE]["dataLength"] = len(api.payloads[NOTE])
        with api_server(api) as (_, address):
            result = local_api_workflow(
                LocalApiConfig(api_url=address), credentials=lambda: KEY
            ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
    assert result.outcome == "refused", result.issues
    assert not (tmp_path / "vault").exists()
    assert TARGET_TOKEN not in repr(result.issues) and uri not in repr(result.issues)


@pytest.mark.parametrize("where", ["target", "label", "suffix", "brain"])
@pytest.mark.parametrize("oracle", ["brz", "api"])
def test_independent_scope_rejects_semantic_foreign_omitted_associations(where, oracle):
    encoded = "&#77;" + TARGET_TOKEN[1:]
    safe = "brain://api.thebrain.com/AAAAAAAAAAAAAAAAAAAAAg/EREREREREUGBEREREREREQ"
    phrases = {
        "target": f"[Foreign]({safe.replace(BRAIN_TOKEN, encoded)})",
        "label": f"[{encoded}]({safe})",
        "suffix": f"[Foreign]({safe}/{encoded})",
        "brain": f"[Foreign](brain://api.thebrain.com/{encoded}/{BRAIN_TOKEN})",
    }
    with pytest.raises(AssertionError, match="excluded"):
        if oracle == "brz":
            source_references(phrases[where], HOME, {}, {ALONE}, qualified_brain=BRAIN)
        else:
            scope_note(phrases[where], {ALONE}, qualified_brain=BRAIN)


@pytest.mark.parametrize("oracle", ["brz", "api"])
def test_independent_scope_preserves_local_removal_and_protected_entity_literals(
    oracle,
):
    encoded = "&#77;" + TARGET_TOKEN[1:]
    local = f"[{encoded}](brain://api.thebrain.com/{BRAIN_TOKEN}/{encoded}/{encoded})"
    safe = f"[Foreign](brain://api.thebrain.com/AAAAAAAAAAAAAAAAAAAAAg/{BRAIN_TOKEN}/exact%252F)"
    literal = f"`{encoded}`\n<!-- {encoded} -->\n"
    if oracle == "api":
        assert scope_note(local + safe + literal, {ALONE}, qualified_brain=BRAIN) == (
            safe + literal,
            frozenset({ALONE}),
        )
    else:
        references = source_references(
            local + safe + literal, HOME, {}, {ALONE}, qualified_brain=BRAIN
        )
        assert len(references) == 1 and references[0]["target"] == ALONE
