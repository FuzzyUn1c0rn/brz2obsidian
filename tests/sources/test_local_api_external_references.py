"""External references through public HTTP acquisition, capture and output."""

import json

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import ALONE, BRAIN, KEY, api_server
from tests.support.local_api_payloads import PayloadApi, attachment

FILE = "b2222222-2222-4222-8222-222222222222"
DIRECTORY = "b8888888-8888-4888-8888-888888888888"
FILE_PATH = "C:\\Source\\caf\u00e9 %#.pdf"
FILE_URI = "file:///C:/Source/caf%C3%A9%20%25%23.pdf"
DIRECTORY_PATH = "D:/Projects/Folder Name"
DIRECTORY_URI = "file:///D:/Projects/Folder%20Name"


class ExternalReferenceApi(PayloadApi):
    def __init__(self, *, mixed=False):
        super().__init__()
        self.thoughts[ALONE]["name"] = "External owner"
        self.attachments = (self.attachments if mixed else {}) | {
            FILE: attachment(FILE, ALONE, 2, FILE_PATH, length=987654),
            DIRECTORY: attachment(DIRECTORY, ALONE, 8, DIRECTORY_PATH, length=123),
        }
        if not mixed:
            self.payloads = {}


def test_external_only_non_home_owner_materializes_both_reference_roles(tmp_path):
    api = ExternalReferenceApi()
    with api_server(api) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assets = {row["asset_id"]: row for row in record["asset_targets"]}
    for key, role, original, label, uri in (
        (FILE, "file", FILE_PATH, "caf\u00e9 %#.pdf", FILE_URI),
        (DIRECTORY, "directory", DIRECTORY_PATH, "Folder Name", DIRECTORY_URI),
    ):
        row = assets[key]
        assert (row["owner"], row["role"], row["availability"]) == (
            ALONE,
            role,
            "external",
        )
        assert row["original_name"] == original
        assert row["display_name"] == label
        assert row["external_uri"] == row["resource_link"] == uri
        assert (
            row["relative_path"] is row["actual_length"] is row["actual_sha256"] is None
        )
    note = (tmp_path / "vault/Notes/External owner.md").read_text(encoding="utf-8")
    assert "## Resources" in note
    assert "[caf\u00e9 %#.pdf](<file:///C:/Source/caf%C3%A9%20%25%23.pdf>)" in note
    assert "[Folder Name](<file:///D:/Projects/Folder%20Name>)" in note
    assert "![" not in note and "Absent source" not in note
    assert not any(path.endswith("/file-content") for path, _, _ in api.requests)
    assert record["source_gaps"] == []
    assert not (tmp_path / "vault/Attachments").exists()


def forbid_external_target_io(monkeypatch):
    import builtins
    import io
    import os
    import subprocess

    def guarded(original):
        def call(path, *args, **kwargs):
            candidates = path if isinstance(path, (list, tuple)) else [path]
            for candidate in candidates:
                if not isinstance(candidate, (str, bytes, os.PathLike)):
                    continue
                text = os.fsdecode(candidate).replace("\\", "/").lower()
                if text.startswith(
                    (
                        "c:/source",
                        "d:/projects",
                        "file:///c:/source",
                        "file:///d:/projects",
                    )
                ):
                    raise AssertionError("External target I/O was attempted")
            return original(path, *args, **kwargs)

        return call

    for module, names in (
        (builtins, ("open",)),
        (io, ("open",)),
        (os, ("open", "stat", "lstat", "listdir", "scandir", "startfile")),
        (subprocess, ("Popen",)),
    ):
        for name in names:
            if hasattr(module, name):
                monkeypatch.setattr(module, name, guarded(getattr(module, name)))


def test_external_target_boundaries_are_never_accessed_and_owned_bytes_still_work(
    tmp_path, monkeypatch
):
    from tests.support.local_api_payloads import NOTE, RAW_NOTE

    api = ExternalReferenceApi(mixed=True)
    forbid_external_target_io(monkeypatch)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="3",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert session.snapshot.source_gaps == ()
            assert session.snapshot.findings == ()
            session.verify_consistency()
            for external_id in (FILE, DIRECTORY):
                with pytest.raises(MigrationRefused), session.open_payload(external_id):
                    pytest.fail("An external reference has no captured payload")
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        assert workflow.inspect(LocalApiSourceRef(BRAIN)).outcome == "clean"
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
    assert (
        tmp_path / "vault/Attachments/22222222/Notes.md.original"
    ).read_bytes() == RAW_NOTE
    content_ids = {
        path.split("/")[-2]
        for path, _, _ in api.requests
        if path.endswith("/file-content")
    }
    assert content_ids == {NOTE}
