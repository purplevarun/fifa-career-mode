import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from . import EXTRACTOR_VERSION, SCHEMA_VERSION
from .database import EXPORT_TABLES, image_hash, json_text, status, validate_database


BOOLEAN_FIELDS = {"is_preseason", "extra_time", "started"}
RECORD_TABLES = {
    "match": "matches", "player_match": "player_matches", "player_snapshot": "player_snapshots",
    "player_competition_snapshot": "player_competition_snapshots",
    "player_transfer": "player_transfers", "competition_event": "competition_events",
}
CONTEXT_FIELDS = {
    "type", "player", "player_id", "nationality", "club", "season", "competition",
    "competition_kind", "is_preseason", "home_club", "away_club", "team_stats",
    "match_source_id", "from_club", "to_club",
}


def parse_sequences(value):
    if value is None:
        return None
    sequences = set()
    for part in value.split(","):
        matched = re.fullmatch(r"\s*(\d+)(?:-(\d+))?\s*", part)
        if not matched:
            raise ValueError(f"Invalid screenshot selection: {part!r}; use 73,76,808-810")
        start = int(matched.group(1))
        end = int(matched.group(2) or start)
        if end < start or end - start > 10000:
            raise ValueError(f"Invalid screenshot range: {part}")
        sequences.update(range(start, end + 1))
    return sequences


def select_sources(connection, sequences=None):
    paths = connection.execute(
        "SELECT path, sequence, source_id FROM source_paths WHERE present = 1 ORDER BY sequence, path"
    ).fetchall()
    selected = {}
    found = set()
    for path in paths:
        if sequences is not None and path["sequence"] not in sequences:
            continue
        found.add(path["sequence"])
        if path["source_id"] not in selected:
            source = dict(connection.execute("SELECT * FROM source_images WHERE id = ?", (path["source_id"],)).fetchone())
            selected[path["source_id"]] = {**source, "path": path["path"], "sequence": path["sequence"]}
    if sequences is not None and sequences - found:
        raise ValueError(f"Screenshot numbers not found: {sorted(sequences - found)}")
    return list(selected.values())


def extract_pending(connection, root, sequences=None, limit=20, reextract=False, extractor=None, progress=None):
    if limit < 1:
        raise ValueError("The extraction limit must be at least one")
    sources = select_sources(connection, sequences)
    counts = {"extracted": 0, "skipped": 0, "errors": 0, "remaining": 0}
    attempted = 0
    for source in sources:
        existing = connection.execute("SELECT 1 FROM extractions WHERE source_id = ?", (source["id"],)).fetchone()
        if existing and not reextract:
            counts["skipped"] += 1
            continue
        if source["width"] is None or source["height"] is None:
            counts["errors"] += 1
            continue
        if attempted >= limit:
            counts["remaining"] += 1
            continue
        attempted += 1
        if extractor is None:
            from .extraction import ScreenshotExtractor

            extractor = ScreenshotExtractor()
        if progress:
            progress(f"Extracting {source['path']}")
        try:
            path = Path(root) / source["path"]
            if image_hash(path) != source["id"]:
                raise ValueError("Image changed after inventory; run inventory again")
            result = extractor.extract(path)
            with connection:
                connection.execute(
                    "INSERT INTO extractions(source_id, extractor_version, candidate_json, evidence_json, issues_json) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(source_id) DO UPDATE SET "
                    "extractor_version = excluded.extractor_version, candidate_json = excluded.candidate_json, "
                    "evidence_json = excluded.evidence_json, issues_json = excluded.issues_json, extracted_at = CURRENT_TIMESTAMP",
                    (source["id"], EXTRACTOR_VERSION, json_text(result["records"]),
                     json_text(result["evidence"]), json_text(result["issues"])),
                )
                connection.execute(
                    "UPDATE source_images SET screen_type = ?, error = NULL, "
                    "status = CASE WHEN status IN ('imported', 'rejected') THEN status ELSE 'needs_review' END WHERE id = ?",
                    (result["screen_type"], source["id"]),
                )
            counts["extracted"] += 1
        except Exception as exception:
            with connection:
                connection.execute(
                    "UPDATE source_images SET error = ?, "
                    "status = CASE WHEN status = 'imported' THEN status ELSE 'error' END WHERE id = ?",
                    (str(exception), source["id"]),
                )
            counts["errors"] += 1
            if progress:
                progress(f"Needs attention: {source['path']}: {exception}")
    return counts


def make_review(connection, sequences=None, match_id=None):
    if match_id is not None and not connection.execute("SELECT 1 FROM matches WHERE id = ?", (match_id,)).fetchone():
        raise ValueError(f"Unknown match ID: {match_id}")
    sources = []
    for source in select_sources(connection, sequences):
        extraction = connection.execute("SELECT * FROM extractions WHERE source_id = ?", (source["id"],)).fetchone()
        if not extraction:
            continue
        latest = connection.execute(
            "SELECT payload_json FROM reviews WHERE source_id = ? ORDER BY id DESC LIMIT 1", (source["id"],),
        ).fetchone()
        previous = json.loads(latest["payload_json"]) if latest else None
        records = previous["records"] if previous else json.loads(extraction["candidate_json"])
        if match_id is not None:
            for record in records:
                if record.get("type") == "player_match":
                    record["match_id"] = match_id
                    record.pop("match_source_id", None)
        sources.append({
            "source_id": source["id"], "path": source["path"], "screen_type": source["screen_type"],
            "complete": previous["complete"] if previous else False,
            "records": records, "issues": json.loads(extraction["issues_json"]),
        })
    return {"schema_version": SCHEMA_VERSION, "sources": sources}


def normalized_name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A non-empty name is required")
    return " ".join(value.split())


def ensure_club(connection, name):
    name = normalized_name(name)
    alias = name.casefold()
    existing = connection.execute("SELECT club_id FROM club_aliases WHERE alias = ?", (alias,)).fetchone()
    if existing:
        return existing["club_id"]
    existing = connection.execute("SELECT id FROM clubs WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    club_id = existing["id"] if existing else connection.execute("INSERT INTO clubs(name) VALUES (?)", (name,)).lastrowid
    connection.execute("INSERT INTO club_aliases(alias, club_id) VALUES (?, ?)", (alias, club_id))
    return club_id


def ensure_player(connection, record):
    name = normalized_name(record.get("player"))
    alias = name.casefold()
    existing = connection.execute("SELECT player_id FROM player_aliases WHERE alias = ?", (alias,)).fetchone()
    explicit_id = record.get("player_id")
    if explicit_id is not None:
        if type(explicit_id) is not int or not connection.execute("SELECT 1 FROM players WHERE id = ?", (explicit_id,)).fetchone():
            raise ValueError(f"Unknown player ID: {explicit_id}")
        if existing and existing["player_id"] != explicit_id:
            raise ValueError(f"Player alias {name!r} already belongs to a different player")
        player_id = explicit_id
    elif existing:
        player_id = existing["player_id"]
    else:
        player_id = connection.execute("INSERT INTO players(name) VALUES (?)", (name,)).lastrowid
    connection.execute("INSERT OR IGNORE INTO player_aliases(alias, player_id) VALUES (?, ?)", (alias, player_id))
    if record.get("nationality"):
        nationality = normalized_name(record["nationality"])
        current = connection.execute("SELECT nationality FROM players WHERE id = ?", (player_id,)).fetchone()[0]
        if current is not None and current != nationality:
            raise ValueError(f"Conflicting nationality for {name}")
        connection.execute("UPDATE players SET nationality = ? WHERE id = ?", (nationality, player_id))
    return player_id


def ensure_season(connection, label):
    if not isinstance(label, str) or not re.fullmatch(r"20\d{2}/\d{2}", label):
        raise ValueError("A season such as 2018/19 is required")
    if int(label[-2:]) != (int(label[:4]) + 1) % 100:
        raise ValueError(f"Season years must be consecutive: {label}")
    connection.execute("INSERT OR IGNORE INTO seasons(label) VALUES (?)", (label,))
    return connection.execute("SELECT id FROM seasons WHERE label = ?", (label,)).fetchone()[0]


def ensure_edition(connection, record):
    season_id = ensure_season(connection, record.get("season"))
    name = normalized_name(record.get("competition"))
    competition = connection.execute("SELECT * FROM competitions WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if competition is None:
        if type(record.get("is_preseason")) is not bool or record.get("competition_kind") not in {"league", "cup", "friendly"}:
            raise ValueError("A new competition requires competition_kind and an explicit boolean is_preseason")
        competition_id = connection.execute(
            "INSERT INTO competitions(name, kind, is_preseason) VALUES (?, ?, ?)",
            (name, record["competition_kind"], record["is_preseason"]),
        ).lastrowid
    else:
        if "is_preseason" in record and (type(record["is_preseason"]) is not bool or
                                          record["is_preseason"] != bool(competition["is_preseason"])):
            raise ValueError(f"Preseason classification conflicts with the saved competition: {name}")
        competition_id = competition["id"]
    connection.execute(
        "INSERT OR IGNORE INTO competition_seasons(competition_id, season_id) VALUES (?, ?)", (competition_id, season_id),
    )
    return connection.execute(
        "SELECT id FROM competition_seasons WHERE competition_id = ? AND season_id = ?", (competition_id, season_id),
    ).fetchone()[0]


def check_season_date(label, observed_on):
    if observed_on is None:
        return
    observed = date.fromisoformat(observed_on)
    first_year = observed.year - (observed.month < 7)
    if int(label[:4]) != first_year:
        raise ValueError(f"Date {observed_on} is outside the July-June career season {label}")


def checked_values(connection, table, record):
    columns = {row["name"]: row["type"] for row in connection.execute(f"PRAGMA table_info({table})")}
    unknown = set(record) - set(columns) - CONTEXT_FIELDS
    if unknown:
        raise ValueError(f"Unrecognized {table} fields: {sorted(unknown)}")
    values = {field: value for field, value in record.items() if field in columns and field != "id"}
    for field, value in values.items():
        if value is None:
            continue
        if columns[field] == "INTEGER":
            if field in BOOLEAN_FIELDS and type(value) is bool:
                continue
            if type(value) is not int:
                raise ValueError(f"{table}.{field} must be an integer or null")
        elif columns[field] == "REAL":
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{table}.{field} must be a finite number or null")
        elif not isinstance(value, str):
            raise ValueError(f"{table}.{field} must be text or null")
        if field.endswith("_on") or field in {"date_from", "date_to"}:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError(f"{field} must use YYYY-MM-DD")
    return values


def merge_record(connection, table, values, key, replace_reviewed=False):
    where = " AND ".join(f"{field} IS ?" for field in key)
    existing = connection.execute(f"SELECT * FROM {table} WHERE {where}", tuple(key.values())).fetchone()
    if existing:
        changes = {}
        for field, value in values.items():
            if field in key or value == existing[field]:
                continue
            if value is None and not replace_reviewed:
                continue
            if existing[field] is not None and not replace_reviewed:
                raise ValueError(f"Conflict in {table} {existing['id']}, {field}: {existing[field]!r} versus {value!r}; "
                                 "review the source and use --replace-reviewed only for an intentional correction")
            changes[field] = value
        if changes:
            setters = ", ".join(f"{field} = ?" for field in changes)
            connection.execute(f"UPDATE {table} SET {setters} WHERE id = ?", (*changes.values(), existing["id"]))
        return existing["id"]
    columns = ", ".join(values)
    placeholders = ", ".join("?" for field in values)
    return connection.execute(f"INSERT INTO {table}({columns}) VALUES ({placeholders})", tuple(values.values())).lastrowid


def confirmed_match(connection, record):
    match_id = record.get("match_id")
    source_id = record.get("match_source_id")
    if match_id is not None and source_id:
        raise ValueError("Supply either match_id or match_source_id, not both")
    if source_id:
        matches = connection.execute("SELECT match_id FROM match_sources WHERE source_id = ?", (source_id,)).fetchall()
        if len(matches) != 1:
            raise ValueError("The referenced match screenshot must resolve to exactly one approved match")
        match_id = matches[0]["match_id"]
    if type(match_id) is not int:
        raise ValueError("A verified match_id or match_source_id is required for a player appearance")
    match = connection.execute(
        "SELECT matches.*, competition_seasons.season_id FROM matches "
        "JOIN competition_seasons ON competition_seasons.id = matches.competition_season_id WHERE matches.id = ?", (match_id,),
    ).fetchone()
    if not match:
        raise ValueError(f"Unknown match: {match_id}")
    return match


def import_record(connection, source_id, record, replace_reviewed=False):
    record_type = record.get("type")
    if record_type not in RECORD_TABLES:
        raise ValueError(f"Unsupported reviewed record type: {record_type}")
    table = RECORD_TABLES[record_type]
    values = checked_values(connection, table, record)
    if record_type == "match":
        values.update(competition_season_id=ensure_edition(connection, record),
                      home_club_id=ensure_club(connection, record.get("home_club")),
                      away_club_id=ensure_club(connection, record.get("away_club")))
        if not values.get("played_on"):
            raise ValueError("An approved match needs an exact played_on date")
        check_season_date(record["season"], values["played_on"])
        key = {field: values[field] for field in ("competition_season_id", "played_on", "home_club_id", "away_club_id")}
        linked = connection.execute(
            "SELECT matches.* FROM matches JOIN match_sources ON match_sources.match_id = matches.id WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        if linked and any(linked[field] != value for field, value in key.items()):
            raise ValueError("This source already belongs to a different fixture; identity changes need separate review")
        record_id = merge_record(connection, table, values, key, replace_reviewed)
        connection.execute("INSERT OR IGNORE INTO match_sources(match_id, source_id) VALUES (?, ?)", (record_id, source_id))
        team_stats = record.get("team_stats", {})
        if not isinstance(team_stats, dict) or set(team_stats) - {"home", "away"}:
            raise ValueError("team_stats must contain only home and away objects")
        for side, stats in team_stats.items():
            team_values = checked_values(connection, "team_matches", stats)
            team_key = {"match_id": record_id, "club_id": values[f"{side}_club_id"]}
            merge_record(connection, "team_matches", {**team_values, **team_key}, team_key, replace_reviewed)
        return record_id
    if record_type == "player_match":
        fixture = confirmed_match(connection, record)
        values.update(match_id=fixture["id"], player_id=ensure_player(connection, record),
                      club_id=ensure_club(connection, record.get("club")))
        linked = connection.execute(
            "SELECT player_matches.* FROM player_matches JOIN player_match_sources "
            "ON player_match_sources.player_match_id = player_matches.id WHERE source_id = ?", (source_id,),
        ).fetchone()
        key = {field: values[field] for field in ("match_id", "player_id")}
        if linked and any(linked[field] != value for field, value in key.items()):
            raise ValueError("This performance source is already linked to a different player or match")
        record_id = merge_record(connection, table, values, key, replace_reviewed)
        connection.execute("INSERT OR IGNORE INTO player_match_sources(player_match_id, source_id) VALUES (?, ?)", (record_id, source_id))
        if "overall" in values and (values["overall"] is not None or replace_reviewed):
            snapshot_key = {"player_id": values["player_id"], "match_id": fixture["id"], "snapshot_kind": "in_season"}
            snapshot_values = {
                **snapshot_key, "club_id": values["club_id"], "season_id": fixture["season_id"], "source_id": source_id,
                "observed_on": fixture["played_on"], "date_precision": "day",
                "date_basis": f"Performance screenshot linked to approved match {fixture['id']}",
                "overall": values["overall"], "displayed_position": values.get("displayed_position"),
            }
            existing = connection.execute(
                "SELECT source_id FROM player_snapshots WHERE player_id = ? AND match_id = ? AND snapshot_kind = 'in_season'",
                (values["player_id"], fixture["id"]),
            ).fetchone()
            if existing:
                snapshot_values["source_id"] = existing["source_id"]
            merge_record(connection, "player_snapshots", snapshot_values, snapshot_key, replace_reviewed)
        return record_id
    values["source_id"] = source_id
    if record_type in {"player_snapshot", "player_competition_snapshot", "player_transfer"}:
        values["player_id"] = ensure_player(connection, record)
    if record_type in {"player_snapshot", "player_competition_snapshot"}:
        values["season_id"] = ensure_season(connection, record.get("season"))
        values["club_id"] = ensure_club(connection, record["club"]) if record.get("club") else None
        check_season_date(record["season"], values.get("observed_on"))
    if record_type == "player_snapshot":
        if values.get("match_id") is not None:
            fixture = confirmed_match(connection, record)
            if values["season_id"] != fixture["season_id"] or values.get("observed_on") != fixture["played_on"]:
                raise ValueError("Snapshot date and season must agree with its linked match")
        key = {field: values[field] for field in ("source_id", "player_id", "season_id")}
    elif record_type == "player_competition_snapshot":
        values["competition_season_id"] = ensure_edition(connection, record) if record.get("scope") == "competition" else None
        key = {field: values[field] for field in ("source_id", "player_id", "season_id", "competition_season_id")}
    elif record_type == "player_transfer":
        values.update(from_club_id=ensure_club(connection, record["from_club"]) if record.get("from_club") else None,
                      to_club_id=ensure_club(connection, record["to_club"]) if record.get("to_club") else None)
        key = {field: values[field] for field in ("source_id", "player_id", "transfer_type")}
    else:
        values["competition_season_id"] = ensure_edition(connection, record)
        values["player_id"] = ensure_player(connection, record) if record.get("player") else None
        values["club_id"] = ensure_club(connection, record["club"]) if record.get("club") else None
        key = {field: values.get(field) for field in ("source_id", "event_type", "player_id", "club_id", "period")}
    return merge_record(connection, table, values, key, replace_reviewed)


def approve_review(connection, document, note, replace_reviewed=False):
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION or not isinstance(document.get("sources"), list):
        raise ValueError("Unsupported or invalid review document")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("A review note is required")
    counts = {"approved_sources": 0, "skipped_reviews": 0, "reviewed_records": 0}
    seen = set()
    with connection:
        for source in document["sources"]:
            if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
                raise ValueError("Each reviewed source needs a source_id string")
            source_id = source.get("source_id")
            if source_id in seen:
                raise ValueError("A review document cannot include the same source twice")
            seen.add(source_id)
            if not connection.execute("SELECT 1 FROM source_images WHERE id = ?", (source_id,)).fetchone():
                raise ValueError(f"Source must be inventoried before review: {source_id}")
            if type(source.get("complete")) is not bool:
                raise ValueError("Set complete to true or false to describe the reviewed source coverage")
            records = source.get("records")
            if not isinstance(records, list) or not records:
                raise ValueError("A source needs at least one reviewed record; unsupported screens must remain queued")
            payload = {"records": records, "complete": source["complete"]}
            serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False)
            payload_hash = hashlib.sha256(serialized.encode()).hexdigest()
            existing = connection.execute("SELECT 1 FROM reviews WHERE source_id = ? AND payload_hash = ?", (source_id, payload_hash)).fetchone()
            if existing and not replace_reviewed:
                counts["skipped_reviews"] += 1
                continue
            if replace_reviewed:
                previous_id = connection.execute("SELECT COALESCE(MAX(id), 0) FROM reviews WHERE source_id = ?", (source_id,)).fetchone()[0]
                payload_hash = hashlib.sha256(f"{serialized}:correction_after:{previous_id}".encode()).hexdigest()
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("Each reviewed record must be an object")
                import_record(connection, source_id, record, replace_reviewed)
                counts["reviewed_records"] += 1
            connection.execute("INSERT INTO reviews(source_id, payload_json, payload_hash, note) VALUES (?, ?, ?, ?)",
                               (source_id, serialized, payload_hash, note.strip()))
            connection.execute("UPDATE source_images SET status = ?, error = NULL WHERE id = ?",
                               ("imported" if source["complete"] else "needs_review", source_id))
            counts["approved_sources"] += 1
        errors = validate_database(connection)
        if errors:
            raise ValueError("Database validation failed: " + "; ".join(errors))
    return counts


def write_json(path, value, overwrite=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        with path.open("x", encoding="utf-8") as output:
            output.write(json_text(value))
        return
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
            temporary_path = Path(output.name)
            output.write(json_text(value))
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def export_data(connection, output_path):
    errors = validate_database(connection)
    if errors:
        raise ValueError("Cannot export an invalid database: " + "; ".join(errors))
    data = {"schema_version": SCHEMA_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
            "coverage": status(connection)}
    for table in EXPORT_TABLES:
        ordering = "1, 2" if table.endswith("_sources") else "id"
        rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY {ordering}")]
        for row in rows:
            for field in BOOLEAN_FIELDS & row.keys():
                if row[field] is not None:
                    row[field] = bool(row[field])
        data[table] = rows
    data["source_images"] = [dict(row) for row in connection.execute(
        "SELECT source_images.id, screen_type, status, "
        "COALESCE(MIN(CASE WHEN present = 1 THEN path END), MIN(path)) AS path, "
        "COALESCE(MAX(present), 0) AS available FROM source_images "
        "LEFT JOIN source_paths ON source_paths.source_id = source_images.id "
        "GROUP BY source_images.id ORDER BY path"
    )]
    for source in data["source_images"]:
        source["available"] = bool(source["available"])
    write_json(output_path, data)
    return {"output": str(output_path), "matches": len(data["matches"]),
            "player_matches": len(data["player_matches"]), "player_snapshots": len(data["player_snapshots"])}


def backup_database(connection, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb"):
        pass
    backup = sqlite3.connect(destination)
    try:
        connection.backup(backup)
    finally:
        backup.close()
    return {"backup": str(destination)}
