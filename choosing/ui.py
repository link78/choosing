from __future__ import annotations

import json

from .data_sources import search_players, search_teams


def app_metadata() -> dict:
    return {
        "name": "choosing",
        "description": "Player-centric sports prediction system for smarter betting decisions.",
        "data_sources": ["SportsDataIO", "The Odds API"],
        "endpoints": {
            "health": "/health",
            "player_prediction": "/player/{id}/prediction",
            "game_edge": "/game/{id}/edge",
            "player_lookup": "/lookup/players?query={name}",
            "team_lookup": "/lookup/teams?query={team}",
            "app_metadata": "/app.json",
        },
        "advisory_only": True,
    }


def render_home_page() -> str:
    metadata = app_metadata()
    metadata_json = json.dumps(metadata, indent=2)
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
    input {{
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
    </section>
  </main>

  <script>
    const byId = (id) => document.getElementById(id);

    function playerMarkup(payload) {{
      return `
        <div class="metric-grid">
          <div class="metric"><strong>Player</strong><br>${{payload.player_name}}</div>
          <div class="metric"><strong>Team</strong><br>${{payload.team}}</div>
          <div class="metric"><strong>Minutes</strong><br>${{payload.predictions.expected_minutes}}</div>
          <div class="metric"><strong>Points</strong><br>${{payload.predictions.expected_points}}</div>
          <div class="metric"><strong>Scoring outlook</strong><br>${{payload.predictions.scoring_outlook}}</div>
          <div class="metric"><strong>Scoring band</strong><br>${{payload.player_profile.scoring_band}}</div>
          <div class="metric"><strong>Readiness score</strong><br>${{payload.player_profile.readiness_score}}</div>
          <div class="metric"><strong>Risk level</strong><br>${{payload.player_profile.risk_level}}</div>
          <div class="metric"><strong>Role</strong><br>${{payload.player_profile.projected_role}}</div>
          <div class="metric"><strong>Performance</strong><br>${{payload.predictions.expected_performance}}</div>
          <div class="metric"><strong>Availability</strong><br>${{payload.predictions.availability_probability}}</div>
          <div class="metric"><strong>Underperformance risk</strong><br>${{payload.predictions.underperformance_risk}}</div>
        </div>
      `;
    }}

    function gameMarkup(payload) {{
      return `
        <div class="metric-grid">
          <div class="metric"><strong>Team</strong><br>${{payload.team}}</div>
          <div class="metric"><strong>Opponent</strong><br>${{payload.opponent}}</div>
          <div class="metric"><strong>Win probability</strong><br>${{payload.team_prediction.win_probability}}</div>
          <div class="metric"><strong>Expected points</strong><br>${{payload.team_prediction.expected_points}}</div>
          <div class="metric"><strong>Implied probability</strong><br>${{payload.market_signals.implied_probability}}</div>
          <div class="metric"><strong>Edge</strong><br>${{payload.betting_edge.edge}}</div>
          <div class="metric"><strong>Action</strong><br>${{payload.betting_edge.recommended_action}}</div>
          <div class="metric"><strong>Stake</strong><br>${{payload.betting_edge.recommended_stake}}</div>
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
      if (team) params.set("team", team);
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

    byId("player-form").addEventListener("submit", loadPlayer);
    byId("game-form").addEventListener("submit", loadGame);
  </script>
</body>
</html>"""
