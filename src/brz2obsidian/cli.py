import argparse

from brz2obsidian.application.wiring import default_workflow


def main(argv=None):
    parser = argparse.ArgumentParser(prog="brz2obsidian")
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("inspect", "convert"):
        command = commands.add_parser(name)
        command.add_argument("source")
        if name == "convert":
            command.add_argument("destination")
        command.add_argument("--json", action="store_true", dest="json_output")
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return 0 if error.code == 0 else 1
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
            print(
                f"Planned thought notes: {result.counts.planned_notes}; present payloads: {result.counts.present_assets}"
            )
        if result.receipt:
            print(f"Verified vault published: {result.receipt.destination}")
        if result.inspection:
            print("Pending: " + ", ".join(result.inspection.pending_checks))
        for issue in result.issues:
            print(f"{issue.code}: {issue.message} {issue.guidance}")
            if issue.leftover_path:
                print(f"Owned staging left at: {issue.leftover_path}")
    return {"clean": 0, "warnings": 2, "refused": 1, "failed": 1}[result.outcome]
