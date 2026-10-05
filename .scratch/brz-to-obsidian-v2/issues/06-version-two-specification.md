# Agree the version 2 specification and conversion acceptance checks

Status: resolved
Type: grilling
Labels: wayfinder:grilling
Parent: [Find the route to version 2 for the Software Engineering Brain](../map.md)
Blocked by: 05, 12
Assignee: /root

## Question

What complete implementation-ready agreement and acceptance evidence will prove version 2 successfully converts the Software Engineering Brain while preserving version 1 coverage?

Use the explicitly required [to-spec skill](C:/Users/stefa/.agents/skills/to-spec/SKILL.md) to consolidate the resolved decisions into a version 2 implementation specification. Account for every observed feature and every known gap, with an explicit mapping, limitation or refusal policy. Agree the source-neutral contract extensions and reviewed source-profile changes needed by those meanings, CLI/library/report compatibility, note and configuration behavior, payload preservation and the user's expected native Obsidian experience. Resolve any architectural tradeoff before publishing implementation tickets. Synthesize the settled discussion; do not use specification generation to reopen decisions or fill unanswered questions with assumptions.

Define full-archive independent preservation checks for the exact new archive, regressions for both earlier archives, synthetic fixtures for each new supported meaning and any controlled source evidence still needed. Require clear distinction between retained raw evidence, semantically preserved knowledge and simplified presentation. A successful run, a few screenshots or a stored JSON field alone is not complete acceptance.

Confirm the highest practical testing seams with the user as required by to-spec. Publish the specification with `Status: ready-for-agent` in the separate version 2 implementation area, using the skill's complete template. Link a human-readable source-feature-to-vault-feature comparison and the accepted specification. This resolves a milestone, not the map: implementation tickets, delivery and final acceptance still follow.

## Answer

Generated the [version 2 implementation specification](../../brz-to-obsidian-v2-implementation/spec.md) with the explicitly invoked to-spec skill and published it to the local Markdown tracker with **Status/Labels: ready-for-agent**. It uses all seven required sections and 82 numbered user stories, accompanied by the [source-feature-to-vault-feature comparison](../../brz-to-obsidian-v2-implementation/source-feature-mapping.md).

The user explicitly confirmed the testing boundaries: the existing public inspect/convert library workflow is the primary automated seam, with thin CLI/result/actual-output checks; the new source-independent read-only checker is tested through its public function and command; independent full-archive audits cover all three archives, followed by native review of actual converter outputs. Prefer existing public module boundaries for focused contract, reference-span and failure tests. Private archives and screenshots are not public fixtures, and the prototype is prior evidence rather than delivery acceptance.

The specification consolidates accepted coverage, category materialization, native templates, icon presentation, canonical properties, contextual rename-safe dashboards, safe existing-note edits, read-only checking and publication protection. It explicitly keeps Icon before Note, omits the decorative Appearance display and additional additive templates, and distinguishes source gaps from PDF-search/remote-playback limits. Architectural contracts remain source-neutral and inward; extended closed contracts/results/evidence receive explicit v2 schema/profile versions, while workflow signatures, command arguments and existing outcome/exit semantics continue.

The next frontier is [Create the approved version 2 implementation tickets with to-tickets](07-version-two-implementation-tickets.md). The accepted specification is a milestone; its implementation, complete preservation/regression evidence and user acceptance of the actual converted vault remain required for the finished-v2 destination.

## Comments

- 2026-10-04 (/root): Document verification passed: all seven required skill sections, 82 consecutive correctly formed stories, every story represented in the feature comparison, 53 valid local links, confirmed testing-boundary metadata, ready-for-agent specification and resolved handoff. Implementation Decisions contains no repository file paths or code snippets. No production tests were needed for this specification-only change; converter implementation remains ahead.
- 2026-10-04 (/root): The user confirms **Yes, use these testing boundaries** in response to the skill's focused check. Published the synthesized specification and mapping, and resolved this handoff. No further product interview, production converter changes or implementation tickets were introduced by this task.

- 2026-10-04 (/root): Claimed at the user's explicit to-spec request. Read the invoked skill, current implementation/testing interfaces, glossary, ADR and accepted v2 decisions. Proposed the existing public inspect/convert workflow as the primary automated seam, thin CLI/output assertions, the new read-only checker at its public function/command, independent three-archive preservation audits and native review of actual generated vaults. The skill's required testing-boundary check is pending; continue synthesis without reopening accepted product decisions.
- 2026-10-04 (/root): [Native maintenance adaptations](12-native-maintenance-adaptations.md) is resolved through the user's agreement: full templates for new notes and direct membership edits for existing notes; contextual rename-safe member queries entered through category dashboards; unambiguous shortened links accepted by the read-only checker. The accepted prototype also removes the decorative Appearance display. All blockers are resolved; this is the next unclaimed frontier. Use the current answers rather than superseded prototype candidates, and still agree the practical testing seams through to-spec.
- 2026-10-04 (/root): The user accepted the prototype presentation with Icon before Note. The trial is resolved; [native maintenance adaptations](12-native-maintenance-adaptations.md) carries the three outstanding decisions into a focused prerequisite before specification generation.
- 2026-10-04: Created during charting. The native trial and any decisions it reopens must resolve before the final agreement.
- 2026-10-04: The user explicitly requires to-spec for this artifact and clarified that the map's destination is a finished version 2.
