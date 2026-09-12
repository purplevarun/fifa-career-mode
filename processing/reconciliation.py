from collections import Counter
from decimal import Decimal, ROUND_DOWN

from . import SCHEMA_VERSION


def compare_metric(observed, derived, missing=0):
    if observed is None:
        result = "not_captured"
    elif missing or derived is None:
        result = "not_comparable"
    else:
        result = "match" if observed == derived else "mismatch"
    return {"observed": observed, "derived": derived, "missing_match_values": missing,
            "result": result, "difference": derived - observed if observed is not None and derived is not None else None}


def reconcile_totals(connection, season=None, club="Notts County", rating_decimals=1):
    if rating_decimals not in (1, 2):
        raise ValueError("Rating display precision must be one or two decimal places")
    parameters = [club]
    season_filter = ""
    if season is not None:
        season_filter = " AND seasons.label = ?"
        parameters.append(season)
    snapshots = connection.execute(
        "SELECT totals.*, players.name AS player, clubs.name AS club, seasons.label AS season, "
        "competitions.name AS competition FROM player_competition_snapshots totals "
        "JOIN players ON players.id = totals.player_id JOIN clubs ON clubs.id = totals.club_id "
        "JOIN seasons ON seasons.id = totals.season_id "
        "LEFT JOIN competition_seasons ON competition_seasons.id = totals.competition_season_id "
        "LEFT JOIN competitions ON competitions.id = competition_seasons.competition_id "
        "WHERE clubs.name = ? COLLATE NOCASE" + season_filter +
        " ORDER BY seasons.label, players.name, totals.scope, competitions.name, totals.observed_on",
        parameters,
    ).fetchall()
    comparisons = []
    metric_counts = {field: Counter() for field in ("appearances", "goals", "assists", "average_rating")}
    for snapshot in snapshots:
        comparison = {field: snapshot[field] for field in
                      ("player_id", "player", "club", "season", "scope", "competition", "source_id", "observed_on", "snapshot_kind", "date_basis")}
        comparison["snapshot_id"] = snapshot["id"]
        if snapshot["observed_on"] is None and snapshot["snapshot_kind"] != "season_end":
            comparison.update(result="unconfirmed_cutoff", metrics={})
            comparisons.append(comparison)
            continue
        filters = ["performances.player_id = ?", "performances.club_id = ?", "editions.season_id = ?"]
        values = [snapshot["player_id"], snapshot["club_id"], snapshot["season_id"]]
        if snapshot["scope"] == "competition":
            filters.append("editions.id = ?")
            values.append(snapshot["competition_season_id"])
        if snapshot["observed_on"] is not None:
            filters.append("matches.played_on <= ?")
            values.append(snapshot["observed_on"])
        performances = connection.execute(
            "SELECT performances.* FROM player_matches performances JOIN matches ON matches.id = performances.match_id "
            "JOIN competition_seasons editions ON editions.id = matches.competition_season_id WHERE " +
            " AND ".join(filters) + " ORDER BY matches.played_on, performances.id", values,
        ).fetchall()
        metrics = {"appearances": compare_metric(snapshot["appearances"], len(performances))}
        for field in ("goals", "assists"):
            missing = sum(performance[field] is None for performance in performances)
            derived = sum(performance[field] for performance in performances) if not missing else None
            metrics[field] = compare_metric(snapshot[field], derived, missing)
        missing_ratings = sum(performance["rating"] is None for performance in performances)
        average = displayed_average = None
        if performances and not missing_ratings:
            average = sum(Decimal(str(performance["rating"])) for performance in performances) / len(performances)
            displayed_average = average.quantize(Decimal(1).scaleb(-rating_decimals), rounding=ROUND_DOWN)
        rating = compare_metric(snapshot["average_rating"], float(displayed_average) if displayed_average is not None else None, missing_ratings)
        rating.update(raw_match_average=float(average) if average is not None else None,
                      display_rule=f"Truncate the mean to {rating_decimals} decimal place(s); keep the unrounded mean separately.")
        if not performances and snapshot["appearances"] == 0 and snapshot["average_rating"] in (0, None):
            rating["result"] = "not_applicable"
        metrics["average_rating"] = rating
        for field, metric in metrics.items():
            metric_counts[field][metric["result"]] += 1
        states = {metric["result"] for metric in metrics.values()}
        comparison["result"] = ("mismatch" if "mismatch" in states else
                                "partial_comparison" if states & {"not_comparable", "not_captured"} else "match")
        comparison["metrics"] = metrics
        comparisons.append(comparison)
    season_totals = [comparison for comparison in comparisons if comparison["scope"] == "all_competitions"]
    return {
        "schema_version": SCHEMA_VERSION, "club": club, "season": season,
        "summary": {
            "snapshot_rows": len(comparisons), "players": len({comparison["player_id"] for comparison in comparisons}),
            "season_total_rows": len(season_totals),
            "mismatched_rows": sum(comparison["result"] == "mismatch" for comparison in comparisons),
            "partial_comparisons": sum(comparison["result"] == "partial_comparison" for comparison in comparisons),
            "unconfirmed_cutoffs": sum(comparison["result"] == "unconfirmed_cutoff" for comparison in comparisons),
            "metrics": {field: dict(counts) for field, counts in metric_counts.items()},
        },
        "comparisons": comparisons,
        "limitations": [
            "Snapshot totals are compared with, never added to, unique player-match records for the same club, season and competition scope.",
            "All-competition comparisons include preseason games belonging to that season.",
            "An undated in-season observation cannot be compared until its cutoff is confirmed.",
            "The one-decimal truncation rule matches the observed first-season display; the raw average remains visible and other editions may use different formatting.",
            "Missing goalkeeper scoring fields are not treated as zero. Unknown match values remain not comparable.",
            "Passes and blocks have no season-end counterpart; cards and outfield clean sheets are retained without inventing unobserved match events or participation times.",
        ],
    }
