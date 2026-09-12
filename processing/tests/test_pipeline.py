import copy
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from processing import EXTRACTOR_VERSION
from processing.database import connect, coverage_report, insert_entity, inventory, status, validate_database
from processing.pipeline import approve_review, backup_database, dashboard_data, ensure_club, ensure_edition, ensure_season, export_data, extract_pending, make_review
from processing.batch_review import fixture_contexts, prepare_player_cores
from processing.identifiers import is_uuid, new_id
from processing.extraction import parse_news_event
from processing.reconciliation import reconcile_totals


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.raw = self.root / "raw_screenshots"
        self.raw.mkdir()
        self.connection = connect(self.root / "career.sqlite")
        self.addCleanup(self.connection.close)

    def create_image(self, name="Screenshot (73).png", color="white"):
        path = self.raw / name
        Image.new("RGB", (40, 20), color).save(path)
        return path

    def create_match(self):
        self.season_id = ensure_season(self.connection, "2018/19")
        self.edition_id = ensure_edition(self.connection, {"competition": "European International Cup", "season": "2018/19"})
        self.home_club_id = ensure_club(self.connection, "Notts County")
        self.away_club_id = ensure_club(self.connection, "Dundee FC")
        self.other_club_id = ensure_club(self.connection, "Other Club")
        self.match_id = insert_entity(self.connection, "matches", {
            "competition_season_id": self.edition_id, "played_on": "2018-07-04",
            "home_club_id": self.home_club_id, "away_club_id": self.away_club_id,
            "home_goals": 1, "away_goals": 1,
        })
        return self.match_id

    def create_player(self, name="Aaron Ramsdale"):
        return insert_entity(self.connection, "players", {"name": name})


class DatabaseTests(DatabaseTestCase):
    def test_uuid_database_reopen_preserves_existing_records(self):
        match_id = self.create_match()
        player_id = self.create_player()
        appearance_id = insert_entity(self.connection, "player_matches", {
            "match_id": match_id, "player_id": player_id, "club_id": self.home_club_id,
            "goals_conceded": 2, "goals_conceded_displayed": 2,
        })
        self.connection.commit()
        self.connection.close()
        self.connection = connect(self.root / "career.sqlite")
        self.addCleanup(self.connection.close)
        self.assertEqual(self.connection.execute("PRAGMA user_version").fetchone()[0], 3)
        self.assertEqual(self.connection.execute("SELECT id FROM player_matches").fetchone()[0], appearance_id)
        self.assertTrue(is_uuid(appearance_id))
        self.assertEqual(tuple(self.connection.execute("SELECT goals_conceded, goals_conceded_displayed FROM player_matches").fetchone()), (2, 2))
        self.assertEqual(validate_database(self.connection), [])

    def test_empty_coverage_has_no_invented_matches(self):
        report = coverage_report(self.connection)
        self.assertEqual(report["summary"]["matches"], 0)
        self.assertEqual(report["summary"]["minimum_player_records_per_match"], 0)
        self.assertEqual(report["warnings"], [])

    def test_dashboard_contains_stats_without_screenshot_references(self):
        self.create_image()
        inventory(self.connection, self.root)
        source_id = self.connection.execute("SELECT id FROM source_images").fetchone()[0]
        match_id = self.create_match()
        player_id = self.create_player()
        insert_entity(self.connection, "player_snapshots", {
            "player_id": player_id, "season_id": self.season_id, "source_id": source_id,
            "snapshot_kind": "first_observed", "date_precision": "season",
            "date_basis": "Screenshot (73).png", "overall": 62,
        })
        dataset = dashboard_data(self.connection)
        self.assertEqual(dataset["matches"][0]["id"], match_id)
        self.assertEqual(dataset["player_snapshots"][0]["overall"], 62)
        for field in ("source_images", "match_sources", "player_match_sources"):
            self.assertNotIn(field, dataset)
        self.assertNotIn("sources", dataset["match_coverage"])
        serialized = json.dumps(dataset)
        self.assertNotIn(source_id, serialized)
        self.assertNotIn("Screenshot (73).png", serialized)
        self.assertNotIn('"source_id"', serialized)

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

    def test_deleted_screenshots_and_reused_names_preserve_saved_matches(self):
        original = self.create_image()
        original_bytes = original.read_bytes()
        self.raw = self.raw.rename(self.root / "raw_screenshots")
        original = self.raw / original.name
        inventory(self.connection, self.root)
        source_id = self.connection.execute("SELECT id FROM source_images").fetchone()[0]
        match_id = self.create_match()
        self.connection.execute("INSERT INTO match_sources VALUES (?, ?)", (match_id, source_id))
        self.connection.execute("UPDATE source_images SET status = 'imported'")
        self.connection.commit()

        original.unlink()
        self.assertEqual(inventory(self.connection, self.root)["new_images"], 0)
        self.assertEqual(status(self.connection)["present_paths"], 0)
        self.assertEqual(status(self.connection)["records"]["matches"], 1)

        Image.new("RGB", (40, 20), "black").save(original)
        self.assertEqual(inventory(self.connection, self.root)["new_images"], 1)
        self.assertEqual(status(self.connection)["source_images"], 2)
        self.assertEqual(self.connection.execute("SELECT source_id FROM match_sources").fetchone()[0], source_id)

        original.unlink()
        (self.raw / "renamed.png").write_bytes(original_bytes)
        self.assertEqual(inventory(self.connection, self.root)["new_images"], 0)
        self.assertEqual(status(self.connection)["source_states"], {"imported": 1, "inventoried": 1})
        self.assertEqual(validate_database(self.connection), [])

    def test_corrupt_image_is_reported(self):
        (self.raw / "broken.png").write_bytes(b"not an image")
        self.assertEqual(inventory(self.connection, self.root)["unreadable"], 1)
        self.assertEqual(status(self.connection)["source_states"], {"error": 1})

    def test_competitions_require_boolean_preseason(self):
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM competitions WHERE is_preseason = 1"
        ).fetchone()[0], 2)
        with self.assertRaises(sqlite3.IntegrityError):
            insert_entity(self.connection, "competitions", {"name": "Invalid", "kind": "cup", "is_preseason": 2})

    def test_matches_cannot_have_missing_competition(self):
        self.create_match()
        for edition in (None, new_id()):
            with self.assertRaises(sqlite3.IntegrityError):
                insert_entity(self.connection, "matches", {
                    "competition_season_id": edition, "played_on": "2018-07-05",
                    "home_club_id": self.home_club_id, "away_club_id": self.away_club_id,
                })

    def test_appearance_must_belong_to_participating_club(self):
        match_id = self.create_match()
        player_id = self.create_player("Takefusa Kubo")
        with self.assertRaises(sqlite3.IntegrityError):
            insert_entity(self.connection, "player_matches", {"match_id": match_id, "player_id": player_id, "club_id": self.other_club_id})
        insert_entity(self.connection, "player_matches", {"match_id": match_id, "player_id": player_id, "club_id": self.home_club_id})
        with self.assertRaises(sqlite3.IntegrityError):
            insert_entity(self.connection, "player_matches", {"match_id": match_id, "player_id": player_id, "club_id": self.home_club_id})
        self.assertEqual(validate_database(self.connection), [])

    def test_snapshot_requires_supported_date_precision(self):
        self.create_image()
        inventory(self.connection, self.root)
        self.create_match()
        player_id = self.create_player()
        source_id = self.connection.execute("SELECT id FROM source_images").fetchone()[0]
        snapshot = {"player_id": player_id, "season_id": self.season_id, "source_id": source_id,
                    "snapshot_kind": "season_start", "date_precision": "day", "date_basis": "Date missing"}
        with self.assertRaises(sqlite3.IntegrityError):
            insert_entity(self.connection, "player_snapshots", snapshot)
        insert_entity(self.connection, "player_snapshots", {
            **snapshot, "snapshot_kind": "first_observed", "date_precision": "season",
            "date_basis": "Opening squad screen, exact day unknown", "overall": 62,
        })
        self.assertEqual(self.connection.execute("SELECT observed_on FROM player_snapshots").fetchone()[0], None)


class ImportTests(DatabaseTestCase):
    def prepare_source(self, sequence, color):
        self.create_image(f"Screenshot ({sequence}).png", color)
        inventory(self.connection, self.root)
        return self.connection.execute("SELECT source_id FROM source_paths WHERE sequence = ?", (sequence,)).fetchone()[0]

    def review(self, source_id, records, complete=True):
        return {"schema_version": 3, "sources": [{"source_id": source_id, "complete": complete, "records": records}]}

    def match_record(self):
        return {"type": "match", "competition": "European International Cup", "season": "2018/19",
                "played_on": "2018-07-04", "home_club": "Notts County", "away_club": "Dundee FC",
                "home_goals": 1, "away_goals": 1, "team_stats": {"home": {"shots": 6}, "away": {"fouls": 0}}}

    def approved_match(self):
        source_id = self.prepare_source(73, "white")
        document = self.review(source_id, [self.match_record()])
        approve_review(self.connection, document, "Verified against the screenshot")
        fixture = self.connection.execute("SELECT * FROM matches").fetchone()
        self.match_id = fixture["id"]
        self.home_club_id = fixture["home_club_id"]
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

    def test_club_alias_resolves_to_same_uuid_without_duplicate_club(self):
        self.approved_match()
        self.connection.execute("INSERT INTO club_aliases(alias, club_id) VALUES (?, ?)", ("nottscounty", self.home_club_id))
        self.assertEqual(ensure_club(self.connection, "NottsCounty"), self.home_club_id)
        self.assertEqual(ensure_club(self.connection, "NOTTS COUNTY"), self.home_club_id)
        self.assertTrue(is_uuid(self.home_club_id))
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM clubs").fetchone()[0], 2)

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

    def test_new_non_match_layouts_refresh_once_without_touching_reviewed_stats(self):
        match_source, document = self.approved_match()
        transfer_source = self.prepare_source(1124, "black")
        transfer = {"type": "player_transfer", "player": "Test Player", "to_club": "Notts County",
                    "transfer_type": "permanent", "date_basis": "Year unknown", "contract_months": 24}
        approve_review(self.connection, self.review(transfer_source, [transfer]), "Reviewed signing")
        for source_id, screen_type in ((match_source, "match_facts"), (transfer_source, "transfer")):
            self.connection.execute("UPDATE source_images SET screen_type = ? WHERE id = ?", (screen_type, source_id))
            self.connection.execute(
                "INSERT INTO extractions(source_id, extractor_version, candidate_json, evidence_json, issues_json) VALUES (?, '1.1.0', '[]', '{}', '[]')",
                (source_id,),
            )
        self.connection.commit()
        before = tuple(self.connection.execute("SELECT * FROM player_transfers").fetchone())
        reviewed = [tuple(row) for row in self.connection.execute("SELECT * FROM reviews ORDER BY id")]
        extractor = Mock()
        extractor.extract.return_value = {"screen_type": "transfer", "records": [{**transfer, "contract_months": 99}], "evidence": {}, "issues": []}
        result = extract_pending(self.connection, self.root, extractor=extractor)
        self.assertEqual((result["extracted"], result["skipped"]), (1, 1))
        self.assertEqual(result["processed_source_ids"], [transfer_source])
        self.assertEqual(tuple(self.connection.execute("SELECT * FROM player_transfers").fetchone()), before)
        self.assertEqual([tuple(row) for row in self.connection.execute("SELECT * FROM reviews ORDER BY id")], reviewed)
        self.assertEqual(self.connection.execute("SELECT extractor_version FROM extractions WHERE source_id = ?", (transfer_source,)).fetchone()[0], EXTRACTOR_VERSION)
        self.assertEqual(self.connection.execute("SELECT extractor_version FROM extractions WHERE source_id = ?", (match_source,)).fetchone()[0], "1.1.0")
        second = extract_pending(self.connection, self.root, extractor=extractor)
        self.assertEqual((second["extracted"], second["skipped"]), (0, 2))
        self.assertEqual(extractor.extract.call_count, 1)
        self.assertEqual(make_review(self.connection, {1124})["sources"][0]["records"][0]["contract_months"], 24)

    def test_failed_layout_refresh_retries_without_marking_it_current(self):
        source_id = self.prepare_source(328, "white")
        self.connection.execute("UPDATE source_images SET screen_type = 'news' WHERE id = ?", (source_id,))
        self.connection.execute(
            "INSERT INTO extractions(source_id, extractor_version, candidate_json, evidence_json, issues_json) VALUES (?, '1.1.0', '[]', '{}', '[]')",
            (source_id,),
        )
        self.connection.commit()
        extractor = Mock()
        extractor.extract.side_effect = [ValueError("OCR interrupted"), {"screen_type": "news", "records": [], "evidence": {}, "issues": []}]
        self.assertEqual(extract_pending(self.connection, self.root, extractor=extractor)["errors"], 1)
        self.assertEqual(self.connection.execute("SELECT extractor_version FROM extractions").fetchone()[0], "1.1.0")
        self.assertEqual(extract_pending(self.connection, self.root, extractor=extractor)["extracted"], 1)

    def test_only_dashboard_award_tiles_are_refreshed(self):
        award_source = self.prepare_source(823, "white")
        ordinary_source = self.prepare_source(824, "black")
        for source_id, text in ((award_source, "STANDINGS Williams grabs January Player of the Month Award"),
                                (ordinary_source, "Mr. Kedia STANDINGS TRANSFER HUB")):
            self.connection.execute("UPDATE source_images SET screen_type = 'dashboard' WHERE id = ?", (source_id,))
            evidence = json.dumps({"full_image_tokens": [{"text": text}]})
            self.connection.execute(
                "INSERT INTO extractions(source_id, extractor_version, candidate_json, evidence_json, issues_json) VALUES (?, '1.1.0', '[]', ?, '[]')",
                (source_id, evidence),
            )
        self.connection.commit()
        extractor = Mock()
        extractor.extract.return_value = {"screen_type": "dashboard_award", "records": [], "evidence": {}, "issues": []}
        result = extract_pending(self.connection, self.root, extractor=extractor)
        self.assertEqual(result["processed_source_ids"], [award_source])
        self.assertEqual((result["extracted"], result["skipped"]), (1, 1))

    def test_news_ocr_reuses_existing_player_and_imports_monthly_award_once(self):
        source_id = self.prepare_source(328, "white")
        player_id = self.create_player("Andy King")
        self.connection.commit()
        candidate = parse_news_event("King grabs August Player of the Month Award",
                                     "King's impressive performance for Notts County earned him the EFL League Two award.", "2018-09-05")
        extractor = Mock()
        extractor.extract.return_value = {"screen_type": "news", "records": [candidate], "evidence": {}, "issues": []}
        extract_pending(self.connection, self.root, extractor=extractor)
        review = make_review(self.connection, {328})
        record = review["sources"][0]["records"][0]
        self.assertEqual((record["player"], record["player_id"]), ("Andy King", player_id))
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM competition_events").fetchone()[0], 0)
        approve_review(self.connection, review, "Checked monthly award")
        approve_review(self.connection, review, "Repeat")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM players").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT player_id, period FROM competition_events").fetchone()[:], (player_id, "2018-08"))
        self.assertEqual(len(dashboard_data(self.connection)["competition_events"]), 1)

    def test_news_ocr_does_not_choose_between_players_with_same_surname(self):
        self.prepare_source(328, "white")
        self.create_player("Andy King")
        self.create_player("Joshua King")
        self.connection.commit()
        candidate = parse_news_event("King grabs August Player of the Month Award", announced_on="2018-09-05")
        extractor = Mock()
        extractor.extract.return_value = {"screen_type": "news", "records": [candidate], "evidence": {}, "issues": []}
        extract_pending(self.connection, self.root, extractor=extractor)
        source = make_review(self.connection, {328})["sources"][0]
        self.assertNotIn("player_id", source["records"][0])
        self.assertEqual(source["records"][0]["player"], "King")
        self.assertTrue(any("Ambiguous OCR player" in issue for issue in source["issues"]))
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM players").fetchone()[0], 2)

    def test_refreshed_news_adds_new_awards_without_replacing_reviewed_values(self):
        source_id = self.prepare_source(1053, "white")
        reviewed = {"type": "competition_event", "event_type": "goalkeeper_of_the_competition",
                    "player": "Aaron Ramsdale", "club": "Notts County", "competition": "EFL League Two",
                    "season": "2018/19", "period": "2018/19", "announced_on": "2019-05-04", "description": "Reviewed award"}
        approve_review(self.connection, self.review(source_id, [reviewed]), "Existing checked award")
        before = tuple(self.connection.execute("SELECT * FROM competition_events").fetchone())
        news = {**reviewed, "description": "Fresh OCR wording"}
        champion = {"type": "competition_event", "event_type": "champion", "club": "Notts County",
                    "competition": "EFL League Two", "season": "2018/19", "period": "2018/19",
                    "announced_on": "2019-05-04", "description": "Notts County Crowned EFL League Two Champions"}
        extractor = Mock()
        extractor.extract.return_value = {"screen_type": "news", "records": [news, champion], "evidence": {}, "issues": []}
        extract_pending(self.connection, self.root, extractor=extractor)
        source = make_review(self.connection, {1053})["sources"][0]
        self.assertEqual(len(source["records"]), 2)
        self.assertEqual(source["records"][0]["description"], "Reviewed award")
        self.assertEqual(source["records"][1]["event_type"], "champion")
        self.assertFalse(source["complete"])
        self.assertEqual(tuple(self.connection.execute("SELECT * FROM competition_events").fetchone()), before)

    def test_new_transfer_ocr_proposes_unknown_wage_without_changing_saved_contract(self):
        source_id = self.prepare_source(1124, "white")
        transfer = {"type": "player_transfer", "player": "Matty James", "to_club": "Notts County",
                    "transfer_type": "permanent", "date_basis": "Year unknown", "contract_months": 24, "weekly_wage_minor": None}
        approve_review(self.connection, self.review(source_id, [transfer]), "Reviewed signing")
        extractor = Mock()
        extractor.extract.return_value = {"screen_type": "transfer", "records": [{**transfer, "weekly_wage_minor": 3599900, "contract_months": 99}], "evidence": {}, "issues": []}
        extract_pending(self.connection, self.root, extractor=extractor)
        source = make_review(self.connection, {1124})["sources"][0]
        self.assertEqual(len(source["records"]), 1)
        self.assertEqual(source["records"][0]["weekly_wage_minor"], 3599900)
        self.assertEqual(source["records"][0]["contract_months"], 24)
        self.assertFalse(source["complete"])
        self.assertIsNone(self.connection.execute("SELECT weekly_wage_minor FROM player_transfers").fetchone()[0])

    def test_export_and_backup_preserve_canonical_data(self):
        self.approved_match()
        output = self.root / "exports" / "career.json"
        export_data(self.connection, output)
        exported = json.loads(output.read_text())
        self.assertEqual(len(exported["matches"]), 1)
        self.assertIs(next(competition for competition in exported["competitions"] if competition["name"] == "European International Cup")["is_preseason"], True)
        backup = self.root / "backup.sqlite"
        backup_database(self.connection, backup)
        with closing(sqlite3.connect(backup)) as restored:
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
        self.assertEqual(source["path"], "raw_screenshots/Screenshot (74).png")
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

    def test_player_review_restores_detailed_candidates_without_overwriting_core_corrections(self):
        match_source, document = self.approved_match()
        player_source = self.prepare_source(76, "black")
        extractor = Mock()
        extractor.extract.return_value = {
            "screen_type": "player_performance", "evidence": {}, "issues": [], "records": [{
                "type": "player_match", "player": "Kubo OCR", "club": "Wrong OCR club", "match_id": None,
                "goals": 9, "assists": 8, "key_passes": 3, "interceptions": 4, "passes_completed_short": 15,
            }],
        }
        extract_pending(self.connection, self.root, {76}, extractor=extractor)
        reviewed = {"type": "player_match", "player": "Takefusa Kubo", "club": "Notts County",
                    "match_id": self.match_id, "goals": 0, "assists": 1, "key_passes": 2, "interceptions": None}
        approve_review(self.connection, self.review(player_source, [reviewed]), "Corrected core fields")

        source = make_review(self.connection, {76})["sources"][0]
        record = source["records"][0]

        self.assertEqual(record["player"], "Takefusa Kubo")
        self.assertEqual(record["club"], "Notts County")
        self.assertEqual(record["match_id"], self.match_id)
        self.assertEqual((record["goals"], record["assists"], record["key_passes"]), (0, 1, 2))
        self.assertEqual(record["interceptions"], 4)
        self.assertEqual(record["passes_completed_short"], 15)
        self.assertFalse(source["complete"])
        self.assertTrue(any("Unreviewed player fields" in issue for issue in source["issues"]))
        self.assertIsNone(self.connection.execute("SELECT interceptions FROM player_matches").fetchone()[0])
        approve_review(self.connection, {"schema_version": 3, "sources": [source]}, "Detailed fields checked")
        saved = self.connection.execute("SELECT goals, assists, key_passes, interceptions, passes_completed_short FROM player_matches").fetchone()
        self.assertEqual(tuple(saved), (0, 1, 2, 4, 15))

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
        player_id = self.create_player("Takefusa Kubo")
        insert_entity(self.connection, "player_matches", {
            "match_id": self.match_id, "player_id": player_id, "club_id": self.home_club_id,
            "displayed_position": "CAM", "goals": 0, "assists": 1, "rating": 8.4, "overall": 63,
            "shots_on_target": 1, "shots_off_target": 0,
        })
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


class CommandTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.record = {
            "type": "match", "season": "2018/19", "competition": "European International Cup",
            "played_on": "2018-07-04", "home_club": "Notts County", "away_club": "Dundee FC",
            "home_goals": 1, "away_goals": 1,
        }
        self.extractor = Mock()
        self.extractor.extract.return_value = {
            "screen_type": "match_facts", "records": [self.record], "evidence": {}, "issues": [],
        }
        replacement = patch("processing.extraction.ScreenshotExtractor", return_value=self.extractor)
        replacement.start()
        self.addCleanup(replacement.stop)

    def command(self, *arguments):
        from processing.__main__ import main

        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--root", str(self.root), "--db", str(self.root / "career.sqlite"), *map(str, arguments)])
        self.assertEqual(result, 0)
        text = output.getvalue()
        return json.loads(text[text.index("{"):])

    def launcher(self, *arguments):
        repository = Path(__file__).resolve().parents[2]
        bin_dir = self.root / "fake commands"
        bin_dir.mkdir(exist_ok=True)
        for name in ("npm", "python3"):
            executable = bin_dir / name
            executable.write_text('#!/bin/sh\nprintf "%s\\n" "$PWD" "$@"\n', encoding="utf-8")
            executable.chmod(0o755)
        environment = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        return subprocess.run(
            [str(repository / "run"), *arguments], cwd=self.root, env=environment,
            capture_output=True, text=True, timeout=5,
        )

    def test_launcher_start_uses_port_5000_from_any_directory(self):
        repository = Path(__file__).resolve().parents[2]
        result = self.launcher("start", "--clearScreen", "false")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            str(repository), "--prefix", str(repository / "frontend"), "run", "dev", "--",
            "--port", "5000", "--strictPort", "--clearScreen", "false",
        ])

    def test_launcher_process_forwards_arguments_from_repository_root(self):
        repository = Path(__file__).resolve().parents[2]
        for arguments in (("--limit", "2", "--screenshots", "73,74"), ("--clean",)):
            with self.subTest(arguments=arguments):
                result = self.launcher("process", *arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), [
                    str(repository), "-m", "processing", "process", *arguments,
                ])

    def test_launcher_only_exposes_start_and_process(self):
        for arguments in ((), ("-h",), ("--help",), ("help",)):
            with self.subTest(arguments=arguments):
                result = self.launcher(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                commands = [line.split()[0] for line in result.stdout.splitlines() if line.startswith("  ")]
                self.assertEqual(commands, ["start", "process"])
        for command in ("dev", "build", "preview", "approve", "review", "status", "backup", "test",
                        "e2e", "lint", "check", "format", "inventory", "validate", "report", "reconcile", "export"):
            with self.subTest(command=command):
                result = self.launcher(command)
                self.assertEqual(result.returncode, 2)
                self.assertIn(f"Unknown command: {command}", result.stderr)

    def test_process_approve_and_dashboard_use_one_sqlite_database(self):
        self.create_image()
        processed = self.command("process")
        self.assertEqual(processed["extraction"]["extracted"], 1)
        self.assertIn("python3 -m processing approve", processed["next"])
        self.assertNotIn("./run approve", processed["next"])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 0)
        review_path = Path(processed["review_file"])
        self.assertTrue(review_path.is_file())
        self.command("approve", review_path, "--note", "Visually checked")
        self.assertEqual(len(self.command("data")["matches"]), 1)
        repeat = self.command("process")
        self.assertEqual(repeat["extraction"]["extracted"], 0)
        self.assertNotIn("review_file", repeat)
        self.extractor.extract.assert_called_once()
        self.assertNotIn("source_images", self.command("data"))

    def test_process_clean_backs_up_reviewed_data_and_reprocesses_known_images(self):
        image = self.create_image()
        original_bytes = image.read_bytes()
        first = self.command("process")
        self.command("approve", first["review_file"], "--note", "Checked before clean")
        source_id = self.connection.execute("SELECT id FROM source_images").fetchone()[0]
        match_id = self.connection.execute("SELECT id FROM matches").fetchone()[0]
        self.connection.close()

        cleaned = self.command("process", "--clean")

        self.assertTrue(cleaned["clean"])
        self.assertEqual(cleaned["inventory"]["new_images"], 1)
        self.assertEqual(cleaned["extraction"]["extracted"], 1)
        self.assertEqual(cleaned["extraction"]["skipped"], 0)
        self.assertEqual(self.command("data")["matches"], [])
        self.assertEqual(image.read_bytes(), original_bytes)
        self.assertTrue(Path(first["review_file"]).is_file())
        with closing(sqlite3.connect(cleaned["backup"])) as backup:
            self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(backup.execute("SELECT id FROM matches").fetchone()[0], match_id)
            self.assertEqual(backup.execute("SELECT id FROM source_images").fetchone()[0], source_id)
            self.assertEqual(backup.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 1)
        with closing(connect(cleaned["database"])) as rebuilt:
            self.assertNotEqual(rebuilt.execute("SELECT id FROM source_images").fetchone()[0], source_id)
            self.assertEqual(rebuilt.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
            self.assertEqual(validate_database(rebuilt), [])
        self.assertEqual(self.command("process")["extraction"]["extracted"], 0)
        self.assertEqual(self.extractor.extract.call_count, 2)

    def test_clean_creates_missing_default_database_without_touching_other_sqlite(self):
        from processing.__main__ import main

        self.create_match()
        self.connection.commit()
        self.create_image()
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--root", str(self.root), "process", "--clean"]), 0)
        text = output.getvalue()
        result = json.loads(text[text.index("{"):])
        self.assertEqual(result["database"], str((self.root / "processing" / "data" / "career.sqlite").resolve()))
        self.assertTrue(result["clean"])
        self.assertNotIn("backup", result)
        self.assertEqual(result["extraction"]["extracted"], 1)
        with closing(connect(result["database"])) as rebuilt:
            self.assertEqual(rebuilt.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 1)

    def test_clean_with_empty_screenshot_folder_resets_stats_and_preserves_backup(self):
        self.create_match()
        self.connection.commit()

        result = self.command("process", "--clean")

        self.assertEqual(result["inventory"]["files"], 0)
        self.assertEqual(result["extraction"]["extracted"], 0)
        self.assertNotIn("review_file", result)
        self.assertIn("reset database contains no reviewed stats", result["message"])
        self.assertEqual(self.command("data")["matches"], [])
        with closing(sqlite3.connect(result["backup"])) as backup:
            self.assertEqual(backup.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 1)
        self.extractor.extract.assert_not_called()

    def test_clean_backup_failure_does_not_reset_existing_database(self):
        match_id = self.create_match()
        self.connection.commit()

        with patch("processing.__main__.backup_database", side_effect=OSError("Backup unavailable")):
            with self.assertRaisesRegex(OSError, "Backup unavailable"):
                self.command("process", "--clean")

        self.assertEqual(self.connection.execute("SELECT id FROM matches").fetchone()[0], match_id)
        self.extractor.extract.assert_not_called()

    def test_clean_rejects_partial_scans_before_resetting_database(self):
        match_id = self.create_match()
        self.connection.commit()

        for arguments in (("--limit", "1"), ("--limit", "0"), ("--screenshots", "73")):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ValueError, "--clean cannot be combined"):
                    self.command("process", "--clean", *arguments)
                self.assertEqual(self.connection.execute("SELECT id FROM matches").fetchone()[0], match_id)
        self.assertFalse((self.root / "backups").exists())
        self.extractor.extract.assert_not_called()

    def test_clean_preserves_committed_wal_records_in_backup(self):
        self.assertEqual(self.connection.execute("PRAGMA journal_mode = WAL").fetchone()[0], "wal")
        match_id = self.create_match()
        self.connection.commit()
        self.assertGreater((self.root / "career.sqlite-wal").stat().st_size, 0)

        result = self.command("process", "--clean")

        with closing(sqlite3.connect(result["backup"])) as backup:
            self.assertEqual(backup.execute("SELECT id FROM matches").fetchone()[0], match_id)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 0)
        self.assertEqual(self.command("data")["matches"], [])

    def test_delete_and_replace_screenshot_never_loses_saved_stats(self):
        original = self.create_image()
        original_bytes = original.read_bytes()
        first = self.command("process")
        self.command("approve", first["review_file"], "--note", "First match checked")
        original.unlink()
        self.assertEqual(self.command("process")["extraction"]["extracted"], 0)
        self.assertEqual(len(self.command("data")["matches"]), 1)

        self.record["played_on"] = "2018-07-05"
        self.create_image(color="black")
        second = self.command("process")
        self.assertEqual(second["inventory"]["new_images"], 1)
        self.command("approve", second["review_file"], "--note", "Second match checked")
        self.assertEqual(len(self.command("data")["matches"]), 2)
        (self.raw / "old-image-renamed.png").write_bytes(original_bytes)
        self.assertEqual(self.command("process")["extraction"]["extracted"], 0)
        self.assertEqual(self.extractor.extract.call_count, 2)

    def test_process_has_no_silent_twenty_image_limit_or_image_copies(self):
        for sequence in range(21):
            self.create_image(f"Screenshot ({sequence}).png", color=(sequence * 10, 0, 0))
        result = self.command("process")
        self.assertEqual(result["extraction"]["extracted"], 21)
        self.assertEqual(result["extraction"]["remaining"], 0)
        self.assertEqual(len(list(self.root.rglob("*.png"))), 21)

    def test_dashboard_read_does_not_create_a_missing_database(self):
        from processing.__main__ import main

        missing = self.root / "missing.sqlite"
        with self.assertRaisesRegex(ValueError, "No local stats database"):
            main(["--db", str(missing), "data"])
        self.assertFalse(missing.exists())


class ReconciliationTests(DatabaseTestCase):
    def prepare_stats(self, *, missing_goals=False, observed_on=None, snapshot_kind="season_end"):
        self.create_image()
        inventory(self.connection, self.root)
        self.create_match()
        self.player_id = self.create_player("Takefusa Kubo")
        source_id = self.connection.execute("SELECT id FROM source_images").fetchone()[0]
        insert_entity(self.connection, "player_matches", {
            "match_id": self.match_id, "player_id": self.player_id, "club_id": self.home_club_id,
            "goals": None if missing_goals else 1, "assists": 1, "rating": 8.4, "displayed_position": "CAM",
        })
        snapshot = {"player_id": self.player_id, "club_id": self.home_club_id, "season_id": self.season_id,
                    "source_id": source_id, "scope": "all_competitions", "snapshot_kind": snapshot_kind,
                    "observed_on": observed_on, "appearances": 1, "goals": 1, "assists": 1, "average_rating": 8.4}
        self.snapshot_id = insert_entity(self.connection, "player_competition_snapshots", snapshot)
        self.connection.commit()

    def test_reconciliation_counts_each_match_once_and_excludes_other_seasons(self):
        self.prepare_stats()
        next_edition = ensure_edition(self.connection, {"competition": "Invitational Cup", "season": "2019/20"})
        next_match = insert_entity(self.connection, "matches", {
            "competition_season_id": next_edition, "played_on": "2019-07-07",
            "home_club_id": self.home_club_id, "away_club_id": self.away_club_id,
        })
        insert_entity(self.connection, "player_matches", {"match_id": next_match, "player_id": self.player_id,
                      "club_id": self.home_club_id, "goals": 5, "assists": 5, "rating": 10})
        report = reconcile_totals(self.connection, "2018/19")
        result = report["comparisons"][0]
        self.assertEqual(result["result"], "match")
        self.assertEqual(result["metrics"]["goals"]["derived"], 1)
        self.assertEqual(result["metrics"]["appearances"]["derived"], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM player_matches").fetchone()[0], 2)

    def test_unconfirmed_cutoff_is_not_compared(self):
        self.prepare_stats(snapshot_kind="in_season")
        report = reconcile_totals(self.connection)
        self.assertEqual(report["summary"]["unconfirmed_cutoffs"], 1)
        self.assertEqual(report["comparisons"][0]["metrics"], {})

    def test_missing_match_goals_are_not_zero(self):
        self.prepare_stats(missing_goals=True)
        metric = reconcile_totals(self.connection)["comparisons"][0]["metrics"]["goals"]
        self.assertEqual(metric["result"], "not_comparable")
        self.assertIsNone(metric["derived"])
        self.assertEqual(metric["missing_match_values"], 1)

    def test_missing_goalkeeper_goals_default_to_zero_without_changing_sqlite(self):
        self.prepare_stats(missing_goals=True)
        self.connection.execute("UPDATE player_matches SET displayed_position = 'GK'")
        self.connection.execute("UPDATE player_competition_snapshots SET goals = 0")

        report = reconcile_totals(self.connection)
        comparison = report["comparisons"][0]
        goals = comparison["metrics"]["goals"]

        self.assertEqual(comparison["result"], "match")
        self.assertEqual(report["summary"]["partial_comparisons"], 0)
        self.assertEqual(goals["derived"], 0)
        self.assertEqual(goals["missing_match_values"], 0)
        self.assertEqual(goals["assumed_zero_match_values"], 1)
        self.assertIsNone(self.connection.execute("SELECT goals FROM player_matches").fetchone()[0])

    def test_dashboard_uses_the_same_goalkeeper_default_and_keeps_its_provenance(self):
        self.prepare_stats(missing_goals=True)
        self.connection.execute("UPDATE player_competition_snapshots SET goals = 0")
        for position, recorded, expected, assumed in (
            ("GK", None, 0, True),
            ("GK", 2, 2, False),
            ("CAM", None, None, False),
            (None, None, None, False),
        ):
            with self.subTest(position=position, recorded=recorded):
                self.connection.execute("UPDATE player_matches SET displayed_position = ?, goals = ?", (position, recorded))
                data = dashboard_data(self.connection)
                performance = data["player_matches"][0]
                self.assertEqual(performance["goals"], expected)
                self.assertIs(performance["goals_assumed_zero"], assumed)
                self.assertEqual(data["season_reconciliation"]["comparisons"][0]["metrics"]["goals"]["derived"], expected)
                self.assertEqual(self.connection.execute("SELECT goals FROM player_matches").fetchone()[0], recorded)

    def test_recorded_goalkeeper_goals_are_never_replaced(self):
        self.prepare_stats()
        self.connection.execute("UPDATE player_matches SET displayed_position = 'GK'")
        goals = reconcile_totals(self.connection)["comparisons"][0]["metrics"]["goals"]
        self.assertEqual(goals["result"], "match")
        self.assertEqual(goals["derived"], 1)
        self.assertEqual(goals["assumed_zero_match_values"], 0)

    def test_goalkeeper_rule_does_not_default_other_metrics_or_outfield_appearances(self):
        self.prepare_stats(missing_goals=True)
        self.connection.execute("UPDATE player_matches SET displayed_position = 'GK', played_position = 'ST'")
        goals = reconcile_totals(self.connection)["comparisons"][0]["metrics"]["goals"]
        self.assertIsNone(goals["derived"])
        self.assertEqual(goals["assumed_zero_match_values"], 0)

        self.connection.execute("UPDATE player_matches SET played_position = 'GK', assists = NULL")
        self.connection.execute("UPDATE player_competition_snapshots SET goals = 0")
        comparison = reconcile_totals(self.connection)["comparisons"][0]
        self.assertEqual(comparison["result"], "partial_comparison")
        self.assertEqual(comparison["metrics"]["goals"]["derived"], 0)
        self.assertIsNone(comparison["metrics"]["assists"]["derived"])

    def test_goal_discrepancy_does_not_rewrite_either_source(self):
        self.prepare_stats()
        self.connection.execute("UPDATE player_competition_snapshots SET goals = 3")
        metric = reconcile_totals(self.connection)["comparisons"][0]["metrics"]["goals"]
        self.assertEqual(metric["result"], "mismatch")
        self.assertEqual(metric["difference"], -2)
        self.assertEqual(self.connection.execute("SELECT goals FROM player_matches").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT goals FROM player_competition_snapshots").fetchone()[0], 3)

    def test_display_average_is_truncated_without_losing_raw_mean(self):
        self.prepare_stats()
        self.connection.execute("UPDATE player_competition_snapshots SET appearances = 2, goals = 2, assists = 2, average_rating = 8.5")
        second_match = insert_entity(self.connection, "matches", {
            "competition_season_id": self.edition_id, "played_on": "2018-07-08",
            "home_club_id": self.home_club_id, "away_club_id": self.away_club_id,
        })
        insert_entity(self.connection, "player_matches", {"match_id": second_match, "player_id": self.player_id,
                      "club_id": self.home_club_id, "goals": 1, "assists": 1, "rating": 8.7})
        metric = reconcile_totals(self.connection)["comparisons"][0]["metrics"]["average_rating"]
        self.assertEqual(metric["result"], "match")
        self.assertEqual(metric["raw_match_average"], 8.55)
        self.assertEqual(metric["derived"], 8.5)

    def test_dated_snapshot_excludes_later_matches(self):
        self.prepare_stats(observed_on="2018-07-04", snapshot_kind="in_season")
        later_match = insert_entity(self.connection, "matches", {
            "competition_season_id": self.edition_id, "played_on": "2018-07-08",
            "home_club_id": self.home_club_id, "away_club_id": self.away_club_id,
        })
        insert_entity(self.connection, "player_matches", {"match_id": later_match, "player_id": self.player_id,
                      "club_id": self.home_club_id, "goals": 5, "assists": 2, "rating": 10})
        comparison = reconcile_totals(self.connection)["comparisons"][0]
        self.assertEqual(comparison["result"], "match")
        self.assertEqual(comparison["metrics"]["appearances"]["derived"], 1)

    def test_competition_scope_excludes_preseason_but_season_total_includes_it(self):
        self.prepare_stats()
        league_edition = ensure_edition(self.connection, {"competition": "EFL League Two", "season": "2018/19"})
        league_match = insert_entity(self.connection, "matches", {
            "competition_season_id": league_edition, "played_on": "2018-08-04",
            "home_club_id": self.home_club_id, "away_club_id": self.away_club_id,
        })
        insert_entity(self.connection, "player_matches", {"match_id": league_match, "player_id": self.player_id,
                      "club_id": self.home_club_id, "goals": 3, "assists": 0, "rating": 7.9})
        self.connection.execute("UPDATE player_competition_snapshots SET appearances = 2, goals = 4, assists = 1, average_rating = 8.1")
        source_id = self.connection.execute("SELECT id FROM source_images").fetchone()[0]
        insert_entity(self.connection, "player_competition_snapshots", {
            "player_id": self.player_id, "club_id": self.home_club_id, "season_id": self.season_id,
            "source_id": source_id, "scope": "competition", "competition_season_id": league_edition,
            "snapshot_kind": "season_end", "appearances": 1, "goals": 3, "assists": 0, "average_rating": 7.9,
        })
        report = reconcile_totals(self.connection)
        totals = {comparison["scope"]: comparison for comparison in report["comparisons"]}
        self.assertEqual(totals["competition"]["result"], "match")
        self.assertEqual(totals["all_competitions"]["result"], "match")
        self.assertEqual(totals["competition"]["metrics"]["goals"]["derived"], 3)
        self.assertEqual(totals["all_competitions"]["metrics"]["goals"]["derived"], 4)


if __name__ == "__main__":
    unittest.main()
