# GitHub issue overview

Snapshot verified against live GitHub on **2026-11-11**. This is a saved overview, not a continuously updated board.

**Continuation instruction, 2026-11-12:** resume #366 after saving this file; monitor weekly usage and pause at **40% remaining or lower**. This supersedes the previous 50% threshold.

## Overall position

There were **10 open issues repository-wide**:

- **5 belong to the current #292 effort:** four parent/acceptance trackers and one current implementation issue, **#366**.
- **5 belong to other work or historical bookkeeping.**
- The complete #292 issue tree contains **38 closed issues and 5 open issues**. This is an issue count, not an estimate of remaining effort.

“Closed” means an internal task was accepted and integrated into the feature branch. It does not necessarily mean released to main.

The earlier description of icon implementation as still outstanding was inaccurate: **#348's implementation children are closed; final qualification and delivery remain open.**

## Relationships

```mermaid
flowchart TD
    A["#292 — Type/tag relationships and inherited icons<br/>OPEN: overall feature"]
    A --> B["Core behavior and source fixes<br/>23 CLOSED issues"]
    A --> C["#348 — Additional icon formats<br/>Implementation done; acceptance OPEN"]
    C --> D["#352, #355, #356<br/>CLOSED"]
    A --> E["#347 — Memory-efficient large-attachment updates<br/>OPEN"]
    E --> F["10 direct prerequisite/implementation issues<br/>CLOSED"]
    E --> G["#357 — Content representation and legacy replay<br/>Parent closeout OPEN"]
    G --> H["#359, #360<br/>CLOSED"]
    E --> I["#366 — Apply, Undo, recovery and remaining consumers<br/>CURRENT IMPLEMENTATION"]

    style I fill:#fff3cd,stroke:#b8860b,stroke-width:3px
    style B fill:#e8f5e9,stroke:#388e3c
    style D fill:#e8f5e9,stroke:#388e3c
    style F fill:#e8f5e9,stroke:#388e3c
    style H fill:#e8f5e9,stroke:#388e3c
```

## Five open issues in the current effort

| Issue | Purpose | Actual progress and remaining work |
|---|---|---|
| [#292](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/292) | Overall type/tag relationships and inherited-icons feature | Core milestones M1–M4 accepted. Actual-source/native acceptance, final regression/review, user verdict and delivery remain. |
| [#347](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/347) | Make large-attachment updates practical in memory | Most foundations and production routes implemented. Finish #366, then complete assembled resource/performance, regression and real-source qualification. |
| [#357](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/357) | Shared content representation and compatible legacy replay | Both implementation children, #359 and #360, closed. Parent acceptance/closeout needs reconciliation; this is not another untouched implementation project. |
| [#366](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/366) | Complete publication, operation history, Undo/recovery and remaining producers | Current implementation issue. Code substantially complete and whole-leaf source review passed. Latest Undo verification needs clean completion, independent verification and feature-root integration. |
| [#348](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/348) | Bounded ICO/DIB/BMP icon support | Implementation and default library/CLI/Windows wiring complete; all three children closed. Broad regression, actual API/BRZ parity, native/user acceptance and delivery remain. |

## Thirty-eight closed issues

| Completed area | Closed issues |
|---|---|
| Core type/tag admission, category rendering, BRZ update compatibility and warning correction | [#324](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/324), [#325](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/325), [#326](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/326), [#329](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/329) |
| Additional source/attachment handling: YouTube, thought links, capture limits, Markdown literals, missing TXT/images and internal files | [#327](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/327), [#330](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/330), [#333](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/333), [#334](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/334), [#335](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/335), [#336](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/336), [#338](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/338) |
| Source/output checking, replay qualification and verification-performance corrections | [#328](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/328), [#331](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/331), [#332](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/332), [#337](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/337), [#339](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/339), [#340](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/340), [#341](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/341), [#342](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/342), [#343](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/343) |
| Review guidance, attachment offers and documentation corrections | [#344](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/344), [#345](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/345), [#346](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/346) |
| Bounded content acquisition, comparison, serialization and legacy replay | [#349](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/349), [#350](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/350), [#354](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/354), [#359](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/359), [#360](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/360) |
| Resource-observation and small resource-proof prerequisites | [#351](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/351), [#353](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/353), [#358](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/358) |
| Cold history inspection, default preparation/choices/Save, onboarding and saved-review restoration | [#361](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/361), [#362](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/362), [#363](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/363), [#364](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/364) |
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

1. Finish #366: clean Undo verification, commit the latest correction, independent verification and feature-root integration.
2. Reconcile #357 closeout; finish #347 resource/regression work and #348 assembled-candidate acceptance.
3. Complete #292 real-source/native checks and user acceptance.
4. Deliver the assembled feature through its final PR and close the remaining parent issues.

Different-Brain imports in #259/#258 are a separate future feature.

## Preserved implementation state at the pause

- Feature root: `codex/r292-type-tag-support`, checkout `C:/Users/stefa/projects/brz2obsidian`, commit `740e3a9d7caa8cd683f5198a1fa3c4065599bf4b`.
- Author: `codex/r347-owned-publication`, checkout `C:/Users/stefa/.codex/worktrees/r359-family-codec/brz2obsidian`, checkpoint `6ad06beee63f511b69df8f747c89f57bd3275e48`, plus five uncommitted restored-Undo files.
- Latest whole-leaf source verdict: PASS for immutable candidate003. Runtime qualification remains incomplete.
- Last focused run logged 18 passed and two Windows child-process exits with status `0xC0000142`; it was also cancelled at the usage threshold. The restored-Undo flow reached its final fresh-process status check; the other case failed during Git initialization. Their cause requires a clean rerun before classifying a product defect.
- The extra Inline terminal-history control fails identically on clean accepted base; its evidence is preserved as a pre-existing failure.
- SQLite/generic accounting work remains parked.
- Detailed pause record: [current-state-resume113-paused.json](tmp/r347-owned-publication-20261110/current-state-resume113-paused.json).

## Progress since the snapshot — 2026-11-12

- Work resumed with the new pause threshold of 40% weekly remaining.
- The unchanged Undo rerun passed all 20 selected tests, lint, formatting, dependency checks, partial coverage reporting and receipt validation in 390.74 seconds. The earlier child-process exits did not reproduce.
- The restored-Undo correction is committed as `150316d6519e2f3ba3793baa268b09686515f628` on `codex/r347-owned-publication`.
- Post-commit completion checks passed all 19 selected tests and all four check types in 214.72 seconds. The author checkout is clean.
- Independent final-candidate verification and actual feature-root integration are still pending. #366 remains open; the parent acceptance/delivery limits above remain unchanged.

