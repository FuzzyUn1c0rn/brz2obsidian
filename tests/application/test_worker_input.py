"""Cold Windows worker preparation and command framing through real processes."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

import pytest

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.protocol import decode_response, encode_request
from brz2obsidian.application.transport import Supervisor
from brz2obsidian.application.wiring import default_workflow
from tests.application.test_vault_checkpoints import git
from tests.application.test_verified_coverage import (
    add_attachment,
    change_record,
    source_parts,
    write_source,
)
from tests.support.local_api_payloads import PNG


@pytest.mark.skipif(os.name != "nt", reason="Windows native pipe/import interaction")
def test_cold_worker_prepares_image_archive_with_idle_control_pipe(tmp_path):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-worker-input-"))
    (tmp_path / "fixture-owner.json").write_text(
        json.dumps({"root": str(root), "owner": uuid4().hex}), encoding="utf-8"
    )
    parts = source_parts(root)
    add_attachment(parts, "66666666-6666-4666-8666-666666666666", 1, "red.png", PNG)
    # The absent inline image follows the real late native-decoder import path.
    note = b"Authored body.\r\n![Unavailable](.data/md-images/not-exported.png)\r\n"
    parts["22222222-2222-4222-8222-222222222222/Notes.md"] = note
    change_record(parts, "33333333-3333-4333-8333-333333333333", DataLength=len(note))
    source = write_source(root, parts)
    vault = root / "vault"
    converted = default_workflow().convert(source, vault)
    assert converted.receipt is not None and converted.receipt.verified
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "Independent authored baseline")
    before = {
        p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    }
    source_before = source.read_bytes()
    supervisor = Supervisor(Path(sys.executable), Path(__file__).parents[2] / "src")
    # One cold worker completes without a control message. A second receives a
    # cooperative cancel during preparation, before any Save or Apply exists.
    for cancel_preparation in (False, True):
        channel = supervisor.open_update()
        request = WorkerRequest(
            request_id=str(uuid4()),
            operation="update",
            sequence=1,
            arguments={
                "command": "prepare",
                "kind": "onboarding",
                "vault": str(vault),
                "source": str(source),
                "selection_id": str(uuid4()),
            },
        )
        results, progress = [], []
        entered = Event()

        def observe(_, value, progress=progress, entered=entered):
            progress.append(value)
            entered.set()

        def run(channel, request, results, observe):
            results.append(channel.run(request, on_progress=observe))

        work = Thread(
            target=run,
            args=(channel, request, results, observe),
            daemon=True,
        )
        work.start()
        try:
            if cancel_preparation:
                assert entered.wait(10), "Preparation must report its admission phase"
                ack = channel.cancel(None, target_request_id=request.request_id)
                assert ack.phase == "completed"
                assert ack.response.result.code == "cancellation_requested"
            work.join(60)
            assert not work.is_alive(), (
                "Cold preparation stalled with an idle control pipe"
            )
            assert len(results) == 1 and results[0].phase == "completed"
            opened = results[0].response.result
            assert progress and not opened.ready
            if cancel_preparation:
                assert opened.status == "cancelled_before_publication", opened
                assert opened.publication in ("not_started", "not_published")
            else:
                assert opened.status == "prepared_review" and opened.binding is not None
                assert opened.publication == "not_started"
            close = channel.run(
                WorkerRequest(
                    request_id=str(uuid4()),
                    operation="update",
                    sequence=1,
                    arguments={
                        "command": "close",
                        "binding": opened.binding,
                        "choice": "discard",
                    },
                )
            )
            assert close.phase == "completed"
            assert close.response.result.code == "context_closed"
        finally:
            # Only prepare/close are admitted; releasing input cannot stop a publisher.
            channel.close()
            work.join(10)
        assert channel.process_status == 0 and not work.is_alive()
    assert source.read_bytes() == source_before
    assert {
        p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    } == before


@pytest.mark.parametrize("input_kind", ("fragmented_pipe", "redirected_file"))
def test_worker_refuses_queued_continuation_before_inspecting_source(
    tmp_path, input_kind
):
    request = WorkerRequest(
        request_id=str(uuid4()),
        operation="inspect",
        arguments={
            "source_selection": {"kind": "brz", "path": str(tmp_path / "absent.brz")}
        },
    )
    wire = encode_request(request).removesuffix(b"\n") + b"\r\n" + b"unrequested\n"
    command = [sys.executable, "-m", "brz2obsidian.worker"]
    if input_kind == "fragmented_pipe":
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            process.stdin.write(wire[:13])
            process.stdin.flush()
            stdout, stderr = process.communicate(input=wire[13:], timeout=15)
        finally:
            if process.poll() is None:
                # This one-shot inspect request cannot publish content.
                process.kill()
                process.communicate(timeout=5)
        returncode = process.returncode
    else:
        path = tmp_path / "request.bin"
        path.write_bytes(wire)
        with path.open("rb") as incoming:
            completed = subprocess.run(
                command, stdin=incoming, capture_output=True, timeout=15, check=False
            )
        stdout, stderr, returncode = (
            completed.stdout,
            completed.stderr,
            completed.returncode,
        )
    response = decode_response(stdout, request)
    assert returncode == 1 and response.result is None
    assert response.protocol_error.code == "invalid_request" and stderr == b""
    assert not (tmp_path / "absent.brz").exists()
