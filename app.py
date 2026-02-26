import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Configuração da página (deve ser a primeira linha)
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

st.title("📊 Simulador de Acúmulo de Patrimônio")
st.markdown("Veja o impacto dos dividendos e dos aportes mensais ao longo do tempo.")

# --- BARRA LATERAL (INPUTS) ---
st.sidebar.header("Configurações")
ticker_input = st.sidebar.text_input("Digite o Ticker (ex: PETR4, WEGE3)", "PETR4").upper()
ticker = ticker_input if ".SA" in ticker_input else ticker_input + ".SA"

valor_aporte = st.sidebar.number_input("Valor do aporte mensal (R$)", min_value=0.0, value=500.0, step=50.0)

# --- BUSCA DE DADOS ---
@st.cache_data # Isso faz o site carregar rápido se você não mudar o ticker
def carregar_dados(ticker):
    data = yf.Ticker(ticker).history(start="2010-01-01")
    data.index = data.index.tz_localize(None)
    return data

try:
    data = carregar_dados(ticker)
    
    # Cálculos de Performance
    data["Price_Pct"] = (data["Close"] / data["Close"].iloc[0]) - 1
    data["Total_Fact"] = (1 + data["Close"].pct_change().fillna(0) + (data["Dividends"]/data["Close"]).fillna(0)).cumprod()
    data["Total_Pct"] = data["Total_Fact"] - 1
    data["Div_Pct"] = data["Total_Pct"] - data["Price_Pct"]

    # --- GRÁFICO ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data.index, y=data["Price_Pct"]*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.5)', line=dict(width=0)))
    fig.add_trace(go.Scatter(x=data.index, y=data["Div_Pct"]*100, stackgroup='one', name='Dividendos Reinvestidos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
    fig.add_trace(go.Scatter(x=data.index, y=data["Total_Pct"]*100, name='TOTAL (Com Proventos)', line=dict(color='black', width=2)))

    fig.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis=dict(side="right", ticksuffix="%"),
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # --- SIMULAÇÃO DE APORTES ---
    st.subheader(f"💰 Resultado com Aportes Mensais de R$ {valor_aporte:,.2f}")
    
    col1, col2, col3 = st.columns(3)
    
    def calc_invest(df, v_mes, anos):
        total_meses = anos * 12
        df_copy = df.copy()
        df_copy['m'] = df_copy.index.to_period('M')
        todas_datas = df_copy.groupby('m').head(1).index
        datas_sim = todas_datas[-total_meses:]
        df_p = df[df.index >= datas_sim[0]].copy()
        capital = len(datas_sim) * v_mes
        total_cotas = sum(v_mes / df_p.loc[d, 'Close'] for d in datas_sim)
        f_total = (1 + df_p['Close'].pct_change().fillna(0) + (df_p['Dividends']/df_p['Close']).fillna(0)).cumprod().iloc[-1]
        f_p = (df_p['Close'].iloc[-1] / df_p['Close'].iloc[0])
        return total_cotas * df_p['Close'].iloc[-1] * (f_total/f_p), capital

    periodos = [(10, col1), (5, col2), (1, col3)]
    for anos, coluna in periodos:
        final, investido = calc_invest(data, valor_aporte, anos)
        with coluna:
            st.metric(label=f"Há {anos} anos", value=f"R$ {final:,.2f}")
            st.caption(f"Investido: R$ {investido:,.2f}")

except Exception as e:
    st.error(f"Erro ao carregar ticker {ticker}. Verifique se o código está correto.")
