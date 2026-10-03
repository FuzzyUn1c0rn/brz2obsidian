# Native first-version acceptance

Status: in progress

Ticket 10 coordinates native presentation acceptance and final usage guidance.
Independent full-source preservation already passed for all six exact/repeat/
reordered A/B conversions; see [the preservation report](real-export-acceptance.md).
The native reviewer is opening fresh copies of the actual accepted generated
vaults, retaining their pre-click originals and keeping private evidence under
ignored `brz/`. Confirmed native observations will be recorded here before the
native criteria are checked. No earlier prototype result supplies this gate.

## Documentation and library/CLI verification

On 2026-10-04, all three documented Python examples ran against the checked-in
synthetic archive through the default Workflow, explicit composition and direct
analyze/plan/render/publish interfaces. Each published a verified one-note vault.
Both console and module entry points passed text/JSON inspect and conversion,
planned/pending inspection and null actual counts, structured result round-trip,
nonempty-destination refusal, help and invalid arguments. Temporary owned
outputs were removed. Captured UTF-8 output used `PYTHONIOENCODING=utf-8`, now
documented for Windows scripts.

README, architecture, testing and source-coverage guidance reflect complete
reviewed v1 behavior, exact warning rules/refusals, intentional uncreated targets,
fresh destination restrictions, actual nested record schema, inward dependencies,
source/profile composition, public/private/native checks and version boundaries.
All 15 local documentation link destinations exist. No production code or
prose-mirroring tests were added by ticket 10.

The applicable public gates passed: 277 pytest tests, Ruff lint/format,
`pip check` and `git diff --check`, using the root project's `.venv` interpreter
with `PYTHONPATH` selecting the ticket worktree source. Runtime/environment
versions are recorded in [testing](../../../docs/testing.md#recorded-versions).
Overall implementation acceptance remains pending the actual native observations
and final integration review.
