# choosing

Sports betting application built on sports data, media and broadcast context, fantasy projections, and betting odds integrations.

## Application

Open the mobile-friendly web app at the root path:

```bash
python -m choosing.api
# then visit http://127.0.0.1:8000/
```

Run the application:

```bash
python -m choosing --players "Stephen Curry,Nikola Jokic" --games "Golden State Warriors,Denver Nuggets" --bankroll 1000
```

Print the report as JSON:

```bash
python -m choosing --json
```

The application uses these upstream categories to produce stronger predictions:

- SportsDataIO
- Media & Broadcast
- Fantasy Sports API
- The Odds API

Together they power:

- player watchlists
- game betting opportunities
- edge-based stake suggestions
- bankroll-aware portfolio summaries

## Existing API utilities

The repository still includes the underlying HTTP prediction utilities:

- `GET /player/{id}/prediction` supports player ids or player names, plus optional `team=...`, and includes predicted points
  and a computed `player_profile`
  with team, sport, injury status, explicit injured yes/no fields, sport-aware betting suggestions, computation/source details, and embedded The Odds API endpoint and sport coverage data
  (`sport=...` can be any supported Odds API sport key such as `basketball_nba` or `americanfootball_nfl`)
- `GET /players/top?sport={sport_key}&limit=10` summarizes the top predicted players for a selected sport and includes each player's leading suggestion
- `GET /game/{id}/edge` supports game ids or team names
- `GET /lookup/players?query={name}`
- `GET /lookup/teams?query={team}`
- `GET /` for the responsive UI
- `GET /app.json` for machine-readable app metadata
- `GET /health`

The home dashboard and `/app.json` also display the tracked The Odds API endpoint catalog:

- `/sports`
- `/sports/{sport}/odds`
- `/sports/{sport}/events`
- `/sports/{sport}/events/{eventId}/odds`
- `/sports/{sport}/scores`
- `/historical/sports/{sport}/odds`

The displayed The Odds API sport coverage includes:

- NFL
- MLB
- NBA
- NHL
- College Football
- College Basketball
- PGA / Golf
- NASCAR
- Soccer
- UFC / MMA
- Tennis
- Olympics

The dashboard also includes a "Top players by sport" section that ranks up to 10 players by predicted performance for the selected sport, surfaces a leading suggestion for each player, and lets you click a player to load the full player prediction view.

## Live API configuration

Set these environment variables to fetch live upstream data before prediction and edge computation:

- `SPORTSDATAIO_API_KEY`
- `MEDIA_BROADCAST_API_KEY`
- `FANTASY_SPORTS_API_KEY`
- `ODDS_API_KEY`

`MEDIA_BROADCAST_API_KEY` and `FANTASY_SPORTS_API_KEY` can reuse the same SportsData key. If they are unset, the app falls back to `SPORTSDATAIO_API_KEY`.

Optional live-data configuration:

- `SPORTSDATAIO_BASE_URL` (defaults to `https://api.sportsdata.io/v3/nba`)
- `SPORTSDATAIO_SEASON` (defaults to `2024`)
- `MEDIA_BROADCAST_BASE_URL` (defaults to `SPORTSDATAIO_BASE_URL`)
- `FANTASY_SPORTS_BASE_URL` (defaults to `SPORTSDATAIO_BASE_URL`)
- `ODDS_API_BASE_URL` (defaults to `https://api.the-odds-api.com/v4`)
- `ODDS_API_SPORT` (defaults to `basketball_nba`)

Behavior:

- when keys are configured, the app attempts live SportsDataIO, Media & Broadcast, Fantasy Sports API, and Odds API requests first
- Media & Broadcast and Fantasy Sports API derive their live signals from the same SportsData-style upstream when pointed at the same base URL/key
- if a live request fails or returns unusable data, the app safely falls back to the existing deterministic local model inputs
- `/health` reports whether each upstream source is configured, whether its most recent upstream call succeeded, and the last error message when a provider fails

## Run

```bash
python -m choosing.api
```

The API server now honors deployment environment variables:

- `HOST` defaults to `0.0.0.0`
- `PORT` defaults to `8000`

## Deploy online

Container deployment:

```bash
docker build -t choosing /home/runner/work/choosing/choosing
docker run -p 8000:8000 -e PORT=8000 choosing
```

Procfile-based deployment:

- `/home/runner/work/choosing/choosing/Procfile` starts the web process with `python -m choosing.api`
- platforms that inject `PORT` can run the app without code changes

Railpack / Railway compatibility:

- `/home/runner/work/choosing/choosing/start.sh` provides the startup script Railpack looks for
- `/home/runner/work/choosing/choosing/requirements.txt` marks the repository as a Python app even though it uses only the standard library

## Test

```bash
python -m unittest discover -s tests
```