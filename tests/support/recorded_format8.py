"""Select format 8 explicitly for historical conversion and update controls."""

from brz2obsidian.application.wiring import default_workflow


def format8_workflow(workflow=None):
    workflow = default_workflow() if workflow is None else workflow
    metadata = workflow.metadata_factory
    workflow.metadata_factory = lambda: metadata().model_copy(
        update={"renderer_version": "8"}
    )
    return workflow
