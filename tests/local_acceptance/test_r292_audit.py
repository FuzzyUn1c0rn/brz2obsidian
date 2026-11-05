"""Independent source-bound complete auditors for the accepted #292 output."""

import asyncio
import hashlib
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow, local_api_workflow
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef
from tests.local_acceptance.api_checker import (
    audit_baseline,
    check_api_vault,
    source_facts,
)
from tests.local_acceptance.api_manifest import load_baseline
from tests.local_acceptance.api_recording import ApiRecording
from tests.local_acceptance.checker import check_run_result, check_vault, read_source
from tests.local_acceptance.facts import relationships
from tests.local_acceptance.test_api_acceptance import source_case
from tests.local_acceptance.test_api_scope_v3 import scope_baseline
from tests.support.audit_sources import (
    ABSENT_INTERMEDIATE_ICON,
    SCHEMA,
    TAG_NOTE,
    VIDEO_URLS,
    paired_audit_source,
    uncreated_tag_source,
)
from tests.support.local_api import BRAIN, api_server
from tests.support.type_tag_sources import IDS, TypeTagApi, brz_source


@pytest.fixture(scope="module")
def paired_outputs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("r292-independent")
    source, api = paired_audit_source(directory / "source.brz")
    brz_vault, api_vault = directory / "brz-vault", directory / "api-vault"
    result = default_workflow().convert(source, brz_vault)
    assert result.outcome in {"clean", "warnings"}, result.issues
    (directory / "brz-result.json").write_bytes(
        result.model_dump_json(by_alias=True).encode()
    )
    qualification = scope_baseline(directory / "separate-direction-controls")
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            directory / "recording",
            upstream,
            brain_id=BRAIN,
            credential="KEY",
            purpose="convert",
        )
        with recording:
            workflow = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: "KEY"
            )
            result = workflow.convert(LocalApiSourceRef(BRAIN), api_vault)
            assert result.outcome in {"clean", "warnings"}, result.issues
            (directory / "api-result.json").write_bytes(
                result.model_dump_json(by_alias=True).encode()
            )
            recording.complete()
        baseline = recording.seal(qualification=qualification)
    return source, brz_vault, baseline, api_vault


def test_current_paired_outputs_are_source_bound(paired_outputs):
    source, brz_vault, baseline, api_vault = paired_outputs
    brz = check_vault(source, brz_vault)
    raw_api = audit_baseline(baseline, profile_version="4")
    api = check_api_vault(baseline, api_vault, profile_version="4")
    assert brz and raw_api and api
    for vault in (brz_vault, api_vault):
        record = json.loads((vault / "migration-record.json").read_bytes())
        assert record["schema_version"] == 8
        assert record["renderer_version"] == "8"
        assert len(record["classification_assignments"]) == 17
        assert len({a["item_key"] for a in record["classification_assignments"]}) == 17
        assert (
            len(
                [
                    t
                    for t in record["item_targets"]
                    if t["relative_path"].startswith("Categories/")
                ]
            )
            == 14
        )
        names = {
            row["item_key"]: row["original_title"] for row in record["item_targets"]
        }
        base = {
            (names[row["definition_key"]], names[row["item_key"]])
            for row in record["classification_assignments"]
            if names[row["definition_key"]] in {"A", "B", "C", "E"}
        }
        assert base == {
            ("A", "B"),
            ("A", "E"),
            ("A", "G"),
            ("B", "C"),
            ("C", "D"),
            ("E", "F"),
        }
        assert sum(row["created"] for row in record["item_targets"]) == 21
        assert {
            (names[row["tag_key"]], names[row["item_key"]])
            for row in record["tag_memberships"]
        } == {("T", "B"), ("U", "T")}
        tag_note = next(
            row for row in record["item_targets"] if row["original_title"] == "T"
        )
        absent_tag = next(
            row for row in record["item_targets"] if row["original_title"] == "U"
        )
        assert tag_note["created"] is True and absent_tag["created"] is False
        urls = {
            row["external_uri"]: row
            for row in record["asset_targets"]
            if row["role"] == "url"
        }
        assert set(urls) == set(VIDEO_URLS)
        assert sum(row["video_presentation"] is not None for row in urls.values()) == (
            2 if vault == brz_vault else 0
        )
        h4 = next(
            row for row in record["item_targets"] if row["original_title"] == "H4"
        )
        assert (h4["declared_appearance"] or {}).get("icon_asset_id") == (
            ABSENT_INTERMEDIATE_ICON if vault == brz_vault else None
        )
        assert h4["icon_snapshot"]["explicit_icon_asset_id"] is None
        assert (
            h4["icon_snapshot"]["appearance_category_key"]
            == "00000000-0000-0000-0000-000000000021"
        )
        assert (
            h4["icon_snapshot"]["effective_icon_asset_id"]
            == "00000000-0000-0000-0000-0000000001f6"
        )
    assert brz["inherited_fallback_affected_members"] == 7
    assert brz["neutral_affected_members"] == 0
    assert brz["warnings"] == 3 and brz["native_icon_depth_warnings"] == 2


def test_icon_oracle_terminates_and_distinguishes_native_depth():
    from tests.local_acceptance.appearance import resolve_icon

    categories = {f"H{i}" for i in range(10)}
    providers = {f"H{i}": f"H{i - 1}" for i in range(1, 10)} | {"N8": "H7", "N9": "H8"}
    memberships = {key: {value} for key, value in providers.items()}
    owned = {"H0": "root-owned"}
    assert (
        resolve_icon("N9", owned, providers, memberships, categories).asset
        == "root-owned"
    )
    assert (
        resolve_icon("N9", owned, providers, memberships, categories, limit=8).status
        == "depth"
    )
    assert (
        resolve_icon("N8", owned, providers, memberships, categories, limit=8).asset
        == "root-owned"
    )
    assert (
        resolve_icon(
            "N9",
            owned | {"H4": "near-owned"},
            providers,
            memberships,
            categories,
            limit=8,
        ).asset
        == "near-owned"
    )
    assert (
        resolve_icon(
            "N9", owned | {"N9": "own"}, providers, memberships, categories
        ).asset
        == "own"
    )
    blank = providers | {"H4": None}
    assert resolve_icon("N9", owned, blank, memberships, categories).status == "blank"
    invalid = providers | {"H4": "missing"}
    assert (
        resolve_icon("N9", owned, invalid, memberships, categories).status == "invalid"
    )
    assert (
        resolve_icon(
            "N9", owned, providers | {"H4": "H8"}, memberships, categories
        ).status
        == "invalid"
    )
    cyclic = providers | {"H0": "H8"}
    cyclic_memberships = memberships | {"H0": {"H8"}}
    result = resolve_icon("N9", {}, cyclic, cyclic_memberships, categories)
    assert (
        result.status == "cycle" and result.asset is None and result.chain[-1] == "H8"
    )
    assert (
        resolve_icon("N9", {}, cyclic, cyclic_memberships, categories, limit=8).status
        == "depth"
    )
    assert (
        resolve_icon(
            "N9",
            {},
            providers | {"H1": "H8"},
            memberships | {"H1": {"H8"}},
            categories,
            limit=8,
        ).status
        == "cycle"
    )
    assert (
        resolve_icon(
            "N9", {"H0": "before-cycle"}, cyclic, cyclic_memberships, categories
        ).asset
        == "before-cycle"
    )


def test_uncreated_child_tag_keeps_nested_membership_listing(tmp_path):
    source, api = uncreated_tag_source(tmp_path / "uncreated-tags.brz")
    brz_vault, api_vault = tmp_path / "brz", tmp_path / "api"
    assert default_workflow().convert(source, brz_vault).outcome == "clean"
    qualification = scope_baseline(tmp_path / "tag-controls")
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "tag-recording",
            upstream,
            brain_id=BRAIN,
            credential="KEY",
            purpose="convert",
        )
        with recording:
            result = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: "KEY"
            ).convert(LocalApiSourceRef(BRAIN), api_vault)
            assert result.outcome == "clean", result.issues
            recording.complete()
        baseline = recording.seal(qualification=qualification)
    check_vault(source, brz_vault)
    check_api_vault(baseline, api_vault, profile_version="4")
    for vault in (brz_vault, api_vault):
        record = json.loads((vault / "migration-record.json").read_bytes())
        child = next(
            row for row in record["item_targets"] if row["original_title"] == "T"
        )
        assert (
            child["created"] is False and not (vault / child["relative_path"]).exists()
        )
        assert record["counts"]["native_tag_memberships"] == 0
        assert record["counts"]["uncreated_tag_memberships"] == 1
        assert (vault / "Tag memberships.md").read_text(encoding="utf-8").count(
            "- Nested source tag: [[Notes/T.md|T]] (#T); uncreated target."
        ) == 1


def test_historical_api_profiles_keep_qualified_boundaries(tmp_path, paired_outputs):
    (tmp_path / "old").mkdir()
    old, _ = source_case(tmp_path / "old")
    for profile in ("1", "2"):
        thoughts, relations, attachments, _ = source_facts(old, profile_version=profile)
        assert (len(thoughts), len(relations), len(attachments)) == (4, 5, 4)
        assert sum(r["kind"] == "classification" for r in relations.values()) == 1
    third = scope_baseline(tmp_path / "third")
    for profile in ("3", "4"):
        raw = audit_baseline(third, profile_version=profile)
        assert raw["classifications"] == 1
        assert raw["payloads"] >= 10
    current = paired_outputs[2]
    for profile in ("1", "2", "3"):
        with pytest.raises(AssertionError, match="unqualified raw relationship"):
            source_facts(current, profile_version=profile)


def test_independent_api_audit_refuses_a_consistent_source_type_cycle(tmp_path):
    api = TypeTagApi(
        edges=((10, 11, 1, 3, -1), (11, 10, 1, 3, -1)), type_fields={10: 11, 11: 10}
    )
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    qualification = scope_baseline(tmp_path / "qualified-controls")
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "cyclic-source", upstream, brain_id=BRAIN, credential="KEY"
        )
        with recording:
            recording.complete()
        baseline = recording.seal(qualification=qualification)
    with pytest.raises(AssertionError, match="type-assignment cycle"):
        audit_baseline(baseline, profile_version="4")


@pytest.mark.parametrize(
    "edges,reason",
    [
        (((17, 18, 1, 7, -1), (18, 17, 1, 7, -1)), "tag cycle"),
        (((17, 18, 3, 1, -1),), "navigation roles"),
    ],
)
def test_independent_oracles_refuse_unqualified_source_forms(tmp_path, edges, reason):
    source = brz_source(tmp_path / "unqualified.brz", edges=edges, type_fields={})
    with ZipFile(source) as archive:
        raw = read_source(archive)
    with pytest.raises(AssertionError):
        relationships(raw)
    api = TypeTagApi(edges=edges, type_fields={})
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    controls = scope_baseline(tmp_path / "controls")
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "unqualified-http", upstream, brain_id=BRAIN, credential="KEY"
        )
        with recording:
            recording.complete()
        baseline = recording.seal(qualification=controls)
    with pytest.raises(AssertionError, match=reason):
        audit_baseline(baseline, profile_version="4")


def test_explicit_one_source_or_pair_audit_records_bound_verdicts(
    tmp_path, paired_outputs
):
    from tests.local_acceptance.audit_run import audit_selected

    source, brz_vault, baseline, api_vault = paired_outputs
    candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    output = tmp_path / "pair-audit.json"
    result = audit_selected(
        candidate=candidate,
        output=output,
        brz_source=source,
        brz_vault=brz_vault,
        brz_result=brz_vault.parent / "brz-result.json",
        api_manifest=baseline.manifest_path,
        manifest_sha256=baseline.fingerprint,
        api_vault=api_vault,
        api_result=api_vault.parent / "api-result.json",
    )
    assert result["outcome"] == "qualified"
    assert set(result["audits"]) == {"brz", "api"}
    assert result["candidate"]["commit"] == candidate
    assert len(result["candidate"]["content_sha256"]) == 64
    assert result["pair_comparison"]["direct_classifications_equal"] is True
    assert len(result["pair_comparison"]["measured_payload_matches"]) == 3
    assert result["pair_comparison"]["brz_only_attachment_ids"] == [
        ABSENT_INTERMEDIATE_ICON
    ]
    assert result["m5_acceptance"] is False
    assert json.loads(output.read_bytes()) == result


def test_audit_entry_refuses_partial_selection(tmp_path):
    from tests.local_acceptance.audit_run import audit_selected

    candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    output = tmp_path / "incomplete-audit.json"
    result = audit_selected(
        candidate=candidate, output=output, brz_source=tmp_path / "only-source.brz"
    )
    assert result["outcome"] == "refused"
    assert not result["audits"] and result["m5_acceptance"] is False
    assert json.loads(output.read_bytes()) == result


def test_complete_api_audit_bounds_repeated_payload_reads(
    tmp_path, paired_outputs, monkeypatch
):
    _, _, baseline, vault = paired_outputs
    payload = baseline.data["payloads"][TAG_NOTE]["path"]
    target = (baseline.manifest_path.parent / payload).resolve()
    length = target.stat().st_size
    assert length > 0
    real_open = Path.open
    read_bytes = 0

    class MeasuredRead:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def read(self, *args):
            nonlocal read_bytes
            data = self.stream.read(*args)
            read_bytes += len(data)
            return data

        def readinto(self, buffer):
            nonlocal read_bytes
            count = self.stream.readinto(buffer)
            read_bytes += count
            return count

    def measured_open(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        return MeasuredRead(stream) if path.resolve() == target else stream

    monkeypatch.setattr(Path, "open", measured_open)
    summary = check_api_vault(baseline, vault, profile_version="4")
    assert summary == {"thoughts": 22, "relationships": 26, "payloads": 3}
    (tmp_path / "payload-read-volume.json").write_text(
        json.dumps({"payload": TAG_NOTE, "length": length, "bytes_read": read_bytes}),
        encoding="utf-8",
    )
    # Full entry/exit scans and necessary consumed reads are allowed. Repeating
    # a complete payload scan for every asset/note qualification is not.
    assert 0 < read_bytes <= 12 * length


def test_standalone_pair_comparison_rechecks_unused_bound_evidence(
    tmp_path, paired_outputs, monkeypatch
):
    from tests.local_acceptance.audit_run import compare_pair

    source, _, original, _ = paired_outputs
    evidence = tmp_path / "evidence"
    shutil.copytree(original.manifest_path.parent, evidence)
    baseline = load_baseline(evidence / "manifest.json", original.fingerprint)
    unused = evidence / baseline.data["http_responses"]
    initial = unused.read_bytes()
    archive_exit = ZipFile.__exit__

    def after_comparison_read(archive, *args):
        result = archive_exit(archive, *args)
        if str(archive.filename) == str(source):
            unused.write_bytes(initial + b" ")
        return result

    monkeypatch.setattr(ZipFile, "__exit__", after_comparison_read)
    with pytest.raises(AssertionError, match="baseline evidence changed"):
        compare_pair(source, baseline, "4")
    assert unused.read_bytes() != initial


@pytest.mark.parametrize("mutation", ["ids", "numeric-type"])
def test_caught_nested_declaration_failure_cannot_publish_a_success(
    paired_outputs, monkeypatch, mutation
):
    from tests.local_acceptance.api_scope import qualify_scope

    _, _, baseline, vault = paired_outputs
    target = (
        baseline.manifest_path.parent / baseline.data["payloads"][TAG_NOTE]["path"]
    ).resolve()
    real_read = Path.read_bytes
    attempted = False

    def observed_read(path):
        nonlocal attempted
        if path.resolve() == target and not attempted:
            attempted = True
            container, key = (
                (baseline.data["scope"], "thought_ids")
                if mutation == "ids"
                else (baseline.data["payloads"][TAG_NOTE], "status")
            )
            previous = container[key]
            container[key] = [] if mutation == "ids" else float(previous)
            try:
                with pytest.raises(AssertionError, match="changed in memory"):
                    qualify_scope(baseline, profile_version="4")
            finally:
                container[key] = previous
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", observed_read)
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="4")
    assert attempted
    monkeypatch.undo()
    assert check_api_vault(baseline, vault, profile_version="4")["thoughts"] == 22


@pytest.mark.parametrize("entry", ["verify", "scope"])
def test_manifest_association_preserves_numeric_declaration_types(
    paired_outputs, entry
):
    from tests.local_acceptance.api_scope import qualify_scope

    _, _, baseline, _ = paired_outputs
    outcome = baseline.data["payloads"][TAG_NOTE]
    previous = outcome["status"]
    assert type(previous) is int and previous == 200
    outcome["status"] = 200.0
    try:
        with pytest.raises(AssertionError, match="changed in memory"):
            if entry == "verify":
                baseline.verify()
            else:
                qualify_scope(baseline, profile_version="4")
    finally:
        outcome["status"] = previous
    baseline.verify()


def test_copied_execution_context_cannot_reuse_a_finished_audit(
    tmp_path, paired_outputs, monkeypatch
):
    from tests.local_acceptance.api_scope import qualify_scope

    _, _, original, vault = paired_outputs
    evidence = tmp_path / "evidence"
    shutil.copytree(original.manifest_path.parent, evidence)
    baseline = load_baseline(evidence / "manifest.json", original.fingerprint)
    target = (evidence / baseline.data["payloads"][TAG_NOTE]["path"]).resolve()
    real_read = Path.read_bytes
    captured = None

    def observed_read(path):
        nonlocal captured
        if path.resolve() == target and captured is None:
            captured = copy_context()
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", observed_read)
    assert check_api_vault(baseline, vault, profile_version="4")["thoughts"] == 22
    assert captured is not None
    unused = evidence / baseline.data["http_responses"]
    initial = unused.read_bytes()
    unused.write_bytes(initial + b" ")
    try:
        with pytest.raises(AssertionError, match="baseline evidence changed"):
            captured.run(qualify_scope, baseline, profile_version="4")
    finally:
        unused.write_bytes(initial)
    assert len(captured.run(qualify_scope, baseline, profile_version="4").graphs) == 22


@pytest.mark.parametrize("entry", ["scope", "vault"])
def test_consumed_evidence_is_pinned_even_when_restored_before_exit(
    tmp_path, paired_outputs, monkeypatch, entry
):
    from tests.local_acceptance.api_scope import qualify_scope

    _, _, original, vault = paired_outputs
    evidence = tmp_path / "evidence"
    shutil.copytree(original.manifest_path.parent, evidence)
    baseline = load_baseline(evidence / "manifest.json", original.fingerprint)
    target = (evidence / baseline.data["payloads"][TAG_NOTE]["path"]).resolve()
    initial = target.read_bytes()
    real_read = Path.read_bytes
    injected = False

    def transient_read(path):
        nonlocal injected
        if path.resolve() == target and not injected:
            injected = True
            target.write_bytes(initial + b" tampered")
            try:
                return real_read(path)
            finally:
                target.write_bytes(initial)
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", transient_read)
    with pytest.raises(AssertionError):
        if entry == "scope":
            qualify_scope(baseline, profile_version="4")
        else:
            check_api_vault(baseline, vault, profile_version="4")
    assert injected and target.read_bytes() == initial
    monkeypatch.undo()
    assert len(qualify_scope(baseline, profile_version="4").graphs) == 22


@pytest.mark.parametrize("execution", ["thread", "task"])
def test_concurrent_context_does_not_borrow_the_parent_audit_pass(
    tmp_path, paired_outputs, monkeypatch, execution
):
    from tests.local_acceptance.api_scope import qualify_scope

    _, _, original, vault = paired_outputs
    evidence = tmp_path / "evidence"
    shutil.copytree(original.manifest_path.parent, evidence)
    baseline = load_baseline(evidence / "manifest.json", original.fingerprint)
    target = (evidence / baseline.data["payloads"][TAG_NOTE]["path"]).resolve()
    unused = evidence / baseline.data["http_responses"]
    initial = unused.read_bytes()
    real_read = Path.read_bytes
    attempted = False

    def concurrent_check():
        with pytest.raises(AssertionError, match="baseline evidence changed"):
            qualify_scope(baseline, profile_version="4")

    async def task_check():
        concurrent_check()

    def observed_read(path):
        nonlocal attempted
        if path.resolve() == target and not attempted:
            attempted = True
            unused.write_bytes(initial + b" ")
            try:
                if execution == "thread":
                    copied = copy_context()
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        executor.submit(copied.run, concurrent_check).result()
                else:
                    asyncio.run(task_check())
            finally:
                unused.write_bytes(initial)
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", observed_read)
    assert check_api_vault(baseline, vault, profile_version="4")["thoughts"] == 22
    assert attempted and unused.read_bytes() == initial


def test_scoped_reads_recheck_containment_after_entry_verification(
    tmp_path, paired_outputs, monkeypatch
):
    from tests.local_acceptance.api_scope import qualify_scope

    _, _, original, _ = paired_outputs
    evidence = tmp_path / "evidence"
    shutil.copytree(original.manifest_path.parent, evidence)
    baseline = load_baseline(evidence / "manifest.json", original.fingerprint)
    target = (evidence / baseline.data["payloads"][TAG_NOTE]["path"]).resolve()
    outside = tmp_path / "outside.md"
    outside.write_bytes(target.read_bytes())
    probe = tmp_path / "capability-link"
    try:
        probe.symlink_to(outside)
    except OSError as error:
        pytest.skip("File symlink capability unavailable: " + str(error.errno))
    probe.unlink()
    real_open = Path.open
    backup = target.with_name(target.name + ".retained")
    injected = False

    class EntryRead:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            nonlocal injected
            result = self.stream.__exit__(*args)
            if not injected:
                target.rename(backup)
                target.symlink_to(outside)
                injected = True
            return result

    def observed_open(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        return EntryRead(stream) if path == target and not injected else stream

    monkeypatch.setattr(Path, "open", observed_open)
    try:
        with pytest.raises(AssertionError, match="unsafe audit path"):
            qualify_scope(baseline, profile_version="4")
        assert injected and target.is_symlink()
    finally:
        if target.is_symlink():
            target.unlink()
        if backup.exists():
            backup.rename(target)
    monkeypatch.undo()
    assert len(qualify_scope(baseline, profile_version="4").graphs) == 22


def test_scope_results_do_not_share_mutable_data_or_other_baselines(
    tmp_path, paired_outputs
):
    from tests.local_acceptance.api_scope import qualify_scope

    _, _, baseline, _ = paired_outputs
    first = qualify_scope(baseline, profile_version="4")
    original_keys = set(first.graphs)
    assert len(original_keys) == 22 and TAG_NOTE in first.declarations
    returned_graphs = first.graphs
    returned_graphs.clear()
    returned_declarations = first.declarations
    returned_declarations.clear()
    assert set(first.graphs) == original_keys and TAG_NOTE in first.declarations
    other = scope_baseline(tmp_path / "other-source")
    assert set(qualify_scope(other, profile_version="4").graphs) != original_keys
    assert set(qualify_scope(baseline, profile_version="4").graphs) == original_keys


def test_nested_scope_cache_does_not_authorize_an_unsupported_profile(
    paired_outputs, monkeypatch
):
    from tests.local_acceptance.api_scope import qualify_scope

    _, _, baseline, vault = paired_outputs
    record = json.loads((vault / "migration-record.json").read_bytes())
    note = next(row for row in record["item_targets"] if row["original_title"] == "T")
    target = (vault / note["relative_path"]).resolve()
    real_read = Path.read_bytes
    attempted = False

    def observed_read(path):
        nonlocal attempted
        if path.resolve() == target and not attempted:
            attempted = True
            with pytest.raises(AssertionError, match="unsupported API profile"):
                qualify_scope(baseline, profile_version="5")
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", observed_read)
    assert check_api_vault(baseline, vault, profile_version="4")["thoughts"] == 22
    assert attempted


@pytest.mark.parametrize(
    "subject_name",
    [
        None,
        "H0\nForged warning detail",
        "password=synthetic-secret",
        "https://private.example/secret",
        "Unrelated private identity",
    ],
)
def test_run_result_display_context_cannot_change_warning_facts(
    paired_outputs, subject_name
):
    _, _, _, vault = paired_outputs
    result = json.loads((vault.parent / "api-result.json").read_bytes())
    assert result["issues"][0]["subject"] == {"kind": "item", "name": "H0"}
    if subject_name is None:
        result["issues"][0]["message"] = "No depth limit applies."
    else:
        result["issues"][0]["subject"]["name"] = subject_name
    with pytest.raises(
        AssertionError, match="result warning (evidence|display context)"
    ):
        check_run_result(
            result,
            vault,
            {
                "notes": 21,
                "files": 55,
                "payloads": 3,
                "category_notes": 14,
                "warnings": 2,
            },
        )


@pytest.mark.parametrize("changed_fact", ["direct-tag", "nested-tag", "navigation"])
def test_pair_comparison_reports_changed_direct_facts(
    tmp_path, paired_outputs, changed_fact
):
    from tests.local_acceptance.audit_run import compare_pair

    source, _, baseline, _ = paired_outputs
    original = compare_pair(source, baseline, "4")
    with ZipFile(source) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    links = [json.loads(line) for line in parts["links.json"].splitlines()]
    if changed_fact == "navigation":
        removed = next(row for row in links if row["Relation"] == 3)
        links.remove(removed)
        field = "navigation_declarations"
        old = [
            "related",
            removed["ThoughtIdA"],
            removed["ThoughtIdB"],
            removed["Direction"],
        ]
        added = []
    else:
        edge = next(
            row
            for row in links
            if row["Meaning"] == (5 if changed_fact == "direct-tag" else 7)
        )
        old = [edge["ThoughtIdA"], edge["ThoughtIdB"]]
        if changed_fact == "direct-tag":
            edge["ThoughtIdA"] = IDS["U"]
        else:
            edge["ThoughtIdA"], edge["ThoughtIdB"] = (
                edge["ThoughtIdB"],
                edge["ThoughtIdA"],
            )
        added = [[edge["ThoughtIdA"], edge["ThoughtIdB"]]]
        field = "direct_tag_memberships"
    parts["links.json"] = b"\n".join(json.dumps(row).encode() for row in links)
    changed = tmp_path / "changed.brz"
    with ZipFile(changed, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    comparison = compare_pair(changed, baseline, "4")
    assert original[field + "_equal"] is True
    assert comparison[field + "_equal"] is False
    assert comparison["api_only_" + field] == [old]
    assert comparison["brz_only_" + field] == added
    assert comparison["direct_classifications_equal"] is True


@pytest.mark.parametrize(
    "changed_input", ["bound-payload", "run-result", "unused-evidence"]
)
def test_pair_audit_refuses_inputs_changed_during_comparison(
    tmp_path, paired_outputs, monkeypatch, changed_input
):
    from tests.local_acceptance import audit_run

    source, brz_vault, original, api_vault = paired_outputs
    evidence = tmp_path / "evidence"
    shutil.copytree(original.manifest_path.parent, evidence)
    baseline = load_baseline(evidence / "manifest.json", original.fingerprint)
    run_result = tmp_path / "api-result.json"
    shutil.copyfile(api_vault.parent / "api-result.json", run_result)
    if changed_input == "bound-payload":
        payload = next(
            row["path"]
            for row in baseline.data["payloads"].values()
            if row["status"] == 200
        )
        changed = evidence / payload
    elif changed_input == "run-result":
        changed = run_result
    else:
        changed = evidence / baseline.data["http_responses"]
    initial = changed.read_bytes()
    real_archive_exit = ZipFile.__exit__
    completed_source_reads = 0

    def source_archive_exit(archive, *args):
        nonlocal completed_source_reads
        result = real_archive_exit(archive, *args)
        if str(archive.filename) == str(source):
            completed_source_reads += 1
            if completed_source_reads == 2:
                # External filesystem fault after the pair's real archive read;
                # the source auditors and comparison execute without replacement.
                changed.write_bytes(initial + b" ")
        return result

    monkeypatch.setattr(ZipFile, "__exit__", source_archive_exit)
    candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    output = tmp_path / "changed-input-audit.json"
    result = audit_run.audit_selected(
        candidate=candidate,
        output=output,
        brz_source=source,
        brz_vault=brz_vault,
        api_manifest=baseline.manifest_path,
        manifest_sha256=baseline.fingerprint,
        api_vault=api_vault,
        api_result=run_result if changed_input == "run-result" else None,
    )
    assert changed.read_bytes() != initial
    assert result["outcome"] == "refused"
    assert result["failure"]["stage"] == "final-input-binding"
    assert result["m5_acceptance"] is False
    assert json.loads(output.read_bytes()) == result


@pytest.mark.parametrize(
    "adapter,damage",
    [
        ("brz", "direct-fact"),
        ("api", "transitive-member"),
        ("brz", "owned-icon"),
        ("api", "inherited-icon"),
        ("brz", "nested-tag"),
        ("api", "body"),
        ("brz", "original"),
        ("brz", "asset"),
        ("api", "video"),
        ("api", "unproved-player"),
        ("brz", "native-depth-formula"),
    ],
)
def test_independent_audits_reject_internally_consistent_output_corruptions(
    tmp_path, paired_outputs, adapter, damage
):
    source, brz_vault, baseline, api_vault = paired_outputs
    vault = tmp_path / "forged-vault"
    shutil.copytree(brz_vault if adapter == "brz" else api_vault, vault)
    record_path = vault / "migration-record.json"
    record = json.loads(record_path.read_bytes())
    targets = {row["item_key"]: row for row in record["item_targets"]}
    if damage == "direct-fact":
        # Remove a genuine direct jump throughout the output's own graph,
        # claimed original records, accounting, adaptations and visible notes.
        # Counts remain consistent, so only independent source truth can expose
        # the missing fact. The accepted source fingerprint remains pinned.
        removed = next(
            row for row in record["relationships"] if row["kind"] == "related"
        )
        record["relationships"].remove(removed)
        record["counts"]["source_relationships"] -= 1
        original = next(
            group
            for group in record["original_evidence"]
            if group["key"] == "links.json"
        )
        index = next(
            i
            for i, row in enumerate(original["records"])
            if row["Id"] == removed["key"]
        )
        original["records"].pop(index)
        record["source_accounting"]["entries"] = [
            row
            for row in record["source_accounting"]["entries"]
            if row["identity"] != f"links.json:{index}"
        ]
        record["adaptations"] = [
            row for row in record["adaptations"] if row["affected"] != removed["key"]
        ]
        replacements = {
            f"links.json:{i + 1}": f"links.json:{i}"
            for i in range(index, len(original["records"]))
        }

        def renumber(value):
            if isinstance(value, str):
                return replacements.get(value, value)
            if isinstance(value, list):
                return [renumber(item) for item in value]
            if isinstance(value, dict):
                return {key: renumber(item) for key, item in value.items()}
            return value

        record = renumber(record)
        for origin, destination in (
            (removed["item_a"], removed["item_b"]),
            (removed["item_b"], removed["item_a"]),
        ):
            path = vault / targets[origin]["relative_path"]
            line = (
                "- [["
                + targets[destination]["relative_path"]
                + "|"
                + targets[destination]["original_title"]
                + "]]\n"
            )
            body = path.read_text(encoding="utf-8").replace(line, "")
            if body.rstrip().endswith("## Related"):
                body = body[: body.rindex("## Related")].rstrip("\n") + "\n"
            path.write_text(body, encoding="utf-8")
        assert (
            len(record["classification_assignments"])
            == record["counts"]["classification_assignments"]
            == record["counts"]["typed_members"]
            == 17
        )
        assert len(record["relationships"]) == record["counts"]["source_relationships"]
        assert len(original["records"]) == record["counts"]["source_relationships"]
        assert (
            len(
                [
                    row
                    for row in record["source_accounting"]["entries"]
                    if row["identity"].startswith("links.json:")
                ]
            )
            == record["counts"]["source_relationships"]
        )
    elif damage == "transitive-member":
        row = record["classification_assignments"][-1]
        row["definition_key"] = record["classification_assignments"][0][
            "definition_key"
        ]
        row["definition_target"] = targets[row["definition_key"]]["relative_path"]
        edge = next(
            r for r in record["relationships"] if r["key"] == row["relationship_key"]
        )
        edge["item_a"], edge["target_a"] = (
            row["definition_key"],
            row["definition_target"],
        )
        assert (
            len(record["classification_assignments"])
            == record["counts"]["typed_members"]
            == 17
        )
    elif damage in {"owned-icon", "inherited-icon"}:
        row = next(
            t
            for t in record["item_targets"]
            if t["icon_snapshot"] and t["icon_snapshot"]["appearance_category_key"]
        )
        row["icon_snapshot"]["effective_icon_asset_id"] = None
        if damage == "owned-icon":
            row["declared_appearance"]["icon_asset_id"] = record["asset_targets"][0][
                "asset_id"
            ]
    elif damage == "nested-tag":
        (vault / "Tag memberships.md").write_text(
            "# Tag memberships\n\nNo source assignments.\n", encoding="utf-8"
        )
    elif damage == "body":
        row = next(t for t in record["item_targets"] if t["documents"])
        path = vault / row["relative_path"]
        path.write_bytes(
            path.read_bytes().replace(
                b"Independent tag T source body.", b"Internally changed tag body."
            )
        )
    elif damage in {"original", "asset"}:
        row = next(
            a
            for a in record["asset_targets"]
            if a["relative_path"]
            and (a["role"] == "note_original") == (damage == "original")
        )
        path = vault / row["relative_path"]
        changed = path.read_bytes() + b"forged"
        path.write_bytes(changed)
        row.update(
            actual_length=len(changed),
            actual_sha256=hashlib.sha256(changed).hexdigest(),
        )
    elif damage in {"video", "unproved-player"}:
        row = next(
            a for a in record["asset_targets"] if a["external_uri"] == VIDEO_URLS[1]
        )
        if damage == "video":
            row["external_uri"] = row["resource_link"] = (
                "https://www.youtube.com/watch?v=SYNTHVID001"
            )
        else:
            row["video_presentation"] = {
                "provider": "youtube",
                "embed_uri": "https://www.youtube.com/embed/SYNTHVID001?start=0",
                "start_seconds": 0,
            }
    else:
        path = vault / "Templates/Bases/Members.base"
        path.write_bytes(path.read_bytes().replace(b"formula.r8]", b"formula.r9]"))
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(AssertionError):
        if adapter == "brz":
            check_vault(source, vault)
        else:
            check_api_vault(baseline, vault, profile_version="4")
