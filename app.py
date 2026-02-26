import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #1f77b4; }
    .resumo-objetivo { font-size: 0.9rem; color: #333; background-color: #e8f0fe; padding: 12px; border-radius: 8px; margin-bottom: 15px; border-left: 5px solid #1f77b4; line-height: 1.4; }
    
    .info-card {
        background-color: #f1f3f6; 
        border: 1px solid #d1d9e6; 
        padding: 18px; 
        border-radius: 12px; 
        margin-top: 10px; 
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    
    .card-header { font-size: 0.75rem; font-weight: 800; color: #4b5563; text-transform: uppercase; margin-bottom: 10px; border-bottom: 1px solid #cbd5e1; padding-bottom: 5px; }
    .card-item { font-size: 0.9rem; margin-bottom: 4px; color: #1f2937; }
    .card-destaque { font-size: 0.95rem; font-weight: 700; color: #166534; margin-top: 8px; }
    
    .glossario { font-size: 0.85rem; color: #444; margin-top: 30px; border-top: 2px solid #eee; padding-top: 20px; background-color: #f9f9f9; padding: 15px; border-radius: 10px; line-height: 1.6; }
    .glossario-item { margin-bottom: 12px; }
    </style>
    """, unsafe_allow_html=True)

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("📊 Simulador de Acúmulo de Patrimônio")

# 2. BARRA LATERAL
st.sidebar.markdown("""
<div class="resumo-objetivo">
<b>Objetivo:</b> Analisar o <b>Total Return</b> de um ativo, calculando o acúmulo real via <b>Proventos (Div/JCP)</b>. O algoritmo neutraliza distorções de <b>splits, grupamentos e bonificações</b>.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker (ex: BBAS3, ITUB4)", "").upper().strip()
valor_aporte = st.sidebar.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

st.sidebar.subheader("Período")
d_fim_padrao = date.today() - timedelta(days=2) 
d_ini_padrao = d_fim_padrao - timedelta(days=365*10)
data_inicio = st.sidebar.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY")

st.sidebar.subheader("Benchmarks no Gráfico")
mostrar_cdi = st.sidebar.checkbox("CDI (Renda Fixa)", value=True)
mostrar_ipca = st.sidebar.checkbox("IPCA (Inflação)", value=True)
mostrar_ibov = st.sidebar.checkbox("Ibovespa (Mercado)", value=True)

btn_analisar = st.sidebar.button("🔍 Analisar Patrimônio")

# 3. FUNÇÕES DE SUPORTE
def busca_indice_bcb(codigo, d_inicio, d_fim):
    s = d_inicio.strftime('%d/%m/%Y')
    e = d_fim.strftime('%d/%m/%Y')
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={s}&dataFinal={e}"
    try:
        r = requests.get(url, timeout=15).json()
        df = pd.DataFrame(r)
        df['data'] = pd.to_datetime(df['data'], dayfirst=True)
        df['valor'] = pd.to_numeric(df['valor']) / 100
        df = df.set_index('data')
        return (1 + df['valor']).cumprod()
    except: return pd.Series(dtype='float64')

@st.cache_data(show_spinner=False)
def carregar_dados_completos(t):
    if not t: return None
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        df = yf.download(t_sa, start="2005-01-01", progress=False, auto_adjust=False)
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
    with st.spinner("Sincronizando dados de mercado..."):
        s_cdi = busca_indice_bcb(12, data_inicio, data_fim) if mostrar_cdi else pd.Series()
        s_ipca = busca_indice_bcb(433, data_inicio, data_fim) if mostrar_ipca else pd.Series()
        df_acao = carregar_dados_completos(ticker_input)
        df_ibov_c = pd.Series()
        try:
            ibov_raw = yf.download("^BVSP", start=data_inicio, end=data_fim, progress=False)
            if not ibov_raw.empty:
                if isinstance(ibov_raw.columns, pd.MultiIndex): ibov_raw.columns = ibov_raw.columns.get_level_values(0)
                df_ibov_c = ibov_raw['Close']
        except: pass

    if df_acao is not None:
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            df_v["Total_Fact_Chart"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
            df_v["Price_Base_Chart"] = df_v["Close"] / df_v["Close"].iloc[0]
            
            fig = go.Figure()

            if not s_cdi.empty:
                fig.add_trace(go.Scatter(x=s_cdi.index, y=(s_cdi/s_cdi.iloc[0]-1)*100, name='CDI', line=dict(color='gray', width=2, dash='dash'), hovertemplate='%{y:.1f}%'))
            if not s_ipca.empty:
                fig.add_trace(go.Scatter(x=s_ipca.index, y=(s_ipca/s_ipca.iloc[0]-1)*100, name='IPCA', line=dict(color='red', width=2), hovertemplate='%{y:.1f}%'))
            if not df_ibov_c.empty:
                fig.add_trace(go.Scatter(x=df_ibov_c.index, y=(df_ibov_c/df_ibov_c.iloc[0]-1)*100, name='Ibovespa', line=dict(color='orange', width=2), hovertemplate='%{y:.1f}%'))

            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base_Chart"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0), hovertemplate='%{y:.1f}%'))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-df_v["Price_Base_Chart"])*100, stackgroup='one', name='Proventos (Div/JCP)', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0), hovertemplate='%{y:.1f}%'))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3), hovertemplate='%{y:.1f}%'))

            fig.update_layout(template="plotly_white", hovermode="x unified", yaxis=dict(side="right", ticksuffix="%", tickformat=".0f"), margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
            st.plotly_chart(fig, use_container_width=True)

            # 5. CARDS DE PATRIMÔNIO REESTRUTURADOS
            st.subheader(f"💰 Simulação de Patrimônio (Aportes Mensais: {formata_br(valor_aporte)})")
            
            def calcular_tudo(df_full, valor_mensal, anos, s_cdi_f, s_ipca_f, s_ibov_f):
                n_meses = anos * 12
                df_calc = df_full.tail(min(len(df_full), n_meses * 22))
                if len(df_calc) < 10: return [0]*6
                df_calc['month'] = df_calc.index.to_period('M')
                datas = df_calc.groupby('month').head(1).index[-n_meses:]
                
                cotas = sum(valor_mensal / df_full.loc[d, 'Close'] for d in datas)
                fator = df_full["Total_Fact"].iloc[-1] / df_full["Total_Fact"].loc[datas[0]]
                vf_at = cotas * df_full["Close"].iloc[-1] * (fator / (df_full["Close"].iloc[-1] / df_full["Close"].loc[datas[0]]))
                
                def c_idx(s):
                    return sum(valor_mensal * (s.iloc[-1] / s.loc[d]) for d in datas if d in s.index) if not s.empty else 0
                return vf_at, n_meses * valor_mensal, vf_at - (n_meses * valor_mensal), c_idx(s_cdi_f), c_idx(s_ipca_f), c_idx(s_ibov_f)

            col1, col2, col3 = st.columns(3)
            for anos, col in [(10, col1), (5, col2), (1, col3)]:
                vf, vi, lucro, v_cdi, v_ipca, v_ibov = calcular_tudo(df_acao, valor_aporte, anos, s_cdi, s_ipca, df_ibov_c)
                with col:
                    if vf > 0:
                        st.metric(f"Acúmulo em {anos} anos", formata_br(vf))
                        
                        st.markdown(f"""
                        <div class="info-card">
                            <div class="card-header">🏛️ Benchmarks Comparativos</div>
                            <div class="card-item">🎯 <b>CDI (100%):</b> {formata_br(v_cdi)}</div>
                            <div class="card-item">📈 <b>Ibovespa (Bolsa):</b> {formata_br(v_ibov)}</div>
                            <div class="card-item">🛡️ <b>Poder de Compra (IPCA):</b> {formata_br(v_ipca)}</div>
                            <hr style="margin: 10px 0; border: 0; border-top: 1px solid #ddd;">
                            <div class="card-header">Análise da Carteira</div>
                            <div class="card-item">💵 <b>Capital Investido:</b> {formata_br(vi)}</div>
                            <div class="card-destaque">💰 Lucro Acumulado: {formata_br(lucro)}</div>
                        </div>
                        """, unsafe_allow_html=True)

            # 6. GLOSSÁRIO DIDÁTICO
            st.markdown("""
            <div class="glossario">
            <div class="glossario-item">
                📌 <b>Poder de Compra (IPCA):</b> Pense neste valor como a sua "linha de empate". Ele mostra quanto dinheiro você precisaria ter hoje para comprar exatamente as mesmas coisas que comprava com os aportes feitos no passado. Se o patrimônio da sua ação é maior que este valor, você ficou "mais rico" de verdade; se for menor, você perdeu poder de compra para a inflação.
            </div>
            <div class="glossario-item">
                📌 <b>Proventos (Div/JCP):</b> É a parte do lucro que a empresa mandou para sua conta (Dividendos e Juros sobre Capital Próprio). O simulador assume que você usou cada centavo desse dinheiro para comprar mais ações da própria empresa.
            </div>
            <div class="glossario-item">
                📌 <b>CDI:</b> É o rendimento de referência da Renda Fixa. Serve para você avaliar se valeu a pena correr o risco da Bolsa de Valores ou se teria sido melhor deixar o dinheiro em uma aplicação conservadora.
            </div>
            </div>
            """, unsafe_allow_html=True)
            
    else: st.error("Ticker não encontrado.")
else: st.info("💡 Digite um Ticker para iniciar a análise.")
