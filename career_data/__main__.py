import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .database import connect, coverage_report, inventory, json_text, status, validate_database
from .pipeline import approve_review, backup_database, export_data, extract_pending, make_review, parse_sequences, write_json
from .reconciliation import reconcile_totals


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import screenshot-backed FIFA career data into SQLite.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--db", type=Path, help="Database path; defaults to ROOT/data/career.sqlite")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inventory", help="Inventory images without running OCR")
    commands.add_parser("status", help="Show canonical record counts and outstanding source states")
    commands.add_parser("validate", help="Check database integrity and relationships")
    reporter = commands.add_parser("report", help="Report fixture, player and team-stat coverage with reconciliation warnings")
    reporter.add_argument("--club", default="Notts County")
    reporter.add_argument("--output", type=Path, help="Write the full report as JSON and print its summary")
    reconciliation = commands.add_parser("reconcile", help="Compare captured cumulative player stats with reviewed match records")
    reconciliation.add_argument("--season")
    reconciliation.add_argument("--club", default="Notts County")
    reconciliation.add_argument("--rating-decimals", type=int, choices=(1, 2), default=1)
    reconciliation.add_argument("--output", type=Path)
    importer = commands.add_parser("import", help="Inventory and extract new screenshots into the review queue")
    importer.add_argument("--screenshots", help="Numeric selection, for example 73,76,808-810")
    importer.add_argument("--limit", type=int, default=20, help="Maximum images to OCR this run (default: 20)")
    importer.add_argument("--reextract", action="store_true", help="Refresh OCR candidates without changing reviewed records")
    reviewer = commands.add_parser("review", help="Write an editable review document; never overwrites an existing file")
    reviewer.add_argument("--screenshots", required=True)
    reviewer.add_argument("--match", help="Propose an approved match UUID for the selected performance records")
    reviewer.add_argument("--output", type=Path, required=True)
    approver = commands.add_parser("approve", help="Validate and transactionally import a visually checked review document")
    approver.add_argument("review_file", type=Path)
    approver.add_argument("--note", required=True, help="Describe the source checks and any corrections")
    approver.add_argument("--replace-reviewed", action="store_true", help="Explicitly allow corrections to existing non-null values")
    exporter = commands.add_parser("export", help="Regenerate the read-only JSON dataset for React")
    exporter.add_argument("--output", type=Path)
    backup = commands.add_parser("backup", help="Create a consistent SQLite backup, including all review history")
    backup.add_argument("destination", type=Path)
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    connection = connect(arguments.db or root / "data" / "career.sqlite")
    try:
        if arguments.command == "inventory":
            print(json_text(inventory(connection, root)), end="")
        elif arguments.command == "status":
            print(json_text(status(connection)), end="")
        elif arguments.command == "report":
            report = coverage_report(connection, arguments.club)
            if arguments.output:
                write_json(arguments.output, report)
                print(json_text({"output": str(arguments.output), "summary": report["summary"], "warnings": report["warnings"]}), end="")
            else:
                print(json_text(report), end="")
        elif arguments.command == "reconcile":
            report = reconcile_totals(connection, arguments.season, arguments.club, arguments.rating_decimals)
            if arguments.output:
                write_json(arguments.output, report)
                print(json_text({"output": str(arguments.output), "summary": report["summary"]}), end="")
            else:
                print(json_text(report), end="")
        elif arguments.command == "validate":
            errors = validate_database(connection)
            print(json_text({"valid": not errors, "errors": errors}), end="")
            return 1 if errors else 0
        elif arguments.command == "import":
            manifest = inventory(connection, root)
            results = extract_pending(connection, root, parse_sequences(arguments.screenshots), arguments.limit,
                                      arguments.reextract, progress=lambda message: print(message, flush=True))
            exported = export_data(connection, root / "data" / "exports" / "career.json")
            print(json_text({"inventory": manifest, "extraction": results, "export": exported}), end="")
            return 1 if results["errors"] else 0
        elif arguments.command == "review":
            review = make_review(connection, parse_sequences(arguments.screenshots), arguments.match)
            if not review["sources"]:
                raise ValueError("No extractions are available for that selection; run import first")
            write_json(arguments.output, review, overwrite=False)
            print(json_text({"review_file": str(arguments.output), "sources": len(review["sources"])}), end="")
        elif arguments.command == "approve":
            review = json.loads(arguments.review_file.read_text(encoding="utf-8"))
            result = approve_review(connection, review, arguments.note, arguments.replace_reviewed)
            exported = export_data(connection, root / "data" / "exports" / "career.json")
            print(json_text({"review": result, "export": exported}), end="")
        elif arguments.command == "export":
            print(json_text(export_data(connection, arguments.output or root / "data" / "exports" / "career.json")), end="")
        elif arguments.command == "backup":
            print(json_text(backup_database(connection, arguments.destination)), end="")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, sqlite3.Error) as exception:
        print(f"Error: {exception}", file=sys.stderr)
        raise SystemExit(1)
