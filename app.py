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

@st.cache_data(show_spinner="Sincronizando Mercado...")
def carregar_dados_completos(t):
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        tk = yf.Ticker(t_sa)
        # Mantemos o history que você gosta
        df = tk.history(start="2005-01-01")[['Close', 'Dividends']]
        if df.empty: return None
        df.index = df.index.tz_localize(None)
        
        # --- FILTRO ANTI-ERRO DE DIVIDENDOS (AQUI ESTÁ A MÁGICA) ---
        # Calculamos o Yield diário. Se for > 15%, é erro de split do Yahoo.
        df['Daily_Yield'] = (df["Dividends"] / df["Close"]).fillna(0)
        
        # Se o yield for absurdo (ex: Copasa no split), zeramos aquele dividendo específico 
        # para não poluir o gráfico com retornos irreais.
        df.loc[df['Daily_Yield'] > 0.15, 'Dividends'] = 0 
        df['Daily_Yield'] = (df["Dividends"] / df["Close"]).fillna(0)
        # ----------------------------------------------------------
        
        df["Total_Fact"] = (1 + df["Close"].pct_change().fillna(0) + df['Daily_Yield']).cumprod()
        return df
    except: return None

# 4. LOGICA PRINCIPAL
if ticker_input:
    df_acao = carregar_dados_completos(ticker_input)
    
    if df_acao is not None:
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            df_v["Total_Fact_Chart"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
            df_v["Price_Base"] = df_v["Close"] / df_v["Close"].iloc[0]
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-df_v["Price_Base"])*100, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))

            if mostrar_cdi:
                s_cdi = busca_indice_bcb(12, data_inicio, data_fim)
                if not s_cdi.empty:
                    fig.add_trace(go.Scatter(x=s_cdi.index, y=(s_cdi/s_cdi.iloc[0]-1)*100, name='CDI', line=dict(color='gray', width=2, dash='dash')))

            if mostrar_ipca:
                s_ipca = busca_indice_bcb(433, data_inicio, data_fim)
                if not s_ipca.empty:
                    fig.add_trace(go.Scatter(x=s_ipca.index, y=(s_ipca/s_ipca.iloc[0]-1)*100, name='IPCA', line=dict(color='red', width=2)))

            if mostrar_ibov:
                try:
                    ibov = yf.download("^BVSP", start=data_inicio, end=data_fim, progress=False)
                    ibov_c = ibov['Close'].iloc[:, 0] if isinstance(ibov['Close'], pd.DataFrame) else ibov['Close']
                    if not ibov_c.empty:
                        ibov_c.index = ibov_c.index.tz_localize(None)
                        fig.add_trace(go.Scatter(x=ibov_c.index, y=(ibov_c/ibov_c.iloc[0]-1)*100, name='Ibovespa', line=dict(color='orange', width=2)))
                except: pass

            fig.update_layout(template="plotly_white", hovermode="x unified", yaxis=dict(side="right", ticksuffix="%"), margin=dict(l=20, r=20, t=50, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
            st.plotly_chart(fig, use_container_width=True)

            # 5. CARDS DE PATRIMÔNIO
            st.subheader(f"💰 Simulação de Aportes Mensais (R$ {valor_aporte:,.2f})")
            
            def calcular_patrimonio(df_full, valor_mensal, anos):
                n_meses = anos * 12
                df_calc = df_full.tail(n_meses * 22)
                if len(df_calc) < 20: return 0, 0
                df_calc['month'] = df_calc.index.to_period('M')
                datas_aporte = df_calc.groupby('month').head(1).index[-n_meses:]
                total_cotas = sum(valor_mensal / df_full.loc[d, 'Close'] for d in datas_aporte)
                fator_reinvestimento = df_full["Total_Fact"].iloc[-1] / df_full["Total_Fact"].loc[datas_aporte[0]]
                valor_final = total_cotas * df_full["Close"].iloc[-1] * (fator_reinvestimento / (df_full["Close"].iloc[-1] / df_full["Close"].loc[datas_aporte[0]]))
                return valor_final, n_meses * valor_mensal

            col1, col2, col3 = st.columns(3)
            for anos, col in [(10, col1), (5, col2), (1, col3)]:
                vf, vi = calcular_patrimonio(df_acao, valor_aporte, anos)
                with col:
                    if vf > 0:
                        st.metric(f"Acúmulo em {anos} anos", formata_br(vf))
                        st.write(f"Investido: {formata_br(vi)}")
                        st.caption(f"Lucro Bruto: {formata_br(vf-vi)}")

            # 6. GLOSSÁRIO DETALHADO
            st.markdown("""
            <div class="glossario">
            📌 <b>Entenda os indicadores de comparação:</b><br><br>
            • <b>CDI (Certificado de Depósito Interbancário):</b> É o principal termômetro da Renda Fixa no Brasil. Se a sua ação rende menos que o CDI, teria sido mais vantajoso (e seguro) deixar o dinheiro no Tesouro Selic.<br><br>
            • <b>IPCA (Índice de Preços ao Consumidor Amplo):</b> É a inflação oficial. O rendimento acima do IPCA é o seu "Lucro Real".<br><br>
            • <b>Ibovespa (Mercado):</b> A média das principais ações da B3. Serve para ver se você bateu a média do mercado.
            </div>
            """, unsafe_allow_html=True)
            
    else: st.error("Ticker não encontrado.")
else: st.info("💡 Digite um Ticker para começar.")
