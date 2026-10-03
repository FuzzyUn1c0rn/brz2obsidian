# 11: Resolve final Standards and Spec review findings

Status: ready-for-agent

**Specification:** [Accepted first version](../spec.md)

**Review:** [Final two-axis review](../research/final-review.md)

**Blocked by:** All implementation tickets 01–10 (resolved).

**What to build:** Repair the two reproduced Spec defects and three Standards maintenance findings without widening the accepted source coverage or public interfaces.

**Acceptance criteria:**

- [ ] Corrupt compressed ZIP data and unsupported compression return durable structured refusals through source/Workflow/CLI seams, with actionable diagnostics and no publication.
- [ ] Authored trailing Markdown block contexts cannot silently absorb generated Resources or relationship navigation; preserve authored text or explicitly refuse unsupported contexts.
- [ ] Share collision decisions and suffix-width progression between note and tag naming while retaining their presentation and diagnostics.
- [ ] Share the common readable filename sanitation while retaining resource basename extraction and intentional distinctions.
- [ ] Renderer consumes planned inline-resource eligibility without rescanning snapshot image references.
- [ ] Meaningful public regression tests and the full applicable public gates pass; independent real-export acceptance remains valid, and affected native observations are repeated if emitted behavior changes.

**Testing seam:** Accepted public source, Workflow, CLI, core and renderer interfaces. Use synthetic real ZIPs and temporary destinations; never assert private helper calls or modify pristine/private native acceptance vaults.

## Comments

- 2026-10-04: The implement-spec final parallel review reported two reproduced P2 Spec defects and three nonblocking Duplicated Code judgments. One implementer will repair all five findings in an isolated worktree based on the complete integration branch. This is review repair, not additional feature scope.
