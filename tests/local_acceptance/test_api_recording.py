"""Public acquisition recording is source evidence, independent of its snapshot."""

import copy
import gzip
import hashlib
import json
import shutil
import subprocess
import threading
import time
from socketserver import BaseRequestHandler, ThreadingTCPServer
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pytest

from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.local_acceptance.api_baseline import build_baseline
from tests.local_acceptance.api_checker import audit_baseline
from tests.local_acceptance.api_manifest import load_baseline
from tests.local_acceptance.api_recording import ApiRecording
from tests.local_acceptance.test_api_scope_v3 import scope_baseline
from tests.support.audit_sources import SCHEMA
from tests.support.local_api import ALONE, BRAIN, HOME, api_server, thought
from tests.support.local_api_graph import GraphApi, link
from tests.support.local_api_payloads import (
    FILE,
    NOTE,
    PNG,
    RAW_NOTE,
    FilePayloadApi,
    PayloadApi,
)


@pytest.fixture(scope="module")
def qualification(tmp_path_factory):
    return scope_baseline(tmp_path_factory.mktemp("qualification") / "baseline")


@pytest.fixture(scope="module")
def capture_setup(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("recording")
    api = PayloadApi()
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    api.overrides[f"/api/attachments/{BRAIN}/{NOTE}/file-content"] = (
        200,
        gzip.compress(RAW_NOTE, mtime=0),
        {"Content-Encoding": "gzip"},
    )
    with api_server(api) as (_, upstream):
        upstream = upstream.replace("127.0.0.1", "localhost")
        recording = ApiRecording(
            tmp_path / "attempt", upstream, brain_id=BRAIN, credential="KEY"
        )
        with recording:
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=recording.api_url),
                credentials=lambda: "KEY",
                profile_version="4",
            )
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                session.verify_consistency()
            recording.complete()
    return recording, upstream


@pytest.fixture(scope="module")
def captured(capture_setup):
    return capture_setup[0]


@pytest.fixture(scope="module")
def captured_origin(capture_setup):
    return capture_setup[1]


@pytest.fixture(scope="module")
def sealed(captured, qualification):
    return captured.seal(qualification=qualification)


def test_public_capture_retains_independent_raw_baseline(
    captured, qualification, sealed, captured_origin
):
    baseline = sealed

    assert baseline.data["schema"] == "brz2obsidian.api-acceptance/2"
    schema = baseline.json(baseline.data["qualification"][0])
    assert schema["info"]["title"] == "Synthetic current acquisition protocol"
    retained_control_manifest = captured.directory / baseline.data["qualification"][1]
    assert (
        load_baseline(retained_control_manifest, qualification.fingerprint).fingerprint
        == qualification.fingerprint
    )
    assert baseline.bytes(baseline.data["payloads"][NOTE]["path"]) == RAW_NOTE
    assert baseline.json(baseline.data["graphs"][HOME])["activeThought"]["name"] == (
        "Entry"
    )
    transcript = baseline.json(baseline.data["http_responses"])
    assert transcript["complete"] is True
    assert transcript["atomic"] is False
    assert len(baseline.data["statistics"]) == 2
    assert sum("/statistics" in r["target"] for r in transcript["occurrences"]) >= 2
    assert transcript["representation"] == "HTTP entity bytes after transfer decoding"
    assert transcript["upstream_api_url"] == captured_origin
    assert transcript["upstream_origin"] == captured_origin.removesuffix("/api")
    assert transcript["effective_upstream_endpoint"] == {
        "address": "127.0.0.1",
        "port": urlsplit(captured_origin).port,
    }
    for occurrence in transcript["occurrences"]:
        raw = baseline.bytes(occurrence["body"])
        assert hashlib.sha256(raw).hexdigest() == occurrence["sha256"]
        assert len(raw) == occurrence["length"]
    all_bytes = b"".join(
        p.read_bytes() for p in captured.directory.rglob("*") if p.is_file()
    )
    assert b"Authorization" not in all_bytes
    assert b"KEY" not in all_bytes
    assert (
        json.loads((captured.directory / "recording.json").read_bytes()) == transcript
    )
    baseline.verify()


def test_recorded_statistics_allow_distinct_generation_times(
    tmp_path, qualification, sealed
):
    # The reviewed live source returned stable counts and generated times ten
    # minutes apart. The older no-timestamp fixture remains independently valid.
    legacy = [sealed.json(path) for path in sealed.data["statistics"]]
    assert len(legacy) == 2 and all("dateGenerated" not in row for row in legacy)

    api = PayloadApi()
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    route = f"/api/brains/{BRAIN}/statistics"
    _, counters = api.response(route, {})
    timestamps = ("2026-11-12T19:49:09+01:00", "2026-11-12T19:59:09+01:00")
    observed_requests = []

    def statistics(query):
        assert not query
        timestamp = timestamps[0] if not observed_requests else timestamps[1]
        observed_requests.append(timestamp)
        return 200, {**counters, "dateGenerated": timestamp}

    api.overrides[route] = statistics
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "generated-statistics",
            upstream,
            brain_id=BRAIN,
            credential="KEY",
        )
        with recording:
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=recording.api_url),
                credentials=lambda: "KEY",
                profile_version="5",
            )
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                session.verify_consistency()
            recording.complete()
    assert len(observed_requests) >= 2
    assert observed_requests[0] == timestamps[0]
    assert all(value == timestamps[1] for value in observed_requests[1:])
    baseline = recording.seal(qualification=qualification)
    audit_baseline(baseline, profile_version="5")
    observed = [baseline.json(path) for path in baseline.data["statistics"]]
    assert [row["dateGenerated"] for row in observed] == list(timestamps)
    assert [row["brainId"] for row in observed] == [BRAIN, BRAIN]
    assert [row["thoughts"] for row in observed] == [2, 2]
    ledger = baseline.json(baseline.data["http_responses"])
    rows = [row for row in ledger["occurrences"] if row["target"] == route]
    assert len(rows) == len(observed_requests)
    assert [baseline.json(row["decoded_body"])["dateGenerated"] for row in rows] == (
        observed_requests
    )
    baseline.verify()


@pytest.mark.parametrize(
    "failure",
    [
        "counter",
        "other_field",
        "field_type",
        "missing_time",
        "time_type",
        "foreign_brain",
        "query",
        "wrong_route",
        "status",
        "duplicate_key",
        "tampered_body",
    ],
)
def test_recorded_statistics_refuse_other_disagreement(
    tmp_path, captured, qualification, failure
):
    directory = tmp_path / "unqualified-statistics"
    directory.mkdir()
    for source in captured.directory.glob("response-*.bin"):
        shutil.copyfile(source, directory / source.name)
    ledger = json.loads((captured.directory / "recording.json").read_bytes())
    statistics = [
        row
        for row in ledger["occurrences"]
        if row["target"] == f"/api/brains/{BRAIN}/statistics"
    ]
    assert len(statistics) >= 2
    for index, row in enumerate(statistics):
        assert row["content_encoding"] == "identity" and row["status"] == 200
        if failure == "wrong_route":
            row["target"] = "/api/brains/other/statistics"
        value = json.loads((directory / row["decoded_body"]).read_bytes())
        value["dateGenerated"] = (
            "2026-11-12T19:49:09+01:00" if index == 0 else "2026-11-12T19:59:09+01:00"
        )
        value["other"] = {"count": 1}
        if index == len(statistics) - 1:
            if failure == "counter":
                value["thoughts"] += 1
            elif failure == "other_field":
                value["other"]["count"] = 2
            elif failure == "field_type":
                value["other"]["count"] = True
            elif failure == "missing_time":
                del value["dateGenerated"]
            elif failure == "time_type":
                value["dateGenerated"] = 1
            elif failure == "foreign_brain":
                value["brainId"] = "99999999-9999-4999-8999-999999999999"
            elif failure == "query":
                row["target"] += "?view=other"
            elif failure == "status":
                row["status"] = 400
        raw = json.dumps(value).encode()
        if index == len(statistics) - 1 and failure == "duplicate_key":
            raw = raw.replace(b'{"brainId":', b'{"brainId":"duplicate","brainId":', 1)
        for field, length, digest in (
            ("body", "length", "sha256"),
            ("decoded_body", "decoded_length", "decoded_sha256"),
        ):
            (directory / row[field]).write_bytes(raw)
            row[length] = len(raw)
            row[digest] = hashlib.sha256(raw).hexdigest()
        if index == len(statistics) - 1 and failure == "tampered_body":
            (directory / row["decoded_body"]).write_bytes(raw + b" ")
    raw = json.dumps(ledger).encode()
    (directory / "recording.json").write_bytes(raw)
    expected = {
        "duplicate_key": "duplicate evidence JSON keys",
        "tampered_body": "changed HTTP response evidence",
    }.get(failure, "contradictory repeated source observation")
    with pytest.raises(AssertionError, match=expected):
        build_baseline(
            directory, hashlib.sha256(raw).hexdigest(), qualification=qualification
        )
    assert not (directory / "manifest.json").exists()


def test_recorded_graph_and_owner_allow_attachment_reordering(tmp_path, qualification):
    # The live API returned the same declarations and positions in a different
    # graph/list order; preserve both independent wire observations.
    api = FilePayloadApi()
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    api.attachments[FILE]["position"] = 1
    graph_path = f"/api/thoughts/{BRAIN}/{HOME}/graph"
    status, graph = api.response(graph_path, {})
    assert status == 200
    assert [row["id"] for row in graph["attachments"]] == [NOTE, FILE]
    graph["attachments"] = list(reversed(graph["attachments"]))
    api.overrides[graph_path] = (200, graph)
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "reordered-attachments",
            upstream,
            brain_id=BRAIN,
            credential="KEY",
        )
        with recording:
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=recording.api_url),
                credentials=lambda: "KEY",
                profile_version="5",
            )
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                session.verify_consistency()
            recording.complete()
    baseline = recording.seal(qualification=qualification)
    audit_baseline(baseline, profile_version="5")
    graph_rows = baseline.json(baseline.data["graphs"][HOME])["attachments"]
    owned = baseline.json(baseline.data["attachment_inventories"][HOME])
    assert [(row["id"], row["position"]) for row in graph_rows] == [
        (FILE, 1),
        (NOTE, 0),
    ]
    assert [(row["id"], row["position"]) for row in owned] == [(NOTE, 0), (FILE, 1)]
    assert baseline.bytes(baseline.data["payloads"][FILE]["path"]) == PNG
    assert baseline.bytes(baseline.data["payloads"][NOTE]["path"]) == RAW_NOTE
    baseline.verify()


@pytest.mark.parametrize(
    "damage",
    [
        "duplicate",
        "missing",
        "extra",
        "position",
        "field",
        "field_type",
        "foreign_owner",
        "foreign_brain",
        "source_type",
        "malformed_item",
        "malformed_array",
        "malformed_id",
    ],
)
def test_recorded_graph_attachment_disagreement_never_seals(
    tmp_path, captured, qualification, damage
):
    directory = tmp_path / "unqualified-graph-attachments"
    directory.mkdir()
    for source in captured.directory.glob("response-*.bin"):
        shutil.copyfile(source, directory / source.name)
    ledger = json.loads((captured.directory / "recording.json").read_bytes())
    route = f"/api/thoughts/{BRAIN}/{HOME}/graph?includeSiblings=true"
    row = next(item for item in ledger["occurrences"] if item["target"] == route)
    assert row["status"] == 200 and row["content_encoding"] == "identity"
    graph = json.loads((directory / row["decoded_body"]).read_bytes())
    attachments = graph["attachments"]
    assert len(attachments) == 1 and attachments[0]["id"] == NOTE
    if damage == "duplicate":
        attachments.append(copy.deepcopy(attachments[0]))
    elif damage == "missing":
        attachments.clear()
    elif damage == "extra":
        extra = copy.deepcopy(attachments[0])
        extra["id"] = "99999999-9999-4999-8999-999999999999"
        attachments.append(extra)
    elif damage == "position":
        attachments[0]["position"] = 7
    elif damage == "field":
        attachments[0]["name"] = "different source name"
    elif damage == "field_type":
        attachments[0]["position"] = False
    elif damage == "foreign_owner":
        attachments[0]["sourceId"] = ALONE
    elif damage == "foreign_brain":
        attachments[0]["brainId"] = "99999999-9999-4999-8999-999999999999"
    elif damage == "source_type":
        attachments[0]["sourceType"] = 3
    elif damage == "malformed_array":
        graph["attachments"] = {"id": NOTE}
    elif damage == "malformed_id":
        attachments[0]["id"] = "not-a-uuid"
    else:
        attachments[0] = "not an attachment object"
    raw = json.dumps(graph).encode()
    for field, length, digest in (
        ("body", "length", "sha256"),
        ("decoded_body", "decoded_length", "decoded_sha256"),
    ):
        (directory / row[field]).write_bytes(raw)
        row[length] = len(raw)
        row[digest] = hashlib.sha256(raw).hexdigest()
    raw = json.dumps(ledger).encode()
    (directory / "recording.json").write_bytes(raw)
    with pytest.raises(AssertionError, match="same-counter attachment disagreement"):
        build_baseline(
            directory, hashlib.sha256(raw).hexdigest(), qualification=qualification
        )
    assert not (directory / "manifest.json").exists()


def test_independent_audit_rechecks_recorded_required_coverage(
    tmp_path, captured, sealed
):
    directory = tmp_path / "forged-complete-baseline"
    shutil.copytree(captured.directory, directory)
    ledger_path = directory / "recording.json"
    ledger = json.loads(ledger_path.read_bytes())
    ledger["occurrences"] = [
        row
        for row in ledger["occurrences"]
        if row["target"] != f"/api/attachments/{BRAIN}/{NOTE}/metadata"
    ]
    for ordinal, row in enumerate(ledger["occurrences"], 1):
        row["ordinal"] = ordinal
    raw = json.dumps(ledger).encode()
    ledger_path.write_bytes(raw)
    manifest = json.loads((directory / "manifest.json").read_bytes())
    manifest["files"]["recording.json"] = {
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    raw = json.dumps(manifest).encode()
    path = directory / "manifest.json"
    path.write_bytes(raw)
    forged = load_baseline(path, hashlib.sha256(raw).hexdigest())
    with pytest.raises(AssertionError, match="missing required acquisition coverage"):
        audit_baseline(forged, profile_version="4")


@pytest.mark.parametrize("brain_parameter", ["brainId", "id"])
def test_capture_entry_audits_its_own_public_conversion(
    tmp_path, monkeypatch, capsys, brain_parameter
):
    from tests.local_acceptance.audit_run import main

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", "KEY")
    controls = tmp_path / "prepared-controls"
    assert main(["prepare-controls", "--directory", str(controls)]) == 0
    manifest = controls / "manifest.json"
    qualification = load_baseline(
        manifest, hashlib.sha256(manifest.read_bytes()).hexdigest()
    )
    assert (
        qualification.fingerprint
        == "3535182dccc9a298c27d163afc12a006b8aa6aeac553168981374c851ba4ed81"
    )
    candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    api = PayloadApi()
    schema = copy.deepcopy(SCHEMA)
    brain_detail = schema["paths"].pop("/api/brains/{brainId}")
    schema["paths"]["/api/brains/{" + brain_parameter + "}"] = brain_detail
    api.overrides["/api/v1/docs.json"] = (200, schema)
    attempt, vault = tmp_path / "command-attempt", tmp_path / "command-vault"
    with api_server(api) as (_, upstream):
        outcome = main(
            [
                "capture-api",
                "--api-url",
                upstream,
                "--brain",
                BRAIN,
                "--candidate",
                candidate,
                "--qualification",
                str(qualification.manifest_path),
                "--qualification-sha256",
                qualification.fingerprint,
                "--attempt",
                str(attempt),
                "--vault",
                str(vault),
            ]
        )
    assert outcome == 0
    report = json.loads((attempt / "audit.json").read_bytes())
    assert report["outcome"] == "qualified" and report["m5_acceptance"] is False
    assert report["api_acquisition"]["upstream_api_url"] == upstream
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert (
        record["profile_version"],
        record["schema_version"],
        record["renderer_version"],
    ) == ("5", 9, "9")
    public = capsys.readouterr().out
    assert "KEY" not in public and BRAIN not in public and upstream not in public
    assert "parent M5 acceptance remains separate" in public


def test_capture_profile_mismatch_preserves_returned_result_and_recording(
    tmp_path, monkeypatch, capsys
):
    from types import SimpleNamespace

    from brz2obsidian.application import wiring
    from tests.local_acceptance.audit_run import main

    monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", "KEY")
    controls = tmp_path / "controls"
    assert main(["prepare-controls", "--directory", str(controls)]) == 0
    manifest = controls / "manifest.json"
    candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    actual_factory = wiring.local_api_workflow
    returned = []

    def mismatched_factory(*args, **kwargs):
        workflow = actual_factory(*args, **kwargs)

        def convert(*convert_args, **convert_kwargs):
            actual = workflow.convert(*convert_args, **convert_kwargs)
            assert workflow.binding.source.profile_version == "5"
            assert (
                workflow.binding.policy.profile_version == actual.profile_version == "5"
            )
            assert actual.outcome in {"clean", "warnings"} and actual.receipt.verified
            declared = actual.model_copy(update={"profile_version": "4"})
            returned.append(declared.model_dump(mode="json", by_alias=True))
            return declared

        return SimpleNamespace(binding=workflow.binding, convert=convert)

    monkeypatch.setattr(wiring, "local_api_workflow", mismatched_factory)
    api = PayloadApi()
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    attempt, vault = tmp_path / "mismatched-attempt", tmp_path / "mismatched-vault"
    with api_server(api) as (_, upstream):
        code = main(
            [
                "capture-api",
                "--api-url",
                upstream,
                "--brain",
                BRAIN,
                "--candidate",
                candidate,
                "--qualification",
                str(manifest),
                "--qualification-sha256",
                hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "--attempt",
                str(attempt),
                "--vault",
                str(vault),
            ]
        )
    assert code == 2 and len(returned) == 1
    report = json.loads((attempt / "audit.json").read_bytes())
    assert report["outcome"] == "refused" and not report["m5_acceptance"]
    assert report["failure"]["stage"] == "api-capture" and not report["audits"]
    assert json.loads((attempt / "result.json").read_bytes()) == returned[0]
    assert returned[0]["profile_version"] == "4"
    recording = json.loads((attempt / "http/recording.json").read_bytes())
    assert not recording["complete"] and recording["occurrences"]
    assert "Acquisition did not complete" in recording["failures"]
    assert all(
        (attempt / "http" / row["body"]).is_file() for row in recording["occurrences"]
    )
    assert not (attempt / "http/manifest.json").exists()
    assert (
        json.loads((vault / "migration-record.json").read_bytes())["profile_version"]
        == "5"
    )
    public = capsys.readouterr().out
    assert "KEY" not in public and BRAIN not in public and upstream not in public


def test_audit_cli_binds_current5_and_preserves_explicit_legacy3(tmp_path, capsys):
    from tests.local_acceptance.audit_run import main
    from tests.local_acceptance.test_api_icon_audit import handcrafted_icon_vault
    from tests.local_acceptance.test_api_scope_v3 import (
        complete_raster_support,
        raster_scope_case,
    )

    candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    baseline, vault = handcrafted_icon_vault(tmp_path / "current", output_version=8)
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert (record["profile_id"], record["profile_version"]) == (
        "thebrain-local-api-reviewed",
        "5",
    )

    def audit_args(baseline, vault, output, output_version=8):
        return [
            "audit",
            "--candidate",
            candidate,
            "--api-manifest",
            str(baseline.manifest_path),
            "--manifest-sha256",
            baseline.fingerprint,
            "--api-vault",
            str(vault),
            "--output",
            str(output),
            "--output-version",
            str(output_version),
        ]

    explicit = tmp_path / "explicit5.json"
    assert main(audit_args(baseline, vault, explicit) + ["--profile-version", "5"]) == 0
    report = json.loads(explicit.read_bytes())
    assert report["outcome"] == "qualified" and not report["m5_acceptance"]
    assert report["audits"]["api"]["outcome"] == "qualified"
    default = tmp_path / "default5.json"
    assert main(audit_args(baseline, vault, default)) == 0
    assert json.loads(default.read_bytes())["outcome"] == "qualified"
    mismatch = tmp_path / "wrong4.json"
    assert main(audit_args(baseline, vault, mismatch) + ["--profile-version", "4"]) == 2
    refused = json.loads(mismatch.read_bytes())
    assert refused["outcome"] == "refused" and refused["failure"]["stage"] == (
        "api-source-audit"
    )
    assert not refused["audits"] and not refused["m5_acceptance"]

    # Tamper only a disposable output copy; the independently pinned source is
    # still a profile5 BMP, so the checker must reach its profile binding guard.
    from tests.local_acceptance.api_checker import check_api_vault

    forged = tmp_path / "forged-profile"
    shutil.copytree(vault, forged)
    forged_record_path = forged / "migration-record.json"
    forged_record = json.loads(forged_record_path.read_bytes())
    forged_record["profile_version"] = "4"
    forged_record_path.write_text(json.dumps(forged_record), encoding="utf-8")
    with pytest.raises(AssertionError, match="API-bound profile"):
        check_api_vault(baseline, forged, profile_version="5")
    forged_report = tmp_path / "forged-profile.json"
    assert (
        main(audit_args(baseline, forged, forged_report) + ["--profile-version", "5"])
        == 2
    )
    assert json.loads(forged_report.read_bytes())["outcome"] == "refused"
    assert json.loads((vault / "migration-record.json").read_bytes()) == record

    with pytest.raises(SystemExit) as invalid:
        main(
            audit_args(baseline, vault, tmp_path / "unsupported.json")
            + ["--profile-version", "6"]
        )
    assert invalid.value.code == 2 and not (tmp_path / "unsupported.json").exists()

    legacy, old_vault = raster_scope_case(tmp_path / "legacy", profile="3")
    complete_raster_support(legacy, old_vault)
    old_record = json.loads((old_vault / "migration-record.json").read_bytes())
    assert old_record["profile_version"] == "3" and old_record["schema_version"] == 7
    old_report = tmp_path / "legacy3.json"
    assert (
        main(
            audit_args(legacy, old_vault, old_report, output_version=7)
            + ["--profile-version", "3"]
        )
        == 0
    )
    assert json.loads(old_report.read_bytes())["outcome"] == "qualified"
    assert "parent M5 acceptance remains separate" in capsys.readouterr().out


def schema_recording(directory, captured, schema):
    """Rebind only schema bytes in an independently complete raw recording."""
    directory.mkdir()
    for source in captured.directory.glob("response-*.bin"):
        shutil.copyfile(source, directory / source.name)
    ledger = json.loads((captured.directory / "recording.json").read_bytes())
    raw = json.dumps(schema).encode()
    for row in ledger["occurrences"]:
        if row["target"] != "/api/v1/docs.json":
            continue
        assert row["content_encoding"] == "identity"
        for field, length, digest in (
            ("body", "length", "sha256"),
            ("decoded_body", "decoded_length", "decoded_sha256"),
        ):
            (directory / row[field]).write_bytes(raw)
            row[length] = len(raw)
            row[digest] = hashlib.sha256(raw).hexdigest()
    raw = json.dumps(ledger).encode()
    (directory / "recording.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_recorded_schema_all_parameter_aliases_preserve_concrete_source(
    tmp_path, captured, qualification, sealed
):
    schema = copy.deepcopy(SCHEMA)
    schema["paths"] = {
        "/api/brains": {"get": {}},
        "/api/brains/{collection}": {"get": {}, "delete": {}},
        "/api/brains/{collection}/statistics": {"get": {}},
        "/api/search/{collection}": {"get": {}},
        "/api/thoughts/{collection}/types": {"get": {}},
        "/api/thoughts/{collection}/tags": {"get": {}},
        "/api/thoughts/{collection}/{item}": {"get": {}},
        "/api/thoughts/{collection}/{item}/graph": {"get": {}},
        "/api/thoughts/{collection}/{item}/attachments": {"get": {}},
        "/api/links/{collection}/{edge}": {"get": {}},
        "/api/links/{collection}/{edge}/attachments": {"get": {}},
        "/api/attachments/{collection}/{resource}/metadata": {"get": {}},
        "/api/attachments/{collection}/{resource}/file-content": {"get": {}},
        "/api/notes/{collection}/{item}": {"get": {}},
        "/api/search/public": {"get": {}},
        "/api/notes/{collection}/{item}/update": {"post": {}},
        "/": {"get": {}},
        "/api/unrelated/": {"get": {}},
    }
    directory = tmp_path / "aliased-complete-source"
    pin = schema_recording(directory, captured, schema)
    baseline = build_baseline(directory, pin, qualification=qualification)
    audit_baseline(baseline, profile_version="4")
    assert baseline.json(baseline.data["qualification"][0]) == schema
    for key in (
        "brain",
        "scope",
        "graphs",
        "payloads",
        "attachment_metadata",
        "relationship_metadata",
        "statistics",
        "scope_inputs",
    ):
        assert baseline.data[key] == sealed.data[key]
    assert baseline.bytes(baseline.data["payloads"][NOTE]["path"]) == RAW_NOTE
    original = json.loads((captured.directory / "recording.json").read_bytes())
    rebound = json.loads((directory / "recording.json").read_bytes())
    assert rebound["brain_id"] == original["brain_id"] == BRAIN
    assert [row["target"] for row in rebound["occurrences"]] == [
        row["target"] for row in original["occurrences"]
    ]
    assert [
        row for row in rebound["occurrences"] if row["target"] != "/api/v1/docs.json"
    ] == [
        row for row in original["occurrences"] if row["target"] != "/api/v1/docs.json"
    ]


@pytest.mark.parametrize(
    ("replacement", "operation", "duplicate"),
    [
        (None, {"get": {}}, False),
        ("/api/Brains/{id}", {"get": {}}, False),
        ("/v2/brains/{id}", {"get": {}}, False),
        ("/api/brains/current", {"get": {}}, False),
        ("/api/brains/{id}/{extra}", {"get": {}}, False),
        ("/api/{id}/brains", {"get": {}}, False),
        ("/api/brains/{id}", {"post": {}}, False),
        ("/api/brains/{id}", {"GET": {}}, False),
        ("/api/brains/{id}", {"get": None}, False),
        ("/api/brains/{id}", {"get": {}}, True),
        ("/api/brains/{id}", {"post": {}}, True),
        ("/api/brains/{}", {"get": {}}, False),
        ("/api/brains/id{suffix}", {"get": {}}, False),
        ("/api/brains/{{id}}", {"get": {}}, False),
        ("/api/brains/{id}/", {"get": {}}, False),
        ("/api/brains/{id\x00}", {"get": {}}, False),
        ("/api/brains/{id\x7f}", {"get": {}}, False),
    ],
)
def test_recorded_schema_route_conflicts_never_seal(
    tmp_path, captured, qualification, replacement, operation, duplicate
):
    schema = copy.deepcopy(SCHEMA)
    if not duplicate:
        del schema["paths"]["/api/brains/{brainId}"]
    if replacement is not None:
        schema["paths"][replacement] = operation
    directory = tmp_path / "unqualified-schema"
    pin = schema_recording(directory, captured, schema)
    with pytest.raises(AssertionError, match="recorded schema"):
        build_baseline(directory, pin, qualification=qualification)
    assert not (directory / "manifest.json").exists()


def test_link_only_discovery_closes_disconnected_endpoints(tmp_path, qualification):
    api = GraphApi()
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    endpoint = "aaaaaaaa-1111-4111-8111-111111111111"
    edge_id = "bbbbbbbb-1111-4111-8111-111111111111"
    api.thoughts[endpoint] = thought(endpoint, "Disconnected endpoint")
    api.links = {edge_id: link(edge_id, ALONE, endpoint)}
    api.search = [
        {
            "brainId": BRAIN,
            "isFromOtherBrain": False,
            "sourceThought": None,
            "sourceLink": {"id": edge_id, "brainId": BRAIN},
        }
    ]
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "link-only", upstream, brain_id=BRAIN, credential="KEY"
        )
        with recording:
            recording.complete()
        baseline = recording.seal(qualification=qualification)
    assert set(baseline.data["graphs"]) == {HOME, ALONE, endpoint}
    assert baseline.data["scope"]["relationship_ids"] == [edge_id]
    assert edge_id in baseline.data["relationship_metadata"]


@pytest.mark.parametrize("disposition", ["forgotten", "private"])
def test_capture_scopes_excluded_metadata_before_content(
    tmp_path, qualification, disposition
):
    api = GraphApi()
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    api.thoughts[ALONE][
        "forgottenDateTime" if disposition == "forgotten" else "acType"
    ] = "2026-10-15T10:00:00" if disposition == "forgotten" else 1
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / disposition, upstream, brain_id=BRAIN, credential="KEY"
        )
        if disposition == "private":
            with (
                pytest.raises(AssertionError, match="private source metadata"),
                recording,
            ):
                recording.complete()
            assert not (recording.directory / "manifest.json").exists()
            assert (
                json.loads((recording.directory / "recording.json").read_bytes())[
                    "complete"
                ]
                is False
            )
        else:
            with recording:
                recording.complete()
            baseline = recording.seal(qualification=qualification)
            assert ALONE in baseline.data["scope_inputs"]["excluded_thoughts"]
            assert ALONE not in baseline.data["graphs"]
            audit_baseline(baseline, profile_version="4")
    paths = [row[0] for row in api.requests]
    assert f"/api/thoughts/{BRAIN}/{ALONE}" in paths
    assert f"/api/thoughts/{BRAIN}/{ALONE}/graph" not in paths
    assert f"/api/thoughts/{BRAIN}/{ALONE}/attachments" not in paths
    assert f"/api/notes/{BRAIN}/{ALONE}" not in paths


def test_recording_waits_for_response_writers_before_finalizing(tmp_path):
    started = threading.Event()
    api = PayloadApi()
    path = f"/api/brains/{BRAIN}"
    body = b"safe slow body" * 20

    def response(query):
        started.set()
        return 200, body

    api.overrides[path] = response
    api.response_chunks[path] = (10, 0.01)
    received = []
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "pending-writer",
            upstream,
            brain_id=BRAIN,
            credential="KEY",
            timeout=3,
        )
        with recording:

            def read():
                request = Request(
                    recording.api_url.removesuffix("/api") + path,
                    headers={"Authorization": "Bearer KEY"},
                )
                with urlopen(request, timeout=3) as result:
                    received.append(result.read())

            thread = threading.Thread(target=read)
            thread.start()
            assert started.wait(2)
        thread.join(timeout=3)
        assert received == [body]
        ledger = json.loads((recording.directory / "recording.json").read_bytes())
        assert len(ledger["occurrences"]) == 1
        assert ledger["occurrences"][0]["sha256"] == hashlib.sha256(body).hexdigest()


def test_total_deadline_bounds_dripped_headers_and_close(tmp_path):
    class Drip(BaseRequestHandler):
        def handle(self):
            self.request.recv(65536)
            try:
                self.request.sendall(b"HTTP/1.0 200 OK\r\nX-Slow: ")
                for _ in range(24):
                    self.request.sendall(b"x")
                    time.sleep(0.02)
                self.request.sendall(b"\r\nContent-Length: 2\r\n\r\n{}")
            except OSError:
                pass

    with ThreadingTCPServer(("127.0.0.1", 0), Drip) as server:
        listener = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.01}
        )
        listener.start()
        try:
            recording = ApiRecording(
                tmp_path / "header-deadline",
                f"http://127.0.0.1:{server.server_address[1]}/api",
                brain_id=BRAIN,
                credential="KEY",
                timeout=0.08,
            )
            started = time.monotonic()
            with recording:
                request = Request(
                    recording.api_url + "/brains/" + BRAIN,
                    headers={"Authorization": "Bearer KEY"},
                )
                with pytest.raises(HTTPError):
                    urlopen(request, timeout=2)
            assert time.monotonic() - started < 0.35
            ledger = json.loads((recording.directory / "recording.json").read_bytes())
            assert ledger["complete"] is False and not ledger["occurrences"]
        finally:
            server.shutdown()
            listener.join(timeout=2)


@pytest.mark.parametrize("limit", ["request", "body", "aggregate"])
def test_recording_bounds_requests_bodies_and_retained_bytes(tmp_path, limit):
    api = PayloadApi()
    path = f"/api/brains/{BRAIN}"
    body = b"safe" if limit == "request" else b"x" * 3500
    api.overrides[path] = (200, body)
    bounds = (
        {"max_requests": 1}
        if limit == "request"
        else {"max_body_bytes": 8}
        if limit == "body"
        else {"max_total_bytes": 8192}
    )
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / limit, upstream, brain_id=BRAIN, credential="KEY", **bounds
        )
        with recording:
            request = Request(
                recording.api_url + "/brains/" + BRAIN,
                headers={"Authorization": "Bearer KEY"},
            )
            if limit != "body":
                with urlopen(request, timeout=3) as response:
                    assert response.read() == body
            with pytest.raises(HTTPError):
                urlopen(request, timeout=3)
        ledger = json.loads((recording.directory / "recording.json").read_bytes())
        assert ledger["complete"] is False
        assert len(ledger["occurrences"]) == (0 if limit == "body" else 1)
        if limit == "aggregate":
            assert (
                sum(path.stat().st_size for path in recording.directory.iterdir())
                <= 8192
            )


@pytest.mark.parametrize(
    "damage", ["omitted-response", "same-counter-metadata", "decoded-transport"]
)
def test_recording_rejects_incomplete_or_conflicting_source_evidence(
    tmp_path, captured, qualification, damage
):
    directory = tmp_path / damage
    directory.mkdir()
    for source in captured.directory.glob("response-*.bin"):
        shutil.copyfile(source, directory / source.name)
    ledger = json.loads((captured.directory / "recording.json").read_bytes())
    target = f"/api/attachments/{BRAIN}/{NOTE}/metadata"
    occurrence = next(r for r in ledger["occurrences"] if r["target"] == target)
    if damage == "omitted-response":
        ledger["occurrences"].remove(occurrence)
        for ordinal, row in enumerate(ledger["occurrences"], 1):
            row["ordinal"] = ordinal
    elif damage == "same-counter-metadata":
        body = directory / occurrence["body"]
        value = json.loads(body.read_bytes())
        value["name"] = "Disagreement without any count change"
        raw = json.dumps(value).encode()
        body.write_bytes(raw)
        occurrence.update(
            length=len(raw),
            decoded_length=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            decoded_sha256=hashlib.sha256(raw).hexdigest(),
        )
    else:
        occurrence = next(
            r for r in ledger["occurrences"] if r["content_encoding"] == "gzip"
        )
        raw = RAW_NOTE.replace(b"Authored", b"Tampered")
        (directory / occurrence["decoded_body"]).write_bytes(raw)
        occurrence.update(
            decoded_length=len(raw), decoded_sha256=hashlib.sha256(raw).hexdigest()
        )
    raw = json.dumps(ledger).encode()
    (directory / "recording.json").write_bytes(raw)
    with pytest.raises(AssertionError, match="missing required|disagreement|transport"):
        build_baseline(
            directory, hashlib.sha256(raw).hexdigest(), qualification=qualification
        )
    assert not (directory / "manifest.json").exists()


@pytest.mark.parametrize(
    "failure",
    [
        "credential",
        "credential-json",
        "credential-gzip",
        "redirect",
        "truncated",
        "foreign",
    ],
)
def test_recording_privacy_transport_failures_never_seal(
    tmp_path, qualification, failure
):
    api = PayloadApi()
    path = f"/api/brains/{BRAIN}"
    if failure == "credential":
        api.overrides[path] = (200, b"Reflected KEY in source error")
    elif failure == "credential-json":
        api.overrides[path] = (200, b'{"message":"K\\u0045Y"}')
    elif failure == "credential-gzip":
        api.overrides[path] = (
            200,
            gzip.compress(b"Reflected KEY", mtime=0),
            {"Content-Encoding": "gzip"},
        )
    elif failure == "redirect":
        api.overrides[path] = (302, b"", {"Location": "http://127.0.0.1:9/forbidden"})
    elif failure == "truncated":
        api.overrides[path] = (200, b"partial", {"Content-Length": "90"})
    else:
        path = "/api/brains/99999999-9999-4999-8999-999999999999"
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "failed-attempt", upstream, brain_id=BRAIN, credential="KEY"
        )
        with recording:
            request = Request(
                recording.api_url.removesuffix("/api") + path,
                headers={"Authorization": "Bearer KEY"},
            )
            with pytest.raises(HTTPError):
                urlopen(request, timeout=3)
        ledger = json.loads((recording.directory / "recording.json").read_bytes())
        assert ledger["complete"] is False
        assert ledger["failures"]
        with pytest.raises(AssertionError, match="incomplete recording"):
            recording.seal(qualification=qualification)
    retained = b"".join(
        p.read_bytes() for p in recording.directory.rglob("*") if p.is_file()
    )
    assert b"KEY" not in retained
    assert not (recording.directory / "manifest.json").exists()
    if failure == "foreign":
        assert not api.requests
