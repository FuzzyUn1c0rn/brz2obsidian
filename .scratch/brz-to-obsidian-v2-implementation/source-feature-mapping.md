# Source features and version 2 vault representation

This comparison accompanies the [implementation specification](spec.md). It records accepted behavior; it is not a completed converter-output audit. All three supplied archives use the same TheBrain version. Later releases may add features exposed by further archives.

| Source feature or observed difference | Obsidian representation / preservation | Boundary or limitation | Spec stories |
| --- | --- | --- | --- |
| Home thought and existing navigation | Original Home remains the entry/bookmark, with category navigation added; Parents/Children/Related and native discovery remain available | No unique-root/tree assumption; directional detail remains evidence | 5, 11–12, 23 |
| Ordinary authored Markdown, code, blockquotes and line endings | Adapt only supported source-local spans; exact original backups and remaining authored text retained | Unreviewed source-local/rich semantics still refuse | 6–10, 52–53, 61–63 |
| Seven thought types and 195 assignments | Faithful category dashboards and real notes for every typed member; linked category properties | Validate field/link correspondence; no category inference or subtype inheritance | 15–22 |
| Typed members without substantive content | Metadata-bearing notes discoverable in Bases | Untyped empty items keep v1 selection/intentional-uncreated behavior | 12, 17 |
| Definition-owned content/resources | Category notes retain their own content and assets | No inherited definition prose or file duplication into members | 21 |
| Type/default icons and one actual member-owned override | Dynamic Base images with explicit appearance provider; member image overrides; body-icon snapshots | Empty provider opts out; invalid provider reported without reselection; body images remain separately editable | 24–32 |
| Source colours, labels and opaque icon tokens | Declared colour facts and raw encoding retained in the migration record; own labels preserved in notes | No foreground/background colour properties in notes, templates, Bases or native property configuration; no decorative Appearance display, inferred member label or token grammar | 26, 33, 44, 61 |
| Source tags and tag assignments | Existing native tags and hidden-membership handling | Tags, categories and ordinary relationships remain distinct; source tag name cannot create a dashboard role | 13, 20, 44 |
| Multiple parents, title collisions, hierarchy/jumps and volume | Existing deterministic identity/naming/graph policy, evaluated with typed materialization included | Full-archive interaction audits required; counts alone insufficient | 11–14, 17, 73 |
| System-to-type connections | Relationship evidence retained in migration record | No invented visible hierarchy/navigation | 22, 61–62 |
| One nonempty Type-1/NoteType-0 canonical thought note | Active Markdown plus exact original backup and supported local-image adaptation | Sole unambiguous candidate with normal integrity checks; arbitrary Markdown attachments not promoted | 52–53 |
| Four zero-length absent TXT declarations | Per-record source-gap warnings and existing-owner notices; exact declarations/PDF association retained | Exact zero-length/state/identity-associated PDF rule; no fabricated TXT or local link | 54, 56, 62–63 |
| Earlier positive-length missing TXT and icon-length discrepancies | Existing narrowly approved warning rules retained | Missing/unreliable required payloads outside the rules remain fatal | 55, 63, 73 |
| Intact PDFs and ordinary files/images | Byte-preserved local assets and normal native resource viewing | Vault Search lacks the evidenced PDF body-search behavior; no extraction/indexing requirement | 8–9, 56–57 |
| Four video URL resources with VideoHtml | Exact usable URLs, retained metadata and native reviewed YouTube/timing presentation | No arbitrary iframe execution/download; network/service availability explicit | 58–60 |
| New display timestamp, settings 41/46/58/62/101, string booleans, history codes 203/204/304/807, position and omission/scalar variations | Every original field/value/history record retained as evidence | No undocumented meaning or display-time-to-updated substitution | 41–42, 61 |
| Source creation/overall modification timestamps | Calendar-date properties with full original strings retained independently | No timezone inference, precision destruction or text-only modification claim | 40–43 |
| Empty events/access/custom-field collections and unexercised type hierarchy/link features | Existing strict source boundary remains | Absence does not establish support; nonempty unreviewed meanings refuse | 62–63 |
| Future user-authored objects | Generic/category templates, canonical properties, native membership edits and starter recipe | No fabricated imported IDs or inferred semantic fields; no additive templates | 34–48 |
| Category renames and shortened native links | Contextual dashboard queries and unambiguous link resolution | Member views entered through dashboards; ambiguous required references reported without repair | 49–51, 67–69 |
| Editable vault conventions | Source-independent read-only library/CLI checker | Custom properties and intentional ordinary uncreated targets allowed; separate from migration audit | 66–72 |
| Existing library/CLI/publication behavior | Reused workflow and thin CLI; explicit v2 schema versions and verified fresh publication | No merge/sync/overwrite or count-only success claim | 2–4, 14, 63–65, 78 |
| Complete delivery | Synthetic public tests, independent exact/repeat/reordered audits for all three archives and native actual-output review | Prototype is prior evidence; final user acceptance still required | 1, 73–82 |

Private input identities, payloads, thought content and native screenshots stay under ignored local storage. [Accepted source comparison](../brz-to-obsidian-v2/research/source-differences.md) and [controlled source evidence](../brz-to-obsidian-v2/research/native-source-behavior.md) distinguish established semantics from unknown causes.
