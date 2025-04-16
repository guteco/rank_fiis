# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import io
import json
import traceback
import os
import locale
from jinja2 import Environment, FileSystemLoader, select_autoescape # Para renderizar HTML
import html # Para escapar HTML (usado no template)
import plotly.express as px # Para gráficos
import streamlit.components.v1 as components # Para exibir HTML

# --- Configurar Locale e Jinja2 Environment ---
st.set_page_config(page_title="Ranking de FIIs", layout="wide")

LOCALE_CONFIGURED = False
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
    LOCALE_CONFIGURED = True
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil') # Fallback para Windows
        LOCALE_CONFIGURED = True
    except locale.Error:
        pass # Fallback manual na formatação

# Configura Jinja2
try:
    jinja_env = Environment(
        loader=FileSystemLoader('.'),
        autoescape=select_autoescape(['html', 'xml'])
    )
    jinja_env.get_template('fii_template.html')
    TEMPLATE_LOADED = True
except Exception as e_jinja:
    st.error(f"Erro Crítico: Não foi possível carregar o template Jinja2 'fii_template.html'.")
    st.error(f"Detalhe: {e_jinja}")
    TEMPLATE_LOADED = False
    # st.stop()

# --- Importar de rank_fiis ---
try:
    from rank_fiis import ( fetch_summary_data, process_data, URL_FII_LIST, FII_TYPES_JSON_FILE, carregar_tipos_do_json, SCRIPT_VERSION as RANK_FIIS_VERSION, FII_SEGMENT_DATA )
    RANK_FIIS_IMPORTED = True
    carregar_tipos_do_json(FII_TYPES_JSON_FILE)
except ImportError as e:
    st.error(f"Erro CRÍTICO ao importar 'rank_fiis'. Verifique se 'rank_fiis.py' está na pasta.")
    st.error(f"Path: {os.getcwd()}, Erro: {e}")
    st.stop()

# --- Constantes de Texto ---
DISCLAIMER_TEXT = """**AVISO IMPORTANTE:**\nEste script foi gerado somente para fins de estudo e análise pessoal.\nAs informações apresentadas **NÃO** constituem recomendação de compra ou venda de ativos financeiros.\nEsta é apenas uma ferramenta para auxiliar na sua própria análise e tomada de decisão.\n*Este script não pode ser vendido ou alterado sem autorização prévia dos autores.*\nQualquer dúvida ou sugestão, entre em contato."""
FOOTER_TEXT = f"""Script feito por Augusto Severo - [@guteco](https://www.instagram.com/guteco) e pela IA do Google.<br>Este trabalho foi carinhosamente pago com a promessa de excelentes pizzas! 🍕 - Versão App: {RANK_FIIS_VERSION} (rank_fiis)"""

# --- Título e Subtítulo ---
st.title("🏢 Ranking de Fundos Imobiliários (FIIs)")
st.markdown("Análise automatizada com dados do [Fundamentus](https://www.fundamentus.com.br/).")

# --- Funções Auxiliares para Formatação ---
def format_brl(value, decimals=0):
    if pd.isna(value): return "N/A"
    try:
        if LOCALE_CONFIGURED: num_str_locale = f"{float(value):n}";
        else: raise locale.Error
        if 'e' not in num_str_locale.lower():
             if decimals == 0:
                 if ',' in num_str_locale: return num_str_locale.split(',')[0]
                 else: return num_str_locale
             elif decimals > 0:
                 if ',' not in num_str_locale: return num_str_locale + ',' + '0' * decimals
                 else:
                     parts = num_str_locale.split(',')
                     if len(parts[1]) < decimals: parts[1] = parts[1].ljust(decimals, '0')
                     elif len(parts[1]) > decimals: parts[1] = parts[1][:decimals]
                     return parts[0] + ',' + parts[1]
             return num_str_locale
        raise locale.Error
    except (ValueError, TypeError, locale.Error):
         try:
             if decimals == 0: formatted_int = "{:,.0f}".format(float(value)).replace(',', '#').replace('.', ',').replace('#', '.'); return formatted_int
             else: formatted_float = "{:,.{prec}f}".format(float(value), prec=decimals).replace(',', '#').replace('.', ',').replace('#', '.'); return formatted_float
         except: return str(value)

def format_brl_cotacao(value):
    return format_brl(value, decimals=2)

def format_percent(value):
    if pd.isna(value): return "N/A"
    try: return f"{float(value) * 100:.2f}".replace('.', ',') + "%"
    except (ValueError, TypeError): return str(value)
# --- Fim Funções Formatação ---

# --- Sidebar com Filtros E Pesos ---
with st.sidebar:
    st.header("🔍 Filtros Principais")
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

    st.write("") # Espaço
    atualizar = st.button("🔄 Atualizar Ranking e Score", help="Buscar dados e calcular score com os pesos definidos.")
    st.write("") # Espaço

    st.divider()
    st.header("⚖️ Pesos do Score")
    st.caption("Defina a importância de cada critério (0 = ignora):")
    peso_pvp = st.slider("Peso P/VP (Menor é Melhor)", 0, 10, 7, key="peso_pvp", help="Importância dada a um P/VP baixo.")
    peso_dy = st.slider("Peso DY (Maior é Melhor)", 0, 10, 10, key="peso_dy", help="Importância dada a um Dividend Yield alto.")
    peso_liq = st.slider("Peso Liquidez (Maior é Melhor)", 0, 10, 3, key="peso_liq", help="Importância dada à liquidez diária.")
    peso_vac = st.slider("Peso Vacância (Menor é Melhor)", 0, 10, 2, key="peso_vac", help="Importância dada a uma baixa taxa de vacância.")
# --- Fim Sidebar ---

# --- Lógica Principal e Exibição ---
df_original_num = pd.DataFrame()
show_help_footer_disclaimer = True

if atualizar:
    with st.spinner("Buscando e processando dados... ⏳"):
        prog_bar = st.progress(0, text="Iniciando...")
        df = None
        error_occurred = False; error_message = ""
        try:
            import rank_fiis # Reimporta
            prog_bar.progress(5, text="Configurando filtros...")
            rank_fiis.MIN_PVP = min_pvp; rank_fiis.MAX_PVP = max_pvp
            rank_fiis.MIN_DY = min_dy_percent / 100.0; rank_fiis.MAX_DY = max_dy_percent / 100.0
            rank_fiis.MIN_LIQUIDEZ = min_liq

            prog_bar.progress(15, text="Buscando dados de resumo...")
            df_raw = fetch_summary_data(URL_FII_LIST)
            prog_bar.progress(30, text="Processando dados e buscando detalhes...")
            df = process_data(df_raw)
            prog_bar.progress(90, text="Finalizando processamento...")

        except Exception as e:
            error_occurred = True; error_message = f"Erro durante execução: {e}"
            st.error(error_message, icon="❌"); st.code(traceback.format_exc())
        finally:
            prog_bar.progress(100, text="Concluído!"); prog_bar.empty()

    if not error_occurred and df is not None:
        if not df.empty:
            st.success(f"{len(df)} FIIs encontrados após filtragem inicial.", icon="✅")
            df_original_num = df.copy()

            # CALCULAR SCORE PERSONALIZADO
            df_original_num['Score_Ponderado'] = 0
            max_rank = len(df_original_num) + 1
            if peso_pvp > 0 and 'Rank_PVP' in df_original_num.columns: df_original_num['Score_Ponderado'] += peso_pvp * df_original_num['Rank_PVP'].fillna(max_rank)
            if peso_dy > 0 and 'Rank_DY' in df_original_num.columns: df_original_num['Score_Ponderado'] += peso_dy * df_original_num['Rank_DY'].fillna(max_rank)
            if peso_liq > 0 and 'Rank_Liquidez' in df_original_num.columns: df_original_num['Score_Ponderado'] += peso_liq * df_original_num['Rank_Liquidez'].fillna(max_rank)
            if peso_vac > 0 and 'Rank_Vacancia' in df_original_num.columns: df_original_num['Score_Ponderado'] += peso_vac * df_original_num['Rank_Vacancia'].fillna(max_rank)
            df_original_num['Score_Ponderado'] = df_original_num['Score_Ponderado'].astype('Int64')

            # ORDENAR PELO SCORE
            df_original_num.sort_values(by='Score_Ponderado', ascending=True, inplace=True, na_position='last')

            df_display = df_original_num.copy()

            # Adicionar/Verificar colunas Tipo e Segmento
            if 'Tipo' not in df_display.columns:
                 if FII_SEGMENT_DATA: df_display['Tipo'] = df_display['Papel'].apply(lambda x: FII_SEGMENT_DATA.get(str(x), {}).get('tipo', 'Indefinido'))
                 else: df_display['Tipo'] = 'Indefinido'
            if 'Segmento' not in df_display.columns:
                if FII_SEGMENT_DATA: df_display['Segmento'] = df_display['Papel'].apply(lambda x: FII_SEGMENT_DATA.get(str(x), {}).get('segmento_original', 'Não Classificado'))
                else: df_display['Segmento'] = 'Não Classificado'
            if 'Segmento' not in df_display.columns: df_display['Segmento'] = 'Não Classificado'

            # AGREGAÇÃO DE SEGMENTOS
            segmento_industrial = "Imóveis Industriais e Logísticos"; segmento_logistica = "Logística"; segmentos_a_unir = [segmento_industrial, segmento_logistica]
            if any(seg in df_display['Segmento'].unique() for seg in segmentos_a_unir):
                replace_map = {seg: segmento_logistica for seg in segmentos_a_unir}
                df_display['Segmento'] = df_display['Segmento'].replace(replace_map)
                if 'Segmento' in df_original_num.columns: df_original_num['Segmento'] = df_original_num['Segmento'].replace(replace_map)

            # PREPARAÇÃO DE DADOS PARA O TEMPLATE JINJA2
            data_for_template = []
            cols_for_render = ['Papel', 'URL Detalhes', 'Segmento', 'Tipo', 'Cotação', 'Dividend Yield', 'P/VP', 'Liquidez', 'FFO Yield', 'Valor de Mercado', 'Qtd de imóveis', 'Vacância Média', 'Osc. Dia', 'Osc. Mês', 'Osc. 12 Meses', 'Data Último Relatório', 'Link Download Relatório', 'Link Documentos FNET']
            cols_present = [col for col in cols_for_render if col in df_display.columns]
            df_subset = df_display[cols_present]

            for idx, row in df_subset.iterrows():
                fii_data = {}
                for col in cols_present: fii_data[col] = row[col]
                # Formatação
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
                fii_data['Link Download Relatório'] = fii_data.get('Link Download Relatório')
                fii_data['Link_FNET'] = fii_data.get('Link Documentos FNET')
                data_for_template.append(fii_data)

            # --- Exibição da Tabela HTML ---
            segmentos_brutos = sorted(df_display['Segmento'].dropna().unique()) if 'Segmento' in df_display.columns else []
            segmentos_ordenados = sorted([s for s in segmentos_brutos if s != 'Outros' and s != 'Não Classificado']);
            if 'Não Classificado' in segmentos_brutos: segmentos_ordenados.append('Não Classificado')
            if 'Outros' in segmentos_brutos: segmentos_ordenados.append('Outros')
            table_height = min(max(len(data_for_template) * 38 + 60, 250), 700)

            if len(segmentos_ordenados) > 0 and TEMPLATE_LOADED:
                st.write("---"); st.subheader("Resultados por Segmento")
                tabs = st.tabs(["🏆 Todos"] + segmentos_ordenados)
                template = jinja_env.get_template('fii_template.html')
                with tabs[0]:
                    html_table = template.render(fiis=data_for_template)
                    components.html(html_table, height=table_height, scrolling=True)
                for i, seg in enumerate(segmentos_ordenados):
                    with tabs[i+1]:
                        data_seg = [fii for fii in data_for_template if fii.get('Segmento') == seg]
                        html_table_seg = template.render(fiis=data_seg)
                        seg_table_height = min(max(len(data_seg) * 38 + 60, 200), 700)
                        components.html(html_table_seg, height=seg_table_height, scrolling=True)
            elif TEMPLATE_LOADED:
                st.write("---"); st.subheader("Resultados")
                template = jinja_env.get_template('fii_template.html')
                html_table = template.render(fiis=data_for_template);
                components.html(html_table, height=table_height, scrolling=True)
            elif not TEMPLATE_LOADED:
                 st.error("Template HTML não carregado. Não é possível exibir a tabela.")
            # --- Fim Exibição Tabela HTML ---

            # --- Download Excel MOVIDO PARA CÁ ---
            st.write("") # Adiciona um pequeno espaço vertical
            output = io.BytesIO();
            cols_to_drop_excel = ['URL Detalhes']
            df_excel = df_original_num.drop(columns=[col for col in cols_to_drop_excel if col in df_original_num.columns], errors='ignore')
            df_excel.rename(columns={ 'Rank_PVP': 'Rank P/VP (Menor Melhor)', 'Rank_DY': 'Rank DY (Maior Melhor)', 'Rank_Liquidez': 'Rank Liquidez (Maior Melhor)', 'Rank_Vacancia': 'Rank Vacancia (Menor Melhor)', 'Score_Ponderado': 'Score Personalizado (Menor Melhor)' }, inplace=True)
            try:
                # --- Bloco de Geração do Excel CORRIGIDO --- <--- CORREÇÃO INDENTAÇÃO
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_excel.to_excel(writer, index=False, sheet_name='Ranking FIIs')
                # Agora `output` contém os dados do Excel
                st.download_button(
                    label="📥 Baixar Tabela Completa (Excel)",
                    data=output.getvalue(), # Pega os bytes do buffer após salvar
                    file_name="ranking_fiis_completo.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_excel_button_main" # Chave única
                )
                # --- Fim Bloco Corrigido ---

            except Exception as e:
                st.error(f"Erro ao gerar Excel: {e}", icon="❌")
            # --- Fim Download Excel ---

            # --- SEÇÃO DE GRÁFICOS ---
            st.write("---"); st.subheader("📊 Visualizações Gráficas") # Divisor antes dos gráficos
            if df_original_num is not None and not df_original_num.empty:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("##### Distribuição por Segmento")
                    if 'Segmento' in df_original_num.columns:
                        segment_counts = df_original_num['Segmento'].value_counts()
                        if not segment_counts.empty: st.bar_chart(segment_counts)
                        else: st.caption("Sem dados de segmento.")
                    else: st.caption("Coluna 'Segmento' ausente.")
                with col2:
                    st.markdown("##### DY (%) vs P/VP")
                    required_cols_scatter = {'Dividend Yield', 'P/VP', 'Segmento', 'Papel'}
                    if required_cols_scatter.issubset(df_original_num.columns):
                        df_scatter = df_original_num.dropna(subset=['P/VP', 'Dividend Yield']).copy()
                        if not df_scatter.empty:
                            df_scatter['DY_Percent'] = df_scatter['Dividend Yield'] * 100
                            fig = px.scatter(df_scatter, x='P/VP', y='DY_Percent', color='Segmento', hover_name='Papel', hover_data={'Segmento': True, 'DY_Percent': ':.2f%', 'P/VP': ':.2f'}, labels={'DY_Percent': 'Dividend Yield (%)', 'P/VP': 'P/VP'})
                            fig.update_layout(yaxis_tickformat='.0f%', legend_title_text='Segmento', margin=dict(l=20, r=20, t=30, b=20))
                            st.plotly_chart(fig, use_container_width=True)
                        else: st.caption("Nenhum dado válido (DY/PVP) para exibir.")
                    else: missing_cols = required_cols_scatter - set(df_original_num.columns); st.caption(f"Dados insuficientes ({', '.join(missing_cols)}).")
            else: st.caption("Nenhum FII encontrado para gerar gráficos.")
            # --- FIM SEÇÃO DE GRÁFICOS ---

        else:
            st.warning("Nenhum FII encontrado com os filtros aplicados.", icon="🚫")

else:
    st.info("⬅️ Configure filtros e pesos na barra lateral, depois clique '🔄 Atualizar'.", icon="💡");
    show_help_footer_disclaimer = True

# --- Seção de Ajuda Expansível, Disclaimer e Footer ---
if show_help_footer_disclaimer:
    st.divider()
    with st.expander("ℹ️ Sobre este App / Ajuda"):
         st.markdown("""
**Fonte dos Dados:**
*   Dados principais (cotação, P/VP, DY, liquidez, etc.) e link para último relatório são coletados do site [Fundamentus](https://www.fundamentus.com.br/).
*   Classificação de **Segmento** e **Tipo** (Tijolo, Papel, Híbrido, etc.) utiliza um arquivo JSON externo (`fii_types.json`) como base, podendo ser complementada ou sobreposta pelos dados do Fundamentus se o JSON não definir.
*   Link **Docs FNET** direciona para a página oficial de documentos do fundo na B3/FNET, extraído da página de detalhes do Fundamentus.

**Score Personalizado e Filtros:**
*   Use os **filtros** na barra lateral para definir os critérios mínimos e máximos (P/VP, DY, Liquidez) que um FII deve atender para aparecer na lista.
*   Clique **"🔄 Atualizar Ranking e Score"** para buscar os dados e aplicar os filtros.
*   Use os **pesos** na barra lateral para definir a importância de cada indicador no cálculo do **Score Personalizado**.
*   A tabela é ordenada pelo **Score Personalizado (menor = melhor)**.
*   ⚠️ **ESSENCIAL:** O score é uma ferramenta **quantitativa**. **Sempre leia os relatórios gerenciais** e faça sua própria análise.

**Principais Indicadores (Tooltips na tabela HTML):**
*   **DY:** Dividend Yield 12 meses.
*   **P/VP:** Preço / Valor Patrimonial.
*   **Liquidez:** Volume médio diário negociado (R$).
*   **Vacância:** Taxa média de vacância reportada.
*   **FFO Yield:** Funds From Operations Yield.
*   **Oscilações:** Variação da cotação.

**Classificação por Segmento/Tipo:**
*   Utiliza `fii_types.json` e dados do Fundamentus. Pode conter imprecisões. Informe erros: `contato@nerdpobre.com`.

**Como Usar:**
1.  Ajuste os **Filtros Principais**.
2.  Clique **"🔄 Atualizar Ranking e Score"**.
3.  Ajuste os **Pesos do Score** (o score recalcula na tabela exibida).
4.  Navegue pelos resultados na tabela (use abas para ver por segmento).
5.  Use os links nas colunas **Papel**, **Relatório**, **Docs FNET**.
6.  Baixe a tabela completa clicando no botão **"📥 Baixar Tabela Completa (Excel)"** abaixo da tabela.

**Limitações:**
*   Estudo, **não** recomendação. Dados dependem do Fundamentus/JSON. Performance pode variar. Faça sua Due Diligence.
        """, unsafe_allow_html=True)
    st.warning(DISCLAIMER_TEXT, icon="⚠️"); st.caption(FOOTER_TEXT, unsafe_allow_html=True)