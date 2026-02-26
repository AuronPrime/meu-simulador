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
3) <b>Período:</b> Escolha o intervalo desejado.<br>
4) <b>Filtros:</b> Compare com índices reais.
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

# 3. FUNÇÕES DE SUPORTE (BCB)
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

# 4. CARREGAMENTO COM CORREÇÃO DE DIVIDENDOS (PRECISÃO TOTAL)
@st.cache_data(show_spinner="Calculando Retorno Real...")
def carregar_dados_acao(t):
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        # Baixamos o histórico SEM ajuste para ter o preço de tela (Price_Base)
        # E o Adj Close para ter o Retorno Total (Total_Fact)
        df = yf.download(t_sa, start="2005-01-01", progress=False)
        if df.empty: return None
        
        # Ajuste para lidar com MultiIndex do yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df_final = pd.DataFrame({
                'Close': df['Close'][t_sa],
                'Adj Close': df['Adj Close'][t_sa]
            })
        else:
            df_final = df[['Close', 'Adj Close']].copy()
            
        df_final.index = df_final.index.tz_localize(None)
        
        # A MÁGICA DA CORREÇÃO:
        # Total_Fact usa o preço ajustado (dividendos reinvestidos + splits)
        df_final["Total_Fact"] = df_final["Adj Close"] / df_final["Adj Close"].iloc[0]
        
        # Price_Base usa o preço de tela (apenas valorização nominal)
        # Importante: O Yahoo ajusta o 'Close' retroativamente para Splits, 
        # o que é correto para não ter buracos no gráfico.
        df_final["Price_Base"] = df_final["Close"] / df_final["Close"].iloc[0]
        
        return df_final
    except: return None

# 5. LÓGICA PRINCIPAL
if ticker_input:
    df_acao = carregar_dados_acao(ticker_input)
    
    if df_acao is not None:
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            # Rebase para o início do período selecionado
            df_v["Total_Fact_Chart"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
            df_v["Price_Base_Chart"] = df_v["Price_Base"] / df_v["Price_Base"].iloc[0]
            
            fig = go.Figure()
            
            # Valorização (Área Azul)
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base_Chart"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
            
            # Dividendos (Área Amarela - Agora calculada como a diferença real do Adj Close)
            diff_div = (df_v["Total_Fact_Chart"] - df_v["Price_Base_Chart"]) * 100
            fig.add_trace(go.Scatter(x=df_v.index, y=diff_div, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
            
            # Linha de Retorno Total
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))

            # Índices de Comparação
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

            # 6. CARDS DE PATRIMÔNIO
            st.subheader(f"💰 Simulação de Aportes Mensais (R$ {valor_aporte:,.2f})")
            
            def calcular_patrimonio(df_full, valor_mensal, anos):
                n_meses = anos * 12
                df_calc = df_full.tail(n_meses * 22)
                if len(df_calc) < 20: return 0, 0
                df_calc['month'] = df_calc.index.to_period('M')
                datas_aporte = df_calc.groupby('month').head(1).index[-n_meses:]
                
                # Cálculo via Preço Ajustado (Simula reinvestimento automático de dividendos)
                total_cotas_ajustadas = sum(valor_mensal / df_full.loc[d, 'Adj Close'] for d in datas_aporte)
                valor_final = total_cotas_ajustadas * df_full["Adj Close"].iloc[-1]
                return valor_final, n_meses * valor_mensal

            col1, col2, col3 = st.columns(3)
            for anos, col in [(10, col1), (5, col2), (1, col3)]:
                vf, vi = calcular_patrimonio(df_acao, valor_aporte, anos)
                with col:
                    if vf > 0:
                        st.metric(f"Acúmulo em {anos} anos", formata_br(vf))
                        st.write(f"Investido: {formata_br(vi)}")
                        st.caption(f"Lucro Bruto: {formata_br(vf-vi)}")

            # 7. GLOSSÁRIO DETALHADO
            st.markdown("""
            <div class="glossario">
            📌 <b>Entenda os indicadores de comparação:</b><br><br>
            • <b>CDI (Certificado de Depósito Interbancário):</b> Referência da Renda Fixa. Se sua ação rende menos que o CDI, o risco da renda variável não compensou.<br><br>
            • <b>IPCA (Inflação):</b> Mostra se seu dinheiro ganhou poder de compra real.<br><br>
            • <b>Ibovespa (Mercado):</b> A média das principais ações da bolsa. Útil para saber se sua escolha foi melhor que a "média" do mercado.
            </div>
            """, unsafe_allow_html=True)
            
    else: st.error("Ticker não encontrado.")
else: st.info("💡 Digite um Ticker para começar.")
