"""Existing frozen-capture admission preserves exact finite 64-bit limits."""

import json

import pytest

from brz2obsidian.application.diagnostics import finding_for
from brz2obsidian.contracts import Issue, SourceSnapshot
from brz2obsidian.diagnostics import diagnosed_issue
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSession
from tests.sources.test_local_api import golden_inputs


def test_signed64_total_limit_survives_public_frozen_session_replay(tmp_path):
    source, snapshot, audit, payloads = golden_inputs()
    config = LocalApiConfig(max_total_capture_bytes=9223372036854775807)
    audit["limits"]["max_total_capture_bytes"] = config.audit_limits()[
        "max_total_capture_bytes"
    ]
    arguments = {
        "source": source,
        "snapshot": SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        "audit": audit,
        "payloads": payloads,
        "capture_parent": tmp_path,
    }
    first = LocalApiSession(**arguments)
    try:
        assert (
            first.acquisition.audit.limits.max_total_capture_bytes
            == 9223372036854775807
        )
        expected_identity = first.source_identity
        arguments["audit"] = json.loads(first.acquisition.audit.model_dump_json())
        replay = LocalApiSession(**arguments)
        try:
            replay.verify_consistency()
            assert replay.source_identity == expected_identity
            assert (
                replay.acquisition.audit.limits.max_total_capture_bytes
                == 9223372036854775807
            )
        finally:
            replay.close()
    finally:
        first.close()


@pytest.mark.parametrize(
    "code,message,total_limit",
    [
        (
            "incomplete_source",
            "max_total_capture_bytes aggregate response bound exhausted",
            True,
        ),
        ("incomplete_source", "max_total_capture_bytes storage limit exhausted", True),
        ("incomplete_source", "UNTRUSTED_CANARY per-payload limit", False),
        ("invalid_source", "max_total_capture_bytes storage limit exhausted", False),
    ],
)
def test_public_finding_only_offers_total_limit_remedy_for_reviewed_reason(
    code, message, total_limit
):
    issue = Issue(
        code=code,
        phase="read",
        message=message,
        guidance="UNTRUSTED_GUIDANCE_CANARY",
    )
    finding = finding_for(diagnosed_issue(issue), "inspect")
    assert finding.code == code
    assert ("--api-max-total-capture-bytes" in finding.message) is total_limit
    if total_limit:
        assert "finite larger" in finding.message
        assert "Per-response and per-payload limits still apply" in finding.message
        assert "memory and disk space" in finding.message
    assert "CANARY" not in finding.model_dump_json()
    assert message not in finding.message
