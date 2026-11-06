"""Complete independent output audits and coherent missing-image forgeries."""

import json
import shutil
from copy import deepcopy
from hashlib import sha256

import pytest

from brz2obsidian.application.wiring import default_workflow, local_api_workflow
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef
from tests.application.test_forgotten_workflow import rewrite
from tests.application.test_literal_angles_workflow import literal_archive
from tests.local_acceptance.api_baseline import prepare_controls
from tests.local_acceptance.api_checker import check_api_vault
from tests.local_acceptance.api_recording import ApiRecording
from tests.local_acceptance.checker import check_run_result, check_vault
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.sources.test_local_api_bom import note_api
from tests.support.audit_sources import SCHEMA
from tests.support.local_api import BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import IMAGE, PNG, attachment

CONTROL_IDS = tuple(f"b{i}111111-1111-4111-8111-111111111111" for i in range(4))
MISSING = "![Lost *label*](.data/md-images/lost.png#$width=70p$)"
DECLARED = f"![Declared](.data/md-images/{IMAGE}.png)"
TABLE = (
    f"|{MISSING}|{MISSING}|`![code](.data/md-images/code.png) x|y`|"
    ':(table="column-widths:-1,0,0,0;justification:default"):\r\n|a|b|c|\r\n'
)
RAW = (
    "Café <X/>\r\n\r\n"
    + TABLE
    + "\r\n"
    + DECLARED
    + "\r\n"
    + "\r\n".join(
        f"![Kept {i}](.data/md-images/{key}.png)" for i, key in enumerate(CONTROL_IDS)
    )
    + "\r\nAfter *kept*.\r\n"
).encode()


@pytest.fixture(scope="module")
def unavailable_outputs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("unavailable-audit")
    source = literal_archive(
        directory / "source.brz",
        RAW,
        resources=tuple(
            ({"Type": 12, "Location": key + ".png"}, PNG) for key in CONTROL_IDS
        )
        + (({"Type": 12, "Location": IMAGE + ".png", "DataLength": 17}, None),),
    )

    def absent(parts):
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"]["aaaaaaaa-0000-4000-8000-000000000005"] = 3
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, absent)
    brz_vault = directory / "brz-vault"
    brz_result = default_workflow().convert(source, brz_vault)
    assert brz_result.outcome == "warnings", brz_result.issues
    api_raw = b"\xef\xbb\xbf" + RAW
    api = note_api(api_raw)
    for key in CONTROL_IDS:
        api.attachments[key] = attachment(key, HOME, 12, key + ".png", length=len(PNG))
        api.payloads[key] = PNG
    api.attachments[IMAGE] = attachment(IMAGE, HOME, 12, IMAGE + ".png", length=17)
    api.overrides[f"/api/attachments/{BRAIN}/{IMAGE}/file-content"] = (
        404,
        {"error": "not retained"},
    )
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    controls = prepare_controls(directory / "controls")
    api_vault = directory / "api-vault"
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
            api_result = workflow.convert(LocalApiSourceRef(BRAIN), api_vault)
            assert api_result.outcome == "warnings", api_result.issues
            recording.complete()
        baseline = recording.seal(qualification=controls)
    return source, brz_vault, brz_result, baseline, api_vault, api_result


def audit(adapter, source, baseline, vault):
    if adapter == "brz":
        return check_vault(source, vault)
    return check_api_vault(baseline, vault, profile_version="4")


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_complete_unavailable_output_is_independently_source_bound(
    unavailable_outputs, adapter
):
    source, brz_vault, brz_result, baseline, api_vault, api_result = unavailable_outputs
    vault, result = (
        (brz_vault, brz_result) if adapter == "brz" else (api_vault, api_result)
    )
    summary = audit(adapter, source, baseline, vault)
    if adapter == "brz":
        check_run_result(result.model_dump(mode="json"), vault, summary)
    record = json.loads((vault / "migration-record.json").read_bytes())
    note = next(t for t in record["item_targets"] if t["documents"])
    body = (vault / note["relative_path"]).read_text(encoding="utf-8")
    assert (
        "|Image unavailable: Lost label|Image unavailable: Lost label|"
        "<code>![code](.data/md-images/code.png) x&#124;y</code>|" in body
    )
    assert "Image unavailable: Declared" in body
    assert "Café \\<X/>" in body and "After *kept*." in body
    assert body.count("Image unavailable:") == 3
    expected = RAW if adapter == "brz" else b"\xef\xbb\xbf" + RAW
    assert next(vault.rglob("*.original")).read_bytes() == expected
    assert (
        sum(
            a["role"] == "image" and a["availability"] == "present"
            for a in record["asset_targets"]
        )
        == 4
    )
    assert (
        sum(
            a["role"] == "image" and a["availability"] == "absent"
            for a in record["asset_targets"]
        )
        == 1
    )


@pytest.mark.parametrize("adapter", ("brz", "api"))
@pytest.mark.parametrize(
    "damage",
    (
        "notice",
        "source-span",
        "final-span",
        "absence",
        "present",
        "byte",
        "role",
        "composition-code",
        "occurrence-swap",
        "missing",
        "report",
    ),
)
def test_complete_unavailable_audit_refuses_coherently_rehashed_forgery(
    unavailable_outputs, tmp_path, adapter, damage
):
    source, brz_vault, brz_result, baseline, api_vault, api_result = unavailable_outputs
    original, result = (
        (brz_vault, brz_result) if adapter == "brz" else (api_vault, api_result)
    )
    vault = tmp_path / "forged"
    shutil.copytree(original, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    identity = deepcopy(record["source_identity"])
    warning = next(
        i for i in record["issues"] if i["rule_id"] == "thebrain.unavailable-image.v1"
    )
    observed = json.loads(warning["message"].split("Observed: ", 1)[1])
    document = next(d for t in record["item_targets"] for d in t["documents"])
    changed_observation = False
    if damage == "report":
        report = vault / "MIGRATION REPORT.md"
        lines = report.read_text(encoding="utf-8").splitlines(keepends=True)
        index = next(
            i for i, line in enumerate(lines) if "thebrain.unavailable-image.v1" in line
        )
        del lines[index]
        report.write_text("".join(lines), encoding="utf-8")
    elif damage == "missing":
        asset = next(
            a
            for a in record["asset_targets"]
            if a["role"] == "image" and a["availability"] == "absent"
        )
        path = "Attachments/phantom.png"
        (vault / path).write_bytes(b"")
        asset.update(
            availability="present",
            actual_length=0,
            actual_sha256=sha256(b"").hexdigest(),
            relative_path=path,
        )
    elif damage == "occurrence-swap":
        other = next(
            i
            for i in record["issues"]
            if i["rule_id"] == warning["rule_id"] and i is not warning
        )
        replacement = json.loads(other["message"].split("Observed: ", 1)[1])
        observed.update(
            {
                k: replacement[k]
                for k in ("source_reference", "intermediate_reference", "notice")
            }
        )
        changed_observation = True
    elif damage == "notice":
        path = vault / document["owner_target"]
        path.write_bytes(
            path.read_bytes().replace(
                b"Image unavailable: Lost label", b"Image recovered: Lost label", 1
            )
        )
    elif damage in {"source-span", "final-span", "absence", "composition-code"}:
        if damage == "source-span":
            observed["source_reference"]["start"] += 1
        elif damage == "final-span":
            observed["notice"]["end"] += 1
        elif damage == "absence":
            observed["absence"]["basis"] = "api_declared_content404"
        else:
            observed["composition"]["base_edits"][0]["kind"] = "literal_text"
        changed_observation = True
    else:
        asset = next(
            a
            for a in record["asset_targets"]
            if a["role"] == "image" and a["availability"] == "present"
        )
        if damage == "byte":
            path = vault / asset["relative_path"]
            data = path.read_bytes() + b"!"
            path.write_bytes(data)
            asset.update(
                actual_length=len(data), actual_sha256=sha256(data).hexdigest()
            )
        elif damage == "role":
            asset["role"] = "file"
        else:
            asset.update(
                availability="absent",
                actual_length=None,
                actual_sha256=None,
                relative_path=None,
            )
    if changed_observation:
        warning["message"] = (
            warning["message"].split("Observed: ", 1)[0]
            + "Observed: "
            + json.dumps(
                observed, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        )
    forged = result.model_dump(mode="json")
    forged["receipt"]["destination"] = str(vault.resolve())
    rewrite_record(vault, record, forged)
    assert record["source_identity"] == identity
    with pytest.raises(AssertionError):
        audit(adapter, source, baseline, vault)
    baseline.verify()


@pytest.mark.parametrize("profile", ("1", "2", "3"))
def test_old_api_profiles_refuse_image404_and_new_acquisition_outcome(
    unavailable_outputs, profile
):
    from tests.local_acceptance.api_checker import expected_asset
    from tests.local_acceptance.api_generated import check_acquisition_protocol

    _, _, _, baseline, vault, _ = unavailable_outputs
    declared = baseline.json(baseline.data["attachment_metadata"][IMAGE]["path"])
    with pytest.raises(
        AssertionError, match="unqualified missing payload|raw image role"
    ):
        expected_asset(baseline, declared, profile)
    record = json.loads((vault / "migration-record.json").read_bytes())
    acquisition = record["run_metadata"]["source_acquisition"]
    check_acquisition_protocol(acquisition, BRAIN, profile_version="4")
    with pytest.raises(AssertionError, match="acquisition HTTP/outcome protocol"):
        check_acquisition_protocol(acquisition, BRAIN, profile_version=profile)


def test_notice_oracle_uses_inert_known_answer_and_keeps_foreign_basename_local(
    tmp_path,
):
    from brz2obsidian.sources.thebrain import BrzSourceModule
    from tests.local_acceptance.unavailable_images import expectation

    raw = "Before ![a_b &lt;X&gt; `p|q` café—](.data/md-images/lost.png) after.\r\n"
    wanted = "Before Image unavailable: a&#95;b &#60;X&#62; p&#124;q café— after.\r\n"
    source = literal_archive(tmp_path / "label.brz", raw.encode())
    with BrzSourceModule().open(source) as session:
        assert session.snapshot.documents[0].text == wanted
    foreign = {
        "foreign": {
            "asset_id": "foreign",
            "owner": "another-owner",
            "role": "image",
            "original_name": "lost.png",
            "availability": "present",
        }
    }
    assert (
        expectation(raw, HOME, foreign, {}, basis="archive_undeclared_no_payload")[0]
        == wanted
    )
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "warnings"
    assert check_vault(source, vault)["image_references"] == 0


def test_raw_api_audit_refuses_rehashed_acquisition_image_subject(
    unavailable_outputs, tmp_path
):
    _, _, _, baseline, original, result = unavailable_outputs
    vault = tmp_path / "forged"
    shutil.copytree(original, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    request = next(
        r
        for r in record["run_metadata"]["source_acquisition"]["audit"]["requests"]
        if r["outcome"] == "missing_image_404"
    )
    request["subject_id"] = CONTROL_IDS[0]
    result = result.model_dump(mode="json")
    result["receipt"]["destination"] = str(vault.resolve())
    rewrite_record(vault, record, result)
    with pytest.raises(AssertionError, match="raw image acquisition"):
        check_api_vault(baseline, vault, profile_version="4")


def test_heading_callout_copies_keep_source_and_final_occurrences(tmp_path):
    from tests.local_acceptance.unavailable_images import expectation

    phrase = "![Lost <X/>](.data/md-images/lost.png)"
    raw = (
        "[/toc/]\n\n# " + phrase + "\n\n"
        "> [!tip|icon:😂] " + phrase + "\n> Body\n"
        "\nAuthored Image unavailable: Lost.\n"
    )
    source = literal_archive(tmp_path / "headings.brz", raw.encode())
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings", result.issues
    assert check_vault(source, vault)["image_references"] == 0
    body = (vault / "Home — Entry thought.md").read_text(encoding="utf-8")
    assert "# Image unavailable: Lost &#60;X&#47;&#62; ^brz-toc-heading-1" in body
    assert "> [!tip] 😂 Image unavailable: Lost &#60;X&#47;&#62;" in body
    assert "Authored Image unavailable: Lost." in body
    final, _, events = expectation(
        raw, HOME, {}, {}, basis="archive_undeclared_no_payload"
    )
    assert len(events) == 2
    assert [e["source_reference"]["start"] for e in events] == [
        raw.index(phrase),
        raw.rindex(phrase),
    ]
    for event in events:
        notice = event["notice"]
        assert (
            final[notice["start"] : notice["end"]]
            == "Image unavailable: Lost &#60;X&#47;&#62;"
        )


def test_independent_notice_proof_refuses_disconnected_flat_edit_union():
    from tests.local_acceptance.unavailable_images import digest, expectation, validate

    raw = "![A](.data/md-images/a.png) gap ![B](.data/md-images/b.png)"
    final, intermediate, events = expectation(
        raw, HOME, {}, {}, basis="archive_undeclared_no_payload"
    )
    assert final == "Image unavailable: A gap Image unavailable: B"
    forged_edit = {
        "kind": "image_unavailable",
        "start": 0,
        "end": len(raw),
        "before": raw,
        "after": final,
        "adapted_start": 0,
        "adapted_end": len(final),
        "source_digest": digest(raw),
        "source_basis": "scoped_source_text/unicode_codepoints",
        "adapted_basis": "document.text/unicode_codepoints",
    }
    observed = [
        event | {"document": "note", "composition": {"flat_edit": 0, "base_edits": []}}
        for event in events
    ]
    with pytest.raises(AssertionError, match="connected source union"):
        validate(raw, final, intermediate, [forged_edit], events, observed)
