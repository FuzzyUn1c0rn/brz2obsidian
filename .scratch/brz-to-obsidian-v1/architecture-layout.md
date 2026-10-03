# Initial source and test folder layout

Accepted: 2026-10-03 as part of the [migration specification](spec.md).

This preserves the user's requested initial code-layout proposal. The reusable module interfaces and inward dependency rules in the specification are authoritative; internal file boundaries may evolve without changing those interfaces.

```text
src/brz2obsidian/
  __init__.py
  __main__.py
  contracts.py
  core/__init__.py
  core/analysis.py
  core/planning.py
  sources/thebrain/__init__.py
  sources/thebrain/reader.py
  sources/thebrain/decoding.py
  sources/thebrain/notes.py
  sources/thebrain/profile.py
  obsidian/__init__.py
  obsidian/rendering.py
  publication/__init__.py
  publication/filesystem.py
  application/__init__.py
  application/workflow.py
  application/wiring.py
  cli.py
tests/{core,sources,obsidian,publication,application,cli,fixtures,local_acceptance}/
docs/{architecture.md,testing.md}
pyproject.toml
README.md
```

The source package interprets TheBrain BRZ and supplies normalized facts and a reviewed profile. Contracts and pure core analysis/planning have no dependencies on outer implementations. The Obsidian renderer generates bytes without I/O; publication manages streamed copies, validation, and destination changes. The generic workflow composes interfaces; the wiring module selects concrete implementations; the CLI is a replaceable outer entry interface.

The test-only alternate source belongs in test support. Public fixtures are synthetic. Full real-source acceptance is explicitly selected and uses private local inputs. No source package, tests, or package configuration has been created by this layout proposal.
