"""Actual pre-change 10/7 bytes, independently retained at the delivered producer."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from tests.support.recorded_format6 import NOTE, ORIGINAL

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/recorded_format7"


def historical_payload():
    proof = json.loads((FIXTURE / "provenance.json").read_text(encoding="utf-8"))
    assert proof["producer_revision"] == "29ebae7e0df263cdc6fb227c569791d64a255109"
    assert proof["migration_schema_version"] == 7 and proof["renderer_version"] == "7"
    assert proof["profile_version"] == "10"
    assert hashlib.sha256((FIXTURE / "source.brz").read_bytes()).hexdigest() == (
        "83f41ca26874418fcaef90545dab26e348e4c36cfdce4b72c159e9ed4cb78f13"
    )
    assert hashlib.sha256(
        (FIXTURE / "generated-format7.zip").read_bytes()
    ).hexdigest() == (
        "9c0b07324854df330161c78a9e5f0e5240fada885c6e65ec8b1b2e4287c12e0d"
    )
    with ZipFile(FIXTURE / "generated-format7.zip") as archive:
        assert archive.testzip() is None
        payload = {name: archive.read(name) for name in archive.namelist()}
    assert set(payload) == set(proof["files"])
    for name, raw in payload.items():
        assert len(raw) == proof["files"][name]["size"]
        assert hashlib.sha256(raw).hexdigest() == proof["files"][name]["sha256"]
    # Both independent producer generations used the same literal source body.
    assert payload[NOTE] == ORIGINAL
    return payload, proof
