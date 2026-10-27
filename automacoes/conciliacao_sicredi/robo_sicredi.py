import os
import sys
import glob
import re
import fitz  # PyMuPDF
import time
import urllib.request
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# CONFIGURAÇÃO DE LOGS
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==========================================
# 0. SISTEMA DE SEGURANÇA DA DIRETORIA
# ==========================================
def verificar_permissao_diretoria(nome_robo):
    url_csv = "https://docs.google.com/spreadsheets/d/SEU_PAINEL_ID/pub?output=csv"
    print("==================================================")
    print(f"📡 Consultando a Central da Diretoria: {nome_robo}...")
    try:
        resposta = urllib.request.urlopen(url_csv, timeout=10)
        linhas = resposta.read().decode('utf-8').splitlines()
        for linha in linhas:
            colunas = linha.split(',')
            if len(colunas) >= 2:
                nome_na_planilha = colunas[0].strip().upper()
                status = colunas[1].strip().upper()
                if nome_na_planilha == nome_robo.upper():
                    if status == "ATIVO":
                        print("✅ Permissão concedida! Iniciando os motores...\n")
                        return True
                    else:
                        print("\n❌ ACESSO NEGADO! ❌")
                        print(f"O robô '{nome_robo}' foi DESATIVADO pela Diretoria.")
                        print("Fechando o sistema em 5 segundos...")
                        time.sleep(5)
                        sys.exit() 
        print(f"\n⚠️ Segurança: Robô '{nome_robo}' não encontrado na planilha.")
        print("Acesso bloqueado por segurança. Fechando...")
        time.sleep(5)
        sys.exit()
    except Exception as e:
        print("\n❌ ERRO DE SEGURANÇA INTERNA ❌")
        print("Não foi possível falar com a Central da Diretoria (Sem Internet?).")
        print("O robô NÃO roda sem autorização online. Fechando...")
        time.sleep(5)
        sys.exit()

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS E COFRE
# ==========================================
# O robô descobre automaticamente onde ele está de verdade logo no início
if getattr(sys, 'frozen', False):
    DIRETORIO_BASE = os.path.dirname(sys.executable)
else:
    DIRETORIO_BASE = os.path.dirname(os.path.abspath(__file__))

env_path = os.path.join(DIRETORIO_BASE, ".env")
load_dotenv(env_path)

USUARIO = os.getenv("USUARIO") or os.getenv("F360_EMAIL")
SENHA = os.getenv("SENHA") or os.getenv("F360_PASSWORD")     

if not USUARIO or not SENHA:
    logger.error(f"❌ Erro: Credenciais não encontradas no arquivo .env na pasta: {DIRETORIO_BASE}")
    input("\nPressione ENTER para fechar a tela...")
    sys.exit()

DE_PARA_LOJAS = {
    "UNIDADE SHOPPING MATRIZ": "UNIDADE SHOPPING MATRIZ (EMPRESA)",
    "UNIDADE SHOPPING FILIAL A": "UNIDADE SHOPPING FILIAL A (EMPRESA)",
    "UNIDADE SHOPPING FILIAL B": "UNIDADE SHOPPING FILIAL B (EMPRESA)",
    "UNIDADE CENTRO": "UNIDADE CENTRO (EMPRESA)"
}

# ==========================================
# 2. O CÉREBRO DE LEITURA DO PDF
# ==========================================
def calcular_data_util(data_obj):
    if data_obj.weekday() == 4: return data_obj + timedelta(days=3)
    elif data_obj.weekday() == 5: return data_obj + timedelta(days=2)
    elif data_obj.weekday() == 6: return data_obj + timedelta(days=1)
    else: return data_obj + timedelta(days=1)

def extrair_numero_do_nome(nome_arquivo):
    numeros = re.findall(r'\d+', nome_arquivo.replace('.pdf', ''))
    if numeros: return int(numeros[0])
    return 9999

def extrair_dados_de_um_pdf(caminho_pdf):
    doc = fitz.open(caminho_pdf)
    texto_bruto = "".join([pag.get_text() for pag in doc]).upper()
    texto_bruto = re.sub(r'\s+', ' ', texto_bruto)
    
    data_base = datetime.now()
    match_data = re.search(r"PER[ÍI]ODO[^0-9]*(\d{2}/\d{2}/\d{4})", texto_bruto)
    if match_data:
        data_base = datetime.strptime(match_data.group(1), '%d/%m/%Y')
            
    data_final = calcular_data_util(data_base)
    data_pt = data_final.strftime('%d/%m/%Y')
    data_falsa = data_base.strftime('%d,%m')
    
    valor_total_pdf = 0.0
    match_total = re.search(r"VALOR TOTAL LIQUIDA[ÇC][ÃA]O R\$:\s*([\d\.,]+)", texto_bruto)
    if match_total:
        valor_total_pdf = float(match_total.group(1).replace('.', '').replace(',', '.'))

    lancamentos = []
    lojas_ordenadas = sorted(DE_PARA_LOJAS.items(), key=lambda x: len(x[0]), reverse=True)
    posicoes_lojas = []
    
    for loja_pdf, loja_f360 in lojas_ordenadas:
        start = 0
        while True:
            idx = texto_bruto.find(loja_pdf, start)
            if idx == -1: break
            
            overlap = False
            for p_idx, p_len, _ in posicoes_lojas:
                if p_idx <= idx < p_idx + p_len:
                    overlap = True; break
            
            if not overlap:
                posicoes_lojas.append((idx, len(loja_pdf), loja_f360))
            
            start = idx + len(loja_pdf)
            
    posicoes_lojas.sort(key=lambda x: x[0])
    
    for i in range(len(posicoes_lojas)):
        idx_atual = posicoes_lojas[i][0]
        loja_f360 = posicoes_lojas[i][2]
        
        if i + 1 < len(posicoes_lojas):
            idx_prox = posicoes_lojas[i+1][0]
            bloco_loja = texto_bruto[idx_atual:idx_prox]
        else:
            bloco_loja = texto_bruto[idx_atual:idx_atual+2000] 
            
        partes_liquidadas = re.split(r"LIQUIDAD[OAS]*|LIQUIDA[CÇ][AÃ]O", bloco_loja)
        
        for pedaco_antes_do_liquidado in partes_liquidadas[:-1]:
            pedaco_limpo = re.split(r"VENCIDO|A VENCER|CANCELADO|DEVOLVIDO|REJEITADO", pedaco_antes_do_liquidado)[-1]
            valores = re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2})", pedaco_limpo)
            
            if valores:
                if valores[-1] == data_falsa:
                    valores.pop()
                    
            if valores:
                valor_real = valores[-1]
                valor_float_real = float(valor_real.replace('.', '').replace(',', '.'))
                if valor_float_real > 0.0:
                    lancamentos.append({
                        "loja": loja_f360, 
                        "valor_str": valor_real,
                        "valor_float": valor_float_real,
                        "data_util": data_pt,
                        "data_alvo_iso": data_final.strftime('%Y-%m-%d')
                    })
                            
    if valor_total_pdf == 0.0:
        valor_total_pdf = sum([item['valor_float'] for item in lancamentos])
                        
    return {
        "data_util": data_pt,
        "lancamentos": lancamentos,
        "total_pdf": valor_total_pdf
    }

# ==========================================
# 3. O ROBÔ EXECUTOR F360 
# ==========================================
class RoboSicrediAuditor:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.acoes = None 

    def inicializar_driver(self):
        os.system("taskkill /f /im chromedriver.exe /T >nul 2>&1")
        try:
            chrome_options = Options()
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.page_load_strategy = 'eager' 
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("prefs", {
                "profile.default_content_setting_values.notifications": 2,
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            })
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            self.driver.maximize_window()
            self.driver.set_page_load_timeout(120) 
            self.wait = WebDriverWait(self.driver, 25) 
            self.acoes = ActionChains(self.driver) 
            logger.info("[SISTEMA] Motor do Navegador Inicializado com Sucesso!")
            return True 
        except Exception as e:
            logger.error(f"Erro ao inicializar o driver: {e}")
            return False

    def injetar_clique_humano(self, elemento, duplo=False):
        script = """
            var el = arguments[0]; var duplo = arguments[1];
            if(!el) return;
            el.scrollIntoView({block: 'center', behavior: 'instant'});
            var rect = el.getBoundingClientRect();
            var cx = rect.left + (rect.width / 2); var cy = rect.top + (rect.height / 2);
            var opts = {bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, buttons: 1};
            el.dispatchEvent(new MouseEvent('mouseover', opts));
            el.dispatchEvent(new MouseEvent('mousedown', opts));
            el.dispatchEvent(new MouseEvent('mouseup', opts));
            el.dispatchEvent(new MouseEvent('click', opts));
            if (duplo) {
                setTimeout(function() {
                    el.dispatchEvent(new MouseEvent('dblclick', Object.assign({}, opts, {detail: 2})));
                }, 100);
            }
        """
        self.driver.execute_script(script, elemento, duplo)

    def fazer_login(self):
        logger.info("[LOGIN] Acessando F360...")
        self.driver.get("https://financas.f360.com.br/")
        try:
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='email' or @type='text' or contains(@class, 'form-control')]")))
            time.sleep(2)
            campos = self.driver.find_elements(By.CSS_SELECTOR, "input.form-control")
            if len(campos) >= 2:
                campos[0].clear(); campos[0].send_keys(USUARIO)
                campos[1].clear(); campos[1].send_keys(SENHA + Keys.ENTER)
            else:
                campo_email = self.driver.find_element(By.XPATH, "//input[@type='email' or @type='text']")
                campo_senha = self.driver.find_element(By.XPATH, "//input[@type='password']")
                campo_email.clear(); campo_email.send_keys(USUARIO)
                campo_senha.clear(); campo_senha.send_keys(SENHA + Keys.ENTER)
        except Exception as e:
            logger.error(f"Erro no login do F360: {e}")

        time.sleep(8)
        for i in range(15): 
            try:
                # Tenta clicar com XPath primeiro
                btn = self.driver.find_elements(By.XPATH, "//button[contains(., 'Continuar')] | //a[contains(., 'Continuar')] | //span[contains(., 'Continuar')]")
                if btn:
                    for b in btn:
                        if b.is_displayed():
                            self.driver.execute_script("arguments[0].click();", b)
                            time.sleep(5)
                            break
                
                # Tenta também usando JS para garantir
                self.driver.execute_script("""
                    var btns = document.querySelectorAll('button, a, span');
                    for(var i=0; i<btns.length; i++){
                        if((btns[i].innerText||'').trim().includes('Continuar') && btns[i].offsetParent !== null){
                            btns[i].click();
                        }
                    }
                """)
            except: pass
            time.sleep(2)


    def lancar_no_fechamento(self, loja, dias_da_loja):
        logger.info(f"\n[+] 🚀 INICIANDO OS LANÇAMENTOS DO FECHAMENTO: LOJA {loja}")
        
        for tentativa in range(3):
            try:
                try:
                    self.driver.get("https://financas.f360.com.br/FechamentoDeCaixa")
                except Exception as e:
                    if "timeout" in str(e).lower():
                        logger.warning("    ⚠️ F360 demorou a carregar. Forçando parada e prosseguindo...")
                        self.driver.execute_script("window.stop();")
                    else:
                        raise e
                        
                time.sleep(10) 
                
                self.driver.execute_script("""
                    try {
                        document.querySelectorAll('.sweetalert, #intercom-container, .f360-campanha-modal-standard, .img-banner-h').forEach(e => e.remove());
                        document.body.classList.remove('modal-open');
                    } catch(e) {}
                """)
                
                logger.info("    -> Injetando contexto da loja...")
                caixa = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "span.k-widget.k-combobox")))
                self.injetar_clique_humano(caixa, duplo=False)
                time.sleep(1)
                
                ipt = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.k-input[role='combobox']")))
                ipt.clear()
                ipt.send_keys(loja)
                time.sleep(3) 
                ipt.send_keys(Keys.ARROW_DOWN)
                time.sleep(0.5)
                ipt.send_keys(Keys.ENTER)
                time.sleep(1)
                ipt.send_keys(Keys.TAB) 
                time.sleep(3)

                from datetime import datetime, timedelta
                datas_ordenadas = sorted(dias_da_loja.keys(), key=lambda d: datetime.strptime(d, "%d/%m/%Y"))
                for data_pt in datas_ordenadas:
                    itens_da_loja = dias_da_loja[data_pt]
                    
                    logger.info(f"\n -> Acessando o dia: {data_pt} (Processando {len(itens_da_loja)} valor(es))")

                    mes_ano_alvo = data_pt[3:]
                    script_mes = "var inputs = document.querySelectorAll('input.k-input'); for(var i=0;i<inputs.length;i++){ if(inputs[i].value && inputs[i].value.includes('/20')) return inputs[i]; } return null;"
                    campo_mes = self.driver.execute_script(script_mes)
                    if campo_mes:
                        mes_atual = self.driver.execute_script("return arguments[0].value;", campo_mes)
                        if mes_ano_alvo not in str(mes_atual):
                            self.driver.execute_script("arguments[0].click();", campo_mes)
                            time.sleep(0.5); campo_mes.send_keys(Keys.CONTROL + "a"); campo_mes.send_keys(Keys.BACKSPACE)
                            campo_mes.send_keys(mes_ano_alvo); campo_mes.send_keys(Keys.ENTER); time.sleep(5)
                    
                    data_obj = datetime.strptime(data_pt, "%d/%m/%Y")
                    
                    def tentar_abrir_gaveta(data_alvo_iso):
                        try:
                            xpath_celula = f"//td[contains(@class, 'fc-day-top') and @data-date='{data_alvo_iso}'] | //td[@data-date='{data_alvo_iso}']"
                            celula = self.wait.until(EC.presence_of_element_located((By.XPATH, xpath_celula)))
                            alvo = celula
                            try: alvo = celula.find_element(By.XPATH, ".//*[contains(@class, 'fc-day-number') or contains(text(), 'Pendente')]")
                            except: pass
                            
                            for _ in range(3): 
                                self.driver.execute_script("document.querySelectorAll('.k-loading-mask, .k-overlay, .modal-backdrop').forEach(e => e.remove());")
                                time.sleep(0.5)
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", alvo)
                                time.sleep(0.5)
                                self.acoes.move_to_element(alvo).double_click().perform()
                                time.sleep(6) 
                                
                                self.driver.execute_script("""
                                    var divs = document.querySelectorAll('div');
                                    for(var i=0; i<divs.length; i++) {
                                        if(divs[i].innerText && divs[i].innerText.startsWith('Depósitos')) {
                                            var icon = divs[i].querySelector('.fa-plus, .fa-caret-right');
                                            if(icon || divs[i].classList.contains('collapsed')) {
                                                divs[i].scrollIntoView({block:'center'});
                                                divs[i].click(); 
                                            }
                                        }
                                    }
                                """)
                                time.sleep(2)
                                
                                btn_add = self.driver.execute_script("""
                                    var btn_bind = document.querySelector("[data-bind*='FazerDepositos.Open']");
                                    if(btn_bind && btn_bind.offsetParent !== null) {
                                        btn_bind.scrollIntoView({block:'center'});
                                        btn_bind.click();
                                        return true;
                                    }
                                    var spans = document.querySelectorAll('span, a, button');
                                    for (var i = 0; i < spans.length; i++) {
                                        if ((spans[i].innerText || '').trim() === '+ Adicionar' && spans[i].offsetParent !== null) {
                                            var pai = spans[i].closest('div, .row, tr');
                                            if (pai && (pai.innerText || '').includes('Depósitos') && !(pai.innerText || '').includes('Despesas')) {
                                                spans[i].scrollIntoView({block: 'center'});
                                                spans[i].click();
                                                return true;
                                            }
                                        }
                                    }
                                    return false;
                                """)
                                
                                if btn_add:
                                    time.sleep(3)
                                    labels = self.driver.find_elements(By.XPATH, "//div[not(contains(@style, 'display: none'))]//label[contains(text(),'Valor do Depósito')]")
                                    if any(lbl.is_displayed() for lbl in labels):
                                        return True
                                    else:
                                        ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                                        time.sleep(1)
                                else:
                                    self.injetar_clique_humano(alvo, duplo=False)
                                    time.sleep(2)
                        except Exception as err:
                            logger.error(f"    [ERRO GAVETA] {err}")
                            return False
                        return False

                    logger.info("    -> Procurando a gaveta no calendário...")
                    status_gaveta = False
                    for dias_para_voltar in range(5): 
                        data_tentativa_obj = data_obj - timedelta(days=dias_para_voltar)
                        data_tentativa_iso = data_tentativa_obj.strftime("%Y-%m-%d")
                        
                        if dias_para_voltar > 0:
                            logger.info(f"    ⚠️ Sem botão de Adicionar. Plano B: Abrindo pelo dia {data_tentativa_obj.strftime('%d/%m/%Y')}...")
                            
                        status_gaveta = tentar_abrir_gaveta(data_tentativa_iso)
                        if status_gaveta: 
                            break
                            
                    if not status_gaveta:
                        raise Exception("A gaveta não abriu nem no dia oficial nem nos dias anteriores.")

                    # TRAVA ANTI-DUPLICIDADE
                    logger.info("    -> Fazendo raio-X da gaveta bancária (Evitar duplicidades)...")
                    import re
                    texto_banco = self.driver.execute_script("""
                        try {
                            var txt = "";
                            var blocos = document.querySelectorAll('.row, tr, li, .k-item');
                            for(var i=0; i<blocos.length; i++) {
                                var t = (blocos[i].innerText || '').toUpperCase();
                                if(t.includes('SICREDI') && (t.includes('R$') || t.includes(','))) {
                                    txt += " || " + t;
                                }
                            }
                            return txt;
                        } catch(e) { return ""; }
                    """)
                    
                    valores_tela_str = re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2})", texto_banco)
                    floats_na_tela = [float(v.replace('.', '').replace(',', '.')) for v in valores_tela_str]
                    
                    valores_pendentes = []
                    for item in itens_da_loja:
                        vf = item['valor_float']
                        if vf in floats_na_tela:
                            floats_na_tela.remove(vf) 
                        else:
                            valores_pendentes.append(item)
                            
                    if not valores_pendentes:
                        logger.info("    ✔️ FEITO: Todos os valores exigidos já estão no portal. Pulando dia.")
                        try:
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                            time.sleep(1)
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                        except: pass
                        continue

                    for idx, item_pendente in enumerate(valores_pendentes):
                        valor_str = item_pendente['valor_str']
                        valor_float = item_pendente['valor_float']

                        logger.info(f"    -> Injetando na esteira: R$ {valor_str} e Datas...")
                        
                        self.driver.execute_script("document.querySelectorAll('.k-loading-mask, .k-overlay, .modal-backdrop').forEach(e => e.remove());")
                        time.sleep(1)

                        # MISTURA INFALÍVEL: Digitação Física do Caçador para o VALOR
                        xpath_visivel = "//div[not(contains(@style, 'display: none'))]//label[contains(text(),'Valor do Depósito')]/following::input[not(@type='hidden')][1]"
                        campo_valor = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_visivel)))
                        
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", campo_valor)
                        time.sleep(0.5)
                        self.injetar_clique_humano(campo_valor, duplo=False)
                        time.sleep(0.5)
                        
                        campo_ativo = self.driver.switch_to.active_element
                        campo_ativo.send_keys(Keys.END)
                        time.sleep(0.2)
                        for _ in range(15): 
                            campo_ativo.send_keys(Keys.BACKSPACE)
                            campo_ativo.send_keys(Keys.DELETE)
                        time.sleep(0.5)
                        
                        for digito in str(valor_str):
                            campo_ativo.send_keys(digito)
                            time.sleep(0.05)
                            
                        time.sleep(0.5)
                        campo_ativo.send_keys(Keys.TAB)
                        time.sleep(1)

                        # INJEÇÃO JS PARA DATAS (E Backup do Valor via Kendo)
                        self.driver.execute_script(f"""
                            var modais = document.querySelectorAll('.k-window');
                            for(var m=0; m<modais.length; m++) {{
                                if (modais[m].style.display !== 'none') {{ 
                                    var ipt = modais[m].querySelector('input[data-role="numerictextbox"]');
                                    if(ipt && window.$(ipt).data("kendoNumericTextBox")) {{ 
                                        window.$(ipt).data("kendoNumericTextBox").value({valor_float}); 
                                        window.$(ipt).data("kendoNumericTextBox").trigger("change"); 
                                    }}
                                    var dt_inputs = modais[m].querySelectorAll('input[data-role="datepicker"], input.hasDatepicker');
                                    for(var i=0; i<dt_inputs.length; i++) {{
                                        var kDate = window.$(dt_inputs[i]).data("kendoDatePicker");
                                        if(kDate) {{
                                            var partes = '{data_pt}'.split('/');
                                            kDate.value(new Date(partes[2], parseInt(partes[1])-1, partes[0]));
                                            kDate.trigger("change");
                                        }} else {{
                                            dt_inputs[i].value = '{data_pt}';
                                            dt_inputs[i].dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        }}
                                    }}
                                }}
                            }}
                        """)
                        time.sleep(1.5)

                        # SELECIONAR A CONTA "SICREDI"
                        try:
                            xpath_input_banco = "//div[not(contains(@style, 'display: none'))]//label[contains(text(), 'Conta de Destino')]/following::input[@role='combobox'][1]"
                            campo_banco = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_input_banco)))
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo_banco)
                            time.sleep(0.5)
                            self.injetar_clique_humano(campo_banco, duplo=False)
                            time.sleep(1)
                            
                            ativo = self.driver.switch_to.active_element
                            ativo.send_keys(Keys.CONTROL + 'a')
                            ativo.send_keys(Keys.BACKSPACE)
                            time.sleep(0.5) 
                            
                            logger.info(f"    -> Digitando conta: SICREDI")
                            for char in "SICREDI":
                                ativo.send_keys(char)
                                time.sleep(0.1) 
                            
                            time.sleep(3) 
                            
                            self.driver.execute_script(f"""
                                var listas = document.querySelectorAll('.k-list-container, .k-animation-container');
                                for(var i=0; i<listas.length; i++) {{
                                    if(listas[i].style.display !== 'none') {{
                                        var itens = listas[i].querySelectorAll('li');
                                        for(var j=0; j<itens.length; j++) {{
                                            if((itens[j].innerText || '').toUpperCase().includes('SICREDI')) {{
                                                itens[j].scrollIntoView({{block: 'center'}});
                                                itens[j].click();
                                                return;
                                            }}
                                        }}
                                    }}
                                }}
                            """)
                            time.sleep(1.5)
                        except Exception as err:
                            raise Exception(f"Falha ao selecionar banco Sicredi: {err}")

                        # --- ETAPA 4: SALVAR ---
                        if idx == len(valores_pendentes) - 1:
                            logger.info("    -> Último valor do DIA. Salvando e fechando o modal...")
                            
                            salvou_popup = self.driver.execute_script("""
                                var modais = document.querySelectorAll('.k-window');
                                for(var i=0; i<modais.length; i++) {
                                    if(modais[i].style.display !== 'none' && modais[i].innerText.includes('Valor do Depósito')) {
                                        var btns = modais[i].querySelectorAll('button');
                                        for(var j=0; j<btns.length; j++) {
                                            if((btns[j].innerText || '').trim() === 'Salvar') {
                                                btns[j].click();
                                                return true;
                                            }
                                        }
                                    }
                                }
                                return false;
                            """)
                            
                            if not salvou_popup:
                                xpath_btn_salvar = "//button[normalize-space(text())='Salvar' and preceding-sibling::button[contains(translate(text(), 'NOVO', 'novo'), 'novo')]]"
                                try:
                                    btn_s = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_btn_salvar)))
                                    self.acoes.move_to_element(btn_s).click().perform()
                                except:
                                    self.driver.execute_script("arguments[0].click();", btn_s)

                            time.sleep(4)
                            
                            alerta_erro = self.driver.execute_script("""
                                try {
                                    var txt = document.body.innerText || '';
                                    if(txt.includes('Ocorreu um erro') || txt.includes('obrigatório')) {
                                        var btns = document.querySelectorAll('button, a');
                                        for(var b=0; b<btns.length; b++) { if((btns[b].innerText||'').includes('OK')) btns[b].click(); }
                                        return true;
                                    } return false;
                                } catch(e) { return false; }
                            """)
                            if alerta_erro: raise Exception("Servidor rejeitou a submissão. Validação falhou.")
                            
                            try:
                                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                                time.sleep(1)
                                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                            except: pass
                        else:
                            logger.info("    -> Mais valores em espera neste dia. Acionando 'Salvar e Criar Novo'...")
                            
                            salvou_novo = self.driver.execute_script("""
                                var modais = document.querySelectorAll('.k-window');
                                for(var i=0; i<modais.length; i++) {
                                    if(modais[i].style.display !== 'none' && modais[i].innerText.includes('Valor do Depósito')) {
                                        var btns = modais[i].querySelectorAll('button');
                                        for(var j=0; j<btns.length; j++) {
                                            if((btns[j].innerText || '').trim().includes('Salvar e criar novo')) {
                                                btns[j].click();
                                                return true;
                                            }
                                        }
                                    }
                                }
                                return false;
                            """)
                            
                            if not salvou_novo:
                                xpath_btn_novo = "//button[contains(translate(text(), 'NOVO', 'novo'), 'novo')]"
                                try:
                                    btn_n = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_btn_novo)))
                                    self.acoes.move_to_element(btn_n).click().perform()
                                except:
                                    self.driver.execute_script("arguments[0].click();", btn_n)

                            time.sleep(4)
                            self.driver.execute_script("document.querySelectorAll('.k-loading-mask, .k-overlay, .modal-backdrop').forEach(e => e.remove());")
                            time.sleep(1)

                break # Sai do loop de 3 tentativas com SUCESSO!
            except Exception as e:
                erro_real = str(e).split('\n')[0].strip()
                if tentativa < 2:
                    logger.warning(f"    ⚠️ Interrupção na injeção da loja: {erro_real}. Refazendo a loja...")
                else:
                    logger.error(f"    ❌ Bloqueio permanente. Pulando loja {loja}.")

    def executar(self):
        # Aqui o robô apenas puxa a variável global que criamos no início
        caminho_final = DIRETORIO_BASE
            
        logger.info(f"Procurando PDFs exatamente na pasta: {caminho_final}")
        
        arquivos_pdf = [f for f in os.listdir(caminho_final) if f.lower().endswith(".pdf")]
        
        if not arquivos_pdf:
            logger.error("NENHUM PDF ENCONTRADO NESTA PASTA.")
            return

        arquivos_pdf.sort(key=extrair_numero_do_nome)

        logger.info("=============================================")
        logger.info("⚡ INICIANDO O ROBÔ TURBO DO SICREDI ⚡")
        logger.info("=============================================")
        
        agrupamento_dias = {}
        agrupamento_lojas = {}
        
        for nome_arquivo in arquivos_pdf:
            caminho_pdf = os.path.join(caminho_final, nome_arquivo)
            resultado = extrair_dados_de_um_pdf(caminho_pdf)
            
            dia = resultado['data_util']
            if dia not in agrupamento_dias: 
                agrupamento_dias[dia] = {'lancamentos': [], 'total_pdf': 0.0}
                
            agrupamento_dias[dia]['lancamentos'].extend(resultado['lancamentos'])
            agrupamento_dias[dia]['total_pdf'] += resultado['total_pdf']

            for lanc in resultado['lancamentos']:
                loja = lanc['loja']
                if loja not in agrupamento_lojas:
                    agrupamento_lojas[loja] = {}
                if dia not in agrupamento_lojas[loja]:
                    agrupamento_lojas[loja][dia] = []
                agrupamento_lojas[loja][dia].append(lanc)

        if not self.inicializar_driver(): return
        self.fazer_login()

        from datetime import datetime
        datas_ordenadas = sorted(agrupamento_dias.keys(), key=lambda d: datetime.strptime(d, "%d/%m/%Y"))

        for dia_pt in datas_ordenadas:
            info = agrupamento_dias[dia_pt]
            lancamentos = info['lancamentos']
            soma_oficial_pdf = info['total_pdf']
            soma_lojas = sum([item['valor_float'] for item in lancamentos])
            
            soma_pdf_str = f"{soma_oficial_pdf:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            soma_robo_str = f"{soma_lojas:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            
            if abs(soma_oficial_pdf - soma_lojas) > 0.05:
                logger.warning(f"\n⚠️ ALERTA: O PDF diz R$ {soma_pdf_str}, mas o robô somou R$ {soma_robo_str}!")
            else:
                logger.info(f"\n✅ SOMA CORRETA: R$ {soma_robo_str} encontrados no PDF do dia {dia_pt}!")

        for loja, dias_da_loja in agrupamento_lojas.items():
            self.lancar_no_fechamento(loja, dias_da_loja)

        logger.info("🏁 PROCESSO TOTALMENTE FINALIZADO!")
        self.driver.quit()

# O "AIRBAG": Se der erro, não fecha a tela preta!
if __name__ == "__main__":
    try:
        verificar_permissao_diretoria("Sicredi") 
        robo = RoboSicrediAuditor()
        robo.executar()
    except Exception as e:
        logger.error(f"\n❌ Ocorreu um erro fatal: {e}")
    finally:
        input("\nPressione ENTER para fechar a tela...")