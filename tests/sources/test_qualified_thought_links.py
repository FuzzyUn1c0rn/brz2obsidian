"""Namespace and syntax qualification through public SourceSession boundaries."""

import json
import tempfile
from contextlib import closing
from uuid import UUID, uuid5

import pytest

from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.application.test_forgotten_workflow import rewrite
from tests.application.test_graph_workflow import graph_archive, identity
from tests.support.local_api import ALONE, BRAIN, KEY, api_server
from tests.support.local_api_payloads import NOTE, PayloadApi

BRAIN_TOKEN = "EREREREREUGBEREREREREQ"
ALONE_TOKEN = "MzMzMzMzM0ODMzMzMzMzMw"
API_QUALIFIED = f"brain://api.thebrain.com/{BRAIN_TOKEN}/{ALONE_TOKEN}"
BRZ_QUALIFIED = f"brain://api.thebrain.com/{BRAIN_TOKEN}/AAAAAAAAAAAAAAAAAAAAAg"


@pytest.mark.parametrize(
    "suffix",
    ["", "/", "/unrelated-name", "/café", "/x%2Fy%3Fz%23a%25", r"/name\(extra\)"],
)
def test_qualified_suffix_is_opaque_and_authored_span_is_exact(tmp_path, suffix):
    phrase = f"[Authored]({BRZ_QUALIFIED}{suffix})"
    body = f"α\r\n> {phrase}\r\n`literal {BRZ_QUALIFIED}`\r\n"
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Target"}, notes={1: (body.encode(), 4)}
    )
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == body
        assert len(document.references) == 1
        reference = document.references[0]
        assert reference.target == identity(2)
        assert reference.expected_original == phrase


@pytest.mark.parametrize(
    "destination",
    [
        BRZ_QUALIFIED + "?",
        BRZ_QUALIFIED + "#",
        BRZ_QUALIFIED + "?x=y",
        BRZ_QUALIFIED + "#x",
        BRZ_QUALIFIED + "/x/y",
        BRZ_QUALIFIED + "/%",
        BRZ_QUALIFIED + "/%0a",
        BRZ_QUALIFIED + "/%5C",
        BRZ_QUALIFIED + "/%7f",
        BRZ_QUALIFIED + "/raw\\x",
        BRZ_QUALIFIED.replace("api.thebrain.com", "API.THEBRAIN.COM"),
        BRZ_QUALIFIED.replace("api.thebrain.com", "api.bra.in"),
        BRZ_QUALIFIED.replace("api.thebrain.com", "user@api.thebrain.com"),
        BRZ_QUALIFIED.replace("api.thebrain.com", "api.thebrain.com:11522"),
        BRZ_QUALIFIED.replace("/AAAAAAAAAAAAAAAAAAAAAg", "/AAAAAAAAAAAAAAAAAAAAAh"),
        BRZ_QUALIFIED.replace(BRAIN_TOKEN, BRAIN_TOKEN + "="),
        BRZ_QUALIFIED.replace("/AAAAAAAAAAAAAAAAAAAAAg", "/%41AAAAAAAAAAAAAAAAAAAAg"),
        BRZ_QUALIFIED + "/a&#9;b",
        "<" + BRZ_QUALIFIED + "/raw\x00name>",
        "<" + BRZ_QUALIFIED + "/raw\tname>",
        "<" + BRZ_QUALIFIED + "/raw\x7fname>",
    ],
)
def test_qualified_ambiguous_destinations_refuse_contextually(tmp_path, destination):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Target"},
        notes={1: (f"[label]({destination})".encode(), 4)},
    )
    with pytest.raises(MigrationRefused) as error, BrzSourceModule().open(source):
        pass
    issue = error.value.issues[0]
    assert issue.code in {"invalid_reference", "unsupported_feature"}
    assert issue.affected == (identity(1), identity(2001))
    assert "attachments.json:0" in issue.evidence
    assert issue.subject is not None


def test_angle_destination_keeps_existing_unicode_and_space_normalization(tmp_path):
    authored = f"[Label](<{BRZ_QUALIFIED}/café name>)"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Target"},
        notes={1: (authored.encode(), 4)},
    )
    with BrzSourceModule().open(source) as session:
        reference = session.snapshot.documents[0].references[0]
        assert reference.target == identity(2)
        assert reference.expected_original == authored
        assert reference.source_target == BRZ_QUALIFIED + "/caf%C3%A9%20name"


def test_qualified_brain_and_thought_tokens_use_guid_little_endian_fields(tmp_path):
    brain = "a1b2c3d4-e5f6-4a78-9abc-def012345678"
    target = "11223344-5566-7788-99aa-bbccddeeff00"
    uri = "brain://api.thebrain.com/1MOyofbleEqavN7wEjRWeA/RDMiEWZViHeZqrvM3e7_AA/name"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", int(UUID(target)): "Target"},
        notes={1: (f"[Label]({uri})".encode(), 4)},
    )

    def namespace(parts):
        for name in ("meta.json", "thoughts.json", "attachments.json"):
            records = [json.loads(line) for line in parts[name].splitlines()]
            for record in records:
                record["BrainId"] = brain
            parts[name] = "\n".join(json.dumps(row) for row in records).encode()
        settings = json.loads(parts["settings.json"])
        settings["Id"] = str(uuid5(UUID(brain), "20"))
        parts["settings.json"] = json.dumps(settings).encode()

    rewrite(source, namespace)
    with BrzSourceModule().open(source) as session:
        reference = session.snapshot.documents[0].references[0]
        assert reference.target == target
        assert reference.source_target == uri


def test_inert_qualified_examples_are_not_interpreted_or_rebuilt(tmp_path):
    uri = BRZ_QUALIFIED + "/bad%"
    text = f"`[example]({uri})`\r\n<!-- {uri} -->\r\n\\[escaped]({uri})\r\n```md\r\n[example]({uri})\r\n```\r\n\r\n[unused]: {uri}\r\n"
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Target"}, notes={1: (text.encode(), 4)}
    )
    with BrzSourceModule().open(source) as session:
        assert session.snapshot.documents[0].references == ()
        assert session.snapshot.documents[0].text == text


def test_current_brz_missing_target_refuses_included_document_context(tmp_path):
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home"},
        notes={1: (f"[Missing]({BRZ_QUALIFIED})".encode(), 4)},
    )
    with pytest.raises(MigrationRefused) as error, BrzSourceModule().open(source):
        pass
    issue = error.value.issues[0]
    assert issue.code == "invalid_reference"
    assert issue.affected == (identity(1), identity(2001))
    assert issue.evidence == ("attachments.json:0",)
    assert issue.subject.name == "Home"


def test_qualified_identity_follows_existing_markdown_destination_escaping(tmp_path):
    destination = BRZ_QUALIFIED.replace("brain:", r"brain\:") + r"/caf&#233;\(name\)"
    phrase = f"[Label]( \t<{destination}>)"
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Target"},
        notes={1: (phrase.encode(), 4)},
    )
    with BrzSourceModule().open(source) as session:
        reference = session.snapshot.documents[0].references[0]
        assert reference.target == identity(2)
        assert reference.source_target == BRZ_QUALIFIED + "/caf%C3%A9(name)"
        assert reference.expected_original == phrase


def test_api_current_qualified_reference_uses_authoritative_context_on_capture_and_replay(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    api = PayloadApi()
    body = f"α\r\n[Authored]({API_QUALIFIED}/Different-name)\r\n".encode()
    api.payloads[NOTE] = body
    api.attachments[NOTE]["dataLength"] = len(body)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            snapshot = session.snapshot
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            assert snapshot.documents[0].references[0].target == ALONE
            assert (
                snapshot.documents[0].references[0].source_target
                == API_QUALIFIED + "/Different-name"
            )
            assert snapshot.documents[0].text.encode() == body
            assert snapshot.documents[0].references[0].expected_original == (
                f"[Authored]({API_QUALIFIED}/Different-name)"
            )
            with session.open_payload(NOTE) as stream:
                assert stream.read() == body
            session.verify_consistency()
    with closing(
        LocalApiSession(
            source=source,
            snapshot=snapshot,
            audit=audit,
            payloads={NOTE: body},
            profile_version="4",
        )
    ) as replay:
        assert replay.snapshot == snapshot
        replay.verify_consistency()


@pytest.mark.parametrize(
    "case",
    [
        "foreign-included",
        "foreign-absent",
        "foreign-omitted",
        "current-forgotten",
        "current-system",
        "current-missing",
    ],
)
def test_api_namespace_classification_preserves_scope_and_never_fetches_foreign(case):
    api = PayloadApi()
    foreign = f"brain://api.thebrain.com/{ALONE_TOKEN}/{ALONE_TOKEN}"
    destination = foreign if case.startswith("foreign") else API_QUALIFIED
    if case == "foreign-absent":
        destination = f"brain://api.thebrain.com/{ALONE_TOKEN}/{BRAIN_TOKEN}"
    if case in {"foreign-omitted", "current-forgotten"}:
        api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-15T10:00:00"
    if case == "current-system":
        api.thoughts[ALONE]["kind"] = 5
    if case == "current-missing":
        destination = f"brain://api.thebrain.com/{BRAIN_TOKEN}/{BRAIN_TOKEN}"
    body = (
        f"Before\r\n[Foreign **label**]({destination}/opaque%252F) after\r\n".encode()
    )
    api.payloads[NOTE] = body
    api.attachments[NOTE]["dataLength"] = len(body)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        if case in {"foreign-omitted", "current-missing"}:
            with (
                pytest.raises(MigrationRefused) as error,
                module.open(LocalApiSourceRef(BRAIN)),
            ):
                pass
            diagnostic = str(error.value) + repr(error.value.issues)
            assert ALONE_TOKEN not in diagnostic
            assert destination not in diagnostic
        else:
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                document = session.snapshot.documents[0]
                assert document.references == ()
                assert len(session.snapshot.items) == (
                    1 if case in {"current-forgotten", "current-system"} else 2
                )
                if case.startswith("foreign"):
                    assert document.text.encode() == body
                    assert document.original_copy_omitted is False
                    assert session.snapshot.relationships == ()
                    with session.open_payload(document.original_asset_id) as stream:
                        assert stream.read() == body
                else:
                    assert document.text == "Before\r\n after\r\n"
                    assert document.original_copy_omitted is True
                    assert document.original_asset_id is None
                    assert not session.snapshot.assets
                session.verify_consistency()
    if case in {"foreign-omitted", "current-forgotten", "current-system"}:
        assert not any(
            path
            in {
                f"/api/thoughts/{BRAIN}/{ALONE}/graph",
                f"/api/thoughts/{BRAIN}/{ALONE}/attachments",
                f"/api/notes/{BRAIN}/{ALONE}",
            }
            for path, _, _ in api.requests
        )
    assert all(
        path.split("/")[3] == BRAIN
        for path, _, _ in api.requests
        if len(path.split("/")) > 3
        and path.split("/")[2]
        in {"brains", "thoughts", "search", "links", "attachments", "notes"}
    )


@pytest.mark.parametrize("profile", ["1", "2", "3"])
def test_historical_profiles_refuse_qualified_and_replay_compact_without_reinterpretation(
    tmp_path, monkeypatch, profile
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    api = PayloadApi()
    body = f"[Old](brain://{ALONE_TOKEN}/old-name)\r\n".encode()
    api.payloads[NOTE] = body
    api.attachments[NOTE]["dataLength"] = len(body)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=profile,
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            snapshot = session.snapshot
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
        with closing(
            LocalApiSession(
                source=source,
                snapshot=snapshot,
                audit=audit,
                payloads={NOTE: body},
                profile_version=profile,
            )
        ) as replay:
            reference = replay.snapshot.documents[0].references[0]
            assert reference.target == ALONE
            assert reference.source_target == f"brain://{ALONE_TOKEN}/old-name"
            assert reference.destination_start is reference.destination_end is None
            replay.verify_consistency()
        api.payloads[NOTE] = f"[New]({API_QUALIFIED})".encode()
        api.attachments[NOTE]["dataLength"] = len(api.payloads[NOTE])
        with (
            pytest.raises(MigrationRefused) as error,
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pass
        assert error.value.issues[0].code == "unsupported_feature"
        assert "Cross-Brain/server-qualified" in error.value.issues[0].message


@pytest.mark.parametrize("form", ["reference", "autolink", "html", "image-wrapped"])
def test_foreign_namespace_does_not_bypass_rich_reference_boundaries(tmp_path, form):
    foreign = f"brain://api.thebrain.com/{ALONE_TOKEN}/AAAAAAAAAAAAAAAAAAAAAg"
    body = {
        "reference": f"[Label][ref]\n\n[ref]: {foreign}",
        "autolink": f"<{foreign}>",
        "html": f'<a href="{foreign}">Label</a>',
        "image-wrapped": f"[![image](.data/md-images/p.png)]({foreign})",
    }[form]
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Target"}, notes={1: (body.encode(), 4)}
    )
    with pytest.raises(MigrationRefused) as error, BrzSourceModule().open(source):
        pass
    assert error.value.issues[0].code == "unsupported_feature"
