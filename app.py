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
data_f = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY")

st.sidebar.subheader("Comparativos")
mostrar_cdi = st.sidebar.checkbox("CDI (Renda Fixa)", value=True)
mostrar_ipca = st.sidebar.checkbox("IPCA (Inflação)", value=True)
mostrar_ibov = st.sidebar.checkbox("Ibovespa (Mercado)", value=True)

btn_analisar = st.sidebar.button("🔍 Analisar Patrimônio")

# 3. FUNÇÕES DE SUPORTE (BCB)
def busca_indice_bcb(codigo, d_inicio, d_fim):
    s = d_inicio.strftime('%d/%m/%Y')
    e = d_fim.strftime('%d/%m/%Y')
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={s}&dataFinal={e}"
    try:
        r = requests.get(url, timeout=15).json()
        df = pd.DataFrame(r)
        df['data'] = pd.to_datetime(df['data'], dayfirst=True)
        df['valor'] = pd.to_numeric(df['valor']) / 100
        df = df.set_index('data')
        return (1 + df['valor']).cumprod()
    except:
        return pd.Series(dtype='float64')

# 4. CARREGAMENTO AÇÃO
@st.cache_data(show_spinner="Buscando dados...")
def carregar_dados_ticker(t, start, end):
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        df = yf.download(t_sa, start=start, end=end, progress=False)
        if df.empty: return None
        # Garante que pegamos a coluna 'Close' mesmo em MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            close_prices = df['Close'][t_sa]
        else:
            close_prices = df['Close']
            
        # Dividendos (via Ticker object para manter compatibilidade)
        tk = yf.Ticker(t_sa)
        divs = tk.dividends.loc[start:end]
        divs.index = divs.index.tz_localize(None)
        
        df_final = pd.DataFrame({'Close': close_prices})
        df_final.index = df_final.index.tz_localize(None)
        df_final['Dividends'] = divs
        df_final['Dividends'] = df_final['Dividends'].fillna(0)
        
        # Fator Retorno Total
        df_final["Total_Fact"] = (1 + df_final["Close"].pct_change().fillna(0) + (df_final["Dividends"]/df_final["Close"]).fillna(0)).cumprod()
        return df_final
    except: return None

# 5. LÓGICA DE EXIBIÇÃO
if ticker_input:
    df_v = carregar_dados_ticker(ticker_input, data_inicio, data_f)
    
    if df_v is not None and not df_v.empty:
        # Rebase da Ação
        df_v["Total_Fact"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
        df_v["Price_Base"] = df_v["Close"] / df_v["Close"].iloc[0]
        
        fig = go.Figure()

        # ÁREAS (Ação)
        fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
        fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact"]-df_v["Price_Base"])*100, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
        fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))

        # CDI (Já funcionando)
        if mostrar_cdi:
            serie_cdi = busca_indice_bcb(12, data_inicio, data_f)
            if not serie_cdi.empty:
                cdi_plot = (serie_cdi / serie_cdi.iloc[0] - 1) * 100
                fig.add_trace(go.Scatter(x=cdi_plot.index, y=cdi_plot, name='CDI (Renda Fixa)', line=dict(color='gray', width=2, dash='dash')))

        # IPCA (Já funcionando)
        if mostrar_ipca:
            serie_ipca = busca_indice_bcb(433, data_inicio, data_f)
            if not serie_ipca.empty:
                ipca_plot = (serie_ipca / serie_ipca.iloc[0] - 1) * 100
                fig.add_trace(go.Scatter(x=ipca_plot.index, y=ipca_plot, name='IPCA (Inflação)', line=dict(color='red', width=2)))

        # IBOVESPA (CORREÇÃO FINAL)
        if mostrar_ibov:
            try:
                ibov_raw = yf.download("^BVSP", start=data_inicio, end=data_f, progress=False)
                if not ibov_raw.empty:
                    # Trata MultiIndex do Yahoo se houver
                    ibov_close = ibov_raw['Close']['^BVSP'] if isinstance(ibov_raw.columns, pd.MultiIndex) else ibov_raw['Close']
                    ibov_close.index = ibov_close.index.tz_localize(None)
                    ibov_plot = (ibov_close / ibov_close.iloc[0] - 1) * 100
                    fig.add_trace(go.Scatter(x=ibov_plot.index, y=ibov_plot, name='Ibovespa (Mercado)', line=dict(color='orange', width=2)))
            except: pass

        fig.update_layout(template="plotly_white", hovermode="x unified", yaxis=dict(side="right", ticksuffix="%"), margin=dict(l=20, r=20, t=50, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
        st.plotly_chart(fig, use_container_width=True)

        # GLOSSÁRIO
        st.markdown("""
        <div class="glossario">
        📌 <b>Entenda os indicadores:</b><br>
        • <b>CDI (Certificado de Depósito Interbancário):</b> Referência da Renda Fixa pós-fixada.<br>
        • <b>IPCA (Índice de Preços ao Consumidor Amplo):</b> Medida oficial da inflação no Brasil.<br>
        • <b>Ibovespa (Mercado):</b> Principal índice de ações da bolsa brasileira (B3).
        </div>
        """, unsafe_allow_html=True)
            
    else: st.error("Ticker não encontrado ou erro nos dados.")
else:
    st.info("💡 Digite um Ticker na barra lateral para começar.")
