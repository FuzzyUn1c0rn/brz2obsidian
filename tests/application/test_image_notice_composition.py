"""Public composition of unavailable-image notices and separate table edits."""

import json
import shutil
from copy import deepcopy
from hashlib import sha256

import pytest

from brz2obsidian.application.wiring import default_workflow, local_api_workflow
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.core import analyze
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.local_api import (
    LOCAL_API_POLICY_V5,
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_forgotten_workflow import rewrite
from tests.application.test_literal_angles_workflow import literal_archive
from tests.local_acceptance.api_baseline import prepare_controls
from tests.local_acceptance.api_checker import check_api_vault
from tests.local_acceptance.api_recording import ApiRecording
from tests.local_acceptance.checker import check_vault
from tests.local_acceptance.test_checker_v2 import rewrite_record
from tests.sources.test_local_api_bom import note_api
from tests.support.audit_sources import SCHEMA
from tests.support.local_api import BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import IMAGE, NOTE, PNG, attachment

DOCUMENT = "01111111-1111-4111-8111-111111111111"
LINK = "[Target](brain://IiIiIiIiIkKCIiIiIiIiIg/Home)"
MISSING = "![Lost](.data/md-images/lost.png)"
NOTICE = "Image unavailable: Lost"
NATIVE_HEADER = "| | |\n|---|---|"
IMAGE_HEADER = '|||:(table="opaque:origin"):'
IMPORTED_HEADER = '||:(table="opaque:imported"):'
IMPORTED_ROW = "|one{nl}two|value|"
IMPORTED_NATIVE = "|one<br>two|value|"
RAGGED_HEADER = '|A|B|:(table="opaque:ragged"):'
RAGGED_ROWS = "\n|---|---|\n|" + LINK + "|\n"
CASES = (
    "imported-after",
    "ragged-after",
    "imported-before",
    "ragged-before",
    "both-no-image",
    "both-present-image",
)


def known_case(name):
    """Literal source and expected replacements, without any producer parser."""
    missing = "no-image" not in name and "present-image" not in name
    image = (
        "kept"
        if "no-image" in name
        else f"![Lost](.data/md-images/{IMAGE}.png)"
        if "present-image" in name
        else MISSING
    )
    row = "|" + image + "|`x|y`|"
    base_row = "|" + image + "|<code>x&#124;y</code>|"
    final_row = "|" + (NOTICE if missing else image) + "|<code>x&#124;y</code>|"
    image_source = IMAGE_HEADER + "\n" + row + "\n"
    image_base = NATIVE_HEADER + "\n" + base_row + "\n"
    image_final = NATIVE_HEADER + "\n" + final_row + "\n"
    imported = IMPORTED_HEADER + "\n" + IMPORTED_ROW + "\n"
    imported_native = NATIVE_HEADER + "\n" + IMPORTED_NATIVE + "\n"
    ragged = RAGGED_HEADER + RAGGED_ROWS
    ragged_native = "|A|B|" + RAGGED_ROWS
    table = imported if name.startswith("imported") else ragged
    table_native = imported_native if name.startswith("imported") else ragged_native
    if name.startswith("both"):
        table, table_native = (
            imported + "\n" + ragged,
            imported_native + "\n" + ragged_native,
        )
    before = name.endswith("before")
    source = table + "\n" + image_source if before else image_source + "\n" + table
    intermediate = (
        table_native + "\n" + image_base if before else image_base + "\n" + table_native
    )
    final = (
        table_native + "\n" + image_final
        if before
        else image_final + "\n" + table_native
    )
    tail = "\nAfter. " + LINK + "\n"
    source, intermediate, final = source + tail, intermediate + tail, final + tail
    changes = [(IMAGE_HEADER, NATIVE_HEADER), (row, final_row)]
    if name.startswith(("imported", "both")):
        changes += [(IMPORTED_HEADER, NATIVE_HEADER), (IMPORTED_ROW, IMPORTED_NATIVE)]
    if name.startswith(("ragged", "both")):
        changes += [(RAGGED_HEADER, "|A|B|")]
    edits, delta = [], 0
    for old, new in sorted(changes, key=lambda pair: source.index(pair[0])):
        start = source.index(old)
        edits.append(
            (
                "markdown_insert_image_unavailable"
                if missing and old == row
                else "markdown_insert",
                start,
                start + len(old),
                old,
                new,
                start + delta,
                start + delta + len(new),
            )
        )
        delta += len(new) - len(old)
    item_contexts = []
    if name.startswith(("ragged", "both")):
        start = final.index(LINK)
        item_contexts.append((start, start + len(LINK), True))
    start = final.rindex(LINK)
    item_contexts.append((start, start + len(LINK), False))
    return {
        "source": source,
        "intermediate": intermediate,
        "final": final,
        "edits": edits,
        "missing": missing,
        "row": row,
        "base_row": base_row,
        "item_contexts": item_contexts,
    }


@pytest.fixture(scope="module")
def composition_api_controls(tmp_path_factory):
    return prepare_controls(
        tmp_path_factory.mktemp("composition-controls") / "controls"
    )


def forged_output(vault, destination, result, facts, damage):
    """Rebind output claims consistently while keeping raw source authoritative."""
    shutil.copytree(vault, destination)
    record = json.loads((destination / "migration-record.json").read_bytes())
    document = next(d for row in record["item_targets"] for d in row["documents"])
    edits = document["text_adaptations"]
    later = next(
        i
        for i, e in enumerate(edits)
        if e["start"] > facts["source"].index(facts["row"])
    )
    image = next(e for e in edits if e["kind"] == "markdown_insert_image_unavailable")
    finding = next(
        f
        for a in record["asset_targets"]
        for f in a["source_findings"]
        if f["kind"] == "unavailable_image_reference"
    )
    observed = json.loads(finding["observed_json"])
    if damage == "later-text":
        edits[later]["after"] = (
            edits[later]["after"].replace("---", "===")
            if "---" in edits[later]["after"]
            else "|A|C|"
        )
    elif damage == "later-missing":
        edits.pop(later)
    elif damage == "later-swapped":
        edits[0]["after"], edits[later]["after"] = (
            edits[later]["after"],
            edits[0]["after"],
        )
    else:
        image["kind"] = "image_unavailable"
        observed["composition"]["base_edits"][0]["kind"] = "literal_text"

    def rebind(values):
        delta = 0
        for edit in values:
            edit["adapted_start"] = edit["start"] + delta
            edit["adapted_end"] = edit["adapted_start"] + len(edit["after"])
            delta += len(edit["after"]) - len(edit["before"])
        body = facts["source"]
        for edit in reversed(values):
            body = body[: edit["start"]] + edit["after"] + body[edit["end"] :]
        return body

    final = rebind(edits)
    base = [deepcopy(e) for e in edits if e is not image] + observed["composition"][
        "base_edits"
    ]
    base.sort(key=lambda e: e["start"])
    middle = rebind(base)
    observed["composition"]["flat_edit"] = edits.index(image)
    for key, body, phrase, digest_key in (
        ("intermediate_reference", middle, MISSING, "document_digest"),
        ("notice", final, NOTICE, "document_digest"),
    ):
        observed[key].update(
            start=body.index(phrase), end=body.index(phrase) + len(phrase)
        )
        observed[key][digest_key] = sha256(body.encode()).hexdigest()
    encoded = json.dumps(observed, sort_keys=True, separators=(",", ":"))
    for asset in record["asset_targets"]:
        for claim in asset["source_findings"]:
            if claim["kind"] == "unavailable_image_reference":
                claim["observed_json"] = encoded
    report = destination / "MIGRATION REPORT.md"
    report_text = report.read_text(encoding="utf-8")
    for warning in record["issues"]:
        if warning["rule_id"] == "thebrain.unavailable-image.v1":
            old = warning["message"]
            warning["message"] = old.split("Observed: ", 1)[0] + "Observed: " + encoded
            report_text = report_text.replace(old, warning["message"])
    report.write_text(report_text, encoding="utf-8")
    document["text_digest"] = sha256(final.encode()).hexdigest()
    cursor = 0
    for reference in document["references"]:
        start = final.index(reference["expected_original"], cursor)
        reference.update(
            start=start,
            end=start + len(reference["expected_original"]),
            document_digest=document["text_digest"],
        )
        cursor = reference["end"]
    template = next(a for a in record["adaptations"] if a.get("text_edit"))
    record["adaptations"] = [a for a in record["adaptations"] if not a.get("text_edit")]
    record["adaptations"] += [
        template
        | {"kind": e["kind"], "affected": f"text:{DOCUMENT}:{i}", "text_edit": e}
        for i, e in enumerate(edits)
    ]
    record["counts"]["text_adaptations"] = len(edits)
    old_rendered, new_rendered = facts["final"], final
    for reference in document["references"]:
        target = (
            "[["
            + document["owner_target"]
            + ("\\|" if reference["table_cell"] else "|")
            + "Target]]"
        )
        old_rendered = old_rendered.replace(LINK, target, 1)
        new_rendered = new_rendered.replace(LINK, target, 1)
    path = destination / document["owner_target"]
    old_note = path.read_text(encoding="utf-8")
    assert old_rendered.rstrip() in old_note
    path.write_text(
        old_note.replace(old_rendered.rstrip(), new_rendered.rstrip(), 1),
        encoding="utf-8",
    )
    forged_result = result.model_dump(mode="json")
    forged_result["receipt"]["destination"] = str(destination.resolve())
    rewrite_record(destination, record, forged_result)
    assert (
        next(destination.rglob("*.original")).read_bytes() == facts["source"].encode()
    )


@pytest.mark.parametrize("adapter", ("brz", "api"))
@pytest.mark.parametrize("case", CASES)
def test_public_image_notice_composes_with_separate_table(
    tmp_path, composition_api_controls, adapter, case
):
    facts = known_case(case)
    raw = facts["source"].encode()
    present = case.endswith("present-image")
    vault = tmp_path / "vault"
    source = literal_archive(
        tmp_path / "source.brz",
        raw,
        resources=(({"Id": IMAGE, "Type": 12, "Location": IMAGE + ".png"}, PNG),)
        if present
        else (),
    )

    def identify(parts):
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        old = rows[0]["Id"]
        rows[0]["Id"] = DOCUMENT
        parts["attachments.json"] = "\n".join(json.dumps(row) for row in rows).encode()
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][DOCUMENT] = meta["AttachmentFileStates"].pop(old)
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, identify)
    source_digest = sha256(source.read_bytes()).hexdigest()
    if adapter == "brz":
        with BrzSourceModule().open(source) as session:
            snapshot = session.snapshot
            with session.open_payload(DOCUMENT) as stream:
                assert stream.read() == raw
        workflow = default_workflow()
        inspected, converted = workflow.inspect(source), workflow.convert(source, vault)
        baseline = None
    else:
        api = note_api(raw)
        api.attachments[DOCUMENT] = api.attachments.pop(NOTE) | {"id": DOCUMENT}
        api.payloads[DOCUMENT] = api.payloads.pop(NOTE)
        api.overrides["/api/v1/docs.json"] = (200, SCHEMA)
        if present:
            api.attachments[IMAGE] = attachment(
                IMAGE, HOME, 12, IMAGE + ".png", length=len(PNG)
            )
            api.payloads[IMAGE] = PNG
        with api_server(api) as (_, address):
            recording = ApiRecording(
                tmp_path / "http",
                address,
                brain_id=BRAIN,
                credential=KEY,
                purpose="convert",
            )
            with recording:
                workflow = local_api_workflow(
                    LocalApiConfig(api_url=recording.api_url), credentials=lambda: KEY
                )
                module = LocalApiSourceModule(
                    LocalApiConfig(api_url=recording.api_url),
                    credentials=lambda: KEY,
                    profile_version="5",
                )
                with module.open(LocalApiSourceRef(BRAIN)) as session:
                    snapshot = session.snapshot
                    with session.open_payload(DOCUMENT) as stream:
                        assert stream.read() == raw
                inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
                converted = workflow.convert(LocalApiSourceRef(BRAIN), vault)
                recording.complete()
            baseline = recording.seal(qualification=composition_api_controls)
    assert sha256(source.read_bytes()).hexdigest() == source_digest
    document = snapshot.documents[0]
    assert document.key == DOCUMENT and document.owner == HOME
    assert document.text == facts["final"]
    assert document.text_digest == sha256(facts["final"].encode()).hexdigest()
    assert [
        (e.kind, e.start, e.end, e.before, e.after, e.adapted_start, e.adapted_end)
        for e in document.text_adaptations
    ] == facts["edits"]
    assert all(
        e.source_digest == sha256(raw).hexdigest() for e in document.text_adaptations
    )
    assert [
        (r.start, r.end, r.table_cell) for r in document.references if r.kind == "item"
    ] == facts["item_contexts"]
    findings = [f for f in snapshot.findings if f.kind == "unavailable_image_reference"]
    assert len(findings) == int(facts["missing"])
    for finding in findings:
        observed = json.loads(finding.observed_json)
        assert observed["source_reference"]["start"] == facts["source"].index(MISSING)
        assert observed["intermediate_reference"]["start"] == facts[
            "intermediate"
        ].index(MISSING)
        assert observed["notice"]["start"] == facts["final"].index(NOTICE)
        assert (
            observed["source_reference"]["before"]
            == observed["intermediate_reference"]["before"]
            == MISSING
        )
        assert observed["notice"]["text"] == NOTICE
        assert observed["source_reference"]["source_digest"] == sha256(raw).hexdigest()
        assert (
            observed["intermediate_reference"]["document_digest"]
            == sha256(facts["intermediate"].encode()).hexdigest()
        )
        assert observed["notice"]["document_digest"] == document.text_digest
        for name, body, phrase in (
            ("source_reference", facts["source"], MISSING),
            ("intermediate_reference", facts["intermediate"], MISSING),
            ("notice", facts["final"], NOTICE),
        ):
            assert observed[name]["end"] == body.index(phrase) + len(phrase)
        before, after = facts["row"], facts["base_row"]
        start, adapted = (
            facts["source"].index(before),
            facts["intermediate"].index(after),
        )
        assert observed["composition"]["base_edits"] == [
            {
                "kind": "markdown_insert",
                "start": start,
                "end": start + len(before),
                "before": before,
                "after": after,
                "adapted_start": adapted,
                "adapted_end": adapted + len(after),
                "source_digest": sha256(raw).hexdigest(),
                "source_basis": "scoped_source_text/unicode_codepoints",
                "adapted_basis": "document.text/unicode_codepoints",
            }
        ]
        assert observed["composition"]["flat_edit"] == next(
            i
            for i, edit in enumerate(facts["edits"])
            if edit[0] == "markdown_insert_image_unavailable"
        )
        assert observed["source_reference"]["uri"] == ".data/md-images/lost.png"
        assert observed["source_reference"]["label"] == "Lost"
        assert (
            observed["source_reference"]["destination_start"]
            == facts["source"].index(MISSING) + 8
        )
        assert (
            observed["source_reference"]["destination_end"]
            == facts["source"].index(MISSING) + len(MISSING) - 1
        )
        assert observed["owner"] == HOME and observed["document"] == DOCUMENT
        assert observed["absence"] == {
            "location": "lost.png",
            "basis": "archive_undeclared_no_payload"
            if adapter == "brz"
            else "api_undeclared_inventory",
        }
        assert finding.affected == (DOCUMENT, HOME)
        assert finding.evidence == (
            ("attachments.json:0",) if adapter == "brz" else ("attachment:" + DOCUMENT,)
        )
        assert finding.rule_id == "thebrain.unavailable-image.v1"
    outcome = "warnings" if facts["missing"] else "clean"
    assert inspected.outcome == converted.outcome == outcome, converted.issues
    assert next(vault.rglob("*.original")).read_bytes() == raw
    if adapter == "brz":
        check_vault(source, vault)
    else:
        check_api_vault(baseline, vault, profile_version="5")
    if case.endswith("after"):
        # Reuse the independently audited public source snapshot for each
        # distinct provenance failure; no extra conversions or fake sources.
        policy = BRZ_POLICY if adapter == "brz" else LOCAL_API_POLICY_V5
        for damage in (
            "flat-F",
            "compound-T",
            "missing",
            "swapped",
            "text",
            "digest",
            "occurrence",
            "code",
        ):
            document = snapshot.documents[0]
            edits = list(document.text_adaptations)
            finding = next(
                f for f in snapshot.findings if f.kind == "unavailable_image_reference"
            )
            observed = deepcopy(json.loads(finding.observed_json))
            later = next(
                i
                for i, edit in enumerate(edits)
                if edit.start > facts["source"].index(facts["row"])
            )
            if damage == "flat-F":
                edit = edits[later]
                edits[later] = edit.model_copy(
                    update={
                        "adapted_start": edit.adapted_start + 1,
                        "adapted_end": edit.adapted_end + 1,
                    }
                )
            elif damage == "compound-T":
                edit = observed["composition"]["base_edits"][0]
                edit["adapted_start"] += 1
                edit["adapted_end"] += 1
            elif damage == "missing":
                edits.pop(later)
            elif damage == "swapped":
                edits[later - 1], edits[later] = edits[later], edits[later - 1]
            elif damage == "text":
                edits[later] = edits[later].model_copy(update={"after": "wrong"})
            elif damage == "digest":
                edits[later] = edits[later].model_copy(
                    update={"source_digest": "0" * 64}
                )
            elif damage == "occurrence":
                observed["intermediate_reference"]["start"] += 1
                observed["intermediate_reference"]["end"] += 1
            else:
                observed["composition"]["base_edits"][0]["kind"] = "literal_text"
            changed = snapshot.model_copy(
                update={
                    "documents": (
                        document.model_copy(update={"text_adaptations": tuple(edits)}),
                    ),
                    "findings": tuple(
                        f.model_copy(update={"observed_json": json.dumps(observed)})
                        if f is finding
                        else f
                        for f in snapshot.findings
                    ),
                }
            )
            expected = (
                "Declared text adaptations"
                if damage in {"flat-F", "missing", "swapped", "text", "digest"}
                else "Image notice transformation evidence"
            )
            with pytest.raises(MigrationRefused, match=expected):
                analyze(changed, policy)
        for damage in (
            "later-text",
            "later-missing",
            "later-swapped",
            "code-authority",
        ):
            destination = tmp_path / damage
            forged_output(vault, destination, converted, facts, damage)
            with pytest.raises(AssertionError) as rejection:
                if adapter == "brz":
                    check_vault(source, destination)
                else:
                    check_api_vault(baseline, destination, profile_version="5")
            if damage == "code-authority":
                assert (
                    str(rejection.value)
                    == "document adaptation exact literal token extent"
                )
