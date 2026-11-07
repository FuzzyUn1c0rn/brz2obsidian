"""Strict command observation adapters and fixed synthetic mechanism controls."""

import ctypes
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from ctypes import wintypes as w
from pathlib import Path
from types import MappingProxyType

MIB = 1024 * 1024
READ_CONSUMERS = ("vault_admission", "vault_attributes", "vault_history")
PAYLOAD_CONSUMERS = (
    "checkpoint_payload",
    "vault_history",
    "vault_repair",
    "attachment_ownership",
    "vault_recovery",
    "vault_apply",
)
STORAGE_CASES = (
    "whole_target_is_delta",
    "delta_target_is_whole",
    "reverse_direction",
    "ofs_instead_of_ref",
    "wrong_header_base",
    "header_overflow",
    "header_truncated",
    "pack_index_corrupt",
    "loose_shadow",
    "external_alternate",
    "stream_byte_mismatch",
)
SUITE_MODES = ("peaks", "refusals", "tiny", "storage", "payload")
STAGE_RESERVES = {"development": 320, "coverage": 260, "author": 160, "verifier": 60}


def _manifest_source(mode):
    from tests.support.resource_pilot import read_control

    suite_name = os.environ.get("BRZ_COMMAND_GIT_SUITE_MANIFEST")
    if not suite_name:
        path = Path(os.environ["BRZ_COMMAND_GIT_MANIFEST"])
        digest = os.environ["BRZ_COMMAND_GIT_MANIFEST_SHA256"]
        return path, digest, None
    if os.environ.get("BRZ_COMMAND_GIT_MANIFEST") or os.environ.get(
        "BRZ_COMMAND_GIT_MANIFEST_SHA256"
    ):
        raise OSError("Ambiguous direct and suite command manifest routing")
    suite_path = Path(suite_name)
    raw = read_control(suite_path)
    if (
        hashlib.sha256(raw).hexdigest()
        != os.environ["BRZ_COMMAND_GIT_SUITE_MANIFEST_SHA256"]
    ):
        raise OSError("Suite manifest differs from Root's immutable bytes")
    suite = json.loads(raw)
    if type(suite) is not dict or set(suite) != {
        "schema_version",
        "issue",
        "checkout",
        "stage",
        "role",
        "started_at",
        "deadline",
        "run_reserved_seconds",
        "prior_charged_seconds",
        "child_cap_seconds",
        "future_reserved_seconds",
        "modes",
    }:
        raise OSError("Unknown suite reservation fields")
    stage = suite["stage"]
    if (
        stage not in ("coverage", "author", "verifier")
        or suite["role"] != ("verifier" if stage == "verifier" else "author")
        or suite["schema_version"] != 1
        or suite["issue"] != 358
        or Path(suite["checkout"]).resolve() != Path(__file__).resolve().parents[2]
    ):
        raise OSError("Suite role or checkout binding differs")
    numbers = [
        suite[key]
        for key in (
            "started_at",
            "deadline",
            "run_reserved_seconds",
            "prior_charged_seconds",
            "child_cap_seconds",
            "future_reserved_seconds",
        )
    ]
    if any(
        type(value) not in (int, float) or not 0 < value < float("inf")
        for value in numbers
    ):
        raise OSError("Invalid suite timing declaration")
    reserve = 60 if stage == "coverage" else 100
    if (
        suite["run_reserved_seconds"] != reserve
        or suite["deadline"] - suite["started_at"] != reserve
        or suite["child_cap_seconds"] != 480
        or suite["future_reserved_seconds"] != STAGE_RESERVES[stage]
        or suite["prior_charged_seconds"] + reserve + suite["future_reserved_seconds"]
        > 480
        or not suite["started_at"] <= time.monotonic() < suite["deadline"]
    ):
        raise OSError("Root-started suite has insufficient finite time credit")
    if (
        type(suite["modes"]) is not dict
        or set(suite["modes"]) != set(SUITE_MODES)
        or mode not in SUITE_MODES
        or stage == "coverage"
        and mode in ("peaks", "payload")
    ):
        raise OSError("Suite mode is outside its exact stage selection")
    paths = set()
    attempts = set()
    children = {}
    for name, declaration in suite["modes"].items():
        if type(declaration) is not dict or set(declaration) != {"path", "sha256"}:
            raise OSError("Unknown suite child declaration")
        path = Path(declaration["path"])
        if path.parent != suite_path.parent or path in paths or path.is_symlink():
            raise OSError("Suite child path is not its exclusive Root sibling")
        paths.add(path)
        child_raw = read_control(path)
        if hashlib.sha256(child_raw).hexdigest() != declaration["sha256"]:
            raise OSError("Suite child bytes differ from the immutable mapping")
        child = json.loads(child_raw)
        if (
            child["mode"] != name
            or child["stage"] != stage
            or child["role"] != suite["role"]
            or child["checkout"] != suite["checkout"]
            or child["attempt"] in attempts
        ):
            raise OSError("Suite child identity or exclusive attempt differs")
        attempts.add(child["attempt"])
        children[name] = child
    suite["children"] = children
    selected = suite["modes"][mode]
    return Path(selected["path"]), selected["sha256"], suite


def control_preflight(*, case=None, mode=None):
    """Bind one exclusive control attempt to Root's cumulative reservation."""
    from tests.support.resource_pilot import (
        Evidence,
        inventory,
        native_identity,
        read_control,
    )

    selected_mode = mode or ("peaks" if case is None else "refusals")
    manifest_path, expected_digest, suite = _manifest_source(selected_mode)
    raw = read_control(manifest_path)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_digest:
        raise OSError("Root command manifest differs from its pinned bytes")
    manifest = json.loads(raw)
    fields = {
        "schema_version",
        "issue",
        "feature_root",
        "base_commit",
        "oracle_commit",
        "role",
        "mode",
        "checkout",
        "attempt_parent",
        "attempt",
        "runner_parent",
        "runtime",
        "artifacts",
        "time",
        "charged_paths",
        "bootstrap",
    }
    if case is not None:
        fields |= {"cases"}
    if mode in ("tiny", "storage"):
        fields |= {"fixture"}
    if mode == "storage":
        fields |= {"cases", "controls"}
    if mode == "payload":
        fields |= {"material"}
    if suite is not None:
        fields |= {"stage"}
    if (
        mode not in (None, "tiny", "storage", "payload")
        or mode is not None
        and case is not None
    ):
        raise OSError("Unknown bounded control mode")
    if type(manifest) is not dict or set(manifest) != fields:
        raise OSError("Unknown Root command manifest fields")
    root = Path(__file__).resolve().parents[2]
    if (
        manifest["schema_version"] != 1
        or manifest["issue"]
        != "https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/358"
        or manifest["feature_root"] != "codex/r292-type-tag-support"
        or manifest["base_commit"] != "5378f0b1184bfe8825d6414475adaaa136203e1e"
        or manifest["oracle_commit"] != "94b4abdf536ce396a9f7b0a0591f7627d0b9079f"
        or manifest["role"] != (suite["role"] if suite else "author")
        or manifest["mode"] != (mode or ("peaks" if case is None else "refusals"))
        or Path(manifest["checkout"]).resolve() != root
    ):
        raise OSError("Root command manifest context mismatch")
    for name in ("attempt_parent", "runner_parent"):
        declaration = manifest[name]
        if type(declaration) is not dict or set(declaration) != {
            "path",
            "native_identity",
        }:
            raise OSError("Unknown native owner declaration")
        if native_identity(Path(declaration["path"])) != declaration["native_identity"]:
            raise OSError("Root-bound native parent identity changed")
    batch = Path(manifest["attempt"])
    batch_started = None
    bootstrap = manifest["bootstrap"]
    if (
        type(bootstrap) is not dict
        or set(bootstrap) != {"lifetimes", "images"}
        or bootstrap["lifetimes"] != 2
        or bootstrap["images"]
        != [manifest["runtime"]["native_executable"], "C:/Windows/System32/conhost.exe"]
    ):
        raise OSError("Bootstrap differs from the frozen native control")
    if batch.parent != Path(manifest["attempt_parent"]["path"]):
        raise OSError("Command attempt is outside its assigned parent")
    if case is not None:
        expected_cases = [
            "constructor_partial",
            "measurement_assign",
            "product_assign",
            "duplicate_measurement",
            "duplicate_creation",
            "registration_ack_lost",
            "family_counter_unavailable",
            "driver_killed_after_registration",
            "outer_deadline",
            "duplicate_return",
            "command_census_bypass",
            "terminal_reserve_exhausted",
        ]
        if manifest["cases"] != expected_cases or case not in expected_cases:
            raise OSError("Unknown refusal batch declaration")
        if batch.exists():
            owner = json.loads(read_control(batch / "batch-owner.json"))
            if (
                set(owner) != {"context", "native_identity", "started_at"}
                or owner["context"] != digest
                or owner["native_identity"] != native_identity(batch)
                or type(owner["started_at"]) not in (int, float)
            ):
                raise OSError("Refusal batch native ownership changed")
            batch_started = owner["started_at"]
        attempt = batch / case
    else:
        attempt = batch
    if attempt.exists():
        raise OSError("Command attempt is not an exclusive fresh destination")
    runner = Path(os.environ["BRZ_CHECK_COUNTS"]).parent
    if runner.parent != Path(manifest["runner_parent"]["path"]):
        raise OSError("Runner is outside the assigned native parent")
    runtime = manifest["runtime"]
    if type(runtime) is not dict or set(runtime) != {
        "venv_executable",
        "native_executable",
        "prefix",
    }:
        raise OSError("Unknown runtime binding declaration")
    for key, actual in (
        ("venv_executable", sys.executable),
        ("native_executable", sys._base_executable),
        ("prefix", sys.prefix),
    ):
        if Path(runtime[key]).resolve() != Path(actual).resolve():
            raise OSError("Command runtime differs from Root qualification")
    artifacts = manifest["artifacts"]
    artifact_fields = {
        "child_cap_bytes",
        "prior_charged_bytes",
        "prior_charge_note",
        "run_reserved_bytes",
        "observer_bytes",
        "terminal_bytes",
        "driver_bytes",
        "runner_bytes",
        "allocation_unit_bytes",
        "minimum_free_bytes",
    }
    if type(artifacts) is not dict or set(artifacts) != artifact_fields:
        raise OSError("Unknown cumulative artifact declaration")
    if any(
        type(value) is not int or value <= 0
        for key, value in artifacts.items()
        if key != "prior_charge_note"
    ):
        raise OSError("Invalid cumulative artifact reservation")
    if (
        artifacts["child_cap_bytes"] != 64 * MIB
        or artifacts["observer_bytes"] != 5 * MIB
        or artifacts["terminal_bytes"] != 4 * MIB
        or artifacts["driver_bytes"] != MIB
        or artifacts["runner_bytes"] != 2 * MIB
        or artifacts["run_reserved_bytes"] != 8 * MIB
        or artifacts["prior_charged_bytes"] + artifacts["run_reserved_bytes"]
        > artifacts["child_cap_bytes"]
        or artifacts["minimum_free_bytes"] < artifacts["run_reserved_bytes"]
        or not artifacts["prior_charge_note"]
    ):
        raise OSError("Root cumulative artifact allowance cannot fit control")
    unit = artifacts["allocation_unit_bytes"]
    paths = manifest["charged_paths"]
    if (
        type(paths) is not list
        or not 1 <= len(paths) <= 128
        or any(type(path) is not str for path in paths)
    ):
        raise OSError("Invalid finite charged path inventory")
    charged = 0
    for name in paths:
        path = Path(name)
        if path.is_dir():
            native_identity(path)
            charged += inventory(path, unit=unit)[0]
        else:
            if path.is_symlink():
                raise OSError("Charged artifact is not a physical file")
            charged += max(unit, ((path.stat().st_size + unit - 1) // unit) * unit)
    if charged > artifacts["prior_charged_bytes"]:
        raise OSError("Retained artifact growth exceeded Root's charged block")
    retained_batch = inventory(batch, unit=unit)[0] if batch.exists() else 0
    if suite is not None:
        retained_batch = sum(
            inventory(Path(child["attempt"]), unit=unit)[0]
            for child in suite["children"].values()
            if Path(child["attempt"]).exists()
        )
    if (
        artifacts["prior_charged_bytes"]
        + retained_batch
        + artifacts["run_reserved_bytes"]
        > artifacts["child_cap_bytes"]
    ):
        raise OSError("Retained refusal attempts exhausted cumulative artifact credit")
    if inventory(runner, unit=unit)[0] > artifacts["runner_bytes"]:
        raise OSError("Active runner artifact reserve exhausted")
    timing = manifest["time"]
    if (
        type(timing) is not dict
        or set(timing)
        != {
            "child_cap_seconds",
            "prior_charged_seconds",
            "run_reserved_seconds",
            "work_seconds",
            "cleanup_seconds",
            "future_reserved_seconds",
        }
        or any(
            type(value) not in (int, float) or not 0 < value <= 480
            for value in timing.values()
        )
    ):
        raise OSError("Invalid cumulative time declaration")
    future = STAGE_RESERVES[suite["stage"]] if suite else 320
    if (
        timing["child_cap_seconds"] != 480
        or timing["cleanup_seconds"] != 4
        or timing["future_reserved_seconds"] != future
        or timing["work_seconds"] + 4 > timing["run_reserved_seconds"]
        or timing["prior_charged_seconds"]
        + timing["run_reserved_seconds"]
        + timing["future_reserved_seconds"]
        > 480
    ):
        raise OSError("Required future work no longer fits the child time allowance")
    if suite is not None and (
        timing["prior_charged_seconds"] != suite["prior_charged_seconds"]
        or time.monotonic() + timing["work_seconds"] + 8 > suite["deadline"]
    ):
        raise OSError(
            "Shared suite cannot fit the next work, cleanup and final validation"
        )
    if (
        batch_started is not None
        and time.monotonic()
        - batch_started
        + timing["work_seconds"]
        + timing["cleanup_seconds"]
        + 4
        > timing["run_reserved_seconds"]
    ):
        raise OSError(
            "Refusal batch lacks the complete next-work and cleanup reservation"
        )
    for path in (batch.parent, runner):
        if shutil.disk_usage(path).free < artifacts["minimum_free_bytes"]:
            raise OSError("Insufficient physical volume headroom before control")
    if mode == "storage":
        controls = manifest["controls"]
        if (
            manifest["cases"] != list(STORAGE_CASES)
            or type(controls) is not dict
            or set(controls)
            != {"prior_rounded_bytes", "cap_bytes", "fresh_fixture_bytes"}
        ):
            raise OSError("Unknown miniature batch declaration")
        if (
            any(type(value) is not int or value < 0 for value in controls.values())
            or controls["cap_bytes"] != 32 * MIB
            or controls["fresh_fixture_bytes"] != MIB
            or controls["prior_rounded_bytes"] + MIB > controls["cap_bytes"]
        ):
            raise OSError("Miniature controls lack cumulative material credit")
    if mode in ("tiny", "storage"):
        fixture = manifest["fixture"]
        if type(fixture) is not dict or set(fixture) != {
            "path",
            "parent",
            "owner",
            "reserve_bytes",
            "allocation_unit_bytes",
            "git_executable",
        }:
            raise OSError("Unknown tiny fixture declaration")
        parent = fixture["parent"]
        if type(parent) is not dict or set(parent) != {"path", "native_identity"}:
            raise OSError("Unknown tiny fixture parent declaration")
        base = Path(parent["path"])
        destination = Path(fixture["path"])
        if (
            base.resolve() != Path(tempfile.gettempdir()).resolve()
            or native_identity(base) != parent["native_identity"]
            or destination.parent != base
            or destination.exists()
        ):
            raise OSError(
                "Tiny fixture destination is not fresh in its owned OS-temp parent"
            )
        if (
            type(fixture["owner"]) is not str
            or not 1 <= len(fixture["owner"]) <= 64
            or any(
                char not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                for char in fixture["owner"]
            )
            or destination.name != "brz2obsidian-358-" + fixture["owner"]
        ):
            raise OSError("Tiny fixture owner declaration is invalid")
        if (
            fixture["reserve_bytes"]
            != (MIB if mode == "storage" or suite else 32 * MIB)
            or fixture["allocation_unit_bytes"] != unit
        ):
            raise OSError("Tiny fixture exceeds the controls partition")
        if any((ancestor / ".git").exists() for ancestor in (base, *base.parents)):
            raise OSError("OS-temp control is inside an enclosing repository")
        if (
            shutil.disk_usage(base).free
            < fixture["reserve_bytes"] + artifacts["run_reserved_bytes"]
        ):
            raise OSError("Tiny fixture and artifacts lack actual-volume headroom")
        if (
            Path(shutil.which("git") or "").resolve()
            != Path(fixture["git_executable"]).resolve()
        ):
            raise OSError("Installed Git selection differs from Root's declaration")
        if any(
            os.environ.get(name)
            for name in (
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_COMMON_DIR",
                "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            )
        ):
            raise OSError(
                "Ambient Git routing conflicts with the exclusively owned fixture"
            )
        if suite is not None:
            prior_controls = suite["children"]["storage"]["controls"][
                "prior_rounded_bytes"
            ]
            retained_controls = sum(
                inventory(Path(child["fixture"]["path"]), unit=unit)[0]
                for child in suite["children"].values()
                if "fixture" in child and Path(child["fixture"]["path"]).exists()
            )
            if prior_controls + retained_controls + fixture["reserve_bytes"] > 32 * MIB:
                raise OSError(
                    "Earlier suite fixtures exhausted cumulative controls credit"
                )
    if mode == "payload":
        if suite is None or suite["stage"] not in ("author", "verifier"):
            raise OSError("Payload execution requires a final author or verifier suite")
        material = manifest["material"]
        material_fields = {
            "root",
            "parent",
            "owner",
            "reserve_bytes",
            "phase_cap_bytes",
            "partition_bytes",
            "controls_charged_bytes",
            "artifacts_charged_bytes",
            "global_reserved_bytes",
            "canonical",
            "git_executable",
            "retained_reserved_bytes",
            "prior_retained_bytes",
        }
        if type(material) is not dict or set(material) != material_fields:
            raise OSError("Unknown payload material declaration")
        partitions = {
            "author": 192 * MIB,
            "verifier": 192 * MIB,
            "controls": 32 * MIB,
            "artifacts": 64 * MIB,
        }
        if (
            material["partition_bytes"] != partitions
            or material["phase_cap_bytes"] != 480 * MIB
            or material["reserve_bytes"] != 192 * MIB
            or type(material["global_reserved_bytes"]) is not int
            or not 480 * MIB <= material["global_reserved_bytes"] <= 4096 * MIB
        ):
            raise OSError(
                "Payload partitions differ from the fixed phase/global envelope"
            )
        for name, cap in (
            ("controls_charged_bytes", 32 * MIB),
            ("artifacts_charged_bytes", 64 * MIB),
            ("prior_retained_bytes", 160 * MIB),
        ):
            if type(material[name]) is not int or not 0 <= material[name] <= cap:
                raise OSError("Payload prior material charge is invalid")
        retained = (112 if manifest["role"] == "author" else 48) * MIB
        if (
            material["retained_reserved_bytes"] != retained
            or material["prior_retained_bytes"] + retained > 160 * MIB
        ):
            raise OSError("Payload retention cannot fit the conditional 160 MiB target")
        parent = material["parent"]
        if type(parent) is not dict or set(parent) != {"path", "native_identity"}:
            raise OSError("Unknown payload native parent declaration")
        base = Path(parent["path"])
        destination = Path(material["root"])
        if (
            base.resolve() != Path(tempfile.gettempdir()).resolve()
            or native_identity(base) != parent["native_identity"]
            or destination.parent != base
            or destination.exists()
            or type(material["owner"]) is not str
            or not 1 <= len(material["owner"]) <= 64
            or any(
                char not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                for char in material["owner"]
            )
            or destination.name != "brz2obsidian-358-" + material["owner"]
        ):
            raise OSError("Payload destination lacks exclusive physical ownership")
        if (
            any((ancestor / ".git").exists() for ancestor in (base, *base.parents))
            or shutil.disk_usage(base).free < 200 * MIB
        ):
            raise OSError(
                "Payload destination lacks independent full-size volume headroom"
            )
        if Path(shutil.which("git") or "").resolve() != Path(
            material["git_executable"]
        ).resolve() or any(
            os.environ.get(name)
            for name in (
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_COMMON_DIR",
                "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            )
        ):
            raise OSError(
                "Payload Git routing differs from the declared installed runtime"
            )
        canonical = material["canonical"]
        if manifest["role"] == "author" and canonical is not None:
            raise OSError("Author payload must create its own canonical inputs")
        if manifest["role"] == "verifier" and (
            type(canonical) is not dict or set(canonical) != {"path", "sha256"}
        ):
            raise OSError("Verifier canonical input lacks an immutable Root pin")
    if case is not None and not batch.exists():
        batch.mkdir()
        Evidence(limit=65536, terminal_reserve=65536).write(
            batch / "batch-owner.json",
            {
                "context": digest,
                "native_identity": native_identity(batch),
                "started_at": time.monotonic(),
            },
            terminal=True,
        )
    attempt.mkdir()
    writer = Evidence(limit=MIB, terminal_reserve=65536)
    writer.write(
        attempt / "owner.json",
        {
            "root": str(attempt),
            "native_identity": native_identity(attempt),
            "context": digest,
            "runner": str(runner),
            "runner_native_identity": native_identity(runner),
        },
    )
    writer.write(
        attempt / "disk-before.json",
        {
            "charged_bytes": charged,
            "prior_reserved_bytes": artifacts["prior_charged_bytes"],
            "retained_batch_bytes": retained_batch,
            "run_reserved_bytes": artifacts["run_reserved_bytes"],
            "free_bytes": shutil.disk_usage(attempt).free,
            "allocation_unit_bytes": unit,
        },
    )
    if mode in ("tiny", "storage"):
        writer.write(
            attempt / "fixture-request.json", {"context": digest, **manifest["fixture"]}
        )
    if mode == "payload":
        writer.write(
            attempt / "payload-request.json",
            {
                "context": digest,
                "material": manifest["material"],
                "role": manifest["role"],
            },
        )
    if case is not None:
        (attempt / "resume-trace.jsonl").open("xb").close()
    return attempt, manifest


def finish_control(attempt, manifest):
    """Retain rounded control charges; final runner closure remains Root-owned."""
    from tests.support.resource_pilot import Evidence, inventory

    bounds = manifest["artifacts"]
    unit = bounds["allocation_unit_bytes"]
    observer = inventory(attempt / "observer", unit=unit)[0]
    total = inventory(attempt, unit=unit)[0]
    driver = total - observer + unit
    runner = inventory(Path(os.environ["BRZ_CHECK_COUNTS"]).parent, unit=unit)[0]
    record = {
        "observer_rounded_bytes": observer,
        "driver_rounded_bytes_with_terminal_reserve": driver + 65536,
        "runner_rounded_bytes_so_far": runner,
        "prior_charged_bytes": bounds["prior_charged_bytes"],
        "final_runner_charge_required": True,
    }
    Evidence(limit=65536, terminal_reserve=65536).write(
        attempt / "allocation-after.json", record, terminal=True
    )
    if (
        observer > bounds["observer_bytes"]
        or driver + 65536 > bounds["driver_bytes"]
        or runner > bounds["runner_bytes"]
    ):
        raise OSError("Control allocation exceeded its individual physical reserve")


def _exchange(event, expected):
    raw = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    if len(raw.encode()) > 12 * 1024:
        raise OSError("Command control record exceeds its finite bound")
    sys.stdout.write(raw)
    sys.stdout.flush()
    if sys.stdin.readline(65) != expected + "\n":
        raise OSError("Command observer acknowledgment was lost or invalid")


class CommandCalls:
    """Only the actual returned call releases command finalization."""

    def __init__(self, fault=None, attempt=None):
        self.seq = 0
        self.current = None
        self.deadline = float(os.environ["BRZ_COMMAND_DEADLINE"])
        self.fault = fault
        self.attempt = attempt
        self.trace_bytes = 0
        self.product_handles = {}
        self.product_closed = 0
        self.product_close_duplicates = 0
        self.measurement_opened = 0
        self.measurement_closed = 0

    def witness(self, boundary, **details):
        if self.attempt is None:
            raise OSError("Native fault witness has no exclusive owner")
        data = (
            json.dumps({"boundary": boundary, "seq": self.seq, **details}) + "\n"
        ).encode()
        if len(data) > 4096:
            raise OSError("Native fault witness exceeds its reserved bytes")
        with (self.attempt / "fault-witness.json").open("xb") as stream:
            if stream.write(data) != len(data):
                raise OSError("Native fault witness was incomplete")
            stream.flush()
            os.fsync(stream.fileno())

    def resume_witness(self):
        if self.attempt is None:
            return
        data = (
            json.dumps(
                {"event": "native_resume_attempt", "seq": self.seq},
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        if self.trace_bytes + len(data) > 65536:
            raise OSError("Native resume witness reservation exhausted")
        self.trace_bytes += len(data)
        with (self.attempt / "resume-trace.jsonl").open("ab") as stream:
            if stream.write(data) != len(data):
                raise OSError("Native resume write-ahead trace was incomplete")
            stream.flush()
            os.fsync(stream.fileno())

    def ownership_witness(self):
        if self.attempt is None:
            return
        data = {
            "measurement_opened": self.measurement_opened,
            "measurement_closed": self.measurement_closed,
            "product_opened": len(self.product_handles),
            "product_closed": self.product_closed,
            "product_close_duplicates": self.product_close_duplicates,
        }
        raw = (json.dumps(data) + "\n").encode()
        with (self.attempt / "driver-ownership.json").open("xb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("Native ownership witness was incomplete")
            stream.flush()
            os.fsync(stream.fileno())

    def exception_witness(self, error):
        if self.attempt is None:
            return
        raw = (
            json.dumps({"type": type(error).__name__, "message": str(error)}) + "\n"
        ).encode()
        if len(raw) > 4096:
            raise OSError("Original exception exceeds its witness reservation")
        with (self.attempt / "original-exception.json").open("xb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("Original exception witness was incomplete")
            stream.flush()
            os.fsync(stream.fileno())

    @contextmanager
    def native_boundary(self, *, constructor=False):
        calls = self
        original = ctypes.WinDLL

        class NativeFunction:
            def __init__(self, function, name):
                self.function = function
                self.name = name

            @property
            def argtypes(self):
                return self.function.argtypes

            @argtypes.setter
            def argtypes(self, value):
                self.function.argtypes = value

            @property
            def restype(self):
                return self.function.restype

            @restype.setter
            def restype(self, value):
                self.function.restype = value

            def __call__(self, *args):
                if self.name == "ResumeThread":
                    calls.resume_witness()
                if (
                    self.name == "SetInformationJobObject"
                    and constructor
                    and calls.fault == "constructor_partial"
                ):
                    result = self.function(args[0], -1, *args[2:])
                    error = ctypes.get_last_error()
                    calls.witness(
                        "constructor_partial",
                        native_error=error,
                        native_result=bool(result),
                    )
                    ctypes.set_last_error(error)
                    return result
                if (
                    self.name == "AssignProcessToJobObject"
                    and calls.fault == "product_assign"
                ):
                    result = self.function(0, args[1])
                    error = ctypes.get_last_error()
                    calls.witness(
                        "product_assign", native_error=error, native_result=bool(result)
                    )
                    ctypes.set_last_error(error)
                    return result
                result = self.function(*args)
                if self.name == "CreateJobObjectW" and result:
                    calls.product_handles[int(result)] = False
                elif (
                    self.name == "CloseHandle" and int(args[0]) in calls.product_handles
                ):
                    handle = int(args[0])
                    if calls.product_handles[handle]:
                        calls.product_close_duplicates += 1
                    if result:
                        calls.product_handles[handle] = True
                        calls.product_closed += 1
                return result

        class WitnessDLL(original):
            def __getattr__(self, name):
                function = super().__getattr__(name)
                if name in (
                    "ResumeThread",
                    "CreateJobObjectW",
                    "CloseHandle",
                    "SetInformationJobObject",
                    "AssignProcessToJobObject",
                ):
                    function = NativeFunction(function, name)
                    setattr(self, name, function)
                return function

        ctypes.WinDLL = WitnessDLL
        try:
            yield
        finally:
            ctypes.WinDLL = original

    def call(self, kind, function, argv, **kwargs):
        if self.current is not None or self.seq >= 512:
            raise OSError("Concurrent or excessive observed command call")
        if time.monotonic() + kwargs.get("timeout", 30) + 4 >= self.deadline:
            raise OSError("Insufficient remaining owned-family work time")
        self.seq += 1
        seq = self.seq
        _exchange(
            {"event": "command_begin", "seq": seq, "kind": kind, "argv": list(argv)},
            f"begin {seq}",
        )
        self.current = {"seq": seq, "created": False, "jobs": []}
        try:
            try:
                result = function(argv, **kwargs)
            except BaseException as original:
                # Original cleanup has completed when the real function raises.
                for job in self.current["jobs"]:
                    try:
                        job.close_measurement()
                    except OSError as error:
                        original.add_note(
                            f"Measurement handle cleanup also failed: {error}"
                        )
                try:
                    self.ownership_witness()
                    self.exception_witness(original)
                except OSError as error:
                    original.add_note(f"Ownership witness also failed: {error}")
                try:
                    _exchange(
                        {
                            "event": "command_return",
                            "seq": seq,
                            "status": "raised"
                            if self.current["created"]
                            else "not_created",
                        },
                        f"finalized {seq}",
                    )
                except OSError, ValueError:
                    pass
                raise
            for job in self.current["jobs"]:
                job.close_measurement()
            self.ownership_witness()
            _exchange(
                {"event": "command_return", "seq": seq, "status": "returned"},
                f"finalized {seq}",
            )
            return result
        finally:
            self.current = None


@contextmanager
def measured_calls(*, fault=None, attempt=None, git_options=()):
    """Adapt fixed identities and factories without changing product cleanup."""
    from brz2obsidian.publication import git_payload, git_read
    from tools.update_resource_probe import _Windows

    resource_pilot = sys.modules.get("tests.support.resource_pilot")
    calls = CommandCalls(fault, attempt)
    api = _Windows()
    original_read, original_verify = git_read.read_git, git_payload.verify_blobs
    original_job, original_popen = git_read._WindowsJob, git_read._SuspendedPopen
    original_run, original_subprocess_popen = subprocess.run, subprocess.Popen
    changes = []

    def bind(module, name, value):
        changes.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    class MeasuredJob(original_job):
        def __init__(self):
            if calls.current is None:
                raise OSError("Process constructor bypassed command begin")
            self.measurement = api.kernel.CreateJobObjectW(None, None)
            api.require(self.measurement)
            calls.measurement_opened += 1
            calls.current["jobs"].append(self)
            try:
                with calls.native_boundary(constructor=True):
                    super().__init__()
            except BaseException:
                self.close_measurement()
                raise

        def close_measurement(self):
            if self.measurement is not None:
                handle, self.measurement = self.measurement, None
                api.require(api.kernel.CloseHandle(handle))
                calls.measurement_closed += 1

        def attach_handle(self, handle):
            calls.current["created"] = True
            if calls.fault == "measurement_assign":
                result = api.kernel.AssignProcessToJobObject(0, handle)
                error = ctypes.get_last_error()
                calls.witness(
                    "measurement_assign", native_error=error, native_result=bool(result)
                )
                ctypes.set_last_error(error)
                api.require(result)
            api.require(api.kernel.AssignProcessToJobObject(self.measurement, handle))
            super().attach_handle(handle)
            seq = calls.current["seq"]
            _exchange(
                {
                    "event": "command_register",
                    "seq": seq,
                    "measurement_handle": self.measurement,
                    "creation_process_handle": int(handle),
                },
                f"registered {seq}",
            )
            # The observer now owns a duplicate. Closing this original does not
            # retain or alter the independently owned product cleanup job.
            self.close_measurement()
            if calls.fault == "outer_deadline":
                calls.witness("outer_deadline", registration_acknowledged=True)
                time.sleep(60)

    class MeasuredPopen(original_popen):
        def _execute_child(self, *args, **kwargs):
            with calls.native_boundary():
                return super()._execute_child(*args, **kwargs)

    def read(argv, **kwargs):
        return calls.call("read", original_read, argv, **kwargs)

    def verify(argv, **kwargs):
        return calls.call("payload", original_verify, argv, **kwargs)

    def fixture(vault, *args):
        def actual(argv, **kwargs):
            job = MeasuredJob()

            class FixturePopen(original_popen):
                def __init__(self, *args, **options):
                    super().__init__(*args, job=job, **options)

            try:
                subprocess.Popen = FixturePopen
                return original_run(argv, **kwargs)
            finally:
                subprocess.Popen = original_subprocess_popen
                job.close()

        return resource_pilot._git_with_runner(
            vault,
            (*git_options, *args),
            lambda argv, **kwargs: calls.call("fixture", actual, argv, **kwargs),
        )

    try:
        for module in (git_read, git_payload):
            if (
                module._WindowsJob is not original_job
                or module._SuspendedPopen is not original_popen
            ):
                raise OSError("Unrecognized Git creation factory")
            bind(module, "_WindowsJob", MeasuredJob)
            bind(module, "_SuspendedPopen", MeasuredPopen)
        for names, attribute, original, replacement in (
            (READ_CONSUMERS, "read_git", original_read, read),
            (PAYLOAD_CONSUMERS, "verify_blobs", original_verify, verify),
        ):
            for name in names:
                module = sys.modules.get("brz2obsidian.publication." + name)
                if module is None:
                    continue
                if getattr(module, attribute, None) is not original:
                    raise OSError("Unrecognized imported Git consumer identity")
                bind(module, attribute, replacement)
        bind(git_read, "read_git", read)
        bind(git_payload, "verify_blobs", verify)
        if resource_pilot is not None:
            bind(resource_pilot, "git", fixture)
        yield calls
    finally:
        for module, name, value in reversed(changes):
            setattr(module, name, value)
        # A fixed consumer imported inside the context inherits the wrapped
        # core function. Restore only this context's known function identities.
        for names, attribute, original, replacement in (
            (READ_CONSUMERS, "read_git", original_read, read),
            (PAYLOAD_CONSUMERS, "verify_blobs", original_verify, verify),
        ):
            for name in names:
                module = sys.modules.get("brz2obsidian.publication." + name)
                if (
                    module is not None
                    and getattr(module, attribute, None) is replacement
                ):
                    setattr(module, attribute, original)


class _Memory(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("faults", w.DWORD)] + [
        (name, ctypes.c_size_t)
        for name in (
            "peak_ws",
            "ws",
            "peak_paged",
            "paged",
            "peak_nonpaged",
            "nonpaged",
            "pagefile",
            "peak_pagefile",
            "private",
        )
    ]


class _Region(ctypes.Structure):
    _fields_ = [
        ("base", ctypes.c_void_p),
        ("allocation_base", ctypes.c_void_p),
        ("protection", w.DWORD),
        ("partition", w.WORD),
        ("size", ctypes.c_size_t),
        ("state", w.DWORD),
        ("protect", w.DWORD),
        ("type", w.DWORD),
    ]


def _private(handle=-1):
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(_Memory), w.DWORD]
    value = _Memory()
    value.cb = ctypes.sizeof(value)
    if not psapi.GetProcessMemoryInfo(w.HANDLE(handle), ctypes.byref(value), value.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return value.private


def _allocate(size, parent_pid):
    """Trusted control witness; measured process imports only Python stdlib."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, w.DWORD, w.DWORD]
    kernel.VirtualAlloc.restype = ctypes.c_void_p
    kernel.VirtualQuery.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_Region),
        ctypes.c_size_t,
    ]
    kernel.VirtualQuery.restype = ctypes.c_size_t
    kernel.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, w.DWORD]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    before = _private()
    address = kernel.VirtualAlloc(None, size, 0x3000, 4)
    if not address:
        raise ctypes.WinError(ctypes.get_last_error())
    ctypes.memset(address, 0x5A, size)
    region = _Region()
    if (
        kernel.VirtualQuery(address, ctypes.byref(region), ctypes.sizeof(region))
        != ctypes.sizeof(region)
        or region.state != 0x1000
        or region.size < size
    ):
        raise OSError("Allocated control region is not fully committed")
    parent = kernel.OpenProcess(0x0410, False, parent_pid)
    if not parent:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        parent_private = _private(parent)
        held = _private()
    finally:
        if not kernel.CloseHandle(parent):
            raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.VirtualFree(address, 0, 0x8000):
        raise ctypes.WinError(ctypes.get_last_error())
    print(
        json.dumps(
            {
                "requested_bytes": size,
                "committed_region_bytes": region.size,
                "child_before_private_bytes": before,
                "child_held_private_bytes": held,
                "parent_private_bytes": parent_private,
                "released_before_parent_exit": True,
            }
        ),
        flush=True,
    )
    # The command parent exits while this child still owns stdout. Only normal
    # product cleanup job closure may end it and release the private Git pipes.
    time.sleep(60)


def _parent(size):
    environment = os.environ.copy()
    environment.pop("__PYVENV_LAUNCHER__", None)
    child = subprocess.Popen(
        [sys._base_executable, __file__, "allocate", str(size), str(os.getpid())],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    raw = child.stdout.readline(4097)
    if not raw.endswith(b"\n") or len(raw) > 4096:
        raise OSError("Missing bounded allocation witness")
    proof = json.loads(raw)
    proof["child_alive_at_parent_exit"] = child.poll() is None
    print(json.dumps(proof), flush=True)
    # Deliberately leave the child alive, with pipes held, for the real cleanup.


def _peaks(attempt):
    from brz2obsidian.publication import git_read
    from tests.support.resource_pilot import Evidence

    witnesses = []
    with measured_calls():
        for size in (32 * MIB, 8 * MIB):
            result = git_read.read_git(
                [sys._base_executable, __file__, "parent", str(size)],
                env=os.environ.copy(),
                timeout=5,
            )
            if result.returncode:
                raise OSError("Fixed allocation control failed")
            witnesses.append(json.loads(result.stdout))
    Evidence(limit=MIB - 65536, terminal_reserve=65536).write(
        attempt / "peaks.json", witnesses
    )


def _refusal(case, attempt):
    from brz2obsidian.publication import git_read

    with measured_calls(fault=case, attempt=attempt) as calls:
        result = git_read.read_git(
            [sys._base_executable, "-c", "pass"],
            env=os.environ.copy(),
            timeout=0.25,
        )
        if result.returncode:
            raise OSError("Fixed refusal command unexpectedly failed")
        if case == "duplicate_return":
            _exchange(
                {"event": "command_return", "seq": calls.seq, "status": "returned"},
                f"finalized {calls.seq}",
            )
        if case == "command_census_bypass":
            subprocess.run(
                [sys._base_executable, "-c", "pass"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=0.25,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )


def _tiny(attempt):
    from brz2obsidian.publication import git_payload, git_read
    from tests.support import resource_pilot

    request = json.loads(resource_pilot.read_control(attempt / "fixture-request.json"))
    manifest_path, expected_digest, _ = _manifest_source("tiny")
    raw_manifest = resource_pilot.read_control(manifest_path)
    digest = hashlib.sha256(raw_manifest).hexdigest()
    manifest = json.loads(raw_manifest)
    if (
        digest != expected_digest
        or request != {"context": digest, **manifest["fixture"]}
        or Path(manifest["attempt"]) != attempt
    ):
        raise OSError("Tiny driver request lost its Root binding")
    root = Path(request["path"])
    parent = Path(request["parent"]["path"])
    if (
        root.parent != parent
        or root.exists()
        or resource_pilot.native_identity(parent)
        != request["parent"]["native_identity"]
        or Path(shutil.which("git") or "").resolve()
        != Path(request["git_executable"]).resolve()
        or shutil.disk_usage(parent).free < request["reserve_bytes"] + 8 * MIB
    ):
        raise OSError("Tiny driver physical ownership preflight changed")
    oracle_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures/resource_git/command16-oracles.json"
    )
    raw_oracle = resource_pilot.read_control(oracle_path)
    if (
        hashlib.sha256(raw_oracle).hexdigest()
        != "8f3cd763911e889f0265e8c046e8375dc136ea3d4b20e3356a3609f5b8e2a850"
    ):
        raise OSError("Independent command oracle differs from accepted bytes")
    oracle = json.loads(raw_oracle)["miniatures"]["objects"]["base"]
    raw = bytes.fromhex(oracle["raw_hex"])
    if (
        len(raw) != oracle["size"]
        or hashlib.sha256(raw).hexdigest() != oracle["sha256"]
    ):
        raise OSError("Independent miniature byte declaration is inconsistent")

    writer = resource_pilot.Evidence(limit=MIB - 65536, terminal_reserve=65536)
    root.mkdir()
    identity = resource_pilot.native_identity(root)
    writer.write(
        root / "owner.json",
        {"context": digest, "owner": request["owner"], "native_identity": identity},
    )
    vault = root / "vault"
    template = root / "empty-template"
    for directory in (vault, template, root / "hooks"):
        directory.mkdir()
    with (vault / "tiny.bin").open("xb") as stream:
        if stream.write(raw) != len(raw):
            raise OSError("Tiny fixture byte write was incomplete")

    original_read, original_verify = git_read.read_git, git_payload.verify_blobs
    original_fixture = resource_pilot.git
    factory_modules = (git_read, git_payload)
    originals = [
        (module, module._WindowsJob, module._SuspendedPopen)
        for module in factory_modules
    ]
    original_subprocess = subprocess.Popen
    common = [
        "git",
        "--no-pager",
        "-c",
        "core.bigFileThreshold=1m",
        "-c",
        "gc.auto=0",
        "-c",
        "maintenance.auto=false",
        "-C",
        str(vault),
    ]
    settings = (
        "-c",
        "core.bigFileThreshold=1m",
        "-c",
        "gc.auto=0",
        "-c",
        "maintenance.auto=false",
    )
    facts = {"fixture_root": str(root), "fixture_native_identity": identity}
    read_names = ("git_read", *READ_CONSUMERS)
    payload_names = ("git_payload", *PAYLOAD_CONSUMERS)

    class PositionSink:
        def __init__(self):
            self.position = 0

        def write(self, block):
            end = self.position + len(block)
            if end > len(raw) or block != raw[self.position : end]:
                raise OSError("Tiny stream differs from independent positional bytes")
            self.position = end
            return len(block)

    with measured_calls():
        facts["git_version"] = (
            resource_pilot.git(vault, *settings, "--version").decode("ascii").strip()
        )
        resource_pilot.git(
            vault,
            *settings,
            "init",
            "--object-format=sha1",
            "--ref-format=files",
            "--template=" + str(template),
        )
        oid = (
            resource_pilot.git(vault, *settings, "hash-object", "-w", "tiny.bin")
            .decode("ascii")
            .strip()
        )
        if oid != oracle["git_blob_sha1"]:
            raise OSError("Installed Git miniature differs from independent object ID")
        facts["blob_oid"] = oid
        read_requests = (
            ("object_format", ["rev-parse", "--show-object-format"], "sha1"),
            ("ref_format", ["rev-parse", "--show-ref-format"], "files"),
            ("big_file_threshold", ["config", "--get", "core.bigFileThreshold"], "1m"),
            ("blob_size", ["cat-file", "-s", oid], "8"),
        )
        for name, (key, arguments, expected) in zip(
            read_names, read_requests, strict=True
        ):
            module = importlib.import_module("brz2obsidian.publication." + name)
            result = module.read_git(common + arguments, env=os.environ.copy())
            value = result.stdout.decode("ascii").strip()
            if result.returncode or value != expected:
                raise OSError(
                    "Actual fixed Git read consumer returned unexpected evidence"
                )
            facts[key] = int(value) if key == "blob_size" else value
        verified = []
        for name in payload_names:
            module = importlib.import_module("brz2obsidian.publication." + name)
            sink = PositionSink()
            module.verify_blobs(
                common + ["cat-file", "--batch"],
                env=os.environ.copy(),
                objects=((oid, oracle["size"], oracle["sha256"], sink),),
            )
            if sink.position != oracle["size"]:
                raise OSError(
                    "Actual fixed Git payload consumer did not finish its stream"
                )
            verified.append(sink.position)
    aliases_restored = (
        resource_pilot.git is original_fixture
        and all(
            sys.modules["brz2obsidian.publication." + name].read_git is original_read
            for name in read_names
        )
        and all(
            sys.modules["brz2obsidian.publication." + name].verify_blobs
            is original_verify
            for name in payload_names
        )
    )
    factories_restored = subprocess.Popen is original_subprocess and all(
        module._WindowsJob is job and module._SuspendedPopen is popen
        for module, job, popen in originals
    )
    if not aliases_restored or not factories_restored:
        raise OSError("Fixed Git adapters did not restore their original identities")
    if resource_pilot.native_identity(root) != identity:
        raise OSError("Tiny fixture native ownership changed during Git calls")
    allocated, rows = resource_pilot.inventory(
        root, unit=request["allocation_unit_bytes"]
    )
    if allocated > request["reserve_bytes"] or any(
        row.get("link_not_followed") for row in rows
    ):
        raise OSError("Tiny fixture exceeded its reserved physical inventory")
    facts.update(
        read_consumers=read_names,
        payload_consumers=payload_names,
        verified_stream_bytes=verified,
        original_aliases_restored=aliases_restored,
        original_factory_classes_restored=factories_restored,
        fixture_rounded_bytes=allocated,
        fixture_inventory=rows,
    )
    writer.write(attempt / "tiny.json", facts)


class StorageRefusal(OSError):
    def __init__(self, reason, **evidence):
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence


def storage_header(path, offset):
    """Inspect only the bounded entry prefix, never decompress a pack."""
    size_on_disk = path.stat().st_size
    if type(offset) is not int or not 0 <= offset < size_on_disk:
        raise StorageRefusal("header_offset", maximum_entry_bytes_read=0)
    consumed = 0
    with path.open("rb") as stream:
        stream.seek(offset)
        size = 0
        shift = 0
        for index in range(10):
            raw = stream.read(1)
            consumed += len(raw)
            if not raw:
                raise StorageRefusal(
                    "header_truncated", maximum_entry_bytes_read=consumed
                )
            value = raw[0]
            if index == 0:
                kind = (value >> 4) & 7
                size = value & 15
                shift = 4
            else:
                part = value & 127
                if part > ((1 << 63) - 1 - size) >> shift:
                    raise StorageRefusal(
                        "header_overflow", maximum_entry_bytes_read=consumed
                    )
                size += part << shift
                shift += 7
            if not value & 128:
                break
        else:
            raise StorageRefusal("header_overflow", maximum_entry_bytes_read=consumed)
        base = None
        if kind == 7:
            raw = stream.read(20)
            consumed += len(raw)
            if len(raw) != 20:
                raise StorageRefusal(
                    "header_truncated", maximum_entry_bytes_read=consumed
                )
            base = raw.hex()
    return {"type": kind, "size": size, "base": base, "bytes_read": consumed}


class PositionVerifier:
    """Record the first positional mismatch without altering product success."""

    def __init__(self, size, expected):
        self.size = size
        self.expected = expected
        self.position = 0
        self.mismatch = None

    def write(self, block):
        if len(block) > MIB or self.position + len(block) > self.size:
            raise OSError("Position verifier received an out-of-bound stream")
        expected = self.expected(self.position, len(block))
        if len(expected) != len(block):
            raise OSError("Position verifier expected-pattern length differs")
        if self.mismatch is None and block != expected:
            for index, (actual, wanted) in enumerate(zip(block, expected, strict=True)):
                if actual != wanted:
                    self.mismatch = {
                        "offset": self.position + index,
                        "actual": actual,
                        "expected": wanted,
                    }
                    break
        self.position += len(block)
        return len(block)


def _git_arguments(vault, *arguments):
    return [
        "git",
        "--no-pager",
        "-c",
        "core.bigFileThreshold=1m",
        "-c",
        "gc.auto=0",
        "-c",
        "maintenance.auto=false",
        "-C",
        str(vault),
        *arguments,
    ]


def verify_storage_stream(vault, declaration, expected):
    from brz2obsidian.publication import git_payload

    sink = PositionVerifier(declaration["size"], expected)
    # Any actual product exception propagates. A positional qualification
    # refusal occurs only after its complete verified stream and cleanup.
    git_payload.verify_blobs(
        _git_arguments(vault, "cat-file", "--batch"),
        env=os.environ.copy(),
        objects=(
            (
                declaration["git_blob_sha1"],
                declaration["size"],
                declaration["sha256"],
                sink,
            ),
        ),
    )
    if sink.position != declaration["size"]:
        raise OSError("Verified storage stream did not reach its declared end")
    evidence = {
        "verified_stream_bytes": sink.position,
        "cryptographic_success": True,
        "mismatch": sink.mismatch,
    }
    if sink.mismatch is not None:
        raise StorageRefusal("stream_bytes", **evidence)
    return evidence


def qualify_packed_storage(vault, pack, *, form, target, base, patterns):
    """Qualify actual layout, Git integrity, bounded headers and full streams."""
    from brz2obsidian.publication import git_read

    objects = vault / ".git" / "objects"
    if (objects / "info" / "alternates").exists() or (
        objects / "info" / "http-alternates"
    ).exists():
        raise StorageRefusal(
            "external_alternate", layout_path="objects/info/alternates"
        )
    oid = target["git_blob_sha1"]
    if (objects / oid[:2] / oid[2:]).exists():
        raise StorageRefusal("loose_shadow", loose_oid=oid)
    expected_files = {pack.resolve(), pack.with_suffix(".idx").resolve()}
    for path in objects.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise OSError("Packed reader contains a redirected object path")
        if path.is_file() and path.resolve() not in expected_files:
            raise OSError("Packed reader contains an unexpected object source")
    result = git_read.read_git(
        _git_arguments(vault, "verify-pack", "-v", str(pack.with_suffix(".idx"))),
        env=os.environ.copy(),
    )
    if result.returncode:
        raise StorageRefusal(
            "pack_integrity",
            git_returncode=result.returncode,
            stderr=result.stderr[:4096].decode("utf-8", errors="replace"),
        )
    rows = {}
    integrity_ok = False
    for line in result.stdout.decode("ascii").splitlines():
        tokens = line.split()
        if (
            tokens
            and len(tokens[0]) == 40
            and all(char in "0123456789abcdef" for char in tokens[0])
        ):
            if (
                len(tokens) not in (5, 7)
                or tokens[1] != "blob"
                or tokens[0] in rows
                or len(rows) >= 512
            ):
                raise OSError("Unexpected verified pack object row")
            values = [int(value) for value in tokens[2:5]]
            if any(value < 0 for value in values):
                raise OSError("Negative verified pack field")
            row = {
                "oid": tokens[0],
                "size": values[0],
                "packed_bytes": values[1],
                "offset": values[2],
                "depth": 0,
                "base": None,
            }
            if len(tokens) == 7:
                row.update(depth=int(tokens[5]), base=tokens[6])
            rows[tokens[0]] = row
        elif line.endswith(": ok"):
            integrity_ok = True
        elif not line.startswith(("non delta: ", "chain length = ")):
            raise OSError("Unexpected verify-pack integrity output")
    if not integrity_ok or oid not in rows:
        raise OSError("Verified pack lacks its complete target evidence")
    headers = {}
    for object_id, row in rows.items():
        if not 12 <= row["offset"] < pack.stat().st_size - 20:
            raise OSError("Verified pack entry offset is outside its object area")
        headers[object_id] = storage_header(pack, row["offset"])
        if headers[object_id]["size"] != row["size"]:
            raise OSError("Verified pack row and actual header size differ")
    maximum = max(header["bytes_read"] for header in headers.values())
    details = {
        "maximum_entry_bytes_read": maximum,
        "pack_integrity_verified": True,
        "target_row": rows[oid],
        "target_header": headers[oid],
    }
    if form == "whole":
        if rows[oid]["depth"] or headers[oid]["type"] != 3:
            raise StorageRefusal("whole_target_type", **details)
        if headers[oid]["size"] != target["size"]:
            raise OSError("Whole target has the wrong full size")
    elif form == "delta":
        base_oid = base["git_blob_sha1"]
        details["required_base_oid"] = base_oid
        details["base_row"] = rows.get(base_oid)
        details["base_header"] = headers.get(base_oid)
        if base_oid in rows and rows[base_oid]["depth"]:
            raise StorageRefusal("delta_direction", **details)
        if not rows[oid]["depth"]:
            raise StorageRefusal("delta_target_type", **details)
        if headers[oid]["type"] != 7:
            raise StorageRefusal("ref_delta_type", **details)
        if headers[oid]["base"] != base_oid:
            raise StorageRefusal("header_base", **details)
        if (
            rows[oid]["depth"] != 1
            or rows[oid]["base"] != base_oid
            or base_oid not in rows
        ):
            raise StorageRefusal("delta_direction", **details)
        if headers[base_oid]["type"] != 3 or headers[base_oid]["size"] != base["size"]:
            raise OSError("Delta base is not a complete whole blob")
    else:
        raise OSError("Unknown packed storage qualification form")
    expected_oids = {oid} | ({base["git_blob_sha1"]} if base is not None else set())
    if set(rows) != expected_oids:
        raise OSError(
            "Pack object census differs from the declared self-contained fixture"
        )
    for declaration in ([base] if base is not None else []) + [target]:
        verify_storage_stream(
            vault, declaration, patterns[declaration["git_blob_sha1"]]
        )
    return details


def _storage(attempt):
    from tests.support import resource_pilot

    request = json.loads(resource_pilot.read_control(attempt / "fixture-request.json"))
    manifest_path, expected_digest, _ = _manifest_source("storage")
    raw_manifest = resource_pilot.read_control(manifest_path)
    digest = hashlib.sha256(raw_manifest).hexdigest()
    manifest = json.loads(raw_manifest)
    if (
        digest != expected_digest
        or request != {"context": digest, **manifest["fixture"]}
        or manifest["cases"] != list(STORAGE_CASES)
        or Path(manifest["attempt"]) != attempt
    ):
        raise OSError("Storage driver request lost its Root binding")
    root = Path(request["path"])
    parent = Path(request["parent"]["path"])
    if (
        root.parent != parent
        or root.exists()
        or resource_pilot.native_identity(parent)
        != request["parent"]["native_identity"]
        or shutil.disk_usage(parent).free < MIB + 8 * MIB
        or Path(shutil.which("git") or "").resolve()
        != Path(request["git_executable"]).resolve()
    ):
        raise OSError("Storage driver physical reservation changed")
    raw_oracle = resource_pilot.read_control(
        Path(__file__).resolve().parents[1]
        / "fixtures/resource_git/command16-oracles.json"
    )
    if (
        hashlib.sha256(raw_oracle).hexdigest()
        != "8f3cd763911e889f0265e8c046e8375dc136ea3d4b20e3356a3609f5b8e2a850"
    ):
        raise OSError("Independent storage oracle differs from accepted bytes")
    oracle = json.loads(raw_oracle)["miniatures"]
    declarations = oracle["objects"]
    expected_refusals = (
        "whole_target_type",
        "delta_target_type",
        "delta_direction",
        "ref_delta_type",
        "header_base",
        "header_overflow",
        "header_truncated",
        "pack_integrity",
        "loose_shadow",
        "external_alternate",
        "stream_bytes",
    )
    writer = resource_pilot.Evidence(limit=MIB - 65536, terminal_reserve=65536)
    root.mkdir()
    identity = resource_pilot.native_identity(root)
    writer.write(
        root / "owner.json",
        {"context": digest, "owner": request["owner"], "native_identity": identity},
    )
    template = root / "empty-template"
    for directory in (template, root / "hooks", root / "cases"):
        directory.mkdir()
    outcomes = {}
    pattern_bytes = {
        item["git_blob_sha1"]: bytes.fromhex(item["raw_hex"])
        for item in declarations.values()
    }
    patterns = {
        oid: (lambda offset, count, raw=raw: raw[offset : offset + count])
        for oid, raw in pattern_bytes.items()
    }
    with measured_calls() as calls:
        for case, expected_refusal in zip(
            STORAGE_CASES, expected_refusals, strict=True
        ):
            case_root = root / "cases" / case
            control = oracle["invalid_storage_controls"][case]
            before = calls.seq
            # Reserve this case's bounded metadata/pack/control growth before
            # creating it; no file written by this fixed case exceeds 64 KiB.
            if resource_pilot.inventory(root)[0] + 65536 > MIB:
                raise OSError(
                    "Miniature fixture reservation exhausted before next case"
                )
            case_root.mkdir()
            case_identity = resource_pilot.native_identity(case_root)
            writer.write(
                case_root / "owner.json",
                {"context": digest, "case": case, "native_identity": case_identity},
            )
            if case.startswith("header_"):
                header = case_root / "entry.bin"
                with header.open("xb") as stream:
                    stream.write(bytes.fromhex(control["entry_header_hex"]))
            else:
                vault = case_root / "vault"
                vault.mkdir()
                resource_pilot.git(
                    vault,
                    "-c",
                    "gc.auto=0",
                    "-c",
                    "maintenance.auto=false",
                    "init",
                    "--object-format=sha1",
                    "--ref-format=files",
                    "--template=" + str(template),
                )
                objects = vault / ".git" / "objects"
                if case == "stream_byte_mismatch":
                    target = declarations["target"]
                    oid = target["git_blob_sha1"]
                    (objects / oid[:2]).mkdir()
                    with (objects / oid[:2] / oid[2:]).open("xb") as stream:
                        stream.write(bytes.fromhex(target["loose_zlib_hex"]))
                else:
                    pinned = oracle["packs"][control["pack"]]
                    pack = (
                        objects
                        / "pack"
                        / ("pack-" + pinned["pack_trailer_sha1"] + ".pack")
                    )
                    for path, field in (
                        (pack, "pack_hex"),
                        (pack.with_suffix(".idx"), "index_v2_hex"),
                    ):
                        data = bytes.fromhex(pinned[field])
                        if case == "pack_index_corrupt" and field == "index_v2_hex":
                            mutation = control["index_mutation"]
                            altered = bytearray(data)
                            altered[mutation["offset"]] ^= mutation["xor"]
                            data = bytes(altered)
                        with path.open("xb") as stream:
                            stream.write(data)
                    if case == "loose_shadow":
                        item = declarations[control["loose_object"]]
                        oid = item["git_blob_sha1"]
                        (objects / oid[:2]).mkdir()
                        with (objects / oid[:2] / oid[2:]).open("xb") as stream:
                            stream.write(bytes.fromhex(item["loose_zlib_hex"]))
                    if case == "external_alternate":
                        (vault / ".git" / "owned-mini-alternate" / "objects").mkdir(
                            parents=True
                        )
                        with (objects / "info" / "alternates").open("xb") as stream:
                            stream.write(
                                control["alternates_file_ascii"].encode("ascii")
                            )
            try:
                if case.startswith("header_"):
                    storage_header(header, 0)
                elif case == "stream_byte_mismatch":
                    wrong_expected = bytes.fromhex(control["actual_raw_hex"])
                    verify_storage_stream(
                        vault,
                        declarations["target"],
                        lambda offset, count, raw=wrong_expected: raw[
                            offset : offset + count
                        ],
                    )
                else:
                    qualify_packed_storage(
                        vault,
                        pack,
                        form="whole" if case == "whole_target_is_delta" else "delta",
                        target=declarations["target"],
                        base=declarations["base"],
                        patterns=patterns,
                    )
            except StorageRefusal as refusal:
                if refusal.reason != expected_refusal:
                    raise OSError(
                        "Storage control reached a different refusal boundary"
                    ) from refusal
                evidence = {
                    "refusal": refusal.reason,
                    "expected_boundary_reached": True,
                    "maximum_entry_bytes_read": 0,
                    **refusal.evidence,
                }
            else:
                raise OSError("Invalid storage control was accepted")
            if case == "stream_byte_mismatch":
                if (
                    evidence["mismatch"] != {"offset": 3, "actual": 89, "expected": 90}
                    or evidence["verified_stream_bytes"] != 8
                ):
                    raise OSError(
                        "Controlled expected-pattern mismatch differs from its pinned roles"
                    )
                evidence.update(
                    stream_command_sequence=calls.seq,
                    expected_pattern_role="R0 invalid-control actual_raw_hex used as expected",
                    actual_stream_role="valid R0 target with independent SHA1/SHA256",
                )
            if resource_pilot.native_identity(case_root) != case_identity:
                raise OSError("Miniature case native ownership changed")
            evidence.update(
                command_sequences=list(range(before + 1, calls.seq + 1)),
                fixture_bytes=resource_pilot.inventory(case_root)[0],
                native_identity=case_identity,
            )
            if evidence["fixture_bytes"] >= MIB:
                raise OSError("Miniature case exceeded its retained material bound")
            writer.write(attempt / (case + ".json"), evidence)
            outcomes[case] = evidence
    if resource_pilot.native_identity(root) != identity:
        raise OSError("Miniature fixture native ownership changed")
    allocated, rows = resource_pilot.inventory(root)
    if allocated > MIB or any(row.get("link_not_followed") for row in rows):
        raise OSError("Miniature fixture exceeds its physical reservation")
    writer.write(
        attempt / "storage.json",
        {
            "outcomes": outcomes,
            "fixture_bytes": allocated,
            "native_identity": identity,
            "inventory": rows,
        },
    )


def storage_control():
    from tests.support.resource_pilot import read_control
    from tools.update_resource_probe import observe_commands

    attempt, manifest = control_preflight(mode="storage")
    report = observe_commands(
        [
            sys.executable,
            "-m",
            "tests.support.git_resource_pilot",
            "storage",
            str(attempt),
        ],
        attempt / "observer",
        phases=(),
        work_timeout=manifest["time"]["work_seconds"],
        artifact_limit=manifest["artifacts"]["observer_bytes"] - 65536,
        bootstrap=manifest["bootstrap"],
    )
    finish_control(attempt, manifest)
    if (
        report["status"] != "completed"
        or report["command_family_coverage"] != "complete"
        or report["census"]["unaccounted_lifetimes"]
        or report["final_job"]["ActiveProcesses"]
        or report["cleanup_errors"]
        or report["proof_handles_remaining"]
        or report["handle_close_duplicates"]
    ):
        raise OSError("Miniature observer did not complete its qualified family census")
    facts = json.loads(read_control(attempt / "storage.json"))
    if list(facts["outcomes"]) != list(STORAGE_CASES) or facts["fixture_bytes"] > MIB:
        raise OSError("Miniature completed evidence differs from the authorized batch")
    commands = {
        row["seq"]: row for row in report["inventory"] if row["kind"] == "command"
    }
    for evidence in facts["outcomes"].values():
        for seq in evidence["command_sequences"]:
            row = commands[seq]
            if (
                row["state"] != "finalized"
                or row["return_status"] != "returned"
                or not row["normal_cleanup_complete"]
                or row["final_job"]["ActiveProcesses"]
            ):
                raise OSError(
                    "Miniature command did not return through original cleanup"
                )
            if (
                row["final_job"]["TotalProcesses"] < 1
                or row["final_job"]["PeakJobMemoryUsed"] <= 0
                or row["final_job"]["PeakProcessMemoryUsed"] <= 0
                or os.path.normcase(row["image"])
                != os.path.normcase(str(Path(manifest["fixture"]["git_executable"])))
            ):
                raise OSError(
                    "Miniature command lost actual Git identity or OS counters"
                )
        evidence["cleanup_complete"] = True
        if "stream_command_sequence" in evidence:
            evidence["stream_command_finalized"] = (
                commands[evidence["stream_command_sequence"]]["state"] == "finalized"
            )
    if len(commands) != 16 or set(commands) != {
        seq
        for evidence in facts["outcomes"].values()
        for seq in evidence["command_sequences"]
    }:
        raise OSError("Miniature commands do not reconcile to exact case ownership")
    if (
        [row["call_kind"] for row in commands.values()].count("fixture") != 9
        or [row["call_kind"] for row in commands.values()].count("read") != 6
        or [row["call_kind"] for row in commands.values()].count("payload") != 1
    ):
        raise OSError("Miniature command kinds differ from the fixed batch")

    def freeze(value):
        if isinstance(value, dict):
            return MappingProxyType({key: freeze(item) for key, item in value.items()})
        if isinstance(value, list):
            return tuple(freeze(item) for item in value)
        return value

    return freeze(facts["outcomes"])


def _oracle_pattern(declaration, offset, count):
    if not 0 <= count <= MIB or not 0 <= offset <= declaration["size"] - count:
        raise OSError("Payload pattern request exceeds its declared block")
    block = bytearray(
        (bytes(range(256)) * ((count + 511) // 256))[
            offset % 256 : offset % 256 + count
        ]
    )
    for replacement in declaration["replacements"]:
        raw = bytes.fromhex(replacement["hex"])
        start = max(offset, replacement["offset"])
        end = min(offset + count, replacement["offset"] + len(raw))
        if start < end:
            block[start - offset : end - offset] = raw[
                start - replacement["offset"] : end - replacement["offset"]
            ]
    return bytes(block)


def _check_payload_file(path, declaration):
    """Independent lane checks validate every byte of a bounded generated file."""
    sha256 = hashlib.sha256()
    sha1 = hashlib.sha1(usedforsecurity=False)
    sha1.update(f"blob {declaration['size']}\0".encode("ascii"))
    position = 0
    with path.open("rb") as stream:
        while block := stream.read(MIB):
            if position + len(block) > declaration["size"]:
                raise OSError("Payload file exceeds its independent size")
            # Lane equality is separate from the repeated-block generator.
            for lane in range(min(256, len(block))):
                values = block[lane::256]
                expected = bytearray([(position + lane) % 256]) * len(values)
                for replacement in declaration["replacements"]:
                    for index, value in enumerate(bytes.fromhex(replacement["hex"])):
                        relative = replacement["offset"] + index - position - lane
                        if 0 <= relative < len(block) - lane and relative % 256 == 0:
                            expected[relative // 256] = value
                if values != expected:
                    raise OSError(
                        "Generated payload differs from independent positional lanes"
                    )
            position += len(block)
            sha256.update(block)
            sha1.update(block)
    if (
        position != declaration["size"]
        or sha256.hexdigest() != declaration["sha256"]
        or sha1.hexdigest() != declaration["git_blob_sha1"]
    ):
        raise OSError("Payload identity differs from the immutable oracle")


def _canonical_tree(root):
    from tests.support.resource_pilot import file_fact, inventory, native_identity

    allocated, entries = inventory(root)
    rows = []
    for entry in entries:
        if entry.get("link_not_followed"):
            raise OSError("Canonical material contains a redirected path")
        path = root / entry["path"]
        rows.append({"path": entry["path"], **file_fact(path)})
    return {
        "path": str(root),
        "native_identity": native_identity(root),
        "allocated": allocated,
        "files": sorted(rows, key=lambda row: row["path"]),
    }


def _payload(attempt):
    from brz2obsidian.publication import git_read
    from tests.support import resource_pilot

    # The parent has admitted all creation roots and their uncompressed growth
    # before launching this driver. Bind again before its first material write.
    request = json.loads(resource_pilot.read_control(attempt / "payload-request.json"))
    manifest_path, expected_digest, _ = _manifest_source("payload")
    raw_manifest = resource_pilot.read_control(manifest_path)
    digest = hashlib.sha256(raw_manifest).hexdigest()
    manifest = json.loads(raw_manifest)
    if digest != expected_digest or request != {
        "context": digest,
        "material": manifest["material"],
        "role": manifest["role"],
    }:
        raise OSError("Payload driver lost its Root-bound material declaration")
    material = request["material"]
    root = Path(material["root"])
    parent = Path(material["parent"]["path"])
    if (
        root.exists()
        or root.parent != parent
        or resource_pilot.native_identity(parent)
        != material["parent"]["native_identity"]
        or shutil.disk_usage(parent).free < 192 * MIB + 8 * MIB
        or Path(shutil.which("git") or "").resolve()
        != Path(material["git_executable"]).resolve()
    ):
        raise OSError("Payload physical ownership or full-volume reservation changed")
    raw_oracle = resource_pilot.read_control(
        Path(__file__).resolve().parents[1]
        / "fixtures/resource_git/command16-oracles.json"
    )
    if (
        hashlib.sha256(raw_oracle).hexdigest()
        != "8f3cd763911e889f0265e8c046e8375dc136ea3d4b20e3356a3609f5b8e2a850"
    ):
        raise OSError("Payload oracle differs from independently qualified bytes")
    oracle = json.loads(raw_oracle)
    declarations = oracle["fixtures"]
    writer = resource_pilot.Evidence(limit=MIB - 65536, terminal_reserve=65536)
    root.mkdir()
    root_identity = resource_pilot.native_identity(root)
    writer.write(
        root / "owner.json",
        {"context": digest, "role": request["role"], "native_identity": root_identity},
    )
    template = root / "empty-template"
    template.mkdir()
    (root / "hooks").mkdir()
    public_evidence = attempt / "public"
    public_evidence.mkdir()
    public_root = root / "public"
    cells = {}

    def public_admission(evidence, ledger_path, expected_sha, evidence_writer):
        if (
            expected_sha != digest
            or evidence != public_evidence
            or public_root.exists()
        ):
            raise OSError(
                "Public pilot additive admission differs from its owned reservation"
            )
        public_root.mkdir()
        record = {
            "context": digest,
            "root": str(public_root),
            "native_identity": resource_pilot.native_identity(public_root),
            "retained_reserved_bytes": 32 * MIB,
            "live_transport_reserved_bytes": 64 * MIB,
        }
        evidence_writer.write(public_root / ".fixture-owner.json", record)
        evidence_writer.write(evidence / "owner.json", record)
        return public_root, parent, 192 * MIB

    def init_reader(name):
        path = root / name
        path.mkdir()
        resource_pilot.git(
            path,
            "init",
            "--object-format=sha1",
            "--ref-format=files",
            "--template=" + str(template),
        )
        return path

    def checked_read(vault, *arguments, input=None):
        result = git_read.read_git(
            _git_arguments(vault, *arguments), env=os.environ.copy(), input=input
        )
        if result.returncode:
            raise OSError("Frozen payload Git command failed")
        return result.stdout.decode("ascii").strip()

    with measured_calls(
        git_options=(
            "-c",
            "core.bigFileThreshold=1m",
            "-c",
            "gc.auto=0",
            "-c",
            "maintenance.auto=false",
        )
    ) as calls:
        first = calls.seq + 1
        public = resource_pilot.run(
            public_evidence,
            manifest_path,
            digest,
            admit=public_admission,
            evidence_writer=writer,
            init_arguments=(
                "--object-format=sha1",
                "--ref-format=files",
                "--template=" + str(template),
            ),
            terminal=False,
            allocation_limit=40 * MIB,
        )
        vault = public_root / "vault"
        if (
            checked_read(vault, "rev-parse", "--show-object-format") != "sha1"
            or checked_read(vault, "rev-parse", "--show-ref-format") != "files"
        ):
            raise OSError(
                "Public pilot object/ref formats differ from the fixed contract"
            )
        public_object = declarations["public16"]
        public_oid = public_object["git_blob_sha1"]
        if not (
            vault / ".git" / "objects" / public_oid[:2] / public_oid[2:]
        ).is_file() or any((vault / ".git" / "objects" / "pack").iterdir()):
            raise OSError("Public target lacks its actual loose-only storage")
        _check_payload_file(vault / "payload.bin", public_object)
        verify_storage_stream(
            vault,
            public_object,
            lambda offset, count: _oracle_pattern(public_object, offset, count),
        )
        cells["public_loose"] = {
            "status": "completed",
            "verified_bytes": public_object["size"],
            "storage": "loose",
            "saved_review_present": public["saved_review_present"],
            "stages_verified": public["stages_verified"],
            "stages_removed": public["stages_removed"],
            "command_sequences": list(range(first, calls.seq + 1)),
        }
        own_public = _canonical_tree(public_root)

        whole_first = calls.seq + 1
        if request["role"] == "verifier":
            canonical_raw = resource_pilot.read_control(
                Path(material["canonical"]["path"])
            )
            if (
                hashlib.sha256(canonical_raw).hexdigest()
                != material["canonical"]["sha256"]
            ):
                raise OSError(
                    "Shared canonical declaration differs from Root's pinned bytes"
                )
            canonical = json.loads(canonical_raw)
            if canonical["oracle_sha256"] != hashlib.sha256(
                raw_oracle
            ).hexdigest() or set(canonical["roots"]) != {
                "public",
                "whole-reader",
                "delta-builder",
                "delta-reader",
            }:
                raise OSError("Shared canonical object declaration is incomplete")
            for record in canonical["roots"].values():
                if _canonical_tree(Path(record["path"])) != record:
                    raise OSError(
                        "Shared canonical native identity or full file bytes changed"
                    )
            _check_payload_file(
                Path(canonical["roots"]["public"]["path"]) / "vault" / "payload.bin",
                public_object,
            )
            builder = Path(canonical["roots"]["delta-builder"]["path"])
            for name in ("base8", "target8"):
                _check_payload_file(builder / (name + ".bin"), declarations[name])
            whole = Path(canonical["roots"]["whole-reader"]["path"])
            delta = Path(canonical["roots"]["delta-reader"]["path"])
        else:
            whole = init_reader("whole-reader")
            builder = None
            delta = None

        first = whole_first
        if request["role"] == "author":
            recipe = oracle["pack_recipes"]["whole"]
            prefix = whole / ".git" / "objects" / "pack" / "pack"
            pack_hash = checked_read(
                vault,
                *recipe["arguments"],
                str(prefix),
                input=recipe["stdin_ascii"].encode("ascii"),
            )
            if len(pack_hash) != 40 or any(
                char not in "0123456789abcdef" for char in pack_hash
            ):
                raise OSError("Whole pack builder returned an invalid output identity")
        whole_packs = list((whole / ".git" / "objects" / "pack").glob("*.pack"))
        if len(whole_packs) != 1:
            raise OSError("Whole reader does not contain exactly one owned pack")
        qualified = qualify_packed_storage(
            whole,
            whole_packs[0],
            form="whole",
            target=public_object,
            base=None,
            patterns={
                public_oid: lambda offset, count: _oracle_pattern(
                    public_object, offset, count
                )
            },
        )
        cells["packed_whole"] = {
            "status": "completed",
            "verified_bytes": public_object["size"],
            "target_type": qualified["target_header"]["type"],
            "command_sequences": list(range(first, calls.seq + 1)),
        }

        first = calls.seq + 1
        if request["role"] == "author":
            builder = init_reader("delta-builder")
            delta = init_reader("delta-reader")
            for name in ("base8", "target8"):
                declaration = declarations[name]
                path = builder / (name + ".bin")
                with path.open("xb") as stream:
                    for offset in range(0, declaration["size"], MIB):
                        block = _oracle_pattern(
                            declaration, offset, min(MIB, declaration["size"] - offset)
                        )
                        if stream.write(block) != len(block):
                            raise OSError("Payload generation write was incomplete")
                _check_payload_file(path, declaration)
                if (
                    checked_read(builder, "hash-object", "-w", path.name)
                    != declaration["git_blob_sha1"]
                ):
                    raise OSError("Delta builder object differs from the frozen oracle")
            recipe = oracle["pack_recipes"]["delta"]
            prefix = delta / ".git" / "objects" / "pack" / "pack"
            pack_hash = checked_read(
                builder,
                *recipe["arguments"],
                str(prefix),
                input=recipe["stdin_ascii"].encode("ascii"),
            )
            if len(pack_hash) != 40 or any(
                char not in "0123456789abcdef" for char in pack_hash
            ):
                raise OSError("Delta pack builder returned an invalid output identity")
        delta_packs = list((delta / ".git" / "objects" / "pack").glob("*.pack"))
        if len(delta_packs) != 1:
            raise OSError("Delta reader does not contain exactly one owned pack")
        base, target = declarations["base8"], declarations["target8"]
        qualified = qualify_packed_storage(
            delta,
            delta_packs[0],
            form="delta",
            target=target,
            base=base,
            patterns={
                item["git_blob_sha1"]: (
                    lambda offset, count, declaration=item: _oracle_pattern(
                        declaration, offset, count
                    )
                )
                for item in (base, target)
            },
        )
        cells["packed_ref_delta"] = {
            "status": "completed",
            "verified_bytes": base["size"] + target["size"],
            "target_type": qualified["target_header"]["type"],
            "base_type": qualified["base_header"]["type"],
            "depth": qualified["target_row"]["depth"],
            "base_oid": qualified["target_header"]["base"],
            "target_oid": target["git_blob_sha1"],
            "command_sequences": list(range(first, calls.seq + 1)),
        }
        if _canonical_tree(public_root) != own_public:
            raise OSError(
                "Raw qualification changed the completed public canonical fixture"
            )
        if request["role"] == "author":
            canonical = {
                "oracle_sha256": hashlib.sha256(raw_oracle).hexdigest(),
                "roots": {
                    name: _canonical_tree(path)
                    for name, path in (
                        ("public", public_root),
                        ("whole-reader", whole),
                        ("delta-builder", builder),
                        ("delta-reader", delta),
                    )
                },
            }
            writer.write(attempt / "canonical.json", canonical)
        else:
            for record in canonical["roots"].values():
                if _canonical_tree(Path(record["path"])) != record:
                    raise OSError(
                        "Verifier changed shared immutable canonical material"
                    )
    allocated, files = resource_pilot.inventory(root)
    if (
        resource_pilot.native_identity(root) != root_identity
        or allocated > material["retained_reserved_bytes"]
    ):
        raise OSError("Payload retained root exceeds its owner or retention allowance")
    writer.write(
        attempt / "payload.json",
        {
            "cells": cells,
            "root": str(root),
            "native_identity": root_identity,
            "retained_bytes": allocated,
            "inventory": files,
        },
    )


def payload_control():
    from tests.support.resource_pilot import PHASES, read_control
    from tools.update_resource_probe import observe_commands

    attempt, manifest = control_preflight(mode="payload")
    report = observe_commands(
        [
            sys.executable,
            "-m",
            "tests.support.git_resource_pilot",
            "payload",
            str(attempt),
        ],
        attempt / "observer",
        phases=PHASES,
        work_timeout=manifest["time"]["work_seconds"],
        artifact_limit=manifest["artifacts"]["observer_bytes"] - 65536,
        bootstrap=manifest["bootstrap"],
    )
    finish_control(attempt, manifest)
    if (
        report["status"] != "completed"
        or report["command_family_coverage"] != "complete"
        or report["census"]["unaccounted_lifetimes"]
        or report["final_job"]["ActiveProcesses"]
        or report["cleanup_errors"]
        or report["proof_handles_remaining"]
        or report["handle_close_duplicates"]
    ):
        raise OSError("Payload cells did not complete their owned command-family proof")
    facts = json.loads(read_control(attempt / "payload.json"))
    if list(facts["cells"]) != ["public_loose", "packed_whole", "packed_ref_delta"]:
        raise OSError("Payload evidence differs from the frozen three cells")
    commands = {
        row["seq"]: row for row in report["inventory"] if row["kind"] == "command"
    }
    sequences = []
    for cell in facts["cells"].values():
        for sequence in cell["command_sequences"]:
            row = commands[sequence]
            if (
                row["state"] != "finalized"
                or row["return_status"] != "returned"
                or not row["normal_cleanup_complete"]
                or row["final_job"]["ActiveProcesses"]
                or row["final_job"]["PeakJobMemoryUsed"] <= 0
                or row["final_job"]["PeakProcessMemoryUsed"] <= 0
                or os.path.normcase(row["image"])
                != os.path.normcase(str(Path(manifest["material"]["git_executable"])))
            ):
                raise OSError(
                    "Payload command lost original cleanup, counters or installed Git identity"
                )
        sequences.extend(cell["command_sequences"])
        cell["commands_finalized"] = True
    if sequences != list(commands):
        raise OSError(
            "Payload cell ownership does not partition actual command sequences"
        )
    return {
        "cells": facts["cells"],
        "unaccounted_lifetimes": report["census"]["unaccounted_lifetimes"],
        "active_processes": report["final_job"]["ActiveProcesses"],
        "cleanup_errors": tuple(report["cleanup_errors"]),
    }


def main():
    mode = sys.argv[1]
    if mode == "allocate":
        _allocate(int(sys.argv[2]), int(sys.argv[3]))
        return
    if mode == "parent":
        _parent(int(sys.argv[2]))
        return
    from tools.update_resource_probe import _runtime_binding

    _exchange({"event": "hello", "pid": os.getpid(), **_runtime_binding()}, "ready")
    if mode == "peaks":
        _peaks(Path(sys.argv[2]))
    elif mode == "refusal":
        _refusal(sys.argv[2], Path(sys.argv[3]))
    elif mode == "tiny":
        _tiny(Path(sys.argv[2]))
    elif mode == "storage":
        _storage(Path(sys.argv[2]))
    elif mode == "payload":
        _payload(Path(sys.argv[2]))
    else:
        raise OSError("Unknown fixed command pilot")
    _exchange({"event": "done", "pid": os.getpid(), "ok": True}, "continue")


if __name__ == "__main__":
    main()
