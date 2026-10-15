"""Explicit reviewed outer policy bindings for local acquisition."""

from brz2obsidian.contracts import FindingDisposition, SourcePolicy

LOCAL_API_POLICY = SourcePolicy(
    profile_id="thebrain-local-api-reviewed",
    profile_version="1",
    module_id="thebrain-local-api",
    module_version="1",
    format_version="1",
    finding_dispositions=(
        FindingDisposition(
            rule_id="local-api.note-formatting.v1",
            kind="formatting_loss",
            disposition="warning",
            issue_code="formatting_loss",
            message="Included thought-note formatting uses a reviewed visible fallback.",
            guidance="Review exact formatting adaptations and preserved source bytes in the Migration report.",
        ),
    ),
)

LOCAL_API_POLICY_V2 = LOCAL_API_POLICY.model_copy(update={"profile_version": "2"})
