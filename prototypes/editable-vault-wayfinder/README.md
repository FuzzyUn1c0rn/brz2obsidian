# Editable-vault Wayfinder prototypes

This directory retains runnable, synthetic prototype sources on
`codex/editable-vault-wayfinder`, as requested for the
[editable-vault Wayfinder map](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/239).
The branch starts at `e9b5148f6446719db57e41f1f80ec5c5bd4673a4`,
after committing the agreed glossary and architecture decisions.

These are planning artifacts. Their behavior and presentation remain proposals
until the user approves the relevant scope in the owning GitHub ticket.
Production implementation is outside this map.

## Working arrangement

- The coordinator owns issue claims, dependencies, publication, commits and
  integration on this branch.
- Independent agents may prepare unblocked tickets in parallel. They work in
  separate subdirectories and do not switch branches or mutate shared Git state.
- Human decisions, design selection and acceptance remain with the user.
- GitHub Issues remain authoritative for requirements, decisions and map status.
- Source files and instructions needed to reproduce these prototypes are retained
  here. Generated vaults, repositories, browser captures and disposable execution
  evidence stay under `tmp/merge-wayfinding/`. Private user content is not used.

## Initial work

- `gui/`: graphical import and update review variants; synthetic state and writes.
- `categories/`: synthetic category and link-preservation scenarios.

The Git recovery prototype remains blocked until the initial repository-support
matrix is agreed. No prototype demonstrates production readiness merely by
running or receiving a design verdict.
