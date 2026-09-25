# choosing

Minimal player-centric sports prediction API.

## Endpoints

- `GET /player/{id}/prediction` returns player signals plus expected minutes, expected performance, underperformance risk, and availability probability.
- `GET /game/{id}/edge` returns team prediction, market signals, and betting edge versus implied bookmaker probability.

## Run

```bash
python -m choosing.api
```

## Test

```bash
python -m unittest discover -s tests
```