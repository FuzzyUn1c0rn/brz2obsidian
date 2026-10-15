"""The reviewed TXT404 exception requires independently preserved owner PDF bytes."""

from brz2obsidian.contracts import SourceFinding

from .errors import refuse

RULE = "local-api.missing-txt-pdf.v1"


def gap_projections(assets, declarations):
    from .capture import canonical

    findings, decisions = [], []
    for asset in sorted(assets, key=lambda a: a.asset_id):
        if asset.availability != "absent":
            continue
        value = declarations[asset.asset_id]
        if (
            asset.role != "file"
            or value["type"] != 15
            or value["isNotes"] is not False
            or not value["location"].lower().endswith(".txt")
        ):
            refuse("Unavailable payload is outside the reviewed TXT exception")
        pdfs = sorted(
            a.asset_id
            for a in assets
            if a.owner == asset.owner
            and a.role == "file"
            and a.availability == "present"
            and declarations[a.asset_id]["type"] == 1
            and declarations[a.asset_id]["isNotes"] is False
            and declarations[a.asset_id]["location"].lower().endswith(".pdf")
            and a.actual_length is not None
            and a.actual_sha256 is not None
        )
        if not pdfs:
            refuse("Unavailable TXT lacks a qualified preserved same-owner PDF")
        keys = [asset.asset_id, *pdfs]
        decision_key = "scope:missing-txt404:" + asset.asset_id
        evidence = sorted("attachment:" + k for k in keys)
        decisions.append(
            {
                "key": decision_key,
                "rule_id": RULE,
                "outcome": "missing_txt404",
                "subjects": evidence,
                "evidence": sorted(evidence + ["payload:" + k for k in keys]),
            }
        )
        findings.append(
            SourceFinding(
                rule_id=RULE,
                kind="known_absent_payload",
                affected=(asset.asset_id,),
                evidence=tuple(sorted(evidence + [decision_key])),
                observed_json=canonical(
                    {
                        "asset_id": asset.asset_id,
                        "owner_id": asset.owner,
                        "filename": value["location"],
                        "retrieval": {"status": 404, "outcome": "missing_txt_404"},
                        "preserved_same_owner_pdf_ids": pdfs,
                    }
                ).decode("utf-8"),
            )
        )
    return findings, decisions


def validate_gap_audit(assets, audit, decisions):
    by_id = {a.asset_id: a for a in assets}
    absent = {a.asset_id for a in assets if a.availability == "absent"}
    pdf_ids = {
        subject.removeprefix("attachment:")
        for decision in decisions
        for subject in decision["subjects"]
    } - absent
    outcomes = {}
    for request in audit.requests:
        if request.outcome == "missing_txt_404" and request.subject_id not in absent:
            refuse("A missing TXT request has no qualified absent asset")
        if request.operation == "attachment-content":
            outcomes.setdefault(request.subject_id, []).append(request)
    if not absent <= outcomes.keys() or any(
        r.status != 404 or r.outcome != "missing_txt_404" or r.actual_length != 0
        for key in absent
        for r in outcomes[key]
    ):
        refuse("Absent TXT is not bound to an exact classified HTTP404 retrieval")
    if not pdf_ids <= outcomes.keys() or any(
        r.status != 200
        or r.outcome != "success"
        or r.actual_length != by_id[key].actual_length
        for key in pdf_ids
        for r in outcomes[key]
    ):
        refuse("The qualification PDF lacks a complete measured HTTP200 retrieval")
