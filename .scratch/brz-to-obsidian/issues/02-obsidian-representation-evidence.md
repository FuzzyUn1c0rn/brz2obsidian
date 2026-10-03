# Establish what standard Obsidian can represent

Status: resolved
Type: research
Labels: wayfinder:research
Parent: [Find the route from a BRZ archive to an Obsidian vault](../map.md)
Blocked by: none
Assignee: /root/obsidian_evidence

## Question

What standard Obsidian mechanisms can represent a Brain's content, files, identities, and relationship meaning, and which limits must the vault design accommodate?

Investigate first-party Obsidian documentation for links and backlinks, relationship labels versus graph behavior, aliases and properties, Markdown content, attachments and embeds, file paths, duplicate titles, forbidden filename/link characters, and portable vault organization. Explain viable options and their consequences without selecting the final representation on the user's behalf.

The baseline must work without community plugins. Distinguish readable semantic relationship sections or metadata from behavior that Obsidian's native graph actually supports. Clarify which claims are documented and which need a small local trial.

Save a concise source-cited findings asset under `../research/`. No account setup, plugin installation, or external upload of the user's archive is needed.

## Comments

- 2026-10-03: The user selected standard Obsidian as the baseline, accepting different navigation while requiring preservation of relationship meaning.

## Answer

Resolved on 2026-10-03. [Standard Obsidian representation evidence](../research/obsidian-representation.md) records the primary sources, viable options, portability constraints, and required local trials. Research was captured on `research/obsidian-representation`, commits `f2cd38be185957ee48b73038e0c8f7808566ef52` and `6dc5a82ef289c9efcf06ae2e215d5051d3e681b8`, and integrated into the main checkout.

- Standard Obsidian can preserve readable relationship meaning in note sections or flat linked properties. Its documented native Graph represents written internal links; it does not expose a typed-edge model. Inverse navigation links affect displayed direction. Canvas offers a separate optional view with labeled directed connections.
- Original names and source IDs can be retained independently of filenames. Naming must account for Windows restrictions, case collisions, Obsidian link syntax, and full destination-path length.
- Archived files can remain available even when Obsidian cannot preview their format. Markdown/HTML appearance, attachments, quoted property links, and nested-folder link resolution need a representative vault trial.
- Documentation establishes mechanisms and limitations. The final note identity, relationship representation, filename policy, attachment organization, and optional views remain decisions for [Choose note identity, relationships, and vault layout](03-vault-model.md).
