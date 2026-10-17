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
        LOCAL_API_POLICY_V3,
        LocalApiSourceModule,
    )

    module = LocalApiSourceModule(config, credentials=credentials, profile_version="3")
    workflow = Workflow(
        SourceModuleBinding(module, LOCAL_API_POLICY_V3),
        ObsidianRenderer(),
        FilesystemPublisher(),
    )
    metadata_factory = workflow.metadata_factory
    workflow.metadata_factory = lambda: module.run_metadata(metadata_factory())
    return workflow


def validate_api_config(values):
    from brz2obsidian.sources.thebrain.local_api import LocalApiConfig

    try:
        return LocalApiConfig(**values)
    except ValueError, TypeError:
        raise ValueError(
            "Use a permitted local API address and valid bounded acquisition settings"
        ) from None


def selected_api_workflow(selection, credentials=None):
    from brz2obsidian.sources.thebrain.local_api import LocalApiSourceRef

    return local_api_workflow(
        validate_api_config(selection.config.model_dump()), credentials=credentials
    ), LocalApiSourceRef(selection.brain_id)


def list_api_brains(config, credentials=None):
    from brz2obsidian.sources.thebrain.local_api import LocalApiSourceModule

    return LocalApiSourceModule(
        validate_api_config(config.model_dump()), credentials=credentials
    ).list_brains()
