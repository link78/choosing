PLAYER_SPORT = {
    "name": "Basketball",
    "league": "NBA",
    "odds_api_key": "basketball_nba",
}


ODDS_API_ENDPOINTS = [
    {"name": "Sports list", "path": "/sports"},
    {"name": "Current odds", "path": "/sports/{sport}/odds"},
    {"name": "Event list", "path": "/sports/{sport}/events"},
    {"name": "Event odds", "path": "/sports/{sport}/events/{eventId}/odds"},
    {"name": "Scores", "path": "/sports/{sport}/scores"},
    {"name": "Historical odds", "path": "/historical/sports/{sport}/odds"},
]


ODDS_API_SPORTS = [
    {"name": "NFL", "key": "americanfootball_nfl"},
    {"name": "MLB", "key": "baseball_mlb"},
    {"name": "NBA", "key": "basketball_nba"},
    {"name": "NHL", "key": "icehockey_nhl"},
    {"name": "College Football", "key": "americanfootball_ncaaf"},
    {"name": "College Basketball", "key": "basketball_ncaab"},
    {"name": "PGA / Golf", "key": "golf_pga"},
    {"name": "NASCAR", "key": "motorsports_nascar"},
    {"name": "Soccer", "key": "soccer_*"},
    {"name": "UFC / MMA", "key": "mma_mixed_martial_arts"},
    {"name": "Tennis", "key": "tennis_*"},
    {"name": "Olympics", "key": "olympics_*"},
]
