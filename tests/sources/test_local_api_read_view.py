"""Finite public payload-reader authority and independently known bytes."""

import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest

from brz2obsidian.contracts import MigrationFailed, MigrationRefused, SourceSnapshot
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.sources.test_local_api import golden_inputs
from tests.support.local_api import BRAIN, KEY, api_server
from tests.support.local_api_payloads import FILE, NOTE, PNG, FilePayloadApi

ASSET = "00000000-0000-4000-8000-000000000003"
RAW = b"A\nB\n"


@pytest.fixture
def capture(tmp_path):
    source, snapshot, audit, payloads = golden_inputs()
    session = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        capture_parent=tmp_path,
    )
    directory = next(tmp_path.iterdir())
    yield session, directory, directory / "payload/0000000000000001.bin"
    session.close()


@pytest.mark.parametrize(
    "fault", ["changed", "short", "long", "restored", "early_close"]
)
def test_view_validates_selected_consumed_bytes_and_caught_failure_stays_failed(
    capture, fault
):
    session, _, path = capture
    view = session.payload_read_view()
    with pytest.raises((MigrationRefused, MigrationFailed)), view as reader:
        with pytest.raises((MigrationRefused, MigrationFailed)):
            if fault in {"changed", "short", "long"}:
                path.write_bytes(
                    {"changed": b"X\nB\n", "short": b"A", "long": RAW + b"!"}[fault]
                )
            with reader.open_payload(ASSET) as stream:
                if fault == "restored":
                    path.write_bytes(b"X\nB\n")
                    assert stream.read(1) == b"X"
                    path.write_bytes(RAW)
                    stream.read()
                elif fault == "early_close":
                    path.write_bytes(b"X\nB\n")
                    assert stream.read(1) == b"X"
                    path.write_bytes(RAW)
                else:
                    stream.read()
        path.write_bytes(RAW)
        with pytest.raises(MigrationRefused), reader.open_payload(ASSET):
            pytest.fail("A caught failure must not restore read authority")


@pytest.mark.parametrize(
    "name",
    ["source.json", "snapshot.json", "metadata.json", "audit.json", "manifest.json"],
)
def test_view_metadata_observation_is_pinned_even_after_restoration(capture, name):
    session, directory, _ = capture
    path = directory / name
    original = path.read_bytes()
    with pytest.raises(MigrationRefused), session.payload_read_view() as reader:
        path.write_bytes(original + b" ")
        with pytest.raises(MigrationRefused), reader.open_payload(ASSET):
            pass
        path.write_bytes(original)
        with pytest.raises(MigrationRefused), reader.open_payload(ASSET):
            pass


@pytest.mark.parametrize(
    "field",
    [
        "snapshot",
        "audit",
        "identifiers",
        "root",
        "bindings",
        "manifest",
        "manifest_bytes",
    ],
)
def test_view_rechecks_current_memory_associations_and_keeps_caught_failure(
    capture, monkeypatch, field
):
    session, _, path = capture
    if field == "snapshot":
        attribute = "_snapshot"
        changed = session.snapshot.model_copy(update={"collection_title": "Changed"})
    elif field == "audit":
        attribute = "_audit"
        # Python equality treats False and zero alike; the capture encoding does not.
        changed = session._audit.model_copy(update={"atomic": 0})
    else:
        attribute = "_" + field
        changed = deepcopy(getattr(session, attribute))
        if field == "identifiers":
            changed["profile_version"] = "changed"
        elif field == "root":
            changed += "changed"
        elif field == "bindings":
            changed[ASSET] = "payload/foreign.bin"
        elif field == "manifest":
            changed["files"][0]["actual_length"] += 1
        else:
            changed += b" "
    with (
        pytest.raises(MigrationRefused),
        session.payload_read_view() as reader,
        reader.open_payload(ASSET) as stream,
    ):
        assert stream.read(1) == b"A"
        with monkeypatch.context() as fault:
            fault.setattr(session, attribute, changed)
            with pytest.raises(MigrationRefused):
                stream.read(1)
        with pytest.raises(MigrationRefused):
            stream.read(1)
    assert path.read_bytes() == RAW


@pytest.mark.parametrize(
    "equivalent", ["order", "sequence", "string", "manifest_bytes"]
)
def test_view_retains_canonical_context_equivalences(capture, monkeypatch, equivalent):
    class Text(str):
        pass

    session, _, path = capture
    with (
        session.payload_read_view() as reader,
        reader.open_payload(ASSET) as stream,
    ):
        assert stream.read(1) == b"A"
        with monkeypatch.context() as change:
            if equivalent == "order":
                change.setattr(
                    session,
                    "_identifiers",
                    dict(reversed(session._identifiers.items())),
                )
            elif equivalent == "sequence":
                manifest = deepcopy(session._manifest)
                manifest["files"] = tuple(manifest["files"])
                change.setattr(session, "_manifest", manifest)
            elif equivalent == "string":
                change.setattr(session, "_root", Text(session._root))
            else:
                change.setattr(
                    session, "_manifest_bytes", bytearray(session._manifest_bytes)
                )
            assert stream.read() == b"\nB\n"
    assert path.read_bytes() == RAW


def test_view_preserves_manifest_hex_observation_when_bytes_type_changes(
    capture, monkeypatch
):
    class UpperHex(bytes):
        def hex(self):
            return super().hex().upper()

    session, _, path = capture
    original = session._manifest_bytes
    encoded = UpperHex(original)
    assert encoded.hex() != original.hex()
    monkeypatch.setattr(session, "_manifest_bytes", encoded)
    with (
        pytest.raises(MigrationRefused),
        session.payload_read_view() as reader,
        reader.open_payload(ASSET) as stream,
    ):
        assert stream.read(1) == b"A"
        with monkeypatch.context() as change:
            change.setattr(session, "_manifest_bytes", original)
            with pytest.raises(MigrationRefused):
                stream.read(1)
        with pytest.raises(MigrationRefused):
            stream.read(1)
    assert path.read_bytes() == RAW


def test_view_rejects_nesting_concurrent_use_reentry_and_escaped_access(capture):
    session, _, _ = capture
    view = session.payload_read_view()
    with pytest.raises(MigrationRefused), view.open_payload(ASSET):
        pass
    # The unopened failed object cannot be revived.
    with pytest.raises(MigrationRefused), view:
        pytest.fail("Admission must fail before yielding a failed view")
    view = session.payload_read_view()
    with view as reader:
        with pytest.raises(MigrationRefused), session.payload_read_view():
            pass
        with reader.open_payload(ASSET) as stream:
            assert stream.read() == RAW
    assert stream.closed
    with pytest.raises(MigrationRefused):
        stream.read()
    with pytest.raises(MigrationRefused), view:
        pass
    with pytest.raises(MigrationRefused), view.open_payload(ASSET):
        pass
    with (
        pytest.raises(MigrationRefused),
        session.payload_read_view() as reader,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        future = pool.submit(lambda: reader.open_payload(ASSET).__enter__())
        with pytest.raises(MigrationRefused):
            future.result()


def test_session_closure_revokes_view_and_open_stream_before_cleanup(capture):
    session, _, _ = capture
    view = session.payload_read_view()
    reader = view.__enter__()
    context = reader.open_payload(ASSET)
    stream = context.__enter__()
    assert stream.read(1) == b"A"
    session.close()
    assert stream.closed and session.closed
    with pytest.raises(MigrationRefused):
        stream.read()
    context.__exit__(None, None, None)
    with pytest.raises(MigrationRefused):
        view.__exit__(None, None, None)


@pytest.mark.parametrize("operation", ["verify", "standalone", "exit"])
def test_view_keeps_complete_checks_forceful_for_unrequested_same_stat_corruption(
    tmp_path, monkeypatch, operation
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with api_server(FilePayloadApi()) as (_, origin):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=origin), credentials=lambda: KEY, profile_version="4"
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            identity = session.source_identity
            directory = next(tmp_path.glob("brz2obsidian-api-*"))
            manifest = json.loads((directory / "manifest.json").read_bytes())
            bindings = {
                row["asset_id"]: row["storage_key"]
                for row in manifest["payload_bindings"]
            }
            unrequested = directory / bindings[FILE]
            before = unrequested.stat()
            try:
                with (
                    pytest.raises(MigrationRefused),
                    session.payload_read_view() as reader,
                ):
                    unrequested.write_bytes(bytes([PNG[0] ^ 1]) + PNG[1:])
                    os.utime(unrequested, ns=(before.st_atime_ns, before.st_mtime_ns))
                    assert unrequested.stat().st_size == before.st_size
                    if operation == "verify":
                        with pytest.raises(MigrationRefused):
                            session.verify_consistency()
                    elif operation == "standalone":
                        with (
                            pytest.raises(MigrationRefused),
                            session.open_payload(NOTE),
                        ):
                            pytest.fail(
                                "Standalone access must still scan unrequested files"
                            )
                    if operation != "exit":
                        unrequested.write_bytes(PNG)
                        with pytest.raises(MigrationRefused), reader.open_payload(NOTE):
                            pytest.fail(
                                "Caught explicit failure must poison its active view"
                            )
            finally:
                unrequested.write_bytes(PNG)
            assert session.source_identity == identity


@pytest.mark.parametrize("when", ["entry", "active"])
def test_replaced_capture_root_remains_caller_owned_and_view_cannot_read_it(
    capture, tmp_path, when
):
    session, directory, _ = capture
    saved = tmp_path / "original-capture"

    def replace():
        directory.rename(saved)
        directory.mkdir()
        (directory / "caller-owned.txt").write_bytes(b"Caller-owned replacement")

    with pytest.raises(MigrationRefused):
        if when == "entry":
            replace()
        with session.payload_read_view() as reader:
            assert when == "active"
            replace()
            with reader.open_payload(ASSET):
                pytest.fail("A replaced root must not yield payload bytes")
    with pytest.raises(MigrationFailed):
        session.close()
    assert (directory / "caller-owned.txt").read_bytes() == b"Caller-owned replacement"
    assert (saved / "payload/0000000000000001.bin").read_bytes() == RAW


def test_view_preserves_partial_reads_and_valid_early_close(capture):
    session, _, _ = capture
    with session.payload_read_view() as reader:
        with reader.open_payload(ASSET) as stream:
            assert stream.read(0) == b""
            assert stream.read(1) == b"A"
        assert stream.closed
        with reader.open_payload(ASSET) as stream:
            assert stream.read(2) == b"A\n"
            assert stream.read(2) == b"B\n"
            assert stream.read(2) == b""
    with session.open_payload(ASSET) as stream:
        assert stream.read() == RAW


@pytest.mark.parametrize("target", ["metadata.json", "payload/0000000000000001.bin"])
def test_filesystem_read_failure_poisoning_survives_caught_io_and_retry(
    capture, monkeypatch, target
):
    session, directory, _ = capture
    real_open = Path.open
    armed = False

    def failed_open(path, *args, **kwargs):
        if armed and path == directory / target and (args and args[0] == "rb"):
            raise OSError("PRIVATE_FILESYSTEM_CANARY")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failed_open)
    with pytest.raises(MigrationRefused), session.payload_read_view() as reader:
        armed = True
        with pytest.raises(MigrationFailed) as caught, reader.open_payload(ASSET):
            pass
        assert "CANARY" not in str(caught.value)
        armed = False
        with pytest.raises(MigrationRefused), reader.open_payload(ASSET):
            pass


def test_selected_open_cannot_substitute_an_unowned_file_descriptor(
    capture, tmp_path, monkeypatch
):
    session, _, selected = capture
    foreign = tmp_path / "caller-owned.bin"
    foreign.write_bytes(RAW)
    real_open = Path.open
    armed = False

    def retargeted_open(path, *args, **kwargs):
        if armed and path == selected and args and args[0] == "rb":
            return real_open(foreign, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", retargeted_open)
    with pytest.raises(MigrationRefused), session.payload_read_view() as reader:
        armed = True
        with pytest.raises(MigrationRefused), reader.open_payload(ASSET):
            pytest.fail("Matching bytes do not give an unowned descriptor authority")
        armed = False
    assert foreign.read_bytes() == RAW


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction ownership")
@pytest.mark.parametrize("replacement", ["directory", "junction"])
def test_view_refuses_replaced_payload_directory_and_cleanup_preserves_caller(
    capture, tmp_path, replacement
):
    session, directory, _ = capture
    caller = tmp_path / "caller"
    caller.mkdir()
    foreign = caller / "0000000000000001.bin"
    foreign.write_bytes(RAW)
    saved = tmp_path / "original-payload"
    with pytest.raises(MigrationRefused), session.payload_read_view() as reader:
        (directory / "payload").rename(saved)
        if replacement == "junction":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(directory / "payload"), str(caller)],
                check=True,
                capture_output=True,
            )
        else:
            (directory / "payload").mkdir()
            (directory / "payload/0000000000000001.bin").write_bytes(RAW)
        with reader.open_payload(ASSET):
            pytest.fail("A replacement cannot redirect selected payload reads")
    session.close()
    assert foreign.read_bytes() == RAW
    assert (saved / "0000000000000001.bin").read_bytes() == RAW


def test_view_rejected_at_nested_admission_cannot_later_be_revived(capture):
    session, _, _ = capture
    rejected = session.payload_read_view()
    with session.payload_read_view(), pytest.raises(MigrationRefused):
        rejected.__enter__()
    try:
        rejected.__enter__()
    except MigrationRefused:
        return
    else:
        rejected.__exit__(None, None, None)
        pytest.fail("A rejected view cannot later regain read authority")


def test_view_entry_filesystem_failure_is_typed_and_releases_admission(
    capture, monkeypatch
):
    session, directory, _ = capture
    real_open, real_lstat = Path.open, Path.lstat
    observed_metadata = False

    def observe_open(path, *args, **kwargs):
        nonlocal observed_metadata
        if path == directory / "source.json" and args and args[0] == "rb":
            observed_metadata = True
        return real_open(path, *args, **kwargs)

    def inaccessible_payload_directory(path, *args, **kwargs):
        if observed_metadata and path == directory / "payload":
            raise OSError("PRIVATE_ENTRY_CANARY")
        return real_lstat(path, *args, **kwargs)

    rejected = session.payload_read_view()
    with monkeypatch.context() as faults:
        faults.setattr(Path, "open", observe_open)
        faults.setattr(Path, "lstat", inaccessible_payload_directory)
        with pytest.raises(MigrationFailed) as caught:
            rejected.__enter__()
        assert "CANARY" not in str(caught.value)
    with pytest.raises(MigrationRefused):
        rejected.__enter__()
    with session.payload_read_view() as reader, reader.open_payload(ASSET) as stream:
        assert stream.read() == RAW


@pytest.mark.parametrize(
    "misuse",
    ["unknown", "nested", "closed_stream", "escaped_context", "wrong_thread_close"],
)
def test_failed_view_authority_is_finite_and_releases_for_a_new_view(capture, misuse):
    session, _, _ = capture
    view = session.payload_read_view()
    with pytest.raises(MigrationRefused), view as reader:
        if misuse == "unknown":
            with pytest.raises(MigrationRefused), reader.open_payload("unknown"):
                pass
        elif misuse == "wrong_thread_close":
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(lambda: view.__exit__(None, None, None))
                with pytest.raises(MigrationRefused):
                    future.result()
        elif misuse == "escaped_context":
            context = reader.open_payload(ASSET)
            stream = context.__enter__()
            assert stream.read(1) == b"A"
        else:
            with reader.open_payload(ASSET) as stream:
                if misuse == "nested":
                    with pytest.raises(MigrationRefused), reader.open_payload(ASSET):
                        pass
                else:
                    stream.close()
                    with pytest.raises(MigrationRefused):
                        stream.read()
    if misuse == "escaped_context":
        assert stream.closed
        context.__exit__(None, None, None)
    with session.payload_read_view() as reader, reader.open_payload(ASSET) as stream:
        assert stream.read() == RAW


@pytest.mark.parametrize(
    "profile,source_hash",
    [
        ("1", "4e71f6e3b436723930602368ef0b975d55ecc517f41e540972af27f39b10d5ef"),
        ("2", "9ccb054d805e16b695ed35d477f2f660a7ac4e8308287b4e53790b872aed69e6"),
        ("3", "a504e0046f89fad35ab965bf42746e1aa747b72612f8f76c829525f84c3c1bc4"),
    ],
)
def test_historical_profile_replay_view_keeps_literal_bytes_and_identity(
    tmp_path, profile, source_hash
):
    source, snapshot, audit, payloads = golden_inputs(profile)
    session = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        profile_version=profile,
        capture_parent=tmp_path,
    )
    try:
        identity = session.source_identity
        assert identity.source_sha256 == source_hash
        with (
            session.payload_read_view() as reader,
            reader.open_payload(ASSET) as stream,
        ):
            assert stream.read() == RAW
        assert session.source_identity == identity
        with session.open_payload(ASSET) as stream:
            assert stream.read() == RAW
        session.verify_consistency()
    finally:
        session.close()


@pytest.mark.parametrize(
    "primary,secondary,secondary_code",
    [
        ("read", "close", "api_payload_read_failed"),
        ("read", "final_io", "api_capture_read_failed"),
        ("read", "final_integrity", "invalid_source"),
        ("interrupt", "final_io", "api_capture_read_failed"),
        ("escaped", "final_io", "api_capture_read_failed"),
    ],
)
def test_view_retains_primary_failure_and_safe_secondary_closure_findings(
    capture, monkeypatch, primary, secondary, secondary_code
):
    session, _, selected = capture
    real_open = Path.open
    signal = KeyboardInterrupt()
    state = {
        "armed": False,
        "primary": False,
        "secondary": False,
        "closing": False,
        "final_opens": 0,
    }
    raw_streams = []

    class FaultyFile:
        def __init__(self, raw):
            self.raw = raw

        def __getattr__(self, name):
            return getattr(self.raw, name)

        def read(self, size):
            if not state["primary"]:
                state["primary"] = True
                if primary == "interrupt":
                    raise signal
                if primary != "escaped":
                    raise OSError("PRIVATE_READ_CANARY")
            return self.raw.read(size)

        def close(self):
            if primary == "escaped" and not state["closing"]:
                state["closing"] = True
                raise OSError("PRIVATE_ESCAPED_CLOSE_CANARY")
            if secondary == "close" and not state["secondary"]:
                state["secondary"] = True
                raise OSError("PRIVATE_CLOSE_CANARY")
            self.raw.close()
            if secondary == "final_integrity" and not state["secondary"]:
                state["secondary"] = True
                selected.write_bytes(b"X\nB\n")

    def fault_open(path, *args, **kwargs):
        if state["armed"] and path == selected and args and args[0] == "rb":
            if state["primary"]:
                state["final_opens"] += 1
                if secondary == "final_io" and not state["secondary"]:
                    state["secondary"] = True
                    raise OSError("PRIVATE_FINAL_CANARY")
                return real_open(path, *args, **kwargs)
            raw = real_open(path, *args, **kwargs)
            raw_streams.append(raw)
            return FaultyFile(raw)
        return real_open(path, *args, **kwargs)

    expected = KeyboardInterrupt if primary == "interrupt" else MigrationFailed
    try:
        with monkeypatch.context() as faults:
            faults.setattr(Path, "open", fault_open)
            with (
                pytest.raises(expected) as caught,
                session.payload_read_view() as reader,
            ):
                # Entry completes unmodified; inject only at the public selected
                # stream and the subsequent fresh full-check descriptor.
                state["armed"] = True
                if primary == "escaped":
                    context = reader.open_payload(ASSET)
                    stream = context.__enter__()
                    assert stream.read(1) == b"A"
                else:
                    with reader.open_payload(ASSET) as stream:
                        stream.read(1)
        assert state["primary"] and state["secondary"] and state["final_opens"]
        if primary == "interrupt":
            assert caught.value is signal
            assert secondary_code in " ".join(caught.value.__notes__)
        else:
            assert [issue.code for issue in caught.value.issues] == [
                "api_payload_read_failed",
                secondary_code,
            ]
            assert caught.value.issues[0].message == (
                "Captured payload stream could not close safely"
                if primary == "escaped"
                else "Captured payload could not be read safely"
            )
            assert "temporary-folder access" in caught.value.issues[0].guidance
        assert "CANARY" not in str(caught.value)
        assert "CANARY" not in " ".join(getattr(caught.value, "__notes__", ()))
    finally:
        selected.write_bytes(RAW)
        if primary == "escaped":
            context.__exit__(None, None, None)
    with session.payload_read_view() as reader, reader.open_payload(ASSET) as stream:
        assert stream.read() == RAW
    session.close()
    assert all(raw.closed for raw in raw_streams)
