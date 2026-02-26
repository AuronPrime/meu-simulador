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
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    .instrucoes { font-size: 0.85rem; color: #555; background-color: #f0f2f6; padding: 12px; border-radius: 5px; margin-bottom: 20px; border-left: 5px solid #ccc; }
    .glossario { font-size: 0.85rem; color: #444; margin-top: 40px; border-top: 2px solid #eee; padding-top: 20px; line-height: 1.8; background-color: #f9f9f9; padding: 20px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("📊 Simulador de Acúmulo de Patrimônio")

# 2. BARRA LATERAL
st.sidebar.header("Guia de Uso")
st.sidebar.markdown("""
<div class="instrucoes">
1) <b>Ativo:</b> Digite o ticker (ex: PETR4).<br>
2) <b>Aporte:</b> Defina o valor mensal.<br>
3) <b>Período:</b> O padrão inicia em 10 anos.<br>
4) <b>Filtros:</b> Compare com índices abaixo.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker (ex: BBAS3, ITUB4)", "").upper().strip()
valor_aporte = st.sidebar.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

st.sidebar.subheader("Período do Gráfico")
d_fim_padrao = date.today() - timedelta(days=2) 
d_ini_padrao = d_fim_padrao - timedelta(days=365*10)
data_inicio = st.sidebar.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY")

st.sidebar.subheader("Comparativos")
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
    except:
        return pd.Series(dtype='float64')

@st.cache_data(show_spinner=False)
def carregar_dados_completos(t):
    if not t: return None
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        df = yf.download(t_sa, start="2005-01-01", progress=False, auto_adjust=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize(None)

        df["Ret_Total"] = df["Adj Close"].pct_change().fillna(0)
        df["Ret_Preco"] = df["Close"].pct_change().fillna(0)
        df["Yield_Fiscalizado"] = (df["Ret_Total"] - df["Ret_Preco"]).apply(lambda x: x if x > 0 else 0)
        df["Total_Fact"] = (1 + df["Ret_Preco"] + df["Yield_Fiscalizado"]).cumprod()
        
        return df[['Close', 'Adj Close', 'Total_Fact']]
    except: return None

# 4. LOGICA PRINCIPAL (CARREGAMENTO RÁPIDO)
if ticker_input:
    # Um único spinner para todo o processo de dados
    with st.spinner(f"Sincronizando {ticker_input} e indicadores..."):
        df_acao = carregar_dados_completos(ticker_input)
        
        # Pré-carregamento dos comparativos para evitar "pulos" na tela
        s_cdi = busca_indice_bcb(12, data_inicio, data_fim) if mostrar_cdi else pd.Series()
        s_ipca = busca_indice_bcb(433, data_inicio, data_fim) if mostrar_ipca else pd.Series()
        df_ibov = pd.Series()
        if mostrar_ibov:
            try:
                ibov_raw = yf.download("^BVSP", start=data_inicio, end=data_fim, progress=False)
                if not ibov_raw.empty:
                    if isinstance(ibov_raw.columns, pd.MultiIndex): ibov_raw.columns = ibov_raw.columns.get_level_values(0)
                    df_ibov = ibov_raw['Close']
            except: pass

    # Se chegamos aqui, os dados já estão no PC. Agora desenhamos tudo de uma vez.
    if df_acao is not None:
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            df_v["Total_Fact_Chart"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
            df_v["Price_Base_Chart"] = df_v["Close"] / df_v["Close"].iloc[0]
            
            fig = go.Figure()

            # Desenho das linhas de referência (CDI, IPCA, IBOV)
            if mostrar_cdi and not s_cdi.empty:
                fig.add_trace(go.Scatter(x=s_cdi.index, y=(s_cdi/s_cdi.iloc[0]-1)*100, name='CDI', line=dict(color='gray', width=2, dash='dash')))

            if mostrar_ipca and not s_ipca.empty:
                fig.add_trace(go.Scatter(x=s_ipca.index, y=(s_ipca/s_ipca.iloc[0]-1)*100, name='IPCA', line=dict(color='red', width=2)))

            if mostrar_ibov and not df_ibov.empty:
                fig.add_trace(go.Scatter(x=df_ibov.index, y=(df_ibov/df_ibov.iloc[0]-1)*100, name='Ibovespa', line=dict(color='orange', width=2)))

            # Desenho da Ação (Áreas e Linha Principal)
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base_Chart"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-df_v["Price_Base_Chart"])*100, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))

            fig.update_layout(template="plotly_white", hovermode="x unified", yaxis=dict(side="right", ticksuffix="%"), margin=dict(l=20, r=20, t=50, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
            
            # Renderização final
            st.plotly_chart(fig, use_container_width=True)

            # 5. CARDS DE PATRIMÔNIO
            st.subheader(f"💰 Simulação de Aportes Mensais (R$ {valor_aporte:,.2f})")
            
            def calcular_patrimonio(df_full, valor_mensal, anos):
                n_meses = anos * 12
                df_calc = df_full.tail(n_meses * 22)
                if len(df_calc) < 20: return 0, 0, 0
                df_calc['month'] = df_calc.index.to_period('M')
                datas_aporte = df_calc.groupby('month').head(1).index[-n_meses:]
                total_cotas = sum(valor_mensal / df_full.loc[d, 'Close'] for d in datas_aporte)
                fator_reinvestimento = df_full["Total_Fact"].iloc[-1] / df_full["Total_Fact"].loc[datas_aporte[0]]
                valor_final = total_cotas * df_full["Close"].iloc[-1] * (fator_reinvestimento / (df_full["Close"].iloc[-1] / df_full["Close"].loc[datas_aporte[0]]))
                investido = n_meses * valor_mensal
                return valor_final, investido, valor_final - investido

            col1, col2, col3 = st.columns(3)
            for anos, col in [(10, col1), (5, col2), (1, col3)]:
                vf, vi, lucro = calcular_patrimonio(df_acao, valor_aporte, anos)
                with col:
                    if vf > 0:
                        st.metric(f"Acúmulo em {anos} anos", formata_br(vf))
                        st.write(f"Total Investido: {formata_br(vi)}")
                        st.caption(f"Lucro Acumulado: {formata_br(lucro)}")

            # 6. GLOSSÁRIO
            st.markdown("""
            <div class="glossario">
            📌 <b>Entenda os indicadores de comparação:</b><br><br>
            • <b>CDI (Certificado de Depósito Interbancário):</b> Referência de Renda Fixa.<br><br>
            • <b>IPCA (Índice de Preços ao Consumidor Amplo):</b> Inflação oficial.<br><br>
            • <b>Ibovespa (Mercado):</b> Média das ações mais negociadas.
            </div>
            """, unsafe_allow_html=True)
            
    else: st.error("Erro: Ticker não encontrado ou falha na conexão.")
else: st.info("💡 Digite um Ticker para começar.")
