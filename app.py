import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from scipy.stats import poisson
import math
import json

API_BASE = 'https://v3.football.api-sports.io'

@st.cache_data(ttl=3600)
def get_api_key():
    if 'API_FOOTBALL_KEY' in st.secrets:
        return st.secrets['API_FOOTBALL_KEY']
    return os.environ.get('API_FOOTBALL_KEY', '')

def get_headers():
    key = get_api_key()
    if not key:
        st.error('Chave API_FOOTBALL_KEY não configurada.')
        st.stop()
    return {'x-apisports-key': key}

@st.cache_data(ttl=3600)
def api_get(endpoint, params):
    url = f'{API_BASE}/{endpoint}'
    try:
        resp = requests.get(url, headers=get_headers(), params=params, timeout=15)
        if resp.status_code == 401:
            st.error('Erro 401: Chave inválida.')
            return None
        if resp.status_code == 403:
            st.error('Erro 403: Acesso negado.')
            return None
        if resp.status_code == 429:
            st.error('Erro 429: Limite de requisições excedido.')
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f'Falha na API: {e}')
        return None

@st.cache_data(ttl=3600)
def fetch_league_fixtures(league_id, season, limit):
    data = api_get('fixtures', {'league': league_id, 'season': season, 'next': limit, 'status': 'NS'})
    return data.get('response', []) if data else []

@st.cache_data(ttl=3600)
def fetch_last_games(team_id, season, count=10):
    data = api_get('fixtures', {'team': team_id, 'season': season, 'last': count, 'status': 'FT'})
    return data.get('response', []) if data else []

@st.cache_data(ttl=3600)
def fetch_h2h(home_id, away_id, count=5):
    data = api_get('fixtures/headtohead', {'h2h': f'{home_id}-{away_id}', 'last': count})
    return data.get('response', []) if data else []

@st.cache_data(ttl=3600)
def fetch_stats(fixture_id):
    data = api_get('fixtures/statistics', {'fixture': fixture_id})
    return data.get('response', []) if data else []

@st.cache_data(ttl=3600)
def fetch_league_finished(league_id, season, limit=50):
    data = api_get('fixtures', {'league': league_id, 'season': season, 'last': limit, 'status': 'FT'})
    return data.get('response', []) if data else []

def extrair_gols(game, is_home):
    try:
        goals = game.get('goals', {})
        val = goals.get('home' if is_home else 'away')
        return val if val is not None else None
    except:
        return None

def extrair_ht_goals(game, is_home):
    try:
        score = game.get('score', {}).get('halftime', {})
        val = score.get('home' if is_home else 'away')
        return val if val is not None else None
    except:
        return None

def extrair_estat(game_stats, team_id, key):
    try:
        for s in game_stats:
            if s['team']['id'] == team_id:
                for stat in s.get('statistics', []):
                    if stat['type'] == key:
                        val = stat.get('value')
                        return val if val is not None else None
        return None
    except:
        return None

def calcular_medias_liga(fixtures_liga):
    gols_ft, gols_ht, cantos, cartoes = [], [], [], []
    for g in fixtures_liga:
        gh = extrair_gols(g, True)
        ga = extrair_gols(g, False)
        if gh is not None and ga is not None:
            gols_ft.append(gh + ga)
        hth = extrair_ht_goals(g, True)
        hta = extrair_ht_goals(g, False)
        if hth is not None and hta is not None:
            gols_ht.append(hth + hta)
        stats = fetch_stats(g['fixture']['id'])
        ch = extrair_estat(stats, g['teams']['home']['id'], 'Corner Kicks') if stats else None
        ca = extrair_estat(stats, g['teams']['away']['id'], 'Corner Kicks') if stats else None
        if ch is not None and ca is not None:
            cantos.append(ch + ca)
        crh = extrair_estat(stats, g['teams']['home']['id'], 'Yellow Cards') if stats else None
        cra = extrair_estat(stats, g['teams']['away']['id'], 'Yellow Cards') if stats else None
        if crh is not None and cra is not None:
            cartoes.append(crh + cra)
    return {
        'media_gols_ft': sum(gols_ft)/len(gols_ft) if gols_ft else None,
        'media_ht': sum(gols_ht)/len(gols_ht) if gols_ht else None,
        'media_cantos': sum(cantos)/len(cantos) if cantos else None,
        'media_cartoes': sum(cartoes)/len(cartoes) if cartoes else None
    }

def calcular_medias_ultimos(games, team_id):
    gols_ft, gols_ht, cantos, cartoes = [], [], [], []
    for g in games:
        is_home = g['teams']['home']['id'] == team_id
        gh = extrair_gols(g, is_home)
        ga = extrair_gols(g, not is_home)
        if gh is not None and ga is not None:
            gols_ft.append(gh + ga)
        hth = extrair_ht_goals(g, is_home)
        hta = extrair_ht_goals(g, not is_home)
        if hth is not None and hta is not None:
            gols_ht.append(hth + hta)
        stats = fetch_stats(g['fixture']['id'])
        c = extrair_estat(stats, team_id, 'Corner Kicks') if stats else None
        if c is not None:
            cantos.append(c)
        cr = extrair_estat(stats, team_id, 'Yellow Cards') if stats else None
        if cr is not None:
            cartoes.append(cr)
    return {
        'media_gols_ft': sum(gols_ft)/len(gols_ft) if gols_ft else None,
        'media_ht': sum(gols_ht)/len(gols_ht) if gols_ht else None,
        'media_cantos': sum(cantos)/len(cantos) if cantos else None,
        'media_cartoes': sum(cartoes)/len(cartoes) if cartoes else None
    }

def calcular_medias_h2h(games, home_id, away_id):
    gols_ft, gols_ht, cantos, cartoes = [], [], [], []
    for g in games:
        is_home = g['teams']['home']['id'] == home_id
        gh = extrair_gols(g, is_home)
        ga = extrair_gols(g, not is_home)
        if gh is not None and ga is not None:
            gols_ft.append(gh + ga)
        hth = extrair_ht_goals(g, is_home)
        hta = extrair_ht_goals(g, not is_home)
        if hth is not None and hta is not None:
            gols_ht.append(hth + hta)
        stats = fetch_stats(g['fixture']['id'])
        ch = extrair_estat(stats, home_id, 'Corner Kicks') if stats else None
        ca = extrair_estat(stats, away_id, 'Corner Kicks') if stats else None
        if ch is not None and ca is not None:
            cantos.append(ch + ca)
        crh = extrair_estat(stats, home_id, 'Yellow Cards') if stats else None
        cra = extrair_estat(stats, away_id, 'Yellow Cards') if stats else None
        if crh is not None and cra is not None:
            cartoes.append(crh + cra)
    return {
        'media_gols_ft': sum(gols_ft)/len(gols_ft) if gols_ft else None,
        'media_ht': sum(gols_ht)/len(gols_ht) if gols_ht else None,
        'media_cantos': sum(cantos)/len(cantos) if cantos else None,
        'media_cartoes': sum(cartoes)/len(cartoes) if cartoes else None
    }

def estimar_lambda(med_liga, med_ult, med_h2h, peso_liga=0.3, peso_ult=0.5, peso_h2h=0.2):
    vals = []
    pesos = []
    if med_liga is not None:
        vals.append(med_liga)
        pesos.append(peso_liga)
    if med_ult is not None:
        vals.append(med_ult)
        pesos.append(peso_ult)
    if med_h2h is not None:
        vals.append(med_h2h)
        pesos.append(peso_h2h)
    if not vals:
        return None
    total_peso = sum(pesos)
    if total_peso == 0:
        return None
    return sum(v * (p / total_peso) for v, p in zip(vals, pesos))

def calcular_lambdas(home_id, away_id, season, num_ult, num_h2h, league_id):
    liga_games = fetch_league_finished(league_id, season)
    med_liga = calcular_medias_liga(liga_games)
    last_home = fetch_last_games(home_id, season, num_ult)
    last_away = fetch_last_games(away_id, season, num_ult)
    med_ult_home = calcular_medias_ultimos(last_home, home_id)
    med_ult_away = calcular_medias_ultimos(last_away, away_id)
    h2h_games = fetch_h2h(home_id, away_id, num_h2h)
    med_h2h = calcular_medias_h2h(h2h_games, home_id, away_id)
    lam_ft = estimar_lambda(med_liga.get('media_gols_ft'), (med_ult_home.get('media_gols_ft', 0) + med_ult_away.get('media_gols_ft', 0)) / 2 if med_ult_home.get('media_gols_ft') and med_ult_away.get('media_gols_ft') else None, med_h2h.get('media_gols_ft'))
    lam_ht = estimar_lambda(med_liga.get('media_ht'), (med_ult_home.get('media_ht', 0) + med_ult_away.get('media_ht', 0)) / 2 if med_ult_home.get('media_ht') and med_ult_away.get('media_ht') else None, med_h2h.get('media_ht'))
    lam_c = estimar_lambda(med_liga.get('media_cantos'), (med_ult_home.get('media_cantos', 0) + med_ult_away.get('media_cantos', 0)) / 2 if med_ult_home.get('media_cantos') and med_ult_away.get('media_cantos') else None, med_h2h.get('media_cantos'))
    lam_cards = estimar_lambda(med_liga.get('media_cartoes'), (med_ult_home.get('media_cartoes', 0) + med_ult_away.get('media_cartoes', 0)) / 2 if med_ult_home.get('media_cartoes') and med_ult_away.get('media_cartoes') else None, med_h2h.get('media_cartoes'))
    return {'media_gols_ft': lam_ft, 'media_ht': lam_ht, 'media_cantos': lam_c, 'media_cartoes': lam_cards}

def aplicar_poisson(medias, corner_line, card_line, home_attack=None, away_def=None, away_attack=None, home_def=None):
    probs = {}
    if medias['media_ht'] is not None:
        lam_ht = medias['media_ht']
        probs['Over 0.5 HT'] = 1 - poisson.pmf(0, lam_ht)
    if medias['media_gols_ft'] is not None:
        lam_ft = medias['media_gols_ft']
        probs['Over 1.5 FT'] = 1 - (poisson.pmf(0, lam_ft) + poisson.pmf(1, lam_ft))
        if home_attack is not None and away_def is not None and away_attack is not None and home_def is not None:
            lam_home = home_attack * away_def
            lam_away = away_attack * home_def
            p00 = poisson.pmf(0, lam_home) * poisson.pmf(0, lam_away)
            probs['BTTS'] = 1 - poisson.pmf(0, lam_home) - poisson.pmf(0, lam_away) + p00
    if medias['media_cantos'] is not None:
        lam_c = medias['media_cantos']
        probs[f'Over {corner_line} Cantos'] = 1 - sum(poisson.pmf(k, lam_c) for k in range(int(corner_line) + 1))
    if medias['media_cartoes'] is not None:
        lam_cards = medias['media_cartoes']
        probs[f'Over {card_line} Cartões'] = 1 - sum(poisson.pmf(k, lam_cards) for k in range(int(card_line) + 1))
    return probs

def main():
    st.title('Previsor de Apostas - Futebol (Poisson)')
    ligas = {
        'Finlândia Veikkausliiga': 244,
        'Dinamarca Superliga': 119,
        'Islândia Úrvalsdeild': 166,
        'Holanda Eredivisie': 88,
        'Holanda Eerste Divisie': 89,
        'Alemanha Bundesliga 2': 79,
        'Alemanha 3. Liga': 80,
        'Polônia Ekstraklasa': 106,
        'Hungria NB I': 271,
        'Sérvia Super Liga': 286,
        'EUA MLS': 253,
        'Colômbia Primera A': 239,
        'Argentina Liga Profesional': 128
    }
    liga_nome = st.selectbox('Selecione a Liga', list(ligas.keys()))
    league_id = ligas[liga_nome]
    season = st.number_input('Temporada', value=2024, min_value=2020)
    num_futuros = st.slider('Jogos futuros', 5, 50, 20)
    num_ult = st.slider('Últimos jogos por equipe', 5, 20, 10)
    num_h2h = st.slider('H2H', 3, 10, 5)
    corner_line = st.number_input('Linha de cantos', value=10.5)
    card_line = st.number_input('Linha de cartões', value=4.5)
    min_prob = st.slider('Limite mínimo probabilidade', 0.5, 0.95, 0.6)
    modo = st.radio('Modo', ['Qualquer mercado', 'Todos os mercados'])
    if st.button('Limpar cache'):
        st.cache_data.clear()
        st.success('Cache limpo.')
    if st.button('Buscar e Calcular'):
        fixtures = fetch_league_fixtures(league_id, season, num_futuros)
        dados = []
        for fix in fixtures:
            home = fix['teams']['home']['name']
            away = fix['teams']['away']['name']
            date = fix['fixture']['date']
            home_id = fix['teams']['home']['id']
            away_id = fix['teams']['away']['id']
            medias = calcular_lambdas(home_id, away_id, season, num_ult, num_h2h, league_id)
            if any(v is None for v in medias.values()):
                st.warning(f'Dados insuficientes para {home} x {away}')
                continue
            probs = aplicar_poisson(medias, corner_line, card_line)
            row = {
                'Jogo': f'{home} x {away}',
                'Data': date,
                'Amostra': f'Últimos {num_ult} + Liga + H2H {num_h2h}',
                'Lambdas': str(medias),
                'Probabilidades': {k: f'{v:.2%}' for k, v in probs.items()}
            }
            dados.append(row)
        if not dados:
            st.warning('Nenhum jogo com dados suficientes.')
            return
        df = pd.DataFrame(dados)
        st.dataframe(df)
        st.download_button('Download CSV', df.to_csv(index=False), 'resultados.csv')
        if st.button('Gerar PDF'):
            doc = SimpleDocTemplate('relatorio.pdf', pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            elements.append(Paragraph('Relatório de Probabilidades', styles['Heading1']))
            table_data = [['Jogo', 'Data', 'Probabilidades']]
            for r in dados:
                table_data.append([r['Jogo'], r['Data'], str(r['Probabilidades'])])
            t = Table(table_data)
            t.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 8), ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
            elements.append(t)
            doc.build(elements)
            st.success('PDF gerado.')
    with st.expander('Diagnóstico e Notas Metodológicas'):
        st.write('Pesos: 50% últimos, 30% liga, 20% H2H. Redistribuição automática quando dados ausentes. Poisson via scipy. Nunca substitui ausência por zero.')

if __name__ == '__main__':
    main()
