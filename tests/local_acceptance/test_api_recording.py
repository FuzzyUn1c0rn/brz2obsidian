"""Public acquisition recording is source evidence, independent of its snapshot."""

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
from tests.support.local_api_payloads import NOTE, RAW_NOTE, PayloadApi


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


def test_capture_entry_audits_its_own_public_conversion(tmp_path, monkeypatch, capsys):
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
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
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
    ) == ("4", 8, "8")
    public = capsys.readouterr().out
    assert "KEY" not in public and BRAIN not in public and upstream not in public
    assert "parent M5 acceptance remains separate" in public


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
            with pytest.raises(AssertionError, match="private source metadata"):
                with recording:
                    recording.complete()
            assert not (recording.directory / "manifest.json").exists()
            assert json.loads((recording.directory / "recording.json").read_bytes())[
                "complete"
            ] is False
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
