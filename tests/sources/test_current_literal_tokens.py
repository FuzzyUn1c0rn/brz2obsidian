"""Approved current-source visible tokens through public source sessions."""

import json
import tempfile
from contextlib import ExitStack, closing, contextmanager
from copy import deepcopy
from hashlib import sha256
from uuid import UUID

import pytest

from brz2obsidian.application import SourceModuleBinding, Workflow
from brz2obsidian.contracts import MigrationRefused, SourceSnapshot, TextAdaptation
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.application.test_forgotten_workflow import forget, rewrite
from tests.application.test_graph_workflow import graph_archive
from tests.application.test_literal_angles_workflow import literal_archive
from tests.application.test_resources_workflow import thought
from tests.sources.test_local_api import golden_inputs
from tests.sources.test_local_api_bom import note_api
from tests.support.local_api import ALONE, BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import IMAGE, PNG, attachment


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_leading_literal_exposes_included_item_then_owned_image_in_source_order(
    tmp_path, adapter
):
    target = "00000000-0000-0000-0000-000000000002" if adapter == "brz" else ALONE
    token = "AAAAAAAAAAAAAAAAAAAAAg" if adapter == "brz" else "MzMzMzMzM0ODMzMzMzMzMw"
    phrase = f"[Alone](brain://{token}/Alone)"
    image = f"![Red](.data/md-images/{IMAGE}.png)"
    raw = ("<X/>\n" + phrase + "\n" + image + "\n</Y>\n").encode()
    with ExitStack() as stack:
        if adapter == "brz":
            source = literal_archive(
                tmp_path / "source.brz",
                raw,
                resources=(({"Type": 12, "Location": IMAGE + ".png"}, PNG),),
                thoughts=(thought(target, "Alone"),),
            )
            session = stack.enter_context(BrzSourceModule().open(source))
            image_id = "aaaaaaaa-0000-4000-8000-000000000001"
        else:
            api = note_api(raw)
            api.attachments[IMAGE] = attachment(
                IMAGE, HOME, 12, IMAGE + ".png", length=len(PNG)
            )
            api.payloads[IMAGE] = PNG
            _, address = stack.enter_context(api_server(api))
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="4",
            )
            session = stack.enter_context(module.open(LocalApiSourceRef(BRAIN)))
            image_id = IMAGE
        document = session.snapshot.documents[0]
        assert document.text == "\\<X/>\n" + phrase + "\n" + image + "\n\\</Y>\n"
        assert [(r.kind, r.target) for r in document.references] == [
            ("item", target),
            ("image", image_id),
        ]
        assert [document.text[r.start : r.end] for r in document.references] == [
            phrase,
            image,
        ]
        with session.open_payload(image_id) as stream:
            assert stream.read() == PNG


@pytest.mark.parametrize("adapter", ("brz", "api"))
@pytest.mark.parametrize("code_owned", (False, True))
def test_selfclosing_marker_exposes_active_html_but_keeps_genuine_code(
    tmp_path, adapter, code_owned
):
    tag = '<img src="https://example.invalid/NO_FETCH_CANARY.png">'
    raw = ("<X/>\n" + ("`" + tag + "`" if code_owned else tag) + "\n").encode()
    with ExitStack() as stack:
        api = None
        if adapter == "brz":
            source = literal_archive(tmp_path / "source.brz", raw)
            manager = BrzSourceModule().open(source)
        else:
            api = note_api(raw)
            _, address = stack.enter_context(api_server(api))
            manager = LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="4",
            ).open(LocalApiSourceRef(BRAIN))
        if code_owned:
            with manager as session:
                document = session.snapshot.documents[0]
                assert document.text == "\\<X/>\n`" + tag + "`\n"
                assert document.references == ()
                assert [(e.before, e.after) for e in document.text_adaptations] == [
                    ("<X/>", "\\<X/>")
                ]
                with session.open_payload(document.original_asset_id) as stream:
                    assert stream.read() == raw
        else:
            with pytest.raises(MigrationRefused) as error, manager:
                pass
            assert error.value.issues[0].code == "unsupported_feature"
            assert "NO_FETCH_CANARY" not in str(error.value) + repr(error.value.issues)
        if api is not None:
            assert all("NO_FETCH_CANARY" not in path for path, _, _ in api.requests)


def historical_note_capture(profile, raw, *, normalized, edits=()):
    source, snapshot, audit, payloads = golden_inputs(profile)
    key = snapshot["documents"][0]["original_asset_id"]
    for row in source["records"]:
        if row["domain"] == "note_text":
            row["value"]["text"] = raw.decode()
        elif row["domain"] == "attachment" and row["value"]["id"] == key:
            row["value"]["dataLength"] = len(raw)
    for evidence in snapshot["original_evidence"]:
        row = next(
            (row for row in source["records"] if row["key"] == evidence["key"]), None
        )
        if row is not None:
            evidence["original_json"] = json.dumps(row["value"])
    for asset in snapshot["assets"] + source["payloads"]:
        if asset["asset_id"] == key:
            asset.update(actual_length=len(raw), actual_sha256=sha256(raw).hexdigest())
    snapshot["documents"][0].update(
        text=normalized,
        text_digest=sha256(normalized.encode()).hexdigest(),
        text_adaptations=list(edits),
        references=[],
    )
    snapshot["identity"]["source_sha256"] = snapshot["identity"]["snapshot_digest"] = ""
    payloads[key] = raw
    return {
        "source": source,
        "snapshot": SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        "audit": audit,
        "payloads": payloads,
        "profile_version": profile,
    }


@pytest.mark.parametrize("profile", ("1", "2", "3"))
def test_historical_constructor_rejects_coherent_new_literal_but_renders_authored_escape_as8(
    tmp_path, profile
):
    from brz2obsidian.sources.thebrain.local_api import (
        LOCAL_API_POLICY,
        LOCAL_API_POLICY_V2,
        LOCAL_API_POLICY_V3,
    )

    policy = {
        "1": LOCAL_API_POLICY,
        "2": LOCAL_API_POLICY_V2,
        "3": LOCAL_API_POLICY_V3,
    }[profile]
    original_source, original_snapshot, original_audit, original_payloads = (
        golden_inputs(profile)
    )
    original_expected = SourceSnapshot.model_validate_json(
        json.dumps(original_snapshot)
    )
    with closing(
        LocalApiSession(
            source=original_source,
            snapshot=original_expected,
            audit=original_audit,
            payloads=original_payloads,
            profile_version=profile,
        )
    ) as unchanged:
        assert unchanged.snapshot == original_expected
        assert unchanged.source_identity == original_expected.identity
        unchanged.verify_consistency()
    raw = b"\\</X>\n"
    arguments = historical_note_capture(profile, raw, normalized=raw.decode())
    with closing(LocalApiSession(**arguments)) as replay:
        expected = replay.snapshot
        assert expected.documents[0].text == raw.decode()
        assert expected.documents[0].text_adaptations == ()
        replay.verify_consistency()

    class FrozenSource:
        @contextmanager
        def open(self, source_ref):
            assert source_ref == "retained-public-capture"
            with closing(LocalApiSession(**arguments)) as session:
                assert session.snapshot == expected
                yield session

    workflow = Workflow(
        SourceModuleBinding(FrozenSource(), policy),
        ObsidianRenderer(),
        FilesystemPublisher(),
    )
    vault = tmp_path / "vault"
    result = workflow.convert("retained-public-capture", vault)
    assert result.outcome == "clean", result.issues
    assert result.source_identity == expected.identity
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["schema_version"] == 9 and record["renderer_version"] == "9"
    assert record["profile_version"] == profile
    document = next(d for target in record["item_targets"] for d in target["documents"])
    assert document["text_adaptations"] == []
    assert document["text_digest"] == sha256(raw).hexdigest()
    assert next(vault.rglob("*.original")).read_bytes() == raw

    # The public SourceModule composition also renders the unchanged independent
    # old capture with output9; source admission still uses the captured profile.
    arguments = {
        "source": original_source,
        "snapshot": original_expected,
        "audit": original_audit,
        "payloads": original_payloads,
        "profile_version": profile,
    }
    expected = original_expected
    old_vault = tmp_path / "unchanged-old"
    old_result = workflow.convert("retained-public-capture", old_vault)
    assert old_result.outcome == "clean", old_result.issues
    assert old_result.source_identity == original_expected.identity
    old_record = json.loads((old_vault / "migration-record.json").read_bytes())
    assert old_record["schema_version"] == 9 and old_record["renderer_version"] == "9"
    emitted = {
        d["key"]: d
        for target in old_record["item_targets"]
        for d in target["documents"]
    }
    for document in original_expected.documents:
        assert emitted[document.key]["text_digest"] == document.text_digest
        assert emitted[document.key]["text_adaptations"] == [
            e.model_dump(mode="json") for e in document.text_adaptations
        ]

    forged_raw = b"</X>\n"
    edit = {
        "kind": "literal_text",
        "start": 0,
        "end": 4,
        "before": "</X>",
        "after": "\\</X>",
        "adapted_start": 0,
        "adapted_end": 5,
        "source_digest": sha256(forged_raw).hexdigest(),
    }
    forged = historical_note_capture(
        profile, forged_raw, normalized="\\</X>\n", edits=(edit,)
    )
    with pytest.raises(MigrationRefused) as error, closing(LocalApiSession(**forged)):
        pytest.fail("historical constructor admitted a new-grammar document")
    assert (
        error.value.issues[0].message
        == "Normalized Markdown is not bound to qualified scoped source text"
    )


@contextmanager
def scoped_current_source(tmp_path, adapter, raw):
    if adapter == "brz":
        source = graph_archive(
            tmp_path / "source.brz",
            {1: "Home", int(UUID(ALONE)): "Private"},
            notes={1: (raw, 4)},
        )
        rewrite(source, lambda parts: forget(parts, int(UUID(ALONE))))
        with BrzSourceModule().open(source) as session:
            yield session
    else:
        api = note_api(raw)
        api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-15T10:00:00"
        with api_server(api) as (_, address):
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="4",
            )
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                yield session


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_leading_closer_exposes_omitted_phrase_and_omits_original(tmp_path, adapter):
    token = "MzMzMzMzM0ODMzMzMzMzMw"
    label = "&#77;" + token[1:]
    raw = f"</X>\n[{label}](brain://{token}/Private)\n".encode()
    with scoped_current_source(tmp_path, adapter, raw) as session:
        document = session.snapshot.documents[0]
        assert document.text == "\\</X>\n\n"
        assert document.references == ()
        assert document.original_copy_omitted and document.original_asset_id is None
        assert [
            (e.start, e.end, e.before, e.after, e.source_digest)
            for e in document.text_adaptations
        ] == [(0, 4, "</X>", "\\</X>", sha256(b"</X>\n\n").hexdigest())]
        assert (
            token not in document.model_dump_json()
            and label not in document.model_dump_json()
        )


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_leading_closer_cannot_hide_entity_derived_private_foreign_label(
    tmp_path, adapter
):
    token = "MzMzMzMzM0ODMzMzMzMzMw"
    label = "&#77;" + token[1:]
    # Foreign Brain + included local API Home token: the omitted display is the defect.
    foreign = "brain://api.thebrain.com/AAAAAAAAAAAAAAAAAAAAAg/IiIiIiIiIkKCIiIiIiIiIg"
    raw = f"</X>\n[{label}]({foreign})\n".encode()
    with (
        pytest.raises(MigrationRefused) as error,
        scoped_current_source(tmp_path, adapter, raw),
    ):
        pass
    expected = (
        (
            "invalid_reference",
            "Note contains an excluded association outside removable references",
        )
        if adapter == "brz"
        else ("invalid_source", "Excluded note associations cannot be removed safely")
    )
    assert (error.value.issues[0].code, error.value.issues[0].message) == expected
    diagnostic = str(error.value) + repr(error.value.issues)
    assert all(value not in diagnostic for value in (token, label, foreign, ALONE))


CURRENT_EXAMPLES = [
    (
        "adjacent-independent",
        "<One></tWo><br  /><THREE-4/><a--1->",
        "\\<One>\\</tWo><br  />\\<THREE-4/>\\<a--1->",
    ),
    ("open-space", "prefix <word \t> tail", "prefix \\<word \t> tail"),
    ("open-crlf", "é <word \t\r\n\t> tail", "é \\<word \t\r\n\t> tail"),
    ("close-cr", "é </word \r    >tail", "é \\</word \r    >tail"),
    ("self-lf", "é <word\n\t/> tail", "é \\<word\n\t/> tail"),
    (
        "leading-block-runs",
        "<One>\r\n*kept*\r\n</tWo>\r\n<THREE-4/>\r\n",
        "\\<One>\r\n*kept*\r\n\\</tWo>\r\n\\<THREE-4/>\r\n",
    ),
    (
        "containers",
        "> </X>\n> *bold*\n\n- <Y/>\n  *em*\n",
        "> \\</X>\n> *bold*\n\n- \\<Y/>\n  *em*\n",
    ),
    (
        "ownership-after-leading",
        "<One>\n`</Code>` <!-- <Keep/> --> \\</Escaped>\n```html\n<Protected/>\n```\n</End>\n",
        "\\<One>\n`</Code>` <!-- <Keep/> --> \\</Escaped>\n```html\n<Protected/>\n```\n\\</End>\n",
    ),
]


@pytest.mark.parametrize(
    "case,raw,expected", CURRENT_EXAMPLES, ids=[c[0] for c in CURRENT_EXAMPLES]
)
def test_current_brz_tokens_keep_surrounding_markdown_and_source_ownership(
    tmp_path, case, raw, expected
):
    source = literal_archive(tmp_path / "source.brz", raw.encode())
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == expected
        for edit in document.text_adaptations:
            assert raw[edit.start : edit.end] == edit.before
            assert expected[edit.adapted_start : edit.adapted_end] == edit.after
            assert edit.source_digest == sha256(raw.encode()).hexdigest()
        with session.open_payload(document.original_asset_id) as stream:
            assert stream.read() == raw.encode()


@pytest.mark.parametrize(
    "token",
    [
        "<DiV>",
        "<fOnT/>",
        "<svg/>",
        "<word hidden>",
        '<word href="https://example.invalid/SECRET_CANARY">',
        "<word onload='SECRET_CANARY'>",
        "<!DOCTYPE word>",
        "<?word SECRET_CANARY?>",
    ],
)
def test_current_brz_keeps_active_known_html_and_attributes_unsupported(
    tmp_path, token
):
    source = literal_archive(tmp_path / "source.brz", (token + "\n").encode())
    with pytest.raises(MigrationRefused) as error, BrzSourceModule().open(source):
        pass
    assert error.value.issues[0].code == "unsupported_feature"
    assert "SECRET_CANARY" not in str(error.value) + repr(error.value.issues)


@pytest.mark.parametrize(
    "raw",
    [
        "<word\n\n>\n",
        "é </word \r > tail",
        "<word_name> <word / >\n",
        "<word.name> <word:thing> < word> </ word>\n",
    ],
)
def test_nonactive_angle_forms_keep_existing_handling_in_current_and_old_api(raw):
    for profile in ("3", "4"):
        with api_server(note_api(raw.encode())) as (_, address):
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version=profile,
            )
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                document = session.snapshot.documents[0]
                assert document.text == raw and document.text_adaptations == ()


def test_unicode_name_whitespace_keeps_its_historical_html_refusal():
    for profile in ("3", "4"):
        with api_server(note_api("<word\u00a0>\n".encode())) as (_, address):
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version=profile,
            )
            with (
                pytest.raises(MigrationRefused) as error,
                module.open(LocalApiSourceRef(BRAIN)),
            ):
                pass
            assert error.value.issues[0].code == "unsupported_feature"


def test_current_brz_leading_closer_preserves_exact_adaptation_and_original(tmp_path):
    raw = "</Example> é *kept*\r\n".encode()
    source = literal_archive(tmp_path / "source.brz", raw)
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == "\\</Example> é *kept*\r\n"
        assert document.text_digest == sha256(document.text.encode()).hexdigest()
        assert [
            (
                edit.start,
                edit.end,
                edit.before,
                edit.after,
                edit.adapted_start,
                edit.adapted_end,
                edit.source_digest,
            )
            for edit in document.text_adaptations
        ] == [(0, 10, "</Example>", "\\</Example>", 0, 11, sha256(raw).hexdigest())]
        assert not document.original_copy_omitted
        with session.open_payload(document.original_asset_id) as stream:
            assert stream.read() == raw


def test_api4_live_and_replay_expose_link_after_leading_literal_with_bom(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    raw = (
        "\ufeff</Marker>\r\n[Alone](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone)\r\n".encode()
    )
    with api_server(note_api(raw)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as live:
            snapshot = live.snapshot
            document = snapshot.documents[0]
            assert (
                document.text
                == "\\</Marker>\r\n[Alone](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone)\r\n"
            )
            assert [
                (e.start, e.end, e.before, e.after, e.adapted_start, e.adapted_end)
                for e in document.text_adaptations
            ] == [
                (0, 1, "\ufeff", "", 0, 0),
                (1, 10, "</Marker>", "\\</Marker>", 0, 10),
            ]
            assert {e.source_digest for e in document.text_adaptations} == {
                sha256(raw).hexdigest()
            }
            assert [r.target for r in document.references] == [ALONE]
            assert document.references[0].start == 12
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            payloads = {}
            for asset in snapshot.assets:
                if asset.availability == "present":
                    with live.open_payload(asset.asset_id) as stream:
                        payloads[asset.asset_id] = stream.read()
    replay = LocalApiSession(
        source=source,
        snapshot=snapshot,
        audit=audit,
        payloads=payloads,
        profile_version="4",
        capture_parent=tmp_path,
    )
    try:
        assert replay.snapshot == snapshot
        replay.verify_consistency()
        with replay.open_payload(document.original_asset_id) as stream:
            assert stream.read() == raw
    finally:
        replay.close()

    for damage in ("body", "adaptation", "original"):
        forged = snapshot.model_dump(mode="json")
        forged_source, forged_payloads = deepcopy(source), deepcopy(payloads)
        forged["identity"]["source_sha256"] = forged["identity"]["snapshot_digest"] = ""
        note = forged["documents"][0]
        if damage == "body":
            text = raw.decode().removeprefix("\ufeff")
            note.update(
                text=text,
                text_digest=sha256(text.encode()).hexdigest(),
                text_adaptations=note["text_adaptations"][:1],
            )
            for reference in note["references"]:
                reference["start"] -= 1
                reference["end"] -= 1
                reference["document_digest"] = note["text_digest"]
        elif damage == "adaptation":
            note["text_adaptations"][1]["source_digest"] = sha256(
                b"false scoped text"
            ).hexdigest()
        else:
            note_id = document.original_asset_id
            forged_payloads[note_id] = raw[:-1] + b"!"
            measured = sha256(forged_payloads[note_id]).hexdigest()
            for asset in forged["assets"] + forged_source["payloads"]:
                if asset["asset_id"] == note_id:
                    asset["actual_sha256"] = measured
        candidate = SourceSnapshot.model_validate_json(json.dumps(forged))
        with (
            pytest.raises(MigrationRefused) as error,
            closing(
                LocalApiSession(
                    source=forged_source,
                    snapshot=candidate,
                    audit=audit,
                    payloads=forged_payloads,
                    profile_version="4",
                    capture_parent=tmp_path,
                )
            ),
        ):
            pytest.fail("constructor exposed an unbound literal capture")
        assert (
            error.value.issues[0].message
            == "Normalized Markdown is not bound to qualified scoped source text"
        )


@pytest.mark.parametrize("profile", ("1", "2", "3"))
def test_historical_api_profiles_keep_refusing_new_literal_closers(profile):
    with api_server(note_api(b"</Marker>\n")) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=profile,
        )
        with (
            pytest.raises(MigrationRefused) as error,
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pass
    assert error.value.issues[0].code == "unsupported_feature"


def test_current_literal_policy_survives_legacy_table_replay_alternative(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    raw = b"</X>\n\n|F|M|\n|a|b|\n"
    prior_text = "\\</X>\n\n|F|M|\n|a|b|\n"
    with api_server(note_api(raw)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as live:
            current = live.snapshot
            assert current.documents[0].text != prior_text
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
    edit = TextAdaptation(
        start=0,
        end=4,
        before="</X>",
        after="\\</X>",
        adapted_start=0,
        adapted_end=5,
        source_digest=sha256(raw).hexdigest(),
    )
    prior = current.model_dump(mode="json")
    prior["identity"]["source_sha256"] = prior["identity"]["snapshot_digest"] = ""
    prior["documents"][0].update(
        text=prior_text,
        text_digest=sha256(prior_text.encode()).hexdigest(),
        text_adaptations=[edit.model_dump(mode="json")],
    )
    prior["findings"] = []
    candidate = SourceSnapshot.model_validate_json(json.dumps(prior))
    with closing(
        LocalApiSession(
            source=source,
            snapshot=candidate,
            audit=audit,
            payloads={current.documents[0].original_asset_id: raw},
            profile_version="4",
        )
    ) as replay:
        assert replay.snapshot.documents == candidate.documents
        assert replay.snapshot.documents[0].text == prior_text
        replay.verify_consistency()
