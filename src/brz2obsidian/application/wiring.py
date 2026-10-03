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
