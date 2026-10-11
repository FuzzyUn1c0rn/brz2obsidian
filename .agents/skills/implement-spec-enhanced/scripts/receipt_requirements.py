"""Independent stage requirements and runner receipt validation for v2 handoffs."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from validate_handoff import commit, evidence, load, require, source_reference, text

CHECK_IDS = {"pytest", "lint", "format", "dependency"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON field {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def requirements(data, stage, ticket, candidate_commit, assessed_commit):
    require(isinstance(data, dict), "requirements must be an object")
    fields = {
        "schema_version",
        "ticket",
        "stage",
        "candidate_commit",
        "assessed_commit",
        "environment",
        "checks",
    }
    require(data.keys() == fields, "requirements have missing or unknown fields")
    require(
        type(data["schema_version"]) is int and data["schema_version"] == 1,
        "unsupported requirements schema_version",
    )
    source_reference(data["ticket"], "requirements.ticket")
    require(data["ticket"] == ticket, "requirements ticket mismatch")
    require(data["stage"] == stage, "requirements stage mismatch")
    for key, expected in (
        ("candidate_commit", candidate_commit),
        ("assessed_commit", assessed_commit),
    ):
        commit(data[key], f"requirements.{key}")
        require(data[key] == expected, f"requirements {key} mismatch")
    require(data["environment"] in ("base", "gui"), "invalid requirements environment")
    require(isinstance(data["checks"], list), "requirements checks must be an array")
    identities = set()
    for check in data["checks"]:
        require(isinstance(check, dict), "required check must be an object")
        require(check.get("id") in CHECK_IDS, "unknown required runner check ID")
        require(
            type(check.get("fresh")) is bool, "required check fresh must be boolean"
        )
        environment = check.get("environment", data["environment"])
        require(environment in ("base", "gui"), "invalid required check environment")
        allowed = {"id", "fresh", "environment", "requirement_key"}
        if "requirement_key" in check:
            require(text(check["requirement_key"]), "requirement_key must be nonempty")
        if check["id"] == "pytest":
            pytest_fields = {"scope", "selectors", "keyword", "marker", "require_gui"}
            allowed |= pytest_fields
            require(
                pytest_fields <= check.keys(),
                "pytest requirements need explicit scope and selectors",
            )
            require(
                check["scope"] in ("full", "focused"), "invalid required pytest scope"
            )
            require(
                isinstance(check["selectors"], list)
                and all(text(item) for item in check["selectors"]),
                "invalid required pytest selectors",
            )
            require(
                all(
                    check[key] is None or text(check[key])
                    for key in ("keyword", "marker")
                ),
                "invalid required pytest expressions",
            )
            require(type(check["require_gui"]) is bool, "require_gui must be boolean")
            require(
                check["scope"] != "full"
                or not (check["selectors"] or check["keyword"] or check["marker"]),
                "full pytest requirement cannot have focused selectors",
            )
        require(not check.keys() - allowed, "unknown required check fields")
        identity = (check["id"], environment, check.get("requirement_key"))
        require(identity not in identities, "duplicate required runner check")
        identities.add(identity)
    return data


def digest(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def bind(record, data):
    requirements(
        data,
        record["kind"],
        record["ticket"],
        record["candidate_commit"],
        record.get("integration_commit", record["candidate_commit"]),
    )
    record["check_requirements"] = data
    record["check_requirements_sha256"] = digest(data)


def validate_record(
    record,
    bundle,
    checkout,
    expected=None,
    *,
    carried=False,
    prior_stage=False,
    reuse_reason=None,
):
    declaration = record.get("check_requirements")
    requirements(
        declaration,
        record["kind"],
        record["ticket"],
        record["candidate_commit"],
        record.get("integration_commit", record["candidate_commit"]),
    )
    require(
        record.get("check_requirements_sha256") == digest(declaration),
        "check requirements digest mismatch",
    )
    if expected is not None:
        requirements(
            expected,
            record["kind"],
            record["ticket"],
            record["candidate_commit"],
            record.get("integration_commit", record["candidate_commit"]),
        )
        require(
            expected == declaration or carried,
            "independent check requirements mismatch",
        )
    effective = expected if expected is not None else declaration
    require(
        text(record.get("assessed_checkout"))
        and Path(record["assessed_checkout"]).is_absolute(),
        "v2 assessed_checkout must be absolute",
    )
    if not prior_stage and not carried:
        require(
            Path(record["assessed_checkout"]).resolve() == checkout.resolve(),
            "assessed checkout mismatch; explicit carry or reuse required",
        )
    for item in record["checks"]:
        kind = item.get("kind")
        require(
            kind in ("manual", "runner", "historical"),
            "v2 check requires kind: manual, runner, or historical",
        )
        if kind != "manual":
            require(item.get("check_id") in CHECK_IDS, "unknown runner check_id")
        if kind == "historical":
            require(
                item["status"] == "reused",
                "historical evidence must retain reused status",
            )
            historical(item, bundle)
    used = set()
    for needed in effective["checks"]:
        environment = needed.get("environment", effective["environment"])
        matches = [
            item
            for item in record["checks"]
            if item.get("kind") in ("runner", "historical")
            and item.get("check_id") == needed["id"]
            and item.get("environment", effective["environment"]) == environment
            and item.get("requirement_key") == needed.get("requirement_key")
        ]
        require(
            len(matches) == 1,
            f"missing required runner check or duplicate result: {needed['id']} ({environment})",
        )
        item = matches[0]
        require(
            not needed["fresh"]
            or (
                item["status"] != "reused"
                and item["kind"] != "historical"
                and not carried
            ),
            "required fresh execution cannot use reused evidence",
        )
        if item["status"] == "unavailable" and item.get("receipt"):
            require(
                text(item["receipt"]) and (bundle / item["receipt"]).is_file(),
                "unavailable check receipt evidence is missing",
            )
        if (
            item["kind"] == "runner"
            and item["status"] != "unavailable"
            and (item["status"] in ("passed", "reused") or item.get("receipt"))
        ):
            validate_receipt(
                item,
                needed,
                environment,
                bundle,
                checkout,
                record,
                carried=carried,
                prior_stage=prior_stage,
                reuse_reason=reuse_reason,
            )
            used.add(id(item))
    # Even additional success claims must have intact receipts; unrequired text
    # claims cannot sneak into PASS as runner evidence.
    for item in record["checks"]:
        if (
            item.get("kind") == "runner"
            and item["status"] in ("passed", "reused")
            and id(item) not in used
        ):
            require(False, "runner success check must have an independent requirement")


def historical(item, bundle):
    require(text(item.get("source_record")), "historical reuse requires source_record")
    require(
        type(item.get("source_check")) is int and item["source_check"] >= 0,
        "historical reuse requires source_check index",
    )
    source_path = (bundle / item["source_record"]).resolve()
    source = read_json(source_path)
    require(
        isinstance(source, dict)
        and type(source.get("schema_version")) is int
        and source["schema_version"] == 1,
        "historical source must be a published v1 record",
    )
    kind = source.get("kind")
    require(
        kind in ("candidate", "verification", "integration")
        and source_path.name == f"{kind}.json",
        "historical source must name the original published record",
    )
    load(source_path.parent, kind, {kind: source})
    source_checks = source.get("checks")
    require(
        isinstance(source_checks, list) and item["source_check"] < len(source_checks),
        "historical source check is missing",
    )
    original = source_checks[item["source_check"]]
    require(
        original.get("source_commit", source["candidate_commit"])
        == item.get("source_commit"),
        "historical source commit mismatch",
    )
    require(
        original.get("status") in ("passed", "reused"),
        "historical source check did not pass",
    )
    evidence(original.get("evidence"), source_path.parent, "historical check evidence")


def validate_receipt(
    item,
    needed,
    environment,
    bundle,
    checkout,
    record,
    *,
    carried,
    prior_stage,
    reuse_reason,
):
    require(text(item.get("receipt")), "runner check requires a receipt")
    receipt = (bundle / item["receipt"]).resolve()
    require(receipt.is_file(), f"missing runner receipt {receipt}")
    require(
        item["status"] != "passed" or item["exit_code"] == 0,
        "runner passed check requires exit_code 0",
    )
    facts = read_json(receipt)
    require(
        isinstance(facts, dict) and isinstance(facts.get("checks"), list),
        "malformed runner receipt",
    )
    if item["status"] == "reused":
        require(
            item.get("source_commit") == facts.get("revision"),
            "runner reuse source_commit must preserve the original run revision",
        )
    rows = [
        row
        for row in facts["checks"]
        if isinstance(row, dict) and row.get("id") == item["check_id"]
    ]
    require(len(rows) == 1, "runner receipt does not identify the claimed check")
    row = rows[0]
    if item["status"] in ("passed", "reused"):
        require(
            row.get("status") == "passed" and row.get("exit_code") == 0,
            "claimed runner success mismatches receipt result",
        )
    else:
        require(
            item["status"] == "failed"
            and row.get("status") == "failed"
            and row.get("exit_code") == item["exit_code"],
            "claimed runner failure mismatches receipt result",
        )
    if item["status"] != "reused" and not carried:
        require(
            text(facts.get("checkout"))
            and Path(facts["checkout"]).resolve()
            == Path(record["assessed_checkout"]).resolve(),
            "fresh runner receipt must come from the stage's assessed checkout",
        )
    selection = {
        key: value
        for key, value in needed.items()
        if key not in ("fresh", "environment", "requirement_key")
    }
    runner_requirements = {
        "schema_version": 1,
        "environment": environment,
        "checks": [selection],
    }
    held = (
        (
            record["kind"] == "candidate"
            and any(check["status"] == "failed" for check in record["checks"])
        )
        or (record["kind"] == "verification" and record.get("verdict") != "PASS")
        or (record["kind"] == "integration" and record.get("status") == "failed")
    )
    runner = Path(__file__).resolve().parents[4] / "tools" / "check.py"
    require(runner.is_file(), f"runner unavailable: {runner}")
    # The runner receives structured requirements through its public process CLI.
    scratch = checkout / "tmp" / "handoff-validation"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="receipt-", dir=scratch) as temporary:
        path = Path(temporary) / "requirements.json"
        path.write_text(json.dumps(runner_requirements), encoding="utf-8")
        command = [
            sys.executable,
            str(runner),
            "validate",
            "--receipt",
            str(receipt),
            "--checkout",
            str(checkout),
            "--requirements",
            str(path),
        ]
        command += [
            "--ref",
            record.get("integration_commit", record["candidate_commit"]),
        ]
        if item["status"] == "failed" or held:
            command += ["--allow-failed"]
        if item["status"] == "reused" or carried:
            reason = item.get("reason")
            if carried:
                reason = (
                    reuse_reason or read_json(bundle / "carry-forward.json")["reason"]
                )
            require(text(reason), "receipt reuse requires applicability reason")
            command += ["--reuse-reason", reason]
        elif prior_stage:
            command += [
                "--reuse-reason",
                "Read-only validation of this earlier stage's original execution against its declared Git contents",
            ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    require(
        result.returncode == 0,
        f"invalid runner receipt for {needed['id']}: {result.stdout.strip()} {result.stderr.strip()}",
    )
