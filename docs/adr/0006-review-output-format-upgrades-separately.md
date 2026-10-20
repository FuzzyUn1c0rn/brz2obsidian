---
status: accepted
---

# Review output-format upgrades separately from source updates

A newer converter can change generated headings, properties and dashboard layouts
without any change to the source collection. Treat output-format upgrades as a
separate, explicitly reviewed operation so users can distinguish changes to their
knowledge from changes to its generated presentation. This accepts the cost of
format compatibility and upgrade handling to avoid silently mixing presentation
changes into source updates; the supported-version strategy requires technical
validation.
