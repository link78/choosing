from __future__ import annotations

import json

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
            "record_outcome": "/predictions/{prediction_id}/outcome",
            "player_lookup": "/lookup/players?query={name}",
            "team_lookup": "/lookup/teams?query={team}",
            "app_metadata": "/app.json",
        },
        "advisory_only": True,
    }


def render_home_page() -> str:
    metadata = app_metadata()
    metadata_json = json.dumps(metadata, indent=2)
    odds_endpoint_markup = "\n".join(
        (
            f'<div class="metric"><strong>{entry["name"]}</strong><br>'
            f'<span class="muted">{entry["path"]}</span></div>'
        )
        for entry in metadata["upstream_endpoints"]["the_odds_api"]
    )
    odds_sport_markup = "\n".join(
        (
            f'<div class="metric"><strong>{entry["name"]}</strong><br>'
            f'<span class="muted">{entry["key"]}</span></div>'
        )
        for entry in metadata["upstream_sports"]["the_odds_api"]
    )
    player_sport_options = "\n".join(
        f'<option value="{sport["key"]}">{sport["name"]}</option>'
        for sport in metadata["upstream_sports"]["the_odds_api"]
    )
    player_options = "\n".join(
        f'<option value="{player["name"]}">{player["team"]}</option>' for player in search_players()
    )
    team_options = "\n".join(
        f'<option value="{team["team"]}">{team["opponent"]}</option>' for team in search_teams()
    )
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
          <button type="submit">Load edge view</button>
        </form>
        <div id="game-result" class="result muted">Waiting for a game lookup.</div>
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
            <input id="outcome-prediction-id" name="outcome-prediction-id" value="" placeholder="Paste a prediction id">
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
      </article>
    </section>

    <section class="cards">
      <article class="card">
        <h3>Available API</h3>
        <pre>{metadata_json}</pre>
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
        <h3>The Odds API endpoints</h3>
        <div class="metric-grid">
          {odds_endpoint_markup}
        </div>
      </article>
      <article class="card">
        <h3>The Odds API sports</h3>
        <div class="metric-grid">
          {odds_sport_markup}
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

    function listMarkup(items, keyField) {{
      return items.map((item) => `
        <div class="metric"><strong>${{item.name}}</strong><br>${{item[keyField]}}</div>
      `).join("");
    }}

    function playerMarkup(payload) {{
      const predictionEndpoints = payload.predictions.odds_api_endpoints || [];
      const profileSports = payload.player_profile.odds_api_coverage?.sports || [];
      const suggestions = payload.predictions.suggestions || [];
      return `
        <div class="profile-stack">
          <div class="profile-panel">
            <h3>Prediction</h3>
            <div class="metric-grid">
              <div class="metric"><strong>Player</strong><br>${{payload.player_name}}</div>
              <div class="metric"><strong>Prediction id</strong><br>${{payload.meta.prediction_id || "Not stored"}}</div>
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
              ${{predictionEndpoints.length ? listMarkup(predictionEndpoints, 'path') : '<div class="metric"><strong>Odds API endpoints</strong><br>No data</div>'}}
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
            <div class="metric-grid">
              ${{profileSports.length ? listMarkup(profileSports, 'key') : '<div class="metric"><strong>Odds API sports</strong><br>No data</div>'}}
            </div>
          </div>
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
                  ? recent.map((item) => `<div class="metric"><strong>${{item.subject}}</strong><br>${{item.prediction_id}}<br>Action: ${{item.recommended_action || "tracked"}}<br>Profit: ${{item.profit_units ?? "N/A"}}</div>`).join("")
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
          <div class="metric"><strong>Prediction id</strong><br>${{payload.meta.prediction_id || "Not stored"}}</div>
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
        ? `<strong>Outcome recorded.</strong><br>Prediction: ${{result.prediction.prediction_id}}`
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
    loadBacktestSummary();
  </script>
</body>
</html>"""
