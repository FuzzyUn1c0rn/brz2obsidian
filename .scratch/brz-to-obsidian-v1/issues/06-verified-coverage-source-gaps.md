# 06: Report known gaps and enforce verified source coverage

Status: ready-for-agent

Published: 2026-10-03 after the user approved ticket granularity and blocking dependencies.

**Specification:** [Convert a TheBrain BRZ archive into a new Obsidian vault](../spec.md)

**Implementation set:** [First-version implementation tickets](../README.md)

**What to build:** Complete the reviewed source profile so verified Brains convert with precise known-gap warnings and unsupported or unreliable input is refused explicitly.

**Blocked by:** [04: Adapt thought and image links without rewriting notes](04-source-note-links.md); [05: Preserve tags using native Obsidian features](05-native-tags.md)

**Specification stories:** 50, 51, 52, 53, 54, 55, 56.

**Boundary and dependency rationale:** Completing the declared profile depends on the graph, resource, reference, and tag behaviors being available; reference and tag slices transitively include the other feature slices.

**Acceptance criteria:**

- [ ] Apply the exact accepted absent-TXT predicate, including source role/type/state/length, absent bytes, and an intact PDF under the same owner. Preserve metadata and avoid claiming purpose, optionality, or a TXT/PDF pairing.
- [ ] Continue on the precise approved present-icon length discrepancy using CRC-valid actual bytes, preserving actual/declared lengths. Neither rule authorizes missing required notes/files/images or unknown absence patterns.
- [ ] Source interpretation emits evidence-backed versioned findings; generic core decides warning/refusal under the reviewed compatible profile. Numeric TheBrain predicates and rule constants stay outside generic core; unknown rules/profile mismatches refuse.
- [ ] Warning conversions publish verified output and exit 2 with consistent structured issues in terminal/JSON, report, and record. Add a brief absent-filename notice only to an existing owner note; do not create a fake link/file or a note solely for a warning.
- [ ] Complete the exact verified thought/relationship/attachment feature boundary. Retain system/history/deletion/raw metadata without invented navigation meaning; malformed/duplicate keys, corrupt ZIP members, unreliable live identities/references, ambiguous payloads, or unverified semantics cannot silently pass.
- [ ] Unsupported format/features, nonempty unverified collections, custom types, HTML/cross-Brain content, unverified direction combinations, and semantic role flags produce stable actionable refusal. Additional uninterpreted metadata remains original evidence.
- [ ] Through full-workflow plus source/core seam tests, test every required conjunct of each warning predicate with matched and near-miss examples, and verify stable issue codes, unavailable counts, source accounting, and unchanged destinations on refusal.
- [ ] Ordinary name adaptations and agreed arrow simplifications are recorded adaptations, not invented warnings; no caller/CLI arbitrary allowlist is introduced.

**Testing seam:** Prefer the reusable workflow for observable operation behavior and the public module interfaces for focused evidence. Use real synthetic ZIPs/temp files for I/O and independently expected artifacts/diagnostics; do not couple tests to private helpers. Retain the accepted specification and architecture dependency rules throughout this slice.

## Comments

- 2026-10-03: The user approved the breakdown. This is an implementation ticket in the separate first-version tracker; the completed Wayfinder map is not its parent. All Python packages used for development, builds, and runtime must be installed only in the project virtual environment as needed.
