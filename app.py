import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

# Estilo para fontes e espaçamento
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    .instrucoes { font-size: 0.85rem; color: #555; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# Função para formatar moeda no padrão PT-BR (1.234,56)
def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("📊 Simulador de Acúmulo de Patrimônio")
st.markdown("Comparativo histórico considerando Reinvestimento de Dividendos, CDI e Inflação.")

# 2. BARRA LATERAL (ORIENTAÇÕES E INPUTS)
st.sidebar.header("Configurações")

# Texto de orientação curto
st.sidebar.markdown("""
<div class="instrucoes">
<b>Como usar:</b><br>
1. Digite o código da ação (Ticker).<br>
2. Defina o aporte mensal pretendido.<br>
3. O sistema calcula o acúmulo total e o ganho real acima da inflação.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker (ex: BBAS3, WEGE3)", "BBAS3").upper()
ticker = ticker_input if ".SA" in ticker_input else ticker_input + ".SA"
valor_aporte = st.sidebar.number_input("Valor do aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

# 3. FUNÇÕES DE DADOS
def get_bcb(codigo, d_ini, d_fim, fallback_diario):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={d_ini}&dataFinal={d_fim}"
    try:
        res = requests.get(url, timeout=10).json()
        df = pd.DataFrame(res)
        df['valor'] = pd.to_numeric(df['valor']) / 100
        df['data'] = pd.to_datetime(df['data'], dayfirst=True)
        return df.set_index('data')
    except:
        return pd.DataFrame({'valor': [fallback_diario]}, index=[pd.to_datetime(d_ini, dayfirst=True)])

@st.cache_data
def carregar_dados_completos(ticker):
    data = yf.Ticker(ticker).history(start="2010-01-01")
    if data.empty: return None
    data.index = data.index.tz_localize(None)
    
    # Performance
    data["Price_Pct"] = (data["Close"] / data["Close"].iloc[0]) - 1
    data["Total_Fact"] = (1 + data["Close"].pct_change().fillna(0) + (data["Dividends"]/data["Close"]).fillna(0)).cumprod()
    data["Total_Pct"] = data["Total_Fact"] - 1
    data["Div_Pct"] = data["Total_Pct"] - data["Price_Pct"]
    
    # Benchmarks
    s, e = data.index[0].strftime('%d/%m/%Y'), data.index[-1].strftime('%d/%m/%Y')
    df_ipca = get_bcb(433, s, e, 0.004)
    ipca_full = df_ipca.reindex(pd.date_range(data.index[0], data.index[-1]), method='ffill')
    data["IPCA_Fator"] = (1 + (ipca_full['valor']/21)).cumprod().reindex(data.index).ffill()
    data["IPCA_Acum"] = data["IPCA_Fator"] - 1
    
    df_cdi = get_bcb(12, s, e, 0.0004)
    cdi_full = df_cdi.reindex(pd.date_range(data.index[0], data.index[-1]), method='ffill')
    data["CDI_Acum"] = (1 + cdi_full['valor']).cumprod().reindex(data.index).ffill() - 1
    
    return data

# 4. GRÁFICO
try:
    df = carregar_dados_completos(ticker)
    if df is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df["Price_Pct"]*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.5)', line=dict(width=0)))
        fig.add_trace(go.Scatter(x=df.index, y=df["Div_Pct"]*100, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
        fig.add_trace(go.Scatter(x=df.index, y=df["IPCA_Acum"]*100, name='Inflação (IPCA)', line=dict(color='red', width=2)))
        fig.add_trace(go.Scatter(x=df.index, y=df["CDI_Acum"]*100, name='CDI', line=dict(color='gray', width=1.5, dash='dash')))
        fig.add_trace(go.Scatter(x=df.index, y=df["Total_Pct"]*100, name='RETORNO TOTAL', line=dict(color='black', width=2)))

        fig.update_layout(
            template="plotly_white", hovermode="x unified",
            yaxis=dict(side="right", ticksuffix="%"),
            margin=dict(l=20, r=20, t=50, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 5. CÁLCULO DE APORTES E LUCRO LÍQUIDO (ACIMA DO IPCA)
        st.subheader(f"💰 Resultado com Aportes Mensais de {formata_br(valor_aporte)}")
        
        def simular_real(df_orig, v_mes, anos):
            n_meses = anos * 12
            df_sim = df_orig.copy()
            df_sim['m'] = df_sim.index.to_period('M')
            datas_aporte = df_sim.groupby('m').head(1).index[-n_meses:]
            
            if len(datas_aporte) < n_meses: return 0, 0, 0
            
            recorte = df_orig[df_orig.index >= datas_aporte[0]].copy()
            
            # Valor Final (com dividendos reinvestidos)
            cotas = sum(v_mes / recorte.loc[d, 'Close'] for d in datas_aporte)
            f_total = (1 + recorte['Close'].pct_change().fillna(0) + (recorte['Dividends']/recorte['Close']).fillna(0)).cumprod().iloc[-1]
            f_preco = (recorte['Close'].iloc[-1] / recorte['Close'].iloc[0])
            valor_final = cotas * recorte['Close'].iloc[-1] * (f_total/f_preco)
            
            # Valor Investido Corrigido pelo IPCA (Custo de Oportunidade Real)
            investido_corrigido = sum(v_mes * (recorte['IPCA_Fator'].iloc[-1] / recorte.loc[d, 'IPCA_Fator']) for d in datas_aporte)
            investido_nominal = n_meses * v_mes
            
            return valor_final, investido_nominal, valor_final - investido_corrigido

        col1, col2, col3 = st.columns(3)
        for anos, coluna in [(10, col1), (5, col2), (1, col3)]:
            v_final, v_nom, lucro_real = simular_real(df, valor_aporte, anos)
            with coluna:
                if v_final > 0:
                    st.metric(label=f"Acúmulo em {anos} anos", value=formata_br(v_final))
                    st.write(f"**Investido:** {formata_br(v_nom)}")
                    st.caption(f"📉 **Lucro Líquido Real:** {formata_br(lucro_real)}")
                    st.caption("(Descontada a inflação do período)")
                else:
                    st.warning(f"Dados insuficientes para {anos} anos.")
except Exception as e:
    st.error(f"Erro: {e}")
