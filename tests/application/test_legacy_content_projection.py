"""Exact old projection bytes through admitted content sessions."""

import io
import json
import os
import tempfile
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest

from brz2obsidian.application.operations import Operations
from tests.application.test_checkpoint_payload import git

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/saved_reviews/memory-347"


def test_unadmitted_reader_cannot_construct_comparison():
    from brz2obsidian.publication.legacy_content import ContentComparison

    with pytest.raises(OSError, match="Live content session"):
        ContentComparison(
            object(), (), raw_work_limit=0, metadata_limit=2, node_limit=1
        )


@pytest.fixture(scope="module")
def projection_vault():
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-354-projection-"))
    owner = {"root": str(root), "owner": uuid4().hex}
    (root / ".fixture-owner.json").write_text(json.dumps(owner))
    records = Path(__file__).resolve().parents[2] / "tmp/legacy-content-projection"
    records.mkdir(parents=True, exist_ok=True)
    (records / (owner["owner"] + ".json")).write_text(json.dumps(owner))
    vault, source, scratch = (root / name for name in ("vault", "source", "scratch"))
    for path in (vault, source, scratch):
        path.mkdir()
    (vault / "literal.bin").write_bytes(b"\xfb\xff")
    (source / "literal.bin").write_bytes(b"\xfb\xff")
    for index, raw in enumerate((b"", b"a", b"ab", b"abc", b"\xfb\xff")):
        (vault / f"vector-{index}.bin").write_bytes(raw)
    for name in ("attachment.current.bin", "attachment.incoming.bin"):
        (vault / name).write_bytes((FIXTURES / name).read_bytes())
    with (vault / "pattern.bin").open("wb") as stream:
        for _ in range(43692):
            stream.write(b"abc")
    git(vault, "init", "-q")
    operations = Operations()
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="projection-vault",
        import_id="projection-import",
        identity={
            "collection_id": "projection",
            "module_id": "fixture",
            "module_version": "1",
            "profile_id": "profile",
            "profile_version": "1",
            "output_format": 7,
            "settings_digest": "literal-settings",
        },
        admission=operations.inspect_vault(vault),
        review=None,
        boundary="local",
    )
    assert captured.status == "captured"
    return vault, scratch


def test_coadmitted_literal_identity_and_complete_legacy_projection(projection_vault):
    vault, scratch = projection_vault
    with (
        Operations().inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=scratch) as session,
    ):
        current = session.acquire("literal.bin", byte_limit=2)
        retained = session.acquire(
            "literal.bin",
            role="vault",
            locator=observed.history.checkpoint.locator,
            byte_limit=2,
        )
        comparison = session.comparison(
            (current, retained),
            raw_work_limit=3,
            metadata_limit=1024,
            node_limit=9,
        )
        assert current != retained
        assert comparison.identity(current) == comparison.identity(retained)
        assert comparison.identity(current).content_id == (
            "sha256:db8fed54159afe40ace5b49d702259fd88c9c4009307181824487baab5c6bdea:2"
        )
        from brz2obsidian.publication.legacy_content import LegacyContentSlot

        result = comparison.project_legacy(
            LegacyContentSlot(current, None),
            dialect="Jc",
            raw_work_limit=3,
            encoded_byte_limit=32,
            metadata_limit=28,
            node_limit=2,
            depth_limit=4,
            preview_limit=32,
        )
        assert result.preview == b'{"data":"-_8=","reference":null}'
        assert result.encoded_size == 32
        assert result.sha256 == (
            "9cae700a35705386f04cf476aeda79668327936fb98bf2b4886f10698455cc01"
        )


def project(comparison, root, **changes):
    options = {
        "dialect": "Jc",
        "raw_work_limit": 1048576,
        "encoded_byte_limit": 65536,
        "metadata_limit": 65536,
        "node_limit": 4096,
        "depth_limit": 64,
        "preview_limit": 65536,
    }
    return comparison.project_legacy(root, **(options | changes))


def metadata_node(value):
    from brz2obsidian.publication.legacy_content import LegacyObject

    if type(value) is dict:
        return LegacyObject(
            tuple((key, metadata_node(child)) for key, child in value.items())
        )
    if type(value) is list:
        return tuple(metadata_node(child) for child in value)
    return value


def test_frozen_dialects_references_and_escaping(projection_vault):
    from brz2obsidian.contracts import ImmutableContentReference
    from brz2obsidian.publication.legacy_content import LegacyContentSlot

    vectors = json.loads((FIXTURES / "encoding-vectors.json").read_bytes())
    vault, scratch = projection_vault
    with (
        Operations().inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=scratch) as session,
    ):
        references = tuple(
            session.acquire(f"vector-{i}.bin", byte_limit=3) for i in range(5)
        )
        comparison = session.comparison(
            references, raw_work_limit=13, metadata_limit=2048, node_limit=21
        )
        for reference, vector in zip(references, vectors["content"], strict=True):
            for dialect in ("Jc", "Js", "Ju"):
                expected = vector[dialect]
                result = project(
                    comparison, LegacyContentSlot(reference, None), dialect=dialect
                )
                assert (result.preview, result.encoded_size, result.sha256) == (
                    expected["preimage"].encode(),
                    expected["size"],
                    expected["sha256"],
                )
        historical = ImmutableContentReference(
            content_id="literal:fbff",
            sha256="db8fed54159afe40ace5b49d702259fd88c9c4009307181824487baab5c6bdea",
            size=2,
        )
        result = project(comparison, LegacyContentSlot(references[-1], historical))
        expected = vectors["reference_present"]["Jc"]
        assert result.preview == expected["preimage"].encode()
        assert result.encoded_size == 142
        assert (
            result.sha256
            == "c738504e17d903738dfba70a5cbecbc7eda60f6e90d49e006c2951e629628fe3"
        )
        ordered = vectors["ordering_and_escaping"]
        for dialect in ("Jc", "Js", "Ju"):
            result = project(
                comparison,
                metadata_node(ordered["input_insertion_order"]),
                dialect=dialect,
                raw_work_limit=0,
            )
            assert result.preview == ordered[dialect]["preimage"].encode()


def test_reserved_os_reads_and_whole_tree_admission(projection_vault, monkeypatch):
    from brz2obsidian.publication.legacy_content import LegacyContentSlot, LegacyObject

    vault, scratch = projection_vault
    with (
        Operations().inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=scratch) as session,
    ):
        reference = session.acquire("literal.bin", byte_limit=2)
        requests = []
        original = os.fdopen
        original_fstat = os.fstat
        backing = next(
            path for path in scratch.glob("content-*/*") if path.stat().st_size == 2
        )
        backing_info = backing.stat()
        fault = None

        class Reads:
            def __init__(self, stream):
                assert type(stream) is io.FileIO
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.stream.close()

            def fileno(self):
                return self.stream.fileno()

            def read(self, size):
                requests.append(size)
                if fault == "short":
                    return self.stream.read(size - 1)
                if fault == "trailing" and self.stream.tell() == 2:
                    return b"x"
                return self.stream.read(size)

        def unbuffered(fd, mode, *args, **kwargs):
            info = os.fstat(fd)
            owned = (info.st_dev, info.st_ino) == (
                backing_info.st_dev,
                backing_info.st_ino,
            )
            stream = original(fd, mode, *args, **kwargs)
            if owned:
                assert kwargs.get("buffering") == 0
                return Reads(stream)
            return stream

        def opened_info(fd):
            info = original_fstat(fd)
            if fault == "opened" and (info.st_dev, info.st_ino) == (
                backing_info.st_dev,
                backing_info.st_ino,
            ):
                return SimpleNamespace(
                    st_dev=info.st_dev,
                    st_ino=info.st_ino,
                    st_size=info.st_size + 1,
                    st_mtime_ns=info.st_mtime_ns,
                )
            return info

        monkeypatch.setattr(os, "fdopen", unbuffered)
        monkeypatch.setattr(os, "fstat", opened_info)
        with pytest.raises(OSError, match="[Mm]etadata"):
            session.comparison(
                (reference, reference.model_copy(update={"size": True})),
                raw_work_limit=0,
                metadata_limit=2,
                node_limit=9,
            )
        assert requests == []
        comparison = session.comparison(
            (reference, reference.model_copy()),
            raw_work_limit=3,
            metadata_limit=1024,
            node_limit=9,
        )
        assert requests == [2, 1]
        slot = LegacyContentSlot(reference, None)
        requests.clear()
        result = project(
            comparison,
            (slot, slot),
            raw_work_limit=6,
            encoded_byte_limit=67,
            metadata_limit=59,
            node_limit=5,
        )
        assert requests == [2, 1, 2, 1]
        assert (
            result.preview
            == b'[{"data":"-_8=","reference":null},{"data":"-_8=","reference":null}]'
        )
        for changes in (
            {"raw_work_limit": 2},
            {"encoded_byte_limit": 31},
            {"metadata_limit": 27},
            {"node_limit": 1},
            {"depth_limit": 1},
        ):
            requests.clear()
            with pytest.raises(OSError):
                project(comparison, slot, **changes)
            assert requests == []
        requests.clear()
        with pytest.raises(OSError, match="Raw work"):
            project(comparison, (slot, slot), raw_work_limit=5)
        assert sum(requests) == 3
        cyclic = LegacyObject(())
        object.__setattr__(cyclic, "fields", (("cycle", cyclic),))
        invalid = [
            [],
            {},
            b"opaque",
            1.5,
            LegacyObject((("dup", 1), ("dup", 2))),
            cyclic,
            LegacyObject((("x", "\x00" * 100),)),
        ]
        for node in invalid:
            requests.clear()
            with pytest.raises(OSError):
                project(comparison, (slot, node), metadata_limit=100)
            assert requests == []
        for fault, expected_requests in (
            ("short", [2]),
            ("trailing", [2, 1]),
            ("opened", []),
        ):
            requests.clear()
            with pytest.raises(OSError):
                project(comparison, slot, raw_work_limit=3, preview_limit=1)
            assert requests == expected_requests


def test_membership_lifetime_typed_values_and_late_integrity(projection_vault):
    from brz2obsidian.contracts import ContentIdentity
    from brz2obsidian.publication.legacy_content import LegacyContentSlot

    for size in (True, -1, 1.0):
        with pytest.raises(ValueError):
            ContentIdentity(
                content_id="sha256:" + "0" * 64 + ":1", sha256="0" * 64, size=size
            )
    with pytest.raises(ValueError):
        ContentIdentity(
            content_id="sha256:" + "0" * 64 + ":01", sha256="0" * 64, size=1
        )
    vault, scratch = projection_vault
    head = (vault / ".git/HEAD").read_bytes()
    refs = git(vault, "for-each-ref")
    original = (vault / "literal.bin").read_bytes()
    with Operations().inspect_update_inputs(vault) as observed:
        with observed.content_session(scratch_parent=scratch) as session:
            reference = session.acquire("literal.bin", byte_limit=2)
            comparison = session.comparison(
                (reference,), raw_work_limit=3, metadata_limit=512, node_limit=5
            )
            identity = comparison.identity(reference.model_copy())
            for changes in (
                {"size": True},
                {"size": 3},
                {"sha256": "0" * 64},
                {"content_id": "unknown"},
            ):
                altered = reference.model_copy(update=changes)
                with pytest.raises(OSError):
                    comparison.identity(altered)
                with pytest.raises(OSError):
                    session.comparison(
                        (reference, altered),
                        raw_work_limit=3,
                        metadata_limit=1024,
                        node_limit=9,
                    )
            outside = session.acquire("vector-1.bin", byte_limit=1)
            with pytest.raises(OSError, match="outside"):
                comparison.identity(outside)
            with observed.content_session(scratch_parent=scratch) as other:
                foreign = other.acquire("literal.bin", byte_limit=2)
                with pytest.raises(OSError, match="outside"):
                    comparison.identity(foreign)
            slot = LegacyContentSlot(reference, None)
            with pytest.raises(OSError, match="Historical"):
                project(comparison, LegacyContentSlot(reference, outside))
            cancelled = Event()
            cancelled.set()
            with pytest.raises(OSError, match="cancel"):
                project(comparison, slot, cancel=cancelled)
            with pytest.raises(OSError, match="time"):
                project(comparison, slot, timeout=1e-9)
            for changes in (
                {"raw_work_limit": True},
                {"encoded_byte_limit": -1},
                {"metadata_limit": 1.5},
                {"node_limit": False},
                {"depth_limit": 257},
                {"preview_limit": 65537},
                {"dialect": "unknown"},
            ):
                with pytest.raises(OSError):
                    project(comparison, slot, **changes)
            backing = next(
                path for path in scratch.glob("content-*/*") if path.stat().st_size == 2
            )
            for damage in (b"\xfb\xff!", b"\xfb", b"\xfb\x00"):
                backing.write_bytes(damage)
                assert comparison.identity(reference) == identity
                with pytest.raises(OSError):
                    project(comparison, slot, preview_limit=1)
            backing.write_bytes(b"\xfb\xff")
        with pytest.raises(OSError, match="closed"):
            comparison.identity(reference)
        with pytest.raises(OSError, match="closed"):
            project(comparison, slot)
    assert (vault / "literal.bin").read_bytes() == original
    assert (vault / ".git/HEAD").read_bytes() == head
    assert git(vault, "for-each-ref") == refs


def test_frozen_candidate_and_real_chunk_residues(projection_vault):
    from brz2obsidian.publication.legacy_content import LegacyContentSlot, LegacyObject

    proof = json.loads((FIXTURES / "proof-vectors.json").read_bytes())
    vault, scratch = projection_vault
    with (
        Operations().inspect_update_inputs(vault) as observed,
        observed.content_session(scratch_parent=scratch) as session,
    ):
        current = session.acquire("attachment.current.bin", byte_limit=9)
        incoming = session.acquire("attachment.incoming.bin", byte_limit=3)
        pattern = session.acquire("pattern.bin", byte_limit=131076)
        comparison = session.comparison(
            (current, incoming, pattern),
            raw_work_limit=131091,
            metadata_limit=1024,
            node_limit=13,
        )
        fields = json.loads(proof[1]["preimage"])
        # Frozen independent positions; never infer slots from a digest map.
        for branch, index, tail, reference in (
            ("outputs", 0, (), current),
            ("outputs", 1, (), incoming),
            ("target_facts", 0, (), current),
            ("target_facts", 1, (), incoming),
            ("target_facts", 0, ("structure",), current),
            ("target_facts", 1, ("structure",), incoming),
        ):
            parent = fields[branch][index]
            for name in tail:
                parent = parent[name]
            parent["content"] = LegacyContentSlot(reference, None)
        result = project(
            comparison,
            metadata_node(fields),
            dialect="Js",
            raw_work_limit=42,
            encoded_byte_limit=7780,
            metadata_limit=7732,
        )
        assert result.preview == proof[1]["preimage"].encode()
        assert result.encoded_size == 7780
        assert (
            result.sha256
            == "f752b9c2bd3d95bb84d7c2440eb743f9e2ce6b046de2aea9487a0359be36bfd7"
        )
        baseline = project(
            comparison,
            metadata_node(json.loads(proof[0]["preimage"])),
            raw_work_limit=0,
        )
        assert baseline.preview == proof[0]["preimage"].encode()
        assert baseline.sha256 == proof[0]["sha256"]
        result = project(
            comparison,
            LegacyContentSlot(pattern, None),
            raw_work_limit=131077,
            encoded_byte_limit=174796,
            metadata_limit=28,
            preview_limit=32,
        )
        assert result.preview == b'{"data":"YWJjYWJjYWJjYWJjYWJjYWJ'
        assert result.encoded_size == 174796
        assert (
            result.sha256
            == "6fe9d81163fe3fda8c5f2f3e77beb339c7cdc6ed49d8fae3ee59cd8dc6b5c15d"
        )
        kept = project(
            comparison,
            LegacyObject((("none", None), ("false", False), ("empty", ()))),
            raw_work_limit=0,
        )
        assert kept.preview == b'{"empty":[],"false":false,"none":null}'
