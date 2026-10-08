"""Publish complete structured handoffs from explicit judgments and Git context."""

import argparse
import contextlib
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path, PureWindowsPath

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


def read_input(path, required):
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    fields(data, required, "input")
    if "checks" in data:
        require(isinstance(data["checks"], list), "checks must be an array")
        for index, check in enumerate(data["checks"]):
            fields(
                check,
                {"name", "status", "method", "exit_code", "evidence"},
                f"checks[{index}]",
                {"reason", "source_commit"},
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
        schema_version=1,
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
        schema_version=1,
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
        schema_version=1,
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


def main():
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
    for command in (candidate, verification, integration):
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
        }
        data = read_input(args.input, required[args.stage])
        checkout = Path(git(args.checkout.resolve(), "rev-parse", "--show-toplevel"))
        if args.stage == "candidate":
            record = candidate_record(data, checkout)
        elif args.stage == "verification":
            record = verification_record(data, args.attempt)
        else:
            record = integration_record(data, args.attempt, checkout)
        allowed = validate(args.attempt, args.stage, checkout, {args.stage: record})
        destination = args.attempt / f"{args.stage}.json"
        publish(
            destination,
            (
                json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8"),
        )
    except (InvalidHandoff, OSError, ValueError) as error:
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
