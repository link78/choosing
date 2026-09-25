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

## Test

```bash
python -m unittest discover -s tests
```