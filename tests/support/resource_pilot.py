"""Bounded synthetic public Operations pilot, outside independent fact helpers."""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from brz2obsidian.application.operations import Operations

MIB = 1024 * 1024
SIZE = 16 * MIB
EXPECTED_SHA = "341aacac661ccb210720bedaa9ead5d668fe5ea41a73532fc147c71e34040df1"

PHASES = (
    "setup",
    "inspect",
    "capture",
    "admission",
    "current",
    "retained",
    "pages",
    "stage_current",
    "stage_retained",
    "verify",
    "close",
    "preservation",
)


def boundary(name):
    print(json.dumps({"event": "phase", "name": name, "pid": os.getpid()}), flush=True)
    if sys.stdin.readline() != "continue\n":
        raise OSError("Pilot boundary was not acknowledged")


class Evidence:
    """Charge driver control files before I/O, reserving a terminal record."""

    def __init__(self, *, limit=4 * MIB, terminal_reserve=MIB):
        if (
            type(limit) is not int
            or type(terminal_reserve) is not int
            or not 0 < terminal_reserve <= limit <= 4 * MIB
        ):
            raise ValueError("Invalid driver evidence bounds")
        self.limit = limit
        self.terminal_reserve = terminal_reserve
        self.used = 0

    def write(self, path, value, *, terminal=False):
        data = (
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode()
        if len(data) > MIB:
            raise OSError("Pilot control evidence exceeds its 1 MiB bound")
        ceiling = self.limit if terminal else self.limit - self.terminal_reserve
        if self.used + len(data) > ceiling:
            raise OSError("Pilot aggregate evidence budget exhausted")
        self.used += len(data)
        with path.open("xb") as stream:
            if stream.write(data) != len(data):
                raise OSError("Pilot evidence write was incomplete")


def read_control(path):
    with path.open("rb") as stream:
        raw = stream.read(MIB + 1)
    if len(raw) > MIB:
        raise OSError("Pilot control input exceeds its 1 MiB bound")
    return raw


def inventory(root, *, unit=4096):
    rows = []
    allocated = unit
    pending = [root]
    while pending:
        parent = pending.pop()
        with os.scandir(parent) as entries:
            for entry in entries:
                path = Path(entry.path)
                info = entry.stat(follow_symlinks=False)
                if path.is_symlink() or path.is_junction():
                    rows.append(
                        {
                            "path": path.relative_to(root).as_posix(),
                            "link_not_followed": True,
                        }
                    )
                    allocated += unit
                elif stat.S_ISDIR(info.st_mode):
                    allocated += unit
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    allocated += max(unit, ((info.st_size + unit - 1) // unit) * unit)
                    rows.append(
                        {
                            "path": path.relative_to(root).as_posix(),
                            "size": info.st_size,
                        }
                    )
                else:
                    raise OSError("Unsupported entry in owned allocation inventory")
                if len(rows) > 20000:
                    raise OSError("Owned allocation inventory exceeds its finite count")
    return allocated, rows


def native_identity(path):
    if path.is_symlink() or path.is_junction() or not path.is_dir():
        raise OSError("Owned allocation root is not a physical directory")
    info = path.stat()
    return [info.st_dev, info.st_ino]


def preflight(evidence, ledger_path, expected_sha, writer):
    write_evidence = writer.write
    raw = read_control(ledger_path)
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise OSError("Prior allocation input differs from the pinned ledger")
    ledger = json.loads(raw)
    if (
        type(ledger["global_synthetic_cap_bytes"]) is not int
        or not 0 < ledger["global_synthetic_cap_bytes"] <= 4 * 1024 * MIB
        or type(ledger["phase_only_artifact_reserve_bytes"]) is not int
        or not 0 < ledger["phase_only_artifact_reserve_bytes"] <= 256 * MIB
    ):
        raise OSError("Declared allocation limits exceed the fixed pilot caps")
    namespaces = [
        Path(row["path"]).resolve() for row in ledger["allowed_future_artifact_roots"]
    ]
    if evidence.parent not in namespaces:
        raise OSError("Pilot evidence is outside the declared exclusive namespaces")
    actual_roots = []
    growth = 0
    for row in ledger["roots"]:
        root = Path(row["path"])
        if native_identity(root) != row["native_identity"]:
            raise OSError("Prior owned allocation identity changed")
        allocated, files = inventory(root, unit=row["allocation_unit"])
        growth += max(0, allocated - row["reserved_bytes"])
        actual_roots.append({"root": str(root), "allocated": allocated, "files": files})
    counts = [0] * len(namespaces)
    artifact_bytes = growth
    known_runners = set()
    for index, namespace in enumerate(namespaces):
        if not namespace.exists():
            continue
        native_identity(namespace)
        allocated, files = inventory(namespace)
        artifact_bytes += allocated
        actual_roots.append(
            {"root": str(namespace), "allocated": allocated, "files": files}
        )
        for request in namespace.glob("*/root-request.json"):
            record = json.loads(read_control(request))
            if (
                record.get("context") == expected_sha
                and not (request.parent / "owner.json").exists()
            ):
                raise OSError("Declared pilot root has no completed ownership record")
        for owner in namespace.glob("*/owner.json"):
            record = json.loads(read_control(owner))
            if not isinstance(record.get("context"), str):
                raise OSError("Unknown pilot experiment ownership")
            if record.get("context") != expected_sha:
                continue
            root = Path(record["root"])
            if root.name != "brz2obsidian-353-pilot-" + record["owner"]:
                raise OSError("Unknown pilot owner record")
            marker = json.loads(read_control(root / ".fixture-owner.json"))
            if marker != record or native_identity(root) != record["native_identity"]:
                raise OSError("Owned pilot root or marker changed")
            allocated, files = inventory(root)
            if allocated > 512 * MIB:
                raise OSError("Retained pilot exceeded its 512 MiB allocation envelope")
            counts[index] += 1
            actual_roots.append(
                {"root": str(root), "allocated": allocated, "files": files}
            )
        for receipt in namespace.glob("*/runner.json"):
            known_runners.add(json.loads(read_control(receipt))["path"])
    runner = Path(os.environ["BRZ_CHECK_COUNTS"]).parent
    known_runners.add(str(runner))
    for name in sorted(known_runners):
        path = Path(name)
        check_roots = {
            Path(value)
            for value in ledger.get(
                "allowed_runner_roots",
                [str(namespace.parent / "checks") for namespace in namespaces],
            )
        }
        if path.parent not in check_roots:
            raise OSError("Runner allocation is outside declared check namespaces")
        allocated, files = inventory(path)
        artifact_bytes += allocated
        actual_roots.append({"root": str(path), "allocated": allocated, "files": files})
    if artifact_bytes > ledger["phase_only_artifact_reserve_bytes"]:
        raise OSError("Phase/check artifact reservation exhausted")
    # The input lists the assigned author namespace, then the independent verifier.
    counts[namespaces.index(evidence.parent)] += 1
    verifier_slots = ledger["future_verifier_reserve_bytes"] // (512 * MIB)
    total = (
        ledger["prior_reserved_bytes"]
        + ledger["ledger_and_later_small_report_reserve_bytes"]
        + ledger["phase_only_artifact_reserve_bytes"]
        + (counts[0] + max(verifier_slots, counts[1])) * 512 * MIB
    )
    if total > ledger["global_synthetic_cap_bytes"]:
        raise OSError("Global 4 GiB synthetic reservation exhausted")
    base = Path(tempfile.gettempdir()).resolve()
    if any((parent / ".git").exists() for parent in (base, *base.parents)):
        raise OSError("OS-temp pilot would be inside an enclosing Git repository")
    for path in (base, evidence):
        if shutil.disk_usage(path).free < 512 * MIB:
            raise OSError("Pilot disk preflight lacks 512 MiB on an actual volume")
    write_evidence(
        evidence / "disk-before.json",
        {
            "roots": actual_roots,
            "phase_bytes": artifact_bytes,
            "reserved_total": total,
            "ledger_sha256": expected_sha,
        },
    )
    write_evidence(
        evidence / "runner.json",
        {"path": str(runner), "native_identity": native_identity(runner)},
    )
    owner = uuid4().hex
    root = base / ("brz2obsidian-353-pilot-" + owner)
    write_evidence(
        evidence / "root-request.json",
        {"root": str(root), "owner": owner, "context": expected_sha},
    )
    root.mkdir()
    record = {
        "root": str(root),
        "owner": owner,
        "base": str(base),
        "native_identity": native_identity(root),
        "context": expected_sha,
    }
    write_evidence(root / ".fixture-owner.json", record)
    write_evidence(evidence / "owner.json", record)
    return root, base, total


def git(vault, *args):
    return _git_with_runner(vault, args, subprocess.run)


def _git_with_runner(vault, args, runner):
    result = runner(
        [
            "git",
            "--no-pager",
            "-c",
            "user.name=Resource pilot",
            "-c",
            "user.email=pilot@example.invalid",
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.hooksPath=" + str(vault.parent / "hooks"),
            "-C",
            str(vault),
            *args,
        ],
        capture_output=True,
        check=True,
        timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
    if len(result.stdout) + len(result.stderr) > 65536:
        raise OSError("Synthetic Git control output exceeded 64 KiB")
    return result.stdout


def file_fact(path):
    info = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(65536):
            digest.update(block)
    return {
        "size": info.st_size,
        "mode": info.st_mode,
        "mtime_ns": info.st_mtime_ns,
        "native_identity": [info.st_dev, info.st_ino],
        "sha256": digest.hexdigest(),
    }


def snapshot(vault, source):
    refs = (
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
        .decode()
        .splitlines()
    )
    return {
        "authored": {
            "vault/note.md": file_fact(vault / "note.md"),
            "vault/payload.bin": file_fact(vault / "payload.bin"),
            "source/note.md": file_fact(source / "note.md"),
        },
        "head": read_control(vault / ".git/HEAD").hex(),
        "index": read_control(vault / ".git/index").hex(),
        "user_refs": [ref for ref in refs if not ref.startswith("refs/brz2obsidian/")],
        "converter_refs": [ref for ref in refs if ref.startswith("refs/brz2obsidian/")],
    }


def verify_positions(path):
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        while block := stream.read(65536):
            # Independent lane checks establish each byte's absolute position.
            # This does not reuse the generator's repeated 256-byte block.
            for lane in range(min(256, len(block))):
                values = block[lane::256]
                if values != bytes([(count + lane) % 256]) * len(values):
                    raise OSError(
                        "Staged byte differs from independent positional rule"
                    )
            digest.update(block)
            count += len(block)
    if count != SIZE or digest.hexdigest() != EXPECTED_SHA:
        raise OSError("Staged length/hash differs from the independently pinned value")


def run(evidence, ledger_path, expected_sha):
    facts = {"status": "failed"}
    writer = Evidence()
    write_evidence = writer.write
    try:
        boundary("setup")
        root, base, reserved = preflight(evidence, ledger_path, expected_sha, writer)
        facts.update(root=str(root), temp_base=str(base), reserved_total=reserved)
        vault, source, scratch = (
            root / name for name in ("vault", "source", "scratch")
        )
        for path in (vault, source, scratch, root / "hooks"):
            path.mkdir()
        note = b"Resource pilot note.\n"
        (vault / "note.md").write_bytes(note)
        (source / "note.md").write_bytes(note)
        git(vault, "init", "-q", "--initial-branch=main")
        git(vault, "add", "note.md")
        git(vault, "commit", "-qm", "Synthetic user baseline")
        block = bytes(range(256)) * 256
        with (vault / "payload.bin").open("xb") as stream:
            for _ in range(256):
                stream.write(block)
        del block
        facts["before"] = snapshot(vault, source)
        if facts["before"]["authored"]["vault/payload.bin"]["sha256"] != EXPECTED_SHA:
            raise OSError("Generated input differs from frozen SHA256")
        operations = Operations()
        boundary("inspect")
        admission = operations.inspect_vault(vault)
        if admission.status != "supported" or not admission.inventory_complete:
            raise OSError(f"Initial public admission failed: {admission}")
        boundary("capture")
        capture = operations.capture_checkpoint(
            vault,
            source,
            vault_id="resource-pilot-vault",
            import_id="resource-pilot-import",
            identity={
                "collection_id": "resource-pilot",
                "module_id": "fixture",
                "module_version": "1",
                "profile_id": "profile",
                "profile_version": "1",
                "output_format": 7,
                "settings_digest": "resource-pilot-settings",
            },
            admission=admission,
            review=None,
            boundary="local",
        )
        if capture.status != "captured":
            raise OSError(f"Public checkpoint refused: {capture}")
        facts["checkpoint"] = capture.model_dump(mode="json")
        facts["converter_refs_after_capture"] = snapshot(vault, source)[
            "converter_refs"
        ]
        boundary("admission")
        with operations.inspect_update_inputs(vault) as observed:
            history = observed.history
            if (
                history.status != "intact"
                or history.admission.status != "supported"
                or not history.admission.inventory_complete
            ):
                raise OSError("Public update input admission is incomplete")
            if history.checkpoint.manifest.review_object is not None:
                raise OSError("Pilot unexpectedly contains a saved review")
            facts["manifest"] = history.checkpoint.manifest.model_dump(mode="json")
            with observed.content_session(scratch_parent=scratch) as session:
                boundary("current")
                current = session.acquire("payload.bin", byte_limit=SIZE)
                boundary("retained")
                retained = session.acquire(
                    "payload.bin",
                    role="vault",
                    locator=history.checkpoint.locator,
                    byte_limit=SIZE,
                )
                boundary("pages")
                pages = []
                for reference in (current, retained):
                    if reference.size != SIZE or reference.sha256 != EXPECTED_SHA:
                        raise OSError(
                            "Admitted content identity differs from pinned bytes"
                        )
                    pages.extend(
                        [
                            session.page(reference, offset=255, limit=4).hex(),
                            session.page(reference, offset=SIZE - 4, limit=4).hex(),
                        ]
                    )
                if pages != ["ff000102", "fcfdfeff"] * 2:
                    raise OSError("Admitted literal pages differ")
                boundary("stage_current")
                first = session.stage(current, byte_limit=SIZE)
                boundary("stage_retained")
                second = session.stage(retained, byte_limit=SIZE)
                boundary("verify")
                for stage in (first, second):
                    verify_positions(stage.path)
                    if stage.mode != "100644":
                        raise OSError("Staged mode differs from ordinary input")
                boundary("close")
            if first.path.exists() or second.path.exists():
                raise OSError("Owned stages survived content session close")
        boundary("preservation")
        facts["after"] = snapshot(vault, source)
        for name in ("authored", "head", "index", "user_refs"):
            if facts["before"][name] != facts["after"][name]:
                raise OSError(f"Public read/capture route changed authored {name}")
        if facts["converter_refs_after_capture"] != facts["after"]["converter_refs"]:
            raise OSError("Content observation changed converter refs")
        allocated, files = inventory(root)
        if allocated > 512 * MIB:
            raise OSError("Pilot exceeded its 512 MiB disk envelope")
        write_evidence(
            evidence / "disk-after.json",
            {"root": str(root), "allocated": allocated, "files": files},
        )
        facts.update(
            status="completed",
            opaque_input_bytes=SIZE,
            payload_sha256=EXPECTED_SHA,
            pages=pages,
            stages_verified=2,
            stages_removed=True,
            saved_review_present=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        facts["error"] = str(error)
        raise
    finally:
        write_evidence(evidence / "pilot.json", facts, terminal=True)
    print(json.dumps({"event": "done", "pid": os.getpid(), "ok": True}), flush=True)
    if sys.stdin.readline() != "continue\n":
        raise OSError("Pilot terminal outcome was not acknowledged")


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]), sys.argv[3])
