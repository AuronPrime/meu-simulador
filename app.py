import streamlit as st
import yfinance as yf
import pandas as pd 
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #1f77b4; }
    .resumo-objetivo { font-size: 0.9rem; color: #333; background-color: #e8f0fe; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 5px solid #1f77b4; line-height: 1.6; }
    .total-card { background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 15px; border-radius: 12px; margin-bottom: 10px; text-align: center; }
    .total-label { font-size: 0.75rem; font-weight: 800; color: #64748b; text-transform: uppercase; margin-bottom: 5px; }
    .total-amount { font-size: 1.6rem; font-weight: 800; color: #1f77b4; }
    .info-card { background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 18px; border-radius: 12px; margin-top: 5px; }
    .card-header { font-size: 0.75rem; font-weight: 800; color: #64748b; text-transform: uppercase; margin-bottom: 10px; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; }
    .card-item { font-size: 0.9rem; margin-bottom: 6px; color: #1e293b; }
    .card-destaque { font-size: 0.95rem; font-weight: 700; color: #0f172a; margin-top: 8px; border-top: 1px solid #e2e8f0; padding-top: 8px; }
    .glossario-container { margin-top: 40px; padding: 25px; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; }
    .glossario-termo { font-weight: 800; color: #1f77b4; font-size: 1rem; display: block; }
    .glossario-def { color: #475569; font-size: 0.9rem; line-height: 1.5; display: block; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("Simulador de Acúmulo de Patrimônio")

# 2. BARRA LATERAL
st.sidebar.markdown("""
<div class="resumo-objetivo">
👋 <b>Bem-vindo!</b><br>
O simulador calcula o acúmulo real de patrimônio via <b>Retorno Total</b>.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker", "BBAS3").upper().strip()
valor_aporte = st.sidebar.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

st.sidebar.subheader("Período da Simulação")
d_fim_padrao = date.today() - timedelta(days=2) 
d_ini_padrao = d_fim_padrao - timedelta(days=365*10 + 5)
data_inicio = st.sidebar.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY")

st.sidebar.subheader("Benchmarks no Gráfico")
mostrar_cdi = st.sidebar.checkbox("CDI (Renda Fixa)", value=True)
mostrar_ipca = st.sidebar.checkbox("IPCA (Inflação)", value=True)
mostrar_ibov = st.sidebar.checkbox("Ibovespa (Mercado)", value=True)

# 3. FUNÇÕES DE DADOS
def busca_indice_bcb(codigo, d_ini, d_fim):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={d_ini.strftime('%d/%m/%Y')}&dataFinal={d_fim.strftime('%d/%m/%Y')}"
    try:
        r = requests.get(url, timeout=15)
        df = pd.DataFrame(r.json())
        df['data'] = pd.to_datetime(df['data'], dayfirst=True)
        df['valor'] = pd.to_numeric(df['valor']) / 100
        df = df.set_index('data')
        return (1 + df['valor']).cumprod()
    except: return pd.Series()

@st.cache_data(show_spinner=False)
def carregar_dados_ativos(t, d_ini, d_fim):
    t_sa = t if ".SA" in t else t + ".SA"
    # Baixa range maior para garantir cálculos de retorno
    df = yf.download([t_sa, "^BVSP"], start=d_ini - timedelta(days=60), end=d_fim + timedelta(days=2), progress=False)
    if df.empty: return None, None
    
    # Resolve problema de MultiIndex do Yahoo
    if isinstance(df.columns, pd.MultiIndex):
        df_t = df.xs(t_sa, axis=1, level=1).dropna()
        df_i = df.xs("^BVSP", axis=1, level=1).dropna()
    else: return None, None

    df_t.index = df_t.index.tz_localize(None)
    df_i.index = df_i.index.tz_localize(None)
    
    # Fator de Retorno Total (Adj Close) e Preço Seco (Close)
    df_t["TR_F"] = (1 + df_t["Adj Close"].pct_change().fillna(0)).cumprod()
    df_t["PR_F"] = (1 + df_t["Close"].pct_change().fillna(0)).cumprod()
    df_i["Norm"] = (1 + df_i["Close"].pct_change().fillna(0)).cumprod()
    
    return df_t, df_i

# 4. EXECUÇÃO
if ticker_input:
    df_acao, df_ibov_raw = carregar_dados_ativos(ticker_input, data_inicio, data_fim)
    s_cdi = busca_indice_bcb(12, data_inicio, data_fim)
    s_ipca = busca_indice_bcb(433, data_inicio, data_fim)

    if df_acao is not None:
        # --- GRÁFICO ---
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        tr_base = df_v["TR_F"] / df_v["TR_F"].iloc[0]
        pr_base = df_v["PR_F"] / df_v["PR_F"].iloc[0]
        
        fig = go.Figure()
        if mostrar_cdi and not s_cdi.empty:
            fig.add_trace(go.Scatter(x=s_cdi.index, y=(s_cdi/s_cdi.iloc[0]-1)*100, name='CDI', line=dict(color='gray', dash='dash')))
        if mostrar_ipca and not s_ipca.empty:
            fig.add_trace(go.Scatter(x=s_ipca.index, y=(s_ipca/s_ipca.iloc[0]-1)*100, name='IPCA', line=dict(color='red')))
        
        # Áreas coloridas
        fig.add_trace(go.Scatter(x=df_v.index, y=(pr_base-1)*100, fill='tozeroy', name='Valorização', line=dict(width=0), fillcolor='rgba(31,119,180,0.3)'))
        fig.add_trace(go.Scatter(x=df_v.index, y=(tr_base-1)*100, fill='tonexty', name='Proventos', line=dict(width=0), fillcolor='rgba(218,165,32,0.3)'))
        fig.add_trace(go.Scatter(x=df_v.index, y=(tr_base-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))
        
        fig.update_layout(template="plotly_white", hovermode="x unified", margin=dict(l=0,r=0,t=30,b=0))
        st.plotly_chart(fig, use_container_width=True)

        # --- SIMULAÇÃO ---
        st.subheader("Simulação de Patrimônio Acumulado")
        
        def simulacao_referenciada(anos):
            dt_fim = pd.to_datetime(data_fim)
            dt_ini = dt_fim - timedelta(days=anos*365)
            if dt_ini < pd.to_datetime(data_inicio): return None

            df_p = df_acao.loc[dt_ini:dt_fim].copy()
            # Pega 1º dia útil de cada mês
            datas = df_p.groupby(df_p.index.to_period('M')).head(1).index.tolist()
            
            vf_ativo = sum(valor_aporte * (df_acao["TR_F"].asof(dt_fim) / df_acao["TR_F"].asof(d)) for d in datas)
            vi = len(datas) * valor_aporte
            
            def calc_b(serie):
                if serie.empty: return 0
                return sum(valor_aporte * (serie.asof(dt_fim) / serie.asof(d)) for d in datas)

            return vf_ativo, vi, calc_b(s_cdi), calc_b(s_ipca), calc_b(df_ibov_raw["Norm"])

        cols = st.columns(3)
        for i, anos in enumerate([10, 5, 1]):
            res = simulacao_referenciada(anos)
            with cols[i]:
                if res:
                    vf, vi, v_cdi, v_ipca, v_ibov = res
                    st.markdown(f"""
                    <div class="total-card">
                        <div class="total-label">Total em {anos} anos</div>
                        <div class="total-amount">{formata_br(vf)}</div>
                    </div>
                    <div class="info-card">
                        <div class="card-header">Benchmarks</div>
                        <div class="card-item">🎯 <b>CDI:</b> {formata_br(v_cdi)}</div>
                        <div class="card-item">📈 <b>Ibovespa:</b> {formata_br(v_ibov)}</div>
                        <div class="card-item">🛡️ <b>IPCA:</b> {formata_br(v_ipca)}</div>
                        <hr>
                        <div class="card-item">💵 <b>Investido:</b> {formata_br(vi)}</div>
                        <div class="card-destaque">💰 Lucro: {formata_br(vf-vi)}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.info(f"Filtre {anos} anos no calendário.")

        # GUIA DE TERMOS
        st.markdown("""<div class="glossario-container">... (seu guia de termos aqui) ...</div>""", unsafe_allow_html=True)
