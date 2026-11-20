"""Explicit one-source/pair audit orchestration; never a source-fact oracle.

    python -m tests.local_acceptance.audit_run --help

All network acquisition is opt-in through capture-api with an explicit loopback
origin and Brain. Ordinary audit reads only the selected retained evidence.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from contextlib import ExitStack
from pathlib import Path
from zipfile import ZipFile

from .api_baseline import prepare_controls
from .api_checker import audit_baseline, check_api_vault, source_facts
from .api_manifest import _audit_pass, audited, load_baseline
from .api_recording import ApiRecording, RecordingError, write_json
from .checker import check_run_result, check_vault, read_source
from .facts import classifications, member, relationships
from .scope import scope

ROOT = Path(__file__).resolve().parents[2]
_API_PROFILE_VERSIONS = ("1", "2", "3", "4", "5")
_CURRENT_API_PROFILE = "5"


def candidate_identity(expected):
    assert re.fullmatch(r"[0-9a-f]{40}", expected), "explicit candidate commit required"
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    assert actual == expected, "candidate commit differs from assessed checkout"
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    digest = hashlib.sha256()
    for name in sorted(set(paths) - {""}):
        path = ROOT / name
        digest.update(name.encode() + b"\0")
        digest.update(
            hashlib.sha256(path.read_bytes()).digest()
            if path.is_file()
            else b"<deleted>"
        )
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain", "-z"], cwd=ROOT)
    )
    return {"commit": actual, "content_sha256": digest.hexdigest(), "dirty": dirty}


def fingerprint(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def vault_identity(vault):
    vault = Path(vault)
    assert vault.is_dir() and not vault.is_symlink(), "regular selected vault required"
    rows = []
    for path in sorted(vault.rglob("*")):
        metadata = path.lstat()
        assert (
            not path.is_symlink()
            and not getattr(metadata, "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ), "vault aliases refuse audit"
        if path.is_file():
            rows.append(
                [
                    path.relative_to(vault).as_posix(),
                    path.stat().st_size,
                    fingerprint(path),
                ]
            )
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


@audited
def compare_pair(source, baseline, profile_version):
    """Compare raw identities/direct facts and actually measured payload bytes.

    Differences are observations, not forced source parity or shared history.
    """
    api_thoughts, api_relations, api_attachments, api_links = source_facts(
        baseline, profile_version=profile_version
    )
    with ZipFile(source) as archive:
        raw = scope(read_source(archive), archive)
        brz_items = {
            row["Id"]: row["Kind"] for row in raw["thoughts.json"] if row["Kind"] != 5
        }
        api_items = {key: row["kind"] for key, row in api_thoughts.items()}
        direct = {
            (row["definition_key"], key) for key, row in classifications(raw).items()
        }
        api_direct = {
            (row["typeId"], key) for key, row in api_thoughts.items() if row["typeId"]
        }
        kinds = relationships(raw)
        brz_tags = {
            (row["ThoughtIdA"], row["ThoughtIdB"])
            for row in raw["links.json"]
            if kinds[row["Id"]] == "tag"
        }
        api_tags = {
            (row["item_a"], row["item_b"])
            for row in api_relations.values()
            if row["kind"] == "tag"
        }
        brz_navigation = {
            (kinds[row["Id"]], row["ThoughtIdA"], row["ThoughtIdB"], row["Direction"])
            for row in raw["links.json"]
            if kinds[row["Id"]] in {"hierarchy", "related"}
        }
        api_navigation = {
            (row["kind"], row["item_a"], row["item_b"], api_links[key]["direction"])
            for key, row in api_relations.items()
            if row["kind"] in {"hierarchy", "related"}
        }

        def direct_comparison(name, brz, api):
            return {
                name + "_equal": brz == api,
                "brz_only_" + name: [list(row) for row in sorted(brz - api)],
                "api_only_" + name: [list(row) for row in sorted(api - brz)],
            }

        matches, differences = [], []
        for row in raw["attachments.json"]:
            outcome = baseline.data["payloads"].get(row["Id"])
            name = member(row)
            if (
                not outcome
                or outcome["status"] != 200
                or name not in archive.namelist()
            ):
                continue
            with archive.open(name) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            observed = hashlib.sha256(baseline.bytes(outcome["path"])).hexdigest()
            (matches if actual == observed else differences).append(row["Id"])
        return {
            "source_identities_equal": raw["meta.json"][0]["BrainId"]
            == baseline.json(baseline.data["brain"])["id"],
            "item_roles_equal": brz_items == api_items,
            **direct_comparison("direct_classifications", direct, api_direct),
            **direct_comparison("direct_tag_memberships", brz_tags, api_tags),
            **direct_comparison(
                "navigation_declarations", brz_navigation, api_navigation
            ),
            "brz_only_attachment_ids": sorted(
                {row["Id"] for row in raw["attachments.json"]} - api_attachments.keys()
            ),
            "api_only_attachment_ids": sorted(
                api_attachments.keys() - {row["Id"] for row in raw["attachments.json"]}
            ),
            "measured_payload_matches": sorted(matches),
            "measured_payload_differences": sorted(differences),
            "limits": "Each output is audited against its own observations; matching IDs do not assert byte parity, atomic acquisition, or API/BRZ history continuity.",
        }


def audit_selected(
    *,
    candidate,
    output,
    brz_source=None,
    brz_vault=None,
    brz_result=None,
    api_manifest=None,
    manifest_sha256=None,
    api_vault=None,
    api_result=None,
    profile_version=_CURRENT_API_PROFILE,
    output_version=9,
):
    """Audit only explicitly complete source/vault selections; retain a verdict.

    A development dirty tree is recorded truthfully with its immutable content
    hash. Formal candidate acceptance still requires its separate clean-commit
    receipts/review. This function never declares parent M5 acceptance.
    """
    output = Path(output)
    assert not output.exists(), "audit output must be new"
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "brz2obsidian.selected-source-audit/1",
        "outcome": "refused",
        "m5_acceptance": False,
        "audits": {},
    }
    stage = "selection"
    try:
        with ExitStack() as passes:
            assert bool(brz_source) == bool(brz_vault), (
                "complete BRZ selection required"
            )
            assert bool(api_manifest) == bool(manifest_sha256) == bool(api_vault), (
                "complete API selection required"
            )
            assert brz_source or api_manifest, (
                "at least one complete source selection required"
            )
            assert not brz_result or brz_source, "BRZ result requires BRZ selection"
            assert not api_result or api_manifest, "API result requires API selection"
            identity = candidate_identity(candidate)
            report["candidate"] = identity
            report["inputs"] = {}
            baseline = None
            for label, source, vault in (
                ("brz", brz_source, brz_vault),
                ("api", api_manifest, api_vault),
            ):
                if source is None:
                    continue
                stage = label + "-source-audit"
                vault = Path(vault)
                before_source, before_vault = fingerprint(source), vault_identity(vault)
                if label == "brz":
                    summary = check_vault(source, vault)
                else:
                    baseline = passes.enter_context(
                        _audit_pass(load_baseline(source, manifest_sha256))
                    )
                    raw_audit = audit_baseline(
                        baseline, profile_version=profile_version
                    )
                    summary = check_api_vault(
                        baseline, vault, profile_version=profile_version
                    )
                    report["api_source_audit"] = raw_audit
                    report["non_atomic_acquisition"] = True
                    if "http_responses" in baseline.data:
                        acquisition = baseline.json(baseline.data["http_responses"])
                        report["api_acquisition"] = {
                            key: acquisition[key]
                            for key in (
                                "acquisition_id",
                                "purpose",
                                "upstream_api_url",
                                "upstream_origin",
                                "effective_upstream_endpoint",
                            )
                        }
                record = json.loads((vault / "migration-record.json").read_bytes())
                assert record["schema_version"] == output_version and record[
                    "renderer_version"
                ] == str(output_version), "explicit audited output generation"
                result_path = brz_result if label == "brz" else api_result
                result_binding = {}
                if result_path:
                    result_bytes = Path(result_path).read_bytes()
                    result_binding = {
                        "result": str(Path(result_path).resolve()),
                        "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
                    }
                    if label == "api":
                        summary = summary | {
                            "notes": sum(
                                row["created"] for row in record["item_targets"]
                            ),
                            "files": sum(path.is_file() for path in vault.rglob("*")),
                            "category_notes": sum(
                                row["kind"] == 2
                                for row in source_facts(
                                    baseline, profile_version=profile_version
                                )[0].values()
                            ),
                            "warnings": len(record["issues"]),
                        }
                    check_run_result(json.loads(result_bytes), vault, summary)
                assert (
                    fingerprint(source) == before_source
                    and vault_identity(vault) == before_vault
                ), "source or output changed during audit"
                if baseline:
                    baseline.verify()
                report["inputs"][label] = {
                    "source": str(Path(source).resolve()),
                    "source_sha256": before_source,
                    "vault": str(vault.resolve()),
                    "vault_sha256": before_vault,
                } | result_binding
                report["audits"][label] = {"outcome": "qualified", "summary": summary}
            if brz_source and baseline:
                stage = "pair-comparison"
                report["pair_comparison"] = compare_pair(
                    brz_source, baseline, profile_version
                )
            stage = "final-input-binding"
            if baseline:
                baseline.verify()
            passes.close()
            for row in report["inputs"].values():
                assert (
                    fingerprint(row["source"]) == row["source_sha256"]
                    and vault_identity(row["vault"]) == row["vault_sha256"]
                ), "source or output changed during final comparison"
                if "result" in row:
                    assert fingerprint(row["result"]) == row["result_sha256"], (
                        "run result changed during audit"
                    )
            assert candidate_identity(candidate) == identity, (
                "candidate changed during audit"
            )
            report["outcome"] = "qualified"
    except Exception as error:  # noqa: BLE001 - retain a safe refusal for every failure
        report["failure"] = {
            "stage": stage,
            "kind": type(error).__name__,
            "message": "Selected audit refused; retained inputs require diagnosis. No complete M5 acceptance is claimed.",
        }
    write_json(output, report)
    return report


def capture_api(
    *,
    upstream,
    brain_id,
    attempt,
    vault,
    qualification,
    qualification_sha256,
    candidate,
    credential,
):
    """Public conversion plus independent raw evidence, then post-capture audit."""
    from brz2obsidian.application.wiring import local_api_workflow
    from brz2obsidian.sources.thebrain.local_api import (
        LocalApiConfig,
        LocalApiSourceRef,
    )

    attempt = Path(attempt)
    attempt.mkdir(parents=True, exist_ok=False)
    identity = None
    try:
        identity = candidate_identity(candidate)
        controls = load_baseline(qualification, qualification_sha256)
        recording = ApiRecording(
            attempt / "http",
            upstream,
            brain_id=brain_id,
            credential=credential,
            purpose="convert",
        )
        with recording:
            workflow = local_api_workflow(
                LocalApiConfig(api_url=recording.api_url),
                credentials=lambda: credential,
            )
            result = workflow.convert(LocalApiSourceRef(brain_id), vault)
            write_json(
                attempt / "result.json", result.model_dump(mode="json", by_alias=True)
            )
            policy = workflow.binding.policy
            profile_version = workflow.binding.source.profile_version
            if (
                profile_version not in _API_PROFILE_VERSIONS
                or policy.profile_id != "thebrain-local-api-reviewed"
                or policy.profile_version != profile_version
                or result.profile_id != policy.profile_id
                or result.profile_version != profile_version
            ):
                raise RecordingError("Public conversion profile binding differs")
            if result.outcome not in {"clean", "warnings"}:
                raise RecordingError(
                    "Public conversion did not publish a complete output"
                )
            recording.complete()
        baseline = recording.seal(qualification=controls)
        assert candidate_identity(candidate) == identity, (
            "candidate changed during acquisition"
        )
        return audit_selected(
            candidate=candidate,
            output=attempt / "audit.json",
            api_manifest=baseline.manifest_path,
            manifest_sha256=baseline.fingerprint,
            api_vault=vault,
            api_result=attempt / "result.json",
            profile_version=profile_version,
        )
    except Exception as error:  # noqa: BLE001 - retain a safe refusal for every failure
        report = {
            "schema": "brz2obsidian.selected-source-audit/1",
            "outcome": "refused",
            "m5_acceptance": False,
            "audits": {},
            "candidate": identity,
            "failure": {
                "stage": "api-capture",
                "kind": type(error).__name__,
                "message": "Acquisition did not qualify; retained attempt is incomplete.",
            },
        }
        write_json(attempt / "audit.json", report)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    controls = commands.add_parser(
        "prepare-controls",
        help="Materialize retained independent API3 qualification; no network or new native claim",
    )
    controls.add_argument("--directory", required=True, type=Path)
    audit = commands.add_parser(
        "audit",
        help="Audit one explicit BRZ/API source or pair; never grants M5 acceptance",
    )
    audit.add_argument("--candidate", required=True)
    audit.add_argument("--output", required=True, type=Path)
    for flag in (
        "brz-source",
        "brz-vault",
        "brz-result",
        "api-manifest",
        "api-vault",
        "api-result",
    ):
        audit.add_argument("--" + flag, type=Path)
    audit.add_argument("--manifest-sha256")
    audit.add_argument(
        "--profile-version", choices=_API_PROFILE_VERSIONS, default=_CURRENT_API_PROFILE
    )
    audit.add_argument("--output-version", type=int, choices=(7, 8, 9), default=9)
    capture = commands.add_parser(
        "capture-api",
        help="Explicit authorized loopback conversion/recording; credentials come only from environment",
    )
    for flag in ("api-url", "brain", "candidate", "qualification-sha256"):
        capture.add_argument("--" + flag, required=True)
    for flag in ("attempt", "vault", "qualification"):
        capture.add_argument("--" + flag, required=True, type=Path)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    if command == "prepare-controls":
        baseline = prepare_controls(**args)
        print(
            "Prepared retained control baseline: "
            + str(baseline.manifest_path)
            + "; SHA256 "
            + baseline.fingerprint
        )
        return 0
    if command == "capture-api":
        args["upstream"], args["brain_id"] = args.pop("api_url"), args.pop("brain")
        args["credential"] = os.environ.get("THE_BRAIN_LOCAL_API_KEY")
        result = capture_api(**args)
    else:
        result = audit_selected(**args)
    print(
        "Selected source audits: "
        + result["outcome"]
        + "; parent M5 acceptance remains separate."
    )
    return 0 if result["outcome"] == "qualified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
