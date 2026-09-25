# choosing

Player-centric sports prediction API.

## Endpoints

- `GET /player/{id}/prediction` returns player signals plus expected minutes, expected performance, underperformance risk, and availability probability.
- `GET /game/{id}/edge` returns team prediction, market signals, and betting edge versus implied bookmaker probability.
- `GET /` returns an application summary and advertised endpoints.
- `GET /health` returns readiness plus configured source status.

Both prediction endpoints accept optional query-string overrides so you can simulate SportsDataIO and bookmaker inputs without external dependencies.

## Run

```bash
python -m choosing.api
```

## Test

```bash
python -m unittest discover -s tests
```