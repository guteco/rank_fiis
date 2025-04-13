# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import io
import json
import traceback
import os
import locale
from jinja2 import Environment, FileSystemLoader, select_autoescape
import html
import plotly.express as px
import streamlit.components.v1 as components # Necessário para renderizar HTML

# --- Configurar Locale e Jinja2 Environment ---
st.set_page_config(page_title="Ranking de FIIs", layout="wide")
LOCALE_CONFIGURED = False
try: locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    try: locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil')
    except locale.Error: pass
else: LOCALE_CONFIGURED = True
jinja_env = Environment(loader=FileSystemLoader('.'), autoescape=select_autoescape(['html', 'xml']))
# --- Fim Configurações Iniciais ---

# --- Importar de rank_fiis ---
try:
    from rank_fiis import ( fetch_summary_data, process_data, URL_FII_LIST, FII_TYPES_JSON_FILE, carregar_tipos_do_json, SCRIPT_VERSION, FII_SEGMENT_DATA )
    RANK_FIIS_IMPORTED = True; carregar_tipos_do_json(FII_TYPES_JSON_FILE)
except ImportError as e: st.error(f"Erro CRÍTICO ao importar 'rank_fiis'."); st.error(f"Path: {os.getcwd()}, Erro: {e}"); st.stop()

# --- Constantes de Texto ---
DISCLAIMER_TEXT = """**AVISO IMPORTANTE:**\nEste script foi gerado somente para fins de estudo e análise pessoal.\nAs informações apresentadas **NÃO** constituem recomendação de compra ou venda de ativos financeiros.\nEsta é apenas uma ferramenta para auxiliar na sua própria análise e tomada de decisão.\n*Este script não pode ser vendido ou alterado sem autorização prévia dos autores.*\nQualquer dúvida ou sugestão, entre em contato."""
FOOTER_TEXT = f"""Script feito por Augusto Severo - [@guteco](https://www.instagram.com/guteco) e pela IA do Google.<br>Este trabalho foi carinhosamente pago com a promessa de excelentes pizzas! 🍕 - Versão App: {SCRIPT_VERSION} (rank_fiis)"""
# --- Fim Constantes ---

# --- Título e Subtítulo ---
st.title("🏢 Ranking de Fundos Imobiliários (FIIs)")
st.markdown("Análise automatizada com dados do [Fundamentus](https://www.fundamentus.com.br/).")

# --- Aviso sobre Locale ---
if not LOCALE_CONFIGURED:
    st.warning("Locale 'pt_BR' não encontrado. Formatação de moeda pode usar fallback.", icon="⚠️")

# --- Funções Auxiliares para Formatação ---
def format_brl(value, decimals=0):
    if pd.isna(value): return "N/A"
    try:
        if LOCALE_CONFIGURED: num_str_locale = f"{float(value):n}";
        else: raise locale.Error
        if 'e' not in num_str_locale.lower():
             if decimals == 0 and ',' in num_str_locale: return num_str_locale.split(',')[0]
             elif decimals > 0 and ',' not in num_str_locale: return num_str_locale + ',00'
             return num_str_locale
        raise locale.Error
    except (ValueError, TypeError, locale.Error):
         try:
             if decimals == 0: formatted_int = "{:,.0f}".format(float(value)).replace(',', '#').replace('.', ',').replace('#', '.'); return formatted_int
             else: formatted_float = "{:,.{prec}f}".format(float(value), prec=decimals).replace(',', '#').replace('.', ',').replace('#', '.'); return formatted_float
         except: return str(value)
def format_brl_cotacao(value): return format_brl(value, decimals=2)
def format_percent(value):
    if pd.isna(value): return "N/A"
    try: return f"{float(value) * 100:.2f}".replace('.', ',') + "%"
    except (ValueError, TypeError): return str(value)
# --- Fim Funções Formatação ---

# --- Sidebar com Filtros ---
with st.sidebar:
    st.header("🔍 Filtros");
    try: from rank_fiis import MIN_PVP as DEFAULT_MIN_PVP, MAX_PVP as DEFAULT_MAX_PVP, MIN_DY as DEFAULT_MIN_DY, MAX_DY as DEFAULT_MAX_DY, MIN_LIQUIDEZ as DEFAULT_MIN_LIQ
    except ImportError: DEFAULT_MIN_PVP=0.7; DEFAULT_MAX_PVP=1.05; DEFAULT_MIN_DY=0.08; DEFAULT_MAX_DY=0.135; DEFAULT_MIN_LIQ=400000; st.warning("Constantes de filtro padrão não encontradas.", icon="⚠️")
    DEFAULT_MIN_DY_PERCENT = DEFAULT_MIN_DY * 100; DEFAULT_MAX_DY_PERCENT = DEFAULT_MAX_DY * 100
    min_pvp = st.slider("P/VP mínimo", 0.0, 2.5, DEFAULT_MIN_PVP, 0.01, key="min_pvp", help="Preço/Valor Patrimonial mínimo.")
    max_pvp = st.slider("P/VP máximo", 0.0, 2.5, DEFAULT_MAX_PVP, 0.01, key="max_pvp", help="Preço/Valor Patrimonial máximo.")
    min_dy_percent = st.slider("DY mínimo (%)", 0.0, 25.0, DEFAULT_MIN_DY_PERCENT, 0.1, key="min_dy", help="Dividend Yield mínimo anualizado (%).")
    max_dy_percent = st.slider("DY máximo (%)", 0.0, 25.0, DEFAULT_MAX_DY_PERCENT, 0.1, key="max_dy", help="Dividend Yield máximo anualizado (%).")
    min_liq = st.number_input("Liquidez mínima (R$)", min_value=0, value=DEFAULT_MIN_LIQ, step=10000, key="min_liq", help="Volume financeiro médio negociado por dia (R$).")
    if min_pvp > max_pvp: st.warning("P/VP mínimo > P/VP máximo.")
    if min_dy_percent > max_dy_percent: st.warning("DY mínimo > DY máximo.")
    atualizar = st.button("🔄 Atualizar Ranking", help="Buscar dados com os filtros.")
# --- Fim Sidebar ---

# --- Lógica Principal e Exibição ---
df_original_num = pd.DataFrame()
show_help_footer_disclaimer = True

if atualizar:
    with st.spinner("Buscando e processando dados... ⏳"):
        prog_bar = st.progress(0, text="Iniciando..."); df = None; error_occurred = False; error_message = ""
        try:
            import rank_fiis; prog_bar.progress(5, text="Configurando filtros...")
            rank_fiis.MIN_PVP = min_pvp; rank_fiis.MAX_PVP = max_pvp; rank_fiis.MIN_DY = min_dy_percent / 100.0; rank_fiis.MAX_DY = max_dy_percent / 100.0; rank_fiis.MIN_LIQUIDEZ = min_liq
            prog_bar.progress(15, text="Buscando dados de resumo...")
            df_raw = fetch_summary_data(URL_FII_LIST); prog_bar.progress(30, text="Processando dados e detalhes...")
            df = process_data(df_raw); prog_bar.progress(90, text="Finalizando...")
        except Exception as e: error_occurred = True; error_message = f"Erro: {e}"; st.error(error_message, icon="❌"); st.code(traceback.format_exc())
        finally: prog_bar.progress(100, text="Concluído!"); prog_bar.empty()

    if not error_occurred and df is not None:
        if not df.empty:
            st.success(f"{len(df)} FIIs encontrados após filtragem.", icon="✅")
            df_original_num = df.copy(); df_display = df.copy()
            if 'Tipo' not in df_display.columns:
                if rank_fiis.FII_SEGMENT_DATA: df_display['Tipo'] = df_display['Papel'].apply(lambda x: rank_fiis.FII_SEGMENT_DATA.get(str(x), {}).get('tipo', 'Indefinido'))
                else: df_display['Tipo'] = 'Indefinido'
            if 'Segmento' not in df_display.columns: df_display['Segmento'] = "N/A"

            # AGREGAÇÃO DE SEGMENTOS
            segmento_industrial = "Imóveis Industriais e Logísticos"; segmento_logistica = "Logística"; segmentos_a_unir = [segmento_industrial, segmento_logistica]
            if any(seg in df_display['Segmento'].unique() for seg in segmentos_a_unir):
                replace_map = {seg: segmento_logistica for seg in segmentos_a_unir}; df_display['Segmento'] = df_display['Segmento'].replace(replace_map)
                df_original_num['Segmento'] = df_original_num['Segmento'].replace(replace_map)

            # PREPARAÇÃO DE DADOS PARA O TEMPLATE JINJA2
            data_for_template = []
            cols_for_render = ['Papel', 'URL Detalhes', 'Segmento', 'Tipo', 'Cotação', 'Dividend Yield', 'P/VP', 'Liquidez', 'FFO Yield', 'Valor de Mercado', 'Qtd de imóveis', 'Vacância Média', 'Osc. Dia', 'Osc. Mês', 'Osc. 12 Meses', 'Data Último Relatório', 'Link Download Relatório']
            cols_present = [col for col in cols_for_render if col in df_display.columns]
            df_subset = df_display[cols_present]
            for _, row in df_subset.iterrows():
                fii_data = row.to_dict()
                fii_data['Cotação_fmt'] = "R$ " + format_brl_cotacao(fii_data.get('Cotação'))
                fii_data['DY_fmt'] = format_percent(fii_data.get('Dividend Yield'))
                fii_data['PVP_fmt'] = f"{fii_data.get('P/VP'):.2f}".replace('.', ',') if pd.notna(fii_data.get('P/VP')) else "N/A"
                fii_data['Liquidez_fmt'] = "R$ " + format_brl(fii_data.get('Liquidez'), decimals=0)
                fii_data['FFOYield_fmt'] = format_percent(fii_data.get('FFO Yield'))
                fii_data['ValorMercado_fmt'] = "R$ " + format_brl(fii_data.get('Valor de Mercado'), decimals=0)
                fii_data['QtdImoveis_fmt'] = format_brl(fii_data.get('Qtd de imóveis'), decimals=0) if pd.notna(fii_data.get('Qtd de imóveis')) else "N/A"
                fii_data['Vacancia_fmt'] = format_percent(fii_data.get('Vacância Média'))
                fii_data['OscDia_fmt'] = format_percent(fii_data.get('Osc. Dia'))
                fii_data['OscMes_fmt'] = format_percent(fii_data.get('Osc. Mês'))
                fii_data['Osc12M_fmt'] = format_percent(fii_data.get('Osc. 12 Meses'))
                fii_data['Segmento'] = fii_data.get('Segmento', 'N/A')
                fii_data['Tipo'] = fii_data.get('Tipo', 'N/A')
                fii_data['Data Último Relatório'] = fii_data.get('Data Último Relatório', 'N/A')
                data_for_template.append(fii_data)

            # Exibição da Tabela HTML com st.components.v1.html
            segmentos_brutos = sorted(df_display['Segmento'].unique());
            segmentos_ordenados = sorted([s for s in segmentos_brutos if s != 'Outros']);
            if 'Outros' in segmentos_brutos: segmentos_ordenados.append('Outros')
            table_height = min(max(len(data_for_template) * 38 + 60, 250), 700) # Aumentei um pouco a altura por linha/min/max

            if len(segmentos_ordenados) > 0:
                st.write("---"); st.subheader("Resultados por Segmento")
                tabs = st.tabs(["🏆 Todos"] + segmentos_ordenados)
                try: template = jinja_env.get_template('fii_template.html')
                except Exception as e_template: st.error(f"Erro ao carregar 'fii_template.html': {e_template}"); template = None
                if template:
                    with tabs[0]:
                        html_table = template.render(fiis=data_for_template)
                        components.html(html_table, height=table_height, scrolling=True) # Usa components.html
                    for i, seg in enumerate(segmentos_ordenados):
                        with tabs[i+1]:
                            data_seg = [fii for fii in data_for_template if fii['Segmento'] == seg]
                            html_table_seg = template.render(fiis=data_seg)
                            seg_table_height = min(max(len(data_seg) * 38 + 60, 200), 700) # Altura dinâmica
                            components.html(html_table_seg, height=seg_table_height, scrolling=True) # Usa components.html
            else:
                st.write("---"); st.subheader("Resultados")
                try: template = jinja_env.get_template('fii_template.html')
                except Exception as e_template: st.error(f"Erro ao carregar 'fii_template.html': {e_template}"); template = None
                if template: html_table = template.render(fiis=data_for_template); components.html(html_table, height=table_height, scrolling=True) # Usa components.html

            # --- SEÇÃO DE GRÁFICOS ---
            st.write("---") # Linha divisória
            st.subheader("📊 Visualizações Gráficas")

            # Verificação inicial se há dados no DataFrame numérico
            if df_original_num is not None and not df_original_num.empty:
                col1, col2 = st.columns(2) # Criar colunas para layout

                # --- Gráfico 1: Distribuição por Segmento (na col1) ---
                with col1:
                    st.markdown("##### Distribuição por Segmento")
                    # Checa a existência da coluna 'Segmento'
                    if 'Segmento' in df_original_num.columns:
                        segment_counts = df_original_num['Segmento'].value_counts()
                        # Checa se a contagem resultou em algo
                        if not segment_counts.empty:
                            st.bar_chart(segment_counts)
                        else:
                            # Segmento existe, mas não há FIIs ou a contagem falhou
                            st.caption("Não há dados de segmento para exibir.")
                    else:
                        # Coluna 'Segmento' não foi encontrada no DataFrame
                        st.caption("Coluna 'Segmento' ausente nos dados.") # Mensagem clara

                # --- Gráfico 2: Scatter Plot DY vs P/VP (na col2) ---
                with col2:
                    st.markdown("##### DY (%) vs P/VP")
                    # Define colunas necessárias
                    required_cols_scatter = {'Dividend Yield', 'P/VP', 'Segmento', 'Papel'}
                    # Checa se todas existem
                    if required_cols_scatter.issubset(df_original_num.columns):
                        # Prepara dados: remove NaN de P/VP e DY, cria DY_Percent
                        df_scatter = df_original_num.dropna(subset=['P/VP', 'Dividend Yield']).copy()
                        if not df_scatter.empty: # Verifica se sobrou algo após remover NaN
                            df_scatter['DY_Percent'] = df_scatter['Dividend Yield'] * 100
                            # Cria o gráfico Plotly
                            fig = px.scatter(
                                df_scatter,
                                x='P/VP',
                                y='DY_Percent',
                                color='Segmento',
                                hover_name='Papel',
                                hover_data={'Segmento': True, 'DY_Percent': ':.2f%', 'P/VP': ':.2f'},
                                labels={'DY_Percent': 'Dividend Yield (%)', 'P/VP': 'P/VP'}
                            )
                            fig.update_layout(yaxis_tickformat='.0f%', legend_title_text='Segmento', margin=dict(l=20, r=20, t=30, b=20))
                            st.plotly_chart(fig, use_container_width=True) # Exibe o gráfico
                        else:
                            # Havia as colunas, mas após remover NaN, ficou vazio
                            st.caption("Nenhum dado válido (DY/PVP não nulos) para exibir.")
                    else:
                        # Alguma coluna necessária para o gráfico não existe
                        missing_cols = required_cols_scatter - set(df_original_num.columns)
                        st.caption(f"Dados insuficientes. Colunas faltando: {', '.join(missing_cols)}")

            else:
                # Caso o df_original_num esteja vazio ou seja None
                st.caption("Nenhum FII encontrado nos resultados para gerar gráficos.")
            # --- FIM SEÇÃO DE GRÁFICOS ---
            # Download Excel (Mantido)
            st.write("---"); output = io.BytesIO(); df_excel = df_original_num.drop(columns=['URL Detalhes'], errors='ignore')
            try:
                with pd.ExcelWriter(output, engine='openpyxl') as writer: df_excel.to_excel(writer, index=False, sheet_name='Ranking FIIs')
                st.download_button(label="📥 Baixar Tabela (Excel)", data=output.getvalue(), file_name="ranking_fiis.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception as e: st.error(f"Erro ao gerar Excel: {e}", icon="❌")

        else: st.warning("Nenhum FII encontrado.", icon="🚫")
else: st.info("⬅️ Configure filtros e clique '🔄 Atualizar Ranking'.", icon="💡"); show_help_footer_disclaimer = True

# --- Seção de Ajuda Expansível, Disclaimer e Footer ---
# (Mantida como na versão anterior)
# --- Seção de Ajuda Expansível, Disclaimer e Footer ---
if show_help_footer_disclaimer:
    st.divider()
    with st.expander("ℹ️ Sobre este App / Ajuda"):
        st.markdown("""
            **Fonte dos Dados:**
            *   Dados coletados do site [Fundamentus](https://www.fundamentus.com.br/). A coleta pode levar um tempo.
            *   A atualização e precisão dependem da fonte. Não são dados em tempo real.

            **Objetivo da Ferramenta e Indicadores Chave:**
            *   Este aplicativo visa facilitar a **identificação inicial** de Fundos Imobiliários (FIIs) que se encaixam em certos critérios quantitativos populares entre investidores, focando em um aparente **custo/benefício**.
            *   Os principais filtros utilizados são:
                *   **P/VP (Preço / Valor Patrimonial):** Compara o preço de mercado da cota com o valor patrimonial por cota informado pelo fundo. Um P/VP **abaixo de 1.0** *pode sugerir* que o mercado está negociando o FII abaixo do seu valor contábil, indicando um possível "desconto" (custo relativo menor). Filtramos por uma faixa de P/VP que você define.
                *   **DY (Dividend Yield):** Mede o percentual de rendimentos distribuídos nos últimos 12 meses em relação ao preço atual da cota. Um DY **mais alto** representa um maior retorno recente via dividendos (benefício recente maior). Filtramos por uma faixa de DY que você define.
                *   **Liquidez:** Volume médio de negociação diária. Filtramos por um valor mínimo para buscar garantir que o FII tenha negociações suficientes para facilitar a compra e venda de cotas.
            *   Ao aplicar esses filtros, a ferramenta apresenta uma lista de FIIs que atendem, *numericamente*, aos seus critérios.
            *   ⚠️ **ESSENCIAL: Vá Além dos Números!** Os indicadores são importantes, mas são apenas uma fotografia do momento e não contam toda a história. Um P/VP baixo pode indicar problemas no fundo, e um DY alto pode não ser sustentável. **É fundamental que você faça sua própria diligência:**
                *   **Leia os Relatórios Gerenciais:** Entenda a estratégia, os ativos (imóveis ou papéis), a qualidade dos inquilinos/devedores, a situação da vacância e os planos futuros da gestão.
                *   **Analise a Gestão:** Pesquise sobre a experiência e o histórico da equipe gestora.
                *   **Considere os Riscos:** Avalie os riscos específicos do segmento, dos ativos e do próprio mercado.
            *   Use esta ferramenta como um **ponto de partida** para sua pesquisa, não como uma recomendação final. A decisão de investir é pessoal e exige análise aprofundada.

            **Classificação por Segmento/Tipo:**
            *   A classificação ("Tijolo", "Papel", "Híbrido", etc.) busca categorizar os FIIs com base em dados externos para facilitar a análise.
            *   Essa classificação pode conter erros ou estar desatualizada. Se encontrar algo incorreto, agradecemos o contato: `contato@nerdpobre.com`

            **Como Usar:**
            1.  Ajuste os filtros (P/VP, DY, Liquidez) na barra lateral.
            2.  Clique "Atualizar Ranking".
            3.  Navegue pelos resultados nas abas.
            4.  Use os links para Fundamentus e Relatórios.
            5.  Baixe o Excel para análise offline.

            **Limitações:**
            *   Ferramenta de estudo, **não** recomendação.
            *   Depende da fonte Fundamentus.
            *   Scraping pode falhar.
        """, unsafe_allow_html=True) # unsafe_allow_html para <br> no footer

    st.warning(DISCLAIMER_TEXT, icon="⚠️") # Disclaimer como warning
    st.caption(FOOTER_TEXT, unsafe_allow_html=True) # Footer
