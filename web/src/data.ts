export type Row = Record<string, unknown>;
export interface Entity extends Row {
  id: string;
}
export interface Player extends Entity {
  name: string;
  nationality: string | null;
}
export interface Club extends Entity {
  name: string;
}
export interface Season extends Entity {
  label: string;
}
export interface Competition extends Entity {
  name: string;
  kind: string;
  is_preseason: boolean;
}
export interface Edition extends Entity {
  competition_id: string;
  season_id: string;
}
export interface Fixture extends Entity {
  competition_season_id: string;
  played_on: string;
  home_club_id: string;
  away_club_id: string;
  home_goals: number | null;
  away_goals: number | null;
  home_penalties: number | null;
  away_penalties: number | null;
  venue: string | null;
  duration_minutes: number | null;
  extra_time: boolean | null;
  round: string | null;
}
export interface Performance extends Entity {
  player_id: string;
  club_id: string;
  match_id: string;
  rating: number | null;
  overall: number | null;
  displayed_position: string | null;
  goals: number | null;
  assists: number | null;
  minutes_played: number | null;
  goals_conceded: number | null;
  goals_conceded_displayed: number | null;
}
export interface Snapshot extends Entity {
  player_id: string;
  club_id: string | null;
  season_id: string;
  source_id: string;
  match_id: string | null;
  overall: number | null;
  displayed_position: string | null;
  snapshot_kind: string;
  observed_on: string | null;
  date_precision: string;
  date_basis: string;
}
export interface Source extends Entity {
  path: string;
  sha256: string;
  screen_type: string;
  status: string;
  available: boolean;
}
export interface MetricComparison {
  observed: number | null;
  derived: number | null;
  result: string;
  difference: number | null;
  missing_match_values: number;
  raw_match_average?: number | null;
  display_rule?: string;
}
export interface Comparison extends Row {
  snapshot_id: string;
  player_id: string;
  player: string;
  season: string;
  competition: string | null;
  scope: string;
  source_id: string;
  result: string;
  metrics: Record<string, MetricComparison>;
}
export interface Dataset {
  schema_version: number;
  generated_at: string;
  players: Player[];
  clubs: Club[];
  seasons: Season[];
  competitions: Competition[];
  competition_seasons: Edition[];
  matches: Fixture[];
  team_matches: Entity[];
  player_matches: Performance[];
  player_snapshots: Snapshot[];
  player_competition_snapshots: Entity[];
  player_transfers: Entity[];
  competition_events: Entity[];
  match_sources: { match_id: string; source_id: string }[];
  player_match_sources: { player_match_id: string; source_id: string }[];
  source_images: Source[];
  coverage: {
    source_states: Record<string, number>;
    records: Record<string, number>;
  };
  match_coverage: {
    summary: Row;
    warnings: Row[];
    player_field_availability: Row;
    sources: Row;
  };
  season_reconciliation: {
    summary: Row;
    comparisons: Comparison[];
    limitations: string[];
  };
}
export interface Match extends Fixture {
  home: string;
  away: string;
  competition: Competition;
  season: Season;
  isHome: boolean;
  opponent: string;
  goalsFor: number | null;
  goalsAgainst: number | null;
  result: "W" | "D" | "L" | null;
  shootout: "W" | "L" | null;
}
export interface Model {
  data: Dataset;
  nottsId: string;
  players: Map<string, Player>;
  clubs: Map<string, Club>;
  competitions: Map<string, Competition>;
  seasons: Map<string, Season>;
  editions: Map<string, Edition>;
  sources: Map<string, Source>;
  matches: Match[];
  matchById: Map<string, Match>;
}
export interface Filters {
  season: string;
  competition: string;
  preseason: boolean;
}
export const defaultFilters: Filters = {
  season: "all",
  competition: "all",
  preseason: true,
};
const index = <Value extends Entity>(values: Value[]) =>
  new Map(values.map((value) => [value.id, value]));

export function createModel(input: unknown): Model {
  if (!input || typeof input !== "object")
    throw new Error("The career export is not valid JSON data.");
  const data = input as Dataset;
  const tables = [
    "players",
    "clubs",
    "seasons",
    "competitions",
    "competition_seasons",
    "matches",
    "team_matches",
    "player_matches",
    "player_snapshots",
    "player_competition_snapshots",
    "player_transfers",
    "competition_events",
    "match_sources",
    "player_match_sources",
    "source_images",
  ] as const;
  if (
    data.schema_version !== 3 ||
    tables.some((table) => !Array.isArray(data[table]))
  )
    throw new Error(
      "This app needs a schema-version 3 career export. Run npm run sync-data.",
    );
  const notts = data.clubs.find((club) => club.name === "Notts County");
  if (!notts)
    throw new Error("Notts County is missing from the career export.");
  const clubs = index(data.clubs),
    players = index(data.players),
    competitions = index(data.competitions);
  const seasons = index(data.seasons),
    editions = index(data.competition_seasons),
    sources = index(data.source_images);
  const matches: Match[] = data.matches
    .map((fixture): Match => {
      const edition = editions.get(fixture.competition_season_id);
      const competition = edition && competitions.get(edition.competition_id);
      const season = edition && seasons.get(edition.season_id);
      const home = clubs.get(fixture.home_club_id)?.name,
        away = clubs.get(fixture.away_club_id)?.name;
      if (!competition || !season || !home || !away)
        throw new Error(`Broken fixture relationship: ${fixture.id}`);
      const isHome = fixture.home_club_id === notts.id;
      const goalsFor = isHome ? fixture.home_goals : fixture.away_goals;
      const goalsAgainst = isHome ? fixture.away_goals : fixture.home_goals;
      const penaltiesFor = isHome
        ? fixture.home_penalties
        : fixture.away_penalties;
      const penaltiesAgainst = isHome
        ? fixture.away_penalties
        : fixture.home_penalties;
      return {
        ...fixture,
        home,
        away,
        competition,
        season,
        isHome,
        opponent: isHome ? away : home,
        goalsFor,
        goalsAgainst,
        result:
          goalsFor === null || goalsAgainst === null
            ? null
            : goalsFor > goalsAgainst
              ? "W"
              : goalsFor < goalsAgainst
                ? "L"
                : "D",
        shootout:
          penaltiesFor === null || penaltiesAgainst === null
            ? null
            : penaltiesFor > penaltiesAgainst
              ? "W"
              : "L",
      };
    })
    .sort(
      (left, right) =>
        left.played_on.localeCompare(right.played_on) ||
        left.id.localeCompare(right.id),
    );
  return {
    data,
    nottsId: notts.id,
    clubs,
    players,
    competitions,
    seasons,
    editions,
    sources,
    matches,
    matchById: index(matches),
  };
}

export function selectMatches(model: Model, filters: Filters): Match[] {
  return model.matches.filter(
    (match) =>
      (filters.season === "all" || match.season.id === filters.season) &&
      (filters.competition === "all" ||
        match.competition.id === filters.competition) &&
      (filters.preseason || !match.competition.is_preseason),
  );
}
export function selectPerformances(
  model: Model,
  matches: Match[],
  clubId: string | null = model.nottsId,
): Performance[] {
  const ids = new Set(matches.map((match) => match.id));
  return model.data.player_matches.filter(
    (row) =>
      ids.has(row.match_id) && (clubId === null || row.club_id === clubId),
  );
}
export function metric(rows: Row[], field: string) {
  const values = rows
    .map((row) => row[field])
    .filter(
      (value): value is number =>
        typeof value === "number" && Number.isFinite(value),
    );
  return {
    value: values.length
      ? values.reduce((total, value) => total + value, 0)
      : null,
    known: values.length,
    total: rows.length,
  };
}
export function average(rows: Row[], field: string) {
  const result = metric(rows, field);
  return result.value === null ? null : result.value / result.known;
}
export function summarize(matches: Match[]) {
  const wins = matches.filter((match) => match.result === "W").length;
  const draws = matches.filter((match) => match.result === "D").length;
  const losses = matches.filter((match) => match.result === "L").length;
  return {
    played: matches.length,
    wins,
    draws,
    losses,
    goalsFor: metric(matches, "goalsFor"),
    goalsAgainst: metric(matches, "goalsAgainst"),
    cleanSheets: matches.filter((match) => match.goalsAgainst === 0).length,
    winRate:
      wins + draws + losses ? (wins / (wins + draws + losses)) * 100 : null,
    leaguePoints: matches
      .filter((match) => match.competition.kind === "league")
      .reduce(
        (total, match) =>
          total + (match.result === "W" ? 3 : match.result === "D" ? 1 : 0),
        0,
      ),
  };
}
export function snapshotOrder(snapshot: Snapshot, model: Model) {
  if (snapshot.observed_on) return snapshot.observed_on;
  const season = model.seasons.get(snapshot.season_id)?.label ?? "0000/00";
  return snapshot.snapshot_kind === "season_end"
    ? `${Number(season.slice(0, 4)) + 1}-06-30`
    : `${season.slice(0, 4)}-07-01`;
}
export function playerSummary(
  model: Model,
  player: Player,
  matches: Match[],
  clubId: string | null = model.nottsId,
) {
  const rows = selectPerformances(model, matches, clubId).filter(
    (row) => row.player_id === player.id,
  );
  const seasons = new Set(matches.map((match) => match.season.id));
  const snapshots = model.data.player_snapshots
    .filter((row) => row.player_id === player.id && seasons.has(row.season_id))
    .sort((left, right) =>
      snapshotOrder(left, model).localeCompare(snapshotOrder(right, model)),
    );
  const last = snapshots.at(-1);
  return {
    ...player,
    rows,
    appearances: rows.length,
    goals: metric(rows, "goals"),
    assists: metric(rows, "assists"),
    rating: average(rows, "rating"),
    overall: last?.overall ?? rows.at(-1)?.overall ?? null,
    position:
      last?.displayed_position ?? rows.at(-1)?.displayed_position ?? null,
    snapshots,
  };
}
export function sourceUrl(sourceId: string) {
  return `${import.meta.env.BASE_URL}evidence/${encodeURIComponent(sourceId)}.webp`;
}
export function referenceLabel(
  model: Model,
  field: string,
  value: unknown,
): string {
  if (typeof value !== "string") return display(value);
  if (field === "player_id") return model.players.get(value)?.name ?? value;
  if (field.endsWith("club_id")) return model.clubs.get(value)?.name ?? value;
  if (field === "season_id") return model.seasons.get(value)?.label ?? value;
  if (field === "competition_id")
    return model.competitions.get(value)?.name ?? value;
  if (field === "competition_season_id") {
    const edition = model.editions.get(value);
    return edition
      ? `${model.competitions.get(edition.competition_id)?.name} ${model.seasons.get(edition.season_id)?.label}`
      : value;
  }
  if (field === "match_id") {
    const match = model.matchById.get(value);
    return match
      ? `${match.played_on} ${match.home} ${match.home_goals ?? "-"}-${match.away_goals ?? "-"} ${match.away}`
      : value;
  }
  if (field === "source_id")
    return model.sources.get(value)?.path.split("/").at(-1) ?? value;
  return value;
}
export function display(value: unknown, digits = 0): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number")
    return value.toLocaleString("en-GB", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
export function dateLabel(value: string | null, short = false) {
  if (!value) return "Date not recorded";
  return new Date(`${value}T12:00:00`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: short ? "short" : "long",
    ...(short ? {} : { year: "numeric" }),
  });
}
export function label(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase())
    .replace(/\bPct\b/g, "%")
    .replace(/\bId\b/g, "ID");
}
export function downloadJson(value: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const performanceGroups: Record<string, string[]> = {
  "Match record": [
    "rating",
    "overall",
    "displayed_position",
    "played_position",
    "started",
    "minutes_played",
  ],
  Attacking: [
    "goals",
    "assists",
    "shots_on_target",
    "shots_off_target",
    "shot_accuracy_pct",
    "key_passes",
  ],
  Passing: [
    "passes_completed_short",
    "passes_completed_medium",
    "passes_completed_long",
    "passes_failed_short",
    "passes_failed_medium",
    "passes_failed_long",
    "crosses_successful",
    "crosses_failed",
    "pass_accuracy_pct",
  ],
  Defending: [
    "tackles_won",
    "tackles_lost",
    "tackle_accuracy_pct",
    "fouls",
    "penalties_conceded",
    "interceptions",
    "blocks",
    "out_of_position",
    "clearances",
    "headers_won",
    "headers_lost",
  ],
  "Possession & movement": [
    "possession_won",
    "possession_lost",
    "key_dribbles",
    "fouled",
    "successful_dribbles",
  ],
  Goalkeeping: [
    "goals_conceded",
    "goals_conceded_displayed",
    "goals_conceded_basis",
    "shots_caught",
    "shots_parried",
    "crosses_caught",
    "balls_stripped",
  ],
};
