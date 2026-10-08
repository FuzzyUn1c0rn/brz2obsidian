"""Hidden process supervision; callers run it outside their GUI thread."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Literal

from brz2obsidian.application.contracts import WorkerRequest, WorkerResponse
from brz2obsidian.application.protocol import (
    RESPONSE_LIMIT,
    STDERR_LIMIT,
    ProtocolFailure,
    decode_response,
    encode_request,
)


@dataclass(frozen=True)
class Terminal:
    phase: Literal["completed", "not_started", "may_have_executed"]
    response: WorkerResponse | None = None
    process_status: int | None = None
    code: (
        Literal[
            "launch_failure",
            "protocol_failure",
            "worker_failure",
            "operation_unavailable",
        ]
        | None
    ) = None


class Supervisor:
    def __init__(self, interpreter: Path, source_root: Path):
        if not interpreter.is_absolute() or not source_root.is_absolute():
            raise ValueError(
                "Explicit absolute interpreter and source paths are required"
            )
        self.interpreter, self.source_root = interpreter, source_root

    def run(self, request: WorkerRequest) -> Terminal:
        try:
            wire = encode_request(request)
        except ProtocolFailure:
            return Terminal(phase="not_started", code="protocol_failure")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.source_root)
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            process = subprocess.Popen(
                [str(self.interpreter), "-m", "brz2obsidian.worker"],
                cwd=str(self.source_root.parent),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError:
            return Terminal(phase="not_started", code="launch_failure")
        output, internal_stderr = bytearray(), bytearray()
        oversized = [False]
        drain_failed = [False]

        def drain(pipe, retained, limit, track_excess=False):
            try:
                with pipe:
                    while chunk := pipe.read(65536):
                        if len(retained) + len(chunk) > limit and track_excess:
                            oversized[0] = True
                        retained.extend(chunk[: max(0, limit - len(retained))])
            except OSError:
                drain_failed[0] = True

        readers = (
            Thread(target=drain, args=(process.stdout, output, RESPONSE_LIMIT, True)),
            Thread(target=drain, args=(process.stderr, internal_stderr, STDERR_LIMIT)),
        )
        for reader in readers:
            reader.start()
        write_failed = False
        try:
            process.stdin.write(wire)
            process.stdin.close()
        except OSError:
            write_failed = True
        status = process.wait()
        for reader in readers:
            reader.join()
        # Never persist, export or display stderr. Drain everything, retain only
        # the bounded transient buffer, then discard it with this invocation.
        internal_stderr.clear()
        if oversized[0] or drain_failed[0] or write_failed:
            return Terminal(
                phase="may_have_executed",
                process_status=status,
                code="protocol_failure",
            )
        try:
            response = decode_response(bytes(output), request)
        except ProtocolFailure:
            return Terminal(
                phase="may_have_executed",
                process_status=status,
                code="protocol_failure",
            )
        if response.protocol_error:
            return Terminal(
                phase="may_have_executed",
                process_status=status,
                code="operation_unavailable"
                if response.protocol_error.code == "operation_unavailable"
                else "worker_failure",
            )
        return Terminal(phase="completed", response=response, process_status=status)
