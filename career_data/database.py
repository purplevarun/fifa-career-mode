import hashlib
import json
import re
import sqlite3
from pathlib import Path

from PIL import Image

from . import SCHEMA_VERSION


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
COMPETITIONS = (
    ("European International Cup", "cup", True),
    ("Invitational Cup", "cup", True),
    ("EFL League Two", "league", False),
    ("EFL League One", "league", False),
    ("Carabao Cup", "cup", False),
    ("Checkatrade Trophy", "cup", False),
    ("FA Cup", "cup", False),
)
EXPORT_TABLES = (
    "players", "clubs", "seasons", "competitions", "competition_seasons",
    "matches", "team_matches", "player_matches", "player_snapshots",
    "player_competition_snapshots", "player_transfers", "competition_events",
    "match_sources", "player_match_sources",
)


def connect(database_path):
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, SCHEMA_VERSION):
        connection.close()
        raise ValueError(f"Unsupported database schema version: {version}")
    if version == 0:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table'").fetchone():
            connection.close()
            raise ValueError("Refusing to initialize an existing unversioned database")
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        try:
            connection.executescript(f"BEGIN;\n{schema}")
            connection.executemany(
                "INSERT INTO competitions(name, kind, is_preseason) VALUES (?, ?, ?)",
                COMPETITIONS,
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()
        except Exception:
            connection.rollback()
            connection.close()
            raise
    return connection


def image_hash(path):
    with Path(path).open("rb") as image_file:
        return hashlib.file_digest(image_file, "sha256").hexdigest()


def screenshot_sequence(path):
    match = re.search(r"(\d+)(?=\D*$)", Path(path).stem)
    return int(match.group(1)) if match else None


def inventory(connection, root):
    root = Path(root).resolve()
    raw_directory = root / "raw_data"
    if not raw_directory.is_dir():
        raise ValueError(f"Screenshot directory does not exist: {raw_directory}")
    counts = {"files": 0, "new_images": 0, "known_images": 0, "unreadable": 0}
    paths = sorted(
        (path for path in raw_directory.rglob("*") if path.is_file()
         and path.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda path: (screenshot_sequence(path) or 0, path.as_posix()),
    )
    with connection:
        connection.execute("UPDATE source_paths SET present = 0")
        for path in paths:
            if not path.resolve().is_relative_to(root):
                raise ValueError(f"Image resolves outside the project: {path}")
            source_id = image_hash(path)
            counts["files"] += 1
            known = connection.execute("SELECT id FROM source_images WHERE id = ?", (source_id,)).fetchone()
            if known:
                counts["known_images"] += 1
            else:
                width = height = None
                error = None
                try:
                    with Image.open(path) as image:
                        width, height = image.size
                        image.verify()
                except (OSError, ValueError, SyntaxError) as exception:
                    error = str(exception)
                    counts["unreadable"] += 1
                connection.execute(
                    "INSERT INTO source_images(id, byte_size, width, height, status, error) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (source_id, path.stat().st_size, width, height,
                     "error" if error else "inventoried", error),
                )
                counts["new_images"] += 1
            connection.execute(
                "INSERT INTO source_paths(path, source_id, sequence, present) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(path) DO UPDATE SET source_id = excluded.source_id, "
                "sequence = excluded.sequence, present = 1",
                (path.relative_to(root).as_posix(), source_id, screenshot_sequence(path)),
            )
    return counts


def status(connection):
    return {
        "schema_version": SCHEMA_VERSION,
        "source_images": connection.execute("SELECT COUNT(*) FROM source_images").fetchone()[0],
        "present_paths": connection.execute("SELECT COUNT(*) FROM source_paths WHERE present = 1").fetchone()[0],
        "source_states": dict(connection.execute("SELECT status, COUNT(*) FROM source_images GROUP BY status")),
        "screen_types": dict(connection.execute("SELECT screen_type, COUNT(*) FROM source_images GROUP BY screen_type")),
        "records": {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in EXPORT_TABLES if not table.endswith("_sources")},
    }


def validate_database(connection):
    errors = []
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        errors.append(integrity)
    errors.extend(str(tuple(row)) for row in connection.execute("PRAGMA foreign_key_check"))
    for table in ("team_matches", "player_matches"):
        invalid = connection.execute(
            f"SELECT record.id FROM {table} record JOIN matches fixture ON fixture.id = record.match_id "
            "WHERE record.club_id NOT IN (fixture.home_club_id, fixture.away_club_id)"
        ).fetchall()
        errors.extend(f"{table} {row['id']}: club is not a match participant" for row in invalid)
    return errors


def json_text(value):
    return json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n"
