import json

from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from brz2obsidian.sources.thebrain.local_api import (
    LOCAL_API_POLICY_V4,
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import BRAIN, KEY, api_server
from tests.support.local_api_payloads import RichPayloadApi, assert_published_payloads


def test_explicit_profile4_preserves_inherited_resources_and_direct_default(tmp_path):
    assert LocalApiSourceModule().profile_version == "1"
    with api_server(RichPayloadApi(jpeg=True)) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        workflow = Workflow(
            SourceModuleBinding(module, LOCAL_API_POLICY_V4),
            ObsidianRenderer(),
            FilesystemPublisher(),
        )
        metadata = workflow.metadata_factory
        workflow.metadata_factory = lambda: module.run_metadata(metadata())
        assert workflow.binding.policy.profile_version == "4"
        assert workflow.binding.source.profile_version == "4"
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
        assert result.receipt.verified
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert record["profile_version"] == "4"
    assert_published_payloads(tmp_path / "vault", jpeg=True, expected_profile="4")
