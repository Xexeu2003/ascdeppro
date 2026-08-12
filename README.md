# ascdeppro
Analise esportivas
# App de Previsão de Apostas em Futebol

Este repositório contém uma aplicação Streamlit para previsão de apostas em futebol, focada em linhas de escanteios e cartões, utilizando o método de Poisson com pesos de 50/30/20.

## Estrutura do Repositório

```
meu-app-streamlit/
├── app.py
├── requirements.txt
└── README.md
```

## Instalação Local

1. Clone o repositório:
   ```bash
   git clone https://github.com/seu-usuario/nome-do-repo.git
   cd nome-do-repo
   ```

2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/Mac
   venv\Scripts\activate      # Windows
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

4. Execute a aplicação:
   ```bash
   streamlit run app.py
   ```

## Configuração da Chave de API no Streamlit Cloud

A chave `API_FOOTBALL_KEY` deve ser configurada diretamente no Streamlit Community Cloud:

1. Acesse as configurações do app no Streamlit Cloud.
2. Na seção **Secrets**, insira o valor no formato TOML:
   ```toml
   API_FOOTBALL_KEY = "sua_chave_aqui"
   ```

**Importante:** Nunca inclua a chave no código-fonte nem envie qualquer arquivo de segredos para o GitHub.

## Funcionalidades da Aplicação

- Selecione **uma liga por vez** no seletor disponível.
- Visualize as **linhas sugeridas de escanteios** e **cartões**.
- As previsões são geradas pelo **método de Poisson** com pesos 50/30/20 aplicados às médias históricas.
- Exporte os resultados em **CSV** ou **PDF**.
- O app trata automaticamente **dados ausentes** e respeita os **limites de requisições** da API.

## Regras de Desenvolvimento

- Não coloque o conteúdo do `requirements.txt` dentro do arquivo `app.py`.
- Não utilize marcadores de bloco de código Markdown (```python) dentro do `app.py`.
- Não armazene a chave da API no repositório.

## Aviso Importante

As probabilidades apresentadas são apenas estimativas estatísticas baseadas em dados históricos e não constituem garantia de resultados. Utilize-as exclusivamente como referência e nunca aposte mais do que pode perder.
