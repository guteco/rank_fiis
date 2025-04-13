# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import io
import json
import traceback
import os
import locale

# --- Configurar Locale ---
try: locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    try: locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil')
    except locale.Error: st.warning("Locale 'pt_BR' não encontrado.", icon="⚠️") # Warning é ok aqui
# --- Fim Locale ---

# --- Importar de rank_fiis ---
# st.set_page_config deve ser o primeiro comando Streamlit
st.set_page_config(page_title="Ranking de FIIs", layout="wide")
try:
    from rank_fiis import ( fetch_summary_data, process_data, URL_FII_LIST, FII_TYPES_JSON_FILE, carregar_tipos_do_json, SCRIPT_VERSION, FII_SEGMENT_DATA )
    RANK_FIIS_IMPORTED = True; carregar_tipos_do_json(FII_TYPES_JSON_FILE)
except ImportError as e: st.error(f"Erro CRÍTICO ao importar 'rank_fiis'."); st.error(f"Path: {os.getcwd()}, Erro: {e}"); st.stop()

# --- Constantes de Texto ---
DISCLAIMER_TEXT = """**AVISO IMPORTANTE:**\nEste script foi gerado somente para fins de estudo e análise pessoal.\nAs informações apresentadas **NÃO** constituem recomendação de compra ou venda de ativos financeiros.\nEsta é apenas uma ferramenta para auxiliar na sua própria análise e tomada de decisão.\n*Este script não pode ser vendido ou alterado sem autorização prévia dos autores.*\nQualquer dúvida ou sugestão, entre em contato."""
FOOTER_TEXT = f"""Script feito por Augusto Severo - [@guteco](https://www.instagram.com/guteco) e pela IA do Google.<br>Este trabalho foi carinhosamente pago com a promessa de excelentes pizzas! 🍕 - Versão App: {SCRIPT_VERSION} (rank_fiis)"""
# --- Fim Constantes ---

# Título e Subtítulo
st.title("🏢 Ranking de Fundos Imobiliários (FIIs)")
st.markdown("Análise automatizada com dados do [Fundamentus](https://www.fundamentus.com.br/).")

# --- Funções Auxiliares para Formatação ---
def format_brl(value, decimals=0):
    if pd.isna(value): return "N/A"
    try: num_str_locale = f"{float(value):n}";
    except (ValueError, TypeError, locale.Error): num_str_locale = 'e' # Força fallback se locale falhar
    try:
        if 'e' not in num_str_locale.lower():
             if decimals == 0 and ',' in num_str_locale: return num_str_locale.split(',')[0]
             elif decimals > 0 and ',' not in num_str_locale: return num_str_locale + ',00'
             return num_str_locale
        if decimals == 0: formatted_int = "{:,.0f}".format(float(value)).replace(',', '#').replace('.', ',').replace('#', '.'); return formatted_int
        else: formatted_float = "{:,.{prec}f}".format(float(value), prec=decimals).replace(',', '#').replace('.', ',').replace('#', '.'); return formatted_float
    except (ValueError, TypeError): return str(value)
def format_brl_cotacao(value): return format_brl(value, decimals=2)
def format_percent(value):
    if pd.isna(value): return "N/A"
    try: return f"{float(value) * 100:.2f}".replace('.', ',') + "%"
    except (ValueError, TypeError): return str(value)
# --- Fim Funções Formatação ---

# --- Sidebar com Filtros e AJUDA ---
with st.sidebar:
    st.header("🔍 Filtros")
    try: from rank_fiis import MIN_PVP as DEFAULT_MIN_PVP, MAX_PVP as DEFAULT_MAX_PVP, MIN_DY as DEFAULT_MIN_DY, MAX_DY as DEFAULT_MAX_DY, MIN_LIQUIDEZ as DEFAULT_MIN_LIQ
    except ImportError: DEFAULT_MIN_PVP=0.7; DEFAULT_MAX_PVP=1.05; DEFAULT_MIN_DY=0.08; DEFAULT_MAX_DY=0.135; DEFAULT_MIN_LIQ=400000; st.warning("Constantes de filtro padrão não encontradas.", icon="⚠️")
    DEFAULT_MIN_DY_PERCENT = DEFAULT_MIN_DY * 100; DEFAULT_MAX_DY_PERCENT = DEFAULT_MAX_DY * 100

    # Adicionando 'help' aos widgets
    min_pvp = st.slider("P/VP mínimo", 0.0, 2.5, DEFAULT_MIN_PVP, 0.01, key="min_pvp",
                        help="Preço/Valor Patrimonial mínimo desejado. Valores < 1 podem indicar FII 'descontado'.")
    max_pvp = st.slider("P/VP máximo", 0.0, 2.5, DEFAULT_MAX_PVP, 0.01, key="max_pvp",
                        help="Preço/Valor Patrimonial máximo desejado.")
    min_dy_percent = st.slider("DY mínimo (%)", 0.0, 25.0, DEFAULT_MIN_DY_PERCENT, 0.1, key="min_dy",
                               help="Dividend Yield mínimo anualizado desejado (%).")
    max_dy_percent = st.slider("DY máximo (%)", 0.0, 25.0, DEFAULT_MAX_DY_PERCENT, 0.1, key="max_dy",
                               help="Dividend Yield máximo anualizado desejado (%). Cuidado com DYs muito altos.")
    min_liq = st.number_input("Liquidez mínima (R$)", min_value=0, value=DEFAULT_MIN_LIQ, step=10000, key="min_liq",
                              help="Volume financeiro médio negociado por dia (R$). Filtra FIIs com baixa negociação.")

    if min_pvp > max_pvp: st.warning("P/VP mínimo > P/VP máximo.")
    if min_dy_percent > max_dy_percent: st.warning("DY mínimo > DY máximo.")
    atualizar = st.button("🔄 Atualizar Ranking", help="Clique para buscar e processar os dados com os filtros selecionados.")
# --- Fim Sidebar ---

# --- Lógica Principal e Exibição ---
df_original = pd.DataFrame()
show_help_footer_disclaimer = True # Controla exibição da ajuda, disclaimer e footer

if atualizar:
    # Barra de progresso para melhor feedback (opcional, mas legal)
    prog_bar = st.progress(0, text="Iniciando busca...")
    df = None; error_occurred = False; error_message = ""
    try:
        import rank_fiis
        prog_bar.progress(5, text="Configurando filtros...")
        rank_fiis.MIN_PVP = min_pvp; rank_fiis.MAX_PVP = max_pvp; rank_fiis.MIN_DY = min_dy_percent / 100.0; rank_fiis.MAX_DY = max_dy_percent / 100.0; rank_fiis.MIN_LIQUIDEZ = min_liq

        prog_bar.progress(15, text="Buscando dados de resumo (Fundamentus)...")
        df_raw = fetch_summary_data(URL_FII_LIST)

        prog_bar.progress(30, text="Processando dados e buscando detalhes...")
        df = process_data(df_raw) # process_data busca detalhes internamente
        prog_bar.progress(90, text="Finalizando processamento...")

    except Exception as e: error_occurred = True; error_message = f"Erro: {e}"; st.error(error_message, icon="❌"); st.code(traceback.format_exc())
    finally:
        prog_bar.progress(100, text="Concluído!") # Completa a barra
        prog_bar.empty() # Remove a barra após a conclusão

    if not error_occurred and df is not None:
        if not df.empty:
            st.success(f"{len(df)} FIIs encontrados após filtragem.", icon="✅")
            df_original = df.copy(); df_display = df.copy()
            # Adicionar Tipo e Segmento
            if 'Tipo' not in df_display.columns:
                if rank_fiis.FII_SEGMENT_DATA: df_display['Tipo'] = df_display['Papel'].apply(lambda x: rank_fiis.FII_SEGMENT_DATA.get(str(x), {}).get('tipo', 'Indefinido'))
                else: df_display['Tipo'] = 'Indefinido' # Não mostra warning aqui
            if 'Segmento' not in df_display.columns: df_display['Segmento'] = "N/A"

            # AGREGAÇÃO DE SEGMENTOS
            segmento_industrial = "Imóveis Industriais e Logísticos"; segmento_logistica = "Logística"; segmentos_a_unir = [segmento_industrial, segmento_logistica]
            if any(seg in df_display['Segmento'].unique() for seg in segmentos_a_unir):
                replace_map = {seg: segmento_logistica for seg in segmentos_a_unir}
                df_display['Segmento'] = df_display['Segmento'].replace(replace_map)

            # Formatar Colunas como STRING
            percent_cols = ['Dividend Yield', 'FFO Yield', 'Vacância Média', 'Osc. Dia', 'Osc. Mês', 'Osc. 12 Meses']; currency_cols_int = ['Liquidez', 'Valor de Mercado']; currency_cols_dec = ['Cotação']
            for col in percent_cols:
                if col in df_display.columns: df_display[col] = df_display[col].apply(format_percent)
            for col in currency_cols_int:
                if col in df_display.columns: df_display[col] = df_display[col].apply(lambda x: "R$ " + format_brl(x, decimals=0))
            for col in currency_cols_dec:
                if col in df_display.columns: df_display[col] = df_display[col].apply(lambda x: "R$ " + format_brl_cotacao(x))
            if 'P/VP' in df_display.columns: df_display['P/VP'] = df_display['P/VP'].apply(lambda x: f"{x:.2f}".replace('.', ',') if pd.notna(x) else "N/A")
            if 'Qtd de imóveis' in df_display.columns: df_display['Qtd de imóveis'] = df_display['Qtd de imóveis'].apply(lambda x: format_brl(x, decimals=0) if pd.notna(x) else "N/A")

            # --- Configuração das Colunas com AJUDA ---
            column_config = {
                "Papel": st.column_config.TextColumn("Papel", help="Ticker do Fundo Imobiliário."),
                "URL Detalhes": st.column_config.LinkColumn("Link", help="Link para a página do FII no Fundamentus.", display_text="🔗 Abrir"),
                "Link Download Relatório": st.column_config.LinkColumn("Relatório", help="Link para baixar o último relatório gerencial disponível.", display_text="📄 Baixar"),
                "Segmento": st.column_config.TextColumn("Segmento", help="Segmento de atuação principal do FII."),
                "Tipo": st.column_config.TextColumn("Tipo", help="Classificação do FII (Tijolo, Papel, Híbrido, Fiagro, etc.)."),
                "Cotação": st.column_config.TextColumn("Cotação", help="Último preço da cota registrado."),
                "Dividend Yield": st.column_config.TextColumn("DY", help="Dividend Yield (rendimento) acumulado nos últimos 12 meses."),
                "P/VP": st.column_config.TextColumn("P/VP", help="Preço da Cota / Valor Patrimonial por Cota."),
                "Liquidez": st.column_config.TextColumn("Liquidez", help="Volume médio diário negociado (R$)."),
                "FFO Yield": st.column_config.TextColumn("FFO Yield", help="Funds From Operations Yield."),
                "Valor de Mercado": st.column_config.TextColumn("Valor Mercado", help="Valor total do FII baseado na cotação atual."),
                "Qtd de imóveis": st.column_config.TextColumn("Qtd Imóveis", help="Número de imóveis no portfólio do FII."),
                "Vacância Média": st.column_config.TextColumn("Vacância", help="Taxa média de vacância física/financeira reportada."),
                "Osc. Dia": st.column_config.TextColumn("Osc. Dia", help="Oscilação percentual da cota no dia."),
                "Osc. Mês": st.column_config.TextColumn("Osc. Mês", help="Oscilação percentual da cota no mês atual."),
                "Osc. 12 Meses": st.column_config.TextColumn("Osc. 12M", help="Oscilação percentual da cota nos últimos 12 meses."),
                "Data Último Relatório": st.column_config.TextColumn("Últ. Relatório", help="Data do último relatório gerencial encontrado."),
            }
            column_config_filtered = {k: v for k, v in column_config.items() if k in df_display.columns}

            # Reordenar Colunas (Removendo Ranks)
            display_order = ['Papel', 'URL Detalhes', 'Segmento', 'Tipo', 'Cotação', 'Dividend Yield', 'P/VP', 'Liquidez', 'FFO Yield', 'Valor de Mercado', 'Qtd de imóveis', 'Vacância Média', 'Osc. Dia', 'Osc. Mês', 'Osc. 12 Meses', 'Data Último Relatório', 'Link Download Relatório']
            final_columns_ordered = [col for col in display_order if col in df_display.columns]
            df_to_show = df_display[final_columns_ordered]

            # Exibição da Tabela e Abas
            segmentos_brutos = sorted(df_to_show['Segmento'].unique()); segmentos_ordenados = sorted([s for s in segmentos_brutos if s != 'Outros']);
            if 'Outros' in segmentos_brutos: segmentos_ordenados.append('Outros')
            if len(segmentos_ordenados) > 0:
                 st.write("---"); st.subheader("Resultados por Segmento")
                 tabs = st.tabs(["🏆 Todos"] + segmentos_ordenados)
                 with tabs[0]: st.dataframe(df_to_show, column_config=column_config_filtered, use_container_width=True, hide_index=True, key="table_todos")
                 for i, seg in enumerate(segmentos_ordenados):
                     with tabs[i+1]:
                         df_seg = df_to_show[df_to_show['Segmento'] == seg]; st.dataframe(df_seg, column_config=column_config_filtered, use_container_width=True, hide_index=True, key=f"table_seg_{seg.replace(' ','_')}")
            else: st.write("---"); st.subheader("Resultados"); st.dataframe(df_to_show, column_config=column_config_filtered, use_container_width=True, hide_index=True, key="table_unica")

            # Download Excel
            st.write("---"); output = io.BytesIO(); df_excel = df_original.drop(columns=['URL Detalhes'], errors='ignore')
            try:
                with pd.ExcelWriter(output, engine='openpyxl') as writer: df_excel.to_excel(writer, index=False, sheet_name='Ranking FIIs')
                st.download_button(label="📥 Baixar Tabela (Excel)", data=output.getvalue(), file_name="ranking_fiis.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception as e: st.error(f"Erro ao gerar Excel: {e}", icon="❌")
        else: st.warning("Nenhum FII encontrado.", icon="🚫")
else: st.info("⬅️ Configure filtros e clique '🔄 Atualizar Ranking'.", icon="💡"); show_footer_and_disclaimer = True

# --- Seção de Ajuda Expansível, Disclaimer e Footer ---
# (Todo o código ANTES do expander permanece igual)

# --- Seção de Ajuda Expansível, Disclaimer e Footer ---
if show_help_footer_disclaimer:
    st.divider() # Linha divisória

    # --- Seção de Ajuda ---
    with st.expander("ℹ️ Sobre este App / Ajuda"):
        st.markdown("""
            **Fonte dos Dados:**
            *   Os dados são coletados automaticamente do site [Fundamentus](https://www.fundamentus.com.br/) através de web scraping.
            *   A coleta de detalhes individuais (link do relatório, oscilações) pode levar algum tempo.
            *   Os dados podem não ser em tempo real e estão sujeitos à disponibilidade e formato do site Fundamentus.

            **Lógica do Ranking (Filtragem Inicial):**
            *   O ranking original (cujos valores foram ocultados da tabela principal) buscava identificar FIIs com um bom **custo/benefício** inicial, combinando o P/VP (Preço/Valor Patrimonial) e o Dividend Yield (DY).
            *   A intenção era destacar fundos que, pelos números, pareciam **relativamente mais baratos** (P/VP baixo) e com **bons rendimentos recentes** (DY alto).
            *   ⚠️ **Importante:** Este ranking é apenas um **filtro inicial numérico**. A análise dos indicadores é útil, mas **a leitura e o estudo dos relatórios gerenciais dos fundos são essenciais**. Só assim você poderá entender a qualidade dos ativos, a estratégia da gestão e os riscos envolvidos para decidir se aquele fundo realmente vale a pena investir.

            **Principais Indicadores (Tooltips nos cabeçalhos para mais detalhes):**
            *   **DY (Dividend Yield):** Rendimento distribuído nos últimos 12 meses em relação à cotação.
            *   **P/VP (Preço / Valor Patrimonial):** Compara o preço de mercado da cota com seu valor patrimonial. Valores abaixo de 1 podem indicar desconto.
            *   **Liquidez:** Volume médio negociado por dia. Valores mais altos indicam maior facilidade de comprar/vender cotas.
            *   **Vacância:** Percentual de área não alugada (física) ou potencial de renda não realizado (financeira). Menor é geralmente melhor.

            **Classificação por Segmento/Tipo:**
            *   A classificação por 'Segmento' e 'Tipo' foi feita com base em dados externos (arquivo `fii_types.json`) para complementar a informação do Fundamentus.
            *   Como essa classificação é em parte manual e sujeita a interpretações ou mudanças no mercado, alguns FIIs podem ter ficado com a classificação incorreta ou desatualizada.
            *   Caso identifique alguma classificação que acredite estar errada, por favor, entre em contato pelo e-mail: `contato@nerdpobre.com` informando o FII e a sugestão de classificação correta para análise e possível correção.

            **Como Usar:**
            1.  Ajuste os filtros na barra lateral esquerda (P/VP, DY, Liquidez).
            2.  Clique no botão "Atualizar Ranking".
            3.  Aguarde enquanto os dados são buscados e processados.
            4.  Navegue pelos resultados na aba "Todos" ou nas abas por segmento.
            5.  Use os links na tabela para acessar detalhes no Fundamentus ou baixar relatórios.
            6.  Clique em "Baixar Tabela (Excel)" para obter os dados (incluindo ranks ocultos) para análise offline.

            **Limitações:**
            *   Esta é uma ferramenta de estudo e **não** uma recomendação financeira.
            *   A qualidade dos dados depende da fonte (Fundamentus).
            *   O web scraping pode falhar se o site de origem mudar sua estrutura.
        """)
    # --- Fim da Seção de Ajuda ---

    st.warning(DISCLAIMER_TEXT, icon="⚠️") # Disclaimer como warning
    st.caption(FOOTER_TEXT, unsafe_allow_html=True) # Footer

# (Restante do código, se houver, permanece igual)
