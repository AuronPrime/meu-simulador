import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import date, timedelta, datetime
import time
import calendar

# =========================================================
# 1) CONFIGURAÇÃO DA PÁGINA
# =========================================================
st.set_page_config(page_title="Simulador de Patrimônio", layout="wide")

st.markdown(
    """
<style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #1f77b4; }

    .resumo-objetivo {
        font-size: 0.95rem;
        color: #333;
        background-color: #e8f0fe;
        padding: 18px;
        border-radius: 10px;
        margin-bottom: 15px;
        border-left: 5px solid #1f77b4;
        line-height: 1.6;
    }

    .instrucoes {
        font-size: 0.9rem;
        color: #0f172a;
        background-color: #f8fafc;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 12px;
        border: 1px solid #e2e8f0;
        line-height: 1.55;
    }
    .instrucoes b { color: #1f77b4; }
    .instrucoes .obs { color: #475569; font-size: 0.85rem; margin-top: 8px; }

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

    .warn-box {
        background: #fff7ed;
        border: 1px solid #fed7aa;
        border-left: 5px solid #fb923c;
        padding: 12px 14px;
        border-radius: 10px;
        color: #7c2d12;
        margin: 10px 0 0 0;
        font-size: 0.9rem;
        line-height: 1.5;
    }

    .ok-box {
        background: #ecfdf5;
        border: 1px solid #a7f3d0;
        border-left: 5px solid #10b981;
        padding: 10px 12px;
        border-radius: 10px;
        color: #065f46;
        margin-top: 8px;
        font-size: 0.88rem;
        line-height: 1.5;
    }

    .bad-box {
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-left: 5px solid #ef4444;
        padding: 10px 12px;
        border-radius: 10px;
        color: #7f1d1d;
        margin-top: 8px;
        font-size: 0.88rem;
        line-height: 1.5;
    }

    .muted {
        color: #64748b;
        font-size: 0.85rem;
    }
</style>
""",
    unsafe_allow_html=True,
)

def formata_br(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formata_pct(x: float) -> str:
    return f"{x:.2f}%".replace(".", ",")

def periodo_em_anos_meses(d1: date, d2: date) -> tuple[int, int]:
    """Retorna (anos, meses) aproximado, considerando dia do mês."""
    if d1 >= d2:
        return (0, 0)
    months = (d2.year - d1.year) * 12 + (d2.month - d1.month)
    # se o dia final é menor, não completou o mês
    if d2.day < d1.day:
        months -= 1
    years = max(0, months // 12)
    rem = max(0, months % 12)
    return years, rem

st.title("Simulador de Acúmulo de Patrimônio")

# =========================================================
# 2) FUNÇÕES DE DADOS (BCB / Yahoo) + CÁLCULOS
# =========================================================

def _fetch_bcb_json(codigo: int, d_inicio: date, d_fim: date, timeout: int = 30) -> pd.DataFrame:
    s, e = d_inicio.strftime("%d/%m/%Y"), d_fim.strftime("%d/%m/%Y")
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
    params = {"formato": "json", "dataInicial": s, "dataFinal": e}
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"BCB/SGS HTTP {r.status_code}")
    df = pd.DataFrame(r.json())
    if df.empty:
        return pd.DataFrame(columns=["data", "valor"])
    return df

@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def busca_indice_bcb(codigo: int, d_inicio: date, d_fim: date) -> pd.Series:
    if d_inicio is None or d_fim is None or d_inicio > d_fim:
        return pd.Series(dtype="float64")

    start = pd.Timestamp(d_inicio)
    end = pd.Timestamp(d_fim)
    partes = []
    cur = start

    # baixa em blocos por robustez (não limita escolha do usuário)
    while cur <= end:
        chunk_end = min(end, (cur + pd.DateOffset(years=10)) - pd.Timedelta(days=1))
        d1, d2 = cur.date(), chunk_end.date()

        ok = False
        for i in range(5):
            try:
                df = _fetch_bcb_json(codigo, d1, d2, timeout=30)
                if not df.empty:
                    partes.append(df)
                ok = True
                break
            except Exception:
                time.sleep(i + 1)

        if not ok:
            return pd.Series(dtype="float64")

        cur = chunk_end + pd.Timedelta(days=1)

    if not partes:
        return pd.Series(dtype="float64")

    df_all = pd.concat(partes, ignore_index=True)
    if df_all.empty:
        return pd.Series(dtype="float64")

    df_all["data"] = pd.to_datetime(df_all["data"], dayfirst=True, errors="coerce")
    df_all["valor"] = df_all["valor"].astype(str).str.replace(",", ".", regex=False)
    df_all["valor"] = pd.to_numeric(df_all["valor"], errors="coerce") / 100.0
    df_all = df_all.dropna(subset=["data", "valor"]).set_index("data").sort_index()
    if df_all.empty:
        return pd.Series(dtype="float64")

    s = df_all["valor"].astype(float)
    s = s[~s.index.duplicated(keep="last")]
    return (1.0 + s).cumprod()

@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def carregar_renda_fixa(d_inicio: date, d_fim: date) -> tuple[pd.Series, str]:
    s_cdi = busca_indice_bcb(12, d_inicio, d_fim)
    if s_cdi is not None and not s_cdi.empty:
        return s_cdi, "CDI"

    s_selic = busca_indice_bcb(11, d_inicio, d_fim)
    if s_selic is not None and not s_selic.empty:
        return s_selic, "Selic (proxy do CDI)"

    return pd.Series(dtype="float64"), "Renda Fixa"

def _split_efetivo_para_evitar_degrau(df: pd.DataFrame) -> pd.Series:
    close = df["Close"].astype(float)
    prev = close.shift(1)

    split_raw = df.get("Stock Splits", pd.Series(0.0, index=df.index)).fillna(0.0).astype(float)
    split_raw = split_raw.replace(0.0, 1.0)

    actual = close / prev
    expected_unadj = 1.0 / split_raw
    mask = (split_raw != 1.0) & (prev > 0) & (close > 0) & (expected_unadj > 0)

    eff = pd.Series(1.0, index=df.index, dtype=float)
    if mask.any():
        diff_unadj = (np.log(actual[mask]) - np.log(expected_unadj[mask])).abs()
        diff_adj = (np.log(actual[mask]) - np.log(1.0)).abs()
        eff.loc[mask] = np.where(diff_unadj < diff_adj, split_raw[mask], 1.0)

    return eff

@st.cache_data(ttl=60 * 30, show_spinner=False)
def carregar_dados_completos(t: str) -> pd.DataFrame | None:
    if not t:
        return None
    t_sa = t if ".SA" in t else t + ".SA"

    try:
        tk = yf.Ticker(t_sa)
        df = tk.history(period="max", auto_adjust=False, actions=True, interval="1d")
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)

        for col in ["Close", "Dividends", "Stock Splits"]:
            if col not in df.columns:
                df[col] = 0.0

        df = df[["Close", "Dividends", "Stock Splits"]].copy()
        df = df.dropna(subset=["Close"]).sort_index()
        df["Dividends"] = df["Dividends"].fillna(0.0).astype(float)
        df["Stock Splits"] = df["Stock Splits"].fillna(0.0).astype(float)

        split_eff = _split_efetivo_para_evitar_degrau(df)
        close = df["Close"].astype(float)
        prev_close = close.shift(1)

        price_factor = (close * split_eff) / prev_close
        total_factor = ((close + df["Dividends"]) * split_eff) / prev_close

        df["Price_Fact"] = price_factor.replace([np.inf, -np.inf], np.nan).fillna(1.0).cumprod()
        df["Total_Fact"] = total_factor.replace([np.inf, -np.inf], np.nan).fillna(1.0).cumprod()

        return df
    except Exception:
        return None

@st.cache_data(ttl=60 * 30, show_spinner=False)
def carregar_ibov(d_inicio: date, d_fim: date) -> pd.Series:
    try:
        start = max(pd.Timestamp(d_inicio), pd.Timestamp("1990-01-01"))
        df = yf.download("^BVSP", start=start.date(), end=d_fim + timedelta(days=1), progress=False, auto_adjust=False)
        if df is None or df.empty:
            return pd.Series(dtype="float64")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        s = df["Close"].dropna().copy()
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
        return s.sort_index()
    except Exception:
        return pd.Series(dtype="float64")

@st.cache_data(ttl=60 * 10, show_spinner=False)
def validar_ticker_rapido(t: str) -> dict:
    """
    Validação leve para UX: tenta pegar alguns dias de histórico.
    Retorna dict com ok, msg e (opcional) primeira_data_aprox.
    """
    if not t:
        return {"ok": False, "msg": "Digite um ticker (ex.: PETR4, VALE3)."}
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        tk = yf.Ticker(t_sa)
        df = tk.history(period="1mo", auto_adjust=False, actions=False)
        if df is None or df.empty:
            return {"ok": False, "msg": "Ticker não encontrado ou sem dados recentes no Yahoo Finance."}
        first = df.index.min()
        first_str = pd.to_datetime(first).date().strftime("%d/%m/%Y") if first is not None else None
        return {"ok": True, "msg": f"Ticker válido. Há dados recentes (últimos 30 dias).", "first_recent": first_str}
    except Exception:
        return {"ok": False, "msg": "Não foi possível validar agora (instabilidade de rede). Tente analisar mesmo assim."}

def ultimo_pregao_ate(df_index: pd.Index, dt: pd.Timestamp) -> pd.Timestamp | None:
    pos = df_index.get_indexer([dt], method="ffill")[0]
    if pos == -1:
        return None
    return df_index[pos]

def proximo_pregao_a_partir(df_index: pd.Index, dt: pd.Timestamp) -> pd.Timestamp | None:
    pos = df_index.get_indexer([dt], method="bfill")[0]
    if pos == -1:
        return None
    return df_index[pos]

def gerar_datas_aporte_mensal(df_index: pd.Index, dt_inicio: pd.Timestamp, dt_fim_exclusivo: pd.Timestamp) -> pd.DatetimeIndex:
    """
    1 aporte por mês ancorado no dia do mês do início (sem deriva 29/30/31).
    - Se cair em dia sem pregão, executa no próximo pregão.
    - Fim exclusivo (data de avaliação): garante 12 aportes em 1 ano.
    """
    if len(df_index) == 0:
        return pd.DatetimeIndex([])

    dt_inicio = pd.to_datetime(dt_inicio).normalize()
    dt_fim_exclusivo = pd.to_datetime(dt_fim_exclusivo).normalize()

    if dt_inicio >= dt_fim_exclusivo:
        return pd.DatetimeIndex([])

    anchor_day = dt_inicio.day
    year, month = dt_inicio.year, dt_inicio.month

    datas_teoricas = []
    cur = dt_inicio
    for _ in range(5000):
        if cur >= dt_fim_exclusivo:
            break
        datas_teoricas.append(cur)

        month += 1
        if month == 13:
            month = 1
            year += 1
        last_day = calendar.monthrange(year, month)[1]
        day = min(anchor_day, last_day)
        cur = pd.Timestamp(year=year, month=month, day=day)

    datas_exec = []
    for d in datas_teoricas:
        d_exec = proximo_pregao_a_partir(df_index, d)
        if d_exec is None:
            continue
        if d_exec < dt_fim_exclusivo:
            datas_exec.append(d_exec)

    if not datas_exec:
        return pd.DatetimeIndex([])

    return pd.DatetimeIndex(datas_exec)

def calc_valor_corrigido_por_indice(valor_mensal: float, datas_aporte: pd.DatetimeIndex, serie_indice: pd.Series, data_ref: pd.Timestamp) -> float | None:
    if serie_indice is None or serie_indice.empty:
        return None
    s = pd.Series(serie_indice).dropna().sort_index()
    end = s.asof(data_ref)
    if pd.isna(end):
        return None
    at = s.reindex(datas_aporte, method="ffill")
    if at.isna().any():
        return None
    return float((valor_mensal * (end / at)).sum())

def calcular_horizonte(
    df_full: pd.DataFrame,
    valor_mensal: float,
    dt_inicio_user: pd.Timestamp,
    dt_ref_target: pd.Timestamp,
    s_rf: pd.Series,
    s_ipca: pd.Series,
    s_ibov: pd.Series,
):
    if df_full is None or df_full.empty or valor_mensal <= 0:
        return None

    idx = df_full.index
    data_ref = ultimo_pregao_ate(idx, dt_ref_target)
    if data_ref is None:
        return None

    dt_inicio_eff = proximo_pregao_a_partir(idx, dt_inicio_user)
    if dt_inicio_eff is None or dt_inicio_eff >= data_ref:
        return None

    datas_aporte = gerar_datas_aporte_mensal(idx, dt_inicio_eff, data_ref)
    if len(datas_aporte) == 0:
        return None

    investido = float(len(datas_aporte) * valor_mensal)

    tr_end = float(df_full.loc[data_ref, "Total_Fact"])
    tr_at = df_full.loc[datas_aporte, "Total_Fact"].astype(float)

    vf_ativo = float((valor_mensal * (tr_end / tr_at)).sum())
    lucro = vf_ativo - investido
    lucro_pct = (lucro / investido * 100.0) if investido > 0 else 0.0

    v_rf = calc_valor_corrigido_por_indice(valor_mensal, datas_aporte, s_rf, data_ref) if (s_rf is not None and not s_rf.empty) else None
    v_ipca = calc_valor_corrigido_por_indice(valor_mensal, datas_aporte, s_ipca, data_ref) if (s_ipca is not None and not s_ipca.empty) else None
    v_ibov = calc_valor_corrigido_por_indice(valor_mensal, datas_aporte, s_ibov, data_ref) if (s_ibov is not None and not s_ibov.empty) else None

    return {
        "data_ref": data_ref,
        "dt_inicio_eff": dt_inicio_eff,
        "vf": vf_ativo,
        "vi": investido,
        "lucro": lucro,
        "lucro_pct": lucro_pct,
        "v_rf": v_rf,
        "v_ipca": v_ipca,
        "v_ibov": v_ibov,
        "n_aportes": int(len(datas_aporte)),
    }

def calcular_periodo_para_export(
    df_full: pd.DataFrame,
    valor_mensal: float,
    dt_inicio_user: pd.Timestamp,
    dt_fim_user: pd.Timestamp,
    s_rf: pd.Series,
    s_ipca: pd.Series,
    s_ibov: pd.Series,
) -> tuple[pd.DataFrame | None, pd.Timestamp | None, pd.Timestamp | None]:
    """
    Gera uma tabela de aportes para export:
    - data_aporte (execução)
    - aporte
    - fator_ativo e valor_final_ativo
    - (opcional) fator_benchmark e valor_final_benchmark
    """
    if df_full is None or df_full.empty or valor_mensal <= 0:
        return None, None, None

    idx = df_full.index
    data_ref = ultimo_pregao_ate(idx, dt_fim_user)
    if data_ref is None:
        return None, None, None

    dt_inicio_eff = proximo_pregao_a_partir(idx, dt_inicio_user)
    if dt_inicio_eff is None or dt_inicio_eff >= data_ref:
        return None, None, None

    datas_aporte = gerar_datas_aporte_mensal(idx, dt_inicio_eff, data_ref)
    if len(datas_aporte) == 0:
        return None, None, None

    tr_end = float(df_full.loc[data_ref, "Total_Fact"])
    tr_at = df_full.loc[datas_aporte, "Total_Fact"].astype(float)
    fator_ativo = (tr_end / tr_at).astype(float)
    valor_final_ativo = (valor_mensal * fator_ativo).astype(float)

    df_out = pd.DataFrame({
        "data_aporte": pd.to_datetime(datas_aporte).date,
        "aporte": valor_mensal,
        "fator_ativo": fator_ativo.values,
        "valor_no_fim_ativo": valor_final_ativo.values,
    })

    def add_bench(col_prefix: str, s_bench: pd.Series):
        if s_bench is None or s_bench.empty:
            return
        s = pd.Series(s_bench).dropna().sort_index()
        end = s.asof(data_ref)
        if pd.isna(end):
            return
        at = s.reindex(datas_aporte, method="ffill")
        if at.isna().any():
            return
        fator = (end / at).astype(float)
        df_out[f"fator_{col_prefix}"] = fator.values
        df_out[f"valor_no_fim_{col_prefix}"] = (valor_mensal * fator).values

    add_bench("cdi_selic", s_rf)
    add_bench("ipca", s_ipca)
    add_bench("ibov", s_ibov)

    return df_out, dt_inicio_eff, data_ref

def serie_pct_desde_base(s: pd.Series, dt_base: pd.Timestamp, dt_end: pd.Timestamp) -> pd.Series:
    if s is None or s.empty:
        return pd.Series(dtype="float64")
    s = pd.Series(s).dropna().sort_index()

    base = s.asof(dt_base)
    if pd.isna(base):
        s2 = s.loc[(s.index >= dt_base) & (s.index <= dt_end)]
        if s2.empty:
            return pd.Series(dtype="float64")
        base = s2.iloc[0]

    s_plot = s.loc[(s.index >= dt_base) & (s.index <= dt_end)]
    if s_plot.empty:
        return pd.Series(dtype="float64")

    return (s_plot / float(base) - 1.0) * 100.0

# =========================================================
# 3) SIDEBAR: INPUTS COM UX MELHOR
# =========================================================

st.sidebar.markdown(
    """
<div class="instrucoes">
<b>Como usar (rápido):</b><br>
1) Digite o <b>Ticker</b> (ex.: <i>PETR4</i>, <i>VALE3</i>).<br>
2) Defina o <b>aporte mensal</b>.<br>
3) Ajuste <b>Início</b> e <b>Fim</b>.<br>
4) Clique em <b>🔍 Analisar</b> para gerar o gráfico e os cards.
<div class="obs">📌 <b>Obs.:</b> a data de <b>Início</b> é tratada como o <b>1º aporte</b>. Se cair em dia sem pregão, o aporte ocorre no <b>próximo pregão</b>.</div>
</div>
""",
    unsafe_allow_html=True,
)

# Defaults solicitados
hoje = date.today()
d_fim_padrao = hoje - timedelta(days=1)
d_ini_padrao = (pd.Timestamp(d_fim_padrao) - pd.DateOffset(years=10) - pd.Timedelta(days=1)).date()

# Modo avançado (mantém a interface limpa)
modo_avancado = st.sidebar.toggle("Modo avançado", value=False)

ticker_input = st.sidebar.text_input("Ticker", value="", help="Ex.: PETR4, VALE3, BBAS3").upper().strip()

# Feedback do ticker (leve)
if ticker_input:
    vt = validar_ticker_rapido(ticker_input)
    if vt.get("ok"):
        st.sidebar.markdown(f'<div class="ok-box">✅ {vt["msg"]}</div>', unsafe_allow_html=True)
    else:
        st.sidebar.markdown(f'<div class="bad-box">⚠️ {vt["msg"]}</div>', unsafe_allow_html=True)
else:
    st.sidebar.markdown('<div class="muted">Dica: use tickers da B3 (ex.: BBAS3, ITUB4).</div>', unsafe_allow_html=True)

# Aporte: atalhos + valor custom
st.sidebar.subheader("Aporte mensal")
atalhos = ["R$ 100", "R$ 500", "R$ 1.000", "R$ 2.000", "R$ 5.000", "Personalizar"]
atalho_sel = st.sidebar.radio("Atalhos", atalhos, horizontal=True, index=2)

if "valor_aporte" not in st.session_state:
    st.session_state["valor_aporte"] = 1000.0

if atalho_sel != "Personalizar":
    mapa = {
        "R$ 100": 100.0,
        "R$ 500": 500.0,
        "R$ 1.000": 1000.0,
        "R$ 2.000": 2000.0,
        "R$ 5.000": 5000.0,
    }
    st.session_state["valor_aporte"] = mapa[atalho_sel]

valor_aporte = st.sidebar.number_input(
    "Valor (R$)",
    min_value=0.0,
    value=float(st.session_state["valor_aporte"]),
    step=100.0,
)

st.session_state["valor_aporte"] = float(valor_aporte)

# Datas
st.sidebar.subheader("Período")
data_inicio = st.sidebar.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY", max_value=hoje)

anos_sel, meses_sel = periodo_em_anos_meses(data_inicio, data_fim)
st.sidebar.caption(f"Período selecionado: **{anos_sel} ano(s)** e **{meses_sel} mes(es)**.")

# Benchmarks
st.sidebar.subheader("Comparações")
mostrar_rf = st.sidebar.checkbox("CDI / Selic", value=True)
mostrar_ipca = st.sidebar.checkbox("IPCA", value=True)
mostrar_ibov = st.sidebar.checkbox("Ibovespa", value=True)

# Avançado
ticker_comp = ""
mostrar_composicao = True
habilitar_export = False

if modo_avancado:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Avançado")
    mostrar_composicao = st.sidebar.checkbox("Mostrar composição (Valorização + Proventos)", value=True)
    ticker_comp = st.sidebar.text_input("Comparar com outro ticker (opcional)", value="").upper().strip()
    habilitar_export = st.sidebar.checkbox("Habilitar exportação CSV (aportes)", value=True)

btn_analisar = st.sidebar.button("🔍 Analisar", use_container_width=True)

st.sidebar.markdown(
    """
<div style="font-size: 0.85rem; color: #64748b; margin-top: 18px; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 12px;">
Fonte: Yahoo Finance (yfinance) + BCB/SGS<br>
</div>
""",
    unsafe_allow_html=True,
)

# =========================================================
# 4) EXECUÇÃO (botão) + PERSISTÊNCIA
# =========================================================

def _set_loading_step(ph, text: str):
    ph.markdown(f"**{text}**")

if btn_analisar:
    if not ticker_input:
        st.error("Digite um ticker válido na barra lateral.")
        st.stop()

    if data_inicio >= data_fim:
        st.error("A data de **Início** deve ser anterior à data de **Fim**.")
        st.stop()

    # Loading com etapas
    step_ph = st.empty()
    prog = st.progress(0)

    try:
        _set_loading_step(step_ph, "1/4 Carregando ativo…")
        prog.progress(15)
        df_acao = carregar_dados_completos(ticker_input)
        if df_acao is None or df_acao.empty:
            st.error("Ticker não encontrado ou sem dados suficientes (Yahoo Finance).")
            st.stop()

        df_acao_comp = None
        if modo_avancado and ticker_comp:
            _set_loading_step(step_ph, "2/4 Carregando ticker de comparação…")
            prog.progress(35)
            df_acao_comp = carregar_dados_completos(ticker_comp)
            # se falhar, não trava o app, apenas ignora (UX)
            if df_acao_comp is None or df_acao_comp.empty:
                df_acao_comp = None

        _set_loading_step(step_ph, "3/4 Carregando benchmarks (BCB/Yahoo)…")
        prog.progress(60)
        s_rf, nome_rf = carregar_renda_fixa(data_inicio, data_fim)
        s_ipca = busca_indice_bcb(433, data_inicio, data_fim)
        s_ibov = carregar_ibov(data_inicio, data_fim)

        _set_loading_step(step_ph, "4/4 Montando simulação…")
        prog.progress(85)

        st.session_state["analysis_ready"] = True
        st.session_state["params"] = {
            "ticker": ticker_input,
            "ticker_comp": ticker_comp,
            "aporte": float(valor_aporte),
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "mostrar_composicao": bool(mostrar_composicao),
            "modo_avancado": bool(modo_avancado),
            "habilitar_export": bool(habilitar_export),
        }
        st.session_state["df_acao"] = df_acao
        st.session_state["df_acao_comp"] = df_acao_comp
        st.session_state["s_rf"] = s_rf
        st.session_state["nome_rf"] = nome_rf
        st.session_state["s_ipca"] = s_ipca
        st.session_state["s_ibov"] = s_ibov
        st.session_state["last_run_at"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        prog.progress(100)
        step_ph.empty()
        prog.empty()

    except Exception as e:
        prog.empty()
        step_ph.empty()
        st.error(f"Ocorreu um erro ao carregar dados: {e}")
        st.stop()

# =========================================================
# 5) BOAS-VINDAS
# =========================================================
if not st.session_state.get("analysis_ready", False):
    st.markdown(
        """
<div class="resumo-objetivo">
<b>Simule seu patrimônio</b> investindo um valor fixo todo mês em um ativo da B3.<br><br>
O cálculo usa <b>Retorno Total</b>, reinvestindo automaticamente os eventos disponíveis na base de dados: 
<b>dividendos</b>, <b>JCP</b>, <b>bonificações</b>, <b>splits</b>, <b>grupamentos</b> e demais efeitos financeiros registrados pelo provedor.
</div>
<div style="font-size:0.95rem; color:#0f172a;">
➡️ Preencha os dados na barra da esquerda e clique em <b>🔍 Analisar</b>.
</div>
""",
        unsafe_allow_html=True,
    )
    st.stop()

# =========================================================
# 6) RENDERIZAÇÃO (resumo + gráfico + cards)
# =========================================================

params = st.session_state["params"]
ticker_exec = params["ticker"]
ticker_comp_exec = params.get("ticker_comp", "")
valor_aporte_exec = float(params["aporte"])
data_inicio_exec = params["data_inicio"]
data_fim_exec = params["data_fim"]
mostrar_composicao_exec = bool(params.get("mostrar_composicao", True))
modo_avancado_exec = bool(params.get("modo_avancado", False))
habilitar_export_exec = bool(params.get("habilitar_export", False))

df_acao = st.session_state["df_acao"]
df_acao_comp = st.session_state.get("df_acao_comp", None)
s_rf = st.session_state.get("s_rf", pd.Series(dtype="float64"))
nome_rf = st.session_state.get("nome_rf", "CDI/Selic")
s_ipca = st.session_state.get("s_ipca", pd.Series(dtype="float64"))
s_ibov = st.session_state.get("s_ibov", pd.Series(dtype="float64"))
last_run_at = st.session_state.get("last_run_at", "")

dt_ini_user = pd.to_datetime(data_inicio_exec).normalize()
dt_fim_user = pd.to_datetime(data_fim_exec).normalize()

anos_sel, meses_sel = periodo_em_anos_meses(data_inicio_exec, data_fim_exec)

# Header fixo (confiança + contexto)
st.markdown(
    f"""
<div class="muted">
<b>Simulação:</b> {ticker_exec} • <b>Aporte:</b> {formata_br(valor_aporte_exec)} • 
<b>Período:</b> {data_inicio_exec.strftime('%d/%m/%Y')} → {data_fim_exec.strftime('%d/%m/%Y')} 
({anos_sel}a {meses_sel}m) • <b>Atualizado:</b> {last_run_at}
</div>
""",
    unsafe_allow_html=True,
)

# Recorte do ativo no período
df_v = df_acao.loc[(df_acao.index >= dt_ini_user) & (df_acao.index <= dt_fim_user)].copy()
if df_v.empty:
    st.error("Não há dados do ativo no período selecionado (Yahoo Finance). Ajuste o intervalo.")
    st.stop()

df_v["Total_Fact_Chart"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
df_v["Price_Fact_Chart"] = df_v["Price_Fact"] / df_v["Price_Fact"].iloc[0]

dt_base_chart = df_v.index[0]
dt_end_chart = df_v.index[-1]

primeiro_dado_ativo = df_acao.index.min()
if dt_ini_user < primeiro_dado_ativo:
    st.markdown(
        f"""
<div class="warn-box">
⚠️ Você escolheu <b>Início</b> em {dt_ini_user.date().strftime('%d/%m/%Y')}, mas o ativo só tem dados a partir de
<b>{primeiro_dado_ativo.date().strftime('%d/%m/%Y')}</b>.<br>
O gráfico ficará em branco antes dessa data. Nos cálculos, os aportes começam no <b>primeiro pregão disponível</b>.
</div>
""",
        unsafe_allow_html=True,
    )

# Início efetivo (para linhas verticais e cards)
dt_ini_eff = proximo_pregao_a_partir(df_acao.index, dt_ini_user)
if dt_ini_eff is None:
    st.error("Não foi possível determinar o primeiro pregão disponível para o ativo.")
    st.stop()

# =========================================================
# GRÁFICO
# =========================================================
fig = go.Figure()

# Benchmarks ancorados na base do ativo (coerência visual)
if mostrar_rf and (s_rf is not None) and (not s_rf.empty):
    y_rf = serie_pct_desde_base(s_rf, dt_base_chart, dt_end_chart)
    if not y_rf.empty:
        fig.add_trace(go.Scatter(
            x=y_rf.index, y=y_rf, name=nome_rf,
            line=dict(color="gray", width=2, dash="dash"),
            hovertemplate="%{x|%d/%m/%Y}<br><b>" + nome_rf + "</b>: %{y:.2f}%<extra></extra>"
        ))

if mostrar_ipca and (s_ipca is not None) and (not s_ipca.empty):
    y_ipca = serie_pct_desde_base(s_ipca, dt_base_chart, dt_end_chart)
    if not y_ipca.empty:
        fig.add_trace(go.Scatter(
            x=y_ipca.index, y=y_ipca, name="IPCA",
            line=dict(color="red", width=2),
            hovertemplate="%{x|%d/%m/%Y}<br><b>IPCA</b>: %{y:.2f}%<extra></extra>"
        ))

if mostrar_ibov and (s_ibov is not None) and (not s_ibov.empty):
    y_ibov = serie_pct_desde_base(s_ibov, dt_base_chart, dt_end_chart)
    if not y_ibov.empty:
        fig.add_trace(go.Scatter(
            x=y_ibov.index, y=y_ibov, name="Ibovespa",
            line=dict(color="orange", width=2),
            hovertemplate="%{x|%d/%m/%Y}<br><b>Ibovespa</b>: %{y:.2f}%<extra></extra>"
        ))

# (Opcional) ticker de comparação
if modo_avancado_exec and df_acao_comp is not None and isinstance(df_acao_comp, pd.DataFrame) and not df_acao_comp.empty:
    df_comp_v = df_acao_comp.loc[(df_acao_comp.index >= dt_ini_user) & (df_acao_comp.index <= dt_fim_user)].copy()
    if not df_comp_v.empty:
        df_comp_v["Total_Fact_Chart"] = df_comp_v["Total_Fact"] / df_comp_v["Total_Fact"].iloc[0]
        fig.add_trace(go.Scatter(
            x=df_comp_v.index,
            y=(df_comp_v["Total_Fact_Chart"] - 1) * 100,
            name=f"{ticker_comp_exec} (Ret. Total)",
            line=dict(width=2, dash="dot"),
            hovertemplate="%{x|%d/%m/%Y}<br><b>" + ticker_comp_exec + "</b>: %{y:.2f}%<extra></extra>"
        ))

# Composição do ativo (toggle)
ret_preco = (df_v["Price_Fact_Chart"] - 1) * 100
ret_total = (df_v["Total_Fact_Chart"] - 1) * 100
ret_prov = (df_v["Total_Fact_Chart"] - df_v["Price_Fact_Chart"]) * 100

# Hover rico no ativo
custom = np.column_stack([ret_total.values, ret_preco.values, ret_prov.values])
hover_rt = (
    "%{x|%d/%m/%Y}"
    "<br><b>Retorno Total</b>: %{customdata[0]:.2f}%"
    "<br>Valorização: %{customdata[1]:.2f}%"
    "<br>Proventos (rein.): %{customdata[2]:.2f}%"
    "<extra></extra>"
)

if mostrar_composicao_exec:
    fig.add_trace(go.Scatter(
        x=df_v.index, y=ret_preco,
        stackgroup="one", name="Valorização",
        fillcolor="rgba(31, 119, 180, 0.35)", line=dict(width=0),
        customdata=custom, hovertemplate=hover_rt,
        showlegend=True
    ))
    fig.add_trace(go.Scatter(
        x=df_v.index, y=ret_prov,
        stackgroup="one", name="Proventos (reinvestidos)",
        fillcolor="rgba(218, 165, 32, 0.35)", line=dict(width=0),
        customdata=custom, hovertemplate=hover_rt,
        showlegend=True
    ))

fig.add_trace(go.Scatter(
    x=df_v.index, y=ret_total,
    name=f"{ticker_exec} (Retorno Total)",
    line=dict(color="black", width=3),
    customdata=custom, hovertemplate=hover_rt
))

# Linhas verticais (1º aporte efetivo e fim escolhido)
fig.add_vline(
    x=dt_ini_eff,
    line_width=1,
    line_dash="dot",
    line_color="rgba(15,23,42,0.45)",
    annotation_text="1º aporte (efetivo)",
    annotation_position="top left",
)
fig.add_vline(
    x=dt_fim_user,
    line_width=1,
    line_dash="dot",
    line_color="rgba(15,23,42,0.25)",
    annotation_text="Fim escolhido",
    annotation_position="top right",
)

fig.update_layout(
    template="plotly_white",
    hovermode="x unified",
    yaxis=dict(side="right", ticksuffix="%", tickformat=".0f"),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
)

# Eixo X respeita o intervalo do usuário (pode mostrar “branco” antes do ativo ter dados)
fig.update_xaxes(range=[dt_ini_user, dt_fim_user])

st.plotly_chart(fig, use_container_width=True)

# =========================================================
# CARDS (10/5/1)
# =========================================================
st.subheader("Simulação de Patrimônio Acumulado")

horizontes = [10, 5, 1]
cols = st.columns(3)

for anos, col in zip(horizontes, cols):
    with col:
        titulo_col = f"Total em {anos} anos" if anos > 1 else "Total em 1 ano"
        dt_target = dt_ini_eff + pd.DateOffset(years=anos)

        if dt_target > dt_fim_user:
            st.markdown(
                f"""
            <div class="total-card">
                <div class="total-label">{titulo_col}</div>
                <div class="total-amount">—</div>
            </div>
            <div class="info-card">
                <div class="card-header">Período insuficiente</div>
                <div class="card-item">
                    Para calcular <b>{anos} anos</b>, selecione uma data final <b>≥ {dt_target.date().strftime('%d/%m/%Y')}</b>.
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )
            continue

        res = calcular_horizonte(
            df_full=df_acao,
            valor_mensal=float(valor_aporte_exec),
            dt_inicio_user=dt_ini_user,
            dt_ref_target=dt_target,
            s_rf=s_rf if mostrar_rf else pd.Series(dtype="float64"),
            s_ipca=s_ipca if mostrar_ipca else pd.Series(dtype="float64"),
            s_ibov=s_ibov if mostrar_ibov else pd.Series(dtype="float64"),
        )

        if res is None:
            st.markdown(
                f"""
            <div class="total-card">
                <div class="total-label">{titulo_col}</div>
                <div class="total-amount">—</div>
            </div>
            <div class="info-card">
                <div class="card-header">Aviso</div>
                <div class="card-item">Dados insuficientes para o cálculo neste horizonte.</div>
            </div>
            """,
                unsafe_allow_html=True,
            )
            continue

        vf = res["vf"]
        vi = res["vi"]
        lucro = res["lucro"]
        lucro_pct = float(res.get("lucro_pct", 0.0))

        v_rf = res["v_rf"]
        v_ipca = res["v_ipca"]
        v_ibov = res["v_ibov"]

        st.markdown(
            f"""
        <div class="total-card">
            <div class="total-label">{titulo_col}</div>
            <div class="total-amount">{formata_br(vf)}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        bench_lines = []
        if mostrar_rf and v_rf is not None:
            bench_lines.append(f'<div class="card-item">🎯 <b>{nome_rf}:</b> {formata_br(v_rf)}</div>')
        if mostrar_ibov and v_ibov is not None:
            bench_lines.append(f'<div class="card-item">📈 <b>Ibovespa:</b> {formata_br(v_ibov)}</div>')
        if mostrar_ipca and v_ipca is not None:
            bench_lines.append(f'<div class="card-item">🛡️ <b>IPCA (correção):</b> {formata_br(v_ipca)}</div>')
        if not bench_lines:
            bench_lines.append('<div class="card-item">—</div>')

        inicio_eff_str = res["dt_inicio_eff"].date().strftime("%d/%m/%Y")
        data_ref_str = res["data_ref"].date().strftime("%d/%m/%Y")

        st.markdown(
            f"""
        <div class="info-card">
            <div class="card-header">Se você tivesse aportado o mesmo valor em…</div>
            {''.join(bench_lines)}
            <hr style="margin: 10px 0; border: 0; border-top: 1px solid #e2e8f0;">
            <div class="card-header">Resumo do investimento</div>
            <div class="card-item">📅 <b>Início efetivo:</b> {inicio_eff_str}</div>
            <div class="card-item">📍 <b>Data de avaliação:</b> {data_ref_str}</div>
            <div class="card-item">💵 <b>Capital investido:</b> {formata_br(vi)}</div>
            <div class="card-item">🗓️ <b>Nº de aportes:</b> {res['n_aportes']}</div>
            <div class="card-destaque">💰 Lucro: {formata_br(lucro)} <span class="muted">({formata_pct(lucro_pct)})</span></div>
        </div>
        """,
            unsafe_allow_html=True,
        )

# =========================================================
# EXPORT (opcional, modo avançado)
# =========================================================
if modo_avancado_exec and habilitar_export_exec:
    st.markdown("---")
    st.subheader("Exportação")

    df_export, dt_ini_eff2, data_ref2 = calcular_periodo_para_export(
        df_full=df_acao,
        valor_mensal=float(valor_aporte_exec),
        dt_inicio_user=dt_ini_user,
        dt_fim_user=dt_fim_user,
        s_rf=s_rf if mostrar_rf else pd.Series(dtype="float64"),
        s_ipca=s_ipca if mostrar_ipca else pd.Series(dtype="float64"),
        s_ibov=s_ibov if mostrar_ibov else pd.Series(dtype="float64"),
    )

    if df_export is None or df_export.empty:
        st.info("Não foi possível gerar o CSV neste período.")
    else:
        st.caption("CSV com aportes (datas de execução) e o valor de cada aporte no fim do período.")
        csv = df_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Baixar CSV dos aportes",
            data=csv,
            file_name=f"aportes_{ticker_exec}_{data_inicio_exec.strftime('%Y%m%d')}_{data_fim_exec.strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

# =========================================================
# GLOSSÁRIO / METODOLOGIA (compacto)
# =========================================================
st.markdown(
    """
<div class="glossario-container">
<h3 style="color: #1f77b4; margin-top:0;">Metodologia (resumo)</h3>

<span class="glossario-termo">• Retorno Total</span>
<span class="glossario-def">Combina valorização do preço + proventos reinvestidos. Considera eventos corporativos disponíveis na fonte: dividendos/JCP, bonificações, splits e grupamentos.</span>

<span class="glossario-termo">• Benchmarks</span>
<span class="glossario-def">Comparam o resultado final de aportes mensais equivalentes em CDI/Selic, IPCA e Ibovespa (quando selecionados).</span>

<p style="margin-top:15px; color:#64748b; font-size:0.85rem;">
<b>Fontes:</b> Yahoo Finance via yfinance (ativo e eventos), BCB/SGS (CDI/Selic e IPCA). Se a fonte omitir algum evento, ele não poderá ser refletido.
</p>
</div>
""",
    unsafe_allow_html=True,
)
