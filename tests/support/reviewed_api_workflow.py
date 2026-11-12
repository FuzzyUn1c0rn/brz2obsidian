"""Explicit historical API workflow compositions for retained test contracts."""

from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain.local_api import (
    LOCAL_API_POLICY_V3,
    LOCAL_API_POLICY_V4,
    LocalApiSourceModule,
)


def reviewed_api_workflow(config=None, *, credentials=None, profile_version):
    policy = {"3": LOCAL_API_POLICY_V3, "4": LOCAL_API_POLICY_V4}[profile_version]
    module = LocalApiSourceModule(
        config, credentials=credentials, profile_version=profile_version
    )
    workflow = Workflow(
        SourceModuleBinding(module, policy), ObsidianRenderer(), FilesystemPublisher()
    )
    metadata_factory = workflow.metadata_factory
    workflow.metadata_factory = lambda: module.run_metadata(metadata_factory())
    return workflow
