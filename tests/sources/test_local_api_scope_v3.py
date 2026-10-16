"""Mixed-scope consumers at the real external HTTP boundary."""

import json

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
