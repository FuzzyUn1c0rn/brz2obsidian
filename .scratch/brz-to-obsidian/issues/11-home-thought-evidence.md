# Verify how BRZ identifies the home thought

Status: resolved
Type: research
Labels: wayfinder:research
Parent: [Find the route from a BRZ archive to an Obsidian vault](../map.md)
Blocked by: none
Assignee: /root/home_evidence

## Question

Which verified source field identifies TheBrain's designated home thought in the inspected format-5 BRZ archives, and how can conversion preserve that designation without guessing a root from graph topology?

Use first-party documentation and, if necessary, a controlled export with a known home thought. Distinguish home from last activated thought, a thought named Home, and a hierarchy node with no parents. Inspect settings and their stable identifiers; do not treat a UUID-valued setting as proven home semantics solely because it references a live thought. Keep private source content local.

Determine the observed behavior when the setting is absent or invalid; leave reporting/override policy to the conversion-contract decision. Supply reproducible evidence for resolving the home thought to its assigned vault target. Native startup/bookmark behavior and visible home naming are validated within the vault trial rather than by this source-format investigation.

## Comments

- 2026-10-03: Human review found the prototype quite good but surfaced a required home designation. TheBrain's home thought is the entry on loading or pressing Home; the user emphasized that the corresponding node must remain clearly identifiable in the migrated graph.
- 2026-10-03: Preliminary read-only inspection of the two exact real input paths found 27/25 settings records. Their schema contains UUID Id fields and string Value fields, without named home keys in the inspected thought/settings schemas. Each archive has one Value containing a live thought UUID. This is a candidate reference, not verified home semantics. No source names or identifiers were printed or sent to web search.
- 2026-10-03: Claimed for a research sub-agent under the wayfinder/research workflow. Root owns all native UI interaction; research may request a controlled UI observation if documentation/source evidence is insufficient. Preserve a reproducible report and throwaway research branch pointer before resolving.
- 2026-10-03: [Draft source investigation](../research/home-thought.md) and [read-only aggregate probe](../research/inspect_home_thought.py) captured in managed worktree `C:\Users\stefa\.codex\worktrees\research-home-thought\brz2obsidian`, branch `codex/research-home-thought`, commit `e4a4a28`. The deterministic candidate key is standard UUIDv5(namespace=meta.BrainId, name=`"20"`), matching one live ordinary thought in each exact real archive and the original controlled export. The official API independently exposes `BrainDto.homeThoughtId`; it does not document the BRZ key derivation.
- 2026-10-03: Root observed native Home return from CHILD to PARENT in the controlled Brain, verifying the baseline correspondence. Changing Home to CHILD and exporting with PEER active remains pending a human step because the current native automation interface did not support the required held mouse modifier. Preserve the draft and keep this ticket claimed; do not assert the candidate's semantic proof or infer source fallback behavior before the controlled comparison. Proposed fresh output: `brz/controlled-home-child.brz`. No real Brain or original export was changed.
- 2026-10-03: The human set CHILD as Home and authorized the remaining steps. Root verified PEER active, exported a separate archive, then clicked Home and observed CHILD central with PARENT above it; the Home tooltip read CHILD. The new `brz/controlled-home-child.brz` is 6,976 bytes, SHA-256 `aa29d7aa0afb687f8b4ffdd490220c3c2e198c729681083fe5065b3bb55dfbf0`. Original fixture fingerprint was independently rechecked unchanged. The controlled comparison passed, with only numeric setting 20 changing Value, PARENT to CHILD, and PEER uniquely most recently activated. No private real source content was exposed.

## Answer

For the inspected exchange-format-5 archives, derive the home setting's `Id` with standard `uuid.uuid5(uuid.UUID(meta["BrainId"]), "20")`. Find that record in `settings.json`; its string `Value` is the designated home thought UUID. Resolve it against `thoughts.json.Id`, then join the same source identity to the single assigned vault target used by all internal links. The setting UUID differs per Brain because BrainId is its namespace; a fixed global UUID, title search, activation history, or hierarchy-root heuristic is not a substitute.

The derived key resolves one live ordinary thought in each exact real input. The controlled change verifies semantics: native Home selected CHILD after the human designated it, while the exported setting Value changed from PARENT to CHILD and PEER remained the uniquely latest activated thought. CHILD has PARENT as its ordinary parent and is not named Home. This separates explicit home designation from last activation, title, and parentlessness. The official API's explicit `BrainDto.homeThoughtId` corroborates home identity, but the BRZ numeric key derivation is observed reverse-engineering evidence rather than a published cross-version guarantee.

The initially generated Review Vault record reserves one target for each real home; A's home is selected and materialized, while B's home is outside that small slice. A full conversion must use the accepted trial's forced home note and root-level target assignment. Native home presentation, bookmark, startup, and rendering belong to the vault trial, not this source-format ticket.

All inspected source home settings are valid. Actual TheBrain fallback for absent, duplicated, malformed, or nonlive home references remains unobserved. The probe distinguishes those evidence states; its altered-record checks run only in memory and are not imported into TheBrain. Reporting, refusal, and explicit override policy remain for [Choose the conversion and failure contract](05-conversion-contract.md). Do not silently call a guessed graph root the source Home.

Evidence and reproduction: [Home-thought source evidence](../research/home-thought.md), [read-only aggregate probe](../research/inspect_home_thought.py), and the locally saved synthetic Home-result screenshot linked by the report. Captured on `codex/research-home-thought`, final commit `1cb330b6ecdf0561c7889f4d492eb81a12775419`, in managed worktree `C:\Users\stefa\.codex\worktrees\research-home-thought\brz2obsidian`. Safe report/probe copies are present in the primary repository. The probe passed with Windows Python 3.14.8, fixed fingerprints, and ZIP CRC checks; no production converter or private output is committed.
