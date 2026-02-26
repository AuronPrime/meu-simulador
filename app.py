import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime, date

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    .instrucoes { font-size: 0.85rem; color: #555; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("📊 Simulador de Acúmulo de Patrimônio")
st.markdown("Comparativo histórico considerando Reinvestimento de Dividendos, Benchmarks e Inflação.")

# 2. BARRA LATERAL
st.sidebar.header("Configurações")

st.sidebar.markdown("""
<div class="instrucoes">
<b>Como usar:</b><br>
1. Digite o ticker e o aporte.<br>
2. Ajuste o período de análise.<br>
3. Use os filtros para comparar índices.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker (ex: BBAS3, WEGE3)", "").upper().strip()
valor_aporte = st.sidebar.number_input("Valor do aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

# Filtro de Datas
st.sidebar.subheader("Período da Análise")
data_inicio = st.sidebar.date_input("Início", date(2010, 1, 1))
data_fim = st.sidebar.date_input("Fim", date.today())

# Checkboxes de exibição
st.sidebar.subheader("Exibir no Gráfico")
mostrar_cdi = st.sidebar.checkbox("CDI", value=True)
mostrar_ipca = st.sidebar.checkbox("Inflação (IPCA)", value=True)
mostrar_ibov = st.sidebar.checkbox("Ibovespa", value=False)

btn_analisar = st.sidebar.button("🔍 Analisar Patrimônio")

# 3. FUNÇÕES DE SUPORTE
def get_bcb(codigo, d_ini, d_f, fallback):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={d_ini}&dataFinal={d_f}"
    try:
        res = requests.get(url, timeout=10).json()
        df_res = pd.DataFrame(res)
        df_res['valor'] = pd.to_numeric(df_res['valor']) / 100
        df_res['data'] = pd.to_datetime(df_res['data'], dayfirst=True)
        return df_res.set_index('data')
    except:
        return pd.DataFrame({'valor': [fallback]}, index=[pd.to_datetime(d_ini, dayfirst=True)])

@st.cache_data(show_spinner="Buscando dados no mercado...")
def carregar_tudo(t, d_ini, d_fim):
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        # Busca Ação e Ibovespa (^BVSP)
        dados_acao = yf.download(t_sa, start=d_ini, end=d_fim)
        dados_ibov = yf.download("^BVSP", start=d_ini, end=d_fim)
        
        if dados_acao.empty: return None
        
        # Limpeza e Performance Ação
        df = dados_acao[['Close', 'Dividends']].copy()
        df.index = df.index.tz_localize(None)
        df["Price_Pct"] = (df["Close"] / df["Close"].iloc[0]) - 1
        df["Total_Fact"] = (1 + df["Close"].pct_change().fillna(0) + (df["Dividends"]/df["Close"]).fillna(0)).cumprod()
        df["Total_Pct"] = df["Total_Fact"] - 1
        df["Div_Pct"] = df["Total_Pct"] - df["Price_Pct"]
        
        # Performance Ibovespa
        if not dados_ibov.empty:
            ibov_close = dados_ibov['Close'].copy()
            ibov_close.index = ibov_close.index.tz_localize(None)
            df["IBOV_Acum"] = (ibov_close / ibov_close.iloc[0]).reindex(df.index).ffill() - 1
        
        # Benchmarks BCB
        s, e = df.index[0].strftime('%d/%m/%Y'), df.index[-1].strftime('%d/%m/%Y')
        
        df_ipca = get_bcb(433, s, e, 0.004)
        ipca_f = df_ipca.reindex(pd.date_range(df.index[0], df.index[-1]), method='ffill')
        df["IPCA_Fator"] = (1 + (ipca_f['valor']/21)).cumprod().reindex(df.index).ffill()
        df["IPCA_Acum"] = df["IPCA_Fator"] - 1
        
        df_cdi = get_bcb(12, s, e, 0.0004)
        cdi_f = df_cdi.reindex(pd.date_range(df.index[0], df.index[-1]), method='ffill')
        df["CDI_Acum"] = (1 + cdi_f['valor']).cumprod().reindex(df.index).ffill() - 1
        
        return df
    except:
        return None

# 4. LÓGICA DE EXIBIÇÃO
if not ticker_input:
    st.info("💡 Digite um **Ticker** e clique em **Analisar Patrimônio**.")
elif btn_analisar or ticker_input:
    df = carregar_tudo(ticker_input, data_inicio, data_fim)
    if df is not None:
        fig = go.Figure()
        
        # Camadas base
        fig.add_trace(go.Scatter(x=df.index, y=df["Price_Pct"]*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.5)', line=dict(width=0)))
        fig.add_trace(go.Scatter(x=df.index, y=df["Div_Pct"]*100, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
        
        # Linhas condicionais
        if mostrar_ipca:
            fig.add_trace(go.Scatter(x=df.index, y=df["IPCA_Acum"]*100, name='Inflação (IPCA)', line=dict(color='red', width=2)))
        if mostrar_cdi:
            fig.add_trace(go.Scatter(x=df.index, y=df["CDI_Acum"]*100, name='CDI', line=dict(color='gray', width=1.5, dash='dash')))
        if mostrar_ibov and "IBOV_Acum" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["IBOV_Acum"]*100, name='Ibovespa', line=dict(color='orange', width=2)))
            
        fig.add_trace(go.Scatter(x=df.index, y=df["Total_Pct"]*100, name='RETORNO TOTAL', line=dict(color='black', width=2.5)))

        fig.update_layout(
            template="plotly_white", hovermode="x unified",
            yaxis=dict(side="right", ticksuffix="%"),
            margin=dict(l=20, r=20, t=50, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 5. RESULTADOS
        st.subheader(f"💰 Simulação de Aportes ({data_inicio.year} - {data_fim.year})")
        
        def simular_periodo(df_orig, v_mes):
            df_sim = df_orig.copy()
            df_sim['m'] = df_sim.index.to_period('M')
            datas_aporte = df_sim.groupby('m').head(1).index
            
            n_aportes = len(datas_aporte)
            if n_aportes < 2: return 0, 0, 0
            
            cotas = sum(v_mes / df_orig.loc[d, 'Close'] for d in datas_aporte)
            f_total = (1 + df_orig['Close'].pct_change().fillna(0) + (df_orig['Dividends']/df_orig['Close']).fillna(0)).cumprod().iloc[-1]
            f_preco = (df_orig['Close'].iloc[-1] / df_orig['Close'].iloc[0])
            valor_final = cotas * df_orig['Close'].iloc[-1] * (f_total/f_preco)
            
            invest_nominal = n_aportes * v_mes
            invest_corrigido = sum(v_mes * (df_orig['IPCA_Fator'].iloc[-1] / df_orig.loc[d, 'IPCA_Fator']) for d in datas_aporte)
            
            return valor_final, invest_nominal, valor_final - invest_corrigido

        v_f, v_n, l_r = simular_periodo(df, valor_aporte)
        
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Patrimônio Acumulado", formata_br(v_f))
        with c2: st.write(f"**Total Investido:** {formata_br(v_n)}")
        with c3: 
            st.caption(f"📉 **Lucro Líquido Real:** {formata_br(l_r)}")
            st.caption("(Acima da inflação do período selecionado)")
    else:
        st.error(f"Erro ao buscar dados para '{ticker_input}' no período selecionado.")
