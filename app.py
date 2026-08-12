import streamlit as st
import requests
import pandas as pd
import os
from scipy.stats import poisson

# Configuração de cache para chamadas à API
@st.cache_data(ttl=3600)
def fetch_api(endpoint, params, api_key):
    url = f"https://api-sports.io{endpoint}"
    headers = {"x-apisports-key": api_key}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if 'response' not in data or not data['response']:
            return []
        return data['response']
    except Exception as e:
        st.error(f"Erro na API ({endpoint}): {str(e)}")
        return []

def get_api_key():
    if 'api' in st.secrets and 'API_FOOTBALL_KEY' in st.secrets['api']:
        return st.secrets['api']['API_FOOTBALL_KEY']
    return os.getenv('API_FOOTBALL_KEY', '')

def calculate_poisson_prob(mean, threshold):
    if mean <= 0:
        return 0.0
    return float(1 - poisson.cdf(threshold - 1, mean))

def analisar_gols_equipe(fixtures, team_id):
    """Calcula a média de gols marcados e sofridos por uma equipe específica"""
    if not fixtures:
        return 0.0, 0.0, 0.0, 0.0
    
    gols_marcados_total = 0
    gols_sofridos_total = 0
    gols_marcados_ht = 0
    gols_sofridos_ht = 0
    
    for f in fixtures:
        is_home = f['teams']['home']['id'] == team_id
        
        # Gols do Tempo Total (FT)
        g_marcados_ft = f['goals']['home'] if is_home else f['goals']['away']
        g_sofridos_ft = f['goals']['away'] if is_home else f['goals']['home']
        gols_marcados_total += g_marcados_ft or 0
        gols_sofridos_total += g_sofridos_ft or 0
        
        # Gols do Primeiro Tempo (HT)
        g_marcados_ht = f['score']['halftime']['home'] if is_home else f['score']['halftime']['away']
        g_sofridos_ht = f['score']['halftime']['away'] if is_home else f['score']['halftime']['home']
        gols_marcados_ht += g_marcados_ht or 0
        gols_sofridos_ht += g_sofridos_ht or 0
        
    total_jogos = len(fixtures)
    return (gols_marcados_ht / total_jogos, gols_sofridos_ht / total_jogos, 
            gols_marcados_total / total_jogos, gols_sofridos_total / total_jogos)

def calcular_btts_poisson(lambda_casa, lambda_visitante):
    """Calcula Ambas Marcam baseado na probabilidade de nenhum time ficar zerado"""
    p_casa_zero = poisson.pmf(0, lambda_casa)
    p_visitante_zero = poisson.pmf(0, lambda_visitante)
    p_btts_nao = p_casa_zero + p_visitante_zero - (p_casa_zero * p_visitante_zero)
    return float(1 - p_btts_nao)

def calcular_placares_provaveis(lambda_casa, lambda_visitante, max_gols=4):
    """Calcula a probabilidade combinada dos placares mais comuns até max_gols"""
    placares = []
    for g_casa in range(max_gols + 1):
        for g_vis in range(max_gols + 1):
            prob_casa = poisson.pmf(g_casa, lambda_casa)
            prob_vis = poisson.pmf(g_vis, lambda_visitante)
            prob_combinada = prob_casa * prob_vis * 100
            placares.append({
                "Placar": f"{g_casa} x {g_vis}",
                "Probabilidade (%)": round(prob_combinada, 1)
            })
    placares_ordenados = sorted(placares, key=lambda x: x["Probabilidade (%)"], reverse=True)
    return placares_ordenados[:3]

def aplicar_estilos_coluna(df):
    """Retorna uma matriz de estilos CSS baseada nas regras de mercado solicitadas"""
    estilos = pd.DataFrame('', index=df.index, columns=df.columns)
    
    for idx, row in df.iterrows():
        if row['Over 0.5 HT (%)'] >= 80.0:
            estilos.at[idx, 'Over 0.5 HT (%)'] = 'background-color: #D1FAE5; color: #065F46; font-weight: bold;'
            
        if row['Over 1.5 FT (%)'] >= 75.0:
            estilos.at[idx, 'Over 1.5 FT (%)'] = 'background-color: #DBEAFE; color: #1E40AF; font-weight: bold;'
            
        if 55.0 <= row['BTTS Sim (%)'] <= 70.0:
            estilos.at[idx, 'BTTS Sim (%)'] = 'background-color: #FEF3C7; color: #92400E; font-weight: bold;'
            
        estilos.at[idx, 'Placares Mais Prováveis'] = 'background-color: #F3E8FF; color: #6B21A8;'
        
    return estilos

def main():
    st.set_page_config(page_title="Apostas de Valor do Dia", layout="wide")
    st.title("⚽ Predictor Inteligente - HT, FT, BTTS & Módulo de Prospecção")
    
    api_key = get_api_key()
    if not api_key:
        st.warning("Configure a chave API_FOOTBALL_KEY nos Secrets ou variável de ambiente.")
        return
    
    col1, col2, col3 = st.columns(3)
    with col1:
        league_id = st.number_input("ID da Liga", value=39)
    with col2:
        season = st.number_input("Temporada", value=2024)
    with col3:
        min_prob = st.slider("Filtrar por Probabilidade Mínima Geral (%)", 50, 95, 65)
        
    show_all = st.checkbox("Mostrar todos os jogos na grade geral")
    
    if "df_resultados" not in st.session_state:
        st.session_state.df_resultados = None
    if "lista_resultados" not in st.session_state:
        st.session_state.lista_resultados = []

    if st.button("🚀 Executar Análise e Triagem"):
        with st.spinner("Processando banco de dados e aplicando regras de colação estatística..."):
            fixtures = fetch_api("fixtures", {"league": league_id, "season": season, "next": 8}, api_key)
            
            if not fixtures:
                st.info("Nenhum jogo futuro agendado para esta liga.")
                return
            
            results = []
            for fix in fixtures:
                home_id = fix['teams']['home']['id']
                away_id = fix['teams']['away']['id']
                
                last_home = fetch_api("fixtures", {"team": home_id, "last": 8, "status": "FT"}, api_key)
                last_away = fetch_api("fixtures", {"team": away_id, "last": 8, "status": "FT"}, api_key)
                
                home_m_ht, home_s_ht, home_m_ft, home_s_ft = analisar_gols_equipe(last_home, home_id)
                away_m_ht, away_s_ht, away_m_ft, away_s_ft = analisar_gols_equipe(last_away, away_id)
                
                exp_gols_casa_ht = (home_m_ht + away_s_ht) / 2
                exp_gols_visitante_ht = (away_m_ht + home_s_ht) / 2
                avg_goals_ht = exp_gols_casa_ht + exp_gols_visitante_ht
                
                exp_gols_casa_ft = (home_m_ft + away_s_ft) / 2
                exp_gols_visitante_ft = (away_m_ft + home_s_ft) / 2
                avg_goals_ft = exp_gols_casa_ft + exp_gols_visitante_ft
                
                p_over05_ht = calculate_poisson_prob(avg_goals_ht, 0.5) * 100
                p_over15_ft = calculate_poisson_prob(avg_goals_ft, 1.5) * 100
                p_btts = calcular_btts_poisson(exp_gols_casa_ft, exp_gols_visitante_ft) * 100
                
                top_placares = calcular_placares_provaveis(exp_gols_casa_ft, exp_gols_visitante_ft)
                texto_placares = " | ".join([f"{p['Placar']} ({p['Probabilidade (%)']}% )" for p in top_placares])
                
                if (p_over05_ht >= min_prob or p_over15_ft >= min_prob or p_btts >= min_prob) or show_all:
                    results.append({
                        "Jogo": f"{fix['teams']['home']['name']} vs {fix['teams']['away']['name']}",
                        "Data": fix['fixture']['date'][:10],
                        "Over 0.5 HT (%)": round(p_over05_ht, 1),
                        "Over 1.5 FT (%)": round(p_over15_ft, 1),
                        "BTTS Sim (%)": round(p_btts, 1),
                        "Placares Mais Prováveis": texto_placares
                    })
            
            if results:
                st.session_state.lista_resultados = results
                st.session_state.df_resultados = pd.DataFrame(results)
            else:
                st.session_state.df_resultados = None
                st.info("Nenhuma partida atingiu os parâmetros de probabilidade calculados.")

    # Renderização Condicional da Interface
    if st.session_state.df_resultados is not None:
        df_base = st.session_state.df_resultados
        
        # ----------------------------------------------------
        # BLOCO 1: SELEÇÃO EXCLUSIVA - APOSTAS DE VALOR DO DIA
        # ----------------------------------------------------
        st.markdown("---")
        st.subheader("🎯 Filtro de Elite: Apostas de Valor do Dia")
        st.caption("Partidas que cumprem as 3 condições de excelência matemática simultaneamente.")
        
        # Criação da máscara lógica rigorosa
        mascara_valor = (
            (df_base['Over 0.5 HT (%)'] >= 80.0) & 
            (df_base['Over 1.5 FT (%)'] >= 75.0) & 
            (df_base['BTTS Sim (%)'] >= 55.0)
        )
        df_apostas_valor = df_base[mascara_valor].copy()
        
        if not df_apostas_valor.empty:
            # Mostra a lista premium aplicando as mesmas estilizações de cores
            df_valor_estilizado = df_apostas_valor.style.apply(aplicar_estilos_coluna, axis=None)
            st.dataframe(df_valor_estilizado, use_container_width=True)
            
            # Botão de download rápido exclusivo para a Lista Premium do Dia
            csv_valor = df_apostas_valor.to_csv(index=False)
            st.download_button("📥 Baixar Apenas Dicas de Elite (CSV)", csv_valor, "apostas_valor_premium.csv", "text/csv")
        else:
            st.info("Nenhum confronto analisado cumpre os critérios combinados de elite para hoje. Paciência é uma virtude no mercado.")
            
        # ----------------------------------------------------
        # BLOCO 2: GRADE GERAL DE JOGOS ANALISADOS
        # ----------------------------------------------------
        st.markdown("---")
        st.subheader("📋 Grade Geral de Jogos Analisados")
        df_geral_estilizado = df_base.style.apply(aplicar_estilos_coluna, axis=None)
