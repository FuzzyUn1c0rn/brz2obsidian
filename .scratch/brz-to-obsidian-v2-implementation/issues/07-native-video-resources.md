# 07: Present reviewed video resources without changing their source URLs

Status: claimed

Assignee: /root/v2_implement_07

Labels: ready-for-agent

Published: 2026-10-04 after the user approved the 11-slice breakdown and dependencies.

**Specification:** [Version 2 implementation specification](../spec.md)

**Implementation set:** [Version 2 implementation index](../README.md)

**Source-feature comparison:** [Accepted representations and limitations](../source-feature-mapping.md)

**What to build:** Converted reviewed YouTube resources retain exact clickable URLs and provide a usable native embed with the evidenced timing intent.

**Blocked by:** [01: Convert thought types and all their members into linked category notes](01-typed-category-conversion.md).

**Specification stories:** 8–10, 58–63, 74, 80.

## Acceptance criteria

- [x] Preserve original URL spelling/query parameters and VideoHtml evidence while deriving native presentation from validated reviewed provider facts, not executing archived iframe HTML.
- [x] Offer the embed alongside the retained original link and account separately for any derived embed URL and timing adaptation, including the demonstrated 18-second start.
- [x] Do not fetch/download remote resources during inspection/conversion, invent a local video payload or silently support unreviewed video semantics/providers.
- [x] Explain remote/offline/service dependence once in report/guide, without treating an unavailable remote preview as missing archived bytes or hiding the original link.
- [ ] Verify native rendering/playback/timing on a review copy of converter-produced output when service availability permits; record material limits honestly and leave playback paused.

## Testing boundaries

Workflow/CLI exact URL/evidence/native-embed fixtures and no-fetch behavior; bounded Computer comparison using the established resource scenarios.

Prefer public inspect/convert workflow calls over private helpers, with actual synthetic archives and temporary vaults. Thin CLI checks verify observable output and exit codes. The vault checker uses its public library/command seam. Focused existing public source, core, renderer and publisher boundaries remain available where the criterion requires precise evidence or failure injection. Native review checks converter-produced output and does not replace independent preservation auditing. Use the specification's Testing Decisions for the complete agreed boundaries.

## Standing constraints and completion

Use the accepted specification, source-feature comparison, domain vocabulary and source-neutral architecture. Use the project virtual environment for Python, packages and tooling. Public automated fixtures are synthetic; real archives, extracted content, vaults and native screenshots stay private. Preserve strict inward contracts, exact source evidence and bytes, deterministic identity/naming and fresh-destination safety. Run applicable cumulative public checks and record the result rather than weakening earlier behavior checks. Early slices demonstrate their own supported subset; full Software Engineering support and finished-v2 acceptance require the later delivery gates.

Follow the [local claim and completion process](../../../docs/agents/issue-tracker.md#implementation-operations), [domain glossary](../../../GLOSSARY.md) and [accepted architecture decision](../../../docs/adr/0001-source-neutral-core.md). Claim only after all linked blockers are resolved; save the claim and assignee before implementation. Check each acceptance box only after its criterion passes, record evidence and material limits under Comments, and resolve only when every criterion is satisfied.

## Comments

- 2026-10-05 (/root/v2_implement_07): Automated implementation is complete at the confirmed workflow/CLI seams. `tests/application/test_video_workflow.py` has 45 synthetic cases covering exact source URLs and raw VideoHtml, separate provider/embed/start facts, timed/untimed native presentation, separate inspect/record adaptations, 31 unknown/conflicting metadata/provider/role controls, plain-URL non-inference, denied socket access, absent local-video states/unassigned bytes, CLI exit codes, exact note backups/image bytes/bound spans and repeat/ZIP-record reorder output. The red/green cycles first demonstrated missing derived facts, missing adaptation accounting and missing remote-limit reporting. `sources/thebrain/videos.py` recognizes only the reviewed HTTPS watch URL and exact matching single-iframe baseline metadata; the source URL's `t=18s` supplies the derived `start=18`, while the original metadata's `start=0` survives independently. `obsidian/resources.py` generates a fresh fixed iframe from the neutral facts, never copying archived HTML. One remote/offline paragraph is separate from the retained single PDF Search limitation and source gaps. `docs/source-coverage.md` records the supported forms and limits.

- 2026-10-05 (/root/v2_implement_07): Before integration refresh, cumulative `pytest -q`: 488 passed in 31.70 seconds; `ruff check src tests`, `ruff format --check src tests` (76 files), `pip check` and `git diff --check` passed. Only the root project's `.venv/Scripts/python.exe` ran, with per-process PYTHONPATH pointing to this worktree's `src`; the import location was confirmed. Native criterion remains unchecked pending root's bounded Computer review of the private converter-produced copy under ignored `brz/v2-ticket07/review-vault`, reproduced by `prepare_review.py` there. It uses synthetic identities and the reviewed actual timed public-video URL/metadata, retains `converter-output` unchanged, and leaves the original archive untouched. No native interaction, shared editable install, source-archive mutation, remote publication or cleanup was performed by this implementer. Guide preservation belongs to ticket 04; full three-archive audit and finished-v2 native acceptance remain tickets 10/11.

- 2026-10-05 (/root): Claimed after resolved ticket 01 and integration of 06 freed the attachment boundary. The implementer owns validated video facts and native resource output; root performs the bounded Computer playback/timing check on a converter-produced review copy before resolution.

- 2026-10-04 (/root): Published from the user-approved to-tickets breakdown. Dependencies are local to this implementation set; planning ticket numbers are not implementation blockers. No implementation has started and no acceptance criterion is marked complete.
