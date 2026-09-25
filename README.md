# choosing

Sports betting application built on existing sports-data and odds integrations.

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

The application uses the existing SportsDataIO-style and Odds API-style integrations to produce:

- player watchlists
- game betting opportunities
- edge-based stake suggestions
- bankroll-aware portfolio summaries

## Existing API utilities

The repository still includes the underlying HTTP prediction utilities:

- `GET /player/{id}/prediction` supports player ids or player names, plus optional `team=...`, and includes predicted points
  and a computed `player_profile`
  with injury status and computation/source details
- `GET /game/{id}/edge` supports game ids or team names
- `GET /lookup/players?query={name}`
- `GET /lookup/teams?query={team}`
- `GET /` for the responsive UI
- `GET /app.json` for machine-readable app metadata
- `GET /health`

## Live API configuration

Set these environment variables to fetch live upstream data before prediction and edge computation:

- `SPORTSDATAIO_API_KEY`
- `ODDS_API_KEY`

Optional live-data configuration:

- `SPORTSDATAIO_BASE_URL` (defaults to `https://api.sportsdata.io/v3/nba`)
- `SPORTSDATAIO_SEASON` (defaults to `2024`)
- `ODDS_API_BASE_URL` (defaults to `https://api.the-odds-api.com/v4`)
- `ODDS_API_SPORT` (defaults to `basketball_nba`)

Behavior:

- when keys are configured, the app attempts live SportsDataIO and Odds API requests first
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