"""Default concrete composition. Generic modules never import this file."""

from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from brz2obsidian.sources.thebrain.reader import BrzSourceModule

from .workflow import SourceModuleBinding, Workflow


def default_workflow():
    return Workflow(
        SourceModuleBinding(BrzSourceModule(), BRZ_POLICY),
        ObsidianRenderer(),
        FilesystemPublisher(),
    )


def local_api_workflow(config=None, *, credentials=None):
    from brz2obsidian.sources.thebrain.local_api import (
        LOCAL_API_POLICY,
        LocalApiSourceModule,
    )

    module = LocalApiSourceModule(config, credentials=credentials)
    workflow = Workflow(
        SourceModuleBinding(module, LOCAL_API_POLICY),
        ObsidianRenderer(),
        FilesystemPublisher(),
    )
    metadata_factory = workflow.metadata_factory
    workflow.metadata_factory = lambda: module.run_metadata(metadata_factory())
    return workflow
