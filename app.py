import streamlit as st
import yfinance as yf
import pandas as pd 
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

# Estilos CSS Restaurados
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #1f77b4; }
    .resumo-objetivo { font-size: 0.9rem; color: #333; background-color: #e8f0fe; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 5px solid #1f77b4; line-height: 1.6; }
    
    .total-card { background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 15px; border-radius: 12px; margin-bottom: 10px; text-align: center; min-height: 110px; display: flex; flex-direction: column; justify-content: center; }
    .total-label { font-size: 0.75rem; font-weight: 800; color: #64748b; text-transform: uppercase; margin-bottom: 5px; }
    .total-amount { font-size: 1.6rem; font-weight: 800; color: #1f77b4; }
    
    .info-card { background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 18px; border-radius: 12px; margin-top: 5px; min-height: 280px; }
    .card-header { font-size: 0.75rem; font-weight: 800; color: #64748b; text-transform: uppercase; margin-bottom: 10px; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; }
    .card-item { font-size: 0.9rem; margin-bottom: 6px; color: #1e293b; }
    .card-destaque { font-size: 0.95rem; font-weight: 700; color: #0f172a; margin-top: 8px; border-top: 1px solid #e2e8f0; padding-top: 8px; }
    
    .glossario-container { margin-top: 40px; padding: 25px; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; }
    .glossario-termo { font-weight: 800; color: #1f77b4; font-size: 1rem; display: block; }
    .glossario-def { color: #475569; font-size: 0.9rem; line-height: 1.5; display: block; margin-bottom: 15px; }
    .aviso-periodo { font-size: 0.85rem; color: #94a3b8; font-style: italic; }
</style>
""", unsafe_allow_html=True)

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("Simulador de Acúmulo de Patrimônio")

# 2. BARRA LATERAL - TEXTO RESTAURADO
st.sidebar.markdown("""
<div class="resumo-objetivo">
👋 <b>Bem-vindo!</b><br>
O simulador calcula o acúmulo real de patrimônio via <b>Retorno Total</b>, reinvestindo automaticamente proventos (Div/JCP). Para garantir precisão técnica, utilizamos um algoritmo de ajuste histórico que neutraliza distorções causadas por compras, divisões (splits), grupamentos e bonificações, permitindo uma análise fiel da evolução do seu capital.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker", "").upper().strip()
valor_aporte = st.sidebar.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

# Sugestão de datas com margem para garantir os 10 anos
d_fim_sugestao = date.today() - timedelta(days=2) 
d_ini_sugestao = d_fim_sugestao - timedelta(days=365*10 + 5) 

data_inicio = st.sidebar.date_input("Início", d_ini_sugestao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_sugestao, format="DD/MM/YYYY")

btn_analisar = st.sidebar.button("🔍 Analisar Patrimônio")

st.sidebar.subheader("Benchmarks no Gráfico")
mostrar_cdi = st.sidebar.checkbox("CDI (Renda Fixa)", value=True)
mostrar_ipca = st.sidebar.checkbox("IPCA (Inflação)", value=True)
mostrar_ibov = st.sidebar.checkbox("Ibovespa (Mercado)", value=True)

# 3. FUNÇÕES DE SUPORTE
def busca_indice_bcb(codigo, d_inicio, d_fim):
    s, e = d_inicio.strftime('%d/%m/%Y'), d_fim.strftime('%d/%m/%Y')
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={s}&dataFinal={e}"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            df = pd.DataFrame(r.json())
            df['data'] = pd.to_datetime(df['data'], dayfirst=True)
            df['valor'] = pd.to_numeric(df['valor']) / 100
            df = df.set_index('data')
            return (1 + df['valor']).cumprod()
    except: pass
    return pd.Series(dtype='float64')

@st.cache_data(show_spinner=False)
def carregar_dados_completos(t):
    if not t: return None
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        df = yf.download(t_sa, start="2000-01-01", progress=False, auto_adjust=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize(None)
        df["Ret_Total"] = df["Adj Close"].pct_change().fillna(0)
        df["Ret_Preco"] = df["Close"].pct_change().fillna(0)
        df["Yield_Fiscalizado"] = (df["Ret_Total"] - df["Ret_Preco"]).apply(lambda x: x if x > 0 else 0)
        df["Total_Fact"] = (1 + df["Ret_Preco"] + df["Yield_Fiscalizado"]).cumprod()
        return df[['Close', 'Adj Close', 'Total_Fact']]
    except: return None

# 4. LOGICA PRINCIPAL
if ticker_input:
    df_acao = carregar_dados_completos(ticker_input)
    if df_acao is not None:
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            df_v["Total_Fact_Chart"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
            df_v["Price_Base_Chart"] = df_v["Close"] / df_v["Close"].iloc[0]
            
            fig = go.Figure()
            if mostrar_cdi:
                s_cdi_g = busca_indice_bcb(12, data_inicio, data_fim)
                if not s_cdi_g.empty: fig.add_trace(go.Scatter(x=s_cdi_g.index, y=(s_cdi_g/s_cdi_g.iloc[0]-1)*100, name='CDI', line=dict(color='gray', width=2, dash='dash')))
            
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base_Chart"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-df_v["Price_Base_Chart"])*100, stackgroup='one', name='Proventos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))
            fig.update_layout(template="plotly_white", hovermode="x unified", margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Simulação de Patrimônio Acumulado")
            st.caption(f"Cálculos baseados em aportes mensais finalizando em {data_fim.strftime('%d/%m/%Y')}")

            # FUNÇÃO DE CÁLCULO DINÂMICO COM IBOVESPA RESTAURADO
            def calcular_janela_movel(df_full, v_aporte, anos, d_fim_alvo, d_inicio_limite):
                d_inicio_janela = pd.to_datetime(d_fim_alvo) - pd.DateOffset(years=anos)
                if d_inicio_janela < pd.to_datetime(d_inicio_limite) or d_inicio_janela < df_full.index[0]:
                    return None
                
                df_janela = df_full.loc[d_inicio_janela:pd.to_datetime(d_fim_alvo)].copy()
                df_janela['month'] = df_janela.index.to_period('M')
                datas_aportes = df_janela.groupby('month').head(1).index.tolist()
                
                # Ação
                cotas = sum(v_aporte / df_full.loc[d, 'Close'] for d in datas_aportes)
                fator_tr = df_full.loc[pd.to_datetime(d_fim_alvo), "Total_Fact"] / df_full.loc[datas_aportes[0], "Total_Fact"]
                vf_ativo = cotas * df_full.loc[pd.to_datetime(d_fim_alvo), 'Close'] * (fator_tr / (df_full.loc[pd.to_datetime(d_fim_alvo), 'Close'] / df_full.loc[datas_aportes[0], 'Close']))
                
                # Benchmarks
                s_cdi = busca_indice_bcb(12, d_inicio_janela, d_fim_alvo)
                s_ipca = busca_indice_bcb(433, d_inicio_janela, d_fim_alvo)
                
                ibov_vf = 0
                try:
                    ibov = yf.download("^BVSP", start=d_inicio_janela, end=pd.to_datetime(d_fim_alvo)+timedelta(days=1), progress=False)
                    if not ibov.empty:
                        if isinstance(ibov.columns, pd.MultiIndex): ibov.columns = ibov.columns.get_level_values(0)
                        ibov_vf = sum(v_aporte * (ibov['Close'].iloc[-1] / ibov.loc[ibov.index.asof(d), 'Close']) for d in datas_aportes)
                except: pass

                def calc_ref(serie):
                    if serie.empty: return 0
                    return sum(v_aporte * (serie.iloc[-1] / serie.iloc[serie.index.get_indexer([d], method='backfill')[0]]) for d in datas_aportes)

                return {
                    "vf": vf_ativo, "vi": len(datas_aportes) * v_aporte, "lucro": vf_ativo - (len(datas_aportes) * v_aporte),
                    "cdi": calc_ref(s_cdi), "ipca": calc_ref(s_ipca), "ibov": ibov_vf
                }

            col1, col2, col3 = st.columns(3)
            for anos, col in [(10, col1), (5, col2), (1, col3)]:
                res = calcular_janela_movel(df_acao, valor_aporte, anos, data_fim, data_inicio)
                titulo_col = f"Total em {anos} anos" if anos > 1 else "Total em 1 ano"
                with col:
                    if res:
                        st.markdown(f'<div class="total-card"><div class="total-label">{titulo_col}</div><div class="total-amount">{formata_br(res["vf"])}</div></div>', unsafe_allow_html=True)
                        st.markdown(f"""
                        <div class="info-card">
                            <div class="card-header">Benchmarks na Janela</div>
                            <div class="card-item">🎯 <b>CDI:</b> {formata_br(res["cdi"])}</div>
                            <div class="card-item">📈 <b>Ibovespa:</b> {formata_br(res["ibov"])}</div>
                            <div class="card-item">🛡️ <b>Correção IPCA:</b> {formata_br(res["ipca"])}</div>
                            <hr style="margin: 10px 0; border: 0; border-top: 1px solid #e2e8f0;">
                            <div class="card-header">Análise da Carteira</div>
                            <div class="card-item">💵 <b>Capital Nominal Investido:</b> {formata_br(res["vi"])}</div>
                            <div class="card-destaque">💰 Lucro Acumulado: {formata_br(res["lucro"])}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="total-card"><div class="total-label">{titulo_col}</div><div class="aviso-periodo">Período Insuficiente</div></div>', unsafe_allow_html=True)
                        st.markdown('<div class="info-card"><div class="aviso-periodo">Aumente o intervalo de datas no menu lateral para habilitar esta janela de tempo.</div></div>', unsafe_allow_html=True)

            # GUIA DE TERMOS TOTALMENTE RESTAURADO
            st.markdown("""
<div class="glossario-container">
<h3 style="color: #1f77b4; margin-top:0;">Guia de Termos e Indicadores</h3>
<span class="glossario-termo">• CDI (Certificado de Depósito Interbancário)</span>
<span class="glossario-def">Referência da renda fixa que representa o retorno de aplicações seguras (ex: Tesouro Selic). Serve para avaliar se o risco de investir em ações trouxe um prêmio sobre a taxa básica.</span>
<span class="glossario-termo">• Correção IPCA (Inflação)</span>
<span class="glossario-def">Atualiza o valor investido para o poder de compra atual. Indica quanto você precisaria ter hoje para manter o mesmo patrimônio real do passado.</span>
<span class="glossario-termo">• Ibovespa</span>
<span class="glossario-def">Principal índice da bolsa brasileira, composto pelas ações com maior volume de negociação. É utilizado como benchmark para medir se a ação escolhida está superando a média do mercado nacional.</span>
<span class="glossario-termo">• Capital Nominal Investido</span>
<span class="glossario-def">É o somatório bruto de todos os aportes mensais que saíram do seu bolso ao longo do tempo, sem considerar juros.</span>
<span class="glossario-termo">• Lucro Acumulado</span>
<span class="glossario-def">Diferença entre o patrimônio atual e o capital nominal investido, especificamente para o investimento realizado nesta ação.</span>
<span class="glossario-termo">• Retorno Total</span>
<span class="glossario-def">Métrica definitiva que combina a valorização da cota com o reinvestimento de proventos. O cálculo neutraliza distorções causadas por compras, desdobramentos (splits), grupamentos e bonificações.</span>
</div>""", unsafe_allow_html=True)
            
    else: st.error("Ticker não encontrado.")
else: st.info("💡 Digite um Ticker no menu lateral para iniciar a análise.")
