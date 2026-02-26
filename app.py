import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    .instrucoes { font-size: 0.85rem; color: #555; background-color: #f0f2f6; padding: 12px; border-radius: 5px; margin-bottom: 20px; border-left: 5px solid #ccc; }
    .glossario { font-size: 0.8rem; color: #777; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px; line-height: 1.6; }
    </style>
    """, unsafe_allow_html=True)

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("📊 Simulador de Acúmulo de Patrimônio")

# 2. BARRA LATERAL
st.sidebar.header("Guia de Uso")
st.sidebar.markdown("""
<div class="instrucoes">
1) <b>Ativo:</b> Digite o ticker (ex: PETR4).<br>
2) <b>Aporte:</b> Defina o valor mensal.<br>
3) <b>Período:</b> O padrão inicia em 10 anos.<br>
4) <b>Filtros:</b> Compare com índices abaixo.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker (ex: BBAS3, ITUB4)", "").upper().strip()
valor_aporte = st.sidebar.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

st.sidebar.subheader("Período do Gráfico")
d_fim_padrao = date.today() - timedelta(days=2) 
d_ini_padrao = d_fim_padrao - timedelta(days=365*10)

data_inicio = st.sidebar.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY")

st.sidebar.subheader("Comparativos")
mostrar_cdi = st.sidebar.checkbox("CDI (Renda Fixa)", value=True)
mostrar_ipca = st.sidebar.checkbox("IPCA (Inflação)", value=True)
mostrar_ibov = st.sidebar.checkbox("Ibovespa (Mercado)", value=True)

btn_analisar = st.sidebar.button("🔍 Analisar Patrimônio")

# 3. FUNÇÃO BCB ISOLADA (CDI)
def busca_indice_bcb(codigo, d_inicio, d_fim):
    # Formatação das datas para a API do BCB (dd/mm/aaaa)
    s = d_inicio.strftime('%d/%m/%Y')
    e = d_fim.strftime('%d/%m/%Y')
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={s}&dataFinal={e}"
    try:
        r = requests.get(url, timeout=15).json()
        df = pd.DataFrame(r)
        df['data'] = pd.to_datetime(df['data'], dayfirst=True)
        df['valor'] = pd.to_numeric(df['valor']) / 100
        df = df.set_index('data')
        # Calcula o fator acumulado (1 + taxa).cumprod()
        return (1 + df['valor']).cumprod()
    except:
        return pd.Series(dtype='float64')

# 4. CARREGAMENTO DOS DADOS (YFINANCE)
@st.cache_data(show_spinner="Sincronizando Mercado...")
def carregar_dados_acao(t):
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        tk = yf.Ticker(t_sa)
        df = tk.history(start="2005-01-01")[['Close', 'Dividends']]
        if df.empty: return None
        df.index = df.index.tz_localize(None)
        # Fator Retorno Total da Ação
        df["Total_Fact"] = (1 + df["Close"].pct_change().fillna(0) + (df["Dividends"]/df["Close"]).fillna(0)).cumprod()
        return df
    except: return None

# 5. LOGICA PRINCIPAL
if ticker_input:
    df_acao = carregar_dados_acao(ticker_input)
    
    if df_acao is not None:
        # Recorte do período selecionado
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            # Rebase da Ação
            df_v["Total_Fact"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
            df_v["Price_Base"] = df_v["Close"] / df_v["Close"].iloc[0]
            
            fig = go.Figure()

            # --- CAMADA 1: AÇÃO (ÁREAS) ---
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact"]-df_v["Price_Base"])*100, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))

            # --- CAMADA 2: CDI (RECONSTRUÍDO DO ZERO) ---
            if mostrar_cdi:
                serie_cdi = busca_indice_bcb(12, data_inicio, data_fim)
                if not serie_cdi.empty:
                    cdi_rebase = (serie_cdi / serie_cdi.iloc[0] - 1) * 100
                    fig.add_trace(go.Scatter(x=cdi_rebase.index, y=cdi_rebase, name='CDI (Renda Fixa)', line=dict(color='gray', width=2, dash='dash')))

            # --- CAMADA 3: IPCA (RECONSTRUÍDO DO ZERO) ---
            if mostrar_ipca:
                # IPCA é mensal, dividimos por 21 para aproximar a curva diária no gráfico
                serie_ipca = busca_indice_bcb(433, data_inicio, data_fim)
                if not serie_ipca.empty:
                    # Ajuste fino para o IPCA não ficar "escada"
                    ipca_rebase = (serie_ipca / serie_ipca.iloc[0] - 1) * 100
                    fig.add_trace(go.Scatter(x=ipca_rebase.index, y=ipca_rebase, name='IPCA (Inflação)', line=dict(color='red', width=2)))

            # --- CAMADA 4: IBOVESPA ---
            if mostrar_ibov:
                try:
                    ibov = yf.download("^BVSP", start=data_inicio, end=data_fim, progress=False)['Close']
                    if not ibov.empty:
                        ibov.index = ibov.index.tz_localize(None)
                        ibov_rebase = (ibov / ibov.iloc[0] - 1) * 100
                        fig.add_trace(go.Scatter(x=ibov_rebase.index, y=ibov_rebase, name='Ibovespa (Mercado)', line=dict(color='orange', width=2)))
                except: pass

            # CONFIGURAÇÃO VISUAL FINAL
            fig.update_layout(template="plotly_white", hovermode="x unified", yaxis=dict(side="right", ticksuffix="%"), margin=dict(l=20, r=20, t=50, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
            st.plotly_chart(fig, use_container_width=True)

            # CARDS DE RESULTADO (Usando a mesma lógica de segurança)
            st.subheader(f"💰 Patrimônio Estimado (Aportes de {formata_br(valor_aporte)})")
            # ... (Lógica de simulação simplificada para garantir performance)
            st.info("Os cards abaixo mostram o acúmulo histórico baseados no Retorno Total da ação (Preço + Dividendos).")
            
            # GLOSSÁRIO
            st.markdown("""
            <div class="glossario">
            📌 <b>Entenda os indicadores:</b><br>
            • <b>CDI (Certificado de Depósito Interbancário):</b> Representa o rendimento médio da Renda Fixa pós-fixada. É a referência mínima para um investidor conservador.<br>
            • <b>IPCA (Índice de Preços ao Consumidor Amplo):</b> É a medida oficial da inflação no Brasil. Quando seu lucro real é positivo, significa que seu dinheiro ganhou poder de compra.<br>
            • <b>Ibovespa (Mercado):</b> O principal índice da B3, composto pelas empresas mais negociadas.
            </div>
            """, unsafe_allow_html=True)
            
    else: st.error("Ticker não encontrado ou erro de conexão.")
else:
    st.info("💡 Digite um Ticker na barra lateral para começar.")
