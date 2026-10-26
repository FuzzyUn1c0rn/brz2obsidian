"""One fresh tiny native graph joins correlated controls to actual durable state."""

import ctypes
import json
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
root,vault=map(Path,sys.argv[1:])
started=time.monotonic()
children=[]
peak_processes=1
launch=subprocess.Popen
def popen(*args,**kwargs):
 global peak_processes
 child=launch(*args,**kwargs)
 children.append(child)
 peak_processes=max(peak_processes,1+sum(p.poll() is None for p in children))
 return child
subprocess.Popen=popen
def metrics():
 (root/('resources-'+str(os.getpid())+'.json')).write_text(json.dumps({
  'worker_pid':os.getpid(),'launched_child_processes':len(children),
  'peak_observed_live_worker_and_children':peak_processes,
  'live_children':sum(p.poll() is None for p in children),
  'elapsed_seconds':time.monotonic()-started}),encoding='utf-8')
def barrier(name,facts):
 metrics()
 (root/(name+'-entered.json')).write_text(json.dumps(facts),encoding='utf-8')
 deadline=time.monotonic()+20
 while not (root/(name+'-release')).exists():
  if time.monotonic()>deadline: raise OSError('owned native return barrier exhausted')
  time.sleep(.005)
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
code=UpdateWorker(context=UpdateContext(operations=Operations(vault_executor=ActualFiles())),output=sys.stdout.buffer).serve(sys.stdin.buffer)
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


def test_hidden_worker_real_capture_and_file_stop_reopen_from_exact_native_history(
    tmp_path, monkeypatch
):
    started = time.monotonic()
    phase_log = tmp_path / "phase.json"

    def phase(name, **facts):
        phase_log.write_text(
            json.dumps(
                {"phase": name, "elapsed_seconds": time.monotonic() - started, **facts}
            ),
            encoding="utf-8",
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
                path
                for path in (vault / ".git/brz2obsidian").rglob("*")
                if path.is_file()
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
                "git_directory_logical_bytes": sum(
                    path.stat().st_size for path in git_files
                ),
            }

        before_storage = storage()
        children, samples, sample_errors = [], [], []
        launch = subprocess.Popen

        def child(argv, *args, **kwargs):
            assert argv[1:] == ["-m", "brz2obsidian.worker"]
            process = launch(
                [argv[0], "-u", str(driver), str(root), str(vault)], *args, **kwargs
            )
            children.append(process)
            return process

        monkeypatch.setattr(subprocess, "Popen", child)
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
        sampling_done = Event()

        def sample():
            while not sampling_done.wait(0.2):
                for process in tuple(children):
                    if process.poll() is not None:
                        continue
                    handle = kernel.OpenProcess(0x0410, False, process.pid)
                    if not handle:
                        if process.poll() is None:
                            sample_errors.append(
                                {"pid": process.pid, "error": ctypes.get_last_error()}
                            )
                        continue
                    try:
                        value = _MemoryCounters()
                        value.cb = ctypes.sizeof(value)
                        if psapi.GetProcessMemoryInfo(
                            handle, ctypes.byref(value), ctypes.sizeof(value)
                        ):
                            samples.append(
                                {
                                    "pid": process.pid,
                                    "rss": value.WorkingSetSize,
                                    "os_peak_working_set": value.PeakWorkingSetSize,
                                }
                            )
                        else:
                            if process.poll() is None:
                                sample_errors.append(
                                    {
                                        "pid": process.pid,
                                        "error": ctypes.get_last_error(),
                                    }
                                )
                    finally:
                        kernel.CloseHandle(handle)

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
            raw_process_metrics = {}
            for process in children:
                path = root / ("resources-" + str(process.pid) + ".json")
                if path.exists():
                    raw_process_metrics[str(process.pid)] = path.read_text(
                        encoding="utf-8"
                    )
            try:
                current_storage = storage()
            except OSError:
                current_storage = {"unavailable_during_operation": True}
            snapshot = {
                "qualification_completed": False,
                "elapsed_seconds": time.monotonic() - started,
                "last_phase": json.loads(phase_log.read_text(encoding="utf-8")),
                "worker_pids": [process.pid for process in children],
                "worker_exit_codes": [process.poll() for process in children],
                "worker_samples": samples,
                "rss_sample_errors": sample_errors,
                "raw_driver_process_metrics": raw_process_metrics,
                "storage_before_worker": before_storage,
                "storage_at_snapshot": current_storage,
                "limits": "Partial observation before a possibly blocking join/close; no native outcome is inferred.",
            }
            path = tmp_path / (
                "native-worker-resource-partial-" + str(partial_index) + ".json"
            )
            path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

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
            resources = [
                json.loads(
                    (root / ("resources-" + str(process.pid) + ".json")).read_text(
                        encoding="utf-8"
                    )
                )
                for process in children
            ]
            assert all(
                row["live_children"] == 0 and row["launched_child_processes"] > 0
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
        process_observations = []
        for process in workers:
            metrics_path = evidence_root / ("resources-" + str(process.pid) + ".json")
            if metrics_path.exists():
                try:
                    process_observations.append(
                        json.loads(metrics_path.read_text(encoding="utf-8"))
                    )
                except ValueError:
                    process_observations.append(
                        {"worker_pid": process.pid, "incomplete_metrics": True}
                    )
            else:
                process_observations.append(
                    {"worker_pid": process.pid, "metrics_unavailable": True}
                )
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
            "worker_pids": [process.pid for process in workers],
            "worker_exit_codes": [process.poll() for process in workers],
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
            "limits": "One tiny graph. Worker RSS excludes Git children. Logical total storage includes evidence. Converter metadata is only .git/brz2obsidian; total .git is separate. Capture and OS removal are held at their completed return boundaries, without interrupting a kernel operation. Incomplete qualification never establishes native rollback or success. The runner and owned watchdog record the complete outer duration.",
        }
        report_path = tmp_path / "native-worker-resource.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["elapsed_seconds_including_seed_final_inventory_and_reporting"] = (
            time.monotonic() - started
        )
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
