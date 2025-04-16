# -*- coding: utf-8 -*-
import pandas as pd
import requests
import numpy as np
import logging
import warnings
import time
import re # <--- NOVO (Importado para usar regex na busca do link)
import html
from bs4 import BeautifulSoup
import json
import os
import io
# import streamlit as st # Removido - O cache @st.cache_data não está mais ativo aqui

# --- Configurações ---
URL_FII_LIST = "https://www.fundamentus.com.br/fii_resultado.php"
BASE_URL_FUNDAMENTUS = "https://www.fundamentus.com.br/"
EXCEL_OUTPUT_FILENAME = "ranking_fiis_completo.xlsx" # Nome indicando dados completos
HTML_OUTPUT_FILENAME = "ranking_fiis_com_abas.html"
FII_TYPES_JSON_FILE = "fii_types.json"
MIN_PVP = 0.7; MAX_PVP = 1.05; MIN_LIQUIDEZ = 400000; MIN_DY = 0.08; MAX_DY = 0.135
REQUEST_DELAY = 0.3
SCRIPT_VERSION = "0.93" # <--- MODIFICADO (Versão incrementada)

# Configuração logging e warnings
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
warnings.simplefilter(action='ignore', category=FutureWarning); warnings.simplefilter(action='ignore', category=UserWarning); warnings.filterwarnings("ignore", category=UserWarning, module='bs4')

# Variável Global para Tipos/Segmentos
FII_SEGMENT_DATA = {}

# --- Funções Auxiliares (Idênticas à sua versão) ---
def carregar_tipos_do_json(filename=FII_TYPES_JSON_FILE):
    global FII_SEGMENT_DATA; FII_SEGMENT_DATA = {} # Reseta
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f: FII_SEGMENT_DATA = json.load(f)
            logging.info(f"'{filename}' carregado ({len(FII_SEGMENT_DATA)} tickers).")
            if FII_SEGMENT_DATA:
                first_key = next(iter(FII_SEGMENT_DATA));
                # Validação mínima da estrutura JSON
                if not isinstance(FII_SEGMENT_DATA[first_key], dict):
                     logging.warning(f"Estrutura JSON '{filename}' inválida."); FII_SEGMENT_DATA = {}
        else: logging.warning(f"'{filename}' não encontrado."); FII_SEGMENT_DATA = {}
    except Exception as e: logging.error(f"Erro ao carregar/ler '{filename}': {e}."); FII_SEGMENT_DATA = {}

def clean_numeric_value(value):
    if isinstance(value, (int, float)): return float(value)
    if isinstance(value, str):
        try: cleaned = value.replace('R$', '').replace('.', '').replace(',', '.').replace('%', '').strip(); return float(cleaned) if cleaned else np.nan
        except ValueError: return np.nan
    return np.nan

# format_value_br_string não é usada pelo app.py, mantida para execução standalone
def format_value_br_string(value, format_type="float", decimals=2):
    if pd.isna(value): return ""
    try:
        if format_type == "percentage": return f"{value * 100:_.{decimals}f}".replace('.', ',').replace('_', '.') + "%"
        if format_type == "integer": return f"{int(value):_}".replace('_', '.')
        if format_type == "large_float": return f"{value:_.0f}".replace('_', '.')
        return f"{value:_.{decimals}f}".replace('_', '#').replace('.', ',').replace('#', '.')
    except (ValueError, TypeError): return str(value)

def get_headers(): return { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36' } # Header padrão

# --- Funções Principais ---

# Removido @st.cache_data daqui, pois a função estava duplicada no seu código
def fetch_summary_data(url):
    logging.info(f"Buscando dados de resumo: {url}")
    try:
        response = requests.get(url, headers=get_headers(), timeout=45, verify=True)
        response.raise_for_status(); response.encoding = response.apparent_encoding
        # Usar io.StringIO é mais robusto para read_html
        tables = pd.read_html(io.StringIO(response.text), decimal=',', thousands='.')
        if tables:
            df = tables[0]; df.columns = df.columns.str.strip()
            logging.info(f"Tabela de resumo encontrada com {len(df)} FIIs.")
            return df
        logging.error("Nenhuma tabela encontrada na página de resumo."); return None
    except requests.exceptions.Timeout: logging.error(f"Timeout (Resumo): {url}"); return None
    except requests.exceptions.RequestException as e: logging.error(f"Erro Requisição (Resumo): {e}"); return None
    except Exception as e: logging.error(f"Erro inesperado fetch/parse (Resumo): {e}"); return None

# --- fetch_fii_details MODIFICADO para buscar o Link FNET ---
def fetch_fii_details(fii_url):
    logging.debug(f"Buscando detalhes de: {fii_url}")
    report_date = "N/A"; download_link = None; fnet_docs_url = None # <--- NOVO: inicializa link FNET
    osc_dia, osc_mes, osc_12m = np.nan, np.nan, np.nan
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(fii_url, headers=get_headers(), timeout=30, verify=True)
        response.raise_for_status(); response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html5lib')

        # 1. Busca Data e Link do Último Relatório (como antes)
        label_td_report = None; all_labels = soup.find_all('td', class_='label')
        for label in all_labels:
            if 'relatório' in label.get_text(strip=True).lower(): label_td_report = label; break
        if label_td_report:
            value_td_report = label_td_report.find_next_sibling('td') # Não precisa classe aqui
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

        # 2. Busca Oscilações (como antes)
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

        # 3. Busca Link "Pesquisar Documentos" para FNET <--- NOVO
        link_pesquisar = soup.find('a', string=re.compile(r'^\s*Pesquisar Documentos\s*$', re.IGNORECASE))
        if link_pesquisar:
            fnet_docs_url = link_pesquisar.get('href')
            if fnet_docs_url and not fnet_docs_url.startswith('http'):
                # Adiciona o domínio base se for um link relativo (embora deva ser absoluto)
                fnet_docs_url = BASE_URL_FUNDAMENTUS.rstrip('/') + '/' + fnet_docs_url.lstrip('/')
            logging.debug(f"Link FNET encontrado: {fnet_docs_url}")
        else:
            logging.debug("Link 'Pesquisar Documentos' não encontrado.")

    except Exception as e: logging.warning(f"Erro parse/extração detalhes {fii_url}: {e}")
    logging.debug(f"Retornando: Data='{report_date}', LinkDL='{download_link}', FNET='{fnet_docs_url}', Osc={osc_dia},{osc_mes},{osc_12m}")
    # Retorna o novo link FNET
    return report_date, download_link, osc_dia, osc_mes, osc_12m, fnet_docs_url # <--- MODIFICADO

# --- process_data MODIFICADO para incluir o Link FNET ---
def process_data(df):
    if df is None or df.empty: logging.error("DataFrame de entrada vazio."); return None
    logging.info("Iniciando limpeza e conversão...")
    df_processed = df.copy()
    cols_to_remove = ['Preço do m2', 'Aluguel por m2', 'Cap Rate']; df_processed.drop(columns=[col for col in cols_to_remove if col in df_processed.columns], errors='ignore', inplace=True)
    columns_to_convert = { 'Cotação': 'float', 'FFO Yield': 'percentage', 'Dividend Yield': 'percentage','P/VP': 'float', 'Valor de Mercado': 'float', 'Liquidez': 'float', 'Qtd de imóveis': 'integer', 'Vacância Média': 'percentage' }
    for col, type in columns_to_convert.items():
        if col in df_processed.columns:
            numeric_col = df_processed[col].apply(clean_numeric_value)
            if type == 'percentage': df_processed[col] = pd.to_numeric(numeric_col / 100.0, errors='coerce')
            elif type == 'integer': df_processed[col] = pd.to_numeric(numeric_col, errors='coerce').astype('Int64')
            else: df_processed[col] = pd.to_numeric(numeric_col, errors='coerce')
    if 'Papel' not in df_processed.columns: logging.error("Coluna 'Papel' não encontrada."); return None
    df_processed['Papel'] = df_processed['Papel'].astype(str)

    # Tratamento Segmento (com JSON - lógica da sua versão)
    if 'Segmento' not in df_processed.columns: df_processed['Segmento'] = 'Não Classificado'
    # Adiciona coluna Tipo baseado no JSON
    if FII_SEGMENT_DATA:
        logging.info("Adicionando/Atualizando 'Tipo' e 'Segmento' com JSON...")
        def get_fii_info(ticker, key):
            data = FII_SEGMENT_DATA.get(str(ticker))
            return data.get(key, None) if isinstance(data, dict) else None

        # Atualiza Segmento
        original_segment_col = df_processed['Segmento'].copy() if 'Segmento' in df_processed.columns else None
        df_processed['Segmento_JSON'] = df_processed['Papel'].apply(lambda x: get_fii_info(x, 'segmento_original'))
        if original_segment_col is not None:
            df_processed['Segmento_JSON'].fillna(original_segment_col, inplace=True)
        df_processed['Segmento'] = df_processed['Segmento_JSON']
        df_processed.drop(columns=['Segmento_JSON'], inplace=True)

        # Adiciona/Atualiza Tipo
        df_processed['Tipo'] = df_processed['Papel'].apply(lambda x: get_fii_info(x, 'tipo'))
        df_processed['Tipo'].fillna('Indefinido', inplace=True) # Garante que a coluna Tipo exista

        df_processed['Segmento'] = df_processed['Segmento'].fillna('Não Classificado').replace('', 'Não Classificado')
        logging.info("Colunas 'Segmento' e 'Tipo' atualizadas/adicionadas.")
    else:
        logging.warning("JSON não carregado. Usando segmentos originais e Tipo 'Indefinido'.")
        if 'Segmento' in df_processed.columns: df_processed['Segmento'] = df_processed['Segmento'].fillna('Não Classificado').replace('', 'Não Classificado')
        else: df_processed['Segmento'] = 'Não Classificado'
        df_processed['Tipo'] = 'Indefinido' # Cria a coluna Tipo se não veio do JSON

    # Filtragem
    required_cols = ['Papel', 'P/VP', 'Liquidez', 'Dividend Yield'];
    if not all(col in df_processed.columns for col in required_cols): logging.error("Colunas essenciais para filtro faltando."); return None
    df_processed.dropna(subset=required_cols, inplace=True)
    logging.info(f"Dados após limpeza: {df_processed.shape[0]} FIIs.")
    logging.info(f"Aplicando filtros...")
    filtered_df = df_processed[(df_processed['P/VP'] >= MIN_PVP) & (df_processed['P/VP'] <= MAX_PVP) & (df_processed['Liquidez'] >= MIN_LIQUIDEZ) & (df_processed['Dividend Yield'] >= MIN_DY) & (df_processed['Dividend Yield'] <= MAX_DY)].copy()
    logging.info(f"FIIs após filtragem: {filtered_df.shape[0]}")
    if filtered_df.empty: logging.warning("Nenhum FII passou pelos filtros."); return filtered_df

    # --- Busca e Adição de Detalhes (Método da sua versão funcional) ---
    logging.info("Buscando detalhes...")
    # <--- MODIFICADO: Adiciona 'Link Documentos FNET' ao dicionário
    details_data = {'Data Último Relatório': [], 'Link Download Relatório': [], 'Osc. Dia': [], 'Osc. Mês': [], 'Osc. 12 Meses': [], 'URL Detalhes': [], 'Link Documentos FNET': []}
    original_indices = filtered_df.index.tolist() # Guarda índice original
    papel_list = filtered_df['Papel'].tolist()
    for i, idx in enumerate(original_indices):
        papel = papel_list[i]
        fii_url = BASE_URL_FUNDAMENTUS + 'detalhes.php?papel=' + papel
        if (i + 1) % 10 == 0 or (i + 1) == len(original_indices): logging.info(f"Detalhes FII {i+1}/{len(original_indices)}: {papel}...")
        # <--- MODIFICADO: Recebe o link FNET retornado
        date, link, o_d, o_m, o_12, fnet_link = fetch_fii_details(fii_url)
        # Adiciona aos dicionários
        details_data['Data Último Relatório'].append(date)
        details_data['Link Download Relatório'].append(link)
        details_data['Osc. Dia'].append(o_d)
        details_data['Osc. Mês'].append(o_m)
        details_data['Osc. 12 Meses'].append(o_12)
        details_data['URL Detalhes'].append(fii_url)
        details_data['Link Documentos FNET'].append(fnet_link) # <--- NOVO: Adiciona o link FNET

    # Adiciona as colunas ao DataFrame usando as listas e o índice original
    logging.info("Adicionando detalhes ao DataFrame...")
    for col, data_list in details_data.items():
        # Garante que a coluna seja criada mesmo se data_list estiver vazia (improvável aqui)
        if col not in filtered_df.columns:
             dtype = float if col.startswith("Osc.") else str
             filtered_df[col] = pd.Series(dtype=dtype, index=filtered_df.index)
        # Atribui a Series alinhada pelo índice original
        filtered_df[col] = pd.Series(data_list, index=original_indices)
    # --- Fim Adição de Detalhes ---
    logging.info("Busca e adição de detalhes concluída.")

    # --- Calcular Ranks Individuais (ADICIONADO AQUI) ---
    logging.info("Calculando Rankings Individuais...")
    df_calc = filtered_df # Usa o dataframe que agora tem os detalhes
    df_calc['Rank_PVP'] = df_calc['P/VP'].rank(method='first', ascending=True).astype('Int64')
    df_calc['Rank_DY'] = df_calc['Dividend Yield'].rank(method='first', ascending=False).astype('Int64')
    if 'Liquidez' in df_calc.columns: df_calc['Rank_Liquidez'] = df_calc['Liquidez'].rank(method='first', ascending=False).astype('Int64')
    else: df_calc['Rank_Liquidez'] = pd.NA
    if 'Vacância Média' in df_calc.columns: df_calc['Rank_Vacancia'] = df_calc['Vacância Média'].rank(method='first', ascending=True, na_option='top').astype('Int64')
    else: df_calc['Rank_Vacancia'] = pd.NA
    # --- Fim Cálculo de Ranks ---

    # --- Reorganizar Colunas Finais (SEM ordenar por score aqui) ---
    logging.info("Reorganizando colunas...")
    # <--- MODIFICADO: Adiciona 'Link Documentos FNET' à ordem das colunas
    first_col=['Papel']; middle_cols_order=['Segmento','Tipo','Cotação','FFO Yield','Dividend Yield','P/VP','Valor de Mercado','Liquidez','Qtd de imóveis','Vacância Média','Osc. Dia','Osc. Mês','Osc. 12 Meses']; detail_cols=['Data Último Relatório','Link Download Relatório', 'Link Documentos FNET']; rank_cols=['Rank_PVP','Rank_DY','Rank_Liquidez','Rank_Vacancia']; last_cols=['URL Detalhes']
    middle_cols=[col for col in middle_cols_order if col in df_calc.columns]; detail_cols_present=[col for col in detail_cols if col in df_calc.columns]; existing_rank_cols=[col for col in rank_cols if col in df_calc.columns]
    final_ordered_cols = first_col + middle_cols + detail_cols_present + existing_rank_cols + last_cols
    final_ordered_cols = [col for col in final_ordered_cols if col in df_calc.columns] # Garante só existentes
    final_df_output = df_calc[final_ordered_cols]

    logging.info(f"Processamento concluído. Retornando {len(final_df_output)} FIIs.")
    return final_df_output


# --- Funções de Salvamento e Bloco __main__ ---
# (Mantidos como na versão anterior, mas save_to_excel foi ajustado para renomear ranks)
def save_to_excel(df, filename):
    if df is None or df.empty: logging.warning("DataFrame vazio, nada para salvar."); return
    logging.info(f"Salvando dados em '{filename}'...")
    try:
        df_save = df.copy()
        df_save.rename(columns={ 'Rank_PVP': 'Rank P/VP (Menor Melhor)', 'Rank_DY': 'Rank DY (Maior Melhor)', 'Rank_Liquidez': 'Rank Liquidez (Maior Melhor)', 'Rank_Vacancia': 'Rank Vacancia (Menor Melhor)' }, inplace=True, errors='ignore') # errors='ignore' se rank não existir
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df_save.to_excel(writer, index=False, sheet_name='Ranking FIIs')
        logging.info(f"Arquivo Excel '{filename}' salvo.")
    except ImportError: logging.error("Biblioteca 'openpyxl' não encontrada.");
    except Exception as e: logging.error(f"Erro ao salvar Excel: {e}")

# save_to_html omitida

if __name__ == "__main__":
    logging.info(f"--- Iniciando Script Ranking FIIs ({SCRIPT_VERSION}) ---")
    carregar_tipos_do_json()
    logging.warning("AVISO: Rodando em modo standalone com filtros padrão.")
    raw_df = fetch_summary_data(URL_FII_LIST)
    if raw_df is not None:
        processed_df = process_data(raw_df) # Usa filtros padrão globais
        if processed_df is not None:
            if not processed_df.empty:
                # Adiciona score simples e ordena para teste standalone
                processed_df['Score_Exemplo'] = (10 * processed_df['Rank_DY'].fillna(len(processed_df)+1) + 7 * processed_df['Rank_PVP'].fillna(len(processed_df)+1)).astype('Int64')
                processed_df.sort_values(by='Score_Exemplo', ascending=True, inplace=True, na_position='last')
                # Mostra as primeiras linhas com a nova coluna no console
                print("\n--- Exemplo de Dados Processados (com Link FNET) ---")
                print(processed_df[['Papel', 'Link Documentos FNET', 'Score_Exemplo']].head())
                print("----------------------------------------------------\n")
                save_to_excel(processed_df, EXCEL_OUTPUT_FILENAME) # Salva Excel com ranks e score
            else: logging.warning("Nenhum FII atendeu aos critérios padrão.")
        else: logging.error("Erro no processamento dos dados.")
    else: logging.error("Não foi possível obter os dados de resumo.")
    logging.info("--- Script Finalizado ---")