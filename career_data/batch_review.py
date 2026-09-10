import argparse
import json
import unicodedata
from pathlib import Path

from .database import connect, json_text
from .extraction import TEAM_ROWS
from .pipeline import approve_review, export_data, make_review, select_sources, write_json


PLAYER_CORE_FIELDS = {
    "type", "player", "club", "overall", "displayed_position", "rating",
    "goals", "assists", "shots_on_target", "shots_off_target",
    "goals_conceded", "goals_conceded_displayed", "goals_conceded_basis", "shots_caught", "shots_parried",
}


def name_key(value):
    normalized = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in normalized if character.isascii() and character.isalnum())


def prepare_match_headers(connection, decisions):
    sequences = decisions["match_header_sequences"]
    if len(set(sequences)) != len(sequences):
        raise ValueError("Reviewed summary sequence list contains duplicates")
    clubs = {name_key(name): name for name in decisions["club_names"]}
    document = make_review(connection, set(sequences))
    source_sequences = {source["id"]: source["sequence"] for source in select_sources(connection, set(sequences))}
    if len(document["sources"]) != len(sequences):
        raise ValueError("Every reviewed summary must have a retained extraction")
    for source in document["sources"]:
        sequence = source_sequences[source["source_id"]]
        if source["screen_type"] != "match_facts" or len(source["records"]) != 1:
            raise ValueError(f"Screenshot {sequence} is not one match summary")
        record = source["records"][0]
        for field in ("home_club", "away_club"):
            key = name_key(record[field])
            if key not in clubs:
                raise ValueError(f"Unreviewed club name on {sequence}: {record[field]}")
            record[field] = clubs[key]
        if record.get("venue", "") and name_key(record["venue"]) in {"ivylane", "lvylane", "livylane"}:
            record["venue"] = "Ivy Lane"
        record.update(decisions.get("match_overrides", {}).get(str(sequence), {}))
        if not source["complete"]:
            record.pop("team_stats", None)
        source["issues"] = ["Header reviewed; team statistics require their own source-image review."]
    return document


def fixture_contexts(connection):
    contexts = {}
    current_match = None
    interrupted = False
    for source in select_sources(connection):
        source_id = source["id"]
        screen_type = source["screen_type"]
        if screen_type == "match_facts":
            matches = connection.execute("SELECT match_id FROM match_sources WHERE source_id = ?", (source_id,)).fetchall()
            current_match = matches[0]["match_id"] if len(matches) == 1 else None
            interrupted = False
        elif screen_type in {"player_performance", "goalkeeper_performance"}:
            if current_match is None or interrupted:
                raise ValueError(f"Player source {source['sequence']} needs a reviewed fixture boundary")
            contexts[source_id] = current_match
        else:
            interrupted = True
    return contexts


def prepare_player_cores(connection, decisions):
    ranges = decisions["player_core_ranges"]
    selected = [source for source in select_sources(connection)
                if source["screen_type"] in {"player_performance", "goalkeeper_performance"}
                and any(start <= source["sequence"] <= end for start, end in ranges)]
    source_sequences = {source["id"]: source["sequence"] for source in selected}
    contexts = fixture_contexts(connection)
    document = make_review(connection, {source["sequence"] for source in selected})
    if len(document["sources"]) != len(selected):
        raise ValueError("Every reviewed player source must have an extraction")
    for source in document["sources"]:
        sequence = source_sequences[source["source_id"]]
        if len(source["records"]) != 1 or source["records"][0].get("type") != "player_match":
            raise ValueError(f"Source {sequence} is not a single player performance")
        record = source["records"][0]
        if not source["complete"]:
            record = {field: value for field, value in record.items() if field in PLAYER_CORE_FIELDS}
        record.pop("match_source_id", None)
        record["match_id"] = contexts[source["source_id"]]
        record["player"] = decisions.get("player_name_aliases", {}).get(record["player"], record["player"])
        if sequence in decisions.get("goalkeeper_zero_assists", []):
            if source["screen_type"] != "goalkeeper_performance":
                raise ValueError(f"Source {sequence} is not a goalkeeper for the reviewed zero-assist correction")
            record["assists"] = 0
        record.update(decisions.get("player_core_overrides", {}).get(str(sequence), {}))
        if source["screen_type"] == "goalkeeper_performance":
            fixture = connection.execute("SELECT matches.*, home.name AS home_club FROM matches "
                                         "JOIN clubs home ON home.id = home_club_id WHERE matches.id = ?",
                                         (record["match_id"],)).fetchone()
            opponent_side = "away" if name_key(record["club"]) == name_key(fixture["home_club"]) else "home"
            displayed = record.get("goals_conceded_displayed", record.get("goals_conceded"))
            record["goals_conceded_displayed"] = displayed
            penalties = fixture[f"{opponent_side}_penalties"]
            opponent_goals = fixture[f"{opponent_side}_goals"]
            if penalties is not None:
                if displayed == opponent_goals + penalties:
                    record["goals_conceded"] = opponent_goals
                    record["goals_conceded_basis"] = "Displayed goalkeeper count includes opponent shootout goals; subtract the separately verified shootout score."
                elif displayed != opponent_goals:
                    raise ValueError(f"Goalkeeper source {sequence}: ambiguous shootout-inclusive count")
                else:
                    record["goals_conceded"] = displayed
                    record["goals_conceded_basis"] = "Displayed count agrees with the opponent's score before the shootout."
            else:
                record["goals_conceded_basis"] = "Displayed goalkeeper count; this match had no penalty shootout."
        source["records"] = [record]
        source["issues"] = ["Core player fields reviewed; unreviewed detailed stats remain in OCR evidence."]
    return document


def prepare_team_tables(connection, decisions):
    selected = set(decisions["team_table_sequences"])
    headers = prepare_match_headers(connection, decisions)
    sequences = {source["id"]: source["sequence"] for source in select_sources(connection, selected)}
    sources = []
    for source in headers["sources"]:
        sequence = sequences.get(source["source_id"])
        if sequence is None:
            continue
        record = source["records"][0]
        if "team_stats" not in record:
            candidate = connection.execute("SELECT candidate_json FROM extractions WHERE source_id = ?", (source["source_id"],)).fetchone()
            record["team_stats"] = json.loads(candidate["candidate_json"])[0]["team_stats"]
        for field, value in decisions.get("team_stat_overrides", {}).get(str(sequence), {}).items():
            side, metric = field.split(".")
            if side not in {"home", "away"} or metric not in TEAM_ROWS:
                raise ValueError(f"Unknown team statistic override: {field}")
            record["team_stats"][side][metric] = value
        for side in ("home", "away"):
            if set(record["team_stats"][side]) != set(TEAM_ROWS):
                raise ValueError(f"Incomplete team-stat field set on source {sequence}")
            if any(value is None for value in record["team_stats"][side].values()):
                raise ValueError(f"Source {sequence} still has unreadable team statistics")
        source["complete"] = True
        source["issues"] = []
        sources.append(source)
    if len(sources) != len(selected):
        raise ValueError("Every reviewed team table must also have a reviewed match header")
    return {"schema_version": headers["schema_version"], "sources": sources}


def main():
    parser = argparse.ArgumentParser(description="Prepare image-reviewed archive batches without approving unreviewed fields.")
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--kind", choices=("matches", "players", "teams"), default="matches")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    connection = connect(root / "data/career.sqlite")
    try:
        decisions = json.loads(arguments.decisions.read_text(encoding="utf-8"))
        prepare = {"matches": prepare_match_headers, "players": prepare_player_cores, "teams": prepare_team_tables}[arguments.kind]
        document = prepare(connection, decisions)
        write_json(arguments.output, document, overwrite=False)
        print(json_text({"review_sources": len(document["sources"]), "output": str(arguments.output)}), end="")
        if arguments.approve:
            note_key = {"matches": "match_header_review", "players": "player_core_review", "teams": "team_table_review"}[arguments.kind]
            note = decisions[note_key]
            print(json_text(approve_review(connection, document, note)), end="")
            print(json_text(export_data(connection, root / "data/exports/career.json")), end="")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
