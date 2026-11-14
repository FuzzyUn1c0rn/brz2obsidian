# GitHub issue overview

Snapshot: **2026-11-14**; open-issue query refreshed at approximately 16:38 UTC. Internal closed-tree counts retain the previously reconciled map.

**One authoritative feature branch:** `codex/r292-type-tag-support`. Latest integrated product revision: `f70c80eefda69b0c4a4f349d9f526e5c8bebafb5`. Helper branches, previous checkouts and all historical evidence remain preserved. Internal task completion does not imply delivery to `main`.

## Current implementation and acceptance

Run numbers below identify local verification attempts. GitHub issues use a # prefix and links.

The type/tag, inherited-icon and bounded ICO/DIB/BMP implementation children are complete and integrated. Large-update lifecycle consumers, owned CLI history, shared-note composition and profile-5 compatibility fixes are integrated. Subsequent repairs prevent a Windows cold-import worker hang and reduce repeated native-binding, link-resolution and current-context lookup work. These are product changes within the current effort.

| Track | Confirmed progress | Remaining work |
|---|---|---|
| Current product repair `f70c80e` | The active-subsequence collision update preserves duplicates and immediately rebuilds the transitive collision closure when a new ID is selected. Author and independent verifier each passed the focused 79-case selection and all four checks; all handoff transition validations passed. The independent review confirms ordering and meaningful public transitive-validation coverage. | Run 346's 79.828431% coverage and GUI result were measured at earlier source `72374a1`; they are not measurements of f70. A fresh full ordinary run on the assembled final source remains needed. Actual-source qualification remains open. |
| Public failure-case coverage (local work350) | Three meaningful public cases are integrated at test-only source commit `6ea3d918a283a211f153fcd86a61891266770e3f`: short writes, malformed data at the legacy chunk boundary, and outer refusal for a retained marker. Private guards are not forced. Author and independent verifier each passed 25 focused tests and all four checks; standalone integration validation passed, and the verifier has two retained receipts. Production behavior remains unchanged from `f70c80e`. | This is scoped test coverage, not ordinary acceptance or actual-source qualification. |
| Inspect-source evidence | Assessment 335 completed with independent PASS: 1,251 thoughts, 1,338 relationships, 38 classifications and 1,666 present payloads. Historical producer `e025919` and current assessor `21a05e3` are explicitly separate. | This qualifies retained inspect run 205 source evidence only. Original run 205 timed out; no new capture/CLI, vault publication, parity or whole-M5 acceptance is claimed. |
| Conversion/source-output evidence | Historical conversion run 276 and assessment 336 are independently qualified. Source-pair comparison 344 closed with exit 0 and independent PASS: all 1,520 shared payloads, including 26 icons, were byte-equal; 146 API-present TXT payloads absent from BRZ match previously approved gap IDs, metadata and lengths. Graph, classes, tags and navigation match; one system node and seven system links are accounted for in scope. | This bounded comparison does not establish atomic capture, full-byte equivalence of unmatched payloads or whole-M5 acceptance. |
| Actual BRZ lifecycle | Run 340 closed unqualified after its real onboarding `prepare_review` returned `prepared_review`, `ready=false`, 2,555 changes and 2,555 unresolved choices. The driver asserted readiness before running the required current-generation choices for each onboarding subject, so it skipped a required public journey step; no Save/Apply occurred. Public close and worker/launcher exit were normal; all six recorded owned processes are absent, Job ActiveProcesses is 0, terminated count 0 and cleanup errors are empty. | Static diagnosis 353 confirms the product requires current-generation choices for every onboarding subject; the driver currently asserts readiness before presenting those choices. Driver-flow correction and a small real public-worker smoke are in progress before any fresh rehearsal. Run 351 remains on HOLD with no new GO. No product bug is inferred. Actual lifecycle, process/capacity, native/reversal and recovery acceptance remain open. |
| Ordinary regression | Run 346 at source `72374a1be71fc69dcc58c30ca3110336102a12c0` completed 2,816 tests with 0 failures and 0 skips/errors, including 155 GUI cases; pytest, lint, format and dependency checks passed. The receipt independently validated, and all 22 recorded owned PIDs are absent. Elapsed time was 1,255.61 seconds and is informational. | Its coverage was 9,771/12,240 (79.828431%), below 80%; this is historical 723 evidence, not an f70 measurement. A fresh full ordinary run on the assembled final source is still needed. |
| Delivery | Current work is integrated on the single feature root. | Remaining acceptance, one delivery PR, independent whole-PR review and final user verdict. |

The older GUI wait failure in run 264 remains preserved as historical evidence. The last full selected GUI pass was run 346 at source `72374a1be71fc69dcc58c30ca3110336102a12c0`; it is historical relative to f70, so fresh current-candidate GUI evidence remains needed. Run 346's 79.828431% branch coverage is likewise tied to 723, not f70. The maintained selection is 402 selectors. Two costly Undo tests were retained after review confirmed distinct successful public consumers; no justified consolidation was found.

Completed scoped rehearsals include single-file and shared-note four-file 16/64/256 MiB journeys, empty/chunk-boundary, duplicate/distinct/incompressible content, packed-storage applicability, and cancellation/cold-recovery controls, with independent review at their recorded revisions. Recorded TheBrain/Obsidian icon and inheritance samples retain their scoped native qualification. These support the effort but do not replace the remaining actual-source or user gates.

Four read-only samples of the older actual run 332 preparation exposed repeated full-context scans. The resulting `d1d9ae2` repair passed independent review and preserved complete synthetic outputs; one controlled larger sequence took 17.73 seconds before and 8.33 seconds after. This is isolated evidence, not actual BRZ workflow timing. Runs 332 and 338 remain closed and unqualified with their original evidence preserved. Run 340 returned an onboarding review requiring 2,555 unresolved choices; its failure record at 20:13:31.212 UTC precedes Root STOP at 20:13:32.725 UTC. The driver assumption failed before publication, no Save/Apply occurred, and normal closeout left zero active or owned processes. Static diagnosis 353 confirms onboarding requires current-generation choices for every subject and the driver skipped that required public step. Driver-flow correction and a small real public-worker smoke are in progress before any fresh rehearsal; run 351 remains on HOLD with no new GO, and no product bug is inferred. Public failure-case coverage is now integrated separately under local work350 at test-only source commit `6ea3d918a283a211f153fcd86a61891266770e3f`; production behavior remains at `f70c80e`.

**Elapsed-time and usage policy:** no automatic overall verification deadline or usage-triggered pause is in effect.

## Overall position

There are **8 open issues repository-wide** after the documented #357 and #366 closeouts:

- **3 belong to the current #292 effort:** the overall #292 parent and its #347 large-update and #348 icon acceptance tracks. Current work covers **#347 qualification and #348 actual-source acceptance**.
- **5 belong to other work or historical bookkeeping.**
- The complete #292 issue tree contains **40 closed issues and 3 open issues**. This is an issue count, not an estimate of remaining effort.

“Closed” means an internal task was accepted and integrated into the feature branch. It does not necessarily mean released to main.

The earlier description of icon implementation as still outstanding was inaccurate: **#348's implementation children are closed; final qualification and delivery remain open.**

## Relationships

```mermaid
flowchart TD
    A["#292 — Type/tag relationships and inherited icons<br/>OPEN: overall feature"]
    A --> B["Core behavior and source fixes<br/>23 CLOSED issues"]
    A --> C["#348 — Additional icon formats<br/>Implementation done; acceptance OPEN"]
    C --> D["#352, #355, #356<br/>CLOSED"]
    A --> E["#347 — Memory-efficient large-attachment updates<br/>Implementation integrated; qualification OPEN"]
    E --> F["10 direct prerequisite/implementation issues<br/>CLOSED"]
    E --> G["#357 — Content representation and legacy replay<br/>CLOSED after evidence reconciliation"]
    G --> H["#359, #360<br/>CLOSED"]
    E --> I["#366 — Apply, Undo, recovery and remaining consumers<br/>CLOSED: independently verified and integrated"]

    style E fill:#fff3cd,stroke:#b8860b,stroke-width:3px
    style I fill:#e8f5e9,stroke:#388e3c
    style B fill:#e8f5e9,stroke:#388e3c
    style D fill:#e8f5e9,stroke:#388e3c
    style F fill:#e8f5e9,stroke:#388e3c
    style G fill:#e8f5e9,stroke:#388e3c
    style H fill:#e8f5e9,stroke:#388e3c
```

## Three open issues in the current effort

| Issue | Purpose | Actual progress and remaining work |
|---|---|---|
| [#292](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/292) | Overall type/tag relationships and inherited-icons feature | Core milestones M1–M4 accepted. Actual-source/native acceptance, final regression/review, user verdict and delivery remain. |
| [#347](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/347) | Make large-attachment updates practical in memory | Lifecycle consumers, shared-note attachment composition and the Windows cold-import worker repair are integrated. Scoped single-file and four-file 16/64/256, empty/chunk-boundary, duplicate, distinct and incompressible-content journeys passed with independent scoped review. Packed-storage applicability and the real-worker cancellation/cold-recovery correction are reviewed. Actual run 340 closed unqualified after onboarding returned an unresolved-choice review and the driver incorrectly required immediate readiness. Static diagnosis 353 confirms the required choice flow; driver-flow correction and a small real public-worker smoke are underway before any fresh rehearsal. Run 351 remains on HOLD with no new GO. The `f70c80e` active-subsequence collision repair is reviewed and preserves order and duplicate rows; earlier D1 current-context indexes remain in place. Run 346 passed its checks and GUI cases at source `72374a1`, but that evidence is historical relative to f70. Fresh full ordinary and GUI evidence on the assembled final source remains needed. |
| [#348](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/348) | Bounded ICO/DIB/BMP icon support | Product implementation and default wiring complete; all three children closed. The profile-5 command and source-baseline compatibility repairs are integrated. Retained inspect-source assessment 335 and conversion/source-output assessment 336 are independently qualified. Source-pair comparison 344 is complete within its recorded bounds. Product candidate `f70c80e` is integrated with independent review. Remaining actual/native/user acceptance, the 80% ordinary branch-coverage gate and delivery remain. |

## Forty closed issues

| Completed area | Closed issues |
|---|---|
| Core type/tag admission, category rendering, BRZ update compatibility and warning correction | [#324](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/324), [#325](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/325), [#326](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/326), [#329](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/329) |
| Additional source/attachment handling: YouTube, thought links, capture limits, Markdown literals, missing TXT/images and internal files | [#327](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/327), [#330](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/330), [#333](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/333), [#334](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/334), [#335](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/335), [#336](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/336), [#338](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/338) |
| Source/output checking, replay qualification and verification-performance corrections | [#328](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/328), [#331](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/331), [#332](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/332), [#337](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/337), [#339](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/339), [#340](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/340), [#341](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/341), [#342](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/342), [#343](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/343) |
| Review guidance, attachment offers and documentation corrections | [#344](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/344), [#345](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/345), [#346](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/346) |
| Bounded content acquisition, comparison, serialization and legacy replay, including reconciled parent | [#349](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/349), [#350](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/350), [#354](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/354), [#357](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/357), [#359](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/359), [#360](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/360) |
| Resource-observation and small resource-proof prerequisites | [#351](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/351), [#353](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/353), [#358](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/358) |
| Cold history inspection, default preparation/choices/Save, onboarding and saved-review restoration | [#361](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/361), [#362](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/362), [#363](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/363), [#364](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/364) |
| Owned publication, operation details, Undo/recovery, terminal cleanup and retained ownership/repair consumers | [#366](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/366) |
| Independent icon expectations, ICO/DIB/BMP admission and default profile wiring | [#352](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/352), [#355](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/355), [#356](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/356) |

## Five other open issues: outside the current #292 implementation

| Issue | Relationship and status |
|---|---|
| [#254](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/254) | Broader editable-vault roadmap. Stage-one updates delivered through [#255 / PR #323](https://github.com/FuzzyUn1c0rn/brz2obsidian/pull/323). Remains open for later import functionality. |
| [#259](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/259) | Future stage-two feature: importing a different Brain and mapping categories/tags. Specified, not dispatched for implementation. |
| [#258](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/258) | Future stage-two shared operations and Windows/CLI review. Depends on #259; not current work. |
| [#203](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/203) | Development-workflow guidance delivered through merged [PR #204](https://github.com/FuzzyUn1c0rn/brz2obsidian/pull/204), while the issue remains open. Bookkeeping needs reconciliation. |
| [#112](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/112) | Historical check-runner subtask. Parent #111 closed, but this issue remains open without its own completion record. Status needs reconciliation; not scheduled feature work. |

## Remaining route for this effort

1. Finish the actual reported-BRZ lifecycle and process/capacity qualification for #347, including the remaining native and reversal/recovery observations. Reuse applicable completed evidence at its recorded revision.
2. Retain qualified inspect assessment 335, conversion/source-output assessment 336 and bounded source-pair comparison 344 for #348, alongside scoped native icon observations with their stated identity limits.
3. Complete the actual onboarding choice-flow correction and a small public-worker smoke before considering any fresh actual rehearsal. Then run the maintained ordinary verification on the assembled final source, including all four checks, GUI execution, validated receipts and the 80% production branch-coverage gate; the current 723 result remains historical.
4. Complete actual-user acceptance and the single delivery PR with independent whole-PR review. Parent #292/#347/#348 remain open until their gates are satisfied.

Different-Brain imports in #259/#258 remain a separate future feature. Historical snapshots, failed receipts, fixtures and worktrees remain preserved.
