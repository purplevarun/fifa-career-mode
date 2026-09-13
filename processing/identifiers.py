from uuid import UUID, uuid4


REFERENCE_TABLES = {
    "source_id": "source_images",
    "match_source_id": "source_images",
    "match_id": "matches",
    "player_id": "players",
    "club_id": "clubs",
    "home_club_id": "clubs",
    "away_club_id": "clubs",
    "from_club_id": "clubs",
    "to_club_id": "clubs",
    "season_id": "seasons",
    "competition_id": "competitions",
    "competition_season_id": "competition_seasons",
    "player_match_id": "player_matches",
}


def new_id():
    return str(uuid4())


def is_uuid(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = UUID(value)
    except ValueError:
        return False
    return str(parsed) == value and parsed.int != 0


def resolve_id(connection, table, value, allow_legacy=False):
    if value is None or is_uuid(value):
        return value
    if allow_legacy and isinstance(value, (int, str)) and not isinstance(value, bool):
        mapped = connection.execute(
            "SELECT uuid FROM legacy_ids WHERE entity_table = ? AND old_value = ?",
            (table, str(value)),
        ).fetchone()
        if mapped:
            return mapped[0]
    raise ValueError(f"{table} identifier must be a canonical UUID: {value!r}")


def normalize_references(connection, value, allow_legacy=False):
    if isinstance(value, list):
        return [normalize_references(connection, item, allow_legacy) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for field, item in value.items():
        if field in REFERENCE_TABLES:
            result[field] = resolve_id(
                connection, REFERENCE_TABLES[field], item, allow_legacy
            )
        else:
            result[field] = normalize_references(connection, item, allow_legacy)
    return result
