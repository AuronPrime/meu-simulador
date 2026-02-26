import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

# 1. CONFIGURAÇÃO DA PÁGINA (Sempre o primeiro comando)
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
st.markdown("Compare ações com Dividendos, IBOV, CDI e Inflação.")

# 2. BARRA LATERAL
st.sidebar.header("Configurações")

st.sidebar.markdown("""
<div class="instrucoes">
<b>Como usar:</b><br>
1. Digite o ticker e o aporte.<br>
2. Ajuste o período de análise.<br>
3. Clique em <b>Analisar Patrimônio</b>.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker (ex: BBAS3, WEGE3)", "").upper().strip()
valor_aporte = st.sidebar.number_input("Valor do aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

st.sidebar.subheader("Período da Análise")
d_ini_padrao = date(2010, 1, 1)
d_fim_padrao = date.today() - timedelta(days=2) # 2 dias para garantir dados fechados

data_inicio = st.sidebar.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY")

st.sidebar.subheader("Exibir no Gráfico")
mostrar_cdi = st.sidebar.checkbox("CDI", value=True)
mostrar_ipca = st.sidebar.checkbox("Inflação (IPCA)", value=True)
mostrar_ibov = st.sidebar.checkbox("Ibovespa", value=False)

btn_analisar = st.sidebar.button("🔍 Analisar Patrimônio")

# 3. FUNÇÕES DE SUPORTE
def get_bcb(codigo, d_ini, d_f, fallback):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={d_ini}&dataFinal={d_f}"
    try:
        res = requests.get(url, timeout=15).json()
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
        # Tenta buscar dados da ação
        ticker_obj = yf.Ticker(t_sa)
        df_hist = ticker_obj.history(start=d_ini, end=d_fim)
        
        if df_hist.empty:
            return None
            
        df = df_hist[['Close']].copy()
        df['Dividends'] = df_hist['Dividends'] if 'Dividends' in df_hist else 0
        df.index = df.index.tz_localize(None)
        
        # Cálculos de Performance
        df["Price_Pct"] = (df["Close"] / df["Close"].iloc[0]) - 1
        df["Total_Fact"] = (1 + df["Close"].pct_change().fillna(0) + (df["Dividends"]/df["Close"]).fillna(0)).cumprod()
        df["Total_Pct"] = df["Total_Fact"] - 1
        df["Div_Pct"] = df["Total_Pct"] - df["Price_Pct"]
        
        # Busca Ibovespa separadamente
        try:
            ibov = yf.download("^BVSP", start=d_ini, end=d_fim, progress=False)
            if not ibov.empty:
                ibov_c = ibov['Close'].copy()
                ibov_c.index = ibov_c.index.tz_localize(None)
                df["IBOV_Acum"] = (ibov_c / ibov_c.iloc[0]).reindex(df.index).ffill() - 1
        except:
            pass # Se o Ibov falhar, o gráfico continua sem ele
            
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

# 4. EXIBIÇÃO
if not ticker_input:
    st.info("💡 Digite um **Ticker** e clique em **Analisar Patrimônio**.")
elif btn_analisar:
    df = carregar_tudo(ticker_input, data_inicio, data_fim)
    if df is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df["Price_Pct"]*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.5)', line=dict(width=0)))
        fig.add_trace(go.Scatter(x=df.index, y=df["Div_Pct"]*100, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
        
        if mostrar_ipca:
            fig.add_trace(go.Scatter(x=df.index, y=df["IPCA_Acum"]*100, name='Inflação (IPCA)', line=dict(color='red', width=2)))
        if mostrar_cdi:
            fig.add_trace(go.Scatter(x=df.index, y=df["CDI_Acum"]*100, name='CDI', line=dict(color='gray', width=1.5, dash='dash')))
        if mostrar_ibov and "IBOV_Acum" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["IBOV_Acum"]*100, name='Ibovespa', line=dict(color='orange', width=2)))
            
        fig.add_trace(go.Scatter(x=df.index, y=df["Total_Pct"]*100, name='RETORNO TOTAL', line=dict(color='black', width=2.5)))
        fig.update_layout(template="plotly_white", hovermode="x unified", yaxis=dict(side="right", ticksuffix="%"), margin=dict(l=20, r=20, t=50, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
        st.plotly_chart(fig, use_container_width=True)

        # 5. RESULTADOS
        st.subheader(f"💰 Simulação de Aportes ({data_inicio.strftime('%d/%m/%Y')} - {data_fim.strftime('%d/%m/%Y')})")
        
        df_sim = df.copy()
        df_sim['m'] = df_sim.index.to_period('M')
        datas_aporte = df_sim.groupby('m').head(1).index
        if len(datas_aporte) >= 2:
            cotas = sum(valor_aporte / df.loc[d, 'Close'] for d in datas_aporte)
            f_total = df["Total_Fact"].iloc[-1] / df["Total_Fact"].iloc[0]
            f_preco = df["Close"].iloc[-1] / df["Close"].iloc[0]
            v_final = cotas * df["Close"].iloc[-1] * (f_total/f_preco)
            v_nom = len(datas_aporte) * valor_aporte
            l_real = v_final - sum(valor_aporte * (df['IPCA_Fator'].iloc[-1] / df.loc[d, 'IPCA_Fator']) for d in datas_aporte)
            
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Patrimônio Acumulado", formata_br(v_final))
            with c2: st.write(f"**Total Investido:** {formata_br(v_nom)}")
            with c3: 
                st.caption(f"📉 **Lucro Líquido Real:** {formata_br(l_real)}")
                st.caption("(Descontada a inflação)")
    else:
        st.error(f"Erro ao buscar '{ticker_input}'. Verifique o código e tente datas mais antigas.")
