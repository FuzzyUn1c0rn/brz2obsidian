import json

from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from tests.support.local_api import BRAIN, KEY, api_server
from tests.support.local_api_payloads import RichPayloadApi, assert_published_payloads


def test_standard_profile3_preserves_inherited_resources_and_direct_default(tmp_path):
    assert LocalApiSourceModule().profile_version == "1"
    with api_server(RichPayloadApi(jpeg=True)) as (_, address):
        workflow = local_api_workflow(
            LocalApiConfig(api_url=address), credentials=lambda: KEY
        )
        assert workflow.binding.policy.profile_version == "3"
        assert workflow.binding.source.profile_version == "3"
        inspected = workflow.inspect(LocalApiSourceRef(BRAIN))
        assert inspected.outcome == "clean", inspected.issues
        result = workflow.convert(LocalApiSourceRef(BRAIN), tmp_path / "vault")
        assert result.outcome == "clean", result.issues
        assert result.receipt.verified
    record = json.loads((tmp_path / "vault/migration-record.json").read_bytes())
    assert record["profile_version"] == "3"
    assert_published_payloads(tmp_path / "vault", jpeg=True)
