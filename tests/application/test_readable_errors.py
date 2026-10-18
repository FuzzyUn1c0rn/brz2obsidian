"""Readable failures through public application operations and HTTP inputs."""

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from brz2obsidian.application.contracts import (
    ApiAcquisitionConfig,
    LocalApiSourceSelection,
)
from brz2obsidian.application.operations import Operations
from tests.support.local_api import BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import NOTE, PayloadApi


def test_inspection_explains_unsupported_note_without_echoing_authored_content():
    api = PayloadApi()
    api.payloads[NOTE] = b"<script>NOTE_BODY_CANARY</script>"
    api.attachments[NOTE]["dataLength"] = len(api.payloads[NOTE])
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).inspect(
            LocalApiSourceSelection(
                brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
            )
        )
    assert result.outcome == "refused"
    message = result.findings[0].message
    assert "Inspection stopped" in message
    assert "HTML" in message and "thought note" in message
    assert "converter does not support" in message
    assert "Report this limitation" in message
    assert message in result.diagnostic_text
    assert "CANARY" not in result.model_dump_json()


def test_note_failure_names_the_thought_and_optional_context_is_compatible():
    from brz2obsidian.contracts import Issue

    old = {
        "code": "invalid_source",
        "severity": "error",
        "phase": "source",
        "message": "Existing message",
        "affected": [],
        "evidence": [],
        "rule_id": None,
        "guidance": "Existing guidance",
        "leftover_path": None,
    }
    issue = Issue.model_validate_json(json.dumps(old))
    assert json.loads(issue.model_dump_json()) == old
    assert "subject" not in issue.model_dump()
    api = PayloadApi()
    api.thoughts[HOME]["name"] = "Create a symbolic link"
    api.payloads[NOTE] = b"<script>NOTE_BODY_CANARY</script>"
    api.attachments[NOTE]["dataLength"] = len(api.payloads[NOTE])
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).inspect(
            LocalApiSourceSelection(
                brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
            )
        )
    assert 'Thought note: "Create a symbolic link".' in result.findings[0].message


def test_brain_listing_explains_access_failure_without_remote_text():
    api = PayloadApi()
    api.overrides["/api/brains"] = (401, b"Authorization: Bearer REMOTE_CANARY")
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).list_brains(
            ApiAcquisitionConfig(api_url=address)
        )
    assert result.outcome == "failed"
    message = result.findings[0].message
    assert "Brain list could not be read" in message
    assert "denied access" in message
    assert "API key in TheBrain settings" in message
    assert "CANARY" not in result.model_dump_json()


def test_unknown_source_error_is_safe_in_structured_cli_and_application_output(
    capsys, monkeypatch
):
    from brz2obsidian.application.wiring import default_workflow
    from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
    from brz2obsidian.cli import main

    ordinary = default_workflow()

    class BrokenSource:
        @contextmanager
        def open(self, reference):
            raise OSError("Authorization: Bearer EXCEPTION_CANARY")
            yield

    workflow = Workflow(
        SourceModuleBinding(BrokenSource(), ordinary.binding.policy),
        ordinary.renderer,
        ordinary.publisher,
    )
    raw = workflow.inspect("unused")
    assert "CANARY" not in raw.model_dump_json()
    result = Operations(workflow).inspect(Path("unused.brz"))
    assert "cause is not known" in result.findings[0].message
    assert "report the problem" in result.findings[0].message
    monkeypatch.setattr(
        "brz2obsidian.application.wiring.default_workflow", lambda: workflow
    )
    assert main(["inspect", "unused.brz"]) == 1
    output = capsys.readouterr()
    assert "cause is not known" in output.out
    assert "CANARY" not in output.out + output.err


@pytest.mark.parametrize(
    "problem,explanation",
    [
        ("invalid_utf8", "not valid UTF-8"),
        ("missing_target", "could not be found in this Brain"),
        ("missing_attachment", "could not find a required attachment"),
        ("foreign_owner", "different Brain or owner"),
        ("changed_metadata", "different details for the same attachment"),
        ("malformed_response", "data in a form the converter could not read"),
        ("unsupported_metadata", "details of a thought"),
    ],
)
def test_api_source_failures_keep_distinct_known_causes(problem, explanation):
    api = PayloadApi()
    if problem == "invalid_utf8":
        api.payloads[NOTE] = b"\xffNOTE_BODY_CANARY"
    elif problem == "missing_target":
        api.payloads[NOTE] = b"[missing](brain://qqqqqqqqqkqKqqqqqqqqqg/Missing)"
    elif problem == "missing_attachment":
        api.overrides[f"/api/attachments/{BRAIN}/{NOTE}/file-content"] = (
            404,
            b"REMOTE_CANARY",
        )
    elif problem == "foreign_owner":
        api.attachments[NOTE]["brainId"] = HOME
    elif problem == "changed_metadata":
        api.overrides[f"/api/attachments/{BRAIN}/{NOTE}/metadata"] = (
            200,
            dict(api.attachments[NOTE], location="Other.md"),
        )
    elif problem == "unsupported_metadata":
        api.thoughts[HOME]["unsupportedField"] = "REMOTE_CANARY"
    else:
        api.overrides[f"/api/brains/{BRAIN}"] = (200, b"REMOTE_CANARY")
    api.attachments[NOTE]["dataLength"] = len(api.payloads[NOTE])
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).inspect(
            LocalApiSourceSelection(
                brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
            )
        )
    assert result.outcome in {"refused", "failed"}
    assert explanation in result.findings[0].message
    if problem == "unsupported_metadata":
        assert 'Thought: "Entry".' in result.findings[0].message
    if problem == "missing_target":
        assert 'Thought note: "Entry".' in result.findings[0].message
    assert result.findings[0].message in result.diagnostic_text
    assert "CANARY" not in result.model_dump_json()


def test_reviewed_conversion_and_human_cli_keep_the_note_reason(
    tmp_path, capsys, monkeypatch
):
    from brz2obsidian.cli import main

    api = PayloadApi()
    with api_server(api) as (_, address):
        selection = LocalApiSourceSelection(
            brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
        )
        operations = Operations(credentials=lambda: KEY)
        reviewed = operations.inspect(selection).reviewed
        assert reviewed is not None
        api.payloads[NOTE] = b"<script>NOTE_BODY_CANARY</script>"
        api.attachments[NOTE]["dataLength"] = len(api.payloads[NOTE])
        result = operations.convert_reviewed(selection, tmp_path, "New vault", reviewed)
        assert result.publication.state == "not_published"
        assert "Conversion stopped" in result.findings[0].message
        assert "does not support this HTML" in result.findings[0].message
        assert result.findings[0].message in result.diagnostic_text
        monkeypatch.setenv("THE_BRAIN_LOCAL_API_KEY", KEY)
        assert (
            main(["inspect", BRAIN, "--source-kind", "local-api", "--api-url", address])
            == 1
        )
        output = capsys.readouterr()
        assert (
            main(
                [
                    "inspect",
                    BRAIN,
                    "--source-kind",
                    "local-api",
                    "--api-url",
                    address,
                    "--json",
                ]
            )
            == 1
        )
        details = json.loads(capsys.readouterr().out)
        assert "Report this limitation" in details["issues"][0]["guidance"]
        assert "re-export" not in details["issues"][0]["guidance"]
    assert "Inspection stopped" in output.out
    assert "does not support this HTML" in output.out
    assert "CANARY" not in output.out + output.err + result.model_dump_json()
    assert not (tmp_path / "New vault").exists()


def test_brz_file_access_and_invalid_archive_have_different_explanations(tmp_path):
    from brz2obsidian.application.wiring import default_workflow

    missing = tmp_path / "missing.brz"
    result = Operations().inspect(missing)
    assert "BRZ archive could not be found" in result.findings[0].message
    assert "Choose an existing BRZ archive" in result.findings[0].message
    raw = default_workflow().inspect(missing)
    assert raw.issues[0].rule_id == "diagnostic.archive_missing"
    invalid = tmp_path / "invalid.brz"
    invalid.write_bytes(b"ARCHIVE_CONTENT_CANARY")
    result = Operations().inspect(invalid)
    assert "could not be read as a supported BRZ archive" in result.findings[0].message
    assert "CANARY" not in result.model_dump_json()


def test_destination_and_vault_check_explain_the_operation_and_next_action(
    tmp_path, capsys
):
    from brz2obsidian.application.operations import validate_destination
    from brz2obsidian.cli import main

    destination = validate_destination(tmp_path, "invalid/name")
    assert "destination cannot be used" in destination.field_errors[0].message
    assert "folder name" in destination.field_errors[0].message
    assert "Enter" in destination.field_errors[0].message
    note = tmp_path / "Broken.md"
    note.write_text("---\nkey: [unterminated\n---\nNOTE_BODY_CANARY", encoding="utf-8")
    result = Operations().check_vault(tmp_path)
    assert result.outcome == "issues"
    assert "Vault check found" in result.findings[0].message
    assert "properties at the start of a note" in result.findings[0].message
    assert result.findings[0].path == "Broken.md"
    assert "Correct" in result.findings[0].message
    assert result.findings[0].message in result.diagnostic_text
    assert main(["check-vault", str(tmp_path)]) == 2
    output = capsys.readouterr()
    assert result.findings[0].message in output.out
    assert "Broken.md" in output.out
    assert "CANARY" not in output.out + output.err + result.model_dump_json()


@pytest.mark.parametrize(
    "code,reason,explanation,action",
    [
        (
            "api_credentials_missing",
            None,
            "key has not been configured",
            "Set THE_BRAIN_LOCAL_API_KEY",
        ),
        ("api_transport_failed", None, "connection to TheBrain", "TheBrain is running"),
        (
            "api_request_timeout",
            None,
            "did not respond within the allowed time",
            "increase the request time limit",
        ),
        ("api_capture_failed", None, "temporary copy", "report"),
        ("api_capture_read_failed", None, "temporary copy", "report"),
        ("api_payload_read_failed", None, "attachment in the temporary copy", "report"),
        (
            "api_capture_storage_changed",
            None,
            "temporary storage changed",
            "Inspect again",
        ),
        ("image_presentation_normalized", None, "image width", "responsive"),
        (
            "invalid_source",
            "diagnostic.relationship_conflict",
            "conflicting information about a relationship",
            "Let changes in TheBrain finish",
        ),
        (
            "invalid_source",
            "diagnostic.attachment_unsupported",
            "attachment's type or details",
            "Report this limitation",
        ),
        ("source_changed", None, "changed while it was being read", "Let edits finish"),
        (
            "unsupported_feature",
            "diagnostic.note_target_missing",
            "does not support a feature",
            "Report this limitation",
        ),
        (
            "invalid_source",
            "foreign.note_html",
            "could not verify the Brain's data",
            "do not establish whether the cause",
        ),
        (
            "unknown_backend_code",
            "diagnostic.note_html",
            "cause could not be identified",
            "report the problem",
        ),
    ],
)
def test_supported_issue_categories_are_safe_without_inventing_causes(
    code, reason, explanation, action
):
    from brz2obsidian.application.wiring import default_workflow
    from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
    from brz2obsidian.contracts import Issue, MigrationRefused

    ordinary = default_workflow()

    class SourceBoundary:
        @contextmanager
        def open(self, reference):
            raise MigrationRefused(
                (
                    Issue(
                        code=code,
                        phase="source",
                        rule_id=reason,
                        message="BODY_CANARY",
                        guidance="GUIDANCE_CANARY",
                        evidence=("Authorization: Bearer SECRET_CANARY",),
                    ),
                )
            )
            yield

    workflow = Workflow(
        SourceModuleBinding(SourceBoundary(), ordinary.binding.policy),
        ordinary.renderer,
        ordinary.publisher,
    )
    result = Operations(workflow).inspect(Path("unused.brz"))
    message = result.findings[0].message
    assert explanation in message and action in message
    assert "CANARY" not in result.model_dump_json()


@pytest.mark.parametrize(
    "payload,explanation,action",
    [
        (
            b"<script>BODY_CANARY</script>",
            "does not support this HTML",
            "Report this limitation",
        ),
        (
            b"[missing](brain://qqqqqqqqqkqKqqqqqqqqqg/Missing)",
            "does not point to a live thought",
            "Check the link",
        ),
        (
            None,
            "required thought-note or attachment contents are unavailable",
            "Check that the contents open in TheBrain",
        ),
    ],
)
def test_brz_note_failures_retain_safe_thought_name(
    tmp_path, payload, explanation, action
):
    from zipfile import ZipFile

    fixture = Path(__file__).parents[1] / "fixtures/minimal.brz"
    source = tmp_path / "note-problem.brz"
    member = "22222222-2222-4222-8222-222222222222/Notes.md"
    with ZipFile(fixture) as original, ZipFile(source, "w") as changed:
        for name in original.namelist():
            content = original.read(name)
            if name == member:
                if payload is None:
                    continue
                content = payload
            elif name == "attachments.json" and payload is not None:
                record = json.loads(content)
                record["DataLength"] = len(payload)
                content = json.dumps(record).encode()
            changed.writestr(name, content)
    result = Operations().inspect(source)
    assert result.outcome == "refused"
    message = result.findings[0].message
    assert explanation in message and action in message
    assert '"Entry thought"' in message
    assert message in result.diagnostic_text
    assert "CANARY" not in result.model_dump_json()
    from brz2obsidian.application.wiring import default_workflow

    issue = default_workflow().inspect(source).issues[0]
    assert issue.subject.name == "Entry thought"
    if payload is not None and payload.startswith(b"<script>"):
        assert "Report this limitation" in issue.guidance
        assert "resolved before retrying" not in issue.guidance


def test_publication_and_cleanup_keep_exception_text_out_of_cli_json(
    tmp_path, monkeypatch, capsys
):
    import shutil

    from brz2obsidian.cli import main

    source = Path(__file__).parents[1] / "fixtures/minimal.brz"
    destination = tmp_path / "Published"
    native_rename, native_rmtree = Path.rename, shutil.rmtree

    def denied_rename(path, target):
        if path.name.startswith(".brz2obsidian-"):
            raise OSError("Authorization: Bearer WRITE_EXCEPTION_CANARY")
        return native_rename(path, target)

    def denied_cleanup(path, *args, **kwargs):
        if Path(path).name.startswith(".brz2obsidian-"):
            raise OSError("Authorization: Bearer CLEANUP_EXCEPTION_CANARY")
        return native_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(Path, "rename", denied_rename)
    monkeypatch.setattr(shutil, "rmtree", denied_cleanup)
    assert main(["convert", str(source), str(destination), "--json"]) == 1
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert [issue["code"] for issue in result["issues"]] == [
        "write_failure",
        "cleanup_failure",
    ]
    assert "CANARY" not in output.out + output.err
    assert "Authorization" not in output.out + output.err
    assert result["receipt"] is None
    assert not destination.exists()
    leftover = Path(result["issues"][1]["leftover_path"])
    assert leftover.parent == tmp_path and leftover.is_dir()
    native_rmtree(leftover)
