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
    .glossario { font-size: 0.8rem; color: #777; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px; line-height: 1.6; }
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
mostrar_ibov = st.sidebar.checkbox("Ibovespa (Mercado)", value=False)

btn_analisar = st.sidebar.button("🔍 Analisar Patrimônio")

# 3. FUNÇÕES DE SUPORTE
def get_bcb(codigo, d_ini, d_f):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={d_ini}&dataFinal={d_f}"
    try:
        res = requests.get(url, timeout=15).json()
        df_res = pd.DataFrame(res)
        df_res['valor'] = pd.to_numeric(df_res['valor']) / 100
        df_res['data'] = pd.to_datetime(df_res['data'], dayfirst=True)
        return df_res.set_index('data')
    except:
        return pd.DataFrame()

@st.cache_data(show_spinner="Buscando dados financeiros...")
def carregar_tudo(t, d_ini, d_fim):
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        ticker_obj = yf.Ticker(t_sa)
        df_hist = ticker_obj.history(start="2005-01-01")
        if df_hist.empty: return None
        df = df_hist[['Close']].copy()
        df['Dividends'] = df_hist['Dividends'] if 'Dividends' in df_hist else 0
        df.index = df.index.tz_localize(None)
        
        # Fator de Retorno da Ação
        df["Total_Fact"] = (1 + df["Close"].pct_change().fillna(0) + (df["Dividends"]/df["Close"]).fillna(0)).cumprod()
        
        # Ibovespa
        try:
            ibov = yf.download("^BVSP", start="2005-01-01", progress=False)
            if not ibov.empty:
                ibov_c = ibov['Close'].copy()
                ibov_c.index = ibov_c.index.tz_localize(None)
                df["IBOV_Fact"] = (ibov_c / ibov_c.iloc[0]).reindex(df.index).ffill()
        except: pass
            
        s, e = df.index[0].strftime('%d/%m/%Y'), df.index[-1].strftime('%d/%m/%Y')
        
        # IPCA (Mensal)
        df_ipca_raw = get_bcb(433, s, e)
        if not df_ipca_raw.empty:
            ipca_f = df_ipca_raw.reindex(pd.date_range(df.index[0], df_ipca_raw.index.max()), method='ffill')
            df["IPCA_Fact"] = (1 + (ipca_f['valor']/21)).cumprod().reindex(df.index)
        
        # CDI (Diário - Correção aqui)
        df_cdi_raw = get_bcb(12, s, e)
        if not df_cdi_raw.empty:
            # Reindexamos para todos os dias e usamos ffill para cobrir fins de semana
            cdi_f = df_cdi_raw.reindex(pd.date_range(df.index[0], df_cdi_raw.index.max()), method='ffill')
            df["CDI_Fact"] = (1 + cdi_f['valor']).cumprod().reindex(df.index).ffill()
        
        return df
    except: return None

# 4. LÓGICA DE EXIBIÇÃO
if not ticker_input:
    st.info("💡 Digite um **Ticker** na barra lateral para começar.")
elif btn_analisar or ticker_input:
    df_completo = carregar_tudo(ticker_input, data_inicio, data_fim)
    if df_completo is not None:
        df_v = df_completo.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            # Rebase
            colunas_fator = ["Total_Fact", "IPCA_Fact", "CDI_Fact", "IBOV_Fact"]
            for col in colunas_fator:
                if col in df_v.columns:
                    valid = df_v[col].dropna()
                    if not valid.empty:
                        df_v[col] = df_v[col] / valid.iloc[0]
            
            df_v["Price_Base"] = df_v["Close"] / df_v["Close"].iloc[0]
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact"]-df_v["Price_Base"])*100, stackgroup='one', name='Dividendos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
            
            if mostrar_ipca and "IPCA_Fact" in df_v.columns:
                p = df_v["IPCA_Fact"].dropna()
                fig.add_trace(go.Scatter(x=p.index, y=(p-1)*100, name='IPCA (Inflação)', line=dict(color='red', width=2)))
            
            if mostrar_cdi and "CDI_Fact" in df_v.columns:
                p = df_v["CDI_Fact"].dropna()
                fig.add_trace(go.Scatter(x=p.index, y=(p-1)*100, name='CDI (Renda Fixa)', line=dict(color='gray', width=1.5, dash='dash')))
            
            if mostrar_ibov and "IBOV_Fact" in df_v.columns:
                fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["IBOV_Fact"]-1)*100, name='Ibovespa (Mercado)', line=dict(color='orange', width=2)))
            
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=2.5)))
            fig.update_layout(template="plotly_white", hovermode="x unified", yaxis=dict(side="right", ticksuffix="%"), margin=dict(l=20, r=20, t=50, b=20), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
            st.plotly_chart(fig, use_container_width=True)

            # 5. CARDS DE RESULTADO
            st.subheader(f"💰 Patrimônio com Aportes Mensais de {formata_br(valor_aporte)}")
            def simular_historico(df_orig, v_mes, anos):
                n_meses = anos * 12
                df_rec = df_orig.tail(n_meses * 21)
                df_rec['m'] = df_rec.index.to_period('M')
                datas_aporte = df_rec.groupby('m').head(1).index[-n_meses:]
                if len(datas_aporte) < n_meses: return 0, 0, 0
                recorte = df_orig[df_orig.index >= datas_aporte[0]].copy()
                cotas = sum(v_mes / recorte.loc[d, 'Close'] for d in datas_aporte)
                f_total = recorte["Total_Fact"].iloc[-1] / recorte["Total_Fact"].iloc[0]
                v_final = cotas * recorte["Close"].iloc[-1] * (f_total/(recorte["Close"].iloc[-1] / recorte["Close"].iloc[0]))
                v_investido = n_meses * v_mes
                ipca_card = recorte["IPCA_Fact"].ffill()
                f_ipca_card = ipca_card / ipca_card.iloc[0]
                l_real = v_final - sum(v_mes * (f_ipca_card.iloc[-1] / f_ipca_card.loc[d]) for d in datas_aporte)
                return v_final, v_investido, l_real

            col1, col2, col3 = st.columns(3)
            for anos, coluna in [(10, col1), (5, col2), (1, col3)]:
                vf, vi, lr = simular_historico(df_completo, valor_aporte, anos)
                with coluna:
                    if vf > 0:
                        st.metric(f"Acúmulo em {anos} anos", formata_br(vf))
                        st.write(f"Investido: {formata_br(vi)}")
                        st.caption(f"📈 Lucro Real: {formata_br(lr)}")

            st.markdown("""
            <div class="glossario">
            📌 <b>Entenda os indicadores:</b><br>
            • <b>CDI (Certificado de Depósito Interbancário):</b> Representa o rendimento médio da Renda Fixa pós-fixada. É a referência mínima para um investidor conservador.<br>
            • <b>IPCA (Índice de Preços ao Consumidor Amplo):</b> É a medida oficial da inflação no Brasil. Quando seu lucro real é positivo, significa que seu dinheiro ganhou poder de compra.<br>
            • <b>Ibovespa (Mercado):</b> O principal índice da B3, composto pelas empresas mais negociadas. Serve para avaliar se sua escolha de ação superou a média do mercado brasileiro.
            </div>
            """, unsafe_allow_html=True)
        else: st.error("Sem dados para o período.")
    else: st.error(f"Ticker '{ticker_input}' não encontrado.")
