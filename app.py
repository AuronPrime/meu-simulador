import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

# CONFIGURAÇÃO DE INTERFACE
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

# SIDEBAR COM O GUIA QUE VOCÊ PEDIU
st.sidebar.header("Guia de Uso")
st.sidebar.markdown("""
<div class="instrucoes">
1) <b>Ativo:</b> Digite o ticker (ex: PETR4).<br>
2) <b>Aporte:</b> Defina o valor mensal.<br>
3) <b>Período:</b> O padrão inicia em 10 anos.<br>
4) <b>Filtros:</b> Compare com índices abaixo.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker", "").upper().strip()
valor_aporte = st.sidebar.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0)

st.sidebar.subheader("Período")
d_fim_padrao = date.today() - timedelta(days=2)
d_ini_padrao = d_fim_padrao - timedelta(days=365*10)
data_inicio = st.sidebar.date_input("Início", d_ini_padrao)
data_fim = st.sidebar.date_input("Fim", d_fim_padrao)

mostrar_cdi = st.sidebar.checkbox("CDI", value=True)
mostrar_ipca = st.sidebar.checkbox("IPCA", value=True)

# FUNÇÃO DE BUSCA DO BANCO CENTRAL (SGS)
def get_bcb(codigo, d_ini, d_f):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={d_ini}&dataFinal={d_f}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            df = pd.DataFrame(r.json())
            df['valor'] = pd.to_numeric(df['valor']) / 100
            df['data'] = pd.to_datetime(df['data'], dayfirst=True)
            return df.set_index('data')
    except: return pd.DataFrame()

# CACHE DE 1 HORA PARA EVITAR BLOQUEIO DO YAHOO
@st.cache_data(ttl=3600, show_spinner="Sincronizando dados...")
def carregar_dados_seguro(t):
    if not t: return None
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        # Busca Ação
        tk = yf.Ticker(t_sa)
        df = tk.history(start="2005-01-01")[['Close', 'Dividends']]
        if df.empty: return None
        df.index = df.index.tz_localize(None)
        
        # Fator de Retorno Total
        df["Total_Fact"] = (1 + df["Close"].pct_change().fillna(0) + (df["Dividends"]/df["Close"]).fillna(0)).cumprod()
        
        s, e = df.index[0].strftime('%d/%m/%Y'), df.index[-1].strftime('%d/%m/%Y')
        
        # Índices BCB (Injetados no mesmo DataFrame)
        for cod, nome in [(433, "IPCA_Fact"), (12, "CDI_Fact")]:
            df_ind = get_bcb(cod, s, e)
            if not df_ind.empty:
                div = 21 if cod == 433 else 1 # IPCA é mensal, CDI é diário
                # Reindexamos até a última data REAL do índice para não inventar o final do gráfico
                limite = df_ind.index.max()
                f_base = df_ind.reindex(pd.date_range(df.index[0], limite), method='ffill')
                df[nome] = (1 + (f_base['valor']/div)).cumprod().reindex(df.index)
        
        return df
    except: return None

# PROCESSAMENTO
if ticker_input:
    dados = carregar_dados_seguro(ticker_input)
    
    if dados is not None:
        df_v = dados.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            # Rebase
            for col in ["Total_Fact", "IPCA_Fact", "CDI_Fact"]:
                if col in df_v.columns:
                    v_ini = df_v[col].dropna().iloc[0]
                    df_v[col] = df_v[col] / v_ini
            
            df_v["Price_Base"] = df_v["Close"] / df_v["Close"].iloc[0]
            
            # GRÁFICO
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.3)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact"]-df_v["Price_Base"])*100, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.3)', line=dict(width=0)))
            
            if mostrar_ipca and "IPCA_Fact" in df_v.columns:
                p = df_v["IPCA_Fact"].dropna()
                fig.add_trace(go.Scatter(x=p.index, y=(p-1)*100, name='IPCA (Inflação)', line=dict(color='red', width=2)))
            
            if mostrar_cdi and "CDI_Fact" in df_v.columns:
                p = df_v["CDI_Fact"].dropna()
                fig.add_trace(go.Scatter(x=p.index, y=(p-1)*100, name='CDI', line=dict(color='gray', dash='dash')))
            
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))
            
            fig.update_layout(template="plotly_white", hovermode="x unified", yaxis=dict(side="right", ticksuffix="%"), margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, use_container_width=True)

            # GLOSSÁRIO ORIGINAL
            st.markdown("""
            <div class="glossario">
            📌 <b>Entenda os indicadores:</b><br>
            • <b>CDI:</b> Rendimento médio da Renda Fixa. Referência mínima para o investidor.<br>
            • <b>IPCA:</b> Inflação oficial. Define se você realmente ganhou poder de compra.<br>
            • <b>Importante:</b> O gráfico interrompe o IPCA/CDI automaticamente na última data oficial publicada, sem estimativas.
            </div>
            """, unsafe_allow_html=True)
        else: st.warning("Sem dados para esse período.")
    else:
        st.error("⚠️ Limite de acesso atingido ou Ticker inválido. Por favor, aguarde 1 minuto e tente novamente.")
else:
    st.info("💡 Digite um Ticker (ex: BBAS3) para começar.")
