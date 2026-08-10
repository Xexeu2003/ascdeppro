app.py
import os
import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import time
from collections import defaultdict
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

st.set_page_config(page_title="Football Analysis", layout="wide")
st.title("Football Analysis Simulator (API-Football v3)")
st.warning("AVISO: Todas as probabilidades sao estimativas estatisticas baseadas em medias historicas. Nao constituem previsao garantida.")

def get_api_key() -> str:
    key = st.secrets.get("API_FOOTBALL_KEY") or os.getenv("API_FOOTBALL_KEY")
    if not key:
        st.error("API_FOOTBALL_KEY nao encontrada.")
        st.stop()
    return key

@st.cache_data(ttl=3600)
def api_request(endpoint: str, params: Dict[str, Any], retries: int = 3) -> Dict[str, Any]:
    url = f"https://v3.football.api-sports.io/{endpoint}"
    headers = {"x-apisports-key": get_api_key()}
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            time.sleep(1)
        except Exception as e:
            if attempt == retries - 1:
                st.error(f"Erro na requisicao: {str(e)}")
    return {"response": []}

def get_fixtures(league_id: int, season: int, from_date: str, to_date: str) -> List[Dict[str, Any]]:
    params = {"league": league_id, "season": season, "from": from_date, "to": to_date}
    data = api_request("fixtures", params)
    return data.get("response", [])

def get_team_stats(team_id: int, league_id: int, season: int) -> Dict[str, Any]:
    params = {"team": team_id, "league": league_id, "season": season}
    data = api_request("teams/statistics", params)
    return data.get("response", {})

def get_h2h(team1: int, team2: int) -> List[Dict[str, Any]]:
    params = {"h2h": f"{team1}-{team2}", "last": 10}
    data = api_request("fixtures/headtohead", params)
    return data.get("response", [])

def calculate_poisson_lambda(avg_for: float, avg_against: float, league_avg: float) -> float:
    return (avg_for * avg_against) / league_avg if league_avg > 0 else 1.0

def poisson_prob(lmbda: float, k: int) -> float:
    from math import exp, factorial
    return (lmbda ** k * exp(-lmbda)) / factorial(k)

def compute_probabilities(fixture: Dict[str, Any], stats_home: Dict, stats_away: Dict, h2h: List, league_avg_goals: float = 2.7) -> Dict[str, float]:
    home_id = fixture["teams"]["home"]["id"]
    away_id = fixture["teams"]["away"]["id"]
    # Gols FT lambda
    home_attack = stats_home.get("goals", {}).get("for", {}).get("average", 1.3)
    away_def = stats_away.get("goals", {}).get("against", {}).get("average", 1.4)
    lambda_ft = calculate_poisson_lambda(home_attack, away_def, league_avg_goals)
    # HT lambda approx 0.45 of FT
    lambda_ht = lambda_ft * 0.45
    p_over05_ht = 1 - poisson_prob(lambda_ht, 0)
    p_over15_ft = 1 - sum(poisson_prob(lambda_ft, k) for k in range(2))
    p_btts = 1 - (poisson_prob(lambda_ft * 0.55, 0) * poisson_prob(lambda_ft * 0.45, 0))
    # Cantos e cartoes com fallback
    corner_lambda = 10.5  # conservative fallback
    card_lambda = 4.8
    if stats_home and stats_away:
        corner_lambda = (stats_home.get("corners", 10.0) + stats_away.get("corners_against", 10.0)) / 2
        card_lambda = (stats_home.get("cards", 4.5) + stats_away.get("cards_against", 5.0)) / 2
    p_over85_corners = 1 - sum(poisson_prob(corner_lambda, k) for k in range(9))
    p_over35_cards = 1 - sum(poisson_prob(card_lambda, k) for k in range(4))
    return {
        "Over 0.5 HT": round(p_over05_ht * 100, 1),
        "Over 1.5 FT": round(p_over15_ft * 100, 1),
        "BTTS": round(p_btts * 100, 1),
        "Over 8.5 Corners": round(p_over85_corners * 100, 1),
        "Over 3.5 Cards": round(p_over35_cards * 100, 1)
    }

def main():
    league_id = st.sidebar.number_input("League ID", value=71)
    season = st.sidebar.number_input("Season", value=2024)
    from_date = st.sidebar.date_input("From", datetime.now() - timedelta(days=1))
    to_date = st.sidebar.date_input("To", datetime.now() + timedelta(days=7))
    show_all = st.sidebar.checkbox("Show all matches (ignore 75% filter)")
    if st.button("Fetch Fixtures"):
        fixtures = get_fixtures(league_id, season, from_date.isoformat(), to_date.isoformat())
        results = []
        for fix in fixtures:
            home = fix["teams"]["home"]["id"]
            away = fix["teams"]["away"]["id"]
            stats_h = get_team_stats(home, league_id, season)
            stats_a = get_team_stats(away, league_id, season)
            h2h = get_h2h(home, away)
            probs = compute_probabilities(fix, stats_h, stats_a, h2h)
            all_above = all(v >= 75 for v in probs.values())
            if all_above or show_all:
                results.append({
                    "Match": f"{fix['teams']['home']['name']} vs {fix['teams']['away']['name']}",
                    "Date": fix["fixture"]["date"],
                    "League": fix["league"]["name"],
                    **probs
                })
        if results:
            st.dataframe(results)
            if st.button("Export CSV"):
                import csv
                output = "\n".join([",".join(map(str, r.values())) for r in results])
                st.download_button("Download CSV", output, "results.csv")
            if REPORTLAB_AVAILABLE and st.button("Export PDF"):
                buffer = BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=letter)
                elements = []
                data = [["Match", "Date", "Over 0.5 HT", "Over 1.5 FT", "BTTS", "Over 8.5 Corners", "Over 3.5 Cards"]]
                for r in results:
                    data.append([r["Match"], r["Date"], r["Over 0.5 HT"], r["Over 1.5 FT"], r["BTTS"], r["Over 8.5 Corners"], r["Over 3.5 Cards"]])
                t = Table(data)
                t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.grey)]))
                elements.append(t)
                doc.build(elements)
                st.download_button("Download PDF", buffer.getvalue(), "results.pdf")
        else:
            st.info("No matches met the criteria.")

if __name__ == "__main__":
    main()

requirements.txt
streamlit==1.37.0
requests==2.32.3
reportlab==4.0.7

README.md
# Football Analysis Simulator

1. Clone repo
2. pip install -r requirements.txt
3. Add API key to .streamlit/secrets.toml
4. streamlit run app.py

.streamlit/secrets.toml.example
API_FOOTBALL_KEY = "SUA_CHAVE_AQUI"

.gitignore
__pycache__/
.streamlit/secrets.toml
*.pdf
*.csv

