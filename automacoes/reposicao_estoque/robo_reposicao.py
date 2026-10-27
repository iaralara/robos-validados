import os
import re
import math
import sys
import logging
import traceback
import unicodedata
import requests
import pandas as pd
import xlwings as xw

# ============================================================================
# ⚙️ CONFIGURAÇÃO DE RASTREABILIDADE (LOGS)
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

if getattr(sys, 'frozen', False):
    DIRETORIO_BASE = os.path.dirname(sys.executable)
else:
    DIRETORIO_BASE = os.path.dirname(os.path.abspath(__file__))

PASTA_LOJAS = os.path.join(DIRETORIO_BASE, "Lojas_Base")

# ============================================================================
# 🛡️ MÓDULO DE SEGURANÇA: VALIDAÇÃO VIA PAINEL DE CONTROLE GOOGLE SHEETS
# ============================================================================
def verificar_licenca(nome_robo):
    url_painel = "https://docs.google.com/spreadsheets/d/SEU_PAINEL_ID/pub?output=csv"
    logger.info("==================================================")
    logger.info(f"📡 Central da Diretoria: Validando credenciais de {nome_robo}...")
    try:
        resposta = requests.get(url_painel, timeout=12)
        resposta.raise_for_status() 
        texto_csv = resposta.text.upper()
        if (f"{nome_robo},ATIVO".upper() in texto_csv) or (f"{nome_robo};ATIVO".upper() in texto_csv):
            logger.info(f"🔒 Licença validada: {nome_robo} liberado para execução.\n")
            return True
        else:
            logger.error("=" * 70)
            logger.error(f"⛔ ACESSO NEGADO: O robô '{nome_robo}' está DESATIVADO no painel principal.")
            logger.error("=" * 70)
            os.system("pause")
            sys.exit(1)
    except Exception as e:
        logger.error(f"⛔ ERRO DE CONEXÃO: {e}")
        os.system("pause")
        sys.exit(1)

# ============================================================================
# 🛠️ FUNÇÕES DE TRATAMENTO DE DADOS (BLINDADAS)
# ============================================================================
def normalizar_texto(texto):
    if pd.isna(texto) or not texto: return ""
    texto = str(texto).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def limpar_referencia(val):
    """Garante que números grandes não virem notação científica nem ganhem casas decimais."""
    if val is None: return ""
    # Se o Excel mandar como número flutuante/inteiro, formata como string exata
    if isinstance(val, (int, float)):
        return f"{val:.0f}"
    
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s

def converter_para_float(valor):
    if pd.isna(valor): return 0.0
    try:
        return float(str(valor).replace(',', '.').strip())
    except ValueError:
        return 0.0

# ============================================================================
# 🚀 MOTOR PRINCIPAL VIA XLWINGS
# ============================================================================
def processar_pin():
    logger.info("⚡ Inicializando a sincronização cruzada CIGAM x Reposição...")
    
    # 1. Carrega o CIGAM da raiz
    lista_arquivos_raiz = os.listdir(DIRETORIO_BASE)
    arquivo_cigam_lista = [f for f in lista_arquivos_raiz if 'cigam' in f.lower() and f.endswith(('.xlsx', '.xlsm')) and not f.startswith('~$')]
    
    if not arquivo_cigam_lista:
        logger.error("❌ Arquivo mestre do CIGAM não localizado na raiz.")
        return

    caminho_cigam_real = os.path.join(DIRETORIO_BASE, arquivo_cigam_lista[0])
    logger.info(f"📖 Lendo CIGAM: {os.path.basename(caminho_cigam_real)}")
    
    df_cigam = pd.read_excel(caminho_cigam_real, skiprows=3)
    df_cigam.columns = df_cigam.columns.str.strip()
    
    df_cigam['H_CODE'] = df_cigam['Loja'].astype(str).str.split(' - ').str[0].str.strip().str.upper()
    df_cigam['Referência'] = df_cigam['Referência'].apply(limpar_referencia)
    df_cigam['Artigo_Norm'] = df_cigam['Artigo'].apply(normalizar_texto)
    
    artigos_alvo = ['PIN', 'PIN GARRA', 'PIN GOTA']
    df_filtrado = df_cigam[df_cigam['Artigo_Norm'].isin(artigos_alvo)].copy()
    
    col_saldo = next((c for c in df_filtrado.columns if normalizar_texto(c) in ['SALDO', 'QTDE', 'QUANTIDADE', 'ESTOQUE']), 'Qtde')
    df_filtrado[col_saldo] = df_filtrado[col_saldo].apply(converter_para_float)
    logger.info(f"📊 {len(df_filtrado)} registros de PINS encontrados.")

    # 2. Varredura das lojas na pasta Lojas_Base
    if not os.path.exists(PASTA_LOJAS):
        logger.error(f"❌ A pasta '{PASTA_LOJAS}' não existe.")
        return

    arquivos_lojas = [os.path.join(PASTA_LOJAS, f) for f in os.listdir(PASTA_LOJAS) 
                      if os.path.isfile(os.path.join(PASTA_LOJAS, f)) 
                      and f.lower().endswith(('.xlsx', '.xlsm')) 
                      and not f.startswith('~$')]

    if not arquivos_lojas:
        logger.warning(f"📭 Nenhum arquivo de loja localizado em: {PASTA_LOJAS}")
        return

    logger.info("🔧 Acionando Excel em background...")
    app = xw.App(visible=False)
    app.display_alerts = False

    try:
        for caminho_loja in arquivos_lojas:
            nome_arquivo = os.path.basename(caminho_loja)
            match_h = re.search(r'(H\d{3})', nome_arquivo.upper())
            if not match_h: continue
                
            codigo_h = match_h.group(1)
            logger.info(f"🔄 Sincronizando Filial {codigo_h} -> {nome_arquivo}")
            
            df_estoque_loja = df_filtrado[df_filtrado['H_CODE'] == codigo_h]
            cache_calculos = {}
            wb = app.books.open(caminho_loja)
            
            try:
                # ====================================================================
                # ABA 1: Sincronização de Estoque Atual e Necessidade de Reposição
                # ====================================================================
                ws1 = wb.sheets[0]
                mapa_abas1 = {}
                linha_cabecalho1 = None
                
                # Mapeamento do cabeçalho
                dados_ws1 = ws1.range('A1:O15').value
                if dados_ws1:
                    for r_idx, row_data in enumerate(dados_ws1):
                        if not row_data: continue
                        for c_idx, cell_value in enumerate(row_data):
                            val = normalizar_texto(cell_value)
                            if 'CODIGO' in val: mapa_abas1['COD'] = c_idx + 1; linha_cabecalho1 = r_idx + 1
                            elif 'QUANT' in val: mapa_abas1['QTD'] = c_idx + 1
                            elif 'ESTOQ' in val or 'SALDO' in val: mapa_abas1['ESTOQ'] = c_idx + 1
                            elif 'REPO' in val: mapa_abas1['REPO'] = c_idx + 1
                        if linha_cabecalho1: break
                        
                if 'COD' in mapa_abas1 and linha_cabecalho1:
                    # LER ATÉ A ÚLTIMA LINHA REAL DA PLANILHA (Ignora linhas em branco no meio)
                    max_row1 = ws1.used_range.last_cell.row
                    
                    for row in range(linha_cabecalho1 + 1, max_row1 + 1):
                        cod_celula_raw = ws1.range(row, mapa_abas1['COD']).value
                        if cod_celula_raw is None: continue
                            
                        cod_celula = limpar_referencia(cod_celula_raw)
                        if not cod_celula: continue
                        
                        estoque_cigam = df_estoque_loja.loc[df_estoque_loja['Referência'] == cod_celula, col_saldo].sum()
                        quant_ideal_raw = ws1.range(row, mapa_abas1['QTD']).value
                        try:
                            quant_ideal = float(str(quant_ideal_raw).replace(',', '.')) if quant_ideal_raw else 0.0
                        except ValueError:
                            quant_ideal = 0.0
                        
                        deficit = quant_ideal - estoque_cigam
                        valor_reposicao = math.ceil(deficit / 12) * 12 if deficit > 0 else 0
                        quantidade_saquinhos = math.ceil(deficit / 12) if deficit > 0 else 0
                        
                        cache_calculos[cod_celula] = {'pecas': valor_reposicao, 'saqs': quantidade_saquinhos}
                        
                        if 'ESTOQ' in mapa_abas1: ws1.range(row, mapa_abas1['ESTOQ']).value = int(estoque_cigam)
                        if 'REPO' in mapa_abas1: ws1.range(row, mapa_abas1['REPO']).value = int(valor_reposicao)

                # ====================================================================
                # ABA 2: Distribuição de Peças e Conversão Logística para Embalagens
                # ====================================================================
                if wb.sheets.count > 1:
                    ws2 = wb.sheets[1]
                    mapa_abas2 = {}
                    linha_cabecalho2 = None
                    
                    dados_ws2 = ws2.range('A1:O15').value
                    if dados_ws2:
                        for r_idx, row_data in enumerate(dados_ws2):
                            if not row_data: continue
                            for c_idx, cell_value in enumerate(row_data):
                                val = normalizar_texto(cell_value)
                                if 'CODIGO' in val: mapa_abas2['COD'] = c_idx + 1; linha_cabecalho2 = r_idx + 1
                                elif 'REPO' in val: mapa_abas2['REPO'] = c_idx + 1
                                elif 'SAQ' in val: mapa_abas2['SAQ'] = c_idx + 1
                            if linha_cabecalho2: break
                            
                    if 'COD' in mapa_abas2 and linha_cabecalho2:
                        # LER ATÉ A ÚLTIMA LINHA REAL DA PLANILHA (Ignora linhas em branco no meio)
                        max_row2 = ws2.used_range.last_cell.row
                        
                        for row2 in range(linha_cabecalho2 + 1, max_row2 + 1):
                            cod_celula2_raw = ws2.range(row2, mapa_abas2['COD']).value
                            if cod_celula2_raw is None: continue
                                
                            cod_celula2 = limpar_referencia(cod_celula2_raw)
                            if not cod_celula2: continue
                            
                            if cod_celula2 in cache_calculos:
                                dados_calculados = cache_calculos[cod_celula2]
                                if 'REPO' in mapa_abas2: ws2.range(row2, mapa_abas2['REPO']).value = int(dados_calculados['pecas'])
                                if 'SAQ' in mapa_abas2: ws2.range(row2, mapa_abas2['SAQ']).value = int(dados_calculados['saqs'])

                wb.save()
                logger.info(f"💾 Alterações salvas com integridade visual: {nome_arquivo}")
                
            finally:
                wb.close()
                
    except Exception as e:
        logger.error(f"❌ Falha de execução: {e}")
        traceback.print_exc()
    finally:
        app.quit()
        
    logger.info("🏁 Sincronização finalizada com sucesso.")

if __name__ == "__main__":
    verificar_licenca("REPOSICAO")
    processar_pin()