import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .identifiers import new_id, normalize_references


def migrate_to_uuids(connection, database_path, schema):
    database_path = Path(database_path)
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (1, 2):
        raise ValueError(f"UUID migration requires schema 1 or 2, found {version}")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = database_path.parent / "backups" / f"{database_path.stem}-before-uuid-{timestamp}.sqlite"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with backup_path.open("xb"):
        pass
    backup = sqlite3.connect(backup_path)
    try:
        connection.backup(backup)
    finally:
        backup.close()
    tables = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
    )]
    old_columns = {table: {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')} for table in tables}
    mappings = {table: {str(row[0]): new_id() for row in connection.execute(f'SELECT id FROM "{table}"')}
                for table in tables if "id" in old_columns[table]}
    drops = [f'DROP {row[0].upper()} "{row[1]}";' for row in connection.execute(
        "SELECT type, name FROM sqlite_master WHERE type IN ('trigger', 'index') AND sql IS NOT NULL"
    )]
    renames = [f'ALTER TABLE "{table}" RENAME TO "legacy_{table}";' for table in tables]
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript("BEGIN IMMEDIATE;\n" + "\n".join(drops + renames) + "\n" + schema)
        for table, identities in mappings.items():
            connection.executemany("INSERT INTO legacy_ids(entity_table, old_value, uuid) VALUES (?, ?, ?)",
                                   ((table, old_value, identifier) for old_value, identifier in identities.items()))
        revisions = {}
        seen_hashes = set()
        for table in tables:
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            foreign_keys = {row[3]: row[2] for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')}
            ordering = "id" if table == "reviews" else "rowid"
            for row in connection.execute(f'SELECT * FROM "legacy_{table}" ORDER BY {ordering}').fetchall():
                values = dict(row)
                if table in mappings:
                    values["id"] = mappings[table][str(row["id"])]
                for field, target in foreign_keys.items():
                    if values.get(field) is not None:
                        values[field] = mappings[target][str(values[field])]
                if table == "source_images":
                    values["sha256"] = row["id"]
                if table == "player_matches" and "goals_conceded_displayed" not in values:
                    values["goals_conceded_displayed"] = values.get("goals_conceded")
                if table == "extractions":
                    values["candidate_json"] = json.dumps(normalize_references(
                        connection, json.loads(values["candidate_json"]), allow_legacy=True), ensure_ascii=True)
                if table == "player_snapshots" and values.get("date_basis", "").startswith("Performance screenshot linked to approved match "):
                    values["date_basis"] = f"Performance screenshot linked to approved match {values['match_id']}"
                if table == "reviews":
                    source_id = values["source_id"]
                    revision = revisions.get(source_id, 0) + 1
                    revisions[source_id] = revision
                    values["revision"] = revision
                    values["legacy_payload_hash"] = values["payload_hash"]
                    payload = normalize_references(connection, json.loads(values["payload_json"]), allow_legacy=True)
                    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False)
                    values["payload_json"] = serialized
                    payload_hash = hashlib.sha256(serialized.encode()).hexdigest()
                    if (source_id, payload_hash) in seen_hashes:
                        payload_hash = hashlib.sha256(f"{serialized}:migrated_revision:{revision}".encode()).hexdigest()
                    values["payload_hash"] = payload_hash
                    seen_hashes.add((source_id, payload_hash))
                values = {field: value for field, value in values.items() if field in columns}
                fields = ", ".join(f'"{field}"' for field in values)
                placeholders = ", ".join("?" for field in values)
                connection.execute(f'INSERT INTO "{table}"({fields}) VALUES ({placeholders})', tuple(values.values()))
            old_count = connection.execute(f'SELECT COUNT(*) FROM "legacy_{table}"').fetchone()[0]
            new_count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if old_count != new_count:
                raise ValueError(f"Migration changed {table} record count: {old_count} -> {new_count}")
        for table in reversed(tables):
            connection.execute(f'DROP TABLE "legacy_{table}"')
        problems = connection.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise ValueError(f"UUID migration created invalid references: {problems}")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("UUID migration failed SQLite integrity validation")
        connection.execute("PRAGMA user_version = 3")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
    return backup_path
