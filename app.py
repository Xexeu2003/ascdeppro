### app.py
```python
# app.py - Aplicativo Streamlit completo para análise de futebol via API-Football v3
import streamlit as st
import os
import requests
import json
from datetime import datetime, timedelta
import time
from collections import defaultdict
# import reportlab only if available
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

st.set_page_config(page_title="Football Analysis Simulator", layout="wide")
st.title("Football Analysis Simulator (API-Football v3)")
st.warning("AVISO: Todas as probabilidades são estimativas estatísticas baseadas em médias históricas. Não constituem previsão garantida.")

# Funções robustas de API com cache, retries, paginação e tratamento de erros
def get_api_key():
    key = st.secrets.get("API_FOOTBALL_KEY") or os.getenv("API_FOOTBALL_KEY")
    if not key:
        st.error("API_FOOTBALL_KEY não encontrada nos secrets ou variável de ambiente.")
        st.stop()
    return key

@st.cache_data(ttl=3600)
def api_request(endpoint, params, retries=3):
    url = f"https://v3.football.api-sports.io/{endpoint}"
    headers = {"x-apisports-key": get_api_key()}
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            time.sleep(1)
        except Exception as e:
            if attempt == retries-1:
                st.error(f"Erro na requisição: {str(e)}")
    return {"response": []}



```
