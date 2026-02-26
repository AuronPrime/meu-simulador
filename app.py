import streamlit as st
import yfinance as yf
import pandas as pd 
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

# Estilos CSS - Identidade Visual Original
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

# 2. BARRA LATERAL (Conforme imagem 5e6223.png)
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

# 3. FUNÇÕES DE DADOS E CÁLCULO
@st.cache_data(show_spinner=False)
def busca_indices_economicos(d_ini, d_fim):
    def get_bcb(codigo):
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={d_ini.strftime('%d/%m/%Y')}&dataFinal={d_fim.strftime('%d/%m/%Y')}"
        try:
            r = requests.get(url, timeout=15)
            df = pd.DataFrame(r.json())
            df['data'] = pd.to_datetime(df['data'], dayfirst=True)
            df['valor'] = pd.to_numeric(df['valor']) / 100
            return df.set_index('data')
        except: return pd.DataFrame()
    return get_bcb(12), get_bcb(433)

@st.cache_data(show_spinner=False)
def carregar_tudo(t, d_ini, d_fim):
    t_sa = t if ".SA" in t else t + ".SA"
    # Baixa dados extras para garantir o cálculo do primeiro dia
    df = yf.download([t_sa, "^BVSP"], start=d_ini - timedelta(days=60), end=d_fim + timedelta(days=2), progress=False, auto_adjust=False)
    if df.empty: return None, None
    
    if isinstance(df.columns, pd.MultiIndex):
        df_ticker = df.xs(t_sa, axis=1, level=1).copy()
        df_ibov = df.xs("^BVSP", axis=1, level=1).copy()
    else: return None, None

    df_ticker.index = df_ticker.index.tz_localize(None)
    df_ibov.index = df_ibov.index.tz_localize(None)
    
    df_ticker["TR_Factor"] = (1 + df_ticker["Adj Close"].pct_change().fillna(0)).cumprod()
    df_ibov["Norm"] = (1 + df_ibov["Close"].pct_change().fillna(0)).cumprod()
    
    return df_ticker, df_ibov

# 4. LÓGICA DE INTERFACE
if ticker_input:
    df_acao, df_ibov_raw = carregar_tudo(ticker_input, data_inicio, data_fim)
    df_cdi, df_ipca = busca_indices_economicos(data_inicio, data_fim)

    if df_acao is not None:
        # GRÁFICO RESTAURADO (Com Proventos e Valorização separados)
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        df_v["TR_Chart"] = df_v["TR_Factor"] / df_v["TR_Factor"].iloc[0]
        df_v["Price_Chart"] = df_v["Close"] / df_v["Close"].iloc[0]
        
        fig = go.Figure()
        # Benchmarks no gráfico
        if mostrar_cdi and not df_cdi.empty:
            s_cdi = (1 + df_cdi['valor']).cumprod()
            fig.add_trace(go.Scatter(x=df_cdi.index, y=(s_cdi/s_cdi.iloc[0]-1)*100, name='CDI', line=dict(color='gray', dash='dash')))
        
        # Áreas coloridas conforme sua versão original
        fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Chart"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
        fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["TR_Chart"]-df_v["Price_Chart"])*100, stackgroup='one', name='Proventos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
        fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["TR_Chart"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))
        
        fig.update_layout(template="plotly_white", hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Simulação de Patrimônio Acumulado")
        
        # MATEMÁTICA QUE MUDA COM O CALENDÁRIO
        def simulacao_dinamica(anos):
            dt_fim = pd.to_datetime(data_fim)
            dt_ini = dt_fim - timedelta(days=anos*365)
            
            # Bloqueia se o calendário não tiver data suficiente
            if dt_ini < pd.to_datetime(data_inicio): return None

            df_p = df_acao.loc[dt_ini:dt_fim].copy()
            df_p['m'] = df_p.index.to_period('M')
            datas = df_p.groupby('m').head(1).index.tolist()
            
            # Cálculo Ativo
            vf = sum(valor_aporte * (df_acao.loc[df_p.index[-1], "TR_Factor"] / df_acao.loc[d, "TR_Factor"]) for d in datas)
            vi = len(datas) * valor_aporte
            
            # Benchmark genérico
            def bench(df_ref, col='valor', is_rate=True):
                if df_ref.empty: return 0
                serie = (1 + df_ref[col]).cumprod() if is_rate else df_ref[col]
                v_fim = serie.asof(dt_fim)
                return sum(valor_aporte * (v_fim / serie.asof(d)) for d in datas)

            return vf, vi, bench(df_cdi), bench(df_ipca), bench(df_ibov_raw, 'Norm', False)

        cols = st.columns(3)
        for i, anos in enumerate([10, 5, 1]):
            res = simulacao_dinamica(anos)
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
                    st.info(f"Filtre mais de {anos} anos no calendário.")

        # GUIA COMPLETO (Conforme imagem_5378de.jpg)
        st.markdown("""
        <div class="glossario-container">
            <h3 style="color: #1f77b4; margin-top:0; border-bottom: 2px solid #e8f0fe; padding-bottom: 10px;">📖 GUIA DE TERMOS E INDICADORES</h3>
            <div class="glossario-item">
                <b>• CDI (Certificado de Depósito Interbancário)</b>
                Representa a rentabilidade média das aplicações de renda fixa pós-fixadas. É o "mínimo" que um investimento deve render para valer o risco.
            </div>
            <div class="glossario-item">
                <b>• Correção IPCA (Inflação)</b>
                Mostra quanto seu dinheiro deveria render apenas para não perder o poder de compra. É a base para entender o lucro real.
            </div>
            <div class="glossario-item">
                <b>• Ibovespa</b>
                O principal índice da bolsa brasileira. Serve para comparar se sua escolha de ação individual está ganhando ou perdendo da média do mercado.
            </div>
            <div class="glossario-item">
                <b>• Capital Nominal Investido</b>
                A soma bruta de todos os seus aportes mensais, sem considerar nenhum rendimento.
            </div>
            <div class="glossario-item">
                <b>• Lucro Acumulado</b>
                A diferença real entre o patrimônio final e o capital nominal que saiu do seu bolso.
            </div>
        </div>
        """, unsafe_allow_html=True)
