# 4. LOGICA PRINCIPAL
if ticker_input:
    df_acao = carregar_dados_completos(ticker_input)
    
    if df_acao is not None:
        # Criamos o container do gráfico primeiro
        df_v = df_acao.loc[pd.to_datetime(data_inicio):pd.to_datetime(data_fim)].copy()
        
        if not df_v.empty:
            df_v["Total_Fact_Chart"] = df_v["Total_Fact"] / df_v["Total_Fact"].iloc[0]
            df_v["Price_Base_Chart"] = df_v["Close"] / df_v["Close"].iloc[0]
            
            fig = go.Figure()
            
            # 1. ADICIONAMOS OS COMPARATIVOS PRIMEIRO (Para garantir que fiquem no fundo)
            if mostrar_cdi:
                with st.spinner('Buscando CDI atualizado...'):
                    s_cdi = busca_indice_bcb(12, data_inicio, data_fim)
                    if not s_cdi.empty:
                        # Garantimos que o índice do CDI esteja alinhado com o da ação
                        fig.add_trace(go.Scatter(x=s_cdi.index, y=(s_cdi/s_cdi.iloc[0]-1)*100, 
                                               name='CDI', line=dict(color='gray', width=2, dash='dash')))

            if mostrar_ipca:
                s_ipca = busca_indice_bcb(433, data_inicio, data_fim)
                if not s_ipca.empty:
                    fig.add_trace(go.Scatter(x=s_ipca.index, y=(s_ipca/s_ipca.iloc[0]-1)*100, 
                                           name='IPCA', line=dict(color='red', width=2)))

            if mostrar_ibov:
                try:
                    ibov = yf.download("^BVSP", start=data_inicio, end=data_fim, progress=False)
                    if isinstance(ibov.columns, pd.MultiIndex): ibov.columns = ibov.columns.get_level_values(0)
                    ibov_c = ibov['Close']
                    fig.add_trace(go.Scatter(x=ibov_c.index, y=(ibov_c/ibov_c.iloc[0]-1)*100, 
                                           name='Ibovespa', line=dict(color='orange', width=2)))
                except: pass

            # 2. ADICIONAMOS A AÇÃO POR CIMA (Para destaque visual)
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Price_Base_Chart"]-1)*100, 
                                   stackgroup='one', name='Valorização', 
                                   fillcolor='rgba(31, 119, 180, 0.4)', line=dict(width=0)))
            
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-df_v["Price_Base_Chart"])*100, 
                                   stackgroup='one', name='Dividendos', 
                                   fillcolor='rgba(218, 165, 32, 0.4)', line=dict(width=0)))
            
            fig.add_trace(go.Scatter(x=df_v.index, y=(df_v["Total_Fact_Chart"]-1)*100, 
                                   name='RETORNO TOTAL', line=dict(color='black', width=3)))

            # 3. ATUALIZAÇÃO DO LAYOUT
            fig.update_layout(template="plotly_white", hovermode="x unified", 
                            yaxis=dict(side="right", ticksuffix="%"), 
                            margin=dict(l=20, r=20, t=50, b=20), 
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
            
            st.plotly_chart(fig, use_container_width=True)
