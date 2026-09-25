# choosing

Sports betting application built on existing sports-data and odds integrations.

## Application

Run the application:

```bash
python -m choosing --players 7,42 --games finals,demo --bankroll 1000
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

- `GET /player/{id}/prediction`
- `GET /game/{id}/edge`
- `GET /`
- `GET /health`

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