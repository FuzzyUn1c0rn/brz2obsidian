"""Publish complete structured handoffs from explicit judgments and Git context."""

import argparse
import contextlib
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path, PureWindowsPath

from receipt_requirements import bind, read_json, validate_record
from validate_handoff import (
    InvalidHandoff,
    git,
    load,
    relative_path,
    require,
    text,
    validate,
)

CANDIDATE_FIELDS = {
    "actor",
    "ticket",
    "spec",
    "base_ref",
    "owned_files",
    "criteria",
    "checks",
    "limits",
}
VERIFICATION_FIELDS = {"actor", "verdict", "criteria", "findings", "checks", "limits"}
INTEGRATION_FIELDS = {"actor", "status", "previous_tip_ref", "checks", "limits"}
CARRY_FIELDS = {"reason", "carry_verification"}
CARRY_RECEIPT = "carry-forward.json"


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def fields(data, required, label, optional=()):
    require(isinstance(data, dict), f"{label} must be an object")
    missing = required - data.keys()
    require(not missing, f"{label}: missing fields {', '.join(sorted(missing))}")
    unknown = data.keys() - required - set(optional)
    require(
        not unknown,
        f"{label}: unknown/helper-owned fields {', '.join(sorted(unknown))}",
    )


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate input field {key}")
        result[key] = value
    return result


def read_input(path, required, optional=()):
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    fields(data, required, "input", optional)
    if "checks" in data:
        require(isinstance(data["checks"], list), "checks must be an array")
        for index, check in enumerate(data["checks"]):
            fields(
                check,
                {"name", "status", "method", "exit_code", "evidence"},
                f"checks[{index}]",
                {
                    "kind",
                    "reason",
                    "source_commit",
                    "check_id",
                    "receipt",
                    "environment",
                    "source_record",
                    "source_check",
                    "requirement_key",
                },
            )
    return data


def repository_path(value, label):
    relative_path(value, label)
    windows = PureWindowsPath(value)
    require(
        not windows.drive and not windows.root and ".." not in windows.parts,
        f"{label} must be repository-relative without parent traversal",
    )
    return Path(value.replace("\\", "/")).as_posix()


def candidate_record(data, checkout):
    require(text(data["base_ref"]), "base_ref must be a nonempty Git reference")
    record = {key: value for key, value in data.items() if key != "base_ref"}
    record.update(
        schema_version=2,
        kind="candidate",
        candidate_commit=git(checkout, "rev-parse", "--verify", "HEAD^{commit}"),
        base_commit=git(
            checkout,
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{data['base_ref']}^{{commit}}",
        ),
        worktree=str(checkout),
    )
    for key in ("ticket", "spec"):
        record[key] = repository_path(record[key], key)
    require(isinstance(record["owned_files"], list), "owned_files must be an array")
    record["owned_files"] = [
        repository_path(item, "owned_files entry") for item in record["owned_files"]
    ]
    return record


def verification_record(data, attempt):
    require(isinstance(data["criteria"], list), "criteria must be an array")
    for index, criterion in enumerate(data["criteria"]):
        fields(criterion, {"id", "status", "evidence"}, f"criteria[{index}]")
    candidate = load(attempt, "candidate")
    return dict(
        data,
        schema_version=2,
        kind="verification",
        ticket=candidate["ticket"],
        candidate_commit=candidate["candidate_commit"],
    )


def integration_record(data, attempt, checkout):
    require(
        text(data["previous_tip_ref"]),
        "previous_tip_ref must be a nonempty Git reference",
    )
    candidate = load(attempt, "candidate")
    record = {key: value for key, value in data.items() if key != "previous_tip_ref"}
    record.update(
        schema_version=2,
        kind="integration",
        ticket=candidate["ticket"],
        candidate_commit=candidate["candidate_commit"],
        previous_tip=git(
            checkout,
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{data['previous_tip_ref']}^{{commit}}",
        ),
        integration_commit=git(checkout, "rev-parse", "--verify", "HEAD^{commit}"),
        verification_sha256=hashlib.sha256(
            (attempt / "verification.json").read_bytes()
        ).hexdigest(),
    )
    return record


def publish(path, payload):
    """Link a fully flushed sibling into place; link never replaces a name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".handoff-", suffix=".tmp", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            # Cleanup cannot reverse publication or mask its original failure.
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)


def direct_evidence_references(record, *, inspecting=False):
    for check in record["checks"]:
        for reference in check["evidence"]:
            yield reference, None
    for check in record["checks"]:
        for field, kind in (("receipt", "runner"), ("source_record", "historical")):
            reference = check.get(field)
            # Early diagnosis sees any textual alias; validated copying only
            # includes the extra reference supported by that check's kind.
            selected = (
                text(reference)
                if inspecting
                else check.get("kind") == kind and reference
            )
            if selected:
                yield reference, field
    if record["kind"] == "verification":
        criteria = record.get("criteria") if inspecting else record["criteria"]
        if inspecting and not isinstance(criteria, list):
            return
        for criterion in criteria:
            if inspecting and (
                not isinstance(criterion, dict)
                or not isinstance(criterion.get("evidence"), list)
            ):
                continue
            for reference in criterion["evidence"]:
                if not inspecting or text(reference):
                    yield reference, None


def carry_forward(attempt, source, checkout, data, expected, candidate_expected=None):
    require(source.is_absolute(), "--from must be an exact absolute path")
    require(text(data["reason"]), "reason must be nonempty")
    require(
        type(data["carry_verification"]) is bool, "carry_verification must be boolean"
    )
    reuse = data["carry_verification"]
    if reuse:
        require(
            text(data.get("verification_reuse_rationale")),
            "PASS reuse requires nonempty verification_reuse_rationale",
        )
    else:
        require(
            "verification_reuse_rationale" not in data,
            "verification_reuse_rationale conflicts with carry_verification false",
        )
    resolved_attempt, resolved_source = attempt.resolve(), source.resolve()
    require(
        not resolved_attempt.is_relative_to(resolved_source)
        and not resolved_source.is_relative_to(resolved_attempt),
        "source/destination attempt collision: attempts must be distinct and non-nested",
    )
    require(
        not attempt.exists() or not any(attempt.iterdir()),
        f"occupied destination {attempt}",
    )
    payloads = {"candidate": (source / "candidate.json").read_bytes()}
    if reuse:
        payloads["verification"] = (source / "verification.json").read_bytes()
    records = {
        kind: json.loads(payload.decode("utf-8")) for kind, payload in payloads.items()
    }
    stage = "verification" if reuse else "candidate"
    require(
        all(record.get("schema_version") == 2 for record in records.values()),
        "historical v1 records cannot be carried into new transitions",
    )
    prior_declarations = {
        kind: record.get("check_requirements") for kind, record in records.items()
    }
    # A check's evidence can occupy this reserved name with arbitrary bytes.
    # Diagnose that alias before interpreting the file as carry metadata.
    source_receipt = (source / CARRY_RECEIPT).resolve()
    for kind, record in records.items():
        load(source, kind, records)
        require(
            not any(
                (source / reference).resolve() == source_receipt
                for reference, _ in direct_evidence_references(record, inspecting=True)
            ),
            "evidence/carry receipt collision",
        )
    if (source / CARRY_RECEIPT).is_file():
        prior_declarations.update(
            read_json(source / CARRY_RECEIPT).get("check_requirements", {})
        )
    allowed = validate(
        source,
        stage,
        checkout,
        records,
        expected=prior_declarations[stage],
        prior_context=True,
    )
    if reuse:
        require(
            records["verification"]["verdict"] == "PASS",
            "only PASS verification can be reused; BLOCKED/REWORK require fresh verification",
        )
    current_declarations = {stage: expected}
    if reuse:
        current_declarations["candidate"] = (
            candidate_expected or prior_declarations["candidate"]
        )
    for kind, record in records.items():
        validate_record(
            record,
            source,
            checkout,
            current_declarations[kind],
            carried=True,
            reuse_reason=data["reason"],
        )
    copies = {}
    for record in records.values():
        references = []
        for reference, field in direct_evidence_references(record):
            references.append(reference)
            if field == "receipt":
                receipt_path = source / reference
                if not Path(reference).is_absolute():
                    for row in read_json(receipt_path).get("checks", []):
                        references.extend(
                            str(Path(reference).parent / item["path"])
                            for item in row.get("evidence", [])
                        )
            if field == "source_record" and not Path(reference).is_absolute():
                original = read_json(source / reference)
                for historical_check in original.get("checks", []):
                    references.extend(
                        str(Path(reference).parent / item)
                        for item in historical_check.get("evidence", [])
                    )
        for reference in references:
            reference_path = Path(reference)
            if not reference_path.is_absolute():
                require(
                    not reference_path.drive and not reference_path.root,
                    f"ambiguous relative evidence path {reference}",
                )
                destination, origin = (
                    (attempt / reference).resolve(),
                    (source / reference).resolve(),
                )
                require(
                    destination not in copies or copies[destination] == origin,
                    f"evidence destination collision {destination}",
                )
                copies[destination] = origin
    reserved = {
        (attempt / name).resolve()
        for name in (
            "candidate.json",
            "verification.json",
            "integration.json",
            CARRY_RECEIPT,
        )
    }
    for destination in copies:
        require(
            destination not in reserved,
            f"evidence/record destination collision {destination}",
        )
        require(
            not destination.is_relative_to(resolved_source),
            f"evidence destination collision with source attempt {destination}",
        )
    targets = set(copies) | reserved
    for destination in targets:
        require(
            not destination.exists() and not destination.is_symlink(),
            f"occupied destination {destination}",
        )
        for parent in destination.parents:
            require(
                parent not in targets, f"file/ancestor destination collision {parent}"
            )
            require(
                not parent.exists() or parent.is_dir(),
                f"occupied ancestor destination {parent}",
            )
    for destination, origin in copies.items():
        publish(destination, origin.read_bytes())
    receipt = dict(
        data,
        source_attempt=str(source),
        destination_attempt=str(attempt),
        check_requirements=current_declarations,
    )
    publish(
        attempt / CARRY_RECEIPT,
        (
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8"),
    )
    allowed = validate(attempt, stage, checkout, records, expected=expected)
    # Candidate is last: an interrupted bundle cannot validate at either stage.
    for kind in reversed(payloads):
        publish(attempt / f"{kind}.json", payloads[kind])
    return allowed


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = Parser(description=__doc__)
    subparsers = parser.add_subparsers(dest="stage", required=True)
    candidate = subparsers.add_parser(
        "candidate",
        help="publish a candidate handoff",
        description="Publish candidate.json from one UTF-8 JSON object.",
        epilog=(
            "Required input: actor, ticket, spec, base_ref, owned_files, criteria, "
            "checks, limits. Arrays remain explicit, including checks/limits when empty. "
            "Use a captured full commit ID for base_ref: the integration tip incorporated "
            "before final candidate checks, rather than a moving branch. Git context comes "
            "from --checkout. Repository paths are normalized; evidence files are absolute "
            "or relative to the final attempt, never the input file. Helper-owned/unknown "
            "fields are refused. Existing records are never replaced. Exit 0: published, "
            "transition allowed; 2: published, transition held; 1: no record published. "
            "Unavailable candidate checks may advance to independent verification. "
            "See references/handoffs.md for field structures and evidence rules."
        ),
    )
    verification = subparsers.add_parser(
        "verification",
        help="publish an independent verification verdict",
        description="Publish verification.json from explicit independent judgments.",
        epilog=(
            "Required input: actor, verdict (PASS, REWORK, BLOCKED), criteria, findings, "
            "checks, limits. Each criterion has exactly id, status, evidence; cover every "
            "candidate criterion once. Arrays and judgments stay explicit, including "
            "empty findings/checks/limits. The actor must be independent of the candidate "
            "implementer. Ticket/candidate identity comes from this exact attempt's "
            "candidate.json; schema/kind and other helper-owned/unknown fields are errors. "
            "Evidence is absolute or relative to the attempt. Assess the clean candidate "
            "commit using --checkout, even when running elsewhere. Exit 0: PASS published, "
            "transition allowed; 2: valid REWORK/BLOCKED published, transition held; "
            "1: invalid input/state or occupied destination, no record published. "
            "Checks never supply an omitted verdict or actual user acceptance. "
            "Machine validation checks structure/state; the verifier judges evidence, "
            "omitted requirements and reuse applicability. Existing records stay immutable. "
            "See references/handoffs.md for input examples and check/reuse structures."
        ),
    )
    integration = subparsers.add_parser(
        "integration",
        help="publish an already-performed integration outcome",
        description="Publish integration.json bound to this attempt's verification bytes.",
        epilog=(
            "Required input: actor, status (integrated or failed), previous_tip_ref, checks, "
            "limits. Capture previous_tip_ref immediately before merging; prefer its full "
            "commit ID over a moving branch. The helper resolves that explicit reference, "
            "reads resulting HEAD from --checkout, and derives ticket/candidate identity "
            "from this attempt's candidate.json. It hashes the exact verification.json "
            "bytes using SHA-256, never a reserialization. Arrays, check outcomes, reuse "
            "source commits/rationale and limits remain explicit agent judgments. "
            "Helper-owned/unknown fields are refused. Evidence is absolute or relative "
            "to the attempt. Assessed checkout must be clean. Integrated requires passing "
            "verification/checks and both previous tip/candidate ancestors of the result. "
            "Valid failed records retain inspected HEAD without those integration ancestry "
            "requirements. Exit 0: published, allowed; 2: valid failed outcome published, "
            "held; 1: invalid input/state or occupied destination, no record published. "
            "Records are immutable. The helper does not merge, execute checks, close "
            "tickets or infer user acceptance. See references/handoffs.md for examples."
        ),
    )
    carry = subparsers.add_parser(
        "carry-forward",
        help="resume an unchanged candidate in an assigned attempt",
        description="Copy immutable candidate/optional PASS bytes into the exact assigned retry attempt.",
        epilog=(
            "Required input: reason (nonempty retry explanation), carry_verification "
            "(explicit boolean). True additionally requires nonempty "
            "verification_reuse_rationale, attesting that PASS evidence remains applicable; "
            "the helper cannot judge applicability. False requires fresh verification and "
            "accepts no reuse rationale. BLOCKED/REWORK cannot be carried. --from selects "
            "an exact absolute source attempt; ATTEMPT is an exact absolute destination. "
            "The coordinator chooses the unused attempt and records the reason in GitHub. "
            "Assess a clean unchanged candidate HEAD using --checkout. Candidate and optional "
            "PASS records retain original bytes/actors/context; integration is never copied. "
            "Absolute evidence references stay intact; relative evidence is copied with its "
            "original layout, including '..' where its destination is unused. Missing files, "
            "occupied destinations and record/evidence aliases are refused. Source and "
            "destination attempts must be distinct and non-nested. The stable auxiliary "
            "carry-forward.json receipt retains reason, source/destination paths, explicit "
            "reuse choice, current check requirements and rationale outside immutable records. Success requires all "
            "requested evidence, receipt and records. Exit 0: carried, transition allowed; "
            "2: carried, transition held; 1: failure, any partial destination is not ready. "
            "Publication is atomic per file without replacement, not a directory transaction. "
            "After I/O failure or interruption inspect the printed assigned destination, "
            "preserve it and ask the coordinator for another unused attempt; retries refuse "
            "occupied partial attempts. Substantive repairs need a new candidate commit and "
            "fresh verification. See references/handoffs.md for recovery examples."
        ),
    )
    carry.add_argument(
        "--candidate-requirements",
        type=Path,
        help="current independent candidate reuse requirements when carrying PASS",
    )
    carry.add_argument(
        "--from",
        dest="source",
        type=Path,
        required=True,
        help="exact absolute source attempt",
    )
    for command in (candidate, verification, integration, carry):
        command.add_argument(
            "--requirements",
            type=Path,
            required=True,
            help="independently authored stage check requirements JSON (v2)",
        )
        command.add_argument(
            "attempt", type=Path, help="coordinator's exact absolute attempt directory"
        )
        command.add_argument(
            "--checkout", type=Path, required=True, help="assessed Git checkout"
        )
        command.add_argument(
            "--input",
            type=Path,
            required=True,
            help="UTF-8 JSON input, preserved unchanged",
        )
    args = parser.parse_args()
    try:
        require(args.attempt.is_absolute(), "attempt must be an exact absolute path")
        required = {
            "candidate": CANDIDATE_FIELDS,
            "verification": VERIFICATION_FIELDS,
            "integration": INTEGRATION_FIELDS,
            "carry-forward": CARRY_FIELDS,
        }
        data = read_input(
            args.input,
            required[args.stage],
            {"verification_reuse_rationale"} if args.stage == "carry-forward" else (),
        )
        checkout = Path(git(args.checkout.resolve(), "rev-parse", "--show-toplevel"))
        expected = read_json(args.requirements)
        if args.stage == "carry-forward":
            print(f"Assigned carry-forward destination {args.attempt}", flush=True)
            candidate_expected = (
                read_json(args.candidate_requirements)
                if args.candidate_requirements
                else None
            )
            require(
                candidate_expected is None or data["carry_verification"] is True,
                "--candidate-requirements applies only when carrying PASS",
            )
            allowed = carry_forward(
                args.attempt, args.source, checkout, data, expected, candidate_expected
            )
            print(f"Carried to {args.attempt}; receipt {args.attempt / CARRY_RECEIPT}")
            print(
                "Transition allowed"
                if allowed
                else "Transition held: repair or prerequisite required"
            )
            return 0 if allowed else 2
        if args.stage == "candidate":
            record = candidate_record(data, checkout)
        elif args.stage == "verification":
            record = verification_record(data, args.attempt)
        else:
            record = integration_record(data, args.attempt, checkout)
        record["assessed_checkout"] = str(checkout)
        bind(record, expected)
        allowed = validate(
            args.attempt, args.stage, checkout, {args.stage: record}, expected=expected
        )
        destination = args.attempt / f"{args.stage}.json"
        publish(
            destination,
            (
                json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8"),
        )
    except (InvalidHandoff, OSError, ValueError) as error:
        if args.stage == "carry-forward":
            print(
                f"Carry-forward failed for destination {args.attempt} (input {args.input}); any partial attempt is not ready; assign another unused attempt: {error}",
                file=sys.stderr,
            )
            return 1
        print(
            f"No record published for {args.attempt} (input {args.input}): {error}",
            file=sys.stderr,
        )
        return 1
    print(f"Published {destination}")
    print(
        "Transition allowed"
        if allowed
        else "Transition held: repair or prerequisite required"
    )
    return 0 if allowed else 2


if __name__ == "__main__":
    sys.exit(main())
