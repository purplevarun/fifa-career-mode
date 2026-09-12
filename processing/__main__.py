import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from .database import connect, coverage_report, inventory, json_text, status, validate_database
from .identifiers import new_id
from .pipeline import approve_review, backup_database, dashboard_data, extract_pending, make_review, parse_sequences, write_json
from .reconciliation import reconcile_totals


def main(argv=None):
    parser = argparse.ArgumentParser(description="Process local FIFA screenshots and manage saved SQLite stats.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--db", type=Path, help="Database path; defaults to ROOT/processing/data/career.sqlite")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("data", help="Read saved stats as JSON for the local dashboard")
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
    importer = commands.add_parser("process", aliases=["import"], help="Scan raw_screenshots and save new OCR results to SQLite")
    importer.add_argument("--screenshots", help="Numeric selection, for example 73,76,808-810")
    importer.add_argument("--limit", type=int, help="Optional maximum images to OCR; default processes all new images")
    importer.add_argument("--clean", action="store_true", help="Back up and reset SQLite, then OCR all current screenshots; clears reviewed stats")
    importer.add_argument("--reextract", action="store_true", help="Refresh OCR candidates without changing reviewed records")
    reviewer = commands.add_parser("review", help="Write an editable review document; never overwrites an existing file")
    reviewer.add_argument("--screenshots", help="Optional numeric screenshot selection")
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
    database_path = (arguments.db or root / "processing" / "data" / "career.sqlite").resolve()
    reset = {}
    if arguments.command in {"process", "import"} and arguments.clean:
        if arguments.screenshots is not None or arguments.limit is not None:
            raise ValueError("--clean cannot be combined with --screenshots or --limit; a clean rebuild processes all screenshots")
        reset["clean"] = True
        print("Clean rebuild: existing stats, approvals, and processing history will be reset.", flush=True)
        if database_path.exists():
            backup_path = database_path.parent / "backups" / f"{database_path.stem}-before-clean-{new_id()}.sqlite"
            with closing(sqlite3.connect(database_path.as_uri() + "?mode=rw", uri=True)) as previous:
                reset.update(backup_database(previous, backup_path))
                with closing(sqlite3.connect(backup_path.as_uri() + "?mode=ro", uri=True)) as saved:
                    if saved.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Backup integrity check failed; existing database was not reset")
                print(f"Existing database backed up to {backup_path}", flush=True)
                with closing(connect(":memory:")) as fresh:
                    fresh.backup(previous)
    if arguments.command == "data":
        if not database_path.is_file():
            raise ValueError("No local stats database yet. Run ./run process first.")
        with closing(sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            print(json_text(dashboard_data(connection)), end="")
        return 0
    if arguments.command in {"process", "import", "inventory"}:
        (root / "raw_screenshots").mkdir(parents=True, exist_ok=True)
    connection = connect(database_path)
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
        elif arguments.command in {"process", "import"}:
            manifest = inventory(connection, root)
            results = extract_pending(connection, root, parse_sequences(arguments.screenshots), arguments.limit,
                                      arguments.reextract, progress=lambda message: print(message, flush=True))
            source_ids = results.pop("processed_source_ids")
            result = {"database": str(database_path), "inventory": manifest, "extraction": results, **reset}
            if source_ids:
                review = make_review(connection, source_ids=set(source_ids))
                review_path = database_path.parent / "reviews" / f"review-{new_id()}.json"
                write_json(review_path, review, overwrite=False)
                result["review_file"] = str(review_path)
                result["next"] = "Check the new OCR values against the originals, then run python3 -m processing approve <review_file> --note 'Checked'."
            else:
                result["message"] = ("No OCR results were saved. The reset database contains no reviewed stats."
                                     if arguments.clean else "No new OCR results. Saved stats are unchanged.")
            print(json_text(result), end="")
            return 1 if results["errors"] else 0
        elif arguments.command == "review":
            review = make_review(connection, parse_sequences(arguments.screenshots), arguments.match)
            if not review["sources"]:
                raise ValueError("No extractions are available for that selection; run ./run process first")
            write_json(arguments.output, review, overwrite=False)
            print(json_text({"review_file": str(arguments.output), "sources": len(review["sources"])}), end="")
        elif arguments.command == "approve":
            review = json.loads(arguments.review_file.read_text(encoding="utf-8"))
            result = approve_review(connection, review, arguments.note, arguments.replace_reviewed)
            print(json_text({"review": result, "message": "Saved to SQLite. Refresh the local dashboard to see the changes."}), end="")
        elif arguments.command == "export":
            output = arguments.output or database_path.parent / "dashboard.json"
            write_json(output, dashboard_data(connection))
            print(json_text({"output": str(output)}), end="")
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
