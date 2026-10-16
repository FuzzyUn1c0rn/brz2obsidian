"""Mixed-scope consumers at the real external HTTP boundary."""

import json

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import KEY, api_server


def test_existing_qualified_svg_packet_uses_public_transport(tmp_path):
    from tests.local_acceptance.api_checker import audit_baseline, check_api_vault
    from tests.local_acceptance.test_api_svg_v3 import svg_baseline, svg_source_packet
    from tests.support.local_api_packet import RawPacketApi

    # This first transport tracer reuses qualified17 inputs, without new18 facts.
    baseline = svg_baseline(tmp_path / "independent-baseline", "plain")
    audit_baseline(baseline, profile_version="3")
    packet = svg_source_packet("plain")
    api = RawPacketApi(packet)
    reference = LocalApiSourceRef(baseline.json(baseline.data["brain"])["id"])
    with api_server(api) as (_, address):
        config = LocalApiConfig(api_url=address)
        with LocalApiSourceModule(
            config, credentials=lambda: KEY, profile_version="3"
        ).open(reference) as session:
            session.verify_consistency()
            for key, payload in baseline.data["payloads"].items():
                with session.open_payload(key) as stream:
                    assert stream.read() == baseline.bytes(payload["path"])
            session.verify_consistency()
        workflow = local_api_workflow(config, credentials=lambda: KEY)
        inspected = workflow.inspect(reference)
        assert inspected.outcome in {"clean", "warnings"}, inspected.issues
        converted = workflow.convert(reference, tmp_path / "actual-vault")
    assert not api.unexpected_requests
    assert api.served
    (tmp_path / "observed-source-requests.json").write_text(
        json.dumps(api.served, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (tmp_path / "observed-conversion-result.json").write_text(
        converted.model_dump_json(by_alias=True), encoding="utf-8"
    )
    assert converted.outcome in {"clean", "warnings"}, converted.issues
    assert converted.receipt.published and converted.receipt.verified
    baseline.verify()
    check_api_vault(baseline, tmp_path / "actual-vault", profile_version="3")

    # The guard is separate from actual source requests and never reaches Workflow.
    guard = RawPacketApi(packet)
    unbound = "/api/unbound-transport-probe"
    assert guard.response(unbound, {}) == (404, b"")
    assert guard.unexpected_requests == [unbound]


@pytest.mark.parametrize("case", ["tags", "zero-tags"])
def test_mixed_scope_source_retains_only_independently_audited_payloads(
    tmp_path, monkeypatch, case
):
    import tempfile

    from brz2obsidian.contracts import MigrationRefused
    from tests.local_acceptance.api_checker import audit_baseline
    from tests.local_acceptance.api_scope_inputs import (
        mixed_expectations,
        mixed_source_packet,
    )
    from tests.local_acceptance.test_api_scope_v3 import scope_baseline
    from tests.support.local_api_packet import RawPacketApi

    baseline = scope_baseline(tmp_path / "independent-source", case)
    audited = audit_baseline(baseline, profile_version="3")
    retention = audited["retention"]
    literal = mixed_expectations()
    packet = mixed_source_packet(case)
    api = RawPacketApi.from_source_packet(packet)
    ledger = json.loads(packet["files"]["endpoints.json"])
    captures = tmp_path / "product-captures"
    captures.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(captures))
    reference = LocalApiSourceRef(baseline.json(baseline.data["brain"])["id"])
    with (
        api_server(api) as (_, address),
        LocalApiSourceModule(
            LocalApiConfig(api_url=address, include_pins=False),
            credentials=lambda: KEY,
            profile_version="3",
        ).open(reference) as session,
    ):
        session.verify_consistency()
        assert (
            sorted(a.asset_id for a in session.snapshot.assets)
            == retention["retained_asset_ids"]
        )
        documents = {d.key: d for d in session.snapshot.documents}
        for key, expected in literal["adapted_notes"].items():
            assert documents[key].text == expected
        for key in retention["omitted_original_ids"]:
            assert documents[key].original_asset_id is None
            assert documents[key].original_copy_omitted is True
            with pytest.raises(MigrationRefused), session.open_payload(key):
                pytest.fail("An omitted original must not open a payload")
        for key in retention["openable_payload_ids"]:
            with session.open_payload(key) as stream:
                assert stream.read() == baseline.bytes(
                    baseline.data["payloads"][key]["path"]
                )
        for path in captures.rglob("*"):
            if path.is_file():
                raw = path.read_bytes()
                assert all(c.encode() not in raw for c in literal["canaries"])
        session.verify_consistency()
    baseline.verify()
    assert not api.unexpected_requests
    requested = {row["path"] for row in api.served}
    assert requested.isdisjoint(ledger["forbidden_routes"])
    assert not any(
        row["optional"] and row["route"] in requested for row in ledger["routes"]
    )


@pytest.mark.parametrize(
    "case,expected_code",
    [
        ("forgotten-invalid-calendar", None),
        ("relationship-contradictory-repeat", None),
        ("resource-unsupported-type", "api_resource_shape_unsupported"),
        ("external-traversal", "api_resource_shape_unsupported"),
        ("note-unresolved-thought", None),
        ("jpeg-premature-entropy", None),
    ],
)
def test_independent_negative_source_refuses_without_retained_capture(
    tmp_path, monkeypatch, case, expected_code
):
    import tempfile

    from brz2obsidian.contracts import MigrationRefused
    from tests.local_acceptance.api_scope_inputs import (
        mixed_expectations,
        negative_mixed_source_packet,
    )
    from tests.support.local_api_packet import RawPacketApi

    packet = negative_mixed_source_packet(case)
    ledger = json.loads(packet["files"]["endpoints.json"])
    brain = json.loads(packet["files"][packet["baseline_inputs"]["brain"]])["id"]
    captures = tmp_path / "product-captures"
    captures.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(captures))
    api = RawPacketApi.from_source_packet(packet)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address, include_pins=False),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with (
            pytest.raises(MigrationRefused) as refusal,
            module.open(LocalApiSourceRef(brain)),
        ):
            pytest.fail("An independently invalid source must refuse session entry")
    assert refusal.value.receipt is None
    if expected_code is not None:
        assert expected_code in {issue.code for issue in refusal.value.issues}
    diagnostic = str(refusal.value) + "".join(
        issue.model_dump_json() for issue in refusal.value.issues
    )
    assert all(c not in diagnostic for c in [*mixed_expectations()["canaries"], KEY])
    assert not tuple(captures.iterdir())
    assert set(tmp_path.iterdir()) == {captures}
    assert not api.unexpected_requests
    requested = {row["path"] for row in api.served}
    assert requested.isdisjoint(ledger["forbidden_routes"])
    assert not any(
        row["optional"] and row["route"] in requested for row in ledger["routes"]
    )
    # A supplied 404 route is available if requested; early note-binding refusal
    # needs no request to the unresolved thought and no invented failure code.
