# Complete real-export preservation acceptance

Verified locally on 2026-10-04 against the exact A/B fingerprints recorded in [BRZ preservation evidence](../../brz-to-obsidian/research/brz-preservation.md). All six complete conversions succeeded with exit code 2: each exact input, a second conversion, and an equivalent archive with reversed ZIP member and root-record order. No unexplained discrepancy or additional warning allowance was accepted. Standard automated tests use only synthetic inputs.

| Independently checked result | A | B |
| --- | ---: | ---: |
| Source thoughts, including retained system items | 76 | 58 |
| Original JSON records across all 13 root collections | 1,712 | 806 |
| Thought-note files, including root Home | 49 | 42 |
| Ordinary / authored tag notes | 48 / 1 | 42 / 0 |
| Hierarchy-only selections | 5 | 2 |
| Reserved uncreated ordinary / tag targets | 15 / 11 | 16 / 0 |
| Present byte-preserved payloads | 60 | 50 |
| Original thought-note backups (included above) | 43 | 34 |
| Canonical local authored references | 68 | 12 |
| Source relationship records | 129 | 57 |
| Hierarchy / Related / tag / retained system relationships | 67 / 4 / 47 / 11 | 56 / 1 / 0 / 0 |
| Native / uncreated tag assignments | 39 / 8 | 0 / 0 |
| Exact permitted warning items / owners | 2 / 2 | 9 / 7 |
| Actual vault files, including supporting files | 114 | 96 |

A's two warnings are present, CRC-valid icons whose actual length differs from the declared length. B's nine warnings meet every absent-TXT conjunct and have intact archived PDFs under seven respective owners. The oracle verifies source role, ownership, extension, declared length, file state, absence/presence, actual byte length/digest, same-owner PDF evidence and warning disposition. It makes no claim about TXT purpose or particular PDF pairing.

The conditional Tag memberships listing is present only for A's hidden memberships and unused source tags. Neither input needs an Uncreated targets listing: accepted hierarchy, Related, tag or authored links already represent every otherwise eligible empty ordinary target. All reserved targets remain distinct, absent files with valid assigned paths. Every native bookmark and startup setting points to the assigned root Home.

## Independent oracle and corruption proofs

[checker.py](../../../../tests/local_acceptance/checker.py) imports only Python standard-library modules. It reads each archive directly, checks ZIP CRCs, independently parses all root records using exact decimal numbers and rejection of duplicate/nonfinite JSON, and compares every retained record/field in source order. Object comparison preserves omission versus null, number precision, boolean/string types, raw timestamps, identity, uninterpreted metadata, settings and historical records. Every physical payload and original-note backup is compared directly byte-for-byte with its archived member; converter hashes and manifests do not supply expected bytes.

Source facts independently establish Home, content eligibility, the agreed greedy hierarchy cover, all nonsystem identity/target assignments, safe names and path limits, flat tag tokens, every accepted relationship and membership. A separate source syntax scanner derives reference targets/spans from decoded original Markdown; it does not consume the converter's spans or import its Markdown parser. It masks code/comments, handles paragraph continuations, and fails if it cannot establish coverage of an active local form. This is an acceptance oracle for these inputs and the synthetic proof cases, not a replacement general Markdown parser.

Every created thought-note byte is checked against the independent expected heading/label, tag frontmatter, original Markdown with only approved local-link edits, resource links/notices and complete deduplicated graph sections. The oracle checks every emitted span/digest/target against its independent scan, every actual local wiki/image destination, every conditional listing, native configuration/bookmark, source-accounting entry, original-evidence identity, attachment assignment/finding and actual file inventory. Structured results and receipts are then audited against the real files and independent totals, rather than trusted as the preservation oracle.

The ordinary suite includes 22 synthetic checker proofs. Deliberate corruptions cover payload bytes, added-null versus omission, changed dates/numbers and decimal rounding, authored text, Home, identity assignments, graph links, native tags, resource links, source spans, warning observations, accounting, conditional listings, unexpected files, logical repeat data, bookmark paths, claimed counts and receipt omissions.

## Reproducibility boundary

Repeated and reordered runs retain identical selections, assigned note/resource paths, every note/report/listing/configuration byte, all copied bytes, graph/tag presentation and logical migration-record data. Native bookmark `ctime` and explicit run `run_id`, `run_time`, `bookmark_time` may differ. Reordered ZIPs necessarily change the source fingerprint and snapshot digest, original record sequence and source-order evidence/accounting pointers; these are separately verified against each reordered archive. Relationship/adaptation list order is compared logically. No other field or generated content difference is allowed.

The original accepted A/B vaults remain in ignored local storage before native review. Open fresh copies for Obsidian checks so application configuration writes and click-to-create do not alter preservation evidence. Private filenames, source IDs/titles/text, archives, structured run results, reordered inputs and generated vaults are not committed.

## Reproduce on native Windows

Use the project virtual environment. In a separate worktree, replace the relative interpreter commands below with the full path to the integration checkout's `.venv\Scripts\python.exe`. From a worktree, set `PYTHONPATH` to that worktree's `src`; from the integration checkout, the editable install already selects its source. Set `$sourceA` and `$sourceB` to the exact fingerprinted local archives and choose a new, short, ignored output directory. The driver refuses an existing output directory, creates six fresh vaults, saves private results alongside them and prints only aggregate counts.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:PYTHONIOENCODING = 'utf-8'
$sourceA = 'C:\path\to\exact-A.brz'
$sourceB = 'C:\path\to\exact-B.brz'
$output = 'C:\short\ignored\new-acceptance-run'
.\.venv\Scripts\python.exe -m tests.local_acceptance.run --source-a $sourceA --source-b $sourceB --output $output
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check --no-cache .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
```

The full applicable public suite passed: 277 tests, including workflows, source/core/renderer/publication seams, failure protection, alternate-source substitution, installed/module CLI behavior, dependency direction and these independent checker proofs. Ruff lint/format and `pip check` passed. The private checker additionally passed on all six vaults and their actual structured receipts. Private input availability and Obsidian GUI access are not required by ordinary pytest.

Native environment: Windows, Python 3.14.8; Pydantic 2.13.5 with pydantic-core 2.46.5; markdown-it-py 4.2.0 with mdurl 0.1.2; pytest 9.1.1; Ruff 0.16.10; setuptools 84.0.0; pip 26.2.1. Obsidian 1.13.7 native presentation acceptance is recorded separately in ticket 10; this report proves preservation independently of its GUI.

## Final repair acceptance

On 2026-10-04, all six exact/repeat/reordered conversions passed again after final review repairs were integrated at `93cdcce`. Every independently checked count above remained unchanged. Final public gates passed with 295 tests, Ruff lint/format and pip check. Direct comparison with the earlier native-reviewed pristine A/B output found unchanged assigned paths, rendered notes/reports/listings/configuration, resource bytes and logical mappings, except permitted run metadata/bookmark time. All 114/96 pristine file hashes and inventories remained unchanged. See [final review closure](final-review.md#final-closure); no unexplained discrepancy or additional warning allowance was introduced.
