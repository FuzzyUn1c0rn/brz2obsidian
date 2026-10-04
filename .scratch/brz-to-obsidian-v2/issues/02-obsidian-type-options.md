# Establish Obsidian options for types and inherited appearance

Status: resolved
Type: research
Labels: wayfinder:research
Parent: [Find the route to version 2 for the Software Engineering Brain](../map.md)
Blocked by: none
Assignee: /root/v2_obsidian_research
Research branch: `research/brz-v2-obsidian-options`

## Question

Which native Obsidian mechanisms can preserve type definitions, type assignments and the shared appearance described by the user, and where would an adaptation or optional extension be necessary?

Start from the version 1 Obsidian evidence, verify current first-party documentation and distinguish source meaning from destination behavior. Investigate linked properties, ordinary definition notes, tags, search, Backlinks, Graph groups, Bases, templates, embeds and native CSS mechanisms where relevant. Explain whether a mechanism stores membership, makes it discoverable, displays a colour/icon, or actually supplies inherited behavior. Distinguish type membership from tag membership and hierarchy. Check limitations affecting multiple assignments, links in properties, uncreated definition targets, visual overrides and portable vault configuration.

Present a small comparison of viable options and their consequences. The baseline uses standard Obsidian; identify any optional extension as a separate dependency, without installing it or selecting it for the user. Mark undocumented behavior as needing a disposable native trial. Do not claim Obsidian has a class system or live appearance inheritance merely because properties can store the source facts.

Save one source-cited findings document under `../research/`, with exact first-party links and date checked. This evidence ticket can proceed before the complete source inventory because its question is already specified; source-specific candidate mappings remain provisional until that inventory is available.

## Comments

- 2026-10-04: Created during charting. Research describes available mechanisms; the human chooses the desired conversion behavior later.
- 2026-10-04: Claimed before documentation research. Source-specific mappings will be considered only after the complete source evidence is available.

## Answer

Resolved on 2026-10-04. [Obsidian options for thought types and shared appearance](../research/obsidian-type-options.md) records the options, exact first-party sources and native trials still needed. Captured on `research/brz-v2-obsidian-options`, commit `6938f9eec83b16302a1f65dbae3d5da6806982f3`; the findings asset is integrated into this checkout. All 20 cited official URLs were checked, and the branch's staged whitespace check passed.

- Native linked properties and definition notes can record assignments and preserve definition content. Search, tags, Backlinks and Bases offer discovery mechanisms, with different treatment of membership versus ordinary links.
- Graph groups, CSS, embeds and Bases-derived images/icons offer possible appearance adaptations. The documentation does not establish general note-property inheritance or TheBrain's override rules; each proposed surface needs a representative native trial.
- Type-only members and uncreated definitions may force reconsideration of version 1's note-materialization policy. Source assignment cardinality must come from source evidence rather than Obsidian's ability to hold a list.
- Remote iframe/YouTube embeds are documented options, subject to site and sanitization limits. A URL or iframe is not an archived offline video, and source attributes need verification if retained.
- No design, extension dependency or generated vault configuration was selected. [Choose how thought types and inherited appearance translate into the vault](03-thought-type-representation.md) owns the human decision after source evidence is available.
