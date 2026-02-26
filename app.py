import streamlit as st
import yfinance as yf
import pandas as pd 
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

# Estilos CSS - Mantidos exatamente como os seus
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #1f77b4; }
    .resumo-objetivo { font-size: 0.9rem; color: #333; background-color: #e8f0fe; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 5px solid #1f77b4; line-height: 1.6; }
    
    .total-card { 
        background-color: #f8fafc; 
        border: 1px solid #e2e8f0; 
        padding: 15px; 
        border-radius: 12px; 
        margin-bottom: 10px; 
        text-align: center; 
    }
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
O simulador calcula o acúmulo real de patrimônio via <b>Retorno Total</b>, reinvestindo automaticamente proventos (Div/JCP).
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker", "BBAS3").upper().strip()
valor_aporte = st.sidebar.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

st.sidebar.subheader("Período da Simulação")
d_fim_padrao = date.today() - timedelta(days=2) 
d_ini_padrao = d_fim_padrao - timedelta(days=365*10)
data_inicio = st.sidebar.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY")

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
        df = yf.download(t_sa, start="2005-01-01", progress=False, auto_adjust=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize(None)
        
        # FATOR INTELIGENTE: Usa o Adj Close apenas para calcular a variação real (Dividendos Reinvestidos)
        # Mas as compras são feitas pelo preço real (Close)
        df["Total_Return_Factor"] = (1 + df["Adj Close"].pct_change().fillna(0)).cumprod()
        return df[['Close', 'Adj Close', 'Total_Return_Factor']]
    except: return None

# 4. LÓGICA PRINCIPAL
if ticker_input:
    with st.spinner("Sincronizando dados de mercado..."):
        s_cdi = busca_indice_bcb(12, data_inicio, data_fim) if mostrar_cdi else pd.Series()
        s_ipca = busca_indice_bcb(433, data_inicio, data_fim) if mostrar_ipca else pd.Series()
        df_acao = carregar_dados_completos(ticker_input)
        df_ibov_c = pd.Series()
        try:
            ibov_raw = yf.download("^BVSP", start=data_inicio, end=data_fim, progress=False)
            if not ibov_raw.empty:
                if isinstance(ibov_raw.columns, pd.MultiIndex): ibov_raw.columns = ibov_raw.columns.get_level_values(0)
                df_ibov_c = (1 + ibov_raw['Close'].pct_change().fillna(0)).cumprod()
        except: pass

    if df_acao is not None:
        # Filtragem baseada na data de início selecionada
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            # Gráfico (Normalizado pela data de início do calendário)
            df_v["Total_Fact_Chart"] = df_v["Total_Return_Factor"] / df_v["Total_Return_Factor"].iloc[0]
            df_v["Price_Base_Chart"] = df_v["Close"] / df_v["Close"].iloc[0]
            
            fig = go.Figure()
            if not s_cdi.empty: fig.add_trace(go.Scatter(x=s_cdi.index, y=(s_cdi/s_cdi.iloc[0]-1)*100, name='CDI', line=dict(color='gray', width=2, dash='dash')))
            if not s_ipca.empty: fig.add_trace(go.Scatter(x=s_ipca.index, y=(s_ipca/s_ipca.iloc[0]-1)*100, name='IPCA', line=dict(color='red', width=2)))
            if not df_ibov_c.empty: fig.add_trace(go.Scatter(x=df_ibov_c.index, y=(df_ibov_c/df_ibov_c.iloc[0]-1)*100, name='Ibovespa', line=dict(color='orange', width=2)))
            
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base_Chart"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-df_v["Price_Base_Chart"])*100, stackgroup='one', name='Proventos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))
            
            fig.update_layout(template="plotly_white", hovermode="x unified", yaxis=dict(side="right", ticksuffix="%", tickformat=".0f"), margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Simulação de Patrimônio Acumulado")
            
            # CONTA MATEMÁTICA INTELIGENTE: Simula cada aporte individualmente
            def calcular_tudo(df_full, valor_mensal, anos, s_cdi_f, s_ipca_f, s_ibov_f, d_ini, d_fim):
                dt_ini = pd.to_datetime(d_ini)
                dt_fim = pd.to_datetime(d_fim)
                
                # Só calcula se o período do calendário comportar os anos pedidos
                if (dt_fim - dt_ini).days / 365.25 < (anos - 0.05): return [0]*6

                df_periodo = df_full.loc[dt_ini:dt_fim].copy()
                df_periodo['month'] = df_periodo.index.to_period('M')
                
                # Pega o primeiro dia útil de cada mês dentro do período
                datas_aportes = df_periodo.groupby('month').head(1).index.tolist()
                # Limita aos primeiros X anos a partir da DATA DE INÍCIO do calendário
                datas_aportes = datas_aportes[:(anos * 12)]
                
                if not datas_aportes: return [0]*6
                
                data_final = df_periodo.index[-1]
                patrimonio_final = 0
                
                for d in datas_aportes:
                    # Lógica: Quantas ações comprei (R$ / Preço Real) * Evolução do Retorno Total
                    fator_crescimento = df_full.loc[data_final, "Total_Return_Factor"] / df_full.loc[d, "Total_Return_Factor"]
                    patrimonio_final += valor_mensal * fator_crescimento

                vi = len(datas_aportes) * valor_mensal
                
                def calc_bench(serie):
                    if serie.empty: return 0
                    v_fim = serie.asof(data_final)
                    return sum(valor_mensal * (v_fim / serie.asof(d)) for d in datas_aportes)

                return patrimonio_final, vi, patrimonio_final - vi, calc_bench(s_cdi_f), calc_bench(s_ipca_f), calc_bench(s_ibov_f)

            col1, col2, col3 = st.columns(3)
            for anos, col in [(10, col1), (5, col2), (1, col3)]:
                vf, vi, lucro, v_cdi, v_ipca, v_ibov = calcular_tudo(df_acao, valor_aporte, anos, s_cdi, s_ipca, df_ibov_c, data_inicio, data_fim)
                titulo_col = f"Total em {anos} anos" if anos > 1 else "Total em 1 ano"
                with col:
                    if vf > 0:
                        st.markdown(f'<div class="total-card"><div class="total-label">{titulo_col}</div><div class="total-amount">{formata_br(vf)}</div></div>', unsafe_allow_html=True)
                        st.markdown(f"""
                        <div class="info-card">
                            <div class="card-header">Benchmarks (Valor Corrigido)</div>
                            <div class="card-item">🎯 <b>CDI:</b> {formata_br(v_cdi)}</div>
                            <div class="card-item">📈 <b>Ibovespa:</b> {formata_br(v_ibov)}</div>
                            <div class="card-item">🛡️ <b>Correção IPCA:</b> {formata_br(v_ipca)}</div>
                            <hr style="margin: 10px 0; border: 0; border-top: 1px solid #e2e8f0;">
                            <div class="card-header">Análise da Carteira</div>
                            <div class="card-item">💵 <b>Capital Nominal Investido:</b> {formata_br(vi)}</div>
                            <div class="card-destaque">💰 Lucro Acumulado: {formata_br(lucro)}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="total-card"><div class="total-label">{titulo_col}</div><div style="font-size:0.8rem; color:#94a3b8; margin-top:10px;">Período Insuficiente no Calendário</div></div>', unsafe_allow_html=True)

            st.markdown("""<div class="glossario-container"><h3 style="color: #1f77b4; margin-top:0;">Guia de Termos e Indicadores</h3>...</div>""", unsafe_allow_html=True)
            
    else: st.error("Ticker não encontrado.")
else: st.info("💡 Digite um Ticker no menu lateral para iniciar.")
