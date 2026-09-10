import copy
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from career_data.database import connect, coverage_report, inventory, status, validate_database
from career_data.pipeline import approve_review, backup_database, export_data, extract_pending, make_review
from career_data.batch_review import fixture_contexts, prepare_player_cores


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.raw = self.root / "raw_data"
        self.raw.mkdir()
        self.connection = connect(self.root / "career.sqlite")
        self.addCleanup(self.connection.close)

    def create_image(self, name="Screenshot (73).png", color="white"):
        path = self.raw / name
        Image.new("RGB", (40, 20), color).save(path)
        return path

    def create_match(self):
        self.connection.execute("INSERT INTO seasons(label) VALUES ('2018/19')")
        self.connection.execute("INSERT INTO competition_seasons(competition_id, season_id) VALUES (1, 1)")
        self.connection.executemany("INSERT INTO clubs(name) VALUES (?)", [("Notts County",), ("Dundee FC",), ("Other Club",)])
        return self.connection.execute(
            "INSERT INTO matches(competition_season_id, played_on, home_club_id, away_club_id, home_goals, away_goals) "
            "VALUES (1, '2018-07-04', 1, 2, 1, 1)"
        ).lastrowid


class DatabaseTests(DatabaseTestCase):
    def test_version_one_migration_preserves_existing_records(self):
        match_id = self.create_match()
        self.connection.execute("INSERT INTO players(name) VALUES ('Aaron Ramsdale')")
        self.connection.execute("INSERT INTO player_matches(match_id, player_id, club_id, goals_conceded) VALUES (?, 1, 1, 2)", (match_id,))
        self.connection.execute("ALTER TABLE player_matches DROP COLUMN goals_conceded_displayed")
        self.connection.execute("ALTER TABLE player_matches DROP COLUMN goals_conceded_basis")
        self.connection.execute("PRAGMA user_version = 1")
        self.connection.commit()
        self.connection.close()
        self.connection = connect(self.root / "career.sqlite")
        self.addCleanup(self.connection.close)
        self.assertEqual(self.connection.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(tuple(self.connection.execute("SELECT goals_conceded, goals_conceded_displayed FROM player_matches").fetchone()), (2, 2))
        self.assertEqual(validate_database(self.connection), [])

    def test_empty_coverage_has_no_invented_matches(self):
        report = coverage_report(self.connection)
        self.assertEqual(report["summary"]["matches"], 0)
        self.assertEqual(report["summary"]["minimum_player_records_per_match"], 0)
        self.assertEqual(report["warnings"], [])

    def test_inventory_is_content_based_and_repeatable(self):
        original = self.create_image()
        shutil.copyfile(original, self.raw / "Screenshot (74).png")
        first = inventory(self.connection, self.root)
        self.assertEqual(first["new_images"], 1)
        self.assertEqual(first["files"], 2)
        self.connection.execute("UPDATE source_images SET status = 'imported'")
        self.connection.commit()
        second = inventory(self.connection, self.root)
        self.assertEqual(second["new_images"], 0)
        self.assertEqual(status(self.connection)["source_states"], {"imported": 1})
        original.rename(self.raw / "Screenshot (75).png")
        inventory(self.connection, self.root)
        self.assertEqual(status(self.connection)["source_images"], 1)
        self.assertEqual(status(self.connection)["present_paths"], 2)

    def test_changed_image_keeps_old_source_history(self):
        self.create_image()
        inventory(self.connection, self.root)
        self.create_image(color="black")
        inventory(self.connection, self.root)
        self.assertEqual(status(self.connection)["source_images"], 2)
        self.assertEqual(status(self.connection)["present_paths"], 1)

    def test_corrupt_image_is_reported(self):
        (self.raw / "broken.png").write_bytes(b"not an image")
        self.assertEqual(inventory(self.connection, self.root)["unreadable"], 1)
        self.assertEqual(status(self.connection)["source_states"], {"error": 1})

    def test_competitions_require_boolean_preseason(self):
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM competitions WHERE is_preseason = 1"
        ).fetchone()[0], 2)
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("INSERT INTO competitions(name, kind, is_preseason) VALUES ('Invalid', 'cup', 2)")

    def test_matches_cannot_have_missing_competition(self):
        self.create_match()
        for edition in (None, 999):
            with self.assertRaises(sqlite3.IntegrityError):
                self.connection.execute(
                    "INSERT INTO matches(competition_season_id, played_on, home_club_id, away_club_id) "
                    "VALUES (?, '2018-07-05', 1, 2)", (edition,),
                )

    def test_appearance_must_belong_to_participating_club(self):
        match_id = self.create_match()
        self.connection.execute("INSERT INTO players(name) VALUES ('Takefusa Kubo')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO player_matches(match_id, player_id, club_id) VALUES (?, 1, 3)", (match_id,),
            )
        self.connection.execute("INSERT INTO player_matches(match_id, player_id, club_id) VALUES (?, 1, 1)", (match_id,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("INSERT INTO player_matches(match_id, player_id, club_id) VALUES (?, 1, 1)", (match_id,))
        self.assertEqual(validate_database(self.connection), [])

    def test_snapshot_requires_supported_date_precision(self):
        self.create_image()
        inventory(self.connection, self.root)
        self.create_match()
        self.connection.execute("INSERT INTO players(name) VALUES ('Aaron Ramsdale')")
        source_id = self.connection.execute("SELECT id FROM source_images").fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO player_snapshots(player_id, season_id, source_id, snapshot_kind, date_precision, date_basis) "
                "VALUES (1, 1, ?, 'season_start', 'day', 'Date missing')", (source_id,),
            )
        self.connection.execute(
            "INSERT INTO player_snapshots(player_id, season_id, source_id, snapshot_kind, date_precision, date_basis, overall) "
            "VALUES (1, 1, ?, 'first_observed', 'season', 'Opening squad screen, exact day unknown', 62)", (source_id,),
        )
        self.assertEqual(self.connection.execute("SELECT observed_on FROM player_snapshots").fetchone()[0], None)


class ImportTests(DatabaseTestCase):
    def prepare_source(self, sequence, color):
        self.create_image(f"Screenshot ({sequence}).png", color)
        inventory(self.connection, self.root)
        return self.connection.execute("SELECT source_id FROM source_paths WHERE sequence = ?", (sequence,)).fetchone()[0]

    def review(self, source_id, records, complete=True):
        return {"schema_version": 1, "sources": [{"source_id": source_id, "complete": complete, "records": records}]}

    def match_record(self):
        return {"type": "match", "competition": "European International Cup", "season": "2018/19",
                "played_on": "2018-07-04", "home_club": "Notts County", "away_club": "Dundee FC",
                "home_goals": 1, "away_goals": 1, "team_stats": {"home": {"shots": 6}, "away": {"fouls": 0}}}

    def approved_match(self):
        source_id = self.prepare_source(73, "white")
        document = self.review(source_id, [self.match_record()])
        approve_review(self.connection, document, "Verified against the screenshot")
        return source_id, document

    def test_review_is_repeatable_and_competition_is_preseason(self):
        source_id, document = self.approved_match()
        result = approve_review(self.connection, document, "Repeated import")
        self.assertEqual(result["skipped_reviews"], 1)
        self.assertEqual(status(self.connection)["records"]["matches"], 1)
        self.assertEqual(status(self.connection)["records"]["team_matches"], 2)
        self.assertEqual(self.connection.execute(
            "SELECT is_preseason FROM competitions JOIN competition_seasons ON competition_id = competitions.id "
            "JOIN matches ON competition_season_id = competition_seasons.id"
        ).fetchone()[0], 1)

    def test_different_capture_merges_same_match(self):
        self.approved_match()
        source_id = self.prepare_source(74, "gray")
        approve_review(self.connection, self.review(source_id, [self.match_record()]), "Duplicate capture, visually checked")
        self.assertEqual(status(self.connection)["records"]["matches"], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM match_sources").fetchone()[0], 2)

    def test_player_import_links_match_and_preserves_history(self):
        match_source, document = self.approved_match()
        player_source = self.prepare_source(76, "black")
        player = {"type": "player_match", "match_source_id": match_source, "player": "Takefusa Kubo",
                  "club": "Notts County", "overall": 63, "rating": 8.4, "goals": 0, "assists": 1}
        review = self.review(player_source, [player])
        approve_review(self.connection, review, "Player and fixture checked")
        approve_review(self.connection, review, "Rerun")
        self.assertEqual(status(self.connection)["records"]["player_matches"], 1)
        snapshot = self.connection.execute("SELECT * FROM player_snapshots").fetchone()
        self.assertEqual(snapshot["overall"], 63)
        self.assertEqual(snapshot["observed_on"], "2018-07-04")
        self.assertEqual(snapshot["snapshot_kind"], "in_season")
        extra_source = self.prepare_source(77, "blue")
        approve_review(self.connection, self.review(extra_source, [player]), "Same player, second capture")
        self.assertEqual(status(self.connection)["records"]["player_snapshots"], 1)

    def test_conflicts_require_explicit_correction(self):
        source_id, original = self.approved_match()
        corrected = copy.deepcopy(original)
        corrected["sources"][0]["records"][0]["home_goals"] = 2
        with self.assertRaisesRegex(ValueError, "Conflict"):
            approve_review(self.connection, corrected, "Unapproved conflicting value")
        self.assertEqual(self.connection.execute("SELECT home_goals FROM matches").fetchone()[0], 1)
        approve_review(self.connection, corrected, "Intentional visual correction", replace_reviewed=True)
        self.assertEqual(self.connection.execute("SELECT home_goals FROM matches").fetchone()[0], 2)
        approve_review(self.connection, original, "Older review must not undo newer correction")
        self.assertEqual(self.connection.execute("SELECT home_goals FROM matches").fetchone()[0], 2)

    def test_failed_batch_rolls_back_all_records(self):
        source_id = self.prepare_source(73, "white")
        bad_player = {"type": "player_match", "match_id": 999, "player": "Unknown", "club": "Notts County"}
        with self.assertRaises(ValueError):
            approve_review(self.connection, self.review(source_id, [self.match_record(), bad_player]), "Invalid batch")
        self.assertEqual(status(self.connection)["records"]["matches"], 0)
        self.assertEqual(status(self.connection)["records"]["clubs"], 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)

    def test_unknown_fields_and_string_numbers_are_rejected(self):
        source_id = self.prepare_source(73, "white")
        for update in ({"home_goals": "1"}, {"home_goal": 1}, {"home_goals": True}):
            with self.assertRaises(ValueError):
                approve_review(self.connection, self.review(source_id, [{**self.match_record(), **update}]), "Invalid data")
        self.assertEqual(status(self.connection)["records"]["matches"], 0)

    def test_match_date_must_belong_to_its_competition_season(self):
        source_id = self.prepare_source(73, "white")
        record = {**self.match_record(), "season": "2019/20"}
        with self.assertRaisesRegex(ValueError, "outside"):
            approve_review(self.connection, self.review(source_id, [record]), "Wrong season")
        self.assertEqual(status(self.connection)["records"]["matches"], 0)

    def test_new_competition_requires_explicit_classification(self):
        source_id = self.prepare_source(73, "white")
        record = {**self.match_record(), "competition": "Preseason Friendlies"}
        with self.assertRaises(ValueError):
            approve_review(self.connection, self.review(source_id, [record]), "Missing classification")
        record.update(is_preseason=True, competition_kind="friendly")
        approve_review(self.connection, self.review(source_id, [record]), "Verified standalone preseason friendly")
        self.assertEqual(status(self.connection)["records"]["matches"], 1)

    def test_extraction_never_overwrites_approved_data(self):
        source_id, document = self.approved_match()

        class FakeExtractor:
            def extract(self, path):
                return {"screen_type": "match_facts", "records": [{"type": "match", "home_goals": 99}],
                        "evidence": {}, "issues": ["Synthetic bad OCR"]}

        result = extract_pending(self.connection, self.root, {73}, extractor=FakeExtractor())
        self.assertEqual(result["extracted"], 1)
        self.assertEqual(self.connection.execute("SELECT home_goals FROM matches").fetchone()[0], 1)
        result = extract_pending(self.connection, self.root, {73}, extractor=FakeExtractor())
        self.assertEqual(result["skipped"], 1)
        review = make_review(self.connection, {73})
        self.assertEqual(review["sources"][0]["records"][0]["home_goals"], 1)

    def test_export_and_backup_preserve_canonical_data(self):
        self.approved_match()
        output = self.root / "exports" / "career.json"
        export_data(self.connection, output)
        exported = json.loads(output.read_text())
        self.assertEqual(len(exported["matches"]), 1)
        self.assertIs(exported["competitions"][0]["is_preseason"], True)
        backup = self.root / "backup.sqlite"
        backup_database(self.connection, backup)
        with sqlite3.connect(backup) as restored:
            self.assertEqual(restored.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 1)
            self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        with self.assertRaises(FileExistsError):
            backup_database(self.connection, backup)

    def test_start_and_end_snapshots_are_distinct_and_partial_source_stays_queued(self):
        start_source = self.prepare_source(70, "white")
        end_source = self.prepare_source(1055, "black")
        base = {"type": "player_snapshot", "player": "Aaron Ramsdale", "season": "2018/19", "club": "Notts County",
                "date_precision": "season", "date_basis": "Boundary squad observation; day not visible"}
        start = {**base, "snapshot_kind": "season_start", "overall": 62}
        end = {**base, "snapshot_kind": "season_end", "overall": 65}
        approve_review(self.connection, self.review(start_source, [start], complete=False), "Opening squad")
        approve_review(self.connection, self.review(end_source, [end], complete=False), "Closing squad")
        self.assertEqual(status(self.connection)["records"]["players"], 1)
        self.assertEqual(status(self.connection)["records"]["player_snapshots"], 2)
        self.assertEqual(status(self.connection)["source_states"], {"needs_review": 2})

    def test_explicit_correction_can_clear_unknown_values_and_restore_previous_value(self):
        source_id, document = self.approved_match()
        cleared = copy.deepcopy(document)
        cleared["sources"][0]["records"][0].update(home_goals=None, away_goals=None)
        approve_review(self.connection, cleared, "Uncertain second reading should not overwrite known data")
        self.assertEqual(self.connection.execute("SELECT home_goals FROM matches").fetchone()[0], 1)
        approve_review(self.connection, cleared, "Withdraw the score after checking evidence", replace_reviewed=True)
        self.assertIsNone(self.connection.execute("SELECT home_goals FROM matches").fetchone()[0])
        approve_review(self.connection, document, "Restore the visually confirmed score", replace_reviewed=True)
        self.assertEqual(self.connection.execute("SELECT home_goals FROM matches").fetchone()[0], 1)
        self.assertEqual(status(self.connection)["records"]["matches"], 1)

    def test_export_uses_present_path_after_rename(self):
        self.approved_match()
        (self.raw / "Screenshot (73).png").rename(self.raw / "Screenshot (74).png")
        inventory(self.connection, self.root)
        output = self.root / "career.json"
        export_data(self.connection, output)
        source = json.loads(output.read_text())["source_images"][0]
        self.assertEqual(source["path"], "raw_data/Screenshot (74).png")
        self.assertIs(source["available"], True)

    def test_non_match_records_are_repeatable_and_totals_keep_their_scope(self):
        source_id = self.prepare_source(1055, "white")
        totals = {"type": "player_competition_snapshot", "player": "Aaron Ramsdale", "club": "Notts County",
                  "season": "2018/19", "scope": "all_competitions", "appearances": 53, "clean_sheets": 18}
        award = {"type": "competition_event", "competition": "EFL League Two", "season": "2018/19",
                 "player": "Aaron Ramsdale", "club": "Notts County", "event_type": "goalkeeper_of_the_competition",
                 "announced_on": "2019-05-04", "description": "Visually checked tournament award"}
        loan = {"type": "player_transfer", "player": "Dominic Calvert-Lewin", "to_club": "Notts County",
                "transfer_type": "loan", "date_basis": "26/08 shown; year is unconfirmed",
                "fee_minor": None, "contract_months": 12, "loan_months": 24}
        document = self.review(source_id, [totals, award, loan], complete=False)
        approve_review(self.connection, document, "Synthetic reviewed non-match records")
        approve_review(self.connection, document, "Repeat")
        self.assertIsNone(self.connection.execute("SELECT competition_season_id FROM player_competition_snapshots").fetchone()[0])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM player_competition_snapshots").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT contract_months, loan_months, fee_minor FROM player_transfers").fetchone()[:], (12, 24, None))

    def test_core_batch_never_imports_unreviewed_detailed_fields(self):
        match_source, document = self.approved_match()
        self.connection.execute("UPDATE source_images SET screen_type = 'match_facts' WHERE id = ?", (match_source,))
        self.connection.commit()
        player_source = self.prepare_source(76, "black")

        class FakePlayerExtractor:
            def extract(self, path):
                return {"screen_type": "player_performance", "evidence": {}, "issues": [], "records": [{
                    "type": "player_match", "player": "Takefusa Kubo", "club": "Notts County",
                    "overall": 63, "rating": 8.4, "goals": 0, "assists": 1,
                    "passes_completed_short": 999, "clearances": 999,
                }]}

        extract_pending(self.connection, self.root, {76}, extractor=FakePlayerExtractor())
        decisions = {"player_core_ranges": [[76, 76]]}
        review = prepare_player_cores(self.connection, decisions)
        record = review["sources"][0]["records"][0]
        self.assertNotIn("clearances", record)
        self.assertNotIn("passes_completed_short", record)
        self.assertFalse(review["sources"][0]["complete"])
        approve_review(self.connection, review, "Only image-reviewed core fields")
        self.assertIsNone(self.connection.execute("SELECT clearances FROM player_matches").fetchone()[0])
        self.assertEqual(self.connection.execute("SELECT assists FROM player_matches").fetchone()[0], 1)

    def test_fixture_context_rejects_interrupted_player_groups(self):
        source_id, document = self.approved_match()
        self.connection.execute("UPDATE source_images SET screen_type = 'match_facts' WHERE id = ?", (source_id,))
        self.connection.commit()
        interruption = self.prepare_source(74, "gray")
        player_source = self.prepare_source(75, "black")
        self.connection.execute("UPDATE source_images SET screen_type = 'squad' WHERE id = ?", (interruption,))
        self.connection.execute("UPDATE source_images SET screen_type = 'player_performance' WHERE id = ?", (player_source,))
        self.connection.commit()
        with self.assertRaisesRegex(ValueError, "boundary"):
            fixture_contexts(self.connection)

    def test_goalkeeper_shootout_counts_remain_separate(self):
        source_id, document = self.approved_match()
        self.connection.execute("UPDATE matches SET home_penalties = 2, away_penalties = 4")
        self.connection.execute("UPDATE source_images SET screen_type = 'match_facts' WHERE id = ?", (source_id,))
        self.connection.commit()
        self.prepare_source(76, "black")

        class FakeKeeperExtractor:
            def extract(self, path):
                return {"screen_type": "goalkeeper_performance", "evidence": {}, "issues": [], "records": [{
                    "type": "player_match", "player": "Aaron Ramsdale", "club": "Notts County",
                    "rating": 6.8, "overall": 63, "goals_conceded": 5, "assists": None,
                }]}

        extract_pending(self.connection, self.root, {76}, extractor=FakeKeeperExtractor())
        review = prepare_player_cores(self.connection, {"player_core_ranges": [[76, 76]], "goalkeeper_zero_assists": [76]})
        approve_review(self.connection, review, "Verified match score and goalkeeper count")
        result = self.connection.execute("SELECT goals_conceded, goals_conceded_displayed FROM player_matches").fetchone()
        self.assertEqual(tuple(result), (1, 5))

    def test_coverage_reports_differences_without_modifying_records(self):
        self.approved_match()
        self.connection.execute("INSERT INTO players(name) VALUES ('Takefusa Kubo')")
        self.connection.execute("INSERT INTO player_matches(match_id, player_id, club_id, displayed_position, goals, assists, rating, overall, shots_on_target, shots_off_target) VALUES (1, 1, 1, 'CAM', 0, 1, 8.4, 63, 1, 0)")
        self.connection.commit()
        report = coverage_report(self.connection)
        self.assertEqual(report["summary"]["matches"], 1)
        self.assertEqual(report["summary"]["preseason_matches"], 1)
        self.assertEqual(report["summary"]["player_records"], 1)
        self.assertEqual(report["summary"]["matches_with_two_complete_team_rows"], 0)
        self.assertEqual(report["player_field_availability"]["minutes_played"], {"recorded": 0, "null": 1})
        discrepancy = next(warning for warning in report["warnings"] if warning["code"] == "player_goal_difference")
        self.assertEqual(discrepancy["difference"], 1)
        self.assertEqual(self.connection.execute("SELECT home_goals FROM matches").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT goals FROM player_matches").fetchone()[0], 0)

    def test_coverage_does_not_treat_unknown_scores_as_draws(self):
        source_id, document = self.approved_match()
        self.connection.execute("UPDATE matches SET home_goals = NULL, away_goals = NULL")
        self.connection.commit()
        report = coverage_report(self.connection)
        self.assertEqual(report["competitions"][0]["known_results"], 0)
        self.assertEqual(report["competitions"][0]["draws"], 0)
        self.assertIsNone(report["matches"][0]["goal_difference"])
        self.assertIn("missing_match_score", [warning["code"] for warning in report["warnings"]])


if __name__ == "__main__":
    unittest.main()
