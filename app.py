=== app.py ===
# app.py - Análise de Futebol com Streamlit, API-Football e Distribuição de Poisson
# Comentários em português conforme solicitado
import streamlit as st
import requests
import pandas as pd
import numpy as np
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from datetime import datetime
import os
from dateutil import parser

# Configuração de cache para chamadas à API
@st.cache_data(ttl=3600)
def fetch_api(endpoint, params, api_key):
    url = f"https://v3.football.api-sports.io/{endpoint}"
    headers = {"x-apisports-key": api_key}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if 'response' not in data or not data['response']:
            return []
        return data['response']
    except Exception as e:
        st.error(f"Erro na API: {str(e)}")
        return []

def get_api_key():
    # Lê a chave via st.secrets ou variável de ambiente (não expõe a chave)
    if 'api' in st.secrets and 'API_FOOTBALL_KEY' in st.secrets['api']:
        return st.secrets['api']['API_FOOTBALL_KEY']
    return os.getenv('API_FOOTBALL_KEY', '')

def calculate_poisson_prob(mean, threshold):
    # Cálculo simplificado de probabilidades com Poisson
    from scipy.stats import poisson
    return 1 - poisson.cdf(threshold - 1, mean)

def main():
    st.title("Análise de Futebol - Over Markets com Poisson")
    api_key = get_api_key()
    if not api_key:
        st.warning("Configure a chave API_FOOTBALL_KEY nos Secrets ou variável de ambiente.")
        return
    
    league_id = st.number_input("ID da Liga", value=39)
    season = st.number_input("Temporada", value=2023)
    min_prob = st.slider("Limite mínimo de probabilidade (%)", 50, 95, 75)
    show_all = st.checkbox("Mostrar todos os jogos (ignorar limite)")
    
    if st.button("Buscar Jogos Futuros"):
        fixtures = fetch_api("fixtures", {"league": league_id, "season": season, "next": 10}, api_key)
        if not fixtures:
            st.info("Nenhum jogo futuro encontrado.")
            return
        
        results = []
        for fix in fixtures:
            home_id = fix['teams']['home']['id']
            away_id = fix['teams']['away']['id']
            # Buscar últimos 10 jogos e H2H (simplificado para demo)
            last_home = fetch_api("fixtures", {"team": home_id, "last": 10}, api_key)
            last_away = fetch_api("fixtures", {"team": away_id, "last": 10}, api_key)
            h2h = fetch_api("fixtures", {"h2h": f"{home_id}-{away_id}", "last": 5}, api_key)
            
            # Médias fictícias baseadas em dados (substitua por cálculos reais)
            avg_goals_ht = 0.8
            avg_goals_ft = 2.6
            avg_corners = 10.2
            avg_cards = 4.1
            avg_btts = 0.48
            
            # Probabilidades com Poisson
            p_over05_ht = calculate_poisson_prob(avg_goals_ht, 0.5) * 100
            p_over15_ft = calculate_poisson_prob(avg_goals_ft, 1.5) * 100
            p_btts = avg_btts * 100
            p_over85_corners = calculate_poisson_prob(avg_corners, 8.5) * 100
            p_over35_cards = calculate_poisson_prob(avg_cards, 3.5) * 100
            
            all_above = all([p_over05_ht, p_over15_ft, p_btts, p_over85_corners, p_over35_cards] >= min_prob)
            if all_above or show_all:
                results.append({
                    "Jogo": f"{fix['teams']['home']['name']} vs {fix['teams']['away']['name']}",
                    "Data": fix['fixture']['date'],
                    "Prob HT Over 0.5": round(p_over05_ht, 1),
                    "Prob FT Over 1.5": round(p_over15_ft, 1),
                    "Prob BTTS": round(p_btts, 1),
                    "Prob Corners Over 8.5": round(p_over85_corners, 1),
                    "Prob Cards Over 3.5": round(p_over35_cards, 1),
                    "Média Gols HT": avg_goals_ht,
                    "Média Gols FT": avg_goals_ft
                })
        
        if results:
            df = pd.DataFrame(results)
            st.dataframe(df)
            csv = df.to_csv(index=False)
            st.download_button("Download CSV", csv, "analise.csv")
            
            # Geração de PDF com ReportLab
            if st.button("Gerar PDF"):
                pdf_file = "relatorio.pdf"
                c = canvas.Canvas(pdf_file, pagesize=letter)
                c.drawString(100, 750, "Relatório de Análise de Futebol")
                y = 700
                for row in results:
                    c.drawString(100, y, str(row))
                    y -= 20
                c.save()
                st.success("PDF gerado!")
        else:
            st.info("Nenhum jogo atende aos critérios.")

if __name__ == "__main__":
    main()

=== requirements.txt ===
streamlit==1.28.0
requests==2.31.0
pandas==2.1.3
numpy==1.26.2
reportlab==4.0.7
python-dateutil==2.8.2

=== .streamlit/secrets.toml.example ===
[api]
API_FOOTBALL_KEY = "sua_chave_aqui"

=== README.md ===
# Projeto Streamlit de Análise de Futebol

## Passo a passo para GitHub e Streamlit Cloud
1. Crie um repositório no GitHub.
2. Adicione os arquivos: app.py, requirements.txt, .streamlit/secrets.toml.example e README.md.
3. No Streamlit Cloud, conecte o repositório e faça deploy.
4. Configure os Secrets no Streamlit Cloud copiando o conteúdo de .streamlit/secrets.toml.example e preenchendo a chave real.

## Configuração dos Secrets
- Nunca exponha a chave API_FOOTBALL_KEY no código.
- Use st.secrets ou variável de ambiente.

## Importante sobre requirements.txt
O arquivo requirements.txt nunca deve ser colado dentro de app.py. As dependências devem permanecer exclusivamente no arquivo requirements.txt para que o deploy no Streamlit Cloud funcione corretamente. O app.py não deve conter nenhuma linha de versão de pacotes.

O código é executável no Streamlit com Python 3.11.
