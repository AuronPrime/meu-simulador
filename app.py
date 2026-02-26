import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

# Estilo para melhorar a visualização dos cards
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 Simulador de Acúmulo de Patrimônio")
st.markdown("Comparativo histórico considerando Reinvestimento de Dividendos, CDI e Inflação.")

# 2. BARRA LATERAL (INPUTS)
st.sidebar.header("Configurações")
ticker_input = st.sidebar.text_input("Digite o Ticker (ex: BBAS3, WEGE3, PETR4)", "BBAS3").upper()
ticker = ticker_input if ".SA" in ticker_input else ticker_input + ".SA"
valor_aporte = st.sidebar.number_input("Valor do aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

# 3. FUNÇÕES DE DADOS (BCB e YAHOO)
def get_bcb(codigo, d_ini, d_fim, fallback_diario):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={d_ini}&dataFinal={d_fim}"
    try:
        res = requests.get(url, timeout=10).json()
        df = pd.DataFrame(res)
        df['valor'] = pd.to_numeric(df['valor']) / 100
        df['data'] = pd.to_datetime(df['data'], dayfirst=True)
        return df.set_index('data')
    except:
        # Se falhar, retorna um DF com a taxa média histórica aproximada
        return pd.DataFrame({'valor': [fallback_diario]}, index=[pd.to_datetime(d_ini, dayfirst=True)])

@st.cache_data
def carregar_dados_completos(ticker):
    # Busca dados desde 2010
    data = yf.Ticker(ticker).history(start="2010-01-01")
    if data.empty:
        return None
    data.index = data.index.tz_localize(None)
    
    # Performance da Ação
    data["Price_Pct"] = (data["Close"] / data["Close"].iloc[0]) - 1
    data["Total_Fact"] = (1 + data["Close"].pct_change().fillna(0) + (data["Dividends"]/data["Close"]).fillna(0)).cumprod()
    data["Total_Pct"] = data["Total_Fact"] - 1
    data["Div_Pct"] = data["Total_Pct"] - data["Price_Pct"]
    
    # Benchmarks (IPCA e CDI)
    s, e = data.index[0].strftime('%d/%m/%Y'), data.index[-1].strftime('%d/%m/%Y')
    
    # IPCA mensal (Série 433) acumulado diariamente por aproximação
    df_ipca = get_bcb(433, s, e, 0.004) # fallback 0.4% am
    ipca_full = df_ipca.reindex(pd.date_range(data.index[0], data.index[-1]), method='ffill')
    # Ajuste: IPCA é mensal, então dividimos a taxa por 21 dias úteis médios para a curva diária
    data["IPCA_Acum"] = (1 + (ipca_full['valor']/21)).cumprod().reindex(data.index).ffill() - 1
    
    # CDI diário (Série 12)
    df_cdi = get_bcb(12, s, e, 0.0004) # fallback 0.04% ad
    cdi_full = df_cdi.reindex(pd.date_range(data.index[0], data.index[-1]), method='ffill')
    data["CDI_Acum"] = (1 + cdi_full['valor']).cumprod().reindex(data.index).ffill() - 1
    
    return data

# 4. EXECUÇÃO E GRÁFICO
try:
    df = carregar_dados_completos(ticker)
    
    if df is None:
        st.error(f"Ticker '{ticker}' não encontrado. Verifique se o código está correto (ex: PETR4).")
    else:
        # Gráfico Plotly
        fig = go.Figure()
        
        # Áreas empilhadas (Valorização + Dividendos)
        fig.add_trace(go.Scatter(x=df.index, y=df["Price_Pct"]*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.5)', line=dict(width=0)))
        fig.add_trace(go.Scatter(x=df.index, y=df["Div_Pct"]*100, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
        
        # Linhas de Comparação
        fig.add_trace(go.Scatter(x=df.index, y=df["IPCA_Acum"]*100, name='Inflação (IPCA)', line=dict(color='red', width=2)))
        fig.add_trace(go.Scatter(x=df.index, y=df["CDI_Acum"]*100, name='CDI', line=dict(color='gray', width=1.5, dash='dash')))
        fig.add_trace(go.Scatter(x=df.index, y=df["Total_Pct"]*100, name='RETORNO TOTAL', line=dict(color='black', width=2)))

        fig.update_layout(
            title=dict(text=f"Performance Histórica: {ticker}", x=0.5, font=dict(size=24)),
            template="plotly_white",
            hovermode="x unified",
            yaxis=dict(side="right", ticksuffix="%"),
            margin=dict(l=20, r=20, t=80, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # 5. CÁLCULO DE APORTES MENSAIS
        st.subheader(f"💰 Resultado com Aportes Mensais de R$ {valor_aporte:,.2f}")
        
        def simular_aportes(df_orig, v_mes, anos):
            n_meses = anos * 12
            df_sim = df_orig.copy()
            df_sim['m'] = df_sim.index.to_period('M')
            
            # Pega o primeiro dia útil de cada mês
            datas_aporte = df_sim.groupby('m').head(1).index
            # Seleciona exatamente os últimos N meses
            datas_simulacao = datas_aporte[-n_meses:]
            
            if len(datas_simulacao) < n_meses:
                return 0, 0
            
            recorte_final = df_orig[df_orig.index >= datas_simulacao[0]].copy()
            
            total_investido = len(datas_simulacao) * v_mes
            cotas_acumuladas = sum(v_mes / recorte_final.loc[d, 'Close'] for d in datas_simulacao)
            
            # Fator de Dividendos do período
            f_total = (1 + recorte_final['Close'].pct_change().fillna(0) + (recorte_final['Dividends']/recorte_final['Close']).fillna(0)).cumprod().iloc[-1]
            f_preco = (recorte_final['Close'].iloc[-1] / recorte_final['Close'].iloc[0])
            
            valor_final = cotas_acumuladas * recorte_final['Close'].iloc[-1] * (f_total/f_preco)
            return valor_final, total_investido

        col1, col2, col3 = st.columns(3)
        for anos, coluna in [(10, col1), (5, col2), (1, col3)]:
            v_final, v_invest = simular_aportes(df, valor_aporte, anos)
            with coluna:
                if v_final > 0:
                    st.metric(label=f"Acúmulo em {anos} anos", value=f"R$ {v_final:,.2f}")
                    st.write(f"**Investido:** R$ {v_invest:,.2f}")
                    st.caption(f"📈 Lucro: R$ {(v_final - v_invest):,.2f}")
                else:
                    st.warning(f"Dados insuficientes para {anos} anos.")

except Exception as e:
    st.error(f"Ocorreu um erro inesperado: {e}")
