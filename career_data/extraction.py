import re
from datetime import date

import numpy as np
from PIL import Image

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
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")
TEAM_ROWS = {
    "shots": 330, "shots_on_target": 366, "possession_pct": 401,
    "tackles": 437, "fouls": 472, "corners": 508,
    "shot_accuracy_pct": 543, "pass_accuracy_pct": 579,
}
OUTFIELD_ROWS = {
    "goals": ("left", 358),
    "shots_on_target/shots_off_target": ("left", 384),
    "assists": ("left", 435),
    "passes_completed_short/passes_completed_medium/passes_completed_long": ("left", 460),
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
    "passes_completed_short/passes_completed_medium/passes_completed_long": ("right", 350),
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
        return "goalkeeper_performance" if "goalkeeping" in normalized else "player_performance"
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


def parse_header(text):
    cleaned = re.sub(r"0October|0ctober", "October", text, flags=re.IGNORECASE)
    pattern = r"(\d{1,2})\s*(" + "|".join(MONTHS) + r")\s*(20\d{2})"
    matched = re.search(pattern, cleaned, re.IGNORECASE)
    played_on = season = None
    if matched:
        month = next(index + 1 for index, name in enumerate(MONTHS)
                     if name.casefold() == matched.group(2).casefold())
        try:
            played_on = date(int(matched.group(3)), month, int(matched.group(1))).isoformat()
        except ValueError:
            played_on = None
        if played_on:
            season_year = int(matched.group(3)) - (month < 7)
            season = f"{season_year}/{str(season_year + 1)[-2:]}"
    competition = next((name for alias, name in COMPETITION_LABELS.items()
                        if alias in compact(cleaned).replace("0", "o")), None)
    sections = re.split(r"\s*[|]\s*|\s+I\s+", cleaned)
    venue = sections[1].strip() if len(sections) >= 3 else None
    return {"played_on": played_on, "season": season, "competition": competition, "venue": venue}


def club_name(text):
    if compact(text) == "nottscounty":
        return "Notts County"
    words = text.strip().title().split()
    return " ".join(word.upper() if word.upper() in {"FC", "MK", "AFC"} else word for word in words) or None


class ScreenshotExtractor:
    def __init__(self, engine=None):
        if engine is None:
            from rapidocr_onnxruntime import RapidOCR

            engine = RapidOCR()
        self.engine = engine

    def recognize(self, image, regions):
        crops = []
        evidence = {}
        for field, bounds in regions.items():
            normalized = [bounds[0] / BASE_WIDTH, bounds[1] / BASE_HEIGHT,
                          bounds[2] / BASE_WIDTH, bounds[3] / BASE_HEIGHT]
            actual = (round(normalized[0] * image.width), round(normalized[1] * image.height),
                      round(normalized[2] * image.width), round(normalized[3] * image.height))
            crops.append(np.asarray(image.crop(actual))[:, :, ::-1].copy())
            evidence[field] = {"box": normalized, "method": "rapidocr_recognizer_crop"}
        readings, elapsed = self.engine.text_recognizer(crops)
        if len(readings) != len(regions):
            raise ValueError("OCR returned a different number of readings than supplied regions")
        for field, (text, confidence) in zip(regions, readings):
            evidence[field].update(raw_text=text, confidence=float(confidence))
        return evidence

    def extract(self, path):
        with Image.open(path) as original:
            image = original.convert("RGB")
        detections, elapsed = self.engine(np.asarray(image)[:, :, ::-1].copy())
        detections = detections or []
        tokens = [{"text": text, "confidence": float(confidence),
                   "box": [[float(point[0]) / image.width, float(point[1]) / image.height] for point in polygon]}
                  for polygon, text, confidence in detections]
        screen_type = classify("\n".join(token["text"] for token in tokens))
        evidence = {"full_image_tokens": tokens, "extractor_version": EXTRACTOR_VERSION,
                    "dimensions": [image.width, image.height], "fields": {}}
        issues = ["Visual review is required before these candidates become canonical data."]
        if abs(image.width / image.height - BASE_WIDTH / BASE_HEIGHT) > 0.015:
            return {"screen_type": screen_type, "records": [], "evidence": evidence,
                    "issues": ["Unsupported aspect ratio; inspect the screenshot and establish its layout."]}
        if screen_type == "match_facts":
            record, fields = self.extract_match(image)
        elif screen_type in {"player_performance", "goalkeeper_performance"}:
            record, fields = self.extract_player(image, screen_type == "goalkeeper_performance")
            issues.append("Confirm match_id from the source sequence and fixture context, not adjacency alone.")
        elif screen_type == "squad":
            record, fields = self.extract_snapshot(image)
            issues.append("Only the selected player's profile is proposed; other squad and totals rows need review.")
            issues.append("Establish season and date precision from surrounding career evidence.")
        else:
            return {"screen_type": screen_type, "records": [], "evidence": evidence,
                    "issues": [f"{screen_type}: no automatic field layout yet; retain this source for manual review."]}
        evidence["fields"] = fields
        issues.extend(f"Low OCR confidence for {field}: {reading['confidence']:.2f}"
                      for field, reading in fields.items() if reading["confidence"] < 0.85)
        return {"screen_type": screen_type, "records": [record], "evidence": evidence, "issues": issues}

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
        fields = self.recognize(image, regions)
        record = {"type": "match", **parse_header(fields["header"]["raw_text"])}
        for side in ("home", "away"):
            record[f"{side}_club"] = club_name(fields[f"{side}_club"]["raw_text"])
            record[f"{side}_goals"] = parse_integer(fields[f"{side}_goals"]["raw_text"])
        clock = fields["clock"]["raw_text"]
        shootout = re.search(r"(\d+)\s*[-:]\s*(\d+).*PEN", clock, re.IGNORECASE)
        minutes = re.search(r"\b(90|120)[:.]00\b", clock)
        record.update(home_penalties=int(shootout.group(1)) if shootout else None,
                      away_penalties=int(shootout.group(2)) if shootout else None,
                      duration_minutes=int(minutes.group(1)) if minutes and not shootout else None,
                      extra_time=True if "ET" in clock else (False if minutes and not shootout else None))
        record["team_stats"] = {
            side: {field: (parse_number if field.endswith("_pct") else parse_integer)(
                fields[f"{side}.{field}"]["raw_text"]) for field in TEAM_ROWS}
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
            regions[field] = (right - width, center - (11 if grouped else 10),
                              right, center + (12 if grouped else 10))
        fields = self.recognize(image, regions)
        record = {
            "type": "player_match", "match_id": None,
            "player": " ".join(fields[field]["raw_text"].strip() for field in ("first_name", "last_name")),
            "club": club_name(fields["club"]["raw_text"]),
            "overall": parse_integer(fields["overall"]["raw_text"]),
            "displayed_position": fields["displayed_position"]["raw_text"].strip() or None,
            "rating": parse_number(fields["rating"]["raw_text"]),
            "started": None, "minutes_played": None,
        }
        for field in rows:
            raw_text = fields[field]["raw_text"]
            parts = field.split("/")
            if len(parts) > 1:
                record.update(zip(parts, parse_counts(raw_text, len(parts))))
            else:
                record[field] = (parse_number if field.endswith("_pct") else parse_integer)(raw_text)
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
            "type": "player_snapshot", "season": None, "club": "Notts County",
            "player": " ".join(fields[field]["raw_text"].strip() for field in ("first_name", "last_name")),
            "overall": parse_integer(fields["overall"]["raw_text"]),
            "age": parse_integer(fields["age"]["raw_text"]),
            "displayed_position": fields["displayed_position"]["raw_text"].strip() or None,
            "nationality": fields["nationality"]["raw_text"].strip() or None,
            "snapshot_kind": "first_observed", "observed_on": None,
            "date_from": None, "date_to": None, "date_precision": "unknown",
            "date_basis": "No exact in-game date on this screen; season context requires review.",
        }, fields
