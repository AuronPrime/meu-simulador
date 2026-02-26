import streamlit as st
import yfinance as yf
import pandas as pd 
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

# Estilos CSS - Restaurando a interface profissional das imagens
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

# 2. BARRA LATERAL (Restaurada)
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

# 3. FUNÇÕES DE DADOS COM BENCHMARKS NO GRÁFICO
@st.cache_data(show_spinner=False)
def busca_macro(d_ini, d_fim):
    def bcb(c):
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{c}/dados?formato=json&dataInicial={d_ini.strftime('%d/%m/%Y')}&dataFinal={d_fim.strftime('%d/%m/%Y')}"
        try:
            r = requests.get(url, timeout=10)
            df = pd.DataFrame(r.json())
            df['data'] = pd.to_datetime(df['data'], dayfirst=True)
            df['v'] = pd.to_numeric(df['valor']) / 100
            return df.set_index('data')
        except: return pd.DataFrame()
    return bcb(12), bcb(433)

@st.cache_data(show_spinner=False)
def carregar_ativos(t, d_ini, d_fim):
    t_sa = t if ".SA" in t else t + ".SA"
    df = yf.download([t_sa, "^BVSP"], start=d_ini - timedelta(days=60), end=d_fim + timedelta(days=2), progress=False)
    if df.empty or isinstance(df.columns, pd.RangeIndex): return None, None
    
    # Extração robusta para MultiIndex
    df_t = df.xs(t_sa, axis=1, level=1).copy().dropna()
    df_i = df.xs("^BVSP", axis=1, level=1).copy().dropna()
    
    df_t.index = df_t.index.tz_localize(None)
    df_i.index = df_i.index.tz_localize(None)
    
    # Fator de Retorno Total (com dividendos) vs Preço Seco
    df_t["TR_F"] = (1 + df_t["Adj Close"].pct_change().fillna(0)).cumprod()
    df_t["PR_F"] = (1 + df_t["Close"].pct_change().fillna(0)).cumprod()
    df_i["Norm"] = (1 + df_i["Close"].pct_change().fillna(0)).cumprod()
    
    return df_t, df_i

# 4. PROCESSAMENTO
if ticker_input:
    df_acao, df_ibov_raw = carregar_ativos(ticker_input, data_inicio, data_fim)
    df_cdi, df_ipca = busca_macro(data_inicio, data_fim)

    if df_acao is not None:
        # --- GRÁFICO ESTILIZADO (Restauração da imagem 5e6223.png) ---
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        # Normalização para o ponto zero do gráfico
        tr_base = df_v["TR_F"] / df_v["TR_F"].iloc[0]
        pr_base = df_v["PR_F"] / df_v["PR_F"].iloc[0]
        
        fig = go.Figure()
        
        # Benchmarks no gráfico (Linhas tracejadas)
        if mostrar_cdi and not df_cdi.empty:
            c_base = (1+df_cdi['v']).cumprod()
            fig.add_trace(go.Scatter(x=df_cdi.index, y=(c_base/c_base.iloc[0]-1)*100, name='CDI', line=dict(color='gray', dash='dash', width=1.5)))
        
        if mostrar_ipca and not df_ipca.empty:
            i_base = (1+df_ipca['v']).cumprod()
            fig.add_trace(go.Scatter(x=df_ipca.index, y=(i_base/i_base.iloc[0]-1)*100, name='IPCA', line=dict(color='red', width=1.5)))

        if mostrar_ibov and not df_ibov_raw.empty:
            ib_base = df_ibov_raw["Norm"] / df_ibov_raw["Norm"].asof(pd.to_datetime(data_inicio))
            fig.add_trace(go.Scatter(x=df_ibov_raw.index, y=(ib_base-1)*100, name='IBOVESPA', line=dict(color='orange', width=1.5)))

        # Camadas de Valorização e Proventos (Área preenchida)
        fig.add_trace(go.Scatter(x=df_v.index, y=(pr_base-1)*100, fill='tozeroy', name='Valorização', line=dict(color='rgba(31,119,180,0)'), fillcolor='rgba(31,119,180,0.3)'))
        fig.add_trace(go.Scatter(x=df_v.index, y=(tr_base-1)*100, fill='tonexty', name='Proventos', line=dict(color='rgba(218,165,32,0)'), fillcolor='rgba(218,165,32,0.3)'))
        
        # Linha principal do Retorno Total
        fig.add_trace(go.Scatter(x=df_v.index, y=(tr_base-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=2.5)))

        fig.update_layout(template="plotly_white", hovermode="x unified", height=450, margin=dict(l=0,r=0,t=20,b=0),
                          yaxis=dict(ticksuffix="%", gridcolor="#f0f0f0"), xaxis=dict(gridcolor="#f0f0f0"))
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Simulação de Patrimônio Acumulado")
        
        # --- CÁLCULO DINÂMICO (CORRIGIDO: Respeita o Calendário) ---
        def simular_pelo_fim(anos_atras):
            dt_alvo_fim = pd.to_datetime(data_fim)
            dt_alvo_ini = dt_alvo_fim - timedelta(days=anos_atras * 365)
            
            # Validação: se o calendário de "Início" for depois da data calculada, usamos o Início do calendário
            if dt_alvo_ini < pd.to_datetime(data_inicio): return None

            df_per = df_acao.loc[dt_alvo_ini:dt_alvo_fim].copy()
            if df_per.empty: return None
            
            # Datas de aportes (Primeiro dia útil de cada mês)
            datas_aportes = df_per.groupby(df_per.index.to_period('M')).head(1).index.tolist()
            
            total_vf = 0
            for d in datas_aportes:
                # O multiplicador é: (Fator no último dia do calendário / Fator no dia do aporte)
                fator_crescimento = df_acao["TR_F"].asof(dt_alvo_fim) / df_acao["TR_F"].asof(d)
                total_vf += valor_aporte * fator_crescimento
            
            vi = len(datas_aportes) * valor_aporte
            
            # Benchmarks de acumulação
            def acumula_bench(df_ref, col='v', is_rate=True):
                if df_ref.empty: return 0
                serie = (1+df_ref[col]).cumprod() if is_rate else df_ref[col]
                v_f = serie.asof(dt_alvo_fim)
                return sum(valor_aporte * (v_f / serie.asof(d)) for d in datas_aportes)

            return total_vf, vi, acumula_bench(df_cdi), acumula_bench(df_ipca), acumula_bench(df_ibov_raw, 'Norm', False)

        cols = st.columns(3)
        for i, anos in enumerate([10, 5, 1]):
            res = simular_pelo_fim(anos)
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
                    st.info(f"O filtro do calendário precisa cobrir ao menos {anos} ano(s).")

        # --- GUIA DE TERMOS COMPLETO (Restauração da imagem 5378de.jpg) ---
        st.markdown("""
        <div class="glossario-container">
            <h3 style="color: #1f77b4; margin-top:0;">📖 GUIA DE TERMOS E INDICADORES</h3>
            <div class="glossario-item">
                <b>• CDI (Certificado de Depósito Interbancário)</b>
                É a régua da renda fixa. Representa o retorno de aplicações seguras como o Tesouro Selic. Serve para você avaliar se o risco de investir em ações trouxe um prêmio real.
            </div>
            <div class="glossario-item">
                <b>• Correção IPCA (Inflação)</b>
                Representa a atualização do seu dinheiro para o <b>valor presente</b>. Indica quanto você precisaria ter hoje para manter o mesmo poder de compra que tinha no passado.
            </div>
            <div class="glossario-item">
                <b>• Ibovespa</b>
                É o termômetro do mercado brasileiro. Reflete a média de desempenho das maiores empresas da Bolsa. Comparar seu ativo com ele mostra se você está batendo o mercado.
            </div>
            <div class="glossario-item">
                <b>• Capital Nominal Investido</b>
                É o somatório bruto de todos os aportes mensais que você fez. É o dinheiro que efetivamente saiu da sua conta corrente ao longo do tempo.
            </div>
            <div class="glossario-item">
                <b>• Lucro Acumulado</b>
                É o ganho real acima do capital investido, somando a valorização das cotas e todos os dividendos recebidos no período.
            </div>
        </div>
        """, unsafe_allow_html=True)

    else: st.error("Ticker não encontrado ou dados indisponíveis para este período.")
