@st.cache_data(show_spinner="Buscando dados no mercado...")
def carregar_tudo(t, d_ini, d_fim):
    t_sa = t if ".SA" in t else t + ".SA"
    try:
        # Ajuste: se a data fim for hoje, o Yahoo pode falhar. 
        # Forçamos a busca para garantir que ele pegue o dado mais recente disponível.
        dados_acao = yf.download(t_sa, start=d_ini, end=d_fim, progress=False)
        dados_ibov = yf.download("^BVSP", start=d_ini, end=d_fim, progress=False)
        
        if dados_acao.empty:
            # Segunda tentativa caso a primeira falhe por conta da data final ser "hoje"
            dados_acao = yf.Ticker(t_sa).history(start=d_ini)
            if dados_acao.empty: return None
        
        # Limpeza e Performance Ação
        df = dados_acao[['Close']].copy()
        # Se os dividendos não vierem no download, buscamos via Ticker
        ticker_obj = yf.Ticker(t_sa)
        divs = ticker_obj.dividends
        df['Dividends'] = divs.reindex(df.index, fill_value=0)
        
        df.index = df.index.tz_localize(None)
        df["Price_Pct"] = (df["Close"] / df["Close"].iloc[0]) - 1
        df["Total_Fact"] = (1 + df["Close"].pct_change().fillna(0) + (df["Dividends"]/df["Close"]).fillna(0)).cumprod()
        df["Total_Pct"] = df["Total_Fact"] - 1
        df["Div_Pct"] = df["Total_Pct"] - df["Price_Pct"]
        
        # Performance Ibovespa
        if not dados_ibov.empty:
            ibov_close = dados_ibov['Close'].copy()
            ibov_close.index = ibov_close.index.tz_localize(None)
            df["IBOV_Acum"] = (ibov_close / ibov_close.iloc[0]).reindex(df.index).ffill() - 1
        
        # Benchmarks BCB
        s, e = df.index[0].strftime('%d/%m/%Y'), df.index[-1].strftime('%d/%m/%Y')
        df_ipca = get_bcb(433, s, e, 0.004)
        ipca_f = df_ipca.reindex(pd.date_range(df.index[0], df.index[-1]), method='ffill')
        df["IPCA_Fator"] = (1 + (ipca_f['valor']/21)).cumprod().reindex(df.index).ffill()
        df["IPCA_Acum"] = df["IPCA_Fator"] - 1
        
        df_cdi = get_bcb(12, s, e, 0.0004)
        cdi_f = df_cdi.reindex(pd.date_range(df.index[0], df.index[-1]), method='ffill')
        df["CDI_Acum"] = (1 + cdi_f['valor']).cumprod().reindex(df.index).ffill() - 1
        
        return df
    except Exception as e:
        print(f"Erro interno: {e}")
        return None
