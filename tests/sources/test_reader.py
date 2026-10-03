import json
import struct
from decimal import Decimal
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import MigrationFailed, MigrationRefused
from brz2obsidian.sources.thebrain import BrzSourceModule
from tests.application.test_minimal_workflow import make_archive


def rewrite(source, name, content):
    with ZipFile(source) as archive:
        files = [
            (info.filename, archive.read(info.filename)) for info in archive.infolist()
        ]
    with ZipFile(source, "w") as archive:
        for path, data in files:
            archive.writestr(path, content if path == name else data)


def test_source_session_returns_durable_facts_and_expires_payload_access(tmp_path):
    source = make_archive(tmp_path / "brain.brz")
    with BrzSourceModule().open(source) as session:
        snapshot = session.snapshot
        with session.open_payload(snapshot.assets[0].asset_id) as stream:
            assert stream.read() == b"Authored body.\r\n"
    assert snapshot.documents[0].text == "Authored body.\r\n"
    with (
        pytest.raises(MigrationFailed),
        session.open_payload(snapshot.assets[0].asset_id),
    ):
        pass


def test_convert_repeats_preparation_and_refuses_changed_home(tmp_path):
    source = make_archive(tmp_path / "brain.brz")
    workflow = default_workflow()
    assert workflow.inspect(source).outcome == "clean"
    rewrite(source, "settings.json", b"")
    result = workflow.convert(source, tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.issues[0].code == "invalid_entry"
    assert result.counts is None
    assert result.receipt is None
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize(
    "record", [b'{"BrainId":"x","BrainId":"y"}', b'{"value":NaN}', b"[]", b""]
)
def test_corrupt_root_records_are_refused_without_output(tmp_path, record):
    source = make_archive(tmp_path / "brain.brz")
    rewrite(source, "meta.json", record)
    result = default_workflow().convert(source, tmp_path / "vault")
    assert result.outcome == "refused"
    assert result.issues[0].code == "invalid_source"
    assert result.receipt is None
    assert not (tmp_path / "vault").exists()


def test_unimplemented_relationships_are_explicitly_refused(tmp_path):
    source = make_archive(tmp_path / "brain.brz")
    rewrite(source, "links.json", json.dumps({"Id": "future relationship"}).encode())
    with pytest.raises(MigrationRefused) as error, BrzSourceModule().open(source):
        pass
    assert error.value.issues[0].code == "unsupported_feature"


def test_retained_evidence_keeps_high_precision_numbers_and_omitted_fields(tmp_path):
    source = make_archive(tmp_path / "brain.brz")
    with ZipFile(source) as archive:
        raw = archive.read("meta.json").decode()
    raw = raw.replace('"number":1.5', '"number":0.123456789012345678901234567890')
    rewrite(source, "meta.json", raw.encode())
    destination = tmp_path / "vault"
    result = default_workflow().convert(source, destination)
    assert result.outcome == "clean"
    record = json.loads(
        (destination / "migration-record.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )
    meta = record["original_evidence"][0]["records"][0]
    thought = record["original_evidence"][1]["records"][0]
    assert meta["Uninterpreted"]["number"] == Decimal(
        "0.123456789012345678901234567890"
    )
    assert meta["Uninterpreted"]["nullable"] is None
    assert "Label" not in thought


def test_corrupt_deflate_is_a_durable_structured_refusal(tmp_path, capsys):
    from brz2obsidian.cli import main

    source = make_archive(tmp_path / "brain.brz")
    with ZipFile(source) as archive:
        files = [(info.filename, archive.read(info)) for info in archive.infolist()]
    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(name, data)
    with ZipFile(source) as archive:
        info = archive.getinfo("meta.json")
    raw = bytearray(source.read_bytes())
    name_length, extra_length = struct.unpack_from("<HH", raw, info.header_offset + 26)
    start = info.header_offset + 30 + name_length + extra_length
    raw[start : start + info.compress_size] = b"\xff" * info.compress_size
    source.write_bytes(raw)

    with pytest.raises(MigrationRefused) as caught, BrzSourceModule().open(source):
        pass
    assert caught.value.issues[0].code == "invalid_source"
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "refused"
    assert inspected.issues == converted.issues == caught.value.issues
    assert converted.receipt is None
    assert converted.issues[0].guidance
    assert not (tmp_path / "vault").exists()
    assert main(["inspect", str(source), "--json"]) == 1
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["outcome"] == "refused"
    assert envelope["issues"][0]["code"] == "invalid_source"


def test_unsupported_zip_compression_is_a_structured_refusal(tmp_path, capsys):
    from brz2obsidian.cli import main

    source = make_archive(tmp_path / "brain.brz")
    raw = bytearray(source.read_bytes())
    struct.pack_into("<H", raw, raw.index(b"PK\x03\x04") + 8, 99)
    struct.pack_into("<H", raw, raw.index(b"PK\x01\x02") + 10, 99)
    source.write_bytes(raw)
    with pytest.raises(MigrationRefused) as caught, BrzSourceModule().open(source):
        pass
    issue = caught.value.issues[0]
    assert issue.code == "unsupported_feature"
    assert "compression" in issue.message.lower()
    assert issue.guidance
    workflow = default_workflow()
    inspected = workflow.inspect(source)
    converted = workflow.convert(source, tmp_path / "vault")
    assert inspected.outcome == converted.outcome == "refused"
    assert inspected.issues == converted.issues == caught.value.issues
    assert converted.receipt is None
    assert not (tmp_path / "vault").exists()
    assert main(["convert", str(source), str(tmp_path / "cli-vault"), "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    envelope = json.loads(captured.out)
    assert envelope["outcome"] == "refused"
    assert envelope["issues"][0]["code"] == "unsupported_feature"
    assert not (tmp_path / "cli-vault").exists()
