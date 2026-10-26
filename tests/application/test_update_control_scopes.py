"""Live controls use the exact admitted closed command scope."""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Thread
from uuid import uuid4

import pytest

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.transport import Supervisor


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
