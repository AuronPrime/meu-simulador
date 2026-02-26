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
    .resumo-objetivo { font-size: 0.9rem; color: #333; background-color: #e8f0fe; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 5px solid #1f77b4; line-height: 1.5; }
    .instrucoes { font-size: 0.85rem; color: #444; background-color: #f0f2f6; padding: 12px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #d1d9e6; }
    
    /* Cards de Resultados */
    .info-card {
        background-color: #f8fafc; 
        border: 1px solid #e2e8f0; 
        padding: 18px; 
        border-radius: 12px; 
        margin-top: 10px; 
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    .card-header { font-size: 0.75rem; font-weight: 800; color: #64748b; text-transform: uppercase; margin-bottom: 10px; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; }
    .card-item { font-size: 0.9rem; margin-bottom: 6px; color: #1e293b; }
    .card-destaque { font-size: 0.95rem; font-weight: 700; color: #0f172a; margin-top: 8px; border-top: 1px solid #e2e8f0; padding-top: 8px; }
    
    /* Estilização do Glossário (Fix) */
    .glossario-container {
        margin-top: 40px;
        padding: 30px;
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .glossario-titulo { font-size: 1.2rem; font-weight: 700; color: #1f77b4; margin-bottom: 20px; text-transform: uppercase; border-bottom: 2px solid #1f77b4; padding-bottom: 10px; }
    .glossario-item { margin-bottom: 20px; line-height: 1.6; border-bottom: 1px solid #f1f5f9; padding-bottom: 15px; }
    .glossario-item b { color: #1e293b; font-size: 0.95rem; }
    .glossario-item span { color: #475569; font-size: 0.9rem; display: block; margin-top: 4px; }

    .creditos { font-size: 0.85rem; color: #64748b; margin-top: 25px; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 15px; }
    .creditos a { color: #1f77b4; text-decoration: none; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def formata_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Título Principal com ícone mais sóbrio
st.title("📈 Simulador de Acúmulo de Patrimônio")

# 2. BARRA LATERAL
st.sidebar.markdown("""
<div class="resumo-objetivo">
👋 <b>Bem-vindo!</b><br>
O objetivo desta ferramenta é analisar o <b>Retorno Total</b> de um ativo, calculando o acúmulo real via <b>Proventos (Div/JCP)</b>. O algoritmo neutraliza distorções de mercado para uma simulação fiel.
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("""
<div class="instrucoes">
<b>Como usar:</b><br>
1. Digite o <b>Ticker</b> (ex: BBAS3).<br>
2. Defina o <b>valor mensal</b> do aporte.<br>
3. Escolha o <b>período</b> desejado.<br>
4. Clique em <b>Analisar</b>.
</div>
""", unsafe_allow_html=True)

ticker_input = st.sidebar.text_input("Digite o Ticker", "").upper().strip()
valor_aporte = st.sidebar.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

st.sidebar.subheader("Período da Simulação")
d_fim_padrao = date.today() - timedelta(days=2) 
d_ini_padrao = d_fim_padrao - timedelta(days=365*10)
data_inicio = st.sidebar.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY")

# BOTÃO ACIMA DOS CHECKBOXES CONFORME SOLICITADO
btn_analisar = st.sidebar.button("🔍 Analisar Patrimônio")

st.sidebar.subheader("Benchmarks no Gráfico")
mostrar_cdi = st.sidebar.checkbox("CDI (Renda Fixa)", value=True)
mostrar_ipca = st.sidebar.checkbox("IPCA (Inflação)", value=True)
mostrar_ibov = st.sidebar.checkbox("Ibovespa (Mercado)", value=True)

st.sidebar.markdown(f"""
<div class="creditos">
Desenvolvido por: <br>
<a href="https://www.instagram.com/ramoon.bastos?igsh=MTFiODlnZ28ybHFqdw%3D%3D&utm_source=qr" target="_blank">IG: Ramoon.Bastos</a>
</div>
""", unsafe_allow_html=True)

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

            # Título de Simulação com ícone sóbrio
            st.subheader("🏛️ Simulação de Patrimônio Acumulado")
            
            def calcular_tudo(df_full, valor_mensal, anos, s_cdi_f, s_ipca_f, s_ibov_f):
                data_limite = datetime.now() - timedelta(days=anos*365)
                df_p = df_full[df_full.index >= data_limite].copy()
                if len(df_p) < 10: return [0]*6
                df_p['month'] = df_p.index.to_period('M')
                datas = df_p.groupby('month').head(1).index
                
                cotas = sum(valor_mensal / df_full.loc[d, 'Close'] for d in datas)
                fator_tr = df_full["Total_Fact"].iloc[-1] / df_full["Total_Fact"].loc[datas[0]]
                vf_ativo = cotas * df_full["Close"].iloc[-1] * (fator_tr / (df_full["Close"].iloc[-1] / df_full["Close"].loc[datas[0]]))
                
                def calc_corrigido(serie):
                    if serie.empty: return 0
                    return sum(valor_mensal * (serie.iloc[-1] / serie.iloc[serie.index.get_indexer([d], method='backfill')[0]]) for d in datas)

                return vf_ativo, len(datas) * valor_mensal, vf_ativo - (len(datas) * valor_mensal), calc_corrigido(s_cdi_f), calc_corrigido(s_ipca_f), calc_corrigido(s_ibov_f)

            col1, col2, col3 = st.columns(3)
            for anos, col in [(10, col1), (5, col2), (1, col3)]:
                vf, vi, lucro, v_cdi, v_ipca, v_ibov = calcular_tudo(df_acao, valor_aporte, anos, s_cdi, s_ipca, df_ibov_c)
                with col:
                    if vf > 0:
                        st.metric(f"Total em {anos} anos", formata_br(vf))
                        st.markdown(f"""
                        <div class="info-card">
                            <div class="card-header">🏛️ Benchmarks (Valor Corrigido)</div>
                            <div class="card-item">🎯 <b>CDI:</b> {formata_br(v_cdi)}</div>
                            <div class="card-item">📈 <b>Ibovespa:</b> {formata_br(v_ibov)}</div>
                            <div class="card-item">🛡️ <b>Correção IPCA:</b> {formata_br(v_ipca)}</div>
                            <hr style="margin: 10px 0; border: 0; border-top: 1px solid #e2e8f0;">
                            <div class="card-header">Análise da Carteira</div>
                            <div class="card-item">💵 <b>Capital Nominal:</b> {formata_br(vi)}</div>
                            <div class="card-destaque">💰 Lucro Acumulado: {formata_br(lucro)}</div>
                        </div>
                        """, unsafe_allow_html=True)

            # GLOSSÁRIO REFORMULADO E FORMATADO
            st.markdown(f"""
            <div class="glossario-container">
                <div class="glossario-titulo">📖 Guia de Termos e Indicadores</div>
                
                <div class="glossario-item">
                    <b>• CDI (Certificado de Depósito Interbancário)</b>
                    <span>É a régua da renda fixa. Representa o retorno de aplicações seguras como o Tesouro Selic. Serve para você avaliar se o risco de investir em ações trouxe um retorno superior ao que você ganharia "sem risco".</span>
                </div>
                
                <div class="glossario-item">
                    <b>• Correção IPCA (Inflação)</b>
                    <span>Representa a atualização do seu dinheiro para o <b>valor presente</b>. Indica quanto você precisaria ter hoje para manter o mesmo poder de compra que tinha no passado. Se seu lucro é maior que esta correção, você ficou mais rico de verdade.</span>
                </div>
                
                <div class="glossario-item">
                    <b>• Ibovespa</b>
                    <span>É o termômetro do mercado brasileiro. Reflete a média de desempenho das maiores empresas da Bolsa. Comparar seu ativo com ele mostra se você está batendo a média do mercado.</span>
                </div>
                
                <div class="glossario-item">
                    <b>• Capital Nominal Investido</b>
                    <span>É o somatório bruto de todos os aportes mensais que você fez. É o dinheiro que efetivamente saiu da sua conta corrente ao longo do tempo.</span>
                </div>
                
                <div class="glossario-item">
                    <b>• Lucro Acumulado</b>
                    <span>É a diferença entre o seu patrimônio atual e o total investido nominalmente. É o quanto o seu capital cresceu através de juros, valorização e proventos.</span>
                </div>
                
                <div class="glossario-item">
                    <b>• Retorno Total</b>
                    <span>A métrica mais fiel ao investidor. No gráfico, ela une a valorização do preço da ação com o reinvestimento automático de todos os proventos recebidos.</span>
                </div>
                
                <div class="glossario-item">
                    <b>• Valorização</b>
                    <span>Refere-se apenas à subida (ou descida) do preço da cota no pregão da Bolsa, sem considerar o pagamento de proventos.</span>
                </div>
                
                <div class="glossario-item">
                    <b>• Proventos (Div/JCP)</b>
                    <span>É a parte do lucro da empresa que cai na sua conta. O simulador considera que esses valores foram usados para comprar mais ações, acelerando o crescimento do seu patrimônio.</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
    else: st.error("Ticker não encontrado.")
else: st.info("💡 Digite um Ticker no menu lateral para iniciar a análise.")
