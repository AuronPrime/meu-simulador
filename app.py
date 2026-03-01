import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import date, timedelta
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

    /* ✅ Hierarquia (cards) */
    .total-sub-muted { font-size: 0.88rem; color: #64748b; margin-top: 4px; }
    .total-sub-profit { font-size: 0.95rem; font-weight: 800; color: #0f172a; margin-top: 6px; }
    .small-muted { font-size: 0.78rem; color: #64748b; }

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

    /* ✅ Status do ticker (menor e discreto) */
    .ticker-status {
        font-size: 0.78rem;
        padding: 6px 8px;
        border-radius: 8px;
        margin-top: 6px;
        border: 1px solid;
        line-height: 1.25;
        opacity: 0.95;
    }
    .ticker-ok { background: #ecfdf5; color: #065f46; border-color: #a7f3d0; }
    .ticker-bad { background: #fef2f2; color: #991b1b; border-color: #fecaca; }
    .ticker-neutral { background: #f8fafc; color: #475569; border-color: #e2e8f0; }

    /* ✅ Título do glossário sem "ícone/link" */
    .glossario-title {
        font-size: 1.45rem;
        font-weight: 800;
        color: #1f77b4;
        margin: 0 0 10px 0;
        padding: 0;
    }
</style>
""",
    unsafe_allow_html=True,
)

def formata_br(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

st.title("Simulador de Acúmulo de Patrimônio")

# =========================================================
# 2) FUNÇÕES DE SUPORTE
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
    while cur <= end:
        chunk_end = min(end, (cur + pd.DateOffset(years=10)) - pd.Timedelta(days=1))
        d1 = cur.date()
        d2 = chunk_end.date()

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
        return s_selic, "Selic (proxy CDI)"

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
        df = tk.history(start="1900-01-01", auto_adjust=False, actions=True, interval="1d")

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
    1 aporte por mês ancorado no dia do mês do início.
    - Se mês não tiver o dia (29/30/31), usa último dia do mês.
    - Se cair em dia sem pregão, executa no próximo pregão.
    - dt_fim_exclusivo é fim EXCLUSIVO (data de avaliação), garantindo:
      1 ano => 12 aportes, 5 anos => 60, 10 anos => 120.
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
    if dt_inicio_eff is None:
        return None
    if dt_inicio_eff >= data_ref:
        return None

    datas_aporte = gerar_datas_aporte_mensal(idx, dt_inicio_eff, data_ref)  # fim exclusivo
    if len(datas_aporte) == 0:
        return None

    investido = float(len(datas_aporte) * valor_mensal)

    tr_end = float(df_full.loc[data_ref, "Total_Fact"])
    tr_at = df_full.loc[datas_aporte, "Total_Fact"].astype(float)

    vf_ativo = float((valor_mensal * (tr_end / tr_at)).sum())
    lucro = vf_ativo - investido

    v_rf = calc_valor_corrigido_por_indice(valor_mensal, datas_aporte, s_rf, data_ref) if (s_rf is not None and not s_rf.empty) else None
    v_ipca = calc_valor_corrigido_por_indice(valor_mensal, datas_aporte, s_ipca, data_ref) if (s_ipca is not None and not s_ipca.empty) else None
    v_ibov = calc_valor_corrigido_por_indice(valor_mensal, datas_aporte, s_ibov, data_ref) if (s_ibov is not None and not s_ibov.empty) else None

    return {
        "data_ref": data_ref,
        "dt_inicio_eff": dt_inicio_eff,
        "vf": vf_ativo,
        "vi": investido,
        "lucro": lucro,
        "v_rf": v_rf,
        "v_ipca": v_ipca,
        "v_ibov": v_ibov,
        "n_aportes": int(len(datas_aporte)),
    }

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
# ✅ TICKER STATUS (certo/errado) – importado do outro código
# =========================================================

def normaliza_ticker_usuario(t: str) -> tuple[str, str]:
    t = (t or "").upper().strip()
    if not t:
        return "", ""
    base = t[:-3] if t.endswith(".SA") else t
    return base, base + ".SA"

TICKER_APELIDOS: dict[str, str] = {
    "BBAS3": "Banco do Brasil",
    "ITUB3": "Banco Itaú",
    "ITUB4": "Banco Itaú",
    "BBDC3": "Banco Bradesco",
    "BBDC4": "Banco Bradesco",
    "SANB3": "Banco Santander",
    "SANB4": "Banco Santander",
    "PETR3": "Petrobras",
    "PETR4": "Petrobras",
    "VALE3": "Vale",
}

def _limpa_nome_yahoo(nome_raw: str) -> str:
    if not nome_raw:
        return ""
    n = " ".join(str(nome_raw).strip().split())
    remove_tokens = {"ON", "PN", "PNA", "PNB", "PNC", "UNT", "UNIT", "NM", "N1", "N2", "MA", "MB"}
    parts = [p for p in n.replace("/", " ").split() if p.upper() not in remove_tokens]
    n2 = " ".join(parts).strip()
    for suf in [" S.A.", " SA"]:
        n2 = n2.replace(suf, " ").strip()
    n2 = " ".join(n2.split())

    title = n2.lower().title()
    for w in [" Da ", " De ", " Do ", " Das ", " Dos ", " E "]:
        title = title.replace(w, w.lower())
    return title.strip()

def nome_comercial_para_ticker(base: str, nome_yahoo: str) -> str:
    base = (base or "").upper().strip()
    if base in TICKER_APELIDOS:
        return TICKER_APELIDOS[base]
    cleaned = _limpa_nome_yahoo(nome_yahoo)
    return cleaned if cleaned else base

@st.cache_data(ttl=60 * 10, show_spinner=False)
def validar_ticker_yahoo(base: str) -> tuple[bool, str]:
    """
    Retorna (ok, nome_raw). Cache curto para não consultar toda hora.
    """
    if not base:
        return False, ""
    _, t_sa = normaliza_ticker_usuario(base)
    try:
        tk = yf.Ticker(t_sa)
        h = tk.history(period="5d", auto_adjust=False)
        if h is None or h.empty:
            return False, ""
        nome = ""
        try:
            info = tk.info or {}
            nome = info.get("shortName") or info.get("longName") or ""
        except Exception:
            nome = ""
        return True, nome
    except Exception:
        return False, ""

# =========================================================
# 3) BARRA LATERAL (inputs + status do ticker)
# =========================================================

st.sidebar.markdown(
    """
<div class="instrucoes">
<b>Como usar (rápido):</b><br>
1) Digite o <b>Ticker</b> (ex.: <i>PETR4</i>, <i>VALE3</i>).<br>
2) Defina o <b>aporte mensal</b>.<br>
3) Escolha <b>Início</b> e <b>Fim</b> da simulação.<br>
4) Clique em <b>🔍 Analisar Patrimônio</b>.<br>
5) Use os toggles de <b>benchmarks</b> para comparar no gráfico e nos cards.
<div class="obs">📌 <b>Obs.:</b> a data de <b>Início</b> é tratada como o <b>1º aporte</b>. Se cair em dia sem pregão, o aporte é executado no <b>próximo pregão</b>.</div>
</div>
""",
    unsafe_allow_html=True,
)

hoje = date.today()
d_fim_padrao = hoje - timedelta(days=1)
d_ini_padrao = (pd.Timestamp(d_fim_padrao) - pd.DateOffset(years=10) - pd.Timedelta(days=1)).date()

ticker_input = st.sidebar.text_input("Digite o Ticker", "", key="ticker_input").upper().strip()

# ✅ Caixa pequena informando se encontrou ou não
ticker_box = st.sidebar.empty()
if ticker_input:
    base, _ = normaliza_ticker_usuario(ticker_input)
    if len(base) >= 4:
        ok, nome_raw = validar_ticker_yahoo(base)
        if ok:
            nome_show = nome_comercial_para_ticker(base, nome_raw)
            ticker_box.markdown(
                f'<div class="ticker-status ticker-ok">Encontrado: <b>{nome_show}</b> ({base})</div>',
                unsafe_allow_html=True,
            )
        else:
            ticker_box.markdown(
                '<div class="ticker-status ticker-bad">Ticker não encontrado. Ex.: <b>PETR4</b>, <b>VALE3</b>, <b>BBAS3</b>…</div>',
                unsafe_allow_html=True,
            )
    else:
        ticker_box.markdown(
            '<div class="ticker-status ticker-neutral">Ex.: <b>PETR4</b>, <b>VALE3</b>, <b>BBAS3</b></div>',
            unsafe_allow_html=True,
        )
else:
    ticker_box.markdown(
        '<div class="ticker-status ticker-neutral">Exemplos: <b>PETR4</b>, <b>VALE3</b>, <b>BBAS3</b></div>',
        unsafe_allow_html=True,
    )

valor_aporte = st.sidebar.number_input("Aporte mensal (R$)", min_value=0.0, value=1000.0, step=100.0)

st.sidebar.subheader("Período da Simulação")
data_inicio = st.sidebar.date_input("Início", d_ini_padrao, format="DD/MM/YYYY")
data_fim = st.sidebar.date_input("Fim", d_fim_padrao, format="DD/MM/YYYY", max_value=hoje)

btn_analisar = st.sidebar.button("🔍 Analisar Patrimônio")

st.sidebar.subheader("Benchmarks")
mostrar_rf = st.sidebar.checkbox("Renda Fixa (CDI/Selic)", value=True, key="mostrar_rf")
mostrar_ipca = st.sidebar.checkbox("IPCA (Inflação)", value=True, key="mostrar_ipca")
mostrar_ibov = st.sidebar.checkbox("Ibovespa (Mercado)", value=True, key="mostrar_ibov")

st.sidebar.markdown(
    """
<div style="font-size: 0.85rem; color: #64748b; margin-top: 25px; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 15px;">
Desenvolvido por: <br>
<a href="https://www.instagram.com/ramoon.bastos?igsh=MTFiODlnZ28ybHFqdw%3D%3D&utm_source=qr" target="_blank" style="color: #1f77b4; text-decoration: none; font-weight: bold;">IG: Ramoon.Bastos</a>
</div>
""",
    unsafe_allow_html=True,
)

# =========================================================
# 4) EXECUÇÃO CONTROLADA (botão) + PERSISTÊNCIA
# =========================================================

if btn_analisar:
    if not ticker_input:
        st.error("Digite um ticker válido no menu lateral.")
        st.stop()

    if data_inicio >= data_fim:
        st.error("A data de **Início** deve ser anterior à data de **Fim**.")
        st.stop()

    with st.spinner("Sincronizando dados de mercado..."):
        s_rf, nome_rf = carregar_renda_fixa(data_inicio, data_fim)
        s_ipca = busca_indice_bcb(433, data_inicio, data_fim)
        df_acao = carregar_dados_completos(ticker_input)
        s_ibov = carregar_ibov(data_inicio, data_fim)

    if df_acao is None or df_acao.empty:
        st.error("Ticker não encontrado ou sem dados suficientes (Yahoo Finance).")
        st.stop()

    st.session_state["analysis_ready"] = True
    st.session_state["params"] = {
        "ticker": ticker_input,
        "aporte": float(valor_aporte),
        "data_inicio": data_inicio,
        "data_fim": data_fim,
    }
    st.session_state["df_acao"] = df_acao
    st.session_state["s_rf"] = s_rf
    st.session_state["nome_rf"] = nome_rf
    st.session_state["s_ipca"] = s_ipca
    st.session_state["s_ibov"] = s_ibov

if not st.session_state.get("analysis_ready", False):
    st.markdown(
        """
<div class="resumo-objetivo">
👋 <b>Bem-vindo!</b><br>
Este simulador calcula o acúmulo de patrimônio via <b>Retorno Total</b>, reinvestindo automaticamente os proventos disponíveis na base de dados (ex.: <b>dividendos</b> / <b>JCP</b>).<br><br>
<b>Eventos corporativos considerados (quando disponíveis na fonte):</b> <b>dividendos</b>, <b>JCP</b>, <b>bonificações</b>, <b>splits</b>, <b>grupamentos</b> e demais efeitos financeiros registrados pelo provedor de dados.
</div>
<div style="font-size:0.95rem; color:#0f172a;">
🙂 Para começar, siga as instruções conforme as orientações da <b>barra da esquerda</b>.
</div>
""",
        unsafe_allow_html=True,
    )
    st.stop()

# =========================================================
# 5) RENDERIZAÇÃO (gráfico + cards)
# =========================================================

params = st.session_state["params"]
ticker_exec = params["ticker"]
valor_aporte_exec = float(params["aporte"])
data_inicio_exec = params["data_inicio"]
data_fim_exec = params["data_fim"]

df_acao = st.session_state["df_acao"]
s_rf = st.session_state.get("s_rf", pd.Series(dtype="float64"))
nome_rf = st.session_state.get("nome_rf", "Renda Fixa")
s_ipca = st.session_state.get("s_ipca", pd.Series(dtype="float64"))
s_ibov = st.session_state.get("s_ibov", pd.Series(dtype="float64"))

dt_ini_user = pd.to_datetime(data_inicio_exec).normalize()
dt_fim_user = pd.to_datetime(data_fim_exec).normalize()

st.caption(
    f"Simulação carregada: **{ticker_exec}** | Aporte mensal: **{formata_br(valor_aporte_exec)}** | Período: **{data_inicio_exec.strftime('%d/%m/%Y')} → {data_fim_exec.strftime('%d/%m/%Y')}**"
)

# Recorte do ativo na janela
df_v = df_acao.loc[(df_acao.index >= dt_ini_user) & (df_acao.index <= dt_fim_user)].copy()
if df_v.empty:
    st.error("Não há dados do ativo no período selecionado (Yahoo Finance). Tente ampliar/alterar o intervalo.")
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
O gráfico ficará “em branco” antes dessa data. Nos cálculos, os aportes passam a contar a partir do <b>primeiro pregão disponível</b>.
</div>
""",
        unsafe_allow_html=True,
    )

# -------------------------
# GRÁFICO
# -------------------------
fig = go.Figure()

if mostrar_rf and (s_rf is not None) and (not s_rf.empty):
    y_rf = serie_pct_desde_base(s_rf, dt_base_chart, dt_end_chart)
    if not y_rf.empty:
        fig.add_trace(go.Scatter(x=y_rf.index, y=y_rf, name=nome_rf,
                                 line=dict(color="gray", width=2, dash="dash")))

if mostrar_ipca and (s_ipca is not None) and (not s_ipca.empty):
    y_ipca = serie_pct_desde_base(s_ipca, dt_base_chart, dt_end_chart)
    if not y_ipca.empty:
        fig.add_trace(go.Scatter(x=y_ipca.index, y=y_ipca, name="IPCA",
                                 line=dict(color="red", width=2)))

if mostrar_ibov and (s_ibov is not None) and (not s_ibov.empty):
    y_ibov = serie_pct_desde_base(s_ibov, dt_base_chart, dt_end_chart)
    if not y_ibov.empty:
        fig.add_trace(go.Scatter(x=y_ibov.index, y=y_ibov, name="Ibovespa",
                                 line=dict(color="orange", width=2)))

fig.add_trace(
    go.Scatter(
        x=df_v.index,
        y=(df_v["Price_Fact_Chart"] - 1) * 100,
        stackgroup="one",
        name="Valorização",
        fillcolor="rgba(31, 119, 180, 0.4)",
        line=dict(width=0),
    )
)
fig.add_trace(
    go.Scatter(
        x=df_v.index,
        y=(df_v["Total_Fact_Chart"] - df_v["Price_Fact_Chart"]) * 100,
        stackgroup="one",
        name="Proventos (reinvestidos)",
        fillcolor="rgba(218, 165, 32, 0.4)",
        line=dict(width=0),
    )
)
fig.add_trace(
    go.Scatter(
        x=df_v.index,
        y=(df_v["Total_Fact_Chart"] - 1) * 100,
        name="RETORNO TOTAL",
        line=dict(color="black", width=3),
    )
)

fig.update_layout(
    template="plotly_white",
    hovermode="x unified",
    yaxis=dict(side="right", ticksuffix="%", tickformat=".0f"),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
)
fig.update_xaxes(range=[dt_ini_user, dt_fim_user])

st.plotly_chart(fig, use_container_width=True)

# -------------------------
# ✅ CARDS (10, 5 e 1 ano) – importado do outro código
# -------------------------
st.subheader("Simulação de Patrimônio Acumulado")

horizontes = [10, 5, 1]
cols = st.columns(3)

dt_ini_eff = proximo_pregao_a_partir(df_acao.index, dt_ini_user)
if dt_ini_eff is None:
    st.error("Não foi possível determinar o primeiro pregão disponível para o ativo.")
    st.stop()

for anos, col in zip(horizontes, cols):
    with col:
        titulo_col = f"Total em {anos} anos" if anos > 1 else "Total em 1 ano"
        dt_target = dt_ini_eff + pd.DateOffset(years=anos)

        if dt_target > dt_fim_user:
            dt_target_str = dt_target.date().strftime("%d/%m/%Y")
            html_insuf = (
                f'<div class="total-card">'
                f'  <div class="total-label">{titulo_col}</div>'
                f'  <div class="total-amount">—</div>'
                f'</div>'
                f'<div class="info-card">'
                f'  <div class="card-header">Período insuficiente</div>'
                f'  <div class="card-item">Para calcular <b>{anos} anos</b>, aumente a data <b>Fim</b> para <b>≥ {dt_target_str}</b> (ajuste no menu lateral).</div>'
                f'</div>'
            )
            st.markdown(html_insuf, unsafe_allow_html=True)
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
            html_none = (
                f'<div class="total-card">'
                f'  <div class="total-label">{titulo_col}</div>'
                f'  <div class="total-amount">—</div>'
                f'</div>'
                f'<div class="info-card">'
                f'  <div class="card-header">Aviso</div>'
                f'  <div class="card-item">Dados insuficientes para o cálculo neste horizonte.</div>'
                f'</div>'
            )
            st.markdown(html_none, unsafe_allow_html=True)
            continue

        vf = float(res["vf"])
        vi = float(res["vi"])
        lucro = float(res["lucro"])
        v_rf = res["v_rf"]
        v_ipca = res["v_ipca"]
        v_ibov = res["v_ibov"]
        pct_lucro = (lucro / vi * 100.0) if vi > 0 else 0.0

        html_total = (
            f'<div class="total-card">'
            f'  <div class="total-label">{titulo_col}</div>'
            f'  <div class="total-amount">{formata_br(vf)}</div>'
            f'  <div class="total-sub-muted">Investido: {formata_br(vi)}</div>'
            f'  <div class="total-sub-profit">Lucro: {formata_br(lucro)} ({pct_lucro:.1f}%)</div>'
            f'</div>'
        )
        st.markdown(html_total, unsafe_allow_html=True)

        bench_lines = []
        if mostrar_rf and v_rf is not None:
            bench_lines.append(f'<div class="card-item">🎯 <b>{nome_rf}:</b> {formata_br(v_rf)}</div>')
        if mostrar_ibov and v_ibov is not None:
            bench_lines.append(f'<div class="card-item">📈 <b>Ibovespa:</b> {formata_br(v_ibov)}</div>')
        if mostrar_ipca and v_ipca is not None:
            bench_lines.append(f'<div class="card-item">🛡️ <b>Correção IPCA:</b> {formata_br(v_ipca)}</div>')
        if not bench_lines:
            bench_lines.append('<div class="card-item">—</div>')

        inicio_eff_str = res["dt_inicio_eff"].date().strftime("%d/%m/%Y")
        data_ref_str = res["data_ref"].date().strftime("%d/%m/%Y")

        html_info = (
            f'<div class="info-card">'
            f'  <div class="card-header">Benchmarks (Valor Corrigido)</div>'
            f'  {"".join(bench_lines)}'
            f'  <hr style="margin: 10px 0; border: 0; border-top: 1px solid #e2e8f0;">'
            f'  <div class="card-header">Análise da Carteira</div>'
            f'  <div class="card-item">📅 <b>Início efetivo (1º pregão):</b> {inicio_eff_str}</div>'
            f'  <div class="card-item">📍 <b>Data final usada no cálculo:</b> {data_ref_str} <span class="small-muted">(último pregão disponível até a data-alvo)</span></div>'
            f'  <div class="card-item">💵 <b>Capital Nominal Investido:</b> {formata_br(vi)}</div>'
            f'  <div class="card-item">🗓️ <b>Nº de aportes:</b> {res["n_aportes"]}</div>'
            f'  <div class="card-destaque">💰 Lucro Acumulado: {formata_br(lucro)} ({pct_lucro:.1f}%)</div>'
            f'</div>'
        )
        st.markdown(html_info, unsafe_allow_html=True)

# -------------------------
# ✅ GLOSSÁRIO (sem hyperlink no título)
# -------------------------
st.markdown(
    """
<div class="glossario-container">
  <div class="glossario-title">Guia de Termos e Indicadores</div>

  <span class="glossario-termo">• Renda Fixa (CDI / Selic)</span>
  <span class="glossario-def">Referência de retorno para aplicações de baixo risco. O app tenta usar <b>CDI</b>; se a fonte falhar, usa a <b>Selic</b> como proxy.</span>

  <span class="glossario-termo">• Correção IPCA (Inflação)</span>
  <span class="glossario-def">Atualiza o valor investido para o poder de compra atual.</span>

  <span class="glossario-termo">• Ibovespa</span>
  <span class="glossario-def">Principal índice da bolsa brasileira, usado como referência de desempenho do mercado.</span>

  <span class="glossario-termo">• Capital Nominal Investido</span>
  <span class="glossario-def">Somatório bruto de todos os aportes mensais, sem considerar juros, inflação ou retornos.</span>

  <span class="glossario-termo">• Lucro Acumulado</span>
  <span class="glossario-def">Diferença entre o patrimônio final calculado (com retorno total) e o capital nominal investido.</span>

  <span class="glossario-termo">• Retorno Total</span>
  <span class="glossario-def">Métrica que combina valorização do preço com proventos reinvestidos. Considera os eventos corporativos disponíveis na fonte (ex.: dividendos/JCP, bonificações, splits/grupamentos etc.).</span>

  <p style="margin-top:15px; color:#64748b; font-size:0.85rem;">
    <b>Nota de dados:</b> proventos e eventos corporativos são obtidos do Yahoo Finance via yfinance. Se a fonte omitir algum evento, ele não poderá ser refletido no resultado.
  </p>
</div>
""",
    unsafe_allow_html=True,
)
