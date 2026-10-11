# Domain Docs

## Layout and reading rules

This repo uses a single-context layout:

- `GLOSSARY.md` at the repo root defines domain vocabulary.
- `docs/adr/` holds architecture decision records.

Consult the glossary when domain terminology or behavior is relevant. Read
applicable ADRs when investigating or changing architecture, module boundaries,
or public interfaces.

When these documents are absent, proceed silently.
Create them through domain-modeling when terms or decisions
are resolved.

## Vocabulary

Use the glossary's terms when naming domain concepts in
issues, proposals, hypotheses, and tests.

If a needed concept is missing, reconsider the terminology
or note the gap for domain-modeling.

## ADR conflicts

Explicitly identify any proposal that contradicts an
existing ADR and explain why reopening it is warranted.
