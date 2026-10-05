# Evaluate the kepano reference vault against the migration requirements

Status: resolved
Type: research
Labels: wayfinder:research
Parent: [Find the route to version 2 for the Software Engineering Brain](../map.md)
Blocked by: none
Assignee: /root/v2_obsidian_research
Research branch: `research/brz-v2-kepano-patterns`

## Question

Which concrete conventions in Steph Ango's actual example vault support the user's proposed Thought Types → Categories → Templates → Properties/Links → Bases → Category Dashboards model, and what adaptations or unresolved decisions does our migration require?

Read the user's requested primary references:

- [How I use Obsidian](https://stephango.com/vault)
- [kepano example vault](https://github.com/kepano/kepano-obsidian)
- [Obsidian articles](https://stephango.com/topics/obsidian/)
- [TheBrain 15](https://www.thebrain.com/products/thebrain/thebrain15)

Inspect the actual repository at a recorded commit. Examine category notes, templates, frontmatter/property vocabulary and linked values, folder/naming conventions, ordinary relationships, `.base` filters, sort/group/columns/views, and dashboard embeds. Trace at least one complete concrete template → object note → linked category → Base → dashboard example. If the repository does not supply an actual object instance or another requested component, state that rather than fabricating a complete example. Separate actual files from the article's descriptions and the user's conceptual proposal.

Compare against our established evidence and requirements: seven supplied thought types and single source assignments, distinct source tags and hierarchy, explicit appearance overrides and qualified label/token behavior, existing deterministic identity/naming/preservation rules, native Obsidian use, empty/uncreated-target policy, and one-time fresh-vault migration. Determine what templates initialize versus actually enforce, what Bases compute versus alter in notes, whether source categories imply domain-specific fields, and how destination multiple categories differ from the archived source model. Keep post-migration editing/agent conventions distinct from building a new ongoing maintenance toolkit.

Produce a single concise source-cited findings asset under `../research/`, with pinned repository paths/commit, a concrete end-to-end trace, reusable conventions, candidate deliberate deviations and focused questions for the human. No design selection, user answers, schema invention, generated production vault or converter edits. Actual UI behavior remains for the disposable vault trial. Never upload private archives or include private thought titles, IDs, text or URLs.

## Comments

- 2026-10-04: Created and claimed after the user proposed the category/template/Base/dashboard architecture during type-representation grilling and explicitly required inspection of the actual reference implementation before design or implementation. Research resolves discoverable facts; the original grilling ticket remains claimed for the human's decisions.

## Answer

Resolved 2026-10-04. [Kepano reference patterns for version 2](../research/kepano-reference-patterns.md) records actual files at repository commit `473697347a0eaac790a6596229c741b3915f3b77`, the requested articles and TheBrain 15 page, a complete existing Book Template → object → Books category → Books Base → dashboard trace, and concrete migration adaptations. Research captured on `research/brz-v2-kepano-patterns`, commit `07bac7cfc561892654faab72ab3607d9ce84a14b`; the findings asset is integrated into the main checkout and checked against its Git blob.

- The reference implements linked categories, lightweight category dashboards, composable templates and reusable Bases with contextual views. Its pinned tree contains 21 category notes, 52 Markdown templates and 30 Bases with 75 views; grouping is not used there.
- Templates initialize metadata; property editor types and Bases do not enforce a category schema. No tracked agent/validation/maintenance toolkit exists in the reference.
- The reference's linked `type` taxonomy is separate from `categories`. Map-marker appearance reads the first type note's properties and requires the Maps community plugin; it neither defines category styling nor implements our evidenced member override rules.
- Deliberate adaptation is necessary for stable source identities/name collisions, source-specific versus destination category cardinality, metadata-only typed members, source-backed properties, canonical vocabulary and robust template exclusions. No category memberships, domain fields, title changes or tool scope were selected by the researcher.

Nineteen pinned file links and integrated local links were verified by the researcher, whose owned commit passed whitespace checks and left its worktree clean. Source facts and UI claims retain their prior evidence boundaries. No converter changes or native trial occurred. The current grilling ticket can now use the concrete findings to ask the human for the remaining representation decisions.

- Integration verification: report byte equality and committed provenance, local artifact links, valid blocker references and dependency acyclicity, and public source-identity/URL privacy checks all passed. The research worktree was submitted for recoverable archival after integration.
