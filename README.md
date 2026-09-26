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
  with team, sport, injury status, explicit injured yes/no fields, sport-aware betting suggestions, sport-specific model weighting, historical form windows, confidence/range outputs, computation/source details, and embedded The Odds API endpoint and sport coverage data
  (`sport=...` can be any supported Odds API sport key such as `basketball_nba` or `americanfootball_nfl`)
- `GET /players/top?sport={sport_key}&limit=10` summarizes the top predicted players for a selected sport and includes each player's leading suggestion
  (when `SPORTSDATAIO_API_KEY` is configured, NFL top-player candidates are pulled from the live SportsDataIO player and season-stat feeds before falling back to local samples)
- `GET /game/{id}/edge` supports game ids or team names
- `GET /backtest/summary.json` returns measured ROI, hit rate, Brier score, calibration bins, player error metrics, recent outcomes, and learned-model status
- `POST /predictions/{prediction_id}/outcome` records actual outcomes for stored player/game predictions so backtesting can grade them over time
  (optionally with `closing_odds` to track closing line value)
- `POST /backtest/grade?date=YYYY-MM-DD` automatically grades pending predictions from The Odds API `/scores`, SportsDataIO `ScoresByDate`, and SportsDataIO `PlayerGameStatsByDate`, and fetches closing lines from `/historical/sports/{sport}/odds` for CLV
- `GET /backtest/timeseries?window=7d|30d|90d|all&sport=...&rolling=20` returns the cumulative profit (bankroll) curve, drawdown, rolling hit rate, rolling Brier score, and rolling log-loss
- `GET /backtest/breakdown?by=sport|market|confidence_band|edge_bucket|model_version` shows where the model wins or loses money
- `GET /predictions.csv` downloads the stored prediction history
- `GET /slate?sport=...&min_edge=...&min_confidence=...&limit=10` ranks today's games (from The Odds API `/events`, or local teams in fallback mode) by best edge
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

Each of these paths is also served by this app (e.g. `GET /sports/basketball_nba/odds`). With `ODDS_API_KEY` set the
request is proxied to The Odds API (supported query params such as `regions`, `markets`, `oddsFormat`, `bookmakers`,
`eventIds`, `daysFrom`, and `date` are forwarded); otherwise, or if the upstream call fails, deterministic local
fallback data is returned. Responses wrap the upstream payload as `{"provider", "endpoint", "path", "sport",
"source_mode", "params", "data"}`. Historical odds default `date` to 24 hours ago when omitted.

The displayed The Odds API sport coverage includes:

- NFL
- MLB
- NBA
- College Basketball
- Tennis

The dashboard also includes a "Top players by sport" section that ranks up to 10 players by predicted performance for the selected sport, surfaces a leading suggestion for each player, and lets you click a player to load the full player prediction view.

Recent computation upgrades now include:

- sport-specific player and game model weighting
- rolling player form windows (`recent_form_l3`, `recent_form_l5`, `recent_form_l10`)
- rest, usage trend, lineup support, and teammate-absence context
- confidence bands and low/mid/high ranges for player and team projections
- market quality inputs such as book disagreement, consensus spread, and market stability
- feature-tracking and heuristic calibration metadata to explain what is helping or hurting a projection

Persistent backtesting and learning now include:

- automatic storage of generated player and game predictions
- persistent outcome recording for later grading
- measured backtesting metrics such as ROI, hit rate, and Brier score
- calibration bins based on resolved game outcomes
- lightweight learned-model adaptation that updates sport profiles from recorded results
- a dashboard section for backtesting performance and model-learning status

Performance tracking and modelling now also include:

- pending/graded counts, a "Grade now" button, log-loss, max drawdown, and closing line value (average CLV, beat-the-close rate, by sport and market) in `/backtest/summary.json`
- inline SVG charts on the dashboard (bankroll curve, rolling hit rate/Brier, calibration plot, breakdown bars) with no JavaScript dependencies
- Platt-scaled win probabilities once at least 30 game outcomes are graded, and ridge-fitted per-sport weights once at least 8 samples exist
- fractional Kelly stake sizing (25% Kelly capped at 1%/2%/3% of bankroll for Low/Moderate/High confidence)
- a `model_version` tag on every stored prediction
- player prop edges: pass `prop_line`, `over_odds`, `under_odds` (and optional `prop_market`) to `/player/{id}/prediction`, or configure `ODDS_API_KEY` to use `/events/{eventId}/odds?markets=player_points`
- h2h odds snapshots (live odds only) with opening-to-current line movement and a warning when the line moves against the pick
- teammate absences from SportsDataIO injuries and rest days from recent game dates
- an optional NFL/MLB weather factor (`weather_impact=0..1` override, or live Open-Meteo data)
- a "why this prediction" panel, an upstream health banner (live vs. fallback), a localStorage watchlist, and the remaining Odds API request quota
- rest and travel from SportsDataIO `Teams` + `Schedules` (or `Games`) for both sides: rest-day advantage, back-to-backs and travel miles shift the game win probability (override with `rest_days`, `opponent_rest_days`, `travel_miles`, `opponent_travel_miles`)
- tennis surface-specific Elo rebuilt from graded tennis predictions and blended into the win probability as match history grows (`/game/{player}/edge?sport=tennis_*&opponent={opponent}&surface=hard|clay|grass`; surface is otherwise inferred from the tournament key)
- player prop line snapshots (live prop lines only) with opening-to-current line movement and a warning when the line moves against the over/under pick
- a copy button next to every displayed prediction id (and the outcome form's prediction id field); copying an id also fills the outcome form

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
- `UPSTREAM_CACHE_TTL_SECONDS` (defaults to `120`; set `0` to disable the upstream response cache)
- `OPEN_METEO_ENABLED` (set to `1` to fetch live NFL/MLB weather from Open-Meteo; no key needed)
- `OPEN_METEO_BASE_URL` (defaults to `https://api.open-meteo.com/v1`)

Behavior:

- when keys are configured, the app attempts live SportsDataIO, Media & Broadcast, Fantasy Sports API, and Odds API requests first
- Media & Broadcast and Fantasy Sports API derive their live signals from the same SportsData-style upstream when pointed at the same base URL/key
- if a live request fails or returns unusable data, the app safely falls back to the existing deterministic local model inputs
- `/health` reports whether each upstream source is configured, whether its most recent upstream call succeeded, and the last error message when a provider fails

## Persistent history

By default the app stores prediction history and learned model files under:

- `~/.choosing/history.sqlite3`
- `~/.choosing/adapted_models.json`

You can override that location with:

- `CHOOSING_DATA_DIR`

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
- the `worker` process runs `python -m choosing.jobs grade --loop --interval 3600` to grade outcomes every hour

Background jobs can also be run once or from cron:

```bash
python -m choosing.jobs grade --date 2026-09-25
python -m choosing.jobs refresh --sport basketball_nba
```

Railpack / Railway compatibility:

- `/home/runner/work/choosing/choosing/start.sh` provides the startup script Railpack looks for
- `/home/runner/work/choosing/choosing/requirements.txt` marks the repository as a Python app even though it uses only the standard library

## Test

```bash
python -m unittest discover -s tests
```