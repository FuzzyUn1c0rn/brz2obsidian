# Reusable migration interfaces

`contracts.py` owns version-1 strict, closed, frozen Pydantic values. Nested
collections are tuples; original JSON is independently retained as immutable
source text and embedded directly in the record so numeric precision and
omission/null distinctions survive. Streams remain scoped outer resources.

Public operations are `SourceModule.open`, `core.analyze`, `core.plan`,
`obsidian.render`, `publication.publish`, and `Workflow.inspect/convert`.
Modules return durable contracts or raise `MigrationRefused`/`MigrationFailed`
with immutable issues. Workflow translates known failures into `RunResult`;
unexpected programming errors propagate. CLI alone presents text/JSON and
translates outcome to exit code. Importing generic modules does not eagerly
load concrete source, publication or CLI modules.

Source interpretation and payload access depend inward on contracts. Core
analysis/planning and Obsidian rendering perform no I/O. Publisher handles
owned staging, streamed copies, length/hash/manifest verification and fresh
destination publication. Workflow receives a `SourceModuleBinding`, renderer
and publisher; `application.wiring.default_workflow` selects the BRZ adapter.
Run metadata supplies time/version/bookmark facts to the pure renderer.

The initial adapter explicitly refuses relationships, tags, resources and
source-local reference adaptations. Later implementation slices extend those
features. This minimal profile is not full real-export coverage.
