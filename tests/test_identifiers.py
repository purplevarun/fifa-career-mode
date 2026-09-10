import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from career_data.identifiers import is_uuid, new_id, resolve_id
from career_data.migrations import migrate_to_uuids
from career_data.database import connect, inventory, validate_database
from career_data.pipeline import approve_review
from PIL import Image


class IdentifierTests(unittest.TestCase):
    def test_ids_are_distinct_canonical_uuids(self):
        identifiers = {new_id() for index in range(100)}
        self.assertEqual(len(identifiers), 100)
        self.assertTrue(all(is_uuid(identifier) for identifier in identifiers))
        for invalid in (1, "1", True, None, "", "a" * 64, "00000000-0000-0000-0000-000000000000"):
            self.assertFalse(is_uuid(invalid))

    def test_legacy_ids_resolve_only_with_explicit_compatibility(self):
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE TABLE legacy_ids(entity_table TEXT, old_value TEXT, uuid TEXT)")
            identifier = new_id()
            connection.execute("INSERT INTO legacy_ids VALUES ('matches', '1', ?)", (identifier,))
            self.assertEqual(resolve_id(connection, "matches", identifier), identifier)
            with self.assertRaises(ValueError):
                resolve_id(connection, "matches", 1)
            self.assertEqual(resolve_id(connection, "matches", 1, allow_legacy=True), identifier)
            with self.assertRaises(ValueError):
                resolve_id(connection, "players", 1, allow_legacy=True)

    def test_migration_preserves_uuid_links_and_review_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "career.sqlite"
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            connection.executescript("""
                CREATE TABLE source_images(id TEXT PRIMARY KEY, byte_size INTEGER, width INTEGER, height INTEGER);
                CREATE TABLE source_paths(path TEXT PRIMARY KEY, source_id TEXT REFERENCES source_images(id), sequence INTEGER, present INTEGER);
                CREATE TABLE players(id INTEGER PRIMARY KEY, name TEXT, nationality TEXT);
                CREATE TABLE player_aliases(alias TEXT PRIMARY KEY, player_id INTEGER REFERENCES players(id));
                CREATE TABLE reviews(id INTEGER PRIMARY KEY, source_id TEXT REFERENCES source_images(id), payload_json TEXT, payload_hash TEXT, note TEXT, reviewed_at TEXT);
                PRAGMA user_version = 2;
            """)
            source_hash = "a" * 64
            connection.execute("INSERT INTO source_images VALUES (?, 10, 40, 20)", (source_hash,))
            connection.execute("INSERT INTO source_paths VALUES ('raw_data/example.png', ?, 1, 1)", (source_hash,))
            connection.execute("INSERT INTO players VALUES (1, 'Aaron Ramsdale', 'England')")
            connection.execute("INSERT INTO player_aliases VALUES ('a. ramsdale', 1)")
            for revision, goals in ((1, 0), (2, 1), (3, 0)):
                payload = json.dumps({"complete": True, "records": [{"player_id": 1, "goals": goals}]})
                connection.execute("INSERT INTO reviews VALUES (?, ?, ?, ?, 'Checked', '2026-09-10')",
                                   (revision, source_hash, payload, str(revision)))
            connection.commit()
            schema = (Path(__file__).resolve().parents[1] / "career_data/schema.sql").read_text()
            backup_path = migrate_to_uuids(connection, path, schema)
            player_id = connection.execute("SELECT id FROM players").fetchone()[0]
            self.assertTrue(is_uuid(player_id))
            self.assertEqual(connection.execute("SELECT player_id FROM player_aliases").fetchone()[0], player_id)
            image = connection.execute("SELECT id, sha256 FROM source_images").fetchone()
            self.assertTrue(is_uuid(image["id"]))
            self.assertEqual(image["sha256"], source_hash)
            self.assertEqual(connection.execute("SELECT source_id FROM source_paths").fetchone()[0], image["id"])
            reviews = connection.execute("SELECT * FROM reviews ORDER BY revision").fetchall()
            self.assertEqual([row["revision"] for row in reviews], [1, 2, 3])
            self.assertTrue(all(is_uuid(row["id"]) for row in reviews))
            self.assertEqual(json.loads(reviews[-1]["payload_json"])["records"][0], {"player_id": player_id, "goals": 0})
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertTrue(backup_path.exists())
            connection.close()

    def test_fresh_importer_uses_uuid_entities_and_stable_source_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw_data").mkdir()
            Image.new("RGB", (40, 20), "white").save(root / "raw_data/Screenshot (73).png")
            connection = connect(root / "career.sqlite")
            self.assertEqual(inventory(connection, root)["new_images"], 1)
            source = connection.execute("SELECT id, sha256 FROM source_images").fetchone()
            self.assertTrue(is_uuid(source["id"]))
            self.assertEqual(len(source["sha256"]), 64)
            self.assertEqual(inventory(connection, root)["new_images"], 0)
            self.assertEqual(connection.execute("SELECT id FROM source_images").fetchone()[0], source["id"])
            fixture = {"type": "match", "season": "2018/19", "competition": "European International Cup",
                       "played_on": "2018-07-04", "home_club": "Notts County", "away_club": "Dundee FC",
                       "home_goals": 1, "away_goals": 1}
            review = {"schema_version": 3, "sources": [{"source_id": source["id"], "complete": True, "records": [fixture]}]}
            approve_review(connection, review, "UUID smoke test")
            self.assertEqual(approve_review(connection, review, "Repeat")["skipped_reviews"], 1)
            for table in ("matches", "clubs", "seasons", "competitions", "competition_seasons", "reviews"):
                self.assertTrue(all(is_uuid(row[0]) for row in connection.execute(f"SELECT id FROM {table}")))
            self.assertEqual(validate_database(connection), [])
            connection.close()

    def test_failed_migration_rolls_back_original_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "career.sqlite"
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            connection.executescript("""
                CREATE TABLE players(id INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE player_aliases(alias TEXT PRIMARY KEY, player_id INTEGER REFERENCES players(id));
                INSERT INTO players VALUES (1, 'Original Player');
                INSERT INTO player_aliases VALUES ('broken alias', 999);
                PRAGMA user_version = 2;
            """)
            schema = (Path(__file__).resolve().parents[1] / "career_data/schema.sql").read_text()
            with self.assertRaises(KeyError):
                migrate_to_uuids(connection, path, schema)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(tuple(connection.execute("SELECT * FROM players").fetchone()), (1, "Original Player"))
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name = 'legacy_players'").fetchone())
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(len(list((Path(directory) / "backups").glob("*.sqlite"))), 1)
            connection.close()


if __name__ == "__main__":
    unittest.main()
