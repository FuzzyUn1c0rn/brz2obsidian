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


FAMILY_REFERENCES = (
    ("PNG", ".data/md-images/generic.png", "generic.png", False),
    ("JPG", ".data/md-images/sub/photo.JPG", "sub/photo.JPG", True),
    (
        "JPEG",
        ".data/md-images/sub/deep/photo.jpeg#$width=70p$",
        "sub/deep/photo.jpeg",
        False,
    ),
    (
        "WEBP",
        ".data/md-images/00000000-0000-0000-0000-000000000000.WEBP",
        "00000000-0000-0000-0000-000000000000.WEBP",
        False,
    ),
    ("GIF", ".data/md-images/animated.GIF", "animated.GIF", False),
    (
        "BMP",
        ".data/md-images/space%20folder/bitmap.bmp",
        "space folder/bitmap.bmp",
        False,
    ),
    ("AVIF", ".data/md-images/sub/still.avif", "sub/still.avif", True),
    ("", ".data/md-images/sub/vector.svg", "sub/vector.svg", True),
)
FAMILY_RAW = (
    "Café before.\r\n"
    + "\r\n".join(
        "![" + label + "](" + ("<" + uri + ">" if angle else uri) + ")"
        for label, uri, _location, angle in FAMILY_REFERENCES
    )
    + "\r\nAfter *kept*.\r\n"
).encode()
FAMILY_BODY = (
    "Café before.\n"
    "Image unavailable: PNG\n"
    "Image unavailable: JPG\n"
    "Image unavailable: JPEG\n"
    "Image unavailable: WEBP\n"
    "Image unavailable: GIF\n"
    "Image unavailable: BMP\n"
    "Image unavailable: AVIF\n"
    "Image unavailable: vector&#46;svg\n"
    "After *kept*.\n"
)


@pytest.fixture(scope="module")
def family_outputs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("image-reference-families")
    source = literal_archive(directory / "source.brz", FAMILY_RAW)
    brz_vault = directory / "brz-vault"
    brz_result = default_workflow().convert(source, brz_vault)
    assert brz_result.outcome == "warnings", brz_result.issues
    api = note_api(b"\xef\xbb\xbf" + FAMILY_RAW)
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
            result = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
            ).convert(LocalApiSourceRef(BRAIN), api_vault)
            assert result.outcome == "warnings", result.issues
            recording.complete()
        baseline = recording.seal(qualification=controls)
    paths = [path for path, _query, _key in api.requests]
    return source, brz_vault, baseline, api_vault, paths


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_complete_missing_reference_families_keep_nested_and_angle_source_evidence(
    family_outputs, adapter
):
    source, brz_vault, baseline, api_vault, requests = family_outputs
    vault = brz_vault if adapter == "brz" else api_vault
    audit(adapter, source, baseline, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    document = next(d for t in record["item_targets"] for d in t["documents"])
    body = (vault / document["owner_target"]).read_text(encoding="utf-8")
    assert FAMILY_BODY in body
    assert len(record["asset_targets"]) == 1
    assert record["asset_targets"][0]["role"] == "note_original"
    assert record["counts"]["source_references"] == 0
    expected_original = FAMILY_RAW if adapter == "brz" else b"\xef\xbb\xbf" + FAMILY_RAW
    assert next(vault.rglob("*.original")).read_bytes() == expected_original
    observations = sorted(
        (
            json.loads(issue["message"].split("Observed: ", 1)[1])
            for issue in record["issues"]
            if issue["rule_id"] == "thebrain.unavailable-image.v1"
        ),
        key=lambda value: value["source_reference"]["start"],
    )
    assert len(observations) == 8
    source_text = expected_original.decode("utf-8")
    for observed, (label, uri, location, angle) in zip(
        observations, FAMILY_REFERENCES, strict=True
    ):
        span = observed["source_reference"]
        authored_destination = "<" + uri + ">" if angle else uri
        phrase = "![" + label + "](" + authored_destination + ")"
        assert source_text[span["start"] : span["end"]] == phrase
        assert (
            source_text[span["destination_start"] : span["destination_end"]]
            == authored_destination
        )
        assert span["uri"] == uri and observed["absence"]["location"] == location
        expected_notice = (
            "Image unavailable: " + label
            if label
            else "Image unavailable: vector&#46;svg"
        )
        assert observed["notice"]["text"] == expected_notice
    if adapter == "api":
        from tests.support.local_api_payloads import NOTE

        content = [path for path in requests if path.endswith("/file-content")]
        assert set(content) == {f"/api/attachments/{BRAIN}/{NOTE}/file-content"}


@pytest.mark.parametrize(
    "uri",
    (
        "foo.png",
        "/.data/md-images/foo.png",
        ".data/md-images/../lost.png",
        ".data/md-images//lost.png",
        ".data/md-images/sub//lost.png",
        ".data/md-images/sub%2flost.png",
        ".data/md-images/sub%5clost.png",
        ".data/md-images/sub%252flost.png",
        ".data/md-images/bad%GG.png",
        ".data/md-images/bad%00.png",
        ".data/md-images/bad%1f.png",
        ".data/md-images/bad:name.png",
        ".data/md-images/bad%3Aname.png",
    ),
)
def test_independent_image_path_predicate_retains_exact_local_safety(uri):
    from tests.local_acceptance.unavailable_images import image_location

    with pytest.raises(AssertionError):
        image_location(uri)


def test_independent_api_audit_rejects_recorded_wrong_declared_image_suffix(tmp_path):
    from tests.local_acceptance.api_checker import audit_baseline

    api = note_api(f"![Declared](.data/md-images/{IMAGE}.jpeg)\n".encode())
    api.attachments[IMAGE] = attachment(
        IMAGE, HOME, 12, IMAGE + ".jpeg", length=len(PNG)
    )
    api.payloads[IMAGE] = PNG
    api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
    controls = prepare_controls(tmp_path / "controls")
    with api_server(api) as (_, upstream):
        recording = ApiRecording(
            tmp_path / "http",
            upstream,
            brain_id=BRAIN,
            credential=KEY,
            purpose="inspect",
        )
        with recording:
            result = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
            ).inspect(LocalApiSourceRef(BRAIN))
            assert result.outcome == "refused", result.issues
            recording.complete()
        baseline = recording.seal(qualification=controls)
    with pytest.raises(AssertionError, match="raw image role"):
        audit_baseline(baseline, profile_version="4")


@pytest.mark.parametrize("stem", (IMAGE, IMAGE.upper(), IMAGE.replace("-", "")))
def test_independent_nested_image_refuses_identified_foreign_asset(stem):
    from tests.local_acceptance.unavailable_images import expectation

    raw = "![Foreign](.data/md-images/sub/" + stem + ".png)"
    foreign = {
        IMAGE: {
            "asset_id": IMAGE,
            "owner": "33333333-3333-4333-8333-333333333333",
            "role": "image",
            "original_name": IMAGE + ".png",
            "availability": "present",
        }
    }
    with pytest.raises(AssertionError, match="foreign identity"):
        expectation(raw, HOME, foreign, {}, basis="archive_undeclared_no_payload")


DECODED_REFERENCES = (
    ("Plain", ".data/md-images/lost.png", ".data/md-images/lost.png", False),
    ("Entity", ".data/md-images/lost&#46;png", ".data/md-images/lost.png", False),
    ("Escape", r".data/md-images/lost\.png", ".data/md-images/lost.png", False),
    (
        "Entity prefix",
        "&#46;data/md-images/lost.png",
        ".data/md-images/lost.png",
        False,
    ),
    ("Escape prefix", r"\.data/md-images/lost.png", ".data/md-images/lost.png", False),
    ("Unicode", ".data/md-images/café.png", ".data/md-images/caf%C3%A9.png", True),
    (
        "Space",
        ".data/md-images/lost image.png",
        ".data/md-images/lost%20image.png",
        True,
    ),
)
DECODED_RAW = (
    "Before.\r\n"
    + "\r\n".join(
        "![" + label + "](" + ("<" + authored + ">" if angle else authored) + ")"
        for label, authored, _semantic, angle in DECODED_REFERENCES
    )
    + f"\r\n![Present plain](.data/md-images/{IMAGE}.png)\r\n"
    + f"![Present entity](.data/md-images/{IMAGE}&#46;png#$width=70p$)\r\n"
    + f"![Present escape](.data/md-images/{IMAGE}\\.png)\r\nAfter.\r\n"
).encode()


@pytest.fixture(scope="module")
def decoded_destination_outputs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("decoded-image-destinations")
    source = literal_archive(
        directory / "source.brz",
        DECODED_RAW,
        resources=(({"Type": 12, "Location": IMAGE + ".png"}, PNG),),
    )
    brz_vault = directory / "brz-vault"
    brz_result = default_workflow().convert(source, brz_vault)
    assert brz_result.outcome == "warnings", brz_result.issues
    api = note_api(b"\xef\xbb\xbf" + DECODED_RAW)
    api.attachments[IMAGE] = attachment(
        IMAGE, HOME, 12, IMAGE + ".png", length=len(PNG)
    )
    api.payloads[IMAGE] = PNG
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
            result = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
            ).convert(LocalApiSourceRef(BRAIN), api_vault)
            assert result.outcome == "warnings", result.issues
            recording.complete()
        baseline = recording.seal(qualification=controls)
    return source, brz_vault, baseline, api_vault


@pytest.mark.parametrize("adapter", ("brz", "api"))
def test_complete_image_destinations_unescape_once_and_keep_raw_evidence(
    decoded_destination_outputs, adapter
):
    source, brz_vault, baseline, api_vault = decoded_destination_outputs
    vault = brz_vault if adapter == "brz" else api_vault
    audit(adapter, source, baseline, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    document = next(d for t in record["item_targets"] for d in t["documents"])
    body = (vault / document["owner_target"]).read_text(encoding="utf-8")
    assert (
        "Before.\nImage unavailable: Plain\nImage unavailable: Entity\n"
        "Image unavailable: Escape\nImage unavailable: Entity prefix\n"
        "Image unavailable: Escape prefix\nImage unavailable: Unicode\n"
        "Image unavailable: Space\n" in body
    )
    assert len(record["asset_targets"]) == 2
    image = next(a for a in record["asset_targets"] if a["role"] == "image")
    assert image["availability"] == "present"
    assert (vault / image["relative_path"]).read_bytes() == PNG
    for label in ("Present plain", "Present entity", "Present escape"):
        assert "![" + label + "](" + image["relative_path"] + ")" in body
    assert record["counts"]["source_references"] == 3
    raw = DECODED_RAW if adapter == "brz" else b"\xef\xbb\xbf" + DECODED_RAW
    assert next(vault.rglob("*.original")).read_bytes() == raw
    raw_text = raw.decode()
    observations = sorted(
        (
            json.loads(i["message"].split("Observed: ", 1)[1])
            for i in record["issues"]
            if i["rule_id"] == "thebrain.unavailable-image.v1"
        ),
        key=lambda value: value["source_reference"]["start"],
    )
    assert len(observations) == len(DECODED_REFERENCES)
    for observed, (label, authored, semantic, angle) in zip(
        observations, DECODED_REFERENCES, strict=True
    ):
        ref = observed["source_reference"]
        destination = "<" + authored + ">" if angle else authored
        phrase = "![" + label + "](" + destination + ")"
        assert raw_text[ref["start"] : ref["end"]] == phrase
        assert (
            raw_text[ref["destination_start"] : ref["destination_end"]] == destination
        )
        assert ref["uri"] == semantic
    assert {r["source_target"] for r in document["references"]} == {
        ".data/md-images/" + IMAGE + ".png",
        ".data/md-images/" + IMAGE + ".png#$width=70p$",
    }
    sized = next(r for r in document["references"] if r["presentation_normalization"])
    normalization = sized["presentation_normalization"]
    assert normalization["declaration"] == "#$width=70p$"
    assert normalization["start"] - sized["destination_start"] == len(
        ".data/md-images/" + IMAGE + "&#46;png"
    )
    assert record["counts"]["image_presentation_normalizations"] == 1


@pytest.mark.parametrize(
    "authored,once",
    (
        (r".data/md-images/lost\\.png", r".data/md-images/lost\.png"),
        (".data/md-images/lost&amp;#46;png", ".data/md-images/lost&#46;png"),
        (r".data/md-images/lost\&#46;png", ".data/md-images/lost&#46;png"),
        (".data/md-images/lost%26%2346%3Bpng", ".data/md-images/lost%26%2346%3Bpng"),
        (".data/md-images/sub&#37;2flost.png", ".data/md-images/sub%2flost.png"),
        (".data/md-images/lost%252epng", ".data/md-images/lost%252epng"),
        (
            ".data/md-images/lost.png&#35;$width=70p$",
            ".data/md-images/lost.png#$width=70p$",
        ),
        (
            r".data/md-images/lost.png#\$width=70p$",
            ".data/md-images/lost.png#$width=70p$",
        ),
        (
            r".data/md-images/lost.png#$width\=70p$",
            ".data/md-images/lost.png#$width=70p$",
        ),
        (
            ".data/md-images/lost.png#$width&#61;70p$",
            ".data/md-images/lost.png#$width=70p$",
        ),
        (".data/md-images/lost.png?query=1", ".data/md-images/lost.png?query=1"),
    ),
)
def test_image_destination_one_pass_does_not_relax_source_safety(authored, once):
    from tests.local_acceptance.note_links import markdown_destination
    from tests.local_acceptance.unavailable_images import expectation

    assert markdown_destination(authored) == once
    with pytest.raises(AssertionError):
        expectation(
            "![Lost](" + authored + ")",
            HOME,
            {},
            {},
            basis="archive_undeclared_no_payload",
        )


@pytest.mark.parametrize("adapter", ("brz", "api"))
@pytest.mark.parametrize("damage", ("semantic-uri", "authored-span"))
def test_decoded_image_audit_rejects_coherent_raw_semantic_evidence_forgery(
    decoded_destination_outputs, tmp_path, adapter, damage
):
    from tests.local_acceptance.unavailable_images import observation_json

    source, brz_vault, baseline, api_vault = decoded_destination_outputs
    vault = tmp_path / "forged"
    shutil.copytree(brz_vault if adapter == "brz" else api_vault, vault)
    record = json.loads((vault / "migration-record.json").read_bytes())
    issue = next(i for i in record["issues"] if "![Entity]" in i["message"])
    before = json.loads(issue["message"].split("Observed: ", 1)[1])
    forged = deepcopy(before)
    if damage == "semantic-uri":
        forged["source_reference"]["uri"] = ".data/md-images/lost&#46;png"
    else:
        forged["source_reference"]["destination_end"] -= 4
    encoded = observation_json(forged, api=adapter == "api")
    issue["message"] = (
        issue["message"].split("Observed: ", 1)[0] + "Observed: " + encoded
    )
    for asset in record["asset_targets"]:
        for finding in asset["source_findings"]:
            if json.loads(finding["observed_json"]) == before:
                finding["observed_json"] = encoded
    actual = {
        p.relative_to(vault).as_posix(): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }
    result = {"receipt": {}}
    rewrite_record(vault, record, result)
    assert all(
        (vault / name).read_bytes() == data
        for name, data in actual.items()
        if name != "migration-record.json"
    )
    with pytest.raises(AssertionError, match="raw-derived unavailable image"):
        audit(adapter, source, baseline, vault)


def test_complete_bracket_image_destinations_keep_raw_and_encoded_uri(tmp_path):
    authored = (
        "![Escaped](.data/md-images/lost\\[1\\].png)\r\n"
        "![Angled](<.data/md-images/lost[1].png>)\r\n"
        "![Punctuation](.data/md-images/lost\\(1\\)'x'.png)\r\n"
        "![Present](<.data/md-images/kept[1].png>)\r\n"
    )
    source = literal_archive(
        tmp_path / "brackets.brz",
        authored.encode(),
        resources=(({"Type": 12, "Location": "kept[1].png"}, PNG),),
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings", result.issues
    assert check_vault(source, vault)["image_references"] == 1
    body = (vault / "Home — Entry thought.md").read_text(encoding="utf-8")
    assert "![Present](Attachments/22222222/kept%281%29.png)" in body
    assert (
        "Image unavailable: Escaped\nImage unavailable: Angled\n"
        "Image unavailable: Punctuation\n" in body
    )
    record = json.loads((vault / "migration-record.json").read_bytes())
    evidence = sorted(
        (json.loads(i["message"].split("Observed: ", 1)[1]) for i in record["issues"]),
        key=lambda value: value["source_reference"]["start"],
    )
    assert {item["source_reference"]["uri"] for item in evidence} == {
        ".data/md-images/lost%5B1%5D.png",
        ".data/md-images/lost(1)'x'.png",
    }
    assert [
        item["source_reference"]["before"] for item in evidence
    ] == authored.splitlines()[:3]
    assert next(vault.rglob("*.original")).read_bytes() == authored.encode()
