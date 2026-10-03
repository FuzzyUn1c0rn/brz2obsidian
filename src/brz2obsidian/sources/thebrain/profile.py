from brz2obsidian.contracts import FindingDisposition, SourcePolicy

from .findings import ABSENT_TXT_RULE, ICON_LENGTH_RULE

BRZ_POLICY = SourcePolicy(
    profile_id="thebrain-format5-reviewed",
    profile_version="1",
    module_id="thebrain-brz",
    module_version="1",
    format_version="5",
    finding_dispositions=(
        FindingDisposition(
            rule_id=ABSENT_TXT_RULE,
            kind="known_absent_payload",
            disposition="warning",
            issue_code="approved_source_gap",
            permits_absent_payload=True,
            message="Absent source file; its metadata is retained and an intact PDF exists under the same owner.",
            guidance="Review the absent filename in the source; no purpose or specific PDF pairing is inferred.",
        ),
        FindingDisposition(
            rule_id=ICON_LENGTH_RULE,
            kind="approved_metadata_discrepancy",
            disposition="warning",
            issue_code="approved_metadata_discrepancy",
            message="Present icon bytes differ from the declared length; actual CRC-valid bytes are preserved.",
            guidance="Review the declared and actual lengths in the migration record.",
        ),
    ),
)
