import streamlit as st
import yfinance as yf
import pandas as pd 
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

# 1. CONFIGURAÇÃO E ESTILO
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
    .glossario-item { margin-bottom: 18px; line-height: 1.6; color: #475569; font-size: 0.95rem; }
    .glossario-item b { color: #1f77b4; font-size: 1.05rem; display: block; margin-bottom: 4px; }
</style>
""", unsafe_allow_html=True)

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("Simulador de Acúmulo de Patrimônio")

# 2. SIDEBAR - RESTAURADA
st.sidebar.markdown("""
<div class="resumo-objetivo">
👋 <b>Bem-vindo!</b><br>
O simulador calcula o acúmulo real de patrimônio via <b>Retorno Total</b>, reinvestindo automaticamente proventos (Div/JCP). Para garantir precisão técnica, utilizamos um algoritmo de ajuste histórico que neutraliza distorções causadas por compras, divisões (splits), grupamentos e bonificações, permitindo uma análise fiel da evolução do seu capital.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker", "BBAS3").upper().strip()
valor_aporte = st.sidebar.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

st.sidebar.subheader("Período da Simulação")
d_fim_padrao = date.today() - timedelta(days=2) 
d_ini_padrao = d_fim_padrao - timedelta(days=365*10 + 5)
data_inicio = st.sidebar.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY")

st.sidebar.button("🔍 Analisar Patrimônio")

st.sidebar.subheader("Benchmarks no Gráfico")
mostrar_cdi = st.sidebar.checkbox("CDI (Renda Fixa)", value=True)
mostrar_ipca = st.sidebar.checkbox("IPCA (Inflação)", value=True)
mostrar_ibov = st.sidebar.checkbox("Ibovespa (Mercado)", value=True)

st.sidebar.markdown(f"""
<div style="font-size: 0.85rem; color: #64748b; margin-top: 25px; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 15px;">
Desenvolvido por: <br>
<a href="https://www.instagram.com/ramoon.bastos" target="_blank" style="color: #1f77b4; text-decoration: none; font-weight: bold;">IG: Ramoon.Bastos</a>
</div>
""", unsafe_allow_html=True)

# 3. FUNÇÕES DE DADOS (BLINDADAS)
@st.cache_data(show_spinner=False)
def busca_macro(d_ini, d_fim):
    def get_bcb(c):
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{c}/dados?formato=json&dataInicial={d_ini.strftime('%d/%m/%Y')}&dataFinal={d_fim.strftime('%d/%m/%Y')}"
        try:
            r = requests.get(url, timeout=10)
            df = pd.DataFrame(r.json())
            df['data'] = pd.to_datetime(df['data'], dayfirst=True)
            df['v'] = pd.to_numeric(df['valor']) / 100
            return df.set_index('data')
        except: return pd.DataFrame()
    return get_bcb(12), get_bcb(433)

@st.cache_data(show_spinner=False)
def carregar_ativos(t, d_ini, d_fim):
    t_sa = t if ".SA" in t else t + ".SA"
    # Baixamos dados extras para garantir o cálculo do primeiro dia
    df = yf.download([t_sa, "^BVSP"], start=d_ini - timedelta(days=60), end=d_fim + timedelta(days=2), progress=False)
    if df.empty: return None, None
    
    # Tratamento para erro de MultiIndex (o que causou o KeyError)
    if isinstance(df.columns, pd.MultiIndex):
        df_t = df.xs(t_sa, axis=1, level=1).copy().dropna()
        df_i = df.xs("^BVSP", axis=1, level=1).copy().dropna()
    else:
        df_t = df.copy() # Caso não venha multiindex
        df_i = pd.DataFrame()

    df_t.index = df_t.index.tz_localize(None)
    df_i.index = df_i.index.tz_localize(None)
    
    # Fatores de crescimento
    df_t["TR_F"] = (1 + df_t["Adj Close"].pct_change().fillna(0)).cumprod()
    df_t["PR_F"] = (1 + df_t["Close"].pct_change().fillna(0)).cumprod()
    df_i["Norm"] = (1 + df_i["Close"].pct_change().fillna(0)).cumprod()
    
    return df_t, df_i

# 4. LÓGICA DE INTERFACE
if ticker_input:
    df_acao, df_ibov_raw = carregar_ativos(ticker_input, data_inicio, data_fim)
    df_cdi, df_ipca = busca_macro(data_inicio, data_fim)

    if df_acao is not None:
        # --- GRÁFICO COMPLETO (IPCA + CDI + ÁREAS) ---
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        tr_base = df_v["TR_F"] / df_v["TR_F"].iloc[0]
        pr_base = df_v["PR_F"] / df_v["PR_F"].iloc[0]
        
        fig = go.Figure()

        # Áreas (Valorização e Proventos)
        fig.add_trace(go.Scatter(x=df_v.index, y=(pr_base-1)*100, fill='tozeroy', name='Valorização', line=dict(width=0), fillcolor='rgba(31,119,180,0.3)'))
        fig.add_trace(go.Scatter(x=df_v.index, y=(tr_base-1)*100, fill='tonexty', name='Proventos', line=dict(width=0), fillcolor='rgba(218,165,32,0.3)'))
        
        # Benchmarks no Gráfico
        if mostrar_cdi and not df_cdi.empty:
            c_base = (1+df_cdi['v']).cumprod()
            fig.add_trace(go.Scatter(x=df_cdi.index, y=(c_base/c_base.iloc[0]-1)*100, name='CDI', line=dict(color='gray', dash='dash')))
        
        if mostrar_ipca and not df_ipca.empty:
            i_base = (1+df_ipca['v']).cumprod()
            fig.add_trace(go.Scatter(x=df_ipca.index, y=(i_base/i_base.iloc[0]-1)*100, name='IPCA', line=dict(color='red')))

        if mostrar_ibov and not df_ibov_raw.empty:
            ib_base = df_ibov_raw["Norm"] / df_ibov_raw["Norm"].asof(pd.to_datetime(data_inicio))
            fig.add_trace(go.Scatter(x=df_ibov_raw.index, y=(ib_base-1)*100, name='IBOVESPA', line=dict(color='orange')))

        fig.add_trace(go.Scatter(x=df_v.index, y=(tr_base-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))

        fig.update_layout(template="plotly_white", hovermode="x unified", margin=dict(l=0,r=0,t=20,b=0), yaxis=dict(ticksuffix="%"))
        st.plotly_chart(fig, use_container_width=True)

        # --- SIMULAÇÃO DE PATRIMÔNIO (RESPEITANDO O CALENDÁRIO) ---
        st.subheader("Simulação de Patrimônio Acumulado")
        
        def simular(anos_atras):
            dt_fim = pd.to_datetime(data_fim)
            dt_ini = dt_fim - timedelta(days=anos_atras * 365)
            
            if dt_ini < pd.to_datetime(data_inicio): return None

            df_p = df_acao.loc[dt_ini:dt_fim].copy()
            datas_aportes = df_p.groupby(df_p.index.to_period('M')).head(1).index.tolist()
            
            vf = sum(valor_aporte * (df_acao["TR_F"].asof(dt_fim) / df_acao["TR_F"].asof(d)) for d in datas_aportes)
            vi = len(datas_aportes) * valor_aporte
            
            def calc_b(df_b, col='v', is_rate=True):
                if df_b.empty: return 0
                s = (1+df_b[col]).cumprod() if is_rate else df_b[col]
                v_f = s.asof(dt_fim)
                return sum(valor_aporte * (v_f / s.asof(d)) for d in datas_aportes)

            return vf, vi, calc_b(df_cdi), calc_b(df_ipca), calc_b(df_ibov_raw, 'Norm', False)

        cols = st.columns(3)
        for i, anos in enumerate([10, 5, 1]):
            res = simular(anos)
            with cols[i]:
                if res:
                    vf, vi, v_cdi, v_ipca, v_ibov = res
                    st.markdown(f'<div class="total-card"><div class="total-label">Total em {anos} anos</div><div class="total-amount">{formata_br(vf)}</div></div>', unsafe_allow_html=True)
                    st.markdown(f"""
                    <div class="info-card">
                        <div class="card-header">Benchmarks (Valor Corrigido)</div>
                        <div class="card-item">🎯 <b>CDI:</b> {formata_br(v_cdi)}</div>
                        <div class="card-item">📈 <b>Ibovespa:</b> {formata_br(v_ibov)}</div>
                        <div class="card-item">🛡️ <b>Correção IPCA:</b> {formata_br(v_ipca)}</div>
                        <hr style="margin: 10px 0; border: 0; border-top: 1px solid #e2e8f0;">
                        <div class="card-header">Análise da Carteira</div>
                        <div class="card-item">💵 <b>Capital Nominal Investido:</b> {formata_br(vi)}</div>
                        <div class="card-destaque">💰 Lucro Acumulado: {formata_br(vf-vi)}</div>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.info(f"O calendário precisa cobrir {anos} ano(s).")

        # --- GUIA DE TERMOS COMPLETO ---
        st.markdown("""
        <div class="glossario-container">
            <h3 style="color: #1f77b4; margin-top:0;">📖 GUIA DE TERMOS E INDICADORES</h3>
            <div class="glossario-item"><b>• CDI (Certificado de Depósito Interbancário)</b>Régua da renda fixa. Mostra o retorno de aplicações seguras como o Tesouro Selic.</div>
            <div class="glossario-item"><b>• Correção IPCA (Inflação)</b>Atualização do seu dinheiro para o <b>valor presente</b>. Indica o poder de compra.</div>
            <div class="glossario-item"><b>• Ibovespa</b>Termômetro da Bolsa brasileira (média das maiores empresas).</div>
            <div class="glossario-item"><b>• Capital Nominal Investido</b>Somatório bruto de todos os seus aportes mensais.</div>
            <div class="glossario-item"><b>• Lucro Acumulado</b>Ganho real somando valorização e dividendos recebidos.</div>
        </div>
        """, unsafe_allow_html=True)
