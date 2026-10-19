import argparse
import sys


class SafeArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)

    def error(self, message):
        self.print_usage(sys.stderr)
        category = (
            "unrecognized arguments"
            if message.startswith("unrecognized arguments:")
            else "invalid command arguments"
        )
        self.exit(
            2,
            f"{self.prog}: error: {category}; use --help for accepted options\n",
        )


def main(argv=None):
    parser = SafeArgumentParser(prog="brz2obsidian")
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("inspect", "convert"):
        command = commands.add_parser(name)
        command.add_argument(
            "source", help="BRZ archive path or canonical lowercase Brain UUID"
        )
        if name == "convert":
            command.add_argument("destination", help="New vault directory to publish")
        command.add_argument("--json", action="store_true", dest="json_output")
        command.add_argument(
            "--source-kind",
            choices=("brz", "local-api"),
            default="brz",
            help="Source selection (default brz); API options require local-api",
        )
        command.add_argument(
            "--api-url",
            help="Local API address from TheBrain settings (default http://127.0.0.1:11522/api)",
        )
        command.add_argument(
            "--api-search-initial-results",
            type=int,
            help="Initial raw result limit, 1..2147483647 (default 5000)",
        )
        command.add_argument(
            "--api-search-timeout",
            type=float,
            help="Total wildcard budget, 0.001..86400 seconds in whole milliseconds (default 300)",
        )
        command.add_argument(
            "--api-search-max-response-bytes",
            type=int,
            help="Post-decompression bytes per wildcard reply, 1..9223372036854775807 (default 128000000)",
        )
        command.add_argument(
            "--api-search-max-results",
            type=int,
            help="Optional raw result ceiling, 1..2147483647 (default disabled)",
        )
        command.epilog = "Local API acquisition spans requests over time and is not an atomic snapshot. Inspection releases its capture; conversion acquires again. Capture verification checks the retained copy. Discovery reconciliation is empirical and does not prove universal discovery completeness. Credentials use THE_BRAIN_LOCAL_API_KEY."
    checker = commands.add_parser("check-vault")
    checker.add_argument("vault")
    checker.add_argument("--json", action="store_true", dest="json_output")
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return 0 if error.code == 0 else 1
    try:
        return _execute(args)
    except Exception:  # noqa: BLE001 -- final CLI boundary; never expose raw errors.
        try:
            return _unexpected_failure(args)
        except Exception:  # noqa: BLE001 -- output may itself be unavailable.
            return 1


def _unexpected_failure(args):
    label = {
        "inspect": "Inspection",
        "convert": "Conversion",
        "check-vault": "Vault check",
    }[args.operation]
    message = f"{label} could not complete because an unexpected error occurred. The cause is not known."
    guidance = "Save this result and report the problem."
    if args.operation == "convert":
        message += " Publication status is unknown."
        guidance += " Check the destination before another conversion."
    if args.operation == "check-vault":
        # The checker envelope has no unknown-operation/no-counts failure shape.
        # Preserve that interface instead of inventing a diagnosis or read counts.
        print(message + " " + guidance, file=sys.stderr)
        return 1
    from brz2obsidian import __version__
    from brz2obsidian.contracts import Issue, RunResult

    result = RunResult(
        converter_version=__version__,
        operation=args.operation,
        outcome="failed",
        issues=(
            Issue(
                code="operation_failure",
                phase="operation",
                message=message,
                guidance=guidance,
            ),
        ),
    )
    if args.json_output:
        print(result.model_dump_json(by_alias=True))
    else:
        print(f"{result.operation}: failed")
        print(message + " " + guidance)
    return 1


def _execute(args):
    if args.operation == "check-vault":
        from brz2obsidian.vault_check import check_vault

        result = check_vault(args.vault)
        if args.json_output:
            print(result.model_dump_json(by_alias=True))
        else:
            from brz2obsidian.application.checking import finding_for_check

            print(f"check-vault: {result.outcome}")
            print(f"Vault: {result.vault.location}")
            print(
                f"Read Markdown files: {result.counts.read_markdown_files}; "
                f"read Bases: {result.counts.read_base_files}"
            )
            for issue in result.issues:
                location = issue.artifact or "vault"
                print(finding_for_check(issue, result.outcome).message)
                print(f"Details: {issue.code}; affected file: {location}")
        return {"clean": 0, "issues": 2, "failed": 1}[result.outcome]
    from brz2obsidian import __version__
    from brz2obsidian.application.wiring import default_workflow, local_api_workflow
    from brz2obsidian.contracts import Issue, RunResult
    from brz2obsidian.diagnostics import explain_issue

    options = {
        name: getattr(args, "api_" + name)
        for name in (
            "url",
            "search_initial_results",
            "search_timeout",
            "search_max_response_bytes",
            "search_max_results",
        )
        if getattr(args, "api_" + name) is not None
    }
    if args.source_kind == "local-api":
        from brz2obsidian.sources.thebrain.local_api import (
            LocalApiConfig,
            LocalApiSourceRef,
        )
    try:
        if args.source_kind == "brz":
            if options:
                raise ValueError
            reference, config = args.source, None
        else:
            if "url" in options:
                options["api_url"] = options.pop("url")
            reference = LocalApiSourceRef(args.source)
            config = LocalApiConfig(**options)
    except ValueError, TypeError:
        result = RunResult(
            converter_version=__version__,
            operation=args.operation,
            outcome="refused",
            issues=(
                Issue(
                    code="invalid_source_configuration",
                    phase="source",
                    message="Source selection or acquisition configuration is invalid",
                    guidance="Use a canonical Brain UUID and valid local API options with --source-kind local-api; API options require that source kind. Use --help for accepted bounds and address guidance.",
                ),
            ),
        )
    else:
        workflow = default_workflow() if config is None else local_api_workflow(config)
        result = (
            workflow.inspect(reference)
            if args.operation == "inspect"
            else workflow.convert(reference, args.destination)
        )
    if args.json_output:
        print(result.model_dump_json(by_alias=True))
    else:
        print(f"{result.operation}: {result.outcome}")
        if args.source_kind == "local-api":
            print(
                "Local API acquisition is not an atomic snapshot. Inspection releases its capture; conversion acquires again. Capture verification checks the retained copy, not live atomicity or universal discovery completeness."
            )
        if result.counts:
            if result.counts.image_presentation_normalizations:
                print(
                    f"Image presentation normalizations: {result.counts.image_presentation_normalizations}"
                )
            if result.counts.text_adaptations:
                print(f"Text adaptations: {result.counts.text_adaptations}")
            print(
                f"Planned thought notes: {result.counts.planned_notes}; present payloads: {result.counts.present_assets}"
            )
            print(
                f"Local references: {result.counts.source_references}; planned conversions: {result.counts.planned_references}"
            )
            if result.counts.planned_generated_embeds:
                print(
                    f"Planned generated image embeds: {result.counts.planned_generated_embeds}"
                )
            if result.counts.actual_generated_embeds:
                print(
                    f"Generated image embeds: {result.counts.actual_generated_embeds}"
                )
            if result.counts.actual_references is not None:
                print(f"Converted local references: {result.counts.actual_references}")
        if result.receipt:
            print(f"Verified vault published: {result.receipt.destination}")
        if result.inspection:
            print("Pending: " + ", ".join(result.inspection.pending_checks))
        for issue in result.issues:
            print(explain_issue(issue, result.operation))
            print(f"Details: {issue.code}")
            if issue.leftover_path:
                print(f"Owned staging left at: {issue.leftover_path}")
    return {"clean": 0, "warnings": 2, "refused": 1, "failed": 1}[result.outcome]
