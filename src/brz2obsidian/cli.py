import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(prog="brz2obsidian")
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("inspect", "convert"):
        command = commands.add_parser(name)
        command.add_argument("source")
        if name == "convert":
            command.add_argument("destination")
        command.add_argument("--json", action="store_true", dest="json_output")
    checker = commands.add_parser("check-vault")
    checker.add_argument("vault")
    checker.add_argument("--json", action="store_true", dest="json_output")
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return 0 if error.code == 0 else 1
    if args.operation == "check-vault":
        from brz2obsidian.vault_check import check_vault

        result = check_vault(args.vault)
        if args.json_output:
            print(result.model_dump_json(by_alias=True))
        else:
            print(f"check-vault: {result.outcome}")
            print(f"Vault: {result.vault.location}")
            print(
                f"Read Markdown files: {result.counts.read_markdown_files}; "
                f"read Bases: {result.counts.read_base_files}"
            )
            for issue in result.issues:
                location = issue.artifact or "vault"
                if issue.property:
                    location += ":" + issue.property
                print(f"{issue.code} ({location}): {issue.message} {issue.guidance}")
                if issue.reference:
                    print(f"Reference: {issue.reference}")
                if issue.candidates:
                    print("Candidates: " + ", ".join(issue.candidates))
        return {"clean": 0, "issues": 2, "failed": 1}[result.outcome]
    from brz2obsidian.application.wiring import default_workflow

    workflow = default_workflow()
    result = (
        workflow.inspect(args.source)
        if args.operation == "inspect"
        else workflow.convert(args.source, args.destination)
    )
    if args.json_output:
        print(result.model_dump_json(by_alias=True))
    else:
        print(f"{result.operation}: {result.outcome}")
        if result.counts:
            if result.counts.image_presentation_normalizations:
                print(
                    f"Image presentation normalizations: {result.counts.image_presentation_normalizations}"
                )
            if result.counts.text_adaptations:
                print(f"Literal text adaptations: {result.counts.text_adaptations}")
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
            print(f"{issue.code}: {issue.message} {issue.guidance}")
            if issue.affected:
                print("Affected: " + ", ".join(issue.affected))
            if issue.evidence:
                print("Evidence: " + ", ".join(issue.evidence))
            if issue.leftover_path:
                print(f"Owned staging left at: {issue.leftover_path}")
    return {"clean": 0, "warnings": 2, "refused": 1, "failed": 1}[result.outcome]
