"""Independent #370 paired source and generated-output challenge."""

import base64
import json
import shutil
from uuid import UUID

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.wiring import default_workflow, local_api_workflow
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef
from tests.application.test_graph_workflow import graph_archive, identity
from tests.local_acceptance.api_checker import check_api_vault
from tests.local_acceptance.api_recording import ApiRecording
from tests.local_acceptance.checker import check_vault
from tests.local_acceptance.test_api_scope_v3 import scope_baseline
from tests.support.audit_sources import SCHEMA
from tests.support.local_api import BRAIN, HOME, api_server, thought
from tests.support.local_api_payloads import attachment
from tests.support.recorded_format8 import format8_workflow
from tests.support.type_tag_sources import TypeTagApi

HUB = UUID("11111111-0000-4000-8000-000000000002").int
TWIN = UUID("22222222-0000-4000-8000-000000000003").int
TITLES = {
    1: "Entry",
    HUB: "Twin",
    TWIN: "Twin",
    4: "Leaf",
    5: "Jump A",
    6: "Jump B",
    7: "Topic",
    8: "Assigned only",
    9: "Isolated",
    11: "Child",
}
EDGES = (
    (1, HUB, 1, 1, -1),
    (HUB, TWIN, 1, 1, -1),
    (HUB, 11, 1, 1, -1),
    (1, 4, 1, 1, -1),
    (1, 7, 1, 1, -1),
    (5, 6, 3, 1, -1),
    (7, 4, 1, 5, -1),
    (7, 8, 1, 5, -1),
)
TOKEN = base64.urlsafe_b64encode(UUID(int=HUB).bytes_le).decode().rstrip("=")
TWIN_BODY = (
    f"[Authored twin](brain://{TOKEN}/Twin)\r\n\r\nLocal source prose.\r\n"
).encode()
NOTE_BODIES = {TWIN: TWIN_BODY, 11: b"Independently substantive child.\r\n"}
HUB_PATH = "Notes/Twin — 11111111.md"
TWIN_PATH = "Notes/Twin — 22222222.md"
LISTING = "Uncreated targets.md"
KINDS = {7: 4}


def paired_source(path):
    source = graph_archive(
        path,
        TITLES | {10: "System"},
        (*EDGES, (10, 9, 1, 6, -1)),
        kinds=KINDS | {10: 5},
        notes={owner: (body, 4) for owner, body in NOTE_BODIES.items()},
    )
    api = TypeTagApi(edges=EDGES, type_fields={})
    api.thoughts = {
        HOME if number == 1 else identity(number): thought(
            HOME if number == 1 else identity(number), title
        )
        | {"kind": KINDS.get(number, 1)}
        for number, title in TITLES.items()
    }
    api.types = []
    api.tags = [api.thoughts[identity(7)]]
    api.search = [
        {
            "brainId": BRAIN,
            "isFromOtherBrain": False,
            "sourceThought": {"id": key, "brainId": BRAIN, "kind": 0},
            "sourceLink": None,
        }
        for key in api.thoughts
    ]
    api.attachments, api.payloads = {}, {}
    for index, (owner, body) in enumerate(NOTE_BODIES.items(), 900):
        note = identity(index)
        api.attachments[note] = attachment(
            note, identity(owner), 1, "Notes.md", is_notes=True, length=len(body)
        )
        api.payloads[note] = body
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    return source, api


@pytest.fixture(scope="module")
def paired_generations(tmp_path_factory):
    root = tmp_path_factory.mktemp("n9")
    source, api = paired_source(root / "brain.brz")
    brz8, brz9, api8, api9 = (root / name for name in ("b8", "b9", "a8", "a9"))
    brz = default_workflow()
    brz_inspection = brz.inspect(source)
    verified(brz.convert(source, brz9))
    verified(format8_workflow().convert(source, brz8))
    qualification = scope_baseline(root / "direction-controls")
    with api_server(api) as (_, upstream):
        ref = LocalApiSourceRef(BRAIN)
        workflow = local_api_workflow(
            LocalApiConfig(api_url=upstream), credentials=lambda: "KEY"
        )
        api_inspection = workflow.inspect(ref)
        verified(format8_workflow(workflow).convert(ref, api8))
        with ApiRecording(
            root / "recording",
            upstream,
            brain_id=BRAIN,
            credential="KEY",
            purpose="convert",
        ) as recording:
            workflow = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: "KEY"
            )
            verified(workflow.convert(ref, api9))
            recording.complete()
        baseline = recording.seal(qualification=qualification)
    return {
        "brz": (source, brz_inspection, brz8, brz9),
        "api": (baseline, api_inspection, api8, api9),
    }


def verified(result):
    assert result.receipt is not None and result.receipt.verified, result.issues
    assert result.counts.actual_notes == result.counts.planned_notes
    assert result.counts.actual_support_files == result.counts.planned_support_files


def audit(adapter, source, vault):
    if adapter == "brz":
        return check_vault(source, vault)
    return check_api_vault(source, vault, profile_version="5")


def test_reviewed_conversion_refuses_an_inspection_from_the_prior_generation(tmp_path):
    source = graph_archive(
        tmp_path / "source.brz", {1: "Entry", 2: "Leaf"}, ((1, 2, 1, 1, -1),)
    )
    reviewed = Operations(workflow=format8_workflow()).inspect(source).reviewed
    assert reviewed is not None and reviewed.output_format == 8
    result = Operations().convert_reviewed(source, tmp_path, "new", reviewed)
    assert result.review_required
    assert {finding.code for finding in result.findings} == {"review_changed"}
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_source_bound_conversion_and_audit_challenges(
    paired_generations, adapter, tmp_path
):
    source, inspection, prior, vault = paired_generations[adapter]
    assert audit(adapter, source, vault)
    # The independent capture binds the same profile and snapshot in both outputs.
    assert audit(adapter, source, prior)
    old_record, record = (
        json.loads((folder / "migration-record.json").read_bytes())
        for folder in (prior, vault)
    )
    assert (old_record["schema_version"], record["schema_version"]) == (8, 9)
    assert inspection.inspection.output_format == 9
    planned = {
        t.original_identity: (t.relative_path, t.created, list(t.creation_reasons))
        for t in inspection.inspection.item_targets
    }
    targets = {
        row["original_identity"]: (
            row["relative_path"],
            row["created"],
            row["creation_reasons"],
        )
        for row in record["item_targets"]
    }
    assert planned == targets
    assert old_record["counts"]["planned_notes"] == 3
    assert inspection.counts.planned_notes == record["counts"]["planned_notes"] == 8
    assert (
        record["source_identity"]["snapshot_digest"]
        == old_record["source_identity"]["snapshot_digest"]
    )
    assert {key: row[0] for key, row in targets.items()} == {
        row["original_identity"]: row["relative_path"]
        for row in old_record["item_targets"]
    }
    assert targets[identity(HUB)] == (HUB_PATH, True, ["navigation"])
    assert targets[identity(TWIN)] == (TWIN_PATH, True, ["content"])
    assert targets[identity(7)] == ("Notes/Topic.md", True, ["navigation"])
    home = identity(1) if adapter == "brz" else HOME
    assert {
        row["original_identity"] for row in old_record["item_targets"] if row["created"]
    } == {home, identity(TWIN), identity(11)}
    assert {key for key, (_, created, _) in targets.items() if created} == {
        home,
        *(identity(number) for number in (HUB, TWIN, 4, 5, 6, 7, 11)),
    }
    assert not (prior / HUB_PATH).exists()
    assert (vault / HUB_PATH).is_file()
    assert (
        "## Children\n\n- [[Notes/Child.md|Child]]\n- [[Notes/Twin — 22222222.md|Twin]]\n"
        in (vault / HUB_PATH).read_text(encoding="utf-8")
    )
    assert "[[Notes/Twin — 11111111.md|Authored twin]]" in (
        vault / TWIN_PATH
    ).read_text(encoding="utf-8")
    assert {
        row["item_key"]: row["native"] for row in old_record["tag_memberships"]
    } == {identity(4): False, identity(8): False}
    assert {row["item_key"]: row["native"] for row in record["tag_memberships"]} == {
        identity(4): True,
        identity(8): False,
    }
    assert (vault / LISTING).read_bytes() == (
        b"# Uncreated targets\n\n## Isolated thoughts\n\n"
        b"- [[Notes/Isolated.md|Isolated]]\n"
    )

    def challenge(name, action, expected):
        altered = tmp_path / name
        shutil.copytree(vault, altered)
        action(altered)
        with pytest.raises(AssertionError, match=expected):
            audit(adapter, source, altered)

    challenge(
        "missing",
        lambda altered: (altered / HUB_PATH).unlink(),
        "created/uncreated file|required materialized imported note",
    )

    def wrong_destination(altered):
        home = altered / "Home — Entry.md"
        raw = home.read_bytes()
        original = f"[[{HUB_PATH}|Twin]]".encode()
        assert raw.count(original) == 1
        home.write_bytes(raw.replace(original, f"[[{TWIN_PATH}|Twin]]".encode()))

    challenge(
        "wrong",
        wrong_destination,
        "navigation destination|complete note/body/graph/tag bytes",
    )

    def obsolete_fallback(altered):
        path = altered / LISTING
        assert b"## Related pairs" not in path.read_bytes()
        with path.open("ab") as stream:
            stream.write(
                b"\n## Related pairs\n\n"
                + "- [[Notes/Jump A.md|Jump A]] — [[Notes/Jump B.md|Jump B]]\n".encode()
            )

    challenge("fallback", obsolete_fallback, "[Uu]ncreated listing|conditional support")
