import streamlit as st
import yfinance as yf
import pandas as pd 
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

# Estilos CSS - Fiel à sua identidade visual
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
    .glossario-item { margin-bottom: 15px; line-height: 1.5; color: #475569; font-size: 0.9rem; }
    .glossario-item b { color: #1f77b4; font-size: 1rem; }
</style>
""", unsafe_allow_html=True)

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("Simulador de Acúmulo de Patrimônio")

# 2. BARRA LATERAL (Texto conforme imagem 5e6223.png)
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
<a href="https://www.instagram.com/ramoon.bastos?igsh=MTFiODlnZ28ybHFqdw%3D%3D&utm_source=qr" target="_blank" style="color: #1f77b4; text-decoration: none; font-weight: bold;">IG: Ramoon.Bastos</a>
</div>
""", unsafe_allow_html=True)

# 3. FUNÇÕES DE DADOS
def busca_indice_bcb(codigo, d_inicio, d_fim):
    s, e = d_inicio.strftime('%d/%m/%Y'), d_fim.strftime('%d/%m/%Y')
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={s}&dataFinal={e}"
    try:
        r = requests.get(url, timeout=30)
        df = pd.DataFrame(r.json())
        df['data'] = pd.to_datetime(df['data'], dayfirst=True)
        df['valor'] = pd.to_numeric(df['valor']) / 100
        return df.set_index('data')
    except: return pd.DataFrame()

@st.cache_data(show_spinner=False)
def carregar_dados_totais(t, d_ini, d_fim):
    t_sa = t if ".SA" in t else t + ".SA"
    # Baixamos um pouco antes para ter base de cálculo de retorno
    df = yf.download(t_sa, start=d_ini - timedelta(days=30), end=d_fim + timedelta(days=2), progress=False, auto_adjust=False)
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df.index = df.index.tz_localize(None)
    df["Total_Return_Factor"] = (1 + df["Adj Close"].pct_change().fillna(0)).cumprod()
    return df

@st.cache_data(show_spinner=False)
def carregar_ibov(d_ini, d_fim):
    df = yf.download("^BVSP", start=d_ini, end=d_fim, progress=False)
    if df.empty: return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df.index = df.index.tz_localize(None)
    df["valor_norm"] = (1 + df["Close"].pct_change().fillna(0)).cumprod()
    return df

# 4. LÓGICA PRINCIPAL
if ticker_input:
    df_acao = carregar_dados_totais(ticker_input, data_inicio, data_fim)
    df_cdi = busca_indice_bcb(12, data_inicio, data_fim)
    df_ipca = busca_indice_bcb(433, data_inicio, data_fim)
    df_ibov = carregar_ibov(data_inicio, data_fim)

    if df_acao is not None:
        # Gráfico principal
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        df_v["Ret_Total_Norm"] = (df_v["Total_Return_Factor"] / df_v["Total_Return_Factor"].iloc[0] - 1) * 100
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_v.index, y=df_v["Ret_Total_Norm"], name='RETORNO TOTAL', line=dict(color='black', width=3)))
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Simulação de Patrimônio Acumulado")
        
        # FUNÇÃO QUE RESPEITA A DATA DE INÍCIO DO CALENDÁRIO
        def calcular_patrimonio(anos_desejados):
            dt_final = pd.to_datetime(data_fim)
            dt_inicial_sim = dt_final - timedelta(days=anos_desejados * 365)
            
            # Se o período selecionado no calendário for menor que os anos do card, não calcula
            if dt_inicial_sim < pd.to_datetime(data_inicio): return None

            df_periodo = df_acao.loc[dt_inicial_sim:dt_final].copy()
            df_periodo['month'] = df_periodo.index.to_period('M')
            datas_aportes = df_periodo.groupby('month').head(1).index.tolist()
            
            # Ativo
            vf_ativo = 0
            for d in datas_aportes:
                fator = df_acao.loc[df_periodo.index[-1], "Total_Return_Factor"] / df_acao.loc[d, "Total_Return_Factor"]
                vf_ativo += valor_aporte * fator
            
            vi = len(datas_aportes) * valor_aporte
            
            # Benchmarks
            def calc_bench_sim(df_b, col='valor'):
                if df_b.empty: return 0
                idx_fim = df_b.index.get_indexer([dt_final], method='pad')[0]
                # Se for IBOV usa valor_norm, se for CDI/IPCA usa cumprod do valor
                serie = df_b[col] if col == 'valor_norm' else (1 + df_b[col]).cumprod()
                v_fim = serie.iloc[idx_fim]
                soma = 0
                for d in datas_aportes:
                    idx_ini = df_b.index.get_indexer([d], method='pad')[0]
                    soma += valor_aporte * (v_fim / serie.iloc[idx_ini])
                return soma

            return vf_ativo, vi, calc_bench_sim(df_cdi), calc_bench_sim(df_ipca), calc_bench_sim(df_ibov, 'valor_norm')

        cols = st.columns(3)
        for i, anos in enumerate([10, 5, 1]):
            res = calcular_patrimonio(anos)
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
                    st.info(f"Período de {anos} anos indisponível para o filtro de datas atual.")

        # GUIA DE TERMOS - Conforme imagem_5ee943.png
        st.markdown("""
        <div class="glossario-container">
            <h3 style="color: #1f77b4; margin-top:0;">📖 GUIA DE TERMOS E INDICADORES</h3>
            <div class="glossario-item">
                <b>• CDI (Certificado de Depósito Interbancário)</b><br>
                <span>É a régua da renda fixa. Representa o retorno de aplicações seguras como o Tesouro Selic. Serve para você avaliar se o risco de investir em ações trouxe um prêmio real.</span>
            </div>
            <div class="glossario-item">
                <b>• Correção IPCA (Inflação)</b><br>
                <span>Representa a atualização do seu dinheiro para o <b>valor presente</b>. Indica quanto você precisaria ter hoje para manter o mesmo poder de compra que tinha no passado.</span>
            </div>
            <div class="glossario-item">
                <b>• Ibovespa</b><br>
                <span>É o termômetro do mercado brasileiro. Reflete a média de desempenho das maiores empresas da Bolsa. Comparar seu ativo com ele mostra se você está batendo o mercado.</span>
            </div>
            <div class="glossario-item">
                <b>• Capital Nominal Investido</b><br>
                <span>É o somatório bruto de todos os aportes mensais que você fez. É o dinheiro que efetivamente saiu da sua conta corrente ao longo do tempo.</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    else: st.error("Ticker não encontrado ou sem dados para o período.")
