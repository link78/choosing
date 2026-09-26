from __future__ import annotations

import html

from .catalog import ODDS_API_ENDPOINTS, ODDS_API_SPORTS
from .data_sources import search_players, search_teams


def app_metadata() -> dict:
    return {
        "name": "choosing",
        "description": "Player-centric sports prediction system for smarter betting decisions.",
        "data_sources": ["SportsDataIO", "Media & Broadcast", "Fantasy Sports API", "The Odds API"],
        "upstream_endpoints": {
            "the_odds_api": ODDS_API_ENDPOINTS,
        },
        "upstream_sports": {
            "the_odds_api": ODDS_API_SPORTS,
        },
        "endpoints": {
            "health": "/health",
            "player_prediction": "/player/{id}/prediction",
            "top_players": "/players/top?sport={sport_key}&limit=10",
            "game_edge": "/game/{id}/edge",
            "backtest_summary": "/backtest/summary.json",
            "backtest_grade": "POST /backtest/grade?date=YYYY-MM-DD",
            "backtest_timeseries": "/backtest/timeseries?window=7d|30d|90d|all&sport={sport_key}",
            "backtest_breakdown": "/backtest/breakdown?by=sport|market|confidence_band|edge_bucket|model_version",
            "slate": "/slate?sport={sport_key}&min_edge=0.02&min_confidence=0.5",
            "predictions_csv": "/predictions.csv",
            "record_outcome": "/predictions/{prediction_id}/outcome",
            "player_lookup": "/lookup/players?query={name}",
            "team_lookup": "/lookup/teams?query={team}",
            "app_metadata": "/app.json",
            "odds_sports": "/sports",
            "odds_current": "/sports/{sport}/odds",
            "odds_events": "/sports/{sport}/events",
            "odds_event_odds": "/sports/{sport}/events/{eventId}/odds",
            "odds_scores": "/sports/{sport}/scores",
            "odds_historical": "/historical/sports/{sport}/odds?date=YYYY-MM-DDTHH:MM:SSZ",
        },
        "advisory_only": True,
    }


def render_home_page() -> str:
    metadata = app_metadata()
    players = search_players()
    teams = search_teams()
    sports = metadata["upstream_sports"]["the_odds_api"]
    players_per_sport = {}
    for player in players:
        players_per_sport[player["sport_key"]] = players_per_sport.get(player["sport_key"], 0) + 1
    coverage_summary_markup = "\n".join(
        (
            f'<div class="metric"><strong>Sports covered</strong><br>{len(sports)}</div>',
            f'<div class="metric"><strong>Players tracked</strong><br>{len(players)}</div>',
            f'<div class="metric"><strong>Teams tracked</strong><br>{len(teams)}</div>',
            f'<div class="metric"><strong>Data sources</strong><br>{len(metadata["data_sources"])}</div>',
        )
    )
    coverage_sport_markup = "\n".join(
        (
            f'<div class="metric"><strong>{html.escape(entry["name"])}</strong><br>'
            f'<span class="muted">{players_per_sport.get(entry["key"], 0)} players tracked</span></div>'
        )
        for entry in sports
    )
    player_sport_options = "\n".join(
        f'<option value="{sport["key"]}">{sport["name"]}</option>'
        for sport in metadata["upstream_sports"]["the_odds_api"]
    )
    player_options = "\n".join(
        f'<option value="{player["name"]}">{player["team"]}</option>' for player in players
    )
    team_options = "\n".join(
        f'<option value="{team["team"]}">{team["opponent"]}</option>' for team in teams
    )
    extra_script = EXTRA_SCRIPT
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Choosing — Smarter Betting Decisions</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07111f;
      --panel: #0e1b2d;
      --panel-2: #13253d;
      --text: #edf4ff;
      --muted: #9eb0ca;
      --accent: #58a6ff;
      --accent-2: #00c2a8;
      --danger: #ff7b72;
      --border: rgba(255,255,255,0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: linear-gradient(180deg, #08111d 0%, #0b1730 100%);
      color: var(--text);
    }}
    .shell {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 20px 16px 40px;
    }}
    .hero {{
      display: grid;
      gap: 16px;
      padding: 22px;
      border-radius: 24px;
      background: linear-gradient(135deg, rgba(88,166,255,0.18), rgba(0,194,168,0.12)), var(--panel);
      border: 1px solid var(--border);
      box-shadow: 0 18px 48px rgba(0,0,0,0.28);
    }}
    .eyebrow, .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(88,166,255,0.12);
      color: #cfe6ff;
      font-size: 12px;
    }}
    h1, h2, h3, p {{ margin: 0; }}
    .hero h1 {{ font-size: clamp(30px, 6vw, 52px); line-height: 1.04; }}
    .hero p {{ color: var(--muted); font-size: 16px; line-height: 1.6; }}
    .hero-grid, .cards, .forms {{
      display: grid;
      gap: 16px;
    }}
    .hero-grid {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    .forms {{ grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); margin-top: 18px; }}
    .cards {{ grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); margin-top: 18px; }}
    .card {{
      background: rgba(8, 17, 31, 0.72);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 18px;
    }}
    .stat {{
      font-size: 28px;
      font-weight: 700;
      margin-top: 10px;
    }}
    .muted {{ color: var(--muted); }}
    form {{
      display: grid;
      gap: 12px;
    }}
    label {{
      font-size: 13px;
      color: var(--muted);
      display: grid;
      gap: 6px;
    }}
    input, select {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 14px;
      background: var(--panel-2);
      color: var(--text);
    }}
    button {{
      border: 0;
      border-radius: 12px;
      padding: 12px 14px;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #04101c;
      font-weight: 700;
      cursor: pointer;
    }}
    .result {{
      margin-top: 14px;
      padding: 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.03);
      min-height: 110px;
    }}
    .metric-grid {{
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 12px;
    }}
    .metric {{
      padding: 10px;
      border-radius: 12px;
      background: rgba(255,255,255,0.04);
    }}
    .profile-stack {{
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }}
    .profile-panel {{
      padding: 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
    }}
    .profile-panel h3 {{
      margin-bottom: 10px;
      font-size: 14px;
    }}
    pre {{
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 12px;
      color: #d7e7ff;
    }}
    .danger {{ color: var(--danger); }}
    .warning {{ color: #f2cc60; }}
    .banner {{
      margin-top: 14px;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.04);
      font-size: 13px;
    }}
    .banner.live {{ border-color: rgba(0,194,168,0.5); }}
    .banner.fallback {{ border-color: rgba(242,204,96,0.5); }}
    .inline-actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .inline-actions a, .link-button {{ color: var(--accent); }}
    .id-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; word-break: break-all; }}
    .id-row code {{ font-size: 12px; }}
    button.copy-id {{ padding: 4px 10px; border-radius: 8px; font-size: 12px; }}
    .input-row {{ display: flex; gap: 8px; }}
    .input-row input {{ flex: 1; }}
    .chart {{ width: 100%; height: auto; margin-top: 10px; background: rgba(255,255,255,0.02); border-radius: 12px; }}
    .chart text {{ fill: var(--muted); font-size: 10px; }}
    @media (max-width: 640px) {{
      .shell {{ padding: 14px 12px 28px; }}
      .hero, .card {{ border-radius: 18px; }}
      .metric-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <span class="eyebrow">Mobile friendly betting dashboard</span>
      <h1>Choosing</h1>
      <p>{metadata["description"]}</p>
      <div class="hero-grid">
        <article class="card">
          <span class="badge">Player intelligence</span>
          <div class="stat">SportsDataIO</div>
          <p class="muted">Recent form, fatigue, injuries, consistency, matchup, and team context.</p>
        </article>
        <article class="card">
          <span class="badge">Broadcast context</span>
          <div class="stat">Media &amp; Broadcast</div>
          <p class="muted">Narrative pressure, TV exposure, and audience confidence around player and game spots.</p>
        </article>
        <article class="card">
          <span class="badge">Fantasy overlay</span>
          <div class="stat">Fantasy Sports API</div>
          <p class="muted">Projection-based scoring support, ownership, and value signals to sharpen expectations.</p>
        </article>
        <article class="card">
          <span class="badge">Market intelligence</span>
          <div class="stat">The Odds API</div>
          <p class="muted">Odds movement, implied probability, sharp/steam signals, and consensus.</p>
        </article>
        <article class="card">
          <span class="badge">Actionable output</span>
          <div class="stat">+EV focus</div>
          <p class="muted">Turns model probability versus bookmaker pricing into betting guidance.</p>
        </article>
      </div>
      <div id="health-banner" class="banner muted">Checking upstream data sources...</div>
    </section>

    <section class="forms">
      <article class="card">
        <h2>Player prediction</h2>
        <p class="muted">Look up performance, risk, and availability by player name, with optional team filtering.</p>
        <form id="player-form">
          <label>Player name
            <input id="player-id" name="player-id" value="" placeholder="Search player name" list="player-options">
          </label>
          <label>Team (optional)
            <input id="player-team" name="player-team" value="" placeholder="Filter by team" list="team-options">
          </label>
          <label>Sport
            <select id="player-sport" name="player-sport">
              {player_sport_options}
            </select>
          </label>
          <datalist id="player-options">{player_options}</datalist>
          <datalist id="team-options">{team_options}</datalist>
          <button type="submit">Load player view</button>
        </form>
        <div id="player-result" class="result muted">Waiting for a player lookup.</div>
      </article>

      <article class="card">
        <h2>Game edge</h2>
        <p class="muted">Look up predicted outcomes and betting edges by team name.</p>
        <form id="game-form">
          <label>Team name
            <input id="game-id" name="game-id" value="" placeholder="Search team name" list="team-options">
          </label>
          <label>Model probability (optional)
            <input id="model-probability" name="model-probability" value="0.61" inputmode="decimal">
          </label>
          <label>American odds (optional)
            <input id="odds" name="odds" value="-110" inputmode="numeric">
          </label>
          <label>Sport
            <select id="game-sport" name="game-sport">
              <option value="">Default (NBA)</option>
              {player_sport_options}
            </select>
          </label>
          <label>Opponent (optional, e.g. tennis opponent)
            <input id="game-opponent" name="game-opponent" value="" placeholder="Override opponent" maxlength="100">
          </label>
          <label>Surface (tennis only)
            <select id="game-surface" name="game-surface">
              <option value="">Infer from tournament</option>
              <option value="hard">Hard</option>
              <option value="clay">Clay</option>
              <option value="grass">Grass</option>
            </select>
          </label>
          <button type="submit">Load edge view</button>
        </form>
        <div id="game-result" class="result muted">Waiting for a game lookup.</div>
      </article>

      <article class="card">
        <h2>Odds API market data</h2>
        <p class="muted">Browse sports, current odds, events, event odds, scores, and historical odds from The Odds API (local fallback data when no key is configured).</p>
        <form id="odds-data-form">
          <label>Data
            <select id="odds-data-endpoint" name="odds-data-endpoint">
              <option value="sports">Sports list</option>
              <option value="odds" selected>Current odds</option>
              <option value="events">Event list</option>
              <option value="event_odds">Event odds</option>
              <option value="scores">Scores</option>
              <option value="historical_odds">Historical odds</option>
            </select>
          </label>
          <label>Sport
            <select id="odds-data-sport" name="odds-data-sport">
              {player_sport_options}
            </select>
          </label>
          <label>Event id (event odds)
            <input id="odds-data-event" name="odds-data-event" value="" placeholder="Pick from the event list" list="odds-event-options" maxlength="128">
          </label>
          <datalist id="odds-event-options"></datalist>
          <label>Snapshot date (historical odds)
            <input id="odds-data-date" name="odds-data-date" type="date" value="">
          </label>
          <button type="submit">Load market data</button>
        </form>
        <div id="odds-data-result" class="result muted">Waiting for a market data lookup.</div>
      </article>

      <article class="card">
        <h2>Top players by sport</h2>
        <p class="muted">Summarize the top 10 players for a selected sport using predicted performance and scoring outlook.</p>
        <form id="top-players-form">
          <label>Sport
            <select id="top-players-sport" name="top-players-sport">
              {player_sport_options}
            </select>
          </label>
          <button type="submit">Load top players</button>
        </form>
        <div id="top-players-result" class="result muted">Waiting for a sport summary.</div>
      </article>

      <article class="card">
        <h2>Backtesting &amp; learning</h2>
        <p class="muted">Record actual outcomes, review measured performance, and monitor learned-model updates.</p>
        <form id="outcome-form">
          <label>Prediction id
            <span class="input-row">
              <input id="outcome-prediction-id" name="outcome-prediction-id" value="" placeholder="Paste a prediction id">
              <button type="button" class="copy-id" data-copy-from="outcome-prediction-id" aria-label="Copy prediction id">Copy</button>
            </span>
          </label>
          <label>Actual outcome (game bet: 1 or 0)
            <input id="actual-outcome" name="actual-outcome" value="" placeholder="1 for win, 0 for loss" inputmode="decimal">
          </label>
          <label>Actual points (player optional)
            <input id="actual-points" name="actual-points" value="" placeholder="e.g. 28.5" inputmode="decimal">
          </label>
          <label>Actual minutes (player optional)
            <input id="actual-minutes" name="actual-minutes" value="" placeholder="e.g. 35" inputmode="decimal">
          </label>
          <button type="submit">Record outcome</button>
        </form>
        <div id="outcome-result" class="result muted">Waiting for recorded outcomes.</div>
        <form id="grade-form">
          <label>Grade date (optional)
            <input id="grade-date" name="grade-date" type="date" value="">
          </label>
          <button type="submit">Grade now</button>
        </form>
        <div id="grade-counts" class="banner muted">Loading Pending / Graded counts...</div>
        <div id="grade-result" class="result muted">Grade pending predictions from upstream final scores.</div>
        <div class="inline-actions"><a href="/predictions.csv" download>Export prediction history (CSV)</a></div>
      </article>

      <article class="card">
        <h2>Today's slate</h2>
        <p class="muted">Best edges first from upcoming events, filtered by sport, minimum edge, and confidence.</p>
        <form id="slate-form">
          <label>Sport
            <select id="slate-sport" name="slate-sport">
              {player_sport_options}
            </select>
          </label>
          <label>Minimum edge
            <input id="slate-min-edge" name="slate-min-edge" value="0" inputmode="decimal">
          </label>
          <label>Minimum confidence
            <input id="slate-min-confidence" name="slate-min-confidence" value="0" inputmode="decimal">
          </label>
          <button type="submit">Load slate</button>
        </form>
        <div id="slate-result" class="result muted">Waiting for a slate lookup.</div>
      </article>

      <article class="card">
        <h2>Watchlist</h2>
        <p class="muted">Players and games you save are stored in this browser.</p>
        <div id="watchlist-result" class="result muted">Nothing saved yet.</div>
      </article>
    </section>

    <section class="cards">
      <article class="card">
        <h3>Performance over time</h3>
        <form id="timeseries-form">
          <label>Window
            <select id="timeseries-window" name="timeseries-window">
              <option value="7d">Last 7 days</option>
              <option value="30d" selected>Last 30 days</option>
              <option value="90d">Last 90 days</option>
              <option value="all">All time</option>
            </select>
          </label>
          <label>Breakdown
            <select id="breakdown-by" name="breakdown-by">
              <option value="sport">Sport</option>
              <option value="market">Market</option>
              <option value="confidence_band">Confidence band</option>
              <option value="edge_bucket" selected>Edge bucket</option>
              <option value="model_version">Model version</option>
            </select>
          </label>
          <button type="submit">Refresh charts</button>
        </form>
        <div id="performance-charts" class="result muted">Loading performance charts...</div>
      </article>
    </section>

    <section class="cards">
      <article class="card">
        <h3>Coverage</h3>
        <p class="muted">What Choosing tracks and models today.</p>
        <div class="metric-grid">
          {coverage_summary_markup}
        </div>
        <div class="metric-grid">
          {coverage_sport_markup}
        </div>
      </article>
      <article class="card">
        <h3>Workflow</h3>
        <div class="metric-grid">
          <div class="metric"><strong>1.</strong><br>Track player and team signals</div>
          <div class="metric"><strong>2.</strong><br>Read bookmaker movement and implied probability</div>
          <div class="metric"><strong>3.</strong><br>Estimate outcomes and risk</div>
          <div class="metric"><strong>4.</strong><br>Act only when the edge is positive</div>
        </div>
      </article>
      <article class="card">
        <h3>Measured backtest summary</h3>
        <div id="backtest-summary" class="result muted">Loading backtest summary...</div>
      </article>
    </section>
  </main>

  <script>
    const byId = (id) => document.getElementById(id);

    function playerMarkup(payload) {{
      const suggestions = payload.predictions.suggestions || [];
      return `
        <div class="profile-stack">
          <div class="profile-panel">
            <h3>Prediction</h3>
            <div class="metric-grid">
              <div class="metric"><strong>Player</strong><br>${{payload.player_name}}</div>
              <div class="metric"><strong>Prediction id</strong><br>${{predictionIdMarkup(payload.meta.prediction_id)}}</div>
              <div class="metric"><strong>Team</strong><br>${{payload.team}}</div>
              <div class="metric"><strong>Sport</strong><br>${{payload.sport.name}} · ${{payload.sport.league}}</div>
              <div class="metric"><strong>Minutes</strong><br>${{payload.predictions.expected_minutes}}</div>
              <div class="metric"><strong>Minutes range</strong><br>${{payload.predictions.expected_minutes_range.low}} - ${{payload.predictions.expected_minutes_range.high}}</div>
              <div class="metric"><strong>Points</strong><br>${{payload.predictions.expected_points}}</div>
              <div class="metric"><strong>Points range</strong><br>${{payload.predictions.expected_points_range.low}} - ${{payload.predictions.expected_points_range.high}}</div>
              <div class="metric"><strong>Injured</strong><br>${{payload.predictions.injured_label}}</div>
              <div class="metric"><strong>Scoring outlook</strong><br>${{payload.predictions.scoring_outlook}}</div>
              <div class="metric"><strong>Performance</strong><br>${{payload.predictions.expected_performance}}</div>
              <div class="metric"><strong>Performance range</strong><br>${{payload.predictions.expected_performance_range.low}} - ${{payload.predictions.expected_performance_range.high}}</div>
              <div class="metric"><strong>Availability</strong><br>${{payload.predictions.availability_probability}}</div>
              <div class="metric"><strong>Availability tier</strong><br>${{payload.predictions.availability_tier}}</div>
              <div class="metric"><strong>Underperformance risk</strong><br>${{payload.predictions.underperformance_risk}}</div>
              <div class="metric"><strong>Prediction confidence</strong><br>${{payload.predictions.prediction_confidence}} · ${{payload.predictions.confidence_band}}</div>
            </div>
            <div class="metric-grid">
              ${{suggestions.length ? suggestions.map((item) => `<div class="metric"><strong>Suggestion</strong><br>${{item}}</div>`).join("") : ""}}
            </div>
          </div>
          <div class="profile-panel">
            <h3>Player profile</h3>
            <div class="metric-grid">
              <div class="metric"><strong>Injury status</strong><br>${{payload.player_profile.injury_status}}</div>
              <div class="metric"><strong>Injured</strong><br>${{payload.player_profile.injured_label}}</div>
              <div class="metric"><strong>Scoring band</strong><br>${{payload.player_profile.scoring_band}}</div>
              <div class="metric"><strong>Readiness score</strong><br>${{payload.player_profile.readiness_score}}</div>
              <div class="metric"><strong>Risk level</strong><br>${{payload.player_profile.risk_level}}</div>
              <div class="metric"><strong>Role</strong><br>${{payload.player_profile.projected_role}}</div>
              <div class="metric"><strong>Confidence</strong><br>${{payload.player_profile.prediction_confidence}} · ${{payload.player_profile.confidence_band}}</div>
              <div class="metric"><strong>Sport profile</strong><br>${{payload.player_profile.sport.name}} · ${{payload.player_profile.sport.league}}</div>
              <div class="metric"><strong>Data mode</strong><br>${{payload.player_profile.computation_data.source_mode}}</div>
            </div>
          </div>
          ${{propMarkup(payload.prop_market)}}
          ${{weatherMarkup(payload.weather)}}
          ${{whyMarkup(payload.predictions.feature_tracking, payload.predictions.calibration)}}
          ${{watchButton("player", payload.player_name, {{ team: payload.team, sport: payload.sport.odds_api_key }})}}
        </div>
      `;
    }}

    function topPlayersMarkup(payload) {{
      return `
        <div class="profile-stack">
          <div class="profile-panel">
            <h3>Top players · ${{payload.sport.league}}</h3>
            <div class="metric-grid">
              <div class="metric"><strong>Sport</strong><br>${{payload.sport.name}}</div>
              <div class="metric"><strong>League</strong><br>${{payload.sport.league}}</div>
              <div class="metric"><strong>Returned</strong><br>${{payload.summary.returned}}</div>
              <div class="metric"><strong>Ranking</strong><br>${{payload.summary.ranking_basis}}</div>
            </div>
          </div>
          <div class="profile-panel">
            <h3>Player summary</h3>
            <div class="metric-grid">
              ${{
                payload.top_players.map((player) => `
                  <div class="metric">
                    <strong>${{player.player_name}}</strong><br>
                    ${{player.team}} · ${{player.sport.league}}<br>
                    Injured: ${{player.injured_label}}<br>
                    Performance: ${{player.expected_performance}}<br>
                    Points: ${{player.expected_points}}<br>
                    Range: ${{player.expected_points_range.low}} - ${{player.expected_points_range.high}}<br>
                    Confidence: ${{player.confidence_band}}<br>
                    Outlook: ${{player.scoring_outlook}}<br>
                    Suggestion: ${{player.suggestions[0]}}<br>
                    <button
                      type="button"
                      class="top-player-button"
                      data-player-name="${{player.player_name}}"
                      data-player-team="${{player.team}}"
                      data-player-sport="${{player.sport.odds_api_key}}">
                      View player data
                    </button>
                  </div>
                `).join("")
              }}
            </div>
          </div>
        </div>
      `;
    }}

    function backtestMarkup(payload) {{
      const curve = payload.calibration_curve || [];
      const recent = payload.recent_results || [];
      return `
        <div class="profile-stack">
          <div class="profile-panel">
            <h3>Performance</h3>
            <div class="metric-grid">
              <div class="metric"><strong>Total predictions</strong><br>${{payload.total_predictions}}</div>
              <div class="metric"><strong>Resolved</strong><br>${{payload.resolved_predictions}}</div>
              <div class="metric"><strong>ROI</strong><br>${{payload.roi ?? "N/A"}}</div>
              <div class="metric"><strong>Hit rate</strong><br>${{payload.hit_rate ?? "N/A"}}</div>
              <div class="metric"><strong>Brier score</strong><br>${{payload.brier_score ?? "N/A"}}</div>
              <div class="metric"><strong>Player MAE</strong><br>${{payload.player_mean_absolute_error ?? "N/A"}}</div>
              <div class="metric"><strong>Pending / Graded</strong><br>${{payload.pending_predictions ?? 0}} / ${{payload.graded_predictions ?? 0}}</div>
              <div class="metric"><strong>Log-loss</strong><br>${{payload.log_loss ?? "N/A"}}</div>
              <div class="metric"><strong>Max drawdown</strong><br>${{payload.max_drawdown ?? "N/A"}}</div>
              <div class="metric"><strong>Average CLV</strong><br>${{payload.closing_line_value?.average_clv ?? "N/A"}}</div>
              <div class="metric"><strong>Beat the close</strong><br>${{payload.closing_line_value?.beat_close_rate ?? "N/A"}} (${{payload.closing_line_value?.samples ?? 0}} samples)</div>
              <div class="metric"><strong>Model version</strong><br>${{esc(payload.current_model_version)}}</div>
            </div>
          </div>
          <div class="profile-panel">
            <h3>Learned models</h3>
            <div class="metric-grid">
              <div class="metric"><strong>Updated at</strong><br>${{payload.learned_models?.updated_at || "Not trained yet"}}</div>
              <div class="metric"><strong>Sports</strong><br>${{(payload.learned_models?.sports || []).join(", ") || "None"}}</div>
            </div>
          </div>
          <div class="profile-panel">
            <h3>Calibration</h3>
            <div class="metric-grid">
              ${{
                curve.length
                  ? curve.map((item) => `<div class="metric"><strong>${{item.range}}</strong><br>Pred ${{item.predicted}}<br>Actual ${{item.actual}}<br>Count ${{item.count}}</div>`).join("")
                  : '<div class="metric"><strong>No calibration data</strong><br>Record resolved game outcomes to measure it.</div>'
              }}
            </div>
          </div>
          <div class="profile-panel">
            <h3>Recent results</h3>
            <div class="metric-grid">
              ${{
                recent.length
                  ? recent.map((item) => `<div class="metric"><strong>${{item.subject}}</strong><br>${{predictionIdMarkup(item.prediction_id)}}<br>Action: ${{item.recommended_action || "tracked"}}<br>Profit: ${{item.profit_units ?? "N/A"}}</div>`).join("")
                  : '<div class="metric"><strong>No stored history</strong><br>Generate predictions and record outcomes to build backtesting.</div>'
              }}
            </div>
          </div>
        </div>
      `;
    }}

    function gameMarkup(payload) {{
      return `
        <div class="metric-grid">
          <div class="metric"><strong>Team</strong><br>${{payload.team}}</div>
          <div class="metric"><strong>Prediction id</strong><br>${{predictionIdMarkup(payload.meta.prediction_id)}}</div>
          <div class="metric"><strong>Opponent</strong><br>${{payload.opponent}}</div>
          <div class="metric"><strong>Win probability</strong><br>${{payload.team_prediction.win_probability}}</div>
          <div class="metric"><strong>Win range</strong><br>${{payload.team_prediction.win_probability_range.low}} - ${{payload.team_prediction.win_probability_range.high}}</div>
          <div class="metric"><strong>Expected points</strong><br>${{payload.team_prediction.expected_points}}</div>
          <div class="metric"><strong>Expected points range</strong><br>${{payload.team_prediction.expected_points_range.low}} - ${{payload.team_prediction.expected_points_range.high}}</div>
          <div class="metric"><strong>Implied probability</strong><br>${{payload.market_signals.implied_probability}}</div>
          <div class="metric"><strong>Edge</strong><br>${{payload.betting_edge.edge}}</div>
          <div class="metric"><strong>Action</strong><br>${{payload.betting_edge.recommended_action}}</div>
          <div class="metric"><strong>Stake</strong><br>${{payload.betting_edge.recommended_stake}}</div>
          <div class="metric"><strong>Edge quality</strong><br>${{payload.betting_edge.edge_quality}}</div>
          <div class="metric"><strong>Confidence</strong><br>${{payload.betting_edge.confidence}}</div>
          <div class="metric"><strong>Calibrated probability</strong><br>${{payload.betting_edge.calibrated_probability}} · ${{esc(payload.betting_edge.calibration.mode)}}</div>
          <div class="metric"><strong>Kelly stake</strong><br>${{kellyLabel(payload.betting_edge.kelly)}}</div>
          <div class="metric"><strong>Line movement</strong><br>${{esc(payload.line_history.opening_odds)}} → ${{esc(payload.line_history.current_odds)}} (${{payload.line_history.snapshots}} snapshots)</div>
        </div>
        ${{payload.line_history.warning ? `<p class="warning">⚠ ${{esc(payload.line_history.warning)}}</p>` : ""}}
        <div class="profile-stack">
          ${{scheduleMarkup(payload.schedule_context, payload.team_prediction.schedule_adjustment)}}
          ${{tennisEloMarkup(payload.tennis_elo)}}
          ${{weatherMarkup(payload.weather)}}
          ${{whyMarkup(payload.betting_edge.feature_tracking, payload.betting_edge.calibration)}}
          ${{watchButton("game", payload.team, {{ sport: payload.sport.odds_api_key }})}}
        </div>
      `;
    }}

    async function loadPlayer(event) {{
      event.preventDefault();
      const target = byId("player-result");
      target.textContent = "Loading player prediction...";
      const playerId = encodeURIComponent(byId("player-id").value.trim());
      const params = new URLSearchParams();
      const team = byId("player-team").value.trim();
      const sport = byId("player-sport").value.trim();
      if (team) params.set("team", team);
      if (sport) params.set("sport", sport);
      const suffix = params.toString() ? `?${{params.toString()}}` : "";
      const response = await fetch(`/player/${{playerId}}/prediction${{suffix}}`);
      const payload = await response.json();
      target.innerHTML = response.ok ? playerMarkup(payload) : `<span class="danger">${{payload.error || "Request failed"}}</span>`;
    }}

    async function loadGame(event) {{
      event.preventDefault();
      const target = byId("game-result");
      target.textContent = "Loading game edge...";
      const params = new URLSearchParams();
      const modelProbability = byId("model-probability").value.trim();
      const odds = byId("odds").value.trim();
      if (modelProbability) params.set("model_probability", modelProbability);
      if (odds) params.set("odds", odds);
      const gameSport = byId("game-sport").value.trim();
      const gameOpponent = byId("game-opponent").value.trim();
      const gameSurface = byId("game-surface").value.trim();
      if (gameSport) params.set("sport", gameSport);
      if (gameOpponent) params.set("opponent", gameOpponent);
      if (gameSurface) params.set("surface", gameSurface);
      const gameId = encodeURIComponent(byId("game-id").value.trim());
      const response = await fetch(`/game/${{gameId}}/edge?${{params.toString()}}`);
      const payload = await response.json();
      target.innerHTML = response.ok ? gameMarkup(payload) : `<span class="danger">${{payload.error || "Request failed"}}</span>`;
    }}

    async function loadTopPlayers(event) {{
      event.preventDefault();
      const target = byId("top-players-result");
      target.textContent = "Loading top players...";
      const sport = byId("top-players-sport").value.trim();
      const params = new URLSearchParams();
      if (sport) params.set("sport", sport);
      params.set("limit", "10");
      const response = await fetch(`/players/top?${{params.toString()}}`);
      const payload = await response.json();
      target.innerHTML = response.ok ? topPlayersMarkup(payload) : `<span class="danger">${{payload.error || "Request failed"}}</span>`;
    }}

    async function loadBacktestSummary() {{
      const target = byId("backtest-summary");
      const response = await fetch("/backtest/summary.json");
      const payload = await response.json();
      target.innerHTML = response.ok ? backtestMarkup(payload) : `<span class="danger">${{payload.error || "Request failed"}}</span>`;
      if (response.ok) {{
        byId("grade-counts").innerHTML = `<strong>Pending / Graded:</strong> ${{payload.pending_predictions ?? 0}} / ${{payload.graded_predictions ?? 0}}`;
      }}
    }}

    async function recordOutcome(event) {{
      event.preventDefault();
      const target = byId("outcome-result");
      const predictionId = byId("outcome-prediction-id").value.trim();
      if (!predictionId) {{
        target.innerHTML = '<span class="danger">Prediction id is required.</span>';
        return;
      }}
      const payload = {{}};
      const actualOutcome = byId("actual-outcome").value.trim();
      const actualPoints = byId("actual-points").value.trim();
      const actualMinutes = byId("actual-minutes").value.trim();
      if (actualOutcome) payload.actual_outcome = Number(actualOutcome);
      if (actualPoints) payload.actual_points = Number(actualPoints);
      if (actualMinutes) payload.actual_minutes = Number(actualMinutes);
      const response = await fetch(`/predictions/${{encodeURIComponent(predictionId)}}/outcome`, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload),
      }});
      const result = await response.json();
      target.innerHTML = response.ok
        ? `<strong>Outcome recorded.</strong><br>Prediction: ${{predictionIdMarkup(result.prediction.prediction_id)}}`
        : `<span class="danger">${{result.error || "Request failed"}}</span>`;
      if (response.ok) {{
        await loadBacktestSummary();
      }}
    }}

    async function loadSelectedTopPlayer(event) {{
      const button = event.target.closest(".top-player-button");
      if (!button) return;
      byId("player-id").value = button.dataset.playerName || "";
      byId("player-team").value = button.dataset.playerTeam || "";
      byId("player-sport").value = button.dataset.playerSport || "";
      await loadPlayer(event);
    }}

    byId("player-form").addEventListener("submit", loadPlayer);
    byId("game-form").addEventListener("submit", loadGame);
    byId("top-players-form").addEventListener("submit", loadTopPlayers);
    byId("outcome-form").addEventListener("submit", recordOutcome);
    byId("top-players-result").addEventListener("click", loadSelectedTopPlayer);
    {extra_script}
    loadBacktestSummary();
  </script>
</body>
</html>"""


EXTRA_SCRIPT = r"""
    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]));
    }

    function kellyLabel(kelly) {
      if (!kelly) return "N/A";
      return `${(kelly.stake_fraction * 100).toFixed(2)}% of bankroll (${kelly.stake_units} u / ${kelly.bankroll_units} u, cap ${(kelly.confidence_cap * 100).toFixed(0)}%)`;
    }

    function whyMarkup(tracking, calibration) {
      const helping = (tracking && tracking.helping) || [];
      const hurting = (tracking && tracking.hurting) || [];
      return `
        <div class="profile-panel">
          <h3>Why this prediction</h3>
          <div class="metric-grid">
            <div class="metric"><strong>Helping</strong><br>${helping.length ? helping.map(esc).join(", ") : "No strong positives"}</div>
            <div class="metric"><strong>Hurting</strong><br>${hurting.length ? hurting.map(esc).join(", ") : "No strong negatives"}</div>
            <div class="metric"><strong>Calibration</strong><br>${esc(calibration?.mode || "n/a")}${calibration?.samples ? ` · ${calibration.samples} samples` : ""}</div>
          </div>
        </div>`;
    }

    function propMarkup(prop) {
      if (!prop) {
        return '<div class="profile-panel"><h3>Prop market</h3><p class="muted">No live prop line. Add prop_line, over_odds and under_odds to compare.</p></div>';
      }
      return `
        <div class="profile-panel">
          <h3>Prop market · ${esc(prop.market)}</h3>
          <div class="metric-grid">
            <div class="metric"><strong>Line</strong><br>${esc(prop.line)} (O ${esc(prop.over_odds)} / U ${esc(prop.under_odds)})</div>
            <div class="metric"><strong>Projection</strong><br>${esc(prop.projection)} ± ${esc(prop.projection_sigma)}</div>
            <div class="metric"><strong>P(over)</strong><br>${esc(prop.probability_over)}</div>
            <div class="metric"><strong>Edge</strong><br>${esc(prop.edge)}</div>
            <div class="metric"><strong>Action</strong><br>${esc(prop.recommended_action)}</div>
            <div class="metric"><strong>Kelly stake</strong><br>${kellyLabel(prop.kelly)}</div>
            ${prop.line_history ? `<div class="metric"><strong>Line movement</strong><br>${esc(prop.line_history.opening_line)} → ${esc(prop.line_history.current_line)} (${esc(prop.line_history.snapshots)} snapshots)</div>` : ""}
          </div>
          ${prop.line_history && prop.line_history.warning ? `<p class="warning">⚠ ${esc(prop.line_history.warning)}</p>` : ""}
        </div>`;
    }

    function predictionIdMarkup(predictionId) {
      if (!predictionId) return "Not stored";
      return `<span class="id-row"><code>${esc(predictionId)}</code><button type="button" class="copy-id" data-copy="${esc(predictionId)}" aria-label="Copy prediction id">Copy</button></span>`;
    }

    async function copyText(text) {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
      }
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.setAttribute("readonly", "");
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      try {
        if (!document.execCommand("copy")) throw new Error("copy failed");
      } finally {
        helper.remove();
      }
    }

    async function handleCopyClick(event) {
      const button = event.target.closest(".copy-id");
      if (!button) return;
      event.preventDefault();
      const text = button.dataset.copyFrom ? byId(button.dataset.copyFrom).value.trim() : button.dataset.copy || "";
      if (!text) {
        button.textContent = "Nothing to copy";
      } else {
        try {
          await copyText(text);
          button.textContent = "Copied!";
          if (!button.dataset.copyFrom) byId("outcome-prediction-id").value = text;
        } catch (error) {
          button.textContent = "Copy failed";
        }
      }
      setTimeout(() => { button.textContent = "Copy"; }, 1500);
    }

    function scheduleMarkup(schedule, adjustment) {
      if (!schedule) return "";
      const side = (rest, miles, b2b) => `${rest ?? "?"} rest days${b2b ? " (back-to-back)" : ""} · ${miles ?? "?"} mi travel`;
      return `
        <div class="profile-panel">
          <h3>Rest &amp; travel (${esc(schedule.source_mode)})</h3>
          <div class="metric-grid">
            <div class="metric"><strong>Team</strong><br>${esc(side(schedule.rest_days, schedule.travel_miles, schedule.back_to_back))}</div>
            <div class="metric"><strong>Opponent</strong><br>${esc(side(schedule.opponent_rest_days, schedule.opponent_travel_miles, schedule.opponent_back_to_back))}</div>
            <div class="metric"><strong>Win probability shift</strong><br>${esc(adjustment)}</div>
          </div>
        </div>`;
    }

    function tennisEloMarkup(elo) {
      if (!elo) return "";
      return `
        <div class="profile-panel">
          <h3>Surface Elo · ${esc(elo.surface)}</h3>
          <div class="metric-grid">
            <div class="metric"><strong>Player rating</strong><br>${esc(elo.player_rating)} (${esc(elo.player_surface_matches)} on surface / ${esc(elo.player_matches)} total)</div>
            <div class="metric"><strong>Opponent rating</strong><br>${esc(elo.opponent_rating)} (${esc(elo.opponent_surface_matches)} on surface / ${esc(elo.opponent_matches)} total)</div>
            <div class="metric"><strong>Elo win probability</strong><br>${esc(elo.elo_probability)}</div>
            <div class="metric"><strong>Blend weight</strong><br>${esc(elo.blend_weight)}</div>
          </div>
        </div>`;
    }

    function weatherMarkup(weather) {
      if (!weather) return "";
      const detail = weather.indoor
        ? "Indoor venue"
        : `${weather.temperature_f ?? "?"}°F · wind ${weather.wind_mph ?? "?"} mph · precip ${weather.precipitation_mm ?? "?"} mm`;
      return `
        <div class="profile-panel">
          <h3>Weather (${esc(weather.mode)})</h3>
          <div class="metric-grid">
            <div class="metric"><strong>Conditions</strong><br>${esc(detail)}</div>
            <div class="metric"><strong>Impact</strong><br>${esc(weather.weather_impact)} · scoring ×${esc(weather.scoring_factor)}</div>
          </div>
        </div>`;
    }

    const WATCHLIST_KEY = "choosing.watchlist";

    function readWatchlist() {
      try {
        const parsed = JSON.parse(localStorage.getItem(WATCHLIST_KEY) || "[]");
        return Array.isArray(parsed) ? parsed : [];
      } catch (error) {
        return [];
      }
    }

    function writeWatchlist(items) {
      localStorage.setItem(WATCHLIST_KEY, JSON.stringify(items.slice(0, 50)));
      renderWatchlist();
    }

    function watchButton(kind, name, extra) {
      const data = esc(JSON.stringify({ kind, name, ...extra }));
      return `<div class="inline-actions"><button type="button" class="watch-add" data-item="${data}">Add to watchlist</button></div>`;
    }

    function renderWatchlist() {
      const target = byId("watchlist-result");
      const items = readWatchlist();
      if (!items.length) {
        target.innerHTML = "Nothing saved yet.";
        return;
      }
      target.innerHTML = `<div class="metric-grid">${items.map((item, index) => `
        <div class="metric">
          <strong>${esc(item.name)}</strong><br>${esc(item.kind)}${item.team ? ` · ${esc(item.team)}` : ""}
          <div class="inline-actions">
            <button type="button" class="watch-open" data-index="${index}">Open</button>
            <button type="button" class="watch-remove" data-index="${index}">Remove</button>
          </div>
        </div>`).join("")}</div>`;
    }

    async function handleWatchClick(event) {
      const addButton = event.target.closest(".watch-add");
      if (addButton) {
        const item = JSON.parse(addButton.dataset.item);
        const items = readWatchlist().filter((entry) => !(entry.kind === item.kind && entry.name === item.name));
        writeWatchlist([item, ...items]);
        addButton.textContent = "Saved";
        return;
      }
      const removeButton = event.target.closest(".watch-remove");
      if (removeButton) {
        const items = readWatchlist();
        items.splice(Number(removeButton.dataset.index), 1);
        writeWatchlist(items);
        return;
      }
      const openButton = event.target.closest(".watch-open");
      if (openButton) {
        const item = readWatchlist()[Number(openButton.dataset.index)];
        if (!item) return;
        if (item.kind === "player") {
          byId("player-id").value = item.name || "";
          byId("player-team").value = item.team || "";
          if (item.sport) byId("player-sport").value = item.sport;
          await loadPlayer(event);
        } else {
          byId("game-id").value = item.name || "";
          if (item.sport) byId("game-sport").value = item.sport;
          await loadGame(event);
        }
      }
    }

    async function loadHealth() {
      const target = byId("health-banner");
      try {
        const response = await fetch("/health");
        const payload = await response.json();
        const sources = payload.sources || {};
        const entries = Object.entries(sources);
        const liveCount = entries.filter(([, status]) => status.mode === "live").length;
        const odds = sources.odds_api || {};
        const quota = odds.requests_remaining != null ? ` · Odds API requests remaining: ${esc(odds.requests_remaining)}` : "";
        target.className = `banner ${liveCount ? "live" : "fallback"}`;
        target.innerHTML = `<strong>${liveCount ? "Live data" : "Fallback sample data"}</strong> · ${entries.map(([name, status]) => `${esc(name)}: ${esc(status.mode)}${status.last_call_succeeded === false ? " (last call failed)" : ""}`).join(" · ")}${quota}`;
      } catch (error) {
        target.className = "banner fallback";
        target.textContent = "Unable to reach /health.";
      }
    }

    async function gradeNow(event) {
      event.preventDefault();
      const target = byId("grade-result");
      target.textContent = "Grading pending predictions...";
      const date = byId("grade-date").value.trim();
      const suffix = date ? `?date=${encodeURIComponent(date)}` : "";
      const response = await fetch(`/backtest/grade${suffix}`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) {
        target.innerHTML = `<span class="danger">${esc(payload.error || "Request failed")}</span>`;
        return;
      }
      const skipped = Object.entries(payload.skipped || {}).map(([reason, count]) => `${esc(reason)}: ${count}`).join(", ");
      target.innerHTML = `<strong>Graded ${payload.graded_count} of ${payload.checked} checked.</strong><br>Pending / Graded: ${payload.pending} / ${payload.total_graded}<br><span class="muted">${skipped || "Nothing skipped"}</span>`;
      await loadBacktestSummary();
      await loadCharts();
    }

    async function loadSlate(event) {
      event.preventDefault();
      const target = byId("slate-result");
      target.textContent = "Loading slate...";
      const params = new URLSearchParams();
      params.set("sport", byId("slate-sport").value.trim());
      const minEdge = byId("slate-min-edge").value.trim();
      const minConfidence = byId("slate-min-confidence").value.trim();
      if (minEdge) params.set("min_edge", minEdge);
      if (minConfidence) params.set("min_confidence", minConfidence);
      const response = await fetch(`/slate?${params.toString()}`);
      const payload = await response.json();
      if (!response.ok) {
        target.innerHTML = `<span class="danger">${esc(payload.error || "Request failed")}</span>`;
        return;
      }
      if (!payload.games.length) {
        target.innerHTML = `No games match the filters (${payload.evaluated} evaluated, ${esc(payload.source_mode)} data).`;
        return;
      }
      target.innerHTML = `<p class="muted">${payload.evaluated} evaluated · ${esc(payload.source_mode)} data</p><div class="metric-grid">${payload.games.map((game) => `
        <div class="metric">
          <strong>${esc(game.matchup)}</strong><br>
          Pick: ${esc(game.pick)} (${esc(game.current_odds)})<br>
          Edge: ${esc(game.edge)} · Confidence: ${esc(game.confidence)}<br>
          Action: ${esc(game.recommended_action)}<br>
          Stake: ${kellyLabel(game.kelly)}<br>
          Why: ${esc((game.feature_tracking.helping || []).join(", ") || "n/a")}
          ${game.line_warning ? `<br><span class="warning">⚠ ${esc(game.line_warning)}</span>` : ""}
          ${watchButton("game", game.pick, {})}
        </div>`).join("")}</div>`;
    }

    function lineChart(points, key, label) {
      const values = points.map((point) => point[key]).filter((value) => value != null);
      if (!values.length) return `<p class="muted">${esc(label)}: no graded results yet.</p>`;
      const width = 320, height = 120, pad = 20;
      const min = Math.min(0, ...values), max = Math.max(0, ...values);
      const span = max - min || 1;
      const x = (index) => pad + (values.length === 1 ? 0 : (index / (values.length - 1)) * (width - pad * 2));
      const y = (value) => height - pad - ((value - min) / span) * (height - pad * 2);
      const path = values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
      return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}">
        <line x1="${pad}" y1="${y(0)}" x2="${width - pad}" y2="${y(0)}" stroke="rgba(255,255,255,0.2)"></line>
        <path d="${path}" fill="none" stroke="#58a6ff" stroke-width="2"></path>
        <text x="${pad}" y="12">${esc(label)} · last ${esc(values[values.length - 1])}</text>
      </svg>`;
    }

    function calibrationChart(curve) {
      if (!curve.length) return "no resolved outcomes yet.";
      const size = 160, pad = 18;
      const scale = (value) => pad + value * (size - pad * 2);
      const dots = curve.map((item) => `<circle cx="${scale(item.predicted).toFixed(1)}" cy="${(size - scale(item.actual)).toFixed(1)}" r="${Math.min(3 + item.count, 9)}" fill="#00c2a8"><title>${esc(item.range)}: predicted ${item.predicted}, actual ${item.actual}, n=${item.count}</title></circle>`).join("");
      return `<svg class="chart" viewBox="0 0 ${size} ${size}" role="img" aria-label="Calibration plot">
        <line x1="${pad}" y1="${size - pad}" x2="${size - pad}" y2="${pad}" stroke="rgba(255,255,255,0.25)" stroke-dasharray="4 3"></line>
        ${dots}
        <text x="${pad}" y="12">Predicted vs actual</text>
      </svg>`;
    }

    function barChart(segments, key, label) {
      if (!segments.length) return `<p class="muted">${esc(label)}: no graded results yet.</p>`;
      const width = 320, rowHeight = 22, pad = 90;
      const values = segments.map((segment) => segment[key] ?? 0);
      const maxAbs = Math.max(...values.map((value) => Math.abs(value)), 0.0001);
      const mid = pad + (width - pad - 10) / 2;
      const half = (width - pad - 10) / 2;
      const bars = segments.map((segment, index) => {
        const value = segment[key] ?? 0;
        const length = (Math.abs(value) / maxAbs) * half;
        const x = value >= 0 ? mid : mid - length;
        const y = 18 + index * rowHeight;
        return `<text x="4" y="${y + 12}">${esc(segment.segment)} (${segment.bets})</text>
          <rect x="${x.toFixed(1)}" y="${y}" width="${length.toFixed(1)}" height="14" fill="${value >= 0 ? "#00c2a8" : "#ff7b72"}"><title>${esc(segment.segment)}: ${value}</title></rect>`;
      }).join("");
      const height = 24 + segments.length * rowHeight;
      return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}">
        <text x="4" y="12">${esc(label)}</text>
        <line x1="${mid}" y1="16" x2="${mid}" y2="${height}" stroke="rgba(255,255,255,0.2)"></line>
        ${bars}
      </svg>`;
    }

    async function loadCharts(event) {
      if (event) event.preventDefault();
      const target = byId("performance-charts");
      const windowValue = byId("timeseries-window").value;
      const by = byId("breakdown-by").value;
      const [seriesResponse, breakdownResponse, summaryResponse] = await Promise.all([
        fetch(`/backtest/timeseries?window=${encodeURIComponent(windowValue)}`),
        fetch(`/backtest/breakdown?by=${encodeURIComponent(by)}`),
        fetch("/backtest/summary.json"),
      ]);
      const series = await seriesResponse.json();
      const breakdown = await breakdownResponse.json();
      const summary = await summaryResponse.json();
      if (!seriesResponse.ok || !breakdownResponse.ok) {
        target.innerHTML = `<span class="danger">${esc(series.error || breakdown.error || "Request failed")}</span>`;
        return;
      }
      const points = series.points || [];
      target.innerHTML = `
        <div class="metric-grid">
          <div class="metric"><strong>Profit (units)</strong><br>${series.summary.total_profit}</div>
          <div class="metric"><strong>Max drawdown</strong><br>${series.summary.max_drawdown ?? "N/A"}</div>
          <div class="metric"><strong>Hit rate</strong><br>${series.summary.hit_rate ?? "N/A"}</div>
          <div class="metric"><strong>Log-loss</strong><br>${series.summary.log_loss ?? "N/A"}</div>
        </div>
        ${lineChart(points, "cumulative_profit", "Bankroll curve (units)")}
        ${lineChart(points, "rolling_hit_rate", "Rolling hit rate")}
        ${lineChart(points, "rolling_brier_score", "Rolling Brier score")}
        ${calibrationChart(summary.calibration_curve || [])}
        ${barChart(breakdown.segments || [], "roi", `ROI by ${by}`)}
      `;
    }

    const ODDS_DATA_PATHS = {
      sports: () => "/sports",
      odds: (sport) => `/sports/${encodeURIComponent(sport)}/odds`,
      events: (sport) => `/sports/${encodeURIComponent(sport)}/events`,
      event_odds: (sport, eventId) => `/sports/${encodeURIComponent(sport)}/events/${encodeURIComponent(eventId)}/odds`,
      scores: (sport) => `/sports/${encodeURIComponent(sport)}/scores`,
      historical_odds: (sport) => `/historical/sports/${encodeURIComponent(sport)}/odds`,
    };

    function formatTime(value) {
      if (!value) return "N/A";
      const parsed = new Date(value);
      return Number.isNaN(parsed.getTime()) ? esc(value) : esc(parsed.toLocaleString());
    }

    function oddsTable(headers, rows) {
      if (!rows.length) return '<p class="muted">No data returned.</p>';
      return `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:0.9rem">
        <thead><tr>${headers.map((header) => `<th style="text-align:left;padding:6px;border-bottom:1px solid rgba(255,255,255,0.15)">${esc(header)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td style="padding:6px;border-bottom:1px solid rgba(255,255,255,0.06);vertical-align:top">${cell}</td>`).join("")}</tr>`).join("")}</tbody>
      </table></div>`;
    }

    function formatPrice(price) {
      const number = Number(price);
      if (!Number.isFinite(number)) return esc(price);
      return esc(number > 0 ? `+${number}` : `${number}`);
    }

    function marketSummary(event) {
      const lines = [];
      (event.bookmakers || []).forEach((bookmaker) => {
        (bookmaker.markets || []).forEach((market) => {
          const outcomes = (market.outcomes || []).map((outcome) => {
            const point = outcome.point !== undefined && outcome.point !== null ? ` ${esc(outcome.point)}` : "";
            return `${esc(outcome.name)}${point} ${formatPrice(outcome.price)}`;
          }).join(" · ");
          lines.push(`<strong>${esc(bookmaker.title || bookmaker.key)}</strong> (${esc(market.key)}): ${outcomes}`);
        });
      });
      return lines.length ? lines.join("<br>") : '<span class="muted">No bookmaker prices</span>';
    }

    function matchupLabel(event) {
      return `${esc(event.away_team)} @ ${esc(event.home_team)}`;
    }

    function oddsEventRows(events) {
      return events.map((event) => [matchupLabel(event), formatTime(event.commence_time), marketSummary(event)]);
    }

    function updateOddsEventOptions(events) {
      const list = byId("odds-event-options");
      list.innerHTML = events.map((event) => `<option value="${esc(event.id)}">${matchupLabel(event)}</option>`).join("");
      const input = byId("odds-data-event");
      if (!input.value && events.length) input.value = events[0].id;
    }

    function renderOddsData(endpoint, payload) {
      const data = payload.data;
      if (endpoint === "sports") {
        const sports = Array.isArray(data) ? data : [];
        return oddsTable(["Sport", "Key", "Group", "Active"], sports.map((sport) => [
          esc(sport.title), `<code>${esc(sport.key)}</code>`, esc(sport.group), sport.active ? "Yes" : "No",
        ]));
      }
      if (endpoint === "events") {
        const events = Array.isArray(data) ? data : [];
        updateOddsEventOptions(events);
        return oddsTable(["Matchup", "Start", "Event id"], events.map((event) => [
          matchupLabel(event), formatTime(event.commence_time), `<code>${esc(event.id)}</code>`,
        ]));
      }
      if (endpoint === "odds") {
        const events = Array.isArray(data) ? data : [];
        updateOddsEventOptions(events);
        return oddsTable(["Matchup", "Start", "Prices"], oddsEventRows(events));
      }
      if (endpoint === "event_odds") {
        const event = data || {};
        return `<div class="metric-grid">
            <div class="metric"><strong>Matchup</strong><br>${matchupLabel(event)}</div>
            <div class="metric"><strong>Start</strong><br>${formatTime(event.commence_time)}</div>
            <div class="metric"><strong>Event id</strong><br><code>${esc(event.id)}</code></div>
          </div>
          ${oddsTable(["Bookmaker", "Last update", "Prices"], (event.bookmakers || []).map((bookmaker) => [
            esc(bookmaker.title || bookmaker.key), formatTime(bookmaker.last_update), marketSummary({bookmakers: [bookmaker]}),
          ]))}`;
      }
      if (endpoint === "scores") {
        const games = Array.isArray(data) ? data : [];
        return oddsTable(["Matchup", "Start", "Score", "Status"], games.map((game) => {
          const scores = (game.scores || []).map((entry) => `${esc(entry.name)} ${esc(entry.score)}`).join("<br>");
          return [matchupLabel(game), formatTime(game.commence_time), scores || '<span class="muted">Not started</span>', game.completed ? "Final" : "Upcoming / live"];
        }));
      }
      if (endpoint === "historical_odds") {
        const snapshot = data || {};
        const events = Array.isArray(snapshot.data) ? snapshot.data : [];
        return `<div class="metric-grid">
            <div class="metric"><strong>Snapshot</strong><br>${formatTime(snapshot.timestamp)}</div>
            <div class="metric"><strong>Previous</strong><br>${formatTime(snapshot.previous_timestamp)}</div>
            <div class="metric"><strong>Next</strong><br>${formatTime(snapshot.next_timestamp)}</div>
          </div>
          ${oddsTable(["Matchup", "Start", "Prices"], oddsEventRows(events))}`;
      }
      return '<p class="muted">Unsupported endpoint.</p>';
    }

    async function loadOddsData(event) {
      if (event) event.preventDefault();
      const target = byId("odds-data-result");
      const endpoint = byId("odds-data-endpoint").value;
      const sport = byId("odds-data-sport").value;
      const eventId = byId("odds-data-event").value.trim();
      const date = byId("odds-data-date").value;
      if (endpoint === "event_odds" && !eventId) {
        target.innerHTML = '<span class="danger">Enter an event id (load the event list or current odds first).</span>';
        return;
      }
      let url = ODDS_DATA_PATHS[endpoint](sport, eventId);
      if (endpoint === "historical_odds" && date) {
        url += `?date=${encodeURIComponent(`${date}T12:00:00Z`)}`;
      }
      target.innerHTML = '<span class="muted">Loading market data...</span>';
      try {
        const response = await fetch(url);
        const payload = await response.json();
        if (!response.ok) {
          target.innerHTML = `<span class="danger">${esc(payload.error || "Request failed")}</span>`;
          return;
        }
        target.innerHTML = `
          <div class="banner muted">${esc(payload.provider)} · <code>${esc(payload.path)}</code> · ${esc(payload.source_mode)} data</div>
          ${renderOddsData(endpoint, payload)}`;
      } catch (error) {
        target.innerHTML = '<span class="danger">Unable to load market data.</span>';
      }
    }

    byId("odds-data-sport").addEventListener("change", () => {
      byId("odds-data-event").value = "";
      byId("odds-event-options").innerHTML = "";
    });
    byId("odds-data-form").addEventListener("submit", loadOddsData);
    byId("grade-form").addEventListener("submit", gradeNow);
    byId("slate-form").addEventListener("submit", loadSlate);
    byId("timeseries-form").addEventListener("submit", loadCharts);
    document.addEventListener("click", handleWatchClick);
    document.addEventListener("click", handleCopyClick);
    renderWatchlist();
    loadHealth();
    loadCharts();
    loadOddsData();
"""
