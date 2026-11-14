# GitHub issue overview

Open issue list refreshed from GitHub on **2026-11-14**. Internal tree counts retain the previously reconciled map; this file is a dated snapshot.

**Current feature root:** `codex/r292-type-tag-support`, product implementation through `eda8949`, reviewed test/setup/selection contribution through `0c81f96` and native cancellation-test correction through `b657275`. There is one authoritative feature branch; isolated helper branches and all historical evidence are preserved.

**Implemented:** the type/tag and icon implementation children are closed. Large-update lifecycle consumers, owned CLI history, shared-note attachment composition, profile-5 acceptance forwarding and source-baseline compatibility fixes are integrated. The API capture-context comparison optimization at `8abd20f` retains fresh validation and the original canonical fallback; it passed 72 author tests and 70 independent tests. The repair at `16e4af0` prevents a Windows worker hang when a missing inline image triggers a cold native-decoder import. A representative baseline reproduced the hang at the same 60-second bound; the repaired preparation completed in about 30 seconds. Fresh author and independent runs each passed 77 tests and all four checks. The subsequent `727b164` refactor reuses Windows API bindings while keeping file and ownership observations fresh; author and independent runs each passed 74 tests and all four checks. Small independent probes measured about 28% lower file-observation overhead, without establishing whole-workflow speed. Both changes have validated integration. The large-source lifecycle remains under qualification.

The link-resolution repair at `eda8949` reuses computed meanings within one immutable review operation while keeping the original resolver, dependency checks, refresh rules and cancellation boundaries. Original candidate `e85c32a` passed154 focused tests and all four checks for both author and independent verifier. A subsequent test-only repair removed an implementation-specific assertion; fresh checks of the retained public semantic case and all four checks passed for both actors at `eda8949`, with exact production-byte identity to `e85c32a`. Independent review and integration passed. A single synthetic helper sequence preserved complete outputs and took about24% less time; actual-source and whole-suite speed remain unverified.

**Scoped native progress:** the single-file and shared-note four-file 16/64/256 MiB series, empty/65,537-byte boundary, duplicate-content, same-size distinct-content and incompressible-content journeys passed at their recorded revisions. They include Save, fresh-process load/resume, Apply, unchanged-source repeat and exact byte/history/user-Git preservation. The complete four-file series and final orthogonal cases have independent review; four-file producer/consumer private-memory endpoint changes were +0.379 MiB / -0.793 MiB, within the 32 MiB tolerance. Existing retained 64/256 MiB packed non-delta lifecycle evidence was independently joined to its exact objects and bytes, avoiding redundant experiments. A fresh focused cancellation/refresh/draft/retirement control passed all four checks. The real-worker Save/cancel/cold-recovery test also passed after correcting its obsolete expectation: acknowledged late cancellation retires the context while retaining the verified checkpoint. Actual-source process/capacity qualification and final native/user obligations remain.

**Remaining regression failures:** the completed404-selector diagnostic at `7affd21`, before the latest API refactor, had 2,756 passed and one GUI wait failure; lint, format and dependency checks passed. Its coverage was **9,726/12,208 branches (79.669%), 41 short of 80%**, and wall time **1,731.79 seconds** under concurrent native work. It does not qualify the ordinary gate. The GUI file passed 5/5 in isolation; the original failure's cause is still unproven. The current candidate needs fresh ordinary verification meeting 80% branches and under 900 seconds.

**Current ordinary candidate:** the reviewed test/setup/selection contribution is integrated. It removes repeated choice replay from one real recovery test while preserving its assertions and identical production line/branch sets. Selecting the complete read-view owner replaces seven narrower selectors; the new worker regression brings the maintained selection to 402 selectors. A quiescent run at `16e4af0` stopped at the 900-second deadline after 2,388 completed call reports and no recorded test failures. A run at `727b164`, with the actual BRZ job active separately, also timed out after 1,866 completed call reports and no recorded test failures. Neither produced a complete receipt or coverage result; the second is not an isolated performance comparison. The earlier 407-selector attempt also timed out. The diagnostic above remains the latest complete measurement; suite runtime, current coverage and the older GUI uncertainty remain open. A bounded inspection found no justified shortcut in the two costly Undo tests, so their distinct assertions were retained. The next maintained run assesses the integrated link-resolution repair after the heavy BRZ job closed. Historical source assessments322/323 continue in the background; this will not be an isolated performance comparison.

**Actual-source status:** the older API conversion was canceled as superseded after 115.45 minutes, with its partial capture/output preserved and unqualified. Public profile-5 conversion276 completed and its source was sealed, but the user's pause stopped its independent audit and retained-inspect reassessment310 before completion. New independently reviewed offline assessments322 and323 are now checking the retained inspect source and conversion source/output; no recapture is involved, and neither has qualified yet. Original inspect205's timed-out orchestration and all canceled attempts remain retained. Recorded native source/API/BRZ samples and controlled inheritance/priority edits in both review copies have independent scoped review. Source selection uses documented unique-title/context inference, conditional on drift reconciliation. Actual BRZ317 was canceled before publication on its test-owned copy at `16e4af0`, ahead of the inherited harness timeout. Preparation returned `cancelled_before_publication`, public close succeeded and worker/launcher exited0. No Save or Apply completed; the attempt remains unqualified. The observer also reported a metadata error and global temporary paths with unverified ownership; all evidence and paths are retained. A later attempt needs practical margins and process-specific temporary isolation, followed by the same actual lifecycle gates. Actual001's system Git text-conversion-driver refusal and actual002's stopped worker hang are preserved. Production refusal rules and host settings are unchanged. Full inspect/conversion/parity qualification, actual BRZ Save/cold-resume/Apply/repeat, further reversal/recovery and native/user verdicts remain open.

**Usage rule:** monitor weekly usage and pause all work at **25% remaining or lower**. Latest observation: 32% remaining.

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
| [#347](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/347) | Make large-attachment updates practical in memory | Lifecycle consumers, shared-note attachment composition and the Windows cold-import worker repair are integrated. Scoped single-file and four-file 16/64/256, empty/chunk-boundary, duplicate, distinct and incompressible-content journeys passed with independent scoped review. Packed-storage applicability and the real-worker cancellation/cold-recovery correction are reviewed. Actual BRZ317 ended before publication and remains unqualified; the reviewed link-resolution repair is integrated. Actual lifecycle/capacity/native observations and ordinary 80%/under 900 remain. |
| [#348](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/348) | Bounded ICO/DIB/BMP icon support | Product implementation and default wiring complete; all three children closed. The profile-5 command and source-baseline compatibility repairs are integrated. A reviewed API read-validation optimization is now integrated. Fresh actual API/BRZ qualification, native/user acceptance, broad regression and delivery remain. |

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
2. Complete the running offline inspect/source-output assessments322/323, reconcile matching BRZ parity for #348, and retain the scoped native icon observations with their stated identity limits.
3. Resolve the regression GUI uncertainty, coverage deficit and ordinary runtime; verify the assembled current candidate.
4. Complete actual-user acceptance and the single delivery PR with independent whole-PR review. Parent #292/#347/#348 remain open until their gates are satisfied.

Different-Brain imports in #259/#258 remain a separate future feature. Historical snapshots, failed receipts, fixtures and worktrees remain preserved.
