# 4. LOGICA PRINCIPAL
if ticker_input and btn_analisar:
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
        # Filtragem do DataFrame pelo período selecionado pelo usuário (Seta Azul)
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            # --- GRÁFICO (Mantido) ---
            df_v["Total_Fact_Chart"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
            df_v["Price_Base_Chart"] = df_v["Close"] / df_v["Close"].iloc[0]
            
            fig = go.Figure()
            if not s_cdi.empty: fig.add_trace(go.Scatter(x=s_cdi.index, y=(s_cdi/s_cdi.iloc[0]-1)*100, name='CDI', line=dict(color='gray', width=2, dash='dash')))
            if not s_ipca.empty: fig.add_trace(go.Scatter(x=s_ipca.index, y=(s_ipca/s_ipca.iloc[0]-1)*100, name='IPCA', line=dict(color='red', width=2)))
            if not df_ibov_c.empty: fig.add_trace(go.Scatter(x=df_ibov_c.index, y=(df_ibov_c/df_ibov_c.iloc[0]-1)*100, name='Ibovespa', line=dict(color='orange', width=2)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base_Chart"]-1)*100, stackgroup='one', name='Valorização', fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-df_v["Price_Base_Chart"])*100, stackgroup='one', name='Proventos', fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-1)*100, name='RETORNO TOTAL', line=dict(color='black', width=3)))
            fig.update_layout(template="plotly_white", hovermode="x unified", yaxis=dict(side="right", ticksuffix="%", tickformat=".0f"), margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
            st.plotly_chart(fig, use_container_width=True)

            # --- NOVA LÓGICA DE CÁLCULO DOS CARDS (Seta Vermelha vinculada à Seta Azul) ---
            st.subheader(f"Resultado Acumulado: {data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}")

            # Identificar datas de aportes mensais dentro do período selecionado
            df_v['month'] = df_v.index.to_period('M')
            datas_aportes = df_v.groupby('month').head(1).index.tolist()
            
            # Cálculo do Valor Final (Ativo com Reinvestimento)
            # Valor Final = Somatório de (Aporte / Preço na data) * Preço Atual * Fator de Proventos acumulado desde a data do aporte
            vf_ativo = sum(valor_aporte * (df_v["Total_Fact"].iloc[-1] / df_v["Total_Fact"].loc[d]) for d in datas_aportes)
            
            capital_nominal = len(datas_aportes) * valor_aporte
            lucro_total = vf_ativo - capital_nominal

            # Cálculo de Benchmarks para o mesmo período exato
            def calc_bench_periodo(serie):
                if serie.empty: return 0
                # Pega o valor da série nas datas de aporte (ou a data mais próxima)
                return sum(valor_aporte * (serie.iloc[-1] / serie.asof(d)) for d in datas_aportes if d in serie.index or d >= serie.index[0])

            v_cdi = calc_bench_periodo(s_cdi)
            v_ipca = calc_bench_periodo(s_ipca)
            
            # Benchmark IBOV (precisa de tratamento por ser Series de preços)
            v_ibov = 0
            if not df_ibov_c.empty:
                v_ibov = sum(valor_aporte * (df_ibov_c.iloc[-1] / df_ibov_c.asof(d)) for d in datas_aportes)

            # EXIBIÇÃO EM CARD ÚNICO DE DESTAQUE (Já que o período agora é customizado)
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown(f"""
                <div class="total-card">
                    <div class="total-label">Patrimônio Final</div>
                    <div class="total-amount">{formata_br(vf_ativo)}</div>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown(f"""
                <div class="info-card">
                    <div class="card-header">Análise da Carteira</div>
                    <div class="card-item">💵 <b>Capital Nominal:</b> {formata_br(capital_nominal)}</div>
                    <div class="card-item">📅 <b>Total de Aportes:</b> {len(datas_aportes)} meses</div>
                    <div class="card-destaque">💰 Lucro Acumulado: {formata_br(lucro_total)}</div>
                </div>
                """, unsafe_allow_html=True)

            with c2:
                st.markdown(f"""
                <div class="info-card" style="height: 100%;">
                    <div class="card-header">Comparativos (Mesmos Aportes no Período)</div>
                    <div class="card-item">🎯 <b>Se aplicado em CDI:</b> {formata_br(v_cdi)}</div>
                    <div class="card-item">📈 <b>Se aplicado em Ibovespa:</b> {formata_br(v_ibov)}</div>
                    <div class="card-item">🛡️ <b>Correção pela Inflação (IPCA):</b> {formata_br(v_ipca)}</div>
                    <p style="font-size: 0.8rem; color: #64748b; margin-top: 15px;">
                    * O cálculo de comparação assume que você faria o mesmo aporte de {formata_br(valor_aporte)} 
                    nos índices nas mesmas datas em que comprou a ação.
                    </p>
                </div>
                """, unsafe_allow_html=True)

        # Glossário (Mantido)
        st.markdown("""<div class="glossario-container">...</div>""", unsafe_allow_html=True)
    else: st.error("Ticker não encontrado.")
elif not ticker_input:
    st.info("💡 Digite um Ticker e defina o período inicial (seta azul) para calcular o patrimônio.")
