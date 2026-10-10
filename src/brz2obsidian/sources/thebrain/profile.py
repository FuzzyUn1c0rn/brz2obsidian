from brz2obsidian.contracts import FindingDisposition, SourcePolicy

from .findings import (
    ABSENT_NOTE_IMAGES_RULE,
    ABSENT_TXT_RULE,
    ABSENT_TYPE_ICON_RULE,
    ABSENT_TYPE_NOTE_RULE,
    ICON_LENGTH_RULE,
    ZERO_LENGTH_ABSENT_TXT_RULE,
)
from .inserts import INSERT_RULE

BRZ_POLICY = SourcePolicy(
    profile_id="thebrain-format5-reviewed",
    profile_version="10",
    module_id="thebrain-brz",
    module_version="10",
    format_version="5",
    finding_dispositions=(
        FindingDisposition(
            rule_id=INSERT_RULE,
            kind="formatting_loss",
            disposition="warning",
            issue_code="formatting_loss",
            message="Included thought-note formatting uses a visible fallback or remains unsupported.",
            guidance="Review the declaration and affected note in the Migration report; edit the converted Markdown or repair the source and re-export.",
        ),
        FindingDisposition(
            rule_id=ABSENT_TYPE_ICON_RULE,
            kind="known_absent_payload",
            disposition="warning",
            issue_code="approved_source_gap",
            permits_absent_payload=True,
            message="Source category icon is absent; its provider and inheriting members have neutral appearance.",
            guidance="Review the provider and affected included members in the Migration report; optionally restore the source icon and re-export.",
        ),
        FindingDisposition(
            rule_id=ABSENT_TYPE_NOTE_RULE,
            kind="known_absent_payload",
            disposition="warning",
            issue_code="approved_source_gap",
            permits_absent_payload=True,
            message="Source category note text is absent and remains unknown.",
            guidance="Review the Migration report evidence and optional source repair checklist.",
        ),
        FindingDisposition(
            rule_id=ABSENT_NOTE_IMAGES_RULE,
            kind="known_absent_payload",
            disposition="warning",
            issue_code="approved_source_gap",
            permits_absent_payload=True,
            message="Source note text is absent; owned note images are displayed without reconstructing prose, captions or layout.",
            guidance="Review the Migration report evidence and optional source repair checklist.",
        ),
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
        FindingDisposition(
            rule_id=ZERO_LENGTH_ABSENT_TXT_RULE,
            kind="known_absent_payload",
            disposition="warning",
            issue_code="approved_source_gap",
            permits_absent_payload=True,
            message="Zero-length source TXT is absent; its filename identifies an intact PDF under the same owner.",
            guidance="Review the retained declaration and PDF association; absent bytes have no inferred purpose.",
        ),
    ),
)
