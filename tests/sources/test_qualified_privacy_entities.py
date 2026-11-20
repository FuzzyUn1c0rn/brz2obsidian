"""Current semantic omission checks at acquisition and replay admission seams."""

import json
from contextlib import closing
from pathlib import Path
from uuid import UUID

import pytest

from brz2obsidian.contracts import MigrationRefused, SourceSnapshot
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.application.test_forgotten_workflow import forget, rewrite
from tests.application.test_graph_workflow import graph_archive
from tests.support.local_api import ALONE, BRAIN, KEY, api_server
from tests.support.local_api_payloads import NOTE, PayloadApi

TOKEN = "MzMzMzMzM0ODMzMzMzMzMw"
ENCODED = "&#77;" + TOKEN[1:]
CURRENT = "brain://api.thebrain.com/EREREREREUGBEREREREREQ/" + ENCODED
FOREIGN = "brain://api.thebrain.com/AAAAAAAAAAAAAAAAAAAAAg/EREREREREUGBEREREREREQ"
TEXTS = {
    "target": f"[Foreign]({FOREIGN.replace('EREREREREUGBEREREREREQ', ENCODED)})",
    "label": f"[{ENCODED}]({FOREIGN})",
    "suffix": f"[Foreign]({FOREIGN}/{ENCODED})",
    "brain": f"[Foreign](brain://api.thebrain.com/{ENCODED}/EREREREREUGBEREREREREQ)",
}


@pytest.mark.parametrize("where", TEXTS)
@pytest.mark.parametrize("adapter", ["brz", "api"])
def test_current_sources_refuse_semantic_omitted_tokens_before_discarding_foreign_reference(
    tmp_path, adapter, where
):
    text = TEXTS[where]
    if adapter == "brz":
        source = graph_archive(
            tmp_path / "source.brz",
            {1: "Home", int(UUID(ALONE)): "Private"},
            notes={1: (text.encode(), 4)},
        )
        rewrite(source, lambda parts: forget(parts, int(UUID(ALONE))))
        with pytest.raises(MigrationRefused) as error, BrzSourceModule().open(source):
            pass
    else:
        api = PayloadApi()
        api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-15T10:00:00"
        api.payloads[NOTE] = text.encode()
        api.attachments[NOTE]["dataLength"] = len(text.encode())
        with api_server(api) as (_, address):
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="4",
            )
            with (
                pytest.raises(MigrationRefused) as error,
                module.open(LocalApiSourceRef(BRAIN)),
            ):
                pass
        assert all(
            path.split("/")[3] == BRAIN
            for path, _, _ in api.requests
            if len(path.split("/")) > 3
            and path.split("/")[2]
            in {"brains", "thoughts", "notes", "attachments", "links", "search"}
        )
    diagnostic = str(error.value) + repr(error.value.issues)
    assert (
        TOKEN not in diagnostic
        and ENCODED not in diagnostic
        and ALONE not in diagnostic
    )
    assert FOREIGN not in diagnostic and text not in diagnostic


def invalid_captures():
    root = Path(__file__).parents[1] / "fixtures/qualified_links"
    return [
        case
        for path in sorted(root.glob("invalid-profile4-entity*.json"))
        for case in json.loads(path.read_bytes())["cases"]
    ]


@pytest.mark.parametrize("case", invalid_captures(), ids=lambda case: case["case"])
def test_public_replay_admission_rejects_bug_admitted_semantic_omission_before_snapshot_access(
    tmp_path, case
):
    # These are exact synthetic captures admitted by 0b's bug, not fabricated
    # projections. Admission/snapshot must refuse without an open_payload call.
    with (
        pytest.raises(MigrationRefused) as error,
        closing(
            LocalApiSession(
                source=case["source"],
                snapshot=SourceSnapshot.model_validate_json(
                    json.dumps(case["snapshot"])
                ),
                audit=case["audit"],
                payloads={
                    key: raw.encode() for key, raw in case["payloads_utf8"].items()
                },
                capture_parent=tmp_path,
                profile_version="4",
            )
        ) as replay,
    ):
        _ = replay.snapshot
    diagnostic = str(error.value) + repr(error.value.issues)
    assert (
        TOKEN not in diagnostic
        and ENCODED not in diagnostic
        and ALONE not in diagnostic
    )


@pytest.mark.parametrize(
    "case", ["local-excluded", "foreign-included", "protected-literal"]
)
@pytest.mark.parametrize("adapter", ["brz", "api"])
def test_semantic_screen_preserves_local_removal_safe_foreign_and_literals(
    tmp_path, monkeypatch, adapter, case
):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    home_token = (
        "AAAAAAAAAAAAAAAAAAAAAQ" if adapter == "brz" else "IiIiIiIiIkKCIiIiIiIiIg"
    )
    safe = f"brain://api.thebrain.com/AAAAAAAAAAAAAAAAAAAAAg/{home_token}"
    phrase = (
        f"[{ENCODED}]({CURRENT}/{ENCODED})"
        if case == "local-excluded"
        else f"[Foreign]({safe}/exact%252F)"
    )
    body = f"Before {phrase} after\n"
    if case == "protected-literal":
        body += f"`{ENCODED}`\n<!-- {ENCODED} -->\n"
    expected = "Before  after\n" if case == "local-excluded" else body
    if adapter == "brz":
        source = graph_archive(
            tmp_path / "source.brz",
            {1: "Home", int(UUID(ALONE)): "Private"},
            notes={1: (body.encode(), 4)},
        )
        rewrite(source, lambda parts: forget(parts, int(UUID(ALONE))))
        module, ref = BrzSourceModule(), source
    else:
        api = PayloadApi()
        api.thoughts[ALONE]["forgottenDateTime"] = "2026-10-15T10:00:00"
        api.payloads[NOTE] = body.encode()
        api.attachments[NOTE]["dataLength"] = len(body.encode())
        server = api_server(api)
        _, address = server.__enter__()
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        ref = LocalApiSourceRef(BRAIN)
    try:
        with module.open(ref) as session:
            snapshot = session.snapshot
            document = snapshot.documents[0]
            assert document.text == expected
            assert document.references == () and snapshot.relationships == ()
            assert document.original_copy_omitted is (case == "local-excluded")
            payloads = {}
            for asset in snapshot.assets:
                with session.open_payload(asset.asset_id) as stream:
                    payloads[asset.asset_id] = stream.read()
            if case == "local-excluded":
                assert document.original_asset_id is None and not payloads
            else:
                assert payloads[document.original_asset_id] == body.encode()
            session.verify_consistency()
            if adapter == "api":
                directory = next(tmp_path.glob("brz2obsidian-api-*"))
                source_data = json.loads((directory / "source.json").read_bytes())
                audit = json.loads((directory / "audit.json").read_bytes())
                assert any(
                    row["domain"] == "exclusion" and row["value"]["id"] == ALONE
                    for row in source_data["records"]
                )
        if adapter == "api":
            with closing(
                LocalApiSession(
                    source=source_data,
                    snapshot=snapshot,
                    audit=audit,
                    payloads=payloads,
                    profile_version="4",
                )
            ) as replay:
                assert replay.snapshot == snapshot
                replay.verify_consistency()
    finally:
        if adapter == "api":
            server.__exit__(None, None, None)
