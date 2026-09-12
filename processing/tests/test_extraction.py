import os
import unittest
from pathlib import Path

from PIL import Image

from processing.extraction import ScreenshotExtractor, classify, parse_calendar_month, parse_counts, parse_header, parse_integer, parse_money, parse_months, parse_news_date, parse_news_event


def ocr_tokens(lines):
    return [{"text": text, "confidence": 0.99,
             "box": [[left / 1366, top / 768], [right / 1366, top / 768],
                     [right / 1366, bottom / 768], [left / 1366, bottom / 768]]}
            for text, left, top, right, bottom in lines]


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
        self.assertEqual(classify("STANDINGS Kubo grabs August Player of the Month Award"), "dashboard_award")
        self.assertEqual(classify("STANDINGS Player of the Month August shortlist"), "dashboard")

    def test_money_uses_minor_units_without_guessing_dollar_currency(self):
        self.assertEqual(parse_money("$33,601"), (3360100, None, "$"))
        self.assertEqual(parse_money("GBP 1.25M"), (125000000, "GBP", "GBP"))
        self.assertEqual(parse_money("\u20ac750K"), (75000000, "EUR", "\u20ac"))
        self.assertEqual(parse_money("USD 0"), (0, "USD", "USD"))
        for text in ("", "$5,9OO", "35,99", "2-Year", "unknown"):
            self.assertIsNone(parse_money(text)[0])

    def test_contract_and_loan_durations(self):
        for text, expected in (("2-Year", 24), ("1 Year(s]", 12), ("3 Year(s)", 36), ("6 Months", 6)):
            self.assertEqual(parse_months(text), expected)
        for text in ("", "0 Years", "Unknown", "$12"):
            self.assertIsNone(parse_months(text))

    def test_monthly_award_uses_award_month_for_year_and_season(self):
        december = parse_news_event("King grabs December Player of the Month Award", announced_on="2019-01-05")
        self.assertEqual((december["period"], december["season"]), ("2018-12", "2018/19"))
        june = parse_news_event("King wins June Player of the Month", announced_on="2019-07-05")
        self.assertEqual((june["period"], june["season"]), ("2019-06", "2018/19"))
        unknown_date = parse_news_event("King grabs August Player of the Month Award")
        self.assertEqual(unknown_date["period"], "August")
        self.assertIsNone(unknown_date["season"])
        self.assertIsNone(unknown_date["competition"])
        self.assertEqual(parse_news_date("05/09/2018"), "2018-09-05")
        self.assertIsNone(parse_news_date("31/02/2019"))
        self.assertIsNone(parse_news_date("NEW!"))

    def test_dashboard_calendar_is_not_an_award_announcement_date(self):
        self.assertEqual(parse_calendar_month("Monday,Feb18,2019"), "2019-02")
        self.assertEqual(parse_calendar_month("APR2019"), "2019-04")
        self.assertIsNone(parse_calendar_month("Feb31,2019"))
        self.assertIsNone(parse_calendar_month("March"))
        award = parse_news_event("Haaland grabs March Player of the Month Award", observed_on="2019-04-01")
        self.assertEqual(award["period"], "2019-03")
        self.assertIsNone(award["announced_on"])

    def test_award_shortlists_predictions_and_unnamed_winners_are_not_records(self):
        for title in ("EFL League Two Player of the Month September shortlist", "King nominated for Player of the Month",
                      "Exeter City Fans Expect Promotion", "Player of the Competition Announced", "Team of the Competition Announced"):
            self.assertIsNone(parse_news_event(title))


class NonMatchExtractionTests(unittest.TestCase):
    def setUp(self):
        self.extractor = ScreenshotExtractor(engine=object())

    def transfer_tokens(self, status="Accepted", completion=None):
        return ocr_tokens([
            ("CONTRACT OFFERS", 688, 202, 803, 219),
            ("Test", 703, 233, 761, 254), ("Player", 702, 256, 862, 286),
            ("Notts County", 735, 289, 808, 308),
            ("$5,900", 698, 358, 744, 376), ("3 Year(s]", 818, 358, 870, 376),
            (completion if completion is not None else "We have agreed terms with Test Player and he just joined the team.", 687, 392, 1011, 409),
            ("$5,900", 756, 523, 802, 547), (status, 869, 529, 918, 546),
            ("Transfer", 966, 530, 1013, 545),
            ("Other Player", 332, 274, 440, 296), ("17/07", 596, 274, 641, 296),
            ("T. Player", 332, 385, 410, 405), ("03/08", 596, 385, 641, 405),
        ])

    def test_contract_wage_is_not_a_transfer_fee(self):
        records, fields, issues = self.extractor.extract_transfer(self.transfer_tokens())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["player"], "Test Player")
        self.assertEqual(records[0]["transfer_type"], "permanent")
        self.assertEqual(records[0]["weekly_wage_minor"], 590000)
        self.assertEqual(records[0]["contract_months"], 36)
        self.assertIsNone(records[0]["fee_minor"])
        self.assertIsNone(records[0]["loan_months"])
        self.assertIsNone(records[0]["effective_on"])
        self.assertNotIn("17/07", records[0]["date_basis"])
        self.assertIn("completion", fields)
        self.assertTrue(issues)

    def test_negotiations_and_rejected_offers_are_not_signings(self):
        for status, completion in (("Rejected", None), ("Pending", None),
                                   ("Accepted", "We have accepted the offer and will negotiate a contract."),
                                   ("Accepted", "He has not joined the team.")):
            with self.subTest(status=status, completion=completion):
                records, fields, issues = self.extractor.extract_transfer(self.transfer_tokens(status, completion))
                self.assertEqual(records, [])
                self.assertTrue(issues)

    def news_tokens(self, headline="King grabs August Player of the Month Award", body=None, matching_date="05/09/2018"):
        return ocr_tokens([
            (headline, 955, 232, 1250, 279),
            (body if body is not None else "King's impressive performance for Notts County earned him the EFL League Two award.", 955, 304, 1238, 344),
            ("Notts County Crowned EFL League One Champions", 105, 210, 353, 239),
            ("05/10/2019", 105, 251, 187, 266),
            (headline, 105, 358, 352, 396),
            (matching_date, 105, 399, 187, 416),
        ])

    def test_news_date_comes_from_matching_headline_not_first_story(self):
        records, fields, issues = self.extractor.extract_news(self.news_tokens())
        award = next(record for record in records if record["event_type"] == "player_of_the_month")
        self.assertEqual(award["announced_on"], "2018-09-05")
        self.assertEqual(award["competition"], "EFL League Two")
        self.assertEqual(award["club"], "Notts County")
        self.assertEqual(sum(record["event_type"] == "player_of_the_month" for record in records), 1)
        self.assertIn("news.2.announced_on", fields)

    def test_unknown_news_date_is_not_replaced_with_neighbor_date(self):
        records, fields, issues = self.extractor.extract_news(self.news_tokens(matching_date="NEW!"))
        award = next(record for record in records if record["event_type"] == "player_of_the_month")
        self.assertIsNone(award["announced_on"])
        self.assertIsNone(award["season"])
        self.assertEqual(award["period"], "August")

    def test_other_article_does_not_supply_golden_boot_competition(self):
        records, fields, issues = self.extractor.extract_news(self.news_tokens("Zoko Wins Golden Boot", body=""))
        award = next(record for record in records if record["event_type"] == "golden_boot")
        self.assertEqual(award["player"], "Zoko")
        self.assertIsNone(award["competition"])
        self.assertIsNone(award["club"])
        self.assertTrue(any("Confirm competition/season" in issue for issue in issues))


@unittest.skipUnless(os.environ.get("CAREER_OCR_TESTS") == "1", "Set CAREER_OCR_TESTS=1 for real-image OCR checks")
class ScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extractor = ScreenshotExtractor()
        cls.root = Path(__file__).resolve().parents[2]

    def extract(self, sequence, method, **kwargs):
        with Image.open(self.root / "raw_screenshots" / f"Screenshot ({sequence}).png") as image:
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
        with Image.open(self.root / "raw_screenshots/Screenshot (1056).png") as image:
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
        extraction = self.extractor.extract(self.root / "raw_screenshots/Screenshot (1071).png")
        records = [record for record in extraction["records"] if record["type"] == "player_competition_snapshot"]
        self.assertEqual(len(records), 6)
        self.assertEqual(records[0]["player"], "Elliott Hewitt")

    def test_completed_loan_preserves_terms_without_inventing_a_date_or_fee(self):
        extraction = self.extractor.extract(self.root / "raw_screenshots/Screenshot (1231).png")
        self.assertEqual([record["type"] for record in extraction["records"]], ["player_transfer"])
        record = extraction["records"][0]
        self.assertEqual(record["player"], "Dominic Calvert-Lewin")
        self.assertEqual(record["transfer_type"], "loan")
        self.assertEqual(record["to_club"], "Notts County")
        self.assertEqual((record["contract_months"], record["loan_months"]), (12, 24))
        self.assertIsNone(record["effective_on"])
        self.assertIsNone(record["fee_minor"])

    def test_completed_permanent_transfers(self):
        for sequence, player, wage, months in ((1124, "Matty James", 3599900, 24),
                                               (1158, "Tosin Adarabioyo", 590000, 36)):
            with self.subTest(sequence=sequence):
                extraction = self.extractor.extract(self.root / "raw_screenshots" / f"Screenshot ({sequence}).png")
                self.assertEqual(len(extraction["records"]), 1)
                record = extraction["records"][0]
                self.assertEqual(record["player"], player)
                self.assertEqual(record["transfer_type"], "permanent")
                self.assertEqual(record["weekly_wage_minor"], wage)
                self.assertEqual(record["contract_months"], months)
                self.assertIsNone(record["fee_minor"])

    def test_player_of_the_month_articles_and_headlines(self):
        for sequence, player, period, announced_on, competition in (
            (328, "King", "2018-08", "2018-09-05", "EFL League Two"),
            (403, "King", "2018-09", "2018-10-05", "EFL League Two"),
            (1354, "Calvert-Lewin", "2019-09", "2019-10-05", None),
        ):
            with self.subTest(sequence=sequence):
                extraction = self.extractor.extract(self.root / "raw_screenshots" / f"Screenshot ({sequence}).png")
                self.assertEqual(len(extraction["records"]), 1)
                record = extraction["records"][0]
                self.assertEqual(record["event_type"], "player_of_the_month")
                self.assertEqual(record["player"], player)
                self.assertEqual(record["period"], period)
                self.assertEqual(record["announced_on"], announced_on)
                self.assertEqual(record["competition"], competition)

    def test_player_and_goalkeeper_competition_awards(self):
        player = self.extractor.extract(self.root / "raw_screenshots/Screenshot (222).png")["records"][0]
        self.assertEqual((player["event_type"], player["player"]), ("player_of_the_competition", "Haaland"))
        self.assertEqual((player["club"], player["competition"]), ("Notts County", "European International Cup"))
        self.assertEqual(player["announced_on"], "2018-07-18")
        records = self.extractor.extract(self.root / "raw_screenshots/Screenshot (1053).png")["records"]
        by_type = {record["event_type"]: record for record in records}
        self.assertEqual(len(records), 3)
        self.assertEqual(by_type["goalkeeper_of_the_competition"]["player"], "Aaron Ramsdale")
        self.assertEqual(by_type["goalkeeper_of_the_competition"]["club"], "Notts County")
        self.assertEqual(by_type["champion"]["competition"], "EFL League Two")
        self.assertEqual(by_type["champion"]["club"], "Notts County")
        self.assertEqual(by_type["golden_boot"]["player"], "Zoko")
        self.assertIsNone(by_type["golden_boot"]["competition"])

    def test_tournament_winner_does_not_invent_a_fixture_or_season(self):
        extraction = self.extractor.extract(self.root / "raw_screenshots/Screenshot (221).png")
        self.assertEqual(len(extraction["records"]), 1)
        record = extraction["records"][0]
        self.assertEqual(record["type"], "competition_event")
        self.assertEqual(record["event_type"], "champion")
        self.assertEqual(record["club"], "Notts County")
        self.assertEqual(record["competition"], "European International Cup")
        self.assertIsNone(record["season"])
        self.assertIsNone(record["announced_on"])

    def test_dashboard_award_banners_do_not_borrow_match_or_training_details(self):
        for sequence, player, period in ((823, "Williams", "2019-01"), (866, "Haaland", "2019-02"),
                                         (959, "Haaland", "2019-03"), (1263, "Kubo", "2019-08")):
            with self.subTest(sequence=sequence):
                extraction = self.extractor.extract(self.root / "raw_screenshots" / f"Screenshot ({sequence}).png")
                self.assertEqual(extraction["screen_type"], "dashboard_award")
                self.assertEqual(len(extraction["records"]), 1)
                record = extraction["records"][0]
                self.assertEqual((record["player"], record["period"]), (player, period))
                self.assertIsNone(record["announced_on"])
                self.assertIsNone(record["competition"])
                self.assertIsNone(record["club"])


if __name__ == "__main__":
    unittest.main()
