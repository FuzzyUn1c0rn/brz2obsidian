"""Public publication read-volume and frozen-capture lifetime controls."""

import hashlib
import json
import time
import tracemalloc
from pathlib import Path
from uuid import UUID

import pytest

from brz2obsidian.application import wiring
from brz2obsidian.contracts import MigrationFailed, MigrationRefused, SourceSnapshot
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from brz2obsidian.publication import publish
from brz2obsidian.sources.thebrain.local_api import (
    LOCAL_API_POLICY,
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceRef,
)
from tests.application.test_module_seams import METADATA
from tests.sources.test_local_api import golden_inputs
from tests.support.local_api import BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import NOTE, PayloadApi, attachment

ABC_SHA = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def payload_inventory(count):
    api = PayloadApi()
    api.payloads[NOTE] = b"abc"
    api.attachments[NOTE]["dataLength"] = 3
    for index in range(count):
        identity = str(UUID(int=0xB0000000000040008000000000000000 + index))
        api.attachments[identity] = attachment(
            identity, HOME, 15, f"file-{index}.txt", length=3
        )
        api.payloads[identity] = b"abc"
    return api


class ReadVolume:
    """Transparent filesystem instrumentation, independent of session internals."""

    def __init__(self, stream, record):
        self.stream, self.record = stream, record

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def read(self, *args):
        data = self.stream.read(*args)
        self.record["bytes"] += len(data)
        return data

    def readinto(self, buffer):
        length = self.stream.readinto(buffer)
        self.record["bytes"] += length
        return length


@pytest.mark.parametrize("file_count", [0, 12])
def test_public_conversion_bounds_frozen_capture_reads(
    tmp_path, monkeypatch, file_count
):
    api = payload_inventory(file_count)
    original_open = Path.open
    reads = {"bytes": 0}
    metadata_reads = {"bytes": 0}

    def measured_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if (
            "r" in mode
            and path.parent.name == "payload"
            and path.parent.parent.name.startswith("brz2obsidian-api-")
        ):
            return ReadVolume(stream, reads)
        if (
            "r" in mode
            and path.parent.name.startswith("brz2obsidian-api-")
            and path.suffix == ".json"
        ):
            return ReadVolume(stream, metadata_reads)
        return stream

    monkeypatch.setattr(Path, "open", measured_open)
    started = time.perf_counter()
    tracemalloc.start()
    try:
        with api_server(api) as (_, origin):
            result = wiring.local_api_workflow(
                LocalApiConfig(api_url=origin), credentials=lambda: KEY
            ).convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    (tmp_path / "read-volume.json").write_text(
        json.dumps(
            {
                "payload_files": len(api.payloads),
                "payload_bytes": sum(map(len, api.payloads.values())),
                "payload_bytes_read": reads["bytes"],
                "metadata_bytes_read": metadata_reads["bytes"],
                "seconds": time.perf_counter() - started,
                "tracemalloc_peak_bytes": peak,
                "limit": "Small synthetic observation, not large-source timing or memory proof",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    assert result.outcome == "clean", result.model_dump_json()
    outputs = list((tmp_path / "vault" / "Attachments").rglob("*.txt"))
    assert len(outputs) == file_count
    assert all(
        hashlib.sha256(path.read_bytes()).hexdigest() == ABC_SHA for path in outputs
    )
    # A constant allowance for retained full checks plus selected-file reads.
    # It does not depend on the number of open_payload calls or implementation
    # cache counters; the old per-open whole-capture pass exceeds it.
    assert reads["bytes"] <= 12 * sum(map(len, api.payloads.values())), reads


@pytest.mark.parametrize(
    "fault", ["restored_copy", "read", "close", "close_before", "closing_scan"]
)
def test_publication_view_faults_cannot_publish_complete_output(
    tmp_path, monkeypatch, fault
):
    source, snapshot, audit, payloads = golden_inputs()
    capture_parent = tmp_path / "captures"
    capture_parent.mkdir()
    session = LocalApiSession(
        source=source,
        snapshot=SourceSnapshot.model_validate_json(json.dumps(snapshot)),
        audit=audit,
        payloads=payloads,
        capture_parent=capture_parent,
    )
    capture = next(capture_parent.iterdir())
    selected = capture / "payload/0000000000000001.bin"
    original = b"A\nB\n"
    artifacts = render(plan(analyze(session.snapshot, LOCAL_API_POLICY)), METADATA)
    target_name = artifacts.copies[0].relative_path
    destination = tmp_path / "vault"
    real_open = Path.open
    state = {"injected": False, "copied": False}
    opened = []

    def copy_started():
        return any(
            (stage / target_name).exists() for stage in tmp_path.glob(".brz2obsidian-*")
        )

    class FaultyFile(ReadVolume):
        def read(self, *args):
            copying = copy_started() and not state["copied"]
            if not state["injected"] and copying:
                if fault == "read":
                    state["injected"] = True
                    raise OSError("PRIVATE_STREAM_CANARY")
                if fault == "restored_copy":
                    state["injected"] = True
                    selected.write_bytes(b"X\nB\n")
                    data = self.stream.read(*args)
                    selected.write_bytes(original)
                    return data
            data = self.stream.read(*args)
            if copying and not data:
                state["copied"] = True
            return data

        def close(self):
            if fault == "close_before" and copy_started() and not state["injected"]:
                state["injected"] = True
                raise OSError("PRIVATE_CLOSE_CANARY")
            self.stream.close()
            if fault == "close" and copy_started() and not state["injected"]:
                state["injected"] = True
                raise OSError("PRIVATE_CLOSE_CANARY")

    def fault_open(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if path == selected and mode == "rb":
            if fault == "closing_scan" and state["copied"] and not state["injected"]:
                state["injected"] = True
                path.write_bytes(b"X\nB\n")
            stream = real_open(path, *args, **kwargs)
            opened.append(stream)
            return FaultyFile(stream, {})
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fault_open)
    try:
        expected_error = (
            MigrationFailed
            if fault in {"read", "close", "close_before"}
            else MigrationRefused
        )
        with pytest.raises(expected_error) as caught:
            publish(artifacts, session, destination)
        assert state["injected"]
        if expected_error is MigrationFailed:
            issue = caught.value.issues[0]
            assert issue.code == "api_payload_read_failed"
            assert issue.guidance == (
                "An attachment in the temporary copy of the Brain could not be read completely. "
                "Check temporary-folder access. Save the diagnostic report and report the problem if it continues."
            )
            if fault == "read":
                assert issue.message == "Captured payload could not be read safely"
        assert caught.value.receipt is None
        assert "CANARY" not in str(caught.value)
        assert not destination.exists()
        assert not list(tmp_path.glob(".brz2obsidian-*"))
    finally:
        selected.write_bytes(original)
        session.close()
    assert all(stream.closed for stream in opened)
