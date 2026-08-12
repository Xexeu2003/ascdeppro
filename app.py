import io
import os
from datetime import date
from math import floor
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from scipy.stats import poisson


# URL oficial da API-Football v3.
BASE_URL = "https://v3.football.api-sports.io"

# Ligas iniciais. O usuário pode informar outros IDs no campo lateral.
LEAGUES = {
    "Finlândia - Veikkausliiga": 244,
    "Dinamarca - Superliga": 119,
    "Islândia - Úrvalsdeild": 166,
    "Holanda - Eredivisie": 88,
    "Holanda - Eerste Divisie": 89,
    "Polônia - Ekstraklasa": 106,
    "Hungria - NB I": 271,
    "Sérvia - Super Liga": 286,
    "EUA - MLS": 253,
    "Colômbia - Primera A": 239,
    "Argentina - Liga Profesional": 128,
}


def get_api_key() -> str:
    """Lê a chave do Streamlit Secrets ou da variável de ambiente."""
    try:
        key = st.secrets.get("API_FOOTBALL_KEY", "")
        if key:
            return str(key).strip()
        # Também aceita o formato [api] usado em configurações antigas.
        api_section = st.secrets.get("api", {})
        if isinstance(api_section, dict):
            return str(api_section.get("API_FOOTBALL_KEY", "")).strip()
    except Exception:
        pass
    return os.getenv("API_FOOTBALL_KEY", "").strip()


@st.cache_data(ttl=1800, show_spinner=False)
def api_get(endpoint: str, params: Dict[str, Any], api_key: str) -> List[Dict[str, Any]]:
    """Consulta a API e guarda a resposta por 30 minutos para economizar requisições."""
    try:
        response = requests.get(
            f"{BASE_URL}/{endpoint}",
            headers={"x-apisports-key": api_key},
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("errors") or {}
        if errors:
            raise RuntimeError(str(errors))
        return payload.get("response") or []
    except requests.RequestException as exc:
        st.warning(f"Falha de comunicação com a API em {endpoint}: {exc}")
    except Exception as exc:
        st.warning(f"A API retornou um erro em {endpoint}: {exc}")
    return []


def completed(fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mantém somente partidas encerradas com placar disponível."""
    result = []
    for fixture in fixtures:
        status = fixture.get("fixture", {}).get("status", {}).get("short", "")
        goals = fixture.get("goals", {})
        if status in {"FT", "AET", "PEN"} and goals.get("home") is not None and goals.get("away") is not None:
            result.append(fixture)
    return result


def stat_value(fixture: Dict[str, Any], team_id: int, names: set) -> Optional[float]:
    """Obtém um indicador da resposta de /fixtures/statistics."""
    for team_block in fixture.get("statistics", []):
        if team_block.get("team", {}).get("id") != team_id:
            continue
        for item in team_block.get("statistics", []):
            if item.get("type") in names:
                value = item.get("value")
                if value is None:
                    return None
                if isinstance(value, str):
                    value = value.replace("%", "").strip()
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
    return None


def fixture_metric(fixture: Dict[str, Any], team_id: int, metric: str) -> Optional[float]:
    names = {
        "corners": {"Corner Kicks", "Corners"},
        "cards": {"Yellow Cards", "Cards"},
    }
    return stat_value(fixture, team_id, names[metric])


def team_averages(fixtures: List[Dict[str, Any]], team_id: int) -> Dict[str, float]:
    """Calcula médias de gols HT/FT, escanteios e cartões da equipe."""
    rows = []
    for f in completed(fixtures):
        home = f.get("teams", {}).get("home", {})
        away = f.get("teams", {}).get("away", {})
        is_home = home.get("id") == team_id
        goals = f.get("goals", {})
        ht = f.get("score", {}).get("halftime", {})
        gf = goals.get("home" if is_home else "away")
        ga = goals.get("away" if is_home else "home")
        hgf = ht.get("home" if is_home else "away")
        hga = ht.get("away" if is_home else "home")
        if gf is None or ga is None:
            continue
        rows.append({
            "gf_ft": float(gf), "ga_ft": float(ga),
            "gf_ht": float(hgf or 0), "ga_ht": float(hga or 0),
            "corners": fixture_metric(f, team_id, "corners"),
            "cards": fixture_metric(f, team_id, "cards"),
        })
    if not rows:
        return {k: np.nan for k in ["gf_ft", "ga_ft", "gf_ht", "ga_ht", "corners", "cards"]}
    frame = pd.DataFrame(rows)
    return {column: float(frame[column].dropna().mean()) if frame[column].notna().any() else np.nan for column in frame.columns}


def league_averages(fixtures: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calcula médias da competição; é usada como referência do modelo."""
    all_rows = []
    for f in completed(fixtures):
        goals = f.get("goals", {})
        ht = f.get("score", {}).get("halftime", {})
        if goals.get("home") is None or goals.get("away") is None:
            continue
        all_rows.append({
            "gf_ft": (float(goals["home"]) + float(goals["away"])) / 2,
            "gf_ht": (float(ht.get("home") or 0) + float(ht.get("away") or 0)) / 2,
        })
    if not all_rows:
        return {"gf_ft": np.nan, "gf_ht": np.nan}
    frame = pd.DataFrame(all_rows)
    return {column: float(frame[column].mean()) for column in frame.columns}


def blend(values: List[Tuple[float, float]]) -> float:
    """Combina valores com pesos, ignorando dados ausentes e renormalizando pesos."""
    valid = [(value, weight) for value, weight in values if pd.notna(value) and value >= 0]
    if not valid:
        return np.nan
    total_weight = sum(weight for _, weight in valid)
    return sum(value * weight for value, weight in valid) / total_weight


def over_probability(lamb: float, line: float) -> float:
    """P(X > linha) para X ~ Poisson(lambda). Ex.: linha 1.5 significa X >= 2."""
    if pd.isna(lamb) or lamb <= 0:
        return np.nan
    minimum = floor(line) + 1
    return float(1 - poisson.cdf(minimum - 1, lamb))


def btts_probability(lambda_home: float, lambda_away: float) -> float:
    if pd.isna(lambda_home) or pd.isna(lambda_away) or lambda_home < 0 or lambda_away < 0:
        return np.nan
    return float((1 - np.exp(-lambda_home)) * (1 - np.exp(-lambda_away)))


def top_scores(lambda_home: float, lambda_away: float, limit: int = 3) -> str:
    if pd.isna(lambda_home) or pd.isna(lambda_away):
        return "Dados insuficientes"
    scores = []
    for home_goals in range(0, 7):
        for away_goals in range(0, 7):
            probability = poisson.pmf(home_goals, lambda_home) * poisson.pmf(away_goals, lambda_away)
            scores.append((probability, f"{home_goals}x{away_goals}"))
    scores.sort(reverse=True)
    return " | ".join(f"{score} ({prob * 100:.1f}%)" for prob, score in scores[:limit])


def pdf_bytes(frame: pd.DataFrame) -> bytes:
    """Gera um PDF simples com a tabela filtrada."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Análise estatística de futebol", styles["Title"]), Spacer(1, 10)]
    export = frame.copy().astype(str)
    data = [list(export.columns)] + export.values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(table)
    document.build(elements)
    return buffer.getvalue()


def main() -> None:
    st.set_page_config(page_title="Analisador de Futebol", page_icon="⚽", layout="wide")
    st.title("⚽ Analisador de Futebol — Poisson")
    st.caption("Estimativas estatísticas; não são garantia de resultado nem recomendação de aposta.")

    api_key = get_api_key()
    if not api_key:
        st.error("Configure API_FOOTBALL_KEY em Streamlit Secrets ou nas variáveis de ambiente.")
        st.code('API_FOOTBALL_KEY = "sua_chave_aqui"', language="toml")
        st.stop()

    with st.sidebar:
        st.header("Configuração")
        league_name = st.selectbox("Liga", list(LEAGUES.keys()))
        custom_id = st.number_input("Ou informe outro ID de liga (0 = usar a lista)", min_value=0, value=0, step=1)
        league_id = int(custom_id or LEAGUES[league_name])
        season = st.number_input("Temporada", min_value=2010, max_value=2035, value=2024, step=1)
        games_to_analyze = st.slider("Próximos jogos", 1, 20, 8)
        history_size = st.slider("Últimos jogos por equipe", 5, 10, 10)
        min_probability = st.slider("Probabilidade mínima (%)", 50, 95, 75)
        corners_line = st.selectbox("Linha de escanteios", [7.5, 8.5, 9.5, 10.5], index=1)
        cards_line = st.selectbox("Linha de cartões", [2.5, 3.5, 4.5, 5.5], index=1)
        strict_filter = st.checkbox("Exigir todos os mercados ≥ mínimo", value=False)

    if "analysis" not in st.session_state:
        st.session_state.analysis = None

    if st.button("🔎 Buscar e analisar", type="primary"):
        with st.spinner("Buscando partidas e calculando as probabilidades..."):
            upcoming = api_get("fixtures", {"league": league_id, "season": int(season), "next": int(games_to_analyze)}, api_key)
            upcoming = [f for f in upcoming if f.get("fixture", {}).get("status", {}).get("short") in {"NS", "TBD"}]
            season_fixtures = api_get("fixtures", {"league": league_id, "season": int(season)}, api_key)
            league_avg = league_averages(season_fixtures)
            rows = []

            for match in upcoming:
                home = match.get("teams", {}).get("home", {})
                away = match.get("teams", {}).get("away", {})
                home_id, away_id = home.get("id"), away.get("id")
                if not home_id or not away_id:
                    continue
                home_history = api_get("fixtures", {"team": home_id, "last": history_size}, api_key)
                away_history = api_get("fixtures", {"team": away_id, "last": history_size}, api_key)
                h2h_history = api_get("fixtures", {"h2h": f"{home_id}-{away_id}", "last": 10}, api_key)
                h = team_averages(home_history, home_id)
                a = team_averages(away_history, away_id)
                hh = league_averages(h2h_history)

                # Mistura últimos jogos, liga e H2H. H2H é usado apenas quando existe.
                lambda_ht = blend([(h["gf_ht"], .35), (a["ga_ht"], .35), (league_avg["gf_ht"], .20), (hh["gf_ht"], .10)]) * 2
                lambda_ft = blend([(h["gf_ft"], .35), (a["ga_ft"], .35), (league_avg["gf_ft"], .20), (hh["gf_ft"], .10)]) * 2
                lambda_home_ft = blend([(h["gf_ft"], .40), (a["ga_ft"], .40), (league_avg["gf_ft"], .20)])
                lambda_away_ft = blend([(a["gf_ft"], .40), (h["ga_ft"], .40), (league_avg["gf_ft"], .20)])
                corner_lambda = blend([(h["corners"], .45), (a["corners"], .45)])
                card_lambda = blend([(h["cards"], .45), (a["cards"], .45)])

                probabilities = {
                    "Over 0.5 HT (%)": over_probability(lambda_ht, .5),
                    "Over 1.5 FT (%)": over_probability(lambda_ft, 1.5),
                    "BTTS (%)": btts_probability(lambda_home_ft, lambda_away_ft),
                    f"Over {corners_line} cantos (%)": over_probability(corner_lambda, corners_line),
                    f"Over {cards_line} cartões (%)": over_probability(card_lambda, cards_line),
                }
                values = {key: round(value * 100, 1) if pd.notna(value) else np.nan for key, value in probabilities.items()}
                selected = [value for value in values.values() if pd.notna(value)]
                qualifies = all(value >= min_probability for value in selected) if strict_filter else any(value >= min_probability for value in selected)
                if qualifies:
                    rows.append({
                        "Jogo": f"{home.get('name', '?')} x {away.get('name', '?')}",
                        "Data": match.get("fixture", {}).get("date", "")[:16].replace("T", " "),
                        **values,
                        "Placares prováveis": top_scores(lambda_home_ft, lambda_away_ft),
                    })

            st.session_state.analysis = pd.DataFrame(rows)

    if st.session_state.analysis is not None:
        frame = st.session_state.analysis
        if frame.empty:
            st.warning("Nenhuma partida atingiu o filtro. Reduza a linha ou a probabilidade mínima.")
        else:
            st.success(f"{len(frame)} partida(s) encontrada(s).")
            st.dataframe(frame, use_container_width=True, hide_index=True)
            st.download_button("📥 Baixar CSV", frame.to_csv(index=False).encode("utf-8-sig"), "analise_futebol.csv", "text/csv")
            st.download_button("📄 Baixar PDF", pdf_bytes(frame), "analise_futebol.pdf", "application/pdf")


if __name__ == "__main__":
    main()
