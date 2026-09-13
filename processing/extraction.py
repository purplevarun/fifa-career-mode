import re
from datetime import date
from decimal import Decimal

import numpy as np
from PIL import Image, ImageOps

from . import EXTRACTOR_VERSION


BASE_WIDTH = 1366
BASE_HEIGHT = 768
COMPETITION_LABELS = {
    "europeanintlcup": "European International Cup",
    "europeaninternationalcup": "European International Cup",
    "invitationalcup": "Invitational Cup",
    "eflleaguetwo": "EFL League Two",
    "eflleagueone": "EFL League One",
    "carabaocup": "Carabao Cup",
    "checkatradetrophy": "Checkatrade Trophy",
    "theemiratesfacup": "FA Cup",
}
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
TEAM_ROWS = {
    "shots": 330,
    "shots_on_target": 366,
    "possession_pct": 401,
    "tackles": 437,
    "fouls": 472,
    "corners": 508,
    "shot_accuracy_pct": 543,
    "pass_accuracy_pct": 579,
}
OUTFIELD_ROWS = {
    "goals": ("left", 358),
    "shots_on_target/shots_off_target": ("left", 384),
    "assists": ("left", 435),
    "passes_completed_short/passes_completed_medium/passes_completed_long": (
        "left",
        460,
    ),
    "passes_failed_short/passes_failed_medium/passes_failed_long": ("left", 486),
    "key_passes": ("left", 512),
    "crosses_successful/crosses_failed": ("left", 537),
    "key_dribbles": ("left", 588),
    "fouled": ("left", 614),
    "successful_dribbles": ("left", 640),
    "tackles_won/tackles_lost": ("right", 358),
    "fouls": ("right", 384),
    "penalties_conceded": ("right", 409),
    "interceptions/blocks": ("right", 460),
    "out_of_position": ("right", 486),
    "possession_won/possession_lost": ("right", 537),
    "clearances": ("right", 563),
    "headers_won/headers_lost": ("right", 588),
    "shot_accuracy_pct": ("left", 333),
    "pass_accuracy_pct": ("left", 409),
    "tackle_accuracy_pct": ("right", 333),
}
GOALKEEPER_ROWS = {
    "goals_conceded": ("left", 333),
    "shots_caught/shots_parried": ("left", 358),
    "crosses_caught": ("left", 384),
    "balls_stripped": ("left", 409),
    "assists": ("right", 324),
    "passes_completed_short/passes_completed_medium/passes_completed_long": (
        "right",
        350,
    ),
    "passes_failed_short/passes_failed_medium/passes_failed_long": ("right", 375),
    "key_passes": ("right", 401),
    "crosses_successful/crosses_failed": ("right", 427),
    "interceptions/blocks": ("right", 478),
    "out_of_position": ("right", 503),
    "possession_won/possession_lost": ("right", 555),
    "clearances": ("right", 580),
    "headers_won/headers_lost": ("right", 606),
    "pass_accuracy_pct": ("right", 299),
}


def compact(text):
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def classify(text):
    normalized = compact(text)
    if "playerperformance" in normalized:
        return (
            "goalkeeper_performance"
            if "goalkeeping" in normalized
            else "player_performance"
        )
    if "matchfacts" in normalized:
        return "match_facts"
    if "careersquadhub" in normalized:
        return "squad"
    if "careertransferhub" in normalized:
        return "transfer"
    if "centralnews" in normalized:
        return "news"
    if "congratulations" in normalized and "winner" in normalized:
        return "competition_result"
    if "standings" in normalized:
        if re.search(
            r"(?:grabs|wins)(?:"
            + "|".join(month.lower() for month in MONTHS)
            + r")playerofthemonth",
            normalized,
        ):
            return "dashboard_award"
        return "dashboard"
    return "unknown"


def parse_integer(text):
    text = text.strip()
    return int(text) if re.fullmatch(r"\d+", text) else None


def parse_number(text):
    text = text.strip().removesuffix("%")
    return float(text) if re.fullmatch(r"\d+(?:\.\d+)?", text) else None


def parse_counts(text, count):
    parts = text.replace(" ", "").split("/")
    if len(parts) != count:
        return [None] * count
    return [parse_integer(part) for part in parts]


def parse_money(text):
    matched = re.fullmatch(
        r"\s*(USD|GBP|EUR|CAD|AUD|INR|Rs|\$|\u00a3|\u20ac|\u20b9)?\s*"
        r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)\s*([KM])?\s*",
        text,
        re.IGNORECASE,
    )
    if not matched:
        return None, None, None
    symbol, number, suffix = matched.groups()
    multiplier = {"K": 1000, "M": 1000000}.get((suffix or "").upper(), 1)
    amount = int(Decimal(number.replace(",", "")) * multiplier * 100)
    currency = {"\u00a3": "GBP", "\u20ac": "EUR", "\u20b9": "INR", "RS": "INR"}.get(
        (symbol or "").upper(),
        symbol.upper() if symbol and symbol != "$" else None,
    )
    return amount, currency, symbol


def parse_months(text):
    matched = re.fullmatch(
        r"\s*(\d+)\s*-?\s*(year|month)s?(?:\s*[\[(]s[\])])?\s*", text, re.IGNORECASE
    )
    if not matched or int(matched.group(1)) == 0:
        return None
    return int(matched.group(1)) * (12 if matched.group(2).lower() == "year" else 1)


def detected_fields(tokens, regions):
    fields = {}
    for field, bounds in regions.items():
        normalized = [
            bounds[0] / BASE_WIDTH,
            bounds[1] / BASE_HEIGHT,
            bounds[2] / BASE_WIDTH,
            bounds[3] / BASE_HEIGHT,
        ]
        selected = [
            token
            for token in tokens
            if normalized[0]
            <= sum(point[0] for point in token["box"]) / len(token["box"])
            <= normalized[2]
            and normalized[1]
            <= sum(point[1] for point in token["box"]) / len(token["box"])
            <= normalized[3]
        ]
        selected.sort(
            key=lambda token: (
                min(point[1] for point in token["box"]),
                min(point[0] for point in token["box"]),
            )
        )
        fields[field] = {
            "box": normalized,
            "method": "rapidocr_detected_region",
            "raw_text": " ".join(token["text"].strip() for token in selected),
            "confidence": min((token["confidence"] for token in selected), default=0.0),
        }
    return fields


def parse_header(text):
    cleaned = re.sub(r"0October|0ctober", "October", text, flags=re.IGNORECASE)
    pattern = r"(\d{1,2})\s*(" + "|".join(MONTHS) + r")\s*(20\d{2})"
    matched = re.search(pattern, cleaned, re.IGNORECASE)
    played_on = season = None
    if matched:
        month = next(
            index + 1
            for index, name in enumerate(MONTHS)
            if name.casefold() == matched.group(2).casefold()
        )
        try:
            played_on = date(
                int(matched.group(3)), month, int(matched.group(1))
            ).isoformat()
        except ValueError:
            played_on = None
        if played_on:
            season_year = int(matched.group(3)) - (month < 7)
            season = f"{season_year}/{str(season_year + 1)[-2:]}"
    competition = next(
        (
            name
            for alias, name in COMPETITION_LABELS.items()
            if alias in compact(cleaned).replace("0", "o")
        ),
        None,
    )
    sections = re.split(r"\s*[|]\s*|\s+I\s+", cleaned)
    venue = sections[1].strip() if len(sections) >= 3 else None
    return {
        "played_on": played_on,
        "season": season,
        "competition": competition,
        "venue": venue,
    }


def club_name(text):
    if compact(text) == "nottscounty":
        return "Notts County"
    words = text.strip().title().split()
    return (
        " ".join(
            word.upper() if word.upper() in {"FC", "MK", "AFC"} else word
            for word in words
        )
        or None
    )


def news_title(text):
    return re.sub(r"^(?:[O0]\s+|O(?=[A-Z]))", "", text.strip())


def parse_news_date(text):
    matched = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(20\d{2})\s*", text)
    if matched:
        try:
            return date(
                int(matched.group(3)), int(matched.group(2)), int(matched.group(1))
            ).isoformat()
        except ValueError:
            pass
    return None


def parse_calendar_month(text):
    labels = "|".join((*MONTHS, *(month[:3] for month in MONTHS)))
    matched = re.search(
        r"(?<![a-z])(" + labels + r")\s*(?:(\d{1,2})\s*,\s*)?(20\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if matched:
        month = next(
            index + 1
            for index, name in enumerate(MONTHS)
            if name[:3].casefold() == matched.group(1)[:3].casefold()
        )
        try:
            return date(
                int(matched.group(3)), month, int(matched.group(2) or 1)
            ).strftime("%Y-%m")
        except ValueError:
            pass
    return None


def parse_news_event(title, body="", announced_on=None, observed_on=None):
    title = news_title(title)
    normalized = compact(title)
    if any(
        word in normalized
        for word in (
            "shortlist",
            "nominee",
            "nominated",
            "nomination",
            "expected",
            "likely",
            "prediction",
        )
    ):
        return None
    player = club = period = event_type = None
    competition = parse_header(f"{title} {body}")["competition"]
    event_date = (
        date.fromisoformat(announced_on or observed_on)
        if announced_on or observed_on
        else None
    )
    monthly = re.match(
        r"(.+?)\s*(?:grabs|wins)\s*("
        + "|".join(MONTHS)
        + r")\s*Player\s*of\s*the\s*Month",
        title,
        re.IGNORECASE,
    )
    champion = re.fullmatch(
        r"(.+?)\s*Crowned\s*(.+?)\s*Champions?[.!]?", title, re.IGNORECASE
    )
    golden_boot = re.fullmatch(
        r"(.+?)\s*Wins\s*Golden\s*Boot[.!]?", title, re.IGNORECASE
    )
    award = re.fullmatch(
        r"(player|goalkeeper)ofthe(competition|tournament)(?:announced)?", normalized
    )
    if monthly:
        event_type = "player_of_the_month"
        player = monthly.group(1).strip()
        month = next(
            index + 1
            for index, name in enumerate(MONTHS)
            if name.casefold() == monthly.group(2).casefold()
        )
        period = MONTHS[month - 1]
        if event_date:
            event_date = date(event_date.year - (month > event_date.month), month, 1)
            period = event_date.strftime("%Y-%m")
        employer = re.search(r"performance\s*for\s*(.+?)\s*earned", body, re.IGNORECASE)
        if employer:
            club = club_name(employer.group(1))
    elif champion:
        event_type = "champion"
        club = club_name(champion.group(1))
        competition = parse_header(champion.group(2))["competition"]
    elif golden_boot:
        event_type = "golden_boot"
        player = golden_boot.group(1).strip()
    elif award:
        event_type = f"{award.group(1)}_of_the_competition"
        ownership = re.match(
            r"(.+?)['\u2019]s\s*(.+?)\s*has\s*been\s*named", body, re.IGNORECASE
        )
        named = re.match(r"(.+?)\s*has\s*been\s*named", body, re.IGNORECASE)
        if ownership:
            club = club_name(ownership.group(1))
            player = ownership.group(2).strip()
        elif named:
            player = named.group(1).strip()
            employer = re.search(r"\bThe\s+([^.!?]+?)\s+stopper\b", body, re.IGNORECASE)
            if employer:
                club = club_name(employer.group(1))
        else:
            return None
    else:
        return None
    season_year = event_date.year - (event_date.month < 7) if event_date else None
    season = f"{season_year}/{str(season_year + 1)[-2:]}" if season_year else None
    return {
        "type": "competition_event",
        "event_type": event_type,
        "player": player,
        "club": club,
        "competition": competition,
        "season": season,
        "announced_on": announced_on,
        "period": period or season,
        "description": f"{title}. {body}".strip(),
    }


class ScreenshotExtractor:
    def __init__(self, engine=None):
        if engine is None:
            from rapidocr_onnxruntime import RapidOCR

            engine = RapidOCR()
        self.engine = engine

    def recognize(self, image, regions, integer_fields=()):
        crops = []
        evidence = {}
        for field, bounds in regions.items():
            normalized = [
                bounds[0] / BASE_WIDTH,
                bounds[1] / BASE_HEIGHT,
                bounds[2] / BASE_WIDTH,
                bounds[3] / BASE_HEIGHT,
            ]
            actual = (
                round(normalized[0] * image.width),
                round(normalized[1] * image.height),
                round(normalized[2] * image.width),
                round(normalized[3] * image.height),
            )
            crops.append(np.asarray(image.crop(actual))[:, :, ::-1].copy())
            evidence[field] = {"box": normalized, "method": "rapidocr_recognizer_crop"}
        readings, elapsed = self.engine.text_recognizer(crops)
        if len(readings) != len(regions):
            raise ValueError(
                "OCR returned a different number of readings than supplied regions"
            )
        for field, (text, confidence) in zip(regions, readings):
            evidence[field].update(raw_text=text, confidence=float(confidence))
        retries = []
        retry_fields = []
        for field, crop in zip(regions, crops):
            if (
                field not in integer_fields
                or parse_integer(evidence[field]["raw_text"]) is not None
            ):
                continue
            grayscale = Image.fromarray(crop[:, :, ::-1]).convert("L")
            binary = grayscale.point(lambda value: 0 if value < 160 else 255)
            bounds = ImageOps.invert(binary).getbbox()
            if bounds is None or bounds[3] - bounds[1] < max(3, binary.height * 0.35):
                continue
            glyph = ImageOps.autocontrast(grayscale.crop(bounds))
            glyph = glyph.resize(
                (max(1, round(glyph.width * 48 / glyph.height)), 48),
                Image.Resampling.LANCZOS,
            )
            for copies in (3, 5):
                strip = Image.new("L", ((glyph.width + 8) * copies + 8, 64), 255)
                for index in range(copies):
                    strip.paste(glyph, (8 + index * (glyph.width + 8), 8))
                retries.append(np.asarray(strip.convert("RGB"))[:, :, ::-1].copy())
                retry_fields.append((field, copies))
        if retries:
            recovered, elapsed = self.engine.text_recognizer(retries)
            if len(recovered) != len(retry_fields):
                raise ValueError(
                    "OCR returned a different number of numeric retry readings than supplied regions"
                )
            for (field, copies), (text, confidence) in zip(retry_fields, recovered):
                evidence[field].setdefault("numeric_retry", []).append(
                    {
                        "copies": copies,
                        "raw_text": text,
                        "confidence": float(confidence),
                    }
                )
            for field in dict.fromkeys(field for field, copies in retry_fields):
                readings = evidence[field]["numeric_retry"]
                valid = [
                    reading
                    for reading in readings
                    if reading["confidence"] >= 0.6
                    and len(reading["raw_text"]) == reading["copies"]
                    and re.fullmatch(r"[0-9]+", reading["raw_text"])
                    and len(set(reading["raw_text"])) == 1
                ]
                if (
                    len(valid) == 2
                    and valid[0]["raw_text"][0] == valid[1]["raw_text"][0]
                ):
                    evidence[field]["initial_reading"] = {
                        "raw_text": evidence[field]["raw_text"],
                        "confidence": evidence[field]["confidence"],
                    }
                    evidence[field].update(
                        raw_text=valid[0]["raw_text"][0],
                        confidence=min(reading["confidence"] for reading in valid),
                        method="rapidocr_repeated_digit_crop",
                    )
        return evidence

    def extract(self, path):
        with Image.open(path) as original:
            image = original.convert("RGB")
        detections, elapsed = self.engine(np.asarray(image)[:, :, ::-1].copy())
        detections = detections or []
        tokens = [
            {
                "text": text,
                "confidence": float(confidence),
                "box": [
                    [float(point[0]) / image.width, float(point[1]) / image.height]
                    for point in polygon
                ],
            }
            for polygon, text, confidence in detections
        ]
        screen_type = classify("\n".join(token["text"] for token in tokens))
        evidence = {
            "full_image_tokens": tokens,
            "extractor_version": EXTRACTOR_VERSION,
            "dimensions": [image.width, image.height],
            "fields": {},
        }
        issues = [
            "Visual review is required before these candidates become canonical data."
        ]
        if abs(image.width / image.height - BASE_WIDTH / BASE_HEIGHT) > 0.015:
            return {
                "screen_type": screen_type,
                "records": [],
                "evidence": evidence,
                "issues": [
                    "Unsupported aspect ratio; inspect the screenshot and establish its layout."
                ],
            }
        if screen_type == "match_facts":
            record, fields = self.extract_match(image)
            records = [record]
        elif screen_type in {"player_performance", "goalkeeper_performance"}:
            record, fields = self.extract_player(
                image, screen_type == "goalkeeper_performance"
            )
            records = [record]
            issues.append(
                "Confirm match_id from the source sequence and fixture context, not adjacency alone."
            )
        elif screen_type == "squad":
            record, fields = self.extract_snapshot(image)
            records = [record]
            issues.append(
                "Only the selected player's profile is proposed; other squad and totals rows need review."
            )
            issues.append(
                "Establish season and date precision from surrounding career evidence."
            )
            squad_text = compact(" ".join(token["text"] for token in tokens)).replace(
                "0", "o"
            )
            if "totals" in squad_text and any(
                alias in squad_text for alias in COMPETITION_LABELS
            ):
                additional_records, totals_fields = self.extract_squad_totals(
                    image, record
                )
                records.extend(additional_records)
                fields.update(totals_fields)
                issues.append(
                    "Cumulative totals are observations, not extra match stats; confirm their season and cutoff."
                )
        elif screen_type == "transfer":
            records, fields, transfer_issues = self.extract_transfer(tokens)
            issues.extend(transfer_issues)
        elif screen_type == "news":
            records, fields, news_issues = self.extract_news(tokens)
            issues.extend(news_issues)
        elif screen_type == "dashboard_award":
            records, fields, news_issues = self.extract_dashboard_award(image, tokens)
            issues.extend(news_issues)
        elif screen_type == "competition_result":
            records, fields = self.extract_competition_result(tokens)
            issues.append(
                "Confirm the competition season and announcement date; the winner screen does not show them."
            )
        else:
            return {
                "screen_type": screen_type,
                "records": [],
                "evidence": evidence,
                "issues": [
                    f"{screen_type}: no automatic field layout yet; retain this source for manual review."
                ],
            }
        evidence["fields"] = fields
        issues.extend(
            f"Low OCR confidence for {field}: {reading['confidence']:.2f}"
            for field, reading in fields.items()
            if reading["confidence"] < 0.85
        )
        return {
            "screen_type": screen_type,
            "records": records,
            "evidence": evidence,
            "issues": issues,
        }

    def extract_transfer(self, tokens):
        fields = detected_fields(
            tokens,
            {
                "panel_heading": (684, 195, 1040, 225),
                "player": (697, 228, 986, 287),
                "to_club": (733, 287, 982, 309),
                "weekly_wage_minor": (692, 357, 806, 383),
                "contract_months": (813, 357, 928, 383),
                "loan_months": (733, 508, 829, 565),
                "transfer_type": (953, 508, 1053, 565),
                "completion": (685, 385, 1054, 453),
                "status": (865, 510, 947, 565),
            },
        )
        text = {field: reading["raw_text"] for field, reading in fields.items()}
        completed = "andhejustjoinedtheteam" in compact(text["completion"])
        transfer_type = {"transfer": "permanent", "loan": "loan"}.get(
            compact(text["transfer_type"])
        )
        if (
            compact(text["panel_heading"]) != "contractoffers"
            or not completed
            or compact(text["status"]) != "accepted"
            or not transfer_type
            or not text["player"]
            or not text["to_club"]
        ):
            return (
                [],
                fields,
                [
                    "No completed transfer or loan confirmed in the selected contract panel; offers are not signings."
                ],
            )
        date_text = ""
        surname = compact(text["player"].split()[-1])
        selected_rows = [
            token
            for token in tokens
            if 320 / BASE_WIDTH
            < min(point[0] for point in token["box"])
            < 520 / BASE_WIDTH
            and 255 / BASE_HEIGHT
            < min(point[1] for point in token["box"])
            < 645 / BASE_HEIGHT
            and compact(token["text"]).endswith(surname)
        ]
        if len(selected_rows) == 1:
            center = (
                sum(point[1] for point in selected_rows[0]["box"])
                / len(selected_rows[0]["box"])
                * BASE_HEIGHT
            )
            fields.update(
                detected_fields(
                    tokens, {"effective_on": (580, center - 14, 667, center + 14)}
                )
            )
            date_text = fields["effective_on"]["raw_text"]
        wage, currency, symbol = parse_money(text["weekly_wage_minor"])
        record = {
            "type": "player_transfer",
            "player": text["player"],
            "from_club": None,
            "to_club": club_name(text["to_club"]),
            "transfer_type": transfer_type,
            "effective_on": None,
            "date_basis": f"{date_text or 'No exact date'} shown in the selected transfer row; year requires review.",
            "fee_minor": None,
            "weekly_wage_minor": wage,
            "currency": currency,
            "currency_display": symbol,
            "contract_months": parse_months(text["contract_months"]),
            "loan_months": parse_months(text["loan_months"])
            if transfer_type == "loan"
            else None,
        }
        return (
            [record],
            fields,
            [
                "Confirm the transfer date/year and selling club; neither is inferred from a badge or filename.",
                "The contract offer is not a transfer fee. A dollar symbol alone does not identify its currency.",
            ],
        )

    def extract_news(self, tokens):
        fields = detected_fields(
            tokens,
            {
                "article.title": (949, 225, 1267, 290),
                "article.body": (949, 300, 1267, 404),
            },
        )
        title = fields["article.title"]["raw_text"]
        body = fields["article.body"]["raw_text"]
        stories = []
        for row_index in range(6):
            top = 198 + row_index * 74.8
            prefix = f"news.{row_index}"
            fields.update(
                detected_fields(
                    tokens,
                    {
                        f"{prefix}.title": (79, top + 7, 369, top + 49),
                        f"{prefix}.announced_on": (99, top + 50, 230, top + 70),
                    },
                )
            )
            headline = fields[f"{prefix}.title"]["raw_text"]
            announced_on = parse_news_date(fields[f"{prefix}.announced_on"]["raw_text"])
            stories.append((headline, announced_on))
        matching = [
            announced_on
            for headline, announced_on in stories
            if compact(news_title(headline)) == compact(news_title(title))
        ]
        selected = parse_news_event(
            title, body, matching[0] if len(matching) == 1 else None
        )
        records = [selected] if selected else []
        for headline, announced_on in stories:
            if selected and compact(news_title(headline)) == compact(news_title(title)):
                continue
            record = parse_news_event(headline, announced_on=announced_on)
            if record:
                records.append(record)
        issues = []
        if not records:
            issues.append(
                "No named award winner or championship found; predictions and shortlists are not awards."
            )
        for record in records:
            if not record["competition"] or not record["season"]:
                issues.append(
                    f"Confirm competition/season for {record['description']}; unrelated articles are not used as context."
                )
            if record["player"]:
                issues.append(
                    f"Confirm the full player identity for {record['player']}; news may display only a surname."
                )
        return records, fields, issues

    def extract_competition_result(self, tokens):
        fields = detected_fields(
            tokens,
            {
                "competition": (139, 74, 654, 105),
                "club": (300, 509, 655, 550),
                "confirmation": (270, 211, 560, 310),
            },
        )
        confirmation = compact(fields["confirmation"]["raw_text"])
        competition = parse_header(fields["competition"]["raw_text"])["competition"]
        winner = club_name(fields["club"]["raw_text"])
        if (
            "winner" not in confirmation
            or "congratulations" not in confirmation
            or not winner
        ):
            return [], fields
        return [
            {
                "type": "competition_event",
                "event_type": "champion",
                "player": None,
                "club": winner,
                "competition": competition,
                "season": None,
                "announced_on": None,
                "period": None,
                "description": f"{winner} won {fields['competition']['raw_text']}.",
            }
        ], fields

    def extract_dashboard_award(self, image, tokens):
        fields = detected_fields(
            tokens,
            {
                "calendar": (590, 208, 676, 236),
                "fixture_date": (87, 248, 373, 270),
                "headline.detected": (775, 439, 1136, 463),
            },
        )
        enlarged = image.resize(
            (image.width * 2, image.height * 2), Image.Resampling.LANCZOS
        )
        fields.update(self.recognize(enlarged, {"headline": (779, 442, 1134, 459)}))
        months = {
            parse_calendar_month(fields[field]["raw_text"])
            for field in ("calendar", "fixture_date")
        }
        months.discard(None)
        observed_on = f"{next(iter(months))}-01" if len(months) == 1 else None
        record = parse_news_event(
            fields["headline"]["raw_text"], observed_on=observed_on
        )
        if record is None:
            record = parse_news_event(
                fields["headline.detected"]["raw_text"], observed_on=observed_on
            )
        return (
            ([record] if record else []),
            fields,
            [
                "Dashboard month/year is observation context, not the award announcement date; confirm the award period.",
                "Confirm the award's competition and club; upcoming fixtures, standings and the training player are not award evidence.",
            ],
        )

    def extract_match(self, image):
        regions = {
            "header": (250, 45, 1110, 72),
            "home_club": (250, 108, 584, 155),
            "away_club": (795, 108, 1136, 155),
            "home_goals": (597, 103, 644, 157),
            "away_goals": (725, 103, 774, 157),
            "clock": (619, 74, 753, 110),
        }
        for field, center in TEAM_ROWS.items():
            regions[f"home.{field}"] = (728, center - 10, 759, center + 10)
            regions[f"away.{field}"] = (1213, center - 10, 1239, center + 10)
        integer_fields = {
            f"{side}.{field}"
            for side in ("home", "away")
            for field in TEAM_ROWS
            if not field.endswith("_pct")
        }
        fields = self.recognize(image, regions, integer_fields)
        record = {"type": "match", **parse_header(fields["header"]["raw_text"])}
        for side in ("home", "away"):
            record[f"{side}_club"] = club_name(fields[f"{side}_club"]["raw_text"])
            record[f"{side}_goals"] = parse_integer(fields[f"{side}_goals"]["raw_text"])
        clock = fields["clock"]["raw_text"]
        shootout = re.search(r"(\d+)\s*[-:]\s*(\d+).*PEN", clock, re.IGNORECASE)
        minutes = re.search(r"\b(90|120)[:.]00\b", clock)
        record.update(
            home_penalties=int(shootout.group(1)) if shootout else None,
            away_penalties=int(shootout.group(2)) if shootout else None,
            duration_minutes=int(minutes.group(1))
            if minutes and not shootout
            else None,
            extra_time=True
            if "ET" in clock
            else (False if minutes and not shootout else None),
        )
        record["team_stats"] = {
            side: {
                field: (parse_number if field.endswith("_pct") else parse_integer)(
                    fields[f"{side}.{field}"]["raw_text"]
                )
                for field in TEAM_ROWS
            }
            for side in ("home", "away")
        }
        return record, fields

    def extract_player(self, image, goalkeeper=False):
        regions = {
            "first_name": (175, 139, 404, 163),
            "last_name": (175, 163, 404, 190),
            "overall": (174, 191, 224, 228),
            "displayed_position": (192, 253, 326, 280),
            "club": (544, 140, 726, 173),
            "rating": (746, 178, 853, 232),
        }
        rows = GOALKEEPER_ROWS if goalkeeper else OUTFIELD_ROWS
        for field, (side, center) in rows.items():
            right = 662 if side == "left" else 1193
            grouped = "/" in field or field.endswith("_pct")
            width = 100 if "/" in field else (66 if grouped else 26)
            regions[field] = (
                right - width,
                center - (11 if grouped else 10),
                right,
                center + (12 if grouped else 10),
            )
        integer_fields = {
            field for field in rows if "/" not in field and not field.endswith("_pct")
        }
        fields = self.recognize(image, regions, integer_fields)
        record = {
            "type": "player_match",
            "match_id": None,
            "player": " ".join(
                fields[field]["raw_text"].strip()
                for field in ("first_name", "last_name")
            ),
            "club": club_name(fields["club"]["raw_text"]),
            "overall": parse_integer(fields["overall"]["raw_text"]),
            "displayed_position": fields["displayed_position"]["raw_text"].strip()
            or None,
            "rating": parse_number(fields["rating"]["raw_text"]),
            "started": None,
            "minutes_played": None,
        }
        for field in rows:
            raw_text = fields[field]["raw_text"]
            parts = field.split("/")
            if len(parts) > 1:
                record.update(zip(parts, parse_counts(raw_text, len(parts))))
            else:
                record[field] = (
                    parse_number if field.endswith("_pct") else parse_integer
                )(raw_text)
        return record, fields

    def extract_snapshot(self, image):
        regions = {
            "first_name": (698, 245, 962, 269),
            "last_name": (698, 270, 973, 302),
            "overall": (982, 268, 1028, 308),
            "displayed_position": (713, 310, 738, 335),
            "age": (764, 310, 784, 335),
            "nationality": (818, 310, 1039, 335),
        }
        fields = self.recognize(image, regions)
        return {
            "type": "player_snapshot",
            "season": None,
            "club": "Notts County",
            "player": " ".join(
                fields[field]["raw_text"].strip()
                for field in ("first_name", "last_name")
            ),
            "overall": parse_integer(fields["overall"]["raw_text"]),
            "age": parse_integer(fields["age"]["raw_text"]),
            "displayed_position": fields["displayed_position"]["raw_text"].strip()
            or None,
            "nationality": fields["nationality"]["raw_text"].strip() or None,
            "snapshot_kind": "first_observed",
            "observed_on": None,
            "date_from": None,
            "date_to": None,
            "date_precision": "unknown",
            "date_basis": "No exact in-game date on this screen; season context requires review.",
        }, fields

    def extract_squad_totals(self, image, profile=None):
        if profile is None:
            profile, profile_fields = self.extract_snapshot(image)
        regions = {}
        numeric_columns = {
            "appearances": (819, 843),
            "goals": (851, 875),
            "assists": (883, 907),
            "clean_sheets": (915, 939),
            "yellow_cards": (947, 971),
            "red_cards": (979, 1003),
            "average_rating": (1009, 1040),
        }
        for row_index, center in enumerate((410, 445, 479, 513, 547, 582)):
            prefix = f"season_totals.{row_index}"
            regions[f"{prefix}.competition"] = (701, center - 10, 809, center + 10)
            for field, (left, right) in numeric_columns.items():
                regions[f"{prefix}.{field}"] = (left, center - 10, right, center + 10)
        evidence = self.recognize(image, regions)
        records = []
        for row_index in range(6):
            prefix = f"season_totals.{row_index}"
            label = compact(evidence[f"{prefix}.competition"]["raw_text"]).replace(
                "0", "o"
            )
            if not label:
                continue
            total = label in {"total", "totals"}
            competition = next(
                (name for alias, name in COMPETITION_LABELS.items() if alias in label),
                None,
            )
            record = {
                "type": "player_competition_snapshot",
                "player": profile["player"],
                "club": profile["club"],
                "season": None,
                "observed_on": None,
                "snapshot_kind": "in_season",
                "date_basis": "Season and observation cutoff must be confirmed from career context.",
                "scope": "all_competitions" if total else "competition",
            }
            if not total:
                record["competition"] = competition
            for field in numeric_columns:
                raw_text = evidence[f"{prefix}.{field}"]["raw_text"]
                record[field] = (
                    parse_number if field == "average_rating" else parse_integer
                )(raw_text)
            records.append(record)
        return records, evidence
