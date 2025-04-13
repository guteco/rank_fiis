# -*- coding: utf-8 -*-
import pandas as pd
import requests
import numpy as np
import logging
import warnings
import time
import re
import html
from bs4 import BeautifulSoup
import json # Para ler JSON
import os   # Para verificar path do JSON
import streamlit as st

# --- Configurações ---
URL_FII_LIST = "https://www.fundamentus.com.br/fii_resultado.php"
BASE_URL_FUNDAMENTUS = "https://www.fundamentus.com.br/"
EXCEL_OUTPUT_FILENAME = "ranking_fiis.xlsx"
HTML_OUTPUT_FILENAME = "ranking_fiis_com_abas.html"
FII_TYPES_JSON_FILE = "fii_types.json" # Arquivo JSON com tipos/segmentos
MIN_PVP = 0.7
MAX_PVP = 1.05
MIN_LIQUIDEZ = 400000
MIN_DY = 0.08
MAX_DY = 0.135
REQUEST_DELAY = 0.3
SCRIPT_VERSION = "0.9a" # Versão com Segmento JSON

# Configuração básica de logging e warnings
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=UserWarning)
warnings.filterwarnings("ignore", category=UserWarning, module='bs4')

# --- Variável Global para Tipos/Segmentos do JSON ---
FII_SEGMENT_DATA = {}

# --- Funções Auxiliares ---

def carregar_tipos_do_json(filename=FII_TYPES_JSON_FILE):
    """Carrega a classificação e segmento original do arquivo JSON."""
    global FII_SEGMENT_DATA
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                FII_SEGMENT_DATA = json.load(f)
            logging.info(f"Arquivo de segmentos '{filename}' carregado com {len(FII_SEGMENT_DATA)} tickers.")
            if FII_SEGMENT_DATA:
                first_key = next(iter(FII_SEGMENT_DATA))
                if not isinstance(FII_SEGMENT_DATA[first_key], dict) or 'segmento_original' not in FII_SEGMENT_DATA[first_key]:
                     logging.warning(f"Estrutura JSON '{filename}' inválida. Ignorando.")
                     FII_SEGMENT_DATA = {}
        else:
            logging.warning(f"Arquivo de segmentos '{filename}' não encontrado. Usará segmentos do Fundamentus.")
            FII_SEGMENT_DATA = {}
    except Exception as e:
        logging.error(f"Erro ao carregar/ler '{filename}': {e}. Usará segmentos do Fundamentus.")
        FII_SEGMENT_DATA = {}

def clean_numeric_value(value):
    if isinstance(value, (int, float)): return float(value)
    if isinstance(value, str):
        try:
            cleaned = value.replace('R$', '').replace('.', '').replace(',', '.').replace('%', '').strip()
            return float(cleaned) if cleaned else np.nan
        except ValueError: return np.nan
    return np.nan

def format_value_br_string(value, format_type="float", decimals=2):
    if pd.isna(value): return ""
    try:
        if format_type == "percentage": return f"{value * 100:.{decimals}f}".replace('.', ',') + "%"
        if format_type == "integer": return f"{int(value):_}".replace('_', '.')
        if format_type == "large_float": return f"{value:_.0f}".replace('_', '.')
        return f"{value:_.{decimals}f}".replace('_', '#').replace('.', ',').replace('#', '.')
    except (ValueError, TypeError): return str(value)

def get_headers():
    return { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36' }

# --- Funções Principais ---

@st.cache_data(ttl=3600) # Cacheia por 1 hora (3600 segundos)
def fetch_summary_data(url):
    logging.info(f"Buscando dados de resumo (CACHE MISS ou TTL expirado): {url}") # Log só roda se não usar cache
    try:
        response = requests.get(url, headers=get_headers(), timeout=45, verify=True)
        response.raise_for_status(); response.encoding = response.apparent_encoding
        # Use io.StringIO para garantir que read_html funcione bem com cache
        tables = pd.read_html(io.StringIO(response.text), decimal=',', thousands='.')
        if tables:
            df = tables[0]; df.columns = df.columns.str.strip()
            logging.info(f"Tabela de resumo encontrada com {len(df)} FIIs.")
            return df # Retorna o dataframe para ser cacheado
        logging.error("Nenhuma tabela encontrada na página de resumo."); return None
    except requests.exceptions.Timeout: logging.error(f"Timeout (Resumo): {url}"); return None
    except requests.exceptions.RequestException as e: logging.error(f"Erro Requisição (Resumo): {e}"); return None
    except Exception as e: logging.error(f"Erro inesperado fetch/parse (Resumo): {e}"); return None

def fetch_summary_data(url):
    logging.info(f"Buscando dados de resumo: {url}")
    try:
        response = requests.get(url, headers=get_headers(), timeout=45, verify=True)
        response.raise_for_status(); response.encoding = response.apparent_encoding
        tables = pd.read_html(response.text, decimal=',', thousands='.')
        if tables:
            df = tables[0]; df.columns = df.columns.str.strip()
            logging.info(f"Tabela de resumo encontrada com {len(df)} FIIs.")
            return df
        logging.error("Nenhuma tabela encontrada na página de resumo."); return None
    except requests.exceptions.Timeout: logging.error(f"Timeout (Resumo): {url}"); return None
    except requests.exceptions.RequestException as e: logging.error(f"Erro Requisição (Resumo): {e}"); return None
    except Exception as e: logging.error(f"Erro inesperado fetch/parse (Resumo): {e}"); return None

def fetch_fii_details(fii_url):
    logging.debug(f"Buscando detalhes de: {fii_url}")
    report_date = "N/A"; download_link = None; osc_dia, osc_mes, osc_12m = np.nan, np.nan, np.nan
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(fii_url, headers=get_headers(), timeout=30, verify=True)
        response.raise_for_status(); response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html5lib')
        label_td_report = None; all_labels = soup.find_all('td', class_='label')
        for label in all_labels:
            if 'relatório' in label.get_text(strip=True).lower(): label_td_report = label; break
        if label_td_report:
            value_td_report = label_td_report.find_next_sibling('td')
            if value_td_report:
                img_tag = value_td_report.find('img', alt='Download')
                if not img_tag: img_tag = value_td_report.find('img', src=re.compile(r'download', re.IGNORECASE))
                if img_tag:
                    parent_link = img_tag.find_parent('a', href=True)
                    if parent_link:
                        href = parent_link['href']
                        dl_prefix = BASE_URL_FUNDAMENTUS.rstrip('/')
                        if href.startswith('/'): download_link = dl_prefix + href
                        elif href.startswith('http'): download_link = href
                        else: download_link = dl_prefix + '/' + href.lstrip('/')
                cell_text_report = value_td_report.get_text(separator=' ', strip=True)
                date_match = re.search(r'(\d{2}/\d{2}/\d{4})', cell_text_report)
                if date_match: report_date = date_match.group(1)
        osc_labels_map = {'Dia': 'osc_dia', 'Mês': 'osc_mes', '12 meses': 'osc_12m'}; temp_osc = {'osc_dia': np.nan, 'osc_mes': np.nan, 'osc_12m': np.nan}
        for label in all_labels:
            label_text = label.get_text(strip=True)
            if label_text in osc_labels_map:
                osc_key = osc_labels_map[label_text]; value_td_osc = label.find_next_sibling('td', class_='data')
                if value_td_osc:
                    value_span = value_td_osc.find('span');
                    if value_span: numeric_value = clean_numeric_value(value_span.get_text(strip=True));
                    if not pd.isna(numeric_value): temp_osc[osc_key] = numeric_value / 100.0
        osc_dia, osc_mes, osc_12m = temp_osc['osc_dia'], temp_osc['osc_mes'], temp_osc['osc_12m']
    except Exception as e: logging.warning(f"Erro parse/extração detalhes {fii_url}: {e}")
    logging.debug(f"Retornando: Data='{report_date}', Link='{download_link}', Osc={osc_dia},{osc_mes},{osc_12m}")
    return report_date, download_link, osc_dia, osc_mes, osc_12m

# ATUALIZADA: process_data (com lógica corrigida para JSON)
def process_data(df):
    if df is None or df.empty: return None
    logging.info("Iniciando limpeza e conversão...")
    original_columns = df.columns.tolist(); df_processed = df.copy()
    cols_to_remove = ['Preço do m2', 'Aluguel por m2', 'Cap Rate'] # Colunas do Fundamentus
    df_processed = df_processed.drop(columns=[col for col in cols_to_remove if col in df_processed.columns], errors='ignore')
    columns_to_convert = { 'Cotação': 'float', 'FFO Yield': 'percentage', 'Dividend Yield': 'percentage','P/VP': 'float', 'Valor de Mercado': 'float', 'Liquidez': 'float', 'Qtd de imóveis': 'integer', 'Vacância Média': 'percentage' }
    for col, type in columns_to_convert.items():
        if col in df_processed.columns:
            numeric_col = df_processed[col].apply(clean_numeric_value)
            if type == 'percentage': df_processed[col] = pd.to_numeric(numeric_col / 100.0, errors='coerce')
            elif type == 'integer': df_processed[col] = pd.to_numeric(numeric_col, errors='coerce').astype('Int64')
            else: df_processed[col] = pd.to_numeric(numeric_col, errors='coerce')

    if 'Papel' not in df_processed.columns: logging.error("Coluna 'Papel' não encontrada."); return None
    df_processed['Papel'] = df_processed['Papel'].astype(str)

    # --- ATUALIZAÇÃO DO SEGMENTO USANDO O JSON (CORRIGIDO) ---
    if 'Segmento' not in df_processed.columns:
        logging.warning("Coluna 'Segmento' original não encontrada. Criando coluna padrão.")
        df_processed['Segmento'] = 'Não Classificado'

    if FII_SEGMENT_DATA:
        logging.info("Atualizando coluna 'Segmento' com dados do JSON...")
        original_segment_col = df_processed['Segmento'].copy() # Salva original para fallback

        def get_detailed_segment(ticker):
            data = FII_SEGMENT_DATA.get(str(ticker))
            if isinstance(data, dict) and 'segmento_original' in data:
                segmento = data['segmento_original']
                return segmento if segmento else None # Retorna segmento se não for vazio
            return None

        # Aplica função para pegar segmentos do JSON (pode ter NaN)
        df_processed['Segmento_JSON'] = df_processed['Papel'].map(get_detailed_segment)

        # Preenche NaN no Segmento_JSON com os valores da coluna original
        df_processed['Segmento_JSON'].fillna(original_segment_col, inplace=True)

        # A coluna final 'Segmento' recebe os valores atualizados
        df_processed['Segmento'] = df_processed['Segmento_JSON']
        df_processed.drop(columns=['Segmento_JSON'], inplace=True) # Remove coluna auxiliar

        # Garante que não há NaNs e substitui vazios por 'Não Classificado'
        df_processed['Segmento'] = df_processed['Segmento'].fillna('Não Classificado').replace('', 'Não Classificado')
        logging.info("Coluna 'Segmento' atualizada.")

    else:
        logging.warning("JSON de tipos não carregado ou vazio. Usando segmentos originais (se existirem).")
        if 'Segmento' in df_processed.columns:
             df_processed['Segmento'] = df_processed['Segmento'].fillna('Não Classificado').replace('', 'Não Classificado')
        else:
             df_processed['Segmento'] = 'Não Classificado' # Garante que a coluna existe
    # --- FIM DA ATUALIZAÇÃO DO SEGMENTO ---


    required_cols = ['Papel', 'P/VP', 'Liquidez', 'Dividend Yield']
    if not all(col in df_processed.columns for col in required_cols): logging.error("Colunas P/VP, Liquidez ou DY não presentes."); return None
    df_processed.dropna(subset=required_cols, inplace=True) # Remove linhas sem dados essenciais para filtro/rank
    logging.info(f"Dados após limpeza/NaNs: {df_processed.shape[0]} FIIs.")

    logging.info("Aplicando filtros...")
    filtered_df = df_processed[(df_processed['P/VP'] >= MIN_PVP) & (df_processed['P/VP'] <= MAX_PVP) & (df_processed['Liquidez'] >= MIN_LIQUIDEZ) & (df_processed['Dividend Yield'] >= MIN_DY) & (df_processed['Dividend Yield'] <= MAX_DY)].copy()
    logging.info(f"FIIs após filtragem: {filtered_df.shape[0]}")

    if filtered_df.empty: logging.warning("Nenhum FII passou pelos filtros."); return filtered_df

    logging.info("Buscando detalhes (Data Relatório/Download/Oscilações)...")
    details_data = {'Data Último Relatório': [], 'Link Download Relatório': [], 'Osc. Dia': [], 'Osc. Mês': [], 'Osc. 12 Meses': [], 'URL Detalhes': []}
    original_indices = filtered_df.index.tolist() # Guarda os índices antes do loop
    papel_list = filtered_df['Papel'].tolist()

    for i, idx in enumerate(original_indices):
        papel = papel_list[i]
        fii_url = BASE_URL_FUNDAMENTUS + 'detalhes.php?papel=' + papel
        if (i + 1) % 10 == 0 or (i + 1) == len(original_indices): logging.info(f"Detalhes FII {i+1}/{len(original_indices)}: {papel}...")

        date, link, o_d, o_m, o_12 = fetch_fii_details(fii_url)
        details_data['Data Último Relatório'].append(date)
        details_data['Link Download Relatório'].append(link)
        details_data['Osc. Dia'].append(o_d)
        details_data['Osc. Mês'].append(o_m)
        details_data['Osc. 12 Meses'].append(o_12)
        details_data['URL Detalhes'].append(fii_url)

    # Atribui os detalhes ao DataFrame usando os índices originais para garantir alinhamento
    for col, data_list in details_data.items():
        filtered_df[col] = pd.Series(data_list, index=filtered_df.index)


    logging.info("Busca de detalhes concluída.")
    logging.info("Calculando Rankings e Rank Final...")
    filtered_df['Rank_PVP'] = filtered_df['P/VP'].rank(method='first', ascending=True).astype(int)
    filtered_df['Rank_DY'] = filtered_df['Dividend Yield'].rank(method='first', ascending=False).astype(int)
    filtered_df['Rank_Final'] = filtered_df['Rank_PVP'] + filtered_df['Rank_DY']

    logging.info("Ordenando pelo Rank Final...")
    final_df = filtered_df.sort_values(by='Rank_Final', ascending=True)

    logging.info("Reorganizando colunas...")
    first_col = ['Papel']; middle_cols_order = ['Segmento', 'Cotação', 'FFO Yield', 'Dividend Yield', 'P/VP', 'Valor de Mercado', 'Liquidez', 'Qtd de imóveis', 'Vacância Média', 'Osc. Dia', 'Osc. Mês', 'Osc. 12 Meses']; detail_cols = ['Data Último Relatório', 'Link Download Relatório']; last_cols = ['Rank_Final', 'Rank_PVP', 'Rank_DY', 'URL Detalhes']; middle_cols = [col for col in middle_cols_order if col in final_df.columns]
    final_ordered_cols = first_col + middle_cols + detail_cols + last_cols; final_ordered_cols = [col for col in final_ordered_cols if col in final_df.columns] # Garante que só colunas existentes entrem
    final_df = final_df[final_ordered_cols]

    return final_df


# --- Funções de Salvamento ---
def save_to_excel(df, filename):
    if df is None or df.empty: return
    logging.info(f"Salvando dados em '{filename}'...")
    try:
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Ranking FIIs')
            worksheet = writer.sheets['Ranking FIIs']
            float_fmt = '#,##0.00'; integer_fmt = '#,##0'; percent_fmt = '0.00%'
            col_formats = { 'Cotação': float_fmt, 'P/VP': float_fmt, 'FFO Yield': percent_fmt, 'Dividend Yield': percent_fmt, 'Vacância Média': percent_fmt, 'Osc. Dia': percent_fmt, 'Osc. Mês': percent_fmt, 'Osc. 12 Meses': percent_fmt, 'Valor de Mercado': integer_fmt, 'Liquidez': integer_fmt,'Qtd de imóveis': integer_fmt, 'Rank_Final': integer_fmt, 'Rank_PVP': integer_fmt, 'Rank_DY': integer_fmt }
            col_widths = { 'Papel': 12, 'Segmento': 30, 'Cotação': 10, 'FFO Yield': 10, 'Dividend Yield': 12, 'P/VP': 8, 'Valor de Mercado': 18, 'Liquidez': 15, 'Qtd de imóveis': 8, 'Vacância Média': 10, 'Osc. Dia': 10, 'Osc. Mês': 10, 'Osc. 12 Meses': 12, 'Data Último Relatório': 18, 'Link Download Relatório': 60, 'Rank_Final': 8, 'Rank_PVP': 8, 'Rank_DY': 8, 'URL Detalhes': 60 }
            for i, col_name in enumerate(df.columns):
                 col_letter = chr(65 + i)
                 if col_name in col_formats: worksheet.column_dimensions[col_letter].number_format = col_formats[col_name]
                 width = col_widths.get(col_name, 15)
                 worksheet.column_dimensions[col_letter].width = width
        logging.info(f"Arquivo Excel '{filename}' salvo.")
    except ImportError: logging.error("openpyxl não encontrado.");
    except Exception as e: logging.error(f"Erro ao salvar/formatar Excel: {e}")

# Função save_to_html (sem alterações na lógica interna, usa o 'Segmento' atualizado)
def save_to_html(df_full, filename):
    if df_full is None or df_full.empty: logging.warning("DataFrame vazio. Nenhum HTML gerado."); return
    logging.info(f"Preparando HTML com abas '{filename}' usando segmentos atualizados...")
    if 'Segmento' not in df_full.columns: logging.error("Coluna 'Segmento' não encontrada."); return
    df_full['Segmento'] = df_full['Segmento'].fillna('Não Classificado')
    segments = ['Todos'] + sorted(df_full['Segmento'].unique())
    segment_tables_html = {}

    for segment in segments:
        logging.debug(f"Processando aba HTML: {segment}")
        df_segment = df_full.copy() if segment == 'Todos' else df_full[df_full['Segmento'] == segment].copy()
        if df_segment.empty:
            segment_tables_html[segment] = "<p style='text-align:center; padding: 20px; color: #777;'>Nenhum FII encontrado.</p>"; continue
        df_html_segment = df_segment.copy()
        formatting_map_html = { 'Cotação': 'float', 'P/VP': 'float', 'FFO Yield': 'percentage', 'Dividend Yield': 'percentage', 'Vacância Média': 'percentage', 'Osc. Dia': 'percentage', 'Osc. Mês': 'percentage', 'Osc. 12 Meses': 'percentage', 'Valor de Mercado': 'large_float', 'Liquidez': 'large_float', 'Qtd de imóveis': 'integer', 'Rank_Final': 'integer', 'Rank_PVP': 'integer', 'Rank_DY': 'integer' }
        for col, fmt_type in formatting_map_html.items():
            if col in df_html_segment.columns: decimals = 2 if fmt_type not in ['integer', 'large_float'] else 0; df_html_segment[col] = df_html_segment[col].apply(lambda x: format_value_br_string(x, format_type=fmt_type, decimals=decimals))
        monetary_cols = ['Cotação', 'Valor de Mercado', 'Liquidez'];
        for col in monetary_cols:
            if col in df_html_segment.columns: df_html_segment[col] = df_html_segment[col].apply(lambda x: f"R$ {x}" if x else "")
        if 'Papel' in df_html_segment.columns and 'URL Detalhes' in df_html_segment.columns: df_html_segment['Papel'] = df_html_segment.apply(lambda row: f'<a href="{row["URL Detalhes"]}" target="_blank">{row["Papel"]}</a>', axis=1)
        if 'Link Download Relatório' in df_html_segment.columns: df_html_segment['Download'] = df_html_segment['Link Download Relatório'].apply( lambda link: f'<a href="{link}" target="_blank">Baixar</a>' if pd.notna(link) and link else "N/D" )
        else: df_html_segment['Download'] = "N/D"
        cols_to_drop_html = ['URL Detalhes', 'Link Download Relatório']; df_html_segment = df_html_segment.drop(columns=[col for col in cols_to_drop_html if col in df_html_segment.columns], errors='ignore')
        first_col_html = ['Papel']; new_detail_cols_html = ['Data Último Relatório', 'Download']; last_cols_html = ['Rank_Final', 'Rank_PVP', 'Rank_DY']; middle_cols_order_html = ['Segmento', 'Cotação', 'FFO Yield', 'Dividend Yield', 'P/VP', 'Valor de Mercado', 'Liquidez', 'Qtd de imóveis', 'Vacância Média', 'Osc. Dia', 'Osc. Mês', 'Osc. 12 Meses']
        middle_cols_html = [col for col in middle_cols_order_html if col in df_html_segment.columns]
        html_ordered_cols = first_col_html + middle_cols_html + new_detail_cols_html + last_cols_html; html_ordered_cols = [col for col in html_ordered_cols if col in df_html_segment.columns]
        df_html_segment = df_html_segment[html_ordered_cols]
        segment_tables_html[segment] = df_html_segment.to_html(index=False, escape=False, classes='fundamentus-table', border=0)
        logging.debug(f"Tabela HTML gerada para aba: {segment}")

    # Geração HTML com Abas (Lógica mantida)
    tab_buttons_html = '<div class="tab-buttons">\n'; tab_content_html = '<div class="tab-content-wrapper">\n'
    for i, segment in enumerate(segments):
        tab_id = "tab-" + re.sub(r'\W+', '-', html.escape(segment).lower().replace(' ', '-').strip('-'))
        active_class = 'active' if i == 0 else ''; display_style = 'block' if i == 0 else 'none'
        tab_buttons_html += f'    <button class="tablink {active_class}" onclick="openTab(event, \'{tab_id}\')">{html.escape(segment)}</button>\n'
        tab_content_html += f'  <div id="{tab_id}" class="tabcontent" style="display: {display_style};">\n<h3>{html.escape(segment)}</h3>\n{segment_tables_html[segment]}\n</div>\n'
    tab_buttons_html += '</div>\n'; tab_content_html += '</div>\n'
    css_style = """ body { font-family: Trebuchet MS, Arial, Helvetica, sans-serif; font-size: 0.9em; margin: 0; padding: 15px; background-color: #f4f4f4; } h2.main-title { text-align:center; color: #008080; margin-bottom: 25px; font-size: 1.7em; font-weight: bold; border-bottom: 2px solid #008080; padding-bottom: 10px; } .tab-buttons { overflow: hidden; border-bottom: 1px solid #ccc; background-color: #f1f1f1; margin-bottom: 10px; } .tab-buttons button { background-color: inherit; float: left; border: none; outline: none; cursor: pointer; padding: 12px 16px; transition: 0.3s; font-size: 0.95em; border-right: 1px solid #ccc; } .tab-buttons button:last-child { border-right: none; } .tab-buttons button:hover { background-color: #ddd; } .tab-buttons button.active { background-color: #008080; color: white; font-weight: bold; } .tabcontent { display: none; padding: 15px 10px; border: 1px solid #ccc; border-top: none; background-color: white; box-shadow: 0 1px 4px rgba(0,0,0,0.05); animation: fadeEffect 0.5s; } .tabcontent h3 { margin-top: 5px; color: #008080; text-align: center; border-bottom: 1px dashed #ccc; padding-bottom: 8px;} @keyframes fadeEffect { from {opacity: 0;} to {opacity: 1;} } .fundamentus-table { border-collapse: collapse; width: 100%; margin: 15px auto; font-size: 0.9em; background-color: #fff; } .fundamentus-table thead th, .fundamentus-table tbody td { border: 1px solid #ddd; padding: 8px 5px; text-align: center; vertical-align: middle; } .fundamentus-table thead th { background-color: #008080; color: white; font-weight: bold; position: sticky; top: 0; z-index: 1; } .fundamentus-table tbody tr:nth-child(even) { background-color: #eaf7f7; } .fundamentus-table tbody tr:nth-child(odd) { background-color: #ffffff; } .fundamentus-table tbody tr:hover { background-color: #d1eded; } .fundamentus-table a { color: #0000EE; text-decoration: none; font-weight: bold; } .fundamentus-table a:hover { text-decoration: underline; } .disclaimer { text-align: center; margin: 30px auto 15px auto; padding: 15px; max-width: 800px; font-size: 0.8em; font-style: italic; color: #666; background-color: #f9f9f9; border: 1px solid #eee; border-radius: 4px; line-height: 1.5; } .disclaimer strong { color: #c00; } .footer-attribution { text-align: center; padding: 20px 0; margin-top: 10px; border-top: 1px solid #e0e0e0; font-size: 0.85em; color: #555; } .footer-attribution a { color: #0056b3; font-weight: normal; } """
    javascript_code = """ <script> function openTab(evt, tabName) { var i, tabcontent, tablinks; tabcontent = document.getElementsByClassName("tabcontent"); for (i = 0; i < tabcontent.length; i++) { tabcontent[i].style.display = "none"; } tablinks = document.getElementsByClassName("tablink"); for (i = 0; i < tablinks.length; i++) { tablinks[i].className = tablinks[i].className.replace(" active", ""); } document.getElementById(tabName).style.display = "block"; evt.currentTarget.className += " active"; } document.addEventListener("DOMContentLoaded", function() { var firstTab = document.querySelector(".tablink"); if (firstTab) { firstTab.click(); } }); </script> """
    full_html = f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Ranking FIIs - Método 2 em 1</title><style>{css_style}</style></head><body><h2 class="main-title">Método 2 em 1 - Ranking FIIs</h2>{tab_buttons_html}{tab_content_html}<div class="disclaimer"><strong>AVISO IMPORTANTE:</strong><br>Este script foi gerado somente para fins de estudo e análise pessoal.<br>As informações apresentadas <strong>NÃO</strong> constituem recomendação de compra ou venda de ativos financeiros.<br>Esta é apenas uma ferramenta para auxiliar na sua própria análise e tomada de decisão.<br>Este script não pode ser vendido ou alterado sem autorização prévia dos autores.<br>Qualquer dúvida ou sugestão, entre em contato.</div><p class="footer-attribution">Script feito por Augusto Severo - <a href="https://www.instagram.com/guteco" target="_blank">@guteco</a> e pela IA do Google.<br>Este trabalho foi carinhosamente pago com a promessa de excelentes pizzas! 🍕 - Versão: {SCRIPT_VERSION}</p>{javascript_code}</body></html>"""
    logging.info(f"Salvando HTML com abas em '{filename}'...")
    try:
        with open(filename, 'w', encoding='utf-8') as f: f.write(full_html)
        logging.info(f"Arquivo HTML com abas '{filename}' salvo.")
    except Exception as e: logging.error(f"Erro ao salvar o HTML: {e}")


# --- Execução Principal ---
if __name__ == "__main__":
    logging.info(f"--- Iniciando Script Ranking FIIs ({SCRIPT_VERSION}) ---")
    carregar_tipos_do_json() # Carrega os dados do JSON
    logging.warning("AVISO: Busca de detalhes online torna a execução MAIS LENTA.")
    raw_df = fetch_summary_data(URL_FII_LIST)
    if raw_df is not None:
        processed_df = process_data(raw_df) # process_data usa FII_SEGMENT_DATA
        if processed_df is not None:
            if not processed_df.empty:
                save_to_excel(processed_df, EXCEL_OUTPUT_FILENAME)
                save_to_html(processed_df, HTML_OUTPUT_FILENAME) # save_to_html usa a coluna 'Segmento' processada
            else: logging.warning("Nenhum FII atendeu aos critérios.")
        else: logging.error("Erro no processamento dos dados.")
    else: logging.error("Não foi possível obter os dados de resumo.")
    logging.info("--- Script Finalizado ---")
    logging.info(f">>> PIZZA TIME ({SCRIPT_VERSION})! Ranking gerado. Bom apetite! <<<")
