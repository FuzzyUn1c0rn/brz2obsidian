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
                    "convert",
                    BRAIN,
                    str(tmp_path / "CLI vault"),
                    "--source-kind",
                    "local-api",
                    "--api-url",
                    address,
                    "--json",
                ]
            )
            == 1
        )
        conversion_details = json.loads(capsys.readouterr().out)
        assert conversion_details["operation"] == "convert"
        assert (
            "does not support this HTML" in conversion_details["issues"][0]["guidance"]
        )
        assert "Report this limitation" in conversion_details["issues"][0]["guidance"]
        assert "Inspection stopped" not in conversion_details["issues"][0]["guidance"]
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


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Explains decision history", 'Relationship: "Explains decision history".'),
        (
            "Explains\u202e decision\x1b history",
            'Relationship: "Explains decision history".',
        ),
        ("https://RELATIONSHIP_LABEL_CANARY", 'Relationship: "Entry \u2014 Alone".'),
        (
            "Authorization: Bearer RELATIONSHIP_SECRET_CANARY",
            'Relationship: "Entry \u2014 Alone".',
        ),
        (
            "Authoriz\u202eation: Bearer RELATIONSHIP_SECRET_CANARY",
            'Relationship: "Entry \u2014 Alone".',
        ),
        ("\u202e\x1b", 'Relationship: "Entry \u2014 Alone".'),
        (None, 'Relationship: "Entry — Alone".'),
    ],
)
def test_relationship_failure_identifies_safe_name_or_endpoints(name, expected):
    from tests.support.local_api_graph import HIERARCHY, GraphApi

    api = GraphApi()
    api.links[HIERARCHY].update(name=name, color="bad_color")
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).inspect(
            LocalApiSourceSelection(
                brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
            )
        )
    message = result.findings[0].message
    assert result.outcome == "refused"
    assert "could not interpret a relationship" in message
    assert expected in message
    assert "CANARY" not in result.model_dump_json()
    assert "\u202e" not in message and "\x1b" not in message


def test_relationship_summary_failure_identifies_affected_thought():
    from tests.support.local_api_graph import CompleteGraphApi

    api = CompleteGraphApi()
    api.thoughts[HOME]["typeId"] = None
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).inspect(
            LocalApiSourceSelection(
                brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
            )
        )
    assert result.outcome == "refused"
    message = result.findings[0].message
    assert "conflicting information about a relationship" in message
    assert 'Thought: "Entry".' in message


def test_api_graph_failure_identifies_current_thought():
    from tests.support.local_api_graph import GraphApi

    api = GraphApi()
    api.overrides[f"/api/thoughts/{BRAIN}/{HOME}/graph"] = (200, {})
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).inspect(
            LocalApiSourceSelection(
                brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
            )
        )
    assert result.outcome == "refused"
    assert 'Thought: "Entry".' in result.findings[0].message


def test_brz_relationship_failure_identifies_safe_endpoints(tmp_path):
    from zipfile import ZipFile

    fixture = Path(__file__).parents[1] / "fixtures/minimal.brz"
    source = tmp_path / "relationship-problem.brz"
    peer = "44444444-4444-4444-8444-444444444444"
    with ZipFile(fixture) as original, ZipFile(source, "w") as changed:
        original_thought = json.loads(original.read("thoughts.json"))
        for name in original.namelist():
            content = original.read(name)
            if name == "thoughts.json":
                content = (
                    json.dumps(original_thought)
                    + "\n"
                    + json.dumps(dict(original_thought, Id=peer, Name="Other thought"))
                )
            elif name == "links.json":
                content = json.dumps(
                    {
                        "Id": "55555555-5555-4555-8555-555555555555",
                        "BrainId": original_thought["BrainId"],
                        "ThoughtIdA": original_thought["Id"],
                        "ThoughtIdB": peer,
                        "Kind": 1,
                        "Relation": 1,
                        "Meaning": 999,
                        "Direction": -1,
                    }
                )
            changed.writestr(name, content)
    result = Operations().inspect(source)
    assert result.outcome == "refused"
    assert (
        'Relationship: "Entry thought — Other thought".' in result.findings[0].message
    )


def test_brz_thought_failure_identifies_admitted_title(tmp_path):
    from zipfile import ZipFile

    fixture = Path(__file__).parents[1] / "fixtures/minimal.brz"
    source = tmp_path / "thought-problem.brz"
    with ZipFile(fixture) as original, ZipFile(source, "w") as changed:
        for name in original.namelist():
            content = original.read(name)
            if name == "thoughts.json":
                content = json.dumps(dict(json.loads(content), Aliases=["BODY_CANARY"]))
            changed.writestr(name, content)
    result = Operations().inspect(source)
    assert result.outcome == "refused"
    assert 'Thought: "Entry thought".' in result.findings[0].message
    assert "CANARY" not in result.model_dump_json()


@pytest.mark.parametrize(
    "display_name", [None, "Authorization: Bearer DISPLAY_NAME_CANARY"]
)
def test_brz_payload_read_failure_identifies_admitted_attachment(
    monkeypatch, tmp_path, display_name
):
    from zipfile import ZipExtFile, ZipFile

    from brz2obsidian.contracts import MigrationFailed
    from brz2obsidian.sources.thebrain import BrzSourceModule

    source = Path(__file__).parents[1] / "fixtures/minimal.brz"
    if display_name is not None:
        selected = tmp_path / "display-name.brz"
        with ZipFile(source) as original, ZipFile(selected, "w") as changed:
            for name in original.namelist():
                content = original.read(name)
                if name == "attachments.json":
                    content = json.dumps(dict(json.loads(content), Name=display_name))
                changed.writestr(name, content)
        source = selected
    with BrzSourceModule().open(source) as session:
        asset = session.snapshot.assets[0]

        def unreadable(*args, **kwargs):
            raise OSError("Authorization: Bearer PAYLOAD_EXCEPTION_CANARY")

        monkeypatch.setattr(ZipExtFile, "read", unreadable)
        with (
            pytest.raises(MigrationFailed) as caught,
            session.open_payload(asset.asset_id) as stream,
        ):
            stream.read()
    issue = caught.value.issues[0]
    assert issue.subject.kind == "asset" and issue.subject.name == "Notes.md"
    assert "CANARY" not in issue.model_dump_json()


def test_api_no_note_failure_identifies_current_thought():
    from tests.support.local_api_graph import GraphApi

    api = GraphApi()
    api.overrides[f"/api/notes/{BRAIN}/{HOME}"] = (200, {})
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).inspect(
            LocalApiSourceSelection(
                brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
            )
        )
    assert result.outcome == "refused"
    assert 'Thought: "Entry".' in result.findings[0].message


def test_excluded_relationship_metadata_is_absent_from_public_api_diagnostics():
    from tests.support.local_api import ALONE
    from tests.support.local_api_graph import HIERARCHY, GraphApi

    api = GraphApi()
    api.thoughts[ALONE].update(
        name="EXCLUDED_THOUGHT_CANARY", forgottenDateTime="2026-10-01T00:00:00"
    )
    api.links[HIERARCHY].update(name="EXCLUDED_RELATIONSHIP_CANARY", color="bad_color")
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).inspect(
            LocalApiSourceSelection(
                brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
            )
        )
    assert result.outcome == "clean"
    assert "CANARY" not in result.model_dump_json()


def test_brz_private_relationship_refusal_does_not_infer_endpoint_names(tmp_path):
    from zipfile import ZipFile

    fixture = Path(__file__).parents[1] / "fixtures/minimal.brz"
    source = tmp_path / "private-relationship.brz"
    peer = "44444444-4444-4444-8444-444444444444"
    with ZipFile(fixture) as original, ZipFile(source, "w") as changed:
        thought = json.loads(original.read("thoughts.json"))
        for name in original.namelist():
            content = original.read(name)
            if name == "thoughts.json":
                content = (
                    json.dumps(thought)
                    + "\n"
                    + json.dumps(
                        dict(
                            thought,
                            Id=peer,
                            Name="PRIVATE_CANARY",
                            ForgottenDateTime="2026-10-01T00:00:00",
                        )
                    )
                )
            elif name == "links.json":
                content = json.dumps(
                    {
                        "Id": "55555555-5555-4555-8555-555555555555",
                        "BrainId": thought["BrainId"],
                        "ThoughtIdA": thought["Id"],
                        "ThoughtIdB": thought["Id"],
                        "Kind": peer,
                        "Relation": 1,
                        "Meaning": 1,
                        "Direction": -1,
                    }
                )
            changed.writestr(name, content)
    result = Operations().inspect(source)
    assert result.outcome == "refused"
    assert "CANARY" not in result.model_dump_json()
    assert "Relationship:" not in result.findings[0].message
    assert "Entry thought" not in result.findings[0].message


@pytest.mark.parametrize("unsafe_owner", [False, True])
def test_core_content_failure_keeps_safe_owner_without_inventing_broken_link(
    unsafe_owner,
):
    from types import SimpleNamespace

    from brz2obsidian.application.wiring import default_workflow
    from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
    from brz2obsidian.sources.thebrain import BrzSourceModule

    ordinary = default_workflow()
    source = Path(__file__).parents[1] / "fixtures/minimal.brz"
    with BrzSourceModule().open(source) as session:
        snapshot = session.snapshot
    document = snapshot.documents[0].model_copy(update={"text_digest": "0" * 64})
    snapshot = snapshot.model_copy(update={"documents": (document,)})
    if unsafe_owner:
        owner = snapshot.items[0].model_copy(
            update={"title": "Authorization: Bearer OWNER_CANARY"}
        )
        snapshot = snapshot.model_copy(update={"items": (owner,)})

    class DeclaredSource:
        @contextmanager
        def open(self, reference):
            yield SimpleNamespace(snapshot=snapshot)

    workflow = Workflow(
        SourceModuleBinding(DeclaredSource(), ordinary.binding.policy),
        ordinary.renderer,
        ordinary.publisher,
    )
    result = Operations(workflow).inspect(Path("unused.brz"))
    assert result.outcome == "refused"
    message = result.findings[0].message
    assert (
        'Attachment: "Notes.md".' if unsafe_owner else 'Thought note: "Entry thought".'
    ) in message
    assert "CANARY" not in result.model_dump_json()
    assert "could not safely prepare" in message
    assert "link" not in message.casefold() and "missing" not in message.casefold()
    assert "report" in message.casefold()


def test_scoped_original_note_payload_keeps_public_access_without_asset_record(
    tmp_path,
):
    import base64
    from uuid import UUID

    from brz2obsidian.sources.thebrain import BrzSourceModule
    from tests.application.test_forgotten_workflow import forget, rewrite
    from tests.application.test_graph_workflow import graph_archive, identity

    compact = base64.urlsafe_b64encode(UUID(identity(2)).bytes_le).decode().rstrip("=")
    original = f"Before [private](brain://{compact}/private) after".encode()
    source = graph_archive(
        tmp_path / "source.brz", {1: "Home", 2: "Private"}, notes={1: (original, 4)}
    )
    rewrite(source, lambda parts: forget(parts, 2))
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.original_copy_omitted
        assert document.key not in {asset.asset_id for asset in session.snapshot.assets}
        with session.open_payload(document.key) as stream:
            assert stream.read() == original


def test_link_owned_failure_uses_safe_endpoints_when_relationship_label_is_unsafe():
    from tests.support.local_api_graph import HIERARCHY, GraphApi

    api = GraphApi()
    api.links[HIERARCHY]["name"] = "Authorization: Bearer RELATIONSHIP_OWNER_CANARY"
    api.overrides[f"/api/links/{BRAIN}/{HIERARCHY}/attachments"] = (200, [{}])
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).inspect(
            LocalApiSourceSelection(
                brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
            )
        )
    assert result.outcome == "refused"
    assert 'Relationship: "Entry \u2014 Alone".' in result.findings[0].message
    assert "CANARY" not in result.model_dump_json()


def test_brz_classification_failure_uses_next_safe_affected_thought(tmp_path):
    from zipfile import ZipFile

    fixture = Path(__file__).parents[1] / "fixtures/minimal.brz"
    source = tmp_path / "classification-problem.brz"
    definition = "44444444-4444-4444-8444-444444444444"
    with ZipFile(fixture) as original, ZipFile(source, "w") as changed:
        thought = json.loads(original.read("thoughts.json"))
        for name in original.namelist():
            content = original.read(name)
            if name == "thoughts.json":
                content = (
                    json.dumps(
                        dict(
                            thought,
                            Name="Authorization: Bearer FIRST_OWNER_CANARY",
                            TypeId=definition,
                        )
                    )
                    + "\n"
                    + json.dumps(
                        dict(thought, Id=definition, Name="Safe definition", Kind=2)
                    )
                )
            changed.writestr(name, content)
    result = Operations().inspect(source)
    assert result.outcome == "refused"
    assert 'Thought: "Safe definition".' in result.findings[0].message
    assert "CANARY" not in result.model_dump_json()


def test_unexpected_library_programming_errors_still_propagate():
    from brz2obsidian.application.wiring import default_workflow
    from brz2obsidian.application.workflow import SourceModuleBinding, Workflow

    ordinary = default_workflow()

    class BrokenSource:
        @contextmanager
        def open(self, reference):
            raise RuntimeError("Authorization: Bearer RUNTIME_EXCEPTION_CANARY")
            yield

    workflow = Workflow(
        SourceModuleBinding(BrokenSource(), ordinary.binding.policy),
        ordinary.renderer,
        ordinary.publisher,
    )
    with pytest.raises(RuntimeError, match="RUNTIME_EXCEPTION_CANARY"):
        workflow.inspect("unused")


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_inspection_contains_unexpected_programming_errors(
    monkeypatch, capsys, json_output
):
    from brz2obsidian.application.wiring import default_workflow
    from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
    from brz2obsidian.cli import main
    from brz2obsidian.contracts import RunResult

    ordinary = default_workflow()

    class BrokenSource:
        @contextmanager
        def open(self, reference):
            raise RuntimeError("Authorization: Bearer RUNTIME_EXCEPTION_CANARY")
            yield

    workflow = Workflow(
        SourceModuleBinding(BrokenSource(), ordinary.binding.policy),
        ordinary.renderer,
        ordinary.publisher,
    )
    monkeypatch.setattr(
        "brz2obsidian.application.wiring.default_workflow", lambda: workflow
    )
    assert main(["inspect", "unused.brz", *(["--json"] if json_output else [])]) == 1
    output = capsys.readouterr()
    assert "CANARY" not in output.out + output.err
    if json_output:
        result = RunResult.model_validate_json(output.out)
        assert (
            result.schema_version == 7
            and result.operation == "inspect"
            and result.outcome == "failed"
        )
        assert result.counts is None and result.receipt is None
        message = result.issues[0].message + " " + result.issues[0].guidance
    else:
        message = output.out
    assert "Inspection" in message and "cause is not known" in message
    assert "report" in message.casefold()


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_conversion_failure_keeps_publication_uncertainty(
    tmp_path, monkeypatch, capsys, json_output
):
    from brz2obsidian.application.wiring import default_workflow
    from brz2obsidian.application.workflow import Workflow
    from brz2obsidian.cli import main
    from brz2obsidian.contracts import RunResult

    ordinary = default_workflow()

    class LaterFailurePublisher:
        def publish(self, artifacts, payloads, destination):
            ordinary.publisher.publish(artifacts, payloads, destination)
            raise RuntimeError("Authorization: Bearer PUBLICATION_RUNTIME_CANARY")

    workflow = Workflow(ordinary.binding, ordinary.renderer, LaterFailurePublisher())
    monkeypatch.setattr(
        "brz2obsidian.application.wiring.default_workflow", lambda: workflow
    )
    source = Path(__file__).parents[1] / "fixtures/minimal.brz"
    destination = tmp_path / "Created before failure"
    assert (
        main(
            [
                "convert",
                str(source),
                str(destination),
                *(["--json"] if json_output else []),
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert destination.is_dir() and (destination / "Home — Entry thought.md").is_file()
    assert "CANARY" not in output.out + output.err
    if json_output:
        result = RunResult.model_validate_json(output.out)
        assert (
            result.schema_version == 7
            and result.operation == "convert"
            and result.outcome == "failed"
        )
        assert result.receipt is None and result.counts is None
        message = result.issues[0].message + " " + result.issues[0].guidance
    else:
        message = output.out
    assert "Conversion" in message and "cause is not known" in message
    assert "Publication status is unknown" in message
    assert "Check the destination" in message and "another" in message
    assert "not published" not in message.casefold()


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_vault_check_contains_unexpected_errors(
    tmp_path, monkeypatch, capsys, json_output
):
    from brz2obsidian.cli import main

    def unavailable(vault):
        raise RuntimeError("Authorization: Bearer CHECK_RUNTIME_CANARY")

    monkeypatch.setattr("brz2obsidian.vault_check.check_vault", unavailable)
    assert (
        main(["check-vault", str(tmp_path), *(["--json"] if json_output else [])]) == 1
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert "CANARY" not in output.err
    assert "Vault check" in output.err and "cause is not known" in output.err
    assert "report" in output.err.casefold()


def test_cli_workflow_factory_type_error_is_unknown_not_invalid_settings(
    monkeypatch, capsys
):
    from brz2obsidian.cli import main
    from brz2obsidian.contracts import RunResult

    def broken_factory():
        raise TypeError("Authorization: Bearer FACTORY_RUNTIME_CANARY")

    monkeypatch.setattr(
        "brz2obsidian.application.wiring.default_workflow", broken_factory
    )
    assert main(["inspect", "unused.brz", "--json"]) == 1
    output = capsys.readouterr()
    result = RunResult.model_validate_json(output.out)
    assert result.outcome == "failed"
    assert result.issues[0].code == "operation_failure"
    assert "cause is not known" in result.issues[0].message
    assert "CANARY" not in output.out + output.err


@pytest.mark.parametrize("signal", [KeyboardInterrupt, SystemExit])
def test_cli_keeps_interruption_and_process_exit_signals(monkeypatch, signal):
    from brz2obsidian.cli import main

    def interrupted_factory():
        raise signal("Controlled process interruption")

    monkeypatch.setattr(
        "brz2obsidian.application.wiring.default_workflow", interrupted_factory
    )
    with pytest.raises(signal):
        main(["inspect", "unused.brz"])


def test_cli_does_not_expose_failure_of_its_safe_error_output(
    tmp_path, monkeypatch, capsys
):
    import sys

    from brz2obsidian.cli import main

    def unavailable(vault):
        raise RuntimeError("Authorization: Bearer ORIGINAL_RUNTIME_CANARY")

    class BrokenOutput:
        def write(self, text):
            raise OSError("Authorization: Bearer OUTPUT_FAILURE_CANARY")

        def flush(self):
            pass

    monkeypatch.setattr("brz2obsidian.vault_check.check_vault", unavailable)
    monkeypatch.setattr(sys, "stderr", BrokenOutput())
    assert main(["check-vault", str(tmp_path), "--json"]) == 1
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_conflicting_observation_uses_established_thought_name():
    from tests.support.local_api import MetadataApi

    api = MetadataApi()
    path = f"/api/thoughts/{BRAIN}/{HOME}/graph"
    graph = api.response(path, {})[1]
    graph["activeThought"] = dict(api.thoughts[HOME], name="CONFLICT_CANARY")
    api.overrides[path] = (200, graph)
    with api_server(api) as (_, address):
        result = Operations(credentials=lambda: KEY).inspect(
            LocalApiSourceSelection(
                brain_id=BRAIN, config=ApiAcquisitionConfig(api_url=address)
            )
        )
    assert result.outcome == "refused"
    message = result.findings[0].message
    assert "conflicting details for the same thought" in message
    assert 'Thought: "Entry".' in message
    assert "CANARY" not in result.model_dump_json()


def test_warning_keeps_qualified_attachment_context_in_application_report(tmp_path):
    from tests.application.test_verified_coverage import absent_parts, write_source

    source = write_source(tmp_path, absent_parts(tmp_path))
    result = Operations().inspect(source)
    assert result.outcome == "warnings"
    finding = next(f for f in result.findings if f.code == "approved_source_gap")
    assert 'Attachment: "paper.txt".' in finding.message
    assert "Review" in finding.message and "Migration report" in finding.message
    assert finding.message in result.diagnostic_text
