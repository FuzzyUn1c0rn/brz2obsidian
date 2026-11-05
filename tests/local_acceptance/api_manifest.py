"""Source-bound API acceptance inputs. Standard library only; no converter imports."""

import hashlib
import json
from asyncio import current_task
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from functools import wraps
from inspect import signature
from pathlib import Path, PurePosixPath
from threading import current_thread


def read_json(data, *, parse_float=float):
    def unique(pairs):
        result = dict(pairs)
        assert len(result) == len(pairs), "duplicate evidence JSON keys"
        return result

    return json.loads(
        data.decode("utf-8"), object_pairs_hook=unique, parse_float=parse_float
    )


def safe_path(root, name):
    path = PurePosixPath(name)
    assert name and str(path) == name and not path.is_absolute(), "unsafe audit path"
    assert not {".", ".."}.intersection(name.split("/")), "unsafe audit path"
    assert not any(c in name for c in "\\:"), "unsafe audit path"
    result = root / name
    assert result.resolve().is_relative_to(root.resolve()), "unsafe audit path"
    return result


def _same_json(left, right):
    """Compare declaration values without Python's bool/int/float coercion."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _same_json(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same_json(a, b) for a, b in zip(left, right)
        )
    return left is right or left == right


@dataclass(frozen=True)
class ApiBaseline:
    manifest_path: Path
    fingerprint: str
    data: dict

    def _declarations(self):
        raw = self.manifest_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == self.fingerprint, (
            "baseline manifest changed; independent requalification required"
        )
        declarations = read_json(raw)
        assert _same_json(declarations, self.data), (
            "baseline manifest changed in memory"
        )
        return declarations

    def verify(self):
        """Always check the complete pin, even inside an active audit."""
        try:
            self._verify_files()
        except Exception:
            _poison_for(self)
            raise

    def _verify_files(self):
        for name, expected in self._declarations()["files"].items():
            path = safe_path(self.manifest_path.parent, name)
            assert path.is_file(), "baseline evidence changed"
            digest, length = hashlib.sha256(), 0
            with path.open("rb") as stream:
                while block := stream.read(131072):
                    length += len(block)
                    digest.update(block)
            assert (
                length == expected["length"]
                and digest.hexdigest() == expected["sha256"]
            ), "baseline evidence changed; independent requalification required"

    def bytes(self, name):
        try:
            return _pinned_bytes(self.manifest_path, self._declarations(), name)
        except Exception:
            _poison_for(self)
            raise

    def json(self, name):
        return read_json(self.bytes(name))


def _pinned_bytes(manifest, declarations, name):
    assert name in declarations["files"], "unbound baseline input"
    payload = safe_path(manifest.parent, name).read_bytes()
    expected = declarations["files"][name]
    assert (
        len(payload) == expected["length"]
        and hashlib.sha256(payload).hexdigest() == expected["sha256"]
    ), "baseline consumed evidence changed"
    return payload


_ACTIVE_PASSES = ContextVar("independent_api_audit_passes", default=())


def _execution_context():
    try:
        task = current_task()
    except RuntimeError:
        task = None
    return current_thread(), task


def _poison_for(owner):
    for assessment in _ACTIVE_PASSES.get():
        if assessment.owner is owner and assessment.joinable():
            assessment.fail()


class _AuditPass:
    def __init__(self, owner):
        self.owner = owner
        self.path, self.pin = owner.manifest_path, owner.fingerprint
        self.declarations = deepcopy(owner._declarations())
        self.memo = {}
        self.origin = _execution_context()
        self.closed = False
        self.failed = False
        self.view = _PassView(self)

    def joinable(self):
        return (
            not self.closed
            and self.origin == _execution_context()
            and self in _ACTIVE_PASSES.get()
        )

    def fail(self):
        self.failed = True
        self.memo.clear()

    def check(self):
        assert self.joinable(), "expired API audit pass"
        assert not self.failed, "API audit pass already refused"
        valid = (
            self.owner.manifest_path == self.path
            and self.owner.fingerprint == self.pin
            and _same_json(self.owner.data, self.declarations)
        )
        if not valid:
            self.fail()
            raise AssertionError("baseline manifest changed in memory")


class _PassView:
    def __init__(self, assessment):
        self._assessment = assessment

    @property
    def manifest_path(self):
        self._assessment.check()
        return self._assessment.path

    @property
    def fingerprint(self):
        self._assessment.check()
        return self._assessment.pin

    @property
    def data(self):
        self._assessment.check()
        return deepcopy(self._assessment.declarations)

    def bytes(self, name):
        self._assessment.check()
        try:
            return _pinned_bytes(
                self._assessment.path, self._assessment.declarations, name
            )
        except Exception:
            self._assessment.fail()
            raise

    def json(self, name):
        return read_json(self.bytes(name))

    def verify(self):
        self._assessment.check()
        self._assessment.owner.verify()


@contextmanager
def _audit_pass(baseline):
    """Privately owned lifetime; its view cannot qualify a later audit."""
    active = _ACTIVE_PASSES.get()
    if isinstance(baseline, _PassView):
        if baseline._assessment.joinable():
            baseline._assessment.check()
            yield baseline
            baseline._assessment.check()
            return
        baseline = baseline._assessment.owner
    existing = next((p for p in active if p.owner is baseline and p.joinable()), None)
    if existing is not None:
        existing.check()
        yield existing.view
        existing.check()
        return
    baseline.verify()
    assessment = _AuditPass(baseline)
    token = _ACTIVE_PASSES.set((*active, assessment))
    try:
        yield assessment.view
        assessment.check()
        baseline.verify()
    finally:
        assessment.closed = True
        assessment.memo.clear()
        _ACTIVE_PASSES.reset(token)


def audited(function=None, *, reuse=None):
    """Own a public helper's pin boundary; only immutable scope/coverage reuse."""
    if function is None:
        return lambda candidate: audited(candidate, reuse=reuse)
    assert reuse in {None, "scope", "coverage"}
    call = signature(function)

    @wraps(function)
    def checked(*args, **kwargs):
        arguments = call.bind(*args, **kwargs)
        arguments.apply_defaults()
        with _audit_pass(arguments.arguments["baseline"]) as view:
            assessment = view._assessment
            key = (function, arguments.arguments.get("profile_version"))
            if reuse is not None and key in assessment.memo:
                return assessment.memo[key]
            arguments.arguments["baseline"] = view
            try:
                result = function(*arguments.args, **arguments.kwargs)
            except Exception:
                assessment.memo.clear()
                raise
            if reuse is not None:
                assessment.memo[key] = result
            return result

    return checked


def load_baseline(manifest_path, expected_sha256):
    path = Path(manifest_path)
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_sha256, (
        "baseline manifest changed; independent requalification required"
    )
    data = read_json(raw)
    assert data["schema"] in {
        "brz2obsidian.api-acceptance/1",
        "brz2obsidian.api-acceptance/2",
    }, "baseline schema"
    if data["schema"] == "brz2obsidian.api-acceptance/1":
        assert "scope_inputs" not in data, "version1 does not grant scope inputs"
    else:
        required = {
            "schema",
            "files",
            "brain",
            "scope",
            "graphs",
            "types",
            "tags",
            "statistics",
            "link_attachments",
            "link_attachment_outcomes",
            "relationship_metadata",
            "no_notes",
            "payloads",
            "attachment_inventories",
            "attachment_metadata",
            "scope_inputs",
            "qualification",
            "archive_matches",
            "one_way_controls",
        }
        assert (
            required
            <= data.keys()
            <= required | {"source_packet_ledger", "http_responses"}
        ), "closed version2 baseline fields"
    baseline = ApiBaseline(path, expected_sha256, data)
    baseline.verify()
    return baseline
