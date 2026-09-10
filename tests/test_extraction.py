import os
import unittest
from pathlib import Path

from PIL import Image

from career_data.extraction import ScreenshotExtractor, classify, parse_counts, parse_header, parse_integer


class ParsingTests(unittest.TestCase):
    def test_missing_values_are_not_zero(self):
        self.assertEqual(parse_integer("0"), 0)
        for text in ("", "O", "-", "1 0", "unknown"):
            self.assertIsNone(parse_integer(text))
        self.assertEqual(parse_counts("0/1/0", 3), [0, 1, 0])
        self.assertEqual(parse_counts("0/1", 3), [None, None, None])

    def test_preseason_header_and_season(self):
        header = parse_header("04 July 2018 | San Siro | European Int'l Cup")
        self.assertEqual(header["competition"], "European International Cup")
        self.assertEqual(header["played_on"], "2018-07-04")
        self.assertEqual(header["season"], "2018/19")
        self.assertEqual(header["venue"], "San Siro")
        self.assertEqual(parse_header("14 February 2019 | Ivy Lane | Checkatrade Trophy")["season"], "2018/19")

    def test_bad_dates_are_not_invented(self):
        self.assertIsNone(parse_header("31 February 2019 | Town Park | EFL League Two")["played_on"])
        self.assertEqual(parse_header("260ctober2019/Ivy Lane/EFLLeague One")["played_on"], "2019-10-26")

    def test_dashboard_tile_is_not_transfer_screen(self):
        self.assertEqual(classify("Mr. Kedia TRANSFER HUB STANDINGS"), "dashboard")
        self.assertEqual(classify("CAREER > TRANSFER HUB SENT OFFERS"), "transfer")
        self.assertEqual(classify("PLAYER PERFORMANCE GOALKEEPING"), "goalkeeper_performance")


@unittest.skipUnless(os.environ.get("CAREER_OCR_TESTS") == "1", "Set CAREER_OCR_TESTS=1 for real-image OCR checks")
class ScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extractor = ScreenshotExtractor()
        cls.root = Path(__file__).resolve().parents[1]

    def extract(self, sequence, method, **kwargs):
        with Image.open(self.root / "raw_data" / f"Screenshot ({sequence}).png") as image:
            return method(image.convert("RGB"), **kwargs)[0]

    def test_preseason_score_and_team_stats(self):
        record = self.extract(73, self.extractor.extract_match)
        self.assertEqual((record["home_goals"], record["away_goals"]), (1, 1))
        self.assertEqual(record["competition"], "European International Cup")
        self.assertEqual(record["team_stats"]["home"]["shots"], 6)
        self.assertEqual(record["team_stats"]["away"]["fouls"], 0)

    def test_outfield_zeroes_and_passing(self):
        record = self.extract(76, self.extractor.extract_player)
        self.assertEqual(record["player"], "Takefusa Kubo")
        self.assertEqual(record["goals"], 0)
        self.assertEqual(record["assists"], 1)
        self.assertEqual(record["rating"], 8.4)
        self.assertEqual([record[f"passes_completed_{distance}"] for distance in ("short", "medium", "long")], [13, 3, 0])
        self.assertEqual(record["possession_lost"], 10)

    def test_goalkeeper_layout(self):
        record = self.extract(108, self.extractor.extract_player, goalkeeper=True)
        self.assertEqual(record["player"], "Aaron Ramsdale")
        self.assertEqual(record["goals_conceded"], 0)
        self.assertEqual(record["shots_caught"], 4)
        self.assertEqual(record["shots_parried"], 2)
        self.assertEqual(record["crosses_caught"], 1)
        self.assertNotIn("goals", record)

    def test_squad_overall_snapshots(self):
        first = self.extract(70, self.extractor.extract_snapshot)
        last = self.extract(1055, self.extractor.extract_snapshot)
        self.assertEqual((first["overall"], last["overall"]), (62, 65))
        self.assertEqual(first["player"], last["player"])
        self.assertIsNone(first["observed_on"])

    def test_season_totals_remain_separate_from_match_stats(self):
        with Image.open(self.root / "raw_data/Screenshot (1056).png") as image:
            records, evidence = self.extractor.extract_squad_totals(image.convert("RGB"))
        total = next(record for record in records if record["scope"] == "all_competitions")
        self.assertEqual(total["type"], "player_competition_snapshot")
        self.assertEqual(total["player"], "Erling Braut Haaland")
        self.assertEqual((total["appearances"], total["goals"], total["assists"]), (52, 23, 13))
        self.assertEqual(total["average_rating"], 7.7)
        self.assertIsNone(total["season"])
        self.assertNotIn("match_id", total)
        self.assertIn("season_totals.5.goals", evidence)

    def test_season_table_detection_survives_misread_heading(self):
        extraction = self.extractor.extract(self.root / "raw_data/Screenshot (1071).png")
        records = [record for record in extraction["records"] if record["type"] == "player_competition_snapshot"]
        self.assertEqual(len(records), 6)
        self.assertEqual(records[0]["player"], "Elliott Hewitt")


if __name__ == "__main__":
    unittest.main()
