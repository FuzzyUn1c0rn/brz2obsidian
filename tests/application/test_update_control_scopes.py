"""Live controls use the exact admitted closed command scope."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.transport import Supervisor


def test_handle_bound_controls_acknowledge_during_real_owned_edit_io(
    tmp_path, monkeypatch
):
    from brz2obsidian.application.protocol import encode_request
    from brz2obsidian.application.update_context import UpdateContext
    from brz2obsidian.application.update_stream import WorkerStreamDecoder
    from brz2obsidian.application.update_worker import UpdateWorker
    from tests.application.test_format_transition import transition_case
    from tests.support.recorded_format6 import CURRENT, FIXTURE, NOTE

    operations, vault, history = transition_case(tmp_path, monkeypatch)
    before = {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(
        operations,
        "read_checkpoint",
        lambda *args, **kwargs: SimpleNamespace(
            **(vars(history.checkpoint) | {"status": "valid"})
        ),
    )
    context = UpdateContext(operations=operations)
    opened = context.prepare(
        vault,
        selection_id=str(uuid4()),
        kind="format_transition",
        source=FIXTURE / "source.brz",
    )
    assert opened.binding is not None
    page = context.page(opened.binding, byte_limit=0)
    note = next(row for row in page.page.items if row.current_path == NOTE)
    offer = next(row for row in page.offers if row.change_id == note.change_id)
    assert "edited" in offer.choices
    edited = CURRENT + b"\r\nIndependently typed after control.\r\n"
    entered = {name: Event() for name in ("write_edit", "seal_edit")}
    release = {name: Event() for name in entered}
    created = []
    native_file = tempfile.TemporaryFile

    class OwnedFile:
        def __init__(self, actual):
            self.actual = actual

        def __enter__(self):
            self.actual.__enter__()
            return self

        def __exit__(self, *args):
            return self.actual.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.actual, name)

        def write(self, raw):
            count = self.actual.write(raw)
            entered["write_edit"].set()
            assert release["write_edit"].wait(5), "Owned edit write barrier exhausted"
            return count

        def read(self, size):
            raw = self.actual.read(size)
            if raw:
                entered["seal_edit"].set()
                assert release["seal_edit"].wait(5), "Owned edit seal barrier exhausted"
            return raw

    def create_owned(*args, **kwargs):
        actual = native_file(*args, **kwargs)
        created.append(actual)
        return OwnedFile(actual)

    monkeypatch.setattr(tempfile, "TemporaryFile", create_owned)
    draft = context.begin_edit(
        opened.binding,
        requirement_id=offer.requirement_id,
        size=len(edited),
        sha256=hashlib.sha256(edited).hexdigest(),
    )
    assert draft.edit is not None and len(created) == 1
    handle = draft.edit.handle
    input_read, input_write = os.pipe()
    output_read, output_write = os.pipe()
    incoming, commands = (
        os.fdopen(input_read, "rb"),
        os.fdopen(input_write, "wb", buffering=0),
    )
    replies, outgoing = (
        os.fdopen(output_read, "rb"),
        os.fdopen(output_write, "wb", buffering=0),
    )
    worker = UpdateWorker(context=context, output=outgoing)
    server = Thread(target=worker.serve, args=(incoming,), daemon=True)
    server.start()

    def response(request):
        decoder = WorkerStreamDecoder(request)
        assert decoder.feed(replies.readline()) is None
        return decoder.feed(replies.readline()).result

    try:
        for sequence, command in ((1, "write_edit"), (3, "seal_edit")):
            arguments = {"command": command, "handle": handle}
            if command == "write_edit":
                arguments.update(offset=0, data=edited)
            work = WorkerRequest(
                operation="update",
                request_id=str(uuid4()),
                sequence=sequence,
                arguments=arguments,
            )
            commands.write(encode_request(work))
            assert entered[command].wait(5)
            cancel = WorkerRequest(
                operation="update",
                request_id=str(uuid4()),
                sequence=sequence + 1,
                arguments={
                    "command": "cancel",
                    "binding": handle.binding,
                    "target_request_id": work.request_id,
                    "target_sequence": sequence,
                },
            )
            commands.write(encode_request(cancel))
            assert (
                response(cancel).code == "cancellation_requested"
                and not release[command].is_set()
            )
            release[command].set()
            actual = response(work)
            assert actual.code == (
                "edit_chunk_accepted" if command == "write_edit" else "edit_sealed"
            )
            assert actual.edit.received_bytes == len(edited)
            assert actual.edit.sealed is (command == "seal_edit")
            assert actual.draft_pending and not actual.ready
    finally:
        for barrier in release.values():
            barrier.set()
        commands.close()
        server.join(5)
        incoming.close()
        outgoing.close()
        replies.close()
    assert not server.is_alive()
    chosen = context.choose(
        handle.binding,
        requirement_id=offer.requirement_id,
        choice="edited",
        assumptions_digest=offer.assumptions_digest,
        edit_handle=handle,
    )
    assert chosen.code == "accepted" and not context.draft_pending
    shown = context.page(chosen.binding)
    assert (
        next(row for row in shown.page.items if row.current_path == NOTE).result
        == edited
    )
    assert all(actual.closed for actual in created)
    assert (vault / NOTE).read_bytes() == CURRENT
    assert {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file()
    } == before


@pytest.mark.parametrize("command", ("load", "resume", "history"))
def test_real_channel_cancels_unbound_read_scope_while_native_inspection_waits(
    tmp_path, monkeypatch, command
):
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-285-control-"))
    owner = {"owner": uuid4().hex, "root": str(root.resolve())}
    (root / ".fixture-owner.json").write_text(json.dumps(owner), encoding="utf-8")
    evidence = Path(__file__).resolve().parents[2] / "tmp/issue-285/control-fixtures"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (owner["owner"] + ".json")).write_text(
        json.dumps(owner), encoding="utf-8"
    )
    vault = root / "vault"
    vault.mkdir()
    raw = b"Personal bytes\r\n"
    (vault / "Personal.md").write_bytes(raw)
    entered, release = root / "entered", root / "release"
    driver = root / "blocked-read.py"
    driver.write_text(
        """import sys,time
from pathlib import Path
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_worker import UpdateWorker
command,entered,release,vault=sys.argv[1:]
entered,release,vault=map(Path,(entered,release,vault))
name='inspect_update_inputs' if command=='resume' else 'inspect_history'
native=getattr(Operations,name)
def blocked(self,path,**kwargs):
 assert Path(path).resolve()==vault.resolve()
 entered.write_text('actual native read entry',encoding='utf-8')
 deadline=time.monotonic()+10
 while not release.exists():
  if time.monotonic()>deadline: raise OSError('owned read barrier exhausted')
  time.sleep(.005)
 return native(self,path,**kwargs)
setattr(Operations,name,blocked)
UpdateWorker(output=sys.stdout.buffer).serve(sys.stdin.buffer)
""",
        encoding="utf-8",
    )
    launch = subprocess.Popen
    children = []

    def actual_child(argv, *args, **kwargs):
        assert argv[1:] == ["-m", "brz2obsidian.worker"]
        child = launch(
            [
                argv[0],
                "-u",
                str(driver),
                command,
                str(entered),
                str(release),
                str(vault),
            ],
            *args,
            **kwargs,
        )
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", actual_child)
    channel = Supervisor(
        Path(sys.executable), Path(__file__).resolve().parents[2] / "src"
    ).open_update()
    request = WorkerRequest(
        operation="update",
        request_id=str(uuid4()),
        sequence=1,
        arguments={
            "command": command,
            "vault": str(vault),
            "selection_id": str(uuid4()),
        },
    )
    answers = []
    work = Thread(target=lambda: answers.append(channel.run(request)), daemon=True)
    work.start()
    try:
        deadline = time.monotonic() + 5
        while not entered.exists():
            assert time.monotonic() < deadline, "Owned native-read diagnostic exhausted"
            time.sleep(0.005)
        ack = channel.cancel(None, target_request_id=request.request_id)
        assert (
            ack.phase == "completed"
            and ack.response.result.code == "cancellation_requested"
        )
        assert not release.exists() and work.is_alive()
        release.touch()
        work.join(10)
        assert not work.is_alive() and answers[0].phase == "completed"
        result = answers[0].response.result
        assert (
            result.status == "cancelled_before_publication"
            and result.publication == "not_published"
        )
        assert (
            not result.ready and result.binding is None and not result.history_retained
        )
        assert result.checkpoint_commit is None
    finally:
        release.touch()
        work.join(10)
        if answers and answers[0].response is not None and not channel.poisoned:
            terminal = channel.run(
                WorkerRequest(
                    operation="update",
                    request_id=str(uuid4()),
                    sequence=1,
                    arguments={
                        "command": "close",
                        "choice": "discard",
                        "binding": answers[0].response.result.binding,
                    },
                )
            )
            assert terminal.response.result.code == "context_closed"
        channel.close()
    assert len(children) == 1 and children[0].poll() == 0
    assert (vault / "Personal.md").read_bytes() == raw
    assert sorted(path.name for path in vault.iterdir()) == ["Personal.md"]
