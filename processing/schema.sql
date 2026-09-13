CREATE TABLE source_images (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    sha256 TEXT NOT NULL UNIQUE CHECK (length(sha256) = 64),
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    width INTEGER CHECK (width > 0),
    height INTEGER CHECK (height > 0),
    screen_type TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'inventoried'
        CHECK (status IN ('inventoried', 'needs_review', 'imported', 'rejected', 'error')),
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE source_paths (
    path TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_images(id),
    sequence INTEGER,
    present INTEGER NOT NULL DEFAULT 1 CHECK (present IN (0, 1))
);
CREATE INDEX source_paths_sequence ON source_paths(sequence);

CREATE TABLE extractions (
    source_id TEXT PRIMARY KEY REFERENCES source_images(id),
    extractor_version TEXT NOT NULL,
    candidate_json TEXT NOT NULL CHECK (json_valid(candidate_json)),
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    issues_json TEXT NOT NULL CHECK (json_valid(issues_json)),
    extracted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reviews (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    source_id TEXT NOT NULL REFERENCES source_images(id),
    revision INTEGER NOT NULL CHECK (revision > 0),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_hash TEXT NOT NULL,
    legacy_payload_hash TEXT,
    note TEXT NOT NULL CHECK (length(trim(note)) > 0),
    reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_id, payload_hash),
    UNIQUE (source_id, revision)
);

CREATE TABLE players (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    nationality TEXT
);
CREATE TABLE player_aliases (
    alias TEXT PRIMARY KEY,
    player_id TEXT NOT NULL REFERENCES players(id)
);

CREATE TABLE clubs (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    name TEXT NOT NULL UNIQUE CHECK (length(trim(name)) > 0)
);
CREATE TABLE club_aliases (
    alias TEXT PRIMARY KEY,
    club_id TEXT NOT NULL REFERENCES clubs(id)
);

CREATE TABLE seasons (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    label TEXT NOT NULL UNIQUE
);
CREATE TABLE competitions (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('league', 'cup', 'friendly')),
    is_preseason INTEGER NOT NULL CHECK (is_preseason IN (0, 1))
);
CREATE TABLE competition_seasons (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    competition_id TEXT NOT NULL REFERENCES competitions(id),
    season_id TEXT NOT NULL REFERENCES seasons(id),
    UNIQUE (competition_id, season_id)
);

CREATE TABLE matches (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    competition_season_id TEXT NOT NULL REFERENCES competition_seasons(id),
    played_on TEXT NOT NULL,
    home_club_id TEXT NOT NULL REFERENCES clubs(id),
    away_club_id TEXT NOT NULL REFERENCES clubs(id),
    venue TEXT,
    round TEXT,
    home_goals INTEGER CHECK (home_goals >= 0),
    away_goals INTEGER CHECK (away_goals >= 0),
    home_penalties INTEGER CHECK (home_penalties >= 0),
    away_penalties INTEGER CHECK (away_penalties >= 0),
    extra_time INTEGER CHECK (extra_time IN (0, 1)),
    duration_minutes INTEGER CHECK (duration_minutes > 0),
    CHECK (home_club_id != away_club_id),
    CHECK ((home_goals IS NULL) = (away_goals IS NULL)),
    CHECK ((home_penalties IS NULL) = (away_penalties IS NULL)),
    CHECK (home_penalties IS NULL OR
        (home_goals IS NOT NULL AND home_goals = away_goals AND home_penalties != away_penalties)),
    UNIQUE (competition_season_id, played_on, home_club_id, away_club_id)
);
CREATE TABLE match_sources (
    match_id TEXT NOT NULL REFERENCES matches(id),
    source_id TEXT NOT NULL REFERENCES source_images(id),
    PRIMARY KEY (match_id, source_id)
);

CREATE TABLE team_matches (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    match_id TEXT NOT NULL REFERENCES matches(id),
    club_id TEXT NOT NULL REFERENCES clubs(id),
    shots INTEGER CHECK (shots >= 0),
    shots_on_target INTEGER CHECK (shots_on_target >= 0),
    possession_pct REAL CHECK (possession_pct BETWEEN 0 AND 100),
    tackles INTEGER CHECK (tackles >= 0),
    fouls INTEGER CHECK (fouls >= 0),
    corners INTEGER CHECK (corners >= 0),
    shot_accuracy_pct REAL CHECK (shot_accuracy_pct BETWEEN 0 AND 100),
    pass_accuracy_pct REAL CHECK (pass_accuracy_pct BETWEEN 0 AND 100),
    CHECK (shots_on_target IS NULL OR shots IS NULL OR shots_on_target <= shots),
    UNIQUE (match_id, club_id)
);

CREATE TABLE player_matches (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    match_id TEXT NOT NULL REFERENCES matches(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    club_id TEXT NOT NULL REFERENCES clubs(id),
    displayed_position TEXT,
    played_position TEXT,
    overall INTEGER CHECK (overall BETWEEN 1 AND 99),
    rating REAL CHECK (rating BETWEEN 0 AND 10),
    started INTEGER CHECK (started IN (0, 1)),
    minutes_played INTEGER CHECK (minutes_played >= 0),
    goals INTEGER CHECK (goals >= 0),
    assists INTEGER CHECK (assists >= 0),
    shots_on_target INTEGER CHECK (shots_on_target >= 0),
    shots_off_target INTEGER CHECK (shots_off_target >= 0),
    passes_completed_short INTEGER CHECK (passes_completed_short >= 0),
    passes_completed_medium INTEGER CHECK (passes_completed_medium >= 0),
    passes_completed_long INTEGER CHECK (passes_completed_long >= 0),
    passes_failed_short INTEGER CHECK (passes_failed_short >= 0),
    passes_failed_medium INTEGER CHECK (passes_failed_medium >= 0),
    passes_failed_long INTEGER CHECK (passes_failed_long >= 0),
    key_passes INTEGER CHECK (key_passes >= 0),
    crosses_successful INTEGER CHECK (crosses_successful >= 0),
    crosses_failed INTEGER CHECK (crosses_failed >= 0),
    tackles_won INTEGER CHECK (tackles_won >= 0),
    tackles_lost INTEGER CHECK (tackles_lost >= 0),
    fouls INTEGER CHECK (fouls >= 0),
    penalties_conceded INTEGER CHECK (penalties_conceded >= 0),
    interceptions INTEGER CHECK (interceptions >= 0),
    blocks INTEGER CHECK (blocks >= 0),
    out_of_position INTEGER CHECK (out_of_position >= 0),
    possession_won INTEGER CHECK (possession_won >= 0),
    possession_lost INTEGER CHECK (possession_lost >= 0),
    clearances INTEGER CHECK (clearances >= 0),
    headers_won INTEGER CHECK (headers_won >= 0),
    headers_lost INTEGER CHECK (headers_lost >= 0),
    key_dribbles INTEGER CHECK (key_dribbles >= 0),
    fouled INTEGER CHECK (fouled >= 0),
    successful_dribbles INTEGER CHECK (successful_dribbles >= 0),
    goals_conceded INTEGER CHECK (goals_conceded >= 0),
    goals_conceded_displayed INTEGER CHECK (goals_conceded_displayed >= 0),
    goals_conceded_basis TEXT,
    shots_caught INTEGER CHECK (shots_caught >= 0),
    shots_parried INTEGER CHECK (shots_parried >= 0),
    crosses_caught INTEGER CHECK (crosses_caught >= 0),
    balls_stripped INTEGER CHECK (balls_stripped >= 0),
    pass_accuracy_pct REAL CHECK (pass_accuracy_pct BETWEEN 0 AND 100),
    shot_accuracy_pct REAL CHECK (shot_accuracy_pct BETWEEN 0 AND 100),
    tackle_accuracy_pct REAL CHECK (tackle_accuracy_pct BETWEEN 0 AND 100),
    UNIQUE (match_id, player_id)
);
CREATE TABLE player_match_sources (
    player_match_id TEXT NOT NULL REFERENCES player_matches(id),
    source_id TEXT NOT NULL REFERENCES source_images(id),
    PRIMARY KEY (player_match_id, source_id)
);

CREATE TABLE player_snapshots (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    player_id TEXT NOT NULL REFERENCES players(id),
    season_id TEXT NOT NULL REFERENCES seasons(id),
    club_id TEXT REFERENCES clubs(id),
    source_id TEXT NOT NULL REFERENCES source_images(id),
    match_id TEXT REFERENCES matches(id),
    snapshot_kind TEXT NOT NULL CHECK (snapshot_kind IN
        ('season_start', 'season_end', 'in_season', 'first_observed', 'arrival')),
    observed_on TEXT,
    date_from TEXT,
    date_to TEXT,
    date_precision TEXT NOT NULL CHECK (date_precision IN ('day', 'range', 'season', 'unknown')),
    date_basis TEXT NOT NULL CHECK (length(trim(date_basis)) > 0),
    overall INTEGER CHECK (overall BETWEEN 1 AND 99),
    age INTEGER CHECK (age BETWEEN 1 AND 99),
    displayed_position TEXT,
    squad_role TEXT,
    CHECK ((date_precision = 'day' AND observed_on IS NOT NULL) OR
        (date_precision != 'day' AND observed_on IS NULL)),
    CHECK (date_precision != 'range' OR
        (date_from IS NOT NULL AND date_to IS NOT NULL AND date_from <= date_to)),
    UNIQUE (player_id, season_id, source_id, snapshot_kind)
);

CREATE TABLE player_competition_snapshots (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    player_id TEXT NOT NULL REFERENCES players(id),
    club_id TEXT NOT NULL REFERENCES clubs(id),
    season_id TEXT NOT NULL REFERENCES seasons(id),
    competition_season_id TEXT REFERENCES competition_seasons(id),
    source_id TEXT NOT NULL REFERENCES source_images(id),
    observed_on TEXT,
    snapshot_kind TEXT NOT NULL DEFAULT 'in_season' CHECK (snapshot_kind IN ('in_season', 'season_end')),
    date_basis TEXT NOT NULL DEFAULT 'Observation cutoff not yet confirmed',
    scope TEXT NOT NULL CHECK (scope IN ('competition', 'all_competitions')),
    appearances INTEGER CHECK (appearances >= 0),
    goals INTEGER CHECK (goals >= 0),
    assists INTEGER CHECK (assists >= 0),
    clean_sheets INTEGER CHECK (clean_sheets >= 0),
    yellow_cards INTEGER CHECK (yellow_cards >= 0),
    red_cards INTEGER CHECK (red_cards >= 0),
    average_rating REAL CHECK (average_rating BETWEEN 0 AND 10),
    CHECK ((scope = 'competition') = (competition_season_id IS NOT NULL))
);

CREATE TABLE player_transfers (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    player_id TEXT NOT NULL REFERENCES players(id),
    from_club_id TEXT REFERENCES clubs(id),
    to_club_id TEXT REFERENCES clubs(id),
    source_id TEXT NOT NULL REFERENCES source_images(id),
    transfer_type TEXT NOT NULL CHECK (transfer_type IN ('permanent', 'loan', 'loan_return')),
    effective_on TEXT,
    date_basis TEXT NOT NULL,
    fee_minor INTEGER CHECK (fee_minor >= 0),
    weekly_wage_minor INTEGER CHECK (weekly_wage_minor >= 0),
    currency TEXT,
    currency_display TEXT,
    contract_months INTEGER CHECK (contract_months > 0),
    loan_months INTEGER CHECK (loan_months > 0),
    CHECK (from_club_id IS NOT NULL OR to_club_id IS NOT NULL),
    CHECK (from_club_id IS NULL OR to_club_id IS NULL OR from_club_id != to_club_id)
);

CREATE TABLE competition_events (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(id) = 36),
    competition_season_id TEXT REFERENCES competition_seasons(id),
    source_id TEXT NOT NULL REFERENCES source_images(id),
    event_type TEXT NOT NULL,
    player_id TEXT REFERENCES players(id),
    club_id TEXT REFERENCES clubs(id),
    announced_on TEXT,
    period TEXT,
    description TEXT NOT NULL,
    CHECK (
        (event_type = 'player_of_the_year' AND competition_season_id IS NULL
            AND player_id IS NOT NULL AND period IS NOT NULL AND period GLOB '20[0-9][0-9]')
        OR (event_type != 'player_of_the_year' AND competition_season_id IS NOT NULL)
    )
);

CREATE TABLE legacy_ids (
    entity_table TEXT NOT NULL,
    old_value TEXT NOT NULL,
    uuid TEXT NOT NULL CHECK (length(uuid) = 36),
    PRIMARY KEY (entity_table, old_value),
    UNIQUE (entity_table, uuid)
);

CREATE TRIGGER player_match_club_insert BEFORE INSERT ON player_matches
WHEN NOT EXISTS (SELECT 1 FROM matches WHERE id = NEW.match_id
    AND NEW.club_id IN (home_club_id, away_club_id))
BEGIN SELECT RAISE(ABORT, 'Player club must participate in the match'); END;
CREATE TRIGGER player_match_club_update BEFORE UPDATE ON player_matches
WHEN NOT EXISTS (SELECT 1 FROM matches WHERE id = NEW.match_id
    AND NEW.club_id IN (home_club_id, away_club_id))
BEGIN SELECT RAISE(ABORT, 'Player club must participate in the match'); END;
CREATE TRIGGER team_match_club_insert BEFORE INSERT ON team_matches
WHEN NOT EXISTS (SELECT 1 FROM matches WHERE id = NEW.match_id
    AND NEW.club_id IN (home_club_id, away_club_id))
BEGIN SELECT RAISE(ABORT, 'Team must participate in the match'); END;
CREATE TRIGGER team_match_club_update BEFORE UPDATE ON team_matches
WHEN NOT EXISTS (SELECT 1 FROM matches WHERE id = NEW.match_id
    AND NEW.club_id IN (home_club_id, away_club_id))
BEGIN SELECT RAISE(ABORT, 'Team must participate in the match'); END;
