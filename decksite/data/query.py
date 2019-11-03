from typing import Optional, Union

from shared.pd_exception import InvalidArgumentException


def person_query(table: str = 'p') -> str:
    return 'LOWER(IFNULL(IFNULL(IFNULL({table}.name, {table}.mtgo_username), {table}.mtggoldfish_username), {table}.tappedout_username))'.format(table=table)

def competition_ids_by_type_select(competition_type: str) -> str:
    return """
        SELECT
            id
        FROM
            competition
        WHERE
            competition_series_id IN
                (
                    SELECT
                        id
                    FROM
                        competition_series
                    WHERE
                        competition_type_id
                    IN ({competition_type_id})
                )
        """.format(competition_type_id=competition_type_id_select(competition_type))

def competition_type_id_select(competition_type: str) -> str:
    return """
        SELECT
            id
        FROM
            competition_type
        WHERE
            name = '{competition_type}'
    """.format(competition_type=competition_type)

def competition_join() -> str:
    return """
        LEFT JOIN
            competition AS c ON d.competition_id = c.id
        LEFT JOIN
            competition_series AS cs ON cs.id = c.competition_series_id
        LEFT JOIN
            competition_type AS ct ON ct.id = cs.competition_type_id
    """

def season_query(season_id: Optional[Union[str, int]], column_name: str = 'season_id') -> str:
    if season_id is None or season_id == 'all' or season_id == 0:
        return 'TRUE'
    try:
        return '{column_name} = {season_id}'.format(column_name=column_name, season_id=int(season_id))
    except ValueError:
        raise InvalidArgumentException('No season with id `{season_id}`'.format(season_id=season_id))

def season_join() -> str:
    return """
        LEFT JOIN
            (
                SELECT
                    `start`.id,
                    `start`.code,
                    `start`.start_date AS start_date,
                    `end`.start_date AS end_date
                FROM
                    season AS `start`
                LEFT JOIN
                    season AS `end` ON `end`.id = `start`.id + 1
            ) AS season ON season.start_date <= d.created_date AND (season.end_date IS NULL OR season.end_date > d.created_date)
    """

def decks_order_by(key: str) -> str:
    # This is not quite right because 5th place in tournaments with top 4 (no stars) get the same score as 5th place in tournaments with top 8 (1 star)
    # but we don't load tournament_top_n in load_decks, only in load_decks_heavy. See #6648.
    marginalia_order_by = """
        (CASE WHEN d.finish = 1 THEN 1
             WHEN d.finish = 2 THEN 2
             WHEN d.finish = 3 THEN 3
             WHEN cache.wins - 5 >= cache.losses THEN 4
             WHEN cache.wins - 3 >= cache.losses THEN 5
             WHEN d.finish = 5 THEN 6
             ELSE 99
         END)
    """
    sort_options = {
        'marginalia': marginalia_order_by,
        'colors': 'cache.color_sort',
        'name': 'cache.normalized_name',
        'person': person_query(),
        'archetype': 'a.name',
        'sourceName': 's.name',
        'record': '(cache.wins - cache.losses)',
        'omw': 'cache.omw IS NOT NULL DESC, cache.omw',
        'top8': 'd.finish IS NOT NULL DESC, d.finish',
        'date': 'cache.active_date',
        'season': 'cache.active_date'
    }
    return sort_options[key]

def exclude_active_league_runs() -> str:
    return """
        d.retired
        OR
        ct.name <> 'League'
        OR
        IFNULL(cache.wins, 0) + IFNULL(cache.draws, 0) + IFNULL(cache.losses, 0) >= 5
        OR
        c.end_date < UNIX_TIMESTAMP(NOW())
    """
