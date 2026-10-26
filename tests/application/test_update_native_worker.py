"""One fresh tiny native graph joins correlated controls to actual durable state."""

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

from brz2obsidian.application.contracts import WorkerRequest
from brz2obsidian.application.transport import Supervisor
from tests.application.test_attachment_cleanup_history import (
    completed_native_ownership_case,
)
from tests.application.test_attachment_cleanup_lifecycle import user_git

_DRIVER = """import json,os,subprocess,sys,time
from pathlib import Path
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_worker import UpdateWorker
from brz2obsidian.publication.vault_replace import move_file
root,vault=map(Path,sys.argv[1:3])
started=time.monotonic()
children=[]
peak_processes=1
worker_complete=False
probe_info={}
launch_init=subprocess.Popen.__init__
def popen_init(self,*args,**kwargs):
 global peak_processes
 launch_init(self,*args,**kwargs)
 children.append(self)
 peak_processes=max(peak_processes,1+sum(p.poll() is None for p in children))
subprocess.Popen.__init__=popen_init
def write_json(path,value):
 temporary=path.with_suffix(path.suffix+'.tmp')
 temporary.write_text(json.dumps(value),encoding='utf-8')
 deadline=time.monotonic()+2
 while True:
  try:
   os.replace(temporary,path)
   return
  except PermissionError:
   if time.monotonic()>=deadline: raise
   time.sleep(.005)
def metrics():
 write_json(root/('resources-'+str(os.getpid())+'.json'),{
  'worker_pid':os.getpid(),'launcher_pid':os.getppid(),
  'worker_complete':worker_complete,'popen_class_identity':isinstance(subprocess.Popen,type),
  'worker_exit_code':globals().get('code',0 if worker_complete and probe_info.get('probe_ready') else None),
  'launched_child_processes':len(children),
  'peak_observed_live_worker_and_children':peak_processes,
  'live_children':sum(p.poll() is None for p in children),
  'elapsed_seconds':time.monotonic()-started,**probe_info})
def wait_for_release(name):
 deadline=time.monotonic()+20
 while not (root/(name+'-release')).exists():
  if time.monotonic()>deadline: raise OSError('owned native return barrier exhausted')
  time.sleep(.005)
def barrier(name,facts):
 metrics()
 write_json(root/(name+'-entered.json'),facts)
 wait_for_release(name)
capture=Operations.capture_checkpoint
def real_capture(self,*args,**kwargs):
 result=capture(self,*args,**kwargs)
 barrier('capture',json.loads(result.model_dump_json()))
 return result
Operations.capture_checkpoint=real_capture
class ActualFiles:
 def move(self,stage,target,*,replace):
  move_file(stage,target,replace=replace)
 def remove(self,target,destination):
  assert target==vault/'Assets/remove.bin'
  destination.parent.mkdir(parents=True,exist_ok=True)
  move_file(target,destination,replace=False)
  barrier('remove',{'target':str(target),'absent':not target.exists()})
 def directory(self,stage,target):
  move_file(stage,target,replace=False)
metrics()
if sys.argv[3:]==['--probe']:
 from brz2obsidian.publication.git_read import _SuspendedPopen,read_git
 result=read_git(['git','--version'],env=os.environ.copy())
 assert result.returncode==0
 probe_info.update(probe_ready=True,git_subclass_identity=issubclass(_SuspendedPopen,subprocess.Popen),git_version=result.stdout.decode().strip())
 metrics()
 wait_for_release('probe')
 worker_complete=True
 metrics()
 raise SystemExit(0)
code=UpdateWorker(context=UpdateContext(operations=Operations(vault_executor=ActualFiles())),output=sys.stdout.buffer).serve(sys.stdin.buffer)
worker_complete=True
metrics()
raise SystemExit(code)
"""


class _MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t)
        for name in (
            "PeakWorkingSetSize",
            "WorkingSetSize",
            "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage",
            "PagefileUsage",
            "PeakPagefileUsage",
        )
    ]


def _write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    deadline = time.monotonic() + 2
    while True:
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.005)


def _driver_metrics(root, launchers):
    if root is None:
        return ()
    owned = {process.pid for process in tuple(launchers)}
    rows = []
    for path in root.glob("resources-*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row["worker_pid"] in owned or row["launcher_pid"] in owned:
            rows.append(row)
    return tuple(rows)


def _memory_sample(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_MemoryCounters),
        wintypes.DWORD,
    )
    handle = kernel.OpenProcess(0x0410, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        value = _MemoryCounters()
        value.cb = ctypes.sizeof(value)
        if not psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(value), ctypes.sizeof(value)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return {
            "pid": pid,
            "rss": value.WorkingSetSize,
            "os_peak_working_set": value.PeakWorkingSetSize,
        }
    finally:
        kernel.CloseHandle(handle)


def test_native_driver_probe_preserves_git_class_and_maps_actual_worker_pid(tmp_path):
    root = tmp_path / "probe"
    root.mkdir()
    driver = root / "worker.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            str(driver),
            str(root),
            str(root / "unused-vault"),
            "--probe",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        deadline = time.monotonic() + 10
        metrics = None
        while metrics is None:
            for candidate in _driver_metrics(root, (process,)):
                if candidate.get("probe_ready"):
                    metrics = candidate
            assert process.poll() is None, process.communicate()[1].decode("utf-8")
            assert time.monotonic() < deadline, (
                "Owned driver probe diagnostic exhausted"
            )
            time.sleep(0.01)
        assert metrics["popen_class_identity"] and metrics["git_subclass_identity"]
        assert (
            metrics["launched_child_processes"] == 1 and metrics["live_children"] == 0
        )
        assert metrics["git_version"].startswith("git version ")
        actual_pid = metrics["worker_pid"]
        assert actual_pid == process.pid or metrics["launcher_pid"] == process.pid
        memory = _memory_sample(actual_pid)
        assert memory["pid"] == actual_pid and memory["rss"] > 0
        assert memory["os_peak_working_set"] >= memory["rss"]
        (root / "probe-release").touch()
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0 and stdout == b"" and stderr == b""
        final = _driver_metrics(root, (process,))[0]
        assert final["worker_complete"] and final["worker_exit_code"] == 0
        assert not (root / "unused-vault").exists()
    finally:
        (root / "probe-release").touch()
        if process.poll() is None:
            process.communicate(timeout=15)


def test_hidden_worker_real_capture_and_file_stop_reopen_from_exact_native_history(
    tmp_path, monkeypatch
):
    started = time.monotonic()
    phase_log = tmp_path / "phase.json"

    def phase(name, **facts):
        _write_json(
            phase_log,
            {"phase": name, "elapsed_seconds": time.monotonic() - started, **facts},
        )

    case_completed = False
    try:
        phase("fresh_tiny_native_seed")
        manual = b"Before [[Assets/remove.bin|old]] after.\r\n`[[Assets/remove.bin|code]]`\r\n"
        vault, source, original, _, _, before_git = completed_native_ownership_case(
            manual=manual
        )
        owner = json.loads(
            (vault.parent / ".fixture-owner.json").read_text(encoding="utf-8")
        )
        assert owner["root"] == str(vault.parent.resolve()) and owner["owner"]
        root = vault.parent / "285-hidden-native"
        root.mkdir()
        driver = root / "worker.py"
        driver.write_text(_DRIVER, encoding="utf-8")

        def storage():
            files = tuple(path for path in vault.parent.rglob("*") if path.is_file())
            history = tuple(
                path for path in (vault / ".brz2obsidian").rglob("*") if path.is_file()
            )
            git_files = tuple(
                path for path in (vault / ".git").rglob("*") if path.is_file()
            )
            return {
                "file_count": len(files),
                "logical_bytes": sum(path.stat().st_size for path in files),
                "converter_metadata_logical_bytes": sum(
                    path.stat().st_size for path in history
                ),
                "converter_metadata_path": ".brz2obsidian",
                "git_directory_logical_bytes": sum(
                    path.stat().st_size for path in git_files
                ),
            }

        before_storage = storage()
        children, samples, sample_errors, safe_responses = [], [], [], []
        launch = subprocess.Popen

        def child(argv, *args, **kwargs):
            assert argv[1:] == ["-m", "brz2obsidian.worker"]
            process = launch(
                [argv[0], "-u", str(driver), str(root), str(vault)], *args, **kwargs
            )
            children.append(process)
            return process

        monkeypatch.setattr(subprocess, "Popen", child)
        sampling_done = Event()

        def sample():
            while not sampling_done.wait(0.2):
                for row in _driver_metrics(root, children):
                    if row["worker_complete"]:
                        continue
                    try:
                        samples.append(_memory_sample(row["worker_pid"]))
                    except OSError as error:
                        latest = next(
                            value
                            for value in _driver_metrics(root, children)
                            if value["worker_pid"] == row["worker_pid"]
                        )
                        if not latest["worker_complete"]:
                            sample_errors.append(
                                {"pid": row["worker_pid"], "error": error.winerror}
                            )

        sampler = Thread(target=sample, daemon=True)
        sampler.start()
        supervisor = Supervisor(
            Path(sys.executable), Path(__file__).resolve().parents[2] / "src"
        )
        channel = None
        partial_index = 0

        def partial_report():
            nonlocal partial_index
            partial_index += 1
            raw_process_metrics = _driver_metrics(root, children)
            try:
                current_storage = storage()
            except OSError:
                current_storage = {"unavailable_during_operation": True}
            snapshot = {
                "qualification_completed": False,
                "elapsed_seconds": time.monotonic() - started,
                "last_phase": json.loads(phase_log.read_text(encoding="utf-8")),
                "launcher_pids": [process.pid for process in children],
                "worker_pids": [row["worker_pid"] for row in raw_process_metrics],
                "launcher_exit_codes": [process.poll() for process in children],
                "worker_exit_codes": [
                    row["worker_exit_code"] for row in raw_process_metrics
                ],
                "worker_samples": samples,
                "rss_sample_errors": sample_errors,
                "raw_driver_process_metrics": raw_process_metrics,
                "safe_responses": safe_responses,
                "storage_before_worker": before_storage,
                "storage_at_snapshot": current_storage,
                "limits": "Partial observation before a possibly blocking join/close; no native outcome is inferred.",
            }
            path = tmp_path / (
                "native-worker-resource-partial-" + str(partial_index) + ".json"
            )
            _write_json(path, snapshot)

        def record_response(command, response):
            safe_responses.append(
                {
                    "command": command,
                    "response": response.model_dump(mode="json", by_alias=True),
                }
            )
            _write_json(root / "safe-responses.json", safe_responses)

        def call(arguments):
            terminal = channel.run(
                WorkerRequest(
                    operation="update",
                    request_id=str(uuid4()),
                    sequence=1,
                    arguments=arguments,
                )
            )
            assert (
                terminal.phase == "completed"
                and terminal.response.protocol_error is None
            )
            record_response(arguments["command"], terminal.response)
            return terminal.response.result

        def controlled(arguments, name):
            request = WorkerRequest(
                operation="update",
                request_id=str(uuid4()),
                sequence=1,
                arguments=arguments,
            )
            results = []
            work = Thread(
                target=lambda: results.append(channel.run(request)), daemon=True
            )
            work.start()
            try:
                deadline = time.monotonic() + 120
                marker = root / (name + "-entered.json")
                while not marker.exists():
                    assert work.is_alive() and time.monotonic() < deadline, (
                        "Owned native phase diagnostic exhausted"
                    )
                    time.sleep(0.01)
                physical = json.loads(marker.read_text(encoding="utf-8"))
                if name == "remove":
                    assert (
                        physical["absent"]
                        and not (vault / "Assets/remove.bin").exists()
                    )
                    assert (vault / "Manual.md").read_bytes() == manual
                ack = channel.cancel(
                    arguments["binding"], target_request_id=request.request_id
                )
                assert (
                    ack.phase == "completed"
                    and ack.response.result.code == "cancellation_requested"
                )
                assert work.is_alive() and not results
                (root / (name + "-release")).touch()
                work.join(90)
                assert not work.is_alive() and len(results) == 1
                assert results[0].phase == "completed"
                record_response(arguments["command"], results[0].response)
                return results[0].response.result, physical
            finally:
                (root / (name + "-release")).touch()
                partial_report()
                work.join(90)

        try:
            phase("worker_review", vault=str(vault), owner=owner["owner"])
            channel = supervisor.open_update()
            opened = call(
                {
                    "command": "prepare",
                    "kind": "attachment_cleanup",
                    "vault": str(vault),
                    "source": None,
                    "selection_id": str(uuid4()),
                }
            )
            assert opened.binding is not None, (opened.status, opened.code)
            offer = call({"command": "choices", "binding": opened.binding}).offers[0]
            references = call(
                {
                    "command": "references",
                    "binding": opened.binding,
                    "requirement_id": offer.requirement_id,
                }
            ).references
            assert len(references) == 1 and "remove" in offer.choices
            chosen = call(
                {
                    "command": "choose",
                    "binding": opened.binding,
                    "requirement_id": offer.requirement_id,
                    "choice": "remove",
                    "assumptions_digest": offer.assumptions_digest,
                    "references": tuple(
                        {"reference_id": row.reference_id, "choice": "drop"}
                        for row in references
                    ),
                }
            )
            assert chosen.ready
            phase("actual_capture_return")
            saved, physical_capture = controlled(
                {"command": "save", "binding": chosen.binding}, "capture"
            )
            assert (
                saved.code == "saved"
                and saved.history_retained
                and saved.capture.status == "captured"
            )
            assert (
                saved.capture.commit
                == physical_capture["commit"]
                == saved.binding.checkpoint_commit
            )
            assert (
                saved.capture.object_storage == "verified"
                and not saved.capture.authored_files_changed
            )
            assert (vault / "Manual.md").read_bytes() == manual
            closed = call(
                {"command": "close", "binding": saved.binding, "choice": "discard"}
            )
            assert (
                closed.history_retained
                and closed.capture.commit == saved.capture.commit
            )
            channel.close()
            phase("fresh_saved_review")
            channel = supervisor.open_update()
            selection = str(uuid4())
            loaded = call(
                {"command": "load", "vault": str(vault), "selection_id": selection}
            )
            assert (
                not loaded.ready and loaded.binding is None and loaded.history_retained
            )
            resumed = call(
                {"command": "resume", "vault": str(vault), "selection_id": selection}
            )
            assert (
                resumed.ready
                and resumed.binding.checkpoint_commit == saved.capture.commit
            )
            assert resumed.binding.context_id != saved.binding.context_id
            phase("actual_os_removal_return")
            stopped, physical_remove = controlled(
                {"command": "apply", "binding": resumed.binding}, "remove"
            )
            assert (
                physical_remove["absent"]
                and stopped.status == "recovery_required"
                and stopped.publication == "partial"
            )
            native = stopped.operation
            assert (
                native.status == "cancelled" and native.code == "cancelled_after_intent"
            )
            assert (
                native.published_files == 1
                and native.planned_files == 2
                and native.stop_commit
            )
            assert (
                native.intent_commit
                and native.result_commit is None
                and native.receipt_commit is None
            )
            assert native.history == "intent" and stopped.history_retained
            call({"command": "close", "binding": None, "choice": "discard"})
            channel.close()
            phase("fresh_physical_recovery_inspection")
            channel = supervisor.open_update()
            restarted = call(
                {
                    "command": "history",
                    "vault": str(vault),
                    "selection_id": str(uuid4()),
                }
            )
            observed = restarted.history.operation
            assert (
                restarted.status == "recovery_required"
                and restarted.next_actions == ("review_recovery",)
            )
            assert (
                observed.operation_id,
                observed.intent_commit,
                observed.generation,
            ) == (native.operation_id, native.intent_commit, native.generation)
            assert (vault / "Manual.md").read_bytes() == manual
            assert all(
                (vault / path).read_bytes() == raw
                for path, raw in original.items()
                if path != "Assets/remove.bin"
            )
            assert {
                p.relative_to(source).as_posix(): p.read_bytes()
                for p in source.rglob("*")
                if p.is_file()
            } == original
            # Sampled worker RSS excludes native Git children; launch counts below include them.
            call(
                {"command": "close", "binding": restarted.binding, "choice": "discard"}
            )
            channel.close()
            channel = None
            assert (
                all(process.poll() == 0 for process in children) and len(children) == 3
            )
            monkeypatch.setattr(subprocess, "Popen", launch)
            assert user_git(vault) == before_git
            assert samples and not sample_errors
            resources = _driver_metrics(root, children)
            assert len(resources) == len(children)
            assert {row["pid"] for row in samples} == {
                row["worker_pid"] for row in resources
            }
            assert all(
                row["live_children"] == 0 and row["launched_child_processes"] > 0
                for row in resources
            )
            assert all(
                row["worker_complete"] and row["worker_exit_code"] == 0
                for row in resources
            )
            phase("complete", operation_id=native.operation_id, vault=str(vault))
            case_completed = True
        finally:
            (root / "capture-release").touch()
            (root / "remove-release").touch()
            sampling_done.set()
            sampler.join(2)
            partial_report()
            if channel is not None:
                channel.close()
    finally:
        state = locals()
        workers = state.get("children", [])
        observed_samples = state.get("samples", [])
        evidence_root = state.get("root")
        process_observations = _driver_metrics(evidence_root, workers)
        observed_outcomes = {
            name: state[name].model_dump(mode="json")
            for name in ("saved", "stopped", "restarted")
            if name in state
        }
        try:
            final_storage = state["storage"]() if "storage" in state else None
        except OSError:
            final_storage = {"unavailable_after_cleanup": True}
        report = {
            "qualification_completed": case_completed,
            "environment": {
                "python": sys.version,
                "windows": tuple(sys.getwindowsversion()),
            },
            "last_phase": json.loads(phase_log.read_text(encoding="utf-8")),
            "owner": state.get("owner"),
            "launcher_pids": [process.pid for process in workers],
            "worker_pids": [row["worker_pid"] for row in process_observations],
            "launcher_exit_codes": [process.poll() for process in workers],
            "worker_exit_codes": [
                row["worker_exit_code"] for row in process_observations
            ],
            "storage_before_worker": state.get("before_storage"),
            "storage_after_cleanup": final_storage,
            "rss_sampling_interval_seconds": 0.2,
            "worker_samples": observed_samples,
            "rss_sample_errors": state.get("sample_errors", []),
            "sampled_worker_peak_rss_bytes": max(
                (row["rss"] for row in observed_samples), default=None
            ),
            "observed_os_worker_peak_working_set_bytes": max(
                (row["os_peak_working_set"] for row in observed_samples), default=None
            ),
            "worker_process_resources": process_observations,
            "sealed_outcomes": observed_outcomes,
            "safe_responses": state.get("safe_responses", []),
            "limits": "One tiny graph. Worker RSS is measured for the actual driver PID and excludes Git children. Launcher PIDs are separate. Logical total storage includes evidence. Converter metadata is only .brz2obsidian; total .git is separate. Capture and OS removal are held at their completed return boundaries, without interrupting a kernel operation. Incomplete qualification never establishes native rollback or success. The runner and owned watchdog record the complete outer duration.",
        }
        report_path = tmp_path / "native-worker-resource.json"
        _write_json(report_path, report)
        report["elapsed_seconds_including_seed_final_inventory_and_reporting"] = (
            time.monotonic() - started
        )
        _write_json(report_path, report)
