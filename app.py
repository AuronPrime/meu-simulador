import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

# Estilos CSS - Mantidos
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #1f77b4; }
    .resumo-objetivo { font-size: 0.9rem; color: #333; background-color: #e8f0fe; padding: 15px; border-radius: 8px; margin-bottom: 15px; border-left: 5px solid #1f77b4; line-height: 1.6; }
    
    /* Card de Destaque - discreto */
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

    /* Cards de Detalhes */
    .info-card { background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 18px; border-radius: 12px; margin-top: 5px; }
    .card-header { font-size: 0.75rem; font-weight: 800; color: #64748b; text-transform: uppercase; margin-bottom: 10px; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; }
    .card-item { font-size: 0.9rem; margin-bottom: 6px; color: #1e293b; }
    .card-destaque { font-size: 0.95rem; font-weight: 700; color: #0f172a; margin-top: 8px; border-top: 1px solid #e2e8f0; padding-top: 8px; }
    
    .glossario-container { margin-top: 40px; padding: 25px; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; }
    .glossario-termo { font-weight: 800; color: #1f77b4; font-size: 1rem; display: block; }
    .glossario-def { color: #475569; font-size: 0.9rem; line-height: 1.5; display: block; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

def formata_br(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("Simulador de Acúmulo de Patrimônio")

# 2. BARRA LATERAL (texto mantido)
st.sidebar.markdown("""
<div class="resumo-objetivo">
👋 <b>Bem-vindo!</b><br>
O simulador calcula o acúmulo real de patrimônio via <b>Retorno Total</b>, reinvestindo automaticamente proventos (Div/JCP).
Para garantir precisão técnica, utilizamos um índice de <b>Retorno Total</b> construído com base em <b>Dividendos</b> e <b>Splits/Grupamentos</b>,
neutralizando distorções causadas por eventos corporativos ao longo do tempo.
</div>
""", unsafe_allow_html=True)

# Defaults de datas
d_fim_padrao = date.today() - timedelta(days=2)
d_ini_padrao = d_fim_padrao - timedelta(days=365*10)

# ✅ FORM: só executa quando clicar em Analisar
with st.sidebar.form("form_simulador"):
    ticker_input = st.text_input("Digite o Ticker", "").upper().strip()
    valor_aporte = st.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

    st.subheader("Período da Simulação")
    data_inicio = st.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
    data_fim = st.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY")

    st.subheader("Benchmarks no Gráfico")
    mostrar_cdi = st.checkbox("CDI (Renda Fixa)", value=True)
    mostrar_ipca = st.checkbox("IPCA (Inflação)", value=True)
    mostrar_ibov = st.checkbox("Ibovespa (Mercado)", value=True)

    btn_analisar = st.form_submit_button("🔍 Analisar Patrimônio")

st.sidebar.markdown(f"""
<div style="font-size: 0.85rem; color: #64748b; margin-top: 25px; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 15px;">
Desenvolvido por: <br>
<a href="https://www.instagram.com/ramoon.bastos?igsh=MTFiODlnZ28ybHFqdw%3D%3D&utm_source=qr" target="_blank" style="color: #1f77b4; text-decoration: none; font-weight: bold;">IG: Ramoon.Bastos</a>
</div>
""", unsafe_allow_html=True)

# Se não clicou, não roda nada
if not btn_analisar:
    st.info("💡 Preencha os campos no menu lateral e clique em **Analisar Patrimônio**.")
    st.stop()

# Validações simples
if not ticker_input:
    st.error("Digite um ticker válido no menu lateral.")
    st.stop()

if data_inicio >= data_fim:
    st.error("A data de **Início** deve ser anterior à data de **Fim**.")
    st.stop()

# 3. FUNÇÕES DE SUPORTE

# ✅ Cache BCB com TTL (6h) + retry
@st.cache_data(ttl=60*60*6, show_spinner=False)
def busca_indice_bcb(codigo: int, d_inicio: date, d_fim: date) -> pd.Series:
    s, e = d_inicio.strftime('%d/%m/%Y'), d_fim.strftime('%d/%m/%Y')
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={s}&dataFinal={e}"

    for i in range(5):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                df = pd.DataFrame(r.json())
                if df.empty:
                    return pd.Series(dtype="float64")

                df['data'] = pd.to_datetime(df['data'], dayfirst=True)
                df['valor'] = pd.to_numeric(df['valor'], errors="coerce") / 100.0
                df = df.dropna(subset=["valor"]).set_index('data').sort_index()

                # índice acumulado (nível), base = 1 no primeiro ponto
                serie = (1.0 + df['valor']).cumprod()
                return serie
        except Exception:
            time.sleep(i + 1)

    return pd.Series(dtype="float64")

# ✅ Cache mercado com TTL (30min)
@st.cache_data(ttl=60*30, show_spinner=False)
def carregar_dados_completos(t: str) -> pd.DataFrame | None:
    """
    Retorna um DataFrame com:
      - Close (preço)
      - Dividends (proventos: dividendos/JCP conforme Yahoo)
      - Stock Splits (splits/grupamentos/bonificações quando representadas como split)
      - Price_Fact (índice de preço ajustado por splits)
      - Total_Fact (índice de retorno total: preço + proventos reinvestidos + splits)
    """
    if not t:
        return None

    t_sa = t if ".SA" in t else t + ".SA"

    try:
        tk = yf.Ticker(t_sa)
        df = tk.history(start="2005-01-01", auto_adjust=False, actions=True, interval="1d")

        if df is None or df.empty:
            return None

        # normaliza colunas (segurança)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # remove fuso se houver
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)

        # garante colunas
        for col in ["Close", "Dividends", "Stock Splits"]:
            if col not in df.columns:
                df[col] = 0.0

        df = df[["Close", "Dividends", "Stock Splits"]].copy()
        df = df.dropna(subset=["Close"]).sort_index()
        df["Dividends"] = df["Dividends"].fillna(0.0)
        df["Stock Splits"] = df["Stock Splits"].fillna(0.0)

        # split ratio do dia (0 -> 1)
        split_ratio = df["Stock Splits"].replace(0.0, 1.0)

        # ✅ Índice de PREÇO ajustado por splits/grupamentos
        # fator diário: (Close_t * split_ratio_t) / Close_{t-1}
        price_factor = (df["Close"] * split_ratio) / df["Close"].shift(1)

        # ✅ Índice de RETORNO TOTAL (preço + dividendos reinvestidos) + splits
        # fator diário: ((Close_t + Div_t) * split_ratio_t) / Close_{t-1}
        total_factor = ((df["Close"] + df["Dividends"]) * split_ratio) / df["Close"].shift(1)

        df["Price_Fact"] = price_factor.fillna(1.0).cumprod()
        df["Total_Fact"] = total_factor.fillna(1.0).cumprod()

        return df

    except Exception:
        return None

@st.cache_data(ttl=60*30, show_spinner=False)
def carregar_ibov(d_inicio: date, d_fim: date) -> pd.Series:
    """
    Retorna série de fechamento do IBOV.
    """
    try:
        # end no yfinance costuma ser exclusivo, então adicionamos 1 dia
        df = yf.download("^BVSP", start=d_inicio, end=d_fim + timedelta(days=1), progress=False, auto_adjust=False)
        if df is None or df.empty:
            return pd.Series(dtype="float64")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        s = df["Close"].dropna().copy()
        # remove tz se vier
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
        return s.sort_index()
    except Exception:
        return pd.Series(dtype="float64")

# 4. LÓGICA PRINCIPAL
with st.spinner("Sincronizando dados de mercado..."):
    s_cdi = busca_indice_bcb(12, data_inicio, data_fim) if mostrar_cdi else pd.Series(dtype="float64")
    s_ipca = busca_indice_bcb(433, data_inicio, data_fim) if mostrar_ipca else pd.Series(dtype="float64")

    df_acao = carregar_dados_completos(ticker_input)

    df_ibov_c = carregar_ibov(data_inicio, data_fim) if mostrar_ibov else pd.Series(dtype="float64")

if df_acao is None:
    st.error("Ticker não encontrado ou sem dados suficientes (Yahoo Finance).")
    st.stop()

# recorte do período para gráfico
dt_ini = pd.to_datetime(data_inicio)
dt_fim = pd.to_datetime(data_fim)

df_v = df_acao.loc[(df_acao.index >= dt_ini) & (df_acao.index <= dt_fim)].copy()

if df_v.empty or len(df_v) < 5:
    st.error("Período selecionado sem dados suficientes para o ativo.")
    st.stop()

# ✅ normalizações para o gráfico
df_v["Total_Fact_Chart"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
df_v["Price_Fact_Chart"] = df_v["Price_Fact"] / df_v["Price_Fact"].iloc[0]

# --------- GRÁFICO ----------
fig = go.Figure()

if not s_cdi.empty:
    fig.add_trace(go.Scatter(
        x=s_cdi.index,
        y=(s_cdi / s_cdi.iloc[0] - 1) * 100,
        name="CDI",
        line=dict(color="gray", width=2, dash="dash")
    ))

if not s_ipca.empty:
    fig.add_trace(go.Scatter(
        x=s_ipca.index,
        y=(s_ipca / s_ipca.iloc[0] - 1) * 100,
        name="IPCA",
        line=dict(color="red", width=2)
    ))

if not df_ibov_c.empty:
    fig.add_trace(go.Scatter(
        x=df_ibov_c.index,
        y=(df_ibov_c / df_ibov_c.iloc[0] - 1) * 100,
        name="Ibovespa",
        line=dict(color="orange", width=2)
    ))

# ✅ decomposição correta (split-safe + dividend-safe)
fig.add_trace(go.Scatter(
    x=df_v.index,
    y=(df_v["Price_Fact_Chart"] - 1) * 100,
    stackgroup="one",
    name="Valorização",
    fillcolor="rgba(31, 119, 180, 0.4)",
    line=dict(width=0)
))
fig.add_trace(go.Scatter(
    x=df_v.index,
    y=(df_v["Total_Fact_Chart"] - df_v["Price_Fact_Chart"]) * 100,
    stackgroup="one",
    name="Proventos (reinvestidos)",
    fillcolor="rgba(218, 165, 32, 0.4)",
    line=dict(width=0)
))
fig.add_trace(go.Scatter(
    x=df_v.index,
    y=(df_v["Total_Fact_Chart"] - 1) * 100,
    name="RETORNO TOTAL",
    line=dict(color="black", width=3)
))

fig.update_layout(
    template="plotly_white",
    hovermode="x unified",
    yaxis=dict(side="right", ticksuffix="%", tickformat=".0f"),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
)

st.plotly_chart(fig, use_container_width=True)

st.subheader("Simulação de Patrimônio Acumulado")

# ✅ Cálculo aporte-a-aporte, ancorado em data_fim, sem look-ahead
def calcular_tudo(
    df_full: pd.DataFrame,
    valor_mensal: float,
    anos: int,
    s_cdi_f: pd.Series,
    s_ipca_f: pd.Series,
    s_ibov_f: pd.Series,
    data_inicio_user: date,
    data_fim_user: date
):
    if df_full is None or df_full.empty or valor_mensal <= 0:
        return 0.0, 0.0, 0.0, None, None, None

    dt_ini_user = pd.to_datetime(data_inicio_user)
    dt_fim_user = pd.to_datetime(data_fim_user)

    # ancora no último pregão <= data_fim
    data_ref = df_full.index[df_full.index <= dt_fim_user].max()
    if pd.isna(data_ref):
        return 0.0, 0.0, 0.0, None, None, None

    # janela do horizonte
    inicio_horizonte = data_ref - pd.DateOffset(years=anos)
    inicio = max(dt_ini_user, inicio_horizonte)

    df_p = df_full.loc[(df_full.index >= inicio) & (df_full.index <= data_ref)].copy()
    if df_p.empty or len(df_p) < 5:
        return 0.0, 0.0, 0.0, None, None, None

    # 1º pregão de cada mês na janela (aportes mensais)
    datas = df_p.groupby(df_p.index.to_period("M")).head(1).index
    if len(datas) == 0:
        return 0.0, 0.0, 0.0, None, None, None

    investido = float(len(datas) * valor_mensal)

    # ✅ patrimônio final do ativo: soma aporte*(TR_end/TR_date)
    tr_end = float(df_full.loc[data_ref, "Total_Fact"])
    tr_at = df_full.loc[datas, "Total_Fact"].astype(float)
    vf_ativo = float((valor_mensal * (tr_end / tr_at)).sum())
    lucro = vf_ativo - investido

    # ✅ benchmark sem look-ahead: usa somente último valor conhecido até a data (ffill/asof)
    def calc_corrigido(serie: pd.Series) -> float | None:
        if serie is None or serie.empty:
            return None

        serie = pd.Series(serie).dropna().sort_index()

        end = serie.asof(data_ref)  # último ponto conhecido até data_ref
        if pd.isna(end):
            return None

        at = serie.reindex(datas, method="ffill")  # último ponto conhecido até cada aporte
        at = at.fillna(serie.iloc[0])             # protege aportes anteriores ao início da série

        return float((valor_mensal * (end / at)).sum())

    v_cdi = calc_corrigido(s_cdi_f) if (s_cdi_f is not None and not s_cdi_f.empty) else None
    v_ipca = calc_corrigido(s_ipca_f) if (s_ipca_f is not None and not s_ipca_f.empty) else None
    v_ibov = calc_corrigido(s_ibov_f) if (s_ibov_f is not None and not s_ibov_f.empty) else None

    return vf_ativo, investido, lucro, v_cdi, v_ipca, v_ibov

col1, col2, col3 = st.columns(3)

for anos, col in [(10, col1), (5, col2), (1, col3)]:
    vf, vi, lucro, v_cdi, v_ipca, v_ibov = calcular_tudo(
        df_acao, valor_aporte, anos,
        s_cdi, s_ipca, df_ibov_c,
        data_inicio, data_fim
    )

    titulo_col = f"Total em {anos} anos" if anos > 1 else "Total em 1 ano"

    with col:
        if vf <= 0 or vi <= 0:
            st.markdown(f"""
            <div class="total-card">
                <div class="total-label">{titulo_col}</div>
                <div class="total-amount">—</div>
            </div>
            <div class="info-card">
                <div class="card-header">Aviso</div>
                <div class="card-item">Dados insuficientes no período selecionado.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="total-card">
                <div class="total-label">{titulo_col}</div>
                <div class="total-amount">{formata_br(vf)}</div>
            </div>
            """, unsafe_allow_html=True)

            # monta benchmarks dinamicamente (não mostra "R$ 0" se não estiver disponível)
            bench_lines = []
            if v_cdi is not None:
                bench_lines.append(f'<div class="card-item">🎯 <b>CDI:</b> {formata_br(v_cdi)}</div>')
            if v_ibov is not None:
                bench_lines.append(f'<div class="card-item">📈 <b>Ibovespa:</b> {formata_br(v_ibov)}</div>')
            if v_ipca is not None:
                bench_lines.append(f'<div class="card-item">🛡️ <b>Correção IPCA:</b> {formata_br(v_ipca)}</div>')

            bench_html = "\n".join(bench_lines) if bench_lines else '<div class="card-item">—</div>'

            st.markdown(f"""
            <div class="info-card">
                <div class="card-header">Benchmarks (Valor Corrigido)</div>
                {bench_html}
                <hr style="margin: 10px 0; border: 0; border-top: 1px solid #e2e8f0;">
                <div class="card-header">Análise da Carteira</div>
                <div class="card-item">💵 <b>Capital Nominal Investido:</b> {formata_br(vi)}</div>
                <div class="card-destaque">💰 Lucro Acumulado: {formata_br(lucro)}</div>
            </div>
            """, unsafe_allow_html=True)

# Glossário mantido (com ajuste de termos)
st.markdown("""
<div class="glossario-container">
<h3 style="color: #1f77b4; margin-top:0;">Guia de Termos e Indicadores</h3>

<span class="glossario-termo">• CDI (Certificado de Depósito Interbancário)</span>
<span class="glossario-def">Referência da renda fixa que representa o retorno de aplicações seguras (ex: Tesouro Selic). Serve para avaliar se o risco de investir em ações trouxe um prêmio sobre a taxa básica.</span>

<span class="glossario-termo">• Correção IPCA (Inflação)</span>
<span class="glossario-def">Atualiza o valor investido para o poder de compra atual. Indica quanto você precisaria ter hoje para manter o mesmo patrimônio real do passado.</span>

<span class="glossario-termo">• Ibovespa</span>
<span class="glossario-def">Principal índice da bolsa brasileira, composto pelas ações com maior volume de negociação. Usado como benchmark para medir se o ativo superou a média do mercado nacional.</span>

<span class="glossario-termo">• Capital Nominal Investido</span>
<span class="glossario-def">Somatório bruto de todos os aportes mensais, sem considerar juros, inflação ou retornos.</span>

<span class="glossario-termo">• Lucro Acumulado</span>
<span class="glossario-def">Diferença entre o patrimônio final calculado (com retorno total) e o capital nominal investido.</span>

<span class="glossario-termo">• Retorno Total</span>
<span class="glossario-def">Métrica que combina valorização do preço com proventos reinvestidos. O cálculo usa dividendos/JCP e eventos como splits/grupamentos (quando disponíveis na fonte), garantindo consistência histórica ao longo do tempo.</span>

<p style="margin-top:15px; color:#64748b; font-size:0.85rem;">
<b>Nota de dados:</b> Dividendos/JCP e splits/grupamentos são obtidos do Yahoo Finance via yfinance.
Se a fonte não registrar um evento corporativo específico, ele não poderá ser refletido no resultado.
</p>
</div>
""", unsafe_allow_html=True)
