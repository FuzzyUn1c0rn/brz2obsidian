"""Current ordinary-file output checked against independently recorded raw API."""

import hashlib
import json
import shutil
from copy import deepcopy

import pytest

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef
from tests.local_acceptance.api_baseline import prepare_controls
from tests.local_acceptance.api_checker import check_api_vault, expected_asset
from tests.local_acceptance.api_recording import ApiRecording
from tests.local_acceptance.api_scope import qualify_scope
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.support.audit_sources import SCHEMA
from tests.support.local_api import BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import FILE, PayloadApi, attachment

INTERNAL_FILES = (
    (FILE, "clip.mp4", b"\x00\xffmedia\x80\r\n"),
    (
        "b1111111-1111-4111-8111-111111111111",
        "document.docx",
        b"PK\x03\x04opaque Office bytes",
    ),
    (
        "b2222222-2222-4222-8222-222222222222",
        "page.html",
        b'<img src="https://example.invalid/never-fetch">\r\n',
    ),
    ("b3333333-3333-4333-8333-333333333333", "pdf", b"not-a-PDF"),
    ("b4444444-4444-4444-8444-444444444444", "empty.future", b""),
)


@pytest.fixture(scope="module")
def internal_file_output(tmp_path_factory):
    directory = tmp_path_factory.mktemp("internal-file-independent")
    api = PayloadApi()
    for identity, filename, raw in INTERNAL_FILES:
        api.attachments[identity] = attachment(
            identity, HOME, 1, filename, length=len(raw)
        )
        api.payloads[identity] = raw
    api.attachments[FILE]["name"] = "Raw media label"
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    controls = prepare_controls(directory / "separate-controls")
    vault = directory / "vault"
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            directory / "http",
            upstream,
            brain_id=BRAIN,
            credential=KEY,
            purpose="convert",
        )
        with recording:
            workflow = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
            )
            result = workflow.convert(LocalApiSourceRef(BRAIN), vault)
            assert result.outcome == "clean", result.issues
            assert result.receipt.verified
            recording.complete()
        baseline = recording.seal(qualification=controls)
    return baseline, vault, result.model_dump(mode="json", by_alias=True)


def test_complete_raw_api_audit_preserves_opaque_files_without_interpreting_them(
    internal_file_output,
):
    baseline, vault, _ = internal_file_output
    assert check_api_vault(baseline, vault, profile_version="4") == {
        "thoughts": 2,
        "relationships": 0,
        "payloads": 6,
    }
    record = json.loads((vault / "migration-record.json").read_bytes())
    targets = {row["asset_id"]: row for row in record["asset_targets"]}
    assert targets[FILE]["display_name"] == "Raw media label"
    home = (vault / "Home — Entry.md").read_text(encoding="utf-8")
    for identity, filename, raw in INTERNAL_FILES:
        expected_path = "Attachments/22222222/" + filename
        assert targets[identity]["role"] == "file"
        assert targets[identity]["relative_path"] == expected_path
        assert (vault / expected_path).read_bytes() == raw
        assert "[[" + expected_path in home
        assert "![[" + expected_path not in home
    assert "<video" not in home and "<img src=" not in home


@pytest.mark.parametrize("damage", ["payload", "role", "assignment", "availability"])
def test_raw_api_audit_rejects_rehashed_ordinary_file_forgeries(
    tmp_path, internal_file_output, damage
):
    baseline, original, original_result = internal_file_output
    vault = tmp_path / "forged"
    shutil.copytree(original, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    asset = next(a for a in record["asset_targets"] if a["asset_id"] == FILE)
    path = vault / asset["relative_path"]
    note_path = vault / "Home — Entry.md"
    note = note_path.read_text(encoding="utf-8")
    if damage == "payload":
        raw = path.read_bytes()
        changed = b"\x01" + raw[1:]
        path.write_bytes(changed)
        asset["actual_sha256"] = hashlib.sha256(changed).hexdigest()
    elif damage == "role":
        asset["role"] = "image"
        note_path.write_text(
            note.replace("[[" + asset["relative_path"], "![[" + asset["relative_path"]),
            encoding="utf-8",
        )
    elif damage == "assignment":
        old_path = asset["relative_path"]
        new_path = "Attachments/22222222/renamed.mp4"
        path.rename(vault / new_path)
        asset["relative_path"] = asset["resource_link"] = new_path
        note_path.write_text(note.replace(old_path, new_path), encoding="utf-8")
    else:
        path.unlink()
        asset.update(
            availability="absent",
            actual_length=None,
            actual_sha256=None,
            relative_path=None,
            resource_link=None,
        )
        record["counts"]["present_assets"] -= 1
        record["counts"]["planned_assets"] -= 1
    # The claimed publication hashes/counts describe the forged actual files.
    # Independently recorded HTTP bytes/declarations still contradict them.
    rewrite_record(vault, record, deepcopy(original_result))
    with pytest.raises(AssertionError):
        check_api_vault(baseline, vault, profile_version="4")


@pytest.mark.parametrize("profile", ["1", "2", "3"])
def test_independent_old_profile_file_grammar_does_not_inherit_current_admission(
    internal_file_output, profile
):
    baseline, _, _ = internal_file_output
    declaration = qualify_scope(baseline, profile_version="4").declarations[FILE]
    with pytest.raises(AssertionError, match="raw file role"):
        expected_asset(baseline, declaration, profile_version=profile)
