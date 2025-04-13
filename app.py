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
    except locale.Error: st.warning("Locale 'pt_BR' não encontrado.", icon="⚠️")
# --- Fim Locale ---

# --- Importar de rank_fiis ---
try:
    from rank_fiis import ( fetch_summary_data, process_data, URL_FII_LIST, FII_TYPES_JSON_FILE, carregar_tipos_do_json, SCRIPT_VERSION, FII_SEGMENT_DATA )
    RANK_FIIS_IMPORTED = True; carregar_tipos_do_json(FII_TYPES_JSON_FILE)
except ImportError as e: st.error(f"Erro CRÍTICO ao importar 'rank_fiis'."); st.error(f"Path: {os.getcwd()}, Erro: {e}"); st.stop()

# --- Constantes de Texto ---
DISCLAIMER_TEXT = """**AVISO IMPORTANTE:**\nEste script foi gerado somente para fins de estudo e análise pessoal.\nAs informações apresentadas **NÃO** constituem recomendação de compra ou venda de ativos financeiros.\nEsta é apenas uma ferramenta para auxiliar na sua própria análise e tomada de decisão.\n*Este script não pode ser vendido ou alterado sem autorização prévia dos autores.*\nQualquer dúvida ou sugestão, entre em contato."""
FOOTER_TEXT = f"""Script feito por Augusto Severo - [@guteco](https://www.instagram.com/guteco) e pela IA do Google.<br>Este trabalho foi carinhosamente pago com a promessa de excelentes pizzas! 🍕 - Versão App: {SCRIPT_VERSION} (rank_fiis)"""
# --- Fim Constantes ---

st.set_page_config(page_title="Ranking de FIIs", layout="wide")
st.title("🏢 Ranking de Fundos Imobiliários (FIIs)")
st.markdown("Análise automatizada com dados do [Fundamentus](https://www.fundamentus.com.br/).")

# --- Funções Auxiliares para Formatação ---
def format_brl(value, decimals=0):
    if pd.isna(value): return "N/A"
    try:
        num_str_locale = f"{float(value):n}"
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

# --- Sidebar com Filtros ---
with st.sidebar:
    st.header("🔍 Filtros");
    try: from rank_fiis import MIN_PVP as DEFAULT_MIN_PVP, MAX_PVP as DEFAULT_MAX_PVP, MIN_DY as DEFAULT_MIN_DY, MAX_DY as DEFAULT_MAX_DY, MIN_LIQUIDEZ as DEFAULT_MIN_LIQ
    except ImportError: DEFAULT_MIN_PVP=0.7; DEFAULT_MAX_PVP=1.05; DEFAULT_MIN_DY=0.08; DEFAULT_MAX_DY=0.135; DEFAULT_MIN_LIQ=400000; st.warning("Constantes de filtro padrão não encontradas.", icon="⚠️")
    DEFAULT_MIN_DY_PERCENT = DEFAULT_MIN_DY * 100; DEFAULT_MAX_DY_PERCENT = DEFAULT_MAX_DY * 100
    min_pvp = st.slider("P/VP mínimo", 0.0, 2.5, DEFAULT_MIN_PVP, 0.01, key="min_pvp")
    max_pvp = st.slider("P/VP máximo", 0.0, 2.5, DEFAULT_MAX_PVP, 0.01, key="max_pvp")
    min_dy_percent = st.slider("DY mínimo (%)", 0.0, 25.0, DEFAULT_MIN_DY_PERCENT, 0.1, key="min_dy")
    max_dy_percent = st.slider("DY máximo (%)", 0.0, 25.0, DEFAULT_MAX_DY_PERCENT, 0.1, key="max_dy")
    min_liq = st.number_input("Liquidez mínima (R$)", min_value=0, value=DEFAULT_MIN_LIQ, step=10000, key="min_liq")
    if min_pvp > max_pvp: st.warning("P/VP mínimo > P/VP máximo.")
    if min_dy_percent > max_dy_percent: st.warning("DY mínimo > DY máximo.")
    atualizar = st.button("🔄 Atualizar Ranking")
# --- Fim Sidebar ---

# --- Lógica Principal e Exibição ---
df_original = pd.DataFrame()
show_footer_and_disclaimer = True

if atualizar:
    with st.spinner("Buscando e processando dados... ⏳"):
        df = None; error_occurred = False; error_message = ""
        try:
            import rank_fiis; rank_fiis.MIN_PVP = min_pvp; rank_fiis.MAX_PVP = max_pvp; rank_fiis.MIN_DY = min_dy_percent / 100.0; rank_fiis.MAX_DY = max_dy_percent / 100.0; rank_fiis.MIN_LIQUIDEZ = min_liq
            df_raw = fetch_summary_data(URL_FII_LIST); df = process_data(df_raw)
        except Exception as e: error_occurred = True; error_message = f"Erro: {e}"; st.error(error_message, icon="❌"); st.code(traceback.format_exc())

    if not error_occurred and df is not None:
        if not df.empty:
            st.success(f"{len(df)} FIIs encontrados após filtragem.", icon="✅")
            df_original = df.copy() # Guarda original para Excel
            df_display = df.copy() # Trabalha com cópia para exibição

            # Adicionar Tipo e Segmento (se necessário)
            if 'Tipo' not in df_display.columns:
                if rank_fiis.FII_SEGMENT_DATA: df_display['Tipo'] = df_display['Papel'].apply(lambda x: rank_fiis.FII_SEGMENT_DATA.get(str(x), {}).get('tipo', 'Indefinido'))
                else: st.warning("Dados JSON não disponíveis para 'Tipo'.", icon="⚠️"); df_display['Tipo'] = 'Indefinido'
            if 'Segmento' not in df_display.columns: df_display['Segmento'] = "N/A"

            # --- AGREGAÇÃO DE SEGMENTOS PARA EXIBIÇÃO ---
            segmento_industrial = "Imóveis Industriais e Logísticos"
            segmento_logistica = "Logística" # Nome final desejado
            segmentos_a_unir = [segmento_industrial, segmento_logistica] # Lista dos segmentos a serem mapeados

            # Verifica se algum dos segmentos a unir existe antes de tentar a substituição
            if any(seg in df_display['Segmento'].unique() for seg in segmentos_a_unir):
                st.info(f"Agregando segmentos relacionados em '{segmento_logistica}'.", icon="🔄")
                # Cria um mapeamento para a função replace
                replace_map = {seg: segmento_logistica for seg in segmentos_a_unir}
                df_display['Segmento'] = df_display['Segmento'].replace(replace_map)
            # --- Fim da Agregação ---

            # Formatar Colunas como STRING (usando a nova format_brl)
            percent_cols = ['Dividend Yield', 'FFO Yield', 'Vacância Média', 'Osc. Dia', 'Osc. Mês', 'Osc. 12 Meses']; currency_cols_int = ['Liquidez', 'Valor de Mercado']; currency_cols_dec = ['Cotação']
            for col in percent_cols:
                if col in df_display.columns: df_display[col] = df_display[col].apply(format_percent)
            for col in currency_cols_int:
                if col in df_display.columns: df_display[col] = df_display[col].apply(lambda x: "R$ " + format_brl(x, decimals=0))
            for col in currency_cols_dec:
                if col in df_display.columns: df_display[col] = df_display[col].apply(lambda x: "R$ " + format_brl_cotacao(x))
            if 'P/VP' in df_display.columns: df_display['P/VP'] = df_display['P/VP'].apply(lambda x: f"{x:.2f}".replace('.', ',') if pd.notna(x) else "N/A")
            if 'Qtd de imóveis' in df_display.columns: df_display['Qtd de imóveis'] = df_display['Qtd de imóveis'].apply(lambda x: format_brl(x, decimals=0) if pd.notna(x) else "N/A")

            # Configuração das Colunas (Mantida)
            column_config = { "Papel": st.column_config.TextColumn("Papel"), "URL Detalhes": st.column_config.LinkColumn("Link", display_text="🔗 Abrir"), "Link Download Relatório": st.column_config.LinkColumn("Relatório", display_text="📄 Baixar"), "Cotação": st.column_config.TextColumn("Cotação"), "Liquidez": st.column_config.TextColumn("Liquidez"), "Valor de Mercado": st.column_config.TextColumn("Valor Mercado"), "Dividend Yield": st.column_config.TextColumn("DY"), "FFO Yield": st.column_config.TextColumn("FFO Yield"), "Vacância Média": st.column_config.TextColumn("Vacância"), "Osc. Dia": st.column_config.TextColumn("Osc. Dia"), "Osc. Mês": st.column_config.TextColumn("Osc. Mês"), "Osc. 12 Meses": st.column_config.TextColumn("Osc. 12M"), "P/VP": st.column_config.TextColumn("P/VP"), "Qtd de imóveis": st.column_config.TextColumn("Qtd Imóveis"), "Data Último Relatório": st.column_config.TextColumn("Últ. Relatório") }
            column_config_filtered = {k: v for k, v in column_config.items() if k in df_display.columns}

            # Reordenar Colunas (Removendo Ranks)
            display_order = ['Papel', 'URL Detalhes', 'Segmento', 'Tipo', 'Cotação', 'Dividend Yield', 'P/VP', 'Liquidez', 'FFO Yield', 'Valor de Mercado', 'Qtd de imóveis', 'Vacância Média', 'Osc. Dia', 'Osc. Mês', 'Osc. 12 Meses', 'Data Último Relatório', 'Link Download Relatório']
            final_columns_ordered = [col for col in display_order if col in df_display.columns]
            df_to_show = df_display[final_columns_ordered]

            # Exibição da Tabela e Abas (AGORA USA O SEGMENTO UNIFICADO)
            # A lógica de ordenação das abas já trata o nome "Logística" corretamente
            segmentos_brutos = sorted(df_to_show['Segmento'].unique());
            segmentos_ordenados = sorted([s for s in segmentos_brutos if s != 'Outros']);
            if 'Outros' in segmentos_brutos: segmentos_ordenados.append('Outros')

            if len(segmentos_ordenados) > 0:
                 st.write("---"); st.subheader("Resultados por Segmento")
                 tabs = st.tabs(["🏆 Todos"] + segmentos_ordenados) # Usa segmentos já unificados
                 with tabs[0]: st.dataframe(df_to_show, column_config=column_config_filtered, use_container_width=True, hide_index=True, key="table_todos")
                 for i, seg in enumerate(segmentos_ordenados): # Itera sobre os nomes de segmento (já unificados)
                     with tabs[i+1]:
                         # Filtra pelo nome do segmento (que agora pode ser "Logística" unificado)
                         df_seg = df_to_show[df_to_show['Segmento'] == seg];
                         st.dataframe(df_seg, column_config=column_config_filtered, use_container_width=True, hide_index=True, key=f"table_seg_{seg.replace(' ','_')}")
            else: st.write("---"); st.subheader("Resultados"); st.dataframe(df_to_show, column_config=column_config_filtered, use_container_width=True, hide_index=True, key="table_unica")

            # Download Excel (Usa df_original com segmentos separados)
            st.write("---"); output = io.BytesIO(); df_excel = df_original.drop(columns=['URL Detalhes'], errors='ignore')
            try:
                with pd.ExcelWriter(output, engine='openpyxl') as writer: df_excel.to_excel(writer, index=False, sheet_name='Ranking FIIs')
                st.download_button(label="📥 Baixar Tabela (Excel)", data=output.getvalue(), file_name="ranking_fiis.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception as e: st.error(f"Erro ao gerar Excel: {e}", icon="❌")
        else: st.warning("Nenhum FII encontrado.", icon="🚫")
else: st.info("⬅️ Configure filtros e clique '🔄 Atualizar Ranking'.", icon="💡"); show_footer_and_disclaimer = True

# --- Disclaimer e Footer ---
if show_footer_and_disclaimer:
    st.divider(); st.warning(DISCLAIMER_TEXT, icon="⚠️"); st.caption(FOOTER_TEXT, unsafe_allow_html=True)