"""Independently acquired historical output; no historical renderer is imported."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/recorded_format6"
NOTE = "Home \u2014 Format six seed.md"
ORIGINAL = (
    b"---\ncategories: []\nappearance_category:\nicon:\ncreated: 2026-10-25\nupdated:\n"
    b"tags: []\naliases: []\nsource_collection_id: \"7b170eec-a7e4-49f6-a0b4-bd553528a201\"\n"
    b"source_item_id: \"5f71e626-527e-47b4-abaa-e53d124619f8\"\n---\n\n"
    b"# Format six seed\n\nIndependent legacy source body.\r\n\n## Categories\n\n"
    b"[[Categories.md|Browse categories]]\n"
)
CURRENT = ORIGINAL + b"\r\nLocal legacy writing remains.\r\n"


def historical_payload():
    proof = json.loads((FIXTURE / "provenance.json").read_text(encoding="utf-8"))
    assert proof["producer_revision"] == "ca83db2dc3ad7bc6ecb435cba3356a974329453f"
    assert proof["migration_schema_version"] == 6 and proof["renderer_version"] == "6"
    assert hashlib.sha256((FIXTURE / "source.brz").read_bytes()).hexdigest() == "83f41ca26874418fcaef90545dab26e348e4c36cfdce4b72c159e9ed4cb78f13"
    with ZipFile(FIXTURE / "generated-format6.zip") as archive:
        payload = {name: archive.read(name) for name in archive.namelist()}
    assert set(payload) == set(proof["files"])
    for name, raw in payload.items():
        assert len(raw) == proof["files"][name]["size"]
        assert hashlib.sha256(raw).hexdigest() == proof["files"][name]["sha256"]
    assert payload[NOTE] == ORIGINAL
    return payload, proof
